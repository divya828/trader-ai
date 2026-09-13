"""Outbound HTTP for public AMFI reference data.

THE INVARIANT: no request may carry a portfolio-derived parameter.

Every function here accepts dates only -- never an ISIN, scheme name, folio, or
amount. AMFI publishes whole-universe files, so the natural access pattern is
already "download everything, filter locally"; scoping to holdings happens
after download, on-machine. Downloading the same public file every Indian
investor downloads reveals nothing about this portfolio; querying it by ISIN
would. tests/marketdata/test_client_privacy.py enforces this by signature.

stdlib urllib only -- no new runtime dependency.
"""

from __future__ import annotations

import ssl
import urllib.request
from datetime import date

import certifi

UNIVERSE_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
HISTORY_BASE = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx"
DEFAULT_TIMEOUT = 120
_AMFI_DATE = "%d-%b-%Y"

# Certificate verification stays ON. Python.org's macOS build does not use the
# system trust store and ships no CA bundle of its own, so urllib fails with
# CERTIFICATE_VERIFY_FAILED out of the box. Point OpenSSL at certifi's bundle
# rather than weakening verification -- this is a financial tool, and an
# unverified TLS connection would let a network attacker feed it fabricated
# NAV data.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def universe_url() -> str:
    """URL of the whole-universe NAV file. Constant; carries no parameters."""
    return UNIVERSE_URL


def history_url(start: date, end: date) -> str:
    """URL for a NAV history range. Date parameters only, by construction."""
    if end < start:
        raise ValueError(f"invalid range: end {end} precedes start {start}")
    return (
        f"{HISTORY_BASE}"
        f"?frmdt={start.strftime(_AMFI_DATE)}"
        f"&todt={end.strftime(_AMFI_DATE)}"
    )


def _get(url: str, timeout: int) -> str:
    with urllib.request.urlopen(url, timeout=timeout, context=_SSL_CONTEXT) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_universe(timeout: int = DEFAULT_TIMEOUT) -> str:
    """Download the whole-universe NAV file (~1.5MB)."""
    return _get(universe_url(), timeout)


def fetch_history(start: date, end: date, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Download NAV history for a date range (~1.16MB per day)."""
    return _get(history_url(start, end), timeout)
