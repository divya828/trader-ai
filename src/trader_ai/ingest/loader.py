"""Persist normalized ingestion payloads into SQLite.

The only module that writes to the ledger. Re-importing the same statement
must never duplicate transactions: that is enforced by the UNIQUE constraint
on transactions.source_row_hash, not by checking first.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def _start_import_run(con: sqlite3.Connection, source_file: str, period: tuple) -> int:
    cur = con.execute(
        "INSERT INTO import_runs(source_file, cas_statement_period_start,"
        " cas_statement_period_end) VALUES (?, ?, ?)",
        (source_file, period[0], period[1]),
    )
    return int(cur.lastrowid)


def _finish_import_run(
    con: sqlite3.Connection, run_id: int, inserted: int, skipped: int
) -> None:
    con.execute(
        "UPDATE import_runs SET rows_inserted = ?, rows_skipped_duplicate = ?"
        " WHERE import_run_id = ?",
        (inserted, skipped, run_id),
    )


def _upsert_folio(con: sqlite3.Connection, folio: dict) -> int:
    con.execute(
        "INSERT OR IGNORE INTO folios(folio_number, amc, pan_masked) VALUES (?, ?, ?)",
        (folio["folio_number"], folio["amc"], folio["pan_masked"]),
    )
    row = con.execute(
        "SELECT folio_id FROM folios WHERE folio_number = ? AND amc = ?",
        (folio["folio_number"], folio["amc"]),
    ).fetchone()
    return int(row["folio_id"])


def _upsert_scheme(con: sqlite3.Connection, folio_id: int, scheme: dict) -> int:
    con.execute(
        "INSERT OR IGNORE INTO schemes(folio_id, amfi_code, isin, scheme_name)"
        " VALUES (?, ?, ?, ?)",
        (folio_id, scheme["amfi_code"], scheme["isin"], scheme["scheme_name"]),
    )
    row = con.execute(
        "SELECT scheme_id FROM schemes WHERE folio_id = ? AND scheme_name = ?"
        " AND isin IS ?",
        (folio_id, scheme["scheme_name"], scheme["isin"]),
    ).fetchone()
    return int(row["scheme_id"])


def _upsert_security(con: sqlite3.Connection, security: dict) -> int:
    con.execute(
        "INSERT OR IGNORE INTO securities(isin, symbol, name, exchange)"
        " VALUES (?, ?, ?, ?)",
        (
            security["isin"],
            security["symbol"],
            security["name"],
            security["exchange"],
        ),
    )
    row = con.execute(
        "SELECT security_id FROM securities WHERE isin = ?", (security["isin"],)
    ).fetchone()
    return int(row["security_id"])


def load_cas(con: sqlite3.Connection, payload: dict[str, Any], source_file: str) -> int:
    """Load a normalized CAMS/KFintech payload. Returns the import_run_id."""
    run_id = _start_import_run(con, source_file, payload["statement_period"])

    folio_ids = {f["folio_number"]: _upsert_folio(con, f) for f in payload["folios"]}

    scheme_ids: dict[tuple, int] = {}
    for scheme in payload["schemes"]:
        folio_id = folio_ids[scheme["folio_number"]]
        key = (scheme["folio_number"], scheme["scheme_name"])
        scheme_ids[key] = _upsert_scheme(con, folio_id, scheme)

    inserted = skipped = 0
    for txn in payload["transactions"]:
        scheme_id = scheme_ids[(txn["folio_number"], txn["scheme_name"])]
        cur = con.execute(
            "INSERT OR IGNORE INTO transactions(scheme_id, txn_date, txn_type,"
            " units, price, amount, source_row_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                scheme_id,
                txn["txn_date"],
                txn["txn_type"],
                txn["units"],
                txn["price"],
                txn["amount"],
                txn["source_row_hash"],
            ),
        )
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1

    for holding in payload["holdings"]:
        scheme_id = scheme_ids[(holding["folio_number"], holding["scheme_name"])]
        con.execute(
            "INSERT INTO holdings_snapshot(import_run_id, scheme_id, as_of_date,"
            " units, price, value, cost) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                scheme_id,
                holding["as_of_date"],
                holding["units"],
                holding["price"],
                holding["value"],
                holding["cost"],
            ),
        )

    _finish_import_run(con, run_id, inserted, skipped)
    con.commit()
    return run_id


def load_nsdl(con: sqlite3.Connection, payload: dict[str, Any], source_file: str) -> int:
    """Load a normalized NSDL/CDSL payload (holdings only). Returns import_run_id."""
    run_id = _start_import_run(con, source_file, payload["statement_period"])

    for account in payload["demat_accounts"]:
        con.execute(
            "INSERT OR IGNORE INTO demat_accounts(dp_id, client_id, depository)"
            " VALUES (?, ?, ?)",
            (account["dp_id"], account["client_id"], account["depository"]),
        )

    security_ids = {s["isin"]: _upsert_security(con, s) for s in payload["securities"]}

    for holding in payload["holdings"]:
        con.execute(
            "INSERT INTO holdings_snapshot(import_run_id, security_id, as_of_date,"
            " units, price, value, cost) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                security_ids[holding["isin"]],
                holding["as_of_date"],
                holding["units"],
                holding["price"],
                holding["value"],
                holding["cost"],
            ),
        )

    _finish_import_run(con, run_id, 0, 0)
    con.commit()
    return run_id
