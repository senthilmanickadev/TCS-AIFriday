import os
import ssl
# ====================== GLOBAL SSL FIX FOR TIKTOKEN (Corporate Proxy) ======================
ssl._create_default_https_context = ssl._create_unverified_context
os.environ["TIKTOKEN_CACHE_DIR"] = "./tiktoken_cache"
os.makedirs(os.environ["TIKTOKEN_CACHE_DIR"], exist_ok=True)

import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from datetime import date, datetime
import httpx
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.document_loaders import CSVLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_community.vectorstores import FAISS

st.set_page_config(page_title="Production Workflow AI", layout="wide", page_icon="🏭")

# ====================== TCS GENAI CONFIG ======================
http_client = httpx.Client(verify=False)

llm = ChatOpenAI(
    base_url="https://genailab.tcs.in",
    model="azure/genailab-maas-gpt-4.1",
    api_key="sk-YRkajdp0I7rcy9ggSXuDuA",
    http_client=http_client,
    temperature=0.7,
)

embedding_model = OpenAIEmbeddings(
    base_url="https://genailab.tcs.in",
    model="text-embedding-large3",
    api_key="sk-YRkajdp0I7rcy9ggSXuDuA",
    http_client=http_client,
)

# ====================== DATABASE ======================
def init_db():
    conn = sqlite3.connect("production.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS production (
                    id INTEGER PRIMARY KEY,
                    date TEXT,
                    shift TEXT,
                    output_qty INTEGER,
                    defect_rate REAL,
                    downtime_hours REAL,
                    notes TEXT)''')
    
    if c.execute("SELECT COUNT(*) FROM production").fetchone()[0] == 0:
        sample_data = [
            ("2026-04-01", "Morning", 1250, 3.2, 1.5, "New machine calibration"),
            ("2026-04-02", "Morning", 1180, 4.1, 2.0, ""),
            ("2026-04-03", "Evening", 1320, 2.8, 0.8, "High efficiency day"),
            ("2026-04-04", "Morning", 1400, 1.9, 0.5, "Best day this month"),
            ("2026-04-05", "Morning", 1290, 3.5, 1.2, ""),
        ]
        c.executemany("INSERT INTO production VALUES (NULL,?,?,?,?,?,?)", sample_data)
    
    c.execute('''CREATE TABLE IF NOT EXISTS justifications (
                    production_id INTEGER PRIMARY KEY,
                    eng_justification TEXT,
                    qa_justification TEXT,
                    eng_approved INTEGER DEFAULT 0,
                    qa_approved INTEGER DEFAULT 0,
                    eng_approved_by TEXT,
                    qa_approved_by TEXT,
                    generated_at TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_data():
    conn = sqlite3.connect("production.db")
    df = pd.read_sql("SELECT * FROM production ORDER BY date DESC", conn)
    conn.close()
    return df

def get_justification(production_id):
    conn = sqlite3.connect("production.db")
    c = conn.cursor()
    c.execute("SELECT * FROM justifications WHERE production_id = ?", (production_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "eng_justification": row[1], "qa_justification": row[2],
            "eng_approved": bool(row[3]), "qa_approved": bool(row[4]),
            "eng_approved_by": row[5], "qa_approved_by": row[6],
            "generated_at": row[7]
        }
    return None

def save_justification(production_id, eng_text, qa_text):
    conn = sqlite3.connect("production.db")
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""INSERT OR REPLACE INTO justifications 
                 (production_id, eng_justification, qa_justification, generated_at)
                 VALUES (?,?,?,?)""", (production_id, eng_text, qa_text, now))
    conn.commit()
    conn.close()

def approve_justification(production_id, dept, username):
    conn = sqlite3.connect("production.db")
    c = conn.cursor()
    if dept == "engineering":
        c.execute("UPDATE justifications SET eng_approved=1, eng_approved_by=? WHERE production_id=?", (username, production_id))
    elif dept == "quality_assurance":
        c.execute("UPDATE justifications SET qa_approved=1, qa_approved_by=? WHERE production_id=?", (username, production_id))
    conn.commit()
    conn.close()

# ====================== RAG (Moved inside page - no longer runs at startup) ======================
@st.cache_resource
def get_vectorstore():
    index_path = "faiss_index"
    if os.path.exists(index_path):
        try:
            return FAISS.load_local(index_path, embedding_model, allow_dangerous_deserialization=True)
        except:
            pass
    if not os.path.exists("output.csv"):
        return None
    try:
        loader = CSVLoader(file_path="output.csv", encoding="utf-8")
        documents = loader.load()
        text_splitter = CharacterTextSplitter(chunk_size=1200, chunk_overlap=100)
        docs = text_splitter.split_documents(documents)
        vectorstore = FAISS.from_documents(docs, embedding_model)
        vectorstore.save_local(index_path)
        return vectorstore
    except Exception as e:
        st.error(f"RAG Error: {e}")
        return None

# ====================== AUTHENTICATION - MOST SAFE VERSION ======================
with open("credentials.yaml", "r", encoding="utf-8") as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# This is the safest way to call login()
login_result = authenticator.login()

if login_result is None:
    st.stop()                    # This stops the script while showing the login form

name, authentication_status, username = login_result

if not authentication_status:
    st.stop()

# ====================== AFTER SUCCESSFUL LOGIN ======================
st.success(f"✅ Login Successful! Welcome **{name}**")
user_role = config['credentials']['usernames'][username]['role']
st.info(f"Role: **{user_role}**")

can_edit = user_role in ["production", "engineering", "quality_assurance"]
can_approve_eng = (user_role == "engineering")
can_approve_qa = (user_role == "quality_assurance")

authenticator.logout("Logout", "sidebar")

# ====================== SIDEBAR ======================
st.sidebar.title("🔄 Production Workflow Tool")
page = st.sidebar.radio("Workflow Steps", 
    ["📊 Dashboard", "📝 Data Entry", "🤖 AI Justification & Approval"])

# ====================== PAGES ======================
if page == "📊 Dashboard":
    st.title("🏭 Production Quality Dashboard")
    df = get_data()
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Avg Output", f"{df['output_qty'].mean():.0f}" if len(df)>0 else 0)
    with col2: st.metric("Avg Defect Rate", f"{df['defect_rate'].mean():.1f}%" if len(df)>0 else 0)
    with col3: st.metric("Total Downtime", f"{df['downtime_hours'].sum():.1f} hrs" if len(df)>0 else 0)
    with col4: st.metric("Records", len(df))

    col1, col2 = st.columns(2)
    with col1: st.plotly_chart(px.line(df, x='date', y='output_qty', title="Output Trend", markers=True), use_container_width=True)
    with col2: st.plotly_chart(px.bar(df, x='date', y='defect_rate', title="Defect Rate Trend", color='shift'), use_container_width=True)

elif page == "📝 Data Entry" and can_edit:
    st.title("📝 Log New Production Record")
    with st.form("entry_form"):
        col1, col2 = st.columns(2)
        with col1:
            entry_date = st.date_input("Date", date.today())
            shift = st.selectbox("Shift", ["Morning", "Evening", "Night"])
        with col2:
            output = st.number_input("Output Quantity", 0, 10000, 1200)
            defect = st.number_input("Defect Rate (%)", 0.0, 100.0, 2.5)
        downtime = st.number_input("Downtime (hours)", 0.0, 24.0, 1.0)
        notes = st.text_area("Notes")
        if st.form_submit_button("💾 Save Record"):
            conn = sqlite3.connect("production.db")
            conn.execute("INSERT INTO production VALUES (NULL,?,?,?,?,?,?)",
                         (str(entry_date), shift, output, defect, downtime, notes))
            conn.commit()
            conn.close()
            st.success("✅ Record saved!")
            st.rerun()

elif page == "🤖 AI Justification & Approval":
    st.title("🤖 AI Justification & Approval Workflow")
    vectorstore = get_vectorstore()   # ← RAG only loads when you open this page

    df = get_data()
    if len(df) == 0:
        st.warning("No records yet.")
        st.stop()

    current_idx = st.selectbox("Select record", df.index,
        format_func=lambda i: f"#{df.loc[i,'id']} | {df.loc[i,'date']} ({df.loc[i,'shift']}) — {df.loc[i,'output_qty']} units")
    
    current = df.loc[current_idx]
    production_id = int(current['id'])
    current_str = f"Date={current['date']}, Shift={current['shift']}, Output={current['output_qty']}, Defect={current['defect_rate']}%, Downtime={current['downtime_hours']}hrs"

    just = get_justification(production_id)

    if st.button("🚀 Generate AI Justifications", type="primary"):
        with st.spinner("Fetching historical context + calling TCS GenAI..."):
            context = ""
            if vectorstore:
                retriever = vectorstore.as_retriever(search_kwargs={"k": 6})
                retrieved = retriever.invoke(current_str)
                context = "\n\n".join([doc.page_content for doc in retrieved])

            eng_prompt = f"You are a senior Engineering analyst.\nCurrent record: {current_str}\nHistorical data:\n{context if context else 'No historical data'}\nGive concise engineering justification."
            qa_prompt = f"You are a senior Quality Assurance analyst.\nCurrent record: {current_str}\nHistorical data:\n{context if context else 'No historical data'}\nGive concise quality justification."

            eng_response = llm.invoke(eng_prompt).content
            qa_response = llm.invoke(qa_prompt).content

            save_justification(production_id, eng_response, qa_response)
            st.success("✅ Justifications generated!")
            st.rerun()

    if just:
        st.divider()
        st.subheader("🛠️ Engineering Justification")
        st.info(just["eng_justification"])
        if just["eng_approved"]:
            st.success(f"✅ Approved by {just['eng_approved_by']}")
        elif can_approve_eng and st.button("✅ Approve Engineering"):
            approve_justification(production_id, "engineering", name)
            st.rerun()

        st.divider()
        st.subheader("✅ Quality Assurance Justification")
        st.info(just["qa_justification"])
        if just["qa_approved"]:
            st.success(f"✅ Approved by {just['qa_approved_by']}")
        elif can_approve_qa and st.button("✅ Approve QA"):
            approve_justification(production_id, "quality_assurance", name)
            st.rerun()

st.sidebar.caption("Production Workflow Tool v2.2")
