import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io

# --- 1. DATABASE ENGINE (RETAINING ALL HISTORICAL DATA) ---
def get_connection():
    return sqlite3.connect('jnf_elect_PRO_v24.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Permanent Baseline Tables
    c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE, contract_val REAL DEFAULT 0.0)')
    c.execute('CREATE TABLE IF NOT EXISTS blueprints (id INTEGER PRIMARY KEY, project_id INTEGER, name TEXT, UNIQUE(project_id, name))')
    c.execute('CREATE TABLE IF NOT EXISTS blueprint_items (id INTEGER PRIMARY KEY, b_id INTEGER, item TEXT, qty REAL, uom TEXT)')
    # Unit Control with Correct Electrical Stages
    c.execute('''CREATE TABLE IF NOT EXISTS units 
                 (id INTEGER PRIMARY KEY, project_id INTEGER, unit_no TEXT, blueprint_id INTEGER, 
                  first_fix INT DEFAULT 0, piping INT DEFAULT 0, wiring INT DEFAULT 0, fitting INT DEFAULT 0, testing INT DEFAULT 0)''')
    # Extras, Files, and Stores
    c.execute('CREATE TABLE IF NOT EXISTS unit_extras (id INTEGER PRIMARY KEY, unit_id INTEGER, item TEXT, qty REAL, uom TEXT, price REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS unit_files (id INTEGER PRIMARY KEY, unit_id INTEGER, file_name TEXT, file_data BLOB)')
    c.execute('CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, item TEXT UNIQUE, available REAL, price REAL, uom TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- 2. INTERFACE SETTINGS ---
st.set_page_config(page_title="JNF Master ERP v24", layout="wide")
st.sidebar.title("⚡ JNF COMMAND CENTER")
user = st.sidebar.text_input("Project Manager:", "Quinton")
menu = ["📊 Dashboard", "📋 Blueprint Library", "🏗️ Project Site Manager", "📦 Stores & Procurement"]
choice = st.sidebar.radio("Navigation", menu)

# --- 3. DASHBOARD (FINANCIALS & PROGRESS) ---
if choice == "📊 Dashboard":
    st.header("Executive Site Health")
    conn = get_connection()
    projects = pd.read_sql_query("SELECT * FROM projects", conn)
    
    for _, p in projects.iterrows():
        with st.container(border=True):
            col1, col2, col3 = st.columns([2,1,1])
            # Progress calculation
            u_df = pd.read_sql_query(f"SELECT first_fix, piping, wiring, fitting, testing FROM units WHERE project_id={p['id']}", conn)
            prog = (u_df.sum().sum() / (len(u_df)*5)) if not u_df.empty else 0
            
            # Value calculation
            cost_q = f"""
                SELECT SUM(bi.qty * IFNULL(s.price, 0)) FROM units u
                JOIN blueprint_items bi ON u.blueprint_id = bi.b_id
                LEFT JOIN stores s ON bi.item = s.item
                WHERE u.project_id = {p['id']}
            """
            val = conn.execute(cost_q).fetchone()[0] or 0.0
            
            col1.subheader(f"Project: {p['name']}")
            col2.write(f"**Completion:** {int(prog*100)}%")
            col2.progress(prog)
            col3.metric("Material Value", f"R {val:,.2f}")

# --- 4. BLUEPRINT LIBRARY (MANAGE & EDIT QUOTES) ---
elif choice == "📋 Blueprint Library":
    st.header("Master Blueprint & Quote Library")
    conn = get_connection()
    
    all_blueprints = pd.read_sql_query("""
        SELECT b.id, b.name, p.name as project_name 
        FROM blueprints b JOIN projects p ON b.project_id = p.id""", conn)
    
    if all_blueprints.empty:
        st.info("No blueprints created yet. Go to 'Project Site Manager' to create your first design.")
    else:
        sel_b = st.selectbox("Select Blueprint to Edit/View", all_blueprints['name'] + " [" + all_blueprints['project_name'] + "]")
        bid = all_blueprints[all_blueprints['name'] + " [" + all_blueprints['project_name'] + "]" == sel_b]['id'].values[0]
        
        st.divider()
        st.subheader(f"🛠️ Editing Blueprint: {sel_b}")
        
        # Add Material Section
        c1, c2, c3 = st.columns([3,1,1])
        m_it = c1.text_input("Material Name")
        m_qt = c2.number_input("Qty", min_value=0.0)
        m_um = c3.selectbox("Unit", ["Units", "Meters", "Rolls", "Boxes"])
        
        if st.button("Add Item to Blueprint"):
            if m_it:
                conn.execute("INSERT INTO blueprint_items (b_id, item, qty, uom) VALUES (?,?,?,?)", (bid, m_it, m_qt, m_um))
                conn.commit()
                st.rerun()

        # The Visible Quote List
        items = pd.read_sql_query(f"""
            SELECT bi.id, bi.item, bi.qty, bi.uom, IFNULL(s.price, 0) as price, (bi.qty * IFNULL(s.price, 0)) as total 
            FROM blueprint_items bi LEFT JOIN stores s ON bi.item = s.item WHERE bi.b_id = {bid}""", conn)
        
        if not items.empty:
            st.table(items.drop(columns=['id']))
            st.metric("Total Design Value", f"R {items['total'].sum():,.2f}")
            
            # Single Item Delete
            st.write("**Remove Single Item:**")
            to_del = st.selectbox("Select Item to Delete", items['item'])
            if st.button("🗑️ Delete Item"):
                conn.execute(f"DELETE FROM blueprint_items WHERE b_id={bid} AND item='{to_del}'")
                conn.commit()
                st.rerun()
        
        if st.button("🚨 DELETE FULL BLUEPRINT", type="secondary"):
            conn.execute(f"DELETE FROM blueprint_items WHERE b_id={bid}")
            conn.execute(f"DELETE FROM blueprints WHERE id={bid}")
            conn.commit()
            st.rerun()

# --- 5. PROJECT SITE MANAGER (THE CORE ENGINE) ---
elif choice == "🏗️ Project Site Manager":
    st.header("Site Operations Control")
    conn = get_connection()
    
    # Create Project
    with st.container(border=True):
        st.write("### ➕ Launch New Project Site")
        p_name = st.text_input("Project Name")
        if st.button("Save Project"):
            if p_name:
                conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (p_name,))
                conn.commit()
                st.rerun()

    st.divider()
    
    projects = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    for _, p in projects.iterrows():
        with st.expander(f"📂 SITE: {p['name']}", expanded=True):
            tab1, tab2 = st.tabs(["📋 Design Blueprints", "🏗️ Unit Tracking & Extras"])
            
            with tab1:
                st.subheader("1. Create Blueprint for this Site")
                bn = st.text_input("New Blueprint Name", key=f"bn_{p['id']}")
                if st.button("Save Blueprint", key=f"bsb_{p['id']}"):
                    if bn:
                        conn.execute("INSERT INTO blueprints (project_id, name) VALUES (?,?)", (p['id'], bn))
                        conn.commit()
                        st.rerun()
                
                # Show blueprints for this site
                bls = pd.read_sql_query(f"SELECT * FROM blueprints WHERE project_id={p['id']}", conn)
                st.write("**Active Site Blueprints:**")
                st.dataframe(bls[['name']], use_container_width=True)

            with tab2:
                st.subheader("2. Unit Management")
                c1, c2 = st.columns(2)
                u_no = c1.text_input("Unit/Yard No", key=f"u_{p['id']}")
                u_bl = c2.selectbox("Assign Blueprint", bls['name'] if not bls.empty else ["None"], key=f"ub_{p['id']}")
                
                if st.button("Link Unit to Site", key=f"lu_{p['id']}"):
                    bid = bls[bls['name'] == u_bl]['id'].values[0]
                    conn.execute("INSERT INTO units (project_id, unit_no, blueprint_id) VALUES (?,?,?)", (p['id'], u_no, bid))
                    conn.commit()
                    st.rerun()
                
                st.divider()
                # Unit Progress & Extras
                units = pd.read_sql_query(f"""
                    SELECT u.*, b.name as b_type FROM units u 
                    JOIN blueprints b ON u.blueprint_id = b.id 
                    WHERE u.project_id={p['id']}""", conn)
                
                for _, u in units.iterrows():
                    with st.container(border=True):
                        st.write(f"### Unit {u['unit_no']} [{u['b_type']}]")
                        
                        # Correct Electrical Stages
                        sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(6)
                        f1 = sc1.checkbox("1st Fix", value=u['first_fix'], key=f"f1_{u['id']}")
                        f2 = sc2.checkbox("Piping", value=u['piping'], key=f"f2_{u['id']}")
                        f3 = sc3.checkbox("Wiring", value=u['wiring'], key=f"f3_{u['id']}")
                        f4 = sc4.checkbox("Fitting", value=u['fitting'], key=f"f4_{u['id']}")
                        f5 = sc5.checkbox("Testing", value=u['testing'], key=f"f5_{u['id']}")
                        
                        if sc6.button("Save Progress", key=f"sp_{u['id']}"):
                            conn.execute(f"UPDATE units SET first_fix={int(f1)}, piping={int(f2)}, wiring={int(f3)}, fitting={int(f4)}, testing={int(f5)} WHERE id={u['id']}")
                            conn.commit()
                            st.rerun()
                        
                        with st.expander("Customer Extras & Drawings"):
                            # Extras
                            st.write("**Add Extra for this Unit:**")
                            ec1, ec2, ec3 = st.columns([3,1,1])
                            e_it = ec1.text_input("Extra Item", key=f"ei_{u['id']}")
                            e_qt = ec2.number_input("Qty", key=f"eq_{u['id']}")
                            e_pr = ec3.number_input("Price", key=f"ep_{u['id']}")
                            if st.button("Add Extra", key=f"eb_{u['id']}"):
                                conn.execute("INSERT INTO unit_extras (unit_id, item, qty, price) VALUES (?,?,?,?)", (u['id'], e_it, e_qt, e_pr))
                                conn.commit()
                                st.rerun()
                            
                            # Files
                            up = st.file_uploader("Upload Drawing", key=f"fl_{u['id']}")
                            if up and st.button("Save Drawing", key=f"sfl_{u['id']}"):
                                conn.execute("INSERT INTO unit_files (unit_id, file_name, file_data) VALUES (?,?,?)", (u['id'], up.name, up.getvalue()))
                                conn.commit()
                                st.rerun()

# --- 6. STORES & PROCUREMENT ---
elif choice == "📦 Stores & Procurement":
    st.header("Warehouse Inventory Control")
    conn = get_connection()
    
    # Add stock
    c1, c2, c3, c4 = st.columns([3,1,1,1])
    s_it = c1.text_input("Material Name")
    s_q = c2.number_input("Stock Qty", min_value=0.0)
    s_p = c3.number_input("Unit Price", min_value=0.0)
    s_u = c4.selectbox("Unit", ["Units", "Meters", "Rolls", "Boxes"])
    
    if st.button("Update Stores"):
        conn.execute("INSERT OR REPLACE INTO stores (item, available, price, uom) VALUES (?,?,?,?)", (s_it, s_q, s_p, s_u))
        conn.commit()
        st.rerun()
    
    st.divider()
    st.subheader("Current Stock Levels")
    st.table(pd.read_sql_query("SELECT * FROM stores", conn))
    
    st.subheader("🚨 Automatic Shortfall Order List")
    short_q = """
        SELECT bi.item, SUM(bi.qty) as 'Total Required', IFNULL(s.available, 0) as 'In Stock'
        FROM units u
        JOIN blueprint_items bi ON u.blueprint_id = bi.b_id
        LEFT JOIN stores s ON bi.item = s.item
        GROUP BY bi.item
    """
    short_df = pd.read_sql_query(short_q, conn)
    short_df['Shortfall'] = (short_df['Total Required'] - short_df['In Stock']).apply(lambda x: x if x > 0 else 0)
    st.dataframe(short_df, use_container_width=True)
