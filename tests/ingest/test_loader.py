import pytest

from trader_ai.ingest.loader import load_cas, load_nsdl

CAS_PAYLOAD = {
    "statement_period": ("2023-04-01", "2024-03-31"),
    "folios": [
        {"folio_number": "12345/67", "amc": "HDFC Mutual Fund", "pan_masked": "ABCXXX234Z"}
    ],
    "schemes": [
        {
            "folio_number": "12345/67",
            "amfi_code": "118989",
            "isin": "INF179K01158",
            "scheme_name": "HDFC Flexi Cap Fund - Growth",
            "scheme_type": "EQUITY",
        }
    ],
    "transactions": [
        {
            "folio_number": "12345/67",
            "isin": "INF179K01158",
            "scheme_name": "HDFC Flexi Cap Fund - Growth",
            "txn_date": "2023-05-10",
            "txn_type": "PURCHASE",
            "amount": 10000.0,
            "units": 100.0,
            "price": 100.0,
            "source_row_hash": "hash-a",
        },
        {
            "folio_number": "12345/67",
            "isin": "INF179K01158",
            "scheme_name": "HDFC Flexi Cap Fund - Growth",
            "txn_date": "2023-08-10",
            "txn_type": "PURCHASE_SIP",
            "amount": 5500.0,
            "units": 50.0,
            "price": 110.0,
            "source_row_hash": "hash-b",
        },
    ],
    "holdings": [
        {
            "folio_number": "12345/67",
            "isin": "INF179K01158",
            "scheme_name": "HDFC Flexi Cap Fund - Growth",
            "as_of_date": "2024-03-31",
            "units": 150.0,
            "price": 120.0,
            "value": 18000.0,
            "cost": 15500.0,
        }
    ],
}

NSDL_PAYLOAD = {
    "statement_period": ("2023-04-01", "2024-03-31"),
    "demat_accounts": [
        {"dp_id": "IN300000", "client_id": "10000001", "depository": "NSDL"}
    ],
    "securities": [
        {
            "isin": "INE002A01018",
            "symbol": "RELIANCE",
            "name": "Reliance Industries Ltd",
            "exchange": "NSE",
        }
    ],
    "holdings": [
        {
            "isin": "INE002A01018",
            "as_of_date": "2024-03-31",
            "units": 50.0,
            "price": 2950.0,
            "value": 147500.0,
            "cost": None,
        }
    ],
}


def _count(db, table):
    return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_load_cas_persists_all_entities(db):
    load_cas(db, CAS_PAYLOAD, source_file="sample.pdf")
    assert _count(db, "folios") == 1
    assert _count(db, "schemes") == 1
    assert _count(db, "transactions") == 2
    assert _count(db, "holdings_snapshot") == 1
    assert _count(db, "import_runs") == 1


def test_reimport_is_idempotent_for_transactions(db):
    load_cas(db, CAS_PAYLOAD, source_file="sample.pdf")
    load_cas(db, CAS_PAYLOAD, source_file="sample.pdf")
    assert _count(db, "transactions") == 2
    assert _count(db, "folios") == 1
    assert _count(db, "schemes") == 1
    # Each import is still logged separately.
    assert _count(db, "import_runs") == 2


def test_reimport_does_not_duplicate_schemes_with_null_isin(db):
    # casparser types Scheme.isin as Optional, so a scheme can arrive with no
    # ISIN. A table-level UNIQUE would not dedupe these (NULL != NULL in SQL),
    # letting every re-import add another row and inflate holdings.
    payload = {
        "statement_period": ("2023-04-01", "2024-03-31"),
        "folios": CAS_PAYLOAD["folios"],
        "schemes": [
            {
                "folio_number": "12345/67",
                "amfi_code": None,
                "isin": None,
                "scheme_name": "Fund Without ISIN",
                "scheme_type": None,
            }
        ],
        "transactions": [],
        "holdings": [],
    }
    load_cas(db, payload, source_file="sample.pdf")
    load_cas(db, payload, source_file="sample.pdf")
    load_cas(db, payload, source_file="sample.pdf")
    assert _count(db, "schemes") == 1


def test_reimport_records_skipped_duplicates(db):
    load_cas(db, CAS_PAYLOAD, source_file="sample.pdf")
    run_id = load_cas(db, CAS_PAYLOAD, source_file="sample.pdf")
    row = db.execute(
        "SELECT rows_inserted, rows_skipped_duplicate FROM import_runs WHERE import_run_id = ?",
        (run_id,),
    ).fetchone()
    assert row["rows_inserted"] == 0
    assert row["rows_skipped_duplicate"] == 2


def test_each_import_gets_its_own_holdings_snapshot(db):
    load_cas(db, CAS_PAYLOAD, source_file="sample.pdf")
    load_cas(db, CAS_PAYLOAD, source_file="sample.pdf")
    # Snapshots are per-run history, so two runs means two rows.
    assert _count(db, "holdings_snapshot") == 2


def test_scheme_asset_class_defaults_to_unclassified(db):
    load_cas(db, CAS_PAYLOAD, source_file="sample.pdf")
    row = db.execute("SELECT asset_class FROM schemes").fetchone()
    assert row["asset_class"] == "UNCLASSIFIED"


def test_transactions_link_to_the_right_scheme(db):
    load_cas(db, CAS_PAYLOAD, source_file="sample.pdf")
    rows = db.execute(
        "SELECT t.txn_type, s.scheme_name FROM transactions t"
        " JOIN schemes s ON s.scheme_id = t.scheme_id"
        " ORDER BY t.txn_date"
    ).fetchall()
    assert [r["txn_type"] for r in rows] == ["PURCHASE", "PURCHASE_SIP"]
    assert all(r["scheme_name"] == "HDFC Flexi Cap Fund - Growth" for r in rows)


def test_load_nsdl_persists_securities_and_holdings(db):
    load_nsdl(db, NSDL_PAYLOAD, source_file="demat.pdf")
    assert _count(db, "demat_accounts") == 1
    assert _count(db, "securities") == 1
    assert _count(db, "holdings_snapshot") == 1
    # Stocks have no transaction history in an eCAS.
    assert _count(db, "transactions") == 0


def test_reimport_nsdl_does_not_duplicate_securities(db):
    load_nsdl(db, NSDL_PAYLOAD, source_file="demat.pdf")
    load_nsdl(db, NSDL_PAYLOAD, source_file="demat.pdf")
    assert _count(db, "securities") == 1
    assert _count(db, "demat_accounts") == 1
