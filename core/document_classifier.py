"""Content-based document identification and relevance validation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.constants import DOCUMENT_TYPES
from core.document_parser import ParsedDocument

# (title patterns - strong), (body / heading terms - supporting)
SIGNATURES: dict[str, tuple[list[str], list[str]]] = {
    "PSAC": ([r"plan for software aspects of certification", r"\bPSAC\b"],
             [r"certification considerations", r"system overview", r"software overview", r"means of compliance",
              r"stage of involvement|\bSOI\b", r"certification liaison", r"schedule", r"additional considerations"]),
    "SDP": ([r"software development plan", r"\bSDP\b"],
            [r"development environment", r"requirements process", r"design process", r"coding process",
             r"integration process", r"transition criteria", r"compiler"]),
    "SVP": ([r"software verification plan", r"\bSVP\b"],
            [r"verification environment", r"independence", r"structural coverage", r"robustness", r"test cases",
             r"reverification", r"partitioning"]),
    "SCMP": ([r"software configuration management plan", r"\bSCMP\b|\bSCM plan\b"],
             [r"configuration identification", r"baseline", r"change control", r"problem report", r"archive",
              r"status accounting", r"load control", r"control categor"]),
    "SQAP": ([r"software quality assurance plan", r"\bSQAP\b|\bSQA plan\b"],
             [r"quality assurance", r"audit", r"conformity review", r"sqa records", r"independence",
              r"transition criteria"]),
    "SRS": ([r"software requirements? standards?"], [r"requirements notation", r"derived requirements", r"shall"]),
    "SDS": ([r"software design standards?"], [r"naming convention", r"complexity", r"recursion", r"design method"]),
    "SCS": ([r"(software )?cod(e|ing) standards?"], [r"misra", r"naming convention", r"indentation", r"language subset",
                                                    r"compiler"]),
    "IVVP": ([r"independent verification and validation plan", r"\bIV&?V plan\b|\bIVVP\b"],
             [r"independence", r"review checklist", r"finding", r"iv&v"]),
    "SRD": ([r"software requirements? (data|document|specification)", r"\bSRD\b|\bSRS\b"],
            [r"\bhlr\b|high[- ]level requirement", r"shall", r"derived requirement", r"interface requirement"]),
    "SDD": ([r"software design (description|document)", r"\bSDD\b"],
            [r"low[- ]level requirement|\bllr\b", r"architecture", r"data flow", r"control flow", r"module",
             r"memory map"]),
    "CODE": ([r"code review", r"source code"], [r"function", r"misra", r"static analysis", r"#include|void\s+\w+\("]),
    "TRACE": ([r"trace(ability)? (data|matrix)", r"\bRTM\b"], [r"trace", r"hlr", r"llr", r"test case"]),
    "SVCP": ([r"software verification cases and procedures", r"\bSVCP\b|test procedures?"],
             [r"test case", r"expected result", r"pass/fail|pass / fail", r"test procedure", r"input"]),
    "SVR": ([r"software verification results?", r"\bSVR\b|test report"],
            [r"pass", r"fail", r"coverage", r"result", r"discrepanc"]),
    "PR": ([r"problem reports?", r"\bPR\b"], [r"corrective action", r"status", r"closed|open"]),
    "SCI": ([r"software configuration index", r"\bSCI\b"], [r"part number", r"executable", r"checksum|crc",
                                                            r"build instructions?"]),
    "SECI": ([r"(software )?life cycle environment configuration index", r"\bSECI\b"],
             [r"compiler", r"linker", r"tool", r"version", r"operating system"]),
    "SAS": ([r"software accomplishment summary", r"\bSAS\b"],
            [r"compliance statement", r"software status", r"software characteristics", r"change history"]),
    "SCMR": ([r"configuration management records?", r"\bSCMR\b"], [r"baseline", r"release", r"archive"]),
    "SQAR": ([r"quality assurance records?", r"\bSQAR\b", r"conformity review report"], [r"audit", r"finding"]),
}

CERT_TERMS = [r"DO[\s-]?178", r"software level|design assurance level|\bDAL\b", r"certification", r"verification",
              r"configuration management", r"quality assurance", r"requirements?", r"airborne", r"RTCA",
              r"CEMILAC|RCMA|EASA|FAA", r"traceab", r"\bSOI\b|stage of involvement", r"test case", r"baseline"]


@dataclass
class Classification:
    best: str | None
    confidence: float
    ranking: list[tuple[str, float]] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


def classify(doc: ParsedDocument) -> Classification:
    head = (doc.title + "\n" + "\n".join(doc.page_texts[:2]))[:5000]
    body = doc.text[:400000]
    headings = " ".join(s.title for s in doc.sections)
    scores: dict[str, float] = {}
    evidence: dict[str, list[str]] = {}
    for code, (titles, terms) in SIGNATURES.items():
        s, ev = 0.0, []
        for i, pat in enumerate(titles):
            if re.search(pat, head, re.I):
                s += 6.0 if i == 0 else 2.0
                ev.append(f"title/front page matches '{pat}'")
        for pat in terms:
            n = len(re.findall(pat, body, re.I))
            if n:
                s += min(2.0, 0.4 + 0.2 * n)
            if re.search(pat, headings, re.I):
                s += 0.8
                ev.append(f"heading mentions '{pat}'")
        scores[code] = s
        evidence[code] = ev
    ranking = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best, top = ranking[0]
    second = ranking[1][1] if len(ranking) > 1 else 0.0
    if top < 3.0:
        return Classification(None, 0.0, ranking[:5], ["No data-item signature found in the document content."])
    conf = round(min(1.0, (top - second) / max(top, 1e-6) + (0.4 if top >= 8 else 0.0)), 2)
    return Classification(best, conf, ranking[:5], evidence[best])


@dataclass
class Relevance:
    ok: bool
    messages: list[str]
    certification_score: int
    detected_type: str | None
    type_matches_selection: bool
    soi_matches: bool
    standard_conflict: bool
    dal_conflict: bool


def check_relevance(doc: ParsedDocument, selected_type: str, soi: str, standard: str, dal: str) -> Relevance:
    msgs: list[str] = []
    text = doc.text[:400000]
    cert_score = sum(1 for pat in CERT_TERMS if re.search(pat, text, re.I))
    cls = classify(doc)
    ok = True
    if cert_score < 4:
        ok = False
        msgs.append("The document does not appear to be airborne-software certification data (few DO-178 / "
                    "certification terms found). Check that the correct file was uploaded.")
    type_match = cls.best == selected_type or selected_type in [c for c, s in cls.ranking[:2] if s >= 3]
    if cls.best and not type_match:
        msgs.append(f"Selected document type is {selected_type}, but the content looks like "
                    f"{cls.best} ({DOCUMENT_TYPES.get(cls.best, (cls.best,))[0]}). Confirm the type or change the "
                    f"selection.")
    if cls.best is None:
        msgs.append("The document type could not be identified from the content; the selected type will be used.")
    soi_ok = True
    if cls.best and DOCUMENT_TYPES.get(cls.best, ("", soi))[1] != soi and not type_match:
        soi_ok = False
        msgs.append(f"{cls.best} normally belongs to {DOCUMENT_TYPES[cls.best][1]}, not {soi}.")
    std_conflict = bool(doc.standard_mentions) and standard not in doc.standard_mentions
    if std_conflict:
        msgs.append(f"The document refers to {', '.join(doc.standard_mentions)} but {standard} was selected.")
    dal_conflict = bool(doc.dal_mentions) and dal not in doc.dal_mentions and len(doc.dal_mentions) == 1
    if dal_conflict:
        msgs.append(f"The document states software level {doc.dal_mentions[0]} but DAL {dal} was selected.")
    if ok and not msgs:
        msgs.append(f"Identified as {cls.best or selected_type} (confidence {cls.confidence:.0%}); consistent with "
                    f"the selection.")
    return Relevance(ok, msgs, cert_score, cls.best, type_match, soi_ok, std_conflict, dal_conflict)
