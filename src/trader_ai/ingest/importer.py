"""Entry point tying casparser output to the ledger.

read_cas_pdf returns CASData for CAMS/KFin and NSDLCASData for NSDL/CDSL;
these have different shapes, so dispatch on type rather than duck-typing.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from casparser.types import CASData, NSDLCASData

from trader_ai.ingest.loader import load_cas, load_nsdl
from trader_ai.ingest.normalize import normalize_cas_data, normalize_nsdl_data


def import_parsed(con: sqlite3.Connection, parsed: Any, source_file: str) -> int:
    """Normalize and persist an already-parsed casparser result."""
    if isinstance(parsed, CASData):
        return load_cas(con, normalize_cas_data(parsed), source_file)
    if isinstance(parsed, NSDLCASData):
        return load_nsdl(con, normalize_nsdl_data(parsed), source_file)
    raise TypeError(f"Unsupported parse result type: {type(parsed).__name__}")


def import_pdf(
    con: sqlite3.Connection, pdf_path: str | Path, password: str
) -> int:
    """Parse a local eCAS PDF and load it. Never leaves this machine."""
    from casparser import read_cas_pdf

    parsed = read_cas_pdf(str(pdf_path), password)
    return import_parsed(con, parsed, source_file=Path(pdf_path).name)
