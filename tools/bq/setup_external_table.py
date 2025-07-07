#!/usr/bin/env python3
"""
Setup BigQuery External Table for OKRs data in Cloud Storage

This script creates an external table in BigQuery that points to CSV files
stored in Cloud Storage, along with helpful views for analysis.

Usage:
    python tools/setup_external_table.py [--dry-run]

Arguments:
    --dry-run    Print SQL commands without executing them

Dependencies are managed in pyproject.toml. Install with: uv sync
"""

import sys
import argparse
from pathlib import Path

# Add helpers to path
sys.path.append(str(Path(__file__).parent.parent.parent / 'helpers'))
from config_loader import get_bigquery_config, load_config

try:
    from google.cloud import bigquery
    BIGQUERY_AVAILABLE = True
except ImportError:
    BIGQUERY_AVAILABLE = False
    print("❌ Google Cloud BigQuery library not available")
    print("   Install with: pip install google-cloud-bigquery")
    sys.exit(1)


def get_bucket_name():
    """Get the Cloud Storage bucket name from configuration"""
    config = load_config()
    
    # Try to get bucket name from environment, otherwise construct it
    bucket_name = config.get('GCS_BUCKET_NAME', '').strip()
    if not bucket_name:
        project_id = config.get('PROJECT_ID', '').strip()
        if project_id:
            bucket_name = f"{project_id}-okrs-data"
        else:
            # Try to get from BigQuery config
            bq_config = get_bigquery_config()
            if bq_config['project']:
                bucket_name = f"{bq_config['project']}-okrs-data"
            else:
                raise ValueError("Could not determine bucket name. Set GCS_BUCKET_NAME or PROJECT_ID in config.env")
    
    return bucket_name


def load_sql_template():
    """Load the SQL DDL template"""
    sql_file = Path(__file__).parent.parent.parent / 'sql' / 'create_external_table.sql'
    
    if not sql_file.exists():
        raise FileNotFoundError(f"SQL template not found: {sql_file}")
    
    with open(sql_file, 'r') as f:
        return f.read()


def substitute_variables(sql_content, project_id, bucket_name):
    """Substitute variables in SQL template"""
    return sql_content.replace('{project_id}', project_id).replace('{bucket_name}', bucket_name)


def execute_sql_statements(client, sql_content, dry_run=False):
    """Execute SQL statements, splitting by semicolon"""
    
    # Split SQL into individual statements
    statements = []
    current_statement = []
    
    for line in sql_content.split('\n'):
        # Skip empty lines and comments
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith('--'):
            continue
            
        current_statement.append(line)
        
        # If line ends with semicolon, it's the end of a statement
        if stripped_line.endswith(';'):
            statement = '\n'.join(current_statement).strip()
            if statement:
                statements.append(statement)
            current_statement = []
    
    # Add any remaining statement
    if current_statement:
        statement = '\n'.join(current_statement).strip()
        if statement:
            statements.append(statement)
    
    print(f"📋 Found {len(statements)} SQL statements to execute\n")
    
    for i, statement in enumerate(statements, 1):
        print(f"🔧 Statement {i}/{len(statements)}:")
        
        # Extract object name for logging
        if 'CREATE OR REPLACE EXTERNAL TABLE' in statement:
            object_type = "External Table"
        elif 'CREATE OR REPLACE VIEW' in statement:
            object_type = "View"
        else:
            object_type = "SQL Statement"
        
        if dry_run:
            print(f"   [DRY RUN] Would execute {object_type}")
            print(f"   SQL Preview:")
            # Show first few lines of the statement
            lines = statement.split('\n')[:5]
            for line in lines:
                print(f"     {line}")
            if len(statement.split('\n')) > 5:
                print(f"     ... ({len(statement.split('\n')) - 5} more lines)")
            print()
        else:
            try:
                print(f"   Executing {object_type}...")
                job = client.query(statement)
                job.result()  # Wait for completion
                print(f"   ✅ {object_type} created successfully")
                print()
            except Exception as e:
                print(f"   ❌ Error creating {object_type}: {e}")
                print(f"   Statement: {statement[:200]}...")
                print()
                raise


def main():
    parser = argparse.ArgumentParser(description='Setup BigQuery External Table for OKRs')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Print SQL commands without executing them')
    args = parser.parse_args()
    
    print("🚀 Setting up BigQuery External Table for OKRs data\n")
    
    try:
        # Load configuration
        bq_config = get_bigquery_config()
        bucket_name = get_bucket_name()
        
        # Determine project ID
        if bq_config['project']:
            project_id = bq_config['project']
        else:
            # Use default project from environment
            try:
                client = bigquery.Client()
                project_id = client.project
            except Exception as e:
                raise ValueError(f"Could not determine project ID: {e}")
        
        print(f"📊 Configuration:")
        print(f"   • Project ID: {project_id}")
        print(f"   • Dataset: {bq_config['dataset']}")
        print(f"   • Bucket: {bucket_name}")
        print(f"   • Dry run: {args.dry_run}")
        print()
        
        # Load and process SQL
        sql_template = load_sql_template()
        sql_content = substitute_variables(sql_template, project_id, bucket_name)
        
        if not args.dry_run:
            # Create BigQuery client
            client = bigquery.Client(project=project_id) if bq_config['project'] else bigquery.Client()
            
            # Ensure dataset exists
            dataset_id = f"{project_id}.{bq_config['dataset']}"
            try:
                client.get_dataset(dataset_id)
                print(f"✅ Dataset {dataset_id} exists")
            except Exception:
                print(f"📦 Creating dataset {dataset_id}...")
                dataset = bigquery.Dataset(dataset_id)
                dataset.location = "EU"  # Set to EU for EMEA data
                client.create_dataset(dataset)
                print(f"✅ Dataset {dataset_id} created")
            print()
        else:
            client = None
        
        # Execute SQL statements
        execute_sql_statements(client, sql_content, args.dry_run)
        
        if args.dry_run:
            print("🔍 Dry run completed - no changes made")
            print("\nTo execute the changes, run:")
            print("   python tools/bq/setup_external_table.py")
        else:
            print("🎉 External table setup completed successfully!")
            print(f"\n📋 Available objects in {bq_config['dataset']}:")
            print(f"   • okrs_external - External table pointing to Cloud Storage")
            print(f"   • okrs_analysis_view - Cleaned and enriched data")
            print(f"   • okrs_latest_view - Most recent data only")
            print(f"   • okrs_emea_analysis_view - EMEA team analysis")
            
            print(f"\n🔍 Example queries:")
            print(f"   SELECT COUNT(*) FROM `{project_id}.{bq_config['dataset']}.okrs_latest_view`;")
            print(f"   SELECT health_status, COUNT(*) FROM `{project_id}.{bq_config['dataset']}.okrs_latest_view` GROUP BY 1;")
            print(f"   SELECT * FROM `{project_id}.{bq_config['dataset']}.okrs_emea_analysis_view` LIMIT 10;")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 