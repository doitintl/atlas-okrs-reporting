#!/usr/bin/env python3
"""
Cloud Run OKRs Scraper Job

This is an optimized version of the OKRs scraping script designed to run as a Cloud Run Job.
Instead of being a web service, it executes once and terminates.

Main features:
1. Recursive OKRs scraping from Atlassian using DFS
2. In-memory processing (no temporary files)
3. Direct upload to Google Cloud Storage
4. Ready for BigQuery and Looker
5. Structured logging for Cloud Run Jobs
6. Designed for scheduled execution (Cloud Scheduler)

Usage:
    - Deploy as Cloud Run Job
    - Execute via gcloud or Cloud Scheduler
    - The CSV file will be generated and uploaded automatically to Cloud Storage
"""

import os
import json
import time
import sys
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from io import StringIO
import csv

import requests
from google.cloud import storage
from google.cloud import logging as cloud_logging
from google.cloud import secretmanager
import pandas as pd

# Configure logging for Cloud Run Jobs
def setup_logging():
    """Configure structured logging for Cloud Run Jobs"""
    # Use Cloud Logging in production
    if os.getenv('GOOGLE_CLOUD_PROJECT'):
        client = cloud_logging.Client()
        client.setup_logging()
    
    # Configure the main logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    return logging.getLogger(__name__)

logger = setup_logging()

@dataclass
class OKRData:
    """Data structure for an OKR"""
    owner_name: str
    goal_key: str
    target_date: str
    goal_name: str
    parent_goal_key: str
    subgoals: List[str]
    tags: List[str]
    progress_type: str
    teams: List[str]
    start_date: str
    creation_date: str
    lineage: str
    archived: bool = False

class CloudRunOKRScraper:
    """OKRs scraper optimized for Cloud Run Jobs"""
    
    def __init__(self):
        logger.info("🚀 Initializing Cloud Run OKRs Scraper Job")
        
        # Initialize Secret Manager client
        self.secret_client = secretmanager.SecretManagerServiceClient()
        self.project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        
        # Non-sensitive configuration from environment variables
        self.base_url = os.getenv('ATLASSIAN_BASE_URL')
        self.organization_id = os.getenv('ORGANIZATION_ID')
        self.cloud_id = os.getenv('CLOUD_ID')
        
        # Sensitive configuration from Secret Manager
        self.workspace_uuid = self._get_secret('workspace-uuid')
        self.directory_view_uuid = self._get_secret('directory-view-uuid')
        self.custom_field_uuid = self._get_secret('custom-field-uuid')
        self.cookies = self._get_secret('atlassian-cookies')
        
        # Cloud Storage configuration
        self.bucket_name = os.getenv('GCS_BUCKET_NAME')
        self.storage_client = storage.Client()
        
        # Headers for requests
        self.headers = {
            'accept': '*/*',
            'accept-language': 'es-ES,es;q=0.9,en;q=0.8',
            'atl-client-name': 'townsquare-frontend',
            'atl-client-version': 'daf3c1',
            'content-type': 'application/json',
            'origin': self.base_url,
            'priority': 'u=1, i',
            'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'
        }
        
        # In-memory data
        self.processed_goals: Set[str] = set()
        self.okr_data: Dict[str, OKRData] = {}
        
        # Validate configuration
        self._validate_config()
    
    def _get_secret(self, secret_name: str) -> str:
        """Get secret value from Google Cloud Secret Manager"""
        try:
            # Build the resource name of the secret version
            name = f"projects/{self.project_id}/secrets/{secret_name}/versions/latest"
            
            # Access the secret version
            response = self.secret_client.access_secret_version(request={"name": name})
            
            # Decode the secret payload
            secret_value = response.payload.data.decode("UTF-8")
            logger.info(f"✅ Successfully retrieved secret: {secret_name}")
            return secret_value
            
        except Exception as e:
            logger.error(f"❌ Error retrieving secret {secret_name}: {e}")
            raise ValueError(f"Could not retrieve secret {secret_name}: {e}")
    
    def _validate_config(self):
        """Validate that all configuration variables are present"""
        # Environment variables
        required_env_vars = [
            'ATLASSIAN_BASE_URL', 'ORGANIZATION_ID', 'CLOUD_ID', 
            'GCS_BUCKET_NAME', 'GOOGLE_CLOUD_PROJECT'
        ]
        
        missing_env_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_env_vars:
            raise ValueError(f"Missing environment variables: {', '.join(missing_env_vars)}")
        
        # Secret Manager secrets
        required_secrets = [
            'workspace-uuid', 'directory-view-uuid', 'custom-field-uuid', 'atlassian-cookies'
        ]
        
        # Check that secrets are accessible (they're loaded in __init__)
        secret_values = [
            self.workspace_uuid, self.directory_view_uuid, 
            self.custom_field_uuid, self.cookies
        ]
        
        if not all(secret_values):
            raise ValueError("Some required secrets could not be retrieved from Secret Manager")
        
        logger.info("✅ Configuration validated successfully")
    
    def get_goal_details(self, goal_key: str, depth: int = 0) -> Optional[Dict]:
        """Get details of a specific goal"""
        indent = "  " * depth
        logger.info(f"{indent}📋 [Level {depth}] Getting details: {goal_key}")
        
        # Payload for GraphQL query
        payload = {
            "query": """
                query GoalViewAsideQuery($key: String!, $trackViewEvent: TrackViewEvent, $isNavRefreshEnabled: Boolean!, $containerId: String!) {
                    workspaceGoalTypes: townsquare {
                        goalTypes(containerId: $containerId) {
                            edges {
                                node {
                                    __typename
                                    id
                                }
                            }
                        }
                    }
                    goal: goalByKey(key: $key, trackViewEvent: $trackViewEvent) @include(if: $isNavRefreshEnabled) {
                        owner {
                            aaid
                            id
                            pii {
                                name
                                email
                                accountId
                            }
                        }
                        key
                        name
                        archived
                        targetDate
                        startDate
                        createdAt
                        contextualizedTags {
                            edges {
                                node {
                                    name
                                    __typename
                                }
                            }
                        }
                        progressType
                        parentGoal {
                            __typename
                            key
                        }
                        subgoals {
                            edges {
                                node {
                                    __typename
                                    key
                                }
                            }
                        }
                        customFields {
                            edges {
                                node {
                                    __typename
                                    id
                                    value
                                }
                            }
                        }
                    }
                }
            """,
            "variables": {
                "key": goal_key,
                "trackViewEvent": {"eventName": "goal.viewed"},
                "isNavRefreshEnabled": True,
                "containerId": self.workspace_uuid
            }
        }
        
        # Make request
        url = f"{self.base_url}/gateway/api/graphql"
        headers = {**self.headers, 'cookie': self.cookies}
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            if 'data' in data and 'goal' in data['data'] and data['data']['goal']:
                goal_data = data['data']['goal']
                logger.info(f"{indent}✅ [Level {depth}] Successfully retrieved: {goal_data.get('name', 'Unknown')}")
                return goal_data
            else:
                logger.warning(f"{indent}⚠️ [Level {depth}] No goal data found for: {goal_key}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"{indent}❌ [Level {depth}] Error retrieving goal {goal_key}: {e}")
            return None
    
    def process_goal_data(self, goal_data: Dict) -> Optional[OKRData]:
        """Process goal data and return OKRData object"""
        try:
            # Extract owner information
            owner_info = goal_data.get('owner', {})
            pii_info = owner_info.get('pii', {})
            owner_name = pii_info.get('name', 'Unknown')
            
            # Extract basic goal information
            goal_key = goal_data.get('key', '')
            goal_name = goal_data.get('name', '')
            target_date = goal_data.get('targetDate', '')
            start_date = goal_data.get('startDate', '')
            created_at = goal_data.get('createdAt', '')
            archived = goal_data.get('archived', False)
            progress_type = goal_data.get('progressType', '')
            
            # Extract parent goal
            parent_goal = goal_data.get('parentGoal', {})
            parent_goal_key = parent_goal.get('key', '') if parent_goal else ''
            
            # Extract subgoals
            subgoals_data = goal_data.get('subgoals', {}).get('edges', [])
            subgoals = [edge['node']['key'] for edge in subgoals_data if edge.get('node', {}).get('key')]
            
            # Extract tags
            tags_data = goal_data.get('contextualizedTags', {}).get('edges', [])
            tags = [edge['node']['name'] for edge in tags_data if edge.get('node', {}).get('name')]
            
            # Extract teams from custom fields
            custom_fields = goal_data.get('customFields', {}).get('edges', [])
            teams = []
            for field in custom_fields:
                field_node = field.get('node', {})
                if field_node.get('id') == self.custom_field_uuid:
                    teams_value = field_node.get('value', '')
                    if teams_value:
                        teams = [team.strip() for team in teams_value.split(',')]
                    break
            
            # Generate lineage (will be updated in recursive processing)
            lineage = goal_key
            
            # Create OKRData object
            okr_data = OKRData(
                owner_name=owner_name,
                goal_key=goal_key,
                target_date=target_date,
                goal_name=goal_name,
                parent_goal_key=parent_goal_key,
                subgoals=subgoals,
                tags=tags,
                progress_type=progress_type,
                teams=teams,
                start_date=start_date,
                creation_date=created_at,
                lineage=lineage,
                archived=archived
            )
            
            logger.info(f"✅ Processed goal data: {goal_name} ({goal_key})")
            return okr_data
            
        except Exception as e:
            logger.error(f"❌ Error processing goal data: {e}")
            return None
    
    def process_goal_recursive(self, goal_key: str, depth: int = 0) -> bool:
        """Process goal recursively using DFS"""
        if goal_key in self.processed_goals:
            return True
        
        # Get goal details
        goal_data = self.get_goal_details(goal_key, depth)
        if not goal_data:
            return False
        
        # Process goal data
        okr_data = self.process_goal_data(goal_data)
        if not okr_data:
            return False
        
        # Store in memory
        self.okr_data[goal_key] = okr_data
        self.processed_goals.add(goal_key)
        
        # Process subgoals recursively
        for subgoal_key in okr_data.subgoals:
            if subgoal_key not in self.processed_goals:
                self.process_goal_recursive(subgoal_key, depth + 1)
        
        return True
    
    def get_initial_snapshot(self) -> List[str]:
        """Get initial snapshot of goals from directory view"""
        logger.info("📊 Getting initial snapshot of goals...")
        
        # GraphQL query for directory view
        payload = {
            "query": """
                query DirectoryViewQuery($first: Int!, $after: String, $directoryViewUuid: String!) {
                    directoryView(uuid: $directoryViewUuid) {
                        goals(first: $first, after: $after) {
                            pageInfo {
                                hasNextPage
                                endCursor
                            }
                            edges {
                                node {
                                    key
                                    name
                                    owner {
                                        pii {
                                            name
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            """,
            "variables": {
                "first": 100,
                "after": None,
                "directoryViewUuid": self.directory_view_uuid
            }
        }
        
        url = f"{self.base_url}/gateway/api/graphql"
        headers = {**self.headers, 'cookie': self.cookies}
        
        all_goals = []
        
        try:
            while True:
                response = requests.post(url, json=payload, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                
                if 'data' not in data or 'directoryView' not in data['data']:
                    logger.error("❌ Invalid response structure")
                    break
                
                directory_view = data['data']['directoryView']
                if not directory_view or 'goals' not in directory_view:
                    logger.error("❌ No goals found in directory view")
                    break
                
                goals = directory_view['goals']
                edges = goals.get('edges', [])
                
                for edge in edges:
                    node = edge.get('node', {})
                    goal_key = node.get('key')
                    goal_name = node.get('name', 'Unknown')
                    
                    if goal_key:
                        all_goals.append(goal_key)
                        logger.info(f"📋 Found goal: {goal_name} ({goal_key})")
                
                # Check if there are more pages
                page_info = goals.get('pageInfo', {})
                if not page_info.get('hasNextPage', False):
                    break
                
                # Update cursor for next page
                payload['variables']['after'] = page_info.get('endCursor')
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error getting initial snapshot: {e}")
            return []
        
        logger.info(f"✅ Initial snapshot completed. Found {len(all_goals)} goals")
        return all_goals
    
    def generate_csv_content(self, timestamp: str) -> str:
        """Generate CSV content from processed OKR data"""
        logger.info("📝 Generating CSV content...")
        
        # Create CSV content in memory
        csv_buffer = StringIO()
        
        # Define CSV headers
        headers = [
            'owner_name', 'goal_key', 'target_date', 'goal_name', 'parent_goal_key',
            'subgoals', 'tags', 'progress_type', 'teams', 'start_date',
            'creation_date', 'lineage', 'archived'
        ]
        
        writer = csv.DictWriter(csv_buffer, fieldnames=headers)
        writer.writeheader()
        
        # Helper function to clean fields
        def clean_field(field):
            if isinstance(field, list):
                return '|'.join(str(item) for item in field)
            return str(field) if field else ''
        
        # Write data rows
        for goal_key, okr_data in self.okr_data.items():
            row = {
                'owner_name': clean_field(okr_data.owner_name),
                'goal_key': clean_field(okr_data.goal_key),
                'target_date': clean_field(okr_data.target_date),
                'goal_name': clean_field(okr_data.goal_name),
                'parent_goal_key': clean_field(okr_data.parent_goal_key),
                'subgoals': clean_field(okr_data.subgoals),
                'tags': clean_field(okr_data.tags),
                'progress_type': clean_field(okr_data.progress_type),
                'teams': clean_field(okr_data.teams),
                'start_date': clean_field(okr_data.start_date),
                'creation_date': clean_field(okr_data.creation_date),
                'lineage': clean_field(okr_data.lineage),
                'archived': clean_field(okr_data.archived)
            }
            writer.writerow(row)
        
        csv_content = csv_buffer.getvalue()
        csv_buffer.close()
        
        logger.info(f"✅ CSV content generated successfully. {len(self.okr_data)} goals processed")
        return csv_content
    
    def upload_to_gcs(self, csv_content: str, filename: str) -> str:
        """Upload CSV content to Google Cloud Storage"""
        logger.info(f"☁️ Uploading to Cloud Storage: {filename}")
        
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(f"okrs/{filename}")
            
            # Upload CSV content
            blob.upload_from_string(csv_content, content_type='text/csv')
            
            # Make blob publicly readable for BigQuery
            blob.make_public()
            
            public_url = blob.public_url
            logger.info(f"✅ File uploaded successfully: {public_url}")
            return public_url
            
        except Exception as e:
            logger.error(f"❌ Error uploading to Cloud Storage: {e}")
            raise
    
    def run_scraping(self) -> Tuple[str, str, int]:
        """Run the complete scraping process"""
        logger.info("🚀 Starting OKRs scraping process...")
        
        start_time = time.time()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        try:
            # Step 1: Get initial snapshot
            initial_goals = self.get_initial_snapshot()
            if not initial_goals:
                raise Exception("No goals found in initial snapshot")
            
            # Step 2: Process goals recursively
            logger.info(f"🔄 Processing {len(initial_goals)} goals recursively...")
            
            processed_count = 0
            for goal_key in initial_goals:
                if self.process_goal_recursive(goal_key):
                    processed_count += 1
            
            if processed_count == 0:
                raise Exception("No goals were processed successfully")
            
            # Step 3: Generate CSV content
            csv_content = self.generate_csv_content(timestamp)
            if not csv_content:
                raise Exception("Failed to generate CSV content")
            
            # Step 4: Upload to Cloud Storage
            filename = f"okrs_emea_goals_{timestamp}.csv"
            public_url = self.upload_to_gcs(csv_content, filename)
            
            # Calculate execution time
            execution_time = time.time() - start_time
            
            logger.info(f"✅ Scraping completed successfully!")
            logger.info(f"📊 Processed {processed_count} goals in {execution_time:.2f} seconds")
            logger.info(f"☁️ File available at: {public_url}")
            
            return public_url, filename, processed_count
            
        except Exception as e:
            logger.error(f"❌ Scraping process failed: {e}")
            raise

def main():
    """Main function for Cloud Run Job execution"""
    logger.info("🚀 Starting Cloud Run OKRs Scraper Job")
    
    try:
        # Create scraper instance
        scraper = CloudRunOKRScraper()
        
        # Run scraping process
        public_url, filename, processed_count = scraper.run_scraping()
        
        # Log final results
        logger.info("=" * 50)
        logger.info("✅ JOB COMPLETED SUCCESSFULLY")
        logger.info(f"📊 Goals processed: {processed_count}")
        logger.info(f"📁 File: {filename}")
        logger.info(f"🔗 URL: {public_url}")
        logger.info("=" * 50)
        
        # Exit with success code
        sys.exit(0)
        
    except Exception as e:
        logger.error("=" * 50)
        logger.error("❌ JOB FAILED")
        logger.error(f"Error: {e}")
        logger.error("=" * 50)
        
        # Exit with error code
        sys.exit(1)

if __name__ == "__main__":
    main() 