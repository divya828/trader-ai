from datetime import date

import pytest

from trader_ai.db.connection import apply_schema, apply_schema_v02, connect
from trader_ai.marketdata.history import (
    SPARSE_ROW_THRESHOLD,
    backfill_history,
    weekly_sample_dates,
)

HISTORY_HEADER = (
    "Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;"
    "ISIN Div Reinvestment;Net Asset Value;Date"
)


def _history_text(day: str, rows: int = 5) -> str:
    lines = [
        HISTORY_HEADER,
        "",
        "Open Ended Schemes(Equity Scheme - Flexi Cap Fund)",
        "",
        "Acme Mutual Fund",
        "",
    ]
    for i in range(rows):
        lines.append(
            f"10000{i};Acme Fund {i};Direct Plan;Growth Option;"
            f"INF001A0101{i};-;{25 + i}.0000;{day}"
        )
    return "\n".join(lines) + "\n"


@pytest.fixture
def db2():
    con = connect(":memory:")
    apply_schema(con)
    apply_schema_v02(con)
    con.execute("INSERT INTO folios(folio_id, folio_number, amc) VALUES (1,'F1','Acme')")
    con.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name, isin)"
        " VALUES (1, 1, 'Acme Fund 0', 'INF001A01010')"
    )
    con.commit()
    yield con
    con.close()


def test_weekly_sample_dates_are_seven_days_apart():
    days = weekly_sample_dates(date(2026, 1, 7), date(2026, 2, 4))
    assert days == [
        date(2026, 1, 7),
        date(2026, 1, 14),
        date(2026, 1, 21),
        date(2026, 1, 28),
        date(2026, 2, 4),
    ]


def test_weekly_sample_dates_land_on_wednesdays():
    # Weekends return ~600 rows instead of ~8,700, so sampling must avoid them.
    days = weekly_sample_dates(date(2026, 1, 1), date(2026, 3, 1))
    assert all(d.weekday() == 2 for d in days), [d.strftime("%a") for d in days]


def test_weekly_sample_dates_empty_for_reversed_window():
    assert weekly_sample_dates(date(2026, 2, 1), date(2026, 1, 1)) == []


def test_weekly_sample_dates_never_exceeds_end():
    days = weekly_sample_dates(date(2026, 1, 7), date(2026, 1, 20))
    assert all(d <= date(2026, 1, 20) for d in days)


def test_backfill_caches_nav_for_held_isins(db2):
    fetched = []

    def fake_fetch(start, end):
        fetched.append((start, end))
        return _history_text(start.strftime("%d-%b-%Y"))

    result = backfill_history(
        db2, date(2026, 1, 7), date(2026, 1, 21), fetch=fake_fetch, min_rows=1
    )
    assert result.days_fetched == 3
    # Only the held ISIN is cached, not all five schemes in the file.
    assert db2.execute("SELECT COUNT(*) FROM md_nav").fetchone()[0] == 3


def test_backfill_skips_already_cached_ranges(db2):
    def fake_fetch(start, end):
        return _history_text(start.strftime("%d-%b-%Y"))

    backfill_history(
        db2, date(2026, 1, 7), date(2026, 1, 21), fetch=fake_fetch, min_rows=1
    )
    second = backfill_history(
        db2, date(2026, 1, 7), date(2026, 1, 21), fetch=fake_fetch, min_rows=1
    )
    assert second.days_fetched == 0
    assert second.days_skipped_cached == 3


def test_backfill_records_sparse_days_without_caching_them(db2):
    """A weekend or holiday returns ~600 rows instead of ~8,700.

    Caching those would leave gaps that look like real data.
    """

    def sparse_fetch(start, end):
        return _history_text(start.strftime("%d-%b-%Y"), rows=1)

    # No min_rows override: this exercises the real SPARSE_ROW_THRESHOLD.
    result = backfill_history(
        db2, date(2026, 1, 7), date(2026, 1, 7), fetch=sparse_fetch
    )
    assert result.days_sparse == 1
    assert result.days_fetched == 0


def test_sparse_threshold_is_low_enough_for_reduced_trading_days():
    # 2026-08-26 returned 5,761 rows -- reduced but usable. Only genuine
    # non-trading days (~600) must be rejected.
    assert SPARSE_ROW_THRESHOLD < 5000
    assert SPARSE_ROW_THRESHOLD > 1000


def test_backfill_makes_no_network_call_when_fetch_injected(db2):
    from trader_ai.marketdata import amfi_client

    original = amfi_client.urllib.request.urlopen

    def explode(*args, **kwargs):  # pragma: no cover
        raise AssertionError("backfill must not perform HTTP when fetch injected")

    amfi_client.urllib.request.urlopen = explode
    try:
        backfill_history(
            db2,
            date(2026, 1, 7),
            date(2026, 1, 7),
            fetch=lambda s, e: _history_text(s.strftime("%d-%b-%Y")),
            min_rows=1,
        )
    finally:
        amfi_client.urllib.request.urlopen = original


def test_backfill_with_no_ledger_isins_caches_nothing(db2):
    db2.execute("DELETE FROM schemes")
    db2.commit()
    result = backfill_history(
        db2,
        date(2026, 1, 7),
        date(2026, 1, 7),
        fetch=lambda s, e: _history_text(s.strftime("%d-%b-%Y")),
        min_rows=1,
    )
    assert db2.execute("SELECT COUNT(*) FROM md_nav").fetchone()[0] == 0
    assert result.days_fetched == 1  # the day was fetched, nothing matched


def test_min_rows_defaults_to_the_production_threshold():
    """The test-only min_rows override must not weaken production.

    Tests pass a small min_rows so a compact fixture is not rejected as
    sparse. The default must remain the real threshold, or every caller
    silently loses weekend rejection.
    """
    import inspect

    signature = inspect.signature(backfill_history)
    assert signature.parameters["min_rows"].default == SPARSE_ROW_THRESHOLD


def test_a_weekend_sized_response_is_sparse_at_the_default_threshold(db2):
    """~600 rows is what a weekend actually returns; it must be rejected."""
    result = backfill_history(
        db2,
        date(2026, 1, 7),
        date(2026, 1, 7),
        fetch=lambda s, e: _history_text(s.strftime("%d-%b-%Y"), rows=600),
    )
    assert result.days_sparse == 1
    assert result.days_fetched == 0


def test_a_reduced_trading_day_is_not_sparse_at_the_default_threshold(db2):
    """2026-08-26 returned 5,761 rows -- real data, must be kept.

    Building 5,761 fixture rows is wasteful, so assert the boundary directly.
    """
    assert 5761 >= SPARSE_ROW_THRESHOLD
    assert 601 < SPARSE_ROW_THRESHOLD
