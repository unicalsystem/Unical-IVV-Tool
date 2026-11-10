"""Review Results page (Phases 5-7): summary, finding approval workflow, checklist assessment
editing, structure / consistency results, report generation and download."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from core.app_context import AppContext
from core.authentication import UserSession
from core.constants import FINDING_STATUSES, SEVERITIES, VERDICTS, doc_full_name
from core.report_manager import generate_reports
from core.review_service import ReviewService
from core.severity_classifier import SeverityClassifier
from database.db_manager import DatabaseManager
from ui.widgets import fill_table, make_table, page_header

APPROVER_ROLES = {"admin", "lead"}
SEV_COLOURS = {"Major": "#FDE2E1", "Minor": "#FFF1D6", "Observation": "#E7F0FB"}
VERDICT_COLOURS = {"C": "#E3F4E8", "PC": "#FFF1D6", "NC": "#FDE2E1", "NA": "#F0F0F0", "PMR": "#EDE4FA",
                   "PCL": "#E7F0FB"}


def open_path(path: str) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606 - local file chosen by the user
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class FindingDialog(QDialog):
    def __init__(self, parent, finding: dict | None):
        super().__init__(parent)
        self.setWindowTitle("Edit finding" if finding else "Add manual finding")
        self.resize(720, 560)
        f = finding or {}
        form = QFormLayout(self)
        self.severity = QComboBox()
        self.severity.addItems(SEVERITIES)
        self.severity.setCurrentText(f.get("severity", "Minor"))
        form.addRow("Severity:", self.severity)
        self.rationale = QPlainTextEdit(f.get("severity_rationale", ""))
        self.rationale.setMaximumHeight(70)
        form.addRow("Severity rationale:", self.rationale)
        self.section = QLineEdit(f.get("section_number", ""))
        form.addRow("Section:", self.section)
        self.reference = QLineEdit(f.get("reference", ""))
        form.addRow("Reference:", self.reference)
        self.observation = QPlainTextEdit(f.get("observation", ""))
        form.addRow("Observation:", self.observation)
        self.evidence = QPlainTextEdit(f.get("evidence", ""))
        self.evidence.setMaximumHeight(70)
        form.addRow("Evidence (quote):", self.evidence)
        self.page = QLineEdit(f.get("page_ref", ""))
        form.addRow("Page / section ref.:", self.page)
        self.recommendation = QPlainTextEdit(f.get("recommendation", ""))
        self.recommendation.setMaximumHeight(80)
        form.addRow("Recommendation:", self.recommendation)
        self.status = QComboBox()
        self.status.addItems(FINDING_STATUSES)
        self.status.setCurrentText(f.get("status", "Open"))
        form.addRow("Status:", self.status)
        self.comment = QPlainTextEdit(f.get("reviewer_comment", ""))
        self.comment.setMaximumHeight(60)
        form.addRow("Reviewer comment:", self.comment)
        self.response = QPlainTextEdit(f.get("customer_response", ""))
        self.response.setMaximumHeight(60)
        form.addRow("Customer response:", self.response)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _ok(self):
        if not self.observation.toPlainText().strip() or not self.recommendation.toPlainText().strip():
            QMessageBox.warning(self, "Finding", "Observation and recommendation are required. Generic comments such "
                                                 "as 'please improve' are not acceptable.")
            return
        if not self.rationale.toPlainText().strip():
            QMessageBox.warning(self, "Finding", "State why this severity was chosen.")
            return
        self.accept()

    def values(self) -> dict:
        return {"severity": self.severity.currentText(), "severity_rationale": self.rationale.toPlainText().strip(),
                "section_number": self.section.text().strip(), "reference": self.reference.text().strip(),
                "observation": self.observation.toPlainText().strip(), "evidence": self.evidence.toPlainText().strip(),
                "page_ref": self.page.text().strip(), "recommendation": self.recommendation.toPlainText().strip(),
                "status": self.status.currentText(), "reviewer_comment": self.comment.toPlainText().strip(),
                "customer_response": self.response.toPlainText().strip()}


class AssessmentDialog(QDialog):
    def __init__(self, parent, a: dict):
        super().__init__(parent)
        self.setWindowTitle(f"Check {a['checklist_ref']}")
        self.resize(760, 600)
        form = QFormLayout(self)
        q = QLabel(f"<b>{a['review_question']}</b><br><i>Expected evidence:</i> {a['expected_evidence'] or '-'}"
                   f"<br><i>Reference:</i> {a['reference'] or '-'} &nbsp; <i>DAL:</i> {a['dal_applicability']}"
                   f"<br><i>Guidance:</i> {a['review_guidance'] or '-'}")
        q.setWordWrap(True)
        q.setTextFormat(Qt.RichText)
        form.addRow(q)
        self.verdict = QComboBox()
        for k, v in VERDICTS.items():
            self.verdict.addItem(f"{k} - {v}", k)
        self.verdict.setCurrentIndex(self.verdict.findData(a["verdict"]))
        form.addRow("Verdict:", self.verdict)
        self.state = QComboBox()
        self.state.addItems(["Present", "Present-Incomplete", "Present-Inconsistent", "Not Present", "Cannot Verify",
                             "Not Applicable"])
        self.state.setCurrentText(a.get("evidence_state") or "Cannot Verify")
        form.addRow("Evidence state:", self.state)
        self.observation = QPlainTextEdit(a.get("observation") or "")
        form.addRow("Observation:", self.observation)
        self.evidence = QPlainTextEdit(a.get("evidence") or "")
        self.evidence.setMaximumHeight(90)
        form.addRow("Evidence (quote):", self.evidence)
        self.page = QLineEdit(a.get("page_ref") or "")
        form.addRow("Page / section:", self.page)
        self.rec = QPlainTextEdit(a.get("recommendation") or "")
        self.rec.setMaximumHeight(70)
        form.addRow("Recommendation:", self.rec)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _ok(self):
        v = self.verdict.currentData()
        if v in ("C", "PC") and not self.evidence.toPlainText().strip() and not self.page.text().strip():
            QMessageBox.warning(self, "Evidence", "A compliant or partially compliant verdict needs supporting evidence "
                                                  "(quote or page/section reference).")
            return
        if v == "NA" and not self.observation.toPlainText().strip():
            QMessageBox.warning(self, "Not Applicable", "State why the check is not applicable.")
            return
        self.accept()

    def values(self) -> dict:
        return {"verdict": self.verdict.currentData(), "evidence_state": self.state.currentText(),
                "observation": self.observation.toPlainText().strip(), "evidence": self.evidence.toPlainText().strip(),
                "page_ref": self.page.text().strip(), "recommendation": self.rec.toPlainText().strip(),
                "origin": "Manual"}


class ReviewResultsPage(QWidget):
    new_review = Signal()

    def __init__(self, ctx: AppContext, db: DatabaseManager, user: UserSession):
        super().__init__()
        self.ctx, self.db, self.user = ctx, db, user
        self.service = ReviewService(ctx, db)
        self.sid: int | None = None
        self.setObjectName("Page")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        self.header = page_header("Review Results", "Open a review from Review History, or run a new review.")
        root.addWidget(self.header)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.RichText)
        root.addWidget(self.info)
        self.banner = QLabel("")
        self.banner.setObjectName("Banner")
        self.banner.setWordWrap(True)
        self.banner.setVisible(False)
        root.addWidget(self.banner)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._findings_tab(), "Findings")
        self.tabs.addTab(self._checklist_tab(), "Checklist Assessment")
        self.tabs.addTab(self._structure_tab(), "Structure && Consistency")
        self.tabs.addTab(self._reports_tab(), "Reports")
        nav = QHBoxLayout()
        self.finalise_btn = QPushButton("Save && Finalise Review")
        self.finalise_btn.setObjectName("PrimaryButton")
        self.finalise_btn.clicked.connect(self.finalise)
        nb = QPushButton("Start New Review")
        nb.clicked.connect(self.new_review.emit)
        nav.addStretch(1)
        nav.addWidget(nb)
        nav.addWidget(self.finalise_btn)
        root.addLayout(nav)
        self._set_enabled(False)

    # ------------------------------------------------------------------ tabs
    def _findings_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        hint = QLabel("Proposed findings are Draft. Approve, edit or reject each one. Only approved findings appear in "
                      "the reports. Every finding states its evidence (or that no evidence was found) and why its "
                      "severity was chosen.")
        hint.setWordWrap(True)
        hint.setObjectName("PageSubtitle")
        lay.addWidget(hint)
        self.f_table = make_table(["No.", "Approval", "Severity", "Status", "Checks", "Observation", "Evidence",
                                   "Page / section", "Recommendation", "Severity rationale", "Origin"])
        self.f_table.doubleClicked.connect(self.edit_finding)
        lay.addWidget(self.f_table, 1)
        row = QHBoxLayout()
        for text, fn in (("Approve", lambda: self.set_approval("Approved")), ("Reject", lambda: self.set_approval("Rejected")),
                         ("Edit…", self.edit_finding), ("Add manual finding…", self.add_finding),
                         ("Approve all drafts", self.approve_all)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        return w

    def _checklist_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        flt = QHBoxLayout()
        self.sheet_filter = QComboBox()
        self.sheet_filter.addItems(["All sheets", "A", "B", "C", "D", "E", "F", "U"])
        self.verdict_filter = QComboBox()
        self.verdict_filter.addItems(["All verdicts"] + list(VERDICTS))
        self.text_filter = QLineEdit()
        self.text_filter.setPlaceholderText("Search checks…")
        for wdg in (self.sheet_filter, self.verdict_filter):
            wdg.currentIndexChanged.connect(self.load_assessments)
        self.text_filter.textChanged.connect(self.load_assessments)
        flt.addWidget(QLabel("Sheet:"))
        flt.addWidget(self.sheet_filter)
        flt.addWidget(QLabel("Verdict:"))
        flt.addWidget(self.verdict_filter)
        flt.addWidget(self.text_filter, 1)
        lay.addLayout(flt)
        self.a_table = make_table(["Ref", "Sheet", "Check / acceptance criterion", "DAL", "Verdict", "Evidence state",
                                   "Observation", "Evidence", "Page / section", "Findings", "Origin"])
        self.a_table.doubleClicked.connect(self.edit_assessment)
        self.a_table.setSelectionMode(QTableWidget.ExtendedSelection)
        lay.addWidget(self.a_table, 1)
        row = QHBoxLayout()
        b1 = QPushButton("Edit verdict…")
        b1.clicked.connect(self.edit_assessment)
        b2 = QPushButton("Raise finding from check")
        b2.clicked.connect(self.raise_from_check)
        b4 = QPushButton("Set verdict for selected…")
        b4.clicked.connect(self.bulk_verdict)
        b3 = QPushButton("Export Checklist Assessment…")
        b3.clicked.connect(self.export_assessment)
        row.addWidget(b1)
        row.addWidget(b4)
        row.addWidget(b2)
        row.addStretch(1)
        row.addWidget(b3)
        lay.addLayout(row)
        return w

    def _structure_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        t1 = QLabel("Document structure")
        t1.setObjectName("SectionTitle")
        lay.addWidget(t1)
        self.s_table = make_table(["Element", "Result", "Detail", "Where"])
        lay.addWidget(self.s_table, 2)
        t2 = QLabel("Cross-document consistency")
        t2.setObjectName("SectionTitle")
        lay.addWidget(t2)
        self.c_table = make_table(["Topic", "Description", "This document", "Compared with", "Value there", "Result",
                                   "Evidence"])
        lay.addWidget(self.c_table, 2)
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setMaximumHeight(110)
        lay.addWidget(self.notes)
        return w

    def _reports_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        info = QLabel("Reports use the Unical review checklist workbook (Excel) and the Unical review report (Word). "
                      "Only approved findings are included. Earlier reports are never overwritten.")
        info.setWordWrap(True)
        info.setObjectName("PageSubtitle")
        lay.addWidget(info)
        row = QHBoxLayout()
        self.out_dir = QLineEdit(str((self.ctx.root / self.ctx.config.get("reports_folder", "reports")).resolve()))
        b = QPushButton("Choose folder…")
        b.clicked.connect(self._choose_dir)
        row.addWidget(QLabel("Output folder:"))
        row.addWidget(self.out_dir, 1)
        row.addWidget(b)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        gen = QPushButton("Generate Excel && Word Reports")
        gen.setObjectName("PrimaryButton")
        gen.clicked.connect(self.generate)
        row2.addWidget(gen)
        self.open_xlsx = QPushButton("Download / Open Excel Report")
        self.open_docx = QPushButton("Download / Open Word Report")
        self.open_xlsx.clicked.connect(lambda: self._open_latest("Excel"))
        self.open_docx.clicked.connect(lambda: self._open_latest("Word"))
        row2.addWidget(self.open_xlsx)
        row2.addWidget(self.open_docx)
        of = QPushButton("Open folder")
        of.clicked.connect(lambda: open_path(self.out_dir.text()))
        row2.addWidget(of)
        row2.addStretch(1)
        lay.addLayout(row2)
        self.r_table = make_table(["Type", "File", "Created", "By", "SHA-256"])
        self.r_table.doubleClicked.connect(lambda idx: open_path(self.r_table.item(idx.row(), 1).text()))
        lay.addWidget(self.r_table, 1)
        return w

    # ------------------------------------------------------------------ load
    def _set_enabled(self, on: bool) -> None:
        self.tabs.setEnabled(on)
        self.finalise_btn.setEnabled(on)

    def load(self, sid: int) -> None:
        self.sid = sid
        s = self.db.get_session(sid)
        if not s:
            return
        self._set_enabled(True)
        res = json.loads(s.get("results_json") or "{}")
        doc = next((d for d in self.db.get_documents(sid) if d["role"] == "primary"), {})
        title = self.header.findChild(QLabel, "PageTitle")
        title.setText(f"Review Results - {s['document_type']} (session {sid}, version {s['review_version']})")
        cl = res.get("checklist", {})
        counts: dict[str, int] = {}
        for a in self.db.get_assessments(sid):
            counts[a["verdict"]] = counts.get(a["verdict"], 0) + 1
        self.info.setText(
            f"<b>Project:</b> {s.get('project') or '-'} &nbsp; <b>Standard:</b> {s['standard']} &nbsp; <b>DAL:</b> "
            f"{s['dal']} &nbsp; <b>SOI:</b> {s['soi_stage']} &nbsp; <b>Document:</b> {doc_full_name(s['document_type'])}"
            f" - {doc.get('file_name', '')} (No. {doc.get('doc_number') or '-'}, {doc.get('doc_version') or '-'})<br>"
            f"<b>Checklist:</b> {cl.get('name', '-')} ({cl.get('items', 0)} checks) &nbsp; <b>Mode:</b> "
            f"{s.get('analysis_mode')} &nbsp; <b>Status:</b> {s['status']} &nbsp; <b>Proposed recommendation:</b> "
            f"{s.get('recommendation') or '-'}<br><b>Verdicts:</b> " +
            ", ".join(f"{k} {counts.get(k, 0)}" for k in VERDICTS))
        notes = list(res.get("notes", []))
        if not cl.get("validated", True):
            notes.append("The checklist used is derived and pending validation by the IV&V Lead.")
        if counts.get("NR"):
            notes.append(f"{counts['NR']} check(s) are Not Verified: the tool located candidate evidence but a reviewer "
                         "must conclude them (double-click a check to set the verdict).")
        self.banner.setText("\n".join(notes))
        self.banner.setVisible(bool(notes))
        self.load_findings()
        self.load_assessments()
        fill_table(self.s_table, [[r["element"], r["state"], r["detail"], r["where"]] for r in res.get("structure", [])])
        fill_table(self.c_table, [[c["topic"], c["description"], c["primary_value"], c["companion"], c["companion_value"],
                                   c["status"], c["evidence"]] for c in res.get("consistency", [])],
                   "No companion documents supplied - cross-document checks could not be performed.")
        ns = res.get("not_supplied", [])
        self.notes.setPlainText(("Referenced but not supplied (cross-references not verified): " + ", ".join(ns))
                                if ns else "All referenced companion documents were supplied or none were referenced.")
        self.load_reports()

    def load_findings(self) -> None:
        self.findings = self.db.get_findings(self.sid)
        fill_table(self.f_table, [[f["finding_no"], f["approval_state"], f["severity"], f["status"],
                                   f.get("checklist_refs") or "", f["observation"], f.get("evidence") or "",
                                   f.get("page_ref") or "", f["recommendation"], f["severity_rationale"], f["origin"]]
                                  for f in self.findings], "No findings proposed.")
        for r, f in enumerate(self.findings):
            for c in (2,):
                it = self.f_table.item(r, c)
                if it:
                    it.setBackground(QColor(SEV_COLOURS.get(f["severity"], "#FFFFFF")))
            it = self.f_table.item(r, 0)
            if it:
                it.setData(Qt.UserRole, f["id"])
        for c in (5, 6, 8, 9):
            self.f_table.setColumnWidth(c, 300)

    def load_assessments(self) -> None:
        if self.sid is None:
            return
        rows = self.db.get_assessments(self.sid)
        sh, vd, tx = self.sheet_filter.currentText(), self.verdict_filter.currentText(), self.text_filter.text().lower()
        self.assessments = [a for a in rows if (sh == "All sheets" or a["sheet"] == sh or (sh == "U" and a["sheet"] not in "ABCDEF"))
                            and (vd == "All verdicts" or a["verdict"] == vd)
                            and (not tx or tx in (a["review_question"] + a["checklist_ref"] + (a["observation"] or "")).lower())]
        fill_table(self.a_table, [[a["checklist_ref"], a["sheet"], a["review_question"], a["dal_applicability"],
                                   a["verdict"], a["evidence_state"] or "", a["observation"] or "", a["evidence"] or "",
                                   a["page_ref"] or "", a.get("finding_nos") or "", a["origin"]] for a in self.assessments],
                   "No checks match the filter.")
        for r, a in enumerate(self.assessments):
            it = self.a_table.item(r, 4)
            if it:
                it.setBackground(QColor(VERDICT_COLOURS.get(a["verdict"], "#FFFFFF")))
            first = self.a_table.item(r, 0)
            if first:
                first.setData(Qt.UserRole, a["id"])
        for c in (2, 6, 7):
            self.a_table.setColumnWidth(c, 320)

    def load_reports(self) -> None:
        self.reports = self.db.get_reports(self.sid) if self.sid else []
        fill_table(self.r_table, [[r["report_type"], r["file_path"], r["created_at"], r["created_by"], r["sha256"][:16]]
                                  for r in self.reports], "No reports generated yet.")

    # ------------------------------------------------------------------ actions
    def _selected_id(self, table: QTableWidget) -> int | None:
        r = table.currentRow()
        it = table.item(r, 0) if r >= 0 else None
        return it.data(Qt.UserRole) if it else None

    def _can_approve(self) -> bool:
        if self.user.role not in APPROVER_ROLES:
            QMessageBox.warning(self, "Approval", "Only an IV&V Lead or administrator can approve or reject findings.")
            return False
        return True

    def set_approval(self, state: str) -> None:
        fid = self._selected_id(self.f_table)
        if fid is None or not self._can_approve():
            return
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.db.update_finding(fid, approval_state=state, approved_by=self.user.username, approved_at=now,
                               status="Withdrawn" if state == "Rejected" else "Open")
        self.db.audit(self.user.username, f"FINDING_{state.upper()}", f"session {self.sid} finding {fid}")
        self.load_findings()
        self.load_assessments()

    def approve_all(self) -> None:
        if not self._can_approve():
            return
        drafts = [f for f in self.findings if f["approval_state"] == "Draft"]
        if not drafts:
            return
        if QMessageBox.question(self, "Approve all", f"Approve all {len(drafts)} draft findings as they are?\n\nOnly do "
                                "this after reading each finding and its evidence.") != QMessageBox.Yes:
            return
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for f in drafts:
            self.db.update_finding(f["id"], approval_state="Approved", approved_by=self.user.username, approved_at=now)
        self.db.audit(self.user.username, "FINDINGS_APPROVED", f"session {self.sid}: {len(drafts)} findings")
        self.load_findings()

    def edit_finding(self, *_):
        fid = self._selected_id(self.f_table)
        if fid is None:
            return
        f = next(x for x in self.findings if x["id"] == fid)
        dlg = FindingDialog(self, f)
        if dlg.exec() == QDialog.Accepted:
            self.db.update_finding(fid, **dlg.values())
            self.db.audit(self.user.username, "FINDING_EDITED", f"session {self.sid} finding {f['finding_no']}")
            self.load_findings()

    def add_finding(self) -> None:
        if self.sid is None:
            return
        dlg = FindingDialog(self, None)
        if dlg.exec() == QDialog.Accepted:
            vals = dlg.values() | {"origin": "Manual", "approval_state": "Draft"}
            doc = next((d for d in self.db.get_documents(self.sid) if d["role"] == "primary"), None)
            vals["document_id"] = doc["id"] if doc else None
            aid = self._selected_id(self.a_table)
            self.db.add_finding(self.sid, vals, [aid] if aid else [])
            self.db.audit(self.user.username, "FINDING_ADDED", f"session {self.sid}")
            self.load_findings()
            self.load_assessments()

    def edit_assessment(self, *_):
        aid = self._selected_id(self.a_table)
        if aid is None:
            return
        a = next(x for x in self.assessments if x["id"] == aid)
        dlg = AssessmentDialog(self, a)
        if dlg.exec() == QDialog.Accepted:
            self.db.update_assessment(aid, **dlg.values())
            self.db.audit(self.user.username, "VERDICT_EDITED", f"session {self.sid} check {a['checklist_ref']}")
            self.load_assessments()

    def bulk_verdict(self) -> None:
        rows = sorted({i.row() for i in self.a_table.selectedIndexes()})
        ids = [self.a_table.item(r, 0).data(Qt.UserRole) for r in rows if self.a_table.item(r, 0)]
        ids = [i for i in ids if i]
        if not ids:
            return
        from PySide6.QtWidgets import QInputDialog
        choices = [f"{k} - {v}" for k, v in VERDICTS.items()]
        choice, ok = QInputDialog.getItem(self, "Set verdict", f"Verdict for {len(ids)} selected check(s):", choices, 0,
                                          False)
        if not ok:
            return
        verdict = choice.split(" - ")[0]
        note, ok = QInputDialog.getText(self, "Set verdict", "Reviewer note added to each observation (required for NA):")
        if not ok:
            return
        sel = [a for a in self.assessments if a["id"] in ids]
        if verdict in ("C", "PC") and any(not (a["evidence"] or a["page_ref"]) for a in sel):
            QMessageBox.warning(self, "Evidence", "Some selected checks have no evidence or page reference. A C/PC "
                                                  "verdict needs evidence - set those checks individually.")
            return
        if verdict == "NA" and not note.strip():
            QMessageBox.warning(self, "Not Applicable", "State why the checks are not applicable.")
            return
        for a in sel:
            obs = (a["observation"] or "") + (f" Reviewer: {note.strip()}" if note.strip() else "")
            self.db.update_assessment(a["id"], verdict=verdict, observation=obs.strip(), origin="Manual")
        self.db.audit(self.user.username, "VERDICT_BULK", f"session {self.sid}: {len(sel)} checks -> {verdict}")
        self.load_assessments()

    def raise_from_check(self) -> None:
        aid = self._selected_id(self.a_table)
        if aid is None:
            return
        a = next(x for x in self.assessments if x["id"] == aid)
        if a["verdict"] not in ("NC", "PC"):
            QMessageBox.information(self, "Finding", "Set the verdict to NC or PC first (Edit verdict).")
            return
        item = {"sheet": a["sheet"], "rule": a["rule"], "reference": a["reference"], "applicability": a["applicability"],
                "condition": a["condition_text"]}
        sev, why = SeverityClassifier().classify(item, a["verdict"], self.db.get_session(self.sid)["dal"],
                                                 a.get("evidence_state") or "")
        pre = {"severity": sev, "severity_rationale": why, "section_number": a["section_number"],
               "reference": a["reference"], "observation": f"[{a['checklist_ref']}] {a['observation'] or ''}",
               "evidence": a["evidence"] or "", "page_ref": a["page_ref"] or "",
               "recommendation": a["recommendation"] or "", "status": "Open"}
        dlg = FindingDialog(self, pre)
        if dlg.exec() == QDialog.Accepted:
            doc = next((d for d in self.db.get_documents(self.sid) if d["role"] == "primary"), None)
            self.db.add_finding(self.sid, dlg.values() | {"origin": "Manual", "approval_state": "Draft",
                                                          "document_id": doc["id"] if doc else None}, [aid])
            self.load_findings()
            self.load_assessments()

    def export_assessment(self) -> None:
        if self.sid is None:
            return
        f, _ = QFileDialog.getSaveFileName(self, "Export checklist assessment",
                                           str(Path(self.out_dir.text()) / f"checklist_assessment_{self.sid}.xlsx"),
                                           "Excel (*.xlsx)")
        if not f:
            return
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "Checklist Assessment"
        hdr = ["Ref", "Sheet", "Section", "Check / acceptance criterion", "Expected evidence", "Reference", "DAL",
               "Applicability", "Verdict", "Evidence state", "Observation", "Evidence", "Page / section",
               "Recommendation", "Findings", "Origin"]
        ws.append(hdr)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F3864")
        for a in self.db.get_assessments(self.sid):
            ws.append([a["checklist_ref"], a["sheet"], a["section_number"], a["review_question"], a["expected_evidence"],
                       a["reference"], a["dal_applicability"], a["applicability"], a["verdict"], a["evidence_state"],
                       a["observation"], a["evidence"], a["page_ref"], a["recommendation"], a.get("finding_nos"),
                       a["origin"]])
        for col, w in zip("ABCDEFGHIJKLMNOP", (8, 6, 10, 60, 40, 24, 8, 12, 8, 16, 50, 40, 16, 40, 12, 8)):
            ws.column_dimensions[col].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
        try:
            wb.save(f)
        except OSError as exc:
            QMessageBox.critical(self, "Export", f"Could not save: {exc}")
            return
        QMessageBox.information(self, "Export", f"Saved {f}")

    def _choose_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.out_dir.text())
        if d:
            self.out_dir.setText(d)

    def generate(self) -> None:
        if self.sid is None:
            return
        drafts = [f for f in self.db.get_findings(self.sid) if f["approval_state"] == "Draft"]
        if drafts and QMessageBox.question(
                self, "Reports", f"{len(drafts)} finding(s) are still Draft and will NOT appear in the reports.\n\n"
                                 "Generate anyway (e.g. as a working copy)?") != QMessageBox.Yes:
            return
        try:
            paths = generate_reports(self.ctx, self.db, self.sid, Path(self.out_dir.text()), self.user.username)
        except Exception as exc:  # show a clear message
            QMessageBox.critical(self, "Reports", f"Report generation failed:\n{exc}")
            return
        self.load_reports()
        QMessageBox.information(self, "Reports", "Generated:\n" + "\n".join(str(p) for p in paths))

    def _open_latest(self, kind: str) -> None:
        rep = next((r for r in self.reports if r["report_type"] == kind), None)
        if not rep:
            QMessageBox.information(self, "Reports", "Generate the reports first.")
            return
        if not Path(rep["file_path"]).exists():
            QMessageBox.warning(self, "Reports", f"File not found: {rep['file_path']}")
            return
        target, _ = QFileDialog.getSaveFileName(self, f"Save {kind} report", rep["file_path"],
                                                "Excel (*.xlsx)" if kind == "Excel" else "Word (*.docx)")
        if target and Path(target) != Path(rep["file_path"]):
            import shutil
            shutil.copy2(rep["file_path"], target)
            open_path(target)
        elif target:
            open_path(target)

    def finalise(self) -> None:
        if self.sid is None or not self._can_approve():
            return
        try:
            rec = self.service.finalise(self.sid, self.user.username)
        except ValueError as exc:
            QMessageBox.warning(self, "Finalise", str(exc))
            return
        QMessageBox.information(self, "Finalise", f"Review completed. Overall recommendation: {rec}.\n\nFindings have "
                                                  "been renumbered FIN-01... Generate the reports from the Reports tab.")
        self.load(self.sid)
