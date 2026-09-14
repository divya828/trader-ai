"""Fill v0.1's schemes.asset_class from cached market data.

v0.1 deliberately left asset_class as UNCLASSIFIED rather than guessing at
ingest time. This supplies the classification from AMFI's own SEBI categories.

Anything unmatched stays UNCLASSIFIED and is surfaced by a rule later -- never
silently assumed, because a wrong asset class corrupts allocation drift
invisibly while an unclassified one is visible.
"""

from __future__ import annotations

import sqlite3

from trader_ai.marketdata.categories import classify_by_name


def set_override(
    con: sqlite3.Connection, isin: str, asset_class: str, note: str | None = None
) -> None:
    """Record a manual asset-class decision for one ISIN.

    Overrides always win over inference. They exist because some SEBI
    categories -- notably "Other Scheme - Index Funds" -- span every asset
    class, and a fund's own name is not always decisive either.
    """
    con.execute(
        "INSERT INTO md_asset_class_override(isin, asset_class, note)"
        " VALUES (?, ?, ?)"
        " ON CONFLICT(isin) DO UPDATE SET"
        "   asset_class=excluded.asset_class, note=excluded.note",
        (isin, asset_class, note),
    )
    con.commit()


def apply_overrides(con: sqlite3.Connection) -> int:
    """Apply manual overrides to ledger schemes. Returns rows updated.

    Runs last and wins unconditionally -- it may overwrite a class that
    inference already set, because a human decision beats a guess.
    """
    cursor = con.execute(
        "UPDATE schemes SET asset_class = ("
        "    SELECT o.asset_class FROM md_asset_class_override o"
        "    WHERE o.isin = schemes.isin"
        ")"
        " WHERE schemes.isin IS NOT NULL"
        "   AND EXISTS ("
        "    SELECT 1 FROM md_asset_class_override o WHERE o.isin = schemes.isin"
        ")"
        "   AND schemes.asset_class IS NOT ("
        "    SELECT o.asset_class FROM md_asset_class_override o"
        "    WHERE o.isin = schemes.isin"
        ")"
    )
    con.commit()
    return cursor.rowcount


def backfill_by_name(con: sqlite3.Connection) -> int:
    """Classify still-unclassified schemes by inferring from the scheme name.

    Second layer, for categories that span asset classes. Only names matching
    exactly one asset-class family are used; ambiguous names stay
    UNCLASSIFIED rather than being guessed.
    """
    rows = con.execute(
        "SELECT s.scheme_id, COALESCE(m.scheme_name, s.scheme_name) AS name"
        " FROM schemes s"
        " LEFT JOIN md_schemes m"
        "   ON m.isin_growth = s.isin OR m.isin_reinvest = s.isin"
        " WHERE s.asset_class = 'UNCLASSIFIED'"
    ).fetchall()

    updated = 0
    for row in rows:
        inferred = classify_by_name(row["name"])
        if inferred:
            con.execute(
                "UPDATE schemes SET asset_class = ? WHERE scheme_id = ?",
                (inferred, int(row["scheme_id"])),
            )
            updated += 1
    con.commit()
    return updated


def classify_all(con: sqlite3.Connection) -> dict[str, int]:
    """Run every classification layer in precedence order.

    category -> name inference -> manual override (override wins).
    """
    by_category = backfill_asset_classes(con)
    by_name = backfill_by_name(con)
    by_override = apply_overrides(con)
    return {
        "by_category": by_category,
        "by_name": by_name,
        "by_override": by_override,
    }


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
