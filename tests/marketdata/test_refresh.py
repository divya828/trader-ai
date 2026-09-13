import pytest

from trader_ai.db.connection import apply_schema, apply_schema_v02, connect
from trader_ai.marketdata.refresh import refresh_universe

SAMPLE = """\
Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date

Open Ended Schemes(Equity Scheme - Flexi Cap Fund)

Acme Mutual Fund

100001;INF001A01011;-;Acme Flexi Cap Fund;Direct Plan;Growth Option;25.1234;11-Sep-2026
100002;INF001A01029;-;Other Fund;Regular Plan;Growth Option;22.5000;11-Sep-2026
"""


@pytest.fixture
def db2():
    con = connect(":memory:")
    apply_schema(con)
    apply_schema_v02(con)
    con.execute("INSERT INTO folios(folio_id, folio_number, amc) VALUES (1,'F1','Acme')")
    con.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name, isin)"
        " VALUES (1, 1, 'Acme Flexi Cap Fund', 'INF001A01011')"
    )
    con.commit()
    yield con
    con.close()


def test_refresh_universe_populates_scheme_master(db2):
    result = refresh_universe(db2, fetch=lambda: SAMPLE)
    assert result.schemes_written == 2
    assert db2.execute("SELECT COUNT(*) FROM md_schemes").fetchone()[0] == 2


def test_refresh_universe_caches_nav_for_held_isins_only(db2):
    result = refresh_universe(db2, fetch=lambda: SAMPLE)
    assert result.nav_ingested == 1
    assert result.nav_skipped == 1


def test_refresh_universe_logs_the_fetch(db2):
    refresh_universe(db2, fetch=lambda: SAMPLE)
    row = db2.execute(
        "SELECT endpoint, rows_ingested FROM md_fetch_log"
    ).fetchone()
    assert row["endpoint"] == "universe"
    assert row["rows_ingested"] == 1


def test_refresh_universe_is_idempotent(db2):
    refresh_universe(db2, fetch=lambda: SAMPLE)
    refresh_universe(db2, fetch=lambda: SAMPLE)
    assert db2.execute("SELECT COUNT(*) FROM md_schemes").fetchone()[0] == 2
    assert db2.execute("SELECT COUNT(*) FROM md_nav").fetchone()[0] == 1


def test_refresh_universe_calls_the_injected_fetch_exactly_once(db2):
    calls = []

    def fake_fetch():
        calls.append(1)
        return SAMPLE

    refresh_universe(db2, fetch=fake_fetch)
    assert calls == [1]


def test_refresh_makes_no_network_call_when_fetch_is_injected(db2):
    """An injected fetch must fully replace the HTTP client.

    If refresh ever called the real client as well, this would raise.
    """
    from trader_ai.marketdata import amfi_client

    original = amfi_client.urllib.request.urlopen

    def explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("refresh must not perform HTTP when fetch is injected")

    amfi_client.urllib.request.urlopen = explode
    try:
        refresh_universe(db2, fetch=lambda: SAMPLE)
    finally:
        amfi_client.urllib.request.urlopen = original


def test_refresh_reports_parse_skips(db2):
    text = SAMPLE + "100003;INF001A01045;-;Bad NAV Fund;Direct Plan;Growth Option;N.A.;11-Sep-2026\n"
    result = refresh_universe(db2, fetch=lambda: text)
    assert result.parse_skipped["non_numeric_nav"] == 1


def test_refresh_with_empty_ledger_caches_schemes_but_no_nav(db2):
    db2.execute("DELETE FROM schemes")
    db2.commit()
    result = refresh_universe(db2, fetch=lambda: SAMPLE)
    assert result.schemes_written == 2
    assert result.nav_ingested == 0
    assert db2.execute("SELECT COUNT(*) FROM md_nav").fetchone()[0] == 0
