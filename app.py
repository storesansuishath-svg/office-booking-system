import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests

# --- 1. การเชื่อมต่อ Supabase ---
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co" 
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination):
    render_url = "https://line-booking-system.onrender.com/notify" # ตรวจสอบ URL ของ Render คุณอีกครั้ง
    payload = {
        "id": booking_id, "resource": resource, "name": name, "dept": dept,
        "date": t_start.strftime("%d/%m/%Y %H:%M"), "end_date": t_end.strftime("%H:%M"),
        "purpose": purpose, "destination": destination
    }
    try: requests.post(render_url, json=payload, timeout=5)
    except: pass

# --- 2. ตั้งค่าหน้าจอ (UI เดิม 100%) ---
st.set_page_config(page_title="ระบบจองรถ & ห้องประชุม", layout="wide")
st.markdown("""<style>
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        background-color: #E3F2FD !important; color: #0D47A1 !important;
    }
</style>""", unsafe_allow_html=True)

st.title("ระบบจองรถยนต์และห้องประชุม Online")
menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin (อนุมัติ)"]
choice = st.sidebar.selectbox("เมนู", menu)

if choice == "📝 จองใหม่":
    st.subheader("รายละเอียดการจอง")
    col1, col2 = st.columns(2)
    with col1:
        cat = st.radio("ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"])
        res = st.selectbox("เลือกรายการ", ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"] if cat=="รถยนต์" else ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"])
        destination = st.text_input("สถานที่ปลายทาง") if cat=="รถยนต์" else "Office"
        name, phone, dept = st.text_input("ชื่อผู้จอง"), st.text_input("เบอร์โทรศัพท์"), st.text_input("แผนก")
    with col2:
        t_start = st.datetime_input("เวลาเริ่ม", datetime.now())
        t_end = st.datetime_input("เวลาสิ้นสุด", datetime.now() + timedelta(hours=1))
        reason = st.text_area("วัตถุประสงค์")

    if st.button("ยืนยันการส่งคำขอจอง"):
        if not name or not reason: st.warning("⚠️ กรุณากรอกข้อมูลให้ครบ")
        else:
            data = {"resource": res, "requester": name, "phone": phone, "dept": dept, "start_time": t_start.isoformat(), "end_time": t_end.isoformat(), "purpose": reason, "destination": destination, "status": "Pending"}
            resp = supabase.table("bookings").insert(data).execute()
            if resp.data:
                send_line_notification(resp.data[0]['id'], res, name, dept, t_start, t_end, reason, destination)
                st.success("✅ ส่งคำขอเรียบร้อย! รอ Admin อนุมัติใน LINE")

elif choice == "🔑 Admin (อนุมัติ)":
    st.subheader("🔑 ระบบจัดการการจอง")
    if st.text_input("🔒 รหัสผ่าน", type="password") == "s1234":
        items = supabase.table("bookings").select("*").eq("status", "Pending").execute().data
        for item in items:
            with st.container(border=True):
                c1, c2, c3 = st.columns([3,3,1])
                c1.write(f"**{item['resource']}**\n\n👤 {item['requester']} | 📍 {item['destination']}")
                c2.write(f"⏰ {item['start_time']}\n\n📝 {item['purpose']}")
                if c3.button("✅", key=f"a{item['id']}"):
                    supabase.table("bookings").update({"status": "Approved"}).eq("id", item['id']).execute()
                    st.rerun()
                if c3.button("❌", key=f"r{item['id']}"):
                    supabase.table("bookings").update({"status": "Rejected"}).eq("id", item['id']).execute()
                    st.rerun()

elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางงานปัจจุบัน")
    res_db = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", datetime.now().isoformat()).order("start_time").execute()
    if res_db.data:
        df = pd.DataFrame(res_db.data)[['resource', 'start_time', 'end_time', 'requester', 'destination']]
        st.dataframe(df, use_container_width=True)
    else: st.info("ไม่มีรายการจองในขณะนี้")
