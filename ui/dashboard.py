"""Dashboard page: review statistics, recent reviews and recent activity."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from database.db_manager import DatabaseManager
from ui.widgets import StatCard, fill_table, make_table, page_header


def _short_ts(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%d-%m-%Y %H:%M")
    except (TypeError, ValueError):
        return iso or ""


class DashboardPage(QWidget):
    navigate = Signal(str)  # page key

    def __init__(self, db: DatabaseManager, app_name: str, recent_rows: int = 15):
        super().__init__()
        self.db = db
        self.recent_rows = recent_rows
        self.setObjectName("Page")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(14)

        root.addWidget(page_header(app_name, "Review planning, development, verification and certification data "
                                             "for SOI-1 to SOI-4 against DO-178B / DO-178C (DAL A to E)."))
        self.welcome = QLabel("")
        self.welcome.setObjectName("PageSubtitle")
        root.addWidget(self.welcome)

        # quick actions
        actions = QHBoxLayout()
        start = QPushButton("+  Start New Review")
        start.setObjectName("PrimaryButton")
        start.setMinimumHeight(36)
        start.clicked.connect(lambda: self.navigate.emit("new_review"))
        actions.addWidget(start)
        for text, key in (("Review History", "history"), ("Checklist Management", "checklists"), ("Settings", "settings")):
            b = QPushButton(text)
            b.setMinimumHeight(36)
            b.clicked.connect(lambda _=False, k=key: self.navigate.emit(k))
            actions.addWidget(b)
        actions.addStretch(1)
        root.addLayout(actions)

        # stat cards
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        self.cards = {
            "total_reviews": StatCard("Total reviews performed"),
            "completed": StatCard("Reviews completed"),
            "pending": StatCard("Reviews pending", tooltip="Draft, in progress or awaiting manual review"),
            "findings": StatCard("Findings raised"),
            "documents": StatCard("Documents reviewed", tooltip="Distinct documents (by file hash)"),
        }
        for i, card in enumerate(self.cards.values()):
            grid.addWidget(card, 0, i)
        root.addLayout(grid)
        self.severity_line = QLabel("")
        self.severity_line.setObjectName("PageSubtitle")
        root.addWidget(self.severity_line)

        # tables
        t1 = QLabel("Recent reviews")
        t1.setObjectName("SectionTitle")
        root.addWidget(t1)
        self.reviews_table = make_table(["ID", "Project", "Standard", "DAL", "SOI", "Document", "Ver.", "Status",
                                         "Findings", "Reviewer", "Started"])
        root.addWidget(self.reviews_table, 3)
        t2 = QLabel("Recent activity")
        t2.setObjectName("SectionTitle")
        root.addWidget(t2)
        self.activity_table = make_table(["Time", "User", "Event", "Details"])
        root.addWidget(self.activity_table, 2)

    def set_user(self, full_name: str) -> None:
        self.welcome.setText(f"Welcome, {full_name}.")

    def refresh(self) -> None:
        stats = self.db.dashboard_stats()
        for key, card in self.cards.items():
            card.set_value(stats.get(key, 0))
        sev = self.db.findings_by_severity()
        self.severity_line.setText(f"Findings by severity - Major: {sev['Major']}   |   Minor: {sev['Minor']}   |   "
                                   f"Observation: {sev['Observation']}   |   Open: {stats['open_findings']}")
        fill_table(self.reviews_table, [
            [r["id"], r["project"], r["standard"], r["dal"], r["soi_stage"], r["document_type"], r["review_version"],
             r["status"], r["findings"], r["started_by"], _short_ts(r["started_at"])]
            for r in self.db.recent_reviews(self.recent_rows)],
            "No reviews yet. Click 'Start New Review' to begin.")
        fill_table(self.activity_table, [
            [_short_ts(a["ts"]), a["username"], a["event"], a["details"]] for a in self.db.recent_activity(self.recent_rows)])
