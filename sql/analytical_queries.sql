-- =============================================================================
-- analytical_queries.sql
-- 20+ analytical SQL queries for the Software Engineering Analytics Platform.
-- Written/tested against SQLite (sql/engineering_analytics.db) using
-- standard ANSI SQL so they port to PostgreSQL/MySQL with minimal changes.
-- Grouped by theme; each query answers a specific business/engineering question.
-- =============================================================================


-- =========================== A. SPRINT & DELIVERY PERFORMANCE =========================

-- Q1. Which teams have the highest average sprint completion rate?
SELECT t.team_name,
       ROUND(AVG(s.sprint_completion_rate) * 100, 1) AS avg_completion_pct,
       COUNT(*) AS sprints_analyzed
FROM sprints s
JOIN teams t ON t.team_id = s.team_id
GROUP BY t.team_name
HAVING COUNT(*) >= 5
ORDER BY avg_completion_pct DESC;

-- Q2. Sprint velocity (avg completed story points) trend per team, most recent 5 sprints
WITH ranked_sprints AS (
    SELECT s.*, t.team_name,
           ROW_NUMBER() OVER (PARTITION BY s.team_id ORDER BY s.sprint_start_date DESC) AS rn
    FROM sprints s
    JOIN teams t ON t.team_id = s.team_id
)
SELECT team_name, ROUND(AVG(completed_story_points), 1) AS avg_velocity_last5
FROM ranked_sprints
WHERE rn <= 5
GROUP BY team_name
ORDER BY avg_velocity_last5 DESC;

-- Q3. Which teams are improving vs. declining in velocity? (first-half vs second-half sprints)
WITH numbered AS (
    SELECT s.team_id, t.team_name, s.completed_story_points,
           ROW_NUMBER() OVER (PARTITION BY s.team_id ORDER BY s.sprint_start_date) AS seq,
           COUNT(*) OVER (PARTITION BY s.team_id) AS total_sprints
    FROM sprints s JOIN teams t ON t.team_id = s.team_id
),
halves AS (
    SELECT team_name,
           AVG(CASE WHEN seq <= total_sprints/2 THEN completed_story_points END) AS first_half_avg,
           AVG(CASE WHEN seq >  total_sprints/2 THEN completed_story_points END) AS second_half_avg
    FROM numbered
    GROUP BY team_name
)
SELECT team_name,
       ROUND(first_half_avg, 1)  AS first_half_avg_velocity,
       ROUND(second_half_avg, 1) AS second_half_avg_velocity,
       CASE WHEN second_half_avg > first_half_avg THEN 'Improving'
            WHEN second_half_avg < first_half_avg THEN 'Declining'
            ELSE 'Stable' END AS trend
FROM halves
ORDER BY (second_half_avg - first_half_avg) DESC;

-- Q4. Average issue cycle time by priority (CASE-based bucketing)
SELECT priority,
       ROUND(AVG(cycle_time_days), 2) AS avg_cycle_time_days,
       CASE
           WHEN AVG(cycle_time_days) <= 1 THEN 'Fast'
           WHEN AVG(cycle_time_days) <= 3 THEN 'Acceptable'
           ELSE 'Slow'
       END AS speed_rating
FROM issues
WHERE resolved_date IS NOT NULL
GROUP BY priority
ORDER BY avg_cycle_time_days DESC;

-- Q5. Projects most likely to miss release targets (historical delay rate > 30%)
SELECT p.project_name,
       COUNT(*) AS total_releases,
       SUM(r.is_delayed) AS delayed_releases,
       ROUND(100.0 * SUM(r.is_delayed) / COUNT(*), 1) AS delay_rate_pct
FROM releases r
JOIN projects p ON p.project_id = r.project_id
GROUP BY p.project_name
HAVING ROUND(100.0 * SUM(r.is_delayed) / COUNT(*), 1) > 30
ORDER BY delay_rate_pct DESC;


-- =========================== B. SOFTWARE QUALITY =========================

-- Q6. Which projects have the highest defect rate (bugs per 100 completed issues)?
SELECT p.project_name,
       SUM(CASE WHEN i.issue_type = 'Bug' THEN 1 ELSE 0 END) AS bug_count,
       COUNT(*) AS total_issues,
       ROUND(100.0 * SUM(CASE WHEN i.issue_type = 'Bug' THEN 1 ELSE 0 END) / COUNT(*), 1) AS defect_rate_pct
FROM issues i
JOIN projects p ON p.project_id = i.project_id
GROUP BY p.project_name
ORDER BY defect_rate_pct DESC;

-- Q7. What percentage of bugs are reopened, overall and by team?
SELECT t.team_name,
       SUM(i.reopened) AS reopened_bugs,
       SUM(CASE WHEN i.issue_type = 'Bug' THEN 1 ELSE 0 END) AS total_bugs,
       ROUND(100.0 * SUM(i.reopened) / NULLIF(SUM(CASE WHEN i.issue_type='Bug' THEN 1 ELSE 0 END), 0), 1) AS reopen_rate_pct
FROM issues i
JOIN teams t ON t.team_id = i.team_id
WHERE i.issue_type = 'Bug'
GROUP BY t.team_name
ORDER BY reopen_rate_pct DESC;

-- Q8. Escaped defect rate by project (bugs that leaked to production)
SELECT p.project_name,
       SUM(i.escaped_defect) AS escaped_defects,
       SUM(CASE WHEN i.issue_type='Bug' THEN 1 ELSE 0 END) AS total_bugs,
       ROUND(100.0 * SUM(i.escaped_defect) / NULLIF(SUM(CASE WHEN i.issue_type='Bug' THEN 1 ELSE 0 END),0), 1) AS escaped_rate_pct
FROM issues i
JOIN projects p ON p.project_id = i.project_id
WHERE i.issue_type = 'Bug'
GROUP BY p.project_name
ORDER BY escaped_rate_pct DESC
LIMIT 10;

-- Q9. Mean time to resolve (MTTR) bugs by severity
SELECT severity,
       ROUND(AVG(resolution_time_hours), 1) AS mttr_hours,
       COUNT(*) AS bug_count
FROM issues
WHERE issue_type = 'Bug' AND resolved_date IS NOT NULL
GROUP BY severity
ORDER BY CASE severity WHEN 'Blocker' THEN 1 WHEN 'Critical' THEN 2
                        WHEN 'Major' THEN 3 WHEN 'Minor' THEN 4 END;

-- Q10. Teams with a statistically unusual bug reopen rate (> overall avg + 1 stdev)
WITH team_rates AS (
    SELECT t.team_id, t.team_name,
           100.0 * SUM(i.reopened) / NULLIF(SUM(CASE WHEN i.issue_type='Bug' THEN 1 ELSE 0 END), 0) AS reopen_rate_pct
    FROM issues i
    JOIN teams t ON t.team_id = i.team_id
    WHERE i.issue_type = 'Bug'
    GROUP BY t.team_id, t.team_name
),
stats AS (
    SELECT AVG(reopen_rate_pct) AS mean_rate,
           -- population stdev computed manually (SQLite has no built-in STDEV)
           SQRT(AVG((reopen_rate_pct - (SELECT AVG(reopen_rate_pct) FROM team_rates)) *
                    (reopen_rate_pct - (SELECT AVG(reopen_rate_pct) FROM team_rates)))) AS stdev_rate
    FROM team_rates
)
SELECT tr.team_name, ROUND(tr.reopen_rate_pct, 1) AS reopen_rate_pct,
       ROUND(s.mean_rate, 1) AS org_avg_rate, ROUND(s.stdev_rate, 1) AS org_stdev
FROM team_rates tr, stats s
WHERE tr.reopen_rate_pct > s.mean_rate + s.stdev_rate
ORDER BY tr.reopen_rate_pct DESC;


-- =========================== C. CODE REVIEW / PR EFFICIENCY =========================

-- Q11. Average PR review time by team
SELECT t.team_name,
       ROUND(AVG(pr.review_time_hours), 1) AS avg_review_hours,
       COUNT(*) AS prs
FROM pull_requests pr
JOIN sprints s ON s.sprint_id = pr.sprint_id
JOIN teams t ON t.team_id = s.team_id
WHERE pr.review_time_hours IS NOT NULL
GROUP BY t.team_name
ORDER BY avg_review_hours DESC;

-- Q12. PR merge rate by project
SELECT p.project_name,
       COUNT(*) AS total_prs,
       SUM(pr.is_merged) AS merged_prs,
       ROUND(100.0 * SUM(pr.is_merged) / COUNT(*), 1) AS merge_rate_pct
FROM pull_requests pr
JOIN projects p ON p.project_id = pr.project_id
GROUP BY p.project_name
ORDER BY merge_rate_pct ASC;

-- Q13. Relationship between PR size and review time (bucketed) — is bigger PRs slower?
SELECT
    CASE
        WHEN pr_size_lines < 50 THEN '1. <50 lines'
        WHEN pr_size_lines < 150 THEN '2. 50-150 lines'
        WHEN pr_size_lines < 400 THEN '3. 150-400 lines'
        ELSE '4. 400+ lines'
    END AS pr_size_bucket,
    ROUND(AVG(review_time_hours), 1) AS avg_review_hours,
    COUNT(*) AS pr_count
FROM pull_requests
WHERE review_time_hours IS NOT NULL
GROUP BY pr_size_bucket
ORDER BY pr_size_bucket;

-- Q14. Reviewer workload — who reviews the most PRs, with running total (window function)
SELECT reviewer_id,
       COUNT(*) AS prs_reviewed,
       SUM(COUNT(*)) OVER (ORDER BY COUNT(*) DESC) AS running_total_prs
FROM pull_requests
GROUP BY reviewer_id
ORDER BY prs_reviewed DESC
LIMIT 15;

-- Q15. Developers with unusually high workload (issues assigned, ranked with PERCENT_RANK)
SELECT developer_id, issues_assigned,
       ROUND(PERCENT_RANK() OVER (ORDER BY issues_assigned), 3) AS workload_percentile
FROM (
    SELECT assignee_id AS developer_id, COUNT(*) AS issues_assigned
    FROM issues
    GROUP BY assignee_id
) dev_load
ORDER BY issues_assigned DESC
LIMIT 15;


-- =========================== D. DEPLOYMENT / DEVOPS =========================

-- Q16. Deployment frequency by project (deploys per week)
SELECT p.project_name,
       COUNT(*) AS total_deployments,
       ROUND(COUNT(*) / (JULIANDAY(MAX(d.deployment_timestamp)) - JULIANDAY(MIN(d.deployment_timestamp)) + 1) * 7, 2) AS deploys_per_week
FROM deployments d
JOIN projects p ON p.project_id = d.project_id
GROUP BY p.project_name
ORDER BY deploys_per_week DESC;

-- Q17. Change failure rate (CFR) by team — a core DORA metric
SELECT t.team_name,
       COUNT(*) AS total_deployments,
       SUM(d.is_failure) AS failed_deployments,
       ROUND(100.0 * SUM(d.is_failure) / COUNT(*), 1) AS change_failure_rate_pct
FROM deployments d
JOIN sprints s ON s.sprint_id = d.sprint_id
JOIN teams t ON t.team_id = s.team_id
GROUP BY t.team_name
ORDER BY change_failure_rate_pct DESC;

-- Q18. How does deployment frequency correlate with release delay? (project-level rollup)
WITH deploy_freq AS (
    SELECT project_id, COUNT(*) AS deploy_count
    FROM deployments GROUP BY project_id
),
release_perf AS (
    SELECT project_id, ROUND(AVG(release_delay_days), 1) AS avg_delay_days
    FROM releases WHERE status != 'Cancelled' GROUP BY project_id
)
SELECT p.project_name, df.deploy_count, rp.avg_delay_days
FROM deploy_freq df
JOIN release_perf rp ON rp.project_id = df.project_id
JOIN projects p ON p.project_id = df.project_id
ORDER BY df.deploy_count DESC;

-- Q19. Rollback rate among failed deployments, by environment
SELECT environment,
       SUM(is_failure) AS failed_deploys,
       SUM(rollback) AS rollbacks,
       ROUND(100.0 * SUM(rollback) / NULLIF(SUM(is_failure), 0), 1) AS rollback_rate_pct
FROM deployments
GROUP BY environment;


-- =========================== E. RELEASE RISK / EXECUTIVE ROLLUP =========================

-- Q20. Release success rate and average delay by project (executive summary query)
SELECT p.project_name,
       COUNT(*) AS total_releases,
       ROUND(100.0 * SUM(CASE WHEN r.status = 'On Time' THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_rate_pct,
       ROUND(AVG(CASE WHEN r.status != 'Cancelled' THEN r.release_delay_days END), 1) AS avg_delay_days
FROM releases r
JOIN projects p ON p.project_id = r.project_id
GROUP BY p.project_name
ORDER BY on_time_rate_pct ASC;

-- Q21. Monthly release delay trend (time-series)
SELECT strftime('%Y-%m', planned_release_date) AS release_month,
       COUNT(*) AS releases,
       ROUND(100.0 * SUM(is_delayed) / COUNT(*), 1) AS delay_rate_pct
FROM releases
GROUP BY release_month
ORDER BY release_month;

-- Q22. Composite "Project Health Score" combining delivery, quality, and DevOps signals
--      (0-100, higher is healthier) — feeds the Executive Overview dashboard page
WITH quality AS (
    SELECT project_id,
           100.0 * (1 - CAST(SUM(escaped_defect) AS REAL) / NULLIF(COUNT(*),0)) AS quality_score
    FROM issues WHERE issue_type='Bug' GROUP BY project_id
),
delivery AS (
    SELECT project_id, AVG(sprint_completion_rate) * 100 AS delivery_score
    FROM sprints GROUP BY project_id
),
devops AS (
    SELECT project_id, 100.0 * (1 - CAST(SUM(is_failure) AS REAL) / NULLIF(COUNT(*),0)) AS devops_score
    FROM deployments GROUP BY project_id
)
SELECT p.project_name,
       ROUND(q.quality_score, 1)   AS quality_score,
       ROUND(d.delivery_score, 1)  AS delivery_score,
       ROUND(dv.devops_score, 1)   AS devops_score,
       ROUND((q.quality_score * 0.35 + d.delivery_score * 0.35 + dv.devops_score * 0.30), 1) AS project_health_score
FROM projects p
JOIN quality q ON q.project_id = p.project_id
JOIN delivery d ON d.project_id = p.project_id
JOIN devops dv ON dv.project_id = p.project_id
ORDER BY project_health_score ASC;

-- Q23. Analytical VIEW: team_performance_summary — reusable rollup for BI tools/dashboard
DROP VIEW IF EXISTS team_performance_summary;
CREATE VIEW team_performance_summary AS
SELECT t.team_id, t.team_name,
       ROUND(AVG(s.sprint_completion_rate) * 100, 1) AS avg_sprint_completion_pct,
       (SELECT ROUND(100.0 * SUM(reopened) / NULLIF(SUM(CASE WHEN issue_type='Bug' THEN 1 ELSE 0 END),0), 1)
        FROM issues WHERE issues.team_id = t.team_id AND issue_type='Bug') AS bug_reopen_rate_pct,
       (SELECT ROUND(AVG(review_time_hours), 1) FROM pull_requests pr
        JOIN sprints s2 ON s2.sprint_id = pr.sprint_id WHERE s2.team_id = t.team_id) AS avg_pr_review_hours
FROM teams t
JOIN sprints s ON s.team_id = t.team_id
GROUP BY t.team_id, t.team_name;

-- Q24. Using the view: teams ranked by a simple blended risk indicator
SELECT team_name, avg_sprint_completion_pct, bug_reopen_rate_pct, avg_pr_review_hours
FROM team_performance_summary
ORDER BY (100 - avg_sprint_completion_pct) + bug_reopen_rate_pct + avg_pr_review_hours DESC;

-- Q25. Developer workload index — commits, PRs authored, and issues resolved combined
--      (used as one input to the KPI "Developer Workload Index" in Section 4)
SELECT dev.developer_id, dev.full_name, t.team_name,
       COALESCE(c.commit_count, 0)   AS commit_count,
       COALESCE(pr.pr_count, 0)      AS pr_count,
       COALESCE(iss.issues_resolved, 0) AS issues_resolved,
       COALESCE(c.commit_count,0) + COALESCE(pr.pr_count,0)*3 + COALESCE(iss.issues_resolved,0)*2 AS workload_index
FROM developers dev
JOIN teams t ON t.team_id = dev.team_id
LEFT JOIN (SELECT developer_id, COUNT(*) AS commit_count FROM commits GROUP BY developer_id) c
       ON c.developer_id = dev.developer_id
LEFT JOIN (SELECT author_id, COUNT(*) AS pr_count FROM pull_requests GROUP BY author_id) pr
       ON pr.author_id = dev.developer_id
LEFT JOIN (SELECT assignee_id, COUNT(*) AS issues_resolved FROM issues WHERE status='Done' GROUP BY assignee_id) iss
       ON iss.assignee_id = dev.developer_id
ORDER BY workload_index DESC
LIMIT 15;
