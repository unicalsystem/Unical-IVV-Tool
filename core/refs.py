"""How locations in a reviewed document are written in results and reports.

Pages are written as 'Page 29' (physical page of the file, as shown by a PDF viewer) and
sections with the number and title from the document's own table of contents, e.g.
'Page 29, Section 3.8 Fault Tolerance'.
"""
from __future__ import annotations

import re


def page_ref(page: int | None, last: int | None = None) -> str:
    if not page:
        return ""
    if last and last != page:
        return f"Pages {page}-{last}"
    return f"Page {page}"


def section_ref(number: str = "", title: str = "") -> str:
    title = " ".join((title or "").split())
    if len(title) > 80:
        title = title[:77].rstrip() + "..."
    if number and title:
        return f"Section {number} {title}"
    if title:
        return f"Section '{title}'"
    return f"Section {number}" if number else ""


def location(page: int | None = None, section=None) -> str:
    """'Page 29, Section 3.8 Fault Tolerance' (either part may be missing)."""
    sec = section_ref(getattr(section, "number", ""), getattr(section, "title", "")) if section is not None else ""
    return ", ".join(x for x in (page_ref(page), sec) if x)


def doc_location(doc, page: int | None, snippet: str | None = None) -> str:
    """Location of a snippet (or page) in a parsed document, using its table of contents."""
    if not page:
        return ""
    pos = None
    if snippet and page <= len(doc.page_texts):
        text = doc.page_texts[page - 1]
        key = " ".join(snippet.split())[:40]
        flat = " ".join(text.split())
        i = flat.find(key)
        if i >= 0:  # map back to an approximate offset in the raw page text
            pos = int(i * len(text) / max(1, len(flat)))
    return location(page, doc.section_for(page, pos))


_P_RANGE = re.compile(r"\bp\.\s?(\d+)\s*[-–]\s*(\d+)\b")
_P_ONE = re.compile(r"\bp\.\s?(\d+)\b")
_SEC = re.compile(r"\bSec\.\s")


def humanise(text: str | None) -> str:
    """Rewrite older short references ('p.29, Sec. 3.8') in the 'Page 29, Section 3.8' style."""
    if not text:
        return text or ""
    text = _P_RANGE.sub(r"Pages \1-\2", text)
    text = _P_ONE.sub(r"Page \1", text)
    return _SEC.sub("Section ", text)
