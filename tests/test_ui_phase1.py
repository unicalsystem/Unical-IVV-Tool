"""UI smoke tests for the login page, dashboard and navigation (run headless)."""
from core.app_context import AppContext, DEFAULT_CONFIG
from ui.login_window import LoginWindow
from ui.main_window import NAV_ITEMS, MainWindow


def _ctx(tmp_path):
    cfg = dict(DEFAULT_CONFIG)
    cfg["database_file"] = "test.db"
    return AppContext(root=tmp_path, config=cfg)


def test_login_success_emits_session(qapp, auth, tmp_path):
    w = LoginWindow(auth, "Test", "0.1", tmp_path / "missing.png")
    got = []
    w.login_succeeded.connect(got.append)
    w.username.setText("admin")
    w.password.setText("admin@123")
    w.attempt_login()
    assert got and got[0].username == "admin"
    assert w.password.text() == ""


def test_login_failure_shows_message(qapp, auth, tmp_path):
    w = LoginWindow(auth, "Test", "0.1", tmp_path / "missing.png")
    w.username.setText("admin")
    w.password.setText("nope")
    w.attempt_login()
    assert not w.error.isHidden() and "Invalid" in w.error.text()


def test_show_hide_password(qapp, auth, tmp_path):
    from PySide6.QtWidgets import QLineEdit
    w = LoginWindow(auth, "Test", "0.1", tmp_path / "missing.png")
    w.show_password.setChecked(True)
    assert w.password.echoMode() == QLineEdit.Normal
    w.show_password.setChecked(False)
    assert w.password.echoMode() == QLineEdit.Password


def test_dashboard_and_navigation(qapp, db, auth, tmp_path):
    session = auth.authenticate("admin", "admin@123").session
    db.create_review_session("DO-178C", "A", "SOI-1", "PSAC", "admin", status="Completed")
    win = MainWindow(_ctx(tmp_path), db, session)
    assert win.stack.currentWidget() is win.dashboard
    assert win.dashboard.cards["total_reviews"].value_label.text() == "1"
    assert win.dashboard.cards["completed"].value_label.text() == "1"
    for key, _ in NAV_ITEMS:
        win.show_page(key)
        assert win.stack.currentWidget() is win.pages[key]
        assert win.nav_buttons[key].isChecked()
    win.dashboard.navigate.emit("new_review")
    assert win.stack.currentWidget() is win.pages["new_review"]
