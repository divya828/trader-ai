import dataclasses
import json

import pytest

from trader_ai.llm.redaction import RedactedFinding, RedactedSubject, redact
from trader_ai.rules.finding import Finding, Severity, Subject


def _finding(subjects, rule_id="diversification.category_duplication"):
    return Finding(
        rule_id=rule_id,
        severity=Severity.MEDIUM,
        title="3 funds share the SEBI category Equity Scheme - Flexi Cap Fund",
        subjects=subjects,
        metrics={"fund_count": 3.0, "combined_weight": 0.29},
        citation_key="sebi_categorization",
        computed_at="2026-09-14T00:00:00",
        dimension="DIVERSIFICATION",
    )


def test_scheme_refs_are_replaced_by_opaque_labels():
    result = redact([_finding([Subject("SCHEME", "HDFC Flexi Cap Fund", 0.1, 1)])])
    assert result.findings[0].subjects[0].label == "fund_1"


def test_the_real_name_is_retained_locally():
    result = redact([_finding([Subject("SCHEME", "HDFC Flexi Cap Fund", 0.1, 1)])])
    assert result.labels["fund_1"] == "HDFC Flexi Cap Fund"


def test_identical_names_with_different_local_ids_get_different_labels():
    """The real ledger case: one fund name, two scheme_ids, two folios.

    Keying on the name merged them into one label carrying two weights.
    """
    name = "ICICI Prudential Technology Fund - Direct Plan - Growth"
    result = redact(
        [_finding([Subject("SCHEME", name, 0.05, 2), Subject("SCHEME", name, 0.09, 3)])]
    )
    labels = [s.label for s in result.findings[0].subjects]
    assert labels[0] != labels[1]


def test_the_same_local_id_reuses_one_label_across_findings():
    a = _finding([Subject("SCHEME", "Fund A", 0.1, 7)], rule_id="cost.regular_plan_drag")
    b = _finding([Subject("SCHEME", "Fund A", 0.1, 7)], rule_id="tax.idcw_inefficiency")
    result = redact([a, b])
    assert result.findings[0].subjects[0].label == result.findings[1].subjects[0].label


def test_asset_class_refs_are_not_redacted():
    # EQUITY is a category, not a holding. Redacting it would make the
    # explanation incomprehensible while protecting nothing.
    result = redact([_finding([Subject("ASSET_CLASS", "EQUITY", 0.6)])])
    assert result.findings[0].subjects[0].label == "EQUITY"


def test_portfolio_refs_are_not_redacted():
    result = redact([_finding([Subject("PORTFOLIO", "portfolio")])])
    assert result.findings[0].subjects[0].label == "portfolio"


def test_titles_are_dropped():
    """Rule titles embed scheme and category names verbatim."""
    result = redact([_finding([Subject("SCHEME", "HDFC Flexi Cap Fund", 0.1, 1)])])
    assert not hasattr(result.findings[0], "title")


def test_redacted_subject_has_no_field_for_local_id():
    """The outbound type cannot carry the key, by construction."""
    fields = {f.name for f in dataclasses.fields(RedactedSubject)}
    assert "local_id" not in fields
    assert "ref" not in fields


def test_metrics_survive_intact():
    result = redact([_finding([Subject("SCHEME", "Fund A", 0.1, 1)])])
    assert result.findings[0].metrics["combined_weight"] == pytest.approx(0.29)


def test_citation_is_resolved_to_source_and_claim():
    result = redact([_finding([Subject("SCHEME", "Fund A", 0.1, 1)])])
    finding = result.findings[0]
    assert "SEBI" in finding.citation_source
    assert len(finding.citation_claim) > 20


def test_an_unknown_citation_key_raises():
    bad = _finding([Subject("SCHEME", "Fund A", 0.1, 1)])
    bad = dataclasses.replace(bad, citation_key="no_such_source")
    with pytest.raises(KeyError):
        redact([bad])


def test_weights_are_preserved_as_ratios():
    result = redact([_finding([Subject("SCHEME", "Fund A", 0.1234, 1)])])
    assert 0.0 <= result.findings[0].subjects[0].weight <= 1.0


def test_redacting_nothing_is_harmless():
    result = redact([])
    assert result.findings == []
    assert result.labels == {}


def test_a_redacted_finding_serialises_without_any_name():
    name = "HDFC Flexi Cap Fund - Direct Plan - Growth"
    result = redact([_finding([Subject("SCHEME", name, 0.1, 1)])])
    blob = json.dumps([dataclasses.asdict(f) for f in result.findings])
    assert name not in blob
    assert "fund_1" in blob
