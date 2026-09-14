import pytest

from trader_ai.analytics.diversification import (
    category_duplication,
    effective_holdings,
    herfindahl,
)


def test_herfindahl_of_a_single_holding_is_one():
    assert herfindahl([1.0]) == pytest.approx(1.0)


def test_herfindahl_of_four_equal_holdings():
    assert herfindahl([0.25, 0.25, 0.25, 0.25]) == pytest.approx(0.25)


def test_herfindahl_normalises_unnormalised_weights():
    # Raw values, not fractions: 2500 each of four is still 0.25.
    assert herfindahl([2500, 2500, 2500, 2500]) == pytest.approx(0.25)


def test_herfindahl_of_empty_is_zero():
    assert herfindahl([]) == 0.0


def test_herfindahl_ignores_zero_and_negative_values():
    assert herfindahl([1.0, 0.0]) == pytest.approx(1.0)


def test_effective_holdings_equals_count_when_equally_weighted():
    assert effective_holdings([0.25, 0.25, 0.25, 0.25]) == pytest.approx(4.0)


def test_effective_holdings_is_far_below_count_when_concentrated():
    # Ten funds, but one is 90% of the portfolio.
    weights = [0.9] + [0.011] * 9
    assert effective_holdings(weights) < 2.0


def test_effective_holdings_of_empty_is_zero():
    assert effective_holdings([]) == 0.0


def test_category_duplication_flags_repeated_categories():
    # Four flexi-cap funds is the classic error the literature names.
    holdings = [
        ("Fund A", "Equity Scheme - Flexi Cap Fund", 1000.0),
        ("Fund B", "Equity Scheme - Flexi Cap Fund", 1000.0),
        ("Fund C", "Equity Scheme - Flexi Cap Fund", 1000.0),
        ("Fund D", "Debt Scheme - Gilt Fund", 1000.0),
    ]
    dupes = category_duplication(holdings)
    assert dupes["Equity Scheme - Flexi Cap Fund"].count == 3
    assert dupes["Equity Scheme - Flexi Cap Fund"].value == pytest.approx(3000.0)
    assert "Debt Scheme - Gilt Fund" not in dupes  # a single fund is not duplication


def test_category_duplication_ignores_unknown_categories():
    holdings = [("A", None, 1000.0), ("B", None, 1000.0)]
    assert category_duplication(holdings) == {}


def test_category_duplication_of_empty_portfolio():
    assert category_duplication([]) == {}
