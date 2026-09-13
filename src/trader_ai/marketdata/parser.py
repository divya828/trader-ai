"""Parse AMFI NAV files into normalized rows.

Pure: text in, dataclasses out. No HTTP, no database, no filesystem.

The file is a state machine. Two kinds of non-data lines appear -- SEBI
category headers and bare AMC names -- and each carries down onto the data rows
that follow. AMC deliberately persists across category headers: AMFI does not
re-emit it after every header, and resetting strands rows (verified: 23 rows in
the live universe file, all Franklin segregated-portfolio schemes).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from trader_ai.marketdata.layouts import Layout

_HEADER = re.compile(
    r"^(Open Ended|Close Ended|Interval Fund)\s*Schemes?\s*\((.*)\)\s*$"
)
_STRUCTURE = {
    "Open Ended": "OPEN",
    "Close Ended": "CLOSED",
    "Interval Fund": "INTERVAL",
}
_ETF_MARKERS = ("ETF", "EXCHANGE TRADED")


@dataclass(frozen=True)
class SchemeRow:
    amfi_code: str
    scheme_name: str
    isin_growth: str | None
    isin_reinvest: str | None
    plan: str            # DIRECT | REGULAR | NOT_APPLICABLE | UNKNOWN
    option: str | None
    nav: float
    nav_date: str        # ISO 8601
    sebi_category: str | None
    scheme_structure: str
    amc: str | None
    is_etf: bool


@dataclass
class ParseResult:
    rows: list[SchemeRow] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)


def _clean(value: str) -> str | None:
    value = value.strip()
    return None if value in ("", "-") else value


def _iso_date(value: str) -> str | None:
    try:
        return datetime.strptime(value.strip(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def _classify_plan(raw: str, structure: str, is_etf: bool) -> str:
    """Four-valued plan. NOT_APPLICABLE and UNKNOWN are different facts.

    NOT_APPLICABLE: no Direct/Regular distinction exists (ETF, close-ended).
    UNKNOWN: the distinction exists but the source omitted it.
    """
    normalized = raw.strip().upper()
    if normalized.startswith("DIRECT"):
        return "DIRECT"
    if normalized.startswith("REGULAR"):
        return "REGULAR"
    if is_etf or structure in ("CLOSED", "INTERVAL"):
        return "NOT_APPLICABLE"
    return "UNKNOWN"


def parse(text: str, layout: Layout) -> ParseResult:
    """Parse an AMFI NAV file body using the given column layout."""
    result = ParseResult()
    category: str | None = None
    structure = "OPEN"
    amc: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if layout.matches_header(line):
            continue

        header_match = _HEADER.match(line)
        if header_match:
            structure = _STRUCTURE[header_match.group(1)]
            category = header_match.group(2).strip()
            # NOTE: amc is intentionally NOT reset here.
            continue

        if ";" not in line:
            amc = line
            continue

        parts = [p.strip() for p in line.split(";")]
        if len(parts) < layout.column_count or not parts[layout.code].isdigit():
            result.skipped["malformed"] += 1
            continue

        try:
            nav = float(parts[layout.nav])
        except ValueError:
            result.skipped["non_numeric_nav"] += 1
            continue

        nav_date = _iso_date(parts[layout.date])
        if nav_date is None:
            result.skipped["bad_date"] += 1
            continue

        scheme_name = parts[layout.scheme_name]
        is_etf = any(m in scheme_name.upper() for m in _ETF_MARKERS)

        result.rows.append(
            SchemeRow(
                amfi_code=parts[layout.code],
                scheme_name=scheme_name,
                isin_growth=_clean(parts[layout.isin_growth]),
                isin_reinvest=_clean(parts[layout.isin_reinvest]),
                plan=_classify_plan(parts[layout.plan], structure, is_etf),
                option=_clean(parts[layout.option]),
                nav=nav,
                nav_date=nav_date,
                sebi_category=category,
                scheme_structure=structure,
                amc=amc,
                is_etf=is_etf,
            )
        )
    return result
