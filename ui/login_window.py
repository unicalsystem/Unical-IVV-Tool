"""Login page."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)

from core.authentication import AuthenticationService, UserSession
from ui.widgets import gold_rule, logo_label


class LoginWindow(QWidget):
    login_succeeded = Signal(object)  # UserSession

    def __init__(self, auth: AuthenticationService, app_name: str, version: str, logo: Path):
        super().__init__()
        self.auth = auth
        self.setObjectName("LoginBackground")
        self.setWindowTitle(f"{app_name} - Login")
        self.resize(980, 640)

        card = QFrame()
        card.setObjectName("LoginCard")
        card.setFixedWidth(420)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(36, 32, 36, 28)
        lay.setSpacing(10)

        lay.addWidget(logo_label(logo, 46), alignment=Qt.AlignHCenter)
        name = QLabel(app_name)
        name.setObjectName("LoginAppName")
        name.setAlignment(Qt.AlignCenter)
        name.setWordWrap(True)
        lay.addWidget(name)
        sub = QLabel("Offline IV&V review assistant for DO-178B / DO-178C life-cycle data")
        sub.setObjectName("PageSubtitle")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        lay.addWidget(sub)
        lay.addSpacing(4)
        lay.addWidget(gold_rule())
        lay.addSpacing(8)

        lay.addWidget(QLabel("Username"))
        self.username = QLineEdit()
        self.username.setPlaceholderText("Enter username")
        self.username.setMaxLength(64)
        lay.addWidget(self.username)

        lay.addWidget(QLabel("Password"))
        self.password = QLineEdit()
        self.password.setPlaceholderText("Enter password")
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setMaxLength(256)
        lay.addWidget(self.password)

        self.show_password = QCheckBox("Show password")
        self.show_password.toggled.connect(
            lambda on: self.password.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        lay.addWidget(self.show_password)

        self.error = QLabel("")
        self.error.setObjectName("LoginError")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        lay.addWidget(self.error)

        self.login_button = QPushButton("Login")
        self.login_button.setObjectName("PrimaryButton")
        self.login_button.setMinimumHeight(38)
        self.login_button.setDefault(True)
        self.login_button.clicked.connect(self.attempt_login)
        lay.addWidget(self.login_button)
        self.username.returnPressed.connect(self.password.setFocus)
        self.password.returnPressed.connect(self.attempt_login)

        note = QLabel(f"Version {version}  |  Works fully offline - no data leaves this computer")
        note.setObjectName("Footnote")
        note.setAlignment(Qt.AlignCenter)
        note.setWordWrap(True)
        lay.addSpacing(6)
        lay.addWidget(note)

        outer = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        outer.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)
        footer = QLabel("© Unical Systems  |  Internal engineering tool  |  Not a certification authority - "
                        "all findings require review by a qualified IV&V engineer")
        footer.setObjectName("Footnote")
        footer.setAlignment(Qt.AlignCenter)
        outer.addWidget(footer)
        self.username.setFocus()

    def attempt_login(self) -> None:
        result = self.auth.authenticate(self.username.text(), self.password.text())
        if result.success:
            self.error.setVisible(False)
            self.password.clear()
            self.login_succeeded.emit(result.session)
        else:
            self.error.setText(result.message)
            self.error.setVisible(True)
            self.password.clear()
            self.password.setFocus()

    def reset(self) -> None:
        self.username.clear()
        self.password.clear()
        self.show_password.setChecked(False)
        self.error.setVisible(False)
        self.username.setFocus()


__all__ = ["LoginWindow", "UserSession"]
