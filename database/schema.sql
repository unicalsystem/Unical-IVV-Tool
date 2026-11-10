-- Unical DO-178B / DO-178C IV&V Review Tool - local SQLite schema
-- Schema version 2. The full data model is created in Phase 1 so later phases
-- add behaviour, not tables. Review records are never overwritten: a re-review
-- of the same document creates a new review_session with review_version + 1.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_info (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    username         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    full_name        TEXT    NOT NULL DEFAULT '',
    role             TEXT    NOT NULL DEFAULT 'reviewer'
                     CHECK (role IN ('admin', 'lead', 'reviewer', 'viewer')),
    password_hash    TEXT    NOT NULL,          -- PBKDF2-HMAC-SHA256, hex
    password_salt    TEXT    NOT NULL,          -- random 16 bytes, hex
    hash_iterations  INTEGER NOT NULL,
    is_active        INTEGER NOT NULL DEFAULT 1,
    failed_attempts  INTEGER NOT NULL DEFAULT 0,
    locked_until     TEXT,                      -- ISO timestamp (UTC)
    created_at       TEXT    NOT NULL,
    last_login_at    TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT NOT NULL UNIQUE,
    customer             TEXT DEFAULT '',
    system_lru           TEXT DEFAULT '',
    part_number          TEXT DEFAULT '',
    standard             TEXT CHECK (standard IN ('DO-178B', 'DO-178C')),
    dal                  TEXT CHECK (dal IN ('A', 'B', 'C', 'D', 'E')),
    certification_basis  TEXT DEFAULT '',        -- e.g. CEMILAC / RCMA, EASA, FAA
    created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER REFERENCES projects(id),
    standard        TEXT NOT NULL CHECK (standard IN ('DO-178B', 'DO-178C')),
    dal             TEXT NOT NULL CHECK (dal IN ('A', 'B', 'C', 'D', 'E')),
    soi_stage       TEXT NOT NULL CHECK (soi_stage IN ('SOI-1', 'SOI-2', 'SOI-3', 'SOI-4')),
    document_type   TEXT NOT NULL,
    review_round    INTEGER NOT NULL DEFAULT 1,  -- 1st review, re-review (closure) ...
    review_version  INTEGER NOT NULL DEFAULT 1,  -- increments on every re-run, never overwritten
    status          TEXT NOT NULL DEFAULT 'Draft'
                    CHECK (status IN ('Draft', 'In Progress', 'Pending Manual Review', 'Completed', 'Cancelled')),
    analysis_mode   TEXT NOT NULL DEFAULT 'Rule-based' CHECK (analysis_mode IN ('Rule-based', 'AI-assisted')),
    checklist_mode  TEXT CHECK (checklist_mode IN ('Built-in', 'User', 'Combined')),
    started_by      TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    notes           TEXT DEFAULT '',
    checklist_id    INTEGER REFERENCES checklists(id),
    recommendation  TEXT DEFAULT '',
    results_json    TEXT DEFAULT '',   -- structure review, consistency results, engine notes
    report_doc_no   TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES review_sessions(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'primary' CHECK (role IN ('primary', 'companion', 'checklist')),
    file_name       TEXT NOT NULL,
    stored_path     TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    file_size       INTEGER NOT NULL,
    doc_title       TEXT DEFAULT '',
    doc_number      TEXT DEFAULT '',
    doc_version     TEXT DEFAULT '',
    detected_type   TEXT DEFAULT '',
    type_confidence REAL,
    page_count      INTEGER,
    has_text        INTEGER,
    is_scanned      INTEGER,
    uploaded_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checklists (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    source         TEXT NOT NULL CHECK (source IN ('Built-in', 'User')),
    standard       TEXT NOT NULL CHECK (standard IN ('DO-178B', 'DO-178C')),
    soi_stage      TEXT NOT NULL,
    document_type  TEXT NOT NULL,
    version        TEXT NOT NULL DEFAULT '1.0',
    file_path      TEXT DEFAULT '',
    created_by     TEXT DEFAULT '',
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checklist_items (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    checklist_id       INTEGER NOT NULL REFERENCES checklists(id) ON DELETE CASCADE,
    checklist_ref      TEXT NOT NULL,        -- e.g. C-04 (Unical sheet letter + number)
    sheet              TEXT DEFAULT '',      -- A Document Control ... F Content Depth
    group_title        TEXT DEFAULT '',
    dal_applicability  TEXT NOT NULL DEFAULT 'All',   -- 'All' or e.g. 'A,B,C'
    section_number     TEXT DEFAULT '',
    section_title      TEXT DEFAULT '',
    review_question    TEXT NOT NULL,
    expected_evidence  TEXT DEFAULT '',
    reference          TEXT DEFAULT '',
    applicability      TEXT NOT NULL DEFAULT 'Mandatory'
                       CHECK (applicability IN ('Mandatory', 'Conditional', 'Not Applicable')),
    condition_text     TEXT DEFAULT '',      -- when Conditional: the condition
    review_guidance    TEXT DEFAULT '',
    rule               TEXT,
    sort_order         INTEGER NOT NULL DEFAULT 0,
    UNIQUE (checklist_id, checklist_ref)
);

CREATE TABLE IF NOT EXISTS findings (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         INTEGER NOT NULL REFERENCES review_sessions(id) ON DELETE CASCADE,
    finding_no         TEXT NOT NULL,        -- FIN-01 ...
    document_id        INTEGER REFERENCES documents(id),
    section_number     TEXT DEFAULT '',
    section_title      TEXT DEFAULT '',
    reference          TEXT DEFAULT '',
    observation        TEXT NOT NULL,
    recommendation     TEXT NOT NULL,
    severity           TEXT NOT NULL CHECK (severity IN ('Major', 'Minor', 'Observation')),
    severity_rationale TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'Open'
                       CHECK (status IN ('Open', 'Closed', 'Closed with comment', 'Not Closed',
                                         'Pending Clarification', 'Not Applicable', 'Withdrawn')),
    evidence           TEXT DEFAULT '',      -- quoted extract
    page_ref           TEXT DEFAULT '',
    reviewer_comment   TEXT DEFAULT '',
    origin             TEXT NOT NULL DEFAULT 'Manual' CHECK (origin IN ('Rule', 'AI', 'Manual')),
    approval_state     TEXT NOT NULL DEFAULT 'Draft'
                       CHECK (approval_state IN ('Draft', 'Approved', 'Rejected')),
    approved_by        TEXT,
    approved_at        TEXT,
    customer_response  TEXT DEFAULT '',
    UNIQUE (session_id, finding_no)
);

-- One finding may affect several checks; one check may raise several findings.
CREATE TABLE IF NOT EXISTS checklist_assessments (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         INTEGER NOT NULL REFERENCES review_sessions(id) ON DELETE CASCADE,
    checklist_item_id  INTEGER NOT NULL REFERENCES checklist_items(id),
    -- Unical verdict codes: C Compliant, PC Partially Compliant, NC Non-Compliant,
    -- NA Not Applicable, NR Not Verified (not reviewed / evidence not available),
    -- PCL Pending Clarification, PMR Pending Manual Review (AI could not conclude)
    verdict            TEXT NOT NULL DEFAULT 'NR'
                       CHECK (verdict IN ('C', 'PC', 'NC', 'NA', 'NR', 'PCL', 'PMR')),
    evidence_state     TEXT CHECK (evidence_state IN ('Present', 'Present-Incomplete', 'Present-Inconsistent',
                                                       'Not Present', 'Cannot Verify', 'Not Applicable')),
    observation        TEXT DEFAULT '',
    evidence           TEXT DEFAULT '',
    page_ref           TEXT DEFAULT '',
    recommendation     TEXT DEFAULT '',
    origin             TEXT NOT NULL DEFAULT 'Manual' CHECK (origin IN ('Rule', 'AI', 'Manual')),
    UNIQUE (session_id, checklist_item_id)
);

CREATE TABLE IF NOT EXISTS finding_checks (
    finding_id     INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    assessment_id  INTEGER NOT NULL REFERENCES checklist_assessments(id) ON DELETE CASCADE,
    PRIMARY KEY (finding_id, assessment_id)
);

CREATE TABLE IF NOT EXISTS reports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL REFERENCES review_sessions(id) ON DELETE CASCADE,
    report_type  TEXT NOT NULL CHECK (report_type IN ('Excel', 'Word')),
    file_path    TEXT NOT NULL,
    sha256       TEXT DEFAULT '',
    created_by   TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    username    TEXT NOT NULL DEFAULT '',
    event       TEXT NOT NULL,
    details     TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS ix_sessions_project ON review_sessions(project_id);
CREATE INDEX IF NOT EXISTS ix_sessions_filters ON review_sessions(soi_stage, dal, standard);
CREATE INDEX IF NOT EXISTS ix_findings_session ON findings(session_id);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_log(ts);
