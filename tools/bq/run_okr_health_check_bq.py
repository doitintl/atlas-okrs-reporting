#!/usr/bin/env python3
"""
Run OKR Health Check Queries on BigQuery External Table

This script executes the enhanced OKR sanity check queries directly on BigQuery,
providing the same analysis as okrs_sanity_check_scrap_data.py but using the external table.

Usage:
    python tools/run_okr_health_check_bq.py [--query <query_number>] [--format <format>]

Arguments:
    --query     Run specific query only (1-9), otherwise runs summary
    --format    Output format: table (default), json, csv

Dependencies are managed in pyproject.toml. Install with: uv sync
"""

import sys
import argparse
from pathlib import Path
from tabulate import tabulate
import json

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


def get_project_id():
    """Get the project ID from configuration"""
    bq_config = get_bigquery_config()
    if bq_config['project']:
        return bq_config['project']
    else:
        # Use default project from environment
        try:
            client = bigquery.Client()
            return client.project
        except Exception as e:
            raise ValueError(f"Could not determine project ID: {e}")


def load_sql_queries():
    """Load the SQL queries from the template file"""
    sql_file = Path(__file__).parent.parent.parent / 'sql' / 'example_queries.sql'
    
    if not sql_file.exists():
        raise FileNotFoundError(f"SQL queries file not found: {sql_file}")
    
    with open(sql_file, 'r') as f:
        content = f.read()
    
    # Split queries by sections and extract them
    queries = {}
    current_section = None
    current_query = []
    
    for line in content.split('\n'):
        stripped = line.strip()
        
        # Detect section headers
        if stripped.startswith('-- ') and any(x in stripped for x in ['1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.']):
            # Save previous query if exists
            if current_section and current_query:
                query_text = '\n'.join(current_query).strip()
                if query_text:
                    queries[current_section] = query_text
            
            # Extract section number and title
            section_parts = stripped.replace('-- ', '').split(' ', 1)
            if len(section_parts) >= 2:
                section_num = section_parts[0].replace('.', '')
                section_title = section_parts[1]
                current_section = f"{section_num}. {section_title}"
                current_query = []
        
        elif current_section and not stripped.startswith('--'):
            # Add non-comment lines to current query
            current_query.append(line)
    
    # Save last query
    if current_section and current_query:
        query_text = '\n'.join(current_query).strip()
        if query_text:
            queries[current_section] = query_text
    
    return queries


def substitute_project_id(query_text, project_id):
    """Replace project_id placeholder in SQL"""
    return query_text.replace('{project_id}', project_id)


def execute_query(client, query, project_id):
    """Execute a BigQuery query and return results"""
    query_with_project = substitute_project_id(query, project_id)
    
    job = client.query(query_with_project)
    results = job.result()
    
    # Convert to list of dictionaries
    rows = []
    for row in results:
        row_dict = {}
        for i, field in enumerate(results.schema):
            row_dict[field.name] = row[i]
        rows.append(row_dict)
    
    return rows, results.schema


def format_output(rows, schema, output_format):
    """Format query results for display"""
    if not rows:
        return "No results found."
    
    if output_format == 'json':
        return json.dumps(rows, indent=2, default=str)
    
    elif output_format == 'csv':
        import csv
        import io
        
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return output.getvalue()
    
    else:  # table format (default)
        if rows:
            return tabulate(rows, headers="keys", tablefmt="fancy_grid", showindex=False)
        return "No data to display."


def run_summary_queries(client, project_id, output_format):
    """Run key summary queries for a quick health check overview"""
    queries = load_sql_queries()
    
    print("🚀 OKR Health Check Summary Report")
    print("=" * 60)
    print()
    
    # Query 1: Enhanced OKR Sanity Check Summary
    print("📊 1. OVERALL HEALTH SUMMARY")
    print("-" * 40)
    try:
        summary_query = queries.get("1. ENHANCED OKR SANITY CHECK SUMMARY")
        if summary_query:
            rows, schema = execute_query(client, summary_query, project_id)
            print(format_output(rows, schema, output_format))
        print()
    except Exception as e:
        print(f"❌ Error running summary query: {e}")
        print()
    
    # Query 2: Health by Team
    print("👥 2. HEALTH BY TEAM")
    print("-" * 40)
    try:
        team_query = queries.get("2. OKRs HEALTH BY TEAM")
        if team_query:
            rows, schema = execute_query(client, team_query, project_id)
            print(format_output(rows, schema, output_format))
        print()
    except Exception as e:
        print(f"❌ Error running team health query: {e}")
        print()
    
    # Query 6: People without OKRs
    print("🚨 6. PEOPLE WITHOUT OKRs")
    print("-" * 40)
    try:
        missing_query = queries.get("6. PEOPLE WITHOUT OKRs BY TEAM")
        if missing_query:
            rows, schema = execute_query(client, missing_query, project_id)
            if rows:
                print(format_output(rows, schema, output_format))
            else:
                print("🎉 All team members have OKRs!")
        print()
    except Exception as e:
        print(f"❌ Error running missing people query: {e}")
        print()
    
    print("✅ Health check summary completed!")


def run_specific_query(client, project_id, query_number, output_format):
    """Run a specific query by number"""
    queries = load_sql_queries()
    
    # Find the query by number
    target_query = None
    query_title = None
    for title, sql in queries.items():
        if title.startswith(f"{query_number}."):
            target_query = sql
            query_title = title
            break
    
    if not target_query:
        print(f"❌ Query {query_number} not found. Available queries:")
        for title in queries.keys():
            print(f"   {title}")
        return
    
    print(f"🔍 Running Query: {query_title}")
    print("=" * 60)
    print()
    
    try:
        rows, schema = execute_query(client, target_query, project_id)
        print(format_output(rows, schema, output_format))
        print()
        print(f"✅ Query completed. {len(rows)} rows returned.")
    except Exception as e:
        print(f"❌ Error executing query: {e}")


def main():
    parser = argparse.ArgumentParser(description='Run OKR Health Check Queries on BigQuery')
    parser.add_argument('--query', type=int, help='Run specific query only (1-9)')
    parser.add_argument('--format', choices=['table', 'json', 'csv'], default='table',
                       help='Output format (default: table)')
    args = parser.parse_args()
    
    try:
        # Get configuration
        project_id = get_project_id()
        
        print(f"📊 Project: {project_id}")
        print(f"📋 Format: {args.format}")
        print()
        
        # Create BigQuery client
        client = bigquery.Client(project=project_id)
        
        if args.query:
            # Run specific query
            run_specific_query(client, project_id, args.query, args.format)
        else:
            # Run summary queries
            run_summary_queries(client, project_id, args.format)
            
            # Show available queries
            print("\n📋 Available detailed queries:")
            queries = load_sql_queries()
            for title in sorted(queries.keys()):
                query_num = title.split('.')[0]
                print(f"   python tools/bq/run_okr_health_check_bq.py --query {query_num}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 