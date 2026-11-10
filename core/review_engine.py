"""IV&V review engine (Phase 5): structure review, checklist assessment (rule-based and
optional local AI), cross-document consistency, finding generation and severity.

Every applicable checklist item receives a proposed verdict (C / PC / NC / NA / NR):
deterministic rules for document-control checks, the evidence assessor (concept coverage
with quoted text) for the others, or the local AI when enabled. Every proposed finding
carries the evidence (quote and page/section) or states that no evidence was found, and
every finding is a Draft until a reviewer approves it.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from core.checklist_engine import applicability_for
from core.constants import DOCUMENT_TYPES, doc_full_name
from core.document_parser import ParsedDocument
from core.evidence_assessor import EvidenceAssessor
from core.severity_classifier import SeverityClassifier
from core.traceability_engine import ConsistencyResult, compare, referenced_documents_not_supplied

log = logging.getLogger(__name__)

STOP = set("""the a an and or of to in for on by with is are be shall should will this that these those each every
any all from as at it its into their there where which when what who how not no than then also such such other
been being has have had was were document plan data software""".split())

# Structural elements expected per data item (DO-178C Section 11 headings; informational)
EXPECTED_SECTIONS = {
    "PSAC": ["system overview", "software overview", "certification considerations", "software life cycle",
             "software life cycle data", "schedule", "additional considerations", "supplier oversight"],
    "SDP": ["standards", "software life cycle", "development environment", "requirements process", "design process",
            "coding process", "integration process", "transition criteria"],
    "SVP": ["organization|organisation", "independence", "verification methods", "verification environment",
            "transition criteria", "partitioning", "reverification", "previously developed", "multiple-version"],
    "SCMP": ["environment", "configuration identification", "baselines", "problem report", "change control",
             "change review", "status accounting", "archive", "load control", "life cycle environment control",
             "transition criteria", "supplier"],
    "SQAP": ["environment", "authority", "activities", "transition criteria", "timing", "records", "supplier"],
    "SRS": ["methods", "notation", "tools", "derived requirements"],
    "SDS": ["design description method", "naming", "constraints", "complexity"],
    "SCS": ["language", "presentation", "naming", "constraints", "tools"],
    "SRD": ["interface", "performance", "timing", "memory", "failure detection|monitoring", "mode"],
    "SDD": ["architecture", "data flow", "control flow", "resource", "scheduling|interrupt", "partitioning",
            "derived requirements"],
    "SVCP": ["test case", "test procedure", "expected result", "pass", "environment"],
    "SVR": ["result", "coverage", "traceab", "discrepanc|problem report"],
    "SCI": ["executable object code", "source code", "life cycle data", "build", "load"],
    "SECI": ["hardware", "operating system", "compiler|tools", "test environment|verification tools", "qualified"],
    "SAS": ["system overview", "software overview", "certification considerations", "software life cycle",
            "software identification", "software characteristics", "change history", "software status",
            "compliance statement"],
}


@dataclass
class Assessment:
    item: dict
    verdict: str = "NR"
    evidence_state: str = "Cannot Verify"
    observation: str = ""
    evidence: str = ""
    page_ref: str = ""
    recommendation: str = ""
    origin: str = "Rule"
    applicable: bool = True
    na_reason: str = ""


@dataclass
class ProposedFinding:
    severity: str
    rationale: str
    observation: str
    recommendation: str
    evidence: str
    page_ref: str
    section: str
    reference: str
    checks: list[int]  # indexes into ReviewResult.assessments
    origin: str = "Rule"


@dataclass
class ReviewResult:
    assessments: list[Assessment] = field(default_factory=list)
    findings: list[ProposedFinding] = field(default_factory=list)
    structure: list[dict] = field(default_factory=list)
    consistency: list[ConsistencyResult] = field(default_factory=list)
    not_supplied: list[str] = field(default_factory=list)
    analysis_mode: str = "Rule-based"
    notes: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        c = Counter(a.verdict for a in self.assessments)
        return {k: c.get(k, 0) for k in ("C", "PC", "NC", "NA", "NR", "PCL", "PMR")}


# ------------------------------------------------------------------------------- rules
def _ref(doc: ParsedDocument, page: int) -> str:
    if page and doc.file_type == "pdf":
        sec = doc.section_at(page)
        return f"p.{page}" + (f", Sec. {sec.number}" if sec and sec.number else "")
    return ""


def _first(doc: ParsedDocument, pattern: str) -> tuple[str, str] | None:
    hits = doc.find(pattern, limit=1)
    if not hits:
        return None
    page, snip = hits[0]
    return snip, _ref(doc, page)


def run_rule(rule: str, doc: ParsedDocument) -> tuple[str, str, str, str]:
    """Return (evidence_state, observation, evidence quote, page ref)."""
    t = doc.text
    if rule == "cover_title":
        first = doc.page_texts[0] if doc.page_texts else ""
        if doc.title and doc.title[:30].lower() in first.lower():
            return "Present", f"Title on the front page: '{doc.title}'.", doc.title, "p.1" if doc.file_type == "pdf" else ""
        if doc.title:
            return "Present-Incomplete", f"Title found ('{doc.title}') but not clearly on the front page.", doc.title, ""
        return "Not Present", "No data-item title could be identified on the front page.", "", "p.1"
    if rule == "doc_number":
        if not doc.doc_number:
            return "Not Present", "No document number found on the front pages.", "", "p.1-3"
        if doc.file_type == "pdf":
            on_pages = sum(1 for pt in doc.page_texts if doc.doc_number in pt)
            missing_hf = on_pages < 0.5 * doc.page_count
        else:
            missing_hf = bool(doc.header_footer) and doc.doc_number not in " ".join(doc.header_footer)
        if missing_hf and doc.file_type in ("pdf", "docx"):
            return ("Present-Incomplete", f"Document number {doc.doc_number} is on the front pages but was not found in "
                    "the running header/footer.", doc.doc_number, "")
        return "Present", f"Document number {doc.doc_number} identified.", doc.doc_number, ""
    if rule == "version_date":
        if doc.version and doc.date:
            return "Present", f"Issue/version '{doc.version}' and date '{doc.date}' found.", f"{doc.version} / {doc.date}", ""
        if doc.version or doc.date:
            return ("Present-Incomplete", f"Only {'version' if doc.version else 'date'} found "
                    f"('{doc.version or doc.date}').", doc.version or doc.date, "")
        return "Not Present", "No issue/version or date found on the front pages.", "", "p.1-3"
    if rule == "states_dal":
        if not doc.dal_mentions:
            return "Not Present", "No statement of the software level (e.g. 'Level A') found.", "", ""
        hit = _first(doc, r"(?:software|criticality|design assurance)\s+level\s*[:\-]?\s*[A-E]\b|\bDAL\s*[A-E]\b")
        if len(doc.dal_mentions) > 1:
            return ("Present-Inconsistent", f"More than one software level is stated: {', '.join(doc.dal_mentions)}.",
                    hit[0] if hit else "", hit[1] if hit else "")
        return "Present", f"Software level {doc.dal_mentions[0]} is stated.", hit[0] if hit else "", hit[1] if hit else ""
    if rule == "signatories":
        roles = [r for r in ("prepared by", "reviewed by", "checked by", "approved by", "verified by")
                 if re.search(r, t, re.I)]
        hit = _first(doc, r"prepared by|approved by|reviewed by|checked by")
        if len(roles) >= 2:
            return "Present", f"Signatory roles found: {', '.join(roles)}.", hit[0] if hit else "", hit[1] if hit else ""
        if roles:
            return "Present-Incomplete", f"Only '{roles[0]}' found in the signatory block.", hit[0] if hit else "", hit[1] if hit else ""
        return "Not Present", "No prepared/reviewed/approved signatory block found.", "", ""
    if rule == "revision_history":
        hit = _first(doc, r"revision history|amendment history|record of (?:revisions|amendments)|change history|document history")
        return ("Present", "Revision / amendment history found.", *hit) if hit else \
            ("Not Present", "No revision or amendment history found.", "", "")
    if rule == "toc":
        toc_lines = len(re.findall(r"(\.{4,}|…{2,})\s*\d{1,4}\s*$", t, re.M))
        hit = _first(doc, r"table of contents|\bcontents\b")
        if hit and toc_lines >= 3 or (doc.file_type == "docx" and hit):
            return "Present", "Table of contents found.", *hit
        return "Not Present", "No table of contents found.", "", ""
    if rule == "abbreviations":
        hit = _first(doc, r"acronyms|abbreviations|definitions and acronyms|glossary")
        return ("Present", "Acronyms / abbreviations section found.", *hit) if hit else \
            ("Not Present", "No acronyms / abbreviations list found.", "", "")
    if rule == "references":
        hit = _first(doc, r"(applicable|reference[sd]?|referenced)\s+documents?|\breferences\b")
        return ("Present", "Reference / applicable documents section found.", *hit) if hit else \
            ("Not Present", "No list of applicable or reference documents found.", "", "")
    if rule == "page_numbering":
        if doc.file_type == "pdf":
            n = sum(1 for p in doc.page_texts if re.search(r"page\s*\d+\s*(of|/)\s*\d+|\bpage\s*\|?\s*\d+", p, re.I))
            if n >= 0.8 * doc.page_count:
                return "Present", f"Page numbering found on {n} of {doc.page_count} pages.", "", ""
            if n:
                return "Present-Incomplete", f"Page numbering found on only {n} of {doc.page_count} pages.", "", ""
            return "Not Present", "No 'Page x of y' numbering found.", "", ""
        if any(re.search(r"page", h, re.I) for h in doc.header_footer):
            return "Present", "Page numbering field found in header/footer.", "", ""
        return "Cannot Verify", "Page numbering cannot be checked for this file type.", "", ""
    if rule == "no_placeholders":
        hits = doc.find(r"Error! Reference source not found|\bTB[DC]\b|\[insert[^\]]*\]|<\s*(?:LRU|System|Platform|"
                        r"Name|Doc|Date)[^>]{0,30}>|\bX{3,}\b", flags=0, limit=8)
        if not hits:
            return "Present", "No unresolved placeholders (TBD/TBC, broken references, template fields) found.", "", ""
        quotes = "; ".join(f"{('p.' + str(p) + ': ') if p else ''}{s[:90]}" for p, s in hits[:4])
        return ("Present-Inconsistent", f"{len(hits)}{'+' if len(hits) == 8 else ''} unresolved placeholder(s) or "
                f"broken field(s) found.", quotes, _ref(doc, hits[0][0]))
    if rule == "classification":
        hit = _first(doc, r"\b(restricted|confidential|secret|unclassified|unrestricted)\b")
        return ("Present", "Security classification marking found.", *hit) if hit else \
            ("Not Present", "No security classification marking found.", "", "")
    if rule == "committal_language":
        shall = len(re.findall(r"\bshall\b", t, re.I)) + len(re.findall(r"\bwill\b", t, re.I))
        weak = len(re.findall(r"\b(may|should|could|wherever possible|as appropriate|if required)\b", t, re.I))
        if shall >= 10 and weak <= shall:
            return "Present", f"Committal language used ({shall} 'shall/will' vs {weak} non-committal terms).", "", ""
        return ("Present-Incomplete", f"Weak commitment wording: {shall} 'shall/will' vs {weak} non-committal "
                "terms ('may', 'should', 'as appropriate').", "", "")
    if rule == "acronyms_defined":
        used = Counter(re.findall(r"\b([A-Z]{2,6})s?\b", t))
        abbr_sec = " ".join(s.text for s in doc.sections if re.search(r"acronym|abbreviation|glossar", s.title, re.I))
        defined_inline = set(re.findall(r"\(([A-Z]{2,6})s?\)", t))
        common = {"DO", "RTCA", "EASA", "FAA", "ID", "OK", "NA", "PDF", "PC", "NC", "TBD", "IT", "UK", "USA", "AND", "OR"}
        missing = sorted(a for a, n in used.items() if n >= 2 and a not in abbr_sec and a not in defined_inline
                         and a not in common)
        if not abbr_sec:
            return "Cannot Verify", "No acronyms list found, so definitions cannot be checked.", "", ""
        if len(missing) > 3:
            return ("Present-Incomplete", f"{len(missing)} acronyms used but not defined, e.g. {', '.join(missing[:10])}.",
                    ", ".join(missing[:20]), "")
        return "Present", "Acronyms used are defined.", "", ""
    if rule == "figures_tables":
        figs = len(set(re.findall(r"\bFigure\s+\d+", t)))
        tabs = len(set(re.findall(r"\bTable\s+\d+", t)))
        if figs or tabs:
            return "Present", f"{figs} numbered figure(s) and {tabs} numbered table(s) found.", "", ""
        return "Cannot Verify", "No numbered figures or tables found (may be acceptable).", "", ""
    return "Cannot Verify", f"No rule implementation for '{rule}'.", "", ""


# --------------------------------------------------------------------- evidence search
def _keywords(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-/]{3,}", text)
    out = []
    for w in words:
        lw = w.lower()
        if lw not in STOP and lw not in out:
            out.append(lw)
    return out[:25]


def retrieve(doc: ParsedDocument, item: dict, top: int = 3) -> list[tuple[float, str, str]]:
    """Rank sections (or pages) by keyword overlap. Returns (score, header, text)."""
    kws = _keywords(f"{item.get('question', '')} {item.get('expected_evidence', '')} {item.get('section', '')}")
    if not kws:
        return []
    units = [(f"Sec. {s.number} {s.title}".strip() + (f", p.{s.page_start}" if s.page_start else ""), s.text)
             for s in doc.sections if s.text and len(s.text) > 40]
    if not units:
        units = [(f"p.{i}" if doc.file_type == "pdf" else f"part {i}", t) for i, t in enumerate(doc.page_texts, 1)]
    scored = []
    for header, text in units:
        low = text.lower()
        hits = sum(1 for k in kws if k in low)
        head_bonus = sum(1 for k in kws if k in header.lower()) * 1.5
        score = (hits + head_bonus) / len(kws)
        if score > 0:
            scored.append((round(score, 3), header, text))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top]


# ------------------------------------------------------------------------------ engine
class ReviewEngine:
    def __init__(self, severity: SeverityClassifier | None = None, ai_agent=None):
        self.severity = severity or SeverityClassifier()
        self.ai = ai_agent

    def structure_review(self, doc: ParsedDocument, doc_type: str) -> list[dict]:
        rows = []
        for rule, label in (("cover_title", "Cover page / title"), ("doc_number", "Document number"),
                            ("version_date", "Issue / version and date"), ("signatories", "Author / reviewer / approver"),
                            ("revision_history", "Revision history"), ("toc", "Table of contents"),
                            ("abbreviations", "Abbreviations"), ("references", "Reference documents"),
                            ("states_dal", "Software level declared"), ("page_numbering", "Page numbering")):
            state, obs, quote, ref = run_rule(rule, doc)
            rows.append({"element": label, "state": state, "detail": obs, "where": ref})
        titles = " ".join(f"{s.number} {s.title}" for s in doc.sections).lower()
        for pat in EXPECTED_SECTIONS.get(doc_type, []):
            found = next((s for s in doc.sections if re.search(pat, s.title, re.I)), None)
            rows.append({"element": f"Section: {pat.split('|')[0]}",
                         "state": "Present" if found else ("Present" if re.search(pat, titles) else "Not found as heading"),
                         "detail": found.label if found else "No heading matched; content may exist under another title.",
                         "where": f"p.{found.page_start}" if found and found.page_start else ""})
        rows.append({"element": "Sections detected", "state": str(len(doc.sections)),
                     "detail": f"{doc.page_count} page(s); file type {doc.file_type.upper()}", "where": ""})
        if doc.scanned_pages:
            rows.append({"element": "Scanned pages", "state": "Warning", "detail": "; ".join(doc.warnings), "where": ""})
        return rows

    def run(self, doc: ParsedDocument, doc_type: str, standard: str, dal: str, soi: str, checklist: dict,
            companions: list[tuple[str, ParsedDocument]] | None = None, use_ai: bool = False,
            progress: Callable[[int, str], None] | None = None, cancelled: Callable[[], bool] | None = None
            ) -> ReviewResult:
        companions = companions or []
        res = ReviewResult()
        prog = progress or (lambda p, m: None)
        is_cancelled = cancelled or (lambda: False)
        ai_ok = False
        if use_ai and self.ai is not None:
            ai_ok = self.ai.is_available()
            if not ai_ok:
                res.notes.append(f"AI-assisted analysis unavailable: {self.ai.last_error} Rule-based mode used.")
        res.analysis_mode = "AI-assisted" if ai_ok else "Rule-based"
        if dal == "E":
            res.notes.append("Software level E: DO-178B/C objectives are not applicable. Only document control is "
                             "reviewed and no compliance findings are raised.")

        prog(5, "Reviewing document structure")
        res.structure = self.structure_review(doc, doc_type)

        items = checklist["items"]
        assessor = EvidenceAssessor(doc, doc_type, [t for t, _ in companions])
        n = len(items)
        for i, item in enumerate(items):
            if is_cancelled():
                res.notes.append("Review cancelled by the user before completion.")
                break
            prog(10 + int(70 * i / max(1, n)), f"Checklist item {item.get('ref')} ({i + 1}/{n})")
            a = Assessment(item=item)
            applies, why = applicability_for(item, dal)
            if not applies and not (dal == "E" and item.get("sheet") == "A"):
                a.applicable, a.na_reason = False, why
                a.verdict, a.evidence_state, a.observation = "NA", "Not Applicable", why
                res.assessments.append(a)
                continue
            prefix = ""
            if item.get("applicability") == "Conditional":
                prefix = f"Conditional check ({item.get('condition')}). "
            rule = item.get("rule")
            state = None
            if rule:
                state, obs, quote, ref = run_rule(rule, doc)
                if state != "Cannot Verify":
                    a.evidence_state, a.evidence, a.page_ref = state, quote, ref
                    a.observation = prefix + obs
                    a.verdict = {"Not Present": "NC", "Present": "C"}.get(state, "PC")
            if not rule or state == "Cannot Verify":
                v = assessor.assess(item)
                a.origin = "Rule"
                a.verdict, a.evidence_state = v.verdict, v.evidence_state
                a.observation, a.evidence, a.page_ref = prefix + v.observation, v.evidence, v.page_ref
                if v.verdict == "NA":
                    a.applicable, a.na_reason = False, v.observation
                if ai_ok and v.verdict != "NA":
                    hits = retrieve(doc, item)
                    ai = self.ai.assess(item, doc_type, standard, dal, soi,
                                        [(h, t) for _, h, t in hits] or [("full text", doc.text[:20000])], doc.text)
                    if ai.verdict != "PMR" or v.verdict == "NR":
                        a.origin = "AI"
                        a.verdict, a.evidence_state = ai.verdict, ai.evidence_state
                        a.observation = prefix + (ai.observation or ai.reasoning)
                        if ai.quote:
                            a.evidence = ai.quote
                            a.page_ref = ", ".join(x for x in (f"p.{ai.page}" if ai.page else "", ai.section) if x) \
                                or a.page_ref
                        a.recommendation = ai.recommendation
                    else:
                        a.observation += " (Local AI could not confirm this with a verified quote.)"
            if dal == "E" and a.verdict in ("NC", "PC"):
                a.observation += " (DAL E: recorded for information only.)"
            res.assessments.append(a)

        prog(82, "Checking cross-document consistency")
        res.consistency = compare(doc, doc_type, companions, dal, standard)
        res.not_supplied = [x for x in referenced_documents_not_supplied(doc, companions) if x != doc_type]

        prog(90, "Generating findings")
        if dal != "E":
            self._findings(res, dal, doc_type)
        prog(100, "Review complete")
        return res

    # ------------------------------------------------------------------ findings
    def _recommendation(self, a: Assessment) -> str:
        if a.recommendation:
            return a.recommendation
        q = a.item.get("question", "").rstrip(".")
        ev = a.item.get("expected_evidence", "")
        if a.verdict == "NC":
            return f"Add the missing content so that: {q[0].lower() + q[1:] if q else q}." + \
                   (f" Expected evidence: {ev}" if ev else "")
        return f"Complete or correct the content so that: {q[0].lower() + q[1:] if q else q}." + \
               (f" Expected evidence: {ev}" if ev else "")

    def _findings(self, res: ReviewResult, dal: str, doc_type: str) -> None:
        for idx, a in enumerate(res.assessments):
            if a.verdict not in ("NC", "PC") or not a.applicable:
                continue
            sev, why = self.severity.classify(a.item, a.verdict, dal, a.evidence_state)
            obs = a.observation.strip()
            if a.verdict == "NC" and not a.evidence:
                obs += " No supporting text was found in the document."
            res.findings.append(ProposedFinding(
                severity=sev, rationale=why, observation=f"[{a.item.get('ref')}] {obs}",
                recommendation=self._recommendation(a), evidence=a.evidence, page_ref=a.page_ref,
                section=a.item.get("section", ""), reference=a.item.get("reference", ""), checks=[idx], origin=a.origin))
        d_idx = next((i for i, a in enumerate(res.assessments) if a.item.get("sheet") == "D" and a.applicable), None)
        for c in res.consistency:
            if c.status != "Inconsistent":
                continue
            sev, why = self.severity.consistency(c.topic)
            res.findings.append(ProposedFinding(
                severity=sev, rationale=why,
                observation=f"{c.description}: the {doc_type} {c.primary_value}" if c.topic == "doc_number" and
                            c.primary_value.startswith(("refers", "does")) else
                            f"{c.description}: this {doc_type} gives '{c.primary_value}' but {c.companion} gives "
                            f"'{c.companion_value}'.",
                recommendation=(f"Quote the {c.companion.split(' (')[0]} by its document number ({c.companion_value}) and "
                                f"issue wherever it is referenced." if c.topic == "doc_number" else
                                f"Align the {c.description.lower()} with {c.companion}, or justify the difference."),
                evidence=c.evidence, page_ref="", section="", reference="DO-178C 4.1.g / 7.2.1 (consistency)",
                checks=[d_idx] if d_idx is not None else [], origin="Rule"))


def overall_recommendation(findings: list[dict], counts: dict[str, int]) -> str:
    """Proposed overall recommendation from approved findings and verdict counts."""
    open_ = [f for f in findings if f.get("status") in ("Open", "Not Closed", "Pending Clarification")
             and f.get("approval_state") != "Rejected"]
    if counts.get("PMR", 0) or counts.get("NR", 0) > 0.25 * max(1, sum(counts.values())):
        incomplete = True
    else:
        incomplete = False
    if any(f["severity"] == "Major" for f in open_):
        return "NOT ACCEPTABLE"
    if incomplete:
        return "REVIEW INCOMPLETE"
    if open_:
        return "ACCEPTABLE WITH COMMENTS"
    return "ACCEPTABLE"


def describe(doc_type: str) -> str:
    return f"{doc_full_name(doc_type)} ({doc_type})" if doc_type in DOCUMENT_TYPES else doc_type
