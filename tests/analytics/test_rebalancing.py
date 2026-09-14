from datetime import date

import pytest

from trader_ai.analytics.rebalancing import (
    ABSOLUTE_BAND,
    RELATIVE_BAND,
    band_breaches,
    tax_aware_disposal,
)


def test_no_breach_when_on_target():
    breaches = band_breaches({"EQUITY": 0.60, "DEBT": 0.40}, {"EQUITY": 0.60, "DEBT": 0.40})
    assert breaches == []


def test_absolute_band_breach():
    # 5 percentage points over target trips the absolute band.
    breaches = band_breaches({"EQUITY": 0.66, "DEBT": 0.34}, {"EQUITY": 0.60, "DEBT": 0.40})
    kinds = {b.asset_class: b for b in breaches}
    assert kinds["EQUITY"].breached_absolute is True


def test_relative_band_breach_on_a_small_target():
    # 25% relative on a 4% target is 1 point -- the relative band binds first.
    breaches = band_breaches({"GOLD": 0.055, "EQUITY": 0.945}, {"GOLD": 0.04, "EQUITY": 0.96})
    gold = {b.asset_class: b for b in breaches}["GOLD"]
    assert gold.breached_relative is True
    assert gold.breached_absolute is False


def test_drift_inside_both_bands_is_not_a_breach():
    breaches = band_breaches({"EQUITY": 0.62, "DEBT": 0.38}, {"EQUITY": 0.60, "DEBT": 0.40})
    assert breaches == []


def test_underweight_breach_is_reported_too():
    breaches = band_breaches({"EQUITY": 0.50, "DEBT": 0.50}, {"EQUITY": 0.60, "DEBT": 0.40})
    equity = {b.asset_class: b for b in breaches}["EQUITY"]
    assert equity.drift < 0
    assert equity.breached_absolute is True


def test_missing_asset_class_counts_as_zero_weight():
    breaches = band_breaches({"EQUITY": 1.0}, {"EQUITY": 0.60, "DEBT": 0.40})
    debt = {b.asset_class: b for b in breaches}["DEBT"]
    assert debt.current_weight == pytest.approx(0.0)
    assert debt.breached_absolute is True


def test_bands_are_the_daryanani_values():
    assert ABSOLUTE_BAND == pytest.approx(0.05)
    assert RELATIVE_BAND == pytest.approx(0.25)


def test_tax_aware_disposal_classifies_the_lots_it_would_sell():
    from trader_ai.analytics.tax_lots import Acquisition

    acquisitions = [
        Acquisition(date(2020, 1, 1), units=100.0, cost_per_unit=10.0),
        Acquisition(date(2026, 1, 1), units=100.0, cost_per_unit=20.0),
    ]
    result = tax_aware_disposal(
        acquisitions,
        units_to_sell=150.0,
        price_per_unit=30.0,
        on=date(2026, 6, 1),
        asset_class="EQUITY",
    )
    assert len(result) == 2
    assert result[0].classification == "LTCG"   # the 2020 lot
    assert result[1].classification == "STCG"   # the 2026 lot
    assert sum(r.units_disposed for r in result) == pytest.approx(150.0)


def test_tax_aware_disposal_raises_when_selling_more_than_held():
    from trader_ai.analytics.tax_lots import Acquisition

    with pytest.raises(ValueError, match="exceeds available units"):
        tax_aware_disposal(
            [Acquisition(date(2020, 1, 1), units=10.0, cost_per_unit=10.0)],
            units_to_sell=50.0,
            price_per_unit=30.0,
            on=date(2026, 6, 1),
            asset_class="EQUITY",
        )


def test_tax_aware_disposal_of_zero_units_returns_nothing():
    from trader_ai.analytics.tax_lots import Acquisition

    result = tax_aware_disposal(
        [Acquisition(date(2020, 1, 1), units=10.0, cost_per_unit=10.0)],
        units_to_sell=0.0,
        price_per_unit=30.0,
        on=date(2026, 6, 1),
        asset_class="EQUITY",
    )
    assert result == []
