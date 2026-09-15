"""The ingest/analytics boundary is load-bearing: it is what makes a future
redaction gate insertable in exactly one place. Assert it mechanically."""

import ast
import pathlib

ANALYTICS = pathlib.Path("src/trader_ai/analytics")
INGEST = pathlib.Path("src/trader_ai/ingest")
MARKETDATA = pathlib.Path("src/trader_ai/marketdata")


def _imported_modules(path: pathlib.Path) -> set[str]:
    names: set[str] = set()
    for py_file in path.rglob("*.py"):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
    return names


def test_analytics_never_imports_ingest():
    offenders = {m for m in _imported_modules(ANALYTICS) if "ingest" in m}
    assert not offenders, f"analytics must not import ingest: {offenders}"


def test_analytics_never_imports_casparser():
    offenders = {m for m in _imported_modules(ANALYTICS) if m.startswith("casparser")}
    assert not offenders, f"analytics must not import casparser: {offenders}"


def test_no_network_libraries_anywhere():
    # v0.1 is fully local: nothing may reach the network.
    banned = {"requests", "httpx", "urllib.request", "aiohttp", "openai", "anthropic"}
    found = (_imported_modules(ANALYTICS) | _imported_modules(INGEST)) & banned
    assert not found, f"v0.1 must make no network calls: {found}"


def test_the_isolation_check_actually_detects_violations():
    # A guard that always passes is worthless. Prove the detector works by
    # running it against a file that genuinely does import ingest.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        decoy = pathlib.Path(tmp)
        (decoy / "bad.py").write_text(
            "from trader_ai.ingest.loader import load_cas\nimport casparser\n"
        )
        found = _imported_modules(decoy)
        assert any("ingest" in m for m in found)
        assert any(m.startswith("casparser") for m in found)


# --- v0.2: the marketdata package ---
#
# v0.2 amends "fully local" to permit outbound fetches of PUBLIC market
# reference data only. These guards are what keep that amendment narrow:
# exactly one module may reach the network, and portfolio data may never
# reach a URL.


def test_analytics_never_imports_the_http_client():
    # Analytics reads marketdata's CACHE TABLES, never its HTTP client. This
    # keeps analytics unit-testable with synthetic data and I/O-free.
    offenders = {m for m in _imported_modules(ANALYTICS) if "amfi_client" in m}
    assert not offenders, f"analytics must not import the HTTP client: {offenders}"


def test_analytics_never_imports_marketdata_at_all():
    offenders = {m for m in _imported_modules(ANALYTICS) if "marketdata" in m}
    assert not offenders, f"analytics must not import marketdata: {offenders}"


def test_marketdata_never_imports_ingest():
    offenders = {m for m in _imported_modules(MARKETDATA) if "ingest" in m}
    assert not offenders, f"marketdata must not import ingest: {offenders}"


def test_marketdata_never_imports_casparser():
    # Market data is public reference data; it must never touch the PII-bearing
    # statement parser.
    offenders = {m for m in _imported_modules(MARKETDATA) if m.startswith("casparser")}
    assert not offenders, f"marketdata must not import casparser: {offenders}"


def test_only_the_client_module_performs_http():
    # Exactly one module may reach the network, so the privacy invariant has
    # exactly one place to be enforced.
    http_markers = {"urllib.request", "urllib", "http.client", "requests", "httpx", "aiohttp"}
    for py_file in sorted(MARKETDATA.rglob("*.py")):
        if py_file.name == "amfi_client.py":
            continue
        tree = ast.parse(py_file.read_text())
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module)
        offenders = found & http_markers
        assert not offenders, f"{py_file} performs HTTP ({offenders}); only amfi_client may"


def test_no_model_client_anywhere():
    # v0.2 still contains no LLM call of any kind. Non-negotiable #3.
    banned = {"openai", "anthropic", "ollama", "langchain", "langgraph", "transformers"}
    found = (
        _imported_modules(ANALYTICS)
        | _imported_modules(INGEST)
        | _imported_modules(MARKETDATA)
    ) & banned
    assert not found, f"v0.2 must contain no LLM client: {found}"


def test_no_portfolio_identifier_near_url_construction():
    # Belt and braces alongside the signature check in test_client_privacy:
    # no URL-building line in the client may reference a portfolio concept.
    banned = ("isin", "folio", "pan", "scheme_name", "amount", "units")
    client = (MARKETDATA / "amfi_client.py").read_text()
    for line in client.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or '"""' in stripped:
            continue
        if "http" not in stripped.lower() and "url" not in stripped.lower():
            continue
        for term in banned:
            assert term not in stripped.lower(), (
                f"portfolio term {term!r} near URL construction: {stripped}"
            )


# --- v0.2b: the literature metrics ---


def test_metrics_never_import_the_http_client():
    # The v0.2b metric modules read cache tables, never the network.
    offenders = {
        m for m in _imported_modules(ANALYTICS)
        if "amfi_client" in m or m.startswith("urllib")
    }
    assert not offenders, f"analytics must not reach the network: {offenders}"


def test_metrics_reuse_v01_math_rather_than_reimplementing_it():
    """behaviour_gap must use v0.1's xirr; rebalancing must use its FIFO matcher.

    A second implementation of either would drift from the tested one.
    """
    behaviour = pathlib.Path("src/trader_ai/analytics/behavior_gap.py").read_text()
    assert "from trader_ai.analytics.xirr import" in behaviour

    rebalancing = pathlib.Path("src/trader_ai/analytics/rebalancing.py").read_text()
    assert "from trader_ai.analytics.tax_lots import" in rebalancing

    consistency = pathlib.Path("src/trader_ai/analytics/consistency.py").read_text()
    assert "from trader_ai.analytics.nav_series import" in consistency


def test_metrics_signal_missing_data_with_measurement_not_none():
    """Metrics signal unavailability with Measurement, not None.

    A None return invites callers to coerce it to zero, which is how an
    unmeasured dimension silently becomes a clean one.
    """
    for name in ("behavior_gap", "cost_drag"):
        source = pathlib.Path(f"src/trader_ai/analytics/{name}.py").read_text()
        assert "Measurement" in source, f"{name} must use Measurement"


def test_no_order_placement_code_anywhere():
    """Non-negotiable #2: nothing in this project places a trade.

    rebalancing.py proposes disposals, so this is the module most likely to
    drift toward execution. Assert it mechanically.
    """
    banned = ("place_order", "submit_order", "execute_trade", "broker_api", "kiteconnect")
    for package in (ANALYTICS, INGEST, MARKETDATA):
        for py_file in package.rglob("*.py"):
            source = py_file.read_text().lower()
            for term in banned:
                assert term not in source, f"{py_file} contains {term!r}"


# --- v0.2c: the rule engine ---

RULES = pathlib.Path("src/trader_ai/rules")


def test_rules_never_import_ingest_or_the_http_client():
    offenders = {
        m for m in _imported_modules(RULES)
        if "ingest" in m or "amfi_client" in m or m.startswith("urllib")
    }
    assert not offenders, f"rules must not reach ingest or the network: {offenders}"


def test_rules_contain_no_llm_client():
    banned = {"openai", "anthropic", "ollama", "langchain", "langgraph", "transformers"}
    assert not (_imported_modules(RULES) & banned), "v0.2c must contain no LLM call"


def test_rules_do_not_recompute_metrics():
    """Rules consume metrics from the context; they never recalculate one.

    This is what keeps a future LLM tier explaining rather than calculating.
    """
    for py_file in (RULES / "families").rglob("*.py"):
        source = py_file.read_text()
        assert "xirr(" not in source, f"{py_file} recomputes XIRR"
        assert "match_fifo(" not in source, f"{py_file} recomputes FIFO lots"


def test_no_rule_can_reach_a_folio_or_pan():
    """Context exposes no identifying field, so a rule cannot leak one."""
    context_source = (RULES / "context.py").read_text()
    for term in ("folio_number", "pan_masked"):
        assert term not in context_source, f"context exposes {term}"


def test_subject_rejects_both_raw_and_masked_pan_shapes():
    """The guard must cover the masked form this project actually stores.

    A raw PAN is ABCPX1234Z; the stored form is first3+XXX+last4. Only
    checking the raw shape would let a masked PAN into a finding.
    """
    import pytest as _pytest

    from trader_ai.rules.finding import Subject

    for bad in ("ABCPX1234Z", "LFGXXX630Q"):
        with _pytest.raises(ValueError, match="PAN"):
            Subject(kind="SCHEME", ref=bad)


# --- v0.3: the explanation layer ---

LLM = pathlib.Path("src/trader_ai/llm")


def _direct_imports(py_file: pathlib.Path) -> set[str]:
    tree = ast.parse(py_file.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_only_the_llm_client_imports_the_anthropic_sdk():
    """One module decides what leaves the machine. Keep it that way."""
    for py_file in sorted(LLM.rglob("*.py")):
        if py_file.name == "client.py":
            continue
        assert "anthropic" not in _direct_imports(py_file), f"{py_file} imports anthropic"


def test_no_llm_module_imports_ingest_or_opens_the_ledger():
    offenders = {m for m in _imported_modules(LLM) if "ingest" in m}
    assert not offenders, f"llm must not import ingest: {offenders}"
    for py_file in sorted(LLM.rglob("*.py")):
        assert "ledger.db" not in py_file.read_text(), f"{py_file} references the ledger"


def test_redaction_never_imports_the_client():
    """The gate must not depend on the thing it guards."""
    found = _direct_imports(LLM / "redaction.py")
    assert not any("client" in m for m in found)


def test_the_client_signature_accepts_only_redacted_findings():
    import inspect

    from trader_ai.llm.client import HostedExplainer

    annotation = str(
        inspect.signature(HostedExplainer.explain).parameters["findings"].annotation
    )
    assert "RedactedFinding" in annotation


def test_no_llm_module_computes_a_portfolio_figure():
    """The model is given numbers; nothing here derives one."""
    for py_file in sorted(LLM.rglob("*.py")):
        source = py_file.read_text()
        for banned in ("xirr(", "match_fifo(", "cagr(", "herfindahl("):
            assert banned not in source, f"{py_file} computes {banned}"


def test_the_redacted_type_cannot_carry_an_identifier():
    """Enforcement by type: the outbound shape has no field for a name or id."""
    import dataclasses

    from trader_ai.llm.redaction import RedactedFinding, RedactedSubject

    subject_fields = {f.name for f in dataclasses.fields(RedactedSubject)}
    assert not subject_fields & {"ref", "local_id", "scheme_name", "folio"}

    finding_fields = {f.name for f in dataclasses.fields(RedactedFinding)}
    assert "title" not in finding_fields  # titles embed scheme names verbatim
