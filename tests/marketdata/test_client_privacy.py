"""Enforcement of the v0.2 outbound-data rule.

v0.1 was fully local. v0.2 amends that to permit outbound fetches of *public
market reference data*, subject to one invariant:

    No request may carry a portfolio-derived parameter.

AMFI publishes whole-universe files, so the natural access pattern is already
"download everything, filter locally". Downloading the same public file every
Indian investor downloads reveals nothing about this portfolio; querying it by
your ISINs would. These tests are what make that a guarantee rather than a
promise -- they assert it by function signature, not by reading prose.
"""

import inspect
from datetime import date

import pytest

from trader_ai.marketdata import amfi_client
from trader_ai.marketdata.amfi_client import history_url, universe_url

# Values that must never appear in an outbound URL.
LEDGER_VALUES = [
    "INF179K01158",      # an ISIN
    "12345/67",          # a folio number
    "ABCPX1234Z",        # a PAN
    "HDFC Flexi Cap",    # a scheme name
    "18000",             # an amount
]


def test_universe_url_is_constant_and_carries_no_parameters():
    url = universe_url()
    assert url == "https://portal.amfiindia.com/spages/NAVAll.txt"
    assert "?" not in url


def test_universe_url_uses_portal_host_not_www():
    # www.amfiindia.com 301-redirects; using it wastes a round trip.
    assert "portal.amfiindia.com" in universe_url()
    assert "www.amfiindia.com" not in universe_url()


def test_history_url_contains_only_dates():
    url = history_url(date(2026, 9, 1), date(2026, 9, 3))
    assert "frmdt=01-Sep-2026" in url
    assert "todt=03-Sep-2026" in url
    for value in LEDGER_VALUES:
        assert value not in url


def test_history_url_rejects_reversed_range():
    with pytest.raises(ValueError, match="range"):
        history_url(date(2026, 9, 3), date(2026, 9, 1))


@pytest.mark.parametrize(
    "func_name",
    ["universe_url", "history_url", "fetch_universe", "fetch_history"],
)
def test_no_public_function_accepts_a_portfolio_parameter(func_name):
    """The invariant is enforced by signature, not by convention.

    Any parameter named for a portfolio concept would let a caller put ledger
    data into a URL. Only date and transport parameters are permitted.
    """
    allowed = {"start", "end", "timeout", "url", "opener"}
    func = getattr(amfi_client, func_name)
    params = set(inspect.signature(func).parameters)
    assert params <= allowed, (
        f"{func_name} exposes non-date parameters: {params - allowed}"
    )


def test_module_defines_no_other_public_callables():
    # A helper that took an ISIN would bypass the signature check above.
    public = {
        name
        for name, value in vars(amfi_client).items()
        if callable(value)
        and not name.startswith("_")
        and getattr(value, "__module__", "") == amfi_client.__name__
    }
    assert public == {
        "universe_url",
        "history_url",
        "fetch_universe",
        "fetch_history",
    }


def test_no_public_function_accepts_arbitrary_kwargs():
    # **kwargs would let a caller smuggle a portfolio value past the
    # signature check above.
    for func_name in ("universe_url", "history_url", "fetch_universe", "fetch_history"):
        signature = inspect.signature(getattr(amfi_client, func_name))
        kinds = {p.kind for p in signature.parameters.values()}
        assert inspect.Parameter.VAR_KEYWORD not in kinds, f"{func_name} accepts **kwargs"
        assert inspect.Parameter.VAR_POSITIONAL not in kinds, f"{func_name} accepts *args"


def test_url_builders_are_pure_and_make_no_request():
    """Building a URL must not touch the network.

    If URL construction performed I/O, a test that merely inspects a URL would
    silently make a request. Replace the module's transport with one that
    raises, then build every URL.
    """
    original = amfi_client.urllib.request.urlopen

    def explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("URL construction must not perform a request")

    amfi_client.urllib.request.urlopen = explode
    try:
        universe_url()
        history_url(date(2026, 9, 1), date(2026, 9, 3))
    finally:
        amfi_client.urllib.request.urlopen = original
