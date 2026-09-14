"""Behaviour gap: what you earned minus what the fund earned.

Source: Morningstar, "Mind the Gap"; Dalbar QAIB.

Money-weighted return (v0.1 xirr, which reflects when you actually invested)
against the fund's own time-weighted return over the same window (NAV start to
NAV end, which ignores timing). The difference is the cost -- or benefit -- of
timing. Negative means your timing cost you relative to simply holding.
"""

from __future__ import annotations

import sqlite3

from trader_ai.analytics.measurement import Measurement
from trader_ai.analytics.nav_series import cagr, nav_series
from trader_ai.analytics.portfolio import scheme_cashflows
from trader_ai.analytics.xirr import xirr

MIN_CASHFLOWS = 2


def scheme_behavior_gap(con: sqlite3.Connection, scheme_id: int) -> Measurement:
    """Money-weighted minus time-weighted annualised return for one scheme."""
    flows = scheme_cashflows(con, scheme_id)
    if len(flows) < MIN_CASHFLOWS:
        return Measurement.unavailable("fewer than two cashflows")

    points = nav_series(con, scheme_id)
    if len(points) < 2:
        return Measurement.unavailable("insufficient nav coverage")

    first_flow = min(when for when, _ in flows)
    last_flow = max(when for when, _ in flows)
    if points[0].nav_date > first_flow or points[-1].nav_date < last_flow:
        return Measurement.unavailable("nav does not span the cashflow window")

    money_weighted = xirr(flows)
    if money_weighted is None:
        return Measurement.unavailable("xirr has no solution for these cashflows")

    days = (points[-1].nav_date - points[0].nav_date).days
    time_weighted = cagr(points[0].nav, points[-1].nav, days)
    if time_weighted is None:
        return Measurement.unavailable("fund return undefined (zero or flat window)")

    return Measurement.of(money_weighted - time_weighted)
