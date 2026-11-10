"""Cross-document consistency (Stage 4) and requirement-ID trace analysis."""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.document_parser import ParsedDocument

TOOL_RE = re.compile(r"\b(VectorCAST|LDRA(?:\s+TBrun)?|Polyspace|PC-?lint(?:\s+Plus)?|Cantata|DOORS(?:\s+Next)?|"
                     r"STM32CubeIDE|STM32CubeMX|STM32CubeProgrammer|IAR(?:\s+Embedded\s+Workbench)?|Keil(?:\s+MDK)?|"
                     r"GCC|arm-none-eabi-gcc|Code\s*Composer\s*Studio|MATLAB|Simulink|SCADE|Git|SVN|Subversion|"
                     r"Jira|Redmine|QAC|Helix\s+QAC|Coverity|Understand|Klocwork|Tessy|RapiCover)\b"
                     r"[\s:,(]*(?:v(?:ersion)?\.?\s*)?([0-9]+(?:\.[0-9]+){0,3}[a-z]?)?", re.I)
DOCNUM_CANDIDATE = re.compile(r"\b(\d{9,16}|[A-Z]{2,6}[-_/][A-Z0-9]{2,}[-_/][A-Z0-9\-_/]{2,30})\b")
REQ_ID = re.compile(r"\b([A-Z][A-Z0-9]{1,12}[-_](?:[A-Z]{2,6}[-_])?\d{2,6})\b")


@dataclass
class ConsistencyResult:
    topic: str
    description: str
    primary_value: str
    companion: str
    companion_value: str
    status: str  # Consistent / Inconsistent / Could not verify
    evidence: str = ""


def tools_in(doc: ParsedDocument) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for m in TOOL_RE.finditer(doc.text):
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        key = name.lower().replace("-", "")
        out.setdefault(key, set())
        if m.group(2):
            out[key].add(m.group(2))
    return out


def _short(doc: ParsedDocument) -> str:
    from pathlib import Path
    return Path(doc.path).name


def compare(primary: ParsedDocument, primary_type: str, companions: list[tuple[str, ParsedDocument]],
            selected_dal: str, selected_standard: str) -> list[ConsistencyResult]:
    res: list[ConsistencyResult] = []
    # --- software level and standard against the selection (always possible)
    if primary.dal_mentions:
        st = "Consistent" if primary.dal_mentions == [selected_dal] else "Inconsistent"
        res.append(ConsistencyResult("dal", "Software level stated in the document vs level selected for review",
                                     ", ".join(primary.dal_mentions), "Review selection", selected_dal, st))
    if primary.standard_mentions:
        st = "Consistent" if selected_standard in primary.standard_mentions else "Inconsistent"
        res.append(ConsistencyResult("standard", "Certification standard stated vs selected",
                                     ", ".join(primary.standard_mentions), "Review selection", selected_standard, st))
    for ctype, comp in companions:
        name = f"{ctype} ({_short(comp)})"
        # software level
        if primary.dal_mentions and comp.dal_mentions:
            st = "Consistent" if set(primary.dal_mentions) == set(comp.dal_mentions) else "Inconsistent"
            res.append(ConsistencyResult("dal", "Software level", ", ".join(primary.dal_mentions), name,
                                         ", ".join(comp.dal_mentions), st))
        # companion document number quoted in primary
        if comp.doc_number:
            hits = primary.find(re.escape(comp.doc_number), limit=1)
            if hits:
                res.append(ConsistencyResult("doc_number", f"Document number of the {ctype} quoted in the {primary_type}",
                                             comp.doc_number, name, comp.doc_number, "Consistent",
                                             f"Page {hits[0][0]}: {hits[0][1]}" if hits[0][0] else hits[0][1]))
            else:
                mention = primary.find(rf"\b{ctype}\b", limit=1)
                ev = f"Page {mention[0][0]}: {mention[0][1]}" if mention and mention[0][0] else (mention[0][1] if mention else "")
                res.append(ConsistencyResult("doc_number", f"Document number of the {ctype} quoted in the {primary_type}",
                                             f"refers to the {ctype} without its document number" if mention
                                             else f"does not refer to the {ctype}", name,
                                             comp.doc_number, "Inconsistent" if mention else "Could not verify", ev))
        # issue / version quoted
        if comp.doc_number and comp.version:
            ctx = primary.find(re.escape(comp.doc_number) + r".{0,80}", limit=1)
            if ctx:
                v = re.escape(comp.version.lstrip("0") or comp.version)
                v_ok = re.search(rf"\b(?:v|ver|version|issue|rev(?:ision)?(?:\s*no)?)\.?\s*[:\-]?\s*0?{v}(?:\.0)?\b",
                                 ctx[0][1], re.I)
                res.append(ConsistencyResult("version", f"Issue of the {ctype} quoted in the {primary_type}",
                                             ctx[0][1][:120], name, comp.version,
                                             "Consistent" if v_ok else "Could not verify", ctx[0][1][:200]))
        # tools and versions
        pt, ct = tools_in(primary), tools_in(comp)
        for tool in sorted(set(pt) & set(ct)):
            if pt[tool] and ct[tool]:
                st = "Consistent" if pt[tool] & ct[tool] else "Inconsistent"
                res.append(ConsistencyResult("tool_version", f"Tool version: {tool.title()}", ", ".join(sorted(pt[tool])),
                                             name, ", ".join(sorted(ct[tool])), st))
    return res


def referenced_documents_not_supplied(primary: ParsedDocument, companions: list[tuple[str, ParsedDocument]]) -> list[str]:
    """Plan/data-item abbreviations mentioned in the document whose files were not uploaded."""
    supplied = {c for c, _ in companions}
    out = []
    for abbr in ("PSAC", "SDP", "SVP", "SCMP", "SQAP", "SRD", "SDD", "SVCP", "SVR", "SCI", "SECI", "SAS"):
        if abbr not in supplied and re.search(rf"\b{abbr}\b", primary.text):
            out.append(abbr)
    return out


def requirement_ids(doc: ParsedDocument) -> set[str]:
    return set(REQ_ID.findall(doc.text))


def trace_analysis(upstream: ParsedDocument, downstream: ParsedDocument) -> dict:
    """IDs of the upstream document that are / are not referenced in the downstream document."""
    up = {i for i in requirement_ids(upstream) if not re.search(r"\d{9,}", i)}
    down_text = downstream.text
    covered = {i for i in up if i in down_text}
    return {"upstream_ids": len(up), "referenced": len(covered), "not_referenced": sorted(up - covered)[:200]}
