# Unical Systems – DO-178 IV&V Review Tool

Offline desktop assistant for Unical IV&V engineers reviewing DO-178B / DO-178C
life-cycle data (SOI-1 to SOI-4, DAL A to E). **The tool proposes, the engineer
decides.** Every verdict carries evidence, and no finding is issued until a
lead or admin approves it.

**Current release:** 1.0.1 (Phases 1–8 complete; every checklist item now gets a proposed verdict).
Architecture and design decisions: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Download the Windows installer

Every push to `main` is tested and built on Windows by GitHub Actions. Download
from the **Releases** page (or the `exe-build` branch, folder `publish/`):

- `UnicalIVVTool_Setup_1.0.1.exe`: standalone installer, one file with Python,
  Qt and all libraries inside. Start Menu and desktop shortcuts, uninstaller,
  no admin rights needed.
- `UnicalIVVTool_Portable.exe`: a single exe that runs without installing.

User data (database, logs, reports, uploads, editable config and edited
checklists) is kept in `%LOCALAPPDATA%\Unical Systems\IVV Review Tool`. It is
kept on uninstall and upgrade.

First sign-in: `admin` / `admin@123` (prototype account, stored only as a
salted PBKDF2 hash). Add named users in **Settings** and stop using the
prototype account before production use.

## How a review runs

1. **New Review → Step 1:** choose DO-178B or DO-178C, the DAL (A–E) and the SOI.
2. **Step 2:** choose the document type (only the types for that SOI are listed),
   fill the project details, and browse to the document (PDF, DOCX, XLSX, TXT).
   - Optional: a user checklist (XLSX, DOCX or PDF). The tool asks whether to use
     the **Built-in**, the **User** or the **Combined** checklist.
   - Optional: companion documents (for example the PSAC when reviewing the SVP)
     for the cross-document consistency checks.
   - **Validate** checks the file and identifies the document from its content.
     A wrong type, an unrelated document, or a DAL / standard conflict is reported
     before the review starts.
3. **Step 3:** the review runs in the background (it can be cancelled).
4. **Review Results:**
   - *Findings*: approve, reject, edit, add a manual finding, approve all.
   - *Checklist Assessment*: every check with verdict, evidence and page. Change a
     verdict, set the same verdict for several checks at once, or raise a finding
     from a check.
   - *Structure & Consistency*: sections found, companion consistency, documents
     referenced but not supplied.
   - **Finalise** (all draft findings decided), then **Reports** generates the
     Unical Excel checklist and Word review report from the reference templates.
5. **Review History** finds any earlier review and re-exports its reports. A
   re-review of the same document is stored as a new version; nothing is
   overwritten.

### Verdicts

| Code | Meaning |
|---|---|
| C | Compliant – evidence quoted |
| PC | Partially compliant |
| NC | Not compliant |
| NA | Not applicable (reason required, e.g. not required at this DAL) |
| NR | Not verified yet – the reviewer must conclude |
| PCL | Pending clarification from the applicant |
| PMR | Pending manual review – the tool could not reach a reliable conclusion |

How the verdicts are proposed without the local AI:
- **Document-control checks** (document number, issue/date, signatories,
  revision history, DAL statement, abbreviations, references, placeholders such
  as TBD, broken cross-references) are decided by fixed rules.
- **Every other check** is decided by evidence matching. The tool finds the
  concepts the criterion asks for, searches every passage of the document, and
  quotes the best passage with its page and section:
  - **C**: the concepts are covered together in one substantive passage (65% coverage or more);
  - **PC**: the topic is addressed but parts are missing, thin or still TBD (the missing points are listed);
  - **NC**: the document has no text covering what the criterion asks for;
  - **NA**: not required at the selected DAL, or a conditional check whose condition is not met;
  - **NR**: the text cannot decide it (scanned pages, a very general criterion, or a check that needs a
    companion document that was not supplied).
- Every NC and PC becomes a draft finding with its severity and reason.

Evidence matching shows whether a topic is covered; it cannot judge depth the
way an experienced reviewer does. On Unical's own completed reviews it
agreed with the reviewer on about half the checks (MSU SQAP 47 of 87). Its
errors are mostly C versus PC; it rarely calls covered content NC. Treat the
verdicts as a first pass: confirm or change them in the Checklist Assessment
tab, and approve the findings before finalising. The local AI, when enabled,
replaces the matcher's verdict wherever it can quote the document.

## Built-in checklists

| SOI | DO-178C | DO-178B (derived, pending validation) |
|---|---|---|
| SOI-1 | PSAC 198, SDP 131, SVP 102, SCMP 80, SQAP 87, SRS 33, SDS 33, SCS 31, IVVP 34 | same documents |
| SOI-2 | SRD 39, SDD 42, Source Code 33, Trace Data 37 | SRD, SDD, Source Code |
| SOI-3 | SVCP 37, SVR 80, PR 29 | SVCP, SVR, PR |
| SOI-4 | SAS 34, SCI 34, SECI 25, SCMR 30, SQAR 30 | same documents |

- Sheets: A Document Control, B Template Compliance, C DO-178 Objectives
  (Annex A, filtered by DAL), D Traceability, E Auditability, F Content Depth.
- The five plan checklists were imported from Unical's own review checklists
  (definitions only, no project data). The others were written from DO-178C
  Section 11 and Annex A.
- DO-178C Annex A was transcribed from the standard and checked: applicable
  objectives A 71 / B 69 / C 62 / D 26.
- **DO-178B:** Annex A is not encoded (no copy of DO-178B was available). The
  DO-178B checklists have DO-178C-only content removed and are marked *not
  validated*. The IV&V Lead should confirm the section references and mark them
  validated in **Checklist Management**.
- Admins can edit, add, delete and validate checks, import another Unical
  checklist workbook, or revert to the built-in version. Edits are saved in the
  user data folder, not in the program folder.

## Optional add-ons (offline)

- **OCR for scanned PDFs:** install Tesseract OCR for Windows
  (default folder `C:\Program Files\Tesseract-OCR`). The tool finds it
  automatically. Without it, scanned pages are reported and left for manual
  review.
- **Local AI assistant:** install Ollama and pull a model, for example
  `ollama pull llama3.1:8b-instruct-q4_K_M`. In **Settings → Local AI** enable
  it and press *Test connection*. Only `127.0.0.1` / `localhost` endpoints are
  accepted. The AI must quote the document word for word; an unverified quote or
  low confidence becomes PMR, and all AI findings stay *Draft* until approved.

## Run from source

Windows 10/11 64-bit, Python 3.11 or later.

```bat
setup.bat      :: one time - creates .venv, installs packages, runs tests
run.bat        :: starts the application
build_exe.bat  :: builds dist\UnicalIVVTool\UnicalIVVTool.exe
```

Offline PC: on a PC with internet run `pip download -r requirements.txt -d wheels`,
copy `wheels` across, then `setup.bat wheels`.

## Tests

`python -m pytest -q` – 90 tests:
- authentication, database, app paths, headless UI;
- upload validation: valid, corrupted, empty, unsupported, wrong extension,
  scanned, password-protected;
- identification of PSAC, SDP, SVP, SCMP, SQAP, SRD, SDD, SVCP, SAS; wrong type,
  unrelated document, DAL conflict;
- checklist library, user checklists (XLSX/DOCX/PDF), combined mode, workbook import;
- review engine: missing / incomplete sections, placeholders, traceable findings,
  severity rationale, NA by DAL, DAL E, cross-document inconsistency,
  recommendation;
- local AI with a mock server: remote endpoint refused, fallback to rules,
  verified quote accepted, invented quote → PMR, low confidence → PMR;
- service end to end, re-review versioning, finalise rules, history search;
- Excel / Word reports from the templates: sheets, finding numbers, check count,
  formulas, no overwrite.

## Folder layout

```text
main.py                 entry point
config/                 app_config.json, model_config.json, severity_rules.json
core/                   services: validator, parser, classifier, checklist engine,
                        review engine, traceability, severity, ai_agent, reports
database/               schema.sql, db_manager.py
ui/                     PySide6 pages and dialogs
standards/do178c        Annex A objective tables (verified)
checklists/DO-178B|C    built-in checklists, JSON, per SOI and document
templates/excel|word    Unical reference templates for the reports
tools/                  checklist build scripts
installer/              Inno Setup script
tests/                  pytest suite
```

## Security

- Fully offline: no cloud APIs, no remote database, no online authentication.
- Uploaded documents are treated as untrusted: they are copied read-only into
  the session folder and only read as text; macros and scripts are never run.
- Passwords are stored only as salted PBKDF2 hashes; 5 failed attempts lock the
  account for 15 minutes. Every login, review, verdict change, approval and
  report is in the audit log.
