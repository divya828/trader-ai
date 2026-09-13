from datetime import date
from decimal import Decimal

import pytest

from trader_ai.ingest.importer import import_parsed


def _cas_data():
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

    scheme = Scheme(
        scheme="Axis Bluechip Fund",
        advisor="DIRECT",
        rta_code="A1",
        rta="KFINTECH",
        type="EQUITY",
        isin="INF846K01131",
        amfi="120503",
        nominees=[],
        open=Decimal("0"),
        close=Decimal("100"),
        close_calculated=Decimal("100"),
        valuation=SchemeValuation(
            date=date(2024, 3, 31),
            nav=Decimal("50"),
            cost=Decimal("4000"),
            value=Decimal("5000"),
        ),
        transactions=[
            TransactionData(
                date=date(2023, 4, 10),
                description="Purchase",
                amount=Decimal("4000"),
                units=Decimal("100"),
                nav=Decimal("40"),
                balance=Decimal("100"),
                type=TransactionType.PURCHASE,
                dividend_rate=None,
            )
        ],
    )
    return CASData(
        statement_period=StatementPeriod(from_="2023-04-01", to="2024-03-31"),
        folios=[
            Folio(
                folio="999/1",
                amc="Axis Mutual Fund",
                name="Test",
                PAN="ABCPX1234Z",
                KYC="OK",
                PANKYC="OK",
                schemes=[scheme],
            )
        ],
        investor_info=InvestorInfo(
            name="Test", email="t@example.com", address="X", mobile="9"
        ),
        cas_type=CASFileType.DETAILED,
        file_type=FileType.KFINTECH,
        parse_warnings=[],
    )


def _nsdl_data():
    from casparser.enums import FileType
    from casparser.types import (
        DematAccount,
        DematOwner,
        Equity,
        InvestorInfo,
        NSDLCASData,
        StatementPeriod,
    )

    return NSDLCASData(
        accounts=[
            DematAccount(
                name="Demat",
                type="NSDL",
                dp_id="IN300000",
                client_id="10000001",
                folios=1,
                balance=Decimal("2950"),
                owners=[DematOwner(name="Test", PAN="ABCPX1234Z")],
                equities=[
                    Equity(
                        name="Reliance Industries Ltd",
                        isin="INE002A01018",
                        num_shares=Decimal("1"),
                        price=Decimal("2950"),
                        value=Decimal("2950"),
                        symbol="RELIANCE",
                        exchange="NSE",
                    )
                ],
                mutual_funds=[],
                bonds=[],
            )
        ],
        statement_period=StatementPeriod(from_="2023-04-01", to="2024-03-31"),
        investor_info=InvestorInfo(
            name="Test", email="t@example.com", address="X", mobile="9"
        ),
        file_type=FileType.NSDL,
        nps=None,
        parse_warnings=[],
    )


def test_import_parsed_dispatches_cas_data(db):
    import_parsed(db, _cas_data(), source_file="cams.pdf")
    assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM schemes").fetchone()[0] == 1


def test_import_parsed_dispatches_nsdl_data(db):
    import_parsed(db, _nsdl_data(), source_file="nsdl.pdf")
    assert db.execute("SELECT COUNT(*) FROM securities").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0


def test_import_parsed_rejects_unknown_type(db):
    with pytest.raises(TypeError, match="Unsupported"):
        import_parsed(db, object(), source_file="x.pdf")


def test_full_reimport_is_idempotent(db):
    cas = _cas_data()
    import_parsed(db, cas, source_file="cams.pdf")
    import_parsed(db, cas, source_file="cams.pdf")
    assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1
