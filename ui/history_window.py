"""Review History and Document Library pages."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from core.app_context import AppContext
from core.authentication import UserSession
from core.constants import DALS, SESSION_STATUSES, SOI_STAGES, STANDARDS
from core.report_manager import generate_reports
from database.db_manager import DatabaseManager
from ui.review_results import open_path
from ui.widgets import fill_table, make_table, page_header


class HistoryPage(QWidget):
    open_session = Signal(int)

    def __init__(self, ctx: AppContext, db: DatabaseManager, user: UserSession):
        super().__init__()
        self.ctx, self.db, self.user = ctx, db, user
        self.setObjectName("Page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.addWidget(page_header("Review History", "Every review is kept. A re-review of the same document creates a "
                                                    "new version; earlier results are never overwritten."))
        f = QHBoxLayout()
        self.text = QLineEdit()
        self.text.setPlaceholderText("Search project, document, file name or number…")
        self.project = QComboBox()
        self.soi = QComboBox()
        self.dal = QComboBox()
        self.std = QComboBox()
        self.status = QComboBox()
        self.soi.addItems(["All SOI"] + list(SOI_STAGES))
        self.dal.addItems(["All DAL"] + list(DALS))
        self.std.addItems(["All standards"] + list(STANDARDS))
        self.status.addItems(["All status"] + list(SESSION_STATUSES))
        f.addWidget(self.text, 2)
        for w in (self.project, self.soi, self.dal, self.std, self.status):
            f.addWidget(w)
            w.currentIndexChanged.connect(self.refresh)
        self.text.returnPressed.connect(self.refresh)
        b = QPushButton("Search")
        b.clicked.connect(self.refresh)
        f.addWidget(b)
        lay.addLayout(f)
        self.table = make_table(["ID", "Project", "Standard", "DAL", "SOI", "Document", "File", "Ver.", "Round",
                                 "Status", "Recommendation", "Findings", "Mode", "Reviewer", "Started", "Completed"])
        self.table.doubleClicked.connect(self._open)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        o = QPushButton("Open Results")
        o.setObjectName("PrimaryButton")
        o.clicked.connect(self._open)
        e = QPushButton("Export Reports…")
        e.clicked.connect(self._export)
        row.addWidget(o)
        row.addWidget(e)
        row.addStretch(1)
        lay.addLayout(row)

    def showEvent(self, ev):
        self._load_projects()
        self.refresh()
        super().showEvent(ev)

    def _load_projects(self) -> None:
        cur = self.project.currentData()
        self.project.blockSignals(True)
        self.project.clear()
        self.project.addItem("All projects", None)
        for p in self.db.list_projects():
            self.project.addItem(p["name"], p["id"])
        idx = self.project.findData(cur)
        self.project.setCurrentIndex(max(0, idx))
        self.project.blockSignals(False)

    def refresh(self) -> None:
        val = lambda cb: "" if cb.currentIndex() == 0 else cb.currentText()
        rows = self.db.search_sessions(self.text.text().strip(), self.project.currentData(), val(self.soi),
                                       val(self.dal), val(self.std), val(self.status))
        self.rows = rows
        fill_table(self.table, [[r["id"], r["project"], r["standard"], r["dal"], r["soi_stage"], r["document_type"],
                                 r["file_name"] or "", r["review_version"], r["review_round"], r["status"],
                                 r["recommendation"] or "", r["findings"], r["analysis_mode"], r["started_by"],
                                 (r["started_at"] or "")[:16].replace("T", " "),
                                 (r["completed_at"] or "")[:16].replace("T", " ")] for r in rows],
                   "No reviews match the filter.")

    def _selected(self) -> int | None:
        r = self.table.currentRow()
        it = self.table.item(r, 0) if r >= 0 else None
        return int(it.data(Qt.DisplayRole)) if it and str(it.data(Qt.DisplayRole)).isdigit() else None

    def _open(self, *_):
        sid = self._selected()
        if sid:
            self.open_session.emit(sid)

    def _export(self) -> None:
        sid = self._selected()
        if not sid:
            return
        d = QFileDialog.getExistingDirectory(self, "Export reports to", str(self.ctx.root / "reports"))
        if not d:
            return
        try:
            paths = generate_reports(self.ctx, self.db, sid, Path(d), self.user.username)
        except Exception as exc:
            QMessageBox.critical(self, "Export", str(exc))
            return
        QMessageBox.information(self, "Export", "Exported:\n" + "\n".join(map(str, paths)))


class DocumentLibraryPage(QWidget):
    def __init__(self, db: DatabaseManager):
        super().__init__()
        self.db = db
        self.setObjectName("Page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.addWidget(page_header("Document Library", "Every document uploaded for review, stored read-only with its "
                                                      "SHA-256 fingerprint."))
        row = QHBoxLayout()
        self.text = QLineEdit()
        self.text.setPlaceholderText("Search file name, number, title or project…")
        self.text.returnPressed.connect(self.refresh)
        b = QPushButton("Search")
        b.clicked.connect(self.refresh)
        row.addWidget(self.text, 1)
        row.addWidget(b)
        lay.addLayout(row)
        self.table = make_table(["Session", "Project", "Role", "File", "Doc. number", "Version", "Detected type",
                                 "Reviewed as", "Pages", "Scanned", "SHA-256", "Uploaded", "Stored copy"])
        self.table.doubleClicked.connect(self._open)
        lay.addWidget(self.table, 1)
        note = QLabel("Double-click a row to open the stored copy.")
        note.setObjectName("PageSubtitle")
        lay.addWidget(note)

    def showEvent(self, ev):
        self.refresh()
        super().showEvent(ev)

    def refresh(self) -> None:
        rows = self.db.document_library(self.text.text().strip())
        fill_table(self.table, [[r["session_id"], r["project"], r["role"], r["file_name"], r["doc_number"] or "",
                                 r["doc_version"] or "", r["detected_type"] or "", r["reviewed_as"], r["page_count"] or "",
                                 "Yes" if r["is_scanned"] else "", (r["sha256"] or "")[:16],
                                 (r["uploaded_at"] or "")[:16].replace("T", " "), r["stored_path"]] for r in rows],
                   "No documents uploaded yet.")

    def _open(self, idx) -> None:
        path = self.table.item(idx.row(), 12).text() if self.table.item(idx.row(), 12) else ""
        if path and Path(path).exists():
            open_path(path)
