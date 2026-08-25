"""
dashboard/app.py
=================
Interactive Plotly Dash dashboard for the Software Engineering Productivity
& Delivery Intelligence Platform. Five pages: Executive Overview, Engineering
Productivity, Software Quality, Delivery & DevOps, Risk Intelligence — each
with cross-filters for Project / Team / Developer / Sprint / Date / Priority
/ Severity.

Run with:  python dashboard/app.py
Then open: http://127.0.0.1:8050
"""

import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")


def load(name):
    return pd.read_csv(os.path.join(DATA_DIR, f"{name}.csv"))


teams = load("teams")
developers = load("developers")
projects = load("projects")
sprints = load("sprints")
issues = load("issues")
pull_requests = load("pull_requests")
deployments = load("deployments")
releases = load("releases")
kpi_team = load("kpi_team_summary")
kpi_project_health = load("kpi_project_health")
risk_scores = load("release_risk_scores")
productivity = load("kpi_developer_productivity")

issues["created_date"] = pd.to_datetime(issues["created_date"])
sprints["sprint_start_date"] = pd.to_datetime(sprints["sprint_start_date"])
deployments["deployment_timestamp"] = pd.to_datetime(deployments["deployment_timestamp"])

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY],
                 suppress_callback_exceptions=True)
app.title = "Engineering Delivery Intelligence Platform"

FILTER_BAR = dbc.Row([
    dbc.Col([
        html.Label("Project"),
        dcc.Dropdown(id="f-project",
                     options=[{"label": p, "value": p} for p in projects["project_name"]],
                     multi=True, placeholder="All projects"),
    ], width=3),
    dbc.Col([
        html.Label("Team"),
        dcc.Dropdown(id="f-team",
                     options=[{"label": t, "value": t} for t in teams["team_name"]],
                     multi=True, placeholder="All teams"),
    ], width=3),
    dbc.Col([
        html.Label("Priority"),
        dcc.Dropdown(id="f-priority",
                     options=[{"label": p, "value": p} for p in issues["priority"].dropna().unique()],
                     multi=True, placeholder="All priorities"),
    ], width=3),
    dbc.Col([
        html.Label("Severity"),
        dcc.Dropdown(id="f-severity",
                     options=[{"label": s, "value": s} for s in issues["severity"].dropna().unique()],
                     multi=True, placeholder="All severities"),
    ], width=3),
], className="mb-4 mt-2")

NAVBAR = dbc.NavbarSimple(
    children=[
        dbc.NavLink("Executive Overview", href="/", active="exact"),
        dbc.NavLink("Engineering Productivity", href="/productivity", active="exact"),
        dbc.NavLink("Software Quality", href="/quality", active="exact"),
        dbc.NavLink("Delivery & DevOps", href="/devops", active="exact"),
        dbc.NavLink("Risk Intelligence", href="/risk", active="exact"),
    ],
    brand="Engineering Delivery Intelligence Platform",
    color="dark", dark=True, className="mb-3",
)

app.layout = html.Div([
    dcc.Location(id="url"),
    NAVBAR,
    dbc.Container([FILTER_BAR, html.Div(id="page-content")], fluid=True),
])


def kpi_card(title, value, color="primary"):
    return dbc.Card(dbc.CardBody([
        html.H6(title, className="card-subtitle text-muted"),
        html.H3(value, className=f"text-{color}"),
    ]), className="shadow-sm")


def apply_filters(proj_names=None, team_names=None, priorities=None, severities=None):
    """
    Returns a filtered snapshot of every shared dataframe based on the
    global filter bar. Filtering project/team narrows via project_id/team_id
    joins; priority/severity narrow the issues table (and anything derived
    from it) directly.
    """
    proj_ids = projects[projects["project_name"].isin(proj_names)]["project_id"] if proj_names else projects["project_id"]
    team_ids = teams[teams["team_name"].isin(team_names)]["team_id"] if team_names else teams["team_id"]

    f_projects = projects[projects["project_id"].isin(proj_ids) & projects["team_id"].isin(team_ids)]
    valid_proj_ids = f_projects["project_id"]

    f_issues = issues[issues["project_id"].isin(valid_proj_ids)]
    if priorities:
        f_issues = f_issues[f_issues["priority"].isin(priorities)]
    if severities:
        f_issues = f_issues[f_issues["severity"].isin(severities)]

    f_sprints = sprints[sprints["project_id"].isin(valid_proj_ids)]
    f_prs = pull_requests[pull_requests["project_id"].isin(valid_proj_ids)]
    f_deployments = deployments[deployments["project_id"].isin(valid_proj_ids)]
    f_releases = releases[releases["project_id"].isin(valid_proj_ids)]
    f_kpi_team = kpi_team[kpi_team["team_id"].isin(team_ids)]
    f_project_health = kpi_project_health[kpi_project_health["project_id"].isin(valid_proj_ids)]
    f_risk_scores = risk_scores[risk_scores["project_id"].isin(valid_proj_ids)]

    return dict(projects=f_projects, issues=f_issues, sprints=f_sprints, pull_requests=f_prs,
                deployments=f_deployments, releases=f_releases, kpi_team=f_kpi_team,
                project_health=f_project_health, risk_scores=f_risk_scores)


# ---------------------------------------------------------------------------
# PAGE 1 — Executive Overview
# ---------------------------------------------------------------------------
def page_executive(f=None):
    f = f or apply_filters()
    kpi_team, issues, sprints, deployments, releases, risk_scores, kpi_project_health = (
        f["kpi_team"], f["issues"], f["sprints"], f["deployments"], f["releases"],
        f["risk_scores"], f["project_health"])

    avg_completion = round(kpi_team["avg_sprint_completion_rate"].mean() * 100, 1) if len(kpi_team) else 0
    avg_cycle = round(issues.dropna(subset=["resolved_date"])["cycle_time_days"].mean(), 1) \
        if "cycle_time_days" in issues.columns and len(issues) else None
    bug_rate = round(100 * (issues["issue_type"] == "Bug").mean(), 1) if len(issues) else 0
    deploy_freq = round(len(deployments) / max(1, deployments["deployment_timestamp"].dt.to_period("W").nunique()), 1) \
        if len(deployments) else 0
    release_success = round(100 * (releases["status"] == "On Time").mean(), 1) if len(releases) else 0
    at_risk = int((risk_scores["risk_tier"] == "High Risk").sum())

    cards = dbc.Row([
        dbc.Col(kpi_card("Overall Project Health", f"{round(kpi_project_health['project_health_score'].mean(),1)}/100")),
        dbc.Col(kpi_card("Sprint Completion Rate", f"{avg_completion}%")),
        dbc.Col(kpi_card("Avg Cycle Time", f"{avg_cycle} days")),
        dbc.Col(kpi_card("Bug Rate", f"{bug_rate}%", "warning")),
        dbc.Col(kpi_card("Deploy Frequency", f"{deploy_freq}/wk")),
        dbc.Col(kpi_card("Release Success Rate", f"{release_success}%")),
        dbc.Col(kpi_card("At-Risk Projects", at_risk, "danger")),
    ], className="mb-4 g-2")

    trend = sprints.groupby("sprint_start_date")["sprint_completion_rate"].mean().reset_index()
    fig_trend = px.line(trend, x="sprint_start_date", y="sprint_completion_rate",
                         title="Org-wide Sprint Completion Rate Trend", markers=True)

    fig_health = px.bar(kpi_project_health.sort_values("project_health_score"),
                         x="project_health_score", y="project_name", orientation="h",
                         color="project_health_score", color_continuous_scale="RdYlGn",
                         title="Project Health Score by Project")

    return html.Div([
        cards,
        dbc.Row([dbc.Col(dcc.Graph(figure=fig_trend), width=6),
                 dbc.Col(dcc.Graph(figure=fig_health), width=6)]),
    ])


# ---------------------------------------------------------------------------
# PAGE 2 — Engineering Productivity
# ---------------------------------------------------------------------------
def page_productivity(f=None):
    f = f or apply_filters()
    kpi_team, issues = f["kpi_team"], f["issues"]

    fig_team_velocity = px.bar(kpi_team.sort_values("avg_sprint_velocity", ascending=False),
                                x="team_name", y="avg_sprint_velocity",
                                title="Team Sprint Velocity Comparison", color="team_name")

    dev_ids = None
    if len(f["projects"]) < len(projects):
        team_ids = f["projects"]["team_id"].unique()
        dev_ids = developers[developers["team_id"].isin(team_ids)]["developer_id"]
    filtered_productivity = productivity[productivity["developer_id"].isin(dev_ids)] if dev_ids is not None else productivity
    fig_workload = px.histogram(filtered_productivity, x="engineering_productivity_score", nbins=20,
                                 title="Engineering Productivity Score Distribution")

    fig_cycle_by_priority = px.box(issues.dropna(subset=["resolved_date"]), x="priority", y="cycle_time_days",
                                    title="Issue Cycle Time by Priority",
                                    category_orders={"priority": ["Low", "Medium", "High", "Critical"]})

    fig_review_time = px.bar(kpi_team.sort_values("avg_pr_review_hours", ascending=False),
                              x="team_name", y="avg_pr_review_hours", title="Avg PR Review Time by Team")

    return html.Div([
        dbc.Row([dbc.Col(dcc.Graph(figure=fig_team_velocity), width=6),
                 dbc.Col(dcc.Graph(figure=fig_review_time), width=6)]),
        dbc.Row([dbc.Col(dcc.Graph(figure=fig_cycle_by_priority), width=6),
                 dbc.Col(dcc.Graph(figure=fig_workload), width=6)]),
    ])


# ---------------------------------------------------------------------------
# PAGE 3 — Software Quality
# ---------------------------------------------------------------------------
def page_quality(f=None):
    f = f or apply_filters()
    kpi_team, issues = f["kpi_team"], f["issues"]

    bugs = issues[issues["issue_type"] == "Bug"]
    fig_severity = px.pie(bugs, names="severity", title="Bugs by Severity")
    fig_by_project = bugs.merge(projects[["project_id", "project_name"]], on="project_id")
    fig_by_project = px.bar(fig_by_project.groupby("project_name").size().reset_index(name="bug_count")
                             .sort_values("bug_count", ascending=False),
                             x="project_name", y="bug_count", title="Bugs by Project")

    fig_reopened = px.bar(kpi_team.sort_values("bug_reopen_rate_pct", ascending=False),
                           x="team_name", y="bug_reopen_rate_pct", title="Bug Reopen Rate by Team")

    bugs_monthly = bugs.copy()
    bugs_monthly["month"] = bugs_monthly["created_date"].dt.to_period("M").astype(str)
    fig_trend = px.line(bugs_monthly.groupby("month").size().reset_index(name="count"),
                         x="month", y="count", title="Defect Trend Over Time", markers=True)

    return html.Div([
        dbc.Row([dbc.Col(dcc.Graph(figure=fig_severity), width=6),
                 dbc.Col(dcc.Graph(figure=fig_by_project), width=6)]),
        dbc.Row([dbc.Col(dcc.Graph(figure=fig_reopened), width=6),
                 dbc.Col(dcc.Graph(figure=fig_trend), width=6)]),
    ])


# ---------------------------------------------------------------------------
# PAGE 4 — Delivery & DevOps
# ---------------------------------------------------------------------------
def page_devops(f=None):
    f = f or apply_filters()
    kpi_team, deployments, releases = f["kpi_team"], f["deployments"], f["releases"]

    dep_monthly = deployments.copy()
    dep_monthly["month"] = dep_monthly["deployment_timestamp"].dt.to_period("M").astype(str)
    fig_freq = px.bar(dep_monthly.groupby("month").size().reset_index(name="deployments"),
                       x="month", y="deployments", title="Deployment Frequency Over Time")

    fig_success = px.pie(releases, names="status", title="Release Outcome Breakdown")

    fig_cfr = px.bar(kpi_team.sort_values("change_failure_rate_pct", ascending=False),
                      x="team_name", y="change_failure_rate_pct", title="Change Failure Rate by Team")

    rel_delay = releases[releases["status"] != "Cancelled"].merge(
        projects[["project_id", "project_name"]], on="project_id")
    fig_delay = px.box(rel_delay, x="project_name", y="release_delay_days", title="Release Delay by Project")

    return html.Div([
        dbc.Row([dbc.Col(dcc.Graph(figure=fig_freq), width=6),
                 dbc.Col(dcc.Graph(figure=fig_success), width=6)]),
        dbc.Row([dbc.Col(dcc.Graph(figure=fig_cfr), width=6),
                 dbc.Col(dcc.Graph(figure=fig_delay), width=6)]),
    ])


# ---------------------------------------------------------------------------
# PAGE 5 — Risk Intelligence
# ---------------------------------------------------------------------------
def page_risk(f=None):
    f = f or apply_filters()
    risk_scores = f["risk_scores"]

    fig_risk = px.bar(risk_scores.sort_values("release_risk_score"),
                       x="release_risk_score", y="project_name", orientation="h",
                       color="risk_tier",
                       color_discrete_map={"High Risk": "crimson", "Medium Risk": "orange", "Low Risk": "seagreen"},
                       title="Release Risk Score by Project")

    fig_components = px.bar(risk_scores.sort_values("release_risk_score", ascending=False),
                             x="project_name",
                             y=["delivery_risk", "quality_risk", "review_bottleneck_risk", "workload_risk"],
                             title="Risk Score Breakdown by Component", barmode="group")

    table = dbc.Table.from_dataframe(
        risk_scores[["project_name", "risk_tier", "release_risk_score"]].sort_values(
            "release_risk_score", ascending=False),
        striped=True, bordered=True, hover=True, className="mt-3")

    return html.Div([
        dbc.Row([dbc.Col(dcc.Graph(figure=fig_risk), width=6),
                 dbc.Col(dcc.Graph(figure=fig_components), width=6)]),
        html.H5("At-Risk Project Detail"),
        table,
    ])


PAGES = {
    "/": page_executive,
    "/productivity": page_productivity,
    "/quality": page_quality,
    "/devops": page_devops,
    "/risk": page_risk,
}


@app.callback(
    Output("page-content", "children"),
    Input("url", "pathname"),
    Input("f-project", "value"),
    Input("f-team", "value"),
    Input("f-priority", "value"),
    Input("f-severity", "value"),
)
def render_page(pathname, f_project, f_team, f_priority, f_severity):
    page_fn = PAGES.get(pathname, page_executive)
    filtered = apply_filters(f_project, f_team, f_priority, f_severity)
    return page_fn(filtered)


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8050)
