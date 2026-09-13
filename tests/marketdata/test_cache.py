from datetime import date

import pytest

from trader_ai.db.connection import apply_schema, apply_schema_v02, connect
from trader_ai.marketdata.cache import (
    ledger_isins,
    missing_ranges,
    upsert_nav_rows,
    upsert_schemes,
)
from trader_ai.marketdata.layouts import UNIVERSE
from trader_ai.marketdata.parser import parse

SAMPLE = """\
Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date

Open Ended Schemes(Equity Scheme - Flexi Cap Fund)

Acme Mutual Fund

100001;INF001A01011;-;Acme Flexi Cap Fund;Direct Plan;Growth Option;25.1234;11-Sep-2026
100002;INF001A01029;-;Acme Flexi Cap Fund;Regular Plan;Growth Option;22.5000;11-Sep-2026
"""


@pytest.fixture
def db2():
    con = connect(":memory:")
    apply_schema(con)
    apply_schema_v02(con)
    yield con
    con.close()


def _rows():
    return parse(SAMPLE, UNIVERSE).rows


def _hold(con, isin, scheme_id=1, name="Acme Flexi Cap Fund"):
    con.execute(
        "INSERT OR IGNORE INTO folios(folio_id, folio_number, amc)"
        " VALUES (1, 'F1', 'Acme')"
    )
    con.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name, isin)"
        " VALUES (?, 1, ?, ?)",
        (scheme_id, name, isin),
    )
    con.commit()


def test_upsert_schemes_inserts_all(db2):
    upsert_schemes(db2, _rows())
    assert db2.execute("SELECT COUNT(*) FROM md_schemes").fetchone()[0] == 2


def test_upsert_schemes_is_idempotent(db2):
    upsert_schemes(db2, _rows())
    upsert_schemes(db2, _rows())
    assert db2.execute("SELECT COUNT(*) FROM md_schemes").fetchone()[0] == 2


def test_upsert_schemes_stores_asset_class_from_category(db2):
    upsert_schemes(db2, _rows())
    classes = {r[0] for r in db2.execute("SELECT asset_class FROM md_schemes")}
    assert classes == {"EQUITY"}


def test_upsert_schemes_stores_plan_and_structure(db2):
    upsert_schemes(db2, _rows())
    rows = {
        r["amfi_code"]: r
        for r in db2.execute("SELECT amfi_code, plan, scheme_structure FROM md_schemes")
    }
    assert rows["100001"]["plan"] == "DIRECT"
    assert rows["100002"]["plan"] == "REGULAR"
    assert rows["100001"]["scheme_structure"] == "OPEN"


def test_upsert_nav_rows_filters_to_ledger_isins(db2):
    # Cache size must be proportional to the portfolio, not the fund universe.
    _hold(db2, "INF001A01011")
    upsert_schemes(db2, _rows())
    ingested, skipped = upsert_nav_rows(db2, _rows(), ledger_isins(db2))
    assert ingested == 1   # only the held ISIN
    assert skipped == 1
    assert db2.execute("SELECT COUNT(*) FROM md_nav").fetchone()[0] == 1


def test_upsert_nav_rows_is_idempotent(db2):
    _hold(db2, "INF001A01011")
    upsert_schemes(db2, _rows())
    isins = ledger_isins(db2)
    upsert_nav_rows(db2, _rows(), isins)
    upsert_nav_rows(db2, _rows(), isins)
    assert db2.execute("SELECT COUNT(*) FROM md_nav").fetchone()[0] == 1


def test_upsert_nav_rows_writes_nothing_when_ledger_is_empty(db2):
    upsert_schemes(db2, _rows())
    ingested, skipped = upsert_nav_rows(db2, _rows(), ledger_isins(db2))
    assert ingested == 0
    assert skipped == 2


def test_ledger_isins_reads_both_schemes_and_securities(db2):
    _hold(db2, "INF001A01011")
    db2.execute(
        "INSERT INTO securities(security_id, isin, name) VALUES (1, 'INE002A01018', 'R')"
    )
    db2.commit()
    assert ledger_isins(db2) == {"INF001A01011", "INE002A01018"}


def test_ledger_isins_ignores_null_isins(db2):
    db2.execute("INSERT INTO folios(folio_id, folio_number, amc) VALUES (1,'F1','Acme')")
    db2.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name, isin)"
        " VALUES (1, 1, 'No ISIN Fund', NULL)"
    )
    db2.commit()
    assert ledger_isins(db2) == set()


def test_missing_ranges_returns_whole_window_when_nothing_cached(db2):
    gaps = missing_ranges(db2, date(2026, 1, 1), date(2026, 1, 10))
    assert gaps == [(date(2026, 1, 1), date(2026, 1, 10))]


def test_missing_ranges_excludes_a_cached_range(db2):
    db2.execute(
        "INSERT INTO md_fetch_log(endpoint, range_start, range_end)"
        " VALUES ('history', '2026-01-01', '2026-01-05')"
    )
    db2.commit()
    gaps = missing_ranges(db2, date(2026, 1, 1), date(2026, 1, 10))
    assert gaps == [(date(2026, 1, 6), date(2026, 1, 10))]


def test_missing_ranges_returns_empty_when_fully_cached(db2):
    db2.execute(
        "INSERT INTO md_fetch_log(endpoint, range_start, range_end)"
        " VALUES ('history', '2026-01-01', '2026-01-31')"
    )
    db2.commit()
    assert missing_ranges(db2, date(2026, 1, 5), date(2026, 1, 20)) == []


def test_missing_ranges_finds_a_hole_between_two_cached_ranges(db2):
    for start, end in (("2026-01-01", "2026-01-05"), ("2026-01-15", "2026-01-31")):
        db2.execute(
            "INSERT INTO md_fetch_log(endpoint, range_start, range_end) VALUES ('history', ?, ?)",
            (start, end),
        )
    db2.commit()
    gaps = missing_ranges(db2, date(2026, 1, 1), date(2026, 1, 31))
    assert gaps == [(date(2026, 1, 6), date(2026, 1, 14))]


def test_missing_ranges_handles_reversed_window(db2):
    assert missing_ranges(db2, date(2026, 1, 10), date(2026, 1, 1)) == []


def test_missing_ranges_single_uncached_day(db2):
    gaps = missing_ranges(db2, date(2026, 1, 10), date(2026, 1, 10))
    assert gaps == [(date(2026, 1, 10), date(2026, 1, 10))]


def test_missing_ranges_single_cached_day(db2):
    db2.execute(
        "INSERT INTO md_fetch_log(endpoint, range_start, range_end)"
        " VALUES ('history', '2026-01-03', '2026-01-03')"
    )
    db2.commit()
    assert missing_ranges(db2, date(2026, 1, 3), date(2026, 1, 3)) == []


def test_log_fetch_records_a_range(db2):
    from trader_ai.marketdata.cache import log_fetch

    log_fetch(db2, "history", date(2026, 1, 1), date(2026, 1, 5), 10, 3)
    row = db2.execute(
        "SELECT endpoint, range_start, range_end, rows_ingested, rows_skipped"
        " FROM md_fetch_log"
    ).fetchone()
    assert row["endpoint"] == "history"
    assert row["range_start"] == "2026-01-01"
    assert row["rows_ingested"] == 10
    assert row["rows_skipped"] == 3
