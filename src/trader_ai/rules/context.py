"""What a rule is allowed to see.

Rules receive already-computed metrics and derived weights -- never raw ledger
rows, and never anything identifying. Folio numbers and PAN are not reachable
from a Context at all, which is how Finding stays PII-free by construction
rather than by remembering to filter.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

DISPOSAL_TYPES = ("REDEMPTION", "SWITCH_OUT", "SWITCH_OUT_MERGER", "GIFT_OUT")


@dataclass(frozen=True)
class HoldingView:
    scheme_id: int
    scheme_name: str
    sebi_category: str | None
    asset_class: str
    plan: str | None
    option: str | None
    weight: float          # share of portfolio value, never an amount


@dataclass(frozen=True)
class Context:
    holdings: list[HoldingView]
    asset_class_weights: dict[str, float]
    disposal_count: int
    has_target: bool
    targets: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, object] = field(default_factory=dict)


def build_context(con: sqlite3.Connection, metrics: dict | None = None) -> Context:
    """Assemble everything the rules may read, and nothing they may not."""
    run = con.execute("SELECT MAX(import_run_id) AS r FROM import_runs").fetchone()
    run_id = None if run["r"] is None else int(run["r"])

    rows = []
    if run_id is not None:
        rows = con.execute(
            "SELECT s.scheme_id, s.scheme_name, s.asset_class, h.value,"
            "       m.sebi_category, m.plan, m.option"
            " FROM holdings_snapshot h"
            " JOIN schemes s ON s.scheme_id = h.scheme_id"
            " LEFT JOIN md_schemes m"
            "   ON m.isin_growth = s.isin OR m.isin_reinvest = s.isin"
            " WHERE h.import_run_id = ?",
            (run_id,),
        ).fetchall()

    total = sum(float(r["value"]) for r in rows)
    holdings = [
        HoldingView(
            scheme_id=int(r["scheme_id"]),
            scheme_name=r["scheme_name"],
            sebi_category=r["sebi_category"],
            asset_class=r["asset_class"],
            plan=r["plan"],
            option=r["option"],
            weight=(float(r["value"]) / total) if total > 0 else 0.0,
        )
        for r in rows
    ]

    weights: dict[str, float] = {}
    for holding in holdings:
        weights[holding.asset_class] = weights.get(holding.asset_class, 0.0) + holding.weight

    placeholders = ",".join("?" for _ in DISPOSAL_TYPES)
    disposals = con.execute(
        f"SELECT COUNT(*) AS n FROM transactions WHERE txn_type IN ({placeholders})",
        DISPOSAL_TYPES,
    ).fetchone()["n"]

    targets = {
        r["asset_class"]: float(r["target_weight"])
        for r in con.execute("SELECT asset_class, target_weight FROM target_allocation")
    }

    return Context(
        holdings=holdings,
        asset_class_weights=weights,
        disposal_count=int(disposals),
        has_target=bool(targets),
        targets=targets,
        metrics=metrics or {},
    )
