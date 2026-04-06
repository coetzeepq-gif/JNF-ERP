import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. DATABASE ENGINE ---
def get_connection():
    return sqlite3.connect('jnf_master_final_v8.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE, date_created TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS baselines (id INTEGER PRIMARY KEY, project_id INTEGER, type_name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS baseline_items (id INTEGER PRIMARY KEY, b_id INTEGER, item TEXT, qty REAL)')
    c.execute('''CREATE TABLE IF NOT EXISTS site_units 
                 (id INTEGER PRIMARY KEY, project_id INTEGER, unit_no TEXT, baseline_id INTEGER, 
                  f_fix INT DEFAULT 0, wire INT DEFAULT 0, s_fix INT DEFAULT 0, test INT DEFAULT 0)''')
    c.execute('CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, item TEXT UNIQUE, available REAL, price REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS store_issues (id INTEGER PRIMARY KEY, ts TEXT, user TEXT, unit_id INTEGER, item TEXT, qty REAL)')
    conn.commit()
    conn.close()

init_db()

# --- 2. NAVIGATION ---
st.set_page_config(page_title="JNF Elect ERP", layout="wide")
st.sidebar.title("⚡ JNF Elect ERP")
user = st.sidebar.text_input("User Name:", "Quinton")
menu = ["🏗️ Project Management", "📦 Stores Control", "📜 System Logs"]
choice = st.sidebar.radio("Navigation", menu)

# --- 3. PROJECT MANAGEMENT ---
if choice == "🏗️ Project Management":
    st.header("Project & Unit Control")
    
    # PROJECT CREATION
    p_name_input = st.text_input("New Project Name")
    if st.button("Save Project"):
        if p_name_input:
            conn = get_connection()
            try:
                conn.execute("INSERT INTO projects (name, date_created) VALUES (?,?)", (p_name_input, datetime.now().strftime("%Y-%m-%d")))
                conn.commit()
                st.success("Project Created")
            except: st.error("Exists")
            conn.close()

    st.divider()
    conn = get_connection()
    projects = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    
    for _, p in projects.iterrows():
        with st.expander(f"📂 PROJECT: {p['name']}", expanded=True):
            t1, t2 = st.tabs(["Templates (Baselines)", "Units & Progress"])
            
            # --- BASELINES (TEMPLATES) ---
            with t1:
                st.subheader("Design Templates")
                b_name = st.text_input("New Template Name", key=f"bn_{p['id']}")
                if st.button("Create Template", key=f"bb_{p['id']}"):
                    conn.execute("INSERT INTO baselines (project_id, type_name) VALUES (?,?)", (p['id'], b_name))
                    conn.commit()
                
                bases = pd.read_sql_query(f"SELECT * FROM baselines WHERE project_id = {p['id']}", conn)
                if not bases.empty:
                    sel_b = st.selectbox("Select Template to Edit", bases['type_name'], key=f"sb_{p['id']}")
                    bid = bases[bases['type_name'] == sel_b]['id'].values[0]
                    
                    # Add Item (NO PRICE INPUT - Price comes from Store)
                    col_m, col_q = st.columns([3,1])
                    m_it = col_m.text_input("Material Name", key=f"mi_{bid}")
                    m_qt = col_q.number_input("Qty", min_value=0.0, key=f"mq_{bid}")
                    
                    if st.button("Add Item to Baseline", key=f"ab_{bid}"):
                        conn.execute("INSERT INTO baseline_items (b_id, item, qty) VALUES (?,?,?)", (bid, m_it, m_qt))
                        conn.commit()
                    
                    # VIEW & DELETE ITEMS
                    items_df = pd.read_sql_query(f"""
                        SELECT bi.id, bi.item, bi.qty, IFNULL(s.price, 0) as price, (bi.qty * IFNULL(s.price, 0)) as total
                        FROM baseline_items bi
                        LEFT JOIN stores s ON bi.item = s.item
                        WHERE bi.b_id = {bid}
                    """, conn)
                    st.table(items_df)
                    
                    del_id = st.number_input("Enter Item ID to Delete", min_value=0, key=f"del_{bid}")
                    if st.button("Delete Item", key=f"delbtn_{bid}"):
                        conn.execute(f"DELETE FROM baseline_items WHERE id = {del_id}")
                        conn.commit()
                        st.rerun()

# --- 4. STORES CONTROL ---
elif choice == "📦 Stores Control":
    st.header("Warehouse & Pricing")
    conn = get_connection()
    
    # ADD/UPDATE STOCK & PRICE
    st.subheader("Update Master Price & Stock")
    c1, c2, c3 = st.columns([3,1,1])
    s_item = c1.text_input("Material Name")
    s_qty = c2.number_input("Total Stock", min_value=0.0)
    s_price = c3.number_input("Unit Price (Rand)", min_value=0.0)
    
    if st.button("Update Stores"):
        conn.execute("INSERT OR REPLACE INTO stores (item, available, price) VALUES (?,?,?)", (s_item, s_qty, s_price))
        conn.commit()
        st.success(f"Updated {s_item}")
        st.rerun()

    st.divider()
    st.subheader("Current Inventory")
    inventory = pd.read_sql_query("SELECT item as Material, available as Stock, price as 'Unit Price' FROM stores", conn)
    st.table(inventory)
