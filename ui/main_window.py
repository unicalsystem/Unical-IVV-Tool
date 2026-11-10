"""Main window: sidebar navigation and page stack."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from core.app_context import AppContext
from core.authentication import UserSession
from database.db_manager import DatabaseManager
from ui.checklist_manager import ChecklistManagerPage
from ui.dashboard import DashboardPage
from ui.history_window import DocumentLibraryPage, HistoryPage
from ui.new_review import NewReviewPage
from ui.review_results import ReviewResultsPage
from ui.settings_window import SettingsPage
from ui.widgets import logo_label, page_header

NAV_ITEMS = [
    ("dashboard", "Dashboard"),
    ("new_review", "New Review"),
    ("results", "Review Results"),
    ("history", "Review History"),
    ("checklists", "Checklist Management"),
    ("library", "Document Library"),
    ("settings", "Settings"),
    ("about", "About"),
]


class AboutPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.setObjectName("Page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.addWidget(page_header("About", ctx.config["app_name"]))
        for line in (
            f"Version: {ctx.config['version']}",
            "Company: Unical Systems",
            "Purpose: assist Unical IV&V engineers in reviewing DO-178B / DO-178C life-cycle data for SOI-1 to SOI-4.",
            "Built-in checklists: DO-178C planning (PSAC, SDP, SVP, SCMP, SQAP - imported from the Unical review "
            "checklists), standards (SRS, SDS, SCS), IVVP, SRD, SDD, source code, trace data, SVCP, SVR, problem "
            "reports, SCI, SECI, SAS, SCM and SQA records; DO-178B variants pending validation.",
            "Important: this tool is a review assistant. It does not make certification decisions. Every finding "
            "must be checked and approved by a qualified IV&V engineer before it is issued.",
            "Supported standards: RTCA DO-178B, RTCA DO-178C (with DO-330, DO-331, DO-332, DO-333 where applicable).",
        ):
            lbl = QLabel(line)
            lbl.setWordWrap(True)
            lay.addWidget(lbl)
        lay.addStretch(1)


class MainWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(self, ctx: AppContext, db: DatabaseManager, session: UserSession):
        super().__init__()
        self.ctx, self.db, self.session = ctx, db, session
        ui = ctx.config["ui"]
        self.setWindowTitle(ctx.config["app_name"])
        self.resize(ui["window_width"], ui["window_height"])
        self.setMinimumSize(1024, 680)

        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {}
        self.dashboard = DashboardPage(db, ctx.config["app_name"], ui.get("recent_activity_rows", 15))
        self.dashboard.set_user(session.full_name or session.username)
        self.dashboard.navigate.connect(self.show_page)
        self._add("dashboard", self.dashboard)
        self.new_review = NewReviewPage(ctx, db, session)
        self.results = ReviewResultsPage(ctx, db, session)
        self.history = HistoryPage(ctx, db, session)
        self.new_review.review_finished.connect(self.open_results)
        self.results.new_review.connect(lambda: self.show_page("new_review"))
        self.history.open_session.connect(self.open_results)
        self._add("new_review", self.new_review)
        self._add("results", self.results)
        self._add("history", self.history)
        self._add("checklists", ChecklistManagerPage(session))
        self._add("library", DocumentLibraryPage(db))
        self._add("settings", SettingsPage(ctx, db, session))
        self._add("about", AboutPage(ctx))
        h.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.show_page("dashboard")

    def _add(self, key: str, page: QWidget) -> None:
        self.pages[key] = page
        self.stack.addWidget(page)

    def _build_sidebar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(232)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(0, 18, 0, 14)
        lay.setSpacing(2)
        logo_box = QFrame()
        logo_box.setStyleSheet("background: white; border-radius: 6px;")
        lb = QVBoxLayout(logo_box)
        lb.setContentsMargins(10, 8, 10, 8)
        lb.addWidget(logo_label(self.ctx.logo_path, 34), alignment=Qt.AlignCenter)
        wrap = QHBoxLayout()
        wrap.setContentsMargins(16, 0, 16, 0)
        wrap.addWidget(logo_box)
        lay.addLayout(wrap)
        lay.addSpacing(10)
        title = QLabel("DO-178 IV&V Review Tool")
        title.setObjectName("SidebarTitle")
        title.setContentsMargins(18, 0, 10, 0)
        lay.addWidget(title)
        sub = QLabel("DO-178B / DO-178C  |  SOI-1 to SOI-4")
        sub.setObjectName("SidebarSub")
        sub.setContentsMargins(18, 0, 10, 0)
        lay.addWidget(sub)
        lay.addSpacing(16)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for key, label in NAV_ITEMS:
            b = QPushButton(label)
            b.setObjectName("NavButton")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            self.nav_group.addButton(b)
            self.nav_buttons[key] = b
            lay.addWidget(b)
        lay.addStretch(1)
        user = QLabel(f"Signed in as {self.session.username} ({self.session.role})")
        user.setObjectName("SidebarUser")
        user.setContentsMargins(18, 0, 10, 4)
        user.setWordWrap(True)
        lay.addWidget(user)
        out = QPushButton("Log out")
        out.setObjectName("LogoutButton")
        out.clicked.connect(self.logout_requested.emit)
        w = QHBoxLayout()
        w.setContentsMargins(16, 0, 16, 0)
        w.addWidget(out)
        lay.addLayout(w)
        return bar

    def open_results(self, session_id: int) -> None:
        self.results.load(session_id)
        self.show_page("results")

    def show_page(self, key: str) -> None:
        if key not in self.pages:
            return
        if key == "dashboard":
            self.dashboard.refresh()
        self.stack.setCurrentWidget(self.pages[key])
        self.nav_buttons[key].setChecked(True)
