import pytest

from trader_ai.analytics.measurement import Measurement
from trader_ai.rules.context import Context, HoldingView
from trader_ai.rules.families.behavior import timing_gap_rule


def _ctx(disposal_count, gaps):
    holding = HoldingView(
        scheme_id=1,
        scheme_name="Fund",
        sebi_category="Equity Scheme - Flexi Cap Fund",
        asset_class="EQUITY",
        plan="DIRECT",
        option="Growth Option",
        weight=1.0,
    )
    return Context(
        holdings=[holding],
        asset_class_weights={"EQUITY": 1.0},
        disposal_count=disposal_count,
        has_target=False,
        metrics={"behavior_gaps": gaps},
    )


def test_silent_without_disposals_even_when_the_gap_is_negative():
    """The real portfolio: 402 purchases, 0 redemptions, median gap -7.27pp.

    Money-weighted return structurally lags time-weighted return when money
    keeps entering a rising market. Firing here would manufacture a finding
    from arithmetic, not detect behaviour.
    """
    ctx = _ctx(disposal_count=0, gaps={1: Measurement.of(-0.0727)})
    assert timing_gap_rule(ctx) == []


def test_fires_when_disposals_exist_and_the_gap_is_materially_negative():
    ctx = _ctx(disposal_count=5, gaps={1: Measurement.of(-0.08)})
    findings = timing_gap_rule(ctx)
    assert len(findings) == 1
    assert findings[0].rule_id == "behavior.timing_gap"
    assert findings[0].metrics["median_gap"] == pytest.approx(-0.08)


def test_silent_when_disposals_exist_but_the_gap_is_small():
    ctx = _ctx(disposal_count=5, gaps={1: Measurement.of(-0.005)})
    assert timing_gap_rule(ctx) == []


def test_silent_when_the_gap_is_positive():
    ctx = _ctx(disposal_count=5, gaps={1: Measurement.of(0.04)})
    assert timing_gap_rule(ctx) == []


def test_silent_when_no_gap_could_be_computed():
    ctx = _ctx(disposal_count=5, gaps={1: Measurement.unavailable("no nav coverage")})
    assert timing_gap_rule(ctx) == []


def test_silent_when_metrics_carry_no_gaps_at_all():
    ctx = _ctx(disposal_count=5, gaps={})
    assert timing_gap_rule(ctx) == []
