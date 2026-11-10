"""Checklist Management (Phase 4): browse, edit (admin), import Unical workbooks, export."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget)

from core import checklist_engine as ce
from core.authentication import UserSession
from core.constants import DOCUMENT_TYPES, SOI_STAGES, STANDARDS
from ui.widgets import fill_table, make_table, page_header


class ItemDialog(QDialog):
    def __init__(self, parent, item: dict):
        super().__init__(parent)
        self.setWindowTitle(f"Checklist item {item.get('ref') or '(new)'}")
        self.resize(760, 620)
        self.item = dict(item)
        form = QFormLayout(self)
        self.fields = {}
        for key, label, multi in (("ref", "Checklist ID", False), ("sheet", "Sheet (A-F)", False),
                                  ("group", "Group", False), ("section", "Section number", False),
                                  ("question", "Review question", True), ("expected_evidence", "Expected evidence", True),
                                  ("reference", "Reference", False), ("dal", "DAL applicability", False),
                                  ("condition", "Condition (if conditional)", False), ("guidance", "Review guidance", True)):
            w = QPlainTextEdit(item.get(key) or "") if multi else QLineEdit(item.get(key) or "")
            if multi:
                w.setMaximumHeight(90)
            self.fields[key] = w
            form.addRow(label + ":", w)
        self.appl = QComboBox()
        self.appl.addItems(["Mandatory", "Conditional", "Not Applicable"])
        self.appl.setCurrentText(item.get("applicability") or "Mandatory")
        form.addRow("Applicability:", self.appl)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _ok(self):
        if not self._text("ref") or not self._text("question"):
            QMessageBox.warning(self, "Item", "Checklist ID and review question are required.")
            return
        self.accept()

    def _text(self, k):
        w = self.fields[k]
        return (w.toPlainText() if isinstance(w, QPlainTextEdit) else w.text()).strip()

    def values(self) -> dict:
        out = dict(self.item)
        for k in self.fields:
            out[k] = self._text(k)
        out["applicability"] = self.appl.currentText()
        return out


class ChecklistManagerPage(QWidget):
    def __init__(self, user: UserSession):
        super().__init__()
        self.user = user
        self.current: dict | None = None
        self.setObjectName("Page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.addWidget(page_header("Checklist Management", "Built-in checklists per standard, SOI and document type, in "
                                                          "the Unical A-F sheet structure. Edits are saved as a local "
                                                          "copy that overrides the shipped checklist."))
        self.admin = user.role == "admin"
        if not self.admin:
            n = QLabel("Read-only: only administrators can edit or import checklists.")
            n.setObjectName("Banner")
            lay.addWidget(n)
        split = QSplitter(Qt.Vertical)
        self.list_table = make_table(["Standard", "SOI", "Document", "Name", "Items", "Validated", "Edited", "Origin"])
        self.list_table.itemSelectionChanged.connect(self._select)
        split.addWidget(self.list_table)
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel("Select a checklist")
        self.title.setObjectName("SectionTitle")
        bl.addWidget(self.title)
        self.items = make_table(["ID", "Sheet", "Section", "Review question", "Expected evidence", "Reference", "DAL",
                                 "Applicability", "Rule"])
        self.items.doubleClicked.connect(self._edit)
        bl.addWidget(self.items, 1)
        row = QHBoxLayout()
        self.btn_edit = QPushButton("Edit item…")
        self.btn_add = QPushButton("Add item…")
        self.btn_del = QPushButton("Delete item")
        self.btn_valid = QPushButton("Mark validated")
        self.btn_import = QPushButton("Import Unical checklist workbook…")
        self.btn_export = QPushButton("Export to Excel…")
        self.btn_reset = QPushButton("Revert to shipped version")
        for b, fn in ((self.btn_edit, self._edit), (self.btn_add, self._add), (self.btn_del, self._delete),
                      (self.btn_valid, self._validate), (self.btn_reset, self._revert)):
            b.clicked.connect(fn)
            b.setEnabled(self.admin)
            row.addWidget(b)
        row.addStretch(1)
        self.btn_import.clicked.connect(self._import)
        self.btn_import.setEnabled(self.admin)
        self.btn_export.clicked.connect(self._export)
        row.addWidget(self.btn_import)
        row.addWidget(self.btn_export)
        bl.addLayout(row)
        split.addWidget(bottom)
        split.setSizes([260, 520])
        lay.addWidget(split, 1)

    def showEvent(self, ev):
        self.refresh()
        super().showEvent(ev)

    def refresh(self) -> None:
        self.catalogue = ce.list_builtin()
        fill_table(self.list_table, [[c["standard"], c["soi"], c["document_type"], c["name"], c["items"],
                                      "Yes" if c["validated"] else "Pending", "Yes" if c.get("edited") else "",
                                      c["origin"]] for c in self.catalogue])
        self.list_table.setColumnWidth(3, 360)

    def _select(self) -> None:
        r = self.list_table.currentRow()
        if r < 0 or r >= len(self.catalogue):
            return
        meta = self.catalogue[r]
        for c in (0, 1, 2):
            pass
        std = self.list_table.item(r, 0).text()
        soi = self.list_table.item(r, 1).text()
        doc = self.list_table.item(r, 2).text()
        self.current = ce.load_builtin(std, soi, doc)
        self._show_items()

    def _show_items(self) -> None:
        if not self.current:
            return
        c = self.current
        self.title.setText(f"{c['name']} - {c['standard']} {c['soi']} ({len(c['items'])} items)"
                           + ("" if c.get("validated", True) else "  [pending validation]"))
        fill_table(self.items, [[i["ref"], i.get("sheet", ""), i.get("section", ""), i["question"],
                                 i.get("expected_evidence", ""), i.get("reference", ""), i.get("dal", ""),
                                 i.get("applicability", "") + (f" ({i['condition']})" if i.get("condition") else ""),
                                 i.get("rule") or ""] for i in c["items"]])
        self.items.setColumnWidth(3, 420)
        self.items.setColumnWidth(4, 260)

    def _save(self) -> None:
        if not self.current:
            return
        self.current["source"] = "Built-in"
        ce.save_builtin(self.current)
        self.refresh()
        self._show_items()

    def _row_ref(self) -> str | None:
        r = self.items.currentRow()
        it = self.items.item(r, 0) if r >= 0 else None
        return it.text() if it else None

    def _edit(self, *_):
        if not self.admin or not self.current:
            return
        ref = self._row_ref()
        idx = next((i for i, it in enumerate(self.current["items"]) if it["ref"] == ref), None)
        if idx is None:
            return
        dlg = ItemDialog(self, self.current["items"][idx])
        if dlg.exec() == QDialog.Accepted:
            self.current["items"][idx] = dlg.values()
            self._save()

    def _add(self) -> None:
        if not self.current:
            return
        dlg = ItemDialog(self, ce.new_item(ref="", sheet="F"))
        if dlg.exec() == QDialog.Accepted:
            v = dlg.values()
            if any(i["ref"] == v["ref"] for i in self.current["items"]):
                QMessageBox.warning(self, "Item", f"ID {v['ref']} already exists.")
                return
            self.current["items"].append(v)
            self._save()

    def _delete(self) -> None:
        ref = self._row_ref()
        if not ref or not self.current:
            return
        if QMessageBox.question(self, "Delete", f"Delete checklist item {ref}?") == QMessageBox.Yes:
            self.current["items"] = [i for i in self.current["items"] if i["ref"] != ref]
            self._save()

    def _validate(self) -> None:
        if not self.current:
            return
        if QMessageBox.question(self, "Validate", "Confirm that this checklist has been checked against the standard by "
                                                  "the IV&V Lead?") == QMessageBox.Yes:
            self.current["validated"] = True
            self.current["origin"] = self.current.get("origin", "") + f" Validated by {self.user.username}."
            self._save()

    def _revert(self) -> None:
        if not self.current or ce.USER_ROOT is None:
            return
        f = ce.USER_ROOT / self.current["standard"] / self.current["soi"] / f"{self.current['document_type']}.json"
        if f.exists() and QMessageBox.question(self, "Revert", "Discard local edits and use the shipped checklist?") \
                == QMessageBox.Yes:
            f.unlink()
            self.refresh()
            self.current = ce.load_builtin(self.current["standard"], self.current["soi"], self.current["document_type"])
            self._show_items()

    def _import(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Unical review checklist workbook", "", "Excel (*.xlsx)")
        if not f:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Import as")
        form = QFormLayout(dlg)
        std, soi, doc = QComboBox(), QComboBox(), QComboBox()
        std.addItems(STANDARDS)
        std.setCurrentText("DO-178C")
        soi.addItems(SOI_STAGES)
        doc.addItems(list(DOCUMENT_TYPES))
        form.addRow("Standard:", std)
        form.addRow("SOI:", soi)
        form.addRow("Document type:", doc)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            cl = ce.import_unical_workbook(f, std.currentText(), soi.currentText(), doc.currentText())
        except Exception as exc:
            QMessageBox.critical(self, "Import", str(exc))
            return
        if ce.load_builtin(std.currentText(), soi.currentText(), doc.currentText()) and QMessageBox.question(
                self, "Import", "A checklist already exists for this selection. Replace it (local copy)?") != QMessageBox.Yes:
            return
        ce.save_builtin(cl)
        self.refresh()
        QMessageBox.information(self, "Import", f"Imported {len(cl['items'])} checks. Project-specific verdicts were "
                                                "not copied.")

    def _export(self) -> None:
        if not self.current:
            return
        f, _ = QFileDialog.getSaveFileName(self, "Export checklist", f"{self.current['id']}.xlsx", "Excel (*.xlsx)")
        if not f:
            return
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "Checklist"
        hdr = ["Checklist ID", "Standard", "DAL", "SOI", "Document Type", "Section", "Group", "Review Question",
               "Expected Evidence", "Reference", "Applicability", "Condition", "Review Guidance"]
        ws.append(hdr)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F3864")
        cl = self.current
        for i in cl["items"]:
            ws.append([i["ref"], cl["standard"], i.get("dal"), cl["soi"], cl["document_type"], i.get("section"),
                       i.get("group"), i["question"], i.get("expected_evidence"), i.get("reference"),
                       i.get("applicability"), i.get("condition"), i.get("guidance")])
        for col, w in zip("ABCDEFGHIJKLM", (10, 10, 10, 8, 10, 12, 30, 70, 45, 28, 13, 20, 50)):
            ws.column_dimensions[col].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
        wb.save(f)
        QMessageBox.information(self, "Export", f"Saved {f}")
