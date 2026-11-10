"""Installed (frozen) build keeps writable data in %LOCALAPPDATA%."""
import sys

from core import app_context


def test_frozen_build_uses_user_data_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    root = app_context.application_root()
    assert root == tmp_path / "Unical Systems" / "IVV Review Tool"
    assert (root / "config" / "app_config.json").exists()
    ctx = app_context.load_context(root)
    assert ctx.db_path.parent == root / "database"


def test_source_build_uses_project_folder():
    assert (app_context.application_root() / "main.py").exists()
