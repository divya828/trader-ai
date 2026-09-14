"""Rule discovery and execution.

Each rule declares what it needs, so the score can distinguish "nothing wrong"
from "nothing to look at". A rule that raises is contained rather than allowed
to silence every other finding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from trader_ai.rules.context import Context
from trader_ai.rules.families import allocation, behavior, cost, diversification, tax
from trader_ai.rules.finding import Finding


@dataclass(frozen=True)
class Rule:
    rule_id: str
    dimension: str
    run: Callable[[Context], list[Finding]]
    requires: Callable[[Context], bool]


def _has_holdings(ctx: Context) -> bool:
    return bool(ctx.holdings)


def _has_cost_data(ctx: Context) -> bool:
    return ctx.metrics.get("cost_drag") is not None


def _has_tax_evidence(ctx: Context) -> bool:
    # Either a sell has happened, or an IDCW option is held.
    return ctx.disposal_count > 0 or any(
        h.option and "IDCW" in h.option.upper() for h in ctx.holdings
    )


ALL_RULES: list[Rule] = [
    Rule("cost.regular_plan_drag", "COST", cost.regular_plan_drag_rule, _has_cost_data),
    Rule("cost.coverage_incomplete", "COST", cost.coverage_incomplete_rule, _has_cost_data),
    Rule("tax.idcw_inefficiency", "TAX_EFFICIENCY", tax.idcw_inefficiency_rule, _has_tax_evidence),
    Rule(
        "tax.rebalance_stcg_exposure",
        "TAX_EFFICIENCY",
        tax.rebalance_stcg_exposure_rule,
        _has_tax_evidence,
    ),
    Rule(
        "behavior.timing_gap",
        "BEHAVIOR",
        behavior.timing_gap_rule,
        lambda ctx: ctx.disposal_count > 0,
    ),
    Rule(
        "diversification.category_duplication",
        "DIVERSIFICATION",
        diversification.category_duplication_rule,
        _has_holdings,
    ),
    Rule(
        "diversification.low_effective_holdings",
        "DIVERSIFICATION",
        diversification.low_effective_holdings_rule,
        _has_holdings,
    ),
    Rule(
        "allocation.band_breach",
        "ALLOCATION",
        allocation.band_breach_rule,
        lambda ctx: ctx.has_target,
    ),
    Rule(
        "allocation.unclassified_holdings",
        "ALLOCATION",
        allocation.unclassified_holdings_rule,
        _has_holdings,
    ),
]


def evaluate(
    ctx: Context, rules: list[Rule] | None = None
) -> tuple[list[Finding], set[str], dict[str, tuple[int, int]]]:
    """Run every rule whose prerequisites are met.

    Returns the findings, the dimensions that had data to evaluate, and per
    dimension how many of its rules actually ran. The last is what lets a
    partially evaluated dimension say so: with no target allocation,
    ALLOCATION runs one of its two rules, and a bare score would hide that.
    """
    rules = ALL_RULES if rules is None else rules
    findings: list[Finding] = []
    evaluable: set[str] = set()
    coverage: dict[str, list[int]] = {}

    for rule in rules:
        entry = coverage.setdefault(rule.dimension, [0, 0])
        entry[1] += 1
        try:
            if not rule.requires(ctx):
                continue
            evaluable.add(rule.dimension)
            findings.extend(rule.run(ctx))
            entry[0] += 1
        except Exception:  # noqa: BLE001
            # One broken rule must not silence the others. The failure is
            # visible as a missing rule_id rather than a crashed report.
            continue

    return findings, evaluable, {k: (v[0], v[1]) for k, v in coverage.items()}
