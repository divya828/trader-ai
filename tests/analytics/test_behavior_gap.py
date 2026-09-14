from datetime import date

import pytest

from trader_ai.analytics.behavior_gap import scheme_behavior_gap
from trader_ai.db.connection import apply_schema, apply_schema_v02, connect


@pytest.fixture
def db2():
    con = connect(":memory:")
    apply_schema(con)
    apply_schema_v02(con)
    con.execute("INSERT INTO folios(folio_id, folio_number, amc) VALUES (1,'F1','A')")
    con.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name, isin)"
        " VALUES (1, 1, 'Fund', 'INF001A01011')"
    )
    con.execute(
        "INSERT INTO md_schemes(amfi_code, isin_growth, scheme_name, asset_class,"
        " last_seen) VALUES ('100001','INF001A01011','Fund','EQUITY','2026-01-01')"
    )
    con.execute("INSERT INTO import_runs(import_run_id, source_file) VALUES (1,'a.pdf')")
    con.commit()
    yield con
    con.close()


def _nav(con, day, value):
    con.execute(
        "INSERT INTO md_nav(amfi_code, nav_date, nav) VALUES ('100001', ?, ?)",
        (day, value),
    )


def _txn(con, day, units, price, amount, kind="PURCHASE", key=None):
    con.execute(
        "INSERT INTO transactions(scheme_id, txn_date, txn_type, units, price,"
        " amount, source_row_hash) VALUES (1, ?, ?, ?, ?, ?, ?)",
        (day, kind, units, price, amount, key or f"{day}-{kind}-{amount}"),
    )


def _holding(con, day, units, price):
    con.execute(
        "INSERT INTO holdings_snapshot(import_run_id, scheme_id, as_of_date, units,"
        " price, value) VALUES (1, 1, ?, ?, ?, ?)",
        (day, units, price, units * price),
    )


def test_no_gap_when_a_single_purchase_is_held(db2):
    # One purchase at the start, held throughout: money-weighted and
    # time-weighted returns coincide, so the gap is ~0.
    _nav(db2, "2024-01-03", 100.0)
    _nav(db2, "2026-01-07", 200.0)
    _txn(db2, "2024-01-03", 100.0, 100.0, 10000.0)
    _holding(db2, "2026-01-07", 100.0, 200.0)
    db2.commit()
    result = scheme_behavior_gap(db2, scheme_id=1)
    assert result.available
    assert result.value == pytest.approx(0.0, abs=0.02)


def test_unavailable_without_nav_coverage(db2):
    _txn(db2, "2024-01-03", 100.0, 100.0, 10000.0)
    _holding(db2, "2026-01-07", 100.0, 200.0)
    db2.commit()
    result = scheme_behavior_gap(db2, scheme_id=1)
    assert not result.available
    assert "nav" in result.reason.lower()


def test_unavailable_with_fewer_than_two_cashflows(db2):
    _nav(db2, "2024-01-03", 100.0)
    _nav(db2, "2026-01-07", 200.0)
    db2.commit()
    result = scheme_behavior_gap(db2, scheme_id=1)
    assert not result.available
    assert "cashflow" in result.reason.lower()


def test_unavailable_when_nav_does_not_span_the_cashflows(db2):
    # NAV starts after the first purchase: the fund's own return over the
    # holding period cannot be computed.
    _nav(db2, "2025-06-01", 150.0)
    _nav(db2, "2026-01-07", 200.0)
    _txn(db2, "2024-01-03", 100.0, 100.0, 10000.0)
    _holding(db2, "2026-01-07", 100.0, 200.0)
    db2.commit()
    result = scheme_behavior_gap(db2, scheme_id=1)
    assert not result.available
    assert "span" in result.reason.lower() or "coverage" in result.reason.lower()


def test_buying_more_before_a_rise_produces_a_positive_gap(db2):
    # Good timing: most money went in just before the NAV doubled.
    _nav(db2, "2024-01-03", 100.0)
    _nav(db2, "2025-01-01", 100.0)
    _nav(db2, "2026-01-07", 200.0)
    _txn(db2, "2024-01-03", 10.0, 100.0, 1000.0, key="a")
    _txn(db2, "2025-01-01", 190.0, 100.0, 19000.0, key="b")
    _holding(db2, "2026-01-07", 200.0, 200.0)
    db2.commit()
    result = scheme_behavior_gap(db2, scheme_id=1)
    assert result.available
    assert result.value > 0


def test_gap_is_reported_as_a_rate_difference(db2):
    _nav(db2, "2024-01-03", 100.0)
    _nav(db2, "2026-01-07", 200.0)
    _txn(db2, "2024-01-03", 100.0, 100.0, 10000.0)
    _holding(db2, "2026-01-07", 100.0, 200.0)
    db2.commit()
    result = scheme_behavior_gap(db2, scheme_id=1)
    # Sanity: a plausible annualised difference, not a raw currency amount.
    assert -2.0 < result.value < 2.0


def test_returns_a_measurement_not_a_bare_none(db2):
    # An unavailable metric must carry a reportable reason.
    result = scheme_behavior_gap(db2, scheme_id=1)
    assert result is not None
    assert hasattr(result, "available")
    assert hasattr(result, "reason")
