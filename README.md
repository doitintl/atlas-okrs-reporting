# OKRs Reporting Tool

Tools to extract and analyze Goals data from Atlassian using web scraping and BigQuery analysis.

## 📁 Project Structure

```
okrs-reporting/
├── scrap_okrs.sh              # Main script - complete recursive extraction
├── export_okrs_csv.sh         # Simple script - snapshot extraction
├── teams.csv                  # EMEA teams list
├── config.env                 # Configuration (sensitive - not in git)
├── config.env.example         # Configuration template
├── helpers/
│   ├── add_timestamp_to_csv.py # Helper to add timestamps & load to BigQuery
│   └── config_loader.py        # Configuration loader for all scripts
└── tools/
    ├── analyse_okr_coverage_in_bq.py      # Coverage analysis in BigQuery
    ├── generate_okr_tree_from_bq.py       # Tree generation from BigQuery
    ├── okrs_sanity_check_bq_data.py       # Sanity check BigQuery data
    └── okrs_sanity_check_scrap_data.py    # Sanity check scraped data
```

## 🚀 Initial Setup

### 1. Clone and prepare environment
```bash
git clone <repo-url>
cd okrs-reporting
./setup_venv_uv.sh  # Setup virtual environment with uv and install dependencies from pyproject.toml
```

### 2. Configure credentials
```bash
cp config.env.example config.env
# Edit config.env with your data (see next section)
```

### 3. Get authentication cookies

**Important**: Cookies expire periodically and need to be updated.

1. Open your browser and go to Atlassian Goals
2. Open Developer Tools (F12) → Network tab
3. Reload the page or perform an action
4. Look for a request to `/graphql`
5. Copy the complete `Cookie:` header
6. Paste in `config.env` as `ATLASSIAN_COOKIES` value

### 4. Complete configuration

Edit `config.env` with:

**Atlassian Configuration:**
- **ATLASSIAN_BASE_URL**: Base URL of your Atlassian instance
- **ORGANIZATION_ID**: Your organization ID
- **CLOUD_ID**: Cloud/site ID
- **WORKSPACE_UUID**: Workspace UUID
- **DIRECTORY_VIEW_UUID**: Directory view UUID
- **CUSTOM_FIELD_UUID**: "Lineage" custom field UUID
- **ATLASSIAN_COOKIES**: Authentication cookies (see step 3)

**BigQuery Configuration:**
- **BQ_PROJECT**: GCP project ID (leave empty to use default)
- **BQ_DATASET**: BigQuery dataset name (default: "okrs_dataset")
- **BQ_TABLE**: BigQuery table name (default: "okrs_table")
- **BQ_TEAMS_TABLE**: Teams table name (default: "teams")
- **CRE_TEAMS**: Comma-separated list of CRE team names for analysis tools
- **EXCLUDE_TEAMS**: Comma-separated list of teams to exclude from reports
- **US_PEOPLE**: Comma-separated list of US-based people to exclude from EMEA analysis

## 📊 Main Scripts

### `scrap_okrs.sh` - Complete Recursive Extraction 
DFS (Depth-First Search) algorithm that traverses the entire goals tree:
```bash
./scrap_okrs.sh
```
- ✅ Finds ALL goals (including nested sub-goals)
- 🌳 Complete recursive tree traversal
- 📋 Complete details for each goal
- 🚫 Automatically filters archived goals

### `export_okrs_csv.sh` - Simple Extraction
Quick extraction of initial snapshot:
```bash
./export_okrs_csv.sh
```
- ⚡ Faster but less complete (missing metrics and lineage)
- Requires BigQuery


## 🛠️ Analysis Tools

### Scraped data analysis
```bash
python tools/okrs_sanity_check_scrap_data.py
```

### BigQuery data analysis
```bash
python tools/okrs_sanity_check_bq_data.py
python tools/analyse_okr_coverage_in_bq.py
python tools/generate_okr_tree_from_bq.py
```

## 🔧 Troubleshooting

### ❌ Error 401 "Unauthorized"

**Symptom**: Script fails with `{"code":401,"message":"Unauthorized"}`

**Cause**: Authentication cookies have expired

**Solution**:
1. Open your browser in Atlassian Goals
2. Open Developer Tools (F12) → Network
3. Reload the page or perform any action
4. Look for a GET/POST request to `/graphql`
5. In the request, go to Headers → Request Headers
6. Copy the complete value of the `Cookie:` header
7. Update `config.env`:
   ```bash
   ATLASSIAN_COOKIES='new_cookie_value_here'
   ```
8. Run the script again

**Note**: Cookies expire periodically (every few days/weeks), so this process needs to be repeated when they fail.

### 🐛 Script hangs or takes too long

**Solution**: 
- The script makes 0.3s pauses between requests to avoid overloading the API
- For many goals it can take several minutes
- Use Ctrl+C to cancel if necessary

### 📄 Empty CSV or "null" data

**Possible causes**:
1. Expired cookies (see above)
2. Incorrect IDs in `config.env`
3. Changes in Atlassian API

**Solution**: Verify configuration and cookies

### 🔍 Method comparison

To verify completeness, you can compare results:
```bash
wc -l scraped/export-*_processed.csv  # Recursive method
wc -l export-*.csv                     # Simple method
```

The recursive method should find more goals.

## 📋 Goals Sanity Check

For a goal to be completely healthy it needs:
- ✅ Descriptive name
- 📅 Target date (monthly preferred)
- 📈 Progress metric (manual or automatic)
- 👤 Single owner
- 🌳 Lineage (dot notation e.g., doit.cs.cre.emea.south.es-pod-1)
- 🏷️ Tags
- 📌 Start date (optional but recommended)
- 🧭 Goal owner's team name

## 🎯 EMEA Teams Only

All tools focus exclusively on goals from EMEA team members according to `teams.csv` and `okrs_dataset.teams` table.

## 📝 Logs and Debugging

Scripts include detailed logging:
- URLs and variables before executing curl
- Success/failure result of each request
- Size of generated files
- Error codes if they fail

For additional debugging, you can uncomment the line:
```bash
# rm -rf "$TEMP_DIR"  # Keep temporary files for debugging
``` 