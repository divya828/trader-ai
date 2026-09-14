import pytest

from trader_ai.rules.citations import CITATIONS, citation


def test_every_citation_has_a_source_and_a_claim():
    for key, ref in CITATIONS.items():
        assert ref.source.strip(), f"{key} has no source"
        assert ref.claim.strip(), f"{key} has no claim"


def test_citation_lookup_returns_the_reference():
    ref = citation("bogle_cost_matters")
    assert "Bogle" in ref.source


def test_unknown_citation_key_raises():
    # A rule citing a source that does not exist must fail loudly, not
    # silently emit an uncited finding.
    with pytest.raises(KeyError):
        citation("no_such_source")


def test_claims_are_specific_not_generic():
    # "see the literature" is not a citation.
    for key, ref in CITATIONS.items():
        assert len(ref.claim) > 20, f"{key} claim is too vague: {ref.claim!r}"


def test_expected_sources_are_present():
    for key in (
        "bogle_cost_matters",
        "morningstar_mind_the_gap",
        "daryanani_5_25",
        "sebi_categorization",
        "herfindahl_concentration",
        "sebi_direct_plan",
        "rolling_return_method",
        "india_capital_gains",
    ):
        assert key in CITATIONS
