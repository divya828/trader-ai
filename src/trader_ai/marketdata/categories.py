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


# --- Layer 2: name inference, for categories that span asset classes ---
#
# "Other Scheme - Index Funds" (1,078 rows) and the untyped ETF/FoF families
# cannot be classified by category: an index fund may track Nifty, a gilt
# index, or gold. Scheme names usually say which, but not always -- measured
# on the live file, 212 of 1,078 index-fund names match more than one asset
# class (e.g. "Crisil IBX 50:50 Gilt Plus SDL Apr 2028 Index Fund" reads as
# both debt and index-equity).
#
# Rule: a name that matches exactly one asset class is classified. A name
# matching several, or none, returns None and stays UNCLASSIFIED. Ambiguity
# must never be resolved by guessing -- a wrong asset class corrupts
# allocation drift silently, while an unclassified one is visibly reported.

import re as _re

_NAME_PATTERNS: dict[str, str] = {
    # Gold/silver first conceptually: these names are unambiguous.
    "GOLD": r"\bGOLD\b|\bSILVER\b",
    # NOTE: "PSU" alone is NOT a debt marker. "PSU Fund" is an equity fund
    # investing in public-sector companies; only "PSU Bond"/"PSU Debt" is
    # debt. Validating name inference against AMFI's own typed categories
    # caught this mislabelling 206 rows as DEBT.
    "DEBT": (
        r"\bG-?SEC\b|\bGILT\b|\bBOND\b|\bSDL\b|\bTREASURY\b|\bLIQUID\b"
        r"|\bDEBT\b|MONEY\s*MARKET|CONSTANT\s+MATURITY|\bAAA\b"
        r"|\bIBX\b|\bDURATION\b|\bOVERNIGHT\b"
    ),
    # "HYBRID"/"BALANCED"/"ASSET ALLOCATION" names often also say "Equity"
    # (e.g. "Aggressive Hybrid Equity Fund"). Listing HYBRID as its own family
    # makes such a name match two families, so it returns None instead of
    # being mislabelled EQUITY.
    "HYBRID": (
        r"\bHYBRID\b|\bBALANCED\b|ASSET\s+ALLOCAT|\bARBITRAGE\b"
        r"|MULTI[\s-]*ASSET|EQUITY\s+SAVINGS"  # "Equity Savings Fund" is SEBI-hybrid
    ),
    "EQUITY": (
        r"\bNIFTY\b|\bSENSEX\b|\bBSE\b|LARGE\s*CAP|MID\s*CAP|SMALL\s*CAP"
        r"|\bEQUITY\b|\bMOMENTUM\b|\bALPHA\b|\bPHARMA\b|\bFMCG\b|\bAUTO\b"
        r"|\bINFRA\b|\bIT\b"
    ),
}
_COMPILED = {k: _re.compile(v, _re.I) for k, v in _NAME_PATTERNS.items()}


def classify_by_name(scheme_name: str | None) -> str | None:
    """Infer asset class from a scheme name, or None when not unambiguous.

    Returns a class only when exactly one pattern family matches. This is a
    fallback for categories that cannot be classified, never an override of
    one that can.
    """
    if not scheme_name:
        return None
    matches = [k for k, pattern in _COMPILED.items() if pattern.search(scheme_name)]
    return matches[0] if len(matches) == 1 else None
