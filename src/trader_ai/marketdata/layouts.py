"""Column maps for AMFI's two file layouts.

The universe and history files both have 8 semicolon-separated columns, but
ISIN and Plan/Option sit in different positions. Verified against the live
endpoints on 2026-09-13. Keeping the maps as data rather than branches is what
stops that divergence leaking into parsing logic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Layout:
    name: str
    code: int
    scheme_name: int
    plan: int
    option: int
    isin_growth: int
    isin_reinvest: int
    nav: int
    date: int
    header_token: str  # a substring unique to this layout's header line

    @property
    def column_count(self) -> int:
        return 8

    def matches_header(self, header: str) -> bool:
        return self.header_token in header


# Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;
# Plan;Option;Net Asset Value;Date
UNIVERSE = Layout(
    name="universe",
    code=0,
    isin_growth=1,
    isin_reinvest=2,
    scheme_name=3,
    plan=4,
    option=5,
    nav=6,
    date=7,
    header_token="ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name",
)

# Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;
# ISIN Div Reinvestment;Net Asset Value;Date
HISTORY = Layout(
    name="history",
    code=0,
    scheme_name=1,
    plan=2,
    option=3,
    isin_growth=4,
    isin_reinvest=5,
    nav=6,
    date=7,
    header_token="NAV Name;Plan;Option",
)
