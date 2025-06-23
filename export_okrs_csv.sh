#!/usr/bin/env bash
set -e

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
required_vars=("ATLASSIAN_BASE_URL" "ORGANIZATION_ID" "CLOUD_ID" "WORKSPACE_UUID" "ATLASSIAN_COOKIES")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Error: Required configuration variable $var is not set in config.env"
        exit 1
    fi
done

# Use curlie if available, otherwise curl
if command -v curlie >/dev/null 2>&1; then
  CURL_BIN="curlie"
else
  CURL_BIN="curl"
fi

EXPECTED_HEADER="Goal Key,Name,Status,Creation Date,Target Date,Owner,Teams,Parent Goal,Sub-goals,Contributing Projects,Tags,Latest update date"

# Timestamp in YYYYMMDDHHMM format
TS=$(date +"%Y%m%d%H%M")
OUTPUT="export-${TS}.csv"

echo "Downloading snapshot to $OUTPUT using $CURL_BIN ..."

$CURL_BIN "${ATLASSIAN_BASE_URL}/gateway/api/townsquare/s/${CLOUD_ID}/export/goals/tql?q=%28archived+%3D+false%29&workspaceUuid=${WORKSPACE_UUID}&sort=WATCHING_DESC%2CLATEST_UPDATE_DATE_DESC%2CNAME_ASC" \
  -H 'accept: */*' \
  -H 'accept-language: es-ES,es;q=0.9,en;q=0.8' \
  -H 'priority: u=1, i' \
  -b "$ATLASSIAN_COOKIES" \
  -H "referer: ${ATLASSIAN_BASE_URL}/o/${ORGANIZATION_ID}/goals" \
  -H 'sec-ch-ua: "Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "macOS"' \
  -H 'sec-fetch-dest: empty' \
  -H 'sec-fetch-mode: cors' \
  -H 'sec-fetch-site: same-origin' \
  -H 'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36' \
  --compressed \
  -o "$OUTPUT"

echo "Verifying CSV header ..."
HEADER=$(head -n 1 "$OUTPUT" | tr -d '\r')
if [[ "$HEADER" != "$EXPECTED_HEADER" ]]; then
  echo "Header mismatch! Expected:\n$EXPECTED_HEADER\nFound:\n$HEADER"
  exit 1
fi

echo "Header OK. Processing with add_timestamp_to_csv.py ..."
python helpers/add_timestamp_to_csv.py "$OUTPUT"

PROCESSED="${OUTPUT/.csv/_processed.csv}"

# Move files to data_snapshots if processing succeeded
mkdir -p data_snapshots
mv "$OUTPUT" "$PROCESSED" data_snapshots/

echo "Files moved to data_snapshots. Running visualization ..."
python tools/okrs_sanity_check_bq_data.py 