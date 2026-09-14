"""Persist findings and scores.

Findings accumulate per run so movement is trackable across statements, and a
NULL score keeps the reason it could not be computed.
"""

from __future__ import annotations

import sqlite3

from trader_ai.rules.finding import Finding
from trader_ai.rules.score import DimensionScore


def save_findings(con: sqlite3.Connection, run_id: str, findings: list[Finding]) -> int:
    """Write findings, their subjects and their metrics. Returns the count."""
    for finding in findings:
        cursor = con.execute(
            "INSERT INTO findings(run_id, rule_id, severity, title, citation_key,"
            " computed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                finding.rule_id,
                finding.severity.value,
                finding.title,
                finding.citation_key,
                finding.computed_at,
            ),
        )
        finding_id = int(cursor.lastrowid)
        for subject in finding.subjects:
            con.execute(
                "INSERT INTO finding_subjects(finding_id, kind, ref, weight)"
                " VALUES (?, ?, ?, ?)",
                (finding_id, subject.kind, subject.ref, subject.weight),
            )
        for name, value in finding.metrics.items():
            con.execute(
                "INSERT INTO finding_metrics(finding_id, name, value)"
                " VALUES (?, ?, ?)",
                (finding_id, name, float(value)),
            )
    con.commit()
    return len(findings)


def save_scores(con: sqlite3.Connection, scores: list[DimensionScore]) -> int:
    """Append this run's dimension scores, preserving history."""
    for score in scores:
        con.execute(
            "INSERT INTO health_scores(dimension, score, finding_count,"
            " unscored_reason) VALUES (?, ?, ?, ?)",
            (
                score.dimension,
                score.score,
                score.finding_count,
                score.unscored_reason,
            ),
        )
    con.commit()
    return len(scores)
