"""
This script queries BigQuery for OKR adoption data and prints:
- OKR penetration and category distribution by team (with totals row)
- Sanity check for OKRs with category breakdown by person
- List of malformed OKRs for team members
- List of unclassified OKRs for team members

Usage:
    python okrs_sanity_check_bq_data.py

Dependencies are managed in pyproject.toml. Install with: uv sync
Make sure your Google Cloud credentials are set (e.g., GOOGLE_APPLICATION_CREDENTIALS env variable).
Set DEBUG_MODE = True to show debug information about goal mapping and classification.
"""
import sys
import os
from pathlib import Path

# Add helpers directory to path for config loader
helpers_dir = Path(__file__).parent.parent / "helpers"
sys.path.insert(0, str(helpers_dir))

from config_loader import get_bigquery_config, get_cre_teams, get_exclude_teams
import pandas as pd
from google.cloud import bigquery
from tabulate import tabulate

# Load configuration
config = get_bigquery_config()

# Teams to exclude from the report (from configuration)
TO_EXCLUDE = get_exclude_teams()

# Debug mode - set to True to show debug information
DEBUG_MODE = False



# Query to get OKR penetration by team and person (with created_at)
PENETRATION_QUERY = f'''
SELECT
  t.team,
  t.name AS person,
  t.role,
  o.created_at,
  COUNT(o.`Goal Key`) AS num_okrs
FROM
  `{config["dataset"]}.{config["teams_table"]}` t
LEFT JOIN
  `{config["dataset"]}.{config["table"]}` o
ON
  LOWER(TRIM(t.name)) = LOWER(TRIM(o.Owner))
GROUP BY
  t.team, t.name, t.role, o.created_at
ORDER BY
  t.team, num_okrs DESC, t.name
'''

def main():
    client = bigquery.Client(project=config["project"]) if config["project"] else bigquery.Client()

    # --- CATEGORY ANALYSIS DEFINITIONS ---
    # Define parent categories
    CORPORATE_GOALS = [
        '🎯 🏢 Enterprise gradeness',
        '🎯 🏢 Exit / IPO Readiness', 
        '🎯 🏢 Revenue Diversity'
    ]
    CSP_RELATED = ['🎯 Better relationships with CSP']
    CRE_GROWTH = ['🎯 Raise the bar']
    
    # Load all OKRs from the latest snapshot for category analysis
    okrs_query = f'SELECT * FROM `{config["dataset"]}.{config["table"]}`'
    okrs_df = client.query(okrs_query).to_dataframe()
    if 'created_at' in okrs_df.columns:
        okrs_df['created_at'] = pd.to_datetime(okrs_df['created_at'], errors='coerce', format='%Y%m%d%H%M')
        latest_ts = okrs_df['created_at'].max()
        okrs_df = okrs_df[okrs_df['created_at'] == latest_ts]
    
    # Create goal maps for efficient search
    goal_id_to_parent = {}
    goal_id_to_name = {}
    goal_name_to_id = {}
    
    for _, row in okrs_df.iterrows():
        goal_id = row.get('Goal Key', '')
        goal_name = row.get('Name', '')
        parent_goal_id = row.get('Parent Goal', '')
        
        if goal_id:
            goal_id_to_parent[goal_id] = parent_goal_id
            goal_id_to_name[goal_id] = goal_name
            if goal_name:
                goal_name_to_id[goal_name] = goal_id
    
    def find_root_parent_by_id(goal_id, visited=None):
        """Recursive function to find the root parent goal by ID"""
        if visited is None:
            visited = set()
        
        if not goal_id or goal_id in visited:
            return goal_id
        
        visited.add(goal_id)
        parent_id = goal_id_to_parent.get(goal_id, '')
        
        if not parent_id or parent_id == goal_id:
            return goal_id
        
        return find_root_parent_by_id(parent_id, visited)
    
    def classify_okr_by_name(goal_name):
        """Classify an OKR according to its root parent goal"""
        goal_id = goal_name_to_id.get(goal_name, '')
        if not goal_id:
            return 'Other'
        
        root_parent_id = find_root_parent_by_id(goal_id)
        if not root_parent_id:
            return 'Other'
        
        root_parent_name = goal_id_to_name.get(root_parent_id, '')
        
        if root_parent_name in CORPORATE_GOALS:
            return 'Corporate Goals'
        elif root_parent_name in CSP_RELATED:
            return 'CSP Related'  
        elif root_parent_name in CRE_GROWTH:
            return 'CRE Growth'
        else:
            return 'Other'



    # Generate penetration_df for use in sanity check (without showing table)
    penetration_df = client.query(PENETRATION_QUERY).to_dataframe()
    if not penetration_df.empty and 'created_at' in penetration_df.columns:
        # Convert and filter to latest timestamp
        penetration_df['created_at'] = pd.to_datetime(penetration_df['created_at'], errors='coerce', format='%Y%m%d%H%M')
        latest_ts = penetration_df['created_at'].max()
        penetration_df = penetration_df[penetration_df['created_at'] == latest_ts]
        penetration_df = penetration_df.drop(columns=['created_at'])

    # Calculate OKR penetration percentage by team WITH CATEGORIES
    print("\nOKR Penetration and Categories by Team (latest snapshot)\n")
    # Get teams table for total people per team
    teams_query = f'SELECT team, name AS person FROM `{config["dataset"]}.{config["teams_table"]}`'
    teams_df = client.query(teams_query).to_dataframe()
    
    # Filter OKRs only from team members and classify
    team_people = set(teams_df['person'].str.strip())
    team_okrs = okrs_df[okrs_df['Owner'].str.strip().isin(team_people)].copy()
    if not team_okrs.empty:
        team_okrs['category'] = team_okrs['Name'].apply(classify_okr_by_name)
    
    # Calculate metrics by team
    penetration_with_categories = []
    
    # Define custom order for teams (using CRE teams from config)
    cre_teams_list = get_cre_teams()
    preferred_order = [team for team in cre_teams_list if team != 'EMEA Leadership']  # Exclude leadership for team order
    all_teams = teams_df['team'].unique()
    
    # Create ordered list: first preferred teams, then the rest alphabetically
    ordered_teams = []
    for team in preferred_order:
        if team in all_teams:
            ordered_teams.append(team)
    
    # Add remaining teams in alphabetical order
    remaining_teams = sorted([team for team in all_teams if team not in preferred_order])
    ordered_teams.extend(remaining_teams)
    
    for team in ordered_teams:
        team_members = teams_df[teams_df['team'] == team]['person'].unique()
        total_people = len(team_members)
        
        # OKRs from this team
        team_okrs_filtered = team_okrs[team_okrs['Owner'].str.strip().isin(team_members)]
        
        # Count people with OKRs
        people_with_okrs = len(team_okrs_filtered['Owner'].unique()) if not team_okrs_filtered.empty else 0
        
        # Count OKRs by category
        category_counts = team_okrs_filtered['category'].value_counts() if not team_okrs_filtered.empty else pd.Series()
        total_team_okrs = len(team_okrs_filtered) if not team_okrs_filtered.empty else 0
        
        penetration_with_categories.append({
            'team': team,
            'total_people': total_people,
            'with_okrs': people_with_okrs,
            'penetration_%': (people_with_okrs / total_people * 100) if total_people > 0 else 0,
            'corporate_goals': (category_counts.get('Corporate Goals', 0) / total_team_okrs * 100) if total_team_okrs > 0 else 0,
            'csp_related': (category_counts.get('CSP Related', 0) / total_team_okrs * 100) if total_team_okrs > 0 else 0,
            'cre_growth': (category_counts.get('CRE Growth', 0) / total_team_okrs * 100) if total_team_okrs > 0 else 0,
            'other': (category_counts.get('Other', 0) / total_team_okrs * 100) if total_team_okrs > 0 else 0
        })
    
    penetration_categories_df = pd.DataFrame(penetration_with_categories)
    # Round the percentages
    penetration_categories_df['penetration_%'] = penetration_categories_df['penetration_%'].round(2)
    penetration_categories_df['corporate_goals'] = penetration_categories_df['corporate_goals'].round(2)
    penetration_categories_df['csp_related'] = penetration_categories_df['csp_related'].round(2)
    penetration_categories_df['cre_growth'] = penetration_categories_df['cre_growth'].round(2)
    penetration_categories_df['other'] = penetration_categories_df['other'].round(2)
    
    # Calculate global totals
    total_people = penetration_categories_df['total_people'].sum()
    total_with_okrs = penetration_categories_df['with_okrs'].sum()
    total_penetration = (total_with_okrs / total_people * 100) if total_people > 0 else 0
    
    # Calculate global category percentages using all team member OKRs
    if not team_okrs.empty:
        global_category_counts = team_okrs['category'].value_counts()
        total_team_okrs = len(team_okrs)
        
        global_corporate = (global_category_counts.get('Corporate Goals', 0) / total_team_okrs * 100) if total_team_okrs > 0 else 0
        global_csp = (global_category_counts.get('CSP Related', 0) / total_team_okrs * 100) if total_team_okrs > 0 else 0
        global_cre = (global_category_counts.get('CRE Growth', 0) / total_team_okrs * 100) if total_team_okrs > 0 else 0
        global_other = (global_category_counts.get('Other', 0) / total_team_okrs * 100) if total_team_okrs > 0 else 0
    else:
        global_corporate = global_csp = global_cre = global_other = 0
    
    # Add totals row
    total_row = {
        'team': 'TOTAL',
        'total_people': total_people,
        'with_okrs': total_with_okrs,
        'penetration_%': round(total_penetration, 2),
        'corporate_goals': round(global_corporate, 2),
        'csp_related': round(global_csp, 2),
        'cre_growth': round(global_cre, 2),
        'other': round(global_other, 2)
    }
    
    # Add the totals row to the DataFrame
    penetration_categories_df = pd.concat([penetration_categories_df, pd.DataFrame([total_row])], ignore_index=True)
    
    # Reorder columns as requested and rename for clarity
    column_order = ['team', 'total_people', 'with_okrs', 'penetration_%', 'corporate_goals', 'csp_related', 'cre_growth', 'other']
    penetration_categories_df = penetration_categories_df[column_order]
    
    # Rename columns to include % in headers
    penetration_categories_df = penetration_categories_df.rename(columns={
        'corporate_goals': 'corporate_goals_%',
        'csp_related': 'csp_related_%',
        'cre_growth': 'cre_growth_%',
        'other': 'other_%'
    })
    
    print(tabulate(penetration_categories_df, headers="keys", tablefmt="fancy_grid", showindex=False))

    # --- SANITY CHECK FOR OKRs ---
    print("\nSanity check for OKRs (latest snapshot)\n")
    # Sanity check: all required fields are not empty
    def okr_sanity(row):
        missing = []
        if not row.get('Target Date') or str(row.get('Target Date')).strip() == '':
            missing.append('Target Date')
        if not row.get('Teams') or str(row.get('Teams')).strip() == '':
            missing.append('Teams')
        if not row.get('Parent Goal') or str(row.get('Parent Goal')).strip() == '':
            missing.append('Parent Goal')
        if not row.get('Owner') or str(row.get('Owner')).strip() == '':
            missing.append('Owner')
        return missing
    okrs_df['sanity_missing'] = okrs_df.apply(okr_sanity, axis=1)
    okrs_df['is_sane'] = okrs_df['sanity_missing'].apply(lambda x: len(x) == 0)

    # --- Penetration with sanity check and categories by person ---
    # Group by owner and count sane and non-sane OKRs
    okrs_sane = okrs_df[okrs_df['is_sane']].groupby('Owner').size()
    okrs_not_sane = okrs_df[~okrs_df['is_sane']].groupby('Owner').size()
    
    # Count OKRs by category per person
    if not team_okrs.empty:
        person_categories = team_okrs.groupby('Owner')['category'].value_counts().unstack(fill_value=0)
        
        # Add columns to the penetration table
        penetration_df['okrs_not_sane'] = penetration_df['person'].map(okrs_not_sane).fillna(0).astype(int)
        
        # Calculate category percentages per person
        for person in penetration_df['person']:
            total_person_okrs = penetration_df[penetration_df['person'] == person]['num_okrs'].iloc[0]
            if total_person_okrs > 0:
                penetration_df.loc[penetration_df['person'] == person, 'corporate_goals'] = (person_categories.get('Corporate Goals', pd.Series()).get(person, 0) / total_person_okrs * 100)
                penetration_df.loc[penetration_df['person'] == person, 'csp_related'] = (person_categories.get('CSP Related', pd.Series()).get(person, 0) / total_person_okrs * 100)
                penetration_df.loc[penetration_df['person'] == person, 'cre_growth'] = (person_categories.get('CRE Growth', pd.Series()).get(person, 0) / total_person_okrs * 100)
                penetration_df.loc[penetration_df['person'] == person, 'other_category'] = (person_categories.get('Other', pd.Series()).get(person, 0) / total_person_okrs * 100)
            else:
                penetration_df.loc[penetration_df['person'] == person, 'corporate_goals'] = 0
                penetration_df.loc[penetration_df['person'] == person, 'csp_related'] = 0
                penetration_df.loc[penetration_df['person'] == person, 'cre_growth'] = 0
                penetration_df.loc[penetration_df['person'] == person, 'other_category'] = 0
        
        # Round the percentages
        penetration_df['corporate_goals'] = penetration_df['corporate_goals'].round(2)
        penetration_df['csp_related'] = penetration_df['csp_related'].round(2)
        penetration_df['cre_growth'] = penetration_df['cre_growth'].round(2)
        penetration_df['other_category'] = penetration_df['other_category'].round(2)
    
    # Rename percentage columns for greater clarity
    penetration_df = penetration_df.rename(columns={
        'corporate_goals': 'corporate_goals_%',
        'csp_related': 'csp_related_%',
        'cre_growth': 'cre_growth_%',
        'other_category': 'other_category_%'
    })
    
    # Show the table without the 'role' columns
    cols_to_show = [col for col in penetration_df.columns if col not in ['role']]
    print(tabulate(penetration_df[cols_to_show], headers="keys", tablefmt="fancy_grid", showindex=False))

    # --- Detailed listing of invalid OKRs by owner (team members only, visual table format) ---
    print("\nMalformed OKRs for team members (latest snapshot):\n")
    # Filter invalid OKRs only for team members
    team_people_mask = okrs_df['Owner'].str.strip().isin(team_people)
    not_sane_in_teams = okrs_df[~okrs_df['is_sane'] & team_people_mask]
    def checkmark(val):
        return '✅' if val else '❌'
    if not not_sane_in_teams.empty:
        table = []
        for _, row in not_sane_in_teams.iterrows():
            table.append([
                row.get('Owner', ''),
                row.get('Name', ''),
                checkmark('Target Date' not in row['sanity_missing']),
                checkmark('Teams' not in row['sanity_missing']),
                checkmark('Parent Goal' not in row['sanity_missing']),
                checkmark('Owner' not in row['sanity_missing']),
            ])
        print(tabulate(
            table,
            headers=["Owner", "OKR Name", "Target Date", "Teams", "Parent Goal", "Owner (OKR)"],
            tablefmt="fancy_grid",
            showindex=False
        ))
    else:
        print("All OKRs for team members pass the sanity check!")

    # --- UNCLASSIFIED OKRs DETAILS ---
    # Show details of "Other" OKRs only if there are some and if DEBUG_MODE is enabled
    if DEBUG_MODE and not team_okrs.empty:
        # DEBUG: Show debug information if enabled
        print("DEBUG: Goal mapping examples (by ID):")
        debug_count = 0
        for goal_id, parent_id in goal_id_to_parent.items():
            if parent_id and debug_count < 10:
                goal_name = goal_id_to_name.get(goal_id, 'Unknown')
                parent_name = goal_id_to_name.get(parent_id, 'Unknown')
                print(f"  '{goal_name}' ({goal_id}) -> '{parent_name}' ({parent_id})")
                debug_count += 1
        print()
        
        print("DEBUG: Classification examples:")
        debug_classifications = []
        for _, row in team_okrs.head(10).iterrows():
            goal_name = row.get('Name', '')
            goal_id = goal_name_to_id.get(goal_name, '')
            root_parent_id = find_root_parent_by_id(goal_id) if goal_id else ''
            root_parent_name = goal_id_to_name.get(root_parent_id, '') if root_parent_id else ''
            category = classify_okr_by_name(goal_name)
            
            debug_classifications.append([
                goal_name[:40] + "..." if len(goal_name) > 40 else goal_name,
                root_parent_name[:40] + "..." if len(root_parent_name) > 40 else root_parent_name,
                category
            ])
        
        print(tabulate(
            debug_classifications,
            headers=["OKR Name", "Root Parent Name", "Category"],
            tablefmt="fancy_grid",
            showindex=False
        ))
        print()
    
    # Show details of unclassified OKRs
    if not team_okrs.empty:
        other_okrs = team_okrs[team_okrs['category'] == 'Other']
        if not other_okrs.empty:
            print(f"\nUnclassified OKRs for team members ({len(other_okrs)} total):\n")
            other_table = []
            for _, row in other_okrs.iterrows():
                goal_name = row.get('Name', '')
                goal_id = goal_name_to_id.get(goal_name, '')
                root_parent_id = find_root_parent_by_id(goal_id) if goal_id else ''
                root_parent_name = goal_id_to_name.get(root_parent_id, '') if root_parent_id else 'No parent'
                
                other_table.append([
                    row.get('Owner', ''),
                    goal_name,
                    root_parent_name
                ])
            
            print(tabulate(
                other_table,
                headers=["Owner", "OKR Name", "Root Parent Goal"],
                tablefmt="fancy_grid",
                showindex=False
            ))

    # --- PEOPLE WITHOUT OKRs BY TEAM ---
    print("\nPeople who have not entered objectives by team (latest snapshot):\n")
    
    # Get people who have OKRs
    people_with_okrs = set(team_okrs['Owner'].str.strip()) if not team_okrs.empty else set()
    
    # Create table grouped by team
    missing_okrs_grouped = []
    has_missing = False
    
    for team in ordered_teams:
        team_members = set(teams_df[teams_df['team'] == team]['person'].str.strip())
        people_without_okrs = team_members - people_with_okrs
        
        if people_without_okrs:
            has_missing = True
            # Sort people without OKRs alphabetically
            sorted_missing = sorted(list(people_without_okrs))
            
            # Add team header row
            missing_okrs_grouped.append([f"📋 {team}", ""])
            
            # Add each person from the team
            for person in sorted_missing:
                missing_okrs_grouped.append([f"   • {person}", ""])
            
            # Add blank line to separate teams
            missing_okrs_grouped.append(["", ""])
    
    if has_missing:
        # Remove the last blank line
        if missing_okrs_grouped and missing_okrs_grouped[-1] == ["", ""]:
            missing_okrs_grouped.pop()
        
        print(tabulate(
            missing_okrs_grouped,
            headers=["Team / Person", ""],
            tablefmt="fancy_grid",
            showindex=False
        ))
    else:
        print("All team members have OKRs!")

if __name__ == "__main__":
    main() 