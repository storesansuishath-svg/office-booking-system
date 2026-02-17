import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests

# --- 1. การเชื่อมต่อ Supabase ---
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co" 
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ฟังก์ชันแจ้งเตือน (คงไว้ตามที่คุณต้องการ)
def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination, status_text="Pending"):
    render_url = "https://line-booking-system.onrender.com/notify"
    start_str = t_start.strftime("%d/%m/%Y %H:%M") if isinstance(t_start, datetime) else str(t_start)
    end_str = t_end.strftime("%H:%M") if isinstance(t_end, datetime) else str(t_end)

    payload = {
        "id": booking_id, "resource": resource, "name": name, "dept": dept,
        "date": start_str, "end_date": end_str, "purpose": purpose, "destination": destination
    }
    try: requests.post(render_url, json=payload, timeout=5)
    except: pass

def auto_delete_old_bookings():
    threshold_time = (datetime.now() - timedelta(hours=24)).isoformat()
    try: supabase.table("bookings").delete().lt("end_time", threshold_time).execute()
    except: pass

# --- 3. UI และ CSS (คงเดิม 100%) ---
st.set_page_config(page_title="ระบบจองรถ & ห้องประชุม", layout="wide")
st.markdown("""
    <style>
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"], .stNumberInput input {
        background-color: #E3F2FD !important;
        color: #0D47A1 !important;
        border: 1px solid #BBDEFB !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border: 2px solid #2196F3 !important;
        background-color: #E1F5FE !important;
    }
    </style>
""", unsafe_allow_html=True)

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
        name, phone, dept = st.text_input("ชื่อผู้จอง"), st.text_input("เบอร์โทรศัพท์"), st.text_input("แผนก")
    with col2:
        t_start = st.datetime_input("เวลาเริ่ม", datetime.now())
        t_end = st.datetime_input("เวลาสิ้นสุด", datetime.now() + timedelta(hours=1))
        reason = st.text_area("วัตถุประสงค์การใช้งาน")

    if st.button("ยืนยันการส่งคำขอจอง"):
        if not name or not phone or not reason or not dept:
            st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")
        else:
            # เช็คเวลาซ้อน
            check_res = supabase.table("bookings").select("*").eq("resource", res).eq("status", "Approved").execute()
            df_check = pd.DataFrame(check_res.data)
            is_overlap = False
            if not df_check.empty:
                df_check['start_time'] = pd.to_datetime(df_check['start_time']).dt.tz_localize(None)
                df_check['end_time'] = pd.to_datetime(df_check['end_time']).dt.tz_localize(None)
                overlap = df_check[~((df_check['start_time'] >= t_end) | (df_check['end_time'] <= t_start))]
                if not overlap.empty: is_overlap = True

            if is_overlap:
                st.error(f"❌ ไม่ว่าง: {res} ถูกจองไปแล้ว")
            else:
                data = {
                    "resource": res, "requester": name, "phone": phone, "dept": dept,
                    "start_time": t_start.isoformat(), "end_time": t_end.isoformat(),
                    "purpose": reason, "destination": destination, "status": "Pending"
                }
                response = supabase.table("bookings").insert(data).execute()
                if response.data:
                    send_line_notification(response.data[0]['id'], res, name, dept, t_start, t_end, reason, destination)
                    st.success("✅ ส่งคำขอเรียบร้อยแล้ว!")

# --- หน้า Admin (คงเดิม 100%) ---
elif choice == "🔑 Admin (อนุมัติ)":
    st.subheader("🔑 ระบบจัดการการจอง (Admin Dashboard)")
    if st.text_input("🔒 ใส่รหัสผ่าน Admin", type="password") == "s1234":
        pending_items = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute().data
        if not pending_items:
            st.info("✅ ไม่มีรายการรออนุมัติ")
        else:
            for item in pending_items:
                with st.container(border=True):
                    col1, col2, col3 = st.columns([3, 2, 1])
                    with col1:
                        e_res = st.text_input("รายการ", item['resource'], key=f"res_{item['id']}")
                        e_req = st.text_input("ผู้ขอ", item['requester'], key=f"req_{item['id']}")
                    with col2:
                        e_purp = st.text_area("เหตุผล", item['purpose'], key=f"purp_{item['id']}")
                    with col3:
                        if st.button("✅", key=f"app_{item['id']}"):
                            supabase.table("bookings").update({"status": "Approved"}).eq("id", item['id']).execute()
                            st.rerun()
                        if st.button("❌", key=f"rej_{item['id']}"):
                            supabase.table("bookings").update({"status": "Rejected"}).eq("id", item['id']).execute()
                            st.rerun()

# --- หน้าตารางงาน (คงเดิม 100%) ---
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางงานปัจจุบัน")
    res_db = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", datetime.now().isoformat()).order("start_time").execute()
    df = pd.DataFrame(res_db.data)
    if df.empty:
        st.info("ไม่มีรายการจอง")
    else:
        df['เวลาเริ่ม'] = pd.to_datetime(df['start_time']).dt.strftime('%d/%m/%Y %H:%M')
        st.dataframe(df[['resource', 'เวลาเริ่ม', 'requester', 'destination']], use_container_width=True)
