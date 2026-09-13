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
