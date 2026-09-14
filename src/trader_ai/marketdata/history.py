"""Weekly NAV history backfill.

v0.2a built fetch_history, missing_ranges and md_nav but never connected them.
This does, and picks the sampling strategy.

Why weekly, whole-universe: the history endpoint returns every scheme per
request (~1.2MB/day), so daily backfill costs ~2.1GB over five years. Weekly
sampling costs ~290MB and is ample for the metrics that consume it -- CAGR,
time-weighted return and rolling returns do not improve with daily points.
AMFI's mf=<amc> parameter would cut this 23x but reveals which fund houses the
user invests with, which is a portfolio-derived parameter and therefore out of
bounds. That constraint is the point, not an oversight.

Why Wednesday: weekends return ~600 rows instead of ~8,700. Mid-week avoids
both weekends and most holiday-adjacent Mondays and Fridays.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from trader_ai.marketdata import amfi_client, cache
from trader_ai.marketdata.layouts import HISTORY
from trader_ai.marketdata.parser import parse

# A full trading day returns ~8,700 rows; a weekend ~600. A reduced trading
# day (2026-08-26) returned 5,761, so the threshold must not reject those.
SPARSE_ROW_THRESHOLD = 3000

_WEDNESDAY = 2
_ONE_DAY = timedelta(days=1)


@dataclass(frozen=True)
class BackfillResult:
    days_fetched: int
    days_skipped_cached: int
    days_sparse: int
    nav_rows_ingested: int


def weekly_sample_dates(start: date, end: date) -> list[date]:
    """Wednesdays between start and end inclusive, seven days apart.

    If start is already a Wednesday it is used as-is, so callers can pin an
    exact cadence; otherwise the first Wednesday on or after start begins it.
    """
    if end < start:
        return []
    first = start
    while first.weekday() != _WEDNESDAY and first <= end:
        first += _ONE_DAY
    days: list[date] = []
    cursor = first
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=7)
    return days


def backfill_history(
    con: sqlite3.Connection,
    start: date,
    end: date,
    fetch: Callable[[date, date], str] | None = None,
    min_rows: int = SPARSE_ROW_THRESHOLD,
) -> BackfillResult:
    """Cache weekly NAV points for held ISINs between start and end.

    min_rows exists so tests can drive the whole path with a compact fixture
    instead of fabricating thousands of rows. It defaults to the real
    threshold, and a test asserts that default, so production keeps weekend
    rejection regardless of what any caller passes.
    """
    fetch = fetch or (lambda s, e: amfi_client.fetch_history(s, e))
    keep = cache.ledger_isins(con)

    fetched = skipped = sparse = ingested = 0
    for day in weekly_sample_dates(start, end):
        if not cache.missing_ranges(con, day, day):
            skipped += 1
            continue

        parsed = parse(fetch(day, day), HISTORY)
        if len(parsed.rows) < min_rows:
            # A non-trading day. Do not log it as cached: a later run should
            # be free to try again rather than treat the gap as filled.
            sparse += 1
            continue

        day_ingested, day_skipped = cache.upsert_nav_rows(con, parsed.rows, keep)
        cache.log_fetch(con, "history", day, day, day_ingested, day_skipped)
        fetched += 1
        ingested += day_ingested

    return BackfillResult(
        days_fetched=fetched,
        days_skipped_cached=skipped,
        days_sparse=sparse,
        nav_rows_ingested=ingested,
    )
