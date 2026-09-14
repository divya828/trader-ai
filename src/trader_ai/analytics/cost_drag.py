"""Cost drag measured from the Direct/Regular NAV spread.

Source: Bogle, cost-matters hypothesis; SEBI direct-plan regulation.

AMFI publishes no machine-readable TER, so drag is measured empirically: the
same scheme's Direct and Regular plans differ only in expenses, so the spread
between their NAV growth over the holding period IS the realised drag,
including trail commission as actually charged.

Coverage is reported, never implied. AMFI populates the Plan column for only
about 60% of the universe, and the gaps have three distinct causes that must
not be collapsed: NOT_APPLICABLE (ETF or close-ended -- no Direct/Regular
distinction exists), UNKNOWN (open-ended, source omitted it), and NO_SIBLING
(a Regular plan whose Direct counterpart is not in the universe). A
portfolio-level figure is never presented without the share of value it covers.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date as _date

from trader_ai.analytics.measurement import Measurement
from trader_ai.analytics.nav_series import NavPoint, cagr

NOT_APPLICABLE = "NOT_APPLICABLE"
UNKNOWN = "UNKNOWN"
NO_SIBLING = "NO_SIBLING"
NO_MARKET_DATA = "NO_MARKET_DATA"
NO_NAV_HISTORY = "NO_NAV_HISTORY"


@dataclass(frozen=True)
class CostDragReport:
    drag: Measurement           # weighted annualised drag across covered value
    covered_value: float
    uncovered_value: float
    exclusions: dict[str, float] = field(default_factory=dict)

    @property
    def coverage_ratio(self) -> float:
        total = self.covered_value + self.uncovered_value
        return self.covered_value / total if total > 0 else 0.0


def _latest_run(con: sqlite3.Connection) -> int | None:
    row = con.execute("SELECT MAX(import_run_id) AS r FROM import_runs").fetchone()
    return None if row["r"] is None else int(row["r"])


def _points_for_code(con: sqlite3.Connection, amfi_code: str) -> list[NavPoint]:
    rows = con.execute(
        "SELECT nav_date, nav FROM md_nav WHERE amfi_code = ? AND nav > 0"
        " ORDER BY nav_date",
        (amfi_code,),
    ).fetchall()
    return [
        NavPoint(nav_date=_date.fromisoformat(r["nav_date"][:10]), nav=float(r["nav"]))
        for r in rows
    ]


def _series_cagr(con: sqlite3.Connection, amfi_code: str) -> float | None:
    points = _points_for_code(con, amfi_code)
    if len(points) < 2:
        return None
    return cagr(
        points[0].nav, points[-1].nav, (points[-1].nav_date - points[0].nav_date).days
    )


def _sibling_code(con: sqlite3.Connection, row) -> str | None:
    """The Direct counterpart of a Regular scheme: same AMC, name and option."""
    match = con.execute(
        "SELECT amfi_code FROM md_schemes"
        " WHERE plan = 'DIRECT' AND scheme_name = ? AND amc IS ? AND option IS ?"
        " LIMIT 1",
        (row["scheme_name"], row["amc"], row["option"]),
    ).fetchone()
    return None if match is None else match["amfi_code"]


def portfolio_cost_drag(con: sqlite3.Connection) -> CostDragReport:
    """Weighted cost drag across the portfolio, with explicit coverage."""
    run_id = _latest_run(con)
    if run_id is None:
        return CostDragReport(
            drag=Measurement.unavailable("no import runs"),
            covered_value=0.0,
            uncovered_value=0.0,
        )

    holdings = con.execute(
        "SELECT h.value, s.isin, m.amfi_code, m.plan, m.scheme_name, m.amc, m.option"
        " FROM holdings_snapshot h"
        " JOIN schemes s ON s.scheme_id = h.scheme_id"
        " LEFT JOIN md_schemes m"
        "   ON m.isin_growth = s.isin OR m.isin_reinvest = s.isin"
        " WHERE h.import_run_id = ?",
        (run_id,),
    ).fetchall()

    covered = 0.0
    weighted_drag = 0.0
    exclusions: dict[str, float] = {}

    def exclude(reason: str, value: float) -> None:
        exclusions[reason] = exclusions.get(reason, 0.0) + value

    for row in holdings:
        value = float(row["value"])
        if row["amfi_code"] is None:
            exclude(NO_MARKET_DATA, value)
            continue

        plan = row["plan"]
        if plan in (NOT_APPLICABLE, UNKNOWN):
            exclude(plan, value)
            continue

        if plan == "DIRECT":
            # Already the cheapest plan: covered, zero drag.
            covered += value
            continue

        sibling = _sibling_code(con, row)
        if sibling is None:
            exclude(NO_SIBLING, value)
            continue

        own = _series_cagr(con, row["amfi_code"])
        theirs = _series_cagr(con, sibling)
        if own is None or theirs is None:
            exclude(NO_NAV_HISTORY, value)
            continue

        covered += value
        weighted_drag += (theirs - own) * value

    uncovered = sum(exclusions.values())
    if covered <= 0:
        return CostDragReport(
            drag=Measurement.unavailable("no holdings with a comparable plan pair"),
            covered_value=0.0,
            uncovered_value=uncovered,
            exclusions=exclusions,
        )

    return CostDragReport(
        drag=Measurement.of(weighted_drag / covered),
        covered_value=covered,
        uncovered_value=uncovered,
        exclusions=exclusions,
    )
