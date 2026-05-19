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

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agent import ask  # noqa: E402


EXAMPLE_QUESTIONS = [
    "How many loans were denied vs approved?",
    "Top 5 counties by total application count?",
    "Compare the average loan amount for Manhattan vs Staten Island",
]


st.set_page_config(
    page_title="HMDA Text-to-SQL",
    page_icon="🏠",
    layout="wide",
)


# Sidebar
with st.sidebar:
    st.header("About")
    st.markdown(
        "Ask plain-English questions about **2025 New York State** mortgage "
        "applications. The agent converts your question to SQL using Claude, "
        "runs it against a DuckDB database, and shows the result."
    )
    st.markdown("---")
    st.markdown("**Data source:** [CFPB HMDA Data Browser](https://ffiec.cfpb.gov/data-browser/)")
    st.markdown("**Built with:** Claude · DuckDB · Streamlit")

    with st.expander("Limitations"):
        st.markdown(
            "- New York State only\n"
            "- 2025 records only (~430k applications)\n"
            "- The agent can make mistakes — always check the generated SQL"
        )


# Main
st.title("Text-to-SQL: NY Mortgage Data")
st.caption("Ask a question about 2025 HMDA mortgage applications in New York State.")

# Example chips
st.markdown("**Try an example:**")
cols = st.columns(len(EXAMPLE_QUESTIONS))
for col, example in zip(cols, EXAMPLE_QUESTIONS):
    if col.button(example, use_container_width=True):
        st.session_state["question"] = example

question = st.text_input(
    "Your question",
    key="question",
    placeholder="e.g. What is the average loan amount by loan purpose?",
)

submitted = st.button("Ask", type="primary")

if submitted and question.strip():
    with st.spinner("Generating SQL and running query..."):
        try:
            result = ask(question)
        except Exception as e:
            st.error(f"Agent crashed: {e}")
            st.stop()

    if result.get("explanation"):
        st.info(result["explanation"])

    with st.expander("Generated SQL", expanded=False):
        st.code(result["sql"], language="sql")

    if result["error"]:
        st.error(f"Query failed: {result['error']}")
    elif result["results"] is None or result["results"].empty:
        st.warning("Query ran successfully but returned no rows.")
    else:
        st.dataframe(result["results"], use_container_width=True)
        st.caption(f"{len(result['results'])} row(s)")

elif submitted:
    st.warning("Please enter a question.")
