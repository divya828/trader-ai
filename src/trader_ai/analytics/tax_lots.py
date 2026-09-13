"""FIFO tax-lot matching with holding-period classification.

v0.1 classifies LTCG/STCG by holding period only. It deliberately computes
no tax amount, applies no exemption slab, and performs no grandfathering.

Mutual funds only: stocks have no acquisition history in an eCAS.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

EQUITY_LTCG_DAYS = 365
DEBT_LTCG_DAYS = 1095
# From this date debt fund gains are slab-rated regardless of holding period.
DEBT_SLAB_REGIME_START = date(2023, 4, 1)
_EPSILON = 1e-9


@dataclass(frozen=True)
class Acquisition:
    acquired_date: date
    units: float
    cost_per_unit: float


@dataclass(frozen=True)
class Disposal:
    disposed_date: date
    units: float
    price_per_unit: float


@dataclass(frozen=True)
class LotDisposal:
    acquired_date: date
    disposed_date: date
    units_disposed: float
    cost_basis: float
    proceeds: float
    gain: float
    holding_period_days: int
    classification: str


def classify(asset_class: str, acquired: date, disposed: date) -> str:
    """Return 'LTCG' or 'STCG' from holding period alone."""
    held_days = (disposed - acquired).days
    if asset_class == "DEBT":
        if acquired >= DEBT_SLAB_REGIME_START:
            return "STCG"
        return "LTCG" if held_days > DEBT_LTCG_DAYS else "STCG"
    return "LTCG" if held_days > EQUITY_LTCG_DAYS else "STCG"


def match_fifo(
    acquisitions: list[Acquisition],
    disposals: list[Disposal],
    asset_class: str,
) -> list[LotDisposal]:
    """Match disposals against acquisitions oldest-first.

    Splits lots as needed; a disposal spanning two lots produces two
    LotDisposal rows. Raises ValueError if a disposal exceeds available units.
    """
    open_lots: list[list] = [
        [a.acquired_date, a.units, a.cost_per_unit]
        for a in sorted(acquisitions, key=lambda a: a.acquired_date)
    ]

    results: list[LotDisposal] = []
    for disposal in sorted(disposals, key=lambda d: d.disposed_date):
        remaining = disposal.units
        while remaining > _EPSILON:
            open_lots = [lot for lot in open_lots if lot[1] > _EPSILON]
            if not open_lots:
                raise ValueError(
                    f"disposal of {disposal.units} units on "
                    f"{disposal.disposed_date} exceeds available units"
                )
            lot = open_lots[0]
            acquired_date, available, cost_per_unit = lot
            taken = min(available, remaining)

            cost_basis = taken * cost_per_unit
            proceeds = taken * disposal.price_per_unit
            results.append(
                LotDisposal(
                    acquired_date=acquired_date,
                    disposed_date=disposal.disposed_date,
                    units_disposed=taken,
                    cost_basis=cost_basis,
                    proceeds=proceeds,
                    gain=proceeds - cost_basis,
                    holding_period_days=(disposal.disposed_date - acquired_date).days,
                    classification=classify(
                        asset_class, acquired_date, disposal.disposed_date
                    ),
                )
            )
            lot[1] = available - taken
            remaining -= taken

    return results
