"""Tax rules.

Both are silent on a portfolio that has never sold and holds only Growth
options -- which is exactly the state of the ledger this was built against.
That silence is the correct output, and the health score reports the dimension
as unmeasured rather than clean.
"""

from __future__ import annotations

from datetime import datetime

from trader_ai.rules.context import Context
from trader_ai.rules.finding import Finding, Severity, Subject

DIMENSION = "TAX_EFFICIENCY"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def idcw_inefficiency_rule(ctx: Context) -> list[Finding]:
    """IDCW payouts are taxed at slab rate; Growth defers the liability."""
    idcw = [h for h in ctx.holdings if h.option and "IDCW" in h.option.upper()]
    if not idcw:
        return []
    weight = sum(h.weight for h in idcw)
    return [
        Finding(
            rule_id="tax.idcw_inefficiency",
            severity=Severity.MEDIUM,
            title=(
                f"{len(idcw)} holdings use an IDCW option "
                f"({weight * 100:.1f}% of the portfolio)"
            ),
            subjects=[
                Subject(kind="SCHEME", ref=h.scheme_name, weight=h.weight)
                for h in idcw
            ],
            metrics={"idcw_count": float(len(idcw)), "idcw_weight": weight},
            citation_key="india_capital_gains",
            computed_at=_now(),
            dimension=DIMENSION,
        )
    ]


def rebalance_stcg_exposure_rule(ctx: Context) -> list[Finding]:
    """Selling within the short-term window realises gains at a higher rate."""
    if ctx.disposal_count == 0:
        return []
    return [
        Finding(
            rule_id="tax.rebalance_stcg_exposure",
            severity=Severity.INFO,
            title=(
                f"{ctx.disposal_count} disposals in the ledger may carry "
                "short-term gains"
            ),
            subjects=[Subject(kind="PORTFOLIO", ref="portfolio")],
            metrics={"disposal_count": float(ctx.disposal_count)},
            citation_key="india_capital_gains",
            computed_at=_now(),
            dimension=DIMENSION,
        )
    ]
