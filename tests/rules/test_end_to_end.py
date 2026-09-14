"""The whole v0.2c pipeline on a synthetic portfolio shaped like the real one.

The real ledger it mirrors: all-Direct plans, no disposals, no IDCW holdings,
no target allocation, and duplicated SEBI categories.
"""

import pytest

from trader_ai.db.connection import (
    apply_schema,
    apply_schema_v02,
    apply_schema_v02c,
    connect,
)
from trader_ai.rules.context import build_context
from trader_ai.rules.registry import evaluate
from trader_ai.rules.score import overall_score, score_dimensions
from trader_ai.rules.store import save_findings, save_scores


@pytest.fixture
def portfolio():
    con = connect(":memory:")
    apply_schema(con)
    apply_schema_v02(con)
    apply_schema_v02c(con)
    con.execute(
        "INSERT INTO folios(folio_id, folio_number, amc) VALUES (1,'12345/67','A')"
    )
    con.execute("INSERT INTO import_runs(import_run_id, source_file) VALUES (1,'a.pdf')")
    # Three funds in one category, as the real portfolio has.
    for i, name in enumerate(["Thematic A", "Thematic B", "Thematic C"], start=1):
        con.execute(
            "INSERT INTO schemes(scheme_id, folio_id, scheme_name, isin, asset_class)"
            " VALUES (?, 1, ?, ?, 'EQUITY')",
            (i, name, f"INF00{i}"),
        )
        con.execute(
            "INSERT INTO md_schemes(amfi_code, isin_growth, scheme_name, sebi_category,"
            " plan, option, asset_class, last_seen) VALUES (?, ?, ?,"
            " 'Equity Scheme - Sectoral/ Thematic', 'DIRECT', 'Growth Option',"
            " 'EQUITY', '2026-01-01')",
            (f"1000{i}", f"INF00{i}", name),
        )
        con.execute(
            "INSERT INTO holdings_snapshot(import_run_id, scheme_id, as_of_date,"
            " units, price, value) VALUES (1, ?, '2026-01-07', 100, 25, 2500)",
            (i,),
        )
    con.commit()
    yield con
    con.close()


def test_pipeline_produces_findings_and_scores(portfolio):
    ctx = build_context(portfolio)
    findings, evaluable, coverage = evaluate(ctx)
    scores = score_dimensions(findings, evaluable, coverage)
    assert findings, "a portfolio with three funds in one category should flag"
    assert set(scores)


def test_tax_dimension_is_unmeasured_not_perfect(portfolio):
    """The finding that motivated this design.

    No disposals and no IDCW holdings means tax behaviour was never observed.
    """
    ctx = build_context(portfolio)
    findings, evaluable, coverage = evaluate(ctx)
    scores = score_dimensions(findings, evaluable, coverage)
    assert scores["TAX_EFFICIENCY"].score is None
    assert scores["TAX_EFFICIENCY"].unscored_reason


def test_behavior_dimension_is_unmeasured_without_disposals(portfolio):
    ctx = build_context(portfolio)
    findings, evaluable, coverage = evaluate(ctx)
    scores = score_dimensions(findings, evaluable, coverage)
    assert scores["BEHAVIOR"].score is None


def test_allocation_band_rule_stays_silent_without_a_target(portfolio):
    ctx = build_context(portfolio)
    findings, evaluable, coverage = evaluate(ctx)
    assert not any(f.rule_id == "allocation.band_breach" for f in findings)


def test_allocation_is_reported_as_only_partly_evaluated(portfolio):
    """One of ALLOCATION's two rules could not run.

    A bare 100 would read as "allocation is fine" when half of it was never
    evaluated.
    """
    ctx = build_context(portfolio)
    findings, evaluable, coverage = evaluate(ctx)
    scores = score_dimensions(findings, evaluable, coverage)
    allocation = scores["ALLOCATION"]
    assert allocation.score is not None
    assert allocation.fully_evaluated is False


def test_overall_reports_how_many_dimensions_were_measured(portfolio):
    ctx = build_context(portfolio)
    findings, evaluable, coverage = evaluate(ctx)
    overall = overall_score(score_dimensions(findings, evaluable, coverage))
    assert overall.measured_count < overall.total_count


def test_unmeasured_dimensions_do_not_inflate_the_overall_score(portfolio):
    """Scoring absent evidence as 100 would overstate the portfolio.

    On the real ledger this is the difference between 81.3 and 88.8.
    """
    ctx = build_context(portfolio)
    findings, evaluable, coverage = evaluate(ctx)
    scores = score_dimensions(findings, evaluable, coverage)
    honest = overall_score(scores).score

    naive = sum(
        (s.score if s.score is not None else 100.0) for s in scores.values()
    ) / len(scores)
    assert honest < naive


def test_findings_persist_without_any_identifying_data(portfolio):
    import re

    ctx = build_context(portfolio)
    findings, evaluable, coverage = evaluate(ctx)
    save_findings(portfolio, "run-1", findings)
    save_scores(portfolio, list(score_dimensions(findings, evaluable, coverage).values()))

    text = " ".join(
        str(value)
        for table in ("findings", "finding_subjects", "finding_metrics")
        for row in portfolio.execute(f"SELECT * FROM {table}")
        for value in tuple(row)
    )
    # The ledger contains folio 12345/67; it must not appear here.
    assert "12345/67" not in text
    assert not re.search(r"[A-Z]{5}[0-9]{4}[A-Z]", text)


def test_a_second_run_accumulates_history(portfolio):
    ctx = build_context(portfolio)
    findings, evaluable, coverage = evaluate(ctx)
    scores = list(score_dimensions(findings, evaluable, coverage).values())
    save_scores(portfolio, scores)
    save_scores(portfolio, scores)
    count = portfolio.execute("SELECT COUNT(*) FROM health_scores").fetchone()[0]
    assert count == len(scores) * 2
