"""Unical Systems - DO-178B / DO-178C IV&V Review Tool (offline desktop application).

Run:  python main.py
"""
from __future__ import annotations

import logging
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from core.app_context import load_context, setup_logging
from core.authentication import AuthenticationService, UserSession
from database.db_manager import DatabaseManager
from ui.login_window import LoginWindow
from ui.main_window import MainWindow
from ui.theme import STYLESHEET

log = logging.getLogger("main")


class Application:
    def __init__(self, qt_app: QApplication):
        self.qt_app = qt_app
        self.ctx = load_context()
        setup_logging(self.ctx)
        log.info("Starting %s %s", self.ctx.config["app_name"], self.ctx.config["version"])
        from core import checklist_engine
        checklist_engine.set_user_root(self.ctx.root / "checklists_user")
        self.db = DatabaseManager(self.ctx.db_path)
        self.db.initialise()
        sec = self.ctx.config["security"]
        self.auth = AuthenticationService(self.db, sec["max_failed_logins"], sec["lockout_minutes"], sec["pbkdf2_iterations"])
        self.auth.ensure_prototype_account()
        self.db.audit("system", "APP_START", self.ctx.config["version"])
        self.session: UserSession | None = None
        self.main_window: MainWindow | None = None
        self.login = LoginWindow(self.auth, self.ctx.config["app_name"], self.ctx.config["version"], self.ctx.logo_path)
        self.login.login_succeeded.connect(self.open_main)

    def start(self) -> None:
        self.login.show()

    def open_main(self, session: UserSession) -> None:
        self.session = session
        self.main_window = MainWindow(self.ctx, self.db, session)
        self.main_window.logout_requested.connect(self.logout)
        self.main_window.show()
        self.login.hide()

    def logout(self) -> None:
        self.auth.logout(self.session)
        self.session = None
        if self.main_window:
            self.main_window.close()
            self.main_window.deleteLater()
            self.main_window = None
        self.login.reset()
        self.login.show()


def main() -> int:
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Unical IV&V Review Tool")
    qt_app.setOrganizationName("Unical Systems")
    qt_app.setStyleSheet(STYLESHEET)
    try:
        app = Application(qt_app)
    except Exception as exc:  # show a clear message instead of a silent crash
        logging.getLogger("main").exception("Start-up failed")
        QMessageBox.critical(None, "Start-up error", f"The application could not start:\n\n{exc}")
        return 1
    qt_app.setWindowIcon(QIcon(str(app.ctx.logo_path)))
    app.start()
    code = qt_app.exec()
    # Release Qt windows while QApplication still exists (clean exit on Windows)
    if app.main_window is not None:
        app.main_window.deleteLater()
    app.login.deleteLater()
    qt_app.processEvents()
    return code


if __name__ == "__main__":
    sys.exit(main())
