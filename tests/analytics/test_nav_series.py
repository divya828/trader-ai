from datetime import date

import pytest

from trader_ai.analytics.nav_series import cagr, nav_on_or_before, nav_series
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
    for day, value in (
        ("2024-01-03", 100.0),
        ("2024-06-05", 110.0),
        ("2025-01-01", 120.0),
        ("2026-01-07", 150.0),
    ):
        con.execute(
            "INSERT INTO md_nav(amfi_code, nav_date, nav) VALUES ('100001', ?, ?)",
            (day, value),
        )
    con.commit()
    yield con
    con.close()


def test_nav_series_returns_points_in_date_order(db2):
    points = nav_series(db2, scheme_id=1)
    assert [p.nav_date for p in points] == [
        date(2024, 1, 3),
        date(2024, 6, 5),
        date(2025, 1, 1),
        date(2026, 1, 7),
    ]


def test_nav_series_respects_a_window(db2):
    points = nav_series(db2, scheme_id=1, start=date(2024, 6, 1), end=date(2025, 6, 1))
    assert [p.nav for p in points] == [110.0, 120.0]


def test_nav_series_is_empty_for_a_scheme_with_no_cached_nav(db2):
    db2.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name, isin)"
        " VALUES (2, 1, 'Other', 'INF999X99999')"
    )
    db2.commit()
    assert nav_series(db2, scheme_id=2) == []


def test_nav_series_excludes_zero_nav_points(db2):
    """241 rows in the live file have NAV exactly 0.0 (side-pocketed debt).

    They are real data and are cached, but a return calculation over them
    divides by zero, so the series helper filters them out.
    """
    db2.execute(
        "INSERT INTO md_nav(amfi_code, nav_date, nav) VALUES ('100001','2025-06-01',0.0)"
    )
    db2.commit()
    assert all(p.nav > 0 for p in nav_series(db2, scheme_id=1))


def test_nav_series_matches_on_the_reinvest_isin_too(db2):
    db2.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name, isin)"
        " VALUES (3, 1, 'Reinvest Fund', 'INF001A01037')"
    )
    db2.execute(
        "INSERT INTO md_schemes(amfi_code, isin_growth, isin_reinvest, scheme_name,"
        " asset_class, last_seen) VALUES ('100002','INF001A01029','INF001A01037',"
        " 'Reinvest Fund','EQUITY','2026-01-01')"
    )
    db2.execute(
        "INSERT INTO md_nav(amfi_code, nav_date, nav) VALUES ('100002','2025-01-01',55.0)"
    )
    db2.commit()
    assert [p.nav for p in nav_series(db2, scheme_id=3)] == [55.0]


def test_nav_on_or_before_finds_the_latest_earlier_point(db2):
    point = nav_on_or_before(db2, scheme_id=1, when=date(2024, 12, 31))
    assert point is not None
    assert point.nav == 110.0


def test_nav_on_or_before_returns_none_when_nothing_precedes(db2):
    assert nav_on_or_before(db2, scheme_id=1, when=date(2023, 1, 1)) is None


def test_cagr_doubling_over_one_year():
    assert cagr(100.0, 200.0, 365) == pytest.approx(1.0, abs=1e-6)


def test_cagr_flat_is_zero():
    assert cagr(100.0, 100.0, 365) == pytest.approx(0.0, abs=1e-9)


def test_cagr_over_multiple_years():
    # 100 -> 121 over 2 years is 10% a year.
    assert cagr(100.0, 121.0, 730) == pytest.approx(0.1, abs=1e-4)


def test_cagr_rejects_zero_start_nav():
    # Side-pocketed schemes have NAV 0.0; dividing by it is undefined.
    assert cagr(0.0, 100.0, 365) is None


def test_cagr_rejects_nonpositive_days():
    assert cagr(100.0, 110.0, 0) is None
    assert cagr(100.0, 110.0, -5) is None


def test_cagr_handles_a_total_loss():
    assert cagr(100.0, 0.0, 365) == pytest.approx(-1.0, abs=1e-9)
