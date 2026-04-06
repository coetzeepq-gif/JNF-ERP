import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io

# --- 1. DATABASE ENGINE ---
def get_connection():
    return sqlite3.connect('jnf_pro_erp_v11.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE, status TEXT DEFAULT "Active")')
    c.execute('CREATE TABLE IF NOT EXISTS baselines (id INTEGER PRIMARY KEY, project_id INTEGER, type_name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS baseline_items (id INTEGER PRIMARY KEY, b_id INTEGER, item TEXT, qty REAL, uom TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS site_units 
                 (id INTEGER PRIMARY KEY, project_id INTEGER, unit_no TEXT, baseline_id INTEGER, 
                  f_fix INT DEFAULT 0, wire INT DEFAULT 0, s_fix INT DEFAULT 0, test INT DEFAULT 0)''')
    c.execute('CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, item TEXT UNIQUE, available REAL, price REAL, uom TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS store_issues (id INTEGER PRIMARY KEY, ts TEXT, user TEXT, unit_id INTEGER, item TEXT, qty REAL)')
    conn.commit()
    conn.close()

init_db()

# --- 2. LAYOUT & THEME ---
st.set_page_config(page_title="JNF Elect Pro-Manager", layout="wide")
st.sidebar.title("⚡ JNF ERP SYSTEM")
user = st.sidebar.text_input("Project Manager:", "Quinton")
menu = ["📊 Executive Dashboard", "🏗️ Project Site Control", "📦 Warehouse & Procurement"]
choice = st.sidebar.radio("Navigation", menu)

# --- 3. EXECUTIVE DASHBOARD (MY LOGIC: OVERVIEW) ---
if choice == "📊 Executive Dashboard":
    st.header("Site Health & Financials")
    conn = get_connection()
    projects = pd.read_sql_query("SELECT * FROM projects", conn)
    
    if projects.empty:
        st.info("No active projects. Start one in Site Control.")
    else:
        for _, p in projects.iterrows():
            # Calculate completion %
            units = pd.read_sql_query(f"SELECT f_fix, wire, s_fix, test FROM site_units WHERE project_id={p['id']}", conn)
            total_tasks = len(units) * 4
            done_tasks = units.sum().sum() if not units.empty else 0
            progress = (done_tasks / total_tasks) if total_tasks > 0 else 0
            
            with st.container(border=True):
                col1, col2, col3 = st.columns([2,1,1])
                col1.subheader(f"Project: {p['name']}")
                col2.progress(progress)
                col2.write(f"Completion: {int(progress*100)}%")
                
                # Financial logic
                cost_q = f"""
                    SELECT SUM(bi.qty * IFNULL(s.price, 0)) FROM site_units su
                    JOIN baseline_items bi ON su.baseline_id = bi.b_id
                    LEFT JOIN stores s ON bi.item = s.item
                    WHERE su.project_id = {p['id']}
                """
                total_val = conn.execute(cost_q).fetchone()[0] or 0.0
                col3.metric("Current Value", f"R {total_val:,.2f}")

# --- 4. PROJECT SITE CONTROL (UNIT & PLAN MANAGEMENT) ---
elif choice == "🏗️ Project Site Control":
    st.header("Project Site Manager")
    
    with st.expander("➕ Initialize New Site"):
        p_name = st.text_input("New Site Name")
        if st.button("Launch Project"):
            conn = get_connection()
            conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (p_name,))
            conn.commit()
            st.rerun()

    conn = get_connection()
    projects = pd.read_sql_query("SELECT * FROM projects", conn)
    for _, p in projects.iterrows():
        with st.expander(f"📂 {p['name']}", expanded=True):
            tab1, tab2 = st.tabs(["Design Blueprints", "Unit Tracking"])
            
            with tab1:
                st.subheader("Project Templates")
                b_name = st.text_input("New Design (e.g. Type A)", key=f"bn_{p['id']}")
                if st.button("Save Design", key=f"bb_{p['id']}"):
                    conn.execute("INSERT INTO baselines (project_id, type_name) VALUES (?,?)", (p['id'], b_name))
                    conn.commit()
                    st.rerun()
                
                bases = pd.read_sql_query(f"SELECT * FROM baselines WHERE project_id = {p['id']}", conn)
                if not bases.empty:
                    sel_b = st.selectbox("Edit Blueprint", bases['type_name'], key=f"sb_{p['id']}")
                    bid = bases[bases['type_name'] == sel_b]['id'].values[0]
                    
                    c1, c2, c3 = st.columns([3,1,1])
                    m_n = c1.text_input("Material", key=f"mn_{bid}")
                    m_q = c2.number_input("Qty", min_value=0.0, key=f"mq_{bid}")
                    m_u = c3.selectbox("Unit", ["Units", "Meters", "Rolls", "Boxes"], key=f"mu_{bid}")
                    
                    if st.button("Add to Blueprint", key=f"ab_{bid}"):
                        conn.execute("INSERT INTO baseline_items (b_id, item, qty, uom) VALUES (?,?,?,?)", (bid, m_n, m_q, m_u))
                        conn.commit()
                        st.rerun()
                    
                    # Display with Delete
                    m_df = pd.read_sql_query(f"SELECT id, item, qty, uom FROM baseline_items WHERE b_id={bid}", conn)
                    for _, row in m_df.iterrows():
                        col_x, col_y, col_z = st.columns([4,1,1])
                        col_x.write(f"{row['item']} ({row['qty']} {row['uom']})")
                        if col_y.button("🗑️", key=f"del_{row['id']}"):
                            conn.execute(f"DELETE FROM baseline_items WHERE id={row['id']}")
                            conn.commit()
                            st.rerun()

            with tab2:
                # Unit Logic
                st.subheader("Site Units")
                cu1, cu2 = st.columns(2)
                u_no = cu1.text_input("Unit No", key=f"uno_{p['id']}")
                u_bl = cu2.selectbox("Apply Design", bases['type_name'] if not bases.empty else ["None"], key=f"ubl_{p['id']}")
                if st.button("Allocate to Site", key=f"al_{p['id']}"):
                    bl_id = bases[bases['type_name'] == u_bl]['id'].values[0]
                    conn.execute("INSERT INTO site_units (project_id, unit_no, baseline_id) VALUES (?,?,?)", (p['id'], u_no, bl_id))
                    conn.commit()
                    st.rerun()
                
                # Unit Progress + Theft/Waste Check
                u_df = pd.read_sql_query(f"SELECT * FROM site_units WHERE project_id={p['id']}", conn)
                for _, u in u_df.iterrows():
                    with st.expander(f"Unit {u['unit_no']} - Status"):
                        sc1, sc2, sc3, sc4, sc5 = st.columns(5)
                        ff = sc1.checkbox("1st Fix", value=u['f_fix'], key=f"f1_{u['id']}")
                        wr = sc2.checkbox("Wiring", value=u['wire'], key=f"f2_{u['id']}")
                        sf = sc3.checkbox("2nd Fix", value=u['s_fix'], key=f"f3_{u['id']}")
                        ts = sc4.checkbox("Testing", value=u['test'], key=f"f4_{u['id']}")
                        if sc5.button("SAVE PROGRESS", key=f"svu_{u['id']}"):
                            conn.execute(f"UPDATE site_units SET f_fix={int(ff)}, wire={int(wr)}, s_fix={int(sf)}, test={int(ts)} WHERE id={u['id']}")
                            conn.commit()
                            st.rerun()

# --- 5. WAREHOUSE & PROCUREMENT (MY LOGIC: SHORTFALL TRACKER) ---
elif choice == "📦 Warehouse & Procurement":
    st.header("Inventory & Ordering Logic")
    conn = get_connection()
    t1, t2 = st.tabs(["Warehouse Stock", "Shortfall / Order List"])
    
    with t1:
        st.subheader("Update Stock")
        c1, c2, c3, c4 = st.columns([3,1,1,1])
        s_it = c1.text_input("Material")
        s_q = c2.number_input("Qty On Hand", min_value=0.0)
        s_p = c3.number_input("Unit Cost", min_value=0.0)
        s_u = c4.selectbox("Unit", ["Units", "Meters", "Rolls", "Boxes"], key="sku")
        if st.button("Sync Store"):
            conn.execute("INSERT OR REPLACE INTO stores (item, available, price, uom) VALUES (?,?,?,?)", (s_it, s_q, s_p, s_u))
            conn.commit()
            st.rerun()
        st.table(pd.read_sql_query("SELECT item, available, price, uom FROM stores", conn))

    with t2:
        st.subheader("🚨 Automatic Order List (What you are missing)")
        # This logic sums all requirements for ALL units and subtracts current store stock
        query = """
            SELECT bi.item, SUM(bi.qty) as 'Total Required', IFNULL(s.available, 0) as 'Stock on Hand'
            FROM site_units su
            JOIN baseline_items bi ON su.baseline_id = bi.b_id
            LEFT JOIN stores s ON bi.item = s.item
            GROUP BY bi.item
        """
        short_df = pd.read_sql_query(query, conn)
        short_df['Shortfall'] = short_df['Total Required'] - short_df['Stock on Hand']
        # Highlight logic
        def color_short(val):
            return 'background-color: #ffcccc' if val > 0 else ''
        st.dataframe(short_df.style.applymap(color_short, subset=['Shortfall']), use_container_width=True)
