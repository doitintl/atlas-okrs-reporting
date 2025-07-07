"""
Improved coverage analysis that uses the real goal hierarchy in BigQuery
instead of direct keyword matching.

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

from config_loader import get_bigquery_config, get_cre_teams, get_us_people
import pandas as pd
from google.cloud import bigquery
from typing import Dict, List, Set
from difflib import SequenceMatcher

# Load configuration
config = get_bigquery_config()

# CRE Teams (Customer Reliability Engineers) - from configuration
CRE_TEAMS = get_cre_teams()

# US-based people to exclude from EMEA analysis - from configuration
US_PEOPLE = get_us_people()

# Corporate objectives as transcribed from the slides
CORPORATE_OBJECTIVES_TRANSCRIBED = {
    "Enterprise-grade": {
        "description": "Demonstrate DCI Compass Success with Enterprise customers",
        "key_results": [
            "100% of the CS Org has completed a training curriculum on DCI by 1/31",
            "Document 10 examples of how we help our customers using Compass by EoQ1",
            "Document 3 DCI Compass objectives each for 50 Enterprise-grade (DCI+Heritage) customers by EoQ2",
            "5 DCI Compass engagement model-based public case study by EoH1",
            "Median engagement score of DCI Enterprise customers is 85% by EoQ1"
        ]
    },
    "Integration, Innovation, and Efficiency": {
        "description": "Deliver seamless integration between product and human in the DCI platform",
        "key_results": [
            "Identify and design 10 new convergence point features between product & humans",
            "Drive adoption of Insights by DCI Compass customers from 15% to 75% by EOY",
            "Run 2 TechChallenges focused on new convergence points between product & humans",
            "Develop guidelines for how we use Custom Insights by end of April 25",
            "100% of PerfectScale Tickets are triaged by Client Services with CS Tools",
            "Develop 20 reusable CloudFlow blueprints integrated into production CloudFlow Library",
            "Create process for relevant vendor updates to customers"
        ]
    },
    "Exit/IPO Ready": {
        "description": "Improve productivity by 20%",
        "key_results": [
            "Implement AI into three top workflows by June 30th to reduce execution time, increase capacity, or improve quality",
            "Develop a new baseline model to measure team efficiency and IC efficacy by role by end of 25'Q2"
        ]
    }
}

def get_all_goals_hierarchy(client):
    """Get all goal hierarchy from BigQuery external table views"""
    # Use latest view instead of raw table - automatically gets most recent data
    okrs_query = f'SELECT * FROM `{config["dataset"]}.okrs_latest_view`'
    okrs_df = client.query(okrs_query).to_dataframe()
    return okrs_df

def get_cre_members(client):
    """Get CRE team members"""
    teams_query = f'''
    SELECT team, name AS person 
    FROM `{config["dataset"]}.{config["teams_table"]}`
    WHERE team IN ({",".join([f"'{team}'" for team in CRE_TEAMS])})
    '''
    teams_df = client.query(teams_query).to_dataframe()
    return set(teams_df['person'].str.strip())

def similarity(a, b):
    """Calculate similarity between two strings"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def find_matching_corporate_goals(okrs_df):
    """Find goals in BigQuery that correspond to corporate objectives"""
    
    print("🔍 STEP 1: Mapping corporate objectives with goals in BigQuery\n")
    
    # Get all unique goals (no duplicates)
    all_goals = okrs_df['Name'].dropna().unique()
    
    matches = {}
    
    for corp_name, corp_data in CORPORATE_OBJECTIVES_TRANSCRIBED.items():
        print(f"📋 Searching matches for: {corp_name}")
        print(f"   Description: {corp_data['description']}")
        
        # Search for similar goals
        best_matches = []
        
        # Key terms to search for
        search_terms = []
        if "enterprise" in corp_name.lower():
            search_terms = ["enterprise", "compass", "dci"]
        elif "integration" in corp_name.lower():
            search_terms = ["integration", "seamless", "product", "human", "dci platform"]
        elif "exit" in corp_name.lower() or "ipo" in corp_name.lower():
            search_terms = ["productivity", "improve", "20%", "efficiency"]
        
        for goal in all_goals:
            goal_str = str(goal).lower()
            
            # Calculate score based on key terms and similarity
            term_score = sum(1 for term in search_terms if term in goal_str)
            similarity_score = similarity(corp_data['description'], goal_str)
            
            combined_score = (term_score * 0.7) + (similarity_score * 0.3)
            
            if combined_score > 0.3:  # Threshold to consider match
                best_matches.append({
                    'goal_name': goal,
                    'term_score': term_score,
                    'similarity_score': similarity_score,
                    'combined_score': combined_score
                })
        
        # Sort by score and show top matches
        best_matches.sort(key=lambda x: x['combined_score'], reverse=True)
        
        print(f"   🎯 Top matches found:")
        for i, match in enumerate(best_matches[:5], 1):
            print(f"      {i}. {match['goal_name']}")
            print(f"         Score: {match['combined_score']:.3f} (terms: {match['term_score']}, similarity: {match['similarity_score']:.3f})")
        
        matches[corp_name] = best_matches[:3]  # Save top 3
        print()
    
    return matches

def analyze_goal_hierarchy_coverage(okrs_df, corporate_matches, cre_members):
    """Analyze coverage using real goal hierarchy"""
    
    print("🔍 STEP 2: Analyzing coverage using real hierarchy\n")
    
    coverage_results = {}
    
    # Build hierarchy map
    goal_to_children = {}
    goal_to_parent = {}
    
    for _, row in okrs_df.iterrows():
        goal_id = row.get('Goal Key', '')
        parent_id = row.get('Parent Goal', '')
        
        if goal_id:
            goal_to_parent[goal_id] = parent_id
            
            if parent_id:
                if parent_id not in goal_to_children:
                    goal_to_children[parent_id] = []
                goal_to_children[parent_id].append(goal_id)

    def get_all_descendant_goals(goal_name, okrs_df):
        """Get all descendant goals of a goal"""
        # Find Goal Key for this goal name
        matching_rows = okrs_df[okrs_df['Name'] == goal_name]
        if matching_rows.empty:
            return set()
        
        root_goal_ids = matching_rows['Goal Key'].tolist()
        
        all_descendants = set()
        
        def collect_descendants(goal_id):
            all_descendants.add(goal_id)
            children = goal_to_children.get(goal_id, [])
            for child_id in children:
                collect_descendants(child_id)
        
        for root_id in root_goal_ids:
            collect_descendants(root_id)
        
        return all_descendants
    
    # Analyze coverage for each corporate objective
    for corp_name, matches in corporate_matches.items():
        print(f"📊 Analyzing coverage for: {corp_name}")
        
        if not matches:
            print("   ❌ No matches found - 0% coverage")
            coverage_results[corp_name] = {
                'coverage_percentage': 0,
                'total_okrs': 0,
                'cre_okrs': 0,
                'contributing_okrs': []
            }
            continue
        
        # Use best match as main goal
        main_goal = matches[0]['goal_name']
        print(f"   🎯 Main goal identified: {main_goal}")
        
        # Get all descendants
        all_descendant_ids = get_all_descendant_goals(main_goal, okrs_df)
        print(f"   📈 Descendant goals found: {len(all_descendant_ids)}")
        
        # Filter OKRs that belong to this hierarchy
        hierarchy_okrs = okrs_df[okrs_df['Goal Key'].isin(all_descendant_ids)]
        
        # Filter only OKRs from CRE members
        cre_hierarchy_okrs = hierarchy_okrs[hierarchy_okrs['Owner'].str.strip().isin(cre_members)]
        
        total_okrs_in_hierarchy = len(hierarchy_okrs)
        cre_okrs_in_hierarchy = len(cre_hierarchy_okrs)
        
        coverage_percentage = (cre_okrs_in_hierarchy / total_okrs_in_hierarchy * 100) if total_okrs_in_hierarchy > 0 else 0
        
        print(f"   📊 Total OKRs in hierarchy: {total_okrs_in_hierarchy}")
        print(f"   👥 CRE OKRs in hierarchy: {cre_okrs_in_hierarchy}")
        print(f"   📈 CRE Coverage: {coverage_percentage:.1f}%")
        
        # Get examples of contributing OKRs
        contributing_okrs = []
        for _, okr in cre_hierarchy_okrs.head(10).iterrows():
            contributing_okrs.append({
                'name': okr.get('Name', ''),
                'owner': okr.get('Owner', ''),
                'goal_key': okr.get('Goal Key', '')
            })
        
        coverage_results[corp_name] = {
            'main_goal': main_goal,
            'coverage_percentage': coverage_percentage,
            'total_okrs': total_okrs_in_hierarchy,
            'cre_okrs': cre_okrs_in_hierarchy,
            'contributing_okrs': contributing_okrs
        }
        
        print()
    
    return coverage_results

def analyze_unimpacted_goals(okrs_df, coverage_results, cre_members):
    """Identify specific goals NOT being impacted by CRE teams"""
    
    print("\n" + "="*80)
    print("🚨 UNIMPACTED GOALS ANALYSIS - ACTION PLAN NEEDED")
    print("="*80)
    
    unimpacted_analysis = {}
    
    for corp_name, results in coverage_results.items():
        print(f"\n🎯 {corp_name}")
        
        if results['coverage_percentage'] == 0:
            print("   ❌ No corresponding goal found in BigQuery")
            unimpacted_analysis[corp_name] = {
                'status': 'no_match',
                'unimpacted_goals': [],
                'recommendations': ['Find and map this corporate objective to existing OKRs', 
                                  'Create new OKRs aligned with this objective']
            }
            continue
        
        main_goal = results['main_goal']
        
        # Get all goals in this hierarchy
        matching_rows = okrs_df[okrs_df['Name'] == main_goal]
        if matching_rows.empty:
            continue
            
        root_goal_ids = matching_rows['Goal Key'].tolist()
        
        # Build hierarchy map for traversal
        goal_to_children = {}
        for _, row in okrs_df.iterrows():
            goal_id = row.get('Goal Key', '')
            parent_id = row.get('Parent Goal', '')
            
            if parent_id:
                if parent_id not in goal_to_children:
                    goal_to_children[parent_id] = []
                goal_to_children[parent_id].append(goal_id)
        
        def get_all_descendant_goals_with_details(root_ids):
            """Get all descendant goals with their details"""
            all_descendants = set()
            
            def collect_descendants(goal_id):
                all_descendants.add(goal_id)
                children = goal_to_children.get(goal_id, [])
                for child_id in children:
                    collect_descendants(child_id)
            
            for root_id in root_ids:
                collect_descendants(root_id)
            
            return all_descendants
        
        all_descendant_ids = get_all_descendant_goals_with_details(root_goal_ids)
        hierarchy_okrs = okrs_df[okrs_df['Goal Key'].isin(all_descendant_ids)]
        
        # Identify goals WITHOUT CRE team members but FROM EMEA region
        # We only care about EMEA goals that don't have CRE coverage
        unimpacted_goals = []
        emea_relevant_goals = []
        
        for _, goal in hierarchy_okrs.iterrows():
            goal_owner = goal.get('Owner', '').strip()
            
            # Skip empty owners
            if goal_owner == '':
                continue
                
            # Only consider EMEA-relevant goals (those that CRE teams SHOULD potentially own)
            # This excludes US-based people using configured list
            emea_keywords = ['emea', 'europe', 'uk', 'germany', 'france', 'spain', 'italy', 'poland']
            
            is_us_person = any(us_name in goal_owner.lower() for us_name in US_PEOPLE)
            
            if is_us_person:
                # Skip US-based people - not relevant for EMEA CRE analysis
                continue
                
            emea_relevant_goals.append(goal)
            
            if goal_owner not in cre_members:
                unimpacted_goals.append({
                    'name': goal.get('Name', ''),
                    'owner': goal_owner,
                    'goal_key': goal.get('Goal Key', ''),
                    'parent_goal': goal.get('Parent Goal', ''),
                    'description': goal.get('Description', '')[:100] + '...' if goal.get('Description', '') else 'No description'
                })
        
        print(f"   📋 Main goal: {main_goal}")
        print(f"   📊 Total goals in hierarchy: {len(hierarchy_okrs)}")
        print(f"   🌍 EMEA-relevant goals: {len(emea_relevant_goals)}")
        print(f"   👥 Goals with CRE members: {results['cre_okrs']}")
        print(f"   🚨 EMEA goals WITHOUT CRE impact: {len(unimpacted_goals)}")
        
        if unimpacted_goals:
            print(f"\n   🔍 UNIMPACTED GOALS (TOP 10):")
            for i, goal in enumerate(unimpacted_goals[:10], 1):
                print(f"      {i}. {goal['name'][:70]}...")
                print(f"         Owner: {goal['owner']}")
                print(f"         Description: {goal['description']}")
                print()
        
        # Generate recommendations based on EMEA-specific coverage
        recommendations = []
        coverage_pct = results['coverage_percentage']
        emea_coverage_pct = (results['cre_okrs'] / len(emea_relevant_goals) * 100) if len(emea_relevant_goals) > 0 else 0
        
        print(f"   📈 EMEA-specific CRE Coverage: {emea_coverage_pct:.1f}% ({results['cre_okrs']}/{len(emea_relevant_goals)} EMEA-relevant goals)")
        
        if emea_coverage_pct < 25:
            recommendations.extend([
                "🚨 CRITICAL: Very low EMEA CRE coverage",
                "Assign CRE team members to key EMEA-relevant goals",
                "Review if CRE teams should be contributing more to this objective"
            ])
        elif emea_coverage_pct < 50:
            recommendations.extend([
                "⚠️ MODERATE: Some gaps in EMEA coverage",
                "Identify high-impact EMEA goals for CRE involvement",
                "Consider expanding CRE scope in this area"
            ])
        else:
            recommendations.extend([
                "✅ GOOD: Strong EMEA CRE coverage",
                "Monitor remaining EMEA goals for potential CRE value-add",
                "Maintain current level of involvement"
            ])
        
        unimpacted_analysis[corp_name] = {
            'status': 'analyzed',
            'coverage_percentage': coverage_pct,
            'emea_coverage_percentage': emea_coverage_pct,
            'total_goals': len(hierarchy_okrs),
            'emea_relevant_goals': len(emea_relevant_goals),
            'unimpacted_count': len(unimpacted_goals),
            'unimpacted_goals': unimpacted_goals,
            'recommendations': recommendations
        }
        
        print(f"   💡 RECOMMENDATIONS:")
        for rec in recommendations:
            print(f"      • {rec}")
        
        print("-" * 80)
    
    return unimpacted_analysis

def print_action_plan_summary(unimpacted_analysis):
    """Print actionable summary for leadership"""
    
    print("\n" + "="*80)
    print("📋 ACTION PLAN SUMMARY")
    print("="*80)
    
    total_unimpacted = 0
    critical_areas = []
    
    for corp_name, analysis in unimpacted_analysis.items():
        if analysis['status'] == 'analyzed':
            unimpacted_count = analysis['unimpacted_count']
            total_unimpacted += unimpacted_count
            
            # Use EMEA-specific coverage for critical assessment
            emea_coverage = analysis.get('emea_coverage_percentage', analysis['coverage_percentage'])
            if emea_coverage < 25:
                critical_areas.append({
                    'name': corp_name,
                    'coverage': emea_coverage,
                    'unimpacted': unimpacted_count
                })
    
    print(f"\n📊 SUMMARY METRICS:")
    print(f"   • Total unimpacted goals across all objectives: {total_unimpacted}")
    print(f"   • Critical coverage areas (< 25%): {len(critical_areas)}")
    
    if critical_areas:
        print(f"\n🚨 PRIORITY ACTIONS NEEDED:")
        for area in critical_areas:
            print(f"   • {area['name']}: {area['coverage']:.1f}% coverage, {area['unimpacted']} unimpacted goals")
    
    print(f"\n📋 RECOMMENDED NEXT STEPS:")
    print(f"   1. Review critical areas and assign CRE team members")
    print(f"   2. Assess if unimpacted goals require CRE expertise")
    print(f"   3. Create new OKRs for areas missing CRE representation")
    print(f"   4. Set quarterly reviews to monitor coverage improvement")

def print_final_coverage_report(coverage_results):
    """Print final coverage report"""
    
    print("\n" + "="*80)
    print("FINAL COVERAGE REPORT (USING REAL HIERARCHY)")
    print("="*80)
    
    total_coverage_scores = []
    
    for corp_name, results in coverage_results.items():
        print(f"\n🎯 {corp_name}")
        if results['coverage_percentage'] > 0:
            print(f"   📋 Main goal: {results['main_goal']}")
            print(f"   📊 Total OKRs in hierarchy: {results['total_okrs']}")
            print(f"   👥 CRE team OKRs: {results['cre_okrs']}")
            print(f"   📈 CRE Coverage: {results['coverage_percentage']:.1f}%")
            
            if results['contributing_okrs']:
                print(f"   🔝 Example contributing OKRs:")
                for i, okr in enumerate(results['contributing_okrs'][:5], 1):
                    print(f"      {i}. {okr['name'][:60]}... ({okr['owner']})")
        else:
            print("   ❌ No corresponding goal found in BigQuery")
        
        total_coverage_scores.append(results['coverage_percentage'])
        print("-" * 80)
    
    # Overall summary
    avg_coverage = sum(total_coverage_scores) / len(total_coverage_scores) if total_coverage_scores else 0
    print(f"\n📊 OVERALL SUMMARY:")
    print(f"   🎯 Average coverage: {avg_coverage:.1f}%")
    
    print(f"\n🎯 REVISED CONCLUSION:")
    print("Are we meeting corporate objectives with current OKRs?")
    
    if avg_coverage > 70:
        print("✅ YES - Good alignment using real hierarchy")
    elif avg_coverage > 40:
        print("⚡ PARTIALLY - Moderate coverage")
    else:
        print("❌ LOW COVERAGE - Need more aligned OKRs")

def main():
    print("🔍 IMPROVED COVERAGE ANALYSIS (USING EXTERNAL TABLES)\n")
    
    client = bigquery.Client(project=config["project"]) if config["project"] else bigquery.Client()
    
    # Get data
    okrs_df = get_all_goals_hierarchy(client)
    cre_members = get_cre_members(client)
    
    print(f"📊 Data loaded:")
    print(f"   • Total goals: {len(okrs_df)}")
    print(f"   • CRE members: {len(cre_members)}")
    print(f"   • Corporate objectives to map: {len(CORPORATE_OBJECTIVES_TRANSCRIBED)}\n")
    
    # Step 1: Map corporate objectives with real goals
    corporate_matches = find_matching_corporate_goals(okrs_df)
    
    # Step 2: Analyze coverage using hierarchy
    coverage_results = analyze_goal_hierarchy_coverage(okrs_df, corporate_matches, cre_members)
    
    # Step 3: Analyze unimpacted goals for action planning
    unimpacted_analysis = analyze_unimpacted_goals(okrs_df, coverage_results, cre_members)
    
    # Step 4: Generate action plan summary
    print_action_plan_summary(unimpacted_analysis)
    
    # Step 5: Final coverage report
    print_final_coverage_report(coverage_results)

if __name__ == "__main__":
    main() 