"""Local AI review agent (Ollama-compatible HTTP API on the loopback interface only).

Guard-rails:
* Endpoint must be localhost / 127.0.0.1 / ::1 - documents never leave the computer.
* The model sees only the checklist item and the retrieved section text.
* Output must be JSON; every quote is verified verbatim against the source text.
  An unverifiable quote, an invalid verdict or low confidence gives 'PMR'
  (Pending Manual Review). The agent never makes a certification decision.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from core.app_context import bundled_resource

log = logging.getLogger(__name__)
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def load_model_config(root: Path | None = None) -> dict:
    for f in ([root / "config" / "model_config.json"] if root else []) + [bundled_resource("config/model_config.json")]:
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
    return {"enabled": False}


@dataclass
class AIAssessment:
    verdict: str
    evidence_state: str
    quote: str
    page: str
    section: str
    observation: str
    recommendation: str
    confidence: float
    reasoning: str
    verified_quote: bool


SYSTEM_PROMPT = """You are assisting a DO-178 Independent Verification & Validation engineer.
You assess ONE checklist item against extracts from ONE document.
Rules:
- Use only the extracts given. Never invent content, references or page numbers.
- If the extracts do not contain the information, say so: evidence_state "Not Present" or "Cannot Verify".
  A missing statement is not proof that the activity was not performed.
- Never claim compliance without quoting the supporting text exactly (copy it character for character).
- Do not make a certification decision.
- If you cannot reach a reliable conclusion, use verdict "PMR".
Answer ONLY with JSON:
{"verdict": "C|PC|NC|NA|PMR", "evidence_state": "Present|Present-Incomplete|Present-Inconsistent|Not Present|Cannot Verify|Not Applicable",
 "quote": "<exact text copied from the extracts, max 300 chars, or empty>", "page": "<page number shown in the extract header or empty>",
 "section": "<section shown in the extract header or empty>", "observation": "<what was found and where>",
 "recommendation": "<specific corrective action if verdict is PC or NC, else empty>", "confidence": 0.0-1.0,
 "reasoning": "<one or two sentences>"}"""


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


class LocalAIAgent:
    def __init__(self, config: dict):
        self.cfg = config
        self.endpoint = (config.get("endpoint") or "http://127.0.0.1:11434").rstrip("/")
        host = urlparse(self.endpoint).hostname or ""
        if host not in LOOPBACK:
            raise ValueError(f"AI endpoint '{self.endpoint}' is not on this computer. Only localhost endpoints are "
                             "allowed - documents must not leave the computer.")
        self.model = config.get("model_name", "")
        self.timeout = float(config.get("timeout_seconds", 180))
        self.last_error = ""

    # ------------------------------------------------------------------ status
    def is_available(self) -> bool:
        if not self.cfg.get("enabled"):
            self.last_error = "AI-assisted analysis is disabled in Settings."
            return False
        try:
            with urllib.request.urlopen(self.endpoint + "/api/tags", timeout=3) as r:
                tags = json.loads(r.read().decode("utf-8"))
            names = [m.get("name", "") for m in tags.get("models", [])]
            if self.model and not any(n == self.model or n.split(":")[0] == self.model.split(":")[0] for n in names):
                self.last_error = f"Model '{self.model}' is not installed in the local runtime ({', '.join(names) or 'none'})."
                return False
            return True
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            self.last_error = f"Local AI runtime not reachable at {self.endpoint}: {exc}"
            return False

    # ------------------------------------------------------------------ assess
    def _generate(self, prompt: str) -> str:
        body = json.dumps({
            "model": self.model, "system": SYSTEM_PROMPT, "prompt": prompt, "stream": False, "format": "json",
            "options": {"temperature": float(self.cfg.get("temperature", 0.1)),
                        "num_ctx": int(self.cfg.get("context_length", 8192)),
                        "num_predict": int(self.cfg.get("max_output_tokens", 1500))},
        }).encode("utf-8")
        req = urllib.request.Request(self.endpoint + "/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("response", "")

    def assess(self, item: dict, doc_type: str, standard: str, dal: str, soi: str,
               extracts: list[tuple[str, str]], source_text: str) -> AIAssessment:
        ctx_budget = int(self.cfg.get("context_length", 8192)) * 3  # ~chars
        blocks, used = [], 0
        for header, text in extracts:
            take = text[: max(0, min(len(text), ctx_budget - used - 1500))]
            if not take:
                break
            blocks.append(f"### EXTRACT [{header}]\n{take}")
            used += len(take)
        prompt = (f"Standard: {standard}. Software level: {dal}. Stage: {soi}. Document type: {doc_type}.\n"
                  f"Checklist item {item.get('ref')}: {item.get('question')}\n"
                  f"Expected evidence: {item.get('expected_evidence') or '-'}\n"
                  f"Reference: {item.get('reference') or '-'}\n"
                  f"Review guidance: {item.get('guidance') or '-'}\n\n" + "\n\n".join(blocks))
        try:
            raw = self._generate(prompt)
            data = json.loads(raw)
        except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as exc:
            self.last_error = str(exc)
            return AIAssessment("PMR", "Cannot Verify", "", "", "", f"AI analysis failed: {exc}", "", 0.0, "", False)
        verdict = str(data.get("verdict", "PMR")).upper()
        if verdict not in ("C", "PC", "NC", "NA", "PMR"):
            verdict = "PMR"
        state = data.get("evidence_state", "Cannot Verify")
        quote = str(data.get("quote", "") or "")[:400]
        verified = bool(quote) and _norm(quote) in _norm(source_text)
        conf = float(data.get("confidence", 0) or 0)
        reasoning = str(data.get("reasoning", ""))
        obs = str(data.get("observation", ""))
        if quote and not verified:
            obs = f"[Quote could not be verified in the document - AI result not accepted] {obs}"
            verdict = "PMR"
        if verdict in ("C", "PC") and not verified:
            verdict = "PMR"  # no compliance claim without a verified quote
        if conf < 0.5 and verdict != "PMR":
            verdict = "PMR"
            reasoning = f"Low confidence ({conf:.2f}). {reasoning}"
        return AIAssessment(verdict, state, quote if verified else "", str(data.get("page", "")),
                            str(data.get("section", "")), obs, str(data.get("recommendation", "")), conf,
                            reasoning, verified)
