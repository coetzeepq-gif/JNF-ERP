import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io

# --- 1. DATABASE ENGINE ---
def get_connection():
    return sqlite3.connect('jnf_master_final_v20.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Projects & Blueprints
    c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE, budget REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS blueprints (id INTEGER PRIMARY KEY, project_id INTEGER, type_name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS blueprint_items (id INTEGER PRIMARY KEY, b_id INTEGER, item TEXT, qty REAL, uom TEXT)')
    # Units & Progress
    c.execute('''CREATE TABLE IF NOT EXISTS units 
                 (id INTEGER PRIMARY KEY, project_id INTEGER, unit_no TEXT, blueprint_id INTEGER, 
                  f_fix INT DEFAULT 0, wire INT DEFAULT 0, s_fix INT DEFAULT 0, test INT DEFAULT 0)''')
    # Extras & Files
    c.execute('CREATE TABLE IF NOT EXISTS unit_extras (id INTEGER PRIMARY KEY, unit_id INTEGER, item TEXT, qty REAL, uom TEXT, price REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS unit_files (id INTEGER PRIMARY KEY, unit_id INTEGER, file_name TEXT, file_data BLOB)')
    # Stores
    c.execute('CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, item TEXT UNIQUE, available REAL, price REAL, uom TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- 2. INTERFACE SETTINGS ---
st.set_page_config(page_title="JNF Master ERP", layout="wide")
st.sidebar.title("⚡ JNF COMMAND")
user = st.sidebar.text_input("User Authority:", "Quinton")
menu = ["📊 Dashboard", "🏗️ Project Site Manager", "📋 Blueprint Designer", "📦 Stores & Procurement"]
choice = st.sidebar.radio("Navigation", menu)

# --- 3. DASHBOARD ---
if choice == "📊 Dashboard":
    st.header("Executive Site Health")
    conn = get_connection()
    projects = pd.read_sql_query("SELECT * FROM projects", conn)
    
    for _, p in projects.iterrows():
        with st.container(border=True):
            col1, col2, col3 = st.columns([2,1,1])
            units_df = pd.read_sql_query(f"SELECT f_fix, wire, s_fix, test FROM units WHERE project_id={p['id']}", conn)
            progress = (units_df.sum().sum() / (len(units_df)*4)) if not units_df.empty else 0
            
            cost_q = f"""
                SELECT SUM(bi.qty * IFNULL(s.price, 0)) FROM units u
                JOIN blueprint_items bi ON u.blueprint_id = bi.b_id
                LEFT JOIN stores s ON bi.item = s.item
                WHERE u.project_id = {p['id']}
            """
            total_val = conn.execute(cost_q).fetchone()[0] or 0.0
            
            col1.subheader(f"Project: {p['name']}")
            col2.write(f"**Completion:** {int(progress*100)}%")
            col2.progress(progress)
            col3.metric("Project Material Value", f"R {total_val:,.2f}")

# --- 4. PROJECT SITE MANAGER (UNITS, EXTRAS, FILES) ---
elif choice == "🏗️ Project Site Manager":
    st.header("Site Operations")
    conn = get_connection()
    
    with st.expander("➕ Create New Project Site"):
        p_name = st.text_input("Site Name")
        if st.button("Launch Project"):
            if p_name:
                conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (p_name,))
                conn.commit()
                st.rerun()

    projects = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    for _, p in projects.iterrows():
        with st.expander(f"📂 Site: {p['name']}", expanded=True):
            # Add Unit
            st.write("### **Link Blueprint to Unit/Yard**")
            c1, c2 = st.columns(2)
            u_no_in = c1.text_input("Unit/Yard No (e.g. R1, Unit 101)", key=f"un_{p['id']}")
            bl_list = pd.read_sql_query(f"SELECT * FROM blueprints WHERE project_id={p['id']}", conn)
            u_bl_in = c2.selectbox("Select Blueprint", bl_list['type_name'] if not bl_list.empty else ["No Blueprints"], key=f"ub_{p['id']}")
            
            if st.button("Allocate Unit to Site", key=f"al_{p['id']}"):
                bl_id = bl_list[bl_list['type_name'] == u_bl_in]['id'].values[0]
                conn.execute("INSERT INTO units (project_id, unit_no, blueprint_id) VALUES (?,?,?)", (p['id'], u_no_in, bl_id))
                conn.commit()
                st.rerun()
            
            # Show Units
            st.divider()
            units = pd.read_sql_query(f"SELECT * FROM units WHERE project_id={p['id']}", conn)
            for _, u in units.iterrows():
                with st.container(border=True):
                    sc1, sc2, sc3 = st.columns([1,2,2])
                    sc1.write(f"**Unit {u['unit_no']}**")
                    
                    # Progress
                    f1 = sc2.checkbox("1st Fix", value=u['f_fix'], key=f"f1_{u['id']}")
                    f2 = sc2.checkbox("Wiring", value=u['wire'], key=f"f2_{u['id']}")
                    f3 = sc3.checkbox("2nd Fix", value=u['s_fix'], key=f"f3_{u['id']}")
                    f4 = sc3.checkbox("Testing", value=u['test'], key=f"f4_{u['id']}")
                    
                    if st.button("Save Progress", key=f"sv_{u['id']}"):
                        conn.execute(f"UPDATE units SET f_fix={int(f1)}, wire={int(f2)}, s_fix={int(f3)}, test={int(f4)} WHERE id={u['id']}")
                        conn.commit()
                        st.rerun()
