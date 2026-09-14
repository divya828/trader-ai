"""Behaviour rules.

The timing gap requires evidence of timing before it will fire.

Measured on a real portfolio: 372 purchases, 30 SIP instalments, zero
redemptions, and a median behaviour gap of -7.27 percentage points. A rule
firing on "gap < 0" would report bad timing there. It would be wrong --
money-weighted return structurally lags time-weighted return whenever money
keeps entering a rising market, because later contributions compound for less
time. That is arithmetic, not a decision.

So the rule demands at least one disposal. Without a sell there is no
sell-low decision to detect, and a finding manufactured from an artifact is
worse than no finding.
"""

from __future__ import annotations

import statistics
from datetime import datetime

from trader_ai.rules.context import Context
from trader_ai.rules.finding import Finding, Severity, Subject

DIMENSION = "BEHAVIOR"
# Below this, a negative gap is noise rather than a signal worth reporting.
MATERIAL_GAP = 0.02


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def timing_gap_rule(ctx: Context) -> list[Finding]:
    """Money-weighted return trailing the funds' own returns, where selling occurred."""
    if ctx.disposal_count == 0:
        # No sell decisions have been made, so no timing behaviour exists to
        # measure. See the module docstring.
        return []

    gaps = ctx.metrics.get("behavior_gaps") or {}
    values = [m.value for m in gaps.values() if m.available]
    if not values:
        return []

    median = statistics.median(values)
    if median >= -MATERIAL_GAP:
        return []

    return [
        Finding(
            rule_id="behavior.timing_gap",
            severity=Severity.MEDIUM if median < -0.05 else Severity.LOW,
            title=(
                f"Your returns trail the funds' own by "
                f"{abs(median) * 100:.1f} points a year"
            ),
            subjects=[Subject(kind="PORTFOLIO", ref="portfolio")],
            metrics={
                "median_gap": median,
                "schemes_measured": float(len(values)),
                "disposal_count": float(ctx.disposal_count),
            },
            citation_key="morningstar_mind_the_gap",
            computed_at=_now(),
            dimension=DIMENSION,
        )
    ]
