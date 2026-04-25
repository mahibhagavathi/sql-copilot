import streamlit as st
import pandas as pd
import sqlite3
import google.generativeai as genai
import os
import re

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="AI SQL Copilot",
    page_icon="🧠",
    layout="wide"
)

st.title("🧠 AI SQL Copilot")
st.write("Ask questions in plain English → get SQL + results + insights")

# ─────────────────────────────────────────────
# GEMINI SETUP (FIXED MODEL)
# ─────────────────────────────────────────────
def get_model():
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if not api_key:
        st.error("❌ Missing GEMINI_API_KEY")
        st.stop()

    genai.configure(api_key=api_key)

    # FIXED MODEL (this is the correct one)
    return genai.GenerativeModel("gemini-1.5-flash-latest")

# ─────────────────────────────────────────────
# LOAD CSV → SQLITE
# ─────────────────────────────────────────────
def load_csv(files):
    conn = sqlite3.connect(":memory:")

    for f in files:
        df = pd.read_csv(f)
        table = f.name.replace(".csv", "").replace(" ", "_").lower()
        df.to_sql(table, conn, index=False, if_exists="replace")

    return conn

# ─────────────────────────────────────────────
# DEMO DATABASE (REALISTIC)
# ─────────────────────────────────────────────
def create_demo_db():
    df = pd.DataFrame({
        "order_id": range(1, 21),
        "user_id": [101, 102, 103, 104, 105] * 4,
        "product": ["Laptop", "Phone", "Shoes", "Watch", "Headphones"] * 4,
        "category": ["Electronics", "Electronics", "Fashion", "Accessories", "Electronics"] * 4,
        "amount": [1200, 800, 120, 250, 150] * 4,
        "country": ["IN", "US", "UK", "IN", "US"] * 4,
        "date": pd.date_range("2024-01-01", periods=20)
    })

    conn = sqlite3.connect(":memory:")
    df.to_sql("sales", conn, index=False, if_exists="replace")
    return conn

# ─────────────────────────────────────────────
# SCHEMA HELPERS
# ─────────────────────────────────────────────
def get_schema(conn):
    schema = {}
    cursor = conn.cursor()

    tables = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table';"
    ).fetchall()

    for (t,) in tables:
        cols = cursor.execute(f"PRAGMA table_info({t})").fetchall()
        schema[t] = [(c[1], c[2]) for c in cols]

    return schema


def schema_text(schema):
    out = []
    for t, cols in schema.items():
        col_str = ", ".join([f"{c[0]} ({c[1]})" for c in cols])
        out.append(f"{t}: {col_str}")
    return "\n".join(out)

# ─────────────────────────────────────────────
# AI SQL GENERATION
# ─────────────────────────────────────────────
def extract_sql(text):
    match = re.search(r"```sql(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def ask_ai(model, schema_txt, question):
    prompt = f"""
You are a senior data analyst.

You convert English → SQL.

Schema:
{schema_txt}

Rules:
- Return ONLY SQL inside ```sql``` block
- Only SELECT queries
- Then explain in simple English
- Then give 1 insight

Question:
{question}
"""
    return model.generate_content(prompt).text


def run_sql(conn, sql):
    try:
        df = pd.read_sql_query(sql, conn)
        return df, None
    except Exception as e:
        return None, str(e)

# ─────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────
if "conn" not in st.session_state:
    st.session_state.conn = None

if "schema" not in st.session_state:
    st.session_state.schema = None

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("🧠 SQL Copilot")

    st.write("Convert English → SQL instantly")

    mode = st.radio("Choose Data Source", ["Upload CSV", "Demo Database"])

    if mode == "Upload CSV":
        files = st.file_uploader("Upload CSV files", type=["csv"], accept_multiple_files=True)

        if files:
            st.session_state.conn = load_csv(files)
            st.session_state.schema = get_schema(st.session_state.conn)
            st.success("CSV loaded")

    else:
        if st.button("Load Demo Dataset"):
            st.session_state.conn = create_demo_db()
            st.session_state.schema = get_schema(st.session_state.conn)
            st.success("Demo loaded")

    st.divider()

    st.subheader("How it works")
    st.write("""
    1. Load dataset  
    2. View schema  
    3. Ask question  
    4. Get SQL + results  
    """)

    st.subheader("Example queries")
    st.write("""
    - Top products by revenue  
    - Revenue by country  
    - Find duplicates  
    """)

# ─────────────────────────────────────────────
# MAIN UI
# ─────────────────────────────────────────────
if not st.session_state.conn:
    st.info("👉 Select dataset from sidebar to start")
    st.stop()

st.subheader("🗂 Schema")

for table, cols in st.session_state.schema.items():
    st.write(f"**{table}**")
    st.write(cols)

# ─────────────────────────────────────────────
# USER INPUT
# ─────────────────────────────────────────────
question = st.text_input("💬 Ask your data anything")

# ─────────────────────────────────────────────
# EXECUTION
# ─────────────────────────────────────────────
if question:

    model = get_model()
    schema_txt = schema_text(st.session_state.schema)

    response = ask_ai(model, schema_txt, question)

    sql = extract_sql(response)

    st.subheader("🧠 AI Response")
    st.write(response)

    if sql:
        st.subheader("⚡ SQL Query")
        st.code(sql, language="sql")

        df, err = run_sql(st.session_state.conn, sql)

        if err:
            st.error(err)
        else:
            st.subheader("📊 Results")
            st.dataframe(df, use_container_width=True)
