"""A metric result that is either a value or an explicit reason it is missing.

Returning None for "cannot compute" invites callers to coerce it to zero. That
is precisely the error the health score must not make: an unmeasured dimension
is not a clean one. Making unavailability carry a reason forces the caller to
handle it, and makes the reason reportable to the user.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Measurement:
    value: float | None
    reason: str | None

    @classmethod
    def of(cls, value: float) -> Measurement:
        """A computed result. A genuine 0.0 is available, not missing."""
        return cls(value=float(value), reason=None)

    @classmethod
    def unavailable(cls, reason: str) -> Measurement:
        """No result, with a reportable explanation."""
        if not reason or not reason.strip():
            raise ValueError("unavailable() requires a non-empty reason")
        return cls(value=None, reason=reason.strip())

    @property
    def available(self) -> bool:
        return self.reason is None

    def __bool__(self) -> bool:
        return self.available

    def or_else(self, default: float) -> float:
        return self.value if self.available else default
