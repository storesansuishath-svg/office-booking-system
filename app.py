import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime

# --- แทนที่ด้วยค่าจริงที่คุณก๊อปมาจาก Supabase ---
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co"
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Booking System", layout="wide")
st.title("🚗 ระบบจองรถและห้องประชุมออนไลน์")

# เมนูหน้าเว็บ
menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)"]
choice = st.sidebar.selectbox("เมนู", menu)

if choice == "📝 จองใหม่":
    with st.form("booking_form", clear_on_submit=True):
        res = st.selectbox("เลือกรายการ", ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "ห้องประชุมชั้น 1"])
        name = st.text_input("ชื่อผู้จอง")
        dest = st.text_input("สถานที่ปลายทาง / ปักหมุด Google Maps")
        purpose = st.text_area("วัตถุประสงค์")
        t_start = st.datetime_input("เวลาเริ่ม", datetime.now())
        t_end = st.datetime_input("เวลาสิ้นสุด", datetime.now())
        
        if st.form_submit_button("ยืนยันการจอง"):
            data = {
                "resource": res, 
                "requester": name, 
                "destination": dest,
                "purpose": purpose,
                "start_time": t_start.isoformat(), 
                "end_time": t_end.isoformat(),
                "status": "Approved" # ตั้งให้ผ่านเลยในช่วงแรกเพื่อทดสอบ
            }
            supabase.table("bookings").insert(data).execute()
            st.success("✅ บันทึกข้อมูลเรียบร้อยแล้ว!")

elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("รายการที่มีการจองขณะนี้")
    now = datetime.now().isoformat()
    # ดึงเฉพาะรายการที่ยังไม่หมดเวลา
    res = supabase.table("bookings").select("*").gt("end_time", now).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        df = df[['resource', 'requester', 'start_time', 'end_time', 'purpose', 'destination']]
        df.columns = ['ทรัพยากร', 'ผู้จอง', 'เริ่ม', 'สิ้นสุด', 'วัตถุประสงค์', 'สถานที่/แผนที่']
        st.table(df)
    else:
        st.info("ขณะนี้ไม่มีรายการใช้งาน")
