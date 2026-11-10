"""Application paths, configuration loading and logging set-up.

Everything is resolved relative to the application folder so the tool runs the
same way from source and from a PyInstaller executable. No network access.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def application_root() -> Path:
    """Folder holding config/, assets/, database/ ... (source or frozen exe)."""
    if getattr(sys, "frozen", False):  # PyInstaller one-folder build
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundled_resource(relative: str) -> Path:
    """Read-only resource shipped with the app (assets, default config)."""
    base = Path(getattr(sys, "_MEIPASS", application_root()))
    return base / relative


DEFAULT_CONFIG: dict[str, Any] = {
    "app_name": "Unical Systems - DO-178 IV&V Review Tool",
    "app_short_name": "Unical IV&V Review Tool",
    "version": "0.1.0",
    "company": "Unical Systems",
    "database_file": "database/unical_ivv.db",
    "log_file": "logs/application.log",
    "log_level": "INFO",
    "reports_folder": "reports",
    "uploads_folder": "uploaded_documents",
    "security": {"max_failed_logins": 5, "lockout_minutes": 15, "pbkdf2_iterations": 240000},
    "ui": {"theme": "light", "window_width": 1280, "window_height": 800, "recent_activity_rows": 15},
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


@dataclass
class AppContext:
    root: Path
    config: dict[str, Any]

    @property
    def db_path(self) -> Path:
        return self._safe_path(self.config["database_file"])

    @property
    def log_path(self) -> Path:
        return self._safe_path(self.config["log_file"])

    @property
    def logo_path(self) -> Path:
        return bundled_resource("assets/unical_logo.png")

    def _safe_path(self, relative: str) -> Path:
        """Resolve a configured path and refuse anything outside the app folder."""
        path = (self.root / relative).resolve()
        if self.root.resolve() not in path.parents and path != self.root.resolve():
            raise ValueError(f"Configured path is outside the application folder: {relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


def load_context(root: Path | None = None) -> AppContext:
    root = root or application_root()
    config = dict(DEFAULT_CONFIG)
    cfg_file = root / "config" / "app_config.json"
    if not cfg_file.exists():
        cfg_file = bundled_resource("config/app_config.json")
    if cfg_file.exists():
        try:
            config = _merge(DEFAULT_CONFIG, json.loads(cfg_file.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:  # fall back to safe defaults
            logging.getLogger(__name__).warning("Config file unreadable (%s); using defaults", exc)
    return AppContext(root=root, config=config)


def setup_logging(ctx: AppContext) -> None:
    level = getattr(logging, str(ctx.config.get("log_level", "INFO")).upper(), logging.INFO)
    handler = logging.handlers.RotatingFileHandler(ctx.log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"))
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root_logger.handlers):
        root_logger.addHandler(handler)
    if not any(type(h) is logging.StreamHandler for h in root_logger.handlers):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
        root_logger.addHandler(console)
