# Independent Tools for OKRs Analysis

This directory contains standalone analysis tools that operate independently with their own output and functionality.

## Available Tools



### ✅ `okrs_sanity_check_scrap_data.py`
- **Purpose:** Sanity check analysis of OKRs health using scraped data
- **Output:** Detailed health reports with statistics by team and issue breakdown from scraped CSV data
- **Usage:** Independent analysis tool for OKR quality assessment from scrap_okrs.sh output

## Usage

Each tool can be executed independently:

```bash
cd tools/
python analyse_okr_coverage_in_bq.py
python generate_okr_tree_from_bq.py
python okrs_sanity_check_bq_data.py
python okrs_sanity_check_scrap_data.py
```

These tools are separate from the main workflow scripts (`scrap_okrs.sh` and `export_OKRS_CSV.sh`) and provide additional analysis capabilities. 