#!/usr/bin/env python3
"""
Post comments to Atlassian for malformed OKRs

This script loads malformed OKRs using the shared logic from okrs_sanity_check_scrap_data.py,
generates a specific English message for each malformed OKR, shows a preview, asks for confirmation,
and if accepted, posts a comment to the Atlassian endpoint using config.env values.

Usage:
    python post_okr_comments.py [--file <csv_file>] [--cloud]

Dependencies are managed in pyproject.toml. Install with: uv sync
"""

import sys
import os
import argparse
import json
import requests
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / 'helpers'))
from config_loader import load_config

sys.path.append(str(Path(__file__).parent))
from okrs_sanity_check_scrap_data import get_malformed_okrs_and_teams, is_empty_or_null

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
    # Fallbacks
    if 'entityId' in okr_row:
        return okr_row['entityId']
    if 'Goal Key' in okr_row and 'ATLASSIAN_ENTITY_ID_PREFIX' in config:
        return config['ATLASSIAN_ENTITY_ID_PREFIX'] + str(okr_row['Goal Key'])
    return config.get('ATLASSIAN_ENTITY_ID')

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
    parser.add_argument('--file', '-f', type=str, help='Specify the CSV file to analyze (optional)')
    parser.add_argument('--cloud', '-c', action='store_true', help='Download and analyze the latest file from Cloud Storage bucket')
    args = parser.parse_args()

    print("\n🔍 Loading malformed OKRs...")
    malformed_okrs, teams_df = get_malformed_okrs_and_teams(file=args.file, cloud=args.cloud)

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