# text-to-sql
A natural language agent that translates questions into DuckDB SQL and executes them against Home Mortgage Disclosure Act (HMDA) data for New York State (2025).

## What it does
User asks a question in plain English to get back a SQL query and results:

```
"What are the top 5 counties by total application count?"
→ runs a JOIN + GROUP BY against 430k HMDA records
→ returns a DataFrame with results
```

The agent uses Claude to generate SQL, then executes it against a local DuckDB database in read-only mode.

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

The raw HMDA dataset is not included in the repo, but a link to the government website where you can download is provided below. I saved it in `data/raw/2025_raw.txt`, then you can run the below scripts to get the cleaned DB that this agent queries against:

```bash
python scripts/filter_raw.py        # filter to NY-only records → data/processed/
python scripts/load_data.py         # load into DuckDB → data/hmda.db
python scripts/build_county_lookup.py  # build county FIPS → name mapping
```

## Usage

```python
from src.agent import ask

result = ask("How many loans were denied vs approved?")

print(result["sql"])      # the generated SQL
print(result["results"])  # pandas DataFrame with query output
print(result["error"])    # None if successful
```

### Example questions

```
"What is the total dollar volume of all originated loans?"
"Compare average loan amount for Manhattan vs Staten Island"
"What is the approval rate by applicant ethnicity?"
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

Questions are defined in [`eval/questions.json`](eval/questions.json).

## Project structure

```
src/
  agent.py              # core ask() function
eval/
  evaluate.py           # eval harness
  questions.json        # 15 test questions with expected outputs
  results/              # eval run CSVs
scripts/
  filter_raw.py         # filter HMDA data to NY
  load_data.py          # load CSV into DuckDB
  build_county_lookup.py
data/
  raw/                  # original HMDA dataset (not in repo)
  processed/            # NY-filtered data
  hmda.db               # DuckDB database
notebooks/
  01_explore_data.ipynb
```
