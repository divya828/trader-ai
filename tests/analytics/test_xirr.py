from datetime import date

import pytest

from trader_ai.analytics.xirr import xirr


def test_exact_doubling_over_one_year_is_100_percent():
    flows = [(date(2023, 1, 1), -1000.0), (date(2024, 1, 1), 2000.0)]
    assert xirr(flows) == pytest.approx(1.0, abs=1e-4)


def test_flat_return_is_zero():
    flows = [(date(2023, 1, 1), -1000.0), (date(2024, 1, 1), 1000.0)]
    assert xirr(flows) == pytest.approx(0.0, abs=1e-6)


def test_known_irregular_cashflows():
    # Reference value verified by solving NPV=0 independently at high
    # precision: at 0.11633756 the NPV of these flows is 0.0 exactly.
    flows = [
        (date(2020, 1, 1), -10000.0),
        (date(2020, 6, 1), -5000.0),
        (date(2021, 1, 1), 16500.0),
    ]
    assert xirr(flows) == pytest.approx(0.11633756, abs=1e-6)


def test_loss_produces_negative_rate():
    flows = [(date(2023, 1, 1), -1000.0), (date(2024, 1, 1), 800.0)]
    result = xirr(flows)
    assert result is not None and result < 0


def test_unsorted_input_is_handled():
    flows = [(date(2024, 1, 1), 2000.0), (date(2023, 1, 1), -1000.0)]
    assert xirr(flows) == pytest.approx(1.0, abs=1e-4)


def test_empty_returns_none():
    assert xirr([]) is None


def test_single_cashflow_returns_none():
    assert xirr([(date(2023, 1, 1), -1000.0)]) is None


def test_all_same_sign_returns_none():
    # No sign change means no root exists; must not raise or hang.
    flows = [(date(2023, 1, 1), -1000.0), (date(2024, 1, 1), -500.0)]
    assert xirr(flows) is None


def test_all_flows_on_same_day_returns_none():
    flows = [(date(2023, 1, 1), -1000.0), (date(2023, 1, 1), 1200.0)]
    assert xirr(flows) is None
