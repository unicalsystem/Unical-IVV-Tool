"""New Review wizard (Phase 2): standard -> DAL -> SOI -> document / checklist upload -> validation -> run."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QRadioButton, QSpinBox, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core.ai_agent import load_model_config
from core.app_context import AppContext
from core.authentication import UserSession
from core.checklist_engine import load_builtin, read_user_checklist
from core.constants import DALS, DOCUMENT_TYPES, SOI_STAGES, SOI_TITLES, STANDARDS, doc_types_for
from core.document_classifier import check_relevance
from core.document_parser import parse_document, tesseract_available
from core.document_validator import CHECKLIST_ALLOWED, validate_file
from core.review_service import ReviewRequest, ReviewService
from database.db_manager import DatabaseManager
from ui.widgets import page_header
from ui.workers import Worker, start_worker

DOC_FILTER = "Documents (*.pdf *.docx *.xlsx *.txt)"
CHK_FILTER = "Checklists (*.xlsx *.docx *.pdf)"
SOI_HELP = {
    "SOI-1": "PSAC, SDP, SVP, SCMP, SQAP, standards (SRS/SDS/SCS), IVVP",
    "SOI-2": "Software requirements (SRD), design (SDD), source code reviews, trace data",
    "SOI-3": "Verification cases & procedures, results, coverage, problem reports",
    "SOI-4": "SCI, SECI, SAS, SCM / SQA records, final verification evidence",
}


class StepIndicator(QLabel):
    def set_step(self, i: int) -> None:
        names = ["1  Standard, DAL & SOI", "2  Documents & checklist", "3  Review"]
        parts = [f"<b style='color:#1F3864'>{n}</b>" if k == i else f"<span style='color:#8A94A6'>{n}</span>"
                 for k, n in enumerate(names)]
        self.setText("  &nbsp;›&nbsp;  ".join(parts))


class NewReviewPage(QWidget):
    review_finished = Signal(int)

    def __init__(self, ctx: AppContext, db: DatabaseManager, session: UserSession):
        super().__init__()
        self.ctx, self.db, self.user = ctx, db, session
        self.service = ReviewService(ctx, db)
        self.validated = False
        self.worker: Worker | None = None
        self.setObjectName("Page")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.addWidget(page_header("New Review", "Select the certification basis, upload the document and start the "
                                                 "review. The tool proposes; the reviewer decides."))
        self.steps = StepIndicator()
        root.addWidget(self.steps)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.stack.addWidget(self._step1())
        self.stack.addWidget(self._step2())
        self.stack.addWidget(self._step3())
        self.go(0)

    # ------------------------------------------------------------------ step 1
    def _step1(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        box = QGroupBox("Certification standard")
        bl = QHBoxLayout(box)
        self.std_group = QButtonGroup(self)
        for i, s in enumerate(STANDARDS):
            rb = QRadioButton(s)
            rb.setChecked(s == "DO-178C")
            self.std_group.addButton(rb, i)
            bl.addWidget(rb)
        bl.addStretch(1)
        note = QLabel("DO-178B and DO-178C use separate checklists and rules. DO-178C supplements (DO-330/331/332/333) "
                      "are never applied to a DO-178B project.")
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        lay.addWidget(box)
        lay.addWidget(note)
        dbox = QGroupBox("Software level (DAL)")
        dl = QHBoxLayout(dbox)
        self.dal = QComboBox()
        self.dal.addItems([f"DAL {d}" for d in DALS])
        self.dal.currentIndexChanged.connect(self._dal_note)
        dl.addWidget(self.dal)
        self.dal_note = QLabel("")
        self.dal_note.setObjectName("PageSubtitle")
        self.dal_note.setWordWrap(True)
        dl.addWidget(self.dal_note, 1)
        lay.addWidget(dbox)
        sbox = QGroupBox("Stage of Involvement")
        sl = QGridLayout(sbox)
        self.soi_group = QButtonGroup(self)
        for i, s in enumerate(SOI_STAGES):
            rb = QRadioButton(f"{s} - {SOI_TITLES[s]}")
            rb.setChecked(i == 0)
            self.soi_group.addButton(rb, i)
            sl.addWidget(rb, i, 0)
            h = QLabel(SOI_HELP[s])
            h.setObjectName("PageSubtitle")
            sl.addWidget(h, i, 1)
        lay.addWidget(sbox)
        lay.addStretch(1)
        nav = QHBoxLayout()
        nav.addStretch(1)
        nxt = QPushButton("Next  ›")
        nxt.setObjectName("PrimaryButton")
        nxt.clicked.connect(lambda: self.go(1))
        nav.addWidget(nxt)
        lay.addLayout(nav)
        self._dal_note()
        return w

    def _dal_note(self) -> None:
        d = self.selected_dal()
        self.dal_note.setText({"A": "Level A: all 71 DO-178C objectives, 30 with independence.",
                               "B": "Level B: 69 objectives, 18 with independence.",
                               "C": "Level C: 62 objectives, 5 with independence.",
                               "D": "Level D: 26 objectives, 2 with independence.",
                               "E": "Level E: DO-178B/C objectives are generally not applicable. Only document "
                                    "control is reviewed; no compliance findings are raised."}[d])

    def selected_standard(self) -> str:
        return STANDARDS[self.std_group.checkedId()]

    def selected_dal(self) -> str:
        return DALS[self.dal.currentIndex()]

    def selected_soi(self) -> str:
        return SOI_STAGES[self.soi_group.checkedId()]

    # ------------------------------------------------------------------ step 2
    def _step2(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        lay.addLayout(top, 1)

        left = QGroupBox("Document under review")
        form = QFormLayout(left)
        self.sel_label = QLabel("")
        form.addRow("Selection:", self.sel_label)
        self.doc_type = QComboBox()
        self.doc_type.currentIndexChanged.connect(self._invalidate)
        form.addRow("Document type:", self.doc_type)
        self.project = QComboBox()
        self.project.setEditable(True)
        self.project.lineEdit().setPlaceholderText("Project name (e.g. Digital MSU GLO-MSU11-D)")
        self.project.currentTextChanged.connect(self._fill_project)
        form.addRow("Project:", self.project)
        self.customer = QLineEdit()
        self.customer.setPlaceholderText("Applicant / design agency")
        form.addRow("Customer:", self.customer)
        self.lru = QLineEdit()
        form.addRow("System / LRU:", self.lru)
        self.part_no = QLineEdit()
        form.addRow("Part number:", self.part_no)
        self.cert_basis = QLineEdit()
        self.cert_basis.setPlaceholderText("e.g. CEMILAC / RCMA")
        form.addRow("Certification authority:", self.cert_basis)
        self.doc_no = QLineEdit()
        self.doc_no.setPlaceholderText("Optional - detected from the document")
        form.addRow("Document number:", self.doc_no)
        self.doc_ver = QLineEdit()
        self.doc_ver.setPlaceholderText("Optional - detected from the document")
        form.addRow("Document version:", self.doc_ver)
        self.round = QSpinBox()
        self.round.setRange(1, 9)
        form.addRow("Review round:", self.round)
        frow = QHBoxLayout()
        self.doc_path = QLineEdit()
        self.doc_path.setReadOnly(True)
        self.doc_path.setPlaceholderText("Mandatory - PDF, DOCX, XLSX or TXT")
        b = QPushButton("Browse Document…")
        b.clicked.connect(self._browse_doc)
        frow.addWidget(self.doc_path, 1)
        frow.addWidget(b)
        form.addRow("Document file:", frow)
        top.addWidget(left, 3)

        right = QVBoxLayout()
        cbox = QGroupBox("Review checklist")
        cl = QFormLayout(cbox)
        crow = QHBoxLayout()
        self.chk_path = QLineEdit()
        self.chk_path.setReadOnly(True)
        self.chk_path.setPlaceholderText("Optional - XLSX, DOCX or PDF")
        cb = QPushButton("Browse Checklist…")
        cb.clicked.connect(self._browse_checklist)
        clr = QPushButton("Clear")
        clr.clicked.connect(lambda: (self.chk_path.clear(), self._invalidate()))
        crow.addWidget(self.chk_path, 1)
        crow.addWidget(cb)
        crow.addWidget(clr)
        cl.addRow("Your checklist:", crow)
        self.chk_mode = QComboBox()
        self.chk_mode.addItems(["Built-in", "User", "Combined"])
        self.chk_mode.setEnabled(False)
        cl.addRow("Use:", self.chk_mode)
        self.builtin_info = QLabel("")
        self.builtin_info.setWordWrap(True)
        self.builtin_info.setObjectName("PageSubtitle")
        cl.addRow("Built-in:", self.builtin_info)
        right.addWidget(cbox)

        comp = QGroupBox("Companion documents (optional, for cross-document consistency)")
        compl = QVBoxLayout(comp)
        self.comp_table = QTableWidget(0, 2)
        self.comp_table.setHorizontalHeaderLabels(["Type", "File"])
        self.comp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.comp_table.verticalHeader().setVisible(False)
        self.comp_table.setMinimumHeight(110)
        compl.addWidget(self.comp_table)
        cr = QHBoxLayout()
        self.comp_type = QComboBox()
        self.comp_type.addItems(list(DOCUMENT_TYPES))
        add = QPushButton("Add…")
        add.clicked.connect(self._add_companion)
        rem = QPushButton("Remove")
        rem.clicked.connect(lambda: self.comp_table.removeRow(self.comp_table.currentRow()))
        cr.addWidget(self.comp_type)
        cr.addWidget(add)
        cr.addWidget(rem)
        cr.addStretch(1)
        compl.addLayout(cr)
        right.addWidget(comp)

        abox = QGroupBox("Analysis")
        al = QVBoxLayout(abox)
        self.use_ai = QCheckBox("Use local AI assistance (Ollama on this computer)")
        cfg = load_model_config(self.ctx.root)
        self.use_ai.setEnabled(bool(cfg.get("enabled")))
        self.use_ai.setToolTip("Enable and configure the local model in Settings." if not cfg.get("enabled") else
                               f"Model {cfg.get('model_name')} at {cfg.get('endpoint')}")
        al.addWidget(self.use_ai)
        ocr = QLabel("OCR for scanned PDFs: " + ("available (Tesseract)" if tesseract_available() else
                                                 "not installed - scanned pages will be reported as not verified"))
        ocr.setObjectName("PageSubtitle")
        al.addWidget(ocr)
        right.addWidget(abox)
        top.addLayout(right, 3)

        self.val_box = QPlainTextEdit()
        self.val_box.setReadOnly(True)
        self.val_box.setMaximumHeight(130)
        self.val_box.setPlaceholderText("Validation results appear here.")
        lay.addWidget(self.val_box)

        nav = QHBoxLayout()
        back = QPushButton("‹  Back")
        back.clicked.connect(lambda: self.go(0))
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reset)
        self.validate_btn = QPushButton("Validate Document")
        self.validate_btn.clicked.connect(self.validate)
        self.start_btn = QPushButton("Start Review")
        self.start_btn.setObjectName("PrimaryButton")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start_review)
        nav.addWidget(back)
        nav.addWidget(cancel)
        nav.addStretch(1)
        nav.addWidget(self.validate_btn)
        nav.addWidget(self.start_btn)
        lay.addLayout(nav)
        return w

    def _fill_project(self, name: str) -> None:
        for p in self.db.list_projects():
            if p["name"] == name:
                self.customer.setText(p.get("customer") or "")
                self.lru.setText(p.get("system_lru") or "")
                self.part_no.setText(p.get("part_number") or "")
                self.cert_basis.setText(p.get("certification_basis") or "")

    def _invalidate(self, *_):
        self.validated = False
        self.start_btn.setEnabled(False)
        self._update_builtin_info()

    def _update_builtin_info(self) -> None:
        dt = self.doc_type.currentData()
        if not dt:
            return
        cl = load_builtin(self.selected_standard(), self.selected_soi(), dt)
        if cl:
            extra = "" if cl.get("validated", True) else " - derived, pending validation by the IV&V Lead"
            self.builtin_info.setText(f"{cl['name']} ({len(cl['items'])} checks){extra}")
        else:
            self.builtin_info.setText("No built-in checklist for this selection - upload your checklist.")
        has_user = bool(self.chk_path.text())
        self.chk_mode.setEnabled(has_user and cl is not None)
        if has_user and cl is None:
            self.chk_mode.setCurrentText("User")
        elif not has_user:
            self.chk_mode.setCurrentText("Built-in")

    def _browse_doc(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Select document", "", DOC_FILTER)
        if f:
            self.doc_path.setText(f)
            self._invalidate()

    def _browse_checklist(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Select review checklist", "", CHK_FILTER)
        if f:
            self.chk_path.setText(f)
            self._invalidate()
            if load_builtin(self.selected_standard(), self.selected_soi(), self.doc_type.currentData()):
                choice = QMessageBox.question(
                    self, "Checklist", "A built-in checklist also exists for this document.\n\nUse your checklist "
                    "together with the built-in one (Combined)?\n\nYes = Combined, No = your checklist only.",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
                if choice == QMessageBox.Cancel:
                    self.chk_path.clear()
                else:
                    self.chk_mode.setCurrentText("Combined" if choice == QMessageBox.Yes else "User")
                self._update_builtin_info()
                if self.chk_path.text():
                    self.chk_mode.setCurrentText("Combined" if choice == QMessageBox.Yes else "User")

    def _add_companion(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Select companion document", "", DOC_FILTER)
        if f:
            r = self.comp_table.rowCount()
            self.comp_table.insertRow(r)
            self.comp_table.setItem(r, 0, QTableWidgetItem(self.comp_type.currentText()))
            it = QTableWidgetItem(Path(f).name)
            it.setData(Qt.UserRole, f)
            self.comp_table.setItem(r, 1, it)

    # ------------------------------------------------------------------ step 3
    def _step3(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.run_title = QLabel("")
        self.run_title.setObjectName("SectionTitle")
        lay.addWidget(self.run_title)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        lay.addWidget(self.bar)
        self.run_msg = QLabel("")
        lay.addWidget(self.run_msg)
        self.run_log = QPlainTextEdit()
        self.run_log.setReadOnly(True)
        lay.addWidget(self.run_log, 1)
        nav = QHBoxLayout()
        nav.addStretch(1)
        self.cancel_run = QPushButton("Cancel review")
        self.cancel_run.clicked.connect(self._cancel)
        nav.addWidget(self.cancel_run)
        lay.addLayout(nav)
        return w

    # ------------------------------------------------------------------ flow
    def go(self, i: int) -> None:
        if i == 1:
            std, soi, dal = self.selected_standard(), self.selected_soi(), self.selected_dal()
            self.sel_label.setText(f"<b>{std}</b>, DAL <b>{dal}</b>, <b>{soi}</b> - {SOI_TITLES[soi]}")
            cur = self.doc_type.currentData()
            self.doc_type.blockSignals(True)
            self.doc_type.clear()
            for code in doc_types_for(soi, std):
                self.doc_type.addItem(f"{code} - {DOCUMENT_TYPES[code][0]}", code)
            idx = self.doc_type.findData(cur)
            self.doc_type.setCurrentIndex(max(0, idx))
            self.doc_type.blockSignals(False)
            names = [p["name"] for p in self.db.list_projects()]
            current = self.project.currentText()
            self.project.blockSignals(True)
            self.project.clear()
            self.project.addItems(names)
            self.project.setEditText(current)
            self.project.blockSignals(False)
            self._invalidate()
        self.stack.setCurrentIndex(i)
        self.steps.set_step(i)

    def reset(self) -> None:
        for wdg in (self.doc_path, self.chk_path, self.doc_no, self.doc_ver):
            wdg.clear()
        self.comp_table.setRowCount(0)
        self.val_box.clear()
        self.round.setValue(1)
        self._invalidate()
        self.go(0)

    def validate(self) -> None:
        path = self.doc_path.text()
        if not path:
            QMessageBox.warning(self, "Validate", "Select the document to review first.")
            return
        if not self.project.currentText().strip():
            QMessageBox.warning(self, "Validate", "Enter the project name.")
            return
        self.val_box.setPlainText("Validating…")
        self.validate_btn.setEnabled(False)
        std, soi, dal, dt = self.selected_standard(), self.selected_soi(), self.selected_dal(), self.doc_type.currentData()
        chk = self.chk_path.text()

        def job():
            out = {"file": validate_file(path)}
            if not out["file"].ok:
                return out
            doc = parse_document(path, use_ocr=self.ctx.config.get("review", {}).get("use_ocr", True))
            out["doc"] = doc
            out["rel"] = check_relevance(doc, dt, soi, std, dal)
            if chk:
                cv = validate_file(chk, CHECKLIST_ALLOWED)
                out["chk_val"] = cv
                if cv.ok:
                    try:
                        out["chk"] = read_user_checklist(chk)
                    except ValueError as exc:
                        out["chk_err"] = str(exc)
            return out

        self.worker = Worker(job)
        self.worker.finished.connect(self._validated)
        self.worker.failed.connect(lambda e: (self.val_box.setPlainText(f"Validation failed: {e}"),
                                              self.validate_btn.setEnabled(True)))
        start_worker(self, self.worker)

    def _validated(self, out: dict) -> None:
        self.validate_btn.setEnabled(True)
        lines = [out["file"].summary()]
        ok = out["file"].ok
        rel = out.get("rel")
        doc = out.get("doc")
        if doc is not None:
            lines.append(f"Pages/parts: {doc.page_count}; sections detected: {len(doc.sections)}; title: "
                         f"{doc.title or '-'}; document no.: {doc.doc_number or '-'}; version: {doc.version or '-'}")
            if not self.doc_no.text() and doc.doc_number:
                self.doc_no.setText(doc.doc_number)
            if not self.doc_ver.text() and doc.version:
                self.doc_ver.setText(doc.version)
            lines += doc.warnings
            if not doc.has_text:
                ok = False
                lines.append("ERROR: no readable text could be extracted, so the document cannot be reviewed.")
        if rel is not None:
            lines.append("Relevance: " + " ".join(rel.messages))
            if not rel.ok:
                ok = False
            elif rel.detected_type and not rel.type_matches_selection:
                choice = QMessageBox.question(
                    self, "Document type",
                    f"The content looks like {rel.detected_type} ({DOCUMENT_TYPES[rel.detected_type][0]}), but "
                    f"{self.doc_type.currentData()} was selected.\n\nUse {rel.detected_type}?\n\nYes = change to "
                    f"{rel.detected_type}; No = keep my selection.", QMessageBox.Yes | QMessageBox.No)
                if choice == QMessageBox.Yes:
                    idx = self.doc_type.findData(rel.detected_type)
                    if idx < 0:
                        lines.append(f"{rel.detected_type} belongs to {DOCUMENT_TYPES[rel.detected_type][1]}; go back "
                                     "and change the SOI stage.")
                        ok = False
                    else:
                        self.doc_type.blockSignals(True)
                        self.doc_type.setCurrentIndex(idx)
                        self.doc_type.blockSignals(False)
                        self._update_builtin_info()
            if rel.dal_conflict or rel.standard_conflict:
                lines.append("Check the standard / DAL selection against the document before starting.")
        if "chk_val" in out:
            if not out["chk_val"].ok:
                ok = False
                lines.append("Checklist: " + "; ".join(out["chk_val"].errors))
            elif "chk_err" in out:
                ok = False
                lines.append("Checklist: " + out["chk_err"])
            elif "chk" in out:
                lines.append(f"Checklist read: {len(out['chk']['items'])} items (original wording preserved).")
        self.val_box.setPlainText("\n".join(lines))
        self.validated = ok
        self.start_btn.setEnabled(ok)

    def build_request(self) -> ReviewRequest:
        comps = [(self.comp_table.item(r, 0).text(), self.comp_table.item(r, 1).data(Qt.UserRole))
                 for r in range(self.comp_table.rowCount())]
        return ReviewRequest(
            standard=self.selected_standard(), dal=self.selected_dal(), soi=self.selected_soi(),
            doc_type=self.doc_type.currentData(), document_path=self.doc_path.text(), username=self.user.username,
            project_name=self.project.currentText().strip(), customer=self.customer.text().strip(),
            system_lru=self.lru.text().strip(), part_number=self.part_no.text().strip(),
            certification_basis=self.cert_basis.text().strip(), doc_number=self.doc_no.text().strip(),
            doc_version=self.doc_ver.text().strip(), companions=comps, checklist_path=self.chk_path.text(),
            checklist_mode=self.chk_mode.currentText(), use_ai=self.use_ai.isChecked(),
            review_round=self.round.value())

    def start_review(self) -> None:
        if not self.validated:
            return
        req = self.build_request()
        sid = self.service.create_session(req)
        self.go(2)
        self.run_title.setText(f"Reviewing {req.doc_type} - {Path(req.document_path).name} (session {sid})")
        self.bar.setValue(0)
        self.run_log.clear()
        self.cancel_run.setEnabled(True)
        self.worker = Worker(self.service.execute, sid, req, with_progress=True)
        self._last_msg = ""
        self.worker.progress.connect(self._progress)
        self.worker.finished.connect(self._done)
        self.worker.failed.connect(self._failed)
        start_worker(self, self.worker)

    def _progress(self, p: int, msg: str) -> None:
        self.bar.setValue(p)
        self.run_msg.setText(msg)
        if msg and msg != self._last_msg and not msg.startswith("Checklist item"):
            self.run_log.appendPlainText(msg)
        self._last_msg = msg

    def _cancel(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.run_log.appendPlainText("Cancelling…")
            self.cancel_run.setEnabled(False)

    def _done(self, result: dict) -> None:
        self.cancel_run.setEnabled(False)
        c = result["counts"]
        self.run_log.appendPlainText(
            f"\nAnalysis mode: {result['mode']}\nVerdicts: C {c['C']}, PC {c['PC']}, NC {c['NC']}, NA {c['NA']}, "
            f"Not verified {c['NR']}, Pending manual review {c['PMR']}\nProposed findings: {result['findings']} "
            f"(Draft - to be approved by the reviewer)\nProposed recommendation: {result['recommendation']}")
        for n in result.get("notes", []):
            self.run_log.appendPlainText("Note: " + n)
        self.reset()
        self.review_finished.emit(result["session_id"])

    def _failed(self, err: str) -> None:
        self.cancel_run.setEnabled(False)
        self.run_log.appendPlainText(f"\nReview failed: {err}")
        QMessageBox.critical(self, "Review failed", err)
