-- =============================================================================
-- data_loading.sql
-- Reference bulk-load statements for PostgreSQL. In this project the actual
-- load is performed programmatically by sql/build_database.py (pandas.to_sql
-- against SQLite, for zero-setup portability). These COPY statements are the
-- production-equivalent you'd run against a real Postgres instance once
-- schema.sql has been applied, loading the cleaned files from data/processed/.
-- =============================================================================

-- Run schema.sql first, then:

COPY teams(team_id, team_name, department, formed_date)
FROM '/data/processed/teams.csv' WITH (FORMAT csv, HEADER true);

COPY developers(developer_id, full_name, team_id, role, seniority, hire_date, timezone)
FROM '/data/processed/developers.csv' WITH (FORMAT csv, HEADER true);

COPY projects(project_id, project_name, team_id, start_date, criticality, tech_stack)
FROM '/data/processed/projects.csv' WITH (FORMAT csv, HEADER true);

COPY sprints(sprint_id, project_id, team_id, sprint_number, sprint_start_date,
             sprint_end_date, planned_story_points, completed_story_points,
             sprint_completion_rate)
FROM '/data/processed/sprints.csv' WITH (FORMAT csv, HEADER true);

COPY issues(issue_id, project_id, sprint_id, team_id, assignee_id, issue_type,
            priority, severity, status, created_date, resolved_date,
            resolution_time_hours, cycle_time_days, reopened, escaped_defect)
FROM '/data/processed/issues.csv' WITH (FORMAT csv, HEADER true);

COPY commits(commit_id, project_id, sprint_id, developer_id, commit_timestamp,
             lines_added, lines_deleted, files_changed, total_churn)
FROM '/data/processed/commits.csv' WITH (FORMAT csv, HEADER true);

COPY pull_requests(pull_request_id, project_id, sprint_id, author_id, reviewer_id,
                    opened_date, closed_date, review_time_hours, pr_size_lines,
                    status, is_merged)
FROM '/data/processed/pull_requests.csv' WITH (FORMAT csv, HEADER true);

COPY code_reviews(review_id, pull_request_id, reviewer_id, review_round,
                   comments_count, approved, review_timestamp)
FROM '/data/processed/code_reviews.csv' WITH (FORMAT csv, HEADER true);

COPY deployments(deployment_id, project_id, sprint_id, environment,
                  deployment_timestamp, status, is_failure, rollback, duration_minutes)
FROM '/data/processed/deployments.csv' WITH (FORMAT csv, HEADER true);

COPY releases(release_id, project_id, team_id, sprint_id, planned_release_date,
              actual_release_date, release_delay_days, status, is_delayed, version)
FROM '/data/processed/releases.csv' WITH (FORMAT csv, HEADER true);

-- Post-load validation (row counts should match data/processed/*.csv line counts - 1)
SELECT 'teams' AS table_name, COUNT(*) FROM teams
UNION ALL SELECT 'developers', COUNT(*) FROM developers
UNION ALL SELECT 'projects', COUNT(*) FROM projects
UNION ALL SELECT 'sprints', COUNT(*) FROM sprints
UNION ALL SELECT 'issues', COUNT(*) FROM issues
UNION ALL SELECT 'commits', COUNT(*) FROM commits
UNION ALL SELECT 'pull_requests', COUNT(*) FROM pull_requests
UNION ALL SELECT 'code_reviews', COUNT(*) FROM code_reviews
UNION ALL SELECT 'deployments', COUNT(*) FROM deployments
UNION ALL SELECT 'releases', COUNT(*) FROM releases;
