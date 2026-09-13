"""Extended internal rate of return.

Bisection on NPV rather than Newton-Raphson: SIP cashflow patterns are
irregular and Newton can diverge on them, while bisection over a bracketed
range always converges when a sign change exists.
"""

from __future__ import annotations

from datetime import date

DAYS_PER_YEAR = 365.0
_LOW = -0.9999999  # rates <= -1 make the discount factor undefined
_HIGH = 1000.0
_MAX_ITERATIONS = 200
_TOLERANCE = 1e-9

Cashflow = tuple[date, float]


def _npv(rate: float, flows: list[Cashflow], t0: date) -> float:
    total = 0.0
    for when, amount in flows:
        years = (when - t0).days / DAYS_PER_YEAR
        total += amount / ((1.0 + rate) ** years)
    return total


def xirr(flows: list[Cashflow]) -> float | None:
    """Annualized IRR for irregularly spaced cashflows.

    Sign convention: money leaving you is negative, money returning is
    positive. Returns None when no rate exists (fewer than two flows, no
    sign change, or all flows on one date) rather than raising.
    """
    if len(flows) < 2:
        return None

    amounts = [amount for _, amount in flows]
    if not (any(a > 0 for a in amounts) and any(a < 0 for a in amounts)):
        return None

    ordered = sorted(flows, key=lambda f: f[0])
    t0 = ordered[0][0]
    if all(when == t0 for when, _ in ordered):
        return None

    low, high = _LOW, _HIGH
    npv_low, npv_high = _npv(low, ordered, t0), _npv(high, ordered, t0)
    if npv_low * npv_high > 0:
        return None

    for _ in range(_MAX_ITERATIONS):
        mid = (low + high) / 2.0
        npv_mid = _npv(mid, ordered, t0)
        if abs(npv_mid) < _TOLERANCE or (high - low) / 2.0 < _TOLERANCE:
            return mid
        if npv_mid * npv_low > 0:
            low, npv_low = mid, npv_mid
        else:
            high = mid
    return (low + high) / 2.0
