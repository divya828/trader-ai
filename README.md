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

## Setup

    uv venv --python 3.12
    uv pip install -e ".[dev]"
    uv run pytest

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
