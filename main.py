import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. DATABASE ENGINE (WITH CASCADE DELETE) ---
def get_connection():
    return sqlite3.connect('jnf_elect_PRO_v22.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Projects
    c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    # Blueprints (Unique per project)
    c.execute('CREATE TABLE IF NOT EXISTS blueprints (id INTEGER PRIMARY KEY, project_id INTEGER, name TEXT, UNIQUE(project_id, name))')
    # Blueprint Items
    c.execute('CREATE TABLE IF NOT EXISTS blueprint_items (id INTEGER PRIMARY KEY, b_id INTEGER, item TEXT, qty REAL, uom TEXT)')
    # Units
    c.execute('''CREATE TABLE IF NOT EXISTS units 
                 (id INTEGER PRIMARY KEY, project_id INTEGER, unit_no TEXT, blueprint_id INTEGER, 
                  f_fix INT DEFAULT 0, wire INT DEFAULT 0, s_fix INT DEFAULT 0, test INT DEFAULT 0)''')
    # Stores
    c.execute('CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, item TEXT UNIQUE, available REAL, price REAL, uom TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- 2. INTERFACE & NAVIGATION ---
st.set_page_config(page_title="JNF Elect PRO-ERP", layout="wide")
st.sidebar.title("⚡ JNF COMMAND CENTER")
menu = ["📊 Dashboard", "🏗️ Project & Blueprint Control", "📦 Stores Control"]
choice = st.sidebar.radio("Navigation", menu)

# --- 3. DASHBOARD ---
if choice == "📊 Dashboard":
    st.header("Executive Site Health")
    conn = get_connection()
    projects = pd.read_sql_query("SELECT * FROM projects", conn)
    
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
            col2.progress(prog)
            col3.metric("Project Value", f"R {val:,.2f}")

# --- 4. PROJECT & BLUEPRINT CONTROL ---
elif choice == "🏗️ Project & Blueprint Control":
    st.header("Site Operations & Blueprinting")
    conn = get_connection()
    
    # PROJECT CREATION
    with st.container(border=True):
        st.write("### ➕ Launch New Project Site")
        p_name = st.text_input("Project Name (e.g. Atlantic Heights)", key="new_proj_input")
        if st.button("Initialize Site"):
            if p_name:
                try:
                    conn.execute("INSERT INTO projects (name) VALUES (?)", (p_name,))
                    conn.commit()
                    st.success(f"Project {p_name} Created.")
                    st.rerun()
                except:
                    st.error("Project name already exists.")

    st.divider()
    
    # MANAGE ACTIVE PROJECTS
    projs = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    for _, p in projs.iterrows():
        with st.expander(f"📂 PROJECT: {p['name']}", expanded=True):
            
            t1, t2 = st.tabs(["📋 Blueprint Designer", "🏗️ Unit Tracking"])
            
            with t1:
                st.write("### Step 1: Design Blueprints (Quotes)")
                
                # UNIQUE BLUEPRINT CREATION
                with st.container():
                    bc1, bc2 = st.columns([3,1])
                    new_b = bc1.text_input(f"New Blueprint Name", placeholder="e.g. House Type E", key=f"bi_in_{p['id']}")
                    if bc2.button("Save Blueprint", key=f"bs_btn_{p['id']}"):
                        if new_b:
                            try:
                                conn.execute("INSERT INTO blueprints (project_id, name) VALUES (?,?)", (p['id'], new_b))
                                conn.commit()
                                st.rerun()
                            except:
                                st.error("This Blueprint name already exists in this project.")

                # MANAGE BLUEPRINTS
                bl_df = pd.read_sql_query(f"SELECT * FROM blueprints WHERE project_id={p['id']}", conn)
                for _, b in bl_df.iterrows():
                    with st.container(border=True):
                        col_bt, col_bd = st.columns([4,1])
                        col_bt.write(f"**Blueprint: {b['name']}**")
                        
                        # HARD DELETE BLUEPRINT & ALL LINKED ITEMS
                        if col_bd.button("🗑️ Delete Blueprint", key=f"db_{b['id']}"):
                            conn.execute(f"DELETE FROM blueprint_items WHERE b_id={b['id']}")
                            conn.execute(f"DELETE FROM units WHERE blueprint_id={b['id']}")
                            conn.execute(f"DELETE FROM blueprints WHERE id={b['id']}")
                            conn.commit()
                            st.rerun()
                        
                        # ADD ITEM SECTION (Resetting via key logic)
                        with st.container():
                            ic1, ic2, ic3, ic4 = st.columns([3,1,1,1])
                            m_n = ic1.text_input("Material", key=f"mn_{b['id']}")
                            m_q = ic2.number_input("Qty", min_value=0.0, key=f"mq_{b['id']}")
                            m_u = ic3.selectbox("Unit", ["Units", "Meters", "Rolls", "Boxes"], key=f"mu_{b['id']}")
                            
                            if ic4.button("Add Item", key=f"ab_{b['id']}"):
                                if m_n:
                                    conn.execute("INSERT INTO blueprint_items (b_id, item, qty, uom) VALUES (?,?,?,?)", (b['id'], m_n, m_q, m_u))
                                    conn.commit()
                                    st.rerun() # This clears the text boxes by resetting the session state

                        # THE QUOTE TABLE WITH SINGLE ITEM DELETE
                        quote_df = pd.read_sql_query(f"""
                            SELECT bi.id, bi.item, bi.qty, bi.uom, IFNULL(s.price, 0) as 'Price', (bi.qty * IFNULL(s.price, 0)) as 'Subtotal'
                            FROM blueprint_items bi LEFT JOIN stores s ON bi.item = s.item WHERE bi.b_id = {b['id']}
                        """, conn)
                        
                        if not quote_df.empty:
                            for idx, row in quote_df.iterrows():
                                rc1, rc2, rc3, rc4, rc5 = st.columns([3,1,1,1,1])
                                rc1.write(row['item'])
                                rc2.write(f"{row['qty']} {row['uom']}")
                                rc3.write(f"R {row['Price']}")
                                rc4.write(f"**R {row['Subtotal']:.2f}**")
                                # SINGLE ITEM DELETE
                                if rc5.button("🗑️", key=f"dim_{row['id']}"):
                                    conn.execute(f"DELETE FROM blueprint_items WHERE id={row['id']}")
                                    conn.commit()
                                    st.rerun()
                            st.write(f"--- **Total Value:** R {quote_df['Subtotal'].sum():,.2f}")

            with t2:
                st.write("### Step 2: Allocate Units")
                # [Unit Logic Restored with Unique Keys]
                uc1, uc2, uc3 = st.columns([2,2,1])
                u_no = uc1.text_input("Unit No", key=f"uno_{p['id']}")
                u_bl = uc2.selectbox("Apply Blueprint", bl_df['name'] if not bl_df.empty else ["No Designs"], key=f"ubl_{p['id']}")
                if uc3.button("Link Unit", key=f"ul_{p['id']}"):
                    bid_match = bl_df[bl_df['name'] == u_bl]['id'].values[0]
                    conn.execute("INSERT INTO units (project_id, unit_no, blueprint_id) VALUES (?,?,?)", (p['id'], u_no, bid_match))
                    conn.commit()
                    st.rerun()
                
                u_list = pd.read_sql_query(f"SELECT * FROM units WHERE project_id={p['id']}", conn)
                for _, u in u_list.iterrows():
                    sc1, sc2, sc3, sc4, sc5, sc6, sc7 = st.columns([1,1,1,1,1,1,1])
                    sc1.write(f"**Unit {u['unit_no']}**")
                    f1 = sc2.checkbox("1st", value=u['f_fix'], key=f"f1_{u['id']}")
                    f2 = sc3.checkbox("Wire", value=u['wire'], key=f"f2_{u['id']}")
                    f3 = sc4.checkbox("2nd", value=u['s_fix'], key=f"f3_{u['id']}")
                    f4 = sc5.checkbox("Test", value=u['test'], key=f"f4_{u['id']}")
                    if sc6.button("Save", key=f"sv_{u['id']}"):
                        conn.execute(f"UPDATE units SET f_fix={int(f1)}, wire={int(f2)}, s_fix={int(f3)}, test={int(f4)} WHERE id={u['id']}")
                        conn.commit()
                    if sc7.button("🗑️", key=f"du_{u['id']}"):
                        conn.execute(f"DELETE FROM units WHERE id={u['id']}")
                        conn.commit()
                        st.rerun()

# --- 5. STORES CONTROL ---
elif choice == "📦 Stores Control":
    st.header("Warehouse Stock & Pricing")
    conn = get_connection()
    c1, c2, c3, c4 = st.columns([3,1,1,1])
    s_it = c1.text_input("Material Name")
    s_q = c2.number_input("Stock Qty", min_value=0.0)
    s_p = c3.number_input("Unit Price", min_value=0.0)
    s_u = c4.selectbox("Unit", ["Units", "Meters", "Rolls", "Boxes"])
    
    if st.button("Sync Store"):
        conn.execute("INSERT OR REPLACE INTO stores (item, available, price, uom) VALUES (?,?,?,?)", (s_it, s_q, s_p, s_u))
        conn.commit()
        st.rerun()
    
    st.divider()
    st.table(pd.read_sql_query("SELECT item, available, price, uom FROM stores", conn))
