"""
automated_report.py
====================
Generates a weekly engineering-analytics report: KPI summary, at-risk
projects, bottlenecks, quality issues, and recommended actions — exported
to CSV and Excel (multi-sheet). Designed to be run on a schedule (cron /
Airflow) against the latest data/processed/ snapshot.
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime

PROCESSED_DIR = "data/processed"
REPORTS_DIR = "reports"


def load_kpis():
    team_kpis = pd.read_csv(f"{PROCESSED_DIR}/kpi_team_summary.csv")
    project_health = pd.read_csv(f"{PROCESSED_DIR}/kpi_project_health.csv")
    risk = pd.read_csv(f"{PROCESSED_DIR}/release_risk_scores.csv")
    productivity = pd.read_csv(f"{PROCESSED_DIR}/kpi_developer_productivity.csv")
    return team_kpis, project_health, risk, productivity


def generate_recommendations(risk_df, team_kpis):
    recs = []
    for _, row in risk_df[risk_df["risk_tier"] == "High Risk"].iterrows():
        drivers = []
        if row["delivery_risk"] > 60:
            drivers.append("sprint completion rate is low")
        if row["quality_risk"] > 60:
            drivers.append("defect/escape rate is elevated")
        if row["review_bottleneck_risk"] > 60:
            drivers.append("PR review time is a bottleneck")
        if row["workload_risk"] > 60:
            drivers.append("team workload is disproportionately high")
        driver_text = "; ".join(drivers) if drivers else "multiple risk factors trending negative"
        action = "Recommend immediate leadership review: reallocate reviewer capacity, " \
                 "triage critical-bug backlog, and reassess sprint scope." \
                 if row["release_risk_score"] > 80 else \
                 "Recommend monitoring closely and addressing the top driver this sprint."
        recs.append({
            "project_name": row["project_name"],
            "risk_score": row["release_risk_score"],
            "primary_drivers": driver_text,
            "recommended_action": action,
        })
    return pd.DataFrame(recs)


def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    team_kpis, project_health, risk, productivity = load_kpis()

    report_date = datetime.now().strftime("%Y-%m-%d")

    # --- KPI summary (org-wide rollup) ---
    kpi_summary = pd.DataFrame([{
        "report_date": report_date,
        "avg_sprint_completion_rate_pct": round(team_kpis["avg_sprint_completion_rate"].mean() * 100, 1),
        "avg_bug_reopen_rate_pct": round(team_kpis["bug_reopen_rate_pct"].mean(), 1),
        "avg_pr_review_hours": round(team_kpis["avg_pr_review_hours"].mean(), 1),
        "avg_change_failure_rate_pct": round(team_kpis["change_failure_rate_pct"].mean(), 1),
        "avg_project_health_score": round(project_health["project_health_score"].mean(), 1),
        "at_risk_project_count": int((risk["risk_tier"] == "High Risk").sum()),
        "total_projects": len(risk),
    }])

    at_risk = risk[risk["risk_tier"].isin(["High Risk", "Medium Risk"])].sort_values(
        "release_risk_score", ascending=False)

    quality_issues = project_health.sort_values("quality_score").head(5)[
        ["project_name", "criticality", "quality_score"]]

    bottlenecks = team_kpis.sort_values("avg_pr_review_hours", ascending=False).head(5)[
        ["team_name", "avg_pr_review_hours", "bug_reopen_rate_pct", "change_failure_rate_pct"]]

    recommendations = generate_recommendations(risk, team_kpis)

    top_performers = productivity.sort_values("engineering_productivity_score", ascending=False).head(10)[
        ["full_name", "team_id", "seniority", "engineering_productivity_score"]]

    # --- Console summary ---
    print("=" * 70)
    print(f"WEEKLY ENGINEERING ANALYTICS REPORT — {report_date}")
    print("=" * 70)
    print("\nORG-WIDE KPI SUMMARY")
    print(kpi_summary.T.to_string(header=False))
    print(f"\nAT-RISK PROJECTS ({len(at_risk)}):")
    print(at_risk[["project_name", "risk_tier", "release_risk_score"]].to_string(index=False))
    print("\nTOP BOTTLENECK TEAMS (by PR review time):")
    print(bottlenecks.to_string(index=False))
    print("\nLOWEST QUALITY-SCORE PROJECTS:")
    print(quality_issues.to_string(index=False))
    print("\nRECOMMENDED ACTIONS:")
    print(recommendations.to_string(index=False) if len(recommendations) else "  No high-risk projects this period.")

    # --- Export CSV ---
    csv_path = f"{REPORTS_DIR}/weekly_report_{report_date}.csv"
    at_risk.to_csv(csv_path, index=False)

    # --- Export Excel (multi-sheet) ---
    xlsx_path = f"{REPORTS_DIR}/weekly_engineering_report_{report_date}.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        kpi_summary.T.rename(columns={0: "value"}).to_excel(writer, sheet_name="KPI Summary")
        at_risk.to_excel(writer, sheet_name="At-Risk Projects", index=False)
        bottlenecks.to_excel(writer, sheet_name="Bottlenecks", index=False)
        quality_issues.to_excel(writer, sheet_name="Quality Issues", index=False)
        recommendations.to_excel(writer, sheet_name="Recommendations", index=False)
        top_performers.to_excel(writer, sheet_name="Top Performers", index=False)
        team_kpis.to_excel(writer, sheet_name="Team KPIs (full)", index=False)
        project_health.to_excel(writer, sheet_name="Project Health (full)", index=False)

    print(f"\nReport exported to:\n  {csv_path}\n  {xlsx_path}")


if __name__ == "__main__":
    main()
