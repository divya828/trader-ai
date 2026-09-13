"""The ingest/analytics boundary is load-bearing: it is what makes a future
redaction gate insertable in exactly one place. Assert it mechanically."""

import ast
import pathlib

ANALYTICS = pathlib.Path("src/trader_ai/analytics")
INGEST = pathlib.Path("src/trader_ai/ingest")


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
