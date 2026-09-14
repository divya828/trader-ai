import pytest

from trader_ai.rules.context import Context, HoldingView
from trader_ai.rules.families.allocation import (
    band_breach_rule,
    unclassified_holdings_rule,
)


def _holding(name, asset_class, weight):
    return HoldingView(
        scheme_id=abs(hash(name)) % 1000,
        scheme_name=name,
        sebi_category="Equity Scheme - Flexi Cap Fund",
        asset_class=asset_class,
        plan="DIRECT",
        option="Growth Option",
        weight=weight,
    )


def _ctx(holdings, targets=None):
    weights: dict[str, float] = {}
    for h in holdings:
        weights[h.asset_class] = weights.get(h.asset_class, 0.0) + h.weight
    return Context(
        holdings=holdings,
        asset_class_weights=weights,
        disposal_count=0,
        has_target=bool(targets),
        targets=targets or {},
    )


def test_band_breach_is_silent_without_a_target():
    """The real portfolio has no target_allocation rows.

    Inventing one would present a default as a recommendation.
    """
    ctx = _ctx([_holding("A", "EQUITY", 1.0)])
    assert band_breach_rule(ctx) == []


def test_band_breach_fires_when_a_class_drifts():
    ctx = _ctx(
        [_holding("A", "EQUITY", 1.0)],
        targets={"EQUITY": 0.6, "DEBT": 0.4},
    )
    findings = band_breach_rule(ctx)
    classes = {f.subjects[0].ref for f in findings}
    assert "EQUITY" in classes and "DEBT" in classes


def test_band_breach_is_silent_when_on_target():
    ctx = _ctx(
        [_holding("A", "EQUITY", 0.6), _holding("B", "DEBT", 0.4)],
        targets={"EQUITY": 0.6, "DEBT": 0.4},
    )
    assert band_breach_rule(ctx) == []


def test_band_breach_records_which_band_bound():
    ctx = _ctx(
        [_holding("A", "GOLD", 0.055), _holding("B", "EQUITY", 0.945)],
        targets={"GOLD": 0.04, "EQUITY": 0.96},
    )
    gold = [f for f in band_breach_rule(ctx) if f.subjects[0].ref == "GOLD"][0]
    assert gold.metrics["breached_relative"] == 1.0
    assert gold.metrics["breached_absolute"] == 0.0


def test_unclassified_fires_when_holdings_lack_an_asset_class():
    ctx = _ctx([_holding("A", "UNCLASSIFIED", 0.3), _holding("B", "EQUITY", 0.7)])
    findings = unclassified_holdings_rule(ctx)
    assert len(findings) == 1
    assert findings[0].metrics["unclassified_weight"] == pytest.approx(0.3)


def test_unclassified_is_silent_when_everything_is_classified():
    ctx = _ctx([_holding("A", "EQUITY", 1.0)])
    assert unclassified_holdings_rule(ctx) == []
