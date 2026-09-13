from datetime import date

import pytest

from trader_ai.analytics.tax_lots import (
    Acquisition,
    Disposal,
    classify,
    match_fifo,
)


def test_single_lot_fully_consumed():
    acquisitions = [Acquisition(date(2020, 1, 1), units=100.0, cost_per_unit=10.0)]
    disposals = [Disposal(date(2022, 1, 1), units=100.0, price_per_unit=15.0)]
    result = match_fifo(acquisitions, disposals, asset_class="EQUITY")
    assert len(result) == 1
    assert result[0].units_disposed == pytest.approx(100.0)
    assert result[0].cost_basis == pytest.approx(1000.0)
    assert result[0].proceeds == pytest.approx(1500.0)
    assert result[0].gain == pytest.approx(500.0)
    assert result[0].classification == "LTCG"


def test_disposal_spans_two_lots_in_fifo_order():
    acquisitions = [
        Acquisition(date(2020, 1, 1), units=100.0, cost_per_unit=10.0),
        Acquisition(date(2021, 1, 1), units=100.0, cost_per_unit=20.0),
    ]
    disposals = [Disposal(date(2023, 1, 1), units=150.0, price_per_unit=30.0)]
    result = match_fifo(acquisitions, disposals, asset_class="EQUITY")
    assert len(result) == 2
    # Oldest lot consumed first, in full.
    assert result[0].units_disposed == pytest.approx(100.0)
    assert result[0].cost_basis == pytest.approx(1000.0)
    assert result[0].gain == pytest.approx(2000.0)
    # Remainder from the second lot.
    assert result[1].units_disposed == pytest.approx(50.0)
    assert result[1].cost_basis == pytest.approx(1000.0)
    assert result[1].gain == pytest.approx(500.0)


def test_partial_lot_leaves_remainder_for_later_disposal():
    acquisitions = [Acquisition(date(2020, 1, 1), units=100.0, cost_per_unit=10.0)]
    disposals = [
        Disposal(date(2022, 1, 1), units=40.0, price_per_unit=15.0),
        Disposal(date(2022, 6, 1), units=60.0, price_per_unit=20.0),
    ]
    result = match_fifo(acquisitions, disposals, asset_class="EQUITY")
    assert len(result) == 2
    assert result[0].units_disposed == pytest.approx(40.0)
    assert result[0].gain == pytest.approx(200.0)
    assert result[1].units_disposed == pytest.approx(60.0)
    assert result[1].gain == pytest.approx(600.0)


def test_disposal_exceeding_holdings_raises():
    acquisitions = [Acquisition(date(2020, 1, 1), units=10.0, cost_per_unit=10.0)]
    disposals = [Disposal(date(2022, 1, 1), units=50.0, price_per_unit=15.0)]
    with pytest.raises(ValueError, match="exceeds available units"):
        match_fifo(acquisitions, disposals, asset_class="EQUITY")


def test_acquisitions_are_sorted_before_matching():
    acquisitions = [
        Acquisition(date(2021, 1, 1), units=100.0, cost_per_unit=20.0),
        Acquisition(date(2020, 1, 1), units=100.0, cost_per_unit=10.0),
    ]
    disposals = [Disposal(date(2023, 1, 1), units=100.0, price_per_unit=30.0)]
    result = match_fifo(acquisitions, disposals, asset_class="EQUITY")
    # The 2020 lot is oldest and must be consumed first.
    assert result[0].acquired_date == date(2020, 1, 1)
    assert result[0].cost_basis == pytest.approx(1000.0)


def test_loss_is_reported_as_negative_gain():
    acquisitions = [Acquisition(date(2023, 1, 1), units=100.0, cost_per_unit=50.0)]
    disposals = [Disposal(date(2023, 6, 1), units=100.0, price_per_unit=30.0)]
    result = match_fifo(acquisitions, disposals, asset_class="EQUITY")
    assert result[0].gain == pytest.approx(-2000.0)
    assert result[0].classification == "STCG"


@pytest.mark.parametrize(
    "asset_class, acquired, disposed, expected",
    [
        # Equity: 365-day boundary.
        ("EQUITY", date(2023, 1, 1), date(2023, 12, 31), "STCG"),  # 364 days
        ("EQUITY", date(2023, 1, 1), date(2024, 1, 1), "STCG"),    # exactly 365
        ("EQUITY", date(2023, 1, 1), date(2024, 1, 2), "LTCG"),    # 366 days
        # Debt acquired pre-2023-04-01: 1095-day boundary.
        ("DEBT", date(2023, 3, 31), date(2026, 3, 30), "STCG"),    # 1095 days
        ("DEBT", date(2023, 3, 31), date(2026, 3, 31), "LTCG"),    # 1096 days
        # Debt acquired on/after 2023-04-01: always STCG.
        ("DEBT", date(2023, 4, 1), date(2030, 1, 1), "STCG"),
    ],
)
def test_classification_boundaries(asset_class, acquired, disposed, expected):
    assert classify(asset_class, acquired, disposed) == expected


def test_no_disposals_returns_empty():
    acquisitions = [Acquisition(date(2020, 1, 1), units=100.0, cost_per_unit=10.0)]
    assert match_fifo(acquisitions, [], asset_class="EQUITY") == []
