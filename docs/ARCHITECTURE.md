# Architecture – Unical DO-178B / DO-178C IV&V Review Tool

Version 0.1 (Phase 1) · Unical Systems · Internal

## 1. Purpose and guiding rule

The tool supports Unical IV&V engineers in reviewing life-cycle data for SOI-1 to
SOI-4. The aim is to get approval from the certification authority (RCMA /
CEMILAC, or another authority) through proper verification, validation and clear
recommendations.

The guiding rule is: **the tool proposes, the engineer decides.**
- Every verdict and finding carries evidence: a quoted extract with a page or section.
- If evidence is not available, the tool says so.
- If the tool cannot reach a reliable conclusion, it marks the item `Pending Manual Review`.
- Nothing is issued until a reviewer or lead approves it.

## 2. Layered architecture

```text
+------------------------------------------------------------------+
| UI (PySide6)  login · dashboard · new review wizard · results ·  |
|               history · checklist manager · settings             |
|               long jobs run in QThread workers (GUI never blocks)|
+------------------------------------------------------------------+
| Application services (core/)                                     |
|  authentication · document_validator · document_parser ·         |
|  document_classifier · checklist_engine · review_engine ·        |
|  traceability_engine · severity_classifier · ai_agent ·          |
|  report_manager                                                  |
+------------------------------------------------------------------+
| Knowledge base (versioned files)                                 |
|  standards/do178b|do178c  objective tables (Annex A), sections   |
|  checklists/soi1..4      built-in checklists (JSON)              |
|  templates/excel|word    Unical report templates                 |
+------------------------------------------------------------------+
| Persistence: SQLite (database/db_manager.py is the only SQL)     |
| Local LLM runtime (optional): Ollama on 127.0.0.1                |
+------------------------------------------------------------------+
```

The modules are kept separate as follows:
- The UI never runs SQL or parses documents.
- `review_engine` never talks to Qt.
- `ai_agent` is behind one interface, so the model can be swapped.

## 3. Review pipeline (Phases 3–7)

1. **Validate the file:** extension, size, readable, encrypted, scanned, text present.
2. **Parse:** PyMuPDF / python-docx / openpyxl turn the file into blocks (page, section number, heading, text, table).
3. **Classify:** a content-based score for the document type, from title, number pattern, headings and terms.
   - The tool asks the user to confirm when the score is low or the type does not match the selection.
4. **Check relevance:** the document must belong to DO-178B/C, the chosen SOI and the chosen DAL. Unrelated documents are rejected.
5. **Select the checklist:** built-in, user-supplied, or combined, filtered by standard, DAL and applicability.
6. **Run the rule stage:** checks that can be decided deterministically.
   - Examples: cover fields, revision history, TOC, required headings, references to companion plans, identifiers, dates.
7. **Run the AI stage (optional):** one prompt per checklist item, using only the retrieved section text.
   - The output must be structured JSON with a verdict, a quote and a page.
   - If the quote cannot be found in the source, the result becomes `Pending Manual Review`.
8. **Check cross-documents:** IDs, versions, DAL, roles, independence and tools are compared across the uploaded plans.
   - If a document is referenced but not uploaded, the result is "could not verify". It is not treated as missing.
9. **Generate findings:** checks are grouped into FIN-nn, each with severity, a written rationale, and recommendation text.
10. **Human approval:** the reviewer edits, approves or rejects each finding. Only approved findings go into the reports.
11. **Produce reports:** Excel (Unical checklist workbook) and Word (Unical review report).

## 4. Decisions taken (defaults proposed for the missing points)

| # | Topic | Default chosen | Reason / note |
|---|---|---|---|
| D1 | Python / Qt | Python 3.11+ (tested on 3.13), PySide6 6.x | As per requirement |
| D2 | Password storage | PBKDF2-HMAC-SHA256, 240,000 iterations, 16-byte random salt; lock-out after 5 failures | No external package needed; a stronger scheme can replace it later |
| D3 | Roles | admin, lead, reviewer, viewer | Lead approves findings (AC-22); admin edits checklists and settings |
| D4 | Verdict codes | Unical codes **C, PC, NC, NA, NR**, plus **PCL** (Pending Clarification) and **PMR** (Pending Manual Review) | Same as the existing Unical checklists. NR = Not Verified |
| D5 | Evidence state | Present / Present-Incomplete / Present-Inconsistent / Not Present / Cannot Verify / Not Applicable | Keeps "not in this document" separate from "activity not done" |
| D6 | Severity | Major / Minor / Observation, each with a written rationale | Not keyword-based; rationale is mandatory |
| D7 | Review history | A new `review_version` on every re-run; nothing is overwritten. `review_round` = 1st review, closure re-review | Matches the Unical round-1 / round-2 closure practice |
| D8 | Checklist master format | JSON files in `checklists/` (reviewable, version-controlled), loaded into SQLite | Editable by admin users in the UI |
| D9 | Excel report | The **Unical review checklist workbook** layout: Instructions, Summary, Findings register, sheets A–F | This is Unical's existing review format; reference copy in `templates/excel` |
| D10 | Word report | The **Unical review report** layout: cover, distribution, amendment history, sections, finding table, closure block | Reference copy in `templates/word` |
| D11 | Local LLM | Ollama, a 7–8B instruct model (e.g. Llama 3.1 8B or Qwen2.5 7B, Q4), temperature 0.1, endpoint restricted to 127.0.0.1 | Runs on a 16 GB RAM laptop; a GPU is optional. Disabled until installed, so the default is rule-based |
| D12 | OCR | Tesseract (local), only if installed | Without it, scanned pages are reported as "not verified". They are never silently skipped |
| D13 | Uploaded files | Copied to `uploaded_documents/<session>/`, SHA-256 recorded, opened read-only; macros and embedded objects never executed | Treated as untrusted input |
| D14 | DAL applicability | Taken from the DO-178C / DO-178B Annex A tables, encoded per objective with independence flags in `standards/` | Applicability is not invented; it is filled from the standard and checked by a lead |
| D15 | DAL E | No DO-178B/C compliance findings; the review is limited to document control and plan consistency | As per requirement |
| D16 | Supplements | DO-330/331/332/333 apply only to DO-178C, and only when the PSAC claims them | Never applied to DO-178B |
| D17 | Distribution | PyInstaller one-folder build, Windows 10/11 x64 | Data folders stay next to the exe |

## 5. Checklist model

Each built-in checklist follows the Unical sheet structure. That way the tool's
output looks the same as the reviews already issued to Aeron (PSAC, SDP, SVP,
SCMP and SQAP reviews of the ALD-ASM40 and GLO-MSU11-D projects).

| Sheet | Content |
|---|---|
| A | Document control and format |
| B | Template compliance (CEMILAC / RCMA, or the authority template) |
| C | DO-178B / DO-178C objectives and Section 11 content |
| D | Traceability and consistency with the other plans |
| E | Clarity and auditability |
| F | Engineering content depth |

Each checklist item stores these fields:
- Checklist ID, standard, DAL applicability, SOI, document type
- Section number and title
- Review question, expected evidence, reference
- Applicability (Mandatory / Conditional + condition / Not Applicable)
- Review guidance
- Sort order

### 5.1 Planned improvements to the existing Unical checklists (Phase 4)

The existing checklists are a strong base. They have about 600 checks across the
five plans: PSAC 198, SDP 131, SVP 102, SCMP 80, SQAP 87. The points below are
what the tool needs from them, and what certification approval needs from them.

| # | Gap in current checklists | Improvement |
|---|---|---|
| 1 | No *Expected evidence* and *Review guidance* columns | Add both to every check. The tool can then explain a verdict, and a new reviewer gets the same result |
| 2 | DAL applicability is mostly "All" | Derive it from the Annex A tables per objective, including the independence flag for Level A/B |
| 3 | Only DO-178C versions exist | Create DO-178B variants. Section 11 numbering differs, there are no supplements, there is no PDI (DO-178C §11.22), and tool qualification follows DO-178B §12.2 |
| 4 | Only planning documents (SOI-1) are covered | Add the SRS / SDS / SCS standards, and the IVVP |
| 5 | SOI-2 to SOI-4 checklists are missing | Add these checklists:<br>• SRD, SDD, source code (CSCR) and trace data<br>• SVCP, SVR, structural coverage (incl. MC/DC), DC/CC, robustness, PR records<br>• SCI, SECI, SAS, SCMR / SQAR, IV&V final report |
| 6 | "Not Applicable" is accepted without a reason | Make an N/A rationale mandatory. The authority asks for it |
| 7 | Closure re-review is done by hand | Add an R2 closure-verification sheet (round-2 status per finding), as already used for the ASM round-2 reviews |
| 8 | No overall readiness statement | Add a per-SOI readiness assessment. It lists the open Majors that block submission, the Minors to fix in the next issue, and a clear recommendation, so the authority sees a decision-ready summary |

None of these changes alters the wording of existing checks. User-uploaded
checklists keep their original wording, as required.

## 6. AI guard-rails (Phase 6)

- Only local inference is used. If the model is unavailable, the tool says "AI-assisted analysis unavailable" and continues in rule-based mode. It never switches to an online service.
- The prompt contains only the retrieved section text and the checklist item. The model must quote, and any quote not found in the source is rejected.
- The model never claims an objective is met without a quote, never invents page numbers or references, and never makes a certification decision.
- AI findings are tagged `origin = AI` and need human approval.

## 7. Phase plan

| Phase | Scope | Exit check |
|---|---|---|
| 1 | Foundation: login, dashboard, SQLite, logging, packaging scripts | 26 tests pass; app runs on Windows (**this release**) |
| 2 | Workflow: standard → DAL → SOI → document type → upload → file validation | AC-04 to AC-07 |
| 3 | Parsing, scanned-PDF detection, OCR, content-based classification | AC-08, AC-09 |
| 4 | Checklist engine: import of the Unical checklists, improvements in 5.1, user / combined checklists, checklist manager | AC-10, AC-11 |
| 5 | Review engine: structure, section, technical and cross-document checks; findings; severity | AC-12 to AC-14 |
| 6 | Local AI agent with rule-based fallback and the human approval workflow | AC-21, AC-22 |
| 7 | Excel and Word reports in the Unical templates; results page; history | AC-15 to AC-19 |
| 8 | Full test, offline test, performance, PyInstaller executable | AC-01, AC-20 |

## 8. Open points for Unical

1. **Local LLM machine:** confirm the reviewers' laptop specification (RAM / GPU). This fixes the model size.
2. **Built-in checklists:** confirm the Unical checklist workbooks to import first. The proposal is the five MSU plan checklists, then the ASM ones.
3. **Template variants:** confirm whether other authorities' templates (FAA / EASA style) are needed alongside CEMILAC / RCMA.
4. **DO-178B Annex A source:** the DO-178C standard is available. A copy of DO-178B is needed to build its objective tables without guessing.
5. **Finding approval:** confirm who approves findings (IV&V Lead only, or any reviewer).
