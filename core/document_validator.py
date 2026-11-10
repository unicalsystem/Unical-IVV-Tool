"""File validation before a review starts (Phase 2/3)."""
from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ALLOWED = {".pdf", ".docx", ".xlsx", ".txt"}
CHECKLIST_ALLOWED = {".xlsx", ".docx", ".pdf"}
MAX_BYTES = 250 * 1024 * 1024


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)

    def summary(self) -> str:
        parts = []
        if self.errors:
            parts.append("Errors:\n- " + "\n- ".join(self.errors))
        if self.warnings:
            parts.append("Warnings:\n- " + "\n- ".join(self.warnings))
        if not parts:
            parts.append("File is valid.")
        return "\n\n".join(parts)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def validate_file(path: str | Path, allowed: set[str] = ALLOWED) -> ValidationResult:
    p = Path(path)
    res = ValidationResult(ok=False)
    if not p.exists() or not p.is_file():
        res.errors.append("File not found.")
        return res
    ext = p.suffix.lower()
    if ext not in allowed:
        res.errors.append(f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(allowed))}.")
        return res
    size = p.stat().st_size
    res.info["size"] = size
    if size == 0:
        res.errors.append("The file is empty.")
        return res
    if size > MAX_BYTES:
        res.errors.append(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
        return res
    try:
        with open(p, "rb") as f:
            head = f.read(8)
    except OSError as exc:
        res.errors.append(f"The file cannot be read: {exc}")
        return res
    if ext == ".pdf":
        if not head.startswith(b"%PDF"):
            res.errors.append("The file does not look like a PDF (corrupted or wrong extension).")
            return res
        try:
            import pymupdf
            doc = pymupdf.open(str(p))
        except Exception as exc:  # noqa: BLE001 - PyMuPDF raises several types
            res.errors.append(f"The PDF is corrupted or cannot be opened: {exc}")
            return res
        if doc.needs_pass or doc.is_encrypted and doc.needs_pass:
            res.errors.append("The PDF is password protected. Remove the password and upload it again.")
            doc.close()
            return res
        res.info["pages"] = doc.page_count
        if doc.page_count == 0:
            res.errors.append("The PDF has no pages.")
            doc.close()
            return res
        no_text = []
        for i, page in enumerate(doc):
            if len((page.get_text("text") or "").strip()) < 30:
                no_text.append(i + 1)
        res.info["pages_without_text"] = no_text
        if len(no_text) == doc.page_count:
            res.warnings.append("No extractable text: the PDF appears to be scanned. OCR will be used if Tesseract is "
                                "installed; otherwise the content cannot be reviewed.")
            res.info["scanned"] = True
        elif no_text:
            res.warnings.append(f"{len(no_text)} page(s) have no extractable text (scanned or image-only).")
        doc.close()
    elif ext in (".docx", ".xlsx"):
        if not zipfile.is_zipfile(p):
            res.errors.append(f"The {ext} file is corrupted (not a valid Office Open XML package).")
            return res
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
            if any(n.lower().endswith("vbaproject.bin") for n in names):
                res.warnings.append("The file contains macros. Macros are never executed; only text is read.")
            needed = "word/document.xml" if ext == ".docx" else "xl/workbook.xml"
            if needed not in names:
                res.errors.append(f"The {ext} file is incomplete or not a Word/Excel file.")
                return res
    elif ext == ".txt":
        try:
            p.read_bytes()[:4096].decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            res.warnings.append("Text file is not UTF-8; it will be read with a fallback encoding.")
    res.info["sha256"] = sha256_of(p)
    res.ok = True
    return res
