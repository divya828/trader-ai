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


def _api_message(exc: anthropic.APIStatusError) -> str | None:
    """Pull the human-readable message out of an API error body."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
    return None


@dataclass(frozen=True)
class ExplanationResult:
    explanations: dict[str, str] = field(default_factory=dict)
    reason: str | None = None

    @property
    def available(self) -> bool:
        return self.reason is None


class HostedExplainer:
    """Sends redacted findings to Claude and returns text per finding_key."""

    def __init__(self, client: object | None = None) -> None:
        self._client = client or anthropic.Anthropic(
            max_retries=MAX_RETRIES, timeout=TIMEOUT_SECONDS
        )

    def explain(self, findings: list[RedactedFinding]) -> ExplanationResult:
        """Explain each finding, keyed by finding_key.

        Never raises; degrades with a reason.
        """
        if not findings:
            return ExplanationResult()

        expected = {f.finding_key for f in findings}

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
        except TypeError:
            # With NO credential configured, the SDK resolves auth lazily and
            # raises TypeError from the REQUEST, not the constructor -- and
            # never as AuthenticationError, which means a key was present and
            # rejected. Letting it escape would crash a report whose numbers
            # were all computed locally, the opposite of what this promises.
            return ExplanationResult(reason="no API credential is configured")
        except anthropic.AuthenticationError:
            return ExplanationResult(reason="no usable API credential")
        except anthropic.APIConnectionError:
            return ExplanationResult(reason="could not reach the model")
        except anthropic.RateLimitError:
            return ExplanationResult(reason="rate limited after retries")
        except anthropic.APIStatusError as exc:
            # Include the API's own message. A bare status code made "your
            # credit balance is too low" indistinguishable from a malformed
            # request, and the first is something the user can act on.
            detail = _api_message(exc)
            reason = f"model returned {exc.status_code}"
            return ExplanationResult(reason=f"{reason}: {detail}" if detail else reason)

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
            entry["finding_key"]: entry["text"]
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("finding_key") in expected
            and isinstance(entry.get("text"), str)
        }
        return ExplanationResult(explanations=explanations)
