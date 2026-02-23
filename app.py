import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests
import json
import io

# --- 1. การเชื่อมต่อ Supabase ---
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co" 
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CSS สำหรับไฟกระพริบและ UI ---
st.markdown("""
    <style>
    @keyframes blinker { 50% { opacity: 0; } }
    .blink { animation: blinker 1s linear infinite; color: #FF0000; font-weight: bold; }
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        background-color: #E3F2FD !important; color: #0D47A1 !important; border: 1px solid #BBDEFB !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. ฟังก์ชันจัดการเวลา ---
def format_time_string(t_raw):
    clean = str(t_raw).replace(":", "").strip()
    return f"{clean[:2]}:{clean[2:]}" if len(clean) == 4 else clean

# --- 3. ระบบเช็กคิวชนกัน (Conflict Checker) ---
def check_booking_conflict(resource, start_time_iso, end_time_iso):
    res = supabase.table("bookings").select("*").eq("resource", resource).eq("status", "Approved").execute()
    new_s = datetime.fromisoformat(start_time_iso).replace(tzinfo=None)
    new_e = datetime.fromisoformat(end_time_iso).replace(tzinfo=None)
    for item in res.data:
        ex_s = pd.to_datetime(item['start_time']).replace(tzinfo=None)
        ex_e = pd.to_datetime(item['end_time']).replace(tzinfo=None)
        if new_s < ex_e and new_e > ex_s:
            return True, item['requester']
    return False, None

# --- 4. [จุดซ่อม] ฟังก์ชันแจ้งเตือน LINE ---
def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination, status_text="Pending"):
    render_url = "https://line-booking-system.onrender.com/notify"
    GROUP_ID = "Cad74a32468ca40051bd7071a6064660d" 
    
    # จัดการฟอร์แมตวันที่ให้สวยงามก่อนส่ง
    if isinstance(t_start, str):
        try: t_start_dt = pd.to_datetime(t_start)
        except: t_start_dt = datetime.now()
    else: t_start_dt = t_start
    
    s_str = t_start_dt.strftime("%d/%m/%Y %H:%M")
    e_str = t_end if isinstance(t_end, str) else t_end.strftime("%H:%M")

    payload = {
        "id": booking_id, "target_id": GROUP_ID, "resource": resource, 
        "name": name, "dept": dept, "date": s_str, "end_date": e_str, 
        "purpose": purpose, "destination": destination, "status": status_text
    }
    
    try:
        r = requests.post(render_url, json=payload, timeout=10)
        if r.status_code == 200:
            st.toast(f"🔔 LINE: {status_text} สำเร็จ", icon="✅")
        else:
            # ถ้าไม่เด้ง ให้โชว์ Error จากฝั่ง Render เลยครับ
            st.error(f"⚠️ LINE Error {r.status_code}: {r.text}")
    except Exception as e:
        st.error(f"📡 เชื่อมต่อ Render ไม่ได้: {e}")

def auto_delete_old_bookings():
    threshold = (datetime.now() - timedelta(days=45)).isoformat()
    try: supabase.table("bookings").delete().lt("end_time", threshold).execute()
    except: pass

# --- 5. Sidebar & Dashboard Logic ---
auto_delete_old_bookings()
pending_data = supabase.table("bookings").select("id").eq("status", "Pending").execute().data
pending_count = len(pending_data)

st.sidebar.image("https://lh3.googleusercontent.com/d/1zCjSjSbCO-mbsaGoDI6g0G-bfmyVfqFV", use_container_width=True)
if pending_count > 0:
    st.sidebar.markdown(f'<p class="blink">📢 รออนุมัติ: {pending_count} รายการ</p>', unsafe_allow_html=True)
st.sidebar.markdown("---")
menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin (อนุมัติ)", "📊 รายงานประจำเดือน"]
choice = st.sidebar.selectbox("เมนูหลัก", menu)

st.title("ระบบจองรถยนต์และห้องประชุม Online")

# --- หน้าจองใหม่ ---
if choice == "📝 จองใหม่":
    st.subheader("📊 สรุปข้อมูลวันนี้")
    t_today = datetime.now().date().isoformat()
    today_approved = supabase.table("bookings").select("id").eq("status", "Approved").gte("start_time", t_today).execute().data
    dash1, dash2, dash3 = st.columns(3)
    dash1.metric("คิวงานวันนี้", f"{len(today_approved)} รายการ")
    dash2.metric("รออนุมัติ", f"{pending_count} รายการ")
    dash3.metric("สถานะ Bot", "พร้อมใช้งาน")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        cat = st.radio("ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"])
        res_list = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG"] if cat == "รถยนต์" else ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]
        res = st.selectbox("เลือกรายการ", res_list)
        dest = st.text_input("สถานที่ปลายทาง") if cat == "รถยนต์" else "Office"
        name, phone, dept = st.text_input("ชื่อผู้จอง"), st.text_input("เบอร์โทร"), st.text_input("แผนก")
    with col2:
        d_s = st.date_input("วันที่เริ่ม", datetime.now().date())
        t_s_raw = st.text_input("เวลาเริ่ม (เช่น 0800)", "0800", max_chars=4)
        d_e = st.date_input("วันที่สิ้นสุด", d_s)
        t_e_raw = st.text_input("เวลาสิ้นสุด (เช่น 1700)", "1700", max_chars=4)
        purp = st.text_area("วัตถุประสงค์")
        try:
            ts = datetime.combine(d_s, datetime.strptime(format_time_string(t_s_raw), "%H:%M").time())
            te = datetime.combine(d_e, datetime.strptime(format_time_string(t_e_raw), "%H:%M").time())
        except: ts, te = None, None

    if st.button("ยืนยันการจอง", use_container_width=True):
        if not name or not dept or ts is None: st.warning("⚠️ ข้อมูลไม่ครบ")
        elif ts >= te: st.error("❌ เวลาผิด")
        else:
            is_conf, u_conf = check_booking_conflict(res, ts.isoformat(), te.isoformat())
            if is_conf: st.error(f"❌ คิวชนกับคุณ {u_conf}!")
            else:
                data = {"resource": res, "requester": name, "phone": phone, "dept": dept, "start_time": ts.isoformat(), "end_time": te.isoformat(), "purpose": purp, "destination": dest, "status": "Pending"}
                resp = supabase.table("bookings").insert(data).execute()
                if resp.data:
                    send_line_notification(resp.data[0]['id'], res, name, dept, ts, te, purp, dest)
                    st.success("✅ ส่งคำขอเรียบร้อย!"); st.rerun()

# --- หน้าตารางงาน (มีส่วนแก้ไข/ลบ ครบถ้วน) ---
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางการใช้งาน")
    f1, f2 = st.columns([2, 1])
    search_q = f1.text_input("🔍 ค้นหาชื่อ/สถานที่")
    view_cat = f2.selectbox("กรองประเภท", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
    
    res_db = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", datetime.now().isoformat()).order("start_time").execute()
    df = pd.DataFrame(res_db.data)
    
    if not df.empty:
        if view_cat == "รถยนต์": df = df[df['resource'].isin(["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG"])]
        elif view_cat == "ห้องประชุม": df = df[~df['resource'].isin(["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG"])]
        if search_q: df = df[df['requester'].str.contains(search_q, case=False, na=False) | df['destination'].str.contains(search_q, case=False, na=False)]
        
        df_show = df.copy().reset_index(drop=True)
        df_show.index += 1
        df_show.insert(0, 'ลำดับ/No.', df_show.index)
        df_show['start_fmt'] = pd.to_datetime(df_show['start_time']).dt.strftime('%d/%m/%Y %H:%M')
        st.dataframe(df_show[['ลำดับ/No.', 'resource', 'start_fmt', 'requester', 'purpose', 'destination']], use_container_width=True)

        st.markdown("---")
        with st.expander("🛠️ แก้ไข/ลบ ข้อมูล (Admin Only)"):
            sel_no = st.selectbox("เลือก No. ที่ต้องการแก้ไข", df_show['ลำดับ/No.'].tolist())
            row = df_show[df_show['ลำดับ/No.'] == sel_no].iloc[0]
            with st.form("edit_form_table"):
                e_c1, e_c2 = st.columns(2)
                n_req = e_c1.text_input("ชื่อผู้จอง", row['requester'])
                n_dest = e_c1.text_input("ปลายทาง", row.get('destination', '-'))
                # เพิ่มเวลาและวัตถุประสงค์ตามสั่ง
                dt_s = pd.to_datetime(row['start_time'])
                dt_e = pd.to_datetime(row['end_time'])
                n_d_e = e_c2.date_input("วันที่สิ้นสุด", dt_e.date())
                n_t_e = e_c2.text_input("เวลาสิ้นสุด (4 หลัก)", dt_e.strftime("%H%M"))
                n_purp = st.text_area("วัตถุประสงค์", row.get('purpose', '-'))
                
                pw = st.text_input("รหัสผ่าน Admin", type="password")
                if st.form_submit_button("💾 บันทึกการแก้ไข"):
                    if pw == "s1234":
                        fe = format_time_string(n_t_e)
                        final_e = datetime.combine(n_d_e, datetime.strptime(fe, "%H:%M").time()).isoformat()
                        supabase.table("bookings").update({"requester": n_req, "destination": n_dest, "purpose": n_purp, "end_time": final_e}).eq("id", row['id']).execute()
                        st.success("อัปเดตแล้ว!"); st.rerun()
                if st.form_submit_button("🗑️ ลบรายการ"):
                    if pw == "s1234":
                        supabase.table("bookings").delete().eq("id", row['id']).execute(); st.rerun()

# --- หน้า Admin (อนุมัติ) ---
elif choice == "🔑 Admin (อนุมัติ)":
    st.subheader("🔑 ระบบจัดการอนุมัติ")
    if st.text_input("Password Admin", type="password") == "s1234":
        items = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute().data
        if not items: st.info("ไม่มีรายการรออนุมัติ")
        else:
            for item in items:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        curr_dt = pd.to_datetime(item['start_time'])
                        a_d = st.date_input("ยืนยันวันที่", curr_dt.date(), key=f"d_{item['id']}")
                        a_t = st.text_input("ยืนยันเวลาเริ่ม", curr_dt.strftime("%H%M"), key=f"t_{item['id']}")
                        st.write(f"🚗 {item['resource']} | 👤 {item['requester']} | 📍 {item.get('destination','-')}")
                    
                    if c2.button("อนุมัติ ✅", key=f"ap_{item['id']}", use_container_width=True):
                        try:
                            ft = format_time_string(a_t)
                            final_t = datetime.combine(a_d, datetime.strptime(ft, "%H:%M").time()).isoformat()
                            supabase.table("bookings").update({"status": "Approved", "start_time": final_t}).eq("id", item['id']).execute()
                            # ✅ จุดสำคัญ: เรียกฟังก์ชันแจ้งเตือนพร้อมส่งสถานะ Approved
                            send_line_notification(item['id'], item['resource'], item['requester'], item['dept'], final_t, item['end_time'], item['purpose'], item.get('destination','-'), "Approved")
                            st.rerun()
                        except: st.error("รูปแบบเวลาผิด")
                    if c2.button("ลบ 🗑️", key=f"dl_{item['id']}", use_container_width=True):
                        supabase.table("bookings").delete().eq("id", item['id']).execute(); st.rerun()

# --- หน้ารายงานประจำเดือน ---
elif choice == "📊 รายงานประจำเดือน":
    st.subheader("📊 รายงานสรุป")
    if st.text_input("รหัสรายงาน", type="password") == "s1234":
        res_rep = supabase.table("bookings").select("*").eq("status", "Approved").execute()
        if res_rep.data:
            df_rep = pd.DataFrame(res_rep.data)
            df_rep['start_time'] = pd.to_datetime(df_rep['start_time'])
            df_rep['Month-Year'] = df_rep['start_time'].dt.strftime('%m/%Y')
            sel_m = st.selectbox("เลือกเดือน", sorted(df_rep['Month-Year'].unique(), reverse=True))
            rep_type = st.selectbox("ประเภท", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
            
            f_df = df_rep[df_rep['Month-Year'] == sel_m].copy()
            if rep_type == "รถยนต์": f_df = f_df[f_df['resource'].str.contains("Civic|Camry|MG", na=False)]
            elif rep_type == "ห้องประชุม": f_df = f_df[f_df['resource'].str.contains("ห้อง", na=False)]
            
            st.dataframe(f_df[['resource', 'requester', 'dept', 'start_time', 'destination', 'purpose']], use_container_width=True)
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as w: f_df.to_excel(w, index=False)
            st.download_button("📥 Excel", buf.getvalue(), f"Report_{sel_m}.xlsx")
