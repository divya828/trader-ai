-- v0.2 additive migration. Applied after schema.sql; never modifies v0.1 tables.

-- Scheme master, refreshed from the NAV universe file.
CREATE TABLE md_schemes (
    amfi_code       TEXT PRIMARY KEY,
    isin_growth     TEXT,
    isin_reinvest   TEXT,
    scheme_name     TEXT NOT NULL,
    amc             TEXT,
    sebi_category   TEXT,                  -- e.g. "Debt Scheme - Gilt Fund"
    plan            TEXT NOT NULL DEFAULT 'UNKNOWN'
                        CHECK (plan IN ('DIRECT','REGULAR','NOT_APPLICABLE','UNKNOWN')),
    scheme_structure TEXT NOT NULL DEFAULT 'OPEN'
                        CHECK (scheme_structure IN ('OPEN','CLOSED','INTERVAL')),
    is_etf          INTEGER NOT NULL DEFAULT 0,
    option          TEXT,                  -- Growth / IDCW
    asset_class     TEXT NOT NULL DEFAULT 'UNCLASSIFIED'
                        CHECK (asset_class IN ('EQUITY','DEBT','HYBRID','GOLD','CASH','UNCLASSIFIED')),
    last_seen       TEXT NOT NULL
);
CREATE INDEX idx_md_schemes_isin ON md_schemes(isin_growth);
CREATE INDEX idx_md_schemes_category ON md_schemes(sebi_category);

-- NAV time series. Filtered on write to ISINs present in the ledger,
-- so DB size is proportional to the portfolio, not the fund universe.
CREATE TABLE md_nav (
    amfi_code   TEXT NOT NULL,
    nav_date    TEXT NOT NULL,             -- ISO 8601
    nav         REAL NOT NULL,
    PRIMARY KEY (amfi_code, nav_date)
);

-- Which date ranges are already cached; makes backfill incremental.
CREATE TABLE md_fetch_log (
    fetch_id        INTEGER PRIMARY KEY,
    endpoint        TEXT NOT NULL,
    range_start     TEXT,
    range_end       TEXT,
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
    rows_ingested   INTEGER NOT NULL DEFAULT 0,
    rows_skipped    INTEGER NOT NULL DEFAULT 0
);

-- SEBI category → v0.1 asset_class mapping. Static, seeded, user-editable.
CREATE TABLE md_category_asset_class (
    sebi_category   TEXT PRIMARY KEY,
    asset_class     TEXT NOT NULL
                        CHECK (asset_class IN ('EQUITY','DEBT','HYBRID','GOLD','CASH'))
);

-- Health score history, one row per dimension per run.
CREATE TABLE health_scores (
    score_id    INTEGER PRIMARY KEY,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    dimension   TEXT NOT NULL CHECK (dimension IN
                    ('COST','DIVERSIFICATION','BEHAVIOR','ALLOCATION','TAX_EFFICIENCY')),
    score       REAL CHECK (score IS NULL OR (score >= 0 AND score <= 100)),
                                -- NULL = unmeasured (no data), distinct from 0
    finding_count INTEGER NOT NULL DEFAULT 0
);
