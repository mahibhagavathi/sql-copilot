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
st.write("Ask questions in English → get SQL + insights instantly")

# ─────────────────────────────────────────────
# GEMINI
# ─────────────────────────────────────────────
def get_model():
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-1.5-flash-latest")

# ─────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────
def load_csv(files):
    conn = sqlite3.connect(":memory:")
    for f in files:
        df = pd.read_csv(f)
        table = f.name.replace(".csv", "").replace(" ", "_")
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
You are a senior data analyst.

Schema:
{schema_txt}

Return:
SQL in ```sql``` block + explanation + insight

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

if "preview" not in st.session_state:
    st.session_state.preview = None

# ─────────────────────────────────────────────
# 1. HOW IT WORKS (TOP SECTION)
# ─────────────────────────────────────────────
st.subheader("📌 How it works")

st.info("""
1️⃣ Upload or select dataset  
2️⃣ Preview data  
3️⃣ Ask questions in English  
4️⃣ Get SQL + results + insights  
""")

st.divider()

# ─────────────────────────────────────────────
# 2. DATA SOURCE
# ─────────────────────────────────────────────
st.subheader("📂 Step 1: Load Data")

mode = st.radio("Choose data source", ["Upload CSV", "Demo Database"])

if mode == "Upload CSV":
    files = st.file_uploader("Upload CSV files", type=["csv"], accept_multiple_files=True)

    if files:
        conn = load_csv(files)
        st.session_state.conn = conn
        st.session_state.schema = get_schema(conn)

        table = list(st.session_state.schema.keys())[0]
        st.session_state.preview = pd.read_sql_query(f"SELECT * FROM {table} LIMIT 10", conn)

        st.success("Dataset loaded")

else:
    if st.button("Load Demo Dataset"):
        conn = create_demo_db()
        st.session_state.conn = conn
        st.session_state.schema = get_schema(conn)
        st.session_state.preview = pd.read_sql_query("SELECT * FROM sales LIMIT 10", conn)

        st.success("Demo loaded")

# ─────────────────────────────────────────────
# STOP IF NO DATA
# ─────────────────────────────────────────────
if not st.session_state.conn:
    st.stop()

# ─────────────────────────────────────────────
# 3. PREVIEW DATA
# ─────────────────────────────────────────────
st.subheader("👀 Step 2: Data Preview")

st.dataframe(st.session_state.preview, use_container_width=True)

# ─────────────────────────────────────────────
# 4. SAMPLE QUESTIONS
# ─────────────────────────────────────────────
st.subheader("💡 Step 3: Sample Questions")

st.write("""
- Top products by revenue  
- Revenue by country  
- Average order value  
- Find duplicates  
- Monthly trends  
""")

# ─────────────────────────────────────────────
# 5. SCHEMA
# ─────────────────────────────────────────────
st.subheader("🗂 Schema")

for table, cols in st.session_state.schema.items():
    st.write(f"**{table}**")
    st.write(cols)

# ─────────────────────────────────────────────
# 6. QUERY INPUT
# ─────────────────────────────────────────────
st.subheader("💬 Step 4: Ask Question")

question = st.text_input("Ask your data anything")

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
