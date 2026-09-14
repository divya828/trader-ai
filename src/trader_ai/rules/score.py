"""Health score across five dimensions.

The rule that matters: a dimension with no findings AND nothing to evaluate
scores None, carrying the reason. It never scores 100.

This is not hypothetical. Measured on a real portfolio, TAX_EFFICIENCY had zero
disposals and zero IDCW holdings, so neither tax rule could fire. Scoring it
100 would report perfect tax efficiency for a portfolio whose tax behaviour has
never been observed.

The weights below are an opinion, not a fact, which is why they live in one
place and are easy to change.
"""

from __future__ import annotations

from dataclasses import dataclass

from trader_ai.rules.finding import Finding, Severity

DIMENSIONS = (
    "COST",
    "DIVERSIFICATION",
    "BEHAVIOR",
    "ALLOCATION",
    "TAX_EFFICIENCY",
)

SEVERITY_PENALTY = {
    Severity.INFO: 0.0,     # informational: reported, not penalised
    Severity.LOW: 8.0,
    Severity.MEDIUM: 20.0,
    Severity.HIGH: 35.0,
}


@dataclass(frozen=True)
class DimensionScore:
    dimension: str
    score: float | None
    finding_count: int
    unscored_reason: str | None = None
    rules_run: int = 0
    rules_total: int = 0

    @property
    def fully_evaluated(self) -> bool:
        """False when some of this dimension's rules could not run.

        A dimension can be PARTLY measured: on a portfolio with no target
        allocation, ALLOCATION scores 100 from the unclassified-holdings rule
        alone while the band-breach rule never ran. Reporting a bare 100 there
        would read as "allocation is fine" when half of it was unevaluated.
        """
        return self.rules_total > 0 and self.rules_run == self.rules_total


@dataclass(frozen=True)
class OverallScore:
    score: float | None
    measured_count: int
    total_count: int


def score_dimensions(
    findings: list[Finding],
    evaluable: set[str],
    rule_coverage: dict[str, tuple[int, int]] | None = None,
) -> dict[str, DimensionScore]:
    """Score every dimension. Unevaluable ones get None and a reason.

    rule_coverage maps a dimension to (rules_run, rules_total) so a partially
    evaluated dimension can say so rather than presenting a clean-looking
    score built from half its rules.
    """
    coverage = rule_coverage or {}
    scores: dict[str, DimensionScore] = {}
    for dimension in DIMENSIONS:
        relevant = [f for f in findings if f.dimension == dimension]
        ran, total = coverage.get(dimension, (0, 0))
        if dimension not in evaluable and not relevant:
            scores[dimension] = DimensionScore(
                dimension=dimension,
                score=None,
                finding_count=0,
                unscored_reason="no data available to evaluate this dimension",
                rules_run=ran,
                rules_total=total,
            )
            continue
        penalty = sum(SEVERITY_PENALTY[f.severity] for f in relevant)
        scores[dimension] = DimensionScore(
            dimension=dimension,
            score=max(0.0, 100.0 - penalty),
            finding_count=len(relevant),
            rules_run=ran,
            rules_total=total,
        )
    return scores


def overall_score(scores: dict[str, DimensionScore]) -> OverallScore:
    """Mean of the dimensions that could be measured, with the count shown.

    Averaging over unmeasured dimensions would let missing data raise or lower
    the headline number, so they are excluded and counted instead.
    """
    measured = [s.score for s in scores.values() if s.score is not None]
    return OverallScore(
        score=(sum(measured) / len(measured)) if measured else None,
        measured_count=len(measured),
        total_count=len(DIMENSIONS),
    )
