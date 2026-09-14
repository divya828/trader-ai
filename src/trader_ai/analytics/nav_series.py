"""Read cached NAV series and compute rates over them.

Shared by behaviour gap, cost drag and consistency. Reads cache tables only --
never the HTTP client, which is what keeps analytics I/O-free and testable with
synthetic rows.

Zero-NAV points are filtered here rather than in each caller: 241 rows in the
live universe carry NAV exactly 0.0 (Franklin side-pocketed debt), and every
return formula divides by a starting NAV.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

DAYS_PER_YEAR = 365.0


@dataclass(frozen=True)
class NavPoint:
    nav_date: date
    nav: float


def _rows_to_points(rows) -> list[NavPoint]:
    return [
        NavPoint(nav_date=date.fromisoformat(r["nav_date"][:10]), nav=float(r["nav"]))
        for r in rows
    ]


def nav_series(
    con: sqlite3.Connection,
    scheme_id: int,
    start: date | None = None,
    end: date | None = None,
) -> list[NavPoint]:
    """Cached NAV points for a ledger scheme, oldest first, zero NAVs removed."""
    sql = (
        "SELECT n.nav_date, n.nav FROM md_nav n"
        " JOIN md_schemes m ON m.amfi_code = n.amfi_code"
        " JOIN schemes s ON (m.isin_growth = s.isin OR m.isin_reinvest = s.isin)"
        " WHERE s.scheme_id = ? AND n.nav > 0"
    )
    params: list = [scheme_id]
    if start is not None:
        sql += " AND n.nav_date >= ?"
        params.append(start.isoformat())
    if end is not None:
        sql += " AND n.nav_date <= ?"
        params.append(end.isoformat())
    sql += " ORDER BY n.nav_date"
    return _rows_to_points(con.execute(sql, params).fetchall())


def nav_on_or_before(
    con: sqlite3.Connection, scheme_id: int, when: date
) -> NavPoint | None:
    """The latest cached NAV point at or before a date, or None."""
    points = nav_series(con, scheme_id, end=when)
    return points[-1] if points else None


def cagr(start_nav: float, end_nav: float, days: int) -> float | None:
    """Compound annual growth rate, or None when undefined.

    Undefined when the starting NAV is zero (side-pocketed schemes) or the
    window is not positive.
    """
    if start_nav <= 0 or days <= 0:
        return None
    if end_nav <= 0:
        return -1.0
    years = days / DAYS_PER_YEAR
    return (end_nav / start_nav) ** (1.0 / years) - 1.0
