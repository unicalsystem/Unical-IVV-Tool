"""Local document parsing: PDF (PyMuPDF, optional Tesseract OCR), DOCX, XLSX, TXT.

Produces a ParsedDocument with page texts, headings, sections and identification
metadata. Documents are treated as untrusted input: nothing embedded is executed,
macros are never run, and only text is extracted.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

HEADING_RE = re.compile(r"^\s*((?:\d{1,2}\.){0,4}\d{1,2})\.?\s+([A-Z][^\n]{2,90})$")
TOC_LINE_RE = re.compile(r"(\.{4,}|…{2,}|\s{3,})\s*\d{1,4}\s*$")
DOC_NO_RE = re.compile(r"(?:Doc(?:ument)?\.?\s*(?:No|Number|ID)\.?\s*[:\-]?\s*)([A-Z0-9][A-Z0-9_./\-]{4,40})", re.I)
VERSION_RE = re.compile(r"\b(?:Version|Ver\.?|Issue|Rev(?:ision)?\.?\s*No\.?|Rev\.?)\s*[:\-]?\s*([0-9]{1,2}(?:\.[0-9]{1,2})?|[A-Z])\b", re.I)
DATE_RE = re.compile(r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{1,2}\s+[A-Z][a-z]{2,8}\s+\d{4}|[A-Z][a-z]{2,8}\s+\d{1,2},\s*\d{4})\b")
DAL_RE = re.compile(r"\b(?:Software\s+Level|Level|DAL|Design\s+Assurance\s+Level|Criticality\s+Level)\s*[:\-]?\s*([A-E])\b")
STANDARD_RE = re.compile(r"DO[\s\-]?178\s*([BC])\b", re.I)


@dataclass
class Section:
    number: str
    title: str
    page_start: int | None
    level: int
    text: str = ""
    page_end: int | None = None

    @property
    def label(self) -> str:
        return f"{self.number} {self.title}".strip()


@dataclass
class TocEntry:
    """One entry of the document's own table of contents, located in the body."""
    title: str
    printed_page: int | None
    number: str = ""
    page: int | None = None  # physical page where the heading is printed
    pos: int = 0  # character offset of the heading in that page's text
    key: str = ""  # normalised heading line, to recognise it again in the body
    level: int = 1


@dataclass
class ParsedDocument:
    path: str
    file_type: str
    page_texts: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    header_footer: list[str] = field(default_factory=list)
    title: str = ""
    doc_number: str = ""
    version: str = ""
    date: str = ""
    dal_mentions: list[str] = field(default_factory=list)
    standard_mentions: list[str] = field(default_factory=list)
    scanned_pages: list[int] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    toc: list[TocEntry] = field(default_factory=list)  # sections from the document's own contents list

    @property
    def text(self) -> str:
        return "\n".join(self.page_texts)

    @property
    def page_count(self) -> int:
        return len(self.page_texts)

    @property
    def has_text(self) -> bool:
        return len(re.sub(r"\s", "", self.text)) > 200

    @property
    def is_scanned(self) -> bool:
        return bool(self.scanned_pages) and len(self.scanned_pages) >= max(1, self.page_count // 2)

    def find(self, pattern: str, flags: int = re.I, limit: int = 5) -> list[tuple[int, str]]:
        """(page number, snippet) for each match; page is 1-based (0 when pages are unknown)."""
        out = []
        rx = re.compile(pattern, flags)
        for i, t in enumerate(self.page_texts, 1):
            for m in rx.finditer(t):
                s, e = max(0, m.start() - 60), min(len(t), m.end() + 90)
                out.append((i if self.file_type == "pdf" else 0, " ".join(t[s:e].split())))
                if len(out) >= limit:
                    return out
        return out

    def section_at(self, page: int) -> Section | None:
        best = None
        for s in self.sections:
            if s.page_start and s.page_start <= page:
                best = s
        return best

    def section_for(self, page: int | None, pos: int | None = None) -> Section | None:
        """Section (from the table of contents when available) containing a page / character offset."""
        if not page:
            return None
        if self.toc:
            best = None
            for e in self.toc:
                if e.page is None:
                    continue
                if e.page < page or (e.page == page and (pos is None and e.pos < 200 or pos is not None and e.pos <= pos)):
                    best = e
            return Section(best.number, best.title, best.page, best.level) if best else None
        return self.section_at(page)


def tesseract_cmd() -> str | None:
    """Local Tesseract OCR engine: PATH first, then the standard Windows install folders."""
    found = shutil.which("tesseract")
    if found:
        return found
    import os
    for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        cand = Path(base) / "Tesseract-OCR" / "tesseract.exe" if base else None
        if cand and cand.exists():
            return str(cand)
    return None


def tesseract_available() -> bool:
    return tesseract_cmd() is not None


# ----------------------------------------------------------------------------- helpers
def _is_toc_page(text: str) -> bool:
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return False
    toc_lines = sum(1 for l in lines if TOC_LINE_RE.search(l))
    return ("contents" in text.lower()[:400] and toc_lines >= 3) or toc_lines >= max(6, len(lines) // 3)


def _sections_from_lines(page_texts: list[str], with_pages: bool) -> list[Section]:
    sections: list[Section] = []
    for pno, text in enumerate(page_texts, 1):
        lines = text.splitlines()
        if _is_toc_page(text):
            # keep only what follows the last contents entry (body may start on the same page)
            last = max((i for i, l in enumerate(lines) if TOC_LINE_RE.search(l)), default=len(lines) - 1)
            lines = lines[last + 1:]
        for line in lines:
            m = HEADING_RE.match(line)
            if not m or TOC_LINE_RE.search(line):
                continue
            num, title = m.group(1), m.group(2).strip()
            if title.endswith((".", ",", ";")) and len(title) > 40:
                continue  # numbered sentence, not a heading
            if re.match(r"^\d", title) or len(title.split()) > 14:
                continue
            first = int(num.split(".")[0])
            if first > 40:
                continue  # numbers such as values in tables
            sections.append(Section(num, title, pno if with_pages else None, num.count(".") + 1))
    # attach text: content between consecutive headings
    full = "\n".join(page_texts)
    positions = []
    for s in sections:
        idx = full.find(f"{s.number} {s.title}") if s.number else -1
        if idx < 0:
            idx = full.find(s.title)
        positions.append(idx)
    for i, s in enumerate(sections):
        start = positions[i]
        if start < 0:
            continue
        nxt = [p for p in positions[i + 1:] if p > start]
        end = nxt[0] if nxt else len(full)
        s.text = full[start:end][:20000]
    for i, s in enumerate(sections[:-1]):
        s.page_end = sections[i + 1].page_start
    if sections:
        sections[-1].page_end = len(page_texts) if with_pages else None
    return sections


def _repeated_lines(page_texts: list[str]) -> list[str]:
    """Lines that repeat on many pages (running header / footer)."""
    if len(page_texts) < 3:
        return []
    cnt: Counter[str] = Counter()
    for t in page_texts:
        lines = [l.strip() for l in t.splitlines() if l.strip()]
        edge = set(lines[:4] + lines[-4:])
        cnt.update(re.sub(r"\d+", "#", l) for l in edge)
    return [l for l, n in cnt.most_common(20) if n >= max(2, len(page_texts) // 2)]


def _metadata(doc: ParsedDocument) -> None:
    head = "\n".join(doc.page_texts[:3])[:6000]
    if not doc.title:
        for line in head.splitlines():
            l = line.strip()
            if len(l) > 12 and re.search(r"plan|description|standard|requirement|data|summary|index|results|"
                                         r"procedures|report|specification", l, re.I) and not TOC_LINE_RE.search(l):
                doc.title = l[:150]
                break
    m = DOC_NO_RE.search(head)
    if m:
        doc.doc_number = m.group(1).strip(" .:")
    m = VERSION_RE.search(head)
    if m:
        doc.version = m.group(1)
    m = DATE_RE.search(head)
    if m:
        doc.date = m.group(1)
    doc.dal_mentions = sorted(set(DAL_RE.findall(doc.text)))
    doc.standard_mentions = sorted({f"DO-178{x.upper()}" for x in STANDARD_RE.findall(doc.text)})


# ------------------------------------------------------------------------------ parsers
def _ocr_page(page, dpi: int = 200) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        img = Path(tmp) / "p.png"
        page.get_pixmap(dpi=dpi).save(str(img))
        try:
            res = subprocess.run([tesseract_cmd() or "tesseract", str(img), "-", "--psm", "3"], capture_output=True, text=True,
                                 timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return res.stdout
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.warning("OCR failed on page %s: %s", page.number + 1, exc)
            return ""


TOC_ENTRY_RE = re.compile(r"^\s*(.*?\S)\s*(?:\.{3,}|…{2,}|·{3,})\s*(\d{1,4})\s*$")
NUM_PREFIX_RE = re.compile(r"^\s*((?:\d{1,2}\.){0,5}\d{1,2}|[A-Z]\.\d{1,2}(?:\.\d{1,2})*)\.?\s+(?=\S)")


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _parse_toc(page_texts: list[str]) -> tuple[list[TocEntry], set[int]]:
    """Read the contents list (title ...... page) from the first pages."""
    entries: list[TocEntry] = []
    toc_pages: set[int] = set()
    for i, text in enumerate(page_texts[:25], 1):
        page_entries = []
        for line in text.splitlines():
            m = TOC_ENTRY_RE.match(line)
            if not m:
                continue
            title, pg = m.group(1).strip(), int(m.group(2))
            if re.match(r"(?i)(table|figure|fig\.|list of|contents|table of contents)\b", title):
                if re.match(r"(?i)(table|figure|fig\.)\s*\d", title):
                    toc_pages.add(i)  # list of tables / figures: not sections
                continue
            number = ""
            nm = NUM_PREFIX_RE.match(title)
            if nm:
                number, title = nm.group(1), title[nm.end():].strip()
            if len(title) >= 3:
                page_entries.append(TocEntry(title=title, printed_page=pg, number=number))
        if len(page_entries) >= 3:
            toc_pages.add(i)
            entries.extend(page_entries)
    return entries, toc_pages


def _levels_from_indent(entries: list[TocEntry], indent: dict[str, list[float]]) -> None:
    """Outline level of each contents entry from its left indent (used when headings carry no number)."""
    if not indent:
        return
    seen: dict[str, int] = {}
    xs = []
    for e in entries:
        k = _norm_title(e.title)
        lst = indent.get(k) or []
        i = seen.get(k, 0)
        seen[k] = i + 1
        xs.append(lst[min(i, len(lst) - 1)] if lst else None)
    distinct = sorted({x for x in xs if x is not None})
    clusters: list[float] = []
    for x in distinct:  # merge indents within 6 pt
        if not clusters or x - clusters[-1] > 6:
            clusters.append(x)
    for e, x in zip(entries, xs):
        if x is not None:
            e.level = 1 + max(i for i, c in enumerate(clusters) if x >= c - 3)


def _renumber(toc: list[TocEntry]) -> None:
    """Give unnumbered headings an outline number from the contents levels (1, 1.1, 1.2 ...)."""
    counters: list[int] = []
    for e in toc:
        if re.match(r"(?i)(appendix|annex|annexure)\b", e.title):
            counters = []
            continue
        if e.number and re.fullmatch(r"\d+(\.\d+)*", e.number):
            counters = [int(x) for x in e.number.split(".")]
            e.level = len(counters)
            continue
        lvl = max(1, e.level)
        counters = (counters + [0] * lvl)[:lvl]
        counters[lvl - 1] += 1
        e.number = ".".join(str(c) for c in counters)


def _locate_toc(entries: list[TocEntry], page_texts: list[str], toc_pages: set[int]) -> list[TocEntry]:
    """Find each contents entry as a heading in the body: gives its number, real page and position."""
    if not entries:
        return []
    start_page = max(toc_pages) + 1 if toc_pages else 1
    page_lines: dict[int, list[tuple[int, str]]] = {}
    for p in range(start_page, len(page_texts) + 1):
        pos, out = 0, []
        for line in page_texts[p - 1].splitlines(keepends=True):
            if line.strip():
                out.append((pos, line.rstrip("\n")))
            pos += len(line)
        page_lines[p] = out
    cur_page, cur_pos, offset = start_page, -1, None
    located = []
    for e in entries:
        want = _norm_title(e.title)
        if not want:
            continue
        lo = cur_page
        hi = len(page_texts)
        if offset is not None and e.printed_page:
            lo = max(cur_page, e.printed_page + offset - 1)
            hi = min(hi, e.printed_page + offset + 3)
        else:
            hi = min(hi, cur_page + 20)
        found = None
        for p in range(lo, hi + 1):
            for pos, line in page_lines.get(p, []):
                if p == cur_page and pos <= cur_pos:
                    continue
                if TOC_ENTRY_RE.match(line) or len(line) > 160:
                    continue
                nm = NUM_PREFIX_RE.match(line)
                body = line[nm.end():] if nm else line
                got = _norm_title(body)
                if got == want or (len(want) >= 12 and got.startswith(want) and len(got) - len(want) < 40):
                    found = (p, pos, nm.group(1) if nm else e.number, line)
                    break
            if found:
                break
        if not found:
            continue
        p, pos, number, line = found
        e.page, e.pos, e.number = p, pos, number or e.number
        e.key = _norm_title(line)
        if number:
            e.level = number.count(".") + 1
        if e.printed_page:
            offset = p - e.printed_page
        cur_page, cur_pos = p, pos
        located.append(e)
    if any(not e.number for e in located):
        _renumber(located)
    return located


def _sections_from_toc(toc: list[TocEntry], page_texts: list[str]) -> list[Section]:
    out = []
    for i, e in enumerate(toc):
        sec = Section(e.number, e.title, e.page, e.level)
        nxt = toc[i + 1] if i + 1 < len(toc) else None
        if nxt and nxt.page == e.page:
            sec.text = page_texts[e.page - 1][e.pos:nxt.pos]
        else:
            end = (nxt.page if nxt else len(page_texts) + 1)
            parts = [page_texts[e.page - 1][e.pos:]] + page_texts[e.page:end - 1]
            if nxt:
                parts.append(page_texts[nxt.page - 1][:nxt.pos])
            sec.text = "\n".join(parts)[:20000]
        sec.page_end = nxt.page if nxt else len(page_texts)
        out.append(sec)
    return out


def parse_pdf(path: Path, use_ocr: bool = True, progress=None) -> ParsedDocument:
    import pymupdf
    doc = ParsedDocument(str(path), "pdf")
    pdf = pymupdf.open(str(path))
    if pdf.needs_pass:
        pdf.close()
        raise PermissionError("The PDF is password protected. Remove the password and upload it again.")
    meta_title = (pdf.metadata or {}).get("title") or ""
    can_ocr = use_ocr and tesseract_available()
    toc_indent: dict[str, list[float]] = {}
    for i, page in enumerate(pdf):
        text = page.get_text("text") or ""
        if i < 25 and len(TOC_ENTRY_RE.findall(text)) + len(re.findall(r"(?:\.{3,}|…{2,})\s*\d{1,4}\s*$", text, re.M)) >= 3:
            try:  # left edge of each contents line = its level in the outline
                for b in page.get_text("dict").get("blocks", []):
                    for ln in b.get("lines", []):
                        t = "".join(sp.get("text", "") for sp in ln.get("spans", []))
                        m = TOC_ENTRY_RE.match(t)
                        if m and not re.match(r"(?i)\s*(table|figure|fig\.|list of|contents|appendix|annex)", m.group(1)) \
                                and not NUM_PREFIX_RE.match(m.group(1)):  # numbered lines carry their level
                            toc_indent.setdefault(_norm_title(m.group(1)), []).append(
                                round(ln["bbox"][0]))
            except Exception:  # layout info is optional
                pass
        if len(text.strip()) < 30 and page.get_images():
            doc.scanned_pages.append(i + 1)
            if can_ocr:
                text = _ocr_page(page)
                doc.ocr_pages.append(i + 1)
        doc.page_texts.append(text)
        if progress:
            progress(int(100 * (i + 1) / max(1, pdf.page_count)))
    pdf.close()
    if doc.scanned_pages and not doc.ocr_pages:
        doc.warnings.append(f"{len(doc.scanned_pages)} scanned page(s) without text: "
                            f"{_ranges(doc.scanned_pages)}. OCR engine (Tesseract) not installed - these pages "
                            f"could not be reviewed and are reported as not verified.")
    elif doc.ocr_pages:
        doc.warnings.append(f"OCR used on page(s) {_ranges(doc.ocr_pages)}. OCR text may contain errors - "
                            f"quotes from these pages must be checked against the original.")
    doc.title = meta_title if len(meta_title) > 8 else ""
    entries, toc_pages = _parse_toc(doc.page_texts)
    _levels_from_indent(entries, toc_indent)
    doc.toc = _locate_toc(entries, doc.page_texts, toc_pages)
    if len(doc.toc) >= 5 and len(doc.toc) >= 0.5 * len(entries):
        doc.sections = _sections_from_toc(doc.toc, doc.page_texts)  # the document's own structure
    else:
        doc.toc = []
        doc.sections = _sections_from_lines(doc.page_texts, True)
    doc.header_footer = _repeated_lines(doc.page_texts)
    _metadata(doc)
    return doc


def _docx_numbered(p) -> bool:
    """True when Word numbers this paragraph automatically (paragraph or heading style numbering)."""
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    ppr = p._p.pPr
    if ppr is not None and ppr.find(W + "numPr") is not None:
        nid = ppr.find(W + "numPr").find(W + "numId")
        return nid is None or nid.get(W + "val") != "0"
    st = p.style
    for _ in range(6):  # follow 'based on' styles
        if st is None:
            return False
        sp = st.element.find(W + "pPr")
        if sp is not None and sp.find(W + "numPr") is not None:
            nid = sp.find(W + "numPr").find(W + "numId")
            return nid is None or nid.get(W + "val") != "0"
        st = st.base_style
    return False


def parse_docx(path: Path, progress=None) -> ParsedDocument:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    d = Document(str(path))
    doc = ParsedDocument(str(path), "docx")
    lines: list[str] = []
    sections: list[Section] = []
    body = d.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, d)
            txt = p.text.strip()
            if not txt:
                continue
            style = (p.style.name if p.style is not None else "") or ""
            lvl = None
            m = re.match(r"Heading\s*(\d)", style)
            if m:
                lvl = int(m.group(1))
            elif HEADING_RE.match(txt) and len(txt) < 100 and not txt.endswith("."):
                lvl = txt.split()[0].count(".") + 1
            if lvl and not TOC_LINE_RE.search(txt):
                hm = HEADING_RE.match(txt)
                num, title = (hm.group(1), hm.group(2)) if hm else ("", txt)
                sec = Section(num, title.strip(), None, lvl)
                sec.auto_numbered = not num and _docx_numbered(p)  # Word list numbering, not in the text
                sections.append(sec)
            lines.append(txt)
        elif tag == "tbl":
            t = Table(child, d)
            rows = []
            for r in t.rows:
                cells = []
                for c in r.cells:
                    v = " ".join(c.text.split())
                    if not cells or cells[-1] != v:  # merged cells repeat their text
                        cells.append(v)
                rows.append(cells)
            doc.tables.append(rows)
            lines.extend(" | ".join(r) for r in rows)
    text = "\n".join(lines)
    # split into pseudo-pages of ~3500 characters so quotes can be located
    chunk = 3500
    doc.page_texts = [text[i:i + chunk] for i in range(0, len(text), chunk)] or [""]
    for s in d.sections:
        for part in (s.header, s.footer):
            for p in part.paragraphs:
                if p.text.strip():
                    doc.header_footer.append(p.text.strip())
            for t in part.tables:
                for r in t.rows:
                    v = " | ".join(dict.fromkeys(c.text.strip() for c in r.cells))
                    if v.strip(" |"):
                        doc.header_footer.append(v)
    full = text
    for i, s in enumerate(sections):
        start = full.find(s.title)
        nxt = full.find(sections[i + 1].title, start + 1) if i + 1 < len(sections) else len(full)
        s.text = full[start:nxt if nxt > start else len(full)][:20000] if start >= 0 else ""
    # Word's automatic heading numbers (1, 1.1, 1.2 ...) are not part of the text: rebuild them
    counters: list[int] = []
    for sec in sections:
        if sec.number and re.fullmatch(r"\d+(\.\d+)*", sec.number):
            counters = [int(x) for x in sec.number.split(".")]
        elif getattr(sec, "auto_numbered", False):
            lvl = max(1, sec.level)
            counters = (counters + [0] * lvl)[:lvl]
            counters[lvl - 1] += 1
            sec.number = ".".join(str(c) for c in counters)
    doc.sections = sections
    doc.title = (d.core_properties.title or "").strip()
    _metadata(doc)
    if progress:
        progress(100)
    return doc


def parse_xlsx(path: Path, progress=None) -> ParsedDocument:
    from openpyxl import load_workbook
    doc = ParsedDocument(str(path), "xlsx")
    wb = load_workbook(str(path), read_only=True, data_only=True)  # formulas are never evaluated or executed
    for ws in wb.worksheets:
        rows = []
        for r in ws.iter_rows(values_only=True):
            cells = ["" if v is None else str(v) for v in r]
            if any(c.strip() for c in cells):
                rows.append(cells)
        doc.tables.append(rows)
        txt = "\n".join(" | ".join(c for c in r if c) for r in rows)
        doc.page_texts.append(f"[Sheet: {ws.title}]\n{txt}")
        doc.sections.append(Section("", ws.title, None, 1, txt[:20000]))
    wb.close()
    _metadata(doc)
    if progress:
        progress(100)
    return doc


def parse_txt(path: Path, progress=None) -> ParsedDocument:
    raw = Path(path).read_bytes()
    for enc in ("utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    doc = ParsedDocument(str(path), "txt")
    chunk = 3500
    doc.page_texts = [text[i:i + chunk] for i in range(0, len(text), chunk)] or [""]
    doc.sections = _sections_from_lines(doc.page_texts, False)
    _metadata(doc)
    if progress:
        progress(100)
    return doc


def parse_document(path: str | Path, use_ocr: bool = True, progress=None) -> ParsedDocument:
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".pdf":
        return parse_pdf(p, use_ocr, progress)
    if ext == ".docx":
        return parse_docx(p, progress)
    if ext == ".xlsx":
        return parse_xlsx(p, progress)
    if ext == ".txt":
        return parse_txt(p, progress)
    raise ValueError(f"Unsupported file type: {ext}")


def _ranges(pages: list[int]) -> str:
    out, start, prev = [], None, None
    for p in pages:
        if start is None:
            start = prev = p
        elif p == prev + 1:
            prev = p
        else:
            out.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = p
    if start is not None:
        out.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(out)
