import pytest

from trader_ai.rules.context import Context
from trader_ai.rules.registry import ALL_RULES, evaluate


def _empty_ctx():
    return Context(
        holdings=[],
        asset_class_weights={},
        disposal_count=0,
        has_target=False,
    )


def test_every_registered_rule_has_a_unique_id():
    ids = [rule.rule_id for rule in ALL_RULES]
    assert len(ids) == len(set(ids))


def test_the_nine_spec_rules_are_registered():
    ids = {rule.rule_id for rule in ALL_RULES}
    assert ids == {
        "cost.regular_plan_drag",
        "cost.coverage_incomplete",
        "tax.idcw_inefficiency",
        "tax.rebalance_stcg_exposure",
        "behavior.timing_gap",
        "diversification.category_duplication",
        "diversification.low_effective_holdings",
        "allocation.band_breach",
        "allocation.unclassified_holdings",
    }


def test_every_rule_declares_a_known_dimension():
    from trader_ai.rules.score import DIMENSIONS

    for rule in ALL_RULES:
        assert rule.dimension in DIMENSIONS


def test_evaluate_on_an_empty_portfolio_produces_no_findings():
    findings, evaluable, _ = evaluate(_empty_ctx())
    assert findings == []


def test_evaluate_reports_which_dimensions_were_evaluable():
    findings, evaluable, _ = evaluate(_empty_ctx())
    # No holdings, no target, no disposals: nothing can be judged.
    assert "TAX_EFFICIENCY" not in evaluable
    assert "ALLOCATION" not in evaluable


def test_evaluate_reports_per_dimension_rule_coverage():
    findings, evaluable, coverage = evaluate(_empty_ctx())
    # ALLOCATION has two rules; neither could run on an empty portfolio.
    assert coverage["ALLOCATION"] == (0, 2)
    assert coverage["COST"] == (0, 2)


def test_a_rule_raising_does_not_abort_the_whole_evaluation():
    """One broken rule must not silence every other finding."""
    from trader_ai.rules import registry

    def exploding(ctx):
        raise RuntimeError("boom")

    broken = registry.Rule(
        rule_id="test.explodes",
        dimension="COST",
        run=exploding,
        requires=lambda ctx: True,
    )
    findings, evaluable, _ = registry.evaluate(_empty_ctx(), rules=[broken])
    assert findings == []  # it failed, but did not propagate
