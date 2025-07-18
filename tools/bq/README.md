# BigQuery Tools

This directory contains tools specifically for BigQuery-based OKR analysis and data management.

## Available Tools

### 1. `setup_external_table.py`
Creates BigQuery external table and views for OKRs data analysis.

**Usage:**
```bash
# Preview the SQL commands (dry run)
python tools/bq/setup_external_table.py --dry-run

# Execute the setup
python tools/bq/setup_external_table.py
```

**Created Objects:**
- `okrs_external` - External table pointing to Cloud Storage CSV files
- `okrs_analysis_view` - Cleaned and enriched data with calculated fields
- `okrs_latest_view` - Most recent scrape data only
- `okrs_emea_analysis_view` - EMEA team-specific analysis

### `run_okr_health_check_bq.py`
Runs comprehensive OKR health checks using BigQuery, replicating the logic from the original Python scripts.

**Usage:**
```bash
# Run full health check summary
python tools/bq/run_okr_health_check_bq.py

# Detailed malformed OKRs with checkmarks
python tools/bq/run_okr_health_check_bq.py --query 4

# Export results as CSV
python tools/bq/run_okr_health_check_bq.py --format csv > health_report.csv
```

### 4. `analyse_okr_coverage_in_bq.py`
Analyzes corporate objectives coverage and alignment.

**Usage:**
```bash
python tools/bq/analyse_okr_coverage_in_bq.py
```

### 5. `generate_okr_tree_from_bq.py`
Generates CRE team goals tree visualization.

**Usage:**
```bash
python tools/bq/generate_okr_tree_from_bq.py
```

## EntityId Column Support

The BigQuery tables now include an `entity_id` column that contains the Atlassian ARI (Entity ID) for each OKR. This enables:

- **Automated comment posting**: The `entity_id` is used by `tools/post_okr_comments.py` to post comments to malformed OKRs
- **API operations**: Direct integration with Atlassian APIs using the Entity ID
- **Data consistency**: EntityId available across all data processing stages

**Example queries with EntityId:**
```sql
-- Check OKRs with EntityId
SELECT goal_key, entity_id 
FROM `{project_id}.okrs_dataset.okrs_latest_view` 
WHERE entity_id IS NOT NULL 
LIMIT 5;

-- Count OKRs with EntityId
SELECT COUNT(*) as okrs_with_entity_id 
FROM `{project_id}.okrs_dataset.okrs_latest_view` 
WHERE has_entity_id = true;
```

## Configuration

All tools use the same configuration as the main project:

- **Environment variables**: `GOOGLE_CLOUD_PROJECT`, `GCS_BUCKET_NAME`
- **Config file**: `config.env` with BigQuery settings
- **Automatic bucket detection**: Falls back to `${PROJECT_ID}-okrs-data` if not specified

## Benefits

- **Zero storage cost**: Data stays in Cloud Storage
- **Always up-to-date**: Automatically includes new files
- **Fast queries**: Direct SQL access to CSV data
- **Rich analysis**: Pre-built views with health metrics
- **EntityId support**: Full integration with automated comment workflow 