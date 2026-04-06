import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. DATABASE ENGINE ---
def get_connection():
    return sqlite3.connect('jnf_elect_PRO_v25.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    c.execute('CREATE TABLE IF NOT EXISTS blueprints (id INTEGER PRIMARY KEY, project_id INTEGER, name TEXT, UNIQUE(project_id, name))')
    c.execute('CREATE TABLE IF NOT EXISTS blueprint_items (id INTEGER PRIMARY KEY, b_id INTEGER, item TEXT, qty REAL, uom TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS units 
                 (id INTEGER PRIMARY KEY, project_id INTEGER, unit_no TEXT, blueprint_id INTEGER, 
                  first_fix INT DEFAULT 0, piping INT DEFAULT 0, wiring INT DEFAULT 0, fitting INT DEFAULT 0, testing INT DEFAULT 0)''')
    c.execute('CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, item TEXT UNIQUE, available REAL, price REAL, uom TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- 2. INTERFACE ---
st.set_page_config(page_title="JNF Master ERP v25", layout="wide")
st.sidebar.title("⚡ JNF COMMAND")
menu = ["📊 Executive Dashboard", "🏗️ Project Site Manager", "📦 Stores Control"]
choice = st.sidebar.radio("Navigation", menu)

# --- 3. DASHBOARD ---
if choice == "📊 Executive Dashboard":
    st.header("Site Progress Dashboard")
    conn = get_connection()
    projects = pd.read_sql_query("SELECT * FROM projects", conn)
    
    for _, p in projects.iterrows():
        with st.container(border=True):
            st.subheader(f"Project: {p['name']}")
            u_df = pd.read_sql_query(f"""
                SELECT u.unit_no, b.name as b_type, (u.first_fix + u.piping + u.wiring + u.fitting + u.testing) as progress
                FROM units u JOIN blueprints b ON u.blueprint_id = b.id 
                WHERE u.project_id={p['id']}""", conn)
            
            if u_df.empty:
                st.info("No units on site yet.")
            else:
                st.dataframe(u_df, use_container_width=True, hide_index=True)

# --- 4. PROJECT SITE MANAGER (THE ALL-IN-ONE HUB) ---
elif choice == "🏗️ Project Site Manager":
    st.header("Project Site Operations")
    conn = get_connection()
    
    # Create Project
    with st.container(border=True):
        p_name = st.text_input("Launch New Project Site")
        if st.button("Initialize Site"):
            if p_name:
                conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (p_name,))
                conn.commit()
                st.rerun()

    st.divider()
    
    projs = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    for _, p in projs.iterrows():
        with st.expander(f"📂 SITE: {p['name']}", expanded=True):
            
            tab1, tab2, tab3 = st.tabs(["📋 Design Blueprints", "🏗️ Unit Tracking & Extras", "📚 Site Blueprint Library"])
            
            # --- TAB 1: DESIGN ---
            with tab1:
                st.write("### Create New Blueprint")
                bn = st.text_input("Blueprint Name", key=f"bn_{p['id']}")
                if st.button("Save Blueprint", key=f"bsb_{p['id']}"):
                    if bn:
                        conn.execute("INSERT INTO blueprints (project_id, name) VALUES (?,?)", (p['id'], bn))
                        conn.commit()
                        st.rerun()

            # --- TAB 2: UNIT TRACKING ---
            with tab2:
                st.write("### Link Unit/Yard to Site")
                c1, c2, c3 = st.columns([2,2,1])
                u_no = c1.text_input("Unit No", key=f"u_{p['id']}")
                bls = pd.read_sql_query(f"SELECT * FROM blueprints WHERE project_id={p['id']}", conn)
                u_bl = c2.selectbox("Assign Blueprint", bls['name'] if not bls.empty else ["None"], key=f"ub_{p['id']}")
                
                if c3.button("Link Unit", key=f"lu_{p['id']}"):
                    if not bls.empty and u_no:
                        bid = bls[bls['name'] == u_bl]['id'].values[0]
                        conn.execute("INSERT INTO units (project_id, unit_no, blueprint_id) VALUES (?,?,?)", (p['id'], u_no, bid))
                        conn.commit()
                        st.rerun()
                
                st.divider()
                st.write("### Active Units & Progress")
                # THE UNIT LIST YOU WERE MISSING
                units = pd.read_sql_query(f"""
                    SELECT u.*, b.name as b_type FROM units u 
                    JOIN blueprints b ON u.blueprint_id = b.id 
                    WHERE u.project_id={p['id']}""", conn)
                
                for _, u in units.iterrows():
                    with st.container(border=True):
                        # Line 1: Unit ID and Blueprint Type
                        st.write(f"**Unit {u['unit_no']}** — *Blueprint: {u['b_type']}*")
                        # Line 2: The 5 Electrical Stages
                        sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(6)
                        f1 = sc1.checkbox("1st Fix", value=u['first_fix'], key=f"f1_{u['id']}")
                        f2 = sc2.checkbox("Piping", value=u['piping'], key=f"f2_{u['id']}")
                        f3 = sc3.checkbox("Wiring", value=u['wiring'], key=f"f3_{u['id']}")
                        f4 = sc4.checkbox("Fitting", value=u['fitting'], key=f"f4_{u['id']}")
                        f5 = sc5.checkbox("Testing", value=u['testing'], key=f"f5_{u['id']}")
                        if sc6.button("Update", key=f"upd_{u['id']}"):
                            conn.execute(f"UPDATE units SET first_fix={int(f1)}, piping={int(f2)}, wiring={int(f3)}, fitting={int(f4)}, testing={int(f5)} WHERE id={u['id']}")
                            conn.commit()
                            st.rerun()

            # --- TAB 3: SITE BLUEPRINT LIBRARY ---
            with tab3:
                st.write(f"### Existing Blueprints for {p['name']}")
                if bls.empty:
                    st.info("No blueprints designed for this site yet.")
                else:
                    for _, b in bls.iterrows():
                        with st.expander(f"Blueprint: {b['name']}"):
                            # Add Material to existing blueprint
                            mc1, mc2, mc3, mc4 = st.columns([3,1,1,1])
                            m_it = mc1.text_input("Material", key=f"mi_{b['id']}")
                            m_qt = mc2.number_input("Qty", min_value=0.0, key=f"mq_{b['id']}")
                            m_um = mc3.selectbox("Unit", ["Units", "Meters", "Rolls"], key=f"mu_{b['id']}")
                            if mc4.button("Add", key=f"ma_{b['id']}"):
                                conn.execute("INSERT INTO blueprint_items (b_id, item, qty, uom) VALUES (?,?,?,?)", (b['id'], m_it, m_qt, m_um))
                                conn.commit()
                                st.rerun()
                            
                            # Show the Quote List
                            items = pd.read_sql_query(f"""
                                SELECT bi.id, bi.item, bi.qty, bi.uom, IFNULL(s.price, 0) as rate, (bi.qty * IFNULL(s.price, 0)) as total 
                                FROM blueprint_items bi LEFT JOIN stores s ON bi.item = s.item WHERE bi.b_id = {b['id']}""", conn)
                            if not items.empty:
                                st.table(items.drop(columns=['id']))
                                if st.button(f"🗑️ Delete {b['name']}", key=f"db_{b['id']}"):
                                    conn.execute(f"DELETE FROM blueprint_items WHERE b_id={b['id']}")
                                    conn.execute(f"DELETE FROM blueprints WHERE id={b['id']}")
                                    conn.commit()
                                    st.rerun()

# --- 5. STORES CONTROL ---
elif choice == "📦 Stores Control":
    st.header("Warehouse Inventory")
    conn = get_connection()
    # [Previous working stores logic kept intact]
    c1, c2, c3, c4 = st.columns([3,1,1,1])
    s_it = c1.text_input("Material Name")
    s_q = c2.number_input("Stock Qty", min_value=0.0)
    s_p = c3.number_input("Unit Price", min_value=0.0)
    s_u = c4.selectbox("Unit", ["Units", "Meters", "Rolls", "Boxes"])
    if st.button("Update Stores"):
        conn.execute("INSERT OR REPLACE INTO stores (item, available, price, uom) VALUES (?,?,?,?)", (s_it, s_q, s_p, s_u))
        conn.commit()
        st.rerun()
    st.table(pd.read_sql_query("SELECT * FROM stores", conn))
