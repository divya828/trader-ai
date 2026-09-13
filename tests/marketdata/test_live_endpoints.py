"""Live endpoint checks. Skipped unless TRADER_AI_LIVE=1.

    TRADER_AI_LIVE=1 uv run pytest tests/marketdata/test_live_endpoints.py -v

Every other test in this suite runs offline against a committed fixture. These
assert only the structural facts the parser depends on, so they fail loudly if
AMFI changes its format rather than silently producing wrong numbers.

If one of these fails, do NOT relax the assertion -- the format has changed and
the parser needs revisiting.
"""

import os
from datetime import date, timedelta

import pytest

from trader_ai.marketdata.amfi_client import fetch_history, fetch_universe
from trader_ai.marketdata.layouts import HISTORY, UNIVERSE
from trader_ai.marketdata.parser import parse

pytestmark = pytest.mark.skipif(
    os.environ.get("TRADER_AI_LIVE") != "1",
    reason="set TRADER_AI_LIVE=1 to run live endpoint checks",
)


@pytest.fixture(scope="module")
def universe_text():
    """Downloaded once for the whole module (~1.5MB)."""
    return fetch_universe()


@pytest.fixture(scope="module")
def history_text():
    """A short recent range (~1.16MB per day, so keep it to 2 days)."""
    end = date.today() - timedelta(days=3)
    return fetch_history(end - timedelta(days=1), end)


def test_universe_endpoint_shape_is_unchanged(universe_text):
    assert UNIVERSE.matches_header(universe_text.splitlines()[0])
    result = parse(universe_text, UNIVERSE)
    assert len(result.rows) > 10_000
    assert result.skipped.get("malformed", 0) == 0


def test_every_live_universe_row_has_an_amc(universe_text):
    # The regression that motivated persisting AMC across category headers:
    # resetting it strands Franklin segregated-portfolio rows.
    result = parse(universe_text, UNIVERSE)
    missing = [r.amfi_code for r in result.rows if not r.amc]
    assert missing == [], f"{len(missing)} rows lost their AMC"


def test_every_live_universe_row_has_a_category(universe_text):
    result = parse(universe_text, UNIVERSE)
    assert all(r.sebi_category for r in result.rows)


def test_live_plan_values_stay_within_the_four_known_values(universe_text):
    result = parse(universe_text, UNIVERSE)
    assert {r.plan for r in result.rows} <= {
        "DIRECT",
        "REGULAR",
        "NOT_APPLICABLE",
        "UNKNOWN",
    }


def test_live_navs_are_never_negative(universe_text):
    # Zero is legitimate (side-pocketed debt); negative would be corruption.
    result = parse(universe_text, UNIVERSE)
    assert all(r.nav >= 0 for r in result.rows)


def test_live_category_coverage_stays_material(universe_text):
    """Guard against AMFI renaming categories out from under the seed list.

    Coverage was 84.5% when measured. A large drop means new category names
    have appeared and holdings would silently fall back to UNCLASSIFIED.
    """
    from trader_ai.marketdata.categories import classify_category

    rows = parse(universe_text, UNIVERSE).rows
    covered = sum(1 for r in rows if classify_category(r.sebi_category))
    ratio = covered / len(rows)
    assert ratio > 0.75, f"category coverage fell to {ratio:.1%} ({covered}/{len(rows)})"


def test_history_endpoint_shape_is_unchanged(history_text):
    assert HISTORY.matches_header(history_text.splitlines()[0])
    result = parse(history_text, HISTORY)
    assert len(result.rows) > 1_000


def test_history_layout_is_not_the_universe_layout(history_text):
    # If AMFI ever aligned the two layouts, parsing history with the history
    # map would start reading the wrong columns. Catch that here.
    assert not UNIVERSE.matches_header(history_text.splitlines()[0])


def test_history_rows_carry_isins_in_the_swapped_position(history_text):
    """The history file puts ISIN at index 4, not 1.

    If the layout were wrong, isin_growth would come back holding a scheme
    name instead. Indian mutual fund ISINs start with "INF".
    """
    rows = [r for r in parse(history_text, HISTORY).rows if r.isin_growth]
    assert rows, "history rows should carry ISINs"
    assert sum(1 for r in rows if r.isin_growth.startswith("INF")) / len(rows) > 0.9
