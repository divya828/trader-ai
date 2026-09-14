"""Cost rules.

Drag is measured from the Direct/Regular NAV spread rather than a published
TER, so the coverage rule matters: a drag figure over half the portfolio is a
different claim from one over all of it.
"""

from __future__ import annotations

from datetime import datetime

from trader_ai.rules.context import Context
from trader_ai.rules.finding import Finding, Severity, Subject

DIMENSION = "COST"
COVERAGE_FLOOR = 0.90


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def regular_plan_drag_rule(ctx: Context) -> list[Finding]:
    """Regular-plan holdings pay a distributor commission a Direct plan does not."""
    report = ctx.metrics.get("cost_drag")
    if report is None or not report.drag.available:
        return []

    regular = [h for h in ctx.holdings if h.plan == "REGULAR"]
    if not regular:
        return []

    weight = sum(h.weight for h in regular)
    return [
        Finding(
            rule_id="cost.regular_plan_drag",
            severity=Severity.HIGH if weight >= 0.25 else Severity.MEDIUM,
            title=(
                f"{len(regular)} Regular-plan holdings "
                f"({weight * 100:.1f}% of the portfolio) have Direct equivalents"
            ),
            subjects=[
                Subject(kind="SCHEME", ref=h.scheme_name, weight=h.weight)
                for h in regular
            ],
            metrics={
                "drag_per_year": report.drag.value,
                "regular_weight": weight,
                "regular_count": float(len(regular)),
            },
            citation_key="sebi_direct_plan",
            computed_at=_now(),
            dimension=DIMENSION,
        )
    ]


def coverage_incomplete_rule(ctx: Context) -> list[Finding]:
    """A cost figure computed over part of the portfolio says so."""
    report = ctx.metrics.get("cost_drag")
    if report is None:
        return []
    ratio = report.coverage_ratio
    if ratio >= COVERAGE_FLOOR:
        return []

    largest = (
        max(report.exclusions.items(), key=lambda kv: kv[1])[0]
        if report.exclusions
        else "unknown"
    )
    return [
        Finding(
            rule_id="cost.coverage_incomplete",
            severity=Severity.INFO,
            title=(
                f"Cost drag covers {ratio * 100:.1f}% of the portfolio; "
                f"the largest gap is {largest}"
            ),
            subjects=[Subject(kind="PORTFOLIO", ref="portfolio")],
            metrics={
                "coverage_ratio": ratio,
                "uncovered_value_share": 1.0 - ratio,
            },
            citation_key="bogle_cost_matters",
            computed_at=_now(),
            dimension=DIMENSION,
        )
    ]
