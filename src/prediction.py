"""
prediction.py
==============
Advanced Analytics — two features required by the project spec:

Feature 1: Release Delay Prediction (binary classification)
    Predicts whether a release will be delayed, using pre-release signals
    only (nothing that "leaks" the outcome), so the model reflects what you'd
    actually know BEFORE a release ships. Compares Logistic Regression,
    Random Forest, and Gradient Boosting; reports Accuracy, Precision,
    Recall, F1, and ROC-AUC — accuracy alone is misleading here since
    delayed releases are the minority class.

Feature 2: Engineering Bottleneck / Release Risk Detection
    Release Risk Score = Delivery Risk + Quality Risk + Review Bottleneck + Workload Risk
    Each sub-score is 0-100 (100 = highest risk), computed per project from
    the same KPI tables built in feature_engineering.py, then min-max scaled
    and averaged into a single composite so no single raw unit dominates.
"""

import pandas as pd
import numpy as np
import os
import json

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                              f1_score, roc_auc_score, confusion_matrix, classification_report)

PROCESSED_DIR = "data/processed"
REPORTS_DIR = "reports"


def load():
    t = {}
    for name in ["teams", "developers", "projects", "sprints", "issues",
                 "commits", "pull_requests", "code_reviews", "deployments", "releases"]:
        t[name] = pd.read_csv(f"{PROCESSED_DIR}/{name}.csv")
    t["sprints"]["sprint_start_date"] = pd.to_datetime(t["sprints"]["sprint_start_date"])
    t["issues"]["created_date"] = pd.to_datetime(t["issues"]["created_date"])
    t["releases"]["planned_release_date"] = pd.to_datetime(t["releases"]["planned_release_date"])
    return t


# ---------------------------------------------------------------------------
# Feature 1: Release Delay Prediction
# ---------------------------------------------------------------------------

def build_release_features(t):
    """
    For every release, build features using ONLY data available up to (and
    including) the sprint that preceded the release — i.e. no future leakage.
    """
    releases = t["releases"][t["releases"]["status"] != "Cancelled"].copy()
    sprints = t["sprints"]
    issues = t["issues"]
    prs = t["pull_requests"]
    deps = t["deployments"]

    rows = []
    for _, rel in releases.iterrows():
        sprint = sprints[sprints["sprint_id"] == rel["sprint_id"]]
        if sprint.empty:
            continue
        sprint = sprint.iloc[0]
        cutoff = pd.Timestamp(sprint["sprint_end_date"])
        project_id = rel["project_id"]

        # Issues open (unresolved) as of the cutoff, for this project
        proj_issues = issues[(issues["project_id"] == project_id) & (issues["created_date"] <= cutoff)]
        open_bugs = proj_issues[(proj_issues["issue_type"] == "Bug") &
                                 ((proj_issues["resolved_date"].isna()) |
                                  (pd.to_datetime(proj_issues["resolved_date"], errors="coerce") > cutoff))]
        critical_bugs = open_bugs[open_bugs["priority"].isin(["Critical", "High"])]

        # PRs pending (not merged/closed) as of cutoff
        proj_prs = prs[(prs["project_id"] == project_id) & (prs["opened_date"] <= cutoff.isoformat())] \
            if prs["opened_date"].dtype == object else prs[prs["project_id"] == project_id]
        pending_prs = proj_prs[proj_prs["status"] == "Open"]
        avg_review_time = proj_prs["review_time_hours"].mean()

        # Recent deployment frequency (last 14 days before cutoff)
        proj_deps = deps[deps["project_id"] == project_id].copy()
        proj_deps["deployment_timestamp"] = pd.to_datetime(proj_deps["deployment_timestamp"])
        recent_deploys = proj_deps[(proj_deps["deployment_timestamp"] <= cutoff) &
                                    (proj_deps["deployment_timestamp"] > cutoff - pd.Timedelta(days=14))]

        # Historical project delay rate (releases for this project prior to this one)
        proj_hist = releases[(releases["project_id"] == project_id) &
                              (releases["planned_release_date"] < rel["planned_release_date"])]
        hist_delay_rate = proj_hist["is_delayed"].mean() if len(proj_hist) > 0 else 0.3  # org prior

        rows.append({
            "release_id": rel["release_id"],
            "project_id": project_id,
            "open_bugs": len(open_bugs),
            "critical_bugs": len(critical_bugs),
            "sprint_completion_pct": sprint["sprint_completion_rate"] * 100,
            "avg_pr_review_time": avg_review_time if pd.notna(avg_review_time) else 0,
            "pending_prs": len(pending_prs),
            "developer_workload_proxy": len(proj_issues) / max(1, t["developers"]
                                             [t["developers"]["team_id"] ==
                                              t["projects"].set_index("project_id").loc[project_id, "team_id"]].shape[0]),
            "recent_deployment_frequency": len(recent_deploys),
            "historical_delay_rate": hist_delay_rate,
            "is_delayed": rel["is_delayed"],
        })

    return pd.DataFrame(rows)


def train_release_delay_models(features_df):
    feature_cols = ["open_bugs", "critical_bugs", "sprint_completion_pct",
                     "avg_pr_review_time", "pending_prs", "developer_workload_proxy",
                     "recent_deployment_frequency", "historical_delay_rate"]

    X = features_df[feature_cols].fillna(0)
    y = features_df["is_delayed"].astype(int)

    print(f"\nDataset for release-delay prediction: {len(X)} releases, "
          f"{y.mean()*100:.1f}% delayed (positive class)")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y if y.nunique() > 1 else None)

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    models = {
        "Logistic Regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
        "Random Forest": RandomForestClassifier(n_estimators=200, max_depth=5,
                                                  class_weight="balanced", random_state=42),
        "Gradient Boosting": GradientBoostingClassifier(n_estimators=150, max_depth=3, random_state=42),
    }

    results = []
    fitted = {}
    for name, model in models.items():
        Xtr = X_train_s if name == "Logistic Regression" else X_train
        Xte = X_test_s if name == "Logistic Regression" else X_test
        model.fit(Xtr, y_train)
        preds = model.predict(Xte)
        probs = model.predict_proba(Xte)[:, 1] if hasattr(model, "predict_proba") else preds

        metrics = {
            "model": name,
            "accuracy": round(accuracy_score(y_test, preds), 3),
            "precision": round(precision_score(y_test, preds, zero_division=0), 3),
            "recall": round(recall_score(y_test, preds, zero_division=0), 3),
            "f1_score": round(f1_score(y_test, preds, zero_division=0), 3),
            "roc_auc": round(roc_auc_score(y_test, probs), 3) if y_test.nunique() > 1 else None,
        }
        results.append(metrics)
        fitted[name] = model
        print(f"\n{name}:")
        for k, v in metrics.items():
            if k != "model":
                print(f"  {k}: {v}")

    results_df = pd.DataFrame(results).sort_values("f1_score", ascending=False)
    best_model_name = results_df.iloc[0]["model"]
    print(f"\nBest model by F1: {best_model_name}")

    # Feature importance from the best tree-based model (or coefficients for LR)
    best_model = fitted[best_model_name]
    if hasattr(best_model, "feature_importances_"):
        importance = pd.Series(best_model.feature_importances_, index=feature_cols).sort_values(ascending=False)
    elif hasattr(best_model, "coef_"):
        importance = pd.Series(np.abs(best_model.coef_[0]), index=feature_cols).sort_values(ascending=False)
    else:
        importance = None

    return results_df, importance, best_model_name


# ---------------------------------------------------------------------------
# Feature 2: Engineering Bottleneck / Release Risk Score
# ---------------------------------------------------------------------------

def compute_risk_scores(t):
    """
    Release Risk Score = Delivery Risk + Quality Risk + Review Bottleneck + Workload Risk
    Each component is min-max scaled to 0-100 across projects (100 = riskiest),
    then averaged (equal weight) into the composite. This is a transparent,
    explainable alternative to a black-box anomaly-detection score, which
    matters for a metric that will drive engineering-management decisions.
    """
    sprints, issues, prs, deps, releases, projects = (
        t["sprints"], t["issues"], t["pull_requests"], t["deployments"], t["releases"], t["projects"])

    def minmax_100(s):
        rng = s.max() - s.min()
        return ((s - s.min()) / rng * 100) if rng > 0 else s * 0

    # Delivery Risk: inverse of sprint completion rate
    delivery = 100 - sprints.groupby("project_id")["sprint_completion_rate"].mean() * 100
    delivery_risk = minmax_100(delivery).rename("delivery_risk")

    # Quality Risk: escaped defect rate + bug reopen rate (blended)
    bugs = issues[issues["issue_type"] == "Bug"]
    escaped = bugs.groupby("project_id")["escaped_defect"].mean() * 100
    reopen = bugs.groupby("project_id")["reopened"].mean() * 100
    quality_raw = (escaped.fillna(0) + reopen.fillna(0)) / 2
    quality_risk = minmax_100(quality_raw).rename("quality_risk")

    # Review Bottleneck: avg PR review time + pending (open) PR count
    review_time = prs.dropna(subset=["review_time_hours"]).groupby("project_id")["review_time_hours"].mean()
    pending = prs[prs["status"] == "Open"].groupby("project_id").size()
    review_raw = minmax_100(review_time.fillna(0)) * 0.7 + minmax_100(pending.reindex(review_time.index).fillna(0)) * 0.3
    review_risk = review_raw.rename("review_bottleneck_risk")

    # Workload Risk: issues per developer on the project's team, relative to org
    proj_team = projects.set_index("project_id")["team_id"]
    dev_counts = t["developers"].groupby("team_id").size()
    issues_per_proj = issues.groupby("project_id").size()
    team_size = proj_team.map(dev_counts)
    workload_raw = issues_per_proj / team_size
    workload_risk = minmax_100(workload_raw).rename("workload_risk")

    risk = pd.concat([delivery_risk, quality_risk, review_risk, workload_risk], axis=1).fillna(0)
    risk["release_risk_score"] = risk.mean(axis=1).round(1)
    risk = risk.round(1).reset_index().rename(columns={"index": "project_id"})
    risk = risk.merge(projects[["project_id", "project_name", "criticality"]], on="project_id")

    def risk_tier(score):
        if score >= 65:
            return "High Risk"
        elif score >= 40:
            return "Medium Risk"
        return "Low Risk"

    risk["risk_tier"] = risk["release_risk_score"].apply(risk_tier)
    return risk.sort_values("release_risk_score", ascending=False)


def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    t = load()

    print("=" * 70)
    print("FEATURE 1: RELEASE DELAY PREDICTION")
    print("=" * 70)
    features_df = build_release_features(t)
    features_df.to_csv(f"{PROCESSED_DIR}/release_delay_features.csv", index=False)
    results_df, importance, best_model = train_release_delay_models(features_df)
    results_df.to_csv(f"{REPORTS_DIR}/model_comparison.csv", index=False)

    if importance is not None:
        print(f"\nFeature importance ({best_model}):")
        print(importance.round(3).to_string())
        importance.round(3).to_csv(f"{REPORTS_DIR}/feature_importance.csv")

    print("\n" + "=" * 70)
    print("FEATURE 2: ENGINEERING BOTTLENECK / RELEASE RISK DETECTION")
    print("=" * 70)
    risk_df = compute_risk_scores(t)
    risk_df.to_csv(f"{PROCESSED_DIR}/release_risk_scores.csv", index=False)
    print(risk_df[["project_name", "criticality", "delivery_risk", "quality_risk",
                    "review_bottleneck_risk", "workload_risk", "release_risk_score",
                    "risk_tier"]].to_string(index=False))

    print(f"\nAt-risk projects (High Risk tier): "
          f"{', '.join(risk_df[risk_df['risk_tier']=='High Risk']['project_name'].tolist()) or 'None'}")

    print("\nOutputs written: data/processed/release_delay_features.csv, "
          "data/processed/release_risk_scores.csv, reports/model_comparison.csv, "
          "reports/feature_importance.csv")


if __name__ == "__main__":
    main()
