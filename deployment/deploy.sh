#!/bin/bash

# Cloud Build Deployment Script for OKRs Scraper
# This script provides a convenient way to deploy using Cloud Build with proper parameters

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT="production"
CONFIG_FILE="../config.env"
ASYNC_DEPLOY=false
WATCH_LOGS=true

# Function to display usage
show_usage() {
    echo -e "${BLUE}🚀 Cloud Build Deployment Script for OKRs Scraper${NC}"
    echo
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  -e, --environment ENV      Environment (production, staging, development) [default: production]"
    echo "  -c, --config FILE          Config file path [default: ../config.env]"
    echo "  -a, --async               Deploy asynchronously (don't wait for completion)"
    echo "  -q, --quiet               Don't stream build logs"
    echo "  -h, --help                Show this help message"
    echo
    echo "Environment-specific options:"
    echo "  --url URL                 Override Atlassian base URL"
    echo "  --org-id ID               Override organization ID"
    echo "  --cloud-id ID             Override cloud ID"
    echo "  --memory MEM              Override memory allocation (e.g., 2Gi, 4Gi)"
    echo "  --cpu CPU                 Override CPU allocation (e.g., 1, 2)"
    echo "  --parallelism N           Override task parallelism (number of parallel tasks)"
    echo "  --task-count N            Override task count (total number of tasks)"
    echo "  --max-retries N           Override max retries for failed tasks"
    echo
    echo "Examples:"
    echo "  $0                                    # Deploy to production with default config"
    echo "  $0 -e staging -c config-staging.env  # Deploy to staging with custom config"
    echo "  $0 --async --quiet                   # Deploy asynchronously without logs"
    echo "  $0 --url https://mycompany.atlassian.net --org-id myorg123"
    echo
}

# Function to validate prerequisites
validate_prerequisites() {
    echo -e "${YELLOW}🔍 Validating prerequisites...${NC}"
    
    # Check if gcloud is installed
    if ! command -v gcloud &> /dev/null; then
        echo -e "${RED}❌ gcloud CLI is not installed${NC}"
        echo "Please install gcloud CLI: https://cloud.google.com/sdk/docs/install"
        exit 1
    fi
    
    # Check if project is configured
    PROJECT_ID=$(gcloud config get-value project)
    if [ -z "$PROJECT_ID" ]; then
        echo -e "${RED}❌ No project configured in gcloud${NC}"
        echo "Run: gcloud config set project YOUR_PROJECT_ID"
        exit 1
    fi
    
    # Check if Cloud Build API is enabled
    if ! gcloud services list --enabled --filter="name:cloudbuild.googleapis.com" --format="value(name)" | grep -q "cloudbuild.googleapis.com"; then
        echo -e "${RED}❌ Cloud Build API is not enabled${NC}"
        echo "Run: gcloud services enable cloudbuild.googleapis.com"
        echo "Or run the infrastructure setup: ./setup_cloud_infrastructure.sh"
        exit 1
    fi
    
    # Check if config file exists
    if [ ! -f "$CONFIG_FILE" ]; then
        echo -e "${RED}❌ Config file not found: $CONFIG_FILE${NC}"
        echo "Please create the config file or specify a different one with -c"
        echo "Example: cp config.env.example $CONFIG_FILE"
        exit 1
    fi
    

    
    echo -e "${GREEN}✅ Prerequisites validated${NC}"
    echo -e "${BLUE}📋 Project: $PROJECT_ID${NC}"
    echo -e "${BLUE}📋 Environment: $ENVIRONMENT${NC}"
    echo -e "${BLUE}📋 Config: $CONFIG_FILE${NC}"
}

# Note: All overrides are now handled through config.env file modifications
# The cloudbuild.yaml reads configuration directly from config.env

# Function to execute deployment
execute_deployment() {
    echo -e "${YELLOW}🚀 Starting Cloud Build deployment...${NC}"
    echo -e "${BLUE}📋 All configuration loaded from config.env${NC}"
    
    # Load configuration to get dynamic values
    if [ -f "$CONFIG_FILE" ]; then
        source "$CONFIG_FILE"
    fi
    
    local region="${REGION:-europe-west1}"
    local artifact_repo="${ARTIFACT_REGISTRY_REPO:-okrs-scraper-repo}"
    
    # Build the gcloud command - execute from parent directory for full context
    local cmd="gcloud builds submit --config=deployment/cloudbuild.yaml"
    
    # Add async flag if requested
    if [ "$ASYNC_DEPLOY" = true ]; then
        cmd="$cmd --async"
    fi
    
    # Add log streaming preference
    if [ "$WATCH_LOGS" = false ]; then
        cmd="$cmd --no-log-http"
    fi
    
    echo -e "${BLUE}📋 Command: $cmd${NC}"
    echo -e "${BLUE}📋 Executing from parent directory for full build context${NC}"
    echo -e "${BLUE}📋 Region: $region, Artifact Repo: $artifact_repo${NC}"
    echo
    
    # Execute the command from parent directory
    cd ..
    eval "$cmd"
    
    if [ $? -eq 0 ]; then
        echo
        echo -e "${GREEN}✅ Deployment completed successfully!${NC}"
        
        # Show job execution commands if not async
        if [ "$ASYNC_DEPLOY" = false ]; then
            # Load configuration to get job name and region
            if [ -f "$CONFIG_FILE" ]; then
                source "$CONFIG_FILE"
            fi
            
            local job_name="${JOB_NAME:-okrs-scraper-job}"
            local region="${REGION:-europe-west1}"
            
            # Override job name for non-production environments
            if [ "$ENVIRONMENT" != "production" ]; then
                job_name="okrs-scraper-job-$ENVIRONMENT"
            fi
            
            echo -e "${GREEN}🚀 Job Name: $job_name${NC}"
            echo -e "${GREEN}📍 Region: $region${NC}"
            echo
            echo -e "${YELLOW}🔧 Execute the job:${NC}"
            echo "  gcloud run jobs execute $job_name --region=$region"
            echo
            echo -e "${YELLOW}📋 Check execution status:${NC}"
            echo "  gcloud run jobs executions list --job=$job_name --region=$region"
            echo
            echo -e "${YELLOW}📝 View logs:${NC}"
            echo "  gcloud run jobs executions logs <EXECUTION_NAME> --region=$region"
        fi
    else
        echo -e "${RED}❌ Deployment failed${NC}"
        exit 1
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -c|--config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        -a|--async)
            ASYNC_DEPLOY=true
            shift
            ;;
        -q|--quiet)
            WATCH_LOGS=false
            shift
            ;;
        --url)
            OVERRIDE_URL="$2"
            shift 2
            ;;
        --org-id)
            OVERRIDE_ORG_ID="$2"
            shift 2
            ;;
        --cloud-id)
            OVERRIDE_CLOUD_ID="$2"
            shift 2
            ;;
        --memory)
            OVERRIDE_MEMORY="$2"
            shift 2
            ;;
        --cpu)
            OVERRIDE_CPU="$2"
            shift 2
            ;;
        --parallelism)
            OVERRIDE_PARALLELISM="$2"
            shift 2
            ;;
        --task-count)
            OVERRIDE_TASK_COUNT="$2"
            shift 2
            ;;
        --max-retries)
            OVERRIDE_MAX_RETRIES="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo -e "${RED}❌ Unknown option: $1${NC}"
            show_usage
            exit 1
            ;;
    esac
done

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(production|staging|development)$ ]]; then
    echo -e "${RED}❌ Invalid environment: $ENVIRONMENT${NC}"
    echo "Valid environments: production, staging, development"
    exit 1
fi

# Main execution
echo -e "${GREEN}🚀 OKRs Scraper - Cloud Build Deployment${NC}"
echo

validate_prerequisites
echo

# Confirm deployment
if [ "$ASYNC_DEPLOY" = false ]; then
    echo -e "${YELLOW}⚠️  This will deploy to $ENVIRONMENT environment${NC}"
    read -p "Continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}⏹️  Deployment cancelled${NC}"
        exit 0
    fi
fi

execute_deployment 