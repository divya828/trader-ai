-- v0.2c additive migration: persisted findings and score reasons.
-- Applied after schema_v02.sql. Never modifies v0.1 or v0.2a tables.

-- Why a NULL score needs a reason: a dimension with no evidence must be
-- reported as unmeasured, not as clean. Measured on a real portfolio, the
-- TAX_EFFICIENCY dimension had zero disposals and zero IDCW holdings, so it
-- cannot be scored at all -- and a bare NULL would not say why.
ALTER TABLE health_scores ADD COLUMN unscored_reason TEXT;

CREATE TABLE findings (
    finding_id   INTEGER PRIMARY KEY,
    run_id       TEXT NOT NULL,          -- groups one evaluation pass
    rule_id      TEXT NOT NULL,          -- e.g. "cost.regular_plan_drag"
    severity     TEXT NOT NULL CHECK (severity IN ('INFO','LOW','MEDIUM','HIGH')),
    title        TEXT NOT NULL,
    citation_key TEXT NOT NULL,
    computed_at  TEXT NOT NULL
);
CREATE INDEX idx_findings_run ON findings(run_id);
CREATE INDEX idx_findings_rule ON findings(rule_id);

-- Subjects carry scheme identity and portfolio share only. Never a folio
-- number, never a PAN, never an absolute amount.
CREATE TABLE finding_subjects (
    subject_id INTEGER PRIMARY KEY,
    finding_id INTEGER NOT NULL REFERENCES findings(finding_id),
    kind       TEXT NOT NULL CHECK (kind IN ('SCHEME','SECURITY','ASSET_CLASS','PORTFOLIO')),
    ref        TEXT NOT NULL,
    weight     REAL CHECK (weight IS NULL OR (weight >= 0 AND weight <= 1))
);
CREATE INDEX idx_finding_subjects ON finding_subjects(finding_id);

-- Every number behind a finding, so v0.3 explains rather than recalculates.
CREATE TABLE finding_metrics (
    finding_id INTEGER NOT NULL REFERENCES findings(finding_id),
    name       TEXT NOT NULL,
    value      REAL NOT NULL,
    PRIMARY KEY (finding_id, name)
);
