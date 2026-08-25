-- =============================================================================
-- schema.sql
-- Software Engineering Productivity & Delivery Intelligence Platform
-- Normalized relational schema (3NF), written in PostgreSQL-compatible DDL.
-- The project ships a SQLite build (build_database.py) for portability/demo
-- purposes; syntax here is standard enough to run on PostgreSQL or MySQL
-- with trivial changes (SERIAL -> AUTO_INCREMENT, etc.)
-- =============================================================================

DROP TABLE IF EXISTS code_reviews;
DROP TABLE IF EXISTS deployments;
DROP TABLE IF EXISTS releases;
DROP TABLE IF EXISTS pull_requests;
DROP TABLE IF EXISTS commits;
DROP TABLE IF EXISTS issues;
DROP TABLE IF EXISTS sprints;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS developers;
DROP TABLE IF EXISTS teams;

-- -----------------------------------------------------------------------------
CREATE TABLE teams (
    team_id         VARCHAR(10)   PRIMARY KEY,
    team_name       VARCHAR(100)  NOT NULL,
    department      VARCHAR(100),
    formed_date     DATE
);

CREATE TABLE developers (
    developer_id    VARCHAR(10)   PRIMARY KEY,
    full_name       VARCHAR(150)  NOT NULL,
    team_id         VARCHAR(10)   REFERENCES teams(team_id),
    role            VARCHAR(50),
    seniority       VARCHAR(20),
    hire_date       DATE,
    timezone        VARCHAR(10)
);

CREATE TABLE projects (
    project_id      VARCHAR(10)   PRIMARY KEY,
    project_name    VARCHAR(150)  NOT NULL,
    team_id         VARCHAR(10)   REFERENCES teams(team_id),
    start_date      DATE,
    criticality     VARCHAR(20),
    tech_stack      VARCHAR(50)
);

CREATE TABLE sprints (
    sprint_id                  VARCHAR(10)  PRIMARY KEY,
    project_id                 VARCHAR(10)  REFERENCES projects(project_id),
    team_id                    VARCHAR(10)  REFERENCES teams(team_id),
    sprint_number               INTEGER,
    sprint_start_date          DATE,
    sprint_end_date            DATE,
    planned_story_points       INTEGER,
    completed_story_points     INTEGER,
    sprint_completion_rate     NUMERIC(5,3)
);

CREATE TABLE issues (
    issue_id                VARCHAR(12)  PRIMARY KEY,
    project_id               VARCHAR(10)  REFERENCES projects(project_id),
    sprint_id                VARCHAR(10)  REFERENCES sprints(sprint_id),
    team_id                  VARCHAR(10)  REFERENCES teams(team_id),
    assignee_id               VARCHAR(10)  REFERENCES developers(developer_id),
    issue_type                VARCHAR(20),
    priority                  VARCHAR(20),
    severity                  VARCHAR(20),
    status                     VARCHAR(20),
    created_date               TIMESTAMP,
    resolved_date               TIMESTAMP,
    resolution_time_hours       NUMERIC(10,1),
    cycle_time_days             NUMERIC(10,2),
    reopened                    SMALLINT,
    escaped_defect               SMALLINT
);

CREATE TABLE commits (
    commit_id           VARCHAR(12)  PRIMARY KEY,
    project_id           VARCHAR(10)  REFERENCES projects(project_id),
    sprint_id            VARCHAR(10)  REFERENCES sprints(sprint_id),
    developer_id          VARCHAR(10)  REFERENCES developers(developer_id),
    commit_timestamp      TIMESTAMP,
    lines_added            INTEGER,
    lines_deleted           INTEGER,
    files_changed            INTEGER,
    total_churn               INTEGER
);

CREATE TABLE pull_requests (
    pull_request_id       VARCHAR(12)  PRIMARY KEY,
    project_id             VARCHAR(10)  REFERENCES projects(project_id),
    sprint_id               VARCHAR(10)  REFERENCES sprints(sprint_id),
    author_id                 VARCHAR(10)  REFERENCES developers(developer_id),
    reviewer_id                VARCHAR(10)  REFERENCES developers(developer_id),
    opened_date                  TIMESTAMP,
    closed_date                    TIMESTAMP,
    review_time_hours                NUMERIC(10,1),
    pr_size_lines                     INTEGER,
    status                              VARCHAR(20),
    is_merged                            SMALLINT
);

CREATE TABLE code_reviews (
    review_id               VARCHAR(12)  PRIMARY KEY,
    pull_request_id           VARCHAR(12)  REFERENCES pull_requests(pull_request_id),
    reviewer_id                 VARCHAR(10)  REFERENCES developers(developer_id),
    review_round                  INTEGER,
    comments_count                   INTEGER,
    approved                           SMALLINT,
    review_timestamp                     TIMESTAMP
);

CREATE TABLE deployments (
    deployment_id       VARCHAR(12)  PRIMARY KEY,
    project_id            VARCHAR(10)  REFERENCES projects(project_id),
    sprint_id              VARCHAR(10)  REFERENCES sprints(sprint_id),
    environment              VARCHAR(20),
    deployment_timestamp       TIMESTAMP,
    status                       VARCHAR(20),
    is_failure                     SMALLINT,
    rollback                         SMALLINT,
    duration_minutes                   NUMERIC(10,1)
);

CREATE TABLE releases (
    release_id             VARCHAR(12)  PRIMARY KEY,
    project_id               VARCHAR(10)  REFERENCES projects(project_id),
    team_id                    VARCHAR(10)  REFERENCES teams(team_id),
    sprint_id                    VARCHAR(10)  REFERENCES sprints(sprint_id),
    planned_release_date           DATE,
    actual_release_date              DATE,
    release_delay_days                 NUMERIC(6,1),
    status                                VARCHAR(20),
    is_delayed                             SMALLINT,
    version                                  VARCHAR(20)
);

-- -----------------------------------------------------------------------------
-- Indexes to support the analytical query workload (joins/group-bys below)
-- -----------------------------------------------------------------------------
CREATE INDEX idx_issues_project ON issues(project_id);
CREATE INDEX idx_issues_sprint  ON issues(sprint_id);
CREATE INDEX idx_issues_team    ON issues(team_id);
CREATE INDEX idx_prs_project    ON pull_requests(project_id);
CREATE INDEX idx_commits_dev    ON commits(developer_id);
CREATE INDEX idx_deploy_project ON deployments(project_id);
CREATE INDEX idx_releases_project ON releases(project_id);
