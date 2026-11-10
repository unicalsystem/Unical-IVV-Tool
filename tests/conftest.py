import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.authentication import AuthenticationService  # noqa: E402
from database.db_manager import DatabaseManager  # noqa: E402


@pytest.fixture
def db(tmp_path):
    d = DatabaseManager(tmp_path / "test.db")
    d.initialise()
    return d


@pytest.fixture
def auth(db):
    a = AuthenticationService(db, max_failed=3, lockout_minutes=15, iterations=1000)
    a.ensure_prototype_account()
    return a


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    from ui.theme import STYLESHEET
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLESHEET)
    return app
