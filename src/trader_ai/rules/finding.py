"""The Finding contract.

Three properties, each load-bearing:

Self-contained -- every number behind a finding is in `metrics`, so v0.3
explains rather than recalculates. This is what keeps "deterministic math is
never delegated to an LLM" intact once a model enters the picture.

Cited -- every finding names its source, so an explanatory tier is honest
rather than plausible-sounding.

PII-free BY CONSTRUCTION -- a Subject carries scheme identity and a portfolio
ratio, never a folio number, a PAN, or an absolute amount. The validation below
enforces that at construction time rather than trusting callers, because v0.3's
redaction gate is designed to have nothing to strip.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

VALID_KINDS = ("SCHEME", "SECURITY", "ASSET_CLASS", "PORTFOLIO")

# A folio number looks like "12345/67" or "20244566/ 39".
_FOLIO_SHAPE = re.compile(r"^\d{3,}\s*/\s*\d+$")

# A PAN in two forms. The raw form is "ABCPX1234Z". But this project stores
# PANs masked as first-three + XXX + last-four ("LFGXXX630Q"), and the raw
# pattern does not match that -- so a masked PAN would have flowed into a
# Finding unnoticed. Found by testing the guard against the real ledger rather
# than a synthetic value. Both forms are rejected: a masked PAN is still a
# derived identifier and has no business in a finding.
_PAN_SHAPE = re.compile(r"^(?:[A-Z]{5}[0-9]{4}[A-Z]|[A-Z]{3}X{3}[0-9]{3}[A-Z])$")


class Severity(Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def rank(self) -> int:
        return {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}[self.value]


@dataclass(frozen=True)
class Subject:
    kind: str
    ref: str
    weight: float | None = None
    local_id: int | None = None
    """Ledger-local identity (a scheme_id), used only as a redaction key.

    RedactedSubject has no counterpart field, so this cannot reach an
    outbound payload. It exists because three real fund names each map to
    two scheme_ids, and keying labels on the name merged distinct holdings.
    """

    def __post_init__(self) -> None:
        if self.kind not in VALID_KINDS:
            raise ValueError(f"kind must be one of {VALID_KINDS}, got {self.kind!r}")
        if _FOLIO_SHAPE.match(self.ref.strip()):
            raise ValueError(f"ref looks like a folio number: {self.ref!r}")
        if _PAN_SHAPE.match(self.ref.strip()):
            raise ValueError(f"ref looks like a PAN: {self.ref!r}")
        if self.weight is not None and not (0.0 <= self.weight <= 1.0):
            raise ValueError(
                f"weight is a portfolio ratio in [0,1], not an amount: {self.weight}"
            )


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: Severity
    title: str
    subjects: list[Subject]
    metrics: dict[str, float]
    citation_key: str
    computed_at: str
    dimension: str = ""
    unavailable_reason: str | None = field(default=None)

    def __post_init__(self) -> None:
        if not self.citation_key.strip():
            raise ValueError("every finding requires a citation key")
        if not self.subjects:
            raise ValueError("every finding requires at least one subject")
