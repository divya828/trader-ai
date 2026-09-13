"""Fill v0.1's schemes.asset_class from cached market data.

v0.1 deliberately left asset_class as UNCLASSIFIED rather than guessing at
ingest time. This supplies the classification from AMFI's own SEBI categories.

Anything unmatched stays UNCLASSIFIED and is surfaced by a rule later -- never
silently assumed, because a wrong asset class corrupts allocation drift
invisibly while an unclassified one is visible.
"""

from __future__ import annotations

import sqlite3


def backfill_asset_classes(con: sqlite3.Connection) -> int:
    """Set asset_class on ledger schemes from md_schemes. Returns rows updated."""
    cursor = con.execute(
        "UPDATE schemes SET asset_class = ("
        "    SELECT m.asset_class FROM md_schemes m"
        "    WHERE (m.isin_growth = schemes.isin OR m.isin_reinvest = schemes.isin)"
        "      AND m.asset_class != 'UNCLASSIFIED'"
        "    LIMIT 1"
        ")"
        " WHERE schemes.isin IS NOT NULL"
        "   AND schemes.asset_class = 'UNCLASSIFIED'"
        "   AND EXISTS ("
        "    SELECT 1 FROM md_schemes m"
        "    WHERE (m.isin_growth = schemes.isin OR m.isin_reinvest = schemes.isin)"
        "      AND m.asset_class != 'UNCLASSIFIED'"
        ")"
    )
    con.commit()
    return cursor.rowcount
