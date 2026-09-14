import dataclasses

import pytest

from trader_ai.rules.finding import Finding, Severity, Subject


def _finding(**overrides):
    defaults = dict(
        rule_id="cost.regular_plan_drag",
        severity=Severity.MEDIUM,
        title="Regular plan holdings cost more than their Direct siblings",
        subjects=[Subject(kind="SCHEME", ref="Some Fund", weight=0.12)],
        metrics={"drag_per_year": 0.0089},
        citation_key="bogle_cost_matters",
        computed_at="2026-09-14T00:00:00",
    )
    defaults.update(overrides)
    return Finding(**defaults)


def test_finding_carries_every_number_behind_it():
    # Self-contained: v0.3 explains, never recalculates.
    finding = _finding()
    assert finding.metrics["drag_per_year"] == pytest.approx(0.0089)


def test_finding_is_immutable():
    finding = _finding()
    with pytest.raises(dataclasses.FrozenInstanceError):
        finding.title = "changed"  # type: ignore[misc]


def test_subject_weight_is_a_ratio_not_an_amount():
    with pytest.raises(ValueError, match="ratio"):
        Subject(kind="SCHEME", ref="Some Fund", weight=250000.0)


def test_subject_weight_may_be_none():
    assert Subject(kind="PORTFOLIO", ref="portfolio", weight=None).weight is None


def test_subject_kind_is_validated():
    with pytest.raises(ValueError, match="kind"):
        Subject(kind="FOLIO", ref="12345/67")


def test_subject_rejects_a_folio_shaped_ref():
    """A folio number must never become a Subject ref.

    v0.3's redaction gate depends on Finding being clean by construction.
    """
    with pytest.raises(ValueError, match="folio"):
        Subject(kind="SCHEME", ref="12345/67")


def test_subject_rejects_a_pan_shaped_ref():
    with pytest.raises(ValueError, match="PAN"):
        Subject(kind="SCHEME", ref="ABCPX1234Z")


def test_finding_requires_a_citation():
    with pytest.raises(ValueError, match="citation"):
        _finding(citation_key="")


def test_finding_requires_at_least_one_subject():
    with pytest.raises(ValueError, match="subject"):
        _finding(subjects=[])


def test_severity_has_four_levels():
    assert [s.value for s in Severity] == ["INFO", "LOW", "MEDIUM", "HIGH"]


def test_severity_orders_by_seriousness():
    assert Severity.HIGH.rank > Severity.MEDIUM.rank > Severity.LOW.rank > Severity.INFO.rank
