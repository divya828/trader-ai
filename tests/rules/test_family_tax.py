from trader_ai.rules.context import Context, HoldingView
from trader_ai.rules.families.tax import (
    idcw_inefficiency_rule,
    rebalance_stcg_exposure_rule,
)


def _holding(name, option, weight=1.0):
    return HoldingView(
        scheme_id=abs(hash(name)) % 1000,
        scheme_name=name,
        sebi_category="Equity Scheme - Flexi Cap Fund",
        asset_class="EQUITY",
        plan="DIRECT",
        option=option,
        weight=weight,
    )


def _ctx(holdings, disposal_count=0):
    return Context(
        holdings=holdings,
        asset_class_weights={"EQUITY": 1.0},
        disposal_count=disposal_count,
        has_target=False,
    )


def test_idcw_rule_silent_when_every_holding_is_growth():
    """The real portfolio holds no IDCW options and received no dividends."""
    assert idcw_inefficiency_rule(_ctx([_holding("A", "Growth Option")])) == []


def test_idcw_rule_fires_on_an_idcw_holding():
    findings = idcw_inefficiency_rule(_ctx([_holding("A", "Quarterly IDCW Option")]))
    assert len(findings) == 1
    assert findings[0].rule_id == "tax.idcw_inefficiency"


def test_idcw_rule_handles_a_missing_option():
    assert idcw_inefficiency_rule(_ctx([_holding("A", None)])) == []


def test_stcg_rule_silent_without_disposals():
    """The real ledger has zero disposals, so there is no STCG exposure."""
    assert rebalance_stcg_exposure_rule(_ctx([_holding("A", "Growth Option")], 0)) == []


def test_stcg_rule_fires_when_disposals_exist():
    findings = rebalance_stcg_exposure_rule(
        _ctx([_holding("A", "Growth Option")], disposal_count=3)
    )
    assert len(findings) == 1
    assert findings[0].metrics["disposal_count"] == 3.0
