"""SEBI scheme category -> v0.1 asset_class.

Seeded from AMFI's own category headers. Deliberately conservative: a category
that does not clearly belong to one asset class returns None and stays
UNCLASSIFIED, because a wrong asset class silently corrupts allocation drift
while an unclassified one is visibly surfaced.
"""

from __future__ import annotations

# Matched by prefix, longest first, case-insensitively.
CATEGORY_ASSET_CLASS: dict[str, str] = {
    # Open-ended SEBI categorization (post-2018 naming).
    "Equity Scheme": "EQUITY",
    "Debt Scheme": "DEBT",
    "Hybrid Scheme": "HYBRID",
    # Close-ended and legacy naming. "Income" alone is AMFI's close-ended debt
    # category and is the single largest family in the file (4,591 rows).
    "Income/Debt Oriented Schemes": "DEBT",
    "Income Scheme": "DEBT",
    "Income": "DEBT",
    "Growth Scheme": "EQUITY",
    "Growth": "EQUITY",
    "Liquid Scheme": "CASH",
    "Liquid": "CASH",
    "Money Market Scheme": "CASH",
    "Money Market": "CASH",
    "Gilt Scheme": "DEBT",
    "Gilt": "DEBT",
    "Floating Rate Scheme": "DEBT",
    "ELSS": "EQUITY",  # equity-linked savings scheme: equity by statute
    # Typed ETF categories name their own asset class, so they are certain
    # even though the generic "Other Scheme - ... ETF" family is not.
    "Exchange Traded Funds (ETFs) - Equity ETF": "EQUITY",
    "Exchange Traded Funds (ETFs) - Debt ETF": "DEBT",
    "Exchange Traded Funds (ETFs) - Gold ETF": "GOLD",
    "Exchange Traded Funds (ETFs) - Silver ETF": "GOLD",
    "Exchange Traded Funds (ETFs) - Hybrid ETF": "HYBRID",
    "Other Scheme - Gold ETF": "GOLD",
    # Typed index-fund categories likewise.
    "Index Funds - Equity Funds": "EQUITY",
    "Index Funds - Debt Funds": "DEBT",
    "Index Funds - Hybrid Fund": "HYBRID",
}

# Deliberately left unmapped, because category alone cannot determine the
# asset class and a wrong answer corrupts allocation silently:
#   "Other Scheme - Index Funds" / "- FoF Domestic" / "- FoF Overseas" /
#       "- Other  ETFs"        -- span every asset class
#   "Fund of Funds Scheme (Domestic)", "Overseas Fund of Funds"
#   "Solution Oriented Scheme" / "Solution Oriented Schemes **",
#       "Children's Fund", "Life Cycle Funds" -- varying equity/debt mix
#   "Exchange Traded Funds (ETFs) - Other ETF" / "- ETFs investing overseas"
# These surface as UNCLASSIFIED and are reported, never guessed.


def classify_category(sebi_category: str | None) -> str | None:
    """Map a SEBI category to an asset class, or None when it is not certain."""
    if not sebi_category:
        return None
    normalized = sebi_category.strip().upper()
    for prefix in sorted(CATEGORY_ASSET_CLASS, key=len, reverse=True):
        if normalized.startswith(prefix.upper()):
            return CATEGORY_ASSET_CLASS[prefix]
    return None
