import json

from trader_ai.llm.prompt import (
    EXPLANATION_SCHEMA,
    SYSTEM_PROMPT,
    build_user_message,
)
from trader_ai.llm.redaction import RedactedFinding, RedactedSubject


def _redacted():
    return [
        RedactedFinding(
            finding_key="diversification.category_duplication#0",
            rule_id="diversification.category_duplication",
            severity="MEDIUM",
            subjects=[RedactedSubject("SCHEME", "fund_1", 0.29)],
            metrics={"fund_count": 3.0, "combined_weight": 0.29},
            citation_source="SEBI circular SEBI/HO/IMD/DF3/CIR/P/2017/114",
            citation_claim="Schemes are assigned to defined categories...",
        )
    ]


def test_system_prompt_forbids_computing_numbers():
    lowered = SYSTEM_PROMPT.lower()
    assert "do not" in lowered
    assert "calculat" in lowered or "comput" in lowered


def test_system_prompt_forbids_investment_advice():
    assert "advice" in SYSTEM_PROMPT.lower()


def test_system_prompt_says_labels_are_opaque():
    assert "label" in SYSTEM_PROMPT.lower()


def test_user_message_contains_the_findings_as_json():
    message = build_user_message(_redacted())
    assert "diversification.category_duplication" in message
    assert "fund_1" in message


def test_user_message_carries_every_metric():
    message = build_user_message(_redacted())
    assert "fund_count" in message
    assert "combined_weight" in message


def test_user_message_carries_the_citation():
    message = build_user_message(_redacted())
    assert "SEBI" in message


def test_schema_requires_one_entry_per_rule_id():
    assert EXPLANATION_SCHEMA["type"] == "object"
    assert "explanations" in EXPLANATION_SCHEMA["properties"]


def test_schema_keys_explanations_by_finding_key():
    """finding_key is unique; rule_id is not (four findings share one)."""
    item = EXPLANATION_SCHEMA["properties"]["explanations"]["items"]
    assert "finding_key" in item["properties"]
    assert "text" in item["properties"]
    assert set(item["required"]) == {"finding_key", "text"}


def test_schema_is_valid_json():
    json.dumps(EXPLANATION_SCHEMA)


def test_empty_findings_produce_a_message_without_crashing():
    assert isinstance(build_user_message([]), str)
