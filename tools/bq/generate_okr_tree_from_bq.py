"""
Script to generate goals tree for CRE teams with owners in parentheses.

⚠️  MIGRATED TO EXTERNAL TABLES: This script now uses BigQuery external table views
   instead of loaded CSV data for better performance and real-time analysis.

Dependencies are managed in pyproject.toml. Install with: uv sync
"""
import sys
import os
from pathlib import Path

# Add helpers directory to path for config loader (go up 3 levels: bq -> tools -> project root -> helpers)
helpers_dir = Path(__file__).parent.parent.parent / "helpers"
sys.path.insert(0, str(helpers_dir))

from config_loader import get_bigquery_config, get_cre_teams
import pandas as pd
from google.cloud import bigquery
from typing import Dict, List, Set

# Load configuration
config = get_bigquery_config()

# CRE Teams (Customer Reliability Engineers) - from configuration
CRE_TEAMS = get_cre_teams()

def get_cre_team_members(client):
    """Get all CRE team members"""
    teams_query = f'''
    SELECT team, name AS person 
    FROM `{config["dataset"]}.{config["teams_table"]}`
    WHERE team IN ({",".join([f"'{team}'" for team in CRE_TEAMS])})
    '''
    teams_df = client.query(teams_query).to_dataframe()
    return set(teams_df['person'].str.strip())

def get_okrs_data(client):
    """Get all OKRs from the most recent snapshot using external table views"""
    # Use latest view instead of raw table - automatically gets most recent data
    okrs_query = f'SELECT * FROM `{config["dataset"]}.okrs_latest_view`'
    okrs_df = client.query(okrs_query).to_dataframe()
    return okrs_df

def build_goal_hierarchy(okrs_df: pd.DataFrame, cre_members: Set[str]) -> Dict:
    """Build goal hierarchy filtering by CRE members"""
    
    # Create maps for efficient navigation
    goal_id_to_data = {}
    goal_id_to_children = {}
    goal_id_to_parent = {}
    root_goals = set()
    
    for _, row in okrs_df.iterrows():
        goal_id = row.get('Goal Key', '') or ''
        goal_name = row.get('Name', '') or ''
        owner = (row.get('Owner', '') or '').strip()
        parent_goal_id = (row.get('Parent Goal', '') or '').strip()
        
        if not goal_id:
            continue
            
        # Store goal data
        goal_id_to_data[goal_id] = {
            'name': goal_name,
            'owner': owner,
            'parent_id': parent_goal_id if parent_goal_id else None
        }
        
        # Map parent-child relationships
        goal_id_to_parent[goal_id] = parent_goal_id if parent_goal_id else None
        
        if parent_goal_id:
            if parent_goal_id not in goal_id_to_children:
                goal_id_to_children[parent_goal_id] = []
            goal_id_to_children[parent_goal_id].append(goal_id)
        else:
            root_goals.add(goal_id)
    
    def is_cre_related(goal_id: str, visited: Set[str] = None) -> bool:
        """Check if a goal is related to CREs (recursively)"""
        if visited is None:
            visited = set()
            
        if goal_id in visited:
            return False
            
        visited.add(goal_id)
        
        # Check if direct owner is CRE
        goal_data = goal_id_to_data.get(goal_id, {})
        if goal_data.get('owner', '') in cre_members:
            return True
            
        # Check children recursively
        children = goal_id_to_children.get(goal_id, [])
        for child_id in children:
            if is_cre_related(child_id, visited.copy()):
                return True
                
        return False
    
    # Filter only CRE-related goals
    cre_related_goals = {goal_id for goal_id in goal_id_to_data.keys() if is_cre_related(goal_id)}
    
    # Build hierarchical tree
    def build_tree_node(goal_id: str, level: int = 0) -> Dict:
        """Build tree node recursively"""
        if goal_id not in cre_related_goals:
            return None
            
        goal_data = goal_id_to_data.get(goal_id, {})
        children = goal_id_to_children.get(goal_id, [])
        
        # Filter and build children
        child_nodes = []
        for child_id in children:
            if child_id in cre_related_goals:
                child_node = build_tree_node(child_id, level + 1)
                if child_node:
                    child_nodes.append(child_node)
        
        return {
            'id': goal_id,
            'name': goal_data.get('name', ''),
            'owner': goal_data.get('owner', ''),
            'level': level,
            'children': child_nodes
        }
    
    # Build trees from root nodes
    trees = []
    for root_id in root_goals:
        if root_id in cre_related_goals:
            tree = build_tree_node(root_id)
            if tree:
                trees.append(tree)
    
    return trees

def print_tree(trees: List[Dict], indent: str = ""):
    """Print tree hierarchically"""
    for tree in trees:
        owner_text = f" ({tree['owner']})" if tree['owner'] else ""
        print(f"{indent}📋 {tree['name']}{owner_text}")
        
        if tree['children']:
            # Sort children by name
            sorted_children = sorted(tree['children'], key=lambda x: x['name'])
            for i, child in enumerate(sorted_children):
                is_last = i == len(sorted_children) - 1
                child_indent = indent + ("    " if is_last else "│   ")
                connector = "└── " if is_last else "├── "
                
                owner_text = f" ({child['owner']})" if child['owner'] else ""
                print(f"{indent}{connector}🎯 {child['name']}{owner_text}")
                
                if child['children']:
                    next_indent = indent + ("    " if is_last else "│   ")
                    print_tree([child], next_indent)

def main():
    print("Generating goals tree for CRE teams (using external tables)...\n")
    
    client = bigquery.Client(project=config["project"]) if config["project"] else bigquery.Client()
    
    # Get CRE members
    cre_members = get_cre_team_members(client)
    print(f"CRE team members found: {len(cre_members)}")
    
    # Get OKRs data
    okrs_df = get_okrs_data(client)
    print(f"Total OKRs in latest snapshot: {len(okrs_df)}")
    
    # Build hierarchy
    trees = build_goal_hierarchy(okrs_df, cre_members)
    
    print(f"\nGoals trees found: {len(trees)}\n")
    print("=" * 80)
    print("GOALS TREE - CRE TEAMS")
    print("=" * 80)
    
    if trees:
        print_tree(trees)
    else:
        print("No goals related to CRE teams were found.")
    
    print("\n" + "=" * 80)
    
    # Additional statistics
    total_goals = sum(count_goals_in_tree(tree) for tree in trees)
    print(f"\nTotal goals in tree: {total_goals}")

def count_goals_in_tree(tree: Dict) -> int:
    """Count total number of goals in a tree"""
    count = 1  # Current node
    for child in tree.get('children', []):
        count += count_goals_in_tree(child)
    return count

if __name__ == "__main__":
    main() 