import pathlib

import pytest

from trader_ai.marketdata.layouts import HISTORY, UNIVERSE
from trader_ai.marketdata.parser import ParseResult, parse

FIXTURE = pathlib.Path("tests/marketdata/fixtures/navall_sample.txt")

SYNTHETIC_UNIVERSE = """\
Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date

Open Ended Schemes(Equity Scheme - Flexi Cap Fund)

Acme Mutual Fund

100001;INF001A01011;-;Acme Flexi Cap Fund;Direct Plan;Growth Option;25.1234;11-Sep-2026
100002;INF001A01029;INF001A01037;Acme Flexi Cap Fund;Regular Plan;Growth Option;22.5000;11-Sep-2026

Open Ended Schemes(Other Scheme - Index Funds)

100003;INF001A01045;-;Acme Nifty ETF;;;150.7500;11-Sep-2026

Close Ended Schemes(Debt Scheme - Fixed Maturity Plan)

100004;INF001A01052;-;Acme FMP Series 1;;;10.5000;11-Sep-2026
100005;INF001A01060;-;Acme Broken Row;Direct Plan;Growth Option;N.A.;11-Sep-2026
"""


def test_parses_synthetic_rows():
    result = parse(SYNTHETIC_UNIVERSE, UNIVERSE)
    assert isinstance(result, ParseResult)
    assert len(result.rows) == 4  # the N.A. row is skipped


def test_non_numeric_nav_is_skipped_and_counted():
    result = parse(SYNTHETIC_UNIVERSE, UNIVERSE)
    assert result.skipped["non_numeric_nav"] == 1


def test_category_carries_down_to_following_rows():
    rows = {r.amfi_code: r for r in parse(SYNTHETIC_UNIVERSE, UNIVERSE).rows}
    assert rows["100001"].sebi_category == "Equity Scheme - Flexi Cap Fund"
    assert rows["100004"].sebi_category == "Debt Scheme - Fixed Maturity Plan"


def test_amc_carries_down_and_persists_across_category_headers():
    # AMFI does not re-emit the AMC after every category header. Resetting it
    # would strand rows with no AMC, breaking cost-drag sibling matching.
    rows = {r.amfi_code: r for r in parse(SYNTHETIC_UNIVERSE, UNIVERSE).rows}
    assert rows["100001"].amc == "Acme Mutual Fund"
    assert rows["100003"].amc == "Acme Mutual Fund"  # after a new category header
    assert rows["100004"].amc == "Acme Mutual Fund"  # after another one


def test_scheme_structure_from_category_header():
    rows = {r.amfi_code: r for r in parse(SYNTHETIC_UNIVERSE, UNIVERSE).rows}
    assert rows["100001"].scheme_structure == "OPEN"
    assert rows["100004"].scheme_structure == "CLOSED"


def test_missing_isin_dash_becomes_none():
    rows = {r.amfi_code: r for r in parse(SYNTHETIC_UNIVERSE, UNIVERSE).rows}
    assert rows["100001"].isin_reinvest is None
    assert rows["100002"].isin_reinvest == "INF001A01037"


def test_dates_normalized_to_iso():
    rows = {r.amfi_code: r for r in parse(SYNTHETIC_UNIVERSE, UNIVERSE).rows}
    assert rows["100001"].nav_date == "2026-09-11"


def test_plan_direct_and_regular_mapped():
    rows = {r.amfi_code: r for r in parse(SYNTHETIC_UNIVERSE, UNIVERSE).rows}
    assert rows["100001"].plan == "DIRECT"
    assert rows["100002"].plan == "REGULAR"


def test_etf_with_empty_plan_is_not_applicable():
    rows = {r.amfi_code: r for r in parse(SYNTHETIC_UNIVERSE, UNIVERSE).rows}
    assert rows["100003"].is_etf is True
    assert rows["100003"].plan == "NOT_APPLICABLE"


def test_closed_ended_with_empty_plan_is_not_applicable():
    rows = {r.amfi_code: r for r in parse(SYNTHETIC_UNIVERSE, UNIVERSE).rows}
    assert rows["100004"].plan == "NOT_APPLICABLE"


def test_open_ended_non_etf_with_empty_plan_is_unknown():
    text = """\
Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date

Open Ended Schemes(Equity Scheme - Large Cap Fund)

Acme Mutual Fund

100006;INF001A01078;-;Acme Mystery Fund;;;12.3400;11-Sep-2026
"""
    rows = {r.amfi_code: r for r in parse(text, UNIVERSE).rows}
    # Open-ended, not an ETF: the distinction COULD exist, so its absence is
    # UNKNOWN, never NOT_APPLICABLE.
    assert rows["100006"].plan == "UNKNOWN"


def test_zero_nav_row_is_kept_not_skipped():
    # 241 rows in the live file have NAV exactly 0.0 (Franklin side-pocketed
    # debt). Legitimate data, not corruption.
    text = """\
Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date

Open Ended Schemes(Debt Scheme - Credit Risk Fund)

Acme Mutual Fund

100007;INF001A01086;-;Acme Segregated Portfolio 1;Direct Plan;Growth Option;0.0000;11-Sep-2026
"""
    result = parse(text, UNIVERSE)
    assert len(result.rows) == 1
    assert result.rows[0].nav == 0.0


def test_history_layout_reads_swapped_columns():
    history_text = (
        "Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;"
        "ISIN Div Reinvestment;Net Asset Value;Date\n"
        "\n"
        "Open Ended Schemes(Equity Scheme - Flexi Cap Fund)\n"
        "\n"
        "Acme Mutual Fund\n"
        "\n"
        "100001;Acme Flexi Cap Fund;Direct Plan;Growth Option;INF001A01011;-;"
        "25.1234;01-Sep-2026\n"
    )
    rows = parse(history_text, HISTORY).rows
    assert len(rows) == 1
    row = rows[0]
    # If the layout were ignored, the ISIN would be read from position 1 and
    # would wrongly come back as the scheme name.
    assert row.isin_growth == "INF001A01011"
    assert row.scheme_name == "Acme Flexi Cap Fund"
    assert row.plan == "DIRECT"


def test_real_sample_parses_without_malformed_rows():
    result = parse(FIXTURE.read_text(encoding="utf-8"), UNIVERSE)
    assert len(result.rows) > 200
    assert result.skipped.get("malformed", 0) == 0


def test_real_sample_assigns_amc_to_every_row():
    # Regression guard for the segregated-portfolio rows that lose their AMC
    # when the parser resets AMC on a category header.
    result = parse(FIXTURE.read_text(encoding="utf-8"), UNIVERSE)
    missing = [r.amfi_code for r in result.rows if not r.amc]
    assert missing == [], f"rows with no AMC: {missing[:5]}"


def test_real_sample_assigns_category_to_every_row():
    result = parse(FIXTURE.read_text(encoding="utf-8"), UNIVERSE)
    assert all(r.sebi_category for r in result.rows)


def test_real_sample_exercises_all_four_plan_values():
    result = parse(FIXTURE.read_text(encoding="utf-8"), UNIVERSE)
    assert {r.plan for r in result.rows} == {
        "DIRECT", "REGULAR", "UNKNOWN", "NOT_APPLICABLE",
    }


def test_real_sample_etfs_are_not_applicable():
    result = parse(FIXTURE.read_text(encoding="utf-8"), UNIVERSE)
    etfs = [r for r in result.rows if r.is_etf]
    assert etfs, "fixture should contain ETF rows"
    assert all(r.plan == "NOT_APPLICABLE" for r in etfs)
