import pytest

from trader_ai.db.connection import apply_schema, connect


@pytest.fixture
def db():
    """In-memory database with the schema applied. Never touches data/ledger.db."""
    con = connect(":memory:")
    apply_schema(con)
    yield con
    con.close()
