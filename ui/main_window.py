"""Main window: sidebar navigation and page stack."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from core.app_context import AppContext
from core.authentication import UserSession
from database.db_manager import DatabaseManager
from ui.dashboard import DashboardPage
from ui.widgets import fill_table, logo_label, make_table, page_header

NAV_ITEMS = [
    ("dashboard", "Dashboard"),
    ("new_review", "New Review"),
    ("history", "Review History"),
    ("checklists", "Checklist Management"),
    ("library", "Document Library"),
    ("settings", "Settings"),
    ("about", "About"),
]

PLANNED = {
    "new_review": ("New Review", "Phase 2 - Workflow Implementation",
                   ["Select DO-178B or DO-178C (separate rule sets; DO-178C supplements never applied to DO-178B)",
                    "Select DAL A-E (DAL E: objectives shown as not applicable, no compliance findings)",
                    "Select SOI-1 / SOI-2 / SOI-3 / SOI-4 and document type",
                    "Upload document (PDF, DOCX, XLSX, TXT) and optional checklist",
                    "File validation: readability, empty, encrypted, scanned, extractable text"]),
    "history": ("Review History", "Phase 2 / Phase 7",
                ["Search and filter by project, SOI stage, DAL and standard",
                 "Re-open results; every re-review is kept as a new version (never overwritten)",
                 "Export previous reports"]),
    "checklists": ("Checklist Management", "Phase 4 - Checklist Engine",
                   ["Built-in checklists per standard / SOI / document, in the Unical A-F sheet structure",
                    "Import of existing Unical review checklists (PSAC, SDP, SVP, SCMP, SQAP)",
                    "User-uploaded checklists (XLSX / DOCX / PDF), original wording preserved",
                    "Built-in only, user only or combined checklist modes",
                    "DAL applicability and Mandatory / Conditional / Not Applicable rules"]),
    "library": ("Document Library", "Phase 3 - Document Processing",
                ["All uploaded documents with hash, version, detected type and page count",
                 "Companion documents for cross-document consistency checks"]),
}


class PlannedPage(QWidget):
    """Shown for modules scheduled in later phases (not part of Phase 1 scope)."""

    def __init__(self, title: str, phase: str, items: list[str]):
        super().__init__()
        self.setObjectName("Page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.addWidget(page_header(title, f"Scheduled for {phase}."))
        banner = QLabel("This module is not part of Phase 1. Planned capability:")
        banner.setObjectName("Banner")
        lay.addWidget(banner)
        for it in items:
            lbl = QLabel("•  " + it)
            lbl.setWordWrap(True)
            lay.addWidget(lbl)
        lay.addStretch(1)


class SettingsPage(QWidget):
    def __init__(self, ctx: AppContext, db: DatabaseManager):
        super().__init__()
        self.setObjectName("Page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.addWidget(page_header("Settings", "Read-only in Phase 1. Editing is restricted to administrators from Phase 4."))
        model_cfg = {}
        cfg_file = ctx.root / "config" / "model_config.json"
        if cfg_file.exists():
            try:
                model_cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                model_cfg = {}
        ai_state = ("Enabled - local model " + model_cfg.get("model_name", "?")) if model_cfg.get("enabled") else \
            "Disabled - rule-based review mode (AI-assisted analysis unavailable)"
        rows = [
            ["Application folder", str(ctx.root)],
            ["Database", str(ctx.db_path)],
            ["Schema version", db.schema_version()],
            ["Log file", str(ctx.log_path)],
            ["Reports folder", str((ctx.root / ctx.config["reports_folder"]).resolve())],
            ["AI analysis", ai_state],
            ["Local model endpoint", model_cfg.get("endpoint", "-")],
            ["Network use", "None. No cloud APIs, no remote database, no online authentication."],
        ]
        table = make_table(["Setting", "Value"])
        table.setSortingEnabled(False)
        fill_table(table, rows)
        lay.addWidget(table)


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
        for key, (title, phase, items) in PLANNED.items():
            self._add(key, PlannedPage(title, phase, items))
        self._add("settings", SettingsPage(ctx, db))
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

    def show_page(self, key: str) -> None:
        if key not in self.pages:
            return
        if key == "dashboard":
            self.dashboard.refresh()
        self.stack.setCurrentWidget(self.pages[key])
        self.nav_buttons[key].setChecked(True)
