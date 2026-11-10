"""Proposes a finding severity with a written rationale. Configurable; never keyword-only."""
from __future__ import annotations

import json
from pathlib import Path

from core.app_context import bundled_resource

DEFAULT_RULES = {
    "major_dal_levels": ["A", "B"],
    "by_sheet": {"A": {"NC": "Minor", "PC": "Observation"}, "B": {"NC": "Major", "PC": "Minor"},
                 "C": {"NC": "Major", "PC": "Minor"}, "D": {"NC": "Major", "PC": "Minor"},
                 "E": {"NC": "Observation", "PC": "Observation"}, "F": {"NC": "by_dal", "PC": "Minor"},
                 "U": {"NC": "Major", "PC": "Minor"}},
    "by_rule": {},
    "consistency": {"dal": "Major", "standard": "Major", "doc_number": "Minor", "version": "Minor",
                    "tool_version": "Minor", "other": "Observation"},
    "conditional_items_downgrade": True,
}

SHEET_MEANING = {
    "A": "document control / identification",
    "B": "content required by the authority template or DO-178 Section 11",
    "C": "evidence for a DO-178 Annex A objective",
    "D": "consistency with the companion plans and data",
    "E": "clarity and auditability of the text",
    "F": "engineering depth of the content",
    "U": "a check from the user-supplied checklist",
}
ORDER = {"Observation": 0, "Minor": 1, "Major": 2}


class SeverityClassifier:
    def __init__(self, rules_file: Path | None = None):
        self.rules = dict(DEFAULT_RULES)
        f = rules_file or bundled_resource("config/severity_rules.json")
        if f and Path(f).exists():
            try:
                self.rules.update(json.loads(Path(f).read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                pass

    def classify(self, item: dict, verdict: str, dal: str, evidence_state: str = "") -> tuple[str, str]:
        """Return (severity, rationale) for a check with verdict NC or PC."""
        sheet = item.get("sheet") or "U"
        rule = item.get("rule")
        table = self.rules["by_rule"].get(rule, {}) if rule else {}
        sev = table.get(verdict) or self.rules["by_sheet"].get(sheet, {}).get(verdict, "Minor")
        if sev == "by_dal":
            sev = "Major" if dal in self.rules["major_dal_levels"] else "Minor"
        reasons = [f"The check concerns {SHEET_MEANING.get(sheet, 'the document')}"
                   f"{' (' + item['reference'] + ')' if item.get('reference') else ''}."]
        if verdict == "NC":
            reasons.append("The required information was not found in the document.")
        else:
            reasons.append("The information is present but incomplete or inconsistent.")
        if evidence_state == "Cannot Verify":
            reasons.append("Evidence could not be verified from the supplied data.")
        if sev == "Major":
            reasons.append("Left unresolved, this could prevent demonstration of compliance with the applicable "
                           f"DO-178 objective or acceptance of the document at software level {dal}.")
        elif sev == "Minor":
            reasons.append("It needs correction or clarification but does not by itself establish a compliance "
                           "deficiency.")
        else:
            reasons.append("It is an improvement or editorial point with no identified compliance deficiency.")
        if self.rules.get("conditional_items_downgrade") and item.get("applicability") == "Conditional" \
                and sev == "Major":
            sev = "Minor"
            reasons.append(f"Downgraded to Minor because the check is conditional ({item.get('condition')}); "
                           "raise to Major if the condition applies.")
        return sev, " ".join(reasons)

    def consistency(self, topic: str) -> tuple[str, str]:
        sev = self.rules["consistency"].get(topic, self.rules["consistency"]["other"])
        why = {"dal": "Different software levels across the plan set would change the applicable objectives.",
               "standard": "Different certification standards across the plan set make the basis ambiguous.",
               "doc_number": "Wrong document numbers break configuration identification and traceability.",
               "version": "Wrong issue references mean the plans may not refer to the approved baseline.",
               "tool_version": "Different tool versions affect reproducibility and tool qualification credit."}
        return sev, why.get(topic, "Inconsistency between documents that should be aligned.")
