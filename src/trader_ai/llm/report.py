"""Assemble findings, scores and explanations into readable output.

Everything here works without a model. When an explanation is missing the
report says so and why, then prints the finding's own numbers and citation --
which were always the substance. The prose was the enhancement.
"""

from __future__ import annotations

from trader_ai.llm.client import ExplanationResult
from trader_ai.rules.citations import citation
from trader_ai.rules.finding import Finding
from trader_ai.rules.score import DimensionScore, OverallScore


def _render_scores(scores: dict[str, DimensionScore]) -> list[str]:
    lines = ["HEALTH SCORE", "-" * 12]
    for name, score in scores.items():
        if score.score is None:
            reason = score.unscored_reason or "no data"
            lines.append(f"  {name:16} unmeasured   ({reason})")
            continue
        coverage = f"[{score.rules_run}/{score.rules_total} rules]"
        partial = "" if score.fully_evaluated else "  <- partial"
        lines.append(f"  {name:16} {score.score:5.1f}        {coverage}{partial}")
    return lines


def _render_finding(finding: Finding, explanation: str | None) -> list[str]:
    reference = citation(finding.citation_key)
    lines = [
        "",
        f"[{finding.severity.value}] {finding.title}",
        f"  rule     : {finding.rule_id}",
        "  numbers  : "
        + ", ".join(f"{k}={v:g}" for k, v in sorted(finding.metrics.items())),
        f"  source   : {reference.source}",
    ]
    if explanation:
        lines.append(f"  meaning  : {explanation}")
    return lines


def render_report(
    findings: list[Finding],
    scores: dict[str, DimensionScore],
    overall: OverallScore,
    explanations: ExplanationResult,
) -> str:
    """Render the whole report. Never raises, with or without a model."""
    lines: list[str] = []

    if overall.score is None:
        lines.append(
            f"OVERALL: unmeasured "
            f"({overall.measured_count}/{overall.total_count} dimensions measured)"
        )
    else:
        lines.append(
            f"OVERALL: {overall.score:.1f} over "
            f"{overall.measured_count}/{overall.total_count} dimensions measured"
        )
    lines.append("")
    lines.extend(_render_scores(scores))

    lines.append("")
    if not findings:
        lines.append("No findings.")
    else:
        lines.append(f"FINDINGS ({len(findings)})")
        lines.append("-" * 12)
        for finding in findings:
            lines.extend(
                _render_finding(finding, explanations.explanations.get(finding.rule_id))
            )

    if not explanations.available:
        lines.append("")
        lines.append(f"Explanations unavailable: {explanations.reason}")
        lines.append("The findings above were computed locally and are unaffected.")

    return "\n".join(lines)
