#!/usr/bin/env python3
"""
Configuration loader for OKRs reporting tools.
Loads configuration from config.env file.
"""

import os
from pathlib import Path


def load_config():
    """
    Load configuration from config.env file.
    
    Returns:
        dict: Configuration dictionary with all environment variables
        
    Raises:
        FileNotFoundError: If config.env file is not found
        ValueError: If required variables are missing
    """
    # Find config.env file (look in current dir and parent dirs)
    config_file = None
    current_dir = Path.cwd()
    
    # Look for config.env in current directory and up to 3 levels up
    for i in range(4):
        potential_config = current_dir / "config.env"
        if potential_config.exists():
            config_file = potential_config
            break
        current_dir = current_dir.parent
    
    if not config_file:
        raise FileNotFoundError(
            "config.env file not found. Please copy config.env.example to config.env and configure it."
        )
    
    # Load environment variables from config.env
    config = {}
    with open(config_file, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Parse KEY=VALUE format
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                config[key] = value
    
    return config


def get_bigquery_config():
    """
    Get BigQuery specific configuration.
    
    Returns:
        dict: BigQuery configuration with keys: project, dataset, table, teams_table
    """
    config = load_config()
    
    # Extract BigQuery configuration
    bq_config = {
        'project': config.get('BQ_PROJECT', '').strip() or None,
        'dataset': config.get('BQ_DATASET', 'okrs_dataset'),
        'table': config.get('BQ_TABLE', 'okrs_table'),
        'teams_table': config.get('BQ_TEAMS_TABLE', 'teams')
    }
    
    return bq_config


def get_atlassian_config():
    """
    Get Atlassian specific configuration.
    
    Returns:
        dict: Atlassian configuration
    """
    config = load_config()
    
    # Required Atlassian variables
    required_vars = [
        'ATLASSIAN_BASE_URL',
        'ORGANIZATION_ID', 
        'CLOUD_ID',
        'WORKSPACE_UUID',
        'DIRECTORY_VIEW_UUID',
        'CUSTOM_FIELD_UUID',
        'ATLASSIAN_COOKIES'
    ]
    
    atlassian_config = {}
    missing_vars = []
    
    for var in required_vars:
        value = config.get(var, '').strip()
        if not value:
            missing_vars.append(var)
        atlassian_config[var.lower()] = value
    
    if missing_vars:
        raise ValueError(f"Missing required Atlassian configuration variables: {', '.join(missing_vars)}")
    
    return atlassian_config


def get_cre_teams():
    """
    Get CRE teams list from configuration.
    
    Returns:
        list: List of CRE team names
    """
    config = load_config()
    
    cre_teams_str = config.get('CRE_TEAMS', '').strip()
    if not cre_teams_str:
        # Default teams if not configured
        return [
            "SNEMEA Pod 1", "SNEMEA Pod 2", "SNEMEA Pod 3", 
            "IL Pod 3", "UKI Pod 3", "UKI Pod 4", "EMEA Leadership"
        ]
    
    # Split by comma and clean up whitespace
    return [team.strip() for team in cre_teams_str.split(',') if team.strip()]


def get_exclude_teams():
    """
    Get teams to exclude from reports.
    
    Returns:
        list: List of team names to exclude
    """
    config = load_config()
    
    exclude_teams_str = config.get('EXCLUDE_TEAMS', '').strip()
    if not exclude_teams_str:
        # Default exclusions if not configured
        return ["Sakura", "au-pod-1"]
    
    # Split by comma and clean up whitespace
    return [team.strip() for team in exclude_teams_str.split(',') if team.strip()]


def get_us_people():
    """
    Get US-based people to exclude from EMEA analysis.
    
    Returns:
        list: List of US people names (lowercase)
    """
    config = load_config()
    
    us_people_str = config.get('US_PEOPLE', '').strip()
    if not us_people_str:
        # Default US people if not configured
        return ['zaar hai', 'arri rucker', 'kendall wondergem', 'satyam gupta']
    
    # Split by comma and clean up whitespace, convert to lowercase
    return [person.strip().lower() for person in us_people_str.split(',') if person.strip()]


if __name__ == "__main__":
    # Test the configuration loader
    try:
        config = load_config()
        print("✅ Configuration loaded successfully")
        print(f"📊 Found {len(config)} configuration variables")
        
        bq_config = get_bigquery_config()
        print(f"🗄️  BigQuery dataset: {bq_config['dataset']}")
        print(f"📋 BigQuery table: {bq_config['table']}")
        print(f"👥 Teams table: {bq_config['teams_table']}")
        
        atlassian_config = get_atlassian_config()
        print(f"🏢 Atlassian organization: {atlassian_config['organization_id']}")
        
        cre_teams = get_cre_teams()
        print(f"👥 CRE teams configured: {len(cre_teams)}")
        for team in cre_teams:
            print(f"   - {team}")
        
        exclude_teams = get_exclude_teams()
        print(f"🚫 Teams to exclude: {len(exclude_teams)}")
        for team in exclude_teams:
            print(f"   - {team}")
        
        us_people = get_us_people()
        print(f"🇺🇸 US people to exclude: {len(us_people)}")
        for person in us_people:
            print(f"   - {person}")
        
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        exit(1) 