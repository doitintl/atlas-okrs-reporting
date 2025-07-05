#!/bin/bash

# Cloud Scheduler Setup Script for OKRs Scraper Job
# This script creates a scheduled job to run the OKRs scraper automatically

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}⏰ Setting up Cloud Scheduler for OKRs Scraper Job${NC}"
echo -e "${BLUE}This script will create a scheduled job to run the scraper automatically${NC}"
echo

# Check if gcloud is installed and configured
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}❌ gcloud CLI is not installed${NC}"
    echo "Please install gcloud CLI: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Get project configuration
PROJECT_ID=$(gcloud config get-value project)
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}❌ No project configured in gcloud${NC}"
    echo "Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

# Load configuration
if [ ! -f "../config.env" ]; then
    echo -e "${RED}❌ ../config.env file not found${NC}"
    echo "Please create ../config.env from ../config.env.example and configure it"
    exit 1
fi

source ../config.env

# Configuration
REGION="${REGION:-europe-west1}"
JOB_NAME="${JOB_NAME:-okrs-scraper-job}"
SCHEDULER_NAME="okrs-scraper-scheduler"
SCHEDULE="${SCHEDULE:-0 8 * * MON}"  # Every Monday at 8 AM
TIMEZONE="${TIMEZONE:-Europe/Madrid}"
DESCRIPTION="Automated OKRs scraping job - executes weekly"

echo -e "${BLUE}📋 Configuration:${NC}"
echo "  Project: $PROJECT_ID"
echo "  Region: $REGION"
echo "  Job Name: $JOB_NAME"
echo "  Scheduler Name: $SCHEDULER_NAME"
echo "  Schedule: $SCHEDULE ($TIMEZONE)"
echo "  Description: $DESCRIPTION"
echo

# Confirm before continuing
read -p "Continue with scheduler setup? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}⏹️  Setup cancelled${NC}"
    exit 0
fi

echo -e "${YELLOW}🔌 Step 1: Enabling Cloud Scheduler API...${NC}"
gcloud services enable cloudscheduler.googleapis.com --project="$PROJECT_ID"

echo -e "${YELLOW}🔐 Step 2: Creating service account for scheduler...${NC}"
SCHEDULER_SA_NAME="okrs-scheduler-sa"
SCHEDULER_SA_EMAIL="$SCHEDULER_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

# Check if service account already exists
if gcloud iam service-accounts describe "$SCHEDULER_SA_EMAIL" --project="$PROJECT_ID" &>/dev/null; then
    echo -e "${YELLOW}⚠️  Service account already exists, skipping creation${NC}"
else
    # Create service account
    gcloud iam service-accounts create "$SCHEDULER_SA_NAME" \
        --display-name="OKRs Scheduler Service Account" \
        --description="Service account for Cloud Scheduler to execute OKRs scraper job" \
        --project="$PROJECT_ID"
    
    echo -e "${GREEN}✅ Service account created${NC}"
fi

echo -e "${YELLOW}🏷️  Step 3: Assigning required IAM roles...${NC}"
# Grant permission to invoke Cloud Run jobs
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SCHEDULER_SA_EMAIL" \
    --role="roles/run.invoker" \
    --condition=None

echo -e "${YELLOW}⏰ Step 4: Creating Cloud Scheduler job...${NC}"

# Check if scheduler job already exists
if gcloud scheduler jobs describe "$SCHEDULER_NAME" --location="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    echo -e "${YELLOW}⚠️  Scheduler job already exists, updating...${NC}"
    
    # Update existing job
    gcloud scheduler jobs update http "$SCHEDULER_NAME" \
        --location="$REGION" \
        --schedule="$SCHEDULE" \
        --time-zone="$TIMEZONE" \
        --description="$DESCRIPTION" \
        --uri="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$JOB_NAME:run" \
        --http-method="POST" \
        --oauth-service-account-email="$SCHEDULER_SA_EMAIL" \
        --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
else
    # Create new job
    gcloud scheduler jobs create http "$SCHEDULER_NAME" \
        --location="$REGION" \
        --schedule="$SCHEDULE" \
        --time-zone="$TIMEZONE" \
        --description="$DESCRIPTION" \
        --uri="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$JOB_NAME:run" \
        --http-method="POST" \
        --oauth-service-account-email="$SCHEDULER_SA_EMAIL" \
        --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
fi

echo -e "${GREEN}✅ Cloud Scheduler setup completed!${NC}"
echo
echo -e "${BLUE}📝 Summary:${NC}"
echo "  📅 Schedule: $SCHEDULE ($TIMEZONE)"
echo "  🔗 Scheduler Job: $SCHEDULER_NAME"
echo "  🚀 Target Job: $JOB_NAME"
echo "  🔐 Service Account: $SCHEDULER_SA_EMAIL"
echo
echo -e "${YELLOW}🔧 Management commands:${NC}"
echo "  # Test the scheduler manually:"
echo "  gcloud scheduler jobs run $SCHEDULER_NAME --location=$REGION"
echo
echo "  # Check scheduler job status:"
echo "  gcloud scheduler jobs describe $SCHEDULER_NAME --location=$REGION"
echo
echo "  # List recent executions:"
echo "  gcloud run jobs executions list --job=$JOB_NAME --region=$REGION"
echo
echo "  # View logs:"
echo "  gcloud run jobs executions logs <EXECUTION_NAME> --region=$REGION"
echo
echo "  # Pause/resume scheduler:"
echo "  gcloud scheduler jobs pause $SCHEDULER_NAME --location=$REGION"
echo "  gcloud scheduler jobs resume $SCHEDULER_NAME --location=$REGION"
echo
echo "  # Delete scheduler (if needed):"
echo "  gcloud scheduler jobs delete $SCHEDULER_NAME --location=$REGION"
echo
echo -e "${GREEN}✨ OKRs scraper will now run automatically according to the schedule!${NC}"
echo -e "${BLUE}💡 You can modify the schedule by editing SCHEDULE variable in ../config.env${NC}"
echo -e "${BLUE}   Format: 'minute hour day month day_of_week' (cron format)${NC}"
echo -e "${BLUE}   Examples:${NC}"
echo -e "${BLUE}     - '0 8 * * MON' = Every Monday at 8 AM${NC}"
echo -e "${BLUE}     - '0 9 1 * *' = First day of every month at 9 AM${NC}"
echo -e "${BLUE}     - '0 */6 * * *' = Every 6 hours${NC}" 