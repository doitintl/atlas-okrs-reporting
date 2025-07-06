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
    """Configure simple logging for Cloud Run Jobs"""
    # Use simple logging - Cloud Run automatically captures stdout/stderr
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True  # Override any existing logging configuration
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
        
        # Debug: log UUID values to verify they're clean
        logger.info(f"🔍 workspace_uuid: '{self.workspace_uuid}'")
        logger.info(f"🔍 directory_view_uuid: '{self.directory_view_uuid}'")
        logger.info(f"🔍 custom_field_uuid: '{self.custom_field_uuid}'")
        logger.info(f"🔍 cookies length: {len(self.cookies)} chars")
        
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
            
            # Decode the secret payload and clean it
            secret_value = response.payload.data.decode("UTF-8").strip()
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
        """Get details of a specific goal using EXACT query from bash script"""
        indent = "  " * depth
        logger.info(f"{indent}📋 [Level {depth}] Getting details: {goal_key}")
        
        # Payload for GraphQL query - EXACT copy from bash script
        payload = {
            "query": "query GoalViewAsideQuery($key: String!, $trackViewEvent: TrackViewEvent, $isNavRefreshEnabled: Boolean!, $containerId: String!) { workspaceGoalTypes: townsquare { goalTypes(containerId: $containerId) { edges { node { __typename id } } } } goal: goalByKey(key: $key, trackViewEvent: $trackViewEvent) @include(if: $isNavRefreshEnabled) { owner { aaid id pii { name email accountId } } key name archived targetDate startDate creationDate progress { type percentage } parentGoal { key name } subGoals { edges { node { key name archived } } } tags { edges { node { name } } } teamsV2 { edges { node { name teamId } } } customFields { edges { node { ... on TextSelectCustomField { values { edges { node { value } } } } } } } id } }",
            "variables": {
                "key": goal_key,
                "trackViewEvent": "DIRECT",
                "isNavRefreshEnabled": True,
                "containerId": f"ari:cloud:townsquare::site/{self.cloud_id}"
            }
        }
        
        # Use EXACT endpoint from bash script
        url = f"{self.base_url}/gateway/api/townsquare/s/{self.cloud_id}/graphql?operationName=GoalViewAsideQuery"
        
        # Use EXACT headers from bash script
        headers = {
            **self.headers, 
            'cookie': self.cookies,
            'referer': f"{self.base_url}/o/{self.organization_id}/s/{self.cloud_id}/goal/{goal_key}"
        }
        
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
        """Process goal data and return OKRData object using EXACT field names from bash script"""
        try:
            # Extract owner information - handle None values
            owner_info = goal_data.get('owner') or {}
            pii_info = owner_info.get('pii') or {}
            owner_name = pii_info.get('name', 'Unknown')
            
            # Extract basic goal information
            goal_key = goal_data.get('key', '')
            goal_name = goal_data.get('name', '')
            target_date = goal_data.get('targetDate', '')
            start_date = goal_data.get('startDate', '')
            created_at = goal_data.get('creationDate', '')  # bash script uses 'creationDate'
            archived = goal_data.get('archived', False)
            
            # Extract progress type from nested progress object - handle None values
            progress_info = goal_data.get('progress') or {}
            progress_type = progress_info.get('type', '')
            
            # Extract parent goal - handle None values
            parent_goal = goal_data.get('parentGoal') or {}
            parent_goal_key = parent_goal.get('key', '')
            
            # Extract subgoals using 'subGoals' field name from bash script - handle None values
            subgoals_data = (goal_data.get('subGoals') or {}).get('edges', [])
            subgoals = [edge['node']['key'] for edge in subgoals_data if edge.get('node', {}).get('key')]
            
            # Extract tags using 'tags' field name from bash script - handle None values
            tags_data = (goal_data.get('tags') or {}).get('edges', [])
            tags = [edge['node']['name'] for edge in tags_data if edge.get('node', {}).get('name')]
            
            # Extract teams from 'teamsV2' field from bash script - handle None values
            teams_data = (goal_data.get('teamsV2') or {}).get('edges', [])
            teams = [edge['node']['name'] for edge in teams_data if edge.get('node', {}).get('name')]
            
            # Extract lineage from custom fields (bash script logic) - handle None values
            custom_fields = (goal_data.get('customFields') or {}).get('edges', [])
            lineage = goal_key  # default to goal_key
            for field in custom_fields:
                field_node = field.get('node', {})
                # Extract first available custom field value (bash script logic) - handle None values
                values = (field_node.get('values') or {}).get('edges', [])
                if values:
                    first_value = values[0].get('node', {}).get('value', '')
                    if first_value:
                        lineage = first_value
                        break
            
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
        
        # GraphQL query - EXACT copy from working bash script
        payload = {
            "query": "query Goals(\n  $after: String\n  $containerId: String\n  $directoryViewUuid: UUID\n  $first: Int = 50\n  $includeFollowerCount: Boolean!\n  $includeFollowing: Boolean!\n  $includeLastUpdated: Boolean!\n  $includeOwner: Boolean!\n  $includeRelatedProjects: Boolean!\n  $includeStatus: Boolean!\n  $includeTags: Boolean!\n  $includeTargetDate: Boolean!\n  $includeTeam: Boolean!\n  $includedCustomFieldUuids: [UUID!]\n  $skipTableTql: Boolean!\n  $sorts: [GoalSortEnum]\n  $tql: String\n  $workspaceUuid: UUID\n) {\n  ...DirectoryTableViewGoal_3JCCLt\n}\n\nfragment CustomFieldCell on CustomFieldConnection {\n  edges {\n    node {\n      __typename\n      ... on CustomFieldNode {\n        __isCustomFieldNode: __typename\n        definition {\n          __typename\n          ... on CustomFieldDefinitionNode {\n            __isCustomFieldDefinitionNode: __typename\n            uuid\n          }\n          ... on Node {\n            __isNode: __typename\n            id\n          }\n        }\n      }\n      ...NumberFieldColumn\n      ...TextSelectFieldColumn\n      ...UserFieldColumn\n      ...TextFieldColumn\n      ... on Node {\n        __isNode: __typename\n        id\n      }\n    }\n  }\n}\n\nfragment DirectoryRow_367brx on Goal {\n  id\n  ari\n  key\n  hasSubgoalMatches\n  latestUpdateDate @include(if: $includeLastUpdated)\n  ...GoalNameColumn\n  ...GoalFollowButton @include(if: $includeFollowing)\n  ...GoalActions\n  dueDate @include(if: $includeTargetDate) {\n    ...TargetDate\n  }\n  state @include(if: $includeStatus) {\n    ...GoalState\n  }\n  owner @include(if: $includeOwner) {\n    ...UserAvatar_2aqwkz\n    id\n  }\n  projects @include(if: $includeRelatedProjects) {\n    ...RelatedGoalProjects\n  }\n  teamsV2 @include(if: $includeTeam) {\n    ...TeamOfGoal\n  }\n  tags @include(if: $includeTags) {\n    ...TagColumn\n  }\n  ...FollowerCount_goal @include(if: $includeFollowerCount)\n  customFields(includedCustomFieldUuids: $includedCustomFieldUuids) {\n    ...CustomFieldCell\n  }\n  ...MetricColumn\n}\n\nfragment DirectoryTableViewGoal_3JCCLt on Query {\n  goalTqlFullHierarchy(first: $first, after: $after, q: $tql, workspaceUuid: $workspaceUuid, containerId: $containerId, sorts: $sorts, directoryViewUuid: $directoryViewUuid) @skip(if: $skipTableTql) {\n    count\n    edges {\n      node {\n        id\n        ari\n        ...RootDirectoryRow_367brx\n        __typename\n      }\n      cursor\n    }\n    pageInfo {\n      endCursor\n      hasNextPage\n    }\n  }\n  currentUser {\n    preferences {\n      wrapTextEnabled\n      id\n    }\n    id\n  }\n}\n\nfragment FollowerCount_goal on Goal {\n  ...GoalFollowersButton\n}\n\nfragment GoalActions on Goal {\n  id\n  name\n  archived\n  parentGoal {\n    id\n  }\n  subGoals {\n    edges {\n      node {\n        archived\n        id\n      }\n    }\n  }\n}\n\nfragment GoalFollowButton on Goal {\n  id\n  uuid\n  watching\n}\n\nfragment GoalFollowersButton on Goal {\n  key\n  watchers {\n    count\n  }\n}\n\nfragment GoalName on Goal {\n  uuid\n  id\n  key\n  ...PlatformGoalIcon\n  name\n}\n\nfragment GoalNameColumn on Goal {\n  id\n  managerData {\n    managers {\n      managerProfile {\n        name\n      }\n      directReports\n    }\n  }\n  ...GoalName\n}\n\nfragment GoalState on GoalState {\n  label(includeScore: false)\n  localizedLabel {\n    messageId\n  }\n  score\n  goalStateValue: value\n  atCompletionState {\n    label(includeScore: false)\n    localizedLabel {\n      messageId\n    }\n    value\n    score\n  }\n}\n\nfragment MetricChart on Goal {\n  ...WrappedWithMetricPopup\n  id\n  progress {\n    type\n    percentage\n  }\n  subGoals {\n    count\n  }\n  metricTargets {\n    edges {\n      node {\n        ...common_metricTarget_direct\n        id\n      }\n    }\n  }\n}\n\nfragment MetricColumn on Goal {\n  id\n  uuid\n  ...progressBarMetricTarget\n  ...hasMetric\n  ...MetricChart\n}\n\nfragment NumberFieldColumn on NumberCustomField {\n  value {\n    numberValue: value\n    id\n  }\n}\n\nfragment PlatformGoalIcon on Goal {\n  icon {\n    key\n    appearance\n  }\n}\n\nfragment ProjectIcon on Project {\n  private\n  iconUrl {\n    square {\n      light\n      dark\n      transparent\n    }\n  }\n}\n\nfragment ProjectName_data on Project {\n  id\n  key\n  name\n  uuid\n  ...ProjectIcon\n}\n\nfragment RelatedGoalProjects on ProjectConnection {\n  count\n  edges {\n    node {\n      ...ProjectName_data\n      id\n    }\n  }\n}\n\nfragment RootDirectoryRow_367brx on Goal {\n  id\n  ...DirectoryRow_367brx\n}\n\nfragment Tag on Tag {\n  ...Tag_createTagOption\n}\n\nfragment TagColumn on TagConnection {\n  edges {\n    node {\n      ...Tag\n      id\n    }\n  }\n  count\n}\n\nfragment Tag_createTagOption on Tag {\n  id\n  name\n  uuid\n  description\n  projectUsageCount\n  goalUsageCount\n  helpPointerUsageCount\n  watcherCount\n}\n\nfragment TargetDate on TargetDate {\n  confidence\n  label\n  localizedLabel {\n    messageId\n  }\n  tooltip: label(longFormat: true)\n  localizedTooltip: localizedLabel(longFormat: true) {\n    messageId\n  }\n  overdue\n}\n\nfragment TeamOfGoal on GoalTeamConnection {\n  edges {\n    node {\n      avatarUrl\n      name\n      teamId\n      id\n    }\n  }\n  count\n}\n\nfragment TextFieldColumn on TextCustomField {\n  value {\n    textValue: value\n    id\n  }\n}\n\nfragment TextSelectFieldColumn on TextSelectCustomField {\n  definition {\n    __typename\n    ... on TextSelectCustomFieldDefinition {\n      canSetMultipleValues\n    }\n    ... on Node {\n      __isNode: __typename\n      id\n    }\n  }\n  values {\n    count\n    edges {\n      node {\n        id\n        value\n      }\n    }\n  }\n}\n\nfragment UserAvatar_2aqwkz on User {\n  aaid\n  pii {\n    picture\n    accountId\n    name\n  }\n}\n\nfragment UserFieldColumn on UserCustomField {\n  definition {\n    __typename\n    ... on UserCustomFieldDefinition {\n      canSetMultipleValues\n    }\n    ... on Node {\n      __isNode: __typename\n      id\n    }\n  }\n  values {\n    count\n    edges {\n      node {\n        pii {\n          accountId\n          name\n          picture\n        }\n        id\n      }\n    }\n  }\n}\n\nfragment WrappedWithMetricPopup on Goal {\n  id\n  progress {\n    percentage\n  }\n  metricTargets {\n    edges {\n      node {\n        ...common_metricTarget_direct\n        metric {\n          archived\n          id\n        }\n        id\n      }\n    }\n  }\n}\n\nfragment common_metricTarget_direct on MetricTarget {\n  startValue\n  targetValue\n  snapshotValue {\n    value\n    id\n  }\n  metric {\n    id\n    name\n    type\n    subType\n  }\n}\n\nfragment hasMetric on Goal {\n  progress {\n    type\n  }\n  metricTargets {\n    edges {\n      node {\n        metric {\n          archived\n          id\n        }\n        id\n      }\n    }\n  }\n}\n\nfragment progressBarMetricTarget on Goal {\n  progress {\n    type\n    percentage\n  }\n  metricTargets {\n    edges {\n      node {\n        snapshotValue {\n          value\n          id\n        }\n        startValue\n        targetValue\n        metric {\n          type\n          subType\n          id\n        }\n        id\n      }\n    }\n  }\n}\n",
            "variables": {
                "after": None,
                "containerId": f"ari:cloud:townsquare::site/{self.cloud_id}",
                "directoryViewUuid": self.directory_view_uuid,
                "first": 50,
                "includeFollowerCount": False,
                "includeFollowing": False,
                "includeLastUpdated": False,
                "includeOwner": True,
                "includeRelatedProjects": False,
                "includeStatus": False,
                "includeTags": True,
                "includeTargetDate": True,
                "includeTeam": True,
                "includedCustomFieldUuids": [self.custom_field_uuid],
                "skipTableTql": False,
                "sorts": None,
                "tql": None,
                "workspaceUuid": self.workspace_uuid
            }
        }
        
        # Use the correct endpoint from bash script
        url = f"{self.base_url}/gateway/api/townsquare/s/{self.cloud_id}/graphql?operationName=DirectoryTableViewGoalPaginationQuery"
        
        # Add referer header like in bash script
        headers = {
            **self.headers, 
            'cookie': self.cookies,
            'referer': f"{self.base_url}/o/{self.organization_id}/goals?viewUuid={self.directory_view_uuid}&cloudId={self.cloud_id}"
        }
        
        all_goals = []
        
        try:
            # Make SINGLE request (NO PAGINATION) like bash script
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Debug: log response structure
            logger.info(f"🔍 Response status: {response.status_code}")
            logger.info(f"🔍 Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            
            if 'data' not in data or 'goalTqlFullHierarchy' not in data['data']:
                logger.error("❌ Invalid response structure")
                logger.error(f"🔍 Full response: {data}")
                return []
            
            goal_hierarchy = data['data']['goalTqlFullHierarchy']
            if not goal_hierarchy:
                logger.error("❌ No goals found in hierarchy")
                return []
            
            edges = goal_hierarchy.get('edges', [])
            
            for edge in edges:
                node = edge.get('node', {})
                goal_key = node.get('key')
                
                if goal_key:
                    all_goals.append(goal_key)
                    logger.info(f"📋 Found goal: {goal_key}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error getting initial snapshot: {e}")
            return []
        
        logger.info(f"✅ Initial snapshot completed. Found {len(all_goals)} goals")
        return all_goals

    def generate_csv_content(self, timestamp: str) -> str:
        """Generate CSV content from processed OKR data matching bash script format"""
        logger.info("📝 Generating CSV content...")
        
        # Create CSV content manually to match bash script format exactly
        csv_lines = []
        
        # Add CSV header exactly as bash script
        csv_lines.append('created_at,Owner,Goal Key,Target Date,Name,Parent Goal,Sub-goals,Tags,Progress Type,Teams,Start Date,Creation Date,Lineage')
        
        # Helper function to clean fields - using semicolon separator like bash script
        def clean_field(field):
            if isinstance(field, list):
                return ';'.join(str(item) for item in field) if field else 'null'
            return str(field) if field else 'null'
        
        # Helper function to clean string fields for CSV (escape commas and quotes)
        def clean_string_field(field):
            if not field or field == 'null':
                return 'null'
            # Replace commas with semicolons and escape quotes like bash script
            cleaned = str(field).replace(',', ';').replace('"', '""')
            return cleaned
        
        # Write data rows - filter out archived goals like bash script
        for goal_key, okr_data in self.okr_data.items():
            # Skip archived goals (like bash script does)
            if okr_data.archived:
                continue
                
            # Generate CSV line exactly like bash script
            csv_line = f'{timestamp},"{clean_string_field(okr_data.owner_name)}","{clean_field(okr_data.goal_key)}","{clean_field(okr_data.target_date)}","{clean_string_field(okr_data.goal_name)}","{clean_field(okr_data.parent_goal_key)}","{clean_field(okr_data.subgoals)}","{clean_field(okr_data.tags)}","{clean_field(okr_data.progress_type)}","{clean_field(okr_data.teams)}","{clean_field(okr_data.start_date)}","{clean_field(okr_data.creation_date)}","{clean_field(okr_data.lineage)}"'
            csv_lines.append(csv_line)
        
        csv_content = '\n'.join(csv_lines)
        
        # Count non-archived goals
        non_archived_count = sum(1 for okr_data in self.okr_data.values() if not okr_data.archived)
        logger.info(f"✅ CSV content generated successfully. {non_archived_count} goals processed (excluding archived)")
        return csv_content
    
    def upload_to_gcs(self, csv_content: str, filename: str) -> str:
        """Upload CSV content to Google Cloud Storage"""
        logger.info(f"☁️ Uploading to Cloud Storage: {filename}")
        
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(f"okrs/{filename}")
            
            # Upload CSV content
            blob.upload_from_string(csv_content, content_type='text/csv')
            
            # Note: Bucket has uniform bucket-level access enabled, so we don't set ACLs
            # The file will be accessible via Cloud Storage for BigQuery integration
            
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
        timestamp = datetime.now().strftime("%Y%m%d%H%M")
        
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
            filename = f"export-{timestamp}_processed.csv"
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