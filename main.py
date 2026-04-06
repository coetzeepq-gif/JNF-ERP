import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. DATABASE ENGINE (INDUSTRIAL LOCK) ---
def get_connection():
    return sqlite3.connect('jnf_elect_PRO_v21.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    c.execute('CREATE TABLE IF NOT EXISTS blueprints (id INTEGER PRIMARY KEY, project_id INTEGER, name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS blueprint_items (id INTEGER PRIMARY KEY, b_id INTEGER, item TEXT, qty REAL, uom TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS units 
                 (id INTEGER PRIMARY KEY, project_id INTEGER, unit_no TEXT, blueprint_id INTEGER, 
                  f_fix INT DEFAULT 0, wire INT DEFAULT 0, s_fix INT DEFAULT 0, test INT DEFAULT 0)''')
    c.execute('CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, item TEXT UNIQUE, available REAL, price REAL, uom TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- 2. INTERFACE & NAVIGATION ---
st.set_page_config(page_title="JNF Elect PRO-ERP", layout="wide")
st.sidebar.title("⚡ JNF COMMAND CENTER")
user = st.sidebar.text_input("Project Authority:", "Quinton")
menu = ["📊 Dashboard", "🏗️ Project & Blueprint Control", "📦 Stores & Procurement"]
choice = st.sidebar.radio("Navigation", menu)

# --- 3. DASHBOARD ---
if choice == "📊 Dashboard":
    st.header("Executive Site Health")
    conn = get_connection()
    projects = pd.read_sql_query("SELECT * FROM projects", conn)
    
    if projects.empty:
        st.info("No active projects. Initialize a site in 'Project Control'.")
    else:
        for _, p in projects.iterrows():
            with st.container(border=True):
                col1, col2, col3 = st.columns([2,1,1])
                u_df = pd.read_sql_query(f"SELECT f_fix, wire, s_fix, test FROM units WHERE project_id={p['id']}", conn)
                prog = (u_df.sum().sum() / (len(u_df)*4)) if not u_df.empty else 0
                
                cost_q = f"""
                    SELECT SUM(bi.qty * IFNULL(s.price, 0)) FROM units u
                    JOIN blueprint_items bi ON u.blueprint_id = bi.b_id
                    LEFT JOIN stores s ON bi.item = s.item
                    WHERE u.project_id = {p['id']}
                """
                val = conn.execute(cost_q).fetchone()[0] or 0.0
                
                col1.subheader(f"Project: {p['name']}")
                col2.metric("Completion", f"{int(prog*100)}%")
                col3.metric("Project Material Value", f"R {val:,.2f}")

# --- 4. PROJECT & BLUEPRINT CONTROL (THE BRAIN) ---
elif choice == "🏗️ Project & Blueprint Control":
    st.header("Site Operations & Blueprinting")
    conn = get_connection()
    
    # 4.1 CREATE PROJECT
    with st.container(border=True):
        st.write("### ➕ Launch New Project Site")
        p_name = st.text_input("Project Name (e.g. Atlantic Heights)")
        if st.button("Initialize Site"):
            if p_name:
                conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (p_name,))
                conn.commit()
                st.success(f"Project {p_name} Created.")
                st.rerun()

    st.divider()
    
    # 4.2 MANAGE ACTIVE PROJECTS
    projs = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    for _, p in projs.iterrows():
        with st.expander(f"📂 PROJECT: {p['name']}", expanded=True):
            
            # --- SECTION A: BLUEPRINT DESIGNER ---
            st.write("### 📋 Step 1: Design Blueprints (Quotes)")
            bc1, bc2 = st.columns([3,1])
            new_b = bc1.text_input(f"New Blueprint for {p['name']}", placeholder="e.g. House Type E", key=f"bi_{p['id']}")
            if bc2.button("Save Blueprint", key=f"bs_{p['id']}"):
                conn.execute("INSERT INTO blueprints (project_id, name) VALUES (?,?)", (p['id'], new_b))
                conn.commit()
                st.rerun()
            
            # Show Blueprints for this Project
            bl_df = pd.read_sql_query(f"SELECT * FROM blueprints WHERE project_id={p['id']}", conn)
            for _, b in bl_df.iterrows():
                with st.container(border=True):
                    st.write(f"**Material List for: {b['name']}**")
                    
                    # Add Item
                    ic1, ic2, ic3, ic4 = st.columns([3,1,1,1])
                    m_n = ic1.text_input("Material", key=f"mn_{b['id']}")
                    m_q = ic2.number_input("Qty", min_value=0.0, key=f"mq_{b['id']}")
                    m_u = ic3.selectbox("Unit", ["Meters", "Units", "Rolls", "Boxes"], key=f"mu_{b['id']}")
                    if ic4.button("Add Item", key=f"ab_{b['id']}"):
                        conn.execute("INSERT INTO blueprint_items (b_id, item, qty, uom) VALUES (?,?,?,?)", (b['id'], m_n, m_q, m_u))
                        conn.commit()
                        st.rerun()
                    
                    # The Quote Table
                    quote_df = pd.read_sql_query(f"""
                        SELECT bi.id, bi.item, bi.qty, bi.uom, IFNULL(s.price, 0) as 'Price', (bi.qty * IFNULL(s.price, 0)) as 'Subtotal'
                        FROM blueprint_items bi LEFT JOIN stores s ON bi.item = s.item WHERE bi.b_id = {b['id']}
                    """, conn)
                    if not quote_df.empty:
                        st.table(quote_df.drop(columns=['id']))
                        st.write(f"**Total Blueprint Value:** R {quote_df['Subtotal'].sum():,.2f}")
                        if st.button("🗑️ Delete Blueprint", key=f"db_{b['id']}"):
                            conn.execute(f"DELETE FROM blueprints WHERE id={b['id']}")
                            conn.commit()
                            st.rerun()

            # --- SECTION B: UNIT TRACKING ---
            st.divider()
            st.write("### 🏗️ Step 2: Allocate Units & Track Progress")
            uc1, uc2, uc3 = st.columns([2,2,1])
            u_no = uc1.text_input("Unit/Yard No", key=f"uno_{p['id']}")
            u_bl = uc2.selectbox("Apply Blueprint", bl_df['name'] if not bl_df.empty else ["No Designs"], key=f"ubl_{p['id']}")
            if uc3.button("Link Unit", key=f"ul_{p['id']}"):
                bid_match = bl_df[bl_df['name'] == u_bl]['id'].values[0]
                conn.execute("INSERT INTO units (project_id, unit_no, blueprint_id) VALUES (?,?,?)", (p['id'], u_no, bid_match))
                conn.commit()
                st.rerun()
            
            # Show Units
            u_list = pd.read_sql_query(f"SELECT * FROM units WHERE project_id={p['id']}", conn)
            for _, u in u_list.iterrows():
                with st.container(border=True):
                    sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(6)
                    sc1.write(f"**Unit {u['unit_no']}**")
                    f1 = sc2.checkbox("1st Fix", value=u['f_fix'], key=f"f1_{u['id']}")
                    f2 = sc3.checkbox("Wire", value=u['wire'], key=f"f2_{u['id']}")
                    f3 = sc4.checkbox("2nd Fix", value=u['s_fix'], key=f"f3_{u['id']}")
                    f4 = sc5.checkbox("Test", value=u['test'], key=f"f4_{u['id']}")
                    if sc6.button("Save", key=f"sv_{u['id']}"):
                        conn.execute(f"UPDATE units SET f_fix={int(f1)}, wire={int(f2)}, s_fix={int(f3)}, test={int(f4)} WHERE id={u['id']}")
                        conn.commit()
                        st.success("Updated.")

# --- 5. STORES & PROCUREMENT ---
elif choice == "📦 Stores & Procurement":
    st.header("Inventory Management")
    conn = get_connection()
    c1, c2, c3, c4 = st.columns([3,1,1,1])
    s_it = c1.text_input("Material Name")
    s_q = c2.number_input("Stock Qty", min_value=0.0)
    s_p = c3.number_input("Unit Price", min_value=0.0)
    s_u = c4.selectbox("Unit", ["Meters", "Units", "Rolls", "Boxes"])
    
    if st.button("Sync Store"):
        conn.execute("INSERT OR REPLACE INTO stores (item, available, price, uom) VALUES (?,?,?,?)", (s_it, s_q, s_p, s_u))
        conn.commit()
        st.rerun()
    
    st.divider()
    st.write("### Current Stock List")
    st.table(pd.read_sql_query("SELECT item, available, price, uom FROM stores", conn))
