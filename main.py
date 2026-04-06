import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. DATABASE ENGINE ---
def get_connection():
    return sqlite3.connect('jnf_elect_FINAL_WORKHORSE.db', check_same_thread=False)

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

# --- 2. NAVIGATION ---
st.set_page_config(page_title="JNF Master ERP", layout="wide")
st.sidebar.title("⚡ JNF COMMAND")
menu = ["📊 Executive Dashboard", "📋 Blueprint Library", "🏗️ Project Site Manager", "📦 Stores Control"]
choice = st.sidebar.radio("Navigation", menu)

# --- 3. EXECUTIVE DASHBOARD ---
if choice == "📊 Executive Dashboard":
    st.header("Site Progress & Unit Material Lists")
    conn = get_connection()
    projects = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    
    for _, p in projects.iterrows():
        with st.container(border=True):
            st.subheader(f"🏗️ Project: {p['name']}")
            u_df = pd.read_sql_query(f"""
                SELECT u.*, b.name as b_type 
                FROM units u JOIN blueprints b ON u.blueprint_id = b.id 
                WHERE u.project_id={p['id']}""", conn)
            
            if u_df.empty:
                st.info("No units linked. Go to 'Project Site Manager' to add units.")
            else:
                u_cols = st.columns(2)
                for i, u in u_df.iterrows():
                    with u_cols[i % 2]:
                        with st.expander(f"UNIT {u['unit_no']} - Type: {u['b_type']}", expanded=False):
                            st.write("**Electrical Progress:**")
                            c1, c2, c3, c4, c5, c6 = st.columns(6)
                            ff = c1.checkbox("1st Fix", value=u['first_fix'], key=f"ff_{u['id']}")
                            pp = c2.checkbox("Piping", value=u['piping'], key=f"pp_{u['id']}")
                            ww = c3.checkbox("Wiring", value=u['wiring'], key=f"ww_{u['id']}")
                            ft = c4.checkbox("Fitting", value=u['fitting'], key=f"ft_{u['id']}")
                            tt = c5.checkbox("Test", value=u['testing'], key=f"tt_{u['id']}")
                            if c6.button("Save", key=f"sv_{u['id']}"):
                                conn.execute(f"UPDATE units SET first_fix={int(ff)}, piping={int(pp)}, wiring={int(ww)}, fitting={int(ft)}, testing={int(tt)} WHERE id={u['id']}")
                                conn.commit()
                                st.rerun()
                            
                            st.write("---")
                            st.write("**Material Bill of Quantities:**")
                            m_df = pd.read_sql_query(f"""
                                SELECT bi.item, bi.qty, bi.uom, IFNULL(s.price, 0) as price, (bi.qty * IFNULL(s.price, 0)) as total
                                FROM blueprint_items bi LEFT JOIN stores s ON bi.item = s.item 
                                WHERE bi.b_id = {u['blueprint_id']}""", conn)
                            st.table(m_df)
                            st.write(f"**Total Unit Value:** R {m_df['total'].sum():,.2f}")

# --- 4. BLUEPRINT LIBRARY ---
elif choice == "📋 Blueprint Library":
    st.header("Master Blueprint Editor")
    conn = get_connection()
    all_b = pd.read_sql_query("SELECT b.id, b.name, p.name as proj FROM blueprints b JOIN projects p ON b.project_id = p.id", conn)
    
    if not all_b.empty:
        sel_b = st.selectbox("Select Blueprint to Edit", all_b['name'] + " [" + all_b['proj'] + "]")
        bid = all_b[all_b['name'] + " [" + all_b['proj'] + "]" == sel_b]['id'].values[0]
        
        st.write("### Add Material Line")
        c1, c2, c3, c4 = st.columns([3,1,1,1])
        m_it = c1.text_input("Item")
        m_qt = c2.number_input("Qty", min_value=0.0)
        m_um = c3.selectbox("UOM", ["Units", "Meters", "Rolls", "Boxes"])
        if c4.button("Add Item"):
            conn.execute("INSERT INTO blueprint_items (b_id, item, qty, uom) VALUES (?,?,?,?)", (bid, m_it, m_qt, m_um))
            conn.commit()
            st.rerun()
            
        items = pd.read_sql_query(f"SELECT * FROM blueprint_items WHERE b_id = {bid}", conn)
        st.table(items[['item', 'qty', 'uom']])
        for _, r in items.iterrows():
            if st.button(f"🗑️ Delete {r['item']}", key=f"del_{r['id']}"):
                conn.execute(f"DELETE FROM blueprint_items WHERE id={r['id']}")
                conn.commit()
                st.rerun()

# --- 5. PROJECT SITE MANAGER ---
elif choice == "🏗️ Project Site Manager":
    st.header("Site Setup")
    conn = get_connection()
    p_name = st.text_input("Project Name")
    if st.button("Create Site"):
        conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (p_name,))
        conn.commit()
        st.rerun()

    projects = pd.read_sql_query("SELECT * FROM projects", conn)
    for _, p in projects.iterrows():
        with st.expander(f"📂 SETUP: {p['name']}", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                st.write("**1. Create Blueprint**")
                bn = st.text_input("Blueprint Name", key=f"bn_{p['id']}")
                if st.button("Save Design", key=f"bs_{p['id']}"):
                    conn.execute("INSERT INTO blueprints (project_id, name) VALUES (?,?)", (p['id'], bn))
                    conn.commit()
                    st.rerun()
            with c2:
                st.write("**2. Link Unit**")
                un = st.text_input("Unit No", key=f"un_{p['id']}")
                bls = pd.read_sql_query(f"SELECT * FROM blueprints WHERE project_id={p['id']}", conn)
                ubl = st.selectbox("Design Type", bls['name'] if not bls.empty else ["None"], key=f"ub_{p['id']}")
                if st.button("Link Unit", key=f"ul_{p['id']}"):
                    bid = bls[bls['name'] == ubl]['id'].values[0]
                    conn.execute("INSERT INTO units (project_id, unit_no, blueprint_id) VALUES (?,?,?)", (p['id'], un, bid))
                    conn.commit()
                    st.rerun()

# --- 6. STORES CONTROL ---
elif choice == "📦 Stores Control":
    st.header("Warehouse Inventory")
    conn = get_connection()
    c1, c2, c3, c4 = st.columns([3,1,1,1])
    s_it = c1.text_input("Material Name")
    s_q = c2.number_input("Stock Qty")
    s_p = c3.number_input("Price")
    s_u = c4.selectbox("Unit", ["Units", "Meters", "Rolls", "Boxes"])
    if st.button("Update"):
        conn.execute("INSERT OR REPLACE INTO stores (item, available, price, uom) VALUES (?,?,?,?)", (s_it, s_q, s_p, s_u))
        conn.commit()
        st.rerun()
    st.table(pd.read_sql_query("SELECT * FROM stores", conn))
