import pytest

from trader_ai.rules.context import Context, HoldingView
from trader_ai.rules.families.diversification import (
    category_duplication_rule,
    low_effective_holdings_rule,
)


def _holding(name, category, weight, asset_class="EQUITY"):
    return HoldingView(
        scheme_id=abs(hash(name)) % 1000,
        scheme_name=name,
        sebi_category=category,
        asset_class=asset_class,
        plan="DIRECT",
        option="Growth Option",
        weight=weight,
    )


def _ctx(holdings):
    weights: dict[str, float] = {}
    for h in holdings:
        weights[h.asset_class] = weights.get(h.asset_class, 0.0) + h.weight
    return Context(
        holdings=holdings,
        asset_class_weights=weights,
        disposal_count=0,
        has_target=False,
    )


def test_duplication_fires_on_repeated_categories():
    ctx = _ctx([
        _holding("A", "Equity Scheme - Sectoral/ Thematic", 0.06),
        _holding("B", "Equity Scheme - Sectoral/ Thematic", 0.06),
        _holding("C", "Equity Scheme - Sectoral/ Thematic", 0.06),
        _holding("D", "Debt Scheme - Gilt Fund", 0.82, "DEBT"),
    ])
    findings = category_duplication_rule(ctx)
    assert len(findings) == 1
    assert findings[0].rule_id == "diversification.category_duplication"
    assert findings[0].metrics["fund_count"] == 3


def test_duplication_is_silent_when_every_category_is_distinct():
    ctx = _ctx([
        _holding("A", "Equity Scheme - Flexi Cap Fund", 0.5),
        _holding("B", "Debt Scheme - Gilt Fund", 0.5, "DEBT"),
    ])
    assert category_duplication_rule(ctx) == []


def test_duplication_severity_rises_with_concentration():
    small = _ctx([
        _holding("A", "Equity Scheme - Flexi Cap Fund", 0.02),
        _holding("B", "Equity Scheme - Flexi Cap Fund", 0.02),
        _holding("C", "Other", 0.96),
    ])
    large = _ctx([
        _holding("A", "Equity Scheme - Flexi Cap Fund", 0.30),
        _holding("B", "Equity Scheme - Flexi Cap Fund", 0.30),
        _holding("C", "Other", 0.40),
    ])
    assert (
        category_duplication_rule(large)[0].severity.rank
        > category_duplication_rule(small)[0].severity.rank
    )


def test_duplication_ignores_holdings_with_no_category():
    ctx = _ctx([_holding("A", None, 0.5), _holding("B", None, 0.5)])
    assert category_duplication_rule(ctx) == []


def test_duplication_subjects_carry_ratios_not_amounts():
    ctx = _ctx([
        _holding("A", "Equity Scheme - Flexi Cap Fund", 0.25),
        _holding("B", "Equity Scheme - Flexi Cap Fund", 0.25),
        _holding("C", "Other", 0.50),
    ])
    finding = category_duplication_rule(ctx)[0]
    for subject in finding.subjects:
        assert subject.weight is None or 0.0 <= subject.weight <= 1.0


def test_low_effective_holdings_fires_when_concentrated():
    ctx = _ctx(
        [_holding("Big", "Cat A", 0.9)]
        + [_holding(f"S{i}", f"Cat {i}", 0.0111) for i in range(9)]
    )
    findings = low_effective_holdings_rule(ctx)
    assert len(findings) == 1
    assert findings[0].metrics["effective_holdings"] < 2.0
    assert findings[0].metrics["nominal_holdings"] == 10


def test_low_effective_holdings_is_silent_when_well_spread():
    ctx = _ctx([_holding(f"S{i}", f"Cat {i}", 0.1) for i in range(10)])
    assert low_effective_holdings_rule(ctx) == []


def test_low_effective_holdings_silent_on_an_empty_portfolio():
    assert low_effective_holdings_rule(_ctx([])) == []


def test_every_finding_has_a_real_citation():
    from trader_ai.rules.citations import citation

    ctx = _ctx([
        _holding("A", "Equity Scheme - Flexi Cap Fund", 0.25),
        _holding("B", "Equity Scheme - Flexi Cap Fund", 0.25),
        _holding("C", "Other", 0.50),
    ])
    for finding in category_duplication_rule(ctx):
        citation(finding.citation_key)  # raises if unknown
