"""Database foundation tests."""
import sqlite3

import pytest

EXPECTED_TABLES = {"schema_info", "users", "projects", "review_sessions", "documents", "checklists", "checklist_items",
                   "findings", "checklist_assessments", "finding_checks", "reports", "audit_log"}


def test_schema_created(db):
    with sqlite3.connect(db.db_path) as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES <= names
    assert db.schema_version() == "1"


def test_initialise_is_idempotent(db):
    db.initialise()
    db.initialise()
    assert db.schema_version() == "1"


def test_empty_dashboard_stats(db):
    s = db.dashboard_stats()
    assert s == {"total_reviews": 0, "completed": 0, "pending": 0, "findings": 0, "open_findings": 0, "documents": 0}


def test_review_versions_never_overwritten(db):
    pid = db.create_project("Digital MSU", standard="DO-178C", dal="A")
    a = db.create_review_session("DO-178C", "A", "SOI-1", "PSAC", "admin", pid)
    b = db.create_review_session("DO-178C", "A", "SOI-1", "PSAC", "admin", pid)
    rows = {r["id"]: r for r in db.recent_reviews()}
    assert rows[a]["review_version"] == 1 and rows[b]["review_version"] == 2


def test_dashboard_counts(db):
    sid = db.create_review_session("DO-178C", "A", "SOI-1", "SDP", "admin", status="Completed")
    db.create_review_session("DO-178B", "C", "SOI-2", "SDD", "admin")
    with db.connect() as conn:
        conn.execute("INSERT INTO findings(session_id, finding_no, observation, recommendation, severity, severity_rationale)"
                     " VALUES (?, 'FIN-01', 'obs', 'rec', 'Major', 'objective cannot be shown')", (sid,))
    s = db.dashboard_stats()
    assert (s["total_reviews"], s["completed"], s["pending"], s["findings"], s["open_findings"]) == (2, 1, 1, 1, 1)
    assert db.findings_by_severity()["Major"] == 1


@pytest.mark.parametrize("field,value", [("standard", "DO-254"), ("dal", "F"), ("soi_stage", "SOI-5")])
def test_constraints_reject_invalid_values(db, field, value):
    args = {"standard": "DO-178C", "dal": "A", "soi_stage": "SOI-1"}
    args[field] = value
    with pytest.raises(sqlite3.IntegrityError):
        with db.connect() as conn:
            conn.execute("INSERT INTO review_sessions(standard, dal, soi_stage, document_type, started_by, started_at)"
                         " VALUES (?, ?, ?, 'PSAC', 'admin', '2026-01-01')", (args["standard"], args["dal"], args["soi_stage"]))


def test_invalid_verdict_rejected(db):
    with pytest.raises(sqlite3.IntegrityError):
        with db.connect() as conn:
            conn.execute("INSERT INTO checklists(name, source, standard, soi_stage, document_type, created_at)"
                         " VALUES ('x','Built-in','DO-178C','SOI-1','PSAC','t')")
            conn.execute("INSERT INTO checklist_items(checklist_id, checklist_ref, review_question) VALUES (1,'A-01','q')")
            sid = conn.execute("INSERT INTO review_sessions(standard, dal, soi_stage, document_type, started_by, started_at)"
                               " VALUES ('DO-178C','A','SOI-1','PSAC','admin','t')").lastrowid
            conn.execute("INSERT INTO checklist_assessments(session_id, checklist_item_id, verdict) VALUES (?, 1, 'YES')", (sid,))


def test_audit_log(db):
    db.audit("admin", "TEST", "details")
    assert db.recent_activity(1)[0]["event"] == "TEST"
