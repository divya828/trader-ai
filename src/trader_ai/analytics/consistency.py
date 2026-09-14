"""Rolling-return distribution rather than a point-to-point figure.

Source: rolling-return methodology; SEBI category peer grouping.

A single "3-year return" depends entirely on its two endpoints, which the
literature flags repeatedly as the error that makes funds look better or worse
than they were. Rolling windows show the distribution instead: how good the
good stretches were, how bad the bad ones, and how often the fund was negative.

Index-benchmark comparison is deferred: NSE refuses programmatic access, so
there is no index series to compare against. Peer-relative ranking against SEBI
category members is the available substitute and belongs to the rule engine.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from trader_ai.analytics.nav_series import NavPoint, cagr


@dataclass(frozen=True)
class Distribution:
    count: int
    median: float | None
    best: float | None
    worst: float | None
    share_negative: float


def rolling_returns(points: list[NavPoint], window_days: int) -> list[float]:
    """Annualised returns over every window of at least window_days.

    For each start point, the first later point at least window_days away is
    used as the window end. Zero-NAV starts are skipped rather than dividing
    by zero.
    """
    results: list[float] = []
    for index, start in enumerate(points):
        if start.nav <= 0:
            continue
        for end in points[index + 1 :]:
            span = (end.nav_date - start.nav_date).days
            if span < window_days:
                continue
            rate = cagr(start.nav, end.nav, span)
            if rate is not None:
                results.append(rate)
            break
    return results


def summarise(returns: list[float]) -> Distribution:
    """Distribution of rolling returns. Empty input yields count 0, not zero."""
    if not returns:
        return Distribution(
            count=0, median=None, best=None, worst=None, share_negative=0.0
        )
    negatives = sum(1 for r in returns if r < 0)
    return Distribution(
        count=len(returns),
        median=statistics.median(returns),
        best=max(returns),
        worst=min(returns),
        share_negative=negatives / len(returns),
    )
