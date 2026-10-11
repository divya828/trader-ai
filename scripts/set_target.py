"""Set, show or clear the target asset allocation in the local ledger.

    uv run python scripts/set_target.py                          # show
    uv run python scripts/set_target.py EQUITY=70 DEBT=20 GOLD=10
    uv run python scripts/set_target.py --clear

Weights are given in percent and must sum to 100. Output is weights and drift
only -- never amounts, folio numbers, scheme names, or PAN.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from trader_ai.analytics.rebalancing import band_breaches  # noqa: E402
from trader_ai.db.connection import connect  # noqa: E402
from trader_ai.db.targets import clear_targets, get_targets, set_targets  # noqa: E402
from trader_ai.rules.context import build_context  # noqa: E402

DB_PATH = Path("data/ledger.db")


def _parse(args: list[str]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for arg in args:
        name, sep, value = arg.partition("=")
        if not sep:
            raise ValueError(f"expected CLASS=PERCENT, got {arg!r}")
        weights[name.strip().upper()] = float(value) / 100.0
    return weights


def _show(con) -> None:
    targets = get_targets(con)
    current = build_context(con).asset_class_weights
    if not targets:
        print("No target set; allocation drift is not evaluated.")
    breached = {b.asset_class for b in band_breaches(current, targets)} if targets else set()
    print(f"{'class':<14}{'current':>9}{'target':>9}{'drift':>9}  band")
    for asset_class in sorted(set(current) | set(targets)):
        now = current.get(asset_class, 0.0)
        line = f"{asset_class:<14}{now * 100:>8.1f}%"
        if targets:
            goal = targets.get(asset_class, 0.0)
            status = "BREACH" if asset_class in breached else "ok"
            line += f"{goal * 100:>8.1f}%{(now - goal) * 100:>+8.1f}  {status}"
        print(line)


def main(argv: list[str]) -> int:
    if not DB_PATH.exists():
        print(f"no ledger at {DB_PATH}")
        return 1
    con = connect(DB_PATH)
    try:
        if argv == ["--clear"]:
            clear_targets(con)
            print("Target cleared.")
        elif argv:
            set_targets(con, _parse(argv))
            print("Target saved.")
    except ValueError as exc:
        print(f"Not saved: {exc}")
        return 2
    _show(con)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
