"""Import a real eCAS PDF and report structural facts only.

This is the first exercise of the real-PDF path: every test to date uses
synthetic fixtures built from casparser's models, so the mapping from an
actual statement has never been verified.

Deliberately prints NO holdings, amounts, folio numbers, scheme names, or PAN
-- only counts, coverage ratios, and pass/fail checks. Run it, read the
summary, and the numbers themselves stay in the local database.

Usage:

    export TRADER_AI_CAS_PASSWORD='...'
    uv run python scripts/import_real_cas.py data/raw/your_statement.pdf

Add --keep to write data/ledger.db instead of using an in-memory database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from trader_ai.analytics.allocation import compute_drift  # noqa: E402
from trader_ai.analytics.portfolio import (  # noqa: E402
    latest_values_by_asset_class,
    portfolio_xirr,
    scheme_xirr,
)
from trader_ai.analytics.tax_lots import (  # noqa: E402
    Acquisition,
    Disposal,
    match_fifo,
)
from trader_ai.db.connection import (  # noqa: E402
    apply_schema,
    apply_schema_v02,
    connect,
)
from trader_ai.ingest.importer import import_pdf  # noqa: E402

ACQUIRING = {
    "PURCHASE",
    "PURCHASE_SIP",
    "SWITCH_IN",
    "SWITCH_IN_MERGER",
    "DIVIDEND_REINVEST",
    "GIFT_IN",
}
DISPOSING = {"REDEMPTION", "SWITCH_OUT", "SWITCH_OUT_MERGER", "GIFT_OUT"}

PAN_SHAPE = __import__("re").compile(r"[A-Z]{5}[0-9]{4}[A-Z]")


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    pdf_path = Path(sys.argv[1])
    keep = "--keep" in sys.argv
    if not pdf_path.exists():
        print(f"ERROR: no such file: {pdf_path}")
        return 2

    password = os.environ.get("TRADER_AI_CAS_PASSWORD")
    if not password:
        print("ERROR: set TRADER_AI_CAS_PASSWORD in your environment first.")
        print("  export TRADER_AI_CAS_PASSWORD='...'")
        return 2

    db_path = "data/ledger.db" if keep else ":memory:"
    con = connect(db_path)
    apply_schema(con)
    apply_schema_v02(con)

    section("1. PARSE + LOAD")
    try:
        run_id = import_pdf(con, pdf_path, password)
    except Exception as exc:  # noqa: BLE001 - this is the finding
        print(f"  FAILED: {type(exc).__name__}: {exc}")
        print("\n  This is the real-PDF mapping gap. Report the exception type,")
        print("  not the statement contents.")
        return 1
    print(f"  OK - import_run_id={run_id}, database={db_path}")

    section("2. WHAT LANDED (counts only)")
    counts = {}
    for table in (
        "folios",
        "schemes",
        "securities",
        "demat_accounts",
        "transactions",
        "holdings_snapshot",
    ):
        counts[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:20} {counts[table]}")

    rows = con.execute(
        "SELECT txn_type, COUNT(*) c FROM transactions GROUP BY txn_type ORDER BY c DESC"
    ).fetchall()
    if rows:
        print("\n  transaction types seen:")
        for row in rows:
            print(f"    {row['txn_type']:22} {row['c']}")

    section("3. PII CHECKS")
    pan_rows = con.execute(
        "SELECT pan_masked FROM folios WHERE pan_masked IS NOT NULL"
    ).fetchall()
    unmasked = [r[0] for r in pan_rows if PAN_SHAPE.fullmatch(r[0] or "")]
    print(f"  folios with a stored PAN   : {len(pan_rows)}")
    print(f"  any stored UNMASKED PAN    : {'FAIL - ' + str(len(unmasked)) if unmasked else 'no (good)'}")
    masked_ok = all(
        (r[0] or "").count("X") >= 3 for r in pan_rows
    )
    print(f"  all stored PANs look masked: {'yes' if masked_ok else 'FAIL'}")

    section("4. IDEMPOTENCY (re-import the same file)")
    before = counts["transactions"]
    import_pdf(con, pdf_path, password)
    after = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    print(f"  transactions before={before} after={after}")
    print(f"  {'OK - no duplicates' if before == after else 'FAIL - re-import duplicated rows'}")

    section("5. XIRR")
    schemes = con.execute("SELECT scheme_id FROM schemes").fetchall()
    computed = sum(
        1 for s in schemes if scheme_xirr(con, int(s["scheme_id"])) is not None
    )
    print(f"  schemes with computable XIRR: {computed}/{len(schemes)}")
    total = portfolio_xirr(con)
    print(f"  portfolio XIRR computable   : {'yes' if total is not None else 'no'}")
    if total is not None:
        print(f"  portfolio XIRR magnitude    : {'plausible' if -1 < total < 10 else 'SUSPECT: ' + str(total)}")

    section("6. ALLOCATION")
    values = latest_values_by_asset_class(con)
    grand = sum(values.values())
    if grand:
        for asset_class, value in sorted(values.items()):
            print(f"  {asset_class:14} {value / grand * 100:5.1f}% of portfolio")
    unclassified_share = values.get("UNCLASSIFIED", 0.0) / grand if grand else 0.0
    print(f"\n  unclassified share: {unclassified_share * 100:.1f}%")
    print("  (run marketdata refresh + backfill to reduce this)")

    report = compute_drift(values, {"EQUITY": 0.6, "DEBT": 0.3, "GOLD": 0.1})
    print(f"  drift computed for {len(report.drifts)} asset classes (illustrative targets)")

    section("7. TAX LOTS (FIFO)")
    ok = failed = skipped = 0
    for scheme in schemes:
        sid = int(scheme["scheme_id"])
        txns = con.execute(
            "SELECT txn_date, txn_type, units, price FROM transactions"
            " WHERE scheme_id=? AND units IS NOT NULL ORDER BY txn_date",
            (sid,),
        ).fetchall()
        acquisitions, disposals = [], []
        for t in txns:
            import datetime

            when = datetime.date.fromisoformat(t["txn_date"][:10])
            units = abs(float(t["units"]))
            price = float(t["price"] or 0)
            if t["txn_type"] in ACQUIRING:
                acquisitions.append(Acquisition(when, units, price))
            elif t["txn_type"] in DISPOSING:
                disposals.append(Disposal(when, units, price))
        if not disposals:
            skipped += 1
            continue
        try:
            match_fifo(acquisitions, disposals, asset_class="EQUITY")
            ok += 1
        except ValueError:
            failed += 1
    print(f"  schemes with disposals   : {ok + failed}")
    print(f"  FIFO matched cleanly     : {ok}")
    print(f"  FIFO raised (unit shortfall): {failed}")
    print(f"  no disposals (skipped)   : {skipped}")

    section("SUMMARY")
    print("  The real-PDF path has now been exercised end to end.")
    if not keep:
        print("  Database was in-memory; nothing was written to disk.")
    else:
        print(f"  Database written to {db_path} (gitignored).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
