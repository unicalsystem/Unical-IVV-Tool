# Unical Systems – DO-178 IV&V Review Tool

Offline desktop assistant for Unical IV&V engineers reviewing DO-178B / DO-178C
life-cycle data (SOI-1 to SOI-4, DAL A to E). It helps the reviewer. It does not
make certification decisions. Every finding must be approved by a qualified
IV&V engineer before it is issued.

**Current release:** 0.1.0, Phase 1 (Application Foundation).
Architecture and phase plan: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## What works in Phase 1

| Item | Status |
|---|---|
| Login page: logo, username, password, show/hide password, error message | Done |
| Prototype login `admin` / `admin@123` (stored only as a salted PBKDF2 hash) | Done |
| Lock-out after 5 failed attempts (15 minutes) | Done |
| Dashboard: totals, completed, pending, findings, documents reviewed; recent reviews; recent activity | Done |
| Sidebar navigation: Dashboard, New Review, Review History, Checklist Management, Document Library, Settings, About | Done (later-phase pages show their planned scope) |
| Local SQLite database with the full data model (sessions, documents, checklists, findings, reports, audit log) | Done |
| Audit log of logins, logouts and app start | Done |
| Logging to `logs/application.log` (rotating) | Done |
| Automated tests (26) | Passing |

## Install and run on Windows (from source)

You need Windows 10 or 11 (64-bit) and Python 3.11 or later from python.org
("Add python.exe to PATH" ticked).

```bat
cd Unical_DO178_IVV_Tool
setup.bat      :: one time - creates .venv, installs packages, runs tests
run.bat        :: starts the application
```

Or do the same by hand:

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q
python main.py
```

**Offline machines:** on a PC with internet, run
`pip download -r requirements.txt -d wheels`. Copy the `wheels` folder to the
offline PC, then run `setup.bat wheels`.

**Expected result:** the login window opens. Sign in with `admin` / `admin@123`
to open the dashboard. A wrong password shows "Invalid username or password."

## Build a Windows executable

```bat
build_exe.bat
```

This produces `dist\UnicalIVVTool\UnicalIVVTool.exe`. The one-folder build keeps
`config`, `database`, `logs`, `reports` and `templates` next to the exe.

## Run the tests

```bat
python -m pytest -q
```

The tests cover:
- authentication: valid, invalid username, invalid password, empty, lock-out, hashing, audit;
- database: schema, constraints, review versioning, dashboard counts;
- headless UI: login, show/hide password, dashboard, navigation.

## Folder layout

```text
main.py                 entry point
config/                 app_config.json, model_config.json (local LLM, used from Phase 6)
core/                   app_context (paths, config, logging), authentication
database/               schema.sql, db_manager.py, unical_ivv.db (created on first run)
ui/                     theme, widgets, login_window, main_window, dashboard
standards/do178b|do178c objective tables per standard (Phase 4)
checklists/soi1..soi4   built-in checklists, JSON (Phase 4)
templates/excel|word    Unical review checklist + review report reference templates
reports/ uploaded_documents/ logs/   runtime data
tests/                  pytest suite
docs/ARCHITECTURE.md    architecture, decisions, checklist model, phase plan
```

## Security notes

- The prototype account is for development only. It will be replaced by proper
  user management before production use.
- No network calls are made. There are no cloud APIs, no remote database and no
  online authentication. The local LLM (Phase 6) is restricted to `127.0.0.1`.
- Configured paths are resolved inside the application folder only.
