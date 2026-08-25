-- BUILD_PLAN L9: SQLite, append-only audit_log enforced by TRIGGER, not convention.

CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,
    seed            TEXT NOT NULL,
    run_date        TEXT NOT NULL,
    opening_count   INTEGER,
    opening_value   TEXT,   -- Decimal stored as text, never float
    new_count       INTEGER,
    new_value       TEXT,
    resolved_count  INTEGER,
    resolved_value  TEXT,
    written_off_count INTEGER,
    written_off_value TEXT,
    closing_count   INTEGER,
    closing_value   TEXT,
    ties            INTEGER NOT NULL,  -- 0/1, set by l5_rollforward
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS breaks (
    break_id        TEXT PRIMARY KEY,
    seed            TEXT NOT NULL,
    first_seen_run  TEXT NOT NULL,
    last_updated_run TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ("OPEN","RESOLVED","WRITTEN_OFF","ESCALATED")),
    merchant_id     TEXT NOT NULL,
    side            TEXT NOT NULL CHECK (side IN ("BANK_ONLY","LEDGER_ONLY","SETTLEMENT_ONLY","AMOUNT_MISMATCH")),
    amount_delta    TEXT NOT NULL,
    age_days        INTEGER NOT NULL DEFAULT 0,
    ageing_bucket   TEXT,
    verdict         TEXT,
    confidence      REAL,
    hypothesis      TEXT,
    evidence_json   TEXT,
    residual_unexplained TEXT,
    tools_called_json TEXT,
    verifier_decision TEXT,
    verifier_reason TEXT,
    verifier_model  TEXT,
    ground_truth_archetype TEXT,   -- NEVER read by agent code, join in scoring only
    proposed_je_json TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    break_id        TEXT NOT NULL,
    who             TEXT NOT NULL,   -- e.g. "l3_investigator", "l4_verifier", "human:approve_je"
    what             TEXT NOT NULL,
    prior_value      TEXT,
    new_value        TEXT,
    at               TEXT NOT NULL
);

-- Append-only: reject any attempt to UPDATE or DELETE an audit_log row.
CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, "audit_log is append-only (BUILD_PLAN L9)");
END;

CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, "audit_log is append-only (BUILD_PLAN L9)");
END;
