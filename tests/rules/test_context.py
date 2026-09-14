import pytest

from trader_ai.db.connection import (
    apply_schema,
    apply_schema_v02,
    apply_schema_v02c,
    connect,
)
from trader_ai.rules.context import build_context


@pytest.fixture
def db3():
    con = connect(":memory:")
    apply_schema(con)
    apply_schema_v02(con)
    apply_schema_v02c(con)
    con.execute("INSERT INTO folios(folio_id, folio_number, amc) VALUES (1,'F1','A')")
    con.execute("INSERT INTO import_runs(import_run_id, source_file) VALUES (1,'a.pdf')")
    con.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name, isin, asset_class)"
        " VALUES (1, 1, 'Equity Fund', 'INF001A01011', 'EQUITY')"
    )
    con.execute(
        "INSERT INTO md_schemes(amfi_code, isin_growth, scheme_name, sebi_category,"
        " plan, option, asset_class, last_seen) VALUES ('100001','INF001A01011',"
        " 'Equity Fund','Equity Scheme - Flexi Cap Fund','DIRECT','Growth Option',"
        " 'EQUITY','2026-01-01')"
    )
    con.execute(
        "INSERT INTO holdings_snapshot(import_run_id, scheme_id, as_of_date, units,"
        " price, value) VALUES (1, 1, '2026-01-07', 100, 25, 2500)"
    )
    con.commit()
    yield con
    con.close()


def test_context_exposes_holdings_with_weights_not_amounts(db3):
    ctx = build_context(db3)
    assert len(ctx.holdings) == 1
    holding = ctx.holdings[0]
    assert holding.weight == pytest.approx(1.0)
    assert holding.scheme_name == "Equity Fund"


def test_context_never_exposes_folio_or_pan(db3):
    """A rule must be unable to reach identifying data even by accident."""
    ctx = build_context(db3)
    holding = ctx.holdings[0]
    assert not hasattr(holding, "folio_number")
    assert not hasattr(holding, "pan_masked")
    assert not hasattr(ctx, "folios")


def test_context_reports_disposal_count(db3):
    # Rules that need evidence of selling behaviour check this.
    ctx = build_context(db3)
    assert ctx.disposal_count == 0


def test_context_counts_disposals_when_present(db3):
    db3.execute(
        "INSERT INTO transactions(scheme_id, txn_date, txn_type, units, price,"
        " amount, source_row_hash) VALUES (1,'2026-02-01','REDEMPTION',-10,30,300,'h1')"
    )
    db3.commit()
    ctx = build_context(db3)
    assert ctx.disposal_count == 1


def test_context_reports_whether_a_target_allocation_exists(db3):
    ctx = build_context(db3)
    assert ctx.has_target is False
    db3.execute(
        "INSERT INTO target_allocation(asset_class, target_weight)"
        " VALUES ('EQUITY', 0.6)"
    )
    db3.commit()
    assert build_context(db3).has_target is True


def test_context_carries_asset_class_weights(db3):
    ctx = build_context(db3)
    assert ctx.asset_class_weights["EQUITY"] == pytest.approx(1.0)


def test_context_on_an_empty_ledger(db3):
    db3.execute("DELETE FROM holdings_snapshot")
    db3.commit()
    ctx = build_context(db3)
    assert ctx.holdings == []
    assert ctx.asset_class_weights == {}


def test_context_weights_sum_to_one_across_several_holdings(db3):
    db3.execute(
        "INSERT INTO schemes(scheme_id, folio_id, scheme_name, isin, asset_class)"
        " VALUES (2, 1, 'Debt Fund', 'INF001A01029', 'DEBT')"
    )
    db3.execute(
        "INSERT INTO holdings_snapshot(import_run_id, scheme_id, as_of_date, units,"
        " price, value) VALUES (1, 2, '2026-01-07', 100, 25, 2500)"
    )
    db3.commit()
    ctx = build_context(db3)
    assert sum(h.weight for h in ctx.holdings) == pytest.approx(1.0)
    assert ctx.asset_class_weights["EQUITY"] == pytest.approx(0.5)


def test_context_accepts_precomputed_metrics(db3):
    # Rules read metrics from here; they never recompute one.
    ctx = build_context(db3, metrics={"cost_drag": "sentinel"})
    assert ctx.metrics["cost_drag"] == "sentinel"
