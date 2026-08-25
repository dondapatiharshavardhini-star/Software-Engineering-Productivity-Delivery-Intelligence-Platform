"""
data_cleaning.py
=================
Loads raw CSVs (as if pulled from Jira/GitHub/CI APIs), cleans them, and
writes validated, analysis-ready tables to data/processed/.

Cleaning decisions are logged to stdout AND written to
reports/data_cleaning_log.txt so every transformation is auditable —
this is the kind of documentation a hiring manager expects to see in a
real data-engineering pipeline.
"""

import pandas as pd
import numpy as np
import os

RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"
LOG_PATH = "reports/data_cleaning_log.txt"

log_lines = []


def log(msg):
    print(msg)
    log_lines.append(msg)


def load_raw():
    tables = {}
    for name in ["teams", "developers", "projects", "sprints", "issues",
                 "commits", "pull_requests", "code_reviews", "deployments", "releases"]:
        tables[name] = pd.read_csv(f"{RAW_DIR}/{name}.csv")
    return tables


# ---------------------------------------------------------------------------
# Individual cleaning steps
# ---------------------------------------------------------------------------

def clean_developers(df):
    log(f"\n[developers] starting rows: {len(df)}")
    before = len(df)
    df = df.drop_duplicates(subset="developer_id", keep="first")
    log(f"[developers] removed {before - len(df)} duplicate developer_id rows "
        f"(likely duplicate HRIS/Jira sync records)")
    df["hire_date"] = pd.to_datetime(df["hire_date"])
    return df


def clean_issues(df):
    log(f"\n[issues] starting rows: {len(df)}")
    before = len(df)
    df = df.drop_duplicates(subset="issue_id", keep="first")
    log(f"[issues] removed {before - len(df)} exact-duplicate issue rows "
        f"(webhook double-fire on Jira sync)")

    # normalize status text: strip whitespace + fix casing
    n_bad_case = (df["status"] != df["status"].str.strip().str.title()).sum()
    df["status"] = df["status"].str.strip().str.title()
    # collapse "Won'T Fix" -> "Won't Fix" from .title() side effect
    df["status"] = df["status"].replace({"Won'T Fix": "Won't Fix"})
    log(f"[issues] normalized casing/whitespace on {n_bad_case} status values "
        f"(e.g. 'DONE  ' -> 'Done')")

    df["created_date"] = pd.to_datetime(df["created_date"])
    df["resolved_date"] = pd.to_datetime(df["resolved_date"], errors="coerce")

    # outlier handling: cap resolution_time_hours at the 99.5th percentile
    # rather than dropping — a genuinely-stuck ticket is real signal, but a
    # 40x data-entry artifact would distort MTTR. We winsorize instead of
    # deleting so we don't lose the "reopened"/"escaped" flags on that row.
    cap = df["resolution_time_hours"].quantile(0.995)
    n_capped = (df["resolution_time_hours"] > cap).sum()
    df["resolution_time_hours"] = df["resolution_time_hours"].clip(upper=cap)
    log(f"[issues] winsorized {n_capped} extreme resolution_time_hours values "
        f"at the 99.5th percentile ({cap:.1f}h) instead of dropping them")

    # missing severity is expected for non-bug issue types -> not an error
    n_missing_severity = df["severity"].isna().sum()
    log(f"[issues] {n_missing_severity} rows have null severity — expected, "
        f"since severity only applies to issue_type == 'Bug'")

    df["reopened"] = df["reopened"].astype(int)
    df["escaped_defect"] = df["escaped_defect"].astype(int)

    # derived metric: cycle time in days (created -> resolved)
    df["cycle_time_days"] = (df["resolved_date"] - df["created_date"]).dt.total_seconds() / 86400
    return df


def clean_commits(df):
    log(f"\n[commits] starting rows: {len(df)}")
    before = len(df)
    df = df.drop_duplicates(subset="commit_id", keep="first")
    log(f"[commits] removed {before - len(df)} duplicate commit_id rows")

    n_negative = (df["lines_added"] < 0).sum()
    df.loc[df["lines_added"] < 0, "lines_added"] = np.nan
    df["lines_added"] = df["lines_added"].fillna(df["lines_added"].median())
    log(f"[commits] fixed {n_negative} rows with impossible negative "
        f"lines_added (broken git-log parser sentinel), imputed with median")

    df["commit_timestamp"] = pd.to_datetime(df["commit_timestamp"])
    df["total_churn"] = df["lines_added"] + df["lines_deleted"]
    return df


def clean_pull_requests(df):
    log(f"\n[pull_requests] starting rows: {len(df)}")
    df["opened_date"] = pd.to_datetime(df["opened_date"])
    df["closed_date"] = pd.to_datetime(df["closed_date"], errors="coerce")

    n_missing_review = df["review_time_hours"].isna().sum()
    log(f"[pull_requests] {n_missing_review} rows missing review_time_hours "
        f"— left as NULL (still-open PRs / API sync gaps), excluded from "
        f"average-review-time KPI rather than imputed, to avoid biasing the metric")

    df["is_merged"] = (df["status"] == "Merged").astype(int)
    return df


def clean_code_reviews(df):
    log(f"\n[code_reviews] starting rows: {len(df)}")
    df["review_timestamp"] = pd.to_datetime(df["review_timestamp"])
    return df


def clean_deployments(df):
    log(f"\n[deployments] starting rows: {len(df)}")
    df["deployment_timestamp"] = pd.to_datetime(df["deployment_timestamp"])
    df["is_failure"] = (df["status"] == "Failed").astype(int)
    return df


def clean_releases(df):
    log(f"\n[releases] starting rows: {len(df)}")
    df["planned_release_date"] = pd.to_datetime(df["planned_release_date"])
    df["actual_release_date"] = pd.to_datetime(df["actual_release_date"], errors="coerce")
    df["is_delayed"] = (df["status"] == "Delayed").astype(int)
    n_cancelled = (df["status"] == "Cancelled").sum()
    log(f"[releases] {n_cancelled} releases cancelled — retained (not dropped); "
        f"cancellations are analytically meaningful, not data errors")
    return df


def clean_sprints(df):
    log(f"\n[sprints] starting rows: {len(df)}")
    df["sprint_start_date"] = pd.to_datetime(df["sprint_start_date"])
    df["sprint_end_date"] = pd.to_datetime(df["sprint_end_date"])
    df["sprint_completion_rate"] = (
        df["completed_story_points"] / df["planned_story_points"]
    ).clip(upper=1.2)  # >100% is possible (stretch work pulled in) but cap runaway values
    return df


def validate(tables):
    log("\n[validation] Referential integrity checks")
    checks = [
        ("issues.project_id -> projects", tables["issues"]["project_id"], tables["projects"]["project_id"]),
        ("issues.assignee_id -> developers", tables["issues"]["assignee_id"], tables["developers"]["developer_id"]),
        ("sprints.project_id -> projects", tables["sprints"]["project_id"], tables["projects"]["project_id"]),
        ("pull_requests.author_id -> developers", tables["pull_requests"]["author_id"], tables["developers"]["developer_id"]),
        ("deployments.project_id -> projects", tables["deployments"]["project_id"], tables["projects"]["project_id"]),
        ("releases.project_id -> projects", tables["releases"]["project_id"], tables["projects"]["project_id"]),
    ]
    all_ok = True
    for label, child_col, parent_col in checks:
        orphans = (~child_col.isin(parent_col)).sum()
        status = "OK" if orphans == 0 else f"FAIL ({orphans} orphans)"
        if orphans != 0:
            all_ok = False
        log(f"  {label}: {status}")

    log(f"\n[validation] Overall referential integrity: {'PASSED' if all_ok else 'FAILED'}")
    return all_ok


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs("reports", exist_ok=True)

    log("=" * 70)
    log("DATA CLEANING PIPELINE — Software Engineering Analytics Platform")
    log("=" * 70)

    tables = load_raw()

    tables["teams"]["formed_date"] = pd.to_datetime(tables["teams"]["formed_date"])
    tables["projects"]["start_date"] = pd.to_datetime(tables["projects"]["start_date"])

    tables["developers"] = clean_developers(tables["developers"])
    tables["sprints"] = clean_sprints(tables["sprints"])
    tables["issues"] = clean_issues(tables["issues"])
    tables["commits"] = clean_commits(tables["commits"])
    tables["pull_requests"] = clean_pull_requests(tables["pull_requests"])
    tables["code_reviews"] = clean_code_reviews(tables["code_reviews"])
    tables["deployments"] = clean_deployments(tables["deployments"])
    tables["releases"] = clean_releases(tables["releases"])

    validate(tables)

    log("\n[output] Writing cleaned tables to data/processed/")
    for name, df in tables.items():
        path = f"{PROCESSED_DIR}/{name}.csv"
        df.to_csv(path, index=False)
        log(f"  wrote {path}  ({len(df):,} rows, {df.shape[1]} cols)")

    with open(LOG_PATH, "w") as f:
        f.write("\n".join(log_lines))
    log(f"\nFull cleaning log written to {LOG_PATH}")


if __name__ == "__main__":
    main()
