"""Streamlit app for the text-to-SQL HMDA agent."""

import os
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

# On Streamlit Cloud, the API key lives in st.secrets. Locally, it's in .env
# (loaded by agent.py via load_dotenv). Accessing st.secrets when no
# secrets.toml exists raises, so swallow that case quietly.
try:
    if "ANTHROPIC_API_KEY" in st.secrets:
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    pass

# Add src/ to path so we can import agent.py without needing to install the package. May change in the future.
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agent import ask  # noqa: E402


def pick_chart(df):
    """Return (chart_type, kwargs) or None based on DataFrame shape.

    Heuristics:
      - 1x1 result → "metric" (single big number)
      - 1 row with up to 4 columns → "metric_row" (side-by-side metrics)
      - Multi-row with a string col + numeric col, ≤20 rows → "bar"
      - Otherwise → None (just show the table)
    """
    if df.empty:
        return None

    n_rows, n_cols = df.shape

    if n_rows == 1 and n_cols == 1:
        return ("metric", {"label": df.columns[0], "value": df.iloc[0, 0]})

    if n_rows == 1 and n_cols <= 4:
        return ("metric_row", {})

    # Treat anything non-numeric as categorical — this handles object,
    # "string", pyarrow strings, pandas 3.0's "str" dtype, etc.
    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    cat_cols = [c for c in df.columns if c not in num_cols]
    if cat_cols and num_cols and n_rows <= 20:
        return ("bar", {"x": cat_cols[0], "y": num_cols[0]})

    return None


def _fmt(val):
    """Format a value for display in st.metric — comma-separate numbers."""
    if isinstance(val, (int, float)):
        return f"{val:,}"
    return str(val)


# List of example questions to show as buttons above the input box.
EXAMPLE_QUESTIONS = [
    "How many loans with no co-applicant?",
    "Top 5 counties by total application count?",
    "Compare the average loan amount for Queens vs Brooklyn",
]


st.set_page_config(
    page_title="Text-to-SQL for NY State Mortgage Data",
    page_icon="🏠",
    layout="wide",
)


# Sidebar
with st.sidebar:
    st.header("About")
    st.markdown(
        "Ask plain-English questions about **2025 New York State** mortgage "
        "applications. The agent converts your question to SQL using Claude, "
        "runs it against a DuckDB database, and outputs the result."
    )
    st.markdown("---")
    st.markdown("**Data source:** [CFPB HMDA Data Browser](https://ffiec.cfpb.gov/data-browser/)")
    st.markdown("**Built with:** Claude · DuckDB · Streamlit")

    with st.expander("Limitations"):
        st.markdown(
            "- The agent can make mistakes — always check and validate the generated SQL\n"
            "- New York State only\n"
            "- 2025 records only (~430k applications)"
        )


# Main
st.title("Text-to-SQL: NY Mortgage Data")
st.caption("Ask any question about the New York State 2025 HMDA mortgage application dataset.")

# Example chips
st.markdown("**Try an example question:**")
cols = st.columns(len(EXAMPLE_QUESTIONS))
for col, example in zip(cols, EXAMPLE_QUESTIONS):
    if col.button(example, width='stretch'):
        st.session_state["question"] = example

# Question input form
with st.form("question_form"):
    question = st.text_input(
        "Your question",
        key="question",
        placeholder="e.g. What is the average loan amount by loan purpose?",
    )
    submitted = st.form_submit_button("Ask", type="primary")

# Handle question submission
if submitted and question.strip():
    with st.spinner("Generating SQL and running query..."):
        try:
            result = ask(question)
        except Exception as e:
            st.error(f"Agent crashed: {e}")
            st.stop()

    # Show the agent's explanation, if it provided one. Returns None if not available.
    if result.get("explanation"):
        st.info(result["explanation"])

    # Show the generated SQL in an expander.
    with st.expander("Generated SQL", expanded=False):
        st.code(result["sql"], language="sql")

    if result["error"]:
        st.error(f"Query failed: {result['error']}")
    elif result["results"] is None or result["results"].empty:
        st.warning("Query ran successfully but returned no rows.")
    else:
        df = result["results"]

        # Try to auto-generate a chart based on the result shape
        chart = pick_chart(df)
        if chart:
            chart_type, kwargs = chart
            if chart_type == "metric":
                st.metric(kwargs["label"], _fmt(kwargs["value"]))
            elif chart_type == "metric_row":
                cols = st.columns(len(df.columns))
                for col, name in zip(cols, df.columns):
                    col.metric(name, _fmt(df.iloc[0][name]))
            elif chart_type == "bar":
                bar = (
                    alt.Chart(df)
                    .mark_bar(color="#2e74c0")
                    .encode(
                        x=alt.X(
                            kwargs["x"],
                            sort="-y",  # bars ordered by value descending
                            axis=alt.Axis(
                                labelFontSize=14,
                                labelFontWeight="bold",
                                titleFontSize=14,
                                labelAngle=-30,  # rotate so long county names don't overlap
                            ),
                        ),
                        y=alt.Y(
                            kwargs["y"],
                            axis=alt.Axis(labelFontSize=12, titleFontSize=14),
                        ),
                    )
                    .properties(height=400)
                )
                st.altair_chart(bar, width='stretch')

        # Always show the underlying table — collapsed if we drew a chart,
        # expanded if we didn't so the user still sees the data.
        with st.expander("Show data table", expanded=(chart is None)):
            st.dataframe(df, width='stretch')
            st.caption(f"{len(df)} row(s)")

# If the user submitted the form without entering a question, shows this warning.
elif submitted:
    st.warning("Please enter a question.")
