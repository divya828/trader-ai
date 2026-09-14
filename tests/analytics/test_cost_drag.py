import pytest

from trader_ai.analytics.cost_drag import portfolio_cost_drag
from trader_ai.db.connection import apply_schema, apply_schema_v02, connect


@pytest.fixture
def db2():
    con = connect(":memory:")
    apply_schema(con)
    apply_schema_v02(con)
    con.execute("INSERT INTO folios(folio_id, folio_number, amc) VALUES (1,'F1','A')")
    con.execute("INSERT INTO import_runs(import_run_id, source_file) VALUES (1,'a.pdf')")
    con.commit()
    yield con
    con.close()


def _pair(con, *, regular_isin, direct_isin, amc="Acme", name="Acme Flexi Cap Fund"):
    """A Regular scheme and its Direct sibling, as AMFI reports them."""
    con.execute(
        "INSERT INTO md_schemes(amfi_code, isin_growth, scheme_name, amc, plan,"
        " option, asset_class, last_seen) VALUES ('R1', ?, ?, ?, 'REGULAR',"
        " 'Growth Option', 'EQUITY', '2026-01-01')",
        (regular_isin, name, amc),
    )
    con.execute(
        "INSERT INTO md_schemes(amfi_code, isin_growth, scheme_name, amc, plan,"
        " option, asset_class, last_seen) VALUES ('D1', ?, ?, ?, 'DIRECT',"
        " 'Growth Option', 'EQUITY', '2026-01-01')",
        (direct_isin, name, amc),
    )


def _navs(con, code, points):
    for day, value in points:
        con.execute(
            "INSERT INTO md_nav(amfi_code, nav_date, nav) VALUES (?, ?, ?)",
            (code, day, value),
        )


def _hold(con, scheme_id, isin, value, name="Acme Flexi Cap Fund"):
    con.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name, isin)"
        " VALUES (?, 1, ?, ?)",
        (scheme_id, name, isin),
    )
    con.execute(
        "INSERT INTO holdings_snapshot(import_run_id, scheme_id, as_of_date, units,"
        " price, value) VALUES (1, ?, '2026-01-07', 100, ?, ?)",
        (scheme_id, value / 100, value),
    )


def test_regular_holding_with_a_direct_sibling_shows_drag(db2):
    _pair(db2, regular_isin="INF001R", direct_isin="INF001D")
    _navs(db2, "R1", [("2024-01-03", 100.0), ("2026-01-07", 120.0)])
    _navs(db2, "D1", [("2024-01-03", 100.0), ("2026-01-07", 130.0)])
    _hold(db2, 1, "INF001R", 12000.0)
    db2.commit()
    report = portfolio_cost_drag(db2)
    assert report.drag.available
    assert report.drag.value > 0  # the Direct plan compounded faster
    assert report.covered_value == pytest.approx(12000.0)
    assert report.uncovered_value == pytest.approx(0.0)


def test_direct_holding_is_covered_with_zero_drag(db2):
    _pair(db2, regular_isin="INF001R", direct_isin="INF001D")
    _navs(db2, "D1", [("2024-01-03", 100.0), ("2026-01-07", 130.0)])
    _hold(db2, 1, "INF001D", 13000.0)
    db2.commit()
    report = portfolio_cost_drag(db2)
    assert report.covered_value == pytest.approx(13000.0)
    assert report.drag.available
    assert report.drag.value == pytest.approx(0.0)


def test_etf_holding_is_excluded_as_not_applicable(db2):
    db2.execute(
        "INSERT INTO md_schemes(amfi_code, isin_growth, scheme_name, plan, is_etf,"
        " asset_class, last_seen) VALUES ('E1','INF001E','Acme Nifty ETF',"
        " 'NOT_APPLICABLE', 1, 'EQUITY','2026-01-01')"
    )
    _hold(db2, 1, "INF001E", 5000.0, name="Acme Nifty ETF")
    db2.commit()
    report = portfolio_cost_drag(db2)
    assert report.uncovered_value == pytest.approx(5000.0)
    assert report.exclusions["NOT_APPLICABLE"] == pytest.approx(5000.0)


def test_unknown_plan_holding_is_excluded_with_its_own_reason(db2):
    db2.execute(
        "INSERT INTO md_schemes(amfi_code, isin_growth, scheme_name, plan,"
        " asset_class, last_seen) VALUES ('U1','INF001U','Mystery Fund',"
        " 'UNKNOWN','EQUITY','2026-01-01')"
    )
    _hold(db2, 1, "INF001U", 7000.0, name="Mystery Fund")
    db2.commit()
    report = portfolio_cost_drag(db2)
    assert report.exclusions["UNKNOWN"] == pytest.approx(7000.0)


def test_regular_without_a_direct_sibling_is_excluded_as_no_sibling(db2):
    db2.execute(
        "INSERT INTO md_schemes(amfi_code, isin_growth, scheme_name, amc, plan,"
        " option, asset_class, last_seen) VALUES ('R9','INF009R','Orphan Fund',"
        " 'Acme','REGULAR','Growth Option','EQUITY','2026-01-01')"
    )
    _hold(db2, 1, "INF009R", 4000.0, name="Orphan Fund")
    db2.commit()
    report = portfolio_cost_drag(db2)
    assert report.exclusions["NO_SIBLING"] == pytest.approx(4000.0)


def test_coverage_ratio_is_reported(db2):
    _pair(db2, regular_isin="INF001R", direct_isin="INF001D")
    _navs(db2, "R1", [("2024-01-03", 100.0), ("2026-01-07", 120.0)])
    _navs(db2, "D1", [("2024-01-03", 100.0), ("2026-01-07", 130.0)])
    _hold(db2, 1, "INF001R", 6000.0)
    db2.execute(
        "INSERT INTO md_schemes(amfi_code, isin_growth, scheme_name, plan,"
        " asset_class, last_seen) VALUES ('U1','INF001U','Mystery','UNKNOWN',"
        " 'EQUITY','2026-01-01')"
    )
    _hold(db2, 2, "INF001U", 2000.0, name="Mystery")
    db2.commit()
    report = portfolio_cost_drag(db2)
    assert report.coverage_ratio == pytest.approx(0.75)


def test_drag_is_unavailable_when_nothing_is_covered(db2):
    db2.execute(
        "INSERT INTO md_schemes(amfi_code, isin_growth, scheme_name, plan,"
        " asset_class, last_seen) VALUES ('U1','INF001U','Mystery','UNKNOWN',"
        " 'EQUITY','2026-01-01')"
    )
    _hold(db2, 1, "INF001U", 9000.0, name="Mystery")
    db2.commit()
    report = portfolio_cost_drag(db2)
    assert not report.drag.available
    assert report.coverage_ratio == pytest.approx(0.0)


def test_holding_with_no_market_data_is_excluded_with_its_own_reason(db2):
    db2.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name, isin)"
        " VALUES (1, 1, 'Unmatched', 'INF999X')"
    )
    db2.execute(
        "INSERT INTO holdings_snapshot(import_run_id, scheme_id, as_of_date, units,"
        " price, value) VALUES (1, 1, '2026-01-07', 10, 100, 1000)"
    )
    db2.commit()
    report = portfolio_cost_drag(db2)
    assert report.exclusions["NO_MARKET_DATA"] == pytest.approx(1000.0)


def test_conservation_covered_plus_uncovered_equals_total(db2):
    """Every rupee must be either covered or excluded with a reason.

    A hole here means some holdings vanish from the report silently.
    """
    _pair(db2, regular_isin="INF001R", direct_isin="INF001D")
    _navs(db2, "R1", [("2024-01-03", 100.0), ("2026-01-07", 120.0)])
    _navs(db2, "D1", [("2024-01-03", 100.0), ("2026-01-07", 130.0)])
    _hold(db2, 1, "INF001R", 6000.0)
    db2.execute(
        "INSERT INTO md_schemes(amfi_code, isin_growth, scheme_name, plan, is_etf,"
        " asset_class, last_seen) VALUES ('E1','INF001E','ETF','NOT_APPLICABLE',1,"
        " 'EQUITY','2026-01-01')"
    )
    _hold(db2, 2, "INF001E", 2000.0, name="ETF")
    db2.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name, isin)"
        " VALUES (3, 1, 'Unmatched', 'INF999X')"
    )
    db2.execute(
        "INSERT INTO holdings_snapshot(import_run_id, scheme_id, as_of_date, units,"
        " price, value) VALUES (1, 3, '2026-01-07', 10, 100, 1000)"
    )
    db2.commit()
    report = portfolio_cost_drag(db2)
    assert report.covered_value + report.uncovered_value == pytest.approx(9000.0)
    assert sum(report.exclusions.values()) == pytest.approx(report.uncovered_value)
