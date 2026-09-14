"""Build the persistent ledger and backfill weekly NAV history.

Reports structural facts and aggregates only -- never holdings, amounts,
folio numbers, scheme names, or PAN.

Two phases, and the first is a dry run:

    uv run python scripts/backfill_nav.py            # plan only, no download
    uv run python scripts/backfill_nav.py --execute  # actually fetch

The dry run computes the window from your earliest transaction and prints the
download size, so nothing large happens without you seeing the number first.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from trader_ai.db.connection import (  # noqa: E402
    apply_schema,
    apply_schema_v02,
    connect,
)
from trader_ai.ingest.importer import import_pdf  # noqa: E402
from trader_ai.marketdata.backfill import classify_all  # noqa: E402
from trader_ai.marketdata.history import (  # noqa: E402
    backfill_history,
    weekly_sample_dates,
)
from trader_ai.marketdata.refresh import refresh_universe  # noqa: E402

DB_PATH = Path("data/ledger.db")
PASSWORD_FILE = Path("data/.cas_password")
MB_PER_FETCH = 1.2


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def _password() -> str | None:
    import os

    from_env = os.environ.get("TRADER_AI_CAS_PASSWORD")
    if from_env:
        return from_env
    if PASSWORD_FILE.exists():
        return PASSWORD_FILE.read_text(encoding="utf-8").strip() or None
    return None


def main() -> int:
    execute = "--execute" in sys.argv
    pdfs = sorted(Path("data/raw").glob("*.pdf"))
    if not pdfs:
        print("ERROR: no PDF in data/raw/")
        return 2
    pdf = pdfs[-1]

    password = _password()
    if password is None:
        print("ERROR: no password. Write it to data/.cas_password (gitignored):")
        print("  echo -n \"$TRADER_AI_CAS_PASSWORD\" > data/.cas_password")
        return 2

    fresh = not DB_PATH.exists()
    con = connect(DB_PATH)
    if fresh:
        apply_schema(con)
        apply_schema_v02(con)
        print(f"created {DB_PATH} (gitignored)")
    else:
        print(f"using existing {DB_PATH}")

    section("1. LEDGER")
    import_pdf(con, pdf, password)
    counts = {
        table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("folios", "schemes", "transactions", "holdings_snapshot")
    }
    for table, count in counts.items():
        print(f"  {table:20} {count}")

    section("2. WINDOW")
    row = con.execute(
        "SELECT MIN(txn_date) AS first, MAX(txn_date) AS last FROM transactions"
    ).fetchone()
    if row["first"] is None:
        print("  no transactions; nothing to backfill")
        return 1
    start = date.fromisoformat(row["first"][:10])
    end = date.today()
    weeks = weekly_sample_dates(start, end)
    print(f"  earliest transaction : {start}")
    print(f"  today                : {end}")
    print(f"  span                 : {(end - start).days} days")
    print(f"  weekly samples       : {len(weeks)}")
    print(f"  estimated download   : ~{len(weeks) * MB_PER_FETCH:.0f} MB")

    if not execute:
        section("DRY RUN")
        print("  Nothing downloaded. Re-run with --execute to fetch.")
        return 0

    section("3. SCHEME MASTER")
    result = refresh_universe(con)
    print(f"  schemes cached       : {result.schemes_written}")
    print(f"  today's NAV ingested : {result.nav_ingested}")

    section("4. ASSET CLASSES")
    print(f"  {classify_all(con)}")
    unclassified = con.execute(
        "SELECT COUNT(*) FROM schemes WHERE asset_class = 'UNCLASSIFIED'"
    ).fetchone()[0]
    print(f"  still unclassified   : {unclassified}/{counts['schemes']}")

    section("5. NAV HISTORY BACKFILL")
    print(f"  fetching {len(weeks)} weekly samples, this will take a while...")
    backfilled = backfill_history(con, start, end)
    print(f"  days fetched         : {backfilled.days_fetched}")
    print(f"  days already cached  : {backfilled.days_skipped_cached}")
    print(f"  days sparse (skipped): {backfilled.days_sparse}")
    print(f"  nav rows ingested    : {backfilled.nav_rows_ingested}")

    section("6. COVERAGE")
    rows = con.execute(
        "SELECT s.scheme_id, COUNT(n.nav_date) AS points"
        " FROM schemes s"
        " LEFT JOIN md_schemes m"
        "   ON m.isin_growth = s.isin OR m.isin_reinvest = s.isin"
        " LEFT JOIN md_nav n ON n.amfi_code = m.amfi_code"
        " GROUP BY s.scheme_id"
    ).fetchall()
    with_history = sum(1 for r in rows if r["points"] >= 2)
    print(f"  schemes with >=2 NAV points: {with_history}/{len(rows)}")

    section("DONE")
    print(f"  Ledger and NAV cache written to {DB_PATH} (gitignored).")
    if PASSWORD_FILE.exists():
        print(f"  REMINDER: rm {PASSWORD_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
