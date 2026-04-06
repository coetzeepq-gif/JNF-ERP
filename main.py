import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. DATABASE ENGINE ---
def get_connection():
    # Use a specific versioned DB to ensure a fresh start
    return sqlite3.connect('jnf_master_final_v17.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    c.execute('CREATE TABLE IF NOT EXISTS blueprints (id INTEGER PRIMARY KEY, project_id INTEGER, type_name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS blueprint_items (id INTEGER PRIMARY KEY, b_id INTEGER, item TEXT, qty REAL, uom TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, item TEXT UNIQUE, available REAL, price REAL, uom TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS units 
                 (id INTEGER PRIMARY KEY, project_id INTEGER, unit_no TEXT, blueprint_id INTEGER, 
                  f_fix INT DEFAULT 0, wire INT DEFAULT 0, s_fix INT DEFAULT 0, test INT DEFAULT 0)''')
    conn.commit()
    conn.close()

init_db()

# --- 2. NAVIGATION ---
st.set_page_config(page_title="JNF Elect ERP", layout="wide")
st.sidebar.title("⚡ JNF COMMAND")
menu = ["🏗️ Project & Unit Dashboard", "📋 Blueprint Designer", "📦 Stores Control"]
choice = st.sidebar.radio("Navigation", menu)

# --- 3. BLUEPRINT DESIGNER (FIXED) ---
if choice == "📋 Blueprint Designer":
    st.header("Blueprint Master Registry")
    conn = get_connection()
    
    # STEP 1: SELECT PROJECT
    projs = pd.read_sql_query("SELECT * FROM projects", conn)
    if projs.empty:
        st.error("⚠️ No Projects Found. Go to 'Project Dashboard' and create a project first.")
    else:
        sel_p = st.selectbox("Assign Blueprint to Project:", projs['name'])
        pid = projs[projs['name'] == sel_p]['id'].values[0]
        
        st.divider()
        
        # STEP 2: CREATE THE BLUEPRINT NAME
        st.subheader("Create New Blueprint")
        col_name, col_btn = st.columns([3,1])
        b_name_input = col_name.text_input("Blueprint Name (e.g., House Type E, Gym, Pod A)", placeholder="Type name here...")
        
        if col_btn.button("🔥 CREATE BLUEPRINT", use_container_width=True):
            if b_name_input:
                conn.execute("INSERT INTO blueprints (project_id, type_name) VALUES (?,?)", (pid, b_name_input))
                conn.commit()
                st.success(f"Successfully Created: {b_name_input}")
                st.rerun()
            else:
                st.warning("Please enter a name first.")

        # STEP 3: ADD MATERIALS TO THE SELECTED BLUEPRINT
        st.divider()
        blueprints = pd.read_sql_query(f"SELECT * FROM blueprints WHERE project_id = {pid}", conn)
        
        if not blueprints.empty:
            sel_b = st.selectbox("Select Blueprint to Edit Materials:", blueprints['type_name'])
            bid = blueprints[blueprints['type_name'] == sel_b]['id'].values[0]
            
            with st.container(border=True):
                st.write(f"### 🛠️ Editing Bill of Materials: {sel_b}")
                c1, c2, c3 = st.columns([3,1,1])
                m_it = c1.text_input("Material Item (e.g., 20mm Conduit)")
                m_qt = c2.number_input("Qty", min_value=0.0, step=1.0)
                m_um = c3.selectbox("Unit", ["Meters", "Units", "Rolls", "Boxes"])
                
                if st.button("➕ ADD TO LIST", use_container_width=True):
                    if m_it:
                        conn.execute("INSERT INTO blueprint_items (b_id, item, qty, uom) VALUES (?,?,?,?)", (bid, m_it, m_qt, m_um))
                        conn.commit()
                        st.rerun()

            # --- THE "QUOTE" VIEW (VISIBLE LIST) ---
            st.markdown("### **Current Blueprint / Quote List**")
            items_df = pd.read_sql_query(f"""
                SELECT bi.id, bi.item as 'Material', bi.qty as 'Qty', bi.uom as 'Unit', 
                IFNULL(s.price, 0) as 'Rate', (bi.qty * IFNULL(s.price, 0)) as 'Subtotal'
                FROM blueprint_items bi 
                LEFT JOIN stores s ON bi.item = s.item 
                WHERE bi.b_id = {bid}""", conn)
            
            if not items_df.empty:
                st.dataframe(items_df.drop(columns=['id']), use_container_width=True, hide_index=True)
                st.metric("Estimated Material Cost", f"R {items_df['Subtotal'].sum():,.2f}")
                
                # Delete Item
                to_del = st.selectbox("Select Item to Remove", items_df['Material'].tolist())
                if st.button("🗑️ Delete Line Item"):
                    conn.execute(f"DELETE FROM blueprint_items WHERE b_id={bid} AND item='{to_del}'")
                    conn.commit()
                    st.rerun()
            else:
                st.info("No materials added to this blueprint yet.")
        conn.close()

# --- 4. PROJECT DASHBOARD ---
elif choice == "🏗️ Project & Unit Dashboard":
    st.header("Site Control Center")
    conn = get_connection()
    
    # Create Project
    p_name = st.text_input("New Project Name")
    if st.button("Launch Project Site"):
        if p_name:
            conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (p_name,))
            conn.commit()
            st.rerun()
            
    st.divider()
    
    # Display Sites
    projs = pd.read_sql_query("SELECT * FROM projects", conn)
    for _, p in projs.iterrows():
        with st.expander(f"📂 Site: {p['name']}", expanded=True):
            # Add Unit logic stays here...
            st.write("Manage units and track progress for this site.")

# --- 5. STORES CONTROL ---
elif choice == "📦 Stores Control":
    st.header("Warehouse Stock & Pricing")
    conn = get_connection()
    c1, c2, c3, c4 = st.columns([3,1,1,1])
    s_it = c1.text_input("Material Description")
    s_aq = c2.number_input("Qty Available", min_value=0.0)
    s_pr = c3.number_input("Unit Price", min_value=0.0)
    s_um = c4.selectbox("Unit", ["Meters", "Units", "Rolls", "Boxes"])
    
    if st.button("Sync Stores"):
        conn.execute("INSERT OR REPLACE INTO stores (item, available, price, uom) VALUES (?,?,?,?)", (s_it, s_aq, s_pr, s_um))
        conn.commit()
        st.rerun()
    st.table(pd.read_sql_query("SELECT * FROM stores", conn))
    conn.close()
