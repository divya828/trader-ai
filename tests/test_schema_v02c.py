import sqlite3

import pytest

from trader_ai.db.connection import (
    apply_schema,
    apply_schema_v02,
    apply_schema_v02c,
    connect,
)


@pytest.fixture
def db3():
    con = connect(":memory:")
    apply_schema(con)
    apply_schema_v02(con)
    apply_schema_v02c(con)
    yield con
    con.close()


def test_v02c_adds_findings_tables(db3):
    names = {
        r[0] for r in db3.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"findings", "finding_subjects", "finding_metrics"} <= names


def test_earlier_tables_survive(db3):
    names = {
        r[0] for r in db3.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"folios", "schemes", "md_schemes", "md_nav", "health_scores"} <= names


def test_health_score_can_be_null_with_a_reason(db3):
    """The concrete case: TAX_EFFICIENCY on a ledger with no disposals.

    A NULL score alone would not say why it is missing.
    """
    db3.execute(
        "INSERT INTO health_scores(dimension, score, unscored_reason)"
        " VALUES ('TAX_EFFICIENCY', NULL, 'no disposals in ledger')"
    )
    row = db3.execute(
        "SELECT score, unscored_reason FROM health_scores"
    ).fetchone()
    assert row["score"] is None
    assert row["unscored_reason"] == "no disposals in ledger"


def test_severity_is_constrained(db3):
    with pytest.raises(sqlite3.IntegrityError):
        db3.execute(
            "INSERT INTO findings(run_id, rule_id, severity, title, citation_key,"
            " computed_at) VALUES ('r','x','BOGUS','t','c','2026-01-01')"
        )


def test_subject_kind_is_constrained(db3):
    db3.execute(
        "INSERT INTO findings(finding_id, run_id, rule_id, severity, title,"
        " citation_key, computed_at)"
        " VALUES (1,'r','x','LOW','t','c','2026-01-01')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db3.execute(
            "INSERT INTO finding_subjects(finding_id, kind, ref)"
            " VALUES (1, 'FOLIO', 'anything')"
        )


def test_subject_weight_must_be_a_ratio(db3):
    """weight is a portfolio share, never an amount. 250000 is not a ratio."""
    db3.execute(
        "INSERT INTO findings(finding_id, run_id, rule_id, severity, title,"
        " citation_key, computed_at)"
        " VALUES (1,'r','x','LOW','t','c','2026-01-01')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db3.execute(
            "INSERT INTO finding_subjects(finding_id, kind, ref, weight)"
            " VALUES (1, 'SCHEME', 'Some Fund', 250000.0)"
        )


def test_finding_metrics_reject_duplicate_names(db3):
    db3.execute(
        "INSERT INTO findings(finding_id, run_id, rule_id, severity, title,"
        " citation_key, computed_at)"
        " VALUES (1,'r','x','LOW','t','c','2026-01-01')"
    )
    db3.execute("INSERT INTO finding_metrics(finding_id,name,value) VALUES (1,'gap',0.1)")
    with pytest.raises(sqlite3.IntegrityError):
        db3.execute(
            "INSERT INTO finding_metrics(finding_id,name,value) VALUES (1,'gap',0.2)"
        )
