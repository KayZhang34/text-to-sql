"""Streamlit app for the text-to-SQL HMDA agent."""

import os
import sys
from pathlib import Path

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

# List of example questions to show as buttons above the input box.
EXAMPLE_QUESTIONS = [
    "What is the average loan amount by loan purpose?",
    "Top 5 counties by total application count?",
    "Compare the average loan amount for Manhattan vs Staten Island",
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
        st.dataframe(result["results"], width='stretch')
        st.caption(f"{len(result['results'])} row(s)")

# If the user submitted the form without entering a question, shows this warning.
elif submitted:
    st.warning("Please enter a question.")
