# Helper Modules for Main Workflows

This directory contains helper scripts that support the main bash workflows.

## Available Helpers

### 🔧 `config_loader.py`
- **Purpose:** Configuration loader used by all Python scripts
- **Function:** Loads settings from `config.env` and provides team configurations
- **Usage:** Automatically imported by other scripts

## Usage

Helper modules are automatically imported by main workflow scripts and typically don't need manual execution.

For BigQuery analysis tools, see [`tools/bq/README.md`](../tools/bq/README.md). 