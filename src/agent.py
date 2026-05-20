"""Text-to-SQL agent: convert natural language questions to DuckDB queries."""
import os
from pathlib import Path

import duckdb
from anthropic import Anthropic
from dotenv import load_dotenv

# Load API key from .env
load_dotenv()

# Set path variables
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'hmda.db'

# Initialize the Claude client
client = Anthropic()

# Write prompt context for schema
SCHEMA_DESCRIPTION = """
DuckDB database (hmdb.db) Access with tables: hmda_ny, ny_counties

Table: hmda_ny
This table contains 2025 Home Mortgage Disclosure Act (HMDA) records for New York state.

Key columns:
- activity_year (INTEGER): year of the application, always 2025 for this dataset
- state_code (VARCHAR): always 'NY' for this dataset
- county_code (INTEGER): FIPS county code 5-digit
- action_taken (INTEGER): outcome of the application
    1 = Loan originated (approved and closed)
    2 = Application approved but not accepted
    3 = Application denied
    4 = Application withdrawn by applicant
    5 = File closed for incompleteness
    6 = Purchased loan
    7 = Preapproval request denied
    8 = Preapproval request approved but not accepted
- loan_amount (DOUBLE): loan amount in dollars, this is roudned to the nearest $10k midpoint
- property_value (DOUBLE): property value in dollars, this is roudned to the nearest $10k midpoint
- income (DOUBLE): applicant gross annual income in thousands of dollars
- loan_purpose (INTEGER): 1=home purchase, 2=home improvement, 31=refinance, 32=cash-out refi, 4=other, 5=N/A
- loan_type (INTEGER): 1=conventional, 2=FHA, 3=VA, 4=USDA
- denial_reason_1 (INTEGER): primary reason for denial when action_taken=3
- applicant_ethnicity_1 (codes: 1=Hispanic/Latino, 11-14=subcategories, 
  2=Not Hispanic/Latino, 3=Info not provided, 4=N/A)
- applicant_race_1 ... applicant_race_5 (codes: 1=American Indian, 2=Asian, 3=Black,
  4=Native Hawaiian/Pacific Islander, 5=White, 6=Info not provided, 7=N/A).
  Up to 5 race codes can be reported per applicant. To find applicants who
  identified with more than one race, filter on applicant_race_2 IS NOT NULL.
  The same _1.._5 multi-value pattern applies to applicant_ethnicity and to
  the co_applicant_race / co_applicant_ethnicity columns below.
- applicant_sex (codes: 1=Male, 2=Female, 3=Info not provided, 4=N/A, 6=Both selected)
- co_applicant_ethnicity_1, co_applicant_race_1, co_applicant_sex: same code system
  as the applicant_* equivalents, plus one extra value:
    5 = No co-applicant
  Use co_applicant_sex = 5 (or co_applicant_race_1 = 5) to find applications with
  no co-applicant. These columns are NOT null when there is no co-applicant —
  they use the sentinel code 5.
- There are special values to filter out 1111 = 'Exempt' and 8888 = 'Not Available' for some fields like aus_1 to aus_5.
    - ^If we see some categorical variables with these special values, we should filter them out for some calcualtions of percentages or averages
- When computing rates by demographic, filter out the "Info not provided"  and "N/A" categories for cleaner results.

(Note: there are many columns, but use only the ones you need.)

IMPORTANT - columns to NOT reference:
- universal_loan_identifier / ULI (redacted for privacy)
- Exact credit scores (only applicant_credit_scoring_model is available, not the score itself)

Table: ny_counties
This table contains a mapping of New York state FIPS county codes to their corresponding county names.
Columns:
- fips_code (INTEGER): FIPS county code 5-digit matches the county_code in hmda_ny directly, no need for casting
- county_name (VARCHAR): name of the county in plain english. Note: 'Kings' is the same as 'Brooklyn', 'Richmond' is the same as 'Staten Island', 'new York' is the same as 'Manhattan'.

When the user asks about counties by name, JOIN hmda_ny to ny_counties.
When showing county results, prefer county_name over county_code in output.
"""

# Define the tool schema for submitting SQL queries to Claude
# This is how we tell Claude to give us SQL that we can run directly, without any extra context.
# The optional "explanation" field is for when context would be helpful, but it should be left out for straightforward queries.
QUERY_TOOL = {
    "name": "submit_query",
    "description": "Submit a DuckDB SQL query that answers the user's question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "A single DuckDB SQL query that answers the user's question."
            },
            "explanation": {
                "type": "string",
                "description": (
                    "Optional. Include ONLY when it adds real value to the user: "
                    "when an assumption was made to resolve ambiguity, when a caveat "
                    "applies to the result (e.g., the dataset doesn't fully cover the "
                    "question), or when the SQL uses non-obvious reasoning worth "
                    "surfacing. Omit entirely for straightforward queries where the "
                    "SQL is self-explanatory — do not pad with summaries of what the "
                    "query does."
                )
            }
        },
        "required": ["sql"]
    }
}


# base prompt sent to claude, includes "SCHEMA_DESCRIPTION" context and the user's "question" input
def build_prompt(question: str) -> str:
    """Build the prompt sent to Claude."""
    return f"""You are an expert SQL analyst. Write a single DuckDB SQL query that answers the user's question, and submit it via the submit_query tool.

{SCHEMA_DESCRIPTION}

User question: {question}

Rules:
- Use DuckDB syntax (PostgreSQL-compatible).
- If the question is ambiguous, make a reasonable assumption and surface it in the explanation field.
- For percentages or rates, use ROUND(... * 100, 2) for readability.
- Only fill in `explanation` when it adds value (assumption made, caveat about the result, dataset coverage limitation, or non-obvious reasoning). Leave it out for straightforward queries.
"""

import re
# Helper function to clean up SQL output. May include markdown code fences or stray non-ASCII characters.
def clean_sql(raw: str) -> str:
    # Remove markdown code fences (```sql ... ``` or ``` ... ```) and stray non-ASCII characters
    cleaned = re.sub(r'^```(?:sql)?\s*', '', raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    
    # Strip non-printable / non-ASCII characters that sometimes sneak in
    cleaned = ''.join(ch for ch in cleaned if ch.isprintable() or ch in '\n\t')
    
    # Collapse leading whitespace
    return cleaned.strip()

def build_retry_prompt(question: str, failed_sql: str, error: str) -> str:
    """Build a follow-up prompt that asks the model to fix a failed query."""
    return f"""You previously generated SQL for the user's question, but it failed when executed against DuckDB. Fix the SQL and submit the corrected version via the submit_query tool.

{SCHEMA_DESCRIPTION}

User question: {question}

Your previous (failed) SQL:
{failed_sql}

DuckDB error:
{error}

Rules:
- Submit a corrected single DuckDB SQL statement via submit_query.
- Address the specific error above. Common causes: missing FROM clause, wrong column name, type mismatch.
- Same explanation rules as before — only fill in `explanation` when it adds real value to the user.
"""


def ask(question: str, max_retries: int = 1) -> dict:
    """
    Take a natural language question, generate SQL, run it, return results.

    On execution failure, retries up to `max_retries` times — each retry sends
    the failed SQL and error back to the model so it can self-correct.

    Returns a dict with keys: question, sql, explanation, results (DataFrame), error.
    """
    prompt = build_prompt(question)
    sql = ""
    explanation = None

    for attempt in range(max_retries + 1):
        response = client.messages.create(
            model='claude-sonnet-4-5',
            max_tokens=1024,
            tools=[QUERY_TOOL],
            tool_choice={"type": "tool", "name": "submit_query"},
            messages=[{'role': 'user', 'content': prompt}],
        )

        # tool_choice forces submit_query, so the tool_use block must exist
        tool_use = next(b for b in response.content if b.type == "tool_use")
        sql = clean_sql(tool_use.input["sql"])
        explanation = tool_use.input.get("explanation")  # None when omitted

        try:
            con = duckdb.connect(str(DB_PATH), read_only=True)
            results = con.execute(sql).fetchdf()
            con.close()
            return {
                'question': question,
                'sql': sql,
                'explanation': explanation,
                'results': results,
                'error': None,
            }
        except Exception as e:
            error = str(e)
            if attempt < max_retries:
                # Swap in a retry prompt that includes the failed SQL + error,
                # so the model can self-correct on the next iteration.
                prompt = build_retry_prompt(question, sql, error)
                continue
            # Out of retries — return the failure
            return {
                'question': question,
                'sql': sql,
                'explanation': explanation,
                'results': None,
                'error': error,
            }


# Quick manual test when running this file directly
if __name__ == '__main__':
    test_questions = [
        "How many loan applications were denied?",
        "What was the average loan amount for approved loans?",
        "What counties have the highest denial rates?",
        "What is the average income for applicants in each county?",
    ]
    
    for q in test_questions:
        # formatting w/ line breaks for readability in the console output
        print(f"\n{'='*60}")
        print(f"Q: {q}")
        result = ask(q)
        print(f"\nSQL:\n{result['sql']}")

        # Show explanation only when it's present, to avoid cluttering the output for simple queries that don't need it.
        if result.get('explanation'):
            print(f"\nExplanation:\n{result['explanation']}")
        if result['error']:
            print(f"\nERROR: {result['error']}")
        else:
            print(f"\nResults:\n{result['results']}")