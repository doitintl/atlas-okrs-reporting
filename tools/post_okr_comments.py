#!/usr/bin/env python3
"""
Post comments to Atlassian for malformed OKRs

This script loads malformed OKRs from multiple sources and posts comments to Atlassian.
Supports three data sources:
1. Local CSV file (--file)
2. Cloud Storage bucket (--cloud) 
3. BigQuery external table (--bigquery)

Usage:
    python post_okr_comments.py [--file <csv_file>] [--cloud] [--bigquery]

Dependencies are managed in pyproject.toml. Install with: uv sync
"""

import sys
import os
import argparse
import json
import requests
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / 'helpers'))
from config_loader import load_config, get_bigquery_config

sys.path.append(str(Path(__file__).parent))
from okrs_sanity_check_scrap_data import get_malformed_okrs_and_teams, is_empty_or_null

try:
    from google.cloud import bigquery
    BIGQUERY_AVAILABLE = True
except ImportError:
    BIGQUERY_AVAILABLE = False

def format_missing_fields_english(missing_fields):
    """Format missing fields as English phrases"""
    field_phrases = {
        'Target Date': 'Target Date',
        'Teams': 'Teams',
        'Parent Goal': 'Parent Goal',
        'Owner': 'Owner',
        'Progress Type (Metric)': 'Progress Metric',
        'Lineage': 'Lineage',
    }
    return ', '.join([field_phrases.get(field, field) for field in missing_fields])

def generate_okr_comment_message(okr_row):
    okr_name = okr_row.get('Name', 'Unknown OKR')
    missing_fields = okr_row.get('sanity_missing', [])
    missing_str = format_missing_fields_english(missing_fields)
    message = (
        f"This OKR is missing some required fields: {missing_str}.\n"
        f"Please update this OKR ASAP to ensure it is healthy and trackable.\n"
        f"If you have any questions, please reach out to your line-up manager.\n"
    )
    return message

def get_entity_id_from_row(okr_row, config):
    """
    Get the entityId for the OKR. Prefer the 'EntityId' column if present and not null.
    Fallback to previous logic if not present.
    """
    # Prefer the 'EntityId' column if available
    entity_id = okr_row.get('EntityId')
    if entity_id and str(entity_id).lower() != 'null' and str(entity_id).strip() != '':
        return entity_id
    
    # Fallback to 'entity_id' (lowercase) if present (BigQuery compatibility)
    entity_id = okr_row.get('entity_id')
    if entity_id and str(entity_id).lower() != 'null' and str(entity_id).strip() != '':
        return entity_id
    
    # Legacy fallbacks
    if 'entityId' in okr_row:
        return okr_row['entityId']
    if 'Goal Key' in okr_row and 'ATLASSIAN_ENTITY_ID_PREFIX' in config:
        return config['ATLASSIAN_ENTITY_ID_PREFIX'] + str(okr_row['Goal Key'])
    return config.get('ATLASSIAN_ENTITY_ID')

def get_malformed_okrs_from_bigquery():
    """
    Get malformed OKRs directly from BigQuery external table.
    Uses the same logic as the Python script but queries BigQuery directly.
    """
    if not BIGQUERY_AVAILABLE:
        raise ImportError("Google Cloud BigQuery library not available. Install with: pip install google-cloud-bigquery")
    
    bq_config = get_bigquery_config()
    
    # Determine project ID
    if bq_config["project"]:
        project_id = bq_config["project"]
    else:
        # Use default project from environment
        client = bigquery.Client()
        project_id = client.project
    
    client = bigquery.Client(project=project_id)
    
    # Query to get malformed OKRs using the same logic as the Python script
    query = f"""
    SELECT 
      goal_key as goal_key,
      goal_name as goal_name,
      owner as owner,
      target_date as target_date,
      parent_goal as parent_goal,
      sub_goals_array as sub_goals_array,
      tags_array as tags_array,
      progress_type as progress_type,
      teams_array as teams_array,
      start_date as start_date,
      creation_date as creation_date,
      lineage as lineage,
      entity_id as entity_id,
      -- Check each requirement (same logic as Python script)
      CASE WHEN has_target_date THEN 0 ELSE 1 END +
      CASE WHEN teams_array IS NOT NULL AND ARRAY_LENGTH(teams_array) > 0 THEN 0 ELSE 1 END +
      CASE WHEN parent_goal IS NOT NULL THEN 0 ELSE 1 END +
      CASE WHEN owner IS NOT NULL AND TRIM(owner) != '' THEN 0 ELSE 1 END +
      CASE WHEN has_metric THEN 0 ELSE 1 END +
      CASE WHEN has_lineage THEN 0 ELSE 1 END as missing_count,
      -- Build missing fields list using CASE statements
      CASE 
        WHEN NOT has_target_date THEN 'Target Date'
        WHEN NOT (teams_array IS NOT NULL AND ARRAY_LENGTH(teams_array) > 0) THEN 'Teams'
        WHEN NOT (parent_goal IS NOT NULL) THEN 'Parent Goal'
        WHEN NOT (owner IS NOT NULL AND TRIM(owner) != '') THEN 'Owner'
        WHEN NOT has_metric THEN 'Progress Type (Metric)'
        WHEN NOT has_lineage THEN 'Lineage'
        ELSE ''
      END as sanity_missing
    FROM `{project_id}.{bq_config['dataset']}.okrs_emea_analysis_view`
    WHERE 
      -- Only malformed OKRs
      CASE WHEN has_target_date THEN 0 ELSE 1 END +
      CASE WHEN teams_array IS NOT NULL AND ARRAY_LENGTH(teams_array) > 0 THEN 0 ELSE 1 END +
      CASE WHEN parent_goal IS NOT NULL THEN 0 ELSE 1 END +
      CASE WHEN owner IS NOT NULL AND TRIM(owner) != '' THEN 0 ELSE 1 END +
      CASE WHEN has_metric THEN 0 ELSE 1 END +
      CASE WHEN has_lineage THEN 0 ELSE 1 END > 0
    ORDER BY owner, goal_name
    """
    
    try:
        query_job = client.query(query)
        results = query_job.result()
        
        # Convert to DataFrame-like structure
        malformed_okrs = []
        for row in results:
            okr_dict = dict(row.items())
            # Map column names to expected format
            mapped_dict = {
                'Goal Key': okr_dict.get('goal_key', ''),
                'Name': okr_dict.get('goal_name', ''),
                'Owner': okr_dict.get('owner', ''),
                'Target Date': okr_dict.get('target_date', ''),
                'Parent Goal': okr_dict.get('parent_goal', ''),
                'Sub-goals': okr_dict.get('sub_goals_array', []),
                'Tags': okr_dict.get('tags_array', []),
                'Progress Type': okr_dict.get('progress_type', ''),
                'Teams': okr_dict.get('teams_array', []),
                'Start Date': okr_dict.get('start_date', ''),
                'Creation Date': okr_dict.get('creation_date', ''),
                'Lineage': okr_dict.get('lineage', ''),
                'EntityId': okr_dict.get('entity_id', ''),
                'sanity_missing': okr_dict.get('sanity_missing', [])
            }
            
            # Convert arrays to strings for compatibility
            if mapped_dict['Sub-goals']:
                mapped_dict['Sub-goals'] = ';'.join(mapped_dict['Sub-goals'])
            if mapped_dict['Tags']:
                mapped_dict['Tags'] = ';'.join(mapped_dict['Tags'])
            if mapped_dict['Teams']:
                mapped_dict['Teams'] = ';'.join(mapped_dict['Teams'])
            # Convert sanity_missing string to list
            if mapped_dict['sanity_missing'] and mapped_dict['sanity_missing'] != '':
                mapped_dict['sanity_missing'] = [mapped_dict['sanity_missing']]
            else:
                mapped_dict['sanity_missing'] = []
            
            malformed_okrs.append(mapped_dict)
        
        return malformed_okrs, []  # Return empty teams list for compatibility
        
    except Exception as e:
        raise Exception(f"Error querying BigQuery: {e}")

def post_comment_to_atlassian(entity_id, comment_text, config):
    """
    Post a comment to the Atlassian endpoint using the provided entity_id and comment_text.
    All headers, cookies, and endpoint URL are loaded from config.
    """
    # Compose the URL from config values
    base_url = config['ATLASSIAN_BASE_URL'].rstrip('/')
    cloud_id = config['CLOUD_ID']
    url = f"{base_url}/gateway/api/townsquare/s/{cloud_id}/graphql?operationName=CreateCommentMutation"
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'atl-client-name': config.get('ATL_CLIENT_NAME', 'townsquare-frontend'),
        'atl-client-version': config.get('ATL_CLIENT_VERSION', '71c854'),
        'content-type': 'application/json',
        'origin': config.get('ATL_ORIGIN', 'https://home.atlassian.com'),
        'referer': config.get('ATL_REFERER', ''),
        'user-agent': config.get('ATL_USER_AGENT', 'Mozilla/5.0'),
        'cookie': config['ATLASSIAN_COOKIES'],
    }
    # Compose the GraphQL payload
    graphql_query = ("mutation CreateCommentMutation(\n  $input: createCommentInput!\n) {\n  createComment(input: $input) {\n    comment {\n      id\n      ...Comment\n    }\n  }\n}\n\nfragment Comment on Comment {\n  id\n  ari\n  commentText\n  creationDate\n  editDate\n  creator {\n    aaid\n    ...UserAvatar\n    id\n  }\n}\n\nfragment UserAvatar on User {\n  aaid\n  pii {\n    picture\n    name\n    accountStatus\n    accountId\n  }\n}\n")
    # Atlassian expects commentText as a JSON string (rich text format)
    comment_text_json = json.dumps({
        "version": 1,
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": comment_text}]}
        ]
    })
    variables = {
        "input": {
            "entityId": entity_id,
            "commentText": comment_text_json
        },
        "connections": [f"client:{entity_id}:comments"]
    }
    payload = {
        "query": graphql_query,
        "variables": variables
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    return response

def main():
    parser = argparse.ArgumentParser(description='Post comments to Atlassian for malformed OKRs')
    parser.add_argument('--file', '-f', type=str, help='Specify the CSV file to analyze (local file)')
    parser.add_argument('--cloud', '-c', action='store_true', help='Download and analyze the latest file from Cloud Storage bucket')
    parser.add_argument('--bigquery', '-b', action='store_true', help='Get malformed OKRs directly from BigQuery external table')
    args = parser.parse_args()

    # Validate arguments
    source_count = sum([bool(args.file), args.cloud, args.bigquery])
    if source_count == 0:
        print("❌ Please specify a data source: --file, --cloud, or --bigquery")
        return
    elif source_count > 1:
        print("❌ Please specify only one data source: --file, --cloud, or --bigquery")
        return

    print("\n🔍 Loading malformed OKRs...")
    
    try:
        if args.bigquery:
            print("📊 Loading from BigQuery...")
            malformed_okrs, teams_df = get_malformed_okrs_from_bigquery()
            # Convert to DataFrame-like structure for compatibility
            import pandas as pd
            malformed_okrs = pd.DataFrame(malformed_okrs)
        else:
            print("📁 Loading from CSV...")
            malformed_okrs, teams_df = get_malformed_okrs_and_teams(file=args.file, cloud=args.cloud)
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        return

    if malformed_okrs.empty:
        print("🎉 No malformed OKRs found. Exiting.")
        return

    print(f"Found {len(malformed_okrs)} malformed OKRs.\n")

    # Load config
    try:
        config = load_config()
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return

    for idx, row in malformed_okrs.iterrows():
        okr_name = row.get('Name', 'Unknown OKR')
        owner = row.get('Owner', 'Unknown Owner')
        missing_fields = row.get('sanity_missing', [])
        message = generate_okr_comment_message(row)
        # Get OKR URL if present, else construct
        okr_url = row.get('url')
        if not okr_url or str(okr_url).lower() == 'null':
            # Try to construct from config and Goal Key
            base_url = config.get('ATLASSIAN_BASE_URL', '').rstrip('/')
            cloud_id = config.get('CLOUD_ID', '')
            goal_key = row.get('Goal Key', '')
            if base_url and cloud_id and goal_key:
                okr_url = f"{base_url}/o/{config.get('ORGANIZATION_ID','')}/s/{cloud_id}/goal/{goal_key}"
            else:
                okr_url = '(URL not available)'
        print("="*60)
        print(f"OKR: {okr_name}\nOwner: {owner}")
        print(f"Atlas URL: {okr_url}")
        print(f"Missing fields: {', '.join(missing_fields)}")
        print("\nPreview of comment to be posted:")
        print("-"*60)
        print(message)
        print("-"*60)
        confirm = input("Do you want to post this comment to Atlassian? [y/N]: ").strip().lower()
        if confirm != 'y':
            print("Skipping this OKR.\n")
            continue
        # Get entityId for this OKR
        entity_id = get_entity_id_from_row(row, config)
        if not entity_id:
            print("❌ Could not determine entityId for this OKR. Skipping.\n")
            continue
        print("Posting comment...")
        response = post_comment_to_atlassian(entity_id, message, config)
        if response.status_code == 200:
            print("✅ Comment posted successfully!\n")
        else:
            print(f"❌ Failed to post comment. Status: {response.status_code}\nResponse: {response.text}\n")

if __name__ == "__main__":
    main() 