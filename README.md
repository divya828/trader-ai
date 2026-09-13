# trader-ai

Local-only personal investment ledger and deterministic analytics for Indian
mutual funds and stocks. **Advisory only — nothing here places trades.**

## v0.1 scope

- Parse an eCAS PDF (CAMS/KFintech/NSDL/CDSL) into a normalized SQLite ledger
- XIRR per scheme and portfolio-level
- Current allocation vs. target, by asset class
- FIFO tax lots with LTCG/STCG classification (holding period only)

No LLM, no orchestration graph, no optimizer, no UI, no broker API.

## Guarantees

- **Fully local.** Nothing reaches the network; `tests/test_layering.py`
  enforces that no network or model client library is imported.
- **No execution.** There is no order-placement code path.
- **Deterministic math.** Every figure comes from tested Python, never a model.
- **PAN is never stored in full** — only a masked form (`ABCPX1234Z` is stored
  as `ABCXXX234Z`).
- **Layer isolation.** `analytics/` never imports `ingest/` or `casparser`.
  That boundary is what makes a future redaction gate insertable in exactly
  one place, and it is asserted mechanically rather than by convention.

## Market data (v0.2a)

`marketdata/` fetches public AMFI reference data — the whole-universe NAV file
and NAV history — and caches it locally.

**The privacy invariant:** no outbound request may carry a portfolio-derived
parameter. Client functions accept dates only, never an ISIN, scheme name,
folio, or amount. AMFI publishes whole-universe files, so the natural access
pattern is already "download everything, filter locally"; scoping to your
holdings happens after download, on your machine. Downloading the same public
file every Indian investor downloads reveals nothing about your portfolio.

This is enforced three ways, all tested: `test_client_privacy.py` asserts no
public client function accepts a non-date parameter (and none accepts
`**kwargs` to smuggle one past); `test_layering.py` asserts only
`amfi_client.py` may perform HTTP at all; and a source scan rejects any
portfolio term near URL construction. Each guard was verified to fail on an
injected violation.

TLS certificate verification is on and asserted by test. It is never disabled
to work around a connection error — an unverified connection would let a
network attacker feed the tool fabricated NAV data.

    from trader_ai.db.connection import apply_schema_v02, connect
    from trader_ai.marketdata.refresh import refresh_universe
    from trader_ai.marketdata.backfill import backfill_asset_classes

    con = connect("data/ledger.db")
    apply_schema_v02(con)          # first v0.2 run only
    refresh_universe(con)          # downloads ~1.5MB
    backfill_asset_classes(con)    # fills v0.1's UNCLASSIFIED schemes

NAV rows are kept only for ISINs your ledger holds, so cache size tracks your
portfolio rather than the ~14,000-scheme universe.

### Plan coverage

AMFI populates the Direct/Regular `Plan` column for about 60% of rows. The
missing values have three distinct causes and are recorded as three distinct
values, because collapsing them would misrepresent the data:

- `NOT_APPLICABLE` — ETFs and close-ended schemes, where no Direct/Regular
  distinction exists.
- `UNKNOWN` — open-ended non-ETF schemes where the source simply omits it
  (~10% of the addressable universe).
- `DIRECT` / `REGULAR` — populated.

Cost-drag metrics in v0.2b will report the share of portfolio value they
covered, never a bare figure.

### Asset-class coverage

SEBI category → asset class covers **84.5%** of rows in the live file.
Everything unmapped is genuinely ambiguous — fund-of-funds, untyped ETFs,
generic index funds, solution-oriented and lifecycle funds — and stays
`UNCLASSIFIED` rather than being guessed, because a wrong asset class corrupts
allocation drift silently while an unclassified one is visible.

## Setup

    uv venv --python 3.12
    uv pip install -e ".[dev]"
    uv run pytest

Live endpoint checks are skipped by default. To verify AMFI's format has not
changed (downloads ~4MB):

    TRADER_AI_LIVE=1 uv run pytest tests/marketdata/test_live_endpoints.py -v

## Importing a statement

    from trader_ai.db.connection import connect, apply_schema
    from trader_ai.ingest.importer import import_pdf

    con = connect("data/ledger.db")
    apply_schema(con)          # first run only
    import_pdf(con, "data/raw/statement.pdf", password="YOURPAN")

Re-importing the same statement is safe: transactions are deduplicated by a
stable content hash, and folios/schemes/securities by partial unique indexes
that handle NULL ISINs correctly.

## Reading the numbers

    from trader_ai.analytics.portfolio import (
        portfolio_xirr, scheme_xirr, latest_values_by_asset_class,
    )
    from trader_ai.analytics.allocation import compute_drift

    portfolio_xirr(con)                      # None if not computable
    latest_values_by_asset_class(con)        # {"EQUITY": 250000.0, ...}
    compute_drift(latest_values_by_asset_class(con), {"EQUITY": 0.7, "DEBT": 0.3})

## Known limits

Stock holdings come from an eCAS as a point-in-time snapshot with no
transaction history. Stock **XIRR and tax lots are therefore not computable**
in v0.1 and are scoped to mutual funds. Stocks do count toward allocation.

Scheme asset classes default to `UNCLASSIFIED` — casparser reports a scheme
type but not a clean asset-class tag. Allocation surfaces unclassified value
separately rather than hiding it in a denominator; classifying schemes is a
deliberate follow-up step.

Tax-lot output classifies gains as LTCG/STCG by holding period only. It
computes no tax amount, applies no exemption slab, and performs no
grandfathering.

The test suite uses synthetic fixtures built from casparser's own models. The
mapping from a **real** eCAS PDF has not been exercised end to end — run
`import_pdf` against an actual statement before trusting the numbers.

Data lives in `data/`, which is gitignored in full.
