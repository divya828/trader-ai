from trader_ai.llm.client import ExplanationResult
from trader_ai.llm.report import render_report
from trader_ai.rules.finding import Finding, Severity, Subject
from trader_ai.rules.score import DimensionScore, OverallScore


def _finding():
    return Finding(
        rule_id="diversification.category_duplication",
        severity=Severity.MEDIUM,
        title="3 funds share the SEBI category Equity Scheme - Flexi Cap Fund",
        subjects=[Subject("SCHEME", "HDFC Flexi Cap Fund", 0.29, 1)],
        metrics={"fund_count": 3.0, "combined_weight": 0.29},
        citation_key="sebi_categorization",
        computed_at="2026-09-14T00:00:00",
        dimension="DIVERSIFICATION",
    )


def _scores():
    return {
        "COST": DimensionScore("COST", 100.0, 0, rules_run=2, rules_total=2),
        "TAX_EFFICIENCY": DimensionScore(
            "TAX_EFFICIENCY",
            None,
            0,
            unscored_reason="no disposals in ledger",
            rules_run=0,
            rules_total=2,
        ),
    }


def test_report_includes_the_finding_title():
    text = render_report(
        [_finding()], _scores(), OverallScore(81.3, 3, 5), ExplanationResult()
    )
    assert "3 funds share" in text


def test_report_includes_the_explanation_when_available():
    result = ExplanationResult({"diversification.category_duplication#0": "Because X."})
    text = render_report([_finding()], _scores(), OverallScore(81.3, 3, 5), result)
    assert "Because X." in text


def test_report_states_why_an_explanation_is_missing():
    result = ExplanationResult(reason="could not reach the model")
    text = render_report([_finding()], _scores(), OverallScore(81.3, 3, 5), result)
    assert "could not reach the model" in text


def test_the_report_is_usable_without_any_explanation():
    """The deterministic layer already produced the whole report."""
    result = ExplanationResult(reason="no usable API credential")
    text = render_report([_finding()], _scores(), OverallScore(81.3, 3, 5), result)
    assert "fund_count" in text or "3" in text
    assert "SEBI" in text


def test_an_unmeasured_dimension_is_shown_as_unmeasured():
    text = render_report(
        [_finding()], _scores(), OverallScore(81.3, 3, 5), ExplanationResult()
    )
    assert "TAX_EFFICIENCY" in text
    assert "unmeasured" in text.lower() or "no disposals" in text


def test_an_unmeasured_dimension_never_renders_as_a_hundred():
    """Reporting 100 for a dimension with no evidence would be a lie."""
    scores = {
        "TAX_EFFICIENCY": DimensionScore(
            "TAX_EFFICIENCY", None, 0, unscored_reason="no disposals", rules_run=0,
            rules_total=2,
        )
    }
    text = render_report([], scores, OverallScore(None, 0, 5), ExplanationResult())
    assert "100" not in text


def test_a_partially_evaluated_dimension_is_flagged():
    scores = {
        "ALLOCATION": DimensionScore("ALLOCATION", 100.0, 0, rules_run=1, rules_total=2),
    }
    text = render_report(
        [_finding()], scores, OverallScore(100.0, 1, 5), ExplanationResult()
    )
    assert "1/2" in text or "partial" in text.lower()


def test_the_overall_score_reports_its_coverage():
    text = render_report(
        [_finding()], _scores(), OverallScore(81.3, 3, 5), ExplanationResult()
    )
    assert "3" in text and "5" in text


def test_an_unmeasured_overall_score_does_not_render_as_a_number():
    text = render_report([], {}, OverallScore(None, 0, 5), ExplanationResult())
    assert "0.0" not in text


def test_a_report_with_no_findings_says_so():
    text = render_report(
        [], _scores(), OverallScore(100.0, 2, 5), ExplanationResult()
    )
    assert "no findings" in text.lower()


def test_rendering_never_raises_on_an_empty_everything():
    assert isinstance(
        render_report([], {}, OverallScore(None, 0, 5), ExplanationResult()), str
    )
