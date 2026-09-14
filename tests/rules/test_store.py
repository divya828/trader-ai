import pytest

from trader_ai.db.connection import (
    apply_schema,
    apply_schema_v02,
    apply_schema_v02c,
    connect,
)
from trader_ai.rules.finding import Finding, Severity, Subject
from trader_ai.rules.score import DimensionScore
from trader_ai.rules.store import save_findings, save_scores


@pytest.fixture
def db3():
    con = connect(":memory:")
    apply_schema(con)
    apply_schema_v02(con)
    apply_schema_v02c(con)
    yield con
    con.close()


def _finding():
    return Finding(
        rule_id="diversification.category_duplication",
        severity=Severity.MEDIUM,
        title="3 funds share one category",
        subjects=[Subject(kind="SCHEME", ref="Some Fund", weight=0.12)],
        metrics={"fund_count": 3.0, "combined_weight": 0.24},
        citation_key="sebi_categorization",
        computed_at="2026-09-14T00:00:00",
        dimension="DIVERSIFICATION",
    )


def test_saving_a_finding_persists_its_parts(db3):
    save_findings(db3, "run-1", [_finding()])
    assert db3.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 1
    assert db3.execute("SELECT COUNT(*) FROM finding_subjects").fetchone()[0] == 1
    assert db3.execute("SELECT COUNT(*) FROM finding_metrics").fetchone()[0] == 2


def test_saved_metrics_round_trip(db3):
    save_findings(db3, "run-1", [_finding()])
    rows = {
        r["name"]: r["value"]
        for r in db3.execute("SELECT name, value FROM finding_metrics")
    }
    assert rows["fund_count"] == pytest.approx(3.0)


def test_severity_is_stored_as_its_string_value(db3):
    save_findings(db3, "run-1", [_finding()])
    assert db3.execute("SELECT severity FROM findings").fetchone()[0] == "MEDIUM"


def test_no_folio_or_pan_reaches_the_findings_tables(db3):
    """The redaction gate in v0.3 depends on this being true already."""
    save_findings(db3, "run-1", [_finding()])
    text = " ".join(
        str(value)
        for table in ("findings", "finding_subjects", "finding_metrics")
        for row in db3.execute(f"SELECT * FROM {table}")
        for value in tuple(row)
    )
    import re

    assert not re.search(r"[A-Z]{5}[0-9]{4}[A-Z]", text), "PAN-shaped value stored"
    assert not re.search(r"\b\d{3,}\s*/\s*\d+\b", text), "folio-shaped value stored"


def test_saving_a_null_score_keeps_its_reason(db3):
    save_scores(
        db3,
        [
            DimensionScore(
                dimension="TAX_EFFICIENCY",
                score=None,
                finding_count=0,
                unscored_reason="no disposals in ledger",
            )
        ],
    )
    row = db3.execute(
        "SELECT score, unscored_reason FROM health_scores"
    ).fetchone()
    assert row["score"] is None
    assert row["unscored_reason"] == "no disposals in ledger"


def test_scores_accumulate_across_runs_for_tracking(db3):
    score = DimensionScore(dimension="COST", score=80.0, finding_count=1)
    save_scores(db3, [score])
    save_scores(db3, [score])
    assert db3.execute("SELECT COUNT(*) FROM health_scores").fetchone()[0] == 2


def test_findings_from_different_runs_are_distinguishable(db3):
    save_findings(db3, "run-1", [_finding()])
    save_findings(db3, "run-2", [_finding()])
    runs = {r["run_id"] for r in db3.execute("SELECT run_id FROM findings")}
    assert runs == {"run-1", "run-2"}


def test_saving_nothing_is_harmless(db3):
    assert save_findings(db3, "run-1", []) == 0
    assert save_scores(db3, []) == 0


def test_subject_weight_round_trips_as_a_ratio(db3):
    save_findings(db3, "run-1", [_finding()])
    weight = db3.execute("SELECT weight FROM finding_subjects").fetchone()[0]
    assert 0.0 <= weight <= 1.0
