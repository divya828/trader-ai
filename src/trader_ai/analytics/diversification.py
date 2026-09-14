"""Concentration and category duplication.

Source: SEBI scheme categorization framework; Herfindahl concentration.

Two complementary readings. Herfindahl / effective holdings answers "how many
funds do I effectively own?" -- ten funds where one is 90% of the portfolio is
effectively one fund. Category duplication answers "am I buying the same thing
repeatedly?" -- four flexi-cap funds is the error the literature names most
often, and it does not show up in a count of holdings.

Holdings-level overlap (do two funds hold the same stocks?) is deferred: AMFI
publishes no machine-readable portfolio disclosures, and scraping 40 AMC sites
is out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryGroup:
    count: int
    value: float


def herfindahl(values: list[float]) -> float:
    """Herfindahl index over holding values. 1.0 = everything in one holding."""
    positive = [float(v) for v in values if v and v > 0]
    total = sum(positive)
    if total <= 0:
        return 0.0
    return sum((v / total) ** 2 for v in positive)


def effective_holdings(values: list[float]) -> float:
    """Effective number of holdings: 1 / H.

    Ten funds with one at 90% gives roughly 1.2 -- the honest count.
    """
    index = herfindahl(values)
    return 0.0 if index <= 0 else 1.0 / index


def category_duplication(
    holdings: list[tuple[str, str | None, float]],
) -> dict[str, CategoryGroup]:
    """Categories holding more than one fund, with their count and value.

    holdings: (scheme_name, sebi_category, value) triples. Entries with no
    category are ignored rather than grouped under a fake bucket.
    """
    grouped: dict[str, list[float]] = {}
    for _, category, value in holdings:
        if not category:
            continue
        grouped.setdefault(category, []).append(float(value))

    return {
        category: CategoryGroup(count=len(values), value=sum(values))
        for category, values in grouped.items()
        if len(values) > 1
    }
