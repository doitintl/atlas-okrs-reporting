-- ========================================
-- OKRs Health Check Queries for BigQuery External Table
-- ========================================
-- 
-- These queries replicate the enhanced OKR sanity checks from 
-- the Python tools, providing the same health analysis directly in BigQuery.

-- 1. ENHANCED OKR SANITY CHECK SUMMARY
-- Replicate the main health check from okrs_sanity_check_scrap_data.py

WITH enhanced_health_check AS (
  SELECT 
    *,
    -- Check each requirement (same logic as Python script)
    CASE WHEN has_target_date THEN 0 ELSE 1 END +
    CASE WHEN teams_array IS NOT NULL AND ARRAY_LENGTH(teams_array) > 0 THEN 0 ELSE 1 END +
    CASE WHEN parent_goal IS NOT NULL THEN 0 ELSE 1 END +
    CASE WHEN owner IS NOT NULL AND TRIM(owner) != '' THEN 0 ELSE 1 END +
    CASE WHEN has_metric THEN 0 ELSE 1 END +
    CASE WHEN has_lineage THEN 0 ELSE 1 END as missing_count,
    
    -- Individual checks for detailed analysis
    has_target_date,
    (teams_array IS NOT NULL AND ARRAY_LENGTH(teams_array) > 0) as has_teams,
    (parent_goal IS NOT NULL) as has_parent_goal,
    (owner IS NOT NULL AND TRIM(owner) != '') as has_owner_set,
    has_metric,
    has_lineage
    
  FROM `{project_id}.okrs_dataset.okrs_emea_analysis_view`
)
SELECT 
  COUNT(*) as total_okrs,
  SUM(CASE WHEN missing_count = 0 THEN 1 ELSE 0 END) as healthy_okrs,
  SUM(CASE WHEN missing_count > 0 THEN 1 ELSE 0 END) as malformed_okrs,
  ROUND(SUM(CASE WHEN missing_count = 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as health_percentage
FROM enhanced_health_check;

-- 2. OKRs HEALTH BY TEAM
-- Replicate the team-by-team health analysis

WITH enhanced_health_check AS (
  SELECT 
    goal_key,
    goal_name,
    owner,
    target_date,
    parent_goal,
    sub_goals_array,
    tags_array,
    progress_type,
    teams_array,
    start_date,
    creation_date,
    lineage,
    has_target_date,
    has_metric,
    has_lineage,
    health_status,
    scraped_at,
    team_name,
    team_role,
    CASE WHEN has_target_date THEN 0 ELSE 1 END +
    CASE WHEN teams_array IS NOT NULL AND ARRAY_LENGTH(teams_array) > 0 THEN 0 ELSE 1 END +
    CASE WHEN parent_goal IS NOT NULL THEN 0 ELSE 1 END +
    CASE WHEN owner IS NOT NULL AND TRIM(owner) != '' THEN 0 ELSE 1 END +
    CASE WHEN has_metric THEN 0 ELSE 1 END +
    CASE WHEN has_lineage THEN 0 ELSE 1 END as missing_count
  FROM `{project_id}.okrs_dataset.okrs_emea_analysis_view`
)
SELECT 
  team_name,
  COUNT(*) as total_okrs,
  SUM(CASE WHEN missing_count = 0 THEN 1 ELSE 0 END) as healthy,
  SUM(CASE WHEN missing_count > 0 THEN 1 ELSE 0 END) as malformed,
  CONCAT(ROUND(SUM(CASE WHEN missing_count = 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1), '%') as health_percentage
FROM enhanced_health_check
GROUP BY team_name

UNION ALL

-- Add totals row
SELECT 
  'TOTAL' as team_name,
  COUNT(*) as total_okrs,
  SUM(CASE WHEN missing_count = 0 THEN 1 ELSE 0 END) as healthy,
  SUM(CASE WHEN missing_count > 0 THEN 1 ELSE 0 END) as malformed,
  CONCAT(ROUND(SUM(CASE WHEN missing_count = 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1), '%') as health_percentage
FROM enhanced_health_check

ORDER BY 
  CASE WHEN team_name = 'TOTAL' THEN 1 ELSE 0 END,
  total_okrs DESC;

-- 3. PROGRESS TYPE DISTRIBUTION
-- Replicate the progress type analysis for malformed vs healthy OKRs

-- Progress Type Distribution (Malformed OKRs)
WITH enhanced_health_check AS (
  SELECT 
    goal_key,
    goal_name,
    owner,
    target_date,
    parent_goal,
    sub_goals_array,
    tags_array,
    progress_type,
    teams_array,
    start_date,
    creation_date,
    lineage,
    has_target_date,
    has_metric,
    has_lineage,
    health_status,
    scraped_at,
    team_name,
    team_role,
    CASE WHEN has_target_date THEN 0 ELSE 1 END +
    CASE WHEN teams_array IS NOT NULL AND ARRAY_LENGTH(teams_array) > 0 THEN 0 ELSE 1 END +
    CASE WHEN parent_goal IS NOT NULL THEN 0 ELSE 1 END +
    CASE WHEN owner IS NOT NULL AND TRIM(owner) != '' THEN 0 ELSE 1 END +
    CASE WHEN has_metric THEN 0 ELSE 1 END +
    CASE WHEN has_lineage THEN 0 ELSE 1 END as missing_count
  FROM `{project_id}.okrs_dataset.okrs_emea_analysis_view`
),
malformed_progress AS (
  SELECT 
    CASE 
      WHEN progress_type IS NULL OR TRIM(progress_type) = '' OR TRIM(progress_type) = 'null' 
      THEN 'Not Set/Empty' 
      ELSE progress_type 
    END as progress_type_clean,
    COUNT(*) as count
  FROM enhanced_health_check
  WHERE missing_count > 0
  GROUP BY 1
),
total_malformed AS (
  SELECT SUM(count) as total FROM malformed_progress
)
SELECT 
  'MALFORMED OKRS' as category,
  mp.progress_type_clean as progress_type,
  mp.count,
  CONCAT(ROUND(mp.count * 100.0 / tm.total, 1), '%') as percentage
FROM malformed_progress mp
CROSS JOIN total_malformed tm

UNION ALL

-- Progress Type Distribution (Healthy OKRs)  
SELECT 
  'HEALTHY OKRS' as category,
  CASE 
    WHEN progress_type IS NULL OR TRIM(progress_type) = '' OR TRIM(progress_type) = 'null' 
    THEN 'Not Set/Empty' 
    ELSE progress_type 
  END as progress_type,
  COUNT(*) as count,
  CONCAT(ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY 'HEALTHY'), 1), '%') as percentage
FROM enhanced_health_check
WHERE missing_count = 0
GROUP BY 2

ORDER BY category DESC, count DESC;

-- 4. MALFORMED OKRs DETAILS 
-- Replicate the detailed breakdown with checkmarks (✅/❌)

WITH enhanced_health_check AS (
  SELECT 
    goal_key,
    goal_name,
    owner,
    target_date,
    parent_goal,
    sub_goals_array,
    tags_array,
    progress_type,
    teams_array,
    start_date,
    creation_date,
    lineage,
    team_name,
    team_role,
    -- Individual field checks
    has_target_date,
    (teams_array IS NOT NULL AND ARRAY_LENGTH(teams_array) > 0) as has_teams,
    (parent_goal IS NOT NULL) as has_parent_goal,
    (owner IS NOT NULL AND TRIM(owner) != '') as has_owner_set,
    has_metric,
    has_lineage,
    
    -- Overall health check
    CASE WHEN has_target_date THEN 0 ELSE 1 END +
    CASE WHEN teams_array IS NOT NULL AND ARRAY_LENGTH(teams_array) > 0 THEN 0 ELSE 1 END +
    CASE WHEN parent_goal IS NOT NULL THEN 0 ELSE 1 END +
    CASE WHEN owner IS NOT NULL AND TRIM(owner) != '' THEN 0 ELSE 1 END +
    CASE WHEN has_metric THEN 0 ELSE 1 END +
    CASE WHEN has_lineage THEN 0 ELSE 1 END as missing_count
  FROM `{project_id}.okrs_dataset.okrs_emea_analysis_view`
)
SELECT 
  owner,
  CASE 
    WHEN LENGTH(goal_name) > 40 THEN CONCAT(SUBSTR(goal_name, 1, 40), '...')
    ELSE goal_name 
  END as okr_name,
  CASE WHEN has_target_date THEN '✅' ELSE '❌' END as target_date_check,
  CASE WHEN has_teams THEN '✅' ELSE '❌' END as teams_check,
  CASE WHEN has_parent_goal THEN '✅' ELSE '❌' END as parent_goal_check,
  CASE WHEN has_owner_set THEN '✅' ELSE '❌' END as owner_check,
  CASE WHEN has_metric THEN '✅' ELSE '❌' END as has_metric_check,
  CASE WHEN has_lineage THEN '✅' ELSE '❌' END as has_lineage_check
FROM enhanced_health_check
WHERE missing_count > 0  -- Only malformed OKRs
ORDER BY owner;

-- 5. PARENT GOALS WITHOUT METRICS (AGGREGATION CANDIDATES)
-- Replicate the aggregation candidates analysis

WITH all_goals AS (
  -- Get all goals from the external table (not just EMEA team members)
  SELECT 
    goal_key,
    goal_name,
    owner,
    parent_goal,
    progress_type,
    sub_goals_array,
    CASE WHEN progress_type = 'ATTACHED_METRIC' THEN true ELSE false END as has_metric
  FROM `{project_id}.okrs_dataset.okrs_latest_view`
),
parent_child_mapping AS (
  -- Build parent-child relationships
  SELECT 
    p.goal_key as parent_key,
    p.goal_name as parent_name,
    p.owner as parent_owner,
    p.has_metric as parent_has_metric,
    ARRAY_LENGTH(p.sub_goals_array) as total_subgoals,
    ARRAY(
      SELECT COUNT(*)
      FROM all_goals c
      WHERE c.parent_goal = p.goal_key 
        AND c.has_metric = true
    )[OFFSET(0)] as subgoals_with_metrics
  FROM all_goals p
  WHERE ARRAY_LENGTH(p.sub_goals_array) > 0  -- Only parent goals
    AND NOT p.has_metric  -- Without metrics
),
emea_candidates AS (
  -- Filter for EMEA team members only
  SELECT 
    pcm.*,
    CASE WHEN pcm.subgoals_with_metrics > 0 THEN '✅' ELSE '❌' END as can_aggregate
  FROM parent_child_mapping pcm
  INNER JOIN `{project_id}.okrs_dataset.teams` t
    ON LOWER(TRIM(pcm.parent_owner)) = LOWER(TRIM(t.name))
)
SELECT 
  parent_owner as owner,
  CASE 
    WHEN LENGTH(parent_name) > 50 THEN CONCAT(SUBSTR(parent_name, 1, 50), '...')
    ELSE parent_name 
  END as parent_goal_name,
  total_subgoals as sub_goals,
  subgoals_with_metrics as sub_goals_w_metrics,
  can_aggregate
FROM emea_candidates
ORDER BY subgoals_with_metrics DESC, parent_owner;

-- 6. PEOPLE WITHOUT OKRs BY TEAM
-- Replicate the analysis of team members who don't have OKRs

WITH people_with_okrs AS (
  SELECT DISTINCT LOWER(TRIM(owner)) as person_lower
  FROM `{project_id}.okrs_dataset.okrs_emea_analysis_view`
  WHERE owner IS NOT NULL
),
all_team_members AS (
  SELECT 
    team,
    LOWER(TRIM(name)) as person_lower,
    name as person_name
  FROM `{project_id}.okrs_dataset.teams`
),
people_without_okrs AS (
  SELECT 
    atm.team,
    atm.person_name
  FROM all_team_members atm
  LEFT JOIN people_with_okrs pwo
    ON atm.person_lower = pwo.person_lower
  WHERE pwo.person_lower IS NULL
)
SELECT 
  team as team_name,
  STRING_AGG(person_name, ', ' ORDER BY person_name) as people_without_okrs,
  COUNT(*) as count_without_okrs
FROM people_without_okrs
GROUP BY team
ORDER BY count_without_okrs DESC, team;

-- 7. DATA FRESHNESS AND BASIC EXPLORATION
-- Check when was the latest scrape
SELECT 
  MAX(scraped_at) as latest_scrape,
  COUNT(*) as total_okrs_latest,
  COUNT(DISTINCT owner) as unique_owners
FROM `{project_id}.okrs_dataset.okrs_emea_analysis_view`;

-- View all available scrape timestamps
SELECT 
  created_at,
  COUNT(*) as okr_count,
  scraped_at
FROM `{project_id}.okrs_dataset.okrs_analysis_view`
GROUP BY created_at, scraped_at
ORDER BY scraped_at DESC
LIMIT 10;

-- 8. COMPARATIVE HEALTH ANALYSIS (Across Time)
-- Compare OKR health across different scrapes using enhanced criteria

WITH enhanced_health_by_scrape AS (
  SELECT 
    o.created_at,
    o.scraped_at,
    COUNT(*) as total_okrs,
    SUM(CASE 
      WHEN CASE WHEN o.has_target_date THEN 0 ELSE 1 END +
           CASE WHEN o.teams_array IS NOT NULL AND ARRAY_LENGTH(o.teams_array) > 0 THEN 0 ELSE 1 END +
           CASE WHEN o.parent_goal IS NOT NULL THEN 0 ELSE 1 END +
           CASE WHEN o.owner IS NOT NULL AND TRIM(o.owner) != '' THEN 0 ELSE 1 END +
           CASE WHEN o.has_metric THEN 0 ELSE 1 END +
           CASE WHEN o.has_lineage THEN 0 ELSE 1 END = 0 
      THEN 1 ELSE 0 
    END) as healthy_okrs
  FROM `{project_id}.okrs_dataset.okrs_analysis_view` o
  INNER JOIN `{project_id}.okrs_dataset.teams` t
    ON LOWER(TRIM(o.owner)) = LOWER(TRIM(t.name))
  GROUP BY o.created_at, o.scraped_at
)
SELECT 
  created_at,
  scraped_at,
  total_okrs,
  healthy_okrs,
  ROUND(healthy_okrs * 100.0 / total_okrs, 1) as health_percentage
FROM enhanced_health_by_scrape
ORDER BY scraped_at DESC
LIMIT 10;

-- 9. SUMMARY STATISTICS FOR REPORTING
-- Quick overview for management reporting

WITH health_summary AS (
  SELECT 
    COUNT(*) as total_okrs,
    SUM(CASE 
      WHEN CASE WHEN o.has_target_date THEN 0 ELSE 1 END +
           CASE WHEN o.teams_array IS NOT NULL AND ARRAY_LENGTH(o.teams_array) > 0 THEN 0 ELSE 1 END +
           CASE WHEN o.parent_goal IS NOT NULL THEN 0 ELSE 1 END +
           CASE WHEN o.owner IS NOT NULL AND TRIM(o.owner) != '' THEN 0 ELSE 1 END +
           CASE WHEN o.has_metric THEN 0 ELSE 1 END +
           CASE WHEN o.has_lineage THEN 0 ELSE 1 END = 0 
      THEN 1 ELSE 0 
    END) as healthy_okrs,
    COUNT(DISTINCT o.owner) as people_with_okrs,
    COUNT(DISTINCT o.team_name) as teams_with_okrs
  FROM `{project_id}.okrs_dataset.okrs_emea_analysis_view` o
),
team_totals AS (
  SELECT 
    COUNT(DISTINCT name) as total_team_members,
    COUNT(DISTINCT team) as total_teams
  FROM `{project_id}.okrs_dataset.teams`
)
SELECT 
  hs.total_okrs,
  hs.healthy_okrs,
  hs.total_okrs - hs.healthy_okrs as malformed_okrs,
  ROUND(hs.healthy_okrs * 100.0 / hs.total_okrs, 1) as health_percentage,
  hs.people_with_okrs,
  tt.total_team_members,
  tt.total_team_members - hs.people_with_okrs as people_without_okrs,
  ROUND(hs.people_with_okrs * 100.0 / tt.total_team_members, 1) as penetration_percentage
FROM health_summary hs
CROSS JOIN team_totals tt; 