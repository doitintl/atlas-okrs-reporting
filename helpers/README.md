# Helper Modules for Main Workflows

This directory contains helper scripts that support the main bash workflows.

## Available Helpers

### 📝 `add_timestamp_to_csv.py`
- **Purpose:** Adds timestamp columns to CSV files
- **Output:** Processed CSV files with timestamps
- **Usage:** Called by `export_OKRS_CSV.sh` workflow
- **Input:** Raw CSV export from Atlassian
- **Output:** CSV with added timestamp information

## Usage

These helpers are automatically called by the main workflow scripts and typically don't need to be run manually.

```bash
# Called automatically by export_OKRS_CSV.sh
python helpers/add_timestamp_to_csv.py input.csv
```

These helpers are dependencies of the main workflows, unlike tools which are independent. 