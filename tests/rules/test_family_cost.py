import pytest

from trader_ai.analytics.cost_drag import CostDragReport
from trader_ai.analytics.measurement import Measurement
from trader_ai.rules.context import Context, HoldingView
from trader_ai.rules.families.cost import (
    coverage_incomplete_rule,
    regular_plan_drag_rule,
)


def _ctx(report, holdings=None):
    holdings = holdings or []
    weights: dict[str, float] = {}
    for h in holdings:
        weights[h.asset_class] = weights.get(h.asset_class, 0.0) + h.weight
    return Context(
        holdings=holdings,
        asset_class_weights=weights,
        disposal_count=0,
        has_target=False,
        metrics={"cost_drag": report},
    )


def _holding(name, plan, weight):
    return HoldingView(
        scheme_id=abs(hash(name)) % 1000,
        scheme_name=name,
        sebi_category="Equity Scheme - Flexi Cap Fund",
        asset_class="EQUITY",
        plan=plan,
        option="Growth Option",
        weight=weight,
    )


def test_regular_plan_drag_is_silent_when_everything_is_direct():
    """The real portfolio: 15 of 16 holdings are Direct plan.

    No finding is the correct output -- there is nothing to fix.
    """
    report = CostDragReport(
        drag=Measurement.of(0.0), covered_value=100.0, uncovered_value=0.0
    )
    ctx = _ctx(report, [_holding("A", "DIRECT", 1.0)])
    assert regular_plan_drag_rule(ctx) == []


def test_regular_plan_drag_fires_on_a_regular_holding():
    report = CostDragReport(
        drag=Measurement.of(0.009), covered_value=100.0, uncovered_value=0.0
    )
    ctx = _ctx(report, [_holding("A", "REGULAR", 0.4), _holding("B", "DIRECT", 0.6)])
    findings = regular_plan_drag_rule(ctx)
    assert len(findings) == 1
    assert findings[0].metrics["drag_per_year"] == pytest.approx(0.009)
    assert findings[0].subjects[0].ref == "A"


def test_regular_plan_drag_silent_when_drag_is_unavailable():
    report = CostDragReport(
        drag=Measurement.unavailable("no comparable pair"),
        covered_value=0.0,
        uncovered_value=100.0,
    )
    ctx = _ctx(report, [_holding("A", "REGULAR", 1.0)])
    assert regular_plan_drag_rule(ctx) == []


def test_regular_plan_drag_silent_without_a_cost_report():
    ctx = Context(
        holdings=[_holding("A", "REGULAR", 1.0)],
        asset_class_weights={"EQUITY": 1.0},
        disposal_count=0,
        has_target=False,
    )
    assert regular_plan_drag_rule(ctx) == []


def test_coverage_rule_silent_at_high_coverage():
    """The real portfolio covers 92.4%, above the 90% threshold."""
    report = CostDragReport(
        drag=Measurement.of(0.0), covered_value=92.4, uncovered_value=7.6
    )
    assert coverage_incomplete_rule(_ctx(report)) == []


def test_coverage_rule_fires_below_the_threshold():
    report = CostDragReport(
        drag=Measurement.of(0.0),
        covered_value=50.0,
        uncovered_value=50.0,
        exclusions={"UNKNOWN": 50.0},
    )
    findings = coverage_incomplete_rule(_ctx(report))
    assert len(findings) == 1
    assert findings[0].metrics["coverage_ratio"] == pytest.approx(0.5)


def test_coverage_rule_reports_the_largest_exclusion_reason():
    report = CostDragReport(
        drag=Measurement.of(0.0),
        covered_value=10.0,
        uncovered_value=90.0,
        exclusions={"UNKNOWN": 20.0, "NOT_APPLICABLE": 70.0},
    )
    finding = coverage_incomplete_rule(_ctx(report))[0]
    assert "NOT_APPLICABLE" in finding.title
