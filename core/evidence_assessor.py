"""Deterministic evidence assessor: proposes a verdict for every checklist item.

For each check the assessor
1. extracts the concepts the criterion asks for (content words and two-word phrases,
   weighted by how specific they are in this document);
2. scores every passage of the document against those concepts;
3. proposes a verdict from the coverage of the best passage and of the whole document:
     C   - the concepts are covered together in one passage with substantive text;
     PC  - the topic is addressed but part of what the criterion asks for is missing,
           thin, or left as TBD/placeholder;
     NC  - the concepts the criterion asks for are not found in the document;
     NA  - a conditional check whose condition is not met by the document;
     NR  - the check cannot be judged from text (no text, too generic, or it depends on
           a companion document that was not supplied).
Every verdict carries a quote, its page/section and the list of concepts not found.
All verdicts are proposals; findings stay Draft until a reviewer approves them.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from core.document_parser import ParsedDocument, _norm_title
from core.refs import location, section_ref

# Words that carry no meaning for compliance (review verbs, generic nouns, template words).
GENERIC = set("""
the a an and or of to in for on by with is are be been being shall should will must may can this that these those
each every any all from as at it its into their there where which when what who how not no nor than then also such
other others has have had was were do does done per via within without between including include includes included
document documents plan plans data item items software section sections clause clauses clearly clear stated state
states statement defined define defines definition described describe describes description identified identify
identifies provided provide provides given given used use uses using available appropriate adequate adequately
sufficient sufficiently specific specified specify specifies explicitly explicit properly proper correct correctly
consistent consistently ensure ensures ensured address addresses addressed covered cover covers mention mentioned
mentions present presence exists exist made make makes way ways means related relevant respective required
required need needs needed one two three four five only both either least well also etc e g i ie eg x n
applicant applicant's whether against under over upon same new existing following follows shown show shows
page pages applicable applicability where ever wherever
text texts blank blanks marked mark marks listed list lists match matches matching through throughout covering
primarily mainly mostly involved involve involves full fully complete completed completely filled fill entire
including actual actually particular particularly given general generally overall single separate separately
distinct distinctly own their them they its his her our we you your reader readers able unable must-have
evidence evidences artifact artifact artefact artefacts record-able showing stating states stated statements
captured capture captures contain contains contained containing exist existence found find finds absent missing
yes either neither nothing something anything everything every-where across before after during while until
since because therefore thus hence however although though unless otherwise instead rather just even still
again further more most less least many much few several various various certain some any each per cent
approach approaches manner form forms format formats type types kind kinds part parts point points case cases
example examples like likely unlike far near high low large small long short first last next previous prior
latest current currently already yet time times good better best acceptable unacceptable possible possibly
should-be shall-be named naming name names title titles heading headings number numbered numbers reference
references referenced refer refers referring cited cite cites quote quoted quotes
""".split())

DOC_WORDS = set("""psac sdp svp scmp sqap srs sds scs ivvp srd sdd svcp svr sci seci sas scmr sqar
do-178b do-178c do-178 rtca""".split())

SYNONYMS = {
    "organisation": "organization", "organisational": "organizational", "authorisation": "authorization",
    "programme": "program", "behaviour": "behavior", "analyse": "analyze", "analysed": "analyzed",
    "dal": "level", "criticality": "level", "amendment": "revision", "acronyms": "abbreviations",
    "sqa": "quality", "scm": "configuration", "cm": "configuration", "qa": "quality", "pr": "problem",
    "prs": "problem", "soi": "involvement", "sois": "involvement", "hlr": "high-level", "llr": "low-level",
    "mc/dc": "mcdc", "eoc": "executable", "tqp": "qualification", "ivv": "independent",
}

PLACEHOLDER = re.compile(r"\bTB[DCA]\b|to be (?:defined|decided|confirmed|provided)|\[insert|<[^>]{2,30}>|"
                         r"Error! Reference source", re.I)


def _stem(w: str) -> str:
    w = SYNONYMS.get(w, w)
    w = re.sub(r"'s$", "", w)
    if len(w) > 4 and w.endswith("ies"):
        w = w[:-3] + "y"
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return w[:6] if len(w) > 6 else w


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z0-9\-/]*", text.lower())


def concepts(text: str, doc_type: str = "") -> list[str]:
    """Distinct concept stems in the criterion, in order."""
    out: list[str] = []
    for t in _tokens(text):
        t = t.strip("-/")
        if len(t) < 3 or t in GENERIC or t in DOC_WORDS or t == doc_type.lower():
            continue
        s = _stem(t)
        if s not in out:
            out.append(s)
    return out


def phrases(text: str, doc_type: str = "") -> list[tuple[str, str]]:
    """Two-word content phrases (both words meaningful), e.g. 'transition criteria'."""
    toks = [t.strip("-/") for t in _tokens(text)]
    out = []
    for a, b in zip(toks, toks[1:]):
        if (len(a) >= 3 and len(b) >= 3 and a not in GENERIC and b not in GENERIC and a not in DOC_WORDS
                and b not in DOC_WORDS):
            p = (_stem(a), _stem(b))
            if p not in out:
                out.append(p)
    return out


@dataclass
class Passage:
    header: str
    text: str
    page: int | None
    stems: set = field(default_factory=set)
    pairs: set = field(default_factory=set)
    words: int = 0


@dataclass
class Verdict:
    verdict: str
    evidence_state: str
    observation: str
    evidence: str = ""
    page_ref: str = ""
    coverage: float = 0.0
    missing: list[str] = field(default_factory=list)


class EvidenceAssessor:
    WINDOW = 140  # words per passage
    STEP = 70

    def __init__(self, doc: ParsedDocument, doc_type: str, companions: list[str] | None = None):
        self.doc = doc
        self.doc_type = doc_type
        self.companions = set(companions or [])
        self.passages = self._build()
        self.df: dict[str, int] = {}
        for p in self.passages:
            for s in p.stems:
                self.df[s] = self.df.get(s, 0) + 1
        self.n = max(1, len(self.passages))
        self.all_stems = set(self.df)
        self.all_pairs = set().union(*(p.pairs for p in self.passages)) if self.passages else set()

    # ------------------------------------------------------------------ passages
    def _label(self, page: int | None, sec) -> str:
        return location(page if self.doc.file_type == "pdf" else None, sec)

    def _units(self) -> list[tuple[str, str, int | None]]:
        doc = self.doc
        if doc.file_type == "pdf" and doc.page_texts:
            norm = lambda l: re.sub(r"\d+", "#", " ".join(l.split())).lower()
            cnt: dict[str, int] = {}
            for t in doc.page_texts:
                for k in {norm(l) for l in t.splitlines() if l.strip()}:
                    cnt[k] = cnt.get(k, 0) + 1
            running = {k for k, c in cnt.items() if c >= max(3, 0.5 * len(doc.page_texts))}
            out = []
            for i, t in enumerate(doc.page_texts, 1):
                if self._is_toc(t):
                    continue
                body = "\n".join(l for l in t.splitlines() if l.strip() and norm(l) not in running
                                 and not re.search(r"(\.{4,}|…{2,})\s*\d{1,4}\s*$", l)
                                 and not re.fullmatch(r"\s*page\s*\|?\s*\d+(\s*(of|/)\s*\d+)?\s*", l, re.I))
                out.append((self._label(i, doc.section_at(i)), body, i))
            # the running header/footer itself is evidence for page-level checks (classification, doc no., footer)
            seen, hf = set(), []
            for t in doc.page_texts[1:4] or doc.page_texts[:1]:
                for l in t.splitlines():
                    k = norm(l)
                    if l.strip() and k in running and k not in seen:
                        seen.add(k)
                        hf.append(" ".join(l.split()))
            if hf:
                out.append(("running header/footer (every page)", "\n".join(hf), None))
            return out
        secs = [s for s in doc.sections if s.text and len(s.text) > 30]
        if secs:
            return [(self._label(None, s), s.text, None) for s in secs]
        return [(f"part {i}", t, None) for i, t in enumerate(doc.page_texts, 1)]

    @staticmethod
    def _is_toc(text: str) -> bool:
        lines = [l for l in text.splitlines() if l.strip()]
        toc = sum(1 for l in lines if re.search(r"(\.{4,}|…{2,}|\s{3,})\s*\d{1,4}\s*$", l))
        return bool(lines) and toc >= max(6, 0.5 * len(lines))

    HEAD = re.compile(r"^\s*((?:\d{1,2}\.){0,4}\d{1,2})\.?\s+([A-Z][A-Za-z0-9 ,&/()\-]{2,70})$")

    def _build(self) -> list[Passage]:
        out = []
        pdf = self.doc.file_type == "pdf"
        toc = " ".join(l.lower() for t in self.doc.page_texts for l in t.splitlines()
                       if re.search(r"(\.{4,}|…{2,})\s*\d{1,4}\s*$", l))
        self._top_titles = {sec.title.strip().lower() for sec in self.doc.sections
                            if sec.number and "." not in sec.number and sec.title.strip().lower() in toc}
        current = ""  # last heading seen (carried across pages)
        if self.doc.toc:
            first_body = next((pg for _, _, pg in self._units() if pg), None)
            sec0 = self.doc.section_for(first_body, 0) if first_body else None
            current = section_ref(sec0.number, sec0.title) if sec0 else ""
        for header, text, page in self._units():
            # word offsets of headings printed on this page, so each passage gets its real section
            marks: list[tuple[int, str]] = []
            words: list[str] = []
            on_page = {e.key: e for e in self.doc.toc if e.page == page} if self.doc.toc else {}
            for line in text.splitlines():
                if on_page:  # headings from the document's table of contents
                    e = on_page.get(_norm_title(line))
                    if e is not None:
                        marks.append((len(words), section_ref(e.number, e.title)))
                elif pdf and not self.doc.toc:
                    m = self.HEAD.match(line)
                    if m and not line.rstrip().endswith(".") and len(m.group(2).split()) <= 10 \
                            and int(m.group(1).split(".")[0]) <= 40 \
                            and ("." in m.group(1) or m.group(2).strip().lower() in self._top_titles):
                        marks.append((len(words), section_ref(m.group(1), m.group(2).strip())))
                words.extend(line.split())
            if not words:
                continue
            starts = range(0, max(1, len(words) - self.STEP), self.STEP) if len(words) > self.WINDOW else [0]
            for st in starts:
                chunk = " ".join(words[st:st + self.WINDOW])
                if pdf:
                    before = [h for w, h in marks if w <= st + 10]
                    sec = before[-1] if before else current
                    label = ", ".join(x for x in (f"Page {page}" if page else "", sec) if x) or header
                else:
                    label = header
                toks = [t.strip("-/") for t in _tokens(chunk)]
                stems = {_stem(t) for t in toks if len(t) >= 3}
                stems |= {_stem(x) for t in toks if re.search(r"[-/]", t) for x in re.split(r"[-/]", t) if len(x) >= 2}
                pairs = {(_stem(a), _stem(b)) for a, b in zip(toks, toks[1:]) if len(a) >= 3 and len(b) >= 3}
                out.append(Passage(label, chunk, page, stems, pairs, len(toks)))
            if marks:
                current = marks[-1][1]
        return out

    # ---------------------------------------------------------------- scoring
    def _weight(self, stem: str) -> float:
        df = self.df.get(stem, 0)
        return 1.0 + math.log(self.n / (1 + df) + 1)

    def _quote(self, p: Passage, cs: list[str]) -> str:
        sentences = re.split(r"(?<=[.;:])\s+(?=[A-Z0-9(])", p.text)
        best, score = "", -1
        for s in sentences:
            st = {_stem(t.strip("-/")) for t in _tokens(s)}
            sc = sum(1 for c in cs if c in st)
            if sc > score or (sc == score and len(s) < len(best)):
                best, score = s, sc
        best = " ".join(best.split())
        return best[:320] + ("…" if len(best) > 320 else "")

    def assess(self, item: dict) -> Verdict:
        doc = self.doc
        if not self.passages or not doc.has_text:
            return Verdict("NR", "Cannot Verify", "The document has no readable text (scanned pages without OCR); "
                                                  "the check cannot be judged from the file.")
        q = item.get("question", "")
        ev = item.get("expected_evidence", "")
        cs = concepts(q, self.doc_type)
        for c in concepts(ev, self.doc_type):
            if c not in cs:
                cs.append(c)
        ph = phrases(q, self.doc_type)
        if len(cs) < 2:
            return Verdict("NR", "Cannot Verify", "The criterion is too general to be judged from the text alone; "
                                                  "reviewer to conclude.")

        # Conditional check whose condition does not occur in the document
        cond = item.get("condition") or ""
        if item.get("applicability") == "Conditional" and cond:
            cc = concepts(cond, self.doc_type)
            if cc and not any(c in self.all_stems for c in cc if self.df.get(c, 0) < 0.6 * self.n):
                return Verdict("NA", "Not Applicable", f"Condition not met: the document does not mention "
                               f"{cond.rstrip('.')}. Reviewer to confirm that the condition does not apply.")

        qw = {c: self._weight(c) * (1.6 if c in concepts(q, self.doc_type) else 1.0) for c in cs}
        total = sum(qw.values())
        doc_cov = sum(w for c, w in qw.items() if c in self.all_stems) / total

        best, best_score = None, -1.0
        for p in self.passages:
            sc = sum(w for c, w in qw.items() if c in p.stems) / total
            if ph:
                sc += 0.15 * sum(1 for x in ph if x in p.pairs) / len(ph)
            if sc > best_score:
                best, best_score = p, sc
        cov = min(1.0, best_score)
        missing_doc = [c for c in cs if c not in self.all_stems]
        missing_best = [c for c in cs if best is None or c not in best.stems]
        words_of = self._readable(q + " " + ev)
        miss_txt = ", ".join(words_of.get(c, c) for c in (missing_best[:6]))
        quote = self._quote(best, cs) if best else ""
        ref = best.header if best else ""

        sheet = item.get("sheet", "")
        needs_companion = sheet == "D" and re.search(r"\b(SDP|SVP|SCMP|SQAP|PSAC|SRD|SDD|SVCP|SAS|companion|other plans?)\b", q)

        if cov >= 0.65 and best.words >= 25:
            if best and PLACEHOLDER.search(best.text):
                return Verdict("PC", "Present-Incomplete", f"Addressed (see {ref}), but the passage still contains "
                               "unresolved placeholders (TBD/TBC or template fields).", quote, ref, cov, missing_best)
            obs = f"Addressed - see {ref} (coverage {cov:.0%})."
            if missing_best:
                obs += f" Not explicit in that passage: {miss_txt}."
            return Verdict("C", "Present", obs, quote, ref, cov, missing_best)
        if cov >= 0.30 or doc_cov >= 0.75:
            obs = (f"Partly addressed - see {ref} (coverage {cov:.0%}). Not found or not explicit: {miss_txt}."
                   if miss_txt else f"Addressed (see {ref}) but the content is thin (coverage {cov:.0%}).")
            return Verdict("PC", "Present-Incomplete", obs, quote, ref, cov, missing_best)
        if needs_companion and not self.companions:
            return Verdict("NR", "Cannot Verify", "This check depends on a companion document that was not supplied "
                           "with the review; upload it as a companion document or conclude manually.", quote, ref, cov,
                           missing_best)
        miss_doc = ", ".join(words_of.get(c, c) for c in missing_doc[:6]) or miss_txt
        obs = f"Not addressed: the document does not contain text covering {miss_doc}."
        if quote and cov >= 0.2:
            obs += f" Nearest text found at {ref} (coverage {cov:.0%})."
        return Verdict("NC", "Not Present", obs, quote if cov >= 0.2 else "", ref if cov >= 0.2 else "", cov,
                       missing_doc)

    @staticmethod
    def _readable(text: str) -> dict[str, str]:
        out = {}
        for t in _tokens(text):
            t = t.strip("-/")
            out.setdefault(_stem(t), t)
        return out
