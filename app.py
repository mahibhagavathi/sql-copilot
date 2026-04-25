import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, inspect
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
st.write("Connect your data, review the schema, and chat with your database.")

# ─────────────────────────────────────────────
# GEMINI SETUP
# ─────────────────────────────────────────────
def get_model():
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        st.error("❌ Missing GEMINI_API_KEY. Please set it in secrets or environment variables.")
        st.stop()
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-1.5-flash-latest")

# ─────────────────────────────────────────────
# DATABASE ENGINES
# ─────────────────────────────────────────────
def get_engine(connection_type, **kwargs):
    """Factory to create SQLAlchemy engines based on user input."""
    try:
        if connection_type == "SQLite (In-Memory)":
            return create_engine("sqlite:///:memory:")
        
        elif connection_type == "External SQL Database":
            # Expecting a SQLAlchemy URI like: postgresql://user:pass@host:port/dbname
            uri = kwargs.get("uri")
            if not uri:
                st.error("Please provide a valid Connection URI")
                return None
            return create_engine(uri)
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None

# ─────────────────────────────────────────────
# SCHEMA & METADATA
# ─────────────────────────────────────────────
def fetch_schema_info(engine):
    """Uses SQLAlchemy inspection to get tables and columns."""
    schema_dict = {}
    try:
        inspector = inspect(engine)
        for table_name in inspector.get_table_names():
            columns = inspector.get_columns(table_name)
            schema_dict[table_name] = [{"name": c["name"], "type": str(c["type"])} for c in columns]
        return schema_dict
    except Exception as e:
        st.error(f"Error fetching schema: {e}")
        return {}

def schema_to_text(schema_dict):
    """Converts schema dict to a prompt-friendly string."""
    text_parts = []
    for table, cols in schema_dict.items():
        col_str = ", ".join([f"{c['name']} ({c['type']})" for c in cols])
        text_parts.append(f"Table '{table}' has columns: {col_str}")
    return "\n".join(text_parts)

# ─────────────────────────────────────────────
# AI LOGIC
# ─────────────────────────────────────────────
def ask_ai(model, schema_txt, question):
    prompt = f"""
    You are an expert SQL Data Analyst.
    
    Database Schema:
    {schema_txt}

    Task:
    1. Provide a standard SQL SELECT query to answer: "{question}"
    2. Wrap the SQL in ```sql blocks.
    3. Provide a brief explanation of how the query works.
    4. Suggest one interesting business insight the user could look for in this data.

    Constraints:
    - Use standard SQL syntax.
    - If the user asks for something not in the schema, politely explain why.
    """
    response = model.generate_content(prompt)
    return response.text

def extract_sql(text):
    match = re.search(r"```sql(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else None

# ─────────────────────────────────────────────
# SIDEBAR / CONNECTION MANAGEMENT
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("🔌 Data Source")
    
    source_type = st.selectbox("Select Source", 
        ["Demo Dataset", "Upload CSV", "External SQL Database"]
    )

    # Initialize or reset engine
    if "engine" not in st.session_state:
        st.session_state.engine = None
    if "schema" not in st.session_state:
        st.session_state.schema = None

    if source_type == "Demo Dataset":
        if st.button("Load Demo Data"):
            engine = get_engine("SQLite (In-Memory)")
            df = pd.DataFrame({
                "order_id": [1, 2, 3], "amount": [100, 200, 150], "category": ["Tech", "Fashion", "Tech"]
            })
            df.to_sql("sales", engine, index=False)
            st.session_state.engine = engine
            st.session_state.schema = fetch_schema_info(engine)
            st.success("Demo Loaded!")

    elif source_type == "Upload CSV":
        uploaded_files = st.file_uploader("Upload CSVs", type="csv", accept_multiple_files=True)
        if uploaded_files and st.button("Process Files"):
            engine = get_engine("SQLite (In-Memory)")
            for f in uploaded_files:
                table_name = f.name.split('.')[0].replace(" ", "_").lower()
                pd.read_csv(f).to_sql(table_name, engine, index=False)
            st.session_state.engine = engine
            st.session_state.schema = fetch_schema_info(engine)
            st.success(f"Loaded {len(uploaded_files)} tables!")

    elif source_type == "External SQL Database":
        st.info("Format: postgresql://user:pass@host:port/dbname")
        db_uri = st.text_input("Connection URI", type="password")
        if st.button("Connect"):
            engine = get_engine("External SQL Database", uri=db_uri)
            if engine:
                st.session_state.engine = engine
                st.session_state.schema = fetch_schema_info(engine)
                st.success("Connected to External DB!")

# ─────────────────────────────────────────────
# MAIN INTERFACE
# ─────────────────────────────────────────────
if st.session_state.engine:
    # --- SCHEMA VIEWER ---
    with st.expander("🗂️ View Database Schema", expanded=False):
        if st.session_state.schema:
            for table, cols in st.session_state.schema.items():
                st.markdown(f"**Table: `{table}`**")
                st.table(pd.DataFrame(cols))
        else:
            st.warning("No schema detected.")

    # --- CHAT INTERFACE ---
    user_query = st.chat_input("Ask a question about your data...")

    if user_query:
        with st.spinner("Analyzing..."):
            model = get_model()
            schema_txt = schema_to_text(st.session_state.schema)
            ai_response = ask_ai(model, schema_txt, user_query)
            
            st.markdown("### 🤖 AI Analysis")
            st.write(ai_response)

            sql_query = extract_sql(ai_response)
            if sql_query:
                try:
                    results_df = pd.read_sql(sql_query, st.session_state.engine)
                    st.markdown("### 📊 Query Results")
                    st.dataframe(results_df, use_container_width=True)
                except Exception as e:
                    st.error(f"The generated SQL failed to run: {e}")
else:
    st.info("👋 Use the sidebar to connect a database or upload a file to get started.")
