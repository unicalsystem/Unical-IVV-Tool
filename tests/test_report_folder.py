"""Report generation asks the user for the destination folder (Review Results page)."""
import json

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog, QMessageBox

from core.app_context import DEFAULT_CONFIG, AppContext
from core.review_service import ReviewRequest, ReviewService
from tests.factory import PSAC_TEXT, make_pdf


def _page(tmp_path, db, auth, monkeypatch):
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path / "qs"))
    QSettings.setDefaultFormat(QSettings.IniFormat)
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    ctx = AppContext(root=tmp_path, config=cfg)
    svc = ReviewService(ctx, db)
    req = ReviewRequest("DO-178C", "A", "SOI-1", "PSAC", str(make_pdf(tmp_path / "in.pdf", PSAC_TEXT)), "admin",
                        project_name="Folder Test")
    sid = svc.create_session(req)
    svc.execute(sid, req)
    from ui.review_results import ReviewResultsPage
    user = auth.authenticate("admin", "admin@123").session
    page = ReviewResultsPage(ctx, db, user)
    page.load(sid)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    return page


def test_generate_asks_for_folder(qapp, tmp_path, db, auth, monkeypatch):
    page = _page(tmp_path, db, auth, monkeypatch)
    chosen = tmp_path / "my reports"
    chosen.mkdir()
    asked = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: asked.append(a) or str(chosen)))
    page.generate()
    assert asked, "the folder dialog must be shown"
    assert {p.suffix for p in chosen.iterdir()} == {".xlsx", ".docx"}
    assert page.out_dir.text() == str(chosen)
    assert QSettings("Unical Systems", "IVV Review Tool").value("reports/last_folder") == str(chosen)


def test_cancel_folder_writes_nothing(qapp, tmp_path, db, auth, monkeypatch):
    page = _page(tmp_path, db, auth, monkeypatch)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    page.generate()
    assert not db.get_reports(page.sid)
