#!/usr/bin/env python3
"""
Generate personalized Slack messages for OKR fixes

This script analyzes malformed OKRs and generates personalized Slack messages
for each person explaining what needs to be fixed in their OKRs.

Usage:
    python generate_okr_fix_messages.py [--file <csv_file>] [--cloud]
    python generate_okr_fix_messages.py -f scraped/export-20250706_102541_processed.csv
    python generate_okr_fix_messages.py --cloud

Arguments:
    --file, -f    Specify the CSV file to analyze (optional)
                  If not provided, uses the most recent file in scraped/
    --cloud, -c   Download and analyze the latest file from Cloud Storage bucket
                  Uses GCS_BUCKET_NAME environment variable (optional, defaults to ${PROJECT_ID}-okrs-data)

Dependencies are managed in pyproject.toml. Install with: uv sync
"""

import pandas as pd
import os
import sys
import argparse
from pathlib import Path
from io import StringIO
import tempfile

# Add helpers to path
sys.path.append(str(Path(__file__).parent.parent / 'helpers'))
from config_loader import load_config

try:
    from google.cloud import storage
    CLOUD_STORAGE_AVAILABLE = True
except ImportError:
    CLOUD_STORAGE_AVAILABLE = False

def find_latest_csv():
    """Find the most recent processed CSV file"""
    import glob
    csv_files = glob.glob("scraped/export-*_processed*.csv")
    if not csv_files:
        raise FileNotFoundError("No CSV files found matching pattern: scraped/export-*_processed*.csv")
    
    latest_file = max(csv_files, key=os.path.getmtime)
    return latest_file

def load_team_members():
    """Load team members from teams.csv"""
    if not os.path.exists("data/teams.csv"):
        raise FileNotFoundError("Teams file not found: data/teams.csv")
    
    teams_df = pd.read_csv("data/teams.csv")
    team_members = set(teams_df['name'].str.strip())
    return teams_df, team_members

def download_latest_from_cloud():
    """Download the latest OKRs CSV file from Cloud Storage"""
    if not CLOUD_STORAGE_AVAILABLE:
        raise ImportError("google-cloud-storage not available. Install with: pip install google-cloud-storage")
    
    # Get bucket name - either from env var or compose from project ID
    bucket_name = os.getenv('GCS_BUCKET_NAME')
    if not bucket_name:
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        if not project_id:
            # Try to get from gcloud config
            try:
                import subprocess
                result = subprocess.run(['gcloud', 'config', 'get-value', 'project'], 
                                      capture_output=True, text=True, check=True)
                project_id = result.stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                raise ValueError("Cannot determine project ID. Set GOOGLE_CLOUD_PROJECT or GCS_BUCKET_NAME environment variable")
        
        bucket_name = f"{project_id}-okrs-data"
    
    print(f"☁️ Connecting to Cloud Storage bucket: {bucket_name}")
    
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        
        # List all CSV files in the okrs/ prefix
        blobs = list(bucket.list_blobs(prefix="okrs/export-"))
        
        # Filter for processed CSV files
        csv_blobs = [blob for blob in blobs if blob.name.endswith('_processed.csv')]
        
        if not csv_blobs:
            raise FileNotFoundError("No processed CSV files found in Cloud Storage bucket")
        
        # Sort by creation time and get the most recent
        latest_blob = max(csv_blobs, key=lambda b: b.time_created)
        
        print(f"📁 Latest file found: {latest_blob.name}")
        print(f"📅 Created: {latest_blob.time_created}")
        
        # Download content as string
        csv_content = latest_blob.download_as_text()
        
        # Create a temporary file
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        temp_file.write(csv_content)
        temp_file.close()
        
        print(f"⬇️ Downloaded to temporary file: {temp_file.name}")
        return temp_file.name, latest_blob.name
        
    except Exception as e:
        raise Exception(f"Error downloading from Cloud Storage: {e}")

def is_empty_or_null(value):
    """Check if a value is empty, null, nan, or None"""
    if value is None:
        return True
    
    str_value = str(value).strip().lower()
    return str_value in ['', 'null', 'nan', 'none', 'na']

def enhanced_okr_sanity_check(row):
    """Enhanced sanity check for OKRs - returns list of missing fields"""
    missing = []
    
    if is_empty_or_null(row.get('Target Date')):
        missing.append('Target Date')
    if is_empty_or_null(row.get('Teams')):
        missing.append('Teams')
    if is_empty_or_null(row.get('Parent Goal')):
        missing.append('Parent Goal')
    if is_empty_or_null(row.get('Owner')):
        missing.append('Owner')
    
    progress_type = str(row.get('Progress Type', '')).strip()
    if is_empty_or_null(progress_type) or progress_type == 'NONE':
        missing.append('Progress Type (Metric)')
    
    if is_empty_or_null(row.get('Lineage')):
        missing.append('Lineage')
    
    return missing

def format_missing_fields_short(missing_fields):
    """Format missing fields into short symbols"""
    field_symbols = {
        'Target Date': '📅',
        'Teams': '👥', 
        'Parent Goal': '🔗',
        'Owner': '👤',
        'Progress Type (Metric)': '📈',
        'Lineage': '🌳'
    }
    
    return ' '.join([field_symbols.get(field, '❓') for field in missing_fields])

def generate_slack_message(person_name, malformed_okrs_data):
    """Generate a personalized Slack message for a person with malformed OKRs"""
    
    # Extract first name only (first word)
    first_name = person_name.split()[0]
    
    # Build table rows
    table_rows = []
    for _, okr in malformed_okrs_data.iterrows():
        okr_name = okr.get('Name', 'Unknown OKR')
        missing_fields = enhanced_okr_sanity_check(okr)
        missing_symbols = format_missing_fields_short(missing_fields)
        
        # Truncate long OKR names
        if len(okr_name) > 40:
            okr_name = okr_name[:37] + "..."
        
        table_rows.append(f"| {okr_name:<43} | {missing_symbols:<8} |")
    
    table_content = '\n'.join(table_rows)
    
    message = f"""Hi {first_name}! 👋

Your OKRs need some updates in Atlas:

```
| OKR Name                                    | Missing  |
|---------------------------------------------|----------|
{table_content}
```

Legend: 📅 Target Date | 👥 Teams | 🔗 Parent Goal | 👤 Owner | 📈 Metric | 🌳 Lineage

Please update when you can. Thanks! 🙏"""
    
    return message

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Generate personalized Slack messages for OKR fixes')
    parser.add_argument('--file', '-f', type=str, help='Specify the CSV file to analyze (optional)')
    parser.add_argument('--cloud', '-c', action='store_true', help='Download and analyze the latest file from Cloud Storage bucket')
    args = parser.parse_args()
    
    # Validate arguments
    if args.file and args.cloud:
        print("❌ Error: Cannot use both --file and --cloud options simultaneously")
        return
    
    print("📝 Generating OKR Fix Messages")
    print("=" * 50)
    print()
    
    # Load configuration
    try:
        config = load_config()
        print("✅ Configuration loaded successfully")
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        return
    
    # Load team members
    print("📋 Loading team members...")
    try:
        teams_df, team_members = load_team_members()
        print(f"✅ Loaded {len(team_members)} team members from {len(teams_df['team'].unique())} teams")
    except Exception as e:
        print(f"❌ Error loading team members: {e}")
        return
    
    # Find and load CSV
    print("📊 Loading OKRs CSV...")
    temp_file_to_cleanup = None
    try:
        if args.cloud:
            # Download from Cloud Storage
            csv_file, cloud_filename = download_latest_from_cloud()
            temp_file_to_cleanup = csv_file
            print(f"✅ Using latest file from cloud: {cloud_filename}")
        elif args.file:
            # Use specified file
            csv_file = args.file
            if not os.path.exists(csv_file):
                print(f"❌ Specified file not found: {csv_file}")
                return
            print(f"✅ Using specified file: {csv_file}")
        else:
            # Auto-detect latest local file
            csv_file = find_latest_csv()
            print(f"✅ Using latest local file: {csv_file}")
        
        okrs_df = pd.read_csv(csv_file)
        print(f"📊 Total OKRs in CSV: {len(okrs_df)}")
    except Exception as e:
        print(f"❌ Error loading OKRs data: {e}")
        # Cleanup temp file if it exists
        if temp_file_to_cleanup and os.path.exists(temp_file_to_cleanup):
            os.unlink(temp_file_to_cleanup)
        return
    
    # Filter only team members' OKRs
    team_okrs = okrs_df[okrs_df['Owner'].str.strip().isin(team_members)].copy()
    print(f"🎯 OKRs from team members: {len(team_okrs)}")
    print()
    
    if team_okrs.empty:
        print("❌ No OKRs found for team members!")
        return
    
    # Perform sanity check
    print("🔍 Analyzing malformed OKRs...")
    team_okrs['sanity_missing'] = team_okrs.apply(enhanced_okr_sanity_check, axis=1)
    team_okrs['is_sane'] = team_okrs['sanity_missing'].apply(lambda x: len(x) == 0)
    
    # Get malformed OKRs
    malformed_okrs = team_okrs[~team_okrs['is_sane']]
    
    if malformed_okrs.empty:
        print("🎉 All OKRs are healthy! No messages needed.")
        return
    
    print(f"📝 Found {len(malformed_okrs)} malformed OKRs from {malformed_okrs['Owner'].nunique()} people")
    print()
    
    # Generate messages for each person
    messages = {}
    for person in malformed_okrs['Owner'].unique():
        person_malformed_okrs = malformed_okrs[malformed_okrs['Owner'] == person]
        message = generate_slack_message(person, person_malformed_okrs)
        messages[person] = message
    
    # Output messages
    print("📤 Generated Slack Messages:")
    print("=" * 60)
    print()
    
    for i, (person, message) in enumerate(messages.items(), 1):
        print(f"MESSAGE {i}: {person}")
        print("-" * 40)
        print(message)
        print()
        print("-" * 60)
        print()
    
    # Summary
    print(f"✅ Generated {len(messages)} personalized messages")
    print()
    
    # Optional: Save to file
    output_file = "okr_fix_messages.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("OKR Fix Messages\n")
        f.write("=" * 50 + "\n\n")
        
        for i, (person, message) in enumerate(messages.items(), 1):
            f.write(f"MESSAGE {i}: {person}\n")
            f.write("-" * 40 + "\n")
            f.write(message + "\n\n")
            f.write("-" * 60 + "\n\n")
    
    print(f"💾 Messages also saved to: {output_file}")
    
    # Cleanup temporary file if it exists
    if temp_file_to_cleanup and os.path.exists(temp_file_to_cleanup):
        os.unlink(temp_file_to_cleanup)
        print("🗑️ Temporary file cleaned up")

if __name__ == "__main__":
    main() 