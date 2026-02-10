import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests
import json

# --- 1. ตั้งค่าการเชื่อมต่อ (ใส่ข้อมูลจริงของคุณ) ---
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co" 
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
LINE_ACCESS_TOKEN = "xEUMxrdi/lmNoq9Mmsh4gnOm7lK7fvQrFTPSN4feHEJ/KsCClHZA6KzaTMm3gdMzOCwMD47HldTFuCBve9JRa1uAlAuq24sK2Iv/C5T/+p97lwL6RGIn/sErc0dqvlzNXOt8ACx3XnKQKXehVBpFyQdB04t89/1O/w1cDnyilFU="
GROUP_ID = "Cd762a95cecb9396d5a4f9e328159c46b" 

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. ฟังก์ชันส่ง LINE (รองรับหลายสถานะ) ---
def send_line_notification(title, resource, name, status, extra_info=""):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    
    status_icon = "🔔" if status == "Pending" else ("✅" if status == "Approved" else "❌")
    
    msg_text = (
        f"{status_icon} **{title}**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🔹 รายการ: {resource}\n"
        f"👤 ผู้จอง: {name}\n"
        f"📊 สถานะ: {status}\n"
        f"{extra_info}"
        f"\n━━━━━━━━━━━━━━━"
    )
    
    payload = {"to": GROUP_ID, "messages": [{"type": "text", "text": msg_text}]}
    try:
        requests.post(url, headers=headers, data=json.dumps(payload))
    except:
        pass

# --- 3. หน้าจอหลัก ---
st.set_page_config(page_title="Sansui Booking System", layout="wide")
LOGO_URL = "https://drive.google.com/uc?export=view&id=1zCjSjSbCO-mbsaGoDI6g0G-bfmyVfqFV"
st.sidebar.image(LOGO_URL, use_container_width=True)

menu = ["📝 จองใหม่", "📅 ดูสถานะและตารางงาน", "🔑 Admin (อนุมัติรายการ)"]
choice = st.sidebar.selectbox("เมนูหลัก", menu)

# --- ส่วนที่ 1: จองใหม่ ---
if choice == "📝 จองใหม่":
    st.header("📝 ลงทะเบียนจอง")
    col1, col2 = st.columns(2)
    with col1:
        cat = st.radio("ประเภท", ["รถยนต์", "ห้องประชุม"], horizontal=True)
        res = st.selectbox("เลือกรายการ", ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"] if cat == "รถยนต์" else ["ห้องใหญ่ ชั้น 1", "ห้องชั้น 2", "ห้อง VIP"])
        name = st.text_input("ชื่อผู้จอง")
        dept = st.text_input("แผนก")
    with col2:
        t_start = st.datetime_input("เริ่ม", datetime.now())
        t_end = st.datetime_input("สิ้นสุด", datetime.now() + timedelta(hours=1))
        dest = st.text_input("ปลายทาง/รายละเอียด")

    if st.button("🚀 ยืนยันการจอง"):
        data = {
            "resource": res, "requester": name, "dept": dept, 
            "start_time": t_start.isoformat(), "end_time": t_end.isoformat(),
            "destination": dest, "status": "Pending"
        }
        supabase.table("bookings").insert(data).execute()
        
        # แจ้งเตือนเข้า LINE กลุ่ม
        send_line_notification("มีคำขอจองใหม่!", res, name, "Pending", f"📍 ปลายทาง: {dest}")
        st.success("✅ ส่งคำขอแล้ว! รอ Admin อนุมัติในกลุ่ม LINE")

# --- ส่วนที่ 2: ดูสถานะและตารางงาน ---
elif choice == "📅 ดูสถานะและตารางงาน":
    st.header("📅 สถานะการจองทั้งหมด")
    res = supabase.table("bookings").select("*").order("created_at", desc=True).execute()
    df = pd.DataFrame(res.data)
    
    if not df.empty:
        # ปรับแต่งการแสดงผล
        df['start_time'] = pd.to_datetime(df['start_time']).dt.strftime('%d/%m %H:%M')
        df['status_display'] = df['status'].map({"Pending": "⏳ รออนุมัติ", "Approved": "✅ อนุมัติแล้ว", "Rejected": "❌ ปฏิเสธ"})
        
        st.dataframe(df[['resource', 'requester', 'start_time', 'status_display', 'destination']], 
                     column_config={"status_display": "สถานะ", "resource": "รายการ", "requester": "ผู้จอง"},
                     use_container_width=True, hide_index=True)
    else:
        st.info("ไม่มีข้อมูลการจอง")

# --- ส่วนที่ 3: Admin (อนุมัติรายการ) ---
elif choice == "🔑 Admin (อนุมัติรายการ)":
    st.header("🔑 ส่วนจัดการสำหรับ Admin")
    if st.text_input("รหัสผ่าน Admin", type="password") == "1234":
        # ดึงเฉพาะรายการที่สถานะเป็น Pending
        res = supabase.table("bookings").select("*").eq("status", "Pending").execute()
        df_p = pd.DataFrame(res.data)
        
        if not df_p.empty:
            for index, row in df_p.iterrows():
                with st.expander(f"📌 {row['resource']} - โดย {row['requester']}"):
                    st.write(f"**เวลา:** {row['start_time']} ถึง {row['end_time']}")
                    st.write(f"**วัตถุประสงค์:** {row['destination']}")
                    
                    c1, c2 = st.columns(2)
                    if c1.button("✅ อนุมัติ", key=f"app_{row['id']}"):
                        supabase.table("bookings").update({"status": "Approved"}).eq("id", row['id']).execute()
                        send_line_notification("ผลการอนุมัติ", row['resource'], row['requester'], "Approved")
                        st.rerun()
                    if c2.button("❌ ปฏิเสธ", key=f"rej_{row['id']}"):
                        supabase.table("bookings").update({"status": "Rejected"}).eq("id", row['id']).execute()
                        send_line_notification("ผลการอนุมัติ", row['resource'], row['requester'], "Rejected")
                        st.rerun()
        else:
            st.success("🎉 ไม่มีรายการค้างคา!")
