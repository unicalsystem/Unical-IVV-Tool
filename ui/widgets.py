"""Small reusable widgets shared by the pages."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)


def logo_label(path: Path, height: int = 44) -> QLabel:
    label = QLabel()
    pix = QPixmap(str(path))
    if pix.isNull():  # logo placeholder when the asset is missing
        label.setText("UNICAL SYSTEMS")
        label.setStyleSheet("font-weight:700; font-size:14pt; color:#1F3864; letter-spacing:1px;")
    else:
        label.setPixmap(pix.scaledToHeight(height, Qt.SmoothTransformation))
    return label


def gold_rule() -> QFrame:
    rule = QFrame()
    rule.setObjectName("GoldRule")
    return rule


def page_header(title: str, subtitle: str = "") -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("PageTitle")
    lay.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("PageSubtitle")
        s.setWordWrap(True)
        lay.addWidget(s)
    lay.addSpacing(6)
    lay.addWidget(gold_rule())
    return w


class StatCard(QFrame):
    def __init__(self, label: str, value: int | str = 0, tooltip: str = ""):
        super().__init__()
        self.setObjectName("Card")
        self.setMinimumHeight(96)
        if tooltip:
            self.setToolTip(tooltip)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 12, 16, 12)
        accent = QFrame()
        accent.setObjectName("CardAccent")
        outer.addWidget(accent)
        box = QVBoxLayout()
        self.value_label = QLabel(str(value))
        self.value_label.setObjectName("CardValue")
        name = QLabel(label)
        name.setObjectName("CardLabel")
        name.setWordWrap(True)
        box.addWidget(self.value_label)
        box.addWidget(name)
        outer.addLayout(box, 1)

    def set_value(self, value: int | str) -> None:
        self.value_label.setText(str(value))


def make_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setAlternatingRowColors(False)
    table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)  # keep the data order until the user sorts
    table.setSortingEnabled(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    table.horizontalHeader().setStretchLastSection(True)
    return table


def fill_table(table: QTableWidget, rows: list[list], empty_text: str = "No records yet.") -> None:
    table.setSortingEnabled(False)
    table.clearContents()
    if not rows:
        table.setRowCount(1)
        item = QTableWidgetItem(empty_text)
        item.setFlags(Qt.ItemIsEnabled)
        table.setItem(0, 0, item)
        table.setSpan(0, 0, 1, table.columnCount())
        return
    table.clearSpans()
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem()
            if isinstance(value, (int, float)):
                item.setData(Qt.DisplayRole, value)
                item.setTextAlignment(Qt.AlignCenter)
            else:
                item.setText("" if value is None else str(value))
            table.setItem(r, c, item)
    table.resizeColumnsToContents()
    table.setSortingEnabled(True)
