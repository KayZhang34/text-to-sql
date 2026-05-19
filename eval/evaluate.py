"""
Run all eval questions through the agent, score them, and write a results CSV.

Usage (from project root):
    python eval/evaluate.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# Make src/ importable when running from project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from agent import ask  # noqa: E402


QUESTIONS_PATH = PROJECT_ROOT / 'eval' / 'questions.json'
RESULTS_DIR = PROJECT_ROOT / 'eval' / 'results'


def check_sql_contains(sql: str, required_substrings: list[str]) -> bool:
    """Return True if all required substrings appear in the SQL (case-insensitive)."""
    if not sql:
        return False
    sql_lower = sql.lower()
    return all(sub.lower() in sql_lower for sub in required_substrings)


def check_scalar_result(actual_df: pd.DataFrame, expected_value) -> bool:
    """For questions expecting a single number, compare with tolerance."""
    if actual_df is None or actual_df.empty:
        return False
    try:
        actual = actual_df.iloc[0, 0]
        # Allow 1% tolerance for floats; exact for ints
        if isinstance(expected_value, float):
            return abs(actual - expected_value) / max(abs(expected_value), 1) < 0.01
        return actual == expected_value
    except Exception:
        return False


def check_result_contains(actual_df: pd.DataFrame, expected_substring: str) -> bool:
    """For row/table results, check that the expected substring appears anywhere."""
    if actual_df is None or actual_df.empty:
        return False
    # Convert the whole DataFrame to a string and check
    text = actual_df.to_string().lower()
    return expected_substring.lower() in text


def score_question(question: dict, agent_output: dict) -> dict:
    """
    Apply the scoring rules for one question.
    Returns the question dict augmented with pass/fail and diagnostic info.
    """
    sql = agent_output.get('sql', '')
    results = agent_output.get('results')
    error = agent_output.get('error')

    # Independent checks - we record each one so we can see what failed
    sql_check_pass = True
    result_check_pass = True
    sql_check_detail = 'no SQL check required'
    result_check_detail = 'no result check required'

    # SQL substring check
    required = question.get('expected_sql_must_contain')
    if required:
        sql_check_pass = check_sql_contains(sql, required)
        sql_check_detail = f"required: {required}"

    # Result check - depends on type
    result_type = question.get('expected_result_type')
    if error:
        result_check_pass = False
        result_check_detail = f"SQL execution error: {error}"
    elif result_type == 'scalar' and 'expected_result' in question:
        result_check_pass = check_scalar_result(results, question['expected_result'])
        result_check_detail = f"expected {question['expected_result']}"
    elif result_type in ('row', 'table') and 'expected_result_contains' in question:
        result_check_pass = check_result_contains(results, question['expected_result_contains'])
        result_check_detail = f"expected to contain '{question['expected_result_contains']}'"
    elif question.get('category') == 'out_of_scope':
        # For adversarial questions: pass if no error and result is empty/sensible
        result_check_pass = error is None
        result_check_detail = "adversarial: agent should not crash"

    overall_pass = sql_check_pass and result_check_pass

    return {
        'id': question['id'],
        'question': question['question'],
        'category': question.get('category', ''),
        'difficulty': question.get('difficulty', ''),
        'pass': overall_pass,
        'sql_check_pass': sql_check_pass,
        'result_check_pass': result_check_pass,
        'sql_check_detail': sql_check_detail,
        'result_check_detail': result_check_detail,
        'generated_sql': sql,
        'explanation': agent_output.get('explanation') or '',
        'error': error or '',
    }


def main():
    # Load questions
    with open(QUESTIONS_PATH) as f:
        questions = json.load(f)

    print(f"Running {len(questions)} eval questions...\n")
    results = []

    for q in questions:
        print(f"  [{q['id']:>2}] {q['question'][:70]}...", end=' ', flush=True)
        try:
            agent_output = ask(q['question'])
        except Exception as e:
            agent_output = {'sql': '', 'results': None, 'error': f"agent crashed: {e}"}

        scored = score_question(q, agent_output)
        results.append(scored)
        print('✓' if scored['pass'] else '✗')

    # Summary stats
    df = pd.DataFrame(results)
    total = len(df)
    passed = df['pass'].sum()
    accuracy = passed / total

    print(f"\n{'='*60}")
    print(f"Overall accuracy: {passed}/{total} = {accuracy:.1%}")
    print(f"{'='*60}")

    # Breakdown by category
    if 'category' in df.columns:
        print("\nAccuracy by category:")
        category_stats = df.groupby('category')['pass'].agg(['sum', 'count'])
        category_stats['accuracy'] = category_stats['sum'] / category_stats['count']
        for cat, row in category_stats.iterrows():
            print(f"  {cat:<30} {int(row['sum'])}/{int(row['count'])} = {row['accuracy']:.1%}")

    # Save full results with timestamp
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = RESULTS_DIR / f'eval_results_{timestamp}.csv'
    df.to_csv(out_path, index=False)
    print(f"\nFull results saved to: {out_path}")

    # Print failures so you can iterate on them right away
    failures = df[~df['pass']]
    if len(failures) > 0:
        print(f"\n{'─'*60}")
        print(f"FAILURES ({len(failures)}):")
        print('─'*60)
        for _, row in failures.iterrows():
            print(f"\n[{row['id']}] {row['question']}")
            print(f"  SQL generated: {row['generated_sql'][:200]}")
            if row['error']:
                print(f"  Error: {row['error']}")
            if not row['sql_check_pass']:
                print(f"  SQL check failed: {row['sql_check_detail']}")
            if not row['result_check_pass']:
                print(f"  Result check failed: {row['result_check_detail']}")


if __name__ == '__main__':
    main()