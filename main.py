import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io

# --- 1. DATABASE ENGINE (REBUILT FOR CLOUD) ---
def get_connection():
    # This creates a fresh connection every time to prevent "Database Locked" errors
    return sqlite3.connect('jnf_master_final.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Templates (House Type E, Gym, etc.)
    c.execute('CREATE TABLE IF NOT EXISTS baselines (id INTEGER PRIMARY KEY, type_name TEXT UNIQUE)')
    c.execute('CREATE TABLE IF NOT EXISTS baseline_items (id INTEGER PRIMARY KEY, b_id INTEGER, item TEXT, qty REAL, cost REAL)')
    # Projects & Units
    c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE, date_created TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS site_units 
                 (id INTEGER PRIMARY KEY, project_id INTEGER, unit_no TEXT, baseline_type TEXT, 
                  f_fix INT DEFAULT 0, wire INT DEFAULT 0, s_fix INT DEFAULT 0, test INT DEFAULT 0)''')
    # Unplanned Adjustments & Stores
    c.execute('CREATE TABLE IF NOT EXISTS unit_adjustments (id INTEGER PRIMARY KEY, unit_id INTEGER, item TEXT, qty REAL, cost REAL, reason TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, item TEXT UNIQUE, available REAL, price REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS store_issues (id INTEGER PRIMARY KEY, ts TEXT, user TEXT, unit_id INTEGER, item TEXT, qty REAL)')
    conn.commit()
    conn.close()

init_db()

# --- 2. INTERFACE SETUP ---
st.set_page_config(page_title="JNF Elect ERP", layout="wide")
st.sidebar.title("⚡ JNF Elect ERP")
user = st.sidebar.text_input("User Name:", "Quinton")

menu = ["📈 Projects & Dashboard", "🏠 Baseline Templates", "📦 Stores Control"]
choice = st.sidebar.radio("Go To:", menu)

# --- 3. PROJECTS & DASHBOARD ---
if choice == "📈 Projects & Dashboard":
    st.header("Project Management Center")
    
    # ADD NEW PROJECT
    with st.expander("➕ Create New Project", expanded=True):
        p_name = st.text_input("Project Name (e.g., Atlantic Estate)")
        if st.button("Save & Start Project"):
            if p_name:
                conn = get_connection()
                try:
                    conn.execute("INSERT INTO projects (name, date_created) VALUES (?,?)", 
                                 (p_name, datetime.now().strftime("%Y-%m-%d")))
                    conn.commit()
                    st.success(f"Project {p_name} Created.")
                except:
                    st.error("Project name already exists.")
                conn.close()

    # DISPLAY PROJECTS
    conn = get_connection()
    projects = pd.read_sql_query("SELECT * FROM projects", conn)
    for _, p in projects.iterrows():
        with st.container(border=True):
            st.subheader(f"🏗️ {p['name']}")
            
            # --- UNIT MANAGEMENT ---
            with st.expander(f"Manage Units for {p['name']}"):
                col1, col2 = st.columns(2)
                u_no = col1.text_input("Unit No (e.g. 101)", key=f"u_in_{p['id']}")
                bls = pd.read_sql_query("SELECT type_name FROM baselines", conn)
                u_bl = col2.selectbox("Link to Baseline Plan", bls['type_name'] if not bls.empty else ["No Templates"], key=f"bl_sel_{p['id']}")
                
                if st.button("Add Unit to Project", key=f"btn_u_{p['id']}"):
                    conn.execute("INSERT INTO site_units (project_id, unit_no, baseline_type) VALUES (?,?,?)", (p['id'], u_no, u_bl))
                    conn.commit()
                    st.rerun()

                # LIST UNITS & PROGRESS
                units = pd.read_sql_query(f"SELECT * FROM site_units WHERE project_id = {p['id']}", conn)
                for _, u in units.iterrows():
                    st.divider()
                    st.write(f"**Unit {u['unit_no']}** ({u['baseline_type']})")
                    c1, c2, c3, c4 = st.columns(4)
                    ff = c1.checkbox("1st Fix", value=bool(u['f_fix']), key=f"ff_{u['id']}")
                    wr = c2.checkbox("Wiring", value=bool(u['wire']), key=f"wr_{u['id']}")
                    sf = c3.checkbox("2nd Fix", value=bool(u['s_fix']), key=f"sf_{u['id']}")
                    ts = c4.checkbox("Testing", value=bool(u['test']), key=f"ts_{u['id']}")
                    
                    if st.button("Save Progress", key=f"sv_prg_{u['id']}"):
                        conn.execute(f"UPDATE site_units SET f_fix={int(ff)}, wire={int(wr)}, s_fix={int(sf)}, test={int(ts)} WHERE id={u['id']}")
                        conn.commit()
                        st.success("Saved.")

# --- 4. BASELINE TEMPLATES ---
elif choice == "🏠 Baseline Templates":
    st.header("Master Plans (Initial Designs)")
    with st.form("new_template"):
        t_name = st.text_input("Template Name (e.g. House Type E)")
        if st.form_submit_button("Create Template"):
            if t_name:
                conn = get_connection()
                try:
                    conn.execute("INSERT INTO baselines (type_name) VALUES (?)", (t_name,))
                    conn.commit()
                    st.success("Template Created.")
                except:
                    st.error("Template already exists.")
                conn.close()

    conn = get_connection()
    bl_df = pd.read_sql_query("SELECT * FROM baselines", conn)
    if not bl_df.empty:
        sel_t = st.selectbox("Select Template to Edit Materials", bl_df['type_name'])
        tid = bl_df[bl_df['type_name'] == sel_t]['id'].values[0]
        
        with st.form("add_mat"):
            m1, m2, m3 = st.columns([3,1,1])
            m_it = m1.text_input("Material Name")
            m_qt = m2.number_input("Qty", min_value=0.0)
            m_pr = m3.number_input("Price", min_value=0.0)
            if st.form_submit_button("Add Material to Plan"):
                conn.execute("INSERT INTO baseline_items (b_id, item, qty, cost) VALUES (?,?,?,?)", (tid, m_it, m_qt, m_pr))
                conn.commit()
                st.rerun()
        
        st.table(pd.read_sql_query(f"SELECT item, qty, cost FROM baseline_items WHERE b_id={tid}", conn))

# --- 5. STORES CONTROL ---
elif choice == "📦 Stores Control":
    st.header("Stores & Stock Management")
    t1, t2 = st.tabs(["Warehouse", "Issue to Site"])
    
    conn = get_connection()
    with t1:
        with st.form("stock_in"):
            s1, s2, s3 = st.columns([3,1,1])
            s_it = s1.text_input("Item Name")
            s_qt = s2.number_input("Qty In", min_value=0.0)
            s_pr = s3.number_input("Price", min_value=0.0)
            if st.form_submit_button("Add to Stock"):
                conn.execute("INSERT OR REPLACE INTO stores (item, available, price) VALUES (?,?,?)", (s_it, s_qt, s_pr))
                conn.commit()
                st.rerun()
        st.table(pd.read_sql_query("SELECT item, available, price FROM stores", conn))

    with t2:
        st.subheader("Issue to Unit")
        u_list = pd.read_sql_query("SELECT su.id, p.name || ' - Unit ' || su.unit_no as display FROM site_units su JOIN projects p ON su.project_id = p.id", conn)
        if not u_list.empty:
            sel_u = st.selectbox("Destination Unit", u_list['display'])
            uid = u_list[u_list['display'] == sel_u]['id'].values[0]
            st_items = pd.read_sql_query("SELECT item FROM stores WHERE available > 0", conn)
            sel_s = st.selectbox("Material", st_items['item'] if not st_items.empty else ["No Stock"])
            iss_q = st.number_input("Qty to Issue", min_value=0.0)
            if st.button("Confirm Issue"):
                conn.execute("UPDATE stores SET available = available - ? WHERE item = ?", (iss_q, sel_s))
                conn.execute("INSERT INTO store_issues (ts, user, unit_id, item, qty) VALUES (?,?,?,?,?)", 
                             (datetime.now().strftime("%Y-%m-%d %H:%M"), user, uid, sel_s, iss_q))
                conn.commit()
                st.success("Issued successfully.")
