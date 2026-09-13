import pytest

from trader_ai.analytics.allocation import compute_drift


def test_perfectly_on_target_has_zero_drift():
    result = compute_drift(
        values_by_class={"EQUITY": 6000.0, "DEBT": 4000.0},
        targets={"EQUITY": 0.6, "DEBT": 0.4},
    )
    by_class = {d.asset_class: d for d in result.drifts}
    assert by_class["EQUITY"].drift == pytest.approx(0.0)
    assert by_class["DEBT"].drift == pytest.approx(0.0)
    assert result.unclassified_value == 0.0


def test_overweight_equity_reports_positive_drift():
    result = compute_drift(
        values_by_class={"EQUITY": 8000.0, "DEBT": 2000.0},
        targets={"EQUITY": 0.6, "DEBT": 0.4},
    )
    by_class = {d.asset_class: d for d in result.drifts}
    assert by_class["EQUITY"].current_weight == pytest.approx(0.8)
    assert by_class["EQUITY"].drift == pytest.approx(0.2)
    assert by_class["DEBT"].drift == pytest.approx(-0.2)


def test_target_class_with_no_holdings_still_reported():
    result = compute_drift(
        values_by_class={"EQUITY": 10000.0},
        targets={"EQUITY": 0.8, "GOLD": 0.2},
    )
    by_class = {d.asset_class: d for d in result.drifts}
    assert by_class["GOLD"].current_value == 0.0
    assert by_class["GOLD"].drift == pytest.approx(-0.2)


def test_held_class_with_no_target_is_reported_as_full_overweight():
    result = compute_drift(
        values_by_class={"EQUITY": 5000.0, "GOLD": 5000.0},
        targets={"EQUITY": 1.0},
    )
    by_class = {d.asset_class: d for d in result.drifts}
    assert by_class["GOLD"].target_weight == 0.0
    assert by_class["GOLD"].drift == pytest.approx(0.5)


def test_unclassified_is_flagged_and_excluded_from_weights():
    result = compute_drift(
        values_by_class={"EQUITY": 6000.0, "DEBT": 4000.0, "UNCLASSIFIED": 1000.0},
        targets={"EQUITY": 0.6, "DEBT": 0.4},
    )
    assert result.unclassified_value == pytest.approx(1000.0)
    by_class = {d.asset_class: d for d in result.drifts}
    # Weights are computed over classified value only (10000, not 11000).
    assert by_class["EQUITY"].current_weight == pytest.approx(0.6)
    assert "UNCLASSIFIED" not in by_class


def test_empty_portfolio_returns_no_drifts():
    result = compute_drift(values_by_class={}, targets={})
    assert result.drifts == []
    assert result.total_value == 0.0


def test_zero_value_portfolio_does_not_divide_by_zero():
    result = compute_drift(
        values_by_class={"EQUITY": 0.0},
        targets={"EQUITY": 1.0},
    )
    by_class = {d.asset_class: d for d in result.drifts}
    assert by_class["EQUITY"].current_weight == 0.0
    assert by_class["EQUITY"].drift == pytest.approx(-1.0)
