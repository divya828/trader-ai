"""Rebalancing bands, made tax-aware.

Source: Daryanani, "The 5/25 rule" -- rebalance when an asset class drifts
5 absolute percentage points OR 25% relative to its target, whichever binds
first. The relative band is what catches small targets: 25% of a 4% gold
allocation is one point, which the absolute band would never flag.

Proposals are run through v0.1's FIFO lot matcher so the user can see which
disposals would realise short-term versus long-term gains before acting. This
is advisory only: nothing here places an order.

Note: the tax-awareness path is validated against synthetic disposals only.
The real ledger this was built against contains no redemptions at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trader_ai.analytics.tax_lots import Acquisition, Disposal, LotDisposal, match_fifo

ABSOLUTE_BAND = 0.05   # 5 percentage points
RELATIVE_BAND = 0.25   # 25% of the target weight


@dataclass(frozen=True)
class BandBreach:
    asset_class: str
    current_weight: float
    target_weight: float
    drift: float               # current - target; negative means underweight
    breached_absolute: bool
    breached_relative: bool


def band_breaches(
    current: dict[str, float], targets: dict[str, float]
) -> list[BandBreach]:
    """Asset classes outside their rebalancing band, in sorted order."""
    breaches: list[BandBreach] = []
    for asset_class in sorted(set(current) | set(targets)):
        weight = float(current.get(asset_class, 0.0))
        target = float(targets.get(asset_class, 0.0))
        drift = weight - target
        absolute = abs(drift) >= ABSOLUTE_BAND
        relative = target > 0 and abs(drift) >= target * RELATIVE_BAND
        if absolute or relative:
            breaches.append(
                BandBreach(
                    asset_class=asset_class,
                    current_weight=weight,
                    target_weight=target,
                    drift=drift,
                    breached_absolute=absolute,
                    breached_relative=relative,
                )
            )
    return breaches


def tax_aware_disposal(
    acquisitions: list[Acquisition],
    units_to_sell: float,
    price_per_unit: float,
    on: date,
    asset_class: str,
) -> list[LotDisposal]:
    """Which lots a proposed sale would consume, and their tax treatment.

    Reuses v0.1's FIFO matcher rather than reimplementing lot logic. Raises if
    the proposal exceeds available units, because a rebalancing suggestion that
    cannot be executed is worse than none.
    """
    if units_to_sell <= 0:
        return []
    return match_fifo(
        acquisitions,
        [Disposal(disposed_date=on, units=units_to_sell, price_per_unit=price_per_unit)],
        asset_class=asset_class,
    )
