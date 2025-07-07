-- ========================================
-- BigQuery External Table for OKRs from Cloud Storage
-- ========================================
-- 
-- This external table allows querying CSV files directly from Cloud Storage
-- without loading them into BigQuery, saving costs and keeping data
-- always up to date.

-- 1. MAIN EXTERNAL TABLE FOR PROCESSED FILES
-- Points to all export-*_processed.csv files in the bucket

CREATE OR REPLACE EXTERNAL TABLE `{project_id}.okrs_dataset.okrs_external`
(
  created_at STRING OPTIONS(description="Timestamp when the data was scraped (YYYYMMDDHHMM format)"),
  owner STRING OPTIONS(description="Goal owner name"),
  goal_key STRING OPTIONS(description="Unique goal identifier/key"),
  target_date STRING OPTIONS(description="Goal target/due date"),
  name STRING OPTIONS(description="Goal name/title"),
  parent_goal STRING OPTIONS(description="Parent goal key (if this is a sub-goal)"),
  sub_goals STRING OPTIONS(description="Semi-colon separated list of sub-goal keys"),
  tags STRING OPTIONS(description="Semi-colon separated list of goal tags"),
  progress_type STRING OPTIONS(description="Type of progress tracking (ATTACHED_METRIC, MANUAL, etc.)"),
  teams STRING OPTIONS(description="Semi-colon separated list of associated teams"),
  start_date STRING OPTIONS(description="Goal start date"),
  creation_date STRING OPTIONS(description="Goal creation date"),
  lineage STRING OPTIONS(description="Goal lineage in dot notation (e.g. doit.cs.cre.emea.south.es-pod-1)")
)
OPTIONS (
  format = 'CSV',
  uris = ['gs://{bucket_name}/okrs/export-*_processed.csv'],
  skip_leading_rows = 1,
  allow_jagged_rows = false,
  allow_quoted_newlines = false
);

-- 2. OPTIMIZED VIEW FOR ANALYSIS
-- View that cleans and transforms data to facilitate analysis

CREATE OR REPLACE VIEW `{project_id}.okrs_dataset.okrs_analysis_view` AS
SELECT 
  created_at,
  TRIM(owner) as owner,
  TRIM(goal_key) as goal_key,
  CASE 
    WHEN TRIM(target_date) = 'null' OR TRIM(target_date) = '' THEN NULL
    ELSE PARSE_DATE('%Y-%m-%d', TRIM(target_date))
  END as target_date,
  TRIM(name) as goal_name,
  CASE 
    WHEN TRIM(parent_goal) = 'null' OR TRIM(parent_goal) = '' THEN NULL
    ELSE TRIM(parent_goal)
  END as parent_goal,
  CASE 
    WHEN TRIM(sub_goals) = 'null' OR TRIM(sub_goals) = '' THEN []
    ELSE SPLIT(TRIM(sub_goals), ';')
  END as sub_goals_array,
  CASE 
    WHEN TRIM(tags) = 'null' OR TRIM(tags) = '' THEN []
    ELSE SPLIT(TRIM(tags), ';')
  END as tags_array,
  TRIM(progress_type) as progress_type,
  CASE 
    WHEN TRIM(teams) = 'null' OR TRIM(teams) = '' THEN []
    ELSE SPLIT(TRIM(teams), ';')
  END as teams_array,
  CASE 
    WHEN TRIM(start_date) = 'null' OR TRIM(start_date) = '' THEN NULL
    ELSE PARSE_DATE('%Y-%m-%d', TRIM(start_date))
  END as start_date,
  CASE 
    WHEN TRIM(creation_date) = 'null' OR TRIM(creation_date) = '' THEN NULL
    ELSE PARSE_DATETIME('%Y-%m-%dT%H:%M:%S', REGEXP_REPLACE(TRIM(creation_date), r'(\.\d+)?(Z|[+-]\d{2}:\d{2})$', ''))
  END as creation_date,
  CASE 
    WHEN TRIM(lineage) = 'null' OR TRIM(lineage) = '' THEN NULL
    ELSE TRIM(lineage)
  END as lineage,
  
  -- Calculated fields for analysis
  CASE 
    WHEN TRIM(target_date) = 'null' OR TRIM(target_date) = '' THEN false
    ELSE true
  END as has_target_date,
  
  CASE 
    WHEN TRIM(progress_type) = 'null' OR TRIM(progress_type) = '' OR TRIM(progress_type) = 'NONE' THEN false
    ELSE true
  END as has_metric,
  
  CASE 
    WHEN TRIM(lineage) = 'null' OR TRIM(lineage) = '' THEN false
    ELSE true
  END as has_lineage,
  
  -- OKR health analysis
  CASE 
    WHEN TRIM(name) != 'null' AND TRIM(name) != ''
         AND (TRIM(target_date) != 'null' AND TRIM(target_date) != '')
         AND TRIM(progress_type) = 'ATTACHED_METRIC'
         AND TRIM(owner) != 'null' AND TRIM(owner) != ''
         AND (TRIM(lineage) != 'null' AND TRIM(lineage) != '')
         AND (TRIM(teams) != 'null' AND TRIM(teams) != '')
    THEN 'healthy'
    ELSE 'needs_attention'
  END as health_status,
  
  -- Latest timestamp for version analysis
  PARSE_DATETIME('%Y%m%d%H%M', created_at) as scraped_at

FROM `{project_id}.okrs_dataset.okrs_external`
WHERE 
  -- Filter empty or malformed rows
  goal_key IS NOT NULL 
  AND TRIM(goal_key) != ''
  AND TRIM(goal_key) != 'null';

-- 3. VIEW TO GET ONLY THE LATEST DATA
-- Useful for analysis that only needs the most current version

CREATE OR REPLACE VIEW `{project_id}.okrs_dataset.okrs_latest_view` AS
WITH latest_scrape AS (
  SELECT MAX(PARSE_DATETIME('%Y%m%d%H%M', created_at)) as max_scrape_time
  FROM `{project_id}.okrs_dataset.okrs_external`
  WHERE created_at IS NOT NULL
)
SELECT *
FROM `{project_id}.okrs_dataset.okrs_analysis_view`
WHERE scraped_at = (SELECT max_scrape_time FROM latest_scrape);

-- 4. VIEW FOR EMEA TEAMS ANALYSIS
-- Combines with teams table for EMEA-specific analysis

CREATE OR REPLACE VIEW `{project_id}.okrs_dataset.okrs_emea_analysis_view` AS
SELECT 
  o.*,
  t.team as team_name,
  t.role as team_role
FROM `{project_id}.okrs_dataset.okrs_latest_view` o
LEFT JOIN `{project_id}.okrs_dataset.teams` t
  ON LOWER(TRIM(o.owner)) = LOWER(TRIM(t.name))
WHERE 
  -- Only include OKRs from EMEA team members
  t.team IS NOT NULL; 