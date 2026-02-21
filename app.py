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

# ฟังก์ชันจัดการรูปแบบเวลา (0800 -> 08:00)
def format_time_string(t_raw):
    clean = str(t_raw).replace(":", "").strip()
    if len(clean) == 4:
        return f"{clean[:2]}:{clean[2:]}"
    return clean

def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination, status_text="Pending"):
    render_url = "https://line-booking-system.onrender.com/notify"
    try:
        s_str = t_start.strftime("%d/%m/%Y %H:%M") if isinstance(t_start, datetime) else str(t_start)
        e_str = t_end.strftime("%H:%M") if isinstance(t_end, datetime) else str(t_end)
        payload = {"id": booking_id, "resource": resource, "name": name, "dept": dept, "date": s_str, "end_date": e_str, "purpose": purpose, "destination": destination}
        requests.post(render_url, json=payload, timeout=10)
        st.toast("🔔 ส่งแจ้งเตือน LINE แล้ว", icon="✅")
    except: pass

def auto_delete_old_bookings():
    # ลบข้อมูลที่จบเกิน 45 วันเพื่อความสะอาด
    threshold_delete = (datetime.now() - timedelta(days=45)).isoformat()
    try: supabase.table("bookings").delete().lt("end_time", threshold_delete).execute()
    except: pass

# --- 3. ตั้งค่าหน้าจอและ CSS ---
st.set_page_config(page_title="ระบบจองรถ & ห้องประชุม", layout="wide")
st.markdown("""
    <style>
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        background-color: #E3F2FD !important; color: #0D47A1 !important; border: 1px solid #BBDEFB !important;
    }
    </style>
""", unsafe_allow_html=True)

LOGO_URL = "https://lh3.googleusercontent.com/d/1zCjSjSbCO-mbsaGoDI6g0G-bfmyVfqFV"
st.sidebar.image(LOGO_URL, use_container_width=True)
st.sidebar.markdown("---")

auto_delete_old_bookings()

st.title("ระบบจองรถยนต์และห้องประชุม Online")
menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin (อนุมัติ)", "📊 รายงานประจำเดือน"]
choice = st.sidebar.selectbox("เมนู", menu)

# --- หน้าจองใหม่ ---
if choice == "📝 จองใหม่":
    st.subheader("รายละเอียดการจอง")
    col1, col2 = st.columns(2)
    with col1:
        cat = st.radio("ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"])
        rooms = ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]
        cars = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG"] # ใช้ชื่อ MG สั้นๆ ตามพี่สั่งครับ
        res = st.selectbox("เลือกรายการ", cars if cat == "รถยนต์" else rooms)
        dest = st.text_input("สถานที่ปลายทาง") if cat == "รถยนต์" else "Office"
        name = st.text_input("ชื่อผู้จอง")
        phone = st.text_input("เบอร์โทรศัพท์")
        dept = st.text_input("แผนก")
    with col2:
        d_start = st.date_input("วันที่เริ่ม", datetime.now().date())
        t_start_raw = st.text_input("เวลาเริ่ม (เช่น 0800)", value="0800", max_chars=4)
        st.markdown("---")
        d_end = st.date_input("วันที่สิ้นสุด", value=d_start, min_value=d_start)
        t_end_raw = st.text_input("เวลาสิ้นสุด (เช่น 1700)", value="1700", max_chars=4)
        reason = st.text_area("วัตถุประสงค์")
        try:
            ts_f, te_f = format_time_string(t_start_raw), format_time_string(t_end_raw)
            t_start = datetime.combine(d_start, datetime.strptime(ts_f, "%H:%M").time())
            t_end = datetime.combine(d_end, datetime.strptime(te_f, "%H:%M").time())
        except: t_start, t_end = None, None

    if st.button("ยืนยันการส่งคำขอจอง"):
        if not name or not dept or t_start is None: st.warning("⚠️ ข้อมูลไม่ครบ")
        elif t_start >= t_end: st.error("❌ เวลาเริ่มต้องก่อนเวลาสิ้นสุด")
        else:
            data = {"resource": res, "requester": name, "phone": phone, "dept": dept, "start_time": t_start.isoformat(), "end_time": t_end.isoformat(), "purpose": reason, "destination": dest, "status": "Pending"}
            resp = supabase.table("bookings").insert(data).execute()
            if resp.data:
                send_line_notification(resp.data[0]['id'], res, name, dept, t_start, t_end, reason, dest)
                st.success("✅ ส่งคำขอเรียบร้อย!")

# --- หน้าตารางงาน (Real-time) ---
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางงานปัจจุบันและล่วงหน้า")
    view_cat = st.radio("เลือกประเภท", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"], horizontal=True)
    now_iso = datetime.now().isoformat()
    # ดึงเฉพาะรายการที่ยังไม่จบ (ปัจจุบัน + อนาคต)
    res_db = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).order("start_time").execute()
    df = pd.DataFrame(res_db.data)
    
    if df.empty: st.info("ไม่มีรายการจองขณะนี้")
    else:
        # กรองข้อมูล
        meeting_rooms = ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]
        if view_cat == "รถยนต์": df = df[~df['resource'].isin(meeting_rooms)]
        elif view_cat == "ห้องประชุม": df = df[df['resource'].isin(meeting_rooms)]
        
        if not df.empty:
            df_show = df.copy().reset_index(drop=True)
            df_show['start_fmt'] = pd.to_datetime(df_show['start_time'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M')
            df_show['end_fmt'] = pd.to_datetime(df_show['end_time'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M')
            
            df_disp = df_show[['resource', 'start_fmt', 'end_fmt', 'requester', 'purpose', 'destination']]
            df_disp.columns = ['รายการ / Resource', 'เวลาเริ่ม / Start Time', 'เวลาสิ้นสุด / End Time', 'ผู้จอง / Name', 'วัตถุประสงค์ / Purpose', 'ปลายทาง / Destination']

            # 💡 แก้หน้าจอแดง: ตรวจสอบเวอร์ชันและใช้ Selection
            try:
                event = st.dataframe(df_disp, use_container_width=True, on_select="rerun", selection_mode="single_row")
                selected_rows = event.selection.rows
            except:
                # ถ้าเวอร์ชันเก่า ให้ใช้ selectbox เหมือนเดิมเพื่อกันเว็บล่มครับ
                selected_id = st.selectbox("เลือก ID เพื่อแก้ไข (โหมดสำรอง)", df_show.index)
                selected_rows = [selected_id] if st.checkbox("ยืนยันการเลือกแถวนี้") else []

            st.markdown("---")
            if selected_rows:
                row_idx = selected_rows[0]
                row = df_show.iloc[row_idx]
                edit_id = row['id']
                st.success(f"📝 แก้ไขรายการ: **{row['resource']}** ของคุณ **{row['requester']}**")
                
                with st.form("edit_form_table"):
                    c1, c2 = st.columns(2)
                    res_opts = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG"] + meeting_rooms
                    try: cur_idx = res_opts.index(row['resource'])
                    except: cur_idx = 0
                    
                    n_res = c1.selectbox("รายการ", res_opts, index=cur_idx)
                    n_req = c1.text_input("ผู้จอง", str(row['requester']))
                    n_dept = c1.text_input("แผนก", str(row.get('dept', '-')))
                    n_dest = c1.text_input("ปลายทาง", str(row.get('destination', '-')))

                    dt_s = pd.to_datetime(row['start_time'], errors='coerce')
                    dt_e = pd.to_datetime(row['end_time'], errors='coerce')
                    n_d_s = c2.date_input("วันที่เริ่ม", dt_s.date() if pd.notnull(dt_s) else datetime.now().date())
                    n_t_s = c2.text_input("เวลาเริ่ม (4 หลัก)", value=dt
