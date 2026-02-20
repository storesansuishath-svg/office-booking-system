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
    start_str = t_start.strftime("%d/%m/%Y %H:%M") if isinstance(t_start, datetime) else str(t_start)
    end_str = t_end.strftime("%H:%M") if isinstance(t_end, datetime) else str(t_end)
    payload = {"id": booking_id, "resource": resource, "name": name, "dept": dept, "date": start_str, "end_date": end_str, "purpose": purpose, "destination": destination}
    try:
        requests.post(render_url, json=payload, timeout=15)
        st.toast("🔔 ส่งแจ้งเตือนเข้า LINE แล้ว", icon="✅")
    except: pass

# --- 2. ฟังก์ชันลบข้อมูลอัตโนมัติ (เก็บข้อมูลไว้ 45 วันเพื่อทำรายงาน) ---
def auto_delete_old_bookings():
    threshold_delete = (datetime.now() - timedelta(days=45)).isoformat()
    try:
        supabase.table("bookings").delete().lt("end_time", threshold_delete).execute()
    except: pass

# --- 3. ตั้งค่าหน้าจอและ Sidebar ---
st.set_page_config(page_title="ระบบจองรถ & ห้องประชุม", layout="wide")
st.markdown("""
    <style>
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"], .stNumberInput input {
        background-color: #E3F2FD !important; color: #0D47A1 !important; border: 1px solid #BBDEFB !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border: 2px solid #2196F3 !important; background-color: #E1F5FE !important;
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
        if cat == "รถยนต์":
            res = st.selectbox("เลือกคัน", ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"])
            dest = st.text_input("สถานที่ปลายทาง", placeholder="เช่น บริษัท ABC")
            if dest:
                st.link_button(f"🔍 ค้นหา '{dest}' บนแผนที่", f"https://www.google.com/maps/search/{dest}")
            else:
                st.link_button("📍 เปิด Google Maps", "http://googleusercontent.com/maps.google.com/4")
        else:
            res = st.selectbox("เลือกห้อง", ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"])
            dest = "Office"
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
            ts_f = format_time_string(t_start_raw); te_f = format_time_string(t_end_raw)
            t_start = datetime.combine(d_start, datetime.strptime(ts_f, "%H:%M").time())
            t_end = datetime.combine(d_end, datetime.strptime(te_f, "%H:%M").time())
        except: t_start, t_end = None, None

    if st.button("ยืนยันการส่งคำขอจอง"):
        if not name or not dept or t_start is None: st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")
        elif t_start >= t_end: st.error("❌ เวลาเริ่มต้องก่อนเวลาสิ้นสุด")
        else:
            check_res = supabase.table("bookings").select("*").eq("resource", res).eq("status", "Approved").execute()
            df_check = pd.DataFrame(check_res.data)
            is_overlap = False
            if not df_check.empty:
                df_check['start_time'] = pd.to_datetime(df_check['start_time']).dt.tz_localize(None)
                df_check['end_time'] = pd.to_datetime(df_check['end_time']).dt.tz_localize(None)
                overlap = df_check[~((df_check['start_time'] >= t_end) | (df_check['end_time'] <= t_start))]
                if not
