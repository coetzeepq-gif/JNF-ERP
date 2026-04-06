import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. DATABASE ENGINE ---
def get_connection():
    return sqlite3.connect('jnf_elect_final.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Projects
    c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    # Baselines (Linked to Project)
    c.execute('CREATE TABLE IF NOT EXISTS baselines (id INTEGER PRIMARY KEY, project_id INTEGER, type_name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS baseline_items (id INTEGER PRIMARY KEY, b_id INTEGER, item TEXT, qty REAL, uom TEXT)')
    # Units
    c.execute('''CREATE TABLE IF NOT EXISTS site_units 
                 (id INTEGER PRIMARY KEY, project_id INTEGER, unit_no TEXT, baseline_id INTEGER, 
                  f_fix INT DEFAULT 0, wire INT DEFAULT 0, s_fix INT DEFAULT 0, test INT DEFAULT 0)''')
    # Stores
    c.execute('CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, item TEXT UNIQUE, available REAL, price REAL, uom TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- 2. NAVIGATION ---
st.set_page_config(page_title="JNF Elect ERP", layout="wide")
st.sidebar.title("⚡ JNF Elect")
menu = ["🏗️ Project Management", "📦 Stores Control"]
choice = st.sidebar.radio("Navigation", menu)

# --- 3. PROJECT MANAGEMENT ---
if choice == "🏗️ Project Management":
    st.header("Project & Site Control")
    
    # CREATE PROJECT
    p_name = st.text_input("New Project Name")
    if st.button("Create Project"):
        if p_name:
            conn = get_connection()
            conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (p_name,))
            conn.commit()
            conn.close()
            st.rerun()

    st.divider()
    conn = get_connection()
    projects = pd.read_sql_query("SELECT * FROM projects", conn)
    
    for _, p in projects.iterrows():
        with st.expander(f"📂 PROJECT: {p['name']}", expanded=True):
            tab1, tab2 = st.tabs(["Design Blueprints", "Unit Tracking"])
            
            # --- BLUEPRINTS (Inside Project) ---
            with tab1:
                st.subheader(f"Add Template for {p['name']}")
                b_name = st.text_input("Template Name (e.g. House E)", key=f"bn_{p['id']}")
                if st.button("Save Template", key=f"bb_{p['id']}"):
                    conn.execute("INSERT INTO baselines (project_id, type_name) VALUES (?,?)", (p['id'], b_name))
                    conn.commit()
                    st.rerun()
                
                bases = pd.read_sql_query(f"SELECT * FROM baselines WHERE project_id = {p['id']}", conn)
                if not bases.empty:
                    sel_b = st.selectbox("Select Template to Edit", bases['type_name'], key=f"sb_{p['id']}")
                    bid = bases[bases['type_name'] == sel_b]['id'].values[0]
                    
                    st.write(f"**Add Materials to {sel_b}**")
                    c1, c2, c3 = st.columns([3,1,1])
                    m_n = c1.text_input("Material Name", key=f"mn_{bid}")
                    m_q = c2.number_input("Qty", min_value=0.0, key=f"mq_{bid}")
                    m_u = c3.selectbox("UOM", ["Meters", "Units", "Rolls", "Boxes"], key=f"mu_{bid}")
                    
                    if st.button("ADD ITEM", key=f"ai_{bid}"):
                        conn.execute("INSERT INTO baseline_items (b_id, item, qty, uom) VALUES (?,?,?,?)", (bid, m_n, m_q, m_u))
                        conn.commit()
                        st.rerun()

                    # LIST ITEMS WITH DELETE
                    items = pd.read_sql_query(f"SELECT id, item, qty, uom FROM baseline_items WHERE b_id={bid}", conn)
                    for _, row in items.iterrows():
                        ic1, ic2, ic3, ic4 = st.columns([3,1,1,1])
                        ic1.write(row['item'])
                        ic2.write(f"{row['qty']} {row['uom']}")
                        # Price pull from stores
                        price = conn.execute("SELECT price FROM stores WHERE item = ?", (row['item'],)).fetchone()
                        ic3.write(f"R {price[0] if price else 0.0}")
                        if ic4.button("🗑️", key=f"del_{row['id']}"):
                            conn.execute(f"DELETE FROM baseline_items WHERE id={row['id']}")
                            conn.commit()
                            st.rerun()

            # --- UNITS ---
            with tab2:
                st.subheader("Allocate Units")
                uc1, uc2 = st.columns(2)
                u_no = uc1.text_input("Unit No", key=f"uno_{p['id']}")
                u_bl = uc2.selectbox("Apply Template", bases['type_name'] if not bases.empty else ["None"], key=f"ubl_{p['id']}")
                if st.button("Link to Site", key=f"ls_{p['id']}"):
                    bl_id = bases[bases['type_name'] == u_bl]['id'].values[0]
                    conn.execute("INSERT INTO site_units (project_id, unit_no, baseline_id) VALUES (?,?,?)", (p['id'], u_no, bl_id))
                    conn.commit()
                    st.rerun()
                
                units = pd.read_sql_query(f"SELECT * FROM site_units WHERE project_id={p['id']}", conn)
                for _, u in units.iterrows():
                    st.write(f"**Unit {u['unit_no']}** ({u['baseline_id']})")
                    cc1, cc2, cc3, cc4, cc5 = st.columns(5)
                    f1 = cc1.checkbox("1st Fix", value=u['f_fix'], key=f"f1_{u['id']}")
                    f2 = cc2.checkbox("Wire", value=u['wire'], key=f"f2_{u['id']}")
                    f3 = cc3.checkbox("2nd Fix", value=u['s_fix'], key=f"f3_{u['id']}")
                    f4 = cc4.checkbox("Test", value=u['test'], key=f"f4_{u['id']}")
                    if cc5.button("SAVE", key=f"sv_{u['id']}"):
                        conn.execute(f"UPDATE site_units SET f_fix={int(f1)}, wire={int(f2)}, s_fix={int(f3)}, test={int(f4)} WHERE id={u['id']}")
                        conn.commit()
                        st.success("Saved")

# --- 4. STORES CONTROL ---
elif choice == "📦 Stores Control":
    st.header("Warehouse & Pricing")
    conn = get_connection()
    c1, c2, c3, c4 = st.columns([3,1,1,1])
    s_it = c1.text_input("Material Name")
    s_q = c2.number_input("Stock Qty", min_value=0.0)
    s_p = c3.number_input("Unit Price", min_value=0.0)
    s_u = c4.selectbox("UOM", ["Meters", "Units", "Rolls", "Boxes"], key="suom")
    
    if st.button("Update Stores"):
        conn.execute("INSERT OR REPLACE INTO stores (item, available, price, uom) VALUES (?,?,?,?)", (s_it, s_q, s_p, s_u))
        conn.commit()
        st.rerun()
    
    st.divider()
    st.table(pd.read_sql_query("SELECT item, available, price, uom FROM stores", conn))
