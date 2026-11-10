"""DO-178B / DO-178C knowledge base access (Annex A objectives, DAL applicability)."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from core.app_context import bundled_resource


def _standards_dir() -> Path:
    return bundled_resource("standards")


@lru_cache(maxsize=4)
def annex_a(standard: str) -> dict | None:
    """Annex A table for the standard, or None when it is not available (DO-178B)."""
    folder = "do178c" if standard == "DO-178C" else "do178b"
    f = _standards_dir() / folder / "annex_a.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def objectives(standard: str, dal: str | None = None) -> list[dict]:
    data = annex_a(standard)
    if not data:
        return []
    out = []
    for table in data["tables"]:
        for obj in table["objectives"]:
            if dal is None or dal in obj["levels"]:
                out.append({**obj, "table": table["id"], "table_title": table["title"]})
    return out


def objective_counts(standard: str) -> dict[str, dict[str, int]]:
    res = {}
    for dal in "ABCD":
        objs = objectives(standard, dal)
        res[dal] = {"applicable": len(objs), "independence": sum(1 for o in objs if o["levels"][dal] == "I")}
    return res


def dal_applies(applicability: str, dal: str) -> bool:
    """Interpret a checklist 'Level Applicability' value such as 'All', 'A, B, C', 'A,B' or 'If used'."""
    if dal == "E":
        return False
    text = (applicability or "All").strip()
    if not text or text.lower().startswith("all") or text.lower().startswith("if") or text.lower() == "mixed dal":
        return True
    levels = set(re.findall(r"\b([A-E])\b", text.upper()))
    return dal in levels if levels else True


TABLE_REF = re.compile(r"Table\s+A-(\d+)\s*(?:obj(?:ective)?\.?\s*|,\s*)?(\d+)?", re.I)


def objective_for_reference(standard: str, reference: str) -> dict | None:
    """Find the Annex A objective named in a reference text such as 'DO-178C Table A-7 obj.5'."""
    m = TABLE_REF.search(reference or "")
    if not m or not m.group(2):
        return None
    tid, num = f"A-{int(m.group(1))}", int(m.group(2))
    for o in objectives(standard):
        if o["table"] == tid and o["number"] == num:
            return o
    return None
