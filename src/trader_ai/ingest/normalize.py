"""Map casparser models to plain dicts ready for insertion.

Pure functions only: no database, no filesystem, no network. This is the one
place raw PAN is seen, and it never leaves this module unmasked.
"""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from typing import Any

PAN_LENGTH = 10


def mask_pan(pan: str | None) -> str | None:
    """Mask a PAN for storage. Full PAN is never persisted."""
    if pan is None:
        return None
    pan = pan.strip()
    if len(pan) != PAN_LENGTH:
        return "X" * len(pan)
    return f"{pan[:3]}XXX{pan[6:]}"


def normalize_date(value: date | str) -> str:
    """casparser dates are typed Union[date, str]; always store ISO 8601."""
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _to_float(value: Decimal | float | None) -> float | None:
    return None if value is None else float(value)


def row_hash(
    account_key: str,
    instrument_key: str,
    txn_date: str,
    txn_type: str,
    amount: Decimal | float | None,
    units: Decimal | float | None,
) -> str:
    """Stable natural key for a transaction row, for idempotent re-import."""
    parts = [
        account_key,
        instrument_key,
        txn_date,
        txn_type,
        "" if amount is None else f"{Decimal(str(amount)):.4f}",
        "" if units is None else f"{Decimal(str(units)):.4f}",
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def normalize_cas_data(cas: Any) -> dict[str, list | tuple]:
    """Normalize a CAMS/KFintech CASData object (mutual funds with history)."""
    folios: list[dict] = []
    schemes: list[dict] = []
    transactions: list[dict] = []
    holdings: list[dict] = []

    for folio in cas.folios:
        folios.append(
            {
                "folio_number": folio.folio,
                "amc": folio.amc,
                "pan_masked": mask_pan(folio.PAN),
            }
        )
        for scheme in folio.schemes:
            schemes.append(
                {
                    "folio_number": folio.folio,
                    "amfi_code": scheme.amfi,
                    "isin": scheme.isin,
                    "scheme_name": scheme.scheme,
                    "scheme_type": scheme.type,
                }
            )
            instrument_key = scheme.isin or scheme.scheme
            for txn in scheme.transactions:
                txn_date = normalize_date(txn.date)
                txn_type = txn.type.name
                transactions.append(
                    {
                        "folio_number": folio.folio,
                        "isin": scheme.isin,
                        "scheme_name": scheme.scheme,
                        "txn_date": txn_date,
                        "txn_type": txn_type,
                        "amount": _to_float(txn.amount) or 0.0,
                        "units": _to_float(txn.units),
                        "price": _to_float(txn.nav),
                        "source_row_hash": row_hash(
                            folio.folio,
                            instrument_key,
                            txn_date,
                            txn_type,
                            txn.amount,
                            txn.units,
                        ),
                    }
                )
            valuation = scheme.valuation
            holdings.append(
                {
                    "folio_number": folio.folio,
                    "isin": scheme.isin,
                    "scheme_name": scheme.scheme,
                    "as_of_date": normalize_date(valuation.date),
                    "units": float(scheme.close),
                    "price": float(valuation.nav),
                    "value": float(valuation.value),
                    "cost": _to_float(valuation.cost),
                }
            )

    return {
        "statement_period": (cas.statement_period.from_, cas.statement_period.to),
        "folios": folios,
        "schemes": schemes,
        "transactions": transactions,
        "holdings": holdings,
    }


def normalize_nsdl_data(nsdl: Any) -> dict[str, list | tuple]:
    """Normalize an NSDL/CDSL NSDLCASData object (demat holdings snapshot).

    Equities carry no transaction history, so this yields securities and
    holdings only — never transactions.
    """
    accounts: list[dict] = []
    securities: list[dict] = []
    holdings: list[dict] = []
    as_of = nsdl.statement_period.to

    for account in nsdl.accounts:
        depository = "NSDL" if "NSDL" in (account.type or "").upper() else "CDSL"
        accounts.append(
            {
                "dp_id": account.dp_id or "",
                "client_id": account.client_id or "",
                "depository": depository,
            }
        )
        for equity in account.equities:
            securities.append(
                {
                    "isin": equity.isin,
                    "symbol": equity.symbol,
                    "name": equity.name or equity.isin,
                    "exchange": equity.exchange,
                }
            )
            holdings.append(
                {
                    "isin": equity.isin,
                    "as_of_date": normalize_date(as_of),
                    "units": float(equity.num_shares),
                    "price": float(equity.price),
                    "value": float(equity.value),
                    "cost": None,
                }
            )

    return {
        "statement_period": (nsdl.statement_period.from_, nsdl.statement_period.to),
        "demat_accounts": accounts,
        "securities": securities,
        "holdings": holdings,
    }
