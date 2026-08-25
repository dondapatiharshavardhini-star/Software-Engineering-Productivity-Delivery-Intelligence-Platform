"""
analysis.py
===========
Exploratory Data Analysis — investigates productivity trends, sprint
performance, bug trends, PR bottlenecks, deployment patterns, release
delays, team differences, workload distribution, correlations, and
time-based patterns. Saves charts as PNGs to reports/figures/.
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import os

sns.set_theme(style="whitegrid", palette="deep")
PROCESSED_DIR = "data/processed"
FIG_DIR = "reports/figures"


def load():
    t = {}
    for name in ["teams", "developers", "projects", "sprints", "issues",
                 "commits", "pull_requests", "code_reviews", "deployments", "releases"]:
        t[name] = pd.read_csv(f"{PROCESSED_DIR}/{name}.csv")
    for col_df, cols in [
        ("sprints", ["sprint_start_date", "sprint_end_date"]),
        ("issues", ["created_date", "resolved_date"]),
        ("pull_requests", ["opened_date", "closed_date"]),
        ("deployments", ["deployment_timestamp"]),
        ("releases", ["planned_release_date", "actual_release_date"]),
    ]:
        for c in cols:
            t[col_df][c] = pd.to_datetime(t[col_df][c], errors="coerce")
    return t


def save(fig, name):
    os.makedirs(FIG_DIR, exist_ok=True)
    fig.tight_layout()
    fig.savefig(f"{FIG_DIR}/{name}.png", dpi=130)
    plt.close(fig)
    print(f"  saved {FIG_DIR}/{name}.png")


def eda_sprint_performance(t):
    print("\n[EDA] Sprint completion rate by team")
    df = t["sprints"].merge(t["teams"], on="team_id")
    fig, ax = plt.subplots(figsize=(9, 5))
    order = df.groupby("team_name")["sprint_completion_rate"].mean().sort_values(ascending=False).index
    sns.boxplot(data=df, x="team_name", y="sprint_completion_rate", order=order, ax=ax)
    ax.set_title("Sprint Completion Rate Distribution by Team")
    ax.set_ylabel("Completion Rate")
    ax.set_xlabel("")
    plt.xticks(rotation=30, ha="right")
    save(fig, "01_sprint_completion_by_team")

    print("[EDA] Sprint velocity trend over time (org-wide)")
    trend = df.sort_values("sprint_start_date").groupby("sprint_start_date")["completed_story_points"].mean()
    fig, ax = plt.subplots(figsize=(10, 4.5))
    trend.rolling(5, min_periods=1).mean().plot(ax=ax)
    ax.set_title("Org-wide Avg Sprint Velocity (5-sprint rolling mean)")
    ax.set_ylabel("Completed Story Points")
    save(fig, "02_velocity_trend")


def eda_bug_trends(t):
    print("\n[EDA] Bug volume and severity mix over time")
    bugs = t["issues"][t["issues"]["issue_type"] == "Bug"].copy()
    bugs["month"] = bugs["created_date"].dt.to_period("M").astype(str)
    monthly = bugs.groupby(["month", "severity"]).size().unstack(fill_value=0)
    fig, ax = plt.subplots(figsize=(10, 5))
    monthly.plot(kind="bar", stacked=True, ax=ax, colormap="RdYlGn_r")
    ax.set_title("Monthly Bug Volume by Severity")
    ax.set_ylabel("Bug Count")
    plt.xticks(rotation=45, ha="right")
    save(fig, "03_bug_volume_by_severity")

    print("[EDA] Bug reopen rate by team")
    reopen = bugs.merge(t["teams"], on="team_id").groupby("team_name")["reopened"].mean().sort_values(ascending=False) * 100
    fig, ax = plt.subplots(figsize=(9, 5))
    reopen.plot(kind="bar", ax=ax, color=sns.color_palette("rocket", len(reopen)))
    ax.set_title("Bug Reopen Rate by Team (%)")
    ax.set_ylabel("Reopen Rate (%)")
    plt.xticks(rotation=30, ha="right")
    save(fig, "04_reopen_rate_by_team")


def eda_pr_bottlenecks(t):
    print("\n[EDA] PR review time vs. PR size")
    pr = t["pull_requests"].dropna(subset=["review_time_hours"])
    fig, ax = plt.subplots(figsize=(8, 5.5))
    sns.regplot(data=pr.sample(min(1000, len(pr)), random_state=1), x="pr_size_lines",
                y="review_time_hours", scatter_kws={"alpha": 0.3, "s": 15}, ax=ax,
                line_kws={"color": "red"})
    ax.set_title("PR Size vs. Review Time")
    ax.set_xlabel("PR Size (lines changed)")
    ax.set_ylabel("Review Time (hours)")
    save(fig, "05_pr_size_vs_review_time")

    print("[EDA] Avg PR review time by team")
    prt = pr.merge(t["sprints"][["sprint_id", "team_id"]], on="sprint_id").merge(t["teams"], on="team_id")
    avg_rt = prt.groupby("team_name")["review_time_hours"].mean().sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(9, 5))
    avg_rt.plot(kind="barh", ax=ax, color=sns.color_palette("mako", len(avg_rt)))
    ax.set_title("Average PR Review Time by Team")
    ax.set_xlabel("Hours")
    save(fig, "06_avg_review_time_by_team")


def eda_deployment_patterns(t):
    print("\n[EDA] Deployment frequency and failure rate over time")
    dep = t["deployments"].copy()
    dep["month"] = dep["deployment_timestamp"].dt.to_period("M").astype(str)
    monthly = dep.groupby("month").agg(deploys=("deployment_id", "count"),
                                        failure_rate=("is_failure", "mean"))
    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.bar(monthly.index, monthly["deploys"], color="steelblue", alpha=0.7, label="Deployments")
    ax1.set_ylabel("Deployment Count", color="steelblue")
    ax2 = ax1.twinx()
    ax2.plot(monthly.index, monthly["failure_rate"] * 100, color="crimson", marker="o", label="Failure Rate")
    ax2.set_ylabel("Change Failure Rate (%)", color="crimson")
    ax1.set_title("Monthly Deployment Volume vs. Change Failure Rate")
    plt.xticks(rotation=45, ha="right")
    save(fig, "07_deployment_volume_vs_failure_rate")


def eda_release_delays(t):
    print("\n[EDA] Release delay distribution by project criticality")
    rel = t["releases"].merge(t["projects"][["project_id", "criticality"]], on="project_id")
    rel_valid = rel[rel["status"] != "Cancelled"]
    fig, ax = plt.subplots(figsize=(8, 5.5))
    sns.violinplot(data=rel_valid, x="criticality", y="release_delay_days",
                    order=["Low", "Medium", "High"], ax=ax)
    ax.set_title("Release Delay Distribution by Project Criticality")
    ax.set_ylabel("Delay (days)")
    save(fig, "08_release_delay_by_criticality")


def eda_workload_distribution(t):
    print("\n[EDA] Developer workload distribution (issues assigned)")
    load_dist = t["issues"].groupby("assignee_id").size()
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.histplot(load_dist, bins=25, kde=True, ax=ax, color="teal")
    ax.set_title("Distribution of Issues Assigned per Developer")
    ax.set_xlabel("Issues Assigned")
    save(fig, "09_developer_workload_distribution")


def eda_correlations(t):
    print("\n[EDA] Correlation matrix of key engineering metrics (project-level)")
    sprints = t["sprints"]
    issues = t["issues"]
    prs = t["pull_requests"]
    deps = t["deployments"]
    releases = t["releases"]

    proj_metrics = pd.DataFrame({"project_id": t["projects"]["project_id"]})

    completion = sprints.groupby("project_id")["sprint_completion_rate"].mean().rename("completion_rate")
    cycle = issues.dropna(subset=["resolved_date"]).groupby("project_id")["cycle_time_days"].mean().rename("cycle_time")
    bug_rate = (issues[issues["issue_type"] == "Bug"].groupby("project_id").size() /
                issues.groupby("project_id").size()).rename("defect_density")
    review_time = prs.dropna(subset=["review_time_hours"]).groupby("project_id")["review_time_hours"].mean().rename("review_time")
    deploy_freq = deps.groupby("project_id").size().rename("deploy_count")
    cfr = deps.groupby("project_id")["is_failure"].mean().rename("change_failure_rate")
    delay = releases[releases["status"] != "Cancelled"].groupby("project_id")["release_delay_days"].mean().rename("avg_release_delay")

    proj_metrics = proj_metrics.set_index("project_id").join(
        [completion, cycle, bug_rate, review_time, deploy_freq, cfr, delay])

    fig, ax = plt.subplots(figsize=(9, 7))
    sns.heatmap(proj_metrics.corr(), annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=ax)
    ax.set_title("Correlation Matrix — Project-level Engineering Metrics")
    save(fig, "10_correlation_matrix")

    return proj_metrics


def main():
    os.makedirs(FIG_DIR, exist_ok=True)
    os.makedirs("reports", exist_ok=True)
    t = load()

    eda_sprint_performance(t)
    eda_bug_trends(t)
    eda_pr_bottlenecks(t)
    eda_deployment_patterns(t)
    eda_release_delays(t)
    eda_workload_distribution(t)
    proj_metrics = eda_correlations(t)

    proj_metrics.to_csv(f"{PROCESSED_DIR}/project_level_metrics.csv")
    print(f"\nProject-level metrics table written to {PROCESSED_DIR}/project_level_metrics.csv")
    print("\nAll EDA figures saved to reports/figures/")

    # Print the strongest correlations as a quick "what did we learn" summary
    corr = proj_metrics.corr()
    print("\nNotable correlations (|r| > 0.4):")
    seen = set()
    for c1 in corr.columns:
        for c2 in corr.columns:
            if c1 != c2 and abs(corr.loc[c1, c2]) > 0.4 and (c2, c1) not in seen:
                print(f"  {c1} <-> {c2}: r = {corr.loc[c1, c2]:.2f}")
                seen.add((c1, c2))


if __name__ == "__main__":
    main()
