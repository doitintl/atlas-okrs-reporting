# OKRs Reporting Tool

A comprehensive tool to extract and analyze Goals data from Atlassian using web scraping and BigQuery analysis.

## 🚀 Quick Start

### 🆕 Cloud Run Version (Recommended)

Modern, scalable version with enterprise-grade security and automation:

```bash
# 1. Setup infrastructure with security best practices
./deployment/setup_cloud_infrastructure.sh

# 2. Configure application settings
cp config.env.example config.env
# Edit config.env with your Atlassian credentials and infrastructure settings

# 3. Deploy with automated script
./deployment/deploy.sh
```

**✨ Features:**
- 🔐 **Automated Secret Management** - Reads config.env and creates secrets automatically
- 🏗️ **Infrastructure as Code** - Complete setup with one script
- 🚀 **Cloud Build Integration** - Automated deployment with security best practices
- 📊 **In-memory Processing** - No temporary files, direct Cloud Storage upload
- 🔄 **Multi-environment Support** - Production, staging, development
- 🔒 **Enterprise Security** - Service accounts, Secret Manager, Artifact Registry

### 📊 Original Bash Scripts

The original bash-based extraction tools are still available for local use:

```bash
# Setup
./scripts/setup_venv_uv.sh
cp config.env.example config.env
# Edit config.env with your credentials

# Extract OKRs (complete recursive extraction)
./scripts/scrap_okrs.sh
```

## 📁 Project Structure

```
okrs-reporting/
├── 🆕 CLOUD RUN VERSION
│   ├── src/                             # Source code
│   │   └── cloud_run_okrs_job.py        # Main Cloud Run job application
│   └── deployment/                      # Deployment configuration
│       ├── setup_cloud_infrastructure.sh  # Infrastructure setup with security
│       ├── deploy.sh                    # Convenient deployment script  
│       ├── cloudbuild.yaml             # Automated Cloud Build configuration
│       ├── Dockerfile                  # Container configuration
│       └── .cloudignore                # Cloud Build optimization
├── 📊 ORIGINAL BASH SCRIPTS
│   └── scripts/                         # Original bash scripts
│       ├── scrap_okrs.sh               # Complete recursive extraction (DFS algorithm)
│       ├── export_okrs_csv.sh          # Simple snapshot extraction
│       └── setup_venv_uv.sh            # Virtual environment setup
├── 📊 DATA
│   └── data/                            # Team configuration and data
│       └── teams.csv                   # EMEA teams list
└── 📚 DOCUMENTATION
    └── docs/                            # Detailed documentation
        └── CLOUD_RUN.md                # Cloud Run deployment guide
├── 🔧 CONFIGURATION
│   ├── config.env                 # Main configuration (not in git)
│   └── config.env.example         # Configuration template
├── helpers/
│   ├── add_timestamp_to_csv.py    # Helper to add timestamps & load to BigQuery
│   └── config_loader.py           # Configuration loader for all scripts
└── tools/
    ├── analyse_okr_coverage_in_bq.py      # Coverage analysis in BigQuery
    ├── generate_okr_fix_messages.py       # Generate Slack messages for OKR fixes
    ├── generate_okr_tree_from_bq.py       # Tree generation from BigQuery
    ├── okrs_sanity_check_bq_data.py       # Sanity check BigQuery data
    └── okrs_sanity_check_scrap_data.py    # Sanity check scraped data
```

## 🔧 Configuration

### Single Configuration File

All versions now use a unified `config.env` file:

```bash
cp config.env.example config.env
```

**Required Configuration:**
- **ATLASSIAN_BASE_URL**: Your Atlassian instance URL
- **ORGANIZATION_ID**: Organization ID from Atlassian URLs
- **CLOUD_ID**: Cloud/site ID
- **WORKSPACE_UUID**: Workspace UUID
- **DIRECTORY_VIEW_UUID**: Directory view UUID
- **CUSTOM_FIELD_UUID**: "Lineage" custom field UUID
- **ATLASSIAN_COOKIES**: Authentication cookies (see below)

**Optional Configuration:**
- **BigQuery settings**: Project, dataset, table names
- **Team filtering**: CRE teams, excluded teams, US people
- **Cloud Run settings**: Region, memory, CPU, scaling

### 🍪 Getting Authentication Cookies

**Important**: Cookies expire periodically and need to be updated.

1. Open your browser and go to Atlassian Goals
2. Open Developer Tools (F12) → Network tab
3. Reload the page or perform an action
4. Look for a request to `/graphql`
5. Copy the complete `Cookie:` header
6. Paste in `config.env` as `ATLASSIAN_COOKIES` value

## 🚀 Cloud Run Deployment

### Automated Deployment (Recommended)

```bash
# Deploy to production
./deployment/deploy.sh

# Deploy to staging
./deployment/deploy.sh -e staging

# Deploy with custom settings
./deployment/deploy.sh --url https://mycompany.atlassian.net --org-id myorg123

# Deploy asynchronously
./deployment/deploy.sh --async --quiet

# See all options
./deployment/deploy.sh --help
```

### Manual Cloud Build

```bash
# Deploy with automatic config loading
gcloud builds submit

# Deploy with overrides
gcloud builds submit \
    --substitutions=ATLASSIAN_BASE_URL=https://mycompany.atlassian.net,ORGANIZATION_ID=myorg123
```

### Cloud Run Usage

```bash
# Health check
curl https://your-service-url/

# Execute scraping
curl -X POST https://your-service-url/scrape
```

**Successful Response:**
```json
{
  "status": "success",
  "message": "Scraping completed successfully",
  "data": {
    "public_url": "https://storage.googleapis.com/your-bucket/okrs/export-202507052015_processed.csv",
    "filename": "okrs/export-202507052015_processed.csv",
    "total_okrs": 150,
    "timestamp": "2025-07-05T20:15:00"
  }
}
```

## 📊 Original Bash Scripts

### Complete Recursive Extraction

```bash
./scripts/scrap_okrs.sh
```

**Features:**
- ✅ **DFS Algorithm** - Finds ALL goals including nested sub-goals
- 🌳 **Complete Tree Traversal** - Recursive exploration of goal hierarchy
- 📋 **Complete Details** - All goal information and metadata
- 🚫 **Automatic Filtering** - Excludes archived goals

### Simple Snapshot Extraction

```bash
./scripts/export_okrs_csv.sh
```

**Features:**
- ⚡ **Faster** - Quick snapshot extraction
- 📊 **Basic Data** - Less complete than recursive extraction
- 🔄 **BigQuery Ready** - Directly uploads to BigQuery

## 🛠️ Analysis Tools

### Scraped Data Analysis

```bash
# Analyze local CSV files
python tools/okrs_sanity_check_scrap_data.py
python tools/okrs_sanity_check_scrap_data.py --file scraped/specific_export.csv

# Analyze latest file from Cloud Storage
python tools/okrs_sanity_check_scrap_data.py --cloud
```

**Enhanced OKRs Sanity Check:**
- ✅ **Health Status** - By team with totals
- 📊 **Progress Distribution** - Healthy vs malformed analysis
- 🎯 **Aggregation Candidates** - Parent goals without metrics
- 👥 **People Without OKRs** - By team analysis
- 📋 **Detailed Breakdown** - Malformed OKRs analysis
- ☁️ **Cloud Mode** - Automatically downloads latest file from Cloud Storage

### Generate Slack Messages

```bash
# Generate messages from local CSV files
python tools/generate_okr_fix_messages.py
python tools/generate_okr_fix_messages.py --file scraped/specific_export.csv

# Generate messages from latest Cloud Storage file
python tools/generate_okr_fix_messages.py --cloud
```

**Personalized OKR Fix Messages:**
- 📤 **Individual Messages** - Ready-to-send Slack messages
- 📊 **Table Format** - Clear breakdown of missing fields
- 🎯 **Emoji Indicators** - Visual symbols for each missing field
- 💾 **Auto-save** - Messages saved to `okr_fix_messages.txt`
- ☁️ **Cloud Mode** - Automatically downloads latest file from Cloud Storage

**Example Message:**
```
Hi John! 👋
Your OKRs need some updates in Atlas:
| OKR Name                  | Missing  |
|---------------------------|----------|
| Improve system uptime     | 👥 📈     |
Legend: 📅 Target Date | 👥 Teams | 🔗 Parent Goal | 👤 Owner | 📈 Metric | 🌳 Lineage
Please update when you can. Thanks! 🙏
```

#### ☁️ Cloud Mode Configuration

**Dynamic Bucket Composition:**
- Tools automatically compose bucket name as `${PROJECT_ID}-okrs-data`
- Consistent with Cloud Run deployment in `cloudbuild.yaml`
- No hardcoded PROJECT_IDs required

**Fallback Hierarchy:**
1. `GCS_BUCKET_NAME` environment variable (if set)
2. `GOOGLE_CLOUD_PROJECT` environment variable
3. `gcloud config get-value project` command

**Usage:**
```bash
# Works out-of-the-box in any GCP project
python tools/okrs_sanity_check_scrap_data.py --cloud

# Override bucket name if needed
export GCS_BUCKET_NAME="custom-bucket-name"
python tools/okrs_sanity_check_scrap_data.py --cloud
```

### BigQuery Analysis

```bash
python tools/okrs_sanity_check_bq_data.py
python tools/analyse_okr_coverage_in_bq.py
python tools/generate_okr_tree_from_bq.py
```

## 🔧 Troubleshooting

### ❌ Error 401 "Unauthorized"

**Cause**: Authentication cookies have expired

**Solution**:
1. Open browser in Atlassian Goals
2. Open Developer Tools (F12) → Network
3. Reload page or perform action
4. Find GET/POST request to `/graphql`
5. Copy complete `Cookie:` header value
6. Update `config.env` with new cookies
7. Run script again

### 🐛 Script Hangs or Takes Too Long

**Cause**: Script makes 0.3s pauses between requests to avoid API overload

**Solution**: 
- For many goals, expect several minutes execution time
- Use Ctrl+C to cancel if necessary
- Check network connectivity and API responses

### 📄 Empty CSV or "null" Data

**Possible Causes**:
- Expired authentication cookies
- Invalid UUIDs in configuration
- Network connectivity issues
- API rate limiting

**Solution**:
- Update authentication cookies
- Verify UUIDs in Atlassian URLs
- Check network connectivity
- Wait and retry if rate limited

## 🔒 Security & Best Practices

### Cloud Run Security Features

- 🔐 **Secret Manager** - Sensitive data encrypted at rest and in transit
- 👤 **Service Account** - Dedicated account with minimal required privileges
- 🗂️ **Artifact Registry** - Modern, secure container image storage
- 🪣 **Bucket Security** - Uniform bucket-level access with IAM restrictions
- 🔍 **Audit Logging** - Complete audit trail of all resource access
- 🏷️ **Resource Labeling** - Proper tagging for governance and cost tracking

### Infrastructure Created

The setup script automatically creates:
- **Service Account**: `okrs-scraper-sa@PROJECT_ID.iam.gserviceaccount.com`
- **Artifact Registry**: `europe-west1-docker.pkg.dev/PROJECT_ID/okrs-scraper-repo`
- **Cloud Storage**: `gs://PROJECT_ID-okrs-data`
- **IAM Roles**: Minimal required permissions only

## 📚 Documentation

- 📖 **docs/CLOUD_RUN.md** - Detailed Cloud Run documentation
- 📋 **tools/README.md** - Analysis tools documentation
- 🔧 **helpers/README.md** - Helper utilities documentation
- 📝 **CHANGELOG.md** - Project history and changes

## 🎯 Team Context

This tool is specifically designed for **EMEA team analysis**. All analysis focuses on teams defined in `data/teams.csv` and the `okrs_dataset.teams` table.

**Goal Health Check Requirements:**
- ✅ **Descriptive Name**
- 📅 **Due Date** (monthly preferred)
- 📈 **Progress Metric** (manual or automatic)
- 👤 **Single Owner**
- 🌳 **Lineage** (dot notation: e.g., doit.cs.cre.emea.south.es-pod-1)
- 🏷️ **Tags**
- 📌 **Start Date** (optional but recommended)
- 🧭 **Team Name** as team field 