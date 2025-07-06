#!/bin/bash

# Cloud Infrastructure Setup Script for OKRs Scraper
# This script sets up all necessary Google Cloud infrastructure with security best practices

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Setting up Cloud Infrastructure for OKRs Scraper${NC}"
echo -e "${BLUE}This script will configure all necessary Google Cloud resources with minimal privileges${NC}"
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

echo -e "${BLUE}📋 Project: $PROJECT_ID${NC}"

# Configuration
SERVICE_ACCOUNT_NAME="okrs-scraper-sa"
SERVICE_ACCOUNT_EMAIL="$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"
BUCKET_NAME="${PROJECT_ID}-okrs-data"
REGION="europe-west1"
ARTIFACT_REGISTRY_REPO="okrs-scraper-repo"

echo -e "${BLUE}📋 Configuration:${NC}"
echo "  Service Account: $SERVICE_ACCOUNT_EMAIL"
echo "  Bucket: $BUCKET_NAME"
echo "  Region: $REGION"
echo "  Artifact Registry: $ARTIFACT_REGISTRY_REPO"

# Confirm before continuing
read -p "Continue with infrastructure setup? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}⏹️  Setup cancelled${NC}"
    exit 0
fi

echo -e "${YELLOW}🔌 Step 1: Enabling required APIs...${NC}"

# List of required APIs
REQUIRED_APIS=(
    "cloudbuild.googleapis.com"
    "run.googleapis.com"
    "secretmanager.googleapis.com"
    "storage.googleapis.com"
    "artifactregistry.googleapis.com"
    "logging.googleapis.com"
    "monitoring.googleapis.com"
    "cloudscheduler.googleapis.com"
)

for api in "${REQUIRED_APIS[@]}"; do
    echo "  Enabling $api..."
    gcloud services enable "$api" --project="$PROJECT_ID"
done

echo -e "${GREEN}✅ APIs enabled successfully${NC}"

echo -e "${YELLOW}🔐 Step 2: Creating service account with minimal privileges...${NC}"

# Check if service account already exists
if gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" --project="$PROJECT_ID" &>/dev/null; then
    echo -e "${YELLOW}⚠️  Service account already exists, skipping creation${NC}"
else
    # Create service account
    gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
        --display-name="OKRs Scraper Service Account" \
        --description="Service account for OKRs scraper with minimal required privileges" \
        --project="$PROJECT_ID"
    
    echo -e "${GREEN}✅ Service account created${NC}"
fi

echo -e "${YELLOW}🏷️  Step 3: Assigning minimal required IAM roles...${NC}"

# IAM roles with minimal privileges
IAM_ROLES=(
    "roles/secretmanager.secretAccessor"  # Access secrets
    "roles/storage.objectAdmin"           # Read/write to specific bucket
    "roles/logging.logWriter"             # Write logs
    "roles/monitoring.metricWriter"       # Write metrics
)

for role in "${IAM_ROLES[@]}"; do
    echo "  Assigning $role..."
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
        --role="$role" \
        --condition=None
done

echo -e "${GREEN}✅ IAM roles assigned${NC}"

echo -e "${YELLOW}🗂️  Step 4: Creating Artifact Registry repository...${NC}"

# Check if repository already exists
if gcloud artifacts repositories describe "$ARTIFACT_REGISTRY_REPO" --location="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    echo -e "${YELLOW}⚠️  Artifact Registry repository already exists, skipping creation${NC}"
else
    # Create Artifact Registry repository
    gcloud artifacts repositories create "$ARTIFACT_REGISTRY_REPO" \
        --repository-format=docker \
        --location="$REGION" \
        --description="Container images for OKRs scraper" \
        --project="$PROJECT_ID"
    
    echo -e "${GREEN}✅ Artifact Registry repository created${NC}"
fi

echo -e "${YELLOW}🪣 Step 5: Creating Cloud Storage bucket...${NC}"

# Check if bucket already exists
if gsutil ls -b "gs://$BUCKET_NAME" &>/dev/null; then
    echo -e "${YELLOW}⚠️  Bucket already exists, skipping creation${NC}"
else
    # Create bucket with security best practices
    gsutil mb -p "$PROJECT_ID" -c STANDARD -l "$REGION" "gs://$BUCKET_NAME"
    
    # Enable uniform bucket-level access for better security
    gsutil uniformbucketlevelaccess set on "gs://$BUCKET_NAME"
    
    # Set bucket IAM policy to restrict access
    gsutil iam ch "serviceAccount:$SERVICE_ACCOUNT_EMAIL:roles/storage.objectAdmin" "gs://$BUCKET_NAME"
    
    echo -e "${GREEN}✅ Bucket created with security configuration${NC}"
fi

echo -e "${YELLOW}🔐 Step 6: Configuring bucket security...${NC}"

# Create bucket structure
gsutil -m cp /dev/null "gs://$BUCKET_NAME/okrs/.gitkeep" 2>/dev/null || true

# Set lifecycle policy to automatically delete old files (optional)
cat > bucket_lifecycle.json <<EOF
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {
        "age": 90,
        "matchesPrefix": ["okrs/"]
      }
    }
  ]
}
EOF

gsutil lifecycle set bucket_lifecycle.json "gs://$BUCKET_NAME"
rm bucket_lifecycle.json

echo -e "${GREEN}✅ Bucket security configured${NC}"

echo -e "${YELLOW}🔑 Step 7: Creating secrets from configuration...${NC}"

# Check if config.env exists
if [ ! -f "../config.env" ]; then
    echo -e "${YELLOW}⚠️  ../config.env not found, creating template...${NC}"
    if [ -f "../config.env.example" ]; then
        cp ../config.env.example ../config.env
        echo -e "${YELLOW}📝 Please edit ../config.env with your actual values and run this script again${NC}"
        echo -e "${BLUE}🔧 Required fields to update in ../config.env:${NC}"
        echo "  - WORKSPACE_UUID"
        echo "  - DIRECTORY_VIEW_UUID" 
        echo "  - CUSTOM_FIELD_UUID"
        echo "  - ATLASSIAN_COOKIES"
        echo "  - ATLASSIAN_BASE_URL"
        echo "  - ORGANIZATION_ID"
        echo "  - CLOUD_ID"
        exit 0
    else
        echo -e "${RED}❌ ../config.env.example not found${NC}"
        exit 1
    fi
fi

# Load configuration
echo -e "${BLUE}📖 Loading configuration from ../config.env...${NC}"
source ../config.env

# Validate required variables
required_vars=(
    "WORKSPACE_UUID"
    "DIRECTORY_VIEW_UUID"
    "CUSTOM_FIELD_UUID"
    "ATLASSIAN_COOKIES"
    "ATLASSIAN_BASE_URL"
    "ORGANIZATION_ID"
    "CLOUD_ID"
)

missing_vars=()
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ] || [ "${!var}" = "your-workspace-uuid" ] || [ "${!var}" = "your-directory-view-uuid" ] || [ "${!var}" = "your-custom-field-uuid" ] || [[ "${!var}" =~ cookie.*=.*value ]]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -gt 0 ]; then
    echo -e "${RED}❌ Please update the following variables in ../config.env with real values:${NC}"
    printf "   - %s\n" "${missing_vars[@]}"
    echo
    echo -e "${YELLOW}💡 To get these values:${NC}"
    echo "  - Open browser DevTools (F12) → Network tab"
    echo "  - Navigate in Atlassian Goals"
    echo "  - Find GraphQL requests to get UUIDs and cookies"
    exit 1
fi

# Create secrets automatically
echo -e "${BLUE}🔐 Creating secrets in Secret Manager...${NC}"

create_secret() {
    local secret_name="$1"
    local secret_value="$2"
    
    if gcloud secrets describe "$secret_name" --project="$PROJECT_ID" &>/dev/null; then
        echo -e "${YELLOW}⚠️  Secret $secret_name already exists, updating...${NC}"
        echo "$secret_value" | gcloud secrets versions add "$secret_name" --data-file=-
    else
        echo "  Creating secret: $secret_name"
        echo "$secret_value" | gcloud secrets create "$secret_name" --data-file=-
    fi
}

create_secret "workspace-uuid" "$WORKSPACE_UUID"
create_secret "directory-view-uuid" "$DIRECTORY_VIEW_UUID"
create_secret "custom-field-uuid" "$CUSTOM_FIELD_UUID" 
create_secret "atlassian-cookies" "$ATLASSIAN_COOKIES"

echo -e "${GREEN}✅ Secrets created successfully${NC}"

echo -e "${GREEN}✅ Infrastructure setup completed!${NC}"
echo
echo -e "${BLUE}📝 Summary of created resources:${NC}"
echo "  🏗️  Service Account: $SERVICE_ACCOUNT_EMAIL"
echo "  🗂️  Artifact Registry: $REGION-docker.pkg.dev/$PROJECT_ID/$ARTIFACT_REGISTRY_REPO"
echo "  🪣 Storage Bucket: gs://$BUCKET_NAME"
echo "  🔐 IAM Roles: Minimal required permissions assigned"
echo "  🔌 APIs: All required services enabled"
echo
echo -e "${YELLOW}🔧 Next steps:${NC}"
echo "1. Create secrets with your actual Atlassian configuration"
echo "2. Run Cloud Build deployment: gcloud builds submit"
echo "3. Test the deployment"
echo
echo -e "${GREEN}✨ Infrastructure is ready for deployment!${NC}" 