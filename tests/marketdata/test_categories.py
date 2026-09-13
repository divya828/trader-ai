from trader_ai.marketdata.categories import CATEGORY_ASSET_CLASS, classify_category

VALID = {"EQUITY", "DEBT", "HYBRID", "GOLD", "CASH"}


def test_every_seeded_value_is_a_valid_asset_class():
    assert set(CATEGORY_ASSET_CLASS.values()) <= VALID


def test_equity_categories_map_to_equity():
    assert classify_category("Equity Scheme - Flexi Cap Fund") == "EQUITY"
    assert classify_category("Equity Scheme - Large Cap Fund") == "EQUITY"


def test_debt_categories_map_to_debt():
    assert classify_category("Debt Scheme - Gilt Fund") == "DEBT"
    assert classify_category("Debt Scheme - Liquid Fund") == "DEBT"


def test_hybrid_categories_map_to_hybrid():
    assert classify_category("Hybrid Scheme - Balanced Advantage Fund") == "HYBRID"


def test_unknown_category_returns_none_not_a_guess():
    # A wrong asset class silently corrupts allocation drift. Unmatched must
    # stay unmatched so the data-quality rule can surface it.
    assert classify_category("Totally Novel Scheme - Something") is None


def test_none_category_returns_none():
    assert classify_category(None) is None


def test_empty_category_returns_none():
    assert classify_category("") is None
    assert classify_category("   ") is None


def test_prefix_matching_is_case_insensitive():
    assert classify_category("EQUITY SCHEME - MID CAP FUND") == "EQUITY"


def test_solution_oriented_schemes_are_not_guessed():
    # Retirement/children's funds vary in composition; they must not be
    # assumed EQUITY.
    assert classify_category("Solution Oriented Scheme - Retirement Fund") is None
    assert classify_category("Solution Oriented Scheme - Childrens Fund") is None


def test_other_scheme_is_not_guessed():
    # "Other Scheme" spans index funds, ETFs and FoFs across every asset
    # class; category alone cannot classify it.
    assert classify_category("Other Scheme - Index Funds") is None
    assert classify_category("Other Scheme - FoF Overseas") is None


def test_real_categories_from_the_fixture_are_handled_without_error():
    # Every category in the committed sample must either map to a valid asset
    # class or return None -- never raise, never return something else.
    import pathlib

    from trader_ai.marketdata.layouts import UNIVERSE
    from trader_ai.marketdata.parser import parse

    fixture = pathlib.Path("tests/marketdata/fixtures/navall_sample.txt")
    rows = parse(fixture.read_text(encoding="utf-8"), UNIVERSE).rows
    for category in {r.sebi_category for r in rows}:
        result = classify_category(category)
        assert result is None or result in VALID
