import pytest

from trader_ai.db.connection import apply_schema, apply_schema_v02, connect
from trader_ai.marketdata.backfill import backfill_asset_classes


@pytest.fixture
def db2():
    con = connect(":memory:")
    apply_schema(con)
    apply_schema_v02(con)
    con.execute("INSERT INTO folios(folio_id, folio_number, amc) VALUES (1,'F1','Acme')")
    yield con
    con.close()


def _add_ledger_scheme(con, scheme_id, isin, name="S"):
    con.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name, isin)"
        " VALUES (?, 1, ?, ?)",
        (scheme_id, name, isin),
    )


def _add_md_scheme(con, code, isin, asset_class):
    con.execute(
        "INSERT INTO md_schemes(amfi_code, isin_growth, scheme_name, asset_class, last_seen)"
        " VALUES (?, ?, 'S', ?, '2026-09-11')",
        (code, isin, asset_class),
    )


def test_backfill_sets_asset_class_from_market_data(db2):
    _add_ledger_scheme(db2, 1, "INF001A01011")
    _add_md_scheme(db2, "100001", "INF001A01011", "EQUITY")
    db2.commit()
    updated = backfill_asset_classes(db2)
    assert updated == 1
    assert db2.execute("SELECT asset_class FROM schemes").fetchone()[0] == "EQUITY"


def test_unmatched_scheme_stays_unclassified(db2):
    # A wrong asset class corrupts allocation silently; an unclassified one is
    # surfaced. Never guess.
    _add_ledger_scheme(db2, 1, "INF999X99999")
    db2.commit()
    backfill_asset_classes(db2)
    assert db2.execute("SELECT asset_class FROM schemes").fetchone()[0] == "UNCLASSIFIED"


def test_scheme_with_null_isin_stays_unclassified(db2):
    _add_ledger_scheme(db2, 1, None)
    db2.commit()
    backfill_asset_classes(db2)
    assert db2.execute("SELECT asset_class FROM schemes").fetchone()[0] == "UNCLASSIFIED"


def test_market_data_unclassified_does_not_overwrite(db2):
    _add_ledger_scheme(db2, 1, "INF001A01011")
    _add_md_scheme(db2, "100001", "INF001A01011", "UNCLASSIFIED")
    db2.commit()
    updated = backfill_asset_classes(db2)
    assert updated == 0
    assert db2.execute("SELECT asset_class FROM schemes").fetchone()[0] == "UNCLASSIFIED"


def test_backfill_is_idempotent(db2):
    _add_ledger_scheme(db2, 1, "INF001A01011")
    _add_md_scheme(db2, "100001", "INF001A01011", "EQUITY")
    db2.commit()
    assert backfill_asset_classes(db2) == 1
    assert backfill_asset_classes(db2) == 0  # already set, nothing to do


def test_backfill_matches_on_reinvest_isin_too(db2):
    _add_ledger_scheme(db2, 1, "INF001A01037")
    db2.execute(
        "INSERT INTO md_schemes(amfi_code, isin_growth, isin_reinvest, scheme_name,"
        " asset_class, last_seen)"
        " VALUES ('100002', 'INF001A01029', 'INF001A01037', 'S', 'DEBT', '2026-09-11')"
    )
    db2.commit()
    assert backfill_asset_classes(db2) == 1
    assert db2.execute("SELECT asset_class FROM schemes").fetchone()[0] == "DEBT"


def test_backfill_does_not_touch_already_classified_schemes(db2):
    # An existing classification is authoritative; do not churn it.
    db2.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name, isin, asset_class)"
        " VALUES (1, 1, 'S', 'INF001A01011', 'DEBT')"
    )
    _add_md_scheme(db2, "100001", "INF001A01011", "EQUITY")
    db2.commit()
    assert backfill_asset_classes(db2) == 0
    assert db2.execute("SELECT asset_class FROM schemes").fetchone()[0] == "DEBT"


def test_backfill_handles_multiple_schemes(db2):
    _add_ledger_scheme(db2, 1, "INF001A01011", "Equity Fund")
    _add_ledger_scheme(db2, 2, "INF001A01029", "Debt Fund")
    _add_ledger_scheme(db2, 3, "INF999X99999", "Unknown Fund")
    _add_md_scheme(db2, "100001", "INF001A01011", "EQUITY")
    _add_md_scheme(db2, "100002", "INF001A01029", "DEBT")
    db2.commit()
    assert backfill_asset_classes(db2) == 2
    rows = {
        r["scheme_name"]: r["asset_class"]
        for r in db2.execute("SELECT scheme_name, asset_class FROM schemes")
    }
    assert rows == {
        "Equity Fund": "EQUITY",
        "Debt Fund": "DEBT",
        "Unknown Fund": "UNCLASSIFIED",
    }


def test_backfill_improves_allocation_drift(db2):
    # The point of this task: v0.1's allocation tool stops reporting
    # everything as unclassified.
    from trader_ai.analytics.portfolio import latest_values_by_asset_class

    _add_ledger_scheme(db2, 1, "INF001A01011")
    _add_md_scheme(db2, "100001", "INF001A01011", "EQUITY")
    db2.execute("INSERT INTO import_runs(import_run_id, source_file) VALUES (1,'a.pdf')")
    db2.execute(
        "INSERT INTO holdings_snapshot(import_run_id, scheme_id, as_of_date, units,"
        " price, value) VALUES (1, 1, '2026-09-11', 100, 25, 2500)"
    )
    db2.commit()

    before = latest_values_by_asset_class(db2)
    assert before == {"UNCLASSIFIED": 2500.0}

    backfill_asset_classes(db2)
    after = latest_values_by_asset_class(db2)
    assert after == {"EQUITY": 2500.0}
