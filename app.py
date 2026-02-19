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

# Session State สำหรับจำการแก้ไข
if 'editing_id' not in st.session_state:
    st.session_state.editing_id = None

def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination, status_text="Pending"):
    render_url = "https://line-booking-system.onrender.com/notify"
    start_str = t_start.strftime("%d/%m/%Y %H:%M") if isinstance(t_start, datetime) else str(t_start)
    end_str = t_end.strftime("%H:%M") if isinstance(t_end, datetime) else str(t_end)
    payload = {"id": booking_id, "resource": resource, "name": name, "dept": dept, "date": start_str, "end_date": end_str, "purpose": purpose, "destination": destination}
    try:
        requests.post(render_url, json=payload, timeout=15)
        st.toast("🔔 ส่งแจ้งเตือนเข้า LINE แล้ว", icon="✅")
    except: pass

def auto_delete_old_bookings():
    threshold_time = (datetime.now() - timedelta(hours=24)).isoformat()
    try: supabase.table("bookings").delete().lt("end_time", threshold_time).execute()
    except: pass

# --- 3. ตั้งค่าหน้าจอและ Sidebar ---
st.set_page_config(page_title="ระบบจองรถ & ห้องประชุม", layout="wide")
st.markdown("""
    <style>
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        background-color: #E3F2FD !important; color: #0D47A1 !important; border: 1px solid #BBDEFB !important;
    }
    </style>
""", unsafe_allow_html=True)

auto_delete_old_bookings()
st.sidebar.markdown("### เมนูใช้งาน")
choice = st.sidebar.selectbox("เมนู", ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin (อนุมัติ)"])

# --- หน้าจองใหม่ (คงเดิม 100%) ---
if choice == "📝 จองใหม่":
    st.title("📝 ลงทะเบียนจองใหม่")
    col1, col2 = st.columns(2)
    with col1:
        cat = st.radio("ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"])
        if cat == "รถยนต์":
            res = st.selectbox("เลือกคัน", ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"])
            destination = st.text_input("สถานที่ปลายทาง")
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
        data = {"resource": res, "requester": name, "phone": phone, "dept": dept, "start_time": t_start.isoformat(), "end_time": t_end.isoformat(), "purpose": reason, "destination": destination, "status": "Pending"}
        response = supabase.table("bookings").insert(data).execute()
        if response.data:
            send_line_notification(response.data[0]['id'], res, name, dept, t_start, t_end, reason, destination)
            st.success("✅ ส่งคำขอเรียบร้อยแล้ว!")

# --- หน้า Admin (อนุมัติ) ---
elif choice == "🔑 Admin (อนุมัติ)":
    st.subheader("🔑 ระบบจัดการการจอง (รออนุมัติ)")
    admin_pw = st.text_input("🔒 ใส่รหัสผ่าน Admin", type="password")
    if admin_pw == "s1234":
        res_pending = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute()
        if not res_pending.data:
            st.info("✅ ไม่มีรายการรออนุมัติ")
        else:
            for item in res_pending.data:
                with st.container(border=True):
                    col1, col2, col3 = st.columns([3, 3, 1])
                    with col1:
                        e_res = st.text_input("รายการ", item['resource'], key=f"p_res_{item['id']}")
                        e_req = st.text_input("ผู้ขอ", item['requester'], key=f"p_req_{item['id']}")
                        e_dept = st.text_input("แผนก", item['dept'], key=f"p_dept_{item['id']}")
                    with col2:
                        e_dest = st.text_input("ปลายทาง", item.get('destination', '-'), key=f"p_dest_{item['id']}")
                        e_start = st.text_input("เริ่ม", item['start_time'], key=f"p_start_{item['id']}")
                        e_purp = st.text_area("เหตุผล", item['purpose'], key=f"p_purp_{item['id']}")
                    with col3:
                        if st.button("✅", key=f"ok_{item['id']}", use_container_width=True):
                            up = {"resource": e_res, "requester": e_req, "dept": e_dept, "destination": e_dest, "start_time": e_start, "status": "Approved"}
                            supabase.table("bookings").update(up).eq("id", item['id']).execute()
                            send_line_notification(item['id'], e_res, e_req, e_dept, e_start, "", e_purp, e_dest, "Approved")
                            st.rerun()
                        if st.button("🗑️", key=f"del_{item['id']}", use_container_width=True):
                            supabase.table("bookings").delete().eq("id", item['id']).execute()
                            st.rerun()

# --- หน้าตารางงาน (Real-time) ---
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางงานปัจจุบันและล่วงหน้า")
    now_iso = datetime.now().isoformat()
    res_db = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).order("start_time").execute()
    
    if not res_db.data:
        st.info("ขณะนี้ไม่มีรายการจอง")
    else:
        # สร้างหัวตารางเลียนแบบของเดิมเป๊ะๆ
        h = st.columns([0.5, 1.5, 1.5, 1.5, 1.5, 1.5, 0.8])
        labels = ['No.', 'รายการ / Resource', 'เวลาเริ่ม', 'ผู้จอง', 'วัตถุประสงค์', 'ปลายทาง', 'จัดการ']
        for col, label in zip(h, labels): col.markdown(f"**{label}**")
        st.markdown("---")

        for i, row in enumerate(res_db.data):
            c = st.columns([0.5, 1.5, 1.5, 1.5, 1.5, 1.5, 0.8])
            c[0].write(i+1)
            c[1].write(row['resource'])
            c[2].write(pd.to_datetime(row['start_time']).strftime('%d/%m/%y %H:%M'))
            c[3].write(row['requester'])
            c[4].write(row['purpose'])
            c[5].write(row.get('destination', '-'))
            
            # ปุ่มแก้ไขท้ายบรรทัด
            if c[6].button("✏️ แก้ไข", key=f"edit_btn_{row['id']}"):
                st
