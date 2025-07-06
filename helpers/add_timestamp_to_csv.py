"""
This script processes a CSV file, adds a 'created_at' column with the file creation timestamp (YYYYMMDDHHmm),
cleans multiline fields, and loads the result into a BigQuery table.

# BigQuery setup commands:

# 1. Create the dataset (example):
#    bq mk --location=EU okrs_dataset

# 2. Create the table (example, autodetect schema from processed CSV):
#    bq mk --autodetect --source_format=CSV --skip_leading_rows=1 -t okrs_dataset.okrs_table ./yourfile_processed.csv
#    # Or define the schema manually if needed:
#    bq mk -t --schema 'created_at:STRING,Goal Key:STRING,Name:STRING,Status:STRING,Creation Date:DATE,Target Date:STRING,Owner:STRING,Teams:STRING,Parent Goal:STRING,Sub-goals:STRING,Contributing Projects:STRING,Tags:STRING,Latest update date:TIMESTAMP' okrs_dataset.okrs_table
#
# 3. Create team table:
#    bq mk -t --schema 'team:STRING,name:STRING,role:STRING' okrs_dataset.teams
#
# 4. Load the team data:
#    bq load --autodetect --source_format=CSV --skip_leading_rows=1 -t okrs_dataset.teams ./data/teams.csv
# 

"""
import csv
import sys
import os
import datetime
import subprocess
from pathlib import Path

# Add helpers directory to path for config loader
helpers_dir = Path(__file__).parent
sys.path.insert(0, str(helpers_dir))

from config_loader import get_bigquery_config

# Load configuration
config = get_bigquery_config()

def clean_multiline_fields(row):
    # Replace internal newlines in each field with spaces
    return [field.replace('\n', ' ').replace('\r', ' ') if isinstance(field, str) else field for field in row]

def main():
    if len(sys.argv) != 2:
        print("Usage: python add_timestamp_to_csv.py input_file.csv")
        sys.exit(1)

    input_file = sys.argv[1]
    basename, ext = os.path.splitext(input_file)
    output_file = f"{basename}_processed{ext}"

    # File creation timestamp in format YYYYMMDDHHmm
    creation_epoch = os.path.getctime(input_file)
    timestamp = datetime.datetime.fromtimestamp(creation_epoch).strftime('%Y%m%d%H%M')

    with open(input_file, newline='', encoding='utf-8') as infile, \
         open(output_file, 'w', newline='', encoding='utf-8') as outfile:
        reader = csv.reader(infile)
        writer = csv.writer(outfile)

        for i, row in enumerate(reader):
            row = clean_multiline_fields(row)
            if i == 0:
                writer.writerow(['created_at'] + row)
            else:
                writer.writerow([timestamp] + row)

    print(f"Processed file: {output_file}")

    # Load to BigQuery
    bq_cmd = [
        "bq", "load", "--autodetect", "--source_format=CSV", "--skip_leading_rows=1",
        f"{config['dataset']}.{config['table']}", output_file
    ]
    print(f"Loading file to BigQuery: {' '.join(bq_cmd)}")
    try:
        result = subprocess.run(bq_cmd, check=True, capture_output=True, text=True)
        print("BigQuery load output:")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("BigQuery load failed:")
        print(e.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main() 