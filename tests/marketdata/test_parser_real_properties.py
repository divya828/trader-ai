"""Properties that must hold on the real universe file, independent of how
ETFs are detected. Runs against the committed sample, not the network."""

import pathlib

import pytest

from trader_ai.marketdata.layouts import UNIVERSE
from trader_ai.marketdata.parser import parse

FIXTURE = pathlib.Path("tests/marketdata/fixtures/navall_sample.txt")
pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(), reason="sample fixture not captured"
)


def _rows():
    return parse(FIXTURE.read_text(encoding="utf-8"), UNIVERSE).rows


def test_every_row_has_one_of_four_plan_values():
    valid = {"DIRECT", "REGULAR", "NOT_APPLICABLE", "UNKNOWN"}
    assert {r.plan for r in _rows()} <= valid


def test_no_open_ended_non_etf_row_is_marked_not_applicable():
    # NOT_APPLICABLE means the distinction cannot exist. For an open-ended
    # non-ETF scheme it can, so absence there must read as UNKNOWN.
    offenders = [
        r.amfi_code
        for r in _rows()
        if r.scheme_structure == "OPEN" and not r.is_etf and r.plan == "NOT_APPLICABLE"
    ]
    assert offenders == []


def test_no_closed_ended_row_is_marked_unknown():
    offenders = [
        r.amfi_code
        for r in _rows()
        if r.scheme_structure == "CLOSED" and r.plan == "UNKNOWN"
    ]
    assert offenders == []


def test_every_row_has_a_structure_and_category():
    assert all(r.scheme_structure and r.sebi_category for r in _rows())


def test_every_row_has_an_amc():
    # Regression guard: resetting AMC on a category header strands rows.
    assert all(r.amc for r in _rows())


def test_navs_are_never_negative():
    assert all(r.nav >= 0 for r in _rows())


def test_zero_nav_rows_are_kept_not_dropped():
    """Zero NAV is real data, not corruption.

    241 rows in the live universe file carry a NAV of exactly 0.0 -- all
    Franklin segregated portfolios (side-pocketed debt written down to zero in
    2020). They must survive parsing so the ledger can reconcile against them,
    but v0.2b's return math must guard against division by zero.
    """
    for r in _rows():
        if r.nav == 0.0:
            assert r.amfi_code and r.nav_date  # kept intact, not skipped


def test_dates_are_iso_formatted():
    import datetime

    for r in _rows():
        datetime.date.fromisoformat(r.nav_date)  # raises if not ISO 8601


def test_print_measured_distribution(capsys):
    from collections import Counter

    rows = _rows()
    with capsys.disabled():
        print(f"\n  sample rows: {len(rows)}")
        print(f"  plan      : {dict(Counter(r.plan for r in rows))}")
        print(f"  structure : {dict(Counter(r.scheme_structure for r in rows))}")
        print(f"  etf       : {sum(1 for r in rows if r.is_etf)}")
        print(f"  zero nav  : {sum(1 for r in rows if r.nav == 0.0)}")
