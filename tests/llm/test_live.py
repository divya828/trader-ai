"""One real call to the hosted model. Skipped unless TRADER_AI_LIVE_LLM=1.

    TRADER_AI_LIVE_LLM=1 uv run pytest tests/llm/test_live.py -v

Costs money and requires a credential, so it is never part of the default
suite. It exists to prove the request shape is actually accepted -- every other
test uses a fake transport and would pass against a wrong schema.
"""

import os

import pytest

from trader_ai.llm.client import HostedExplainer
from trader_ai.llm.redaction import RedactedFinding, RedactedSubject

pytestmark = pytest.mark.skipif(
    os.environ.get("TRADER_AI_LIVE_LLM") != "1",
    reason="set TRADER_AI_LIVE_LLM=1 to run the live model check",
)


def _redacted():
    return [
        RedactedFinding(
            finding_key="diversification.category_duplication#0",
            rule_id="diversification.category_duplication",
            severity="MEDIUM",
            subjects=[
                RedactedSubject("SCHEME", "fund_1", 0.12),
                RedactedSubject("SCHEME", "fund_2", 0.17),
            ],
            metrics={"fund_count": 2.0, "combined_weight": 0.29},
            citation_source="SEBI circular SEBI/HO/IMD/DF3/CIR/P/2017/114",
            citation_claim=(
                "Schemes are assigned to defined categories, so holding several "
                "funds in one category adds names without adding exposure."
            ),
        )
    ]


def test_a_real_call_returns_an_explanation():
    result = HostedExplainer().explain(_redacted())
    assert result.available, result.reason
    assert "diversification.category_duplication#0" in result.explanations
    assert len(result.explanations["diversification.category_duplication#0"]) > 20


def test_the_model_uses_the_opaque_labels_rather_than_inventing_names():
    result = HostedExplainer().explain(_redacted())
    assert result.available, result.reason
    text = result.explanations["diversification.category_duplication#0"]
    # It need not mention a label, but it must not invent a real fund house.
    for invented in ("HDFC", "ICICI", "SBI", "Axis", "Kotak", "Nippon"):
        assert invented not in text, f"model invented a fund name: {invented}"


def test_the_model_does_not_offer_investment_advice():
    """The tool is advisory-only: it explains findings, it does not recommend.

    A soft check -- prose varies -- but a direct instruction to buy or sell
    would be a clear breach of the system prompt.
    """
    result = HostedExplainer().explain(_redacted())
    assert result.available, result.reason
    lowered = result.explanations["diversification.category_duplication#0"].lower()
    for phrase in ("you should sell", "you should buy", "i recommend buying"):
        assert phrase not in lowered, f"model gave advice: {phrase!r}"
