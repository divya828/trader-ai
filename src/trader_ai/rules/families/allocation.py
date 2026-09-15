"""Allocation rules.

band_breach deliberately emits nothing when no target allocation is
configured. The alternative -- assuming a conventional split -- would present
a default as a recommendation, and a portfolio that is 100% equity may be a
deliberate choice rather than a drift.
"""

from __future__ import annotations

from datetime import datetime

from trader_ai.analytics.rebalancing import band_breaches
from trader_ai.rules.context import Context
from trader_ai.rules.finding import Finding, Severity, Subject

DIMENSION = "ALLOCATION"
UNCLASSIFIED = "UNCLASSIFIED"
LARGE_DRIFT = 0.10


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def band_breach_rule(ctx: Context) -> list[Finding]:
    """Asset classes outside their 5/25 rebalancing band."""
    if not ctx.has_target:
        return []
    findings: list[Finding] = []
    for breach in band_breaches(ctx.asset_class_weights, ctx.targets):
        severity = Severity.MEDIUM if abs(breach.drift) >= LARGE_DRIFT else Severity.LOW
        findings.append(
            Finding(
                rule_id="allocation.band_breach",
                severity=severity,
                title=(
                    f"{breach.asset_class} is "
                    f"{breach.drift * 100:+.1f} points from its target"
                ),
                subjects=[
                    Subject(
                        kind="ASSET_CLASS",
                        ref=breach.asset_class,
                        weight=breach.current_weight,
                    )
                ],
                metrics={
                    "current_weight": breach.current_weight,
                    "target_weight": breach.target_weight,
                    "drift": breach.drift,
                    "breached_absolute": float(breach.breached_absolute),
                    "breached_relative": float(breach.breached_relative),
                },
                citation_key="daryanani_5_25",
                computed_at=_now(),
                dimension=DIMENSION,
            )
        )
    return findings


def unclassified_holdings_rule(ctx: Context) -> list[Finding]:
    """Holdings with no asset class make every allocation figure incomplete."""
    unclassified = [h for h in ctx.holdings if h.asset_class == UNCLASSIFIED]
    if not unclassified:
        return []
    weight = sum(h.weight for h in unclassified)
    return [
        Finding(
            rule_id="allocation.unclassified_holdings",
            severity=Severity.LOW,
            title=(
                f"{len(unclassified)} holdings have no asset class "
                f"({weight * 100:.1f}% of the portfolio)"
            ),
            subjects=[
                Subject(kind="SCHEME", ref=h.scheme_name, weight=h.weight, local_id=h.scheme_id)
                for h in unclassified
            ],
            metrics={
                "unclassified_count": float(len(unclassified)),
                "unclassified_weight": weight,
            },
            citation_key="sebi_categorization",
            computed_at=_now(),
            dimension=DIMENSION,
        )
    ]
