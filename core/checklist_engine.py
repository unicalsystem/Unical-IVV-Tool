"""Checklist engine: built-in checklists, Unical workbook import, user-uploaded checklists,
checklist modes (built-in / user / combined) and DAL applicability.

A checklist is a dict:
    {"id", "name", "standard", "soi", "document_type", "version", "source", "origin",
     "validated", "items": [item, ...]}
An item is a dict with the keys in ITEM_KEYS. Original wording of user checklists
is preserved exactly; only whitespace at the ends is trimmed.
"""
from __future__ import annotations

import copy
import json
import logging
import re
from pathlib import Path
from typing import Any

from core.app_context import bundled_resource
from core.constants import DOCUMENT_TYPES, SHEETS
from core.standards import dal_applies

log = logging.getLogger(__name__)

ITEM_KEYS = ("ref", "sheet", "group", "section", "question", "expected_evidence", "reference", "dal",
             "applicability", "condition", "guidance", "rule")

SHEET_GUIDANCE = {
    "A": "Check the front matter and identification against the authority template. Record exactly what is on the "
         "page (quote it) and where.",
    "B": "Locate the clause required by the template / DO-178 Section 11 for this data item. 'Present' means the "
         "content exists with enough detail to be used; a heading with no content is Partially Compliant.",
    "C": "Confirm the document provides what the DO-178 objective needs at the declared level. Missing evidence in "
         "this document is not proof that the activity was not done - say what is missing and where it should be.",
    "D": "Compare identifiers, versions, roles, tools and statements with the companion documents. If a companion "
         "document was not supplied, record 'could not verify' rather than a non-compliance.",
    "E": "Judge whether an auditor could check compliance from the text: committal language, named roles, records "
         "and timing, consistent terminology.",
    "F": "Judge the engineering depth: is the content specific to this product and sufficient for the declared "
         "level, or generic text that cannot be verified?",
}

RULE_PATTERNS = [  # order matters: first match wins
    ("cover_title", r"cover.*title|title.*cover|cover page"),
    ("version_date", r"issue no|issue date|issue / revision|revision (?:no|number)|version and date"),
    ("doc_number", r"document number|doc(?:ument)?\.? no|numbering format|unique (?:document )?number"),
    ("states_dal", r"(software|criticality) level.*(declared|stated)|level [a-e] .*declared|\bdal\b.*declared"),
    ("signatories", r"signat|approval block|prepared by|approved by"),
    ("page_numbering", r"page (?:x|\d+) of|pages?.*number|no\.? of pages"),
    ("revision_history", r"revision history|amendment history|record of revisions"),
    ("toc", r"table of contents|\bcontents\b"),
    ("abbreviations", r"acronym|abbreviation"),
    ("no_placeholders", r"tbd|tbc|placeholder|unresolved|error! reference"),
    ("classification", r"security classification|classification field|restricted|confidential marking"),
    ("committal_language", r"committal|'shall'|“shall”"),
    ("figures_tables", r"figures? and tables?.*number|numbered.*(figures|tables)"),
]


def guess_rule(question: str, sheet: str) -> str | None:
    if sheet not in ("A", "E"):
        return None
    q = question.lower()[:80]  # the subject of a check is stated at its start
    for rule, pat in RULE_PATTERNS:
        if re.search(pat, q):
            return rule
    return None


def new_item(**kw: Any) -> dict:
    item = {k: "" for k in ITEM_KEYS}
    item.update({k: v for k, v in kw.items() if k in ITEM_KEYS and v is not None})
    item["dal"] = item["dal"] or "All"
    item["applicability"] = item["applicability"] or "Mandatory"
    item["rule"] = item["rule"] or None
    return item


def applicability_from_level(level_text: str) -> tuple[str, str, str]:
    """Split Unical 'Level Applicability' into (dal, applicability, condition)."""
    t = (level_text or "All").strip()
    if t.lower().startswith("if ") or t.lower() in ("if applicable", "if used", "if claimed"):
        return "All", "Conditional", t
    if t.lower() == "mixed dal":
        return "All", "Conditional", "If more than one software level is used"
    return t, "Mandatory", ""


# ------------------------------------------------------------------------------ built-in
USER_ROOT: Path | None = None  # writable override folder (edited / imported checklists), set by the app


def set_user_root(path: Path | None) -> None:
    global USER_ROOT
    USER_ROOT = path


def checklists_root() -> Path:
    return bundled_resource("checklists")


def builtin_path(standard: str, soi: str, doc_type: str) -> Path:
    if USER_ROOT is not None:
        f = USER_ROOT / standard / soi / f"{doc_type}.json"
        if f.exists():
            return f
    return checklists_root() / standard / soi / f"{doc_type}.json"


def list_builtin() -> list[dict]:
    out = []
    files: dict[str, Path] = {}
    for root in [checklists_root()] + ([USER_ROOT] if USER_ROOT else []):
        if root and root.exists():
            for f in root.glob("*/*/*.json"):
                files[str(f.relative_to(root))] = f  # user copy overrides the bundled one
    for _, f in sorted(files.items()):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.error("Bad checklist file %s: %s", f, exc)
            continue
        out.append({k: data.get(k) for k in ("id", "name", "standard", "soi", "document_type", "version", "origin",
                                             "validated")} | {"items": len(data.get("items", [])), "path": str(f),
                                                              "edited": USER_ROOT is not None and USER_ROOT in f.parents})
    return out


def load_builtin(standard: str, soi: str, doc_type: str) -> dict | None:
    f = builtin_path(standard, soi, doc_type)
    if not f.exists():
        # a document type may be reviewed at a later SOI with the checklist of its home SOI
        home = DOCUMENT_TYPES.get(doc_type, ("", soi))[1]
        f = builtin_path(standard, home, doc_type)
        if not f.exists():
            return None
    data = json.loads(f.read_text(encoding="utf-8"))
    data["source"] = "Built-in"
    return data


def save_builtin(checklist: dict, root: Path | None = None) -> Path:
    root = root or USER_ROOT or checklists_root()
    f = root / checklist["standard"] / checklist["soi"] / f"{checklist['document_type']}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(checklist, indent=1, ensure_ascii=False), encoding="utf-8")
    return f


# ------------------------------------------------------------------- Unical workbook import
UNICAL_SHEET = re.compile(r"^([A-F])\.\s")
CHECK_ID = re.compile(r"^([A-F])-(\d+)\s*$")
GENERICISE = [
    (r"\bAeron(?:'s|’s)?\b", "the applicant"),
    (r"\b(?:GLO-MSU11-D|ALD-ASM40)\b", "the LRU"),
    (r"\bMSU\b", "the LRU"),
    (r"\bASM\b", "the LRU"),
    (r"\bLCH\b", "the platform"),
]


def genericise(text: str) -> str:
    for pat, rep in GENERICISE:
        text = re.sub(pat, rep, text)
    return text


def import_unical_workbook(path: str | Path, standard: str, soi: str, doc_type: str,
                           name: str | None = None, strip_project_terms: bool = True) -> dict:
    """Read a Unical IV&V review checklist workbook (sheets 'A. ...' to 'F. ...').

    Only the check definition columns are taken (ID, clause, criterion, reference,
    level applicability). Verdicts, observations and recommendations of the
    earlier project review are deliberately ignored.
    """
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True, read_only=True)
    items: list[dict] = []
    for ws in wb.worksheets:
        m = UNICAL_SHEET.match(ws.title)
        if not m:
            continue
        sheet = m.group(1)
        group = ""
        header_seen = False
        for row in ws.iter_rows(values_only=True):
            first = str(row[0]).strip() if row and row[0] is not None else ""
            if first.lower().startswith("check id"):
                header_seen = True
                continue
            if not header_seen or not first:
                continue
            cid = CHECK_ID.match(first)
            if cid:
                clause = str(row[1] or "").strip()
                question = str(row[2] or "").strip()
                if not question:
                    continue
                reference = str(row[3] or "").strip()
                dal, appl, cond = applicability_from_level(str(row[4] or "All"))
                if strip_project_terms:
                    question, reference = genericise(question), genericise(reference)
                items.append(new_item(ref=f"{sheet}-{int(cid.group(2)):02d}", sheet=sheet, group=group,
                                      section=clause, question=question, reference=reference, dal=dal,
                                      applicability=appl, condition=cond, guidance=SHEET_GUIDANCE[sheet],
                                      rule=guess_rule(question, sheet)))
            elif not any(row[1:4]):
                group = first  # group heading row such as '2.1 Section 1 - Introduction'
    wb.close()
    if not items:
        raise ValueError("No checks found. Expected Unical checklist sheets named 'A. ...' to 'F. ...' with a "
                         "'Check ID' header row.")
    return {"id": f"{standard}_{soi}_{doc_type}", "name": name or f"{doc_type} Review Checklist", "standard": standard,
            "soi": soi, "document_type": doc_type, "version": "1.0", "source": "Built-in",
            "origin": "Imported from Unical review checklist " + (
                re.search(r"UNI-CHK-[A-Z0-9]+-\d+", Path(path).name) or re.search(r".*", Path(path).stem)).group(0), "validated": True, "items": items}


# --------------------------------------------------------------------- user checklists
HEADER_HINTS = {
    "ref": ("check id", "checklist id", "id", "s.no", "sl", "sl.no", "item", "no.", "ref"),
    "question": ("check / acceptance criterion", "acceptance criterion", "review question", "question", "check",
                 "criterion", "checklist item", "requirement", "description", "check item"),
    "section": ("section", "clause", "section number", "template ref"),
    "section_title": ("section title", "heading"),
    "reference": ("reference", "reference std", "standard reference", "objective", "do-178"),
    "expected_evidence": ("expected evidence", "evidence"),
    "dal": ("level applicability", "dal", "level", "applicability"),
    "guidance": ("guidance", "review guidance", "how to check"),
}


def _match_header(cells: list[str]) -> dict[str, int] | None:
    norm = [re.sub(r"\s+", " ", (c or "").strip().lower()) for c in cells]
    mapping: dict[str, int] = {}
    for key, hints in HEADER_HINTS.items():
        for i, cell in enumerate(norm):
            if not cell or i in mapping.values():
                continue
            if any(cell == h or cell.startswith(h) for h in hints):
                mapping.setdefault(key, i)
                break
    return mapping if "question" in mapping else None


def _rows_to_items(rows: list[list[str]], sheet_label: str) -> list[dict]:
    items: list[dict] = []
    header = None
    for row in rows:
        cells = ["" if c is None else str(c) for c in row]
        if header is None:
            header = _match_header(cells)
            continue
        q = cells[header["question"]].strip() if header["question"] < len(cells) else ""
        if not q or len(q) < 8:
            continue
        get = lambda k: cells[header[k]].strip() if k in header and header[k] < len(cells) else ""
        dal, appl, cond = applicability_from_level(get("dal") or "All")
        items.append(new_item(ref=get("ref") or f"U-{len(items) + 1:03d}", sheet="U", group=sheet_label,
                              section=get("section"), question=q, reference=get("reference"),
                              expected_evidence=get("expected_evidence"), dal=dal, applicability=appl,
                              condition=cond, guidance=get("guidance")))
    return items


def read_user_checklist(path: str | Path) -> dict:
    """Read a user checklist (XLSX, DOCX or PDF) and keep the original wording."""
    p = Path(path)
    ext = p.suffix.lower()
    items: list[dict] = []
    if ext == ".xlsx":
        from openpyxl import load_workbook
        if any(UNICAL_SHEET.match(n) for n in load_workbook(p, read_only=True).sheetnames):
            data = import_unical_workbook(p, "DO-178C", "SOI-1", "USER", p.stem, strip_project_terms=False)
            for it in data["items"]:
                it["guidance"] = it["guidance"] or SHEET_GUIDANCE.get(it["sheet"], "")
            items = data["items"]
        else:
            wb = load_workbook(p, data_only=True, read_only=True)
            for ws in wb.worksheets:
                items += _rows_to_items([list(r) for r in ws.iter_rows(values_only=True)], ws.title)
            wb.close()
    elif ext == ".docx":
        from docx import Document
        d = Document(str(p))
        for ti, t in enumerate(d.tables, 1):
            rows = [[c.text for c in r.cells] for r in t.rows]
            items += _rows_to_items(rows, f"Table {ti}")
    elif ext == ".pdf":
        import pymupdf
        doc = pymupdf.open(str(p))
        pat = re.compile(r"^\s*((?:[A-Z]{1,4}-)?\d+(?:\.\d+)*[.)]?)\s+(.{10,})$")
        for page in doc:
            for line in page.get_text().splitlines():
                m = pat.match(line)
                if m:
                    items.append(new_item(ref=m.group(1).rstrip(".)"), sheet="U", group=f"Page {page.number + 1}",
                                          question=m.group(2).strip()))
        doc.close()
    else:
        raise ValueError(f"Unsupported checklist format: {ext} (use XLSX, DOCX or PDF)")
    if not items:
        raise ValueError("No checklist items could be read. The checklist needs a header row with a question / "
                         "criterion column (XLSX or DOCX table), or numbered lines (PDF).")
    seen: set[str] = set()
    for it in items:  # make refs unique while keeping the user's IDs
        base, n = it["ref"], 2
        while it["ref"] in seen:
            it["ref"] = f"{base}#{n}"
            n += 1
        seen.add(it["ref"])
    return {"id": f"USER_{p.stem}", "name": p.stem, "standard": "", "soi": "", "document_type": "",
            "version": "user", "source": "User", "origin": f"User checklist {p.name}", "validated": False,
            "items": items}


# ---------------------------------------------------------------- combination / filtering
def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{4,}", text.lower())}


def combine(builtin: dict | None, user: dict | None, mode: str) -> dict:
    """mode: 'Built-in', 'User' or 'Combined'. Combined = user items first, then built-in items not duplicated."""
    if mode == "User" or builtin is None:
        if user is None:
            raise ValueError("No user checklist supplied.")
        return copy.deepcopy(user)
    if mode == "Built-in" or user is None:
        return copy.deepcopy(builtin)
    out = copy.deepcopy(user)
    out["name"] = f"{user['name']} + {builtin['name']}"
    out["source"] = "Combined"
    user_tokens = [_tokens(i["question"]) for i in user["items"]]
    for it in builtin["items"]:
        t = _tokens(it["question"])
        dup = any(t and len(t & u) / max(1, len(t | u)) >= 0.6 for u in user_tokens)
        if not dup:
            out["items"].append(copy.deepcopy(it))
    return out


def applicability_for(item: dict, dal: str) -> tuple[bool, str]:
    """(applies, reason). DAL E: DO-178 objectives are not applicable."""
    if dal == "E":
        return False, "Software level E: DO-178B/C objectives are not applicable."
    if item.get("applicability") == "Not Applicable":
        return False, "Marked Not Applicable in the checklist."
    if not dal_applies(item.get("dal", "All"), dal):
        return False, f"Check applies to level(s) {item.get('dal')} only; declared level is {dal}."
    return True, ""


def sheet_title(code: str) -> str:
    return SHEETS.get(code, "User Checklist")
