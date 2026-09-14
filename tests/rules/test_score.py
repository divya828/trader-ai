import pytest

from trader_ai.rules.finding import Finding, Severity, Subject
from trader_ai.rules.score import DIMENSIONS, score_dimensions


def _finding(dimension, severity):
    return Finding(
        rule_id="x.y",
        severity=severity,
        title="t",
        subjects=[Subject(kind="PORTFOLIO", ref="portfolio")],
        metrics={},
        citation_key="bogle_cost_matters",
        computed_at="2026-09-14T00:00:00",
        dimension=dimension,
    )


def test_a_dimension_with_no_findings_but_data_scores_full():
    scores = score_dimensions([], evaluable={"COST"})
    assert scores["COST"].score == pytest.approx(100.0)
    assert scores["COST"].unscored_reason is None


def test_a_dimension_with_no_data_scores_none_not_zero_or_full():
    """The real case: TAX_EFFICIENCY with no disposals and no IDCW holdings.

    Scoring it 100 would report perfect tax efficiency for a portfolio whose
    tax behaviour has never been observed.
    """
    scores = score_dimensions([], evaluable=set())
    assert scores["TAX_EFFICIENCY"].score is None
    assert scores["TAX_EFFICIENCY"].unscored_reason


def test_findings_reduce_the_score_by_severity():
    high = score_dimensions([_finding("COST", Severity.HIGH)], evaluable={"COST"})
    low = score_dimensions([_finding("COST", Severity.LOW)], evaluable={"COST"})
    assert high["COST"].score < low["COST"].score


def test_score_never_goes_below_zero():
    findings = [_finding("COST", Severity.HIGH) for _ in range(20)]
    assert score_dimensions(findings, evaluable={"COST"})["COST"].score >= 0.0


def test_info_findings_do_not_reduce_the_score():
    scores = score_dimensions([_finding("COST", Severity.INFO)], evaluable={"COST"})
    assert scores["COST"].score == pytest.approx(100.0)


def test_every_dimension_appears_in_the_result():
    scores = score_dimensions([], evaluable={"COST"})
    assert set(scores) == set(DIMENSIONS)


def test_a_partially_evaluated_dimension_says_so():
    """ALLOCATION with no target runs 1 of its 2 rules.

    A bare 100 would read as "allocation is fine" when the band-breach rule
    never ran. fully_evaluated makes the gap visible.
    """
    scores = score_dimensions(
        [], evaluable={"ALLOCATION"}, rule_coverage={"ALLOCATION": (1, 2)}
    )
    allocation = scores["ALLOCATION"]
    assert allocation.score == pytest.approx(100.0)
    assert allocation.fully_evaluated is False
    assert allocation.rules_run == 1 and allocation.rules_total == 2


def test_a_fully_evaluated_dimension_reports_full_coverage():
    scores = score_dimensions(
        [], evaluable={"COST"}, rule_coverage={"COST": (2, 2)}
    )
    assert scores["COST"].fully_evaluated is True


def test_overall_is_computed_over_scored_dimensions_only():
    from trader_ai.rules.score import overall_score

    scores = score_dimensions(
        [_finding("COST", Severity.HIGH)], evaluable={"COST", "ALLOCATION"}
    )
    overall = overall_score(scores)
    assert overall.measured_count == 2
    assert overall.total_count == len(DIMENSIONS)
    assert overall.score is not None


def test_overall_is_none_when_nothing_could_be_measured():
    from trader_ai.rules.score import overall_score

    overall = overall_score(score_dimensions([], evaluable=set()))
    assert overall.score is None
    assert overall.measured_count == 0
