"""Diversification rules.

Two distinct failures. Category duplication is holding several funds that do
the same job -- it does not show up in a count of holdings. Low effective
holdings is owning many funds but concentrating value in one, which a count
also conceals.
"""

from __future__ import annotations

from datetime import datetime

from trader_ai.analytics.diversification import (
    category_duplication,
    effective_holdings,
)
from trader_ai.rules.context import Context
from trader_ai.rules.finding import Finding, Severity, Subject

DIMENSION = "DIVERSIFICATION"
# Below this share of the nominal count, weights are concentrated enough that
# the fund count materially overstates diversification.
EFFECTIVE_RATIO_FLOOR = 0.5
DUPLICATION_HIGH_WEIGHT = 0.20


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def category_duplication_rule(ctx: Context) -> list[Finding]:
    """Several funds in one SEBI category add names without adding exposure."""
    triples = [
        (h.scheme_name, h.sebi_category, h.weight)
        for h in ctx.holdings
        if h.sebi_category
    ]
    groups = category_duplication(triples)
    findings: list[Finding] = []
    for category, group in sorted(groups.items(), key=lambda kv: -kv[1].value):
        members = [h for h in ctx.holdings if h.sebi_category == category]
        severity = (
            Severity.MEDIUM if group.value >= DUPLICATION_HIGH_WEIGHT else Severity.LOW
        )
        findings.append(
            Finding(
                rule_id="diversification.category_duplication",
                severity=severity,
                title=f"{group.count} funds share the SEBI category {category}",
                subjects=[
                    Subject(
                        kind="SCHEME",
                        ref=m.scheme_name,
                        weight=m.weight,
                        local_id=m.scheme_id,
                    )
                    for m in members
                ],
                metrics={
                    "fund_count": float(group.count),
                    "combined_weight": float(group.value),
                },
                citation_key="sebi_categorization",
                computed_at=_now(),
                dimension=DIMENSION,
            )
        )
    return findings


def low_effective_holdings_rule(ctx: Context) -> list[Finding]:
    """Many funds, but value concentrated in a few."""
    weights = [h.weight for h in ctx.holdings]
    if len(weights) < 2:
        return []
    effective = effective_holdings(weights)
    nominal = float(len(weights))
    if effective >= nominal * EFFECTIVE_RATIO_FLOOR:
        return []
    return [
        Finding(
            rule_id="diversification.low_effective_holdings",
            severity=Severity.MEDIUM,
            title=(
                f"{nominal:.0f} funds held, but effectively "
                f"{effective:.1f} after weighting"
            ),
            subjects=[Subject(kind="PORTFOLIO", ref="portfolio")],
            metrics={
                "effective_holdings": effective,
                "nominal_holdings": nominal,
            },
            citation_key="herfindahl_concentration",
            computed_at=_now(),
            dimension=DIMENSION,
        )
    ]
