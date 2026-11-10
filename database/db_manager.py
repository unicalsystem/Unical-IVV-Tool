"""SQLite access layer. All SQL lives here; UI and core modules call these methods."""
from __future__ import annotations

import logging
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger(__name__)
SCHEMA_VERSION = "2"
MIGRATIONS = {  # table -> [(column, definition)] added after schema version 1
    "review_sessions": [("checklist_id", "INTEGER"), ("recommendation", "TEXT DEFAULT ''"),
                        ("results_json", "TEXT DEFAULT ''"), ("report_doc_no", "TEXT DEFAULT ''")],
    "checklist_items": [("rule", "TEXT")],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _schema_file() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "database" / "schema.sql"


class DatabaseManager:
    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)

    # ---------------------------------------------------------------- basics
    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialise(self) -> None:
        """Create tables if needed. Safe to call on every start."""
        script = _schema_file().read_text(encoding="utf-8")
        with self.connect() as conn:
            conn.executescript(script)
            for table, cols in MIGRATIONS.items():
                have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                for col, ddl in cols:
                    if col not in have:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
            conn.execute("INSERT OR REPLACE INTO schema_info(key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
            conn.execute("INSERT OR IGNORE INTO schema_info(key, value) VALUES ('created_at', ?)", (utc_now(),))
        log.info("Database ready at %s", self.db_path)

    def schema_version(self) -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM schema_info WHERE key='schema_version'").fetchone()
            return row["value"] if row else ""

    # ----------------------------------------------------------------- users
    def get_user(self, username: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
            return dict(row) if row else None

    def create_user(self, username: str, full_name: str, role: str, pw_hash: str, salt: str, iterations: int) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO users(username, full_name, role, password_hash, password_salt, hash_iterations, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (username, full_name, role, pw_hash, salt, iterations, utc_now()))
            return int(cur.lastrowid)

    def record_login_failure(self, username: str, locked_until: str | None) -> int:
        with self.connect() as conn:
            conn.execute("UPDATE users SET failed_attempts = failed_attempts + 1, locked_until = COALESCE(?, locked_until)"
                         " WHERE username = ?", (locked_until, username))
            row = conn.execute("SELECT failed_attempts FROM users WHERE username = ?", (username,)).fetchone()
            return int(row["failed_attempts"]) if row else 0

    def record_login_success(self, username: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login_at = ? WHERE username = ?",
                         (utc_now(), username))

    # ------------------------------------------------------------- audit log
    def audit(self, username: str, event: str, details: str = "") -> None:
        try:
            with self.connect() as conn:
                conn.execute("INSERT INTO audit_log(ts, username, event, details) VALUES (?, ?, ?, ?)",
                             (utc_now(), username or "", event, details[:2000]))
        except sqlite3.Error as exc:  # audit must never crash the app
            log.error("Audit log write failed: %s", exc)

    # ------------------------------------------------------------- dashboard
    def dashboard_stats(self) -> dict[str, int]:
        q = {
            "total_reviews": "SELECT COUNT(*) FROM review_sessions WHERE status != 'Cancelled'",
            "completed": "SELECT COUNT(*) FROM review_sessions WHERE status = 'Completed'",
            "pending": "SELECT COUNT(*) FROM review_sessions WHERE status IN ('Draft','In Progress','Pending Manual Review')",
            "findings": "SELECT COUNT(*) FROM findings WHERE status != 'Withdrawn'",
            "open_findings": "SELECT COUNT(*) FROM findings WHERE status IN ('Open','Not Closed','Pending Clarification')",
            "documents": "SELECT COUNT(DISTINCT sha256) FROM documents WHERE role = 'primary'",
        }
        with self.connect() as conn:
            return {k: int(conn.execute(sql).fetchone()[0]) for k, sql in q.items()}

    def findings_by_severity(self) -> dict[str, int]:
        out = {"Major": 0, "Minor": 0, "Observation": 0}
        with self.connect() as conn:
            for row in conn.execute("SELECT severity, COUNT(*) n FROM findings WHERE status != 'Withdrawn' GROUP BY severity"):
                out[row["severity"]] = int(row["n"])
        return out

    def recent_reviews(self, limit: int = 15) -> list[dict[str, Any]]:
        sql = """
            SELECT s.id, COALESCE(p.name, '-') AS project, s.standard, s.dal, s.soi_stage, s.document_type,
                   s.review_version, s.status, s.started_by, s.started_at,
                   (SELECT COUNT(*) FROM findings f WHERE f.session_id = s.id AND f.status != 'Withdrawn') AS findings
            FROM review_sessions s LEFT JOIN projects p ON p.id = s.project_id
            ORDER BY s.started_at DESC, s.id DESC LIMIT ?"""
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, (limit,))]

    def recent_activity(self, limit: int = 15) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT ts, username, event, details FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))]

    # ------------------------------------------------- review sessions (core)
    def create_review_session(self, standard: str, dal: str, soi: str, document_type: str, started_by: str,
                              project_id: int | None = None, status: str = "Draft") -> int:
        """Never overwrites: a repeat review of the same project/doc type gets the next review_version."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(review_version), 0) FROM review_sessions WHERE COALESCE(project_id, 0) = COALESCE(?, 0)"
                " AND document_type = ? AND soi_stage = ?", (project_id, document_type, soi)).fetchone()
            version = int(row[0]) + 1
            cur = conn.execute(
                "INSERT INTO review_sessions(project_id, standard, dal, soi_stage, document_type, review_version, status,"
                " started_by, started_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (project_id, standard, dal, soi, document_type, version, status, started_by, utc_now()))
            return int(cur.lastrowid)

    def create_project(self, name: str, **fields: Any) -> int:
        allowed = {"customer", "system_lru", "part_number", "standard", "dal", "certification_basis"}
        cols = {k: v for k, v in fields.items() if k in allowed}
        with self.connect() as conn:
            cur = conn.execute(
                f"INSERT INTO projects(name, created_at{''.join(', ' + c for c in cols)}) VALUES (?, ?{', ?' * len(cols)})",
                (name, utc_now(), *cols.values()))
            return int(cur.lastrowid)

    # ------------------------------------------------------------- projects
    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY name")]

    def get_or_create_project(self, name: str, **fields: Any) -> int:
        name = name.strip()
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM projects WHERE name = ?", (name,)).fetchone()
        if row:
            pid = int(row["id"])
            allowed = {"customer", "system_lru", "part_number", "standard", "dal", "certification_basis"}
            upd = {k: v for k, v in fields.items() if k in allowed and v}
            if upd:
                with self.connect() as conn:
                    conn.execute(f"UPDATE projects SET {', '.join(k + '=?' for k in upd)} WHERE id = ?",
                                 (*upd.values(), pid))
            return pid
        return self.create_project(name, **fields)

    # ------------------------------------------------------------- sessions
    SESSION_FIELDS = {"status", "analysis_mode", "checklist_mode", "completed_at", "notes", "checklist_id",
                      "recommendation", "results_json", "report_doc_no", "review_round"}

    def update_session(self, session_id: int, **fields: Any) -> None:
        upd = {k: v for k, v in fields.items() if k in self.SESSION_FIELDS}
        if not upd:
            return
        with self.connect() as conn:
            conn.execute(f"UPDATE review_sessions SET {', '.join(k + '=?' for k in upd)} WHERE id = ?",
                         (*upd.values(), session_id))

    def get_session(self, session_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT s.*, p.name AS project, p.customer, p.system_lru, p.part_number, p.certification_basis "
                "FROM review_sessions s LEFT JOIN projects p ON p.id = s.project_id WHERE s.id = ?",
                (session_id,)).fetchone()
            return dict(row) if row else None

    def search_sessions(self, text: str = "", project_id: int | None = None, soi: str = "", dal: str = "",
                        standard: str = "", status: str = "", limit: int = 500) -> list[dict[str, Any]]:
        sql = ["SELECT s.id, COALESCE(p.name,'-') AS project, s.standard, s.dal, s.soi_stage, s.document_type,",
               "s.review_version, s.review_round, s.status, s.analysis_mode, s.recommendation, s.started_by,",
               "s.started_at, s.completed_at,",
               "(SELECT COUNT(*) FROM findings f WHERE f.session_id=s.id AND f.status!='Withdrawn' AND",
               " f.approval_state!='Rejected') AS findings,",
               "(SELECT file_name FROM documents d WHERE d.session_id=s.id AND d.role='primary' LIMIT 1) AS file_name",
               "FROM review_sessions s LEFT JOIN projects p ON p.id = s.project_id WHERE 1=1"]
        args: list[Any] = []
        if project_id:
            sql.append("AND s.project_id = ?")
            args.append(project_id)
        for col, val in (("s.soi_stage", soi), ("s.dal", dal), ("s.standard", standard), ("s.status", status)):
            if val:
                sql.append(f"AND {col} = ?")
                args.append(val)
        if text:
            sql.append("AND (p.name LIKE ? OR s.document_type LIKE ? OR EXISTS (SELECT 1 FROM documents d WHERE "
                       "d.session_id = s.id AND (d.file_name LIKE ? OR d.doc_number LIKE ? OR d.doc_title LIKE ?)))")
            like = f"%{text}%"
            args += [like] * 5
        sql.append("ORDER BY s.started_at DESC, s.id DESC LIMIT ?")
        args.append(limit)
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(" ".join(sql), args)]

    # ------------------------------------------------------------- documents
    def add_document(self, session_id: int, role: str, file_name: str, stored_path: str, sha256: str, size: int,
                     **meta: Any) -> int:
        cols = {"doc_title", "doc_number", "doc_version", "detected_type", "type_confidence", "page_count",
                "has_text", "is_scanned"}
        extra = {k: v for k, v in meta.items() if k in cols}
        with self.connect() as conn:
            cur = conn.execute(
                f"INSERT INTO documents(session_id, role, file_name, stored_path, sha256, file_size, uploaded_at"
                f"{''.join(', ' + c for c in extra)}) VALUES (?, ?, ?, ?, ?, ?, ?{', ?' * len(extra)})",
                (session_id, role, file_name, stored_path, sha256, size, utc_now(), *extra.values()))
            return int(cur.lastrowid)

    def get_documents(self, session_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM documents WHERE session_id = ? ORDER BY role = 'primary' DESC, id", (session_id,))]

    def document_library(self, text: str = "") -> list[dict[str, Any]]:
        sql = ("SELECT d.*, s.standard, s.dal, s.soi_stage, s.document_type AS reviewed_as, COALESCE(p.name,'-') AS project "
               "FROM documents d JOIN review_sessions s ON s.id = d.session_id LEFT JOIN projects p ON p.id = s.project_id "
               "WHERE d.role != 'checklist'")
        args: list[Any] = []
        if text:
            sql += " AND (d.file_name LIKE ? OR d.doc_number LIKE ? OR d.doc_title LIKE ? OR p.name LIKE ?)"
            args = [f"%{text}%"] * 4
        sql += " ORDER BY d.uploaded_at DESC"
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, args)]

    # ------------------------------------------------------------- checklists
    def save_checklist(self, checklist: dict, created_by: str = "") -> tuple[int, dict[str, int]]:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO checklists(name, source, standard, soi_stage, document_type, version, file_path, created_by,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (checklist.get("name", ""), "User" if checklist.get("source") in ("User", "Combined") else "Built-in",
                 checklist.get("standard") or "DO-178C", checklist.get("soi") or "", checklist.get("document_type") or "",
                 str(checklist.get("version", "")), checklist.get("origin", ""), created_by, utc_now()))
            cid = int(cur.lastrowid)
            ids: dict[str, int] = {}
            for order, it in enumerate(checklist["items"]):
                c2 = conn.execute(
                    "INSERT INTO checklist_items(checklist_id, checklist_ref, sheet, group_title, dal_applicability,"
                    " section_number, section_title, review_question, expected_evidence, reference, applicability,"
                    " condition_text, review_guidance, rule, sort_order) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cid, it["ref"], it.get("sheet", ""), it.get("group", ""), it.get("dal", "All"),
                     it.get("section", ""), it.get("section_title", ""), it["question"],
                     it.get("expected_evidence", ""), it.get("reference", ""), it.get("applicability", "Mandatory"),
                     it.get("condition", ""), it.get("guidance", ""), it.get("rule"), order))
                ids[it["ref"]] = int(c2.lastrowid)
            return cid, ids

    # ------------------------------------------------------------- assessments
    def save_assessments(self, session_id: int, rows: list[dict[str, Any]]) -> list[int]:
        out = []
        with self.connect() as conn:
            for r in rows:
                cur = conn.execute(
                    "INSERT INTO checklist_assessments(session_id, checklist_item_id, verdict, evidence_state, observation,"
                    " evidence, page_ref, recommendation, origin) VALUES (?,?,?,?,?,?,?,?,?)",
                    (session_id, r["item_id"], r["verdict"], r.get("evidence_state"), r.get("observation", ""),
                     r.get("evidence", ""), r.get("page_ref", ""), r.get("recommendation", ""), r.get("origin", "Rule")))
                out.append(int(cur.lastrowid))
        return out

    def get_assessments(self, session_id: int) -> list[dict[str, Any]]:
        sql = """SELECT a.*, i.checklist_ref, i.sheet, i.group_title, i.dal_applicability, i.section_number,
                        i.review_question, i.expected_evidence, i.reference, i.applicability, i.condition_text,
                        i.review_guidance, i.rule,
                        (SELECT GROUP_CONCAT(f.finding_no, ', ') FROM finding_checks fc JOIN findings f ON f.id = fc.finding_id
                         WHERE fc.assessment_id = a.id AND f.approval_state != 'Rejected' AND f.status != 'Withdrawn') AS finding_nos
                 FROM checklist_assessments a JOIN checklist_items i ON i.id = a.checklist_item_id
                 WHERE a.session_id = ? ORDER BY i.sort_order"""
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, (session_id,))]

    def update_assessment(self, assessment_id: int, **fields: Any) -> None:
        allowed = {"verdict", "evidence_state", "observation", "evidence", "page_ref", "recommendation", "origin"}
        upd = {k: v for k, v in fields.items() if k in allowed}
        if upd:
            with self.connect() as conn:
                conn.execute(f"UPDATE checklist_assessments SET {', '.join(k + '=?' for k in upd)} WHERE id = ?",
                             (*upd.values(), assessment_id))

    # ------------------------------------------------------------- findings
    def next_finding_no(self, session_id: int) -> str:
        with self.connect() as conn:
            n = conn.execute("SELECT COUNT(*) FROM findings WHERE session_id = ?", (session_id,)).fetchone()[0]
        return f"FIN-{int(n) + 1:02d}"

    def add_finding(self, session_id: int, data: dict[str, Any], assessment_ids: list[int]) -> int:
        fields = {"document_id", "section_number", "section_title", "reference", "observation", "recommendation",
                  "severity", "severity_rationale", "status", "evidence", "page_ref", "reviewer_comment", "origin",
                  "approval_state"}
        row = {k: v for k, v in data.items() if k in fields}
        row.setdefault("status", "Open")
        no = data.get("finding_no") or self.next_finding_no(session_id)
        with self.connect() as conn:
            cur = conn.execute(
                f"INSERT INTO findings(session_id, finding_no, {', '.join(row)}) VALUES (?, ?{', ?' * len(row)})",
                (session_id, no, *row.values()))
            fid = int(cur.lastrowid)
            for aid in assessment_ids:
                conn.execute("INSERT OR IGNORE INTO finding_checks(finding_id, assessment_id) VALUES (?, ?)", (fid, aid))
            return fid

    def get_findings(self, session_id: int, approved_only: bool = False) -> list[dict[str, Any]]:
        sql = """SELECT f.*, (SELECT GROUP_CONCAT(i.checklist_ref, ', ') FROM finding_checks fc
                   JOIN checklist_assessments a ON a.id = fc.assessment_id JOIN checklist_items i ON i.id = a.checklist_item_id
                   WHERE fc.finding_id = f.id) AS checklist_refs,
                   (SELECT COUNT(*) FROM finding_checks fc WHERE fc.finding_id = f.id) AS n_checks
                 FROM findings f WHERE f.session_id = ?"""
        if approved_only:
            sql += " AND f.approval_state = 'Approved' AND f.status != 'Withdrawn'"
        sql += " ORDER BY f.id"
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, (session_id,))]

    def update_finding(self, finding_id: int, **fields: Any) -> None:
        allowed = {"section_number", "section_title", "reference", "observation", "recommendation", "severity",
                   "severity_rationale", "status", "evidence", "page_ref", "reviewer_comment", "approval_state",
                   "approved_by", "approved_at", "customer_response"}
        upd = {k: v for k, v in fields.items() if k in allowed}
        if upd:
            with self.connect() as conn:
                conn.execute(f"UPDATE findings SET {', '.join(k + '=?' for k in upd)} WHERE id = ?",
                             (*upd.values(), finding_id))

    def renumber_findings(self, session_id: int) -> None:
        """Approved / draft findings numbered FIN-01.. in order; rejected ones moved to the end (REJ-xx)."""
        with self.connect() as conn:
            rows = conn.execute("SELECT id, approval_state FROM findings WHERE session_id = ? ORDER BY id",
                                (session_id,)).fetchall()
            conn.execute("UPDATE findings SET finding_no = 'TMP-' || id WHERE session_id = ?", (session_id,))
            n = r = 0
            for row in rows:
                if row["approval_state"] == "Rejected":
                    r += 1
                    no = f"REJ-{r:02d}"
                else:
                    n += 1
                    no = f"FIN-{n:02d}"
                conn.execute("UPDATE findings SET finding_no = ? WHERE id = ?", (no, row["id"]))

    # ------------------------------------------------------------- reports
    def add_report(self, session_id: int, report_type: str, path: str, sha256: str, created_by: str) -> int:
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO reports(session_id, report_type, file_path, sha256, created_by, created_at)"
                               " VALUES (?, ?, ?, ?, ?, ?)", (session_id, report_type, path, sha256, created_by, utc_now()))
            return int(cur.lastrowid)

    def get_reports(self, session_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM reports WHERE session_id = ? ORDER BY id DESC",
                                                  (session_id,))]
