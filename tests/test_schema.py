import sqlite3

from trader_ai.db.connection import connect, apply_schema

EXPECTED_TABLES = {
    "folios", "schemes", "securities", "demat_accounts", "transactions",
    "tax_lots", "lot_disposals", "holdings_snapshot", "target_allocation",
    "import_runs",
}


def test_schema_creates_all_tables():
    con = connect(":memory:")
    apply_schema(con)
    names = {
        r[0]
        for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert EXPECTED_TABLES <= names


def test_foreign_keys_are_enforced():
    con = connect(":memory:")
    apply_schema(con)
    # scheme_id 999 does not exist
    try:
        con.execute(
            "INSERT INTO transactions(scheme_id, txn_date, txn_type, amount, source_row_hash)"
            " VALUES (999, '2024-01-01', 'PURCHASE', 100, 'h')"
        )
        raise AssertionError("expected FK violation")
    except sqlite3.IntegrityError:
        pass


def test_holdings_snapshot_dedupes_within_a_run():
    con = connect(":memory:")
    apply_schema(con)
    con.execute("INSERT INTO folios(folio_id, folio_number, amc) VALUES (1, 'F1', 'HDFC')")
    con.execute("INSERT INTO schemes(scheme_id, folio_id, scheme_name) VALUES (1, 1, 'S1')")
    con.execute("INSERT INTO import_runs(import_run_id, source_file) VALUES (1, 'a.pdf')")
    ins = (
        "INSERT INTO holdings_snapshot(import_run_id, scheme_id, as_of_date, units, price, value)"
        " VALUES (1, 1, '2024-01-01', 10, 5, 50)"
    )
    con.execute(ins)
    try:
        con.execute(ins)
        raise AssertionError("expected duplicate holding to be rejected")
    except sqlite3.IntegrityError:
        pass
