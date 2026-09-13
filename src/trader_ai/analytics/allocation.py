"""Current allocation versus target, by asset class.

Weights are computed over classified value only. UNCLASSIFIED value is
surfaced separately so it is visible rather than silently folded into a
denominator and hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

UNCLASSIFIED = "UNCLASSIFIED"


@dataclass(frozen=True)
class AllocationDrift:
    asset_class: str
    current_value: float
    current_weight: float
    target_weight: float
    drift: float  # current_weight - target_weight; positive means overweight


@dataclass(frozen=True)
class AllocationReport:
    drifts: list[AllocationDrift]
    total_value: float
    unclassified_value: float


def compute_drift(
    values_by_class: dict[str, float],
    targets: dict[str, float],
) -> AllocationReport:
    """Compare current asset-class weights against target weights.

    values_by_class: current market value per asset class, may include
        an "UNCLASSIFIED" key.
    targets: target weight per asset class, as fractions summing to ~1.0.
    """
    unclassified = float(values_by_class.get(UNCLASSIFIED, 0.0))
    classified = {k: float(v) for k, v in values_by_class.items() if k != UNCLASSIFIED}
    total = sum(classified.values())

    drifts: list[AllocationDrift] = []
    for asset_class in sorted(set(classified) | set(targets)):
        value = classified.get(asset_class, 0.0)
        weight = (value / total) if total > 0 else 0.0
        target = float(targets.get(asset_class, 0.0))
        drifts.append(
            AllocationDrift(
                asset_class=asset_class,
                current_value=value,
                current_weight=weight,
                target_weight=target,
                drift=weight - target,
            )
        )

    return AllocationReport(
        drifts=drifts,
        total_value=total,
        unclassified_value=unclassified,
    )
