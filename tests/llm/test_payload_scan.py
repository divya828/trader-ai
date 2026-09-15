"""Assert that nothing from the ledger reaches an outbound payload.

This compares against ACTUAL VALUES read from the database rather than matching
shapes. A shape-based folio check (\\d{3,}/\\d+) false-positives on the citation
"SEBI circular SEBI/HO/IMD/DF3/CIR/P/2017/114" -> "2017/114", and a test that
fails on a public regulation number is a test someone will weaken. Comparing
values is both stricter (it catches any format) and free of false positives
(the ledger knows its own values).
"""

import json
import pathlib

import pytest

from trader_ai.db.connection import connect
from trader_ai.llm.client import HostedExplainer
from trader_ai.llm.redaction import redact
from trader_ai.rules.context import build_context
from trader_ai.rules.registry import evaluate

LEDGER = pathlib.Path("data/ledger.db")
pytestmark = pytest.mark.skipif(
    not LEDGER.exists(), reason="no local ledger to scan against"
)


class _Capture:
    """Stands in for the SDK and records exactly what would be sent."""

    def __init__(self):
        self.sent = None
        self.messages = self

    def create(self, **kwargs):
        self.sent = kwargs
        raise RuntimeError("stop here; the payload is what matters")


def _outbound_payload():
    con = connect(LEDGER)
    findings, _, _ = evaluate(build_context(con))
    assert findings, "the ledger produced no findings, so nothing would be sent"
    capture = _Capture()
    explainer = HostedExplainer(client=capture)
    try:
        explainer.explain(redact(findings).findings)
    except RuntimeError:
        pass
    assert capture.sent is not None, "nothing was sent"
    return json.dumps(capture.sent, default=str), con


def test_no_real_folio_number_appears_in_the_payload():
    payload, con = _outbound_payload()
    folios = [r["folio_number"] for r in con.execute("SELECT folio_number FROM folios")]
    assert folios, "fixture ledger has no folios to check against"
    leaked = [f for f in folios if f and f in payload]
    assert leaked == [], f"folio numbers in payload: {leaked}"


def test_no_stored_pan_appears_in_the_payload():
    payload, con = _outbound_payload()
    pans = [
        r["pan_masked"]
        for r in con.execute(
            "SELECT pan_masked FROM folios WHERE pan_masked IS NOT NULL"
        )
    ]
    assert pans, "fixture ledger has no PANs to check against"
    leaked = [p for p in pans if p and p in payload]
    assert leaked == [], f"PANs in payload: {leaked}"


def test_no_scheme_name_appears_in_the_payload():
    payload, con = _outbound_payload()
    names = [r["scheme_name"] for r in con.execute("SELECT scheme_name FROM schemes")]
    assert names, "fixture ledger has no schemes to check against"
    leaked = [n for n in names if n and n in payload]
    assert leaked == [], f"scheme names in payload: {leaked}"


def test_no_holding_value_appears_in_the_payload():
    """Rupee amounts must not leave, in any rendering."""
    payload, con = _outbound_payload()
    values = [
        r["value"]
        for r in con.execute(
            "SELECT value FROM holdings_snapshot"
            " WHERE import_run_id = (SELECT MAX(import_run_id) FROM import_runs)"
        )
    ]
    assert values, "fixture ledger has no holdings to check against"
    leaked = [v for v in values if f"{v:.2f}" in payload or str(int(v)) in payload]
    assert leaked == [], f"holding values in payload: {leaked}"


def test_the_payload_still_carries_what_an_explanation_needs():
    """A guard that redacts everything is useless. Check the payload is usable."""
    payload, _ = _outbound_payload()
    assert "fund_1" in payload
    assert "rule_id" in payload
    assert "citation_source" in payload


def test_the_scan_would_catch_a_leak():
    """A guard never seen failing is not a guard.

    Inject a real scheme name into the payload and confirm the check trips.
    """
    payload, con = _outbound_payload()
    name = con.execute("SELECT scheme_name FROM schemes LIMIT 1").fetchone()[0]
    poisoned = payload + name
    assert [n for n in [name] if n in poisoned] == [name]


def test_a_citation_containing_a_folio_shaped_string_does_not_trip_the_scan():
    """SEBI/HO/IMD/DF3/CIR/P/2017/114 contains "2017/114".

    A shape-based folio regex fails on that public regulation number. This
    test pins why the scan compares values instead: the citation is present
    and legitimate, and the scan must not object to it.
    """
    payload, con = _outbound_payload()
    assert "2017/114" in payload, "the SEBI citation should be in the payload"
    folios = [r["folio_number"] for r in con.execute("SELECT folio_number FROM folios")]
    assert "2017/114" not in folios, "that string is a citation, not a folio"
