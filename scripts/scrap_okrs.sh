#!/bin/bash

# Script for complete recursive traversal of Goals tree from Atlassian
# Depth-First Search (DFS) algorithm to obtain all goals in the tree

# Load configuration from config.env
if [ -f "config.env" ]; then
    source config.env
    echo "✅ Configuration loaded from config.env"
else
    echo "❌ Error: config.env file not found"
    echo "Please create config.env with required configuration variables"
    exit 1
fi

# Validate required configuration variables
required_vars=("ATLASSIAN_BASE_URL" "ORGANIZATION_ID" "CLOUD_ID" "WORKSPACE_UUID" "DIRECTORY_VIEW_UUID" "CUSTOM_FIELD_UUID" "ATLASSIAN_COOKIES")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Error: Required configuration variable $var is not set in config.env"
        exit 1
    fi
done

# Get current timestamp
TIMESTAMP=$(date +"%Y%m%d%H%M")
OUTPUT_DIR="scraped"
FINAL_CSV="${OUTPUT_DIR}/export-${TIMESTAMP}_processed.csv"
TEMP_DIR="${OUTPUT_DIR}/temp_${TIMESTAMP}"
PROCESSED_GOALS="${TEMP_DIR}/processed_goals.txt"

# Create directories if they don't exist
mkdir -p "$OUTPUT_DIR" "$TEMP_DIR"

echo "🌳 Starting complete recursive traversal of Goals tree..."
echo "📅 Timestamp: $TIMESTAMP"
echo "📁 Output directory: $OUTPUT_DIR"
echo "📊 Final CSV: $FINAL_CSV"
echo "🔍 Algorithm: Recursive Depth-First Search (DFS)"

# Initialize processed goals file (to avoid duplicates)
touch "$PROCESSED_GOALS"

# Function to get details of a specific goal
get_goal_details() {
    local goal_key="$1"
    local goal_file="$2"
    local depth="$3"
    
    # Create indentation based on depth
    local indent=""
    for ((i=0; i<depth; i++)); do
        indent="  $indent"
    done
    
    echo "${indent}📋 [Level $depth] Getting details: $goal_key"
    
    # Print the curl command that will be executed
    echo "${indent}🔧 Executing curl for goal: $goal_key"
    echo "${indent}   URL: ${ATLASSIAN_BASE_URL}/gateway/api/townsquare/s/${CLOUD_ID}/graphql?operationName=GoalViewAsideQuery"
          echo "${indent}   Variables: {\"key\":\"$goal_key\",\"trackViewEvent\":\"DIRECT\",\"isNavRefreshEnabled\":true,\"containerId\":\"ari:cloud:townsquare::site/${CLOUD_ID}\"}"
    
    # Create the correctly escaped JSON payload
    local json_payload=$(cat <<EOF
{
  "query": "query GoalViewAsideQuery(\$key: String!, \$trackViewEvent: TrackViewEvent, \$isNavRefreshEnabled: Boolean!, \$containerId: String!) { workspaceGoalTypes: townsquare { goalTypes(containerId: \$containerId) { edges { node { __typename id } } } } goal: goalByKey(key: \$key, trackViewEvent: \$trackViewEvent) @include(if: \$isNavRefreshEnabled) { owner { aaid id pii { name email accountId } } key name archived targetDate startDate creationDate progress { type percentage } parentGoal { key name } subGoals { edges { node { key name archived } } } tags { edges { node { name } } } teamsV2 { edges { node { name teamId } } } customFields { edges { node { ... on TextSelectCustomField { values { edges { node { value } } } } } } } id } }",
  "variables": {
    "key": "$goal_key",
    "trackViewEvent": "DIRECT",
    "isNavRefreshEnabled": true,
    "containerId": "ari:cloud:townsquare::site/${CLOUD_ID}"
  }
}
EOF
)

    # Make individual request using GoalViewAsideQuery
    curl -s "${ATLASSIAN_BASE_URL}/gateway/api/townsquare/s/${CLOUD_ID}/graphql?operationName=GoalViewAsideQuery" \
      -H 'accept: */*' \
      -H 'accept-language: es-ES,es;q=0.9,en;q=0.8' \
      -H 'atl-client-name: townsquare-frontend' \
      -H 'atl-client-version: daf3c1' \
      -H 'content-type: application/json' \
      -b "$ATLASSIAN_COOKIES" \
      -H "origin: ${ATLASSIAN_BASE_URL}" \
      -H 'priority: u=1, i' \
      -H "referer: ${ATLASSIAN_BASE_URL}/o/${ORGANIZATION_ID}/s/${CLOUD_ID}/goal/${goal_key}" \
      -H 'sec-ch-ua: "Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"' \
      -H 'sec-ch-ua-mobile: ?0' \
      -H 'sec-ch-ua-platform: "macOS"' \
      -H 'sec-fetch-dest: empty' \
      -H 'sec-fetch-mode: cors' \
      -H 'sec-fetch-site: same-origin' \
      -H 'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36' \
      --data-raw "$json_payload" \
      -o "$goal_file"
    
    curl_exit_code=$?
    if [ $curl_exit_code -ne 0 ]; then
        echo "${indent}❌ Curl error (code: $curl_exit_code) for goal: $goal_key"
        return 1
    else
        echo "${indent}✅ Curl successful for goal: $goal_key (file: $goal_file)"
        if [ -f "$goal_file" ]; then
            file_size=$(du -h "$goal_file" | cut -f1)
            echo "${indent}   📄 File generated: $file_size"
        fi
    fi
    
    return 0
}

# Recursive function to process a goal and all its subgoals (DFS)
process_goal_recursive() {
    local goal_key="$1"
    local depth="$2"
    
    # Check if we have already processed this goal (avoid cycles)
    if grep -q "^$goal_key$" "$PROCESSED_GOALS"; then
        echo "  🔄 Goal $goal_key already processed, skipping..."
        return 0
    fi
    
    # Mark as processed
    echo "$goal_key" >> "$PROCESSED_GOALS"
    
    local goal_file="${TEMP_DIR}/${goal_key}.json"
    
    # Get current goal details
    get_goal_details "$goal_key" "$goal_file" "$depth"
    
    # Small pause to not overload the API
    sleep 0.3
    
    # Extract subgoals from response, filtering only non-archived ones
    if [ -f "$goal_file" ] && command -v jq &> /dev/null; then
        # Extract active subgoals (not archived)
        local active_subgoals=$(jq -r '.data.goal.subGoals.edges[]? | select(.node.archived != true) | .node.key // empty' "$goal_file" 2>/dev/null)
        
        if [ -n "$active_subgoals" ]; then
            local indent=""
            for ((i=0; i<depth; i++)); do
                indent="  $indent"
            done
            
            echo "${indent}🌱 Found active subgoals for $goal_key:"
            echo "$active_subgoals" | while read subgoal_key; do
                if [ -n "$subgoal_key" ]; then
                    echo "${indent}  - $subgoal_key"
                fi
            done
            
            # Recursively process each active subgoal
            echo "$active_subgoals" | while read subgoal_key; do
                if [ -n "$subgoal_key" ]; then
                    process_goal_recursive "$subgoal_key" $((depth + 1))
                fi
            done
        fi
        
        # Also show archived subgoals for information (without processing them)
        local archived_subgoals=$(jq -r '.data.goal.subGoals.edges[]? | select(.node.archived == true) | .node.key // empty' "$goal_file" 2>/dev/null)
        if [ -n "$archived_subgoals" ]; then
            local indent=""
            for ((i=0; i<depth; i++)); do
                indent="  $indent"
            done
            echo "${indent}📦 Archived subgoals found (not processed):"
            echo "$archived_subgoals" | while read archived_key; do
                if [ -n "$archived_key" ]; then
                    echo "${indent}  - $archived_key (archived)"
                fi
            done
        fi
    fi
    
    return 0
}

# Function to process JSON and extract specific fields
process_goal_json() {
    local json_file="$1"

    # Verify that the file exists and has content
    if [ ! -f "$json_file" ] || [ ! -s "$json_file" ]; then
        echo "null,null,null,null,null,null,null,null,null,null,null,null"
        return
    fi

    if command -v jq &> /dev/null; then
        # Extract fields using jq with specified paths (all from .data.goal)
        local owner_name=$(jq -r '.data.goal.owner.pii.name // "null"' "$json_file" 2>/dev/null || echo "null")
        local goal_key=$(jq -r '.data.goal.key // "null"' "$json_file" 2>/dev/null || echo "null")
        local target_date=$(jq -r '.data.goal.targetDate // "null"' "$json_file" 2>/dev/null || echo "null")
        local goal_name=$(jq -r '.data.goal.name // "null"' "$json_file" 2>/dev/null || echo "null")
        local parent_goal_key=$(jq -r '.data.goal.parentGoal.key // "null"' "$json_file" 2>/dev/null || echo "null")
        # Extract subgoals keys (separated by ;)
        local subgoals=$(jq -r '[.data.goal.subGoals.edges[]?.node.key // empty] | join(";")' "$json_file" 2>/dev/null || echo "")
        if [ -z "$subgoals" ]; then
            subgoals="null"
        fi
        # Extract tags (separated by ;)
        local tags=$(jq -r '[.data.goal.tags.edges[]?.node.name // empty] | join(";")' "$json_file" 2>/dev/null || echo "")
        if [ -z "$tags" ]; then
            tags="null"
        fi
        # Extract progress type
        local progress_type=$(jq -r '.data.goal.progress.type // "null"' "$json_file" 2>/dev/null || echo "null")
        # Extract teams (separated by ;)
        local teams=$(jq -r '[.data.goal.teamsV2.edges[]?.node.name // empty] | join(";")' "$json_file" 2>/dev/null || echo "")
        if [ -z "$teams" ]; then
            teams="null"
        fi
        # Extract start date
        local start_date=$(jq -r '.data.goal.startDate // "null"' "$json_file" 2>/dev/null || echo "null")
        # Extract creation date
        local creation_date=$(jq -r '.data.goal.creationDate // "null"' "$json_file" 2>/dev/null || echo "null")
        # Extract Lineage (specific custom field)
        local lineage=$(jq -r '.data.goal.customFields.edges[]?.node.values.edges[]?.node.value // empty' "$json_file" 2>/dev/null | head -1)
        if [ -z "$lineage" ]; then
            lineage="null"
        fi
        # Extract ARI/entityId
        local ari=$(jq -r '.data.goal.id // "null"' "$json_file" 2>/dev/null || echo "null")
        # Clean fields (escape commas and quotes for CSV)
        owner_name=$(echo "$owner_name" | sed 's/,/;/g' | sed 's/\"/\"\"/g')
        goal_name=$(echo "$goal_name" | sed 's/,/;/g' | sed 's/\"/\"\"/g')
        # Generate CSV line
        echo "\"$owner_name\",\"$goal_key\",\"$target_date\",\"$goal_name\",\"$parent_goal_key\",\"$subgoals\",\"$tags\",\"$progress_type\",\"$teams\",\"$start_date\",\"$creation_date\",\"$lineage\",\"$ari\""
    else
        echo "null,null,null,null,null,null,null,null,null,null,null,null"
    fi
}

# STEP 1: Get initial snapshot to find root goals
echo ""
echo "📋 STEP 1: Getting initial snapshot to identify entry points..."

INITIAL_SNAPSHOT="${TEMP_DIR}/initial_snapshot.json"

# Build the JSON payload with variable substitution
PAYLOAD_JSON=$(cat <<EOF
{
  "query": "query Goals(\\n  \$after: String\\n  \$containerId: String\\n  \$directoryViewUuid: UUID\\n  \$first: Int = 50\\n  \$includeFollowerCount: Boolean!\\n  \$includeFollowing: Boolean!\\n  \$includeLastUpdated: Boolean!\\n  \$includeOwner: Boolean!\\n  \$includeRelatedProjects: Boolean!\\n  \$includeStatus: Boolean!\\n  \$includeTags: Boolean!\\n  \$includeTargetDate: Boolean!\\n  \$includeTeam: Boolean!\\n  \$includedCustomFieldUuids: [UUID!]\\n  \$skipTableTql: Boolean!\\n  \$sorts: [GoalSortEnum]\\n  \$tql: String\\n  \$workspaceUuid: UUID\\n) {\\n  ...DirectoryTableViewGoal_3JCCLt\\n}\\n\\nfragment CustomFieldCell on CustomFieldConnection {\\n  edges {\\n    node {\\n      __typename\\n      ... on CustomFieldNode {\\n        __isCustomFieldNode: __typename\\n        definition {\\n          __typename\\n          ... on CustomFieldDefinitionNode {\\n            __isCustomFieldDefinitionNode: __typename\\n            uuid\\n          }\\n          ... on Node {\\n            __isNode: __typename\\n            id\\n          }\\n        }\\n      }\\n      ...NumberFieldColumn\\n      ...TextSelectFieldColumn\\n      ...UserFieldColumn\\n      ...TextFieldColumn\\n      ... on Node {\\n        __isNode: __typename\\n        id\\n      }\\n    }\\n  }\\n}\\n\\nfragment DirectoryRow_367brx on Goal {\\n  id\\n  ari\\n  key\\n  hasSubgoalMatches\\n  latestUpdateDate @include(if: \$includeLastUpdated)\\n  ...GoalNameColumn\\n  ...GoalFollowButton @include(if: \$includeFollowing)\\n  ...GoalActions\\n  dueDate @include(if: \$includeTargetDate) {\\n    ...TargetDate\\n  }\\n  state @include(if: \$includeStatus) {\\n    ...GoalState\\n  }\\n  owner @include(if: \$includeOwner) {\\n    ...UserAvatar_2aqwkz\\n    id\\n  }\\n  projects @include(if: \$includeRelatedProjects) {\\n    ...RelatedGoalProjects\\n  }\\n  teamsV2 @include(if: \$includeTeam) {\\n    ...TeamOfGoal\\n  }\\n  tags @include(if: \$includeTags) {\\n    ...TagColumn\\n  }\\n  ...FollowerCount_goal @include(if: \$includeFollowerCount)\\n  customFields(includedCustomFieldUuids: \$includedCustomFieldUuids) {\\n    ...CustomFieldCell\\n  }\\n  ...MetricColumn\\n}\\n\\nfragment DirectoryTableViewGoal_3JCCLt on Query {\\n  goalTqlFullHierarchy(first: \$first, after: \$after, q: \$tql, workspaceUuid: \$workspaceUuid, containerId: \$containerId, sorts: \$sorts, directoryViewUuid: \$directoryViewUuid) @skip(if: \$skipTableTql) {\\n    count\\n    edges {\\n      node {\\n        id\\n        ari\\n        ...RootDirectoryRow_367brx\\n        __typename\\n      }\\n      cursor\\n    }\\n    pageInfo {\\n      endCursor\\n      hasNextPage\\n    }\\n  }\\n  currentUser {\\n    preferences {\\n      wrapTextEnabled\\n      id\\n    }\\n    id\\n  }\\n}\\n\\nfragment FollowerCount_goal on Goal {\\n  ...GoalFollowersButton\\n}\\n\\nfragment GoalActions on Goal {\\n  id\\n  name\\n  archived\\n  parentGoal {\\n    id\\n  }\\n  subGoals {\\n    edges {\\n      node {\\n        archived\\n        id\\n      }\\n    }\\n  }\\n}\\n\\nfragment GoalFollowButton on Goal {\\n  id\\n  uuid\\n  watching\\n}\\n\\nfragment GoalFollowersButton on Goal {\\n  key\\n  watchers {\\n    count\\n  }\\n}\\n\\nfragment GoalName on Goal {\\n  uuid\\n  id\\n  key\\n  ...PlatformGoalIcon\\n  name\\n}\\n\\nfragment GoalNameColumn on Goal {\\n  id\\n  managerData {\\n    managers {\\n      managerProfile {\\n        name\\n      }\\n      directReports\\n    }\\n  }\\n  ...GoalName\\n}\\n\\nfragment GoalState on GoalState {\\n  label(includeScore: false)\\n  localizedLabel {\\n    messageId\\n  }\\n  score\\n  goalStateValue: value\\n  atCompletionState {\\n    label(includeScore: false)\\n    localizedLabel {\\n      messageId\\n    }\\n    value\\n    score\\n  }\\n}\\n\\nfragment MetricChart on Goal {\\n  ...WrappedWithMetricPopup\\n  id\\n  progress {\\n    type\\n    percentage\\n  }\\n  subGoals {\\n    count\\n  }\\n  metricTargets {\\n    edges {\\n      node {\\n        ...common_metricTarget_direct\\n        id\\n      }\\n    }\\n  }\\n}\\n\\nfragment MetricColumn on Goal {\\n  id\\n  uuid\\n  ...progressBarMetricTarget\\n  ...hasMetric\\n  ...MetricChart\\n}\\n\\nfragment NumberFieldColumn on NumberCustomField {\\n  value {\\n    numberValue: value\\n    id\\n  }\\n}\\n\\nfragment PlatformGoalIcon on Goal {\\n  icon {\\n    key\\n    appearance\\n  }\\n}\\n\\nfragment ProjectIcon on Project {\\n  private\\n  iconUrl {\\n    square {\\n      light\\n      dark\\n      transparent\\n    }\\n  }\\n}\\n\\nfragment ProjectName_data on Project {\\n  id\\n  key\\n  name\\n  uuid\\n  ...ProjectIcon\\n}\\n\\nfragment RelatedGoalProjects on ProjectConnection {\\n  count\\n  edges {\\n    node {\\n      ...ProjectName_data\\n      id\\n    }\\n  }\\n}\\n\\nfragment RootDirectoryRow_367brx on Goal {\\n  id\\n  ...DirectoryRow_367brx\\n}\\n\\nfragment Tag on Tag {\\n  ...Tag_createTagOption\\n}\\n\\nfragment TagColumn on TagConnection {\\n  edges {\\n    node {\\n      ...Tag\\n      id\\n    }\\n  }\\n  count\\n}\\n\\nfragment Tag_createTagOption on Tag {\\n  id\\n  name\\n  uuid\\n  description\\n  projectUsageCount\\n  goalUsageCount\\n  helpPointerUsageCount\\n  watcherCount\\n}\\n\\nfragment TargetDate on TargetDate {\\n  confidence\\n  label\\n  localizedLabel {\\n    messageId\\n  }\\n  tooltip: label(longFormat: true)\\n  localizedTooltip: localizedLabel(longFormat: true) {\\n    messageId\\n  }\\n  overdue\\n}\\n\\nfragment TeamOfGoal on GoalTeamConnection {\\n  edges {\\n    node {\\n      avatarUrl\\n      name\\n      teamId\\n      id\\n    }\\n  }\\n  count\\n}\\n\\nfragment TextFieldColumn on TextCustomField {\\n  value {\\n    textValue: value\\n    id\\n  }\\n}\\n\\nfragment TextSelectFieldColumn on TextSelectCustomField {\\n  definition {\\n    __typename\\n    ... on TextSelectCustomFieldDefinition {\\n      canSetMultipleValues\\n    }\\n    ... on Node {\\n      __isNode: __typename\\n      id\\n    }\\n  }\\n  values {\\n    count\\n    edges {\\n      node {\\n        id\\n        value\\n      }\\n    }\\n  }\\n}\\n\\nfragment UserAvatar_2aqwkz on User {\\n  aaid\\n  pii {\\n    picture\\n    accountId\\n    name\\n  }\\n}\\n\\nfragment UserFieldColumn on UserCustomField {\\n  definition {\\n    __typename\\n    ... on UserCustomFieldDefinition {\\n      canSetMultipleValues\\n    }\\n    ... on Node {\\n      __isNode: __typename\\n      id\\n    }\\n  }\\n  values {\\n    count\\n    edges {\\n      node {\\n        pii {\\n          accountId\\n          name\\n          picture\\n        }\\n        id\\n      }\\n    }\\n  }\\n}\\n\\nfragment WrappedWithMetricPopup on Goal {\\n  id\\n  progress {\\n    percentage\\n  }\\n  metricTargets {\\n    edges {\\n      node {\\n        ...common_metricTarget_direct\\n        metric {\\n          archived\\n          id\\n        }\\n        id\\n      }\\n    }\\n  }\\n}\\n\\nfragment common_metricTarget_direct on MetricTarget {\\n  startValue\\n  targetValue\\n  snapshotValue {\\n    value\\n    id\\n  }\\n  metric {\\n    id\\n    name\\n    type\\n    subType\\n  }\\n}\\n\\nfragment hasMetric on Goal {\\n  progress {\\n    type\\n  }\\n  metricTargets {\\n    edges {\\n      node {\\n        metric {\\n          archived\\n          id\\n        }\\n        id\\n      }\\n    }\\n  }\\n}\\n\\nfragment progressBarMetricTarget on Goal {\\n  progress {\\n    type\\n    percentage\\n  }\\n  metricTargets {\\n    edges {\\n      node {\\n        snapshotValue {\\n          value\\n          id\\n        }\\n        startValue\\n        targetValue\\n        metric {\\n          type\\n          subType\\n          id\\n        }\\n        id\\n      }\\n    }\\n  }\\n}\\n",
  "variables": {
    "after": null,
    "containerId": "ari:cloud:townsquare::site/${CLOUD_ID}",
    "directoryViewUuid": "${DIRECTORY_VIEW_UUID}",
    "first": 50,
    "includeFollowerCount": false,
    "includeFollowing": false,
    "includeLastUpdated": false,
    "includeOwner": true,
    "includeRelatedProjects": false,
    "includeStatus": false,
    "includeTags": true,
    "includeTargetDate": true,
    "includeTeam": true,
    "includedCustomFieldUuids": ["${CUSTOM_FIELD_UUID}"],
    "skipTableTql": false,
    "sorts": null,
    "tql": null,
    "workspaceUuid": "${WORKSPACE_UUID}"
  }
}
EOF
)

curl -s "${ATLASSIAN_BASE_URL}/gateway/api/townsquare/s/${CLOUD_ID}/graphql?operationName=DirectoryTableViewGoalPaginationQuery" \
  -H 'accept: */*' \
  -H 'accept-language: es-ES,es;q=0.9,en;q=0.8' \
  -H 'atl-client-name: townsquare-frontend' \
  -H 'atl-client-version: daf3c1' \
  -H 'content-type: application/json' \
  -b "$ATLASSIAN_COOKIES" \
  -H "origin: ${ATLASSIAN_BASE_URL}" \
  -H 'priority: u=1, i' \
  -H "referer: ${ATLASSIAN_BASE_URL}/o/${ORGANIZATION_ID}/goals?viewUuid=${DIRECTORY_VIEW_UUID}&cloudId=${CLOUD_ID}" \
  -H 'sec-ch-ua: "Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "macOS"' \
  -H 'sec-fetch-dest: empty' \
  -H 'sec-fetch-mode: cors' \
  -H 'sec-fetch-site: same-origin' \
  -H 'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36' \
  --data-raw "$PAYLOAD_JSON" \
  -o "$INITIAL_SNAPSHOT"

if [ ! -f "$INITIAL_SNAPSHOT" ]; then
    echo "❌ Error: Could not download initial snapshot"
    exit 1
fi

echo "✅ Initial snapshot downloaded: $(du -h "$INITIAL_SNAPSHOT" | cut -f1)"

# STEP 2: Identify root goals (tree entry points)
echo ""
echo "🌳 STEP 2: Identifying root goals as entry points..."

if command -v jq &> /dev/null; then
    root_goals=$(jq -r '.data.goalTqlFullHierarchy.edges[]?.node.key // empty' "$INITIAL_SNAPSHOT" 2>/dev/null)
    if [ -z "$root_goals" ]; then
        echo "❌ Error: Could not extract goal keys from snapshot"
        exit 1
    fi
    
    root_count=$(echo "$root_goals" | wc -l | tr -d ' ')
    echo "🌱 Found $root_count goals as entry points:"
    echo "$root_goals" | while read goal; do
        echo "  🎯 $goal"
    done
else
    echo "❌ Error: jq is not available. Required to process JSON"
    exit 1
fi

# STEP 3: Recursive depth-first search (DFS) of the tree
echo ""
echo "🔍 STEP 3: Starting recursive depth-first search (DFS)..."
echo "🌳 Tree structure:"

# Process each root goal recursively
echo "$root_goals" | while read root_goal; do
    if [ -n "$root_goal" ]; then
        echo ""
        echo "🎯 Processing tree from root: $root_goal"
        process_goal_recursive "$root_goal" 0
    fi
done

# STEP 4: Generate final CSV with all found goals
echo ""
echo "📊 STEP 4: Generating final CSV with all goals from the tree..."

# Create CSV header
echo "created_at,Owner,Goal Key,Target Date,Name,Parent Goal,Sub-goals,Tags,Progress Type,Teams,Start Date,Creation Date,Lineage,EntityId" > "$FINAL_CSV"

# Process all generated JSON files
total_processed=0
for json_file in "${TEMP_DIR}"/*.json; do
    if [ -f "$json_file" ] && [[ "$json_file" != *"initial_snapshot.json" ]]; then
        csv_line=$(process_goal_json "$json_file")
        echo "$TIMESTAMP,$csv_line" >> "$FINAL_CSV"
        total_processed=$((total_processed + 1))
    fi
done

# STEP 5: Cleanup
echo ""
echo "🧹 STEP 5: Cleaning up temporary files..."
rm -rf "$TEMP_DIR"

# Final summary
echo ""
echo "🎉 Recursive traversal completed successfully!"
echo "📊 Final CSV: $FINAL_CSV ($(du -h "$FINAL_CSV" | cut -f1))"
echo "🌳 Total goals processed: $total_processed"
echo "📅 Lines in CSV: $(wc -l < "$FINAL_CSV" | tr -d ' ') (including header)"
echo "🔍 Algorithm used: Recursive Depth-First Search (DFS)"

echo ""
echo "🔍 CSV preview:"
head -5 "$FINAL_CSV" 