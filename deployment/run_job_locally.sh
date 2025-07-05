#!/bin/bash

# Local execution script for OKRs Scraper Job
# This script allows you to test the job locally before deploying

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Running OKRs Scraper Job Locally${NC}"
echo -e "${BLUE}This script will execute the job using your local environment${NC}"
echo

# Check if ../config.env exists
if [ ! -f ../config.env ]; then
    echo -e "${RED}❌ ../config.env file not found${NC}"
    echo "Please create ../config.env from ../config.env.example and configure it"
    exit 1
fi

# Load configuration
echo -e "${BLUE}📖 Loading configuration from ../config.env...${NC}"
source ../config.env

# Check if virtual environment is active
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment not detected${NC}"
    echo "Activating virtual environment..."
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    elif [ -d "venv" ]; then
        source venv/bin/activate
    else
        echo -e "${RED}❌ No virtual environment found${NC}"
        echo "Please create a virtual environment first:"
        echo "  python -m venv .venv"
        echo "  source .venv/bin/activate"
        echo "  pip install -r requirements.txt"
        exit 1
    fi
fi

# Check if required dependencies are installed
echo -e "${BLUE}📋 Checking dependencies...${NC}"
if ! python -c "import google.cloud.storage, google.cloud.secretmanager, requests, pandas" 2>/dev/null; then
    echo -e "${RED}❌ Missing dependencies${NC}"
    echo "Please install dependencies:"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Validate required environment variables
echo -e "${BLUE}🔍 Validating configuration...${NC}"
required_vars=(
    "ATLASSIAN_BASE_URL"
    "ORGANIZATION_ID"
    "CLOUD_ID"
    "WORKSPACE_UUID"
    "DIRECTORY_VIEW_UUID"
    "CUSTOM_FIELD_UUID"
    "ATLASSIAN_COOKIES"
    "GOOGLE_CLOUD_PROJECT"
    "GCS_BUCKET_NAME"
)

missing_vars=()
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -gt 0 ]; then
    echo -e "${RED}❌ Missing required environment variables:${NC}"
    printf "   - %s\n" "${missing_vars[@]}"
    echo "Please update ../config.env with the missing variables"
    exit 1
fi

# Set environment variables for local execution
export ATLASSIAN_BASE_URL
export ORGANIZATION_ID
export CLOUD_ID
export GOOGLE_CLOUD_PROJECT
export GCS_BUCKET_NAME

# Note: For local execution, secrets should be set directly in ../config.env
# In production, these come from Secret Manager
export WORKSPACE_UUID
export DIRECTORY_VIEW_UUID
export CUSTOM_FIELD_UUID
export ATLASSIAN_COOKIES

echo -e "${GREEN}✅ Configuration validated${NC}"
echo

# Execute the job
echo -e "${YELLOW}🏃 Executing OKRs Scraper Job...${NC}"
echo "============================================"
echo

# Check if the job file exists
if [ ! -f "cloud_run_okrs_job.py" ]; then
    echo -e "${RED}❌ cloud_run_okrs_job.py not found${NC}"
    echo "Please ensure the job file exists in the current directory"
    exit 1
fi

# Run the job
python cloud_run_okrs_job.py

echo
echo "============================================"
echo -e "${GREEN}✅ Job execution completed${NC}"
echo
echo -e "${YELLOW}💡 To deploy to Cloud Run Jobs:${NC}"
echo "  ./deploy.sh"
echo
echo -e "${YELLOW}📋 To check Cloud Storage:${NC}"
echo "  gsutil ls gs://${GCS_BUCKET_NAME}/okrs/" 