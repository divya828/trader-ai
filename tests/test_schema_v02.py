import sqlite3

import pytest

from trader_ai.db.connection import apply_schema, apply_schema_v02, connect

V02_TABLES = {
    "md_schemes", "md_nav", "md_fetch_log",
    "md_category_asset_class", "health_scores",
}


@pytest.fixture
def db2():
    con = connect(":memory:")
    apply_schema(con)
    apply_schema_v02(con)
    yield con
    con.close()


def test_v02_adds_all_tables(db2):
    names = {
        r[0] for r in db2.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert V02_TABLES <= names


def test_v01_tables_still_present(db2):
    names = {
        r[0] for r in db2.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"folios", "schemes", "transactions", "holdings_snapshot"} <= names


def test_plan_accepts_all_four_values(db2):
    for plan in ("DIRECT", "REGULAR", "NOT_APPLICABLE", "UNKNOWN"):
        db2.execute(
            "INSERT INTO md_schemes(amfi_code, scheme_name, plan, last_seen)"
            " VALUES (?, 'S', ?, '2026-01-01')",
            (plan, plan),
        )
    assert db2.execute("SELECT COUNT(*) FROM md_schemes").fetchone()[0] == 4


def test_plan_rejects_unknown_value(db2):
    with pytest.raises(sqlite3.IntegrityError):
        db2.execute(
            "INSERT INTO md_schemes(amfi_code, scheme_name, plan, last_seen)"
            " VALUES ('1', 'S', 'BOGUS', '2026-01-01')"
        )


def test_health_score_allows_null_for_unmeasured(db2):
    # NULL must be distinct from 0: an unmeasured dimension is not a clean one.
    db2.execute("INSERT INTO health_scores(dimension, score) VALUES ('COST', NULL)")
    assert db2.execute("SELECT score FROM health_scores").fetchone()[0] is None


def test_health_score_rejects_out_of_range(db2):
    with pytest.raises(sqlite3.IntegrityError):
        db2.execute("INSERT INTO health_scores(dimension, score) VALUES ('COST', 101)")


def test_md_nav_rejects_duplicate_code_date(db2):
    db2.execute("INSERT INTO md_nav(amfi_code, nav_date, nav) VALUES ('1','2026-01-01',10.0)")
    with pytest.raises(sqlite3.IntegrityError):
        db2.execute("INSERT INTO md_nav(amfi_code, nav_date, nav) VALUES ('1','2026-01-01',11.0)")
