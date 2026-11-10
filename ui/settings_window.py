"""Settings (admin-editable): report signatories, review options, local AI model, user management."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from core.ai_agent import LocalAIAgent, load_model_config
from core.app_context import AppContext
from core.authentication import AuthenticationService, UserSession, hash_password
from core.document_parser import tesseract_available
from database.db_manager import DatabaseManager
from ui.widgets import fill_table, make_table, page_header


class SettingsPage(QWidget):
    def __init__(self, ctx: AppContext, db: DatabaseManager, user: UserSession):
        super().__init__()
        self.ctx, self.db, self.user = ctx, db, user
        self.admin = user.role == "admin"
        self.setObjectName("Page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22)
        outer.addWidget(page_header("Settings", "Changes are saved locally. Only administrators can edit settings."))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("Page")
        lay = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        rep = ctx.config.get("report", {})
        g1 = QGroupBox("Report signatories and defaults")
        f1 = QFormLayout(g1)
        self.sig = {}
        for key, label in (("prepared", "Prepared by"), ("checked", "Checked / reviewed by"), ("approved", "Approved by")):
            s = rep.get("signatories", {}).get(key, {})
            n, d = QLineEdit(s.get("name", "")), QLineEdit(s.get("designation", ""))
            row = QHBoxLayout()
            row.addWidget(n, 2)
            row.addWidget(d, 1)
            n.setPlaceholderText("Name")
            d.setPlaceholderText("Designation")
            self.sig[key] = (n, d)
            f1.addRow(label + ":", row)
        self.default_customer = QLineEdit(rep.get("default_customer", ""))
        f1.addRow("Default customer:", self.default_customer)
        self.classification = QLineEdit(rep.get("classification", ""))
        self.classification.setPlaceholderText("Default: 'Unical Systems & <customer> - Confidential'")
        f1.addRow("Report classification:", self.classification)
        self.reports_folder = QLineEdit(ctx.config.get("reports_folder", "reports"))
        f1.addRow("Default reports folder:", self.reports_folder)
        lay.addWidget(g1)

        g2 = QGroupBox("Document processing")
        f2 = QFormLayout(g2)
        self.use_ocr = QCheckBox("Use OCR for scanned PDF pages")
        self.use_ocr.setChecked(ctx.config.get("review", {}).get("use_ocr", True))
        f2.addRow(self.use_ocr)
        f2.addRow(QLabel("Tesseract OCR: " + ("installed" if tesseract_available() else
                                              "not installed (install Tesseract and add it to PATH to enable OCR)")))
        lay.addWidget(g2)

        m = load_model_config(ctx.root)
        g3 = QGroupBox("Local AI model (optional - runs on this computer only)")
        f3 = QFormLayout(g3)
        self.ai_enabled = QCheckBox("Enable AI-assisted analysis")
        self.ai_enabled.setChecked(bool(m.get("enabled")))
        f3.addRow(self.ai_enabled)
        self.model = QLineEdit(m.get("model_name", ""))
        f3.addRow("Model name:", self.model)
        self.endpoint = QLineEdit(m.get("endpoint", "http://127.0.0.1:11434"))
        f3.addRow("Local endpoint:", self.endpoint)
        self.ctx_len = QSpinBox()
        self.ctx_len.setRange(1024, 262144)
        self.ctx_len.setValue(int(m.get("context_length", 8192)))
        f3.addRow("Context length:", self.ctx_len)
        self.temp = QDoubleSpinBox()
        self.temp.setRange(0, 1)
        self.temp.setSingleStep(0.05)
        self.temp.setValue(float(m.get("temperature", 0.1)))
        f3.addRow("Temperature:", self.temp)
        self.timeout = QSpinBox()
        self.timeout.setRange(10, 3600)
        self.timeout.setValue(int(m.get("timeout_seconds", 180)))
        f3.addRow("Timeout (s):", self.timeout)
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(128, 16384)
        self.max_tokens.setValue(int(m.get("max_output_tokens", 1500)))
        f3.addRow("Max output tokens:", self.max_tokens)
        test = QPushButton("Test connection")
        test.clicked.connect(self._test_ai)
        f3.addRow(test)
        lay.addWidget(g3)

        g4 = QGroupBox("Users")
        v4 = QVBoxLayout(g4)
        self.users = make_table(["Username", "Full name", "Role", "Active", "Last login"])
        self.users.setMaximumHeight(170)
        v4.addWidget(self.users)
        add = QHBoxLayout()
        self.nu_name, self.nu_full, self.nu_pw = QLineEdit(), QLineEdit(), QLineEdit()
        self.nu_pw.setEchoMode(QLineEdit.Password)
        self.nu_name.setPlaceholderText("username")
        self.nu_full.setPlaceholderText("full name")
        self.nu_pw.setPlaceholderText("password (min 10 chars)")
        self.nu_role = QComboBox()
        self.nu_role.addItems(["reviewer", "lead", "viewer", "admin"])
        b = QPushButton("Add user")
        b.clicked.connect(self._add_user)
        for w in (self.nu_name, self.nu_full, self.nu_pw, self.nu_role, b):
            add.addWidget(w)
        v4.addLayout(add)
        lay.addWidget(g4)

        g5 = QGroupBox("Paths")
        v5 = QVBoxLayout(g5)
        info = make_table(["Item", "Value"])
        info.setSortingEnabled(False)
        info.setMaximumHeight(170)
        fill_table(info, [["Data folder", str(ctx.root)], ["Database", str(ctx.db_path)],
                          ["Schema version", db.schema_version()], ["Log file", str(ctx.log_path)],
                          ["Network use", "None. No cloud services; the AI endpoint must be on this computer."]])
        v5.addWidget(info)
        lay.addWidget(g5)
        lay.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)
        self.save_btn = QPushButton("Save settings")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self._save)
        row.addWidget(self.save_btn)
        outer.addLayout(row)
        if not self.admin:
            for w in body.findChildren((QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox, QPushButton)):
                if w is not test:
                    w.setEnabled(False)
            self.save_btn.setEnabled(False)
        self._load_users()

    def _load_users(self) -> None:
        with self.db.connect() as conn:
            rows = [dict(r) for r in conn.execute("SELECT username, full_name, role, is_active, last_login_at FROM users")]
        fill_table(self.users, [[r["username"], r["full_name"], r["role"], "Yes" if r["is_active"] else "No",
                                 (r["last_login_at"] or "")[:16]] for r in rows])

    def _add_user(self) -> None:
        name, pw = self.nu_name.text().strip(), self.nu_pw.text()
        if not name or len(pw) < 10:
            QMessageBox.warning(self, "Users", "Enter a username and a password of at least 10 characters.")
            return
        if self.db.get_user(name):
            QMessageBox.warning(self, "Users", "That username already exists.")
            return
        it = int(self.ctx.config["security"]["pbkdf2_iterations"])
        h, s = hash_password(pw, iterations=it)
        self.db.create_user(name, self.nu_full.text().strip(), self.nu_role.currentText(), h, s, it)
        self.db.audit(self.user.username, "USER_CREATED", f"{name} ({self.nu_role.currentText()})")
        for w in (self.nu_name, self.nu_full, self.nu_pw):
            w.clear()
        self._load_users()

    def _model_cfg(self) -> dict:
        return {"enabled": self.ai_enabled.isChecked(), "runtime": "ollama", "model_name": self.model.text().strip(),
                "endpoint": self.endpoint.text().strip(), "context_length": self.ctx_len.value(),
                "temperature": self.temp.value(), "timeout_seconds": self.timeout.value(),
                "max_output_tokens": self.max_tokens.value()}

    def _test_ai(self) -> None:
        cfg = self._model_cfg() | {"enabled": True}
        try:
            agent = LocalAIAgent(cfg)
        except ValueError as exc:
            QMessageBox.warning(self, "AI", str(exc))
            return
        if agent.is_available():
            QMessageBox.information(self, "AI", f"Local model '{cfg['model_name']}' is available.")
        else:
            QMessageBox.warning(self, "AI", agent.last_error + "\n\nThe tool will continue in rule-based mode.")

    def _save(self) -> None:
        try:
            LocalAIAgent(self._model_cfg())  # refuses non-local endpoints
        except ValueError as exc:
            QMessageBox.warning(self, "Settings", str(exc))
            return
        cfg_dir = self.ctx.root / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        app_file = cfg_dir / "app_config.json"
        data = json.loads(app_file.read_text(encoding="utf-8")) if app_file.exists() else {}
        data.setdefault("report", {})
        data["report"]["signatories"] = {k: {"name": n.text().strip(), "designation": d.text().strip()}
                                         for k, (n, d) in self.sig.items()}
        data["report"]["default_customer"] = self.default_customer.text().strip()
        data["report"]["classification"] = self.classification.text().strip()
        data["reports_folder"] = self.reports_folder.text().strip() or "reports"
        data.setdefault("review", {})["use_ocr"] = self.use_ocr.isChecked()
        app_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        (cfg_dir / "model_config.json").write_text(json.dumps(self._model_cfg(), indent=2), encoding="utf-8")
        for k in ("report", "review", "reports_folder"):
            self.ctx.config[k] = data[k]
        self.db.audit(self.user.username, "SETTINGS_SAVED", "")
        QMessageBox.information(self, "Settings", "Settings saved.")
