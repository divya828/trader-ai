from trader_ai.marketdata.layouts import HISTORY, UNIVERSE


def test_universe_layout_matches_real_header():
    header = (
        "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;"
        "Scheme Name;Plan;Option;Net Asset Value;Date"
    )
    assert UNIVERSE.matches_header(header)


def test_history_layout_matches_real_header():
    header = (
        "Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;"
        "ISIN Div Reinvestment;Net Asset Value;Date"
    )
    assert HISTORY.matches_header(header)


def test_layouts_do_not_match_each_other():
    # The two files differ by more than a leading column; a layout must not
    # silently accept the other's header or every ISIN would be misread.
    universe_header = (
        "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;"
        "Scheme Name;Plan;Option;Net Asset Value;Date"
    )
    assert not HISTORY.matches_header(universe_header)


def test_universe_column_positions():
    assert UNIVERSE.code == 0
    assert UNIVERSE.isin_growth == 1
    assert UNIVERSE.scheme_name == 3
    assert UNIVERSE.plan == 4
    assert UNIVERSE.option == 5
    assert UNIVERSE.nav == 6
    assert UNIVERSE.date == 7


def test_history_column_positions_differ_from_universe():
    # ISIN and Plan/Option are swapped relative to the universe file.
    assert HISTORY.code == 0
    assert HISTORY.scheme_name == 1
    assert HISTORY.plan == 2
    assert HISTORY.option == 3
    assert HISTORY.isin_growth == 4
    assert HISTORY.nav == 6
    assert HISTORY.date == 7
