"""Persist parsed market data, incrementally and scoped to the ledger.

Downloads are whole-universe (the privacy invariant); filtering happens here,
after download, on-machine. NAV rows are kept only for ISINs the ledger
actually holds, so cache size tracks the portfolio rather than the fund
universe.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from trader_ai.marketdata.categories import classify_category
from trader_ai.marketdata.parser import SchemeRow

_ONE_DAY = timedelta(days=1)


def ledger_isins(con: sqlite3.Connection) -> set[str]:
    """Every ISIN the ledger holds, across mutual funds and securities."""
    isins: set[str] = set()
    for query in (
        "SELECT isin FROM schemes WHERE isin IS NOT NULL",
        "SELECT isin FROM securities WHERE isin IS NOT NULL",
    ):
        isins.update(row[0] for row in con.execute(query))
    return isins


def upsert_schemes(con: sqlite3.Connection, rows: list[SchemeRow]) -> int:
    """Refresh the scheme master. Returns the number of rows written."""
    written = 0
    for row in rows:
        asset_class = classify_category(row.sebi_category) or "UNCLASSIFIED"
        con.execute(
            "INSERT INTO md_schemes(amfi_code, isin_growth, isin_reinvest,"
            " scheme_name, amc, sebi_category, plan, scheme_structure, is_etf,"
            " option, asset_class, last_seen)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(amfi_code) DO UPDATE SET"
            "   isin_growth=excluded.isin_growth,"
            "   isin_reinvest=excluded.isin_reinvest,"
            "   scheme_name=excluded.scheme_name,"
            "   amc=excluded.amc,"
            "   sebi_category=excluded.sebi_category,"
            "   plan=excluded.plan,"
            "   scheme_structure=excluded.scheme_structure,"
            "   is_etf=excluded.is_etf,"
            "   option=excluded.option,"
            "   asset_class=excluded.asset_class,"
            "   last_seen=excluded.last_seen",
            (
                row.amfi_code,
                row.isin_growth,
                row.isin_reinvest,
                row.scheme_name,
                row.amc,
                row.sebi_category,
                row.plan,
                row.scheme_structure,
                1 if row.is_etf else 0,
                row.option,
                asset_class,
                row.nav_date,
            ),
        )
        written += 1
    con.commit()
    return written


def upsert_nav_rows(
    con: sqlite3.Connection, rows: list[SchemeRow], keep_isins: set[str]
) -> tuple[int, int]:
    """Write NAV points for held ISINs only. Returns (ingested, skipped)."""
    ingested = skipped = 0
    for row in rows:
        held = (row.isin_growth in keep_isins) or (row.isin_reinvest in keep_isins)
        if not held:
            skipped += 1
            continue
        con.execute(
            "INSERT INTO md_nav(amfi_code, nav_date, nav) VALUES (?, ?, ?)"
            " ON CONFLICT(amfi_code, nav_date) DO UPDATE SET nav=excluded.nav",
            (row.amfi_code, row.nav_date, row.nav),
        )
        ingested += 1
    con.commit()
    return ingested, skipped


def log_fetch(
    con: sqlite3.Connection,
    endpoint: str,
    start: date | None,
    end: date | None,
    ingested: int,
    skipped: int,
) -> None:
    """Record a completed fetch so the range is not downloaded again."""
    con.execute(
        "INSERT INTO md_fetch_log(endpoint, range_start, range_end,"
        " rows_ingested, rows_skipped) VALUES (?, ?, ?, ?, ?)",
        (
            endpoint,
            start.isoformat() if start else None,
            end.isoformat() if end else None,
            ingested,
            skipped,
        ),
    )
    con.commit()


def missing_ranges(
    con: sqlite3.Connection, start: date, end: date
) -> list[tuple[date, date]]:
    """Sub-ranges of [start, end] not already covered by md_fetch_log.

    Day-granular set subtraction: correct for the modest windows a personal
    ledger spans, and far easier to verify than interval arithmetic.
    """
    if end < start:
        return []

    cached: set[date] = set()
    rows = con.execute(
        "SELECT range_start, range_end FROM md_fetch_log"
        " WHERE range_start IS NOT NULL AND range_end IS NOT NULL"
    ).fetchall()
    for row in rows:
        cursor = date.fromisoformat(row[0])
        last = date.fromisoformat(row[1])
        while cursor <= last:
            cached.add(cursor)
            cursor += _ONE_DAY

    gaps: list[tuple[date, date]] = []
    run_start: date | None = None
    cursor = start
    while cursor <= end:
        if cursor in cached:
            if run_start is not None:
                gaps.append((run_start, cursor - _ONE_DAY))
                run_start = None
        elif run_start is None:
            run_start = cursor
        cursor += _ONE_DAY
    if run_start is not None:
        gaps.append((run_start, end))
    return gaps
