from trader_ai.llm.client import ExplanationResult
from trader_ai.llm.explainer import explain_findings
from trader_ai.rules.finding import Finding, Severity, Subject


def _finding(rule_id="diversification.category_duplication", subjects=None):
    return Finding(
        rule_id=rule_id,
        severity=Severity.MEDIUM,
        title="3 funds share a category",
        subjects=subjects or [Subject("SCHEME", "HDFC Flexi Cap Fund", 0.29, 1)],
        metrics={"fund_count": 3.0},
        citation_key="sebi_categorization",
        computed_at="2026-09-14T00:00:00",
        dimension="DIVERSIFICATION",
    )


class _FakeExplainer:
    def __init__(self, result):
        self.result = result
        self.received = None

    def explain(self, findings):
        self.received = findings
        return self.result


def test_the_client_only_ever_receives_redacted_findings():
    fake = _FakeExplainer(
        ExplanationResult({"diversification.category_duplication": "x"})
    )
    explain_findings([_finding()], client=fake)
    assert all(type(f).__name__ == "RedactedFinding" for f in fake.received)


def test_labels_are_replaced_with_real_names_in_the_returned_text():
    fake = _FakeExplainer(
        ExplanationResult(
            {"diversification.category_duplication": "fund_1 overlaps with others."}
        )
    )
    result = explain_findings([_finding()], client=fake)
    text = result.explanations["diversification.category_duplication"]
    assert "HDFC Flexi Cap Fund" in text
    assert "fund_1" not in text


def test_re_attachment_handles_several_labels():
    subjects = [
        Subject("SCHEME", "Fund Alpha", 0.2, 1),
        Subject("SCHEME", "Fund Beta", 0.3, 2),
    ]
    fake = _FakeExplainer(
        ExplanationResult({"diversification.category_duplication": "fund_1 and fund_2."})
    )
    result = explain_findings([_finding(subjects=subjects)], client=fake)
    text = result.explanations["diversification.category_duplication"]
    assert "Fund Alpha" in text and "Fund Beta" in text


def test_an_unavailable_result_passes_through_with_its_reason():
    fake = _FakeExplainer(ExplanationResult(reason="could not reach the model"))
    result = explain_findings([_finding()], client=fake)
    assert not result.available
    assert result.reason == "could not reach the model"


def test_no_findings_returns_an_empty_available_result():
    fake = _FakeExplainer(ExplanationResult())
    result = explain_findings([], client=fake)
    assert result.available
    assert result.explanations == {}


def test_a_label_that_does_not_appear_in_the_text_is_harmless():
    fake = _FakeExplainer(
        ExplanationResult({"diversification.category_duplication": "No labels here."})
    )
    result = explain_findings([_finding()], client=fake)
    assert (
        result.explanations["diversification.category_duplication"] == "No labels here."
    )


def test_longer_labels_are_replaced_before_shorter_prefixes():
    """fund_1 must not corrupt fund_10.

    The names here are deliberately NOT sequential. With names like "Fund 1"
    and "Fund 10", shortest-first replacement happens to produce the right
    string by coincidence -- "fund_10" becomes "Fund 1" + leftover "0" --
    so the test would pass against buggy code. With unrelated names the bug
    is visible: shortest-first yields "Alpha Fund0", a fabricated name shown
    to the user as if it were a real holding.
    """
    subjects = [
        Subject("SCHEME", "Alpha Fund", 0.05, 1),
        *[Subject("SCHEME", f"Filler {i}", 0.05, i) for i in range(2, 10)],
        Subject("SCHEME", "Omega Fund", 0.05, 10),
    ]
    fake = _FakeExplainer(
        ExplanationResult({"diversification.category_duplication": "fund_10 is largest."})
    )
    result = explain_findings([_finding(subjects=subjects)], client=fake)
    text = result.explanations["diversification.category_duplication"]
    assert text == "Omega Fund is largest."
    assert "Fund0" not in text  # the shortest-first corruption
