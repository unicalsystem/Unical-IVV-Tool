"""Review orchestration: session set-up, safe file storage, parsing, checklist selection,
engine run and persistence. Used by the UI background worker and by the tests."""
from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from core.ai_agent import LocalAIAgent, load_model_config
from core.app_context import AppContext
from core.checklist_engine import combine, load_builtin, read_user_checklist
from core.document_classifier import classify
from core.document_parser import ParsedDocument, parse_document
from core.document_validator import CHECKLIST_ALLOWED, validate_file
from core.review_engine import ReviewEngine, overall_recommendation
from database.db_manager import DatabaseManager, utc_now

log = logging.getLogger(__name__)
SAFE_NAME = re.compile(r"[^A-Za-z0-9._ \-()]+")


@dataclass
class ReviewRequest:
    standard: str
    dal: str
    soi: str
    doc_type: str
    document_path: str
    username: str
    project_name: str = ""
    customer: str = ""
    system_lru: str = ""
    part_number: str = ""
    certification_basis: str = ""
    doc_number: str = ""
    doc_version: str = ""
    companions: list[tuple[str, str]] = field(default_factory=list)
    checklist_path: str = ""
    checklist_mode: str = "Built-in"  # Built-in / User / Combined
    use_ai: bool = False
    review_round: int = 1


class ReviewService:
    def __init__(self, ctx: AppContext, db: DatabaseManager):
        self.ctx, self.db = ctx, db

    @property
    def uploads_dir(self) -> Path:
        d = (self.ctx.root / self.ctx.config.get("uploads_folder", "uploaded_documents")).resolve()
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------ files
    def _store(self, session_id: int, src: str, prefix: str) -> tuple[Path, dict]:
        allowed = CHECKLIST_ALLOWED if prefix == "checklist" else {".pdf", ".docx", ".xlsx", ".txt"}
        val = validate_file(src, allowed)
        if not val.ok:
            raise ValueError(f"{Path(src).name}: " + "; ".join(val.errors))
        folder = self.uploads_dir / f"session_{session_id:05d}"
        folder.mkdir(parents=True, exist_ok=True)
        name = SAFE_NAME.sub("_", Path(src).name)[:150]
        dest = folder / f"{prefix}__{name}"
        n = 2
        while dest.exists():  # never overwrite
            dest = folder / f"{prefix}__{n}_{name}"
            n += 1
        shutil.copy2(src, dest)
        dest.chmod(0o444)  # stored copy is read-only
        return dest, val.info

    # --------------------------------------------------------------- session
    def create_session(self, req: ReviewRequest) -> int:
        pid = None
        if req.project_name.strip():
            pid = self.db.get_or_create_project(req.project_name, customer=req.customer, system_lru=req.system_lru,
                                                part_number=req.part_number, standard=req.standard, dal=req.dal,
                                                certification_basis=req.certification_basis)
        sid = self.db.create_review_session(req.standard, req.dal, req.soi, req.doc_type, req.username, pid,
                                            status="In Progress")
        self.db.update_session(sid, checklist_mode=req.checklist_mode, review_round=req.review_round,
                               analysis_mode="AI-assisted" if req.use_ai else "Rule-based")
        self.db.audit(req.username, "REVIEW_STARTED",
                      f"session {sid}: {req.standard} DAL {req.dal} {req.soi} {req.doc_type} {Path(req.document_path).name}")
        return sid

    def execute(self, sid: int, req: ReviewRequest, progress: Callable[[int, str], None] | None = None,
                cancelled: Callable[[], bool] | None = None) -> dict:
        prog = progress or (lambda p, m: None)
        try:
            return self._execute(sid, req, prog, cancelled)
        except Exception as exc:
            log.exception("Review %s failed", sid)
            self.db.update_session(sid, status="Draft", notes=f"Review failed: {exc}")
            self.db.audit(req.username, "REVIEW_FAILED", f"session {sid}: {exc}")
            raise

    def _execute(self, sid: int, req: ReviewRequest, prog, cancelled) -> dict:
        prog(1, "Storing documents")
        primary_path, info = self._store(sid, req.document_path, "primary")
        prog(3, "Reading the document")
        doc = parse_document(primary_path, progress=lambda p: prog(3 + p // 20, "Reading the document"))
        cls = classify(doc)
        self.db.add_document(sid, "primary", Path(req.document_path).name, str(primary_path), info["sha256"],
                             info["size"], doc_title=doc.title, doc_number=req.doc_number or doc.doc_number,
                             doc_version=req.doc_version or doc.version, detected_type=cls.best or "",
                             type_confidence=cls.confidence, page_count=doc.page_count, has_text=int(doc.has_text),
                             is_scanned=int(doc.is_scanned))
        if req.doc_number:
            doc.doc_number = req.doc_number
        if req.doc_version:
            doc.version = req.doc_version
        companions: list[tuple[str, ParsedDocument]] = []
        for ctype, cpath in req.companions:
            prog(9, f"Reading companion {ctype}")
            stored, cinfo = self._store(sid, cpath, f"companion_{ctype}")
            cdoc = parse_document(stored)
            cdoc.path = Path(cpath).name  # report the user's file name, not the stored copy's
            companions.append((ctype, cdoc))
            self.db.add_document(sid, "companion", Path(cpath).name, str(stored), cinfo["sha256"], cinfo["size"],
                                 doc_title=cdoc.title, doc_number=cdoc.doc_number, doc_version=cdoc.version,
                                 detected_type=ctype, page_count=cdoc.page_count, has_text=int(cdoc.has_text),
                                 is_scanned=int(cdoc.is_scanned))

        prog(10, "Loading checklist")
        builtin = load_builtin(req.standard, req.soi, req.doc_type)
        user = None
        if req.checklist_path:
            stored, cinfo = self._store(sid, req.checklist_path, "checklist")
            self.db.add_document(sid, "checklist", Path(req.checklist_path).name, str(stored), cinfo["sha256"],
                                 cinfo["size"])
            user = read_user_checklist(stored)
            user.update(standard=req.standard, soi=req.soi, document_type=req.doc_type)
        mode = req.checklist_mode if user else "Built-in"
        if builtin is None and user is None:
            raise ValueError(f"No built-in checklist exists for {req.standard} {req.soi} {req.doc_type}. Upload a "
                             "review checklist.")
        checklist = combine(builtin, user, mode if builtin else "User")
        cl_id, item_ids = self.db.save_checklist(checklist, req.username)
        self.db.update_session(sid, checklist_id=cl_id, checklist_mode=mode if builtin else "User")

        ai = None
        if req.use_ai:
            try:
                ai = LocalAIAgent(load_model_config(self.ctx.root))
            except ValueError as exc:
                log.warning("AI disabled: %s", exc)
        engine = ReviewEngine(ai_agent=ai)
        result = engine.run(doc, req.doc_type, req.standard, req.dal, req.soi, checklist, companions,
                            use_ai=req.use_ai, progress=lambda p, m: prog(10 + int(p * 0.85), m), cancelled=cancelled)

        prog(96, "Saving results")
        rows = [{"item_id": item_ids[a.item["ref"]], "verdict": a.verdict, "evidence_state": a.evidence_state,
                 "observation": a.observation.strip(), "evidence": a.evidence, "page_ref": a.page_ref,
                 "recommendation": a.recommendation, "origin": a.origin} for a in result.assessments]
        a_ids = self.db.save_assessments(sid, rows)
        primary_doc_id = self.db.get_documents(sid)[0]["id"]
        for f in result.findings:
            self.db.add_finding(sid, {"document_id": primary_doc_id, "section_number": f.section,
                                      "reference": f.reference, "observation": f.observation,
                                      "recommendation": f.recommendation, "severity": f.severity,
                                      "severity_rationale": f.rationale, "evidence": f.evidence,
                                      "page_ref": f.page_ref, "origin": f.origin, "approval_state": "Draft"},
                                [a_ids[i] for i in f.checks if i is not None and i < len(a_ids)])
        results = {
            "structure": result.structure,
            "consistency": [asdict(c) for c in result.consistency],
            "not_supplied": result.not_supplied,
            "notes": result.notes + doc.warnings,
            "classification": {"best": cls.best, "confidence": cls.confidence, "ranking": cls.ranking,
                               "evidence": cls.evidence},
            "document": {"title": doc.title, "doc_number": doc.doc_number, "version": doc.version, "date": doc.date,
                         "pages": doc.page_count, "dal_mentions": doc.dal_mentions,
                         "standard_mentions": doc.standard_mentions, "scanned_pages": doc.scanned_pages,
                         "ocr_pages": doc.ocr_pages},
            "companions": [{"type": t, "file": Path(c.path).name, "doc_number": c.doc_number, "version": c.version}
                           for t, c in companions],
            "checklist": {"name": checklist["name"], "origin": checklist.get("origin", ""),
                          "items": len(checklist["items"]), "validated": checklist.get("validated", True)},
        }
        cancelled_run = bool(cancelled and cancelled())
        counts = result.counts()
        rec = overall_recommendation([{"severity": f.severity, "status": "Open", "approval_state": "Draft"}
                                      for f in result.findings], counts)
        self.db.update_session(sid, status="Cancelled" if cancelled_run else "Pending Manual Review",
                               analysis_mode=result.analysis_mode, results_json=json.dumps(results),
                               recommendation=rec)
        self.db.audit(req.username, "REVIEW_COMPLETED" if not cancelled_run else "REVIEW_CANCELLED",
                      f"session {sid}: {len(result.findings)} proposed findings, verdicts {counts}")
        prog(100, "Done")
        return {"session_id": sid, "counts": counts, "findings": len(result.findings), "recommendation": rec,
                "mode": result.analysis_mode, "notes": result.notes}

    # ------------------------------------------------------------- finalise
    def finalise(self, sid: int, username: str) -> str:
        """Mark the review completed. Draft findings must be approved or rejected first."""
        findings = self.db.get_findings(sid)
        drafts = [f for f in findings if f["approval_state"] == "Draft"]
        if drafts:
            raise ValueError(f"{len(drafts)} finding(s) are still Draft. Approve or reject every finding first.")
        counts: dict[str, int] = {}
        for a in self.db.get_assessments(sid):
            counts[a["verdict"]] = counts.get(a["verdict"], 0) + 1
        rec = overall_recommendation([f for f in findings if f["approval_state"] == "Approved"], counts)
        self.db.renumber_findings(sid)
        self.db.update_session(sid, status="Completed", completed_at=utc_now(), recommendation=rec)
        self.db.audit(username, "REVIEW_FINALISED", f"session {sid}: {rec}")
        return rec
