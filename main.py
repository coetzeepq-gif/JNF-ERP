import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io

# --- 1. DATABASE ENGINE (ADVANCED HIERARCHY) ---
def get_connection():
    return sqlite3.connect('jnf_elect_master_v7.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Projects
    c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE, date_created TEXT)')
    # Project-Specific Baselines (Templates are now linked to a Project ID)
    c.execute('CREATE TABLE IF NOT EXISTS baselines (id INTEGER PRIMARY KEY, project_id INTEGER, type_name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS baseline_items (id INTEGER PRIMARY KEY, b_id INTEGER, item TEXT, qty REAL, cost REAL)')
    # Units
    c.execute('''CREATE TABLE IF NOT EXISTS site_units 
                 (id INTEGER PRIMARY KEY, project_id INTEGER, unit_no TEXT, baseline_id INTEGER, 
                  f_fix INT DEFAULT 0, wire INT DEFAULT 0, s_fix INT DEFAULT 0, test INT DEFAULT 0)''')
    # File Vault (For Drawings/Photos)
    c.execute('CREATE TABLE IF NOT EXISTS unit_files (id INTEGER PRIMARY KEY, unit_id INTEGER, file_name TEXT, file_data BLOB)')
    # Stores & Issues
    c.execute('CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, item TEXT UNIQUE, available REAL, price REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS store_issues (id INTEGER PRIMARY KEY, ts TEXT, user TEXT, unit_id INTEGER, item TEXT, qty REAL)')
    conn.commit()
    conn.close()

init_db()

# --- 2. INTERFACE SETUP ---
st.set_page_config(page_title="JNF Elect ERP", layout="wide")
st.sidebar.title("⚡ JNF Elect ERP")
user = st.sidebar.text_input("User Name:", "Quinton")

menu = ["🏗️ Project Management", "📦 Stores Control", "📜 System Logs"]
choice = st.sidebar.radio("Navigation", menu)

# --- 3. PROJECT MANAGEMENT (Templates & Units Integrated) ---
if choice == "🏗️ Project Management":
    st.header("Project & Unit Control")
    
    # ADD NEW PROJECT
    with st.expander("➕ Create New Project", expanded=False):
        p_name = st.text_input("Project Name")
        if st.button("Save Project"):
            if p_name:
                conn = get_connection()
                try:
                    conn.execute("INSERT INTO projects (name, date_created) VALUES (?,?)", 
                                 (p_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    st.success(f"Project {p_name} Created.")
                except: st.error("Project already exists.")
                conn.close()
                st.rerun()

    # DISPLAY ALL PROJECTS
    conn = get_connection()
    projects = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    for _, p in projects.iterrows():
        with st.container(border=True):
            st.subheader(f"📂 Project: {p['name']}")
            
            t1, t2 = st.tabs(["Design Templates (Project Baselines)", "Unit Management & Files"])
            
            # --- TAB 1: PROJECT-SPECIFIC TEMPLATES ---
            with t1:
                st.write(f"Define standard designs for **{p['name']}**")
                with st.form(f"base_form_{p['id']}"):
                    b_name = st.text_input("Template Name (e.g. House Type E)")
                    if st.form_submit_button("Create Template for this Project"):
                        conn.execute("INSERT INTO baselines (project_id, type_name) VALUES (?,?)", (p['id'], b_name))
                        conn.commit()
                        st.rerun()
                
                # Manage items in these templates
                project_bases = pd.read_sql_query(f"SELECT * FROM baselines WHERE project_id = {p['id']}", conn)
                if not project_bases.empty:
                    sel_b = st.selectbox("Select Template to Edit Materials", project_bases['type_name'], key=f"sb_{p['id']}")
                    bid = project_bases[project_bases['type_name'] == sel_b]['id'].values[0]
                    
                    with st.form(f"mat_form_{p['id']}_{bid}"):
                        c1, c2, c3 = st.columns([3,1,1])
                        m_it = c1.text_input("Material")
                        m_qt = c2.number_input("Qty", min_value=0.0)
                        m_pr = c3.number_input("Price", min_value=0.0)
                        if st.form_submit_button("Add to Baseline"):
                            conn.execute("INSERT INTO baseline_items (b_id, item, qty, cost) VALUES (?,?,?,?)", (bid, m_it, m_qt, m_pr))
                            conn.commit()
                            st.rerun()
                    st.dataframe(pd.read_sql_query(f"SELECT item, qty, cost FROM baseline_items WHERE b_id={bid}", conn), use_container_width=True)

            # --- TAB 2: UNIT MANAGEMENT & FILE VAULT ---
            with t2:
                # Add Unit
                with st.form(f"unit_add_{p['id']}"):
                    c1, c2 = st.columns(2)
                    u_no = c1.text_input("Unit No (e.g. 101)")
                    u_bl = c2.selectbox("Assign Project Template", project_bases['type_name'] if not project_bases.empty else ["No Templates"])
                    if st.form_submit_button("Allocate Unit"):
                        bid_link = project_bases[project_bases['type_name'] == u_bl]['id'].values[0]
                        conn.execute("INSERT INTO site_units (project_id, unit_no, baseline_id) VALUES (?,?,?)", (p['id'], u_no, bid_link))
                        conn.commit()
                        st.rerun()

                # List Units
                units = pd.read_sql_query(f"SELECT * FROM site_units WHERE project_id = {p['id']}", conn)
                for _, u in units.iterrows():
                    with st.expander(f"🏠 Unit {u['unit_no']} (Plan: {u['baseline_id']})"):
                        # Progress
                        st.write("**Construction Progress**")
                        cc1, cc2, cc3, cc4 = st.columns(4)
                        ff = cc1.checkbox("1st Fix", value=bool(u['f_fix']), key=f"ff_{u['id']}")
                        wr = cc2.checkbox("Wiring", value=bool(u['wire']), key=f"wr_{u['id']}")
                        sf = cc3.checkbox("2nd Fix", value=bool(u['s_fix']), key=f"sf_{u['id']}")
                        ts = cc4.checkbox("Testing", value=bool(u['test']), key=f"ts_{u['id']}")
                        if st.button("Update Progress", key=f"upd_{u['id']}"):
                            conn.execute(f"UPDATE site_units SET f_fix={int(ff)}, wire={int(wr)}, s_fix={int(sf)}, test={int(ts)} WHERE id={u['id']}")
                            conn.commit()
                            st.success("Updated.")

                        # --- FILE VAULT (Upload/Download) ---
                        st.divider()
                        st.write("**Drawing & Photo Vault**")
                        uploaded_file = st.file_uploader("Upload Drawing/Photo (PDF, PNG, JPG)", key=f"file_{u['id']}")
                        if uploaded_file is not None:
                            if st.button("Save File to Unit", key=f"save_f_{u['id']}"):
                                file_bytes = uploaded_file.getvalue()
                                conn.execute("INSERT INTO unit_files (unit_id, file_name, file_data) VALUES (?,?,?)", (u['id'], uploaded_file.name, file_bytes))
                                conn.commit()
                                st.success("File Uploaded.")
                        
                        # List Files
                        files = pd.read_sql_query(f"SELECT id, file_name FROM unit_files WHERE unit_id = {u['id']}", conn)
                        for _, f in files.iterrows():
                            st.write(f"📄 {f['file_name']}")
                            # Download Button
                            f_data = conn.execute("SELECT file_data FROM unit_files WHERE id = ?", (f['id'],)).fetchone()[0]
                            st.download_button("Download", f_data, file_name=f['file_name'], key=f"dl_{f['id']}")

# --- 4. STORES CONTROL ---
elif choice == "📦 Stores Control":
    st.header("Warehouse & Site Issuing")
    # Same Stores Logic as before...
