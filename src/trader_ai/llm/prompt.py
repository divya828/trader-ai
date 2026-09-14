"""What the model is told, and what shape it must answer in.

Separate from the client so prompt content is testable without a network or a
key, and so the module that decides what leaves the machine stays small.

The system prompt does three jobs, each guarding a project constraint: the
model may not produce a number (non-negotiable #3), may not give investment
advice (the tool is advisory-only and explains findings), and must treat labels
as opaque strings (they are the redaction, and inventing a real name would
defeat it).
"""

from __future__ import annotations

import dataclasses
import json

from trader_ai.llm.redaction import RedactedFinding

SYSTEM_PROMPT = """\
You explain findings from a personal investment analysis tool to its owner.

Every number you are given was computed by tested, deterministic code. Restate
those numbers when useful, but do not calculate, adjust, extrapolate or infer
any figure of your own. If a number you want is not given, say so instead of
producing one.

Holdings appear as opaque labels such as "fund_1". Use those labels verbatim.
Never guess or invent a real fund name -- the labels exist precisely so that
holdings are not disclosed.

Explain what each finding means and why it matters, grounded in the cited
source. Do not offer investment advice, recommend buying or selling anything,
or suggest what the owner should do with their money. This tool is advisory
only and never places trades.

Write plainly, two or three sentences per finding. No preamble, no headings."""

EXPLANATION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "explanations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rule_id": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["rule_id", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["explanations"],
    "additionalProperties": False,
}


def build_user_message(findings: list[RedactedFinding]) -> str:
    """Serialise redacted findings as the model's input.

    Keyed by rule_id on the way out too, so a response cannot be silently
    misattributed to the wrong finding.
    """
    payload = [dataclasses.asdict(f) for f in findings]
    return (
        "Explain each of these findings. Return one entry per rule_id.\n\n"
        + json.dumps(payload, indent=2, sort_keys=True)
    )
