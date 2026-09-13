"""SEBI scheme category -> v0.1 asset_class.

Seeded from AMFI's own category headers. Deliberately conservative: a category
that does not clearly belong to one asset class returns None and stays
UNCLASSIFIED, because a wrong asset class silently corrupts allocation drift
while an unclassified one is visibly surfaced.
"""

from __future__ import annotations

# Matched by prefix, longest first, case-insensitively.
CATEGORY_ASSET_CLASS: dict[str, str] = {
    "Equity Scheme": "EQUITY",
    "Debt Scheme": "DEBT",
    "Hybrid Scheme": "HYBRID",
    "Income Scheme": "DEBT",
    "Growth Scheme": "EQUITY",
    "Liquid Scheme": "CASH",
    "Money Market Scheme": "CASH",
    "Gilt Scheme": "DEBT",
    "Floating Rate Scheme": "DEBT",
}

# Categories deliberately left unmapped: "Other Scheme" (index funds, ETFs and
# fund-of-funds spanning every asset class) and "Solution Oriented Scheme"
# (retirement and children's funds with varying composition). Both are
# classified per-scheme later or surfaced as unclassified.


def classify_category(sebi_category: str | None) -> str | None:
    """Map a SEBI category to an asset class, or None when it is not certain."""
    if not sebi_category:
        return None
    normalized = sebi_category.strip().upper()
    for prefix in sorted(CATEGORY_ASSET_CLASS, key=len, reverse=True):
        if normalized.startswith(prefix.upper()):
            return CATEGORY_ASSET_CLASS[prefix]
    return None
