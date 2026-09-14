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


def test_subject_rejects_a_masked_pan_ref():
    """This project stores PANs masked (first3 + XXX + last4).

    The raw PAN pattern does not match that form, so a masked PAN would have
    passed straight into a Finding. Caught by testing the guard against a real
    ledger value rather than a synthetic one. A masked PAN is still a derived
    identifier and does not belong in a finding.
    """
    with pytest.raises(ValueError, match="PAN"):
        Subject(kind="SCHEME", ref="LFGXXX630Q")


def test_subject_still_accepts_a_normal_scheme_name():
    # The guard must not become so broad it rejects legitimate refs.
    subject = Subject(
        kind="SCHEME", ref="HDFC Flexi Cap Fund - Direct Plan - Growth", weight=0.12
    )
    assert subject.weight == 0.12


def test_subject_accepts_an_isin():
    # ISINs look like INF179K01158 -- similar shape to a PAN, must not be
    # rejected. An ISIN is public reference data, not an identifier of a person.
    assert Subject(kind="SCHEME", ref="INF179K01158").ref == "INF179K01158"


def test_subject_carries_an_optional_local_id():
    """local_id keys redaction on identity rather than name.

    Three real fund names each map to two scheme_ids (the same fund held in
    two folios). Keying labels on the name collapsed them into one label
    carrying two different weights.
    """
    subject = Subject(kind="SCHEME", ref="Some Fund", weight=0.1, local_id=42)
    assert subject.local_id == 42


def test_local_id_defaults_to_none():
    assert Subject(kind="PORTFOLIO", ref="portfolio").local_id is None


def test_two_subjects_with_one_name_can_differ_by_local_id():
    a = Subject(kind="SCHEME", ref="ICICI Prudential Technology Fund", local_id=2)
    b = Subject(kind="SCHEME", ref="ICICI Prudential Technology Fund", local_id=3)
    assert a != b
    assert a.local_id != b.local_id
