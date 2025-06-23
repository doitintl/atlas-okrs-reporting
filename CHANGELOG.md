# Changelog - Atlas OKRs Reporting

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