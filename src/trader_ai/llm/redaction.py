"""The redaction gate.

Everything that leaves this machine passes through here first. A Finding is
already free of amounts, folios and PAN -- v0.2c enforces that at construction
-- but it still names schemes, and a name plus a weight discloses which funds
are held and in what proportion. So names are replaced by opaque labels and the
mapping stays local.

Labels key on `Subject.local_id` (a scheme_id), not on the name. Three real
fund names each map to two scheme_ids -- the same fund held through two folios
-- and keying on the name merged them into a single label carrying two
different weights, which would have made the explanation wrong.

`RedactedSubject` has no field for the local_id and no field for the real ref,
so neither can reach a payload: the outbound type simply cannot express them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from trader_ai.rules.citations import citation
from trader_ai.rules.finding import Finding

# Refs of these kinds are category names ("EQUITY") or fixed words
# ("portfolio"), not holdings. Redacting them would obscure the explanation
# while protecting nothing.
NON_IDENTIFYING_KINDS = ("ASSET_CLASS", "PORTFOLIO")


@dataclass(frozen=True)
class RedactedSubject:
    kind: str
    label: str
    weight: float | None = None


@dataclass(frozen=True)
class RedactedFinding:
    finding_key: str
    """Unique within one evaluation: "<rule_id>#<index>".

    rule_id alone is NOT unique -- the real portfolio produces four findings
    all carrying diversification.category_duplication. Keying explanations by
    rule_id collapsed them into one, silently leaving three unexplained.
    """

    rule_id: str
    severity: str
    subjects: list[RedactedSubject]
    metrics: dict[str, float]
    citation_source: str
    citation_claim: str


@dataclass(frozen=True)
class Redaction:
    findings: list[RedactedFinding]
    labels: dict[str, str] = field(default_factory=dict)
    """label -> real ref. Stays in this process; never serialised outbound."""


def redact(findings: list[Finding]) -> Redaction:
    """Convert findings into the only shape the hosted client will accept."""
    labels: dict[str, str] = {}
    by_key: dict[object, str] = {}

    def label_for(subject) -> str:
        if subject.kind in NON_IDENTIFYING_KINDS:
            return subject.ref
        key = subject.local_id if subject.local_id is not None else subject.ref
        if key not in by_key:
            name = f"fund_{len(by_key) + 1}"
            by_key[key] = name
            labels[name] = subject.ref
        return by_key[key]

    redacted: list[RedactedFinding] = []
    for index, finding in enumerate(findings):
        reference = citation(finding.citation_key)  # raises on an unknown key
        redacted.append(
            RedactedFinding(
                finding_key=f"{finding.rule_id}#{index}",
                rule_id=finding.rule_id,
                severity=finding.severity.value,
                subjects=[
                    RedactedSubject(kind=s.kind, label=label_for(s), weight=s.weight)
                    for s in finding.subjects
                ],
                metrics=dict(finding.metrics),
                citation_source=reference.source,
                citation_claim=reference.claim,
            )
        )

    return Redaction(findings=redacted, labels=labels)
