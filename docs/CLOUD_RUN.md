# Cloud Run Jobs Deployment - Detailed Guide

This document provides detailed information for deploying the OKRs scraper to Google Cloud Run Jobs.

> **🔄 Architecture Change**: This project now uses Cloud Run **Jobs** instead of Services. Jobs are perfect for batch processing tasks like OKRs scraping that run periodically and terminate, rather than web services that need to be always available.

## 🔧 Prerequisites

1. **Google Cloud Project** with billing enabled
2. **gcloud CLI** installed and configured
3. **Project Owner or Editor** permissions
4. **Internet connectivity** for API calls

## 🏗️ Infrastructure Setup

### Automated Setup (Recommended)

```bash
# Run the automated infrastructure setup
./setup_cloud_infrastructure.sh
```

This script performs the following actions:

### 1. API Enablement
- Cloud Run API
- Secret Manager API
- Artifact Registry API
- Cloud Storage API
- Cloud Build API
- Cloud Logging API
- IAM Service Account Credentials API

### 2. Service Account Creation
Creates `okrs-scraper-sa@PROJECT_ID.iam.gserviceaccount.com` with minimal required roles:
- `roles/secretmanager.secretAccessor` - Read secrets
- `roles/storage.objectAdmin` - Write to storage bucket
- `roles/run.invoker` - Allow Cloud Run execution
- `roles/logging.logWriter` - Write structured logs

### 3. Infrastructure Resources
- **Artifact Registry**: `europe-west1-docker.pkg.dev/PROJECT_ID/okrs-scraper-repo`
- **Cloud Storage**: `gs://PROJECT_ID-okrs-data`
- **Bucket Security**: Uniform bucket-level access, lifecycle policies
- **Secret Manager**: Automatic secret creation from config.env

## 🚀 Deployment Options

### 1. Automated Script (Recommended)

```bash
# Basic deployment
./deployment/deploy.sh

# Multi-environment deployment
./deployment/deploy.sh -e staging
./deployment/deploy.sh -e development

# Custom configuration
./deployment/deploy.sh --url https://mycompany.atlassian.net --org-id myorg123

# Asynchronous deployment
./deployment/deploy.sh --async --quiet

# Available options
./deployment/deploy.sh --help
```

### 2. Manual Cloud Build

```bash
# Deploy with automatic config loading
gcloud builds submit

# Deploy with configuration overrides
gcloud builds submit \
    --substitutions=ATLASSIAN_BASE_URL=https://mycompany.atlassian.net,ORGANIZATION_ID=myorg123,CLOUD_ID=mycloud456
```

### 3. Manual Docker Deployment

```bash
# Configure Docker for Artifact Registry
gcloud auth configure-docker europe-west1-docker.pkg.dev

# Build and push
docker build -t europe-west1-docker.pkg.dev/PROJECT_ID/okrs-scraper-repo/okrs-scraper:latest .
docker push europe-west1-docker.pkg.dev/PROJECT_ID/okrs-scraper-repo/okrs-scraper:latest

# Deploy to Cloud Run Job (not Service)
gcloud run jobs replace job.yaml --region europe-west1

# Or create job manually
gcloud run jobs create okrs-scraper-job \
    --image europe-west1-docker.pkg.dev/PROJECT_ID/okrs-scraper-repo/okrs-scraper:latest \
    --service-account okrs-scraper-sa@PROJECT_ID.iam.gserviceaccount.com \
    --region europe-west1 \
    --memory 2Gi \
    --cpu 1 \
    --task-timeout 3600 \
    --parallelism 1 \
    --task-count 1 \
    --max-retries 3 \
    --set-env-vars="ATLASSIAN_BASE_URL=https://your-domain.atlassian.net,ORGANIZATION_ID=your-org-id,CLOUD_ID=your-cloud-id,GCS_BUCKET_NAME=PROJECT_ID-okrs-data,GOOGLE_CLOUD_PROJECT=PROJECT_ID"
```

## 🚀 Job Execution

### Manual Execution

```bash
# Execute the job manually
gcloud run jobs execute okrs-scraper-job --region=europe-west1

# Execute with custom environment
gcloud run jobs execute okrs-scraper-job-staging --region=europe-west1
```

### Check Execution Status

```bash
# List recent executions
gcloud run jobs executions list --job=okrs-scraper-job --region=europe-west1

# Get detailed execution info
gcloud run jobs executions describe EXECUTION_NAME --region=europe-west1
```

### View Logs

```bash
# Stream logs from latest execution
gcloud run jobs executions logs EXECUTION_NAME --region=europe-west1

# Follow logs in real-time during execution
gcloud run jobs executions logs EXECUTION_NAME --region=europe-west1 --follow
```

### Automated Scheduling

```bash
# Set up Cloud Scheduler for automatic execution
./setup_scheduler.sh

# Test scheduler manually
gcloud scheduler jobs run okrs-scraper-scheduler --location=europe-west1
```

### Local Testing

```bash
# Test the job locally before deployment
./run_job_locally.sh
```

## ⏰ Cloud Scheduler Integration

### Automated Setup

```bash
# Set up automated scheduling (runs every Monday at 8 AM)
./setup_scheduler.sh
```

### Manual Configuration

```bash
# Create scheduler job manually
gcloud scheduler jobs create http okrs-scraper-scheduler \
    --location=europe-west1 \
    --schedule="0 8 * * MON" \
    --time-zone="Europe/Madrid" \
    --description="Automated OKRs scraping job" \
    --uri="https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT_ID/jobs/okrs-scraper-job:run" \
    --http-method="POST" \
    --oauth-service-account-email="okrs-scheduler-sa@PROJECT_ID.iam.gserviceaccount.com" \
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
```

### Schedule Configuration

Edit `config.env` to customize the schedule:

```bash
# Cron format: 'minute hour day month day_of_week'
SCHEDULE="0 8 * * MON"  # Every Monday at 8 AM
SCHEDULE="0 9 1 * *"    # First day of every month at 9 AM
SCHEDULE="0 */6 * * *"  # Every 6 hours
TIMEZONE="Europe/Madrid"
```

### Management Commands

```bash
# Test scheduler manually
gcloud scheduler jobs run okrs-scraper-scheduler --location=europe-west1

# Check scheduler status
gcloud scheduler jobs describe okrs-scraper-scheduler --location=europe-west1

# Pause/resume scheduler
gcloud scheduler jobs pause okrs-scraper-scheduler --location=europe-west1
gcloud scheduler jobs resume okrs-scraper-scheduler --location=europe-west1

# Delete scheduler
gcloud scheduler jobs delete okrs-scraper-scheduler --location=europe-west1
```

## 📊 BigQuery Integration

### Automatic Table Creation

```bash
# Create BigQuery dataset
bq mk --dataset PROJECT_ID:okrs_dataset

# Create table and import data
bq load \
    --source_format=CSV \
    --skip_leading_rows=1 \
    --replace \
    okrs_dataset.okrs_table \
    gs://PROJECT_ID-okrs-data/okrs/export-*.csv \
    created_at:STRING,Owner:STRING,Goal_Key:STRING,Target_Date:STRING,Name:STRING,Parent_Goal:STRING,Sub_goals:STRING,Tags:STRING,Progress_Type:STRING,Teams:STRING,Start_Date:STRING,Creation_Date:STRING,Lineage:STRING
```

### Scheduled Imports

```bash
# Create a scheduled query to import data automatically
bq query \
    --use_legacy_sql=false \
    --destination_table=okrs_dataset.okrs_table \
    --replace \
    "SELECT * FROM EXTERNAL_QUERY(
        'projects/PROJECT_ID/locations/europe-west1/connections/okrs-connection',
        'SELECT * FROM okrs_table'
    )"
```

## 🔧 Advanced Configuration

### Environment Variables

All environment variables are loaded from `config.env`:

**Application Variables:**
- `ATLASSIAN_BASE_URL` - Atlassian instance URL
- `ORGANIZATION_ID` - Organization ID
- `CLOUD_ID` - Cloud ID
- `BQ_PROJECT` - BigQuery project (optional)
- `BQ_DATASET` - BigQuery dataset name
- `BQ_TABLE` - BigQuery table name
- `BQ_TEAMS_TABLE` - Teams table name
- `CRE_TEAMS` - CRE teams list
- `EXCLUDE_TEAMS` - Teams to exclude
- `US_PEOPLE` - US people to exclude

**Infrastructure Variables:**
- `PROJECT_ID` - Google Cloud Project ID
- `REGION` - Deployment region
- `ARTIFACT_REGISTRY_REPO` - Container registry repository
- `JOB_NAME` - Cloud Run job name
- `ENVIRONMENT` - Environment (production/staging/development)

**Cloud Run Job Configuration:**
- `MEMORY` - Memory allocation per task (e.g., "2Gi")
- `CPU` - CPU allocation per task (e.g., "1")
- `TASK_TIMEOUT` - Maximum time per task (e.g., "3600s")
- `PARALLELISM` - Number of parallel tasks (usually "1")
- `TASK_COUNT` - Total number of tasks (usually "1")
- `MAX_RETRIES` - Maximum retries for failed tasks (e.g., "2")

**Cloud Scheduler Configuration (Optional):**
- `SCHEDULE` - Cron schedule (e.g., "0 8 * * MON")
- `TIMEZONE` - Timezone for schedule (e.g., "Europe/Madrid")

### Cloud Run Jobs vs Services

| Feature | Cloud Run Jobs | Cloud Run Services |
|---------|---------------|-------------------|
| **Purpose** | Batch processing, scripts | Web applications, APIs |
| **Execution** | Run to completion | Always available |
| **Scaling** | Task-based | Request-based |
| **Pricing** | Pay per execution | Pay for running time |
| **HTTP endpoints** | No | Yes |
| **Scheduling** | Cloud Scheduler | Not applicable |
| **Use case** | OKRs scraping | Web backends |

### Security Features

**Secret Manager Integration:**
- Sensitive data stored in Google Cloud Secret Manager
- Automatic secret retrieval during job execution
- No secrets in environment variables or code

**IAM Security:**
- Dedicated service account with minimal privileges
- Bucket-specific storage permissions
- Secret-specific access control

**Network Security:**
- Private container execution
- No public endpoints (since it's a job)
- VPC connector support (if needed)

### Secret Manager Configuration

Sensitive data is automatically stored in Secret Manager:
- `workspace-uuid` - Workspace UUID
- `directory-view-uuid` - Directory view UUID
- `custom-field-uuid` - Custom field UUID
- `atlassian-cookies` - Authentication cookies

### Multi-Environment Deployment

```bash
# Production (default)
./deployment/deploy.sh

# Staging
./deployment/deploy.sh -e staging

# Development
./deployment/deploy.sh -e development
```

Each environment creates separate resources:
- **Production**: `okrs-scraper-job`
- **Staging**: `okrs-scraper-job-staging`
- **Development**: `okrs-scraper-job-development`

## 🔍 Monitoring & Logging

### Cloud Logging

```bash
# View job execution logs
gcloud run jobs executions logs EXECUTION_NAME --region=europe-west1

# List recent executions
gcloud run jobs executions list --job=okrs-scraper-job --region=europe-west1

# View logs from latest execution
LATEST_EXECUTION=$(gcloud run jobs executions list --job=okrs-scraper-job --region=europe-west1 --limit=1 --format="value(metadata.name)")
gcloud run jobs executions logs $LATEST_EXECUTION --region=europe-west1

# View error logs only using Cloud Logging
gcloud logging read "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"okrs-scraper-job\" AND severity>=ERROR" --limit=20
```

### Cloud Build Logs

```bash
# List recent builds
gcloud builds list --limit=10

# View build logs
gcloud builds log BUILD_ID --stream
```

### Performance Monitoring

```bash
# Check job status
gcloud run jobs describe okrs-scraper-job --region=europe-west1

# View job configuration
gcloud run jobs describe okrs-scraper-job --region=europe-west1 --format="table(
  metadata.name,
  spec.template.spec.template.spec.containers[0].image,
  spec.template.spec.template.spec.containers[0].resources.limits.memory,
  spec.template.spec.template.spec.containers[0].resources.limits.cpu
)"

# Check recent execution history
gcloud run jobs executions list --job=okrs-scraper-job --region=europe-west1 --format="table(
  metadata.name,
  status.startTime,
  status.completionTime,
  status.conditions[0].type,
  status.conditions[0].status
)"
```

## 🛠️ Troubleshooting

### Common Issues

#### 1. Build Fails - Missing config.env

**Error:** "config.env file not found"

**Solution:**
```bash
cp config.env.example config.env
# Edit config.env with your actual values
```

#### 2. Deployment Fails - Insufficient Permissions

**Error:** "Permission denied"

**Solution:**
```bash
# Ensure you have the required roles
gcloud projects add-iam-policy-binding PROJECT_ID \
    --member="user:your-email@domain.com" \
    --role="roles/editor"
```

#### 3. Secret Manager Access Issues

**Error:** "Secret not found" or "Access denied"

**Solution:**
```bash
# Re-run infrastructure setup
./setup_cloud_infrastructure.sh

# Verify secrets exist
gcloud secrets list
```

#### 4. Storage Access Issues

**Error:** "Storage bucket not found"

**Solution:**
```bash
# Create bucket manually
gsutil mb gs://PROJECT_ID-okrs-data

# Set proper permissions
gsutil iam ch serviceAccount:okrs-scraper-sa@PROJECT_ID.iam.gserviceaccount.com:roles/storage.objectAdmin gs://PROJECT_ID-okrs-data
```

#### 5. Data Loss - Missing Goals (Fixed in v2025-07-06)

**Symptoms:**
- Cloud Run processing fewer goals than expected
- Error logs showing `'NoneType' object has no attribute 'get'`
- Goals with null fields (owner, progress, etc.) not appearing in output

**Previous Error:** `'NoneType' object has no attribute 'get'`

**Root Cause:** When JSON fields contain `null` values, Python's `dict.get('field', {})` returns `None` instead of the default `{}`, causing subsequent `.get()` calls to fail.

**Solution Applied:** ✅ **Fixed in version 2025-07-06**
- Updated null handling pattern from `goal_data.get('field', {})` to `goal_data.get('field') or {}`
- Applied to all nested field access: `owner`, `progress`, `parentGoal`, `pii`, `subGoals`, `tags`, etc.
- Now achieves perfect parity with bash script (344 goals processed)

**Verification:**
```bash
# Check goal count in latest execution
gcloud run jobs executions logs EXECUTION_NAME --region=europe-west1 | grep "goals processed"

# Should show: "✅ CSV content generated successfully. 344 goals processed"
```

### Debug Commands

```bash
# Check service account
gcloud iam service-accounts describe okrs-scraper-sa@PROJECT_ID.iam.gserviceaccount.com

# Check bucket permissions
gsutil iam get gs://PROJECT_ID-okrs-data

# Check secret access
gcloud secrets versions access latest --secret="workspace-uuid"

# Test job locally (no port needed for jobs)
docker run \
    -e ATLASSIAN_BASE_URL="https://your-domain.atlassian.net" \
    -e ORGANIZATION_ID="your-org-id" \
    -e CLOUD_ID="your-cloud-id" \
    -e GCS_BUCKET_NAME="PROJECT_ID-okrs-data" \
    -e GOOGLE_CLOUD_PROJECT="PROJECT_ID" \
    europe-west1-docker.pkg.dev/PROJECT_ID/okrs-scraper-repo/okrs-scraper:latest
```

## 🔄 Updates & Maintenance

### Updating Secrets

```bash
# Update a secret
gcloud secrets versions add workspace-uuid --data-file=- <<< "new-value"

# The job will automatically pick up the new secret version on next execution
```

### Updating Configuration

```bash
# Update config.env
vim config.env

# Redeploy
./deployment/deploy.sh
```

### Rollback

```bash
# Deploy previous version of the job
gcloud run jobs replace job.yaml --region europe-west1

# Or update the job image directly
gcloud run jobs update okrs-scraper-job \
    --image europe-west1-docker.pkg.dev/PROJECT_ID/okrs-scraper-repo/okrs-scraper:PREVIOUS_SHA \
    --region europe-west1
```

## 📚 Additional Resources

- [Google Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Secret Manager Documentation](https://cloud.google.com/secret-manager/docs)
- [Artifact Registry Documentation](https://cloud.google.com/artifact-registry/docs)
- [Cloud Build Documentation](https://cloud.google.com/build/docs) 