"""
generate_data.py
=================
Generates a realistic synthetic Software Development Lifecycle (SDLC) dataset
that mimics data you'd extract from Jira + GitHub + a CI/CD system
(e.g. Jenkins/GitHub Actions) via their APIs.

Design principles used (documented for the README / interview prep):
  - Entities are generated in dependency order (teams -> developers -> projects
    -> sprints -> issues -> commits -> PRs -> code reviews -> deployments -> releases)
    so foreign keys always resolve.
  - Realistic *correlated* noise is injected on purpose: teams with higher
    workload have higher bug/reopen rates, PR review time drags cycle time,
    critical-bug-heavy sprints are more likely to slip. This is what makes the
    downstream EDA/ML findings meaningful instead of purely random.
  - A handful of teams/projects are deliberately seeded as "chronically at risk"
    so the risk-scoring and ML sections have real signal to detect.

Output: 10 raw CSVs written to data/raw/
"""

import numpy as np
import pandas as pd
from faker import Faker
from datetime import datetime, timedelta
import random

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker()
Faker.seed(SEED)

OUT_DIR = "data/raw"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
N_TEAMS = 8
N_DEVELOPERS = 60
N_PROJECTS = 12
SPRINTS_PER_PROJECT = 10          # ~5 months of 2-week sprints per project
SPRINT_LENGTH_DAYS = 14
PROJECT_START = datetime(2024, 1, 1)

ISSUE_TYPES = ["Bug", "Story", "Task", "Sub-task"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
SEVERITIES = ["Minor", "Major", "Critical", "Blocker"]
ISSUE_STATUSES = ["Done", "In Progress", "Reopened", "Won't Fix"]
ISSUE_STATUS_PROBS = [0.62, 0.24, 0.10, 0.04]
PR_STATUSES = ["Merged", "Closed", "Open"]
PR_STATUS_PROBS = [0.75, 0.15, 0.10]
DEPLOY_ENVS = ["staging", "production"]
RELEASE_STATUSES = ["On Time", "Delayed", "On Time", "On Time", "Delayed", "Cancelled"]

ROLES = ["Backend Engineer", "Frontend Engineer", "Full-Stack Engineer",
         "QA Engineer", "DevOps Engineer", "Data Engineer", "Engineering Manager"]
SENIORITY = ["Junior", "Mid", "Senior", "Staff"]

# Team "archetypes" — deliberately injected signal so at-risk teams are
# genuinely riskier across every table (bugs, review time, deploys, releases).
TEAM_RISK_PROFILE = {}  # team_id -> risk multiplier in [0.6 (healthy) .. 1.6 (at risk)]


def make_teams():
    rows = []
    team_names = ["Payments", "Checkout", "Search", "Identity", "Platform-Infra",
                  "Mobile", "Notifications", "Data-Platform"]
    for i in range(1, N_TEAMS + 1):
        team_id = f"T{i:03d}"
        risk = np.random.choice([0.7, 0.9, 1.0, 1.1, 1.3, 1.5],
                                 p=[0.15, 0.2, 0.25, 0.2, 0.12, 0.08])
        TEAM_RISK_PROFILE[team_id] = risk
        rows.append({
            "team_id": team_id,
            "team_name": team_names[i - 1] if i - 1 < len(team_names) else f"Team-{i}",
            "department": np.random.choice(["Engineering", "Platform", "Product Engineering"]),
            "formed_date": (PROJECT_START - timedelta(days=int(np.random.uniform(180, 900)))).date(),
        })
    return pd.DataFrame(rows)


def make_developers(teams_df):
    rows = []
    for i in range(1, N_DEVELOPERS + 1):
        dev_id = f"D{i:04d}"
        team_id = np.random.choice(teams_df["team_id"])
        seniority = np.random.choice(SENIORITY, p=[0.3, 0.35, 0.25, 0.10])
        # seniority influences base productivity/quality later
        rows.append({
            "developer_id": dev_id,
            "full_name": fake.name(),
            "team_id": team_id,
            "role": np.random.choice(ROLES, p=[0.25, 0.2, 0.2, 0.15, 0.1, 0.05, 0.05]),
            "seniority": seniority,
            "hire_date": (PROJECT_START - timedelta(days=int(np.random.uniform(60, 1500)))).date(),
            "timezone": np.random.choice(["IST", "PST", "EST", "CET", "GMT"]),
        })
    return pd.DataFrame(rows)


def make_projects(teams_df):
    rows = []
    project_names = ["Checkout-Web", "Payments-API", "Search-Service", "Auth-Gateway",
                      "Mobile-App-iOS", "Mobile-App-Android", "Notification-Hub",
                      "Data-Pipeline", "Fraud-Detection", "Customer-Portal",
                      "Inventory-Service", "Analytics-Dashboard"]
    for i in range(1, N_PROJECTS + 1):
        project_id = f"P{i:03d}"
        team_id = np.random.choice(teams_df["team_id"])
        rows.append({
            "project_id": project_id,
            "project_name": project_names[i - 1] if i - 1 < len(project_names) else f"Project-{i}",
            "team_id": team_id,
            "start_date": (PROJECT_START - timedelta(days=int(np.random.uniform(0, 60)))).date(),
            "criticality": np.random.choice(["Low", "Medium", "High"], p=[0.25, 0.45, 0.3]),
            "tech_stack": np.random.choice(["Java/Spring", "Python/Django", "Node/Express",
                                             "Go", "React/TypeScript", "Kotlin/Android"]),
        })
    return pd.DataFrame(rows)


def make_sprints(projects_df):
    rows = []
    sprint_counter = 1
    for _, proj in projects_df.iterrows():
        start = pd.Timestamp(proj["start_date"])
        for s in range(1, SPRINTS_PER_PROJECT + 1):
            sprint_id = f"S{sprint_counter:04d}"
            sprint_counter += 1
            sprint_start = start + timedelta(days=(s - 1) * SPRINT_LENGTH_DAYS)
            sprint_end = sprint_start + timedelta(days=SPRINT_LENGTH_DAYS - 1)
            team_risk = TEAM_RISK_PROFILE[proj["team_id"]]

            planned_points = int(np.random.uniform(30, 70))
            # completion rate erodes with team risk, with sprint-to-sprint noise
            base_completion = np.clip(np.random.normal(0.88 / team_risk, 0.12), 0.35, 1.05)
            completed_points = int(planned_points * min(base_completion, 1.0))

            rows.append({
                "sprint_id": sprint_id,
                "project_id": proj["project_id"],
                "team_id": proj["team_id"],
                "sprint_number": s,
                "sprint_start_date": sprint_start.date(),
                "sprint_end_date": sprint_end.date(),
                "planned_story_points": planned_points,
                "completed_story_points": completed_points,
            })
    return pd.DataFrame(rows)


def make_issues(sprints_df, developers_df, projects_df):
    rows = []
    dev_by_team = developers_df.groupby("team_id")["developer_id"].apply(list).to_dict()
    issue_counter = 1
    for _, sprint in sprints_df.iterrows():
        team_risk = TEAM_RISK_PROFILE[sprint["team_id"]]
        n_issues = int(np.random.uniform(15, 35))
        candidate_devs = dev_by_team.get(sprint["team_id"], developers_df["developer_id"].tolist())
        sprint_start = pd.Timestamp(sprint["sprint_start_date"])
        sprint_end = pd.Timestamp(sprint["sprint_end_date"])

        for _ in range(n_issues):
            issue_id = f"I{issue_counter:06d}"
            issue_counter += 1
            issue_type = np.random.choice(ISSUE_TYPES, p=[0.35, 0.3, 0.25, 0.10])
            priority = np.random.choice(PRIORITIES, p=[0.35, 0.35, 0.22, 0.08])
            severity = (np.random.choice(SEVERITIES, p=[0.45, 0.32, 0.18, 0.05])
                        if issue_type == "Bug" else None)

            created = sprint_start + timedelta(days=np.random.uniform(0, SPRINT_LENGTH_DAYS - 1))

            # resolution time (in hours) driven by priority + team risk + a long tail
            priority_factor = {"Low": 1.4, "Medium": 1.0, "High": 0.7, "Critical": 0.45}[priority]
            base_hours = np.random.gamma(shape=2.0, scale=14) * priority_factor * team_risk
            resolution_hours = round(max(1, base_hours), 1)

            status = np.random.choice(ISSUE_STATUSES, p=ISSUE_STATUS_PROBS)
            resolved_date = created + timedelta(hours=resolution_hours) if status in \
                ("Done", "Reopened", "Won't Fix") else pd.NaT

            reopened = 1 if (status == "Reopened" or
                              (issue_type == "Bug" and np.random.random() < 0.06 * team_risk)) else 0

            # escaped defect: a bug found in production after release
            escaped = 1 if (issue_type == "Bug" and np.random.random() < 0.08 * team_risk) else 0

            rows.append({
                "issue_id": issue_id,
                "project_id": sprint["project_id"],
                "sprint_id": sprint["sprint_id"],
                "team_id": sprint["team_id"],
                "assignee_id": np.random.choice(candidate_devs),
                "issue_type": issue_type,
                "priority": priority,
                "severity": severity,
                "status": status,
                "created_date": created,
                "resolved_date": resolved_date,
                "resolution_time_hours": resolution_hours if pd.notna(resolved_date) else np.nan,
                "reopened": reopened,
                "escaped_defect": escaped,
            })
    return pd.DataFrame(rows)


def make_commits(sprints_df, developers_df):
    rows = []
    dev_by_team = developers_df.groupby("team_id")["developer_id"].apply(list).to_dict()
    commit_counter = 1
    for _, sprint in sprints_df.iterrows():
        candidate_devs = dev_by_team.get(sprint["team_id"], developers_df["developer_id"].tolist())
        n_commits = int(np.random.uniform(40, 140))
        sprint_start = pd.Timestamp(sprint["sprint_start_date"])
        for _ in range(n_commits):
            commit_id = f"C{commit_counter:07d}"
            commit_counter += 1
            ts = sprint_start + timedelta(
                days=np.random.uniform(0, SPRINT_LENGTH_DAYS - 1),
                hours=np.random.uniform(0, 23))
            rows.append({
                "commit_id": commit_id,
                "project_id": sprint["project_id"],
                "sprint_id": sprint["sprint_id"],
                "developer_id": np.random.choice(candidate_devs),
                "commit_timestamp": ts,
                "lines_added": int(np.random.gamma(2.0, 25)),
                "lines_deleted": int(np.random.gamma(1.5, 15)),
                "files_changed": int(np.clip(np.random.gamma(1.5, 2), 1, 40)),
            })
    return pd.DataFrame(rows)


def make_pull_requests(sprints_df, developers_df):
    rows = []
    dev_by_team = developers_df.groupby("team_id")["developer_id"].apply(list).to_dict()
    pr_counter = 1
    for _, sprint in sprints_df.iterrows():
        team_risk = TEAM_RISK_PROFILE[sprint["team_id"]]
        candidate_devs = dev_by_team.get(sprint["team_id"], developers_df["developer_id"].tolist())
        n_prs = int(np.random.uniform(10, 30))
        sprint_start = pd.Timestamp(sprint["sprint_start_date"])
        for _ in range(n_prs):
            pr_id = f"PR{pr_counter:06d}"
            pr_counter += 1
            author = np.random.choice(candidate_devs)
            reviewers = [d for d in candidate_devs if d != author]
            reviewer = np.random.choice(reviewers) if reviewers else author

            opened = sprint_start + timedelta(days=np.random.uniform(0, SPRINT_LENGTH_DAYS - 2))
            size_lines = int(np.random.gamma(2.0, 60))  # PR size in changed lines
            # bigger PRs + risk teams take longer to review (in hours)
            size_factor = 1 + (size_lines / 400)
            review_hours = round(max(0.5, np.random.gamma(2.0, 6) * size_factor * team_risk), 1)

            status = np.random.choice(PR_STATUSES, p=PR_STATUS_PROBS)
            closed = opened + timedelta(hours=review_hours) if status in ("Merged", "Closed") else pd.NaT

            rows.append({
                "pull_request_id": pr_id,
                "project_id": sprint["project_id"],
                "sprint_id": sprint["sprint_id"],
                "author_id": author,
                "reviewer_id": reviewer,
                "opened_date": opened,
                "closed_date": closed,
                "review_time_hours": review_hours if pd.notna(closed) else np.nan,
                "pr_size_lines": size_lines,
                "status": status,
            })
    return pd.DataFrame(rows)


def make_code_reviews(pull_requests_df):
    rows = []
    review_counter = 1
    merged_or_closed = pull_requests_df[pull_requests_df["status"].isin(["Merged", "Closed"])]
    for _, pr in merged_or_closed.iterrows():
        n_review_rounds = np.random.choice([1, 2, 3], p=[0.55, 0.3, 0.15])
        for r in range(n_review_rounds):
            review_id = f"RV{review_counter:07d}"
            review_counter += 1
            rows.append({
                "review_id": review_id,
                "pull_request_id": pr["pull_request_id"],
                "reviewer_id": pr["reviewer_id"],
                "review_round": r + 1,
                "comments_count": int(np.random.gamma(1.5, 3)),
                "approved": 1 if r == n_review_rounds - 1 else 0,
                "review_timestamp": (pr["opened_date"] + timedelta(
                    hours=np.random.uniform(1, max(2, pr["review_time_hours"] or 4)))),
            })
    return pd.DataFrame(rows)


def make_deployments(sprints_df):
    rows = []
    deploy_counter = 1
    for _, sprint in sprints_df.iterrows():
        team_risk = TEAM_RISK_PROFILE[sprint["team_id"]]
        n_deploys = int(np.clip(np.random.poisson(6 / team_risk), 1, 20))
        sprint_start = pd.Timestamp(sprint["sprint_start_date"])
        for _ in range(n_deploys):
            deploy_id = f"DEP{deploy_counter:06d}"
            deploy_counter += 1
            ts = sprint_start + timedelta(days=np.random.uniform(0, SPRINT_LENGTH_DAYS - 1))
            # higher team risk -> higher chance of a failed deployment
            failed = 1 if np.random.random() < 0.08 * team_risk else 0
            rows.append({
                "deployment_id": deploy_id,
                "project_id": sprint["project_id"],
                "sprint_id": sprint["sprint_id"],
                "environment": np.random.choice(DEPLOY_ENVS, p=[0.6, 0.4]),
                "deployment_timestamp": ts,
                "status": "Failed" if failed else "Success",
                "rollback": 1 if (failed and np.random.random() < 0.5) else 0,
                "duration_minutes": round(max(1, np.random.gamma(2.0, 8)), 1),
            })
    return pd.DataFrame(rows)


def make_releases(projects_df, sprints_df):
    rows = []
    release_counter = 1
    for _, proj in projects_df.iterrows():
        proj_sprints = sprints_df[sprints_df["project_id"] == proj["project_id"]].sort_values("sprint_number")
        team_risk = TEAM_RISK_PROFILE[proj["team_id"]]
        # a release roughly every 2 sprints
        for idx in range(1, len(proj_sprints), 2):
            sprint = proj_sprints.iloc[idx]
            release_id = f"REL{release_counter:05d}"
            release_counter += 1
            planned_date = pd.Timestamp(sprint["sprint_end_date"]) + timedelta(days=2)
            delay_days = max(0, np.random.exponential(2.0 * team_risk) - 1)
            actual_date = planned_date + timedelta(days=delay_days)
            status = "Delayed" if delay_days > 1 else np.random.choice(
                ["On Time", "Cancelled"], p=[0.96, 0.04])

            rows.append({
                "release_id": release_id,
                "project_id": proj["project_id"],
                "team_id": proj["team_id"],
                "sprint_id": sprint["sprint_id"],
                "planned_release_date": planned_date.date(),
                "actual_release_date": actual_date.date() if status != "Cancelled" else pd.NaT,
                "release_delay_days": round(delay_days, 1) if status != "Cancelled" else np.nan,
                "status": status,
                "version": f"v{np.random.randint(1,5)}.{np.random.randint(0,20)}.{np.random.randint(0,10)}",
            })
    return pd.DataFrame(rows)


def inject_data_quality_issues(dfs):
    """
    Deliberately injects realistic messiness so the cleaning pipeline (Section 2)
    has real problems to solve: nulls, dupes, inconsistent casing, outliers.
    This mirrors what you'd actually pull from a Jira/GitHub export.
    """
    issues = dfs["issues"].copy()
    # 1) Duplicate a handful of issue rows (double-synced webhook events)
    dup_sample = issues.sample(frac=0.01, random_state=SEED)
    issues = pd.concat([issues, dup_sample], ignore_index=True)
    # 2) Inconsistent status casing/whitespace
    mask = issues.sample(frac=0.03, random_state=1).index
    issues.loc[mask, "status"] = issues.loc[mask, "status"].str.upper() + "  "
    # 3) A few extreme resolution-time outliers (stuck tickets)
    out_idx = issues.sample(frac=0.005, random_state=2).index
    issues.loc[out_idx, "resolution_time_hours"] = issues.loc[out_idx, "resolution_time_hours"] * 40
    dfs["issues"] = issues

    prs = dfs["pull_requests"].copy()
    null_idx = prs.sample(frac=0.02, random_state=3).index
    prs.loc[null_idx, "review_time_hours"] = np.nan
    dfs["pull_requests"] = prs

    devs = dfs["developers"].copy()
    dup_dev = devs.sample(n=2, random_state=4)
    devs = pd.concat([devs, dup_dev], ignore_index=True)
    dfs["developers"] = devs

    commits = dfs["commits"].copy()
    neg_idx = commits.sample(frac=0.002, random_state=5).index
    commits.loc[neg_idx, "lines_added"] = -1  # bad sentinel value from a broken parser
    dfs["commits"] = commits

    return dfs


def main():
    import os
    os.makedirs(OUT_DIR, exist_ok=True)

    print("Generating teams...")
    teams = make_teams()
    print("Generating developers...")
    developers = make_developers(teams)
    print("Generating projects...")
    projects = make_projects(teams)
    print("Generating sprints...")
    sprints = make_sprints(projects)
    print("Generating issues/bugs...")
    issues = make_issues(sprints, developers, projects)
    print("Generating git commits...")
    commits = make_commits(sprints, developers)
    print("Generating pull requests...")
    pull_requests = make_pull_requests(sprints, developers)
    print("Generating code reviews...")
    code_reviews = make_code_reviews(pull_requests)
    print("Generating deployments...")
    deployments = make_deployments(sprints)
    print("Generating releases...")
    releases = make_releases(projects, sprints)

    dfs = {
        "teams": teams, "developers": developers, "projects": projects,
        "sprints": sprints, "issues": issues, "commits": commits,
        "pull_requests": pull_requests, "code_reviews": code_reviews,
        "deployments": deployments, "releases": releases,
    }

    dfs = inject_data_quality_issues(dfs)

    for name, df in dfs.items():
        path = f"{OUT_DIR}/{name}.csv"
        df.to_csv(path, index=False)
        print(f"  wrote {path}  ({len(df):,} rows)")

    print("\nRaw data generation complete.")


if __name__ == "__main__":
    main()
