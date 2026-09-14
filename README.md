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

## Metrics (v0.2b)

Five deterministic metrics derived from the retail investment literature, each
returning either a value or an explicit reason it could not be computed. No LLM
is involved: these are formulas from named sources, not judgments.

| Metric | Source | Needs NAV history |
|---|---|---|
| Behaviour gap | Morningstar, *Mind the Gap* | yes |
| Cost drag | Bogle; SEBI direct-plan regulation | yes |
| Diversification | SEBI categories; Herfindahl | no |
| Consistency | rolling-return methodology | yes |
| Rebalancing | Daryanani 5/25 | no |

**Unavailability is explicit.** Every metric returns a `Measurement` that is
either a value or a reason — never a bare `None` that a caller might read as
zero. An unmeasured dimension must never look like a clean one.

**v0.1 math is reused, not reimplemented.** Behaviour gap uses v0.1's `xirr`;
rebalancing uses its FIFO lot matcher; consistency uses the shared `cagr`. A
layering test asserts this, because a second implementation would drift from
the tested one.

### NAV history

Metrics that need history require a backfill, which samples **weekly**:

    from datetime import date
    from trader_ai.marketdata.history import backfill_history

    backfill_history(con, date(2021, 1, 1), date.today())

Weekly, whole-universe sampling costs roughly 290MB over five years. Daily
would cost ~2.1GB, because AMFI's history endpoint returns every scheme per
request. AMFI's `mf=<amc>` parameter would cut this 23×, but it reveals which
fund houses you invest with — a portfolio-derived parameter, and therefore out
of bounds. The constraint is deliberate.

Weekends return ~600 rows instead of ~8,700, so sampling targets Wednesdays and
records sparse days *without* caching them — a cached weekend would look like a
filled gap and never be retried.

### Cost-drag coverage

AMFI publishes no machine-readable TER, so drag is measured from the spread
between a scheme's Direct and Regular NAV series — which captures trail
commission as actually charged, and is therefore a better number than stated
TER.

Every result reports the share of portfolio value it covered, with a distinct
reason for each exclusion, because each implies a different remedy:

| Reason | Meaning | Remedy |
|---|---|---|
| `NOT_APPLICABLE` | ETF or close-ended; no plan distinction exists | none needed |
| `UNKNOWN` | open-ended, but AMFI omits the plan | better source data |
| `NO_SIBLING` | Regular plan whose Direct twin is not in the universe | wider universe |
| `NO_MARKET_DATA` | the holding's ISIN matched no AMFI scheme | refresh |
| `NO_NAV_HISTORY` | a pair exists but one side lacks two NAV points | backfill |

A portfolio figure is never shown without its coverage share, and covered plus
uncovered always equals total portfolio value — asserted by test, so holdings
cannot vanish from the report silently.

## Findings and health score (v0.2c)

Nine rules turn the metrics into typed, cited findings, aggregated into five
dimension scores. Still no LLM: these are thresholds from named sources.

**Findings are PII-free by construction.** A `Subject` carries a scheme name or
ISIN and a portfolio *ratio* — never a folio number, a PAN, or a rupee amount,
enforced at construction time. Both the raw PAN shape and the masked form this
project actually stores are rejected. A future redaction gate will therefore
have nothing to strip.

**Every finding cites its source and carries its numbers.** `metrics` holds
every figure behind the finding, so an explanatory tier can explain rather than
recalculate.

**An unmeasured dimension scores `None`, never 100.** On a portfolio with no
disposals and no IDCW holdings, neither tax rule can fire — so TAX_EFFICIENCY
reports as unmeasured with a reason, and the overall score says how many
dimensions it covered. On the real portfolio this is the difference between an
honest 81.3 and a flattering 88.8.

**A dimension can be only partly evaluated.** ALLOCATION has two rules; with no
target configured, one runs and one cannot. `fully_evaluated` exposes that, so
a score of 100 built from half a dimension does not read as "allocation is
fine".

**Two rules deliberately stay silent rather than guess:**

- `behavior.timing_gap` requires at least one disposal. A negative behaviour
  gap is the normal arithmetic of accumulating into a rising market — the real
  portfolio shows −8.2 points a year across 402 purchases and zero
  redemptions. Firing on that alone would manufacture a finding from an
  artifact.
- `allocation.band_breach` requires a configured target. Assuming a
  conventional split would present a default as a recommendation.

<!-- -->

    from trader_ai.rules.context import build_context
    from trader_ai.rules.registry import evaluate
    from trader_ai.rules.score import overall_score, score_dimensions
    from trader_ai.rules.store import save_findings, save_scores

    ctx = build_context(con, metrics={"cost_drag": ..., "behavior_gaps": ...})
    findings, evaluable, coverage = evaluate(ctx)
    scores = score_dimensions(findings, evaluable, coverage)
    overall = overall_score(scores)

    save_findings(con, "run-1", findings)
    save_scores(con, list(scores.values()))

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
