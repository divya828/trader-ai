"""Static registry of the sources rules rely on.

Every rule names a source and the specific claim it uses. This is what lets
v0.3 explain a finding honestly instead of generating plausible-sounding
rationale, and it is why an unknown citation key raises rather than silently
producing an uncited finding.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CitationRef:
    source: str   # author or organisation, work, year
    claim: str    # the specific claim relied upon


CITATIONS: dict[str, CitationRef] = {
    "bogle_cost_matters": CitationRef(
        source="John C. Bogle, Common Sense on Mutual Funds (1999)",
        claim=(
            "Costs compound against the investor: a persistent expense "
            "difference reduces terminal wealth by far more than the "
            "nominal annual figure suggests."
        ),
    ),
    "sebi_direct_plan": CitationRef(
        source="SEBI circular CIR/IMD/DF/21/2012, effective 1 January 2013",
        claim=(
            "Every mutual fund scheme must offer a Direct plan with a lower "
            "expense ratio than its Regular plan, identical in portfolio and "
            "differing only in distributor commission."
        ),
    ),
    "morningstar_mind_the_gap": CitationRef(
        source="Morningstar, Mind the Gap (annual study)",
        claim=(
            "Investor returns trail fund returns because money tends to "
            "arrive after gains and leave after losses; the difference is "
            "the measurable cost of timing."
        ),
    ),
    "daryanani_5_25": CitationRef(
        source="Gobind Daryanani, Journal of Financial Planning (2008)",
        claim=(
            "Rebalance when an asset class drifts 5 absolute percentage "
            "points or 25 percent relative to its target, whichever binds "
            "first; the relative band governs small allocations."
        ),
    ),
    "sebi_categorization": CitationRef(
        source="SEBI circular SEBI/HO/IMD/DF3/CIR/P/2017/114",
        claim=(
            "Schemes are assigned to defined categories, and a fund house "
            "may offer only one scheme per category, so holding several "
            "funds in one category adds names without adding exposure."
        ),
    ),
    "herfindahl_concentration": CitationRef(
        source="Herfindahl-Hirschman concentration index",
        claim=(
            "The reciprocal of the sum of squared weights gives the "
            "effective number of holdings, which falls far below the "
            "nominal count when weights are uneven."
        ),
    ),
    "rolling_return_method": CitationRef(
        source="Rolling-return methodology, standard practice in fund analysis",
        claim=(
            "A single point-to-point return depends entirely on its two "
            "endpoints; the distribution of rolling windows shows the "
            "consistency a single figure conceals."
        ),
    ),
    "india_capital_gains": CitationRef(
        source="Income-tax Act 1961, as amended by Finance Act 2023 and 2024",
        claim=(
            "Equity holdings sold within 365 days realise short-term gains "
            "taxed at a higher rate than long-term gains, and IDCW payouts "
            "are taxed at the investor's slab rate."
        ),
    ),
}


def citation(key: str) -> CitationRef:
    """Look up a citation, raising if the key is unknown."""
    if key not in CITATIONS:
        raise KeyError(f"unknown citation key: {key!r}")
    return CITATIONS[key]
