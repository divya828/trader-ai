"""Orchestrate a market-data refresh: fetch, parse, cache.

The fetch callable is injected so tests exercise the whole path without
touching the network.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from typing import Callable

from trader_ai.marketdata import amfi_client, cache
from trader_ai.marketdata.layouts import UNIVERSE
from trader_ai.marketdata.parser import parse


@dataclass(frozen=True)
class RefreshResult:
    schemes_written: int
    nav_ingested: int
    nav_skipped: int
    parse_skipped: Counter


def refresh_universe(
    con: sqlite3.Connection,
    fetch: Callable[[], str] | None = None,
) -> RefreshResult:
    """Refresh the scheme master and today's NAV from the universe file."""
    fetch = fetch or amfi_client.fetch_universe
    parsed = parse(fetch(), UNIVERSE)

    schemes_written = cache.upsert_schemes(con, parsed.rows)
    ingested, skipped = cache.upsert_nav_rows(
        con, parsed.rows, cache.ledger_isins(con)
    )
    cache.log_fetch(con, "universe", None, None, ingested, skipped)

    return RefreshResult(
        schemes_written=schemes_written,
        nav_ingested=ingested,
        nav_skipped=skipped,
        parse_skipped=parsed.skipped,
    )
