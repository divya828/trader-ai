from datetime import date
from decimal import Decimal

import pytest

from trader_ai.ingest.normalize import (
    mask_pan,
    normalize_date,
    row_hash,
    normalize_cas_data,
    normalize_nsdl_data,
)


def test_mask_pan_keeps_first_three_and_last_four():
    assert mask_pan("ABCPX1234Z") == "ABCXXX234Z"


def test_mask_pan_handles_none():
    assert mask_pan(None) is None


def test_mask_pan_leaves_unexpected_length_fully_masked():
    assert mask_pan("SHORT") == "XXXXX"


def test_normalize_date_accepts_date_object():
    assert normalize_date(date(2024, 3, 15)) == "2024-03-15"


def test_normalize_date_accepts_iso_string():
    assert normalize_date("2024-03-15") == "2024-03-15"


def test_row_hash_is_stable_across_calls():
    a = row_hash("F1", "INE001", "2024-01-01", "PURCHASE", Decimal("100.50"), Decimal("10"))
    b = row_hash("F1", "INE001", "2024-01-01", "PURCHASE", Decimal("100.50"), Decimal("10"))
    assert a == b


def test_row_hash_differs_on_any_field_change():
    base = row_hash("F1", "INE001", "2024-01-01", "PURCHASE", Decimal("100"), Decimal("10"))
    assert base != row_hash("F2", "INE001", "2024-01-01", "PURCHASE", Decimal("100"), Decimal("10"))
    assert base != row_hash("F1", "INE002", "2024-01-01", "PURCHASE", Decimal("100"), Decimal("10"))
    assert base != row_hash("F1", "INE001", "2024-01-02", "PURCHASE", Decimal("100"), Decimal("10"))
    assert base != row_hash("F1", "INE001", "2024-01-01", "REDEMPTION", Decimal("100"), Decimal("10"))
    assert base != row_hash("F1", "INE001", "2024-01-01", "PURCHASE", Decimal("101"), Decimal("10"))


def test_normalize_cas_data_extracts_folios_schemes_transactions():
    cas = _build_cas_data()
    result = normalize_cas_data(cas)

    assert result["statement_period"] == ("2023-04-01", "2024-03-31")

    assert len(result["folios"]) == 1
    folio = result["folios"][0]
    assert folio["folio_number"] == "12345/67"
    assert folio["amc"] == "HDFC Mutual Fund"
    assert folio["pan_masked"] == "ABCXXX234Z"
    assert "PAN" not in folio  # raw PAN must never survive normalization

    assert len(result["schemes"]) == 1
    scheme = result["schemes"][0]
    assert scheme["scheme_name"] == "HDFC Flexi Cap Fund - Growth"
    assert scheme["isin"] == "INF179K01158"
    assert scheme["amfi_code"] == "118989"
    assert scheme["folio_number"] == "12345/67"

    assert len(result["transactions"]) == 2
    txn = result["transactions"][0]
    assert txn["txn_date"] == "2023-05-10"
    assert txn["txn_type"] == "PURCHASE"
    assert txn["amount"] == pytest.approx(10000.0)
    assert txn["units"] == pytest.approx(100.0)
    assert txn["price"] == pytest.approx(100.0)
    assert txn["source_row_hash"]

    assert len(result["holdings"]) == 1
    holding = result["holdings"][0]
    assert holding["units"] == pytest.approx(150.0)
    assert holding["price"] == pytest.approx(120.0)
    assert holding["value"] == pytest.approx(18000.0)


def test_normalize_nsdl_data_extracts_accounts_and_equities():
    nsdl = _build_nsdl_data()
    result = normalize_nsdl_data(nsdl)

    assert len(result["demat_accounts"]) == 1
    account = result["demat_accounts"][0]
    assert account["dp_id"] == "IN300000"
    assert account["client_id"] == "10000001"
    assert account["depository"] == "NSDL"

    assert len(result["securities"]) == 1
    security = result["securities"][0]
    assert security["isin"] == "INE002A01018"
    assert security["symbol"] == "RELIANCE"

    assert len(result["holdings"]) == 1
    holding = result["holdings"][0]
    assert holding["isin"] == "INE002A01018"
    assert holding["units"] == pytest.approx(50.0)
    assert holding["value"] == pytest.approx(147500.0)


# --- fixtures built from real casparser types ---


def _build_cas_data():
    from casparser.enums import CASFileType, FileType, TransactionType
    from casparser.types import (
        CASData,
        Folio,
        InvestorInfo,
        Scheme,
        SchemeValuation,
        StatementPeriod,
        TransactionData,
    )

    transactions = [
        TransactionData(
            date=date(2023, 5, 10),
            description="Purchase",
            amount=Decimal("10000"),
            units=Decimal("100"),
            nav=Decimal("100"),
            balance=Decimal("100"),
            type=TransactionType.PURCHASE,
            dividend_rate=None,
        ),
        TransactionData(
            date=date(2023, 8, 10),
            description="SIP Purchase",
            amount=Decimal("5500"),
            units=Decimal("50"),
            nav=Decimal("110"),
            balance=Decimal("150"),
            type=TransactionType.PURCHASE_SIP,
            dividend_rate=None,
        ),
    ]
    scheme = Scheme(
        scheme="HDFC Flexi Cap Fund - Growth",
        advisor="DIRECT",
        rta_code="H1234",
        rta="CAMS",
        type="EQUITY",
        isin="INF179K01158",
        amfi="118989",
        nominees=[],
        open=Decimal("0"),
        close=Decimal("150"),
        close_calculated=Decimal("150"),
        valuation=SchemeValuation(
            date=date(2024, 3, 31),
            nav=Decimal("120"),
            cost=Decimal("15500"),
            value=Decimal("18000"),
        ),
        transactions=transactions,
    )
    folio = Folio(
        folio="12345/67",
        amc="HDFC Mutual Fund",
        name="Test Investor",
        PAN="ABCPX1234Z",
        KYC="OK",
        PANKYC="OK",
        schemes=[scheme],
    )
    return CASData(
        statement_period=StatementPeriod(from_="2023-04-01", to="2024-03-31"),
        folios=[folio],
        investor_info=InvestorInfo(
            name="Test Investor",
            email="test@example.com",
            address="Somewhere",
            mobile="9999999999",
        ),
        cas_type=CASFileType.DETAILED,
        file_type=FileType.CAMS,
        parse_warnings=[],
    )


def _build_nsdl_data():
    from casparser.enums import FileType
    from casparser.types import (
        DematAccount,
        DematOwner,
        Equity,
        InvestorInfo,
        NSDLCASData,
        StatementPeriod,
    )

    account = DematAccount(
        name="NSDL Demat Account",
        type="NSDL",
        dp_id="IN300000",
        client_id="10000001",
        folios=1,
        balance=Decimal("147500"),
        owners=[DematOwner(name="Test Investor", PAN="ABCPX1234Z")],
        equities=[
            Equity(
                name="Reliance Industries Ltd",
                isin="INE002A01018",
                num_shares=Decimal("50"),
                price=Decimal("2950"),
                value=Decimal("147500"),
                symbol="RELIANCE",
                exchange="NSE",
            )
        ],
        mutual_funds=[],
        bonds=[],
    )
    return NSDLCASData(
        accounts=[account],
        statement_period=StatementPeriod(from_="2023-04-01", to="2024-03-31"),
        investor_info=InvestorInfo(
            name="Test Investor",
            email="test@example.com",
            address="Somewhere",
            mobile="9999999999",
        ),
        file_type=FileType.NSDL,
        nps=None,
        parse_warnings=[],
    )
