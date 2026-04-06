import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io

# --- 1. DATABASE ENGINE ---
def init_db():
    conn = sqlite3.connect('jnf_elect_pro_v6.db', check_same_thread=False)
    c = conn.cursor()
    # Templates
    c.execute('CREATE TABLE IF NOT EXISTS baselines (id INTEGER PRIMARY KEY, type_name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS baseline_items (id INTEGER PRIMARY KEY, b_id INTEGER, item TEXT, qty REAL, cost REAL)')
    # Projects
    c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT, date_created TEXT)')
    # Units / Pods
    c.execute('''CREATE TABLE IF NOT EXISTS site_units 
                 (id INTEGER PRIMARY KEY, project_id INTEGER, unit_no TEXT, baseline_type TEXT, 
                  first_fix INT DEFAULT 0, wiring INT DEFAULT 0, second_fix INT DEFAULT 0, testing INT DEFAULT 0)''')
    # Unplanned / Adjustments
    c.execute('CREATE TABLE IF NOT EXISTS unit_adjustments (id INTEGER PRIMARY KEY, unit_id INTEGER, item TEXT, adj_qty REAL, adj_cost REAL, reason TEXT)')
    # Stores & Issues
    c.execute('CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, item TEXT, available_qty REAL, price REAL)')
    c.execute('''CREATE TABLE IF NOT EXISTS store_issues 
                 (id INTEGER PRIMARY KEY, timestamp TEXT, user TEXT, unit_id INTEGER, item TEXT, qty_issued REAL)''')
    conn.commit()
    return conn

conn = init_db()

# --- 2. INTERFACE & STYLE ---
st.set_page_config(page_title="JNF Elect Pro-Manager", layout="wide")
st.sidebar.title("⚡ JNF Elect ERP")
user = st.sidebar.text_input("User:", "Quinton")

menu = ["📈 Projects & Dashboard", "🏠 Baseline Templates", "📦 Stores Control"]
choice = st.sidebar.radio("Navigation", menu)

# --- 3. PROJECTS & MASTER DASHBOARD ---
if choice == "📈 Projects & Dashboard":
    st.header("Project & Unit Control Center")
    
    with st.expander("➕ Start New Project"):
        p_name = st.text_input("Project Name")
        if st.button("Initialize"):
            conn.execute("INSERT INTO projects (name, date_created) VALUES (?,?)", (p_name, datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            st.rerun()

    projects = pd.read_sql_query("SELECT * FROM projects", conn)
    for _, p in projects.iterrows():
        # Calculate Project Cost including Baselines + Extras
        cost_q = f"""
            SELECT SUM(total) FROM (
                SELECT SUM(bi.qty * bi.cost) as total FROM site_units su 
                JOIN baselines b ON su.baseline_type = b.type_name
                JOIN baseline_items bi ON b.id = bi.b_id WHERE su.project_id = {p['id']}
                UNION ALL
                SELECT SUM(ua.adj_qty * ua.adj_cost) as total FROM unit_adjustments ua
                JOIN site_units su ON ua.unit_id = su.id WHERE su.project_id = {p['id']}
            )
        """
        total_p_cost = conn.execute(cost_q).fetchone()[0] or 0.0
        
        with st.container(border=True):
            col_a, col_b = st.columns([3,1])
            col_a.subheader(f"🏗️ Project: {p['name']}")
            col_b.metric("Project Total Cost", f"R {total_p_cost:,.2f}")
            
            # --- DRILL DOWN INTO UNITS ---
            with st.expander(f"Manage Units for {p['name']}"):
                # Add Unit Form
                with st.form(f"add_u_{p['id']}"):
                    c1, c2 = st.columns(2)
                    u_no = c1.text_input("Unit/Pod ID (e.g. 101, Gym)")
                    bls = pd.read_sql_query("SELECT type_name FROM baselines", conn)
                    u_bl = c2.selectbox("Apply Plan", bls['type_name'] if not bls.empty else ["None"])
                    if st.form_submit_button("Allocate Unit"):
                        conn.execute("INSERT INTO site_units (project_id, unit_no, baseline_type) VALUES (?,?,?)", (p['id'], u_no, u_bl))
                        conn.commit()
                        st.rerun()

                # List Units with Status and Comparison
                units = pd.read_sql_query(f"SELECT * FROM site_units WHERE project_id = {p['id']}", conn)
                for _, u in units.iterrows():
                    st.divider()
                    st.markdown(f"#### Unit: {u['unit_no']} (Plan: {u['baseline_type']})")
                    
                    # Progress Section
                    pc1, pc2, pc3, pc4 = st.columns(4)
                    f_fix = pc1.checkbox("1st Fix", value=bool(u['first_fix']), key=f"f{u['id']}")
                    wire = pc2.checkbox("Wiring", value=bool(u['wiring']), key=f"w{u['id']}")
                    s_fix = pc3.checkbox("2nd Fix", value=bool(u['second_fix']), key=f"s{u['id']}")
                    test = pc4.checkbox("Testing", value=bool(u['testing']), key=f"t{u['id']}")
                    
                    if st.button("Update Progress", key=f"btn_p_{u['id']}"):
                        conn.execute(f"UPDATE site_units SET first_fix={int(f_fix)}, wiring={int(wire)}, second_fix={int(s_fix)}, testing={int(test)} WHERE id={u['id']}")
                        conn.commit()
                        st.success("Progress Saved")

                    # PLANNED VS ACTUAL TABLE
                    st.write("**Material Variance (Planned vs Issued)**")
                    
                    # Get Baseline Qty
                    base_id = pd.read_sql_query(f"SELECT id FROM baselines WHERE type_name='{u['baseline_type']}'", conn).iloc[0,0]
                    planned_df = pd.read_sql_query(f"SELECT item, qty as Planned FROM baseline_items WHERE b_id={base_id}", conn)
                    
                    # Get Issued Qty from Stores
                    issued_df = pd.read_sql_query(f"SELECT item, SUM(qty_issued) as Issued FROM store_issues WHERE unit_id={u['id']} GROUP BY item", conn)
                    
                    # Merge and Highlight
                    compare_df = pd.merge(planned_df, issued_df, on='item', how='outer').fillna(0)
                    compare_df['Variance'] = compare_df['Issued'] - compare_df['Planned']
                    
                    def highlight_variance(val):
                        color = 'red' if val > 0 else 'green' if val < 0 else 'white'
                        return f'color: {color}'
                    
                    st.dataframe(compare_df.style.applymap(highlight_variance, subset=['Variance']), hide_index=True, use_container_width=True)

                    # Add Unplanned Extras for this Unit
                    with st.form(f"extra_{u['id']}"):
                        st.write("✏️ Add Unplanned Material/Cost Adjustment")
                        ex1, ex2, ex3, ex4 = st.columns([2,1,1,2])
                        ex_item = ex1.text_input("Item Name")
                        ex_qty = ex2.number_input("Qty", value=0.0)
                        ex_cost = ex3.number_input("Price", value=0.0)
                        ex_reason = ex4.text_input("Reason (e.g. Blocked Pipes)")
                        if st.form_submit_button("Add Unplanned Cost"):
                            conn.execute("INSERT INTO unit_adjustments (unit_id, item, adj_qty, adj_cost, reason) VALUES (?,?,?,?,?)", 
                                         (u['id'], ex_item, ex_qty, ex_cost, ex_reason))
                            conn.commit()
                            st.rerun()

# --- 4. BASELINE TEMPLATES ---
elif choice == "🏠 Baseline Templates":
    st.header("Master Plans (Initial Designs)")
    # [Code for adding Template items - same as before, keeping it clean]
    name = st.text_input("Template Name")
    if st.button("Create"):
        conn.execute("INSERT INTO baselines (type_name) VALUES (?)", (name,))
        conn.commit()

# --- 5. STORES CONTROL ---
elif choice == "📦 Stores Control":
    st.header("Stores & Site Issuing")
    t1, t2 = st.tabs(["Warehouse Inventory", "Issue Stock to Unit"])
    # [Standard Stock Logic, but issuing specifically to Unit ID]
