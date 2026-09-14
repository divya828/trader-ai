"""The only module in this project that talks to a hosted model.

It accepts `RedactedFinding` and nothing else. That is the enforcement the
project's fourth constraint asks for: the gate is the input type the hosted node
accepts, not a sentence in a prompt. There is no overload taking a `Finding`,
and `RedactedFinding` has no field that could carry a scheme name or an id.

Failure never propagates. The deterministic layer has already produced the whole
report; an explanation is an enhancement, so a missing key or a dropped
connection degrades to "unavailable, and here is why".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic

from trader_ai.llm.prompt import EXPLANATION_SCHEMA, SYSTEM_PROMPT, build_user_message
from trader_ai.llm.redaction import RedactedFinding

MODEL = "claude-opus-5"
MAX_TOKENS = 4096
# The SDK retries connection errors, 408/409/429 and 5xx with exponential
# backoff. Two is its default; a hand-rolled loop on top would double-retry.
MAX_RETRIES = 2
TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class ExplanationResult:
    explanations: dict[str, str] = field(default_factory=dict)
    reason: str | None = None

    @property
    def available(self) -> bool:
        return self.reason is None


class HostedExplainer:
    """Sends redacted findings to Claude and returns text per rule_id."""

    def __init__(self, client: object | None = None) -> None:
        self._client = client or anthropic.Anthropic(
            max_retries=MAX_RETRIES, timeout=TIMEOUT_SECONDS
        )

    def explain(self, findings: list[RedactedFinding]) -> ExplanationResult:
        """Explain each finding. Never raises; degrades with a reason."""
        if not findings:
            return ExplanationResult()

        expected = {f.rule_id for f in findings}

        try:
            message = self._client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_message(findings)}],
                output_config={
                    "format": {"type": "json_schema", "schema": EXPLANATION_SCHEMA}
                },
            )
        except anthropic.AuthenticationError:
            return ExplanationResult(reason="no usable API credential")
        except anthropic.APIConnectionError:
            return ExplanationResult(reason="could not reach the model")
        except anthropic.RateLimitError:
            return ExplanationResult(reason="rate limited after retries")
        except anthropic.APIStatusError as exc:
            return ExplanationResult(reason=f"model returned {exc.status_code}")

        return self._parse(message, expected)

    @staticmethod
    def _parse(message, expected: set[str]) -> ExplanationResult:
        text = "".join(
            block.text
            for block in message.content
            if getattr(block, "type", "") == "text"
        )
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            return ExplanationResult(reason="could not parse the model response")

        entries = payload.get("explanations") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            return ExplanationResult(reason="response had an unexpected format")

        # Keep only rule_ids that were actually sent: a response must not
        # introduce findings the deterministic layer never produced.
        explanations = {
            entry["rule_id"]: entry["text"]
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("rule_id") in expected
            and isinstance(entry.get("text"), str)
        }
        return ExplanationResult(explanations=explanations)
