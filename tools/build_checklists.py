"""Build the built-in checklist library (checklists/<standard>/<SOI>/<DOC>.json).

Usage:
    python tools/build_checklists.py [--unical PSAC=path.xlsx SDP=path.xlsx ...]

* PSAC, SDP, SVP, SCMP, SQAP: imported from the Unical review checklist workbooks
  (check definitions only; project verdicts are not copied). Expected evidence is
  derived from the criterion; review guidance is added per sheet.
* All other data items: authored from tools/checklist_content.py (DO-178C Section 11
  and Annex A), plus generic Document Control (A) and Auditability (E) sheets.
* DO-178B: derived from the DO-178C set with DO-178C-only content removed;
  marked validated=false until checked against a DO-178B copy.
"""
from __future__ import annotations

import argparse
import copy
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.checklist_engine import SHEET_GUIDANCE, import_unical_workbook, new_item, save_builtin  # noqa: E402
from core.constants import DOCUMENT_TYPES, doc_full_name  # noqa: E402
from core.standards import objectives  # noqa: E402
from tools.checklist_content import CONTENT, D_COMMON, FAMILY, GENERIC_A, GENERIC_E  # noqa: E402

IMPORTED = ("PSAC", "SDP", "SVP", "SCMP", "SQAP")


def dal_from_levels(levels: dict) -> str:
    keys = [k for k in "ABCD" if k in levels]
    return "All" if keys == list("ABCD") else ", ".join(keys)


def conditional(dal_text: str) -> tuple[str, str, str]:
    if dal_text.lower().startswith("if"):
        return "All", "Conditional", dal_text
    return dal_text, "Mandatory", ""


def authored(doc: str, standard: str = "DO-178C") -> dict:
    soi = DOCUMENT_TYPES[doc][1]
    sec = DOCUMENT_TYPES[doc][2]
    items = []
    for i, (section, q, ev, ref, dal, guid, rule) in enumerate(GENERIC_A, 1):
        items.append(new_item(ref=f"A-{i:02d}", sheet="A", group="1.1 Identification and document control",
                              section=section, question=q, expected_evidence=ev, reference=ref, dal=dal,
                              guidance=guid or SHEET_GUIDANCE["A"], rule=rule))
    for i, (section, q, ev, ref, dal, guid) in enumerate(CONTENT[doc]["B"], 1):
        d, appl, cond = conditional(dal)
        items.append(new_item(ref=f"B-{i:02d}", sheet="B", group=f"2.1 Required content - DO-178C {sec}",
                              section=section, question=q, expected_evidence=ev, reference=ref, dal=d,
                              applicability=appl, condition=cond, guidance=guid or SHEET_GUIDANCE["B"]))
    n = 0
    for obj in objectives("DO-178C"):
        if doc in obj["outputs"]:
            n += 1
            indep = [k for k, v in obj["levels"].items() if v == "I"]
            note = f" Independence required at level(s) {', '.join(indep)}." if indep else ""
            items.append(new_item(
                ref=f"C-{n:02d}", sheet="C", group=f"3.1 DO-178C Annex A objectives supported by the {doc}",
                section=obj["ref"], question=f"{obj['description']} - the {doc} provides the evidence this objective "
                                             f"needs at the declared level.{note}",
                expected_evidence=f"Content in the {doc} that substantiates {obj['table']} objective {obj['number']} "
                                  f"(DO-178C {obj['ref']}).",
                reference=f"DO-178C Table {obj['table']} obj.{obj['number']} ({obj['ref']})",
                dal=dal_from_levels(obj["levels"]), guidance=SHEET_GUIDANCE["C"]))
    for i, (section, q, ev, ref, dal, guid) in enumerate(D_COMMON[FAMILY[doc]], 1):
        items.append(new_item(ref=f"D-{i:02d}", sheet="D", group="4.1 Consistency with companion data", section=section,
                              question=q, expected_evidence=ev, reference=ref, dal=dal,
                              guidance=guid or SHEET_GUIDANCE["D"]))
    for i, (section, q, ev, ref, dal, guid, rule) in enumerate(GENERIC_E, 1):
        items.append(new_item(ref=f"E-{i:02d}", sheet="E", group="5.1 Language, clarity and auditability",
                              section=section, question=q, expected_evidence=ev, reference=ref, dal=dal,
                              guidance=guid or SHEET_GUIDANCE["E"], rule=rule))
    for i, (section, q, ev, ref, dal, guid) in enumerate(CONTENT[doc]["F"], 1):
        d, appl, cond = conditional(dal)
        items.append(new_item(ref=f"F-{i:02d}", sheet="F", group="6.1 Engineering content depth", section=section,
                              question=q, expected_evidence=ev, reference=ref, dal=d, applicability=appl,
                              condition=cond, guidance=guid or SHEET_GUIDANCE["F"]))
    return {"id": f"{standard}_{soi}_{doc}", "name": f"{doc_full_name(doc)} ({doc}) Review Checklist",
            "standard": standard, "soi": soi, "document_type": doc, "version": "1.0", "source": "Built-in",
            "origin": f"Authored by Unical from DO-178C Section {sec} content, Annex A objectives and Unical IV&V "
                      f"practice", "validated": True, "items": items}


def enrich_imported(cl: dict) -> dict:
    for it in cl["items"]:
        if not it["expected_evidence"]:
            crit = re.sub(r"\s+", " ", it["question"])
            it["expected_evidence"] = "Text in the document that shows: " + crit[0].lower() + crit[1:]
    cl["name"] = f"{doc_full_name(cl['document_type'])} ({cl['document_type']}) Review Checklist"
    return cl


DO178C_ONLY = re.compile(r"DO-33[0-3]|parameter data item|\bPDI\b|11\.2[12]\b|\b6\.6\b|trace data|supplement|"
                         r"model-based|object-oriented|formal method", re.I)


def derive_178b(cl: dict) -> dict | None:
    if cl["document_type"] == "TRACE":
        return None  # DO-178B has no separate Trace Data item (traceability is part of verification results)
    b = copy.deepcopy(cl)
    b["standard"] = "DO-178B"
    b["id"] = b["id"].replace("DO-178C", "DO-178B")
    b["validated"] = False
    b["origin"] = ("Derived from the DO-178C checklist: DO-178C-only content removed. Section references to be "
                   "confirmed against RTCA DO-178B by the IV&V Lead.")
    keep = []
    for it in b["items"]:
        text = f"{it['question']} {it['reference']}"
        if DO178C_ONLY.search(text):
            continue
        if it["sheet"] == "C":
            continue  # Annex A objectives differ in DO-178B; not encoded until a DO-178B copy is available
        for k in ("group", "section", "question", "reference", "expected_evidence", "guidance"):
            it[k] = it[k].replace("DO-178C", "DO-178B")
        keep.append(it)
    b["items"] = keep
    return b


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unical", nargs="*", default=[], help="DOC=path.xlsx pairs for the imported plan checklists")
    args = ap.parse_args()
    sources = dict(a.split("=", 1) for a in args.unical)
    built = []
    for doc in IMPORTED:
        if doc in sources:
            cl = enrich_imported(import_unical_workbook(sources[doc], "DO-178C", "SOI-1", doc))
            save_builtin(cl, ROOT / "checklists")
            built.append(cl)
    for doc in CONTENT:
        cl = authored(doc)
        save_builtin(cl, ROOT / "checklists")
        built.append(cl)
    # existing imported files that were not re-imported this run
    for doc in IMPORTED:
        if doc not in sources:
            f = ROOT / "checklists" / "DO-178C" / "SOI-1" / f"{doc}.json"
            if f.exists():
                import json
                built.append(json.loads(f.read_text(encoding="utf-8")))
    for cl in built:
        b = derive_178b(cl)
        if b:
            save_builtin(b, ROOT / "checklists")
    for cl in built:
        print(f"{cl['standard']} {cl['soi']} {cl['document_type']:5} {len(cl['items']):4d} items")


if __name__ == "__main__":
    main()
