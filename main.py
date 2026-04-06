import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. DATABASE ENGINE (ZERO-FAIL CONNECT) ---
def get_connection():
    return sqlite3.connect('jnf_master_intel_v16.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE, budget REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS blueprints (id INTEGER PRIMARY KEY, project_id INTEGER, type_name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS blueprint_items (id INTEGER PRIMARY KEY, b_id INTEGER, item TEXT, qty REAL, uom TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS units 
                 (id INTEGER PRIMARY KEY, project_id INTEGER, unit_no TEXT, blueprint_id INTEGER, 
                  f_fix INT DEFAULT 0, wire INT DEFAULT 0, s_fix INT DEFAULT 0, test INT DEFAULT 0)''')
    c.execute('CREATE TABLE IF NOT EXISTS unit_variations (id INTEGER PRIMARY KEY, unit_id INTEGER, item TEXT, qty REAL, uom TEXT, price REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, item TEXT UNIQUE, available REAL, price REAL, uom TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS issued_stock (id INTEGER PRIMARY KEY, unit_id INTEGER, item TEXT, qty REAL)')
    conn.commit()
    conn.close()

init_db()

# --- 2. INTERFACE & STYLE ---
st.set_page_config(page_title="JNF Master Intelligence", layout="wide")
st.sidebar.title("⚡ JNF COMMAND")
user = st.sidebar.text_input("Project Authority:", "Quinton")
menu = ["📊 Project Command", "📋 Blueprint Engine", "📦 Stores & Logistics"]
choice = st.sidebar.radio("Navigate System", menu)

# --- 3. PROJECT COMMAND (DASHBOARD & UNIT EXTRAS) ---
if choice == "📊 Project Command":
    st.header("Executive Project Command")
    conn = get_connection()
    
    with st.expander("🚀 Launch New Project Site"):
        c1, c2 = st.columns(2)
        p_name = c1.text_input("Project Name")
        p_budget = c2.number_input("Contract Value (R)", min_value=0.0)
        if st.button("Initialize Project"):
            conn.execute("INSERT OR IGNORE INTO projects (name, budget) VALUES (?,?)", (p_name, p_budget))
            conn.commit()
            st.rerun()

    projects = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    for _, p in projects.iterrows():
        with st.container(border=True):
            st.subheader(f"🏗️ SITE: {p['name']}")
            
            # Dashboard Calculations
            units = pd.read_sql_query(f"SELECT * FROM units WHERE project_id={p['id']}", conn)
            
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Units Allocated", len(units))
            
            # Financial Health Logic
            cost_q = f"""
                SELECT SUM(bi.qty * IFNULL(s.price, 0)) FROM units u
                JOIN blueprint_items bi ON u.blueprint_id = bi.id
                LEFT JOIN stores s ON bi.item = s.item
                WHERE u.project_id = {p['id']}
            """
            total_cost = conn.execute(cost_q).fetchone()[0] or 0.0
            mc2.metric("Total Material Cost", f"R {total_cost:,.2f}")
            mc3.metric("Project Profit (Est)", f"R {(p['budget'] - total_cost):,.2f}")

            # Unit Interaction
            tab_u, tab_v = st.tabs(["Unit Progress", "Variation Orders (Extras)"])
            
            with tab_u:
                for _, u in units.iterrows():
                    st.write(f"**Unit {u['unit_no']}**")
                    ck1, ck2, ck3, ck4, ck5 = st.columns(5)
                    f1 = ck1.checkbox("1st Fix", value=u['f_fix'], key=f"f1_{u['id']}")
                    f2 = ck2.checkbox("Wire", value=u['wire'], key=f"f2_{u['id']}")
                    f3 = ck3.checkbox("2nd Fix", value=u['s_fix'], key=f"f3_{u['id']}")
                    f4 = ck4.checkbox("Test", value=u['test'], key=f"f4_{u['id']}")
                    if ck5.button("SAVE STATUS", key=f"sv_{u['id']}"):
                        conn.execute(f"UPDATE units SET f_fix={int(f1)}, wire={int(f2)}, s_fix={int(f3)}, test={int(f4)} WHERE id={u['id']}")
                        conn.commit()
                        st.rerun()

            with tab_v:
                st.info("Add Customer-requested extras to a specific unit below.")
                sel_unit = st.selectbox("Select Unit for Variation", units['unit_no'] if not units.empty else ["None"], key=f"su_{p['id']}")
                if sel_unit != "None":
                    uid = units[units['unit_no'] == sel_unit]['id'].values[0]
                    vc1, vc2, vc3, vc4 = st.columns([3,1,1,1])
                    v_it = vc1.text_input("Extra Description", key=f"vi_{uid}")
                    v_qt = vc2.number_input("Qty", key=f"vq_{uid}")
                    v_um = vc3.selectbox("Unit", ["Meters", "Units", "Rolls"], key=f"vu_{uid}")
                    v_pr = vc4.number_input("Price (Charge to Client)", key=f"vp_{uid}")
                    if st.button("Add Variation Order", key=f"vb_{uid}"):
                        conn.execute("INSERT INTO unit_variations (unit_id, item, qty, uom, price) VALUES (?,?,?,?,?)", (uid, v_it, v_qt, v_um, v_pr))
                        conn.commit()
                        st.rerun()
                    
                    vars_df = pd.read_sql_query(f"SELECT item, qty, uom, price, (qty*price) as total FROM unit_variations WHERE unit_id={uid}", conn)
                    st.dataframe(vars_df, use_container_width=True)

# --- 4. BLUEPRINT ENGINE (THE "QUOTE" GENERATOR) ---
elif choice == "📋 Blueprint Engine":
    st.header("Master Blueprint & Quotation Engine")
    conn = get_connection()
    
    projs = pd.read_sql_query("SELECT * FROM projects", conn)
    if projs.empty:
        st.error("No projects found. Create a project first.")
    else:
        sel_p = st.selectbox("Link Blueprint to Site:", projs['name'])
        pid = projs[projs['name'] == sel_p]['id'].values[0]
        
        b_name = st.text_input("New Blueprint Name (e.g. Type E - 3 Bed)")
        if st.button("Create Master Blueprint"):
            conn.execute("INSERT INTO blueprints (project_id, type_name) VALUES (?,?)", (pid, b_name))
            conn.commit()
            st.rerun()
            
        blueprints = pd.read_sql_query(f"SELECT * FROM blueprints WHERE project_id = {pid}", conn)
        if not blueprints.empty:
            sel_b = st.selectbox("Currently Designing:", blueprints['type_name'])
            bid = blueprints[blueprints['type_name'] == sel_b]['id'].values[0]
            
            st.divider()
            st.subheader(f"📋 Bill of Quantities: {sel_b}")
            c1, c2, c3 = st.columns([3,1,1])
            m_it = c1.text_input("Material Item (Search Stores or Type New)")
            m_qt = c2.number_input("Standard Qty", min_value=0.0)
            m_um = c3.selectbox("Unit", ["Meters", "Units", "Rolls", "Boxes", "Liters"])
            
            if st.button("ADD TO BLUEPRINT"):
                if m_it:
                    conn.execute("INSERT INTO blueprint_items (b_id, item, qty, uom) VALUES (?,?,?,?)", (bid, m_it, m_qt, m_um))
                    conn.commit()
                    st.rerun()
            
            # THE "QUOTE" LIST
            items_df = pd.read_sql_query(f"""
                SELECT bi.id, bi.item as 'Description', bi.qty as 'Qty', bi.uom as 'Unit', 
                IFNULL(s.price, 0) as 'Rate', (bi.qty * IFNULL(s.price, 0)) as 'Subtotal'
                FROM blueprint_items bi 
                LEFT JOIN stores s ON bi.item = s.item 
                WHERE bi.b_id = {bid}""", conn)
            
            if not items_df.empty:
                st.table(items_df.drop(columns=['id']))
                st.metric(f"Total Design Value ({sel_b})", f"R {items_df['Subtotal'].sum():,.2f}")
                
                # Dynamic Delete
                to_del = st.selectbox("Select Item to Delete", items_df['Description'])
                if st.button("🗑️ Remove Line Item"):
                    conn.execute(f"DELETE FROM blueprint_items WHERE b_id={bid} AND item='{to_del}'")
                    conn.commit()
                    st.rerun()

# --- 5. STORES & LOGISTICS ---
elif choice == "📦 Stores & Logistics":
    st.header("Stores Control & Master Pricing")
    conn = get_connection()
    c1, c2, c3, c4 = st.columns([3,1,1,1])
    s_it = c1.text_input("Material Description")
    s_avail = c2.number_input("Current Stock")
    s_pr = c3.number_input("Unit Cost (Supplier Price)")
    s_um = c4.selectbox("Unit", ["Meters", "Units", "Rolls", "Boxes"])
    
    if st.button("Sync Store Item"):
        conn.execute("INSERT OR REPLACE INTO stores (item, available, price, uom) VALUES (?,?,?,?)", (s_it, s_avail, s_pr, s_um))
        conn.commit()
        st.rerun()
    
    st.divider()
    inventory = pd.read_sql_query("SELECT item, available as 'Stock', price as 'Unit Cost', uom as 'Unit' FROM stores", conn)
    st.dataframe(inventory, use_container_width=True)
