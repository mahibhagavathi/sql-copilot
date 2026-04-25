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
# GEMINI SETUP
# ─────────────────────────────────────────────
def get_model():
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if not api_key:
        st.error("Missing GEMINI_API_KEY")
        st.stop()

    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-1.5-flash-latest")

# ─────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────
def load_csv(files):
    conn = sqlite3.connect(":memory:")
    for f in files:
        df = pd.read_csv(f)
        table = f.name.replace(".csv", "").replace(" ", "_").lower()
        df.to_sql(table, conn, index=False, if_exists="replace")
    return conn


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
# SCHEMA
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
# AI
# ─────────────────────────────────────────────
def extract_sql(text):
    match = re.search(r"```sql(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def ask_ai(model, schema_txt, question):
    prompt = f"""
You are a data analyst.

Schema:
{schema_txt}

Return:
- SQL in ```sql``` block
- Explanation
- Insight

Question:
{question}
"""
    return model.generate_content(prompt).text


def run_sql(conn, sql):
    try:
        return pd.read_sql_query(sql, conn), None
    except Exception as e:
        return None, str(e)

# ─────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────
if "conn" not in st.session_state:
    st.session_state.conn = None

if "schema" not in st.session_state:
    st.session_state.schema = None

if "preview_df" not in st.session_state:
    st.session_state.preview_df = None

# ─────────────────────────────────────────────
# SIDEBAR (ENHANCED UX)
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("🧠 SQL Copilot")

    mode = st.radio("Select Data Source", ["Upload CSV", "Demo Database"])

    # ── DATA LOAD ──
    if mode == "Upload CSV":
        files = st.file_uploader("Upload CSV files", type=["csv"], accept_multiple_files=True)

        if files:
            conn = load_csv(files)
            st.session_state.conn = conn
            st.session_state.schema = get_schema(conn)

            # preview ANY table
            table = list(st.session_state.schema.keys())[0]
            st.session_state.preview_df = pd.read_sql_query(f"SELECT * FROM {table} LIMIT 10", conn)

            st.success("CSV loaded")

    else:
        if st.button("Load Demo Dataset"):
            conn = create_demo_db()
            st.session_state.conn = conn
            st.session_state.schema = get_schema(conn)

            st.session_state.preview_df = pd.read_sql_query("SELECT * FROM sales LIMIT 10", conn)

            st.success("Demo loaded")

    # ── SAMPLE QUESTIONS ──
    st.divider()
    st.subheader("💡 Sample Questions")

    st.write("""
    - Top products by revenue  
    - Revenue by country  
    - Find duplicate users  
    - Average order value  
    - Sales trend over time  
    """)

    # ── DATA PREVIEW (IMPORTANT FEATURE) ──
    st.divider()
    st.subheader("👀 Data Preview")

    if st.session_state.preview_df is not None:
        st.dataframe(st.session_state.preview_df, use_container_width=True)
    else:
        st.info("Load dataset to preview")

    # ── HOW IT WORKS ──
    st.divider()
    st.subheader("ℹ️ How it works")
    st.write("""
    1. Load data  
    2. View schema  
    3. Ask question  
    4. Get SQL + results  
    """)

# ─────────────────────────────────────────────
# MAIN UI
# ─────────────────────────────────────────────
if not st.session_state.conn:
    st.info("👉 Select dataset from sidebar to begin")
    st.stop()

st.subheader("🗂 Schema")

for table, cols in st.session_state.schema.items():
    st.write(f"**{table}**")
    st.write(cols)

# ─────────────────────────────────────────────
# QUERY INPUT
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
