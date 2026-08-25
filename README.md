# Software Engineering Productivity & Delivery Intelligence Platform

An end-to-end data analytics platform that analyzes software development lifecycle
(SDLC) data — sprints, issues, pull requests, code reviews, deployments, and releases —
to surface productivity patterns, engineering bottlenecks, quality risk, and release
delay probability. Built to demonstrate the full analyst workflow an engineering
organization would actually use to monitor delivery performance:

```
Raw Data → Python ETL → SQL Database → SQL Analytics → Python EDA/ML → Dashboard → Business Recommendations
```

---

## 1. Business Problem

Engineering leaders often can't answer basic delivery-health questions without manually
stitching together Jira, GitHub, and CI/CD dashboards: *Which teams are falling behind?
Is code review a bottleneck? Which releases are at risk of slipping, and why?* This
project builds a single analytics layer — from raw data to a risk-scored, ML-backed
dashboard — that answers those questions with evidence, not guesswork.

## 2. Objectives

- Model a realistic multi-table SDLC dataset (10 relational tables, ~20K+ records).
- Build a documented Python ETL pipeline that cleans and validates the data.
- Design a normalized SQL schema and write 25+ analytical queries (joins, CTEs, window
  functions, views) that answer real engineering-management questions.
- Define and compute a KPI framework spanning delivery, quality, and DevOps.
- Run EDA to find real (not invented) relationships between engineering metrics.
- Build a release-delay prediction model and an explainable project risk score.
- Ship a 5-page interactive dashboard and an automated weekly report.

## 3. Dataset

Because no public dataset combines Jira + GitHub + CI/CD at this granularity, this
project generates a **realistic synthetic dataset** (`src/generate_data.py`) modeled on
actual SDLC workflows — 8 teams, 60 developers, 12 projects, 120 sprints, and:

| Table | Rows | Key fields |
|---|---|---|
| teams | 8 | team_id, department |
| developers | 60 | seniority, role, team_id |
| projects | 12 | criticality, tech_stack |
| sprints | 120 | planned/completed story points, completion rate |
| issues | ~3,070 | type, priority, severity, cycle time, reopened, escaped_defect |
| commits | ~10,360 | lines added/deleted, churn |
| pull_requests | ~2,290 | size, review time, status |
| code_reviews | ~3,330 | review rounds, comments, approval |
| deployments | ~770 | environment, failure, rollback |
| releases | 60 | planned/actual date, delay days, status |

The generator deliberately injects **correlated, realistic signal** — teams with a
higher "risk profile" have measurably worse bug reopen rates, review times, and
deployment failure rates — so the downstream EDA/ML findings reflect genuine patterns
rather than noise. It also injects **realistic data-quality problems** (duplicate rows,
inconsistent status casing, an outlier resolution time, a broken-parser negative value,
missing review times) so the cleaning pipeline has real problems to solve.

## 4. Architecture / Workflow

```
src/generate_data.py     → data/raw/*.csv           (10 raw tables)
src/data_cleaning.py     → data/processed/*.csv      (cleaned, validated)
sql/build_database.py    → sql/engineering_analytics.db  (SQLite; schema.sql is
                                                            Postgres-compatible DDL)
sql/analytical_queries.sql → 25 queries + 1 view, all tested against the DB
src/feature_engineering.py → data/processed/kpi_*.csv (15-KPI framework)
src/analysis.py          → reports/figures/*.png     (10 EDA charts)
src/prediction.py        → release-delay model + release risk scores
src/automated_report.py  → reports/weekly_report_*.csv / .xlsx
dashboard/app.py         → 5-page interactive Plotly Dash app
```

## 5. Technologies Used

Python (pandas, NumPy) · SQL (SQLite, Postgres-compatible DDL) · Matplotlib/Seaborn/Plotly
· scikit-learn · Plotly Dash · openpyxl · pytest · Jupyter

## 6. Database Schema

Normalized (3NF) relational schema — 10 tables, foreign keys enforced, indexed on every
join column used by the analytical query workload. Full DDL in [`sql/schema.sql`](sql/schema.sql).

```
teams ─┬─< developers ─┬─< commits
       ├─< projects ───┼─< pull_requests ─< code_reviews
       │                └─< issues
       └─< sprints ─┬─< issues
                     ├─< commits
                     ├─< pull_requests
                     └─< deployments
projects ─< releases
```

## 7. Data Pipeline

`src/data_cleaning.py` handles, with every decision logged to
[`reports/data_cleaning_log.txt`](reports/data_cleaning_log.txt):

- **Duplicates** — exact-duplicate rows removed (simulated webhook double-fires).
- **Inconsistent text** — status values normalized (`'DONE  '` → `'Done'`).
- **Outliers** — extreme resolution times **winsorized** at the 99.5th percentile
  rather than dropped, preserving the row's reopened/escaped flags.
- **Invalid values** — a broken-parser negative `lines_added` sentinel imputed with
  the median rather than dropped.
- **Missing values** — left as `NULL` where appropriate (e.g. `severity` is legitimately
  null for non-Bug issues; open PRs legitimately have no `review_time_hours`), and
  explicitly *excluded* from averages rather than imputed, to avoid biasing KPIs.
- **Referential integrity** — validated after cleaning (all 6 foreign-key relationships
  checked; 0 orphaned rows in the shipped dataset).

## 8. KPI Framework

All 15 required KPIs are implemented in [`src/feature_engineering.py`](src/feature_engineering.py)
with formulas and business meaning documented inline. Highlights:

| KPI | Formula | Business meaning |
|---|---|---|
| Sprint Completion Rate | completed / planned story points | Delivery predictability |
| Bug Reopen Rate | reopened bugs / total bugs | Fix quality |
| Defect Density | bugs / total issues | Feature vs. defect-driven effort |
| PR Review Time | avg(review close − open), merged/closed only | Review-cycle bottleneck |
| Change Failure Rate (CFR) | failed deploys / total deploys | DORA DevOps metric |
| Project Health Score | 0.35×quality + 0.35×delivery + 0.30×devops (0–100) | Composite exec KPI |
| **Developer Workload Index** | commits×1 + PRs×3 + issues_resolved×2 | Multi-signal workload — **not** a raw commit count |
| **Engineering Productivity Score** | 40% delivery + 25% quality + 20% collaboration + 15% workload-balance (all min-max normalized, 0–100) | Balanced productivity — explicitly penalizes rewarding raw commit volume |

The productivity score is deliberately **not** commit count: a developer who ships
fewer, well-reviewed, non-reopened PRs and helps review others' code scores higher
than one who produces high commit volume alone.

## 9. SQL Analysis

[`sql/analytical_queries.sql`](sql/analytical_queries.sql) contains **25 queries** (all
tested error-free against the shipped SQLite DB — see `sql/run_queries.py`), covering:
GROUP BY/HAVING, CTEs, correlated & scalar subqueries, CASE-based bucketing, window
functions (`ROW_NUMBER`, `PERCENT_RANK`, running totals), and a reusable analytical
`VIEW` (`team_performance_summary`). Sample questions answered:

- Which teams have the highest sprint completion rate, and are they improving or declining?
- Which projects have the highest defect / escaped-defect rate?
- What is the average PR review time by team, and does PR size predict it?
- Which teams have a bug reopen rate more than 1 standard deviation above the org mean?
- What is the change failure rate (DORA) by team?
- Which projects are statistically most likely to miss release targets?

## 10. Exploratory Data Analysis

Full walkthrough: [`notebooks/01_exploratory_data_analysis.ipynb`](notebooks/01_exploratory_data_analysis.ipynb)
(executed, with all outputs saved). Static charts also in `reports/figures/`.

**Key findings (from actual results, not invented):**

- **Delivery predictability and review speed are tightly linked.** Sprint completion
  rate correlates at **r ≈ −0.98** with average PR review time and **r ≈ −0.99** with
  issue cycle time at the project level — teams that review code fast also ship
  predictably; this is the same underlying capacity constraint showing up in three
  metrics, not three separate problems.
- **PR size predicts review time** — larger PRs take measurably longer to review,
  a concrete, actionable lever (encourage smaller PRs) rather than an abstract one.
- **Change failure rate correlates with review time (r ≈ 0.89)** — rushed, slowly
  (or under-)reviewed changes fail more often once deployed.
- **Risk isn't spread evenly.** A small number of teams/projects account for most of
  the reopen-rate, review-time, and change-failure risk in the org — which is exactly
  what the Risk Intelligence dashboard page and the ML risk score are built to surface.

## 11. Advanced Analytics

### Feature 1 — Release Delay Prediction (`src/prediction.py`)

Predicts whether a release will be delayed using only **pre-release** signals (open
bugs, critical bugs, sprint completion %, avg PR review time, pending PRs, developer
workload proxy, recent deployment frequency, historical project delay rate) — features
are built with a strict time cutoff at the preceding sprint's end date, so nothing
leaks the outcome.

Three models compared on a held-out test set (25%), using Accuracy/Precision/Recall/F1/ROC-AUC
since delayed releases are the minority class and accuracy alone would be misleading:

| Model | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|---|
| **Random Forest** | 0.80 | 0.70 | **1.00** | **0.82** | 0.79 |
| Gradient Boosting | 0.73 | 0.71 | 0.71 | 0.71 | 0.79 |
| Logistic Regression | 0.60 | 0.57 | 0.57 | 0.57 | 0.57 |

Random Forest wins on F1 and, notably, catches every delayed release in the test set
(recall = 1.0) — the more costly error for an early-warning system is a *missed* delay,
not a false alarm. Top predictive features: **developer workload proxy** (0.21),
**open bugs** (0.17), and **sprint completion %** (0.15) — consistent with the EDA
finding that delivery-capacity strain, not any single metric, drives delay risk.

*(Note: only 59 non-cancelled releases exist in this synthetic dataset — a real
deployment would retrain on a much larger release history; the pipeline itself is
production-shaped and would scale directly.)*

### Feature 2 — Engineering Bottleneck / Release Risk Score

```
Release Risk Score = Delivery Risk + Quality Risk + Review Bottleneck + Workload Risk
```

Each component is min-max scaled to 0–100 across projects (100 = riskiest) from the
same KPI tables, then averaged into one transparent, explainable composite — chosen
over a black-box anomaly-detection model because a metric that drives engineering
management decisions needs to be defensible in a 1:1, not just accurate.

Projects flagged **High Risk** (score ≥ 65) in the current run: **Fraud-Detection (91.2)**,
**Data-Pipeline (87.3)**, **Inventory-Service (74.6)** — all three trace back to the same
underlying team, correctly identified by the model without being told which team it was.

## 12. Dashboard

[`dashboard/app.py`](dashboard/app.py) — a 5-page Plotly Dash app with a live cross-filter
bar (Project / Team / Priority / Severity):

1. **Executive Overview** — KPI cards, project health ranking, completion-rate trend
2. **Engineering Productivity** — team velocity, PR review time, cycle time by priority
3. **Software Quality** — bugs by severity/project, reopen rate, defect trend
4. **Delivery & DevOps** — deployment frequency, release outcomes, CFR, delay by project
5. **Risk Intelligence** — risk score ranking, risk-component breakdown, at-risk table

Run with:
```bash
python dashboard/app.py
# open http://127.0.0.1:8050
```

## 13. Automated Reporting

`src/automated_report.py` generates a weekly report (KPI summary, at-risk projects,
bottleneck teams, lowest-quality projects, and driver-specific recommended actions)
and exports both a CSV and a multi-sheet Excel workbook to `reports/`. Designed to run
on a schedule (cron/Airflow) against the latest `data/processed/` snapshot.

## 14. Business & Engineering Insights (sample)

> **What happened?** Teams with the highest average PR review time (Platform-Infra,
> ~24h) also have the highest change failure rate (~15%) and the lowest sprint
> completion rate (~58%) in the org.
> **Why?** Review capacity appears to be a genuine constraint, not a coincidence — the
> project-level correlation between review time and completion rate is r ≈ −0.98.
> **Impact:** Slow review is very likely contributing to (not just coinciding with)
> missed sprint commitments and production failures on that team's projects.
> **Recommended action:** Add reviewer capacity or introduce review-priority triage for
> Platform-Infra's projects before addressing symptoms elsewhere in the pipeline.

## 15. How to Run This Project

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate the synthetic raw dataset
python src/generate_data.py

# 3. Clean and validate the data
python src/data_cleaning.py

# 4. Build the SQL database and run the analytical queries
python sql/build_database.py
python sql/run_queries.py

# 5. Compute the KPI framework
python src/feature_engineering.py

# 6. Run EDA (script or notebook)
python src/analysis.py
# or: jupyter notebook notebooks/01_exploratory_data_analysis.ipynb

# 7. Train the ML model and compute risk scores
python src/prediction.py

# 8. Generate the automated weekly report
python src/automated_report.py

# 9. Launch the dashboard
python dashboard/app.py   # http://127.0.0.1:8050

# 10. Run tests
pytest tests/
```

### Running on PostgreSQL/MySQL instead of SQLite

`sql/schema.sql` and `sql/data_loading.sql` are written in Postgres-compatible DDL/COPY
syntax and can be run directly against a Postgres instance. Swap
`sql/build_database.py`'s `sqlite3.connect(...)` for `psycopg2.connect(...)` (or a
SQLAlchemy Postgres engine) — the pandas `to_sql` loading logic is unchanged.

## 16. Machine Learning Component

See Section 11 above. Model artifacts (comparison table, feature importances) are
written to `reports/model_comparison.csv` and `reports/feature_importance.csv` on
every run of `src/prediction.py`.

## 17. Future Improvements

- Retrain the release-delay model on a longer release history as more data accumulates
  (currently constrained by the synthetic dataset's ~60 releases).
- Add a time-series forecasting component (e.g. Prophet) for sprint velocity forecasting.
- Wire the dashboard's Sprint/Date filters (currently Project/Team/Priority/Severity are
  live) and add a Developer-level drill-down page.
- Move the SQLite build to a hosted Postgres instance and containerize the dashboard
  (Docker) for a one-command deploy.
- Add CI (GitHub Actions) to run `pytest` and the SQL query smoke test on every push.

## 18. Project Structure

```
software-engineering-analytics/
├── data/
│   ├── raw/                  # generated synthetic source data
│   └── processed/            # cleaned tables + KPI/risk/feature outputs
├── notebooks/
│   └── 01_exploratory_data_analysis.ipynb
├── src/
│   ├── generate_data.py
│   ├── data_cleaning.py
│   ├── feature_engineering.py
│   ├── analysis.py
│   ├── prediction.py
│   └── automated_report.py
├── sql/
│   ├── schema.sql
│   ├── data_loading.sql
│   ├── analytical_queries.sql
│   ├── build_database.py
│   ├── run_queries.py
│   └── engineering_analytics.db
├── dashboard/
│   └── app.py
├── reports/
│   ├── figures/               # EDA charts
│   ├── data_cleaning_log.txt
│   ├── model_comparison.csv
│   ├── feature_importance.csv
│   └── weekly_report_*.csv / .xlsx
├── tests/
│   └── test_pipeline.py
├── requirements.txt
├── README.md
└── .gitignore
```

---

See [`RESUME_AND_INTERVIEW_PREP.md`](RESUME_AND_INTERVIEW_PREP.md) for a resume-ready
project description and interview Q&A based on this project.
