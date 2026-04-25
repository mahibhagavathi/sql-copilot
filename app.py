import streamlit as st
import pandas as pd
import sqlite3
import google.generativeai as genai
import json
import re
import os

# ── Page config ─────────────────────────────────────────────
st.set_page_config(
    page_title="AI SQL Copilot",
    page_icon="🧠",
    layout="wide",
)

# ── Gemini setup ─────────────────────────────────────────────
def get_gemini_model():
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        st.error("❌ Missing GEMINI_API_KEY in secrets or environment")
        st.stop()

    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-1.5-flash")


# ── Load CSV into SQLite ─────────────────────────────────────
def load_csv_to_sqlite(uploaded_files):
    conn = sqlite3.connect(":memory:")

    for f in uploaded_files:
        df = pd.read_csv(f)
        table_name = os.path.splitext(f.name)[0].replace(" ", "_").lower()
        df.to_sql(table_name, conn, if_exists="replace", index=False)

    return conn


# ── Get schema ───────────────────────────────────────────────
def get_schema(conn):
    schema = {}
    cursor = conn.cursor()

    tables = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table';"
    ).fetchall()

    for (table,) in tables:
        cols = cursor.execute(f"PRAGMA table_info({table})").fetchall()
        schema[table] = [(c[1], c[2]) for c in cols]

    return schema


def schema_to_text(schema):
    text = []
    for table, cols in schema.items():
        col_text = ", ".join([f"{c[0]} ({c[1]})" for c in cols])
        text.append(f"{table}: {col_text}")
    return "\n".join(text)


# ── Extract SQL from AI response ─────────────────────────────
def extract_sql(text):
    match = re.search(r"```sql(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    match = re.search(r"(SELECT[\s\S]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return ""


# ── Run SQL ───────────────────────────────────────────────────
def run_query(conn, sql):
    try:
        df = pd.read_sql_query(sql, conn)
        return df, None
    except Exception as e:
        return None, str(e)


# ── Gemini prompt ────────────────────────────────────────────
def ask_gemini(model, schema_text, question, error=None):
    prompt = f"""
You are an expert data analyst.

You are working with a SQLite database.

Schema:
{schema_text}

Rules:
- Always return a SQL query inside ```sql ``` block
- Only use SELECT queries
- Then explain the query in simple English
- Then add INSIGHT section with business insights
- If error exists, fix it

User question:
{question}

Error (if any):
{error}
"""

    response = model.generate_content(prompt)
    return response.text


# ── App state ────────────────────────────────────────────────
if "conn" not in st.session_state:
    st.session_state.conn = None

if "schema" not in st.session_state:
    st.session_state.schema = None

if "history" not in st.session_state:
    st.session_state.history = []


# ── UI ───────────────────────────────────────────────────────
st.title("🧠 AI SQL Copilot (Gemini Powered)")

mode = st.radio("Select data source", ["Upload CSV", "Demo DB"])

# ── CSV MODE ────────────────────────────────────────────────
if mode == "Upload CSV":
    files = st.file_uploader("Upload CSV files", type=["csv"], accept_multiple_files=True)

    if files:
        st.session_state.conn = load_csv_to_sqlite(files)
        st.session_state.schema = get_schema(st.session_state.conn)
        st.success("Data loaded successfully!")

# ── DEMO MODE ───────────────────────────────────────────────
else:
    if st.button("Load Sample Data"):
        df = pd.DataFrame({
            "user": ["A", "B", "C", "A"],
            "sales": [100, 200, 300, 100],
            "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-01"]
        })

        conn = sqlite3.connect(":memory:")
        df.to_sql("sales", conn, index=False, if_exists="replace")

        st.session_state.conn = conn
        st.session_state.schema = get_schema(conn)

        st.success("Sample DB loaded!")

# ── If no data ───────────────────────────────────────────────
if not st.session_state.conn:
    st.info("Upload CSV or load demo to start")
    st.stop()

# ── Show schema ──────────────────────────────────────────────
st.subheader("📊 Schema")

for table, cols in st.session_state.schema.items():
    st.write(f"**{table}**")
    st.write(cols)

# ── Chat input ───────────────────────────────────────────────
question = st.text_input("Ask your data anything:")

if question:
    model = get_gemini_model()

    schema_text = schema_to_text(st.session_state.schema)

    response = ask_gemini(model, schema_text, question)

    sql = extract_sql(response)

    st.subheader("🧠 AI Response")
    st.write(response)

    if sql:
        st.subheader("⚡ Executed SQL")
        st.code(sql, language="sql")

        df, err = run_query(st.session_state.conn, sql)

        if err:
            st.error(err)
        else:
            st.subheader("📊 Result")
            st.dataframe(df)

    st.session_state.history.append({
        "q": question,
        "r": response
    })
