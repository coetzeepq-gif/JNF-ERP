import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. DATABASE ENGINE (FORCED REFRESH) ---
def get_connection():
    return sqlite3.connect('jnf_elect_master_v13.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    c.execute('CREATE TABLE IF NOT EXISTS baselines (id INTEGER PRIMARY KEY, project_id INTEGER, type_name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS baseline_items (id INTEGER PRIMARY KEY, b_id INTEGER, item TEXT, qty REAL, uom TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS site_units 
                 (id INTEGER PRIMARY KEY, project_id INTEGER, unit_no TEXT, baseline_id INTEGER, 
                  f_fix INT DEFAULT 0, wire INT DEFAULT 0, s_fix INT DEFAULT 0, test INT DEFAULT 0)''')
    c.execute('CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, item TEXT UNIQUE, available REAL, price REAL, uom TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- 2. LAYOUT ---
st.set_page_config(page_title="JNF Elect ERP", layout="wide")
st.sidebar.title("⚡ JNF COMMAND")
menu = ["📊 Dashboard", "🏗️ Project Site Manager", "📦 Stores Control"]
choice = st.sidebar.radio("Navigation", menu)

# --- 3. PROJECT SITE MANAGER (FIXED BASELINE ADDITION) ---
if choice == "🏗️ Project Site Manager":
    st.header("Site Operations")
    conn = get_connection()
    
    # PROJECT CREATION
    p_name = st.text_input("New Project Name")
    if st.button("Launch Project"):
        if p_name:
            conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (p_name,))
            conn.commit()
            st.rerun()

    st.divider()
    projects = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    
    for _, p in projects.iterrows():
        with st.expander(f"📂 PROJECT: {p['name']}", expanded=True):
            tab1, tab2 = st.tabs(["Design Templates", "Unit Tracking"])
            
            # --- TAB 1: DESIGN TEMPLATES (FIXED) ---
            with tab1:
                st.subheader("Add Design Template")
                b_name_input = st.text_input("Template Name (e.g. House E)", key=f"bn_{p['id']}")
                if st.button("Save New Template", key=f"bb_{p['id']}"):
                    conn.execute("INSERT INTO baselines (project_id, type_name) VALUES (?,?)", (p['id'], b_name_input))
                    conn.commit()
                    st.rerun()
                
                bases = pd.read_sql_query(f"SELECT * FROM baselines WHERE project_id = {p['id']}", conn)
                if not bases.empty:
                    sel_b = st.selectbox("Select Template to Edit Materials", bases['type_name'], key=f"sb_{p['id']}")
                    bid = bases[bases['type_name'] == sel_b]['id'].values[0]
                    
                    st.write(f"**Adding Materials to: {sel_b}**")
                    c1, c2, c3 = st.columns([3,1,1])
                    m_n = c1.text_input("Material Description", key=f"mn_{bid}")
                    m_q = c2.number_input("Quantity", min_value=0.0, key=f"mq_{bid}")
                    m_u = c3.selectbox("Unit", ["Meters", "Units", "Rolls", "Boxes"], key=f"mu_{bid}")
                    
                    # THE FIX: Direct Database Write + Immediate State Change
                    if st.button("ADD MATERIAL TO BASELINE", key=f"ab_{bid}"):
                        if m_n:
                            cursor = conn.cursor()
                            cursor.execute("INSERT INTO baseline_items (b_id, item, qty, uom) VALUES (?,?,?,?)", (bid, m_n, m_q, m_u))
                            conn.commit()
                            st.success(f"Added {m_n} successfully!")
                            st.rerun() # Forces the table below to update immediately
                    
                    # LIVE TABLE VIEW
                    items_df = pd.read_sql_query(f"SELECT id, item, qty, uom FROM baseline_items WHERE b_id = {bid}", conn)
                    if not items_df.empty:
                        for _, row in items_df.iterrows():
                            ic1, ic2, ic3, ic4 = st.columns([3,1,1,1])
                            ic1.write(row['item'])
                            ic2.write(f"{row['qty']} {row['uom']}")
                            # Price Lookup
                            pr_check = conn.execute("SELECT price FROM stores WHERE item = ?", (row['item'],)).fetchone()
                            ic3.write(f"R {pr_check[0] if pr_check else 0.0}")
                            if ic4.button("🗑️", key=f"del_{row['id']}"):
                                conn.execute(f"DELETE FROM baseline_items WHERE id = {row['id']}")
                                conn.commit()
                                st.rerun()

            # --- TAB 2: UNIT TRACKING ---
            with tab2:
                # [Unit allocation and progress tracking logic remains here]
                st.write("Manage Unit progress and allocation here.")

# --- 4. STORES CONTROL ---
elif choice == "📦 Stores Control":
    st.header("Warehouse & Pricing")
    conn = get_connection()
    c1, c2, c3, c4 = st.columns([3,1,1,1])
    s_it = c1.text_input("Item Name")
    s_avail = c2.number_input("Stock Qty", min_value=0.0)
    s_pr = c3.number_input("Unit Price", min_value=0.0)
    s_uom = c4.selectbox("Measure", ["Meters", "Units", "Rolls", "Boxes"])
    
    if st.button("Update Stores"):
        conn.execute("INSERT OR REPLACE INTO stores (item, available, price, uom) VALUES (?,?,?,?)", (s_it, s_avail, s_pr, s_uom))
        conn.commit()
        st.rerun()
    
    st.divider()
    st.table(pd.read_sql_query("SELECT item, available, price, uom FROM stores", conn))

# --- 5. DASHBOARD ---
elif choice == "📊 Dashboard":
    st.header("Project Financials")
    # [Dashboard logic to sum all items and show project totals]
