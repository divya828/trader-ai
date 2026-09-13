"""Bridge stored ledger rows into the pure analytics functions.

Reads only. XIRR is mutual-fund-only by construction: stocks have no
transaction rows to build cashflows from.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from trader_ai.analytics.xirr import Cashflow, xirr

# Types where money leaves you (a cost), from casparser's TransactionType.
_OUTFLOW_TYPES = {
    "PURCHASE",
    "PURCHASE_SIP",
    "SWITCH_IN",
    "SWITCH_IN_MERGER",
    "GIFT_IN",
}
# Types where money returns to you.
_INFLOW_TYPES = {
    "REDEMPTION",
    "SWITCH_OUT",
    "SWITCH_OUT_MERGER",
    "DIVIDEND_PAYOUT",
    "GIFT_OUT",
}


def _parse(iso: str) -> date:
    return date.fromisoformat(iso[:10])


def latest_import_run_id(con: sqlite3.Connection) -> int | None:
    row = con.execute("SELECT MAX(import_run_id) AS rid FROM import_runs").fetchone()
    return None if row["rid"] is None else int(row["rid"])


def scheme_cashflows(con: sqlite3.Connection, scheme_id: int) -> list[Cashflow]:
    """Dated cashflows for one scheme, ending with its current value."""
    flows: list[Cashflow] = []
    rows = con.execute(
        "SELECT txn_date, txn_type, amount FROM transactions"
        " WHERE scheme_id = ? ORDER BY txn_date",
        (scheme_id,),
    ).fetchall()
    for row in rows:
        txn_type = row["txn_type"]
        amount = abs(float(row["amount"]))
        if txn_type in _OUTFLOW_TYPES:
            flows.append((_parse(row["txn_date"]), -amount))
        elif txn_type in _INFLOW_TYPES:
            flows.append((_parse(row["txn_date"]), amount))
        # Tax/misc types carry no investment cashflow meaning; skip them.

    run_id = latest_import_run_id(con)
    if run_id is not None:
        holding = con.execute(
            "SELECT as_of_date, value FROM holdings_snapshot"
            " WHERE import_run_id = ? AND scheme_id = ?",
            (run_id, scheme_id),
        ).fetchone()
        if holding is not None and float(holding["value"]) != 0.0:
            flows.append((_parse(holding["as_of_date"]), float(holding["value"])))
    return flows


def scheme_xirr(con: sqlite3.Connection, scheme_id: int) -> float | None:
    """XIRR for one mutual fund scheme, or None when it cannot be computed."""
    return xirr(scheme_cashflows(con, scheme_id))


def portfolio_xirr(con: sqlite3.Connection) -> float | None:
    """XIRR across every scheme's cashflows pooled together.

    Stocks are excluded: an eCAS carries no stock transaction history.
    """
    flows: list[Cashflow] = []
    for row in con.execute("SELECT scheme_id FROM schemes"):
        flows.extend(scheme_cashflows(con, int(row["scheme_id"])))
    return xirr(flows)


def latest_values_by_asset_class(con: sqlite3.Connection) -> dict[str, float]:
    """Current market value per asset class from the most recent import run."""
    run_id = latest_import_run_id(con)
    if run_id is None:
        return {}

    values: dict[str, float] = {}
    # GROUP BY repeats the COALESCE expression rather than the alias: both
    # joined tables have an asset_class column, so the bare alias is ambiguous.
    rows = con.execute(
        "SELECT COALESCE(s.asset_class, sec.asset_class) AS asset_class,"
        " SUM(h.value) AS total"
        " FROM holdings_snapshot h"
        " LEFT JOIN schemes s ON s.scheme_id = h.scheme_id"
        " LEFT JOIN securities sec ON sec.security_id = h.security_id"
        " WHERE h.import_run_id = ?"
        " GROUP BY COALESCE(s.asset_class, sec.asset_class)",
        (run_id,),
    ).fetchall()
    for row in rows:
        values[row["asset_class"]] = float(row["total"])
    return values
