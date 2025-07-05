#!/usr/bin/env python3
"""
Generate personalized Slack messages for OKR fixes

This script analyzes malformed OKRs and generates personalized Slack messages
for each person explaining what needs to be fixed in their OKRs.

Usage:
    python generate_okr_fix_messages.py

Dependencies are managed in pyproject.toml. Install with: uv sync
"""

import pandas as pd
import os
import sys
from pathlib import Path

# Add helpers to path
sys.path.append(str(Path(__file__).parent.parent / 'helpers'))
from config_loader import load_config

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
    
    # Find and load latest CSV
    print("📊 Finding latest OKRs CSV...")
    try:
        latest_csv = find_latest_csv()
        print(f"✅ Using: {latest_csv}")
        
        okrs_df = pd.read_csv(latest_csv)
        print(f"📊 Total OKRs in CSV: {len(okrs_df)}")
    except Exception as e:
        print(f"❌ Error loading OKRs data: {e}")
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

if __name__ == "__main__":
    main() 