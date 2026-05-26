"""Filter raw HMDA data to NY-only records and save to data/processed/."""

import pandas as pd
from pathlib import Path

# Project root = the folder containing this script's parent folder
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent 

raw_path = PROJECT_ROOT / 'data' / 'raw' / '2025_raw.txt'
processed_path = PROJECT_ROOT / 'data' / 'processed' / '2025_processed_NY.txt'

# Make sure the processed folder exists before writing
processed_path.parent.mkdir(parents=True, exist_ok=True)

#read raw data into dataframe
df = pd.read_csv(raw_path, sep='|')
#filter dataframe by NY state
df_filtered = df[df['state_code'] == 'NY']
#write datafrme to a processed file
df_filtered.to_csv(processed_path, sep='|', index=False)

print(f"Data processed and filtered and saved to {processed_path}")