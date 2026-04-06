import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io

# --- 1. DATABASE ENGINE ---
def get_connection():
    return sqlite3.connect('jnf_elect_final_master.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE, date_created TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS baselines (id INTEGER PRIMARY KEY, project_id INTEGER, type_name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS baseline_items (id INTEGER PRIMARY KEY, b_id INTEGER, item TEXT, qty REAL, uom TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS site_units 
                 (id INTEGER PRIMARY KEY, project_id INTEGER, unit_no TEXT, baseline_id INTEGER, 
                  f_fix INT DEFAULT 0, wire INT DEFAULT 0, s_fix INT DEFAULT 0, test INT DEFAULT 0)''')
    c.execute('CREATE TABLE IF NOT EXISTS unit_files (id INTEGER PRIMARY KEY, unit_id INTEGER, file_name TEXT, file_data BLOB)')
    c.execute('CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, item TEXT UNIQUE, available REAL, price REAL, uom TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- 2. INTERFACE ---
st.set_page_config(page_title="JNF Elect ERP", layout="wide")
st.sidebar.title("⚡ JNF COMMAND CENTER")
user = st.sidebar.text_input("Project Manager:", "Quinton")
menu = ["📊 Dashboard", "🏗️ Project Site Manager", "📦 Stores & Procurement"]
choice = st.sidebar.radio("Navigation", menu)

# --- 3. DASHBOARD (FINANCIALS & PROGRESS) ---
if choice == "📊 Dashboard":
    st.header("Executive Site Overview")
    conn = get_connection()
    projects = pd.read_sql_query("SELECT * FROM projects", conn)
    
    for _, p in projects.iterrows():
        with st.container(border=True):
            col1, col2, col3 = st.columns([2,1,1])
            units = pd.read_sql_query(f"SELECT f_fix, wire, s_fix, test FROM site_units WHERE project_id={p['id']}", conn)
            prog = (units.sum().sum() / (len(units)*4)) if not units.empty else 0
            
            cost_q = f"""
                SELECT SUM(bi.qty * IFNULL(s.price, 0)) FROM site_units su
                JOIN baseline_items bi ON su.baseline_id = bi.b_id
                LEFT JOIN stores s ON bi.item = s.item
                WHERE su.project_id = {p['id']}
            """
            val = conn.execute(cost_q).fetchone()[0] or 0.0
            
            col1.subheader(f"Project: {p['name']}")
            col2.write(f"**Progress:** {int(prog*100)}%")
            col2.progress(prog)
            col3.metric("Project Value", f"R {val:,.2f}")

# --- 4. PROJECT SITE MANAGER (THE ENGINE) ---
elif choice == "🏗️ Project Site Manager":
    st.header("Site Operations")
    conn = get_connection()
    
    p_name = st.text_input("New Project Name")
    if st.button("Initialize Site"):
        if p_name:
            conn.execute("INSERT OR IGNORE INTO projects (name, date_created) VALUES (?,?)", (p_name, datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            st.rerun()

    st.divider()
    projects = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    for _, p in projects.iterrows():
        with st.expander(f"📂 {p['name']}", expanded=True):
            t1, t2 = st.tabs(["📋 Design Baselines", "🏗️ Unit Tracking & Files"])
            
            with t1:
                st.subheader("Project-Bound Design")
                b_name = st.text_input("Template Name", key=f"bn_{p['id']}")
                if st.button("Save Design", key=f"bb_{p['id']}"):
                    conn.execute("INSERT INTO baselines (project_id, type_name) VALUES (?,?)", (p['id'], b_name))
                    conn.commit()
                    st.rerun()
                
                bases = pd.read_sql_query(f"SELECT * FROM baselines WHERE project_id={p['id']}", conn)
                if not bases.empty:
                    sel_b = st.selectbox("Select Design to Edit", bases['type_name'], key=f"sb_{p['id']}")
                    bid = bases[bases['type_name'] == sel_b]['id'].values[0]
                    
                    st.write(f"**Add Materials to {sel_b}**")
                    c1, c2, c3 = st.columns([3,1,1])
                    m_n = c1.text_input("Material", key=f"mn_{bid}")
                    m_q = c2.number_input("Qty", min_value=0.0, key=f"mq_{bid}")
                    m_u = c3.selectbox("Unit", ["Meters", "Units", "Rolls", "Boxes"], key=f"mu_{bid}")
                    
                    if st.button("ADD ITEM", key=f"ai_{bid}"):
                        if m_n:
                            conn.execute("INSERT INTO baseline_items (b_id, item, qty, uom) VALUES (?,?,?,?)", (bid, m_n, m_q, m_u))
                            conn.commit()
                            st.rerun()

                    # VISIBLE LIST
                    items = pd.read_sql_query(f"SELECT id, item, qty, uom FROM baseline_items WHERE b_id={bid}", conn)
                    for _, row in items.iterrows():
                        ic1, ic2, ic3 = st.columns([4,1,1])
                        ic1.write(f"{row['item']} - {row['qty']} {row['uom']}")
                        if ic2.button("🗑️", key=f"del_{row['id']}"):
                            conn.execute(f"DELETE FROM baseline_items WHERE id={row['id']}")
                            conn.commit()
                            st.rerun()

            with t2:
                st.subheader("Unit Status & Drawings")
                uc1, uc2 = st.columns(2)
                u_no = uc1.text_input("Unit No", key=f"un_{p['id']}")
                u_bl = uc2.selectbox("Design Plan", bases['type_name'] if not bases.empty else ["None"], key=f"ub_{p['id']}")
                if st.button("Link Unit", key=f"lu_{p['id']}"):
                    bl_id = bases[bases['type_name'] == u_bl]['id'].values[0]
                    conn.execute("INSERT INTO site_units (project_id, unit_no, baseline_id) VALUES (?,?,?)", (p['id'], u_no, bl_id))
                    conn.commit()
                    st.rerun()
                
                units = pd.read_sql_query(f"SELECT * FROM site_units WHERE project_id={p['id']}", conn)
                for _, u in units.iterrows():
                    with st.expander(f"Unit {u['unit_no']} Status"):
                        sc1, sc2, sc3, sc4, sc5 = st.columns(5)
                        f1 = sc1.checkbox("1st Fix", value=u['f_fix'], key=f"f1_{u['id']}")
                        f2 = sc2.checkbox("Wire", value=u['wire'], key=f"f2_{u['id']}")
                        f3 = sc3.checkbox("2nd Fix", value=u['s_fix'], key=f"f3_{u['id']}")
                        f4 = sc4.checkbox("Test", value=u['test'], key=f"f4_{u['id']}")
                        if sc5.button("SAVE", key=f"sv_{u['id']}"):
                            conn.execute(f"UPDATE site_units SET f_fix={int(f1)}, wire={int(f2)}, s_fix={int(f3)}, test={int(f4)} WHERE id={u['id']}")
                            conn.commit()
                            st.rerun()
                        
                        # Drawing Vault
                        up = st.file_uploader("Upload Plan", key=f"up_{u['id']}")
                        if up and st.button("Save Drawing", key=f"su_{u['id']}"):
                            conn.execute("INSERT INTO unit_files (unit_id, file_name, file_data) VALUES (?,?,?)", (u['id'], up.name, up.getvalue()))
                            conn.commit()
                            st.success("Saved")
                        
                        files = pd.read_sql_query(f"SELECT id, file_name FROM unit_files WHERE unit_id={u['id']}", conn)
                        for _, f in files.iterrows():
                            f_data = conn.execute("SELECT file_data FROM unit_files WHERE id=?", (f['id'],)).fetchone()[0]
                            st.download_button(f"Download {f['file_name']}", f_data, file_name=f['file_name'], key=f"dl_{f['id']}")

# --- 5. STORES & PROCUREMENT (SHORTFALL LOGIC) ---
elif choice == "📦 Stores & Procurement":
    st.header("Inventory & Order Tracking")
    conn = get_connection()
    tab1, tab2 = st.tabs(["Warehouse", "🚨 Procurement / Shortfall"])
    
    with tab1:
        c1, c2, c3, c4 = st.columns([3,1,1,1])
        s_it = c1.text_input("Material Name")
        s_q = c2.number_input("Qty Available", min_value=0.0)
        s_p = c3.number_input("Unit Price", min_value=0.0)
        s_u = c4.selectbox("Unit", ["Meters", "Units", "Rolls", "Boxes"], key="suom")
        if st.button("Update Stores"):
            conn.execute("INSERT OR REPLACE INTO stores (item, available, price, uom) VALUES (?,?,?,?)", (s_it, s_q, s_p, s_u))
            conn.commit()
            st.rerun()
        st.table(pd.read_sql_query("SELECT item, available, price, uom FROM stores", conn))

    with tab2:
        st.subheader("🚨 Automatic Order List")
        query = """
            SELECT bi.item as 'Material', SUM(bi.qty) as 'Required', IFNULL(s.available, 0) as 'In Stock', IFNULL(s.price, 0) as 'Price Each'
            FROM site_units su
            JOIN baseline_items bi ON su.baseline_id = bi.b_id
            LEFT JOIN stores s ON bi.item = s.item
            GROUP BY bi.item
        """
        short_df = pd.read_sql_query(query, conn)
        short_df['Shortfall'] = (short_df['Required'] - short_df['In Stock']).apply(lambda x: x if x > 0 else 0)
        short_df['Total Cost'] = short_df['Shortfall'] * short_df['Price Each']
        st.dataframe(short_df, use_container_width=True)
        st.metric("Total Order Value Required", f"R {short_df['Total Cost'].sum():,.2f}")
