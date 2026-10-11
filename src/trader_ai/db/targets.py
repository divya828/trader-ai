"""The target asset allocation: the one input that is a choice, not a fact.

Every other table is derived from a statement or a public file. This one
records what the owner intends, and the allocation rules measure drift against
it. Validation lives here rather than in the CHECK constraint because the
mistakes worth catching span rows: weights that do not sum to 1, or a class
left over from a previous target.
"""

from __future__ import annotations

import math
import sqlite3

ASSET_CLASSES = ("EQUITY", "DEBT", "HYBRID", "GOLD", "CASH")
SUM_TOLERANCE = 1e-6


def _validate(weights: dict[str, float]) -> None:
    if not weights:
        raise ValueError("a target needs at least one asset class")
    for asset_class, weight in weights.items():
        if asset_class not in ASSET_CLASSES:
            raise ValueError(
                f"unknown asset class {asset_class!r}; expected one of {ASSET_CLASSES}"
            )
        if not 0.0 <= weight <= 1.0:
            raise ValueError(
                f"{asset_class} weight {weight} is outside [0, 1]; "
                "weights are fractions, so 70% is 0.70"
            )
    total = sum(weights.values())
    if not math.isclose(total, 1.0, abs_tol=SUM_TOLERANCE):
        raise ValueError(
            f"weights must sum to 1.0 (100%), got {total:.6f} ({total * 100:.1f}%)"
        )


def set_targets(con: sqlite3.Connection, weights: dict[str, float]) -> None:
    """Replace the whole target allocation, or change nothing if it is invalid."""
    _validate(weights)
    with con:
        con.execute("DELETE FROM target_allocation")
        con.executemany(
            "INSERT INTO target_allocation (asset_class, target_weight) VALUES (?, ?)",
            sorted(weights.items()),
        )


def get_targets(con: sqlite3.Connection) -> dict[str, float]:
    return {
        r["asset_class"]: float(r["target_weight"])
        for r in con.execute("SELECT asset_class, target_weight FROM target_allocation")
    }


def clear_targets(con: sqlite3.Connection) -> None:
    """Return to 'no target', under which band_breach deliberately stays silent."""
    with con:
        con.execute("DELETE FROM target_allocation")
