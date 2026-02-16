import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests
import json

# --- 1. การเชื่อมต่อ Supabase ---
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co" 
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ฟังก์ชันแจ้งเตือน LINE
def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination, status_text="ส่งคำขอใหม่"):
    render_url = "https://line-booking-system.onrender.com/notify"
    
    start_str = t_start.strftime("%d/%m/%Y %H:%M") if isinstance(t_start, datetime) else str(t_start)
    end_str = t_end.strftime("%H:%M") if isinstance(t_end, datetime) else str(t_end)

    payload = {
        "id": booking_id,
        "resource": resource,
        "name": name,
        "dept": dept,
        "date": start_str,
        "end_date": end_str,
        "destination": destination, # เพิ่มบรรทัดนี้เพื่อส่งปลายทางไป LINE
        "purpose": f"[{status_text}] {purpose}" 
    }
    
    try:
        requests.post(render_url, json=payload, timeout=5)
    except Exception as e:
        print(f"LINE Error: {e}")

# --- 2. ฟังก์ชันลบข้อมูลอัตโนมัติ ---
def auto_delete_old_bookings():
    threshold_time = (datetime.now() - timedelta(hours=24)).isoformat()
    try:
        supabase.table("bookings").delete().lt("end_time", threshold_time).execute()
    except:
        pass

# --- 3. ตั้งค่าหน้าจอ ---
st.set_page_config(page_title="ระบบจองรถ & ห้องประชุม", layout="wide")
auto_delete_old_bookings()

st.title("ระบบจองรถยนต์และห้องประชุม Online")
menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin (อนุมัติ)"]
choice = st.sidebar.selectbox("เมนู", menu)

# --- หน้าจองใหม่ ---
if choice == "📝 จองใหม่":
    st.subheader("รายละเอียดการจอง")
    col1, col2 = st.columns(2)
    with col1:
        cat = st.radio("ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"])
        if cat == "รถยนต์":
            res = st.selectbox("เลือกคัน", ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"])
            destination = st.text_input("สถานที่ปลายทาง", placeholder="เช่น บริษัท ABC")
        else:
            res = st.selectbox("เลือกห้อง", ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"])
            destination = "Office"
        name = st.text_input("ชื่อผู้จอง")
        phone = st.text_input("เบอร์โทรศัพท์")
        dept = st.text_input("แผนก")
    with col2:
        t_start = st.datetime_input("เวลาเริ่ม", datetime.now())
        t_end = st.datetime_input("เวลาสิ้นสุด", datetime.now() + timedelta(hours=1))
        reason = st.text_area("วัตถุประสงค์การใช้งาน")

    if st.button("ยืนยันการส่งคำขอจอง"):
        if not name or not phone or not reason or not dept:
            st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")
        else:
            data = {
                "resource": res, "requester": name, "phone": phone, "dept": dept, 
                "start_time": t_start.isoformat(), "end_time": t_end.isoformat(), 
                "purpose": reason, "destination": destination, "status": "Pending"
            }
            response = supabase.table("bookings").insert(data).execute()
            if response.data:
                booking_id = response.data[0]['id']
                send_line_notification(booking_id, res, name, dept, t_start, t_end, reason, destination, "Pending")
                st.success("✅ ส่งคำขอเรียบร้อยแล้ว!")

# --- หน้า Admin (อนุมัติ) ---
elif choice == "🔑 Admin (อนุมัติ)":
    st.subheader("🔑 ระบบจัดการการจอง")
    admin_pw = st.text_input("🔒 ใส่รหัสผ่าน Admin", type="password")
    
    if admin_pw == "s1234":
        st.success("Login สำเร็จ!")
        res_pending = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute()
        pending_items = res_pending.data if res_pending.data else []

        for item in pending_items:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 2, 2])
                with col1:
                    edit_res = st.text_input("รายการ", item['resource'], key=f"res_{item['id']}")
                    edit_req = st.text_input("ผู้ขอ", item['requester'], key=f"req_{item['id']}")
                    edit_dest = st.text_input("ปลายทาง", item.get('destination', '-'), key=f"dest_{item['id']}")
                with col2:
                    edit_start = st.text_input("เริ่ม", item['start_time'], key=f"start_{item['id']}")
                    edit_purp = st.text_area("เหตุผล", item['purpose'], key=f"purp_{item['id']}")
                with col3:
                    if st.button("✅", key=f"app_{item['id']}", use_container_width=True):
                        up_data = {"resource": edit_res, "requester": edit_req, "destination": edit_dest, "status": "Approved"}
                        supabase.table("bookings").update(up_data).eq("id", item['id']).execute()
                        send_line_notification(item['id'], edit_res, edit_req, "-", edit_start, "-", edit_purp, edit_dest, "Approved")
                        st.rerun()
                    if st.button("❌", key=f"rej_{item['id']}", use_container_width=True):
                        supabase.table("bookings").update({"status": "Rejected"}).eq("id", item['id']).execute()
                        st.rerun()

# --- หน้าตารางงาน (Real-time) ---
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางงานปัจจุบัน")
    now_iso = datetime.now().isoformat()
    res_db = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).order("start_time").execute()
    df = pd.DataFrame(res_db.data)
    if not df.empty:
        st.dataframe(df[['resource', 'start_time', 'requester', 'destination']], use_container_width=True)
