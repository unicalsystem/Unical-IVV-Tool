"""End-to-end service, history persistence and report generation (section 16)."""
import json
import shutil
from pathlib import Path

import pytest
from openpyxl import load_workbook

from core.app_context import DEFAULT_CONFIG, AppContext
from core.report_manager import generate_reports
from core.review_service import ReviewRequest, ReviewService
from database.db_manager import DatabaseManager
from tests.factory import PSAC_TEXT, SDD_TEXT, make_pdf, make_txt, make_user_checklist_xlsx


@pytest.fixture
def env(tmp_path):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    cfg["database_file"] = "db/test.db"
    cfg["report"]["signatories"]["prepared"]["name"] = "Test Engineer"
    ctx = AppContext(root=tmp_path, config=cfg)
    db = DatabaseManager(ctx.db_path)
    db.initialise()
    return ctx, db, ReviewService(ctx, db)


def _run(env, tmp_path, **kw):
    ctx, db, svc = env
    text = "\n".join(l for l in PSAC_TEXT.splitlines() if "Revision History" not in l) + "\nValue TBD."
    req = ReviewRequest("DO-178C", "A", "SOI-1", "PSAC", str(make_pdf(tmp_path / "in.pdf", text)), "admin",
                        project_name="Test Project", customer="Test Customer", **kw)
    sid = svc.create_session(req)
    out = svc.execute(sid, req)
    return sid, out


def test_full_review_persisted(env, tmp_path):
    ctx, db, svc = env
    sid, out = _run(env, tmp_path, companions=[("SDD", str(make_txt(tmp_path / "sdd.txt", SDD_TEXT)))])
    s = db.get_session(sid)
    assert s["status"] == "Pending Manual Review" and s["checklist_id"]
    assert len(db.get_assessments(sid)) == 198
    docs = db.get_documents(sid)
    assert {d["role"] for d in docs} == {"primary", "companion"}
    stored = Path(docs[0]["stored_path"])
    assert stored.exists() and stored.parent.name == f"session_{sid:05d}"
    findings = db.get_findings(sid)
    assert findings and all(f["approval_state"] == "Draft" for f in findings)
    assert all(f["n_checks"] >= 1 for f in findings)


def test_rereview_creates_new_version(env, tmp_path):
    sid1, _ = _run(env, tmp_path)
    sid2, _ = _run(env, tmp_path)
    db = env[1]
    assert db.get_session(sid1)["review_version"] == 1 and db.get_session(sid2)["review_version"] == 2
    assert len(db.get_assessments(sid1)) == len(db.get_assessments(sid2))


def test_user_checklist_review(env, tmp_path):
    sid, out = _run(env, tmp_path, checklist_path=str(make_user_checklist_xlsx(tmp_path / "u.xlsx")),
                    checklist_mode="User")
    refs = [a["checklist_ref"] for a in env[1].get_assessments(sid)]
    assert refs == ["UC-1", "UC-2"]


def test_finalise_requires_decisions(env, tmp_path):
    ctx, db, svc = env
    sid, _ = _run(env, tmp_path)
    with pytest.raises(ValueError):
        svc.finalise(sid, "admin")
    fs = db.get_findings(sid)
    for f in fs:
        db.update_finding(f["id"], approval_state="Approved")
    db.update_finding(fs[0]["id"], approval_state="Rejected", status="Withdrawn")
    svc.finalise(sid, "admin")
    s = db.get_session(sid)
    assert s["status"] == "Completed" and s["recommendation"]
    nos = [f["finding_no"] for f in db.get_findings(sid, approved_only=True)]
    assert nos == [f"FIN-{i:02d}" for i in range(1, len(nos) + 1)]


def test_reports_generated_from_templates(env, tmp_path):
    ctx, db, svc = env
    sid, _ = _run(env, tmp_path)
    fs = db.get_findings(sid)
    for f in fs:
        db.update_finding(f["id"], approval_state="Approved")
    svc.finalise(sid, "admin")
    paths = generate_reports(ctx, db, sid, tmp_path / "out", "admin")
    xlsx = next(p for p in paths if p.suffix == ".xlsx")
    docx = next(p for p in paths if p.suffix == ".docx")
    assert xlsx.name.startswith("Test_Project_DO178C_DALA_SOI1_PSAC_Review_Report")
    wb = load_workbook(xlsx)
    assert wb.sheetnames[:3] == ["Instructions", "Summary", "Findings"]
    assert "C. DO-178C Objectives" in wb.sheetnames and "F. Content Depth" in wb.sheetnames
    ws = wb["Findings"]
    nos = [ws.cell(r, 1).value for r in range(4, 4 + len(fs))]
    assert nos == [f["finding_no"] for f in db.get_findings(sid, approved_only=True)]  # finding count consistency
    checks = sum(1 for n in wb.sheetnames if n[:2] in ("A.", "B.", "C.", "D.", "E.", "F.")
                 for r in wb[n].iter_rows(min_row=4, values_only=True) if r[0] and str(r[0])[:2] in ("A-", "B-", "C-", "D-", "E-", "F-"))
    assert checks == 198
    assert str(wb["Summary"]["B14"].value).startswith("=COUNTIF(Findings!")
    from docx import Document
    d = Document(str(docx))
    reg = d.tables[11]
    assert len(reg.rows) - 2 == len(fs)
    assert "Test Customer" in reg.rows[0].cells[0].text
    # earlier reports are never overwritten
    again = generate_reports(ctx, db, sid, tmp_path / "out", "admin")
    assert {p.name for p in again}.isdisjoint({p.name for p in paths})
    assert len(db.get_reports(sid)) == 4


def test_history_search(env, tmp_path):
    sid, _ = _run(env, tmp_path)
    db = env[1]
    assert db.search_sessions("Test Project")[0]["id"] == sid
    assert db.search_sessions(soi="SOI-2") == []
    assert db.search_sessions(dal="A")
    assert db.document_library("in.pdf")
