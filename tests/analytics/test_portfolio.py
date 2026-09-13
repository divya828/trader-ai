import pytest

from trader_ai.analytics.portfolio import (
    latest_values_by_asset_class,
    portfolio_xirr,
    scheme_cashflows,
    scheme_xirr,
)


def _seed(db):
    db.execute("INSERT INTO folios(folio_id, folio_number, amc) VALUES (1, 'F1', 'HDFC')")
    db.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name, asset_class)"
        " VALUES (1, 1, 'Equity Fund', 'EQUITY')"
    )
    db.execute(
        "INSERT INTO securities(security_id, isin, name, asset_class)"
        " VALUES (1, 'INE002A01018', 'Reliance', 'EQUITY')"
    )
    db.execute("INSERT INTO import_runs(import_run_id, source_file) VALUES (1, 'a.pdf')")
    db.execute(
        "INSERT INTO transactions(scheme_id, txn_date, txn_type, units, price, amount,"
        " source_row_hash) VALUES (1, '2023-01-01', 'PURCHASE', 100, 10, 1000, 'h1')"
    )
    db.execute(
        "INSERT INTO holdings_snapshot(import_run_id, scheme_id, as_of_date, units,"
        " price, value) VALUES (1, 1, '2024-01-01', 100, 20, 2000)"
    )
    db.execute(
        "INSERT INTO holdings_snapshot(import_run_id, security_id, as_of_date, units,"
        " price, value) VALUES (1, 1, '2024-01-01', 10, 100, 1000)"
    )
    db.commit()


def test_scheme_cashflows_signs_purchases_negative(db):
    _seed(db)
    flows = scheme_cashflows(db, scheme_id=1)
    # A purchase is money out, so it must be negative regardless of stored sign.
    assert flows[0][1] == pytest.approx(-1000.0)


def test_scheme_cashflows_appends_current_value_as_final_inflow(db):
    _seed(db)
    flows = scheme_cashflows(db, scheme_id=1)
    assert len(flows) == 2
    assert flows[-1][1] == pytest.approx(2000.0)


def test_scheme_xirr_doubling_in_one_year(db):
    _seed(db)
    # 1000 out on 2023-01-01, worth 2000 on 2024-01-01 -> ~100%.
    assert scheme_xirr(db, scheme_id=1) == pytest.approx(1.0, abs=1e-3)


def test_portfolio_xirr_pools_all_scheme_cashflows(db):
    _seed(db)
    # Only one scheme is seeded, so the portfolio figure matches it.
    assert portfolio_xirr(db) == pytest.approx(1.0, abs=1e-3)


def test_portfolio_xirr_excludes_stocks(db):
    _seed(db)
    # The seeded stock holding is worth 1000 but has no transactions. If it
    # leaked into the cashflows it would distort the rate; it must not.
    assert portfolio_xirr(db) == pytest.approx(scheme_xirr(db, 1), abs=1e-9)


def test_portfolio_xirr_is_none_on_empty_ledger(db):
    assert portfolio_xirr(db) is None


def test_latest_values_include_both_schemes_and_securities(db):
    _seed(db)
    values = latest_values_by_asset_class(db)
    # 2000 from the fund plus 1000 from the stock.
    assert values["EQUITY"] == pytest.approx(3000.0)


def test_latest_values_uses_only_the_most_recent_run(db):
    _seed(db)
    db.execute("INSERT INTO import_runs(import_run_id, source_file) VALUES (2, 'b.pdf')")
    db.execute(
        "INSERT INTO holdings_snapshot(import_run_id, scheme_id, as_of_date, units,"
        " price, value) VALUES (2, 1, '2024-06-01', 100, 25, 2500)"
    )
    db.commit()
    values = latest_values_by_asset_class(db)
    # Only run 2 counts; the stale 2000 from run 1 must not be summed in.
    assert values["EQUITY"] == pytest.approx(2500.0)


def test_unclassified_scheme_is_reported_separately(db):
    _seed(db)
    db.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name) VALUES (2, 1, 'Mystery')"
    )
    db.execute(
        "INSERT INTO holdings_snapshot(import_run_id, scheme_id, as_of_date, units,"
        " price, value) VALUES (1, 2, '2024-01-01', 10, 10, 100)"
    )
    db.commit()
    values = latest_values_by_asset_class(db)
    assert values["UNCLASSIFIED"] == pytest.approx(100.0)
