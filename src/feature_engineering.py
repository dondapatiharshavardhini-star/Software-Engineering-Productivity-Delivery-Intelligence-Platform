"""
feature_engineering.py
=======================
KPI Framework — computes every KPI required by the project spec at the
team, project, and (where applicable) developer grain, from the cleaned
tables in data/processed/. Writes kpi_* tables back to data/processed/ so
both the dashboard and the ML pipeline can reuse them.

KPI DEFINITIONS (business meaning documented inline, restated in the README):

1.  Sprint Completion Rate      = completed_story_points / planned_story_points
    Meaning: how reliably a team delivers what it commits to each sprint.

2.  Sprint Velocity              = avg(completed_story_points) per sprint
    Meaning: throughput capacity, used for forward sprint planning.

3.  Avg Issue Cycle Time (days)  = avg(resolved_date - created_date)
    Meaning: how fast work moves end-to-end; a proxy for delivery speed.

4.  Mean Time to Resolve Bugs (MTTR, hours) = avg(resolution_time_hours) for issue_type='Bug'
    Meaning: responsiveness to defects; directly affects customer-facing quality.

5.  Bug Reopen Rate (%)          = reopened_bugs / total_bugs * 100
    Meaning: fix quality — high reopen rate suggests rushed/incomplete fixes.

6.  Defect Density (%)           = bug_count / total_issues * 100
    Meaning: what share of engineering effort is defect-driven vs. feature-driven.

7.  PR Review Time (hours)       = avg(review_time_hours) for closed/merged PRs
    Meaning: code-review turnaround; a common delivery bottleneck.

8.  PR Merge Rate (%)            = merged_prs / total_prs * 100
    Meaning: how much submitted work actually ships vs. gets abandoned/rejected.

9.  Deployment Frequency (per week) = deployments / active_weeks
    Meaning: a core DORA metric for delivery throughput/DevOps maturity.

10. Release Success Rate (%)     = on_time_releases / total_releases * 100
    Meaning: predictability of the release process.

11. Release Delay Rate (%)       = delayed_releases / total_releases * 100
    Meaning: inverse of #10, tracked separately since "Cancelled" releases
    count against success but not necessarily against delay.

12. Change Failure Rate (CFR, %) = failed_deployments / total_deployments * 100
    Meaning: another core DORA metric — how often a deployment causes a
    failure requiring remediation.

13. Developer Workload Index     = commits*1 + PRs_authored*3 + issues_resolved*2
    Meaning: a WEIGHTED, multi-signal workload proxy. Deliberately NOT just
    a commit count — commit count alone rewards small/noisy commits and
    penalizes developers who write fewer, larger, well-tested PRs. Weighting
    PRs and resolved issues higher reflects that review-ready, shippable
    work is worth more than raw commit volume.

14. Project Health Score (0-100) = 0.35*quality_score + 0.35*delivery_score + 0.30*devops_score
    where quality_score = 100*(1 - escaped_defect_rate),
          delivery_score = avg sprint completion rate * 100,
          devops_score   = 100*(1 - change_failure_rate)
    Meaning: single composite index for the exec dashboard's project ranking.

15. Engineering Productivity Score (0-100), per developer = balanced blend of:
      - delivery contribution (issues resolved, PRs merged)
      - quality (inverse of bugs authored / reopen involvement)
      - collaboration (code reviews given)
      - workload normalization (avoids just rewarding raw activity)
    Explicitly NOT commits-per-day. See compute_productivity_score() below.
"""

import pandas as pd
import numpy as np
import os

PROCESSED_DIR = "data/processed"


def load_processed():
    tables = {}
    for name in ["teams", "developers", "projects", "sprints", "issues",
                 "commits", "pull_requests", "code_reviews", "deployments", "releases"]:
        tables[name] = pd.read_csv(f"{PROCESSED_DIR}/{name}.csv", parse_dates=False)
    return tables


def kpi_sprint_metrics(sprints):
    g = sprints.groupby("team_id").agg(
        avg_sprint_completion_rate=("sprint_completion_rate", "mean"),
        avg_sprint_velocity=("completed_story_points", "mean"),
        sprints_count=("sprint_id", "count"),
    ).reset_index()
    return g


def kpi_issue_metrics(issues):
    issues = issues.copy()
    resolved = issues[issues["resolved_date"].notna()]
    cycle = resolved.groupby("team_id")["cycle_time_days"].mean().rename("avg_cycle_time_days")

    bugs = issues[issues["issue_type"] == "Bug"]
    mttr = bugs[bugs["resolved_date"].notna()].groupby("team_id")["resolution_time_hours"].mean().rename("mttr_hours")
    reopen_rate = (bugs.groupby("team_id")["reopened"].sum() /
                    bugs.groupby("team_id").size() * 100).rename("bug_reopen_rate_pct")
    escaped_rate = (bugs.groupby("team_id")["escaped_defect"].sum() /
                     bugs.groupby("team_id").size() * 100).rename("escaped_defect_rate_pct")
    defect_density = (bugs.groupby("team_id").size() /
                       issues.groupby("team_id").size() * 100).rename("defect_density_pct")

    out = pd.concat([cycle, mttr, reopen_rate, escaped_rate, defect_density], axis=1).reset_index()
    out.rename(columns={"index": "team_id"}, inplace=True)
    return out


def kpi_pr_metrics(pull_requests, sprints):
    pr = pull_requests.merge(sprints[["sprint_id", "team_id"]], on="sprint_id", how="left")
    review_time = pr[pr["review_time_hours"].notna()].groupby("team_id")["review_time_hours"] \
        .mean().rename("avg_pr_review_hours")
    merge_rate = (pr.groupby("team_id")["is_merged"].sum() /
                  pr.groupby("team_id").size() * 100).rename("pr_merge_rate_pct")
    out = pd.concat([review_time, merge_rate], axis=1).reset_index()
    out.rename(columns={"index": "team_id"}, inplace=True)
    return out


def kpi_deployment_metrics(deployments, sprints):
    dep = deployments.merge(sprints[["sprint_id", "team_id"]], on="sprint_id", how="left")
    cfr = (dep.groupby("team_id")["is_failure"].sum() /
           dep.groupby("team_id").size() * 100).rename("change_failure_rate_pct")
    total_deploys = dep.groupby("team_id").size().rename("total_deployments")
    out = pd.concat([cfr, total_deploys], axis=1).reset_index()
    out.rename(columns={"index": "team_id"}, inplace=True)
    return out


def kpi_release_metrics(releases):
    g = releases.groupby("team_id").apply(lambda d: pd.Series({
        "total_releases": len(d),
        "release_success_rate_pct": (d["status"] == "On Time").mean() * 100,
        "release_delay_rate_pct": (d["status"] == "Delayed").mean() * 100,
        "avg_release_delay_days": d.loc[d["status"] != "Cancelled", "release_delay_days"].mean(),
    })).reset_index()
    return g


def compute_team_kpis(tables):
    sprint_k = kpi_sprint_metrics(tables["sprints"])
    issue_k = kpi_issue_metrics(tables["issues"])
    pr_k = kpi_pr_metrics(tables["pull_requests"], tables["sprints"])
    deploy_k = kpi_deployment_metrics(tables["deployments"], tables["sprints"])
    release_k = kpi_release_metrics(tables["releases"])

    kpis = tables["teams"][["team_id", "team_name"]].copy()
    for df in [sprint_k, issue_k, pr_k, deploy_k, release_k]:
        kpis = kpis.merge(df, on="team_id", how="left")

    # Project Health Score components (team-level rollup here; project-level in KPI #14 dashboard query)
    kpis["quality_score"] = 100 - kpis["escaped_defect_rate_pct"].fillna(0)
    kpis["delivery_score"] = kpis["avg_sprint_completion_rate"] * 100
    kpis["devops_score"] = 100 - kpis["change_failure_rate_pct"].fillna(0)
    kpis["team_health_score"] = (
        0.35 * kpis["quality_score"] + 0.35 * kpis["delivery_score"] + 0.30 * kpis["devops_score"]
    ).round(1)

    return kpis


def compute_project_health(tables):
    """Project-level Project Health Score (Q22 equivalent, computed in pandas)."""
    issues, sprints, deployments, projects = (
        tables["issues"], tables["sprints"], tables["deployments"], tables["projects"])

    bugs = issues[issues["issue_type"] == "Bug"]
    quality = (100 * (1 - bugs.groupby("project_id")["escaped_defect"].mean())).rename("quality_score")
    delivery = (sprints.groupby("project_id")["sprint_completion_rate"].mean() * 100).rename("delivery_score")
    devops = (100 * (1 - deployments.groupby("project_id")["is_failure"].mean())).rename("devops_score")

    out = pd.concat([quality, delivery, devops], axis=1).reset_index()
    out.rename(columns={"index": "project_id"}, inplace=True)
    out["project_health_score"] = (
        0.35 * out["quality_score"] + 0.35 * out["delivery_score"] + 0.30 * out["devops_score"]
    ).round(1)
    out = out.merge(projects[["project_id", "project_name", "criticality"]], on="project_id", how="left")
    return out.sort_values("project_health_score")


def compute_developer_workload(tables):
    commits, prs, issues, developers = (
        tables["commits"], tables["pull_requests"], tables["issues"], tables["developers"])

    commit_count = commits.groupby("developer_id").size().rename("commit_count")
    pr_count = prs.groupby("author_id").size().rename("pr_count")
    resolved_count = issues[issues["status"] == "Done"].groupby("assignee_id").size().rename("issues_resolved")
    reviews_given = tables["code_reviews"].groupby("reviewer_id").size().rename("reviews_given")

    out = developers[["developer_id", "full_name", "team_id", "seniority"]].set_index("developer_id")
    out = out.join([commit_count, pr_count, resolved_count, reviews_given]).fillna(0).reset_index()

    out["workload_index"] = (out["commit_count"] * 1 + out["pr_count"] * 3 +
                              out["issues_resolved"] * 2)
    return out


def compute_productivity_score(tables, workload_df):
    """
    Engineering Productivity Score (0-100) — a BALANCED metric.

    Deliberately does NOT use raw commit count as a proxy for productivity.
    Combines four normalized (0-1) sub-scores, each min-max scaled across
    developers so no single raw unit dominates:

      delivery_component      (40%): issues_resolved + pr_count (shippable output)
      quality_component       (25%): inverse of (bugs authored that got reopened)
      collaboration_component (20%): reviews_given (helping the team, not just self)
      workload_balance        (15%): penalizes extreme overload (proxy for burnout risk /
                                       unsustainable pace), not just rewards raw volume
    """
    df = workload_df.copy()
    issues = tables["issues"]

    # quality: reopen involvement per developer (lower is better)
    bugs = issues[issues["issue_type"] == "Bug"]
    reopen_by_dev = bugs.groupby("assignee_id")["reopened"].mean().rename("reopen_rate")
    df = df.merge(reopen_by_dev, left_on="developer_id", right_index=True, how="left")
    df["reopen_rate"] = df["reopen_rate"].fillna(0)

    def minmax(s):
        rng = s.max() - s.min()
        return (s - s.min()) / rng if rng > 0 else s * 0

    delivery = minmax(df["issues_resolved"] + df["pr_count"])
    quality = 1 - minmax(df["reopen_rate"])
    collaboration = minmax(df["reviews_given"])

    # workload_balance: peaks at the median workload, decays for extreme over/under-load
    median_load = df["workload_index"].median()
    dist_from_median = (df["workload_index"] - median_load).abs()
    workload_balance = 1 - minmax(dist_from_median)

    df["engineering_productivity_score"] = (
        100 * (0.40 * delivery + 0.25 * quality + 0.20 * collaboration + 0.15 * workload_balance)
    ).round(1)

    return df.sort_values("engineering_productivity_score", ascending=False)


def main():
    tables = load_processed()

    team_kpis = compute_team_kpis(tables)
    project_health = compute_project_health(tables)
    workload = compute_developer_workload(tables)
    productivity = compute_productivity_score(tables, workload)

    team_kpis.to_csv(f"{PROCESSED_DIR}/kpi_team_summary.csv", index=False)
    project_health.to_csv(f"{PROCESSED_DIR}/kpi_project_health.csv", index=False)
    productivity.to_csv(f"{PROCESSED_DIR}/kpi_developer_productivity.csv", index=False)

    print("Team-level KPIs:\n", team_kpis[["team_name", "avg_sprint_completion_rate",
          "bug_reopen_rate_pct", "avg_pr_review_hours", "change_failure_rate_pct",
          "team_health_score"]].round(2).to_string(index=False))

    print("\nProject Health Scores (lowest = highest risk):\n",
          project_health[["project_name", "criticality", "project_health_score"]]
          .round(1).to_string(index=False))

    print("\nTop 10 developers by Engineering Productivity Score:\n",
          productivity[["full_name", "team_id", "seniority", "engineering_productivity_score"]]
          .head(10).to_string(index=False))

    print("\nKPI tables written to data/processed/: "
          "kpi_team_summary.csv, kpi_project_health.csv, kpi_developer_productivity.csv")


if __name__ == "__main__":
    main()
