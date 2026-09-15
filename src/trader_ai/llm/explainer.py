"""Redact, explain, then put the real names back.

The label map never leaves this process. Re-attachment happens here, after the
response returns, so the user reads real fund names while the model never saw
one.
"""

from __future__ import annotations

from trader_ai.llm.client import ExplanationResult, HostedExplainer
from trader_ai.llm.redaction import redact
from trader_ai.rules.finding import Finding


def _reattach(text: str, labels: dict[str, str]) -> str:
    """Swap opaque labels back for real names.

    Longest label first, so "fund_1" cannot corrupt "fund_10". With
    shortest-first and unrelated names, "fund_10" becomes "Alpha Fund0" -- a
    fabricated fund name presented to the user as a real holding.
    """
    for label in sorted(labels, key=len, reverse=True):
        text = text.replace(label, labels[label])
    return text


def explain_findings(
    findings: list[Finding], client: object | None = None
) -> ExplanationResult:
    """Explain findings via a hosted model, with names redacted in transit."""
    redaction = redact(findings)
    explainer = client or HostedExplainer()
    result = explainer.explain(redaction.findings)

    if not result.available:
        return result

    return ExplanationResult(
        explanations={
            rule_id: _reattach(text, redaction.labels)
            for rule_id, text in result.explanations.items()
        }
    )
