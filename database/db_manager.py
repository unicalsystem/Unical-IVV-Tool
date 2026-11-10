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
SCHEMA_VERSION = "1"


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
            conn.execute("INSERT OR IGNORE INTO schema_info(key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
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
