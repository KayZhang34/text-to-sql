# text-to-sql

A natural-language agent that converts plain-English questions into DuckDB SQL and executes them against Home Mortgage Disclosure Act (HMDA) data for New York State (2025). Includes a Streamlit web app for end users and an evaluation harness for measuring agent accuracy.

> **Live demo:** [your-app-name.streamlit.app](https://your-app-name.streamlit.app)

## What it does

Ask a question in plain English, get back a SQL query the agent wrote and the result:

```
"What are the top 5 counties by total application count?"
→ generates a query w/ JOIN + GROUP BY against 430k HMDA records
→ returns a DataFrame, plus an auto-generated chart
```

Under the hood, the agent uses Claude's tool-use API to return a SQL query plus an optional explanation and an optional chart spec. If a query fails to execute, the agent self-corrects on a retry by feeding the error back to the model.

## Running the app

```bash
streamlit run app.py
```

Opens a local web UI where you can ask questions, see the generated SQL, and view the result as a chart and/or table.

## Setup

**Prerequisites:** Python 3.9+, an Anthropic API key, and the raw HMDA data file.

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=your-key-here
```

### Build the database

The raw HMDA dataset is not committed to the repo. Download it from the [CFPB HMDA Data](https://ffiec.cfpb.gov/data-publication/modified-lar/2025) site and save it to `data/raw/2025_raw.txt`. Then run the loaders in order:

```bash
python scripts/01_filter_raw.py           # filter to NY-only records → data/processed/
python scripts/02_load_data.py            # load CSV into DuckDB → data/hmda.db
python scripts/03_build_county_lookup.py  # build county FIPS → name mapping
```

The loader auto-detects numeric columns and casts them from VARCHAR to DOUBLE via `TRY_CAST`, handling HMDA's mixed-type fields (e.g., `loan_amount` containing both numbers and `'Exempt'`). It deletes and rebuilds the `.db` file on each run so the script is idempotent.

## Programmatic usage

```python
from src.agent import ask

result = ask("How many loans were denied vs approved?")

print(result["sql"])          # the generated SQL
print(result["results"])      # pandas DataFrame with query output
print(result["explanation"])  # optional context from the model (or None)
print(result["chart"])        # optional chart spec dict (or None)
print(result["error"])        # None if successful
```

### Example questions

```
"What is the total dollar volume of all originated loans?"
"Compare average loan amount for Manhattan vs Staten Island"
"What is the approval rate by applicant ethnicity?"
"Top 5 counties by application count"
"Distribution of loan purposes"
```

## Data

**Source:** [CFPB HMDA Data](https://ffiec.cfpb.gov/data-publication/modified-lar/2025) — 2025 loan application records
**Scope:** New York State only (~430k records, 85 columns)
**Database:** DuckDB at `data/hmda.db`

Key columns: `action_taken`, `loan_amount`, `loan_purpose`, `loan_type`, `county_code`, `income` (in thousands), applicant demographics.

Special codes to be aware of: `1111` = Exempt, `8888` = Not Available.

## Evaluation

An eval suite of 15 questions tests correctness across categories (simple aggregation, joins, demographic analysis, edge cases, out-of-scope handling):

```bash
python eval/evaluate.py
# outputs → eval/results/eval_results_TIMESTAMP.csv
```

Questions are defined in [`eval/questions.json`](eval/questions.json). Results CSVs include the generated SQL, any explanation the model surfaced, pass/fail per check, and execution errors.

## Project structure

```
app.py                       # Streamlit web app entry point
src/
  agent.py                   # core ask() function — Claude tool-use, retries, schema prompt
eval/
  evaluate.py                # eval harness
  questions.json             # 15 test questions with expected outputs
  results/                   # eval run CSVs
scripts/
  01_filter_raw.py           # filter HMDA data to NY
  02_load_data.py            # load CSV into DuckDB with auto-cast
  03_build_county_lookup.py  # build county FIPS → name mapping
data/
  raw/                       # original HMDA dataset (not in repo)
  processed/                 # NY-filtered data (not in repo)
  hmda.db                    # DuckDB database
notebooks/
  01_explore_data.ipynb
```
