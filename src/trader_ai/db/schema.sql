-- Folios: one row per (AMC folio number) as reported in the CAS.
-- Mutual fund transactions/holdings nest under folios.
CREATE TABLE folios (
    folio_id        INTEGER PRIMARY KEY,
    folio_number    TEXT NOT NULL,
    amc             TEXT NOT NULL,          -- e.g. "HDFC Mutual Fund"
    pan_masked      TEXT,                   -- masked (e.g. "ABCXXX234Z"), never full PAN
    UNIQUE (folio_number, amc)
);

-- Schemes: one row per mutual fund scheme within a folio.
CREATE TABLE schemes (
    scheme_id       INTEGER PRIMARY KEY,
    folio_id        INTEGER NOT NULL REFERENCES folios(folio_id),
    amfi_code       TEXT,                   -- AMFI scheme code, nullable if unmatched
    isin            TEXT,
    scheme_name     TEXT NOT NULL,
    asset_class     TEXT NOT NULL DEFAULT 'UNCLASSIFIED'
                        CHECK (asset_class IN ('EQUITY','DEBT','HYBRID','GOLD','CASH','UNCLASSIFIED')),
    UNIQUE (folio_id, scheme_name, isin)
);

-- Securities: one row per stock (ISIN), held in demat — separate from MF schemes
-- because casparser reports these as holdings, not scheme transaction streams.
CREATE TABLE securities (
    security_id     INTEGER PRIMARY KEY,
    isin            TEXT NOT NULL UNIQUE,
    symbol          TEXT,
    name            TEXT NOT NULL,
    exchange        TEXT,                   -- NSE / BSE
    asset_class     TEXT NOT NULL DEFAULT 'EQUITY'
                        CHECK (asset_class IN ('EQUITY','UNCLASSIFIED'))
);

-- Demat accounts: analogous to folios, for stock holdings.
CREATE TABLE demat_accounts (
    demat_account_id INTEGER PRIMARY KEY,
    dp_id           TEXT NOT NULL,
    client_id       TEXT NOT NULL,
    depository      TEXT NOT NULL CHECK (depository IN ('CDSL','NSDL')),
    UNIQUE (dp_id, client_id)
);

-- Unified transaction ledger for BOTH mutual fund and stock transactions.
-- One table keeps XIRR/lot logic asset-type-agnostic (same shape, different FK populated).
CREATE TABLE transactions (
    transaction_id        INTEGER PRIMARY KEY,
    scheme_id             INTEGER REFERENCES schemes(scheme_id),
    security_id           INTEGER REFERENCES securities(security_id),
    demat_account_id       INTEGER REFERENCES demat_accounts(demat_account_id),
    txn_date               TEXT NOT NULL,      -- ISO 8601 'YYYY-MM-DD'
    -- Mirrors casparser.enums.TransactionType exactly (v1.4.1), so ingestion
    -- never has to lossily remap and never trips the CHECK on real data.
    txn_type                TEXT NOT NULL CHECK (txn_type IN (
                                'PURCHASE','PURCHASE_SIP','REDEMPTION',
                                'DIVIDEND_PAYOUT','DIVIDEND_REINVEST',
                                'SWITCH_IN','SWITCH_IN_MERGER',
                                'SWITCH_OUT','SWITCH_OUT_MERGER',
                                'STT_TAX','STAMP_DUTY_TAX','TDS_TAX',
                                'SEGREGATION','GIFT_IN','GIFT_OUT',
                                'MISC','UNKNOWN','REVERSAL'
                            )),
    units                    REAL,             -- signed: +buy, -sell (NULL for pure cash entries like STT)
    price                     REAL,             -- NAV for MF, trade price for stock
    amount                    REAL NOT NULL,    -- signed cashflow, always populated (used by XIRR)
    source_row_hash            TEXT NOT NULL UNIQUE,  -- hash of raw source fields; enforces idempotent re-import
    CHECK (
        (scheme_id IS NOT NULL AND security_id IS NULL) OR
        (scheme_id IS NULL AND security_id IS NOT NULL)
    )
);

CREATE INDEX idx_transactions_scheme ON transactions(scheme_id, txn_date);
CREATE INDEX idx_transactions_security ON transactions(security_id, txn_date);

-- Cost basis lots — populated/refreshed by the FIFO tax-lot tool, not by ingestion.
-- Kept as a derived table (not raw ledger) so it can be recomputed deterministically
-- from transactions at any time.
CREATE TABLE tax_lots (
    lot_id                 INTEGER PRIMARY KEY,
    scheme_id              INTEGER REFERENCES schemes(scheme_id),
    security_id            INTEGER REFERENCES securities(security_id),
    open_transaction_id    INTEGER NOT NULL REFERENCES transactions(transaction_id),
    acquired_date           TEXT NOT NULL,
    units_remaining          REAL NOT NULL,
    cost_per_unit             REAL NOT NULL,
    CHECK (
        (scheme_id IS NOT NULL AND security_id IS NULL) OR
        (scheme_id IS NULL AND security_id IS NOT NULL)
    )
);

-- Lot consumption record — which redemption consumed which lot, how many units,
-- and the resulting gain classification. This is the FIFO matching's audit trail.
CREATE TABLE lot_disposals (
    disposal_id             INTEGER PRIMARY KEY,
    lot_id                  INTEGER NOT NULL REFERENCES tax_lots(lot_id),
    close_transaction_id    INTEGER NOT NULL REFERENCES transactions(transaction_id),
    disposed_date            TEXT NOT NULL,
    units_disposed            REAL NOT NULL,
    cost_basis                 REAL NOT NULL,   -- units_disposed * lot.cost_per_unit
    proceeds                    REAL NOT NULL,
    gain                          REAL NOT NULL,
    holding_period_days             INTEGER NOT NULL,
    classification                    TEXT NOT NULL CHECK (classification IN ('STCG','LTCG'))
);

-- Point-in-time holdings snapshot, per import run.
-- This is how stocks get valued (they have no transaction stream), and it
-- also captures each scheme's reported NAV/value so allocation needs no
-- external price feed in v0.1.
CREATE TABLE holdings_snapshot (
    snapshot_id        INTEGER PRIMARY KEY,
    import_run_id      INTEGER NOT NULL REFERENCES import_runs(import_run_id),
    scheme_id          INTEGER REFERENCES schemes(scheme_id),
    security_id        INTEGER REFERENCES securities(security_id),
    as_of_date          TEXT NOT NULL,     -- ISO 8601
    units                REAL NOT NULL,    -- units (MF) or num_shares (stock)
    price                 REAL NOT NULL,   -- NAV (MF) or market price (stock)
    value                  REAL NOT NULL,
    cost                    REAL,          -- reported cost basis where available
    CHECK (
        (scheme_id IS NOT NULL AND security_id IS NULL) OR
        (scheme_id IS NULL AND security_id IS NOT NULL)
    )
);

-- NOTE: a table-level UNIQUE(import_run_id, scheme_id, security_id) does NOT
-- work here: SQL treats NULL as distinct from NULL, so rows with a NULL
-- security_id would never collide and re-imports would silently duplicate
-- holdings. Two partial unique indexes are required instead.
CREATE UNIQUE INDEX idx_holdings_snapshot_scheme_uniq
    ON holdings_snapshot(import_run_id, scheme_id) WHERE scheme_id IS NOT NULL;
CREATE UNIQUE INDEX idx_holdings_snapshot_security_uniq
    ON holdings_snapshot(import_run_id, security_id) WHERE security_id IS NOT NULL;

CREATE INDEX idx_holdings_snapshot_run ON holdings_snapshot(import_run_id);

-- Target allocation, specified per asset class.
CREATE TABLE target_allocation (
    asset_class      TEXT PRIMARY KEY CHECK (asset_class IN ('EQUITY','DEBT','HYBRID','GOLD','CASH')),
    target_weight     REAL NOT NULL CHECK (target_weight >= 0 AND target_weight <= 1)
);

-- Ingestion run log — tracks each casparser import for traceability/idempotency debugging.
CREATE TABLE import_runs (
    import_run_id                INTEGER PRIMARY KEY,
    source_file                    TEXT NOT NULL,
    imported_at                      TEXT NOT NULL DEFAULT (datetime('now')),
    cas_statement_period_start         TEXT,
    cas_statement_period_end             TEXT,
    rows_inserted                          INTEGER NOT NULL DEFAULT 0,
    rows_skipped_duplicate                   INTEGER NOT NULL DEFAULT 0
);
