"""
test_pipeline.py
=================
Lightweight pytest suite validating the data pipeline's integrity:
referential integrity, KPI value ranges, and no unexpected nulls in
primary keys. Run with: pytest tests/
"""

import pandas as pd
import pytest
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")


@pytest.fixture(scope="module")
def tables():
    names = ["teams", "developers", "projects", "sprints", "issues", "commits",
              "pull_requests", "code_reviews", "deployments", "releases"]
    return {n: pd.read_csv(f"{DATA_DIR}/{n}.csv") for n in names}


def test_primary_keys_unique(tables):
    pk_map = {
        "teams": "team_id", "developers": "developer_id", "projects": "project_id",
        "sprints": "sprint_id", "issues": "issue_id", "commits": "commit_id",
        "pull_requests": "pull_request_id", "code_reviews": "review_id",
        "deployments": "deployment_id", "releases": "release_id",
    }
    for table, pk in pk_map.items():
        df = tables[table]
        assert df[pk].is_unique, f"{table}.{pk} has duplicate values"
        assert df[pk].notna().all(), f"{table}.{pk} has null values"


def test_referential_integrity(tables):
    checks = [
        (tables["issues"]["project_id"], tables["projects"]["project_id"]),
        (tables["issues"]["assignee_id"], tables["developers"]["developer_id"]),
        (tables["sprints"]["project_id"], tables["projects"]["project_id"]),
        (tables["pull_requests"]["author_id"], tables["developers"]["developer_id"]),
        (tables["deployments"]["project_id"], tables["projects"]["project_id"]),
        (tables["releases"]["project_id"], tables["projects"]["project_id"]),
    ]
    for child, parent in checks:
        orphans = (~child.isin(parent)).sum()
        assert orphans == 0, f"Found {orphans} orphaned foreign key values"


def test_sprint_completion_rate_bounds(tables):
    rates = tables["sprints"]["sprint_completion_rate"]
    assert rates.min() >= 0, "Sprint completion rate should not be negative"
    assert rates.max() <= 1.21, "Sprint completion rate exceeds the capped upper bound"


def test_no_negative_commit_lines(tables):
    assert (tables["commits"]["lines_added"] >= 0).all(), \
        "Cleaning pipeline should have removed negative lines_added sentinels"


def test_issue_status_values_normalized(tables):
    valid_statuses = {"Done", "In Progress", "Reopened", "Won't Fix"}
    actual = set(tables["issues"]["status"].unique())
    assert actual.issubset(valid_statuses), f"Unexpected status values: {actual - valid_statuses}"


def test_kpi_files_exist():
    for f in ["kpi_team_summary.csv", "kpi_project_health.csv", "kpi_developer_productivity.csv"]:
        assert os.path.exists(f"{DATA_DIR}/{f}"), f"Missing KPI output: {f}"


def test_project_health_score_bounds():
    df = pd.read_csv(f"{DATA_DIR}/kpi_project_health.csv")
    assert (df["project_health_score"] >= 0).all()
    assert (df["project_health_score"] <= 100).all()
