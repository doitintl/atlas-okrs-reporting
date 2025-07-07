# BigQuery Tools

This directory contains tools specifically for BigQuery-based OKR analysis and data management.

## Scripts

### `setup_external_table.py`
Sets up BigQuery external table pointing to OKR CSV files in Cloud Storage.

**Usage:**
```bash
# Dry run to preview changes
python tools/bq/setup_external_table.py --dry-run

# Execute setup
python tools/bq/setup_external_table.py
```

**Creates:**
- `okrs_external` - External table pointing to Cloud Storage
- `okrs_analysis_view` - Cleaned and enriched data view
- `okrs_latest_view` - Most recent scrape data only
- `okrs_emea_analysis_view` - EMEA team analysis view

### `run_okr_health_check_bq.py`
Runs comprehensive OKR health checks using BigQuery, replicating the logic from the original Python scripts.

**Usage:**
```bash
# Run full health check summary
python tools/bq/run_okr_health_check_bq.py

# Run specific query by number (1-9)
python tools/bq/run_okr_health_check_bq.py --query 4

# Output in different formats
python tools/bq/run_okr_health_check_bq.py --format json
python tools/bq/run_okr_health_check_bq.py --format csv
```

**Available Queries:**
1. Overall health summary
2. Health by team 
3. Progress type distribution
4. Malformed OKRs details with checkmarks
5. Parent goals without metrics (aggregation candidates)
6. People without OKRs
7. Data freshness check
8. Comparative health analysis across time
9. Summary statistics

## Benefits

- **Zero storage cost** - Data stays in Cloud Storage
- **Real-time analysis** - Always reflects latest CSV files
- **Fast queries** - SQL performance vs Python processing
- **Scalable** - Handles growing data volumes efficiently
- **Compatible** - Same analysis logic as existing Python tools

## Dependencies

- Google Cloud BigQuery
- Cloud Storage with OKR CSV files
- Project configuration in `config.env` 