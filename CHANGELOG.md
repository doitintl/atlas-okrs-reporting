# Changelog - Atlas OKRs Reporting

## [2025-07-06] - Enhanced analysis tools with dynamic bucket composition

### ✨ New Features

#### 🚀 Dynamic Cloud Storage bucket composition
- **Enhanced `tools/okrs_sanity_check_scrap_data.py`** and `tools/generate_okr_fix_messages.py`:
  - Automatic bucket name composition using PROJECT_ID
  - Format: `${PROJECT_ID}-okrs-data` (consistent with `cloudbuild.yaml`)
  - Fallback hierarchy: `GCS_BUCKET_NAME` → `GOOGLE_CLOUD_PROJECT` → `gcloud config get-value project`

#### 📊 Improved analysis capabilities
- **Enhanced `--cloud` mode** in both tools:
  - Automatic project detection without hardcoded bucket names
  - Seamless integration with Cloud Storage
  - Proper error handling and temporary file cleanup

### 🛠️ Technical Improvements
- **Portability**: Code works across different GCP projects without modifications
- **Maintainability**: No hardcoded PROJECT_IDs to update
- **Consistency**: Uses same bucket naming convention as Cloud Run deployment
- **Flexibility**: Supports explicit `GCS_BUCKET_NAME` override when needed

### 🎯 Benefits
- **Zero configuration**: Works out-of-the-box in any GCP project
- **Robust fallbacks**: Multiple ways to determine the correct bucket
- **Error prevention**: Clear error messages if project cannot be determined
- **Documentation**: Updated tool help text with optional parameter info

### 📋 Configuration update
- **`config.env`** simplified:
  - Removed hardcoded `GCS_BUCKET_NAME="angel-sandbox-386416-okrs-data"`
  - Added comment explaining optional nature: `# GCS_BUCKET_NAME="project-id-okrs-data"  # Optional: defaults to ${PROJECT_ID}-okrs-data`

---

## [2025-07-06] - Critical bug fix: Null handling in Cloud Run Python implementation

### 🐛 Bug Fixed

#### ⚠️ Issue: Data loss due to null field handling
- **Problem**: Cloud Run Python implementation was losing ~20 goals (324 vs 344) compared to bash script
- **Root cause**: `'NoneType' object has no attribute 'get'` errors when processing goals with null fields
- **Impact**: Missing goals with null values in fields like `owner`, `progress`, `parentGoal`, etc.

#### ✅ Solution: Robust null handling
- **Fixed null field processing** in `src/cloud_run_okrs_job.py`:
  - `owner_info = goal_data.get('owner') or {}` (instead of `goal_data.get('owner', {})`)
  - `progress_info = goal_data.get('progress') or {}` 
  - `parent_goal = goal_data.get('parentGoal') or {}`
  - Similar fixes for `pii`, `subGoals`, `tags`, `teamsV2`, `customFields`, `values`

#### 🎯 Results
- **✅ Perfect parity**: Both bash and Python implementations now process exactly 344 goals
- **✅ No data loss**: All goals with null fields are now processed correctly
- **✅ Error elimination**: Completely resolved `'NoneType' object has no attribute 'get'` errors

### 🛠️ Technical Details
- **Problem pattern**: When JSON field exists but has `null` value, `.get('field', {})` returns `None`, not `{}`
- **Solution pattern**: Use `goal_data.get('field') or {}` to handle null values correctly
- **Affected fields**: `owner`, `progress`, `parentGoal`, `pii`, `subGoals`, `tags`, `teamsV2`, `customFields`, `values`

### 📊 Verification
- **Bash script**: 344 goals processed ✅
- **Cloud Run (before fix)**: 323 goals processed ❌
- **Cloud Run (after fix)**: 344 goals processed ✅

---

## [2025-06-23] - Enhanced aggregation analysis

### ✅ New Features

#### 📊 Aggregation Candidates Analysis
- **Enhanced `okrs_sanity_check_scrap_data.py`** with new table:
  - Identifies parent goals without metrics that have sub-goals
  - Shows count of sub-goals with metrics
  - Recommends goals that can enable `AVERAGE_ROLLUP`
  - Prioritized by aggregation potential

#### 🎯 Key Benefits
- **Easy optimization**: Quick identification of goals ready for automatic metric aggregation
- **Data-driven recommendations**: Clear insight into which parent goals can benefit from rollup metrics
- **Actionable output**: Direct guidance on enabling `AVERAGE_ROLLUP` progress type

### 🛠️ Technical Improvements
- Added `find_aggregation_candidates()` function
- Enhanced hierarchy analysis with parent-child mapping
- Improved data validation for NaN values
- Updated documentation in README.md

---

## [2025-06-23] - Complete parameterization of sensitive data

### ✅ Changes made

#### 🔧 New configuration files
- **`config.env`** - Configuration file with sensitive data (in .gitignore)
- **`config.env.example`** - Example file with documentation
- **`README.md`** - Complete configuration and usage documentation

#### 🔒 Parameterized variables
- `ATLASSIAN_BASE_URL` - Atlassian base URL
- `ORGANIZATION_ID` - Organization ID
- `CLOUD_ID` - Cloud/site ID
- `WORKSPACE_UUID` - Workspace UUID
- `DIRECTORY_VIEW_UUID` - Directory view UUID
- `CUSTOM_FIELD_UUID` - "Lineage" field UUID
- `ATLASSIAN_COOKIES` - Complete authentication cookies

#### 📝 Modified scripts
- **`scrap_okrs.sh`** - Fully parameterized
  - Loads and validates configuration from `config.env`
  - Replaces all hardcoded URLs
  - Uses variables for cookies and UUIDs
  
- **`export_okrs_csv.sh`** - Fully parameterized
  - Loads and validates configuration from `config.env`
  - Replaces hardcoded URL and cookies

#### 🛡️ Enhanced security
- **`.gitignore`** updated:
  - `config.env` (file with sensitive data)
  - `scraped/` (scraping results)
  - `data_snapshots/` (data snapshots)

#### 🔍 Added validations
- Verification of `config.env` existence
- Validation of required variables at startup
- Clear error messages if configuration is missing

### 🎯 Benefits

1. **Security**: Sensitive data is not in source code
2. **Maintainability**: Easy updating of cookies and configuration
3. **Portability**: Each user can have their own configuration
4. **Documentation**: Complete README with step-by-step instructions

### 📋 Migration tasks

To use the parameterized scripts:

1. **Create configuration**:
   ```bash
   cp config.env.example config.env
   ```

2. **Update config.env** with:
   - Valid cookies from your Atlassian session
   - Specific IDs for your organization/workspace

3. **Verify functionality**:
   ```bash
   ./scrap_okrs.sh  # Should load configuration correctly
   ```

### 🔄 Compatibility

- ✅ Existing scripts continue to work the same way
- ✅ Same interface and output
- ✅ New validations and improved error messages 