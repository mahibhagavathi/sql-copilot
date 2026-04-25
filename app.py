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
    page_title="QueryMeThis 🧠",
    page_icon="🧠",
    layout="wide"
)

# ─────────────────────────────────────────────
# SAAS UI (FIXED LIGHT THEME)
# ─────────────────────────────────────────────
st.markdown("""
<style>

.main {
    background-color: #f8fafc;
    color: #111827;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #111827;
    color: white;
}

/* Cards */
.card {
    background: white;
    padding: 16px;
    border-radius: 12px;
    border: 1px solid #e5e7eb;
    margin-bottom: 12px;
    box-shadow: 0px 1px 4px rgba(0,0,0,0.05);
}

/* SQL block */
.sql-block {
    background: #0b1220;
    color: #38bdf8;
    padding: 12px;
    border-radius: 10px;
    font-family: monospace;
    border: 1px solid #1e3a8a;
    overflow-x: auto;
}

/* Insight box */
.insight-box {
    background: #ecfdf5;
    border-left: 4px solid #22c55e;
    padding: 12px;
    border-radius: 8px;
    color: #065f46;
}

/* Inputs */
.stTextInput input {
    border-radius: 10px;
    border: 1px solid #d1d5db;
    padding: 10px;
    color: #111827;
    background: white;
}

/* Buttons */
.stButton button {
    background-color: #2563eb;
    color: white;
    border-radius: 8px;
    font-weight: 600;
}

</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# GEMINI SETUP
# ─────────────────────────────────────────────
def get_model():
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        st.error("❌ Missing GEMINI_API_KEY")
        st.stop()

    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-1.5-flash")

# ─────────────────────────────────────────────
# LOAD CSV → SQLITE
# ─────────────────────────────────────────────
def load_csv(files):
    conn = sqlite3.connect(":memory:")

    for f in files:
        df = pd.read_csv(f)
        table = f.name.replace(".csv", "").replace(" ", "_")
        df.to_sql(table, conn, index=False, if_exists="replace")

    return conn

# ─────────────────────────────────────────────
# DEMO DATABASE (IMPROVED)
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

Schema:
{schema_txt}

Rules:
- Return SQL in ```sql``` block
- Only SELECT queries
- Then explain in simple English
- Then give insights

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

# ─────────────────────────────────────────────
# SIDEBAR (SAAS ONBOARDING)
# ─────────────────────────────────────────────
with st.sidebar:

    st.title("🧠 QueryMeThis")

    st.markdown("""
    <div class="card">
    <h4>📌 What is this?</h4>
    Ask questions in English → get SQL + insights instantly.
    </div>
    """, unsafe_allow_html=True)

    st.subheader("📂 Data Source")

    mode = st.radio("Choose", ["Upload CSV", "Demo Database"])

    if mode == "Upload CSV":
        files = st.file_uploader("Upload CSV", type=["csv"], accept_multiple_files=True)

        if files:
            st.session_state.conn = load_csv(files)
            st.session_state.schema = get_schema(st.session_state.conn)
            st.success("CSV loaded!")

    else:
        if st.button("Load Demo Dataset"):
            st.session_state.conn = create_demo_db()
            st.session_state.schema = get_schema(st.session_state.conn)
            st.success("Demo loaded!")

    # ── Instructions (IMPORTANT UX ADDITION)
    st.markdown("---")

    st.markdown("""
    <div class="card">
    <h4>🚀 How to use</h4>
    <ol>
        <li>Select data source</li>
        <li>Check schema</li>
        <li>Ask questions in English</li>
        <li>Get SQL + results + insights</li>
    </ol>

    <h4>💡 Try asking</h4>
    <ul>
        <li>Top products by revenue</li>
        <li>Revenue by country</li>
        <li>Find duplicate users</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# MAIN UI
# ─────────────────────────────────────────────
st.title("📊 AI SQL Copilot")

if not st.session_state.conn:
    st.markdown("""
    <div class="card">
    👈 Start by selecting a dataset from sidebar
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── SCHEMA DISPLAY (FIXED)
st.subheader("🗂 Schema")

for table, cols in st.session_state.schema.items():
    st.markdown(f"""
    <div class="card">
        <b>📌 {table}</b><br><br>
        {"<br>".join([f"• {c[0]} <span style='color:gray'>({c[1]})</span>" for c in cols])}
    </div>
    """, unsafe_allow_html=True)

# ── INPUT
question = st.text_input("💬 Ask your data anything")

# ─────────────────────────────────────────────
# EXECUTION FLOW
# ─────────────────────────────────────────────
if question:

    model = get_model()
    schema_txt = schema_text(st.session_state.schema)

    response = ask_ai(model, schema_txt, question)

    sql = extract_sql(response)

    st.markdown("### 🧠 AI Response")
    st.write(response)

    if sql:
        st.markdown("### ⚡ SQL Query")
        st.markdown(f'<div class="sql-block">{sql}</div>', unsafe_allow_html=True)

        df, err = run_sql(st.session_state.conn, sql)

        if err:
            st.error(err)
        else:
            st.markdown("### 📊 Results")
            st.dataframe(df, use_container_width=True)
