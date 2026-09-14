from datetime import date

import pytest

from trader_ai.analytics.consistency import rolling_returns, summarise
from trader_ai.analytics.nav_series import NavPoint


def _series(pairs):
    return [NavPoint(nav_date=d, nav=n) for d, n in pairs]


def test_rolling_returns_over_a_steady_series():
    # Doubling each year for three years, sampled yearly.
    points = _series(
        [
            (date(2023, 1, 4), 100.0),
            (date(2024, 1, 3), 200.0),
            (date(2025, 1, 1), 400.0),
            (date(2026, 1, 7), 800.0),
        ]
    )
    windows = rolling_returns(points, window_days=365)
    assert len(windows) == 3
    assert all(w == pytest.approx(1.0, abs=0.05) for w in windows)


def test_rolling_returns_empty_when_series_shorter_than_window():
    points = _series([(date(2025, 1, 1), 100.0), (date(2025, 6, 1), 110.0)])
    assert rolling_returns(points, window_days=365) == []


def test_rolling_returns_empty_for_empty_series():
    assert rolling_returns([], window_days=365) == []


def test_rolling_returns_skips_zero_nav_start_points():
    # A side-pocketed point would divide by zero.
    points = _series(
        [
            (date(2024, 1, 3), 0.0),
            (date(2025, 1, 1), 100.0),
            (date(2026, 1, 7), 150.0),
        ]
    )
    windows = rolling_returns(points, window_days=365)
    assert all(w is not None for w in windows)
    assert len(windows) == 1  # only the 2025->2026 window is computable


def test_summarise_reports_distribution_not_a_single_number():
    stats = summarise([0.10, 0.20, 0.30, -0.05])
    assert stats.count == 4
    assert stats.best == pytest.approx(0.30)
    assert stats.worst == pytest.approx(-0.05)
    assert stats.median == pytest.approx(0.15)
    assert stats.share_negative == pytest.approx(0.25)


def test_summarise_of_empty_is_unavailable():
    stats = summarise([])
    assert stats.count == 0
    assert stats.median is None


def test_summarise_share_negative_is_zero_when_all_positive():
    assert summarise([0.1, 0.2]).share_negative == pytest.approx(0.0)


def test_summarise_handles_a_single_window():
    stats = summarise([0.12])
    assert stats.count == 1
    assert stats.median == pytest.approx(0.12)
    assert stats.best == stats.worst == pytest.approx(0.12)
