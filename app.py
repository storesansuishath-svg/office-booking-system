import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests

# --- 1. การเชื่อมต่อ Supabase ---
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co" 
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ฟังก์ชันแจ้งเตือน LINE
def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination):
    render_url = "https://line-booking-system.onrender.com/notify"
    try:
        start_str = t_start.strftime("%d/%m/%Y %H:%M") if isinstance(t_start, datetime) else str(t_start)
        end_str = t_end.strftime("%H:%M") if isinstance(t_end, datetime) else str(t_end)
        payload = {
            "id": booking_id, "resource": resource, "name": name, "dept": dept,
            "date": start_str, "end_date": end_str, "purpose": purpose, "destination": destination
        }
        requests.post(render_url, json=payload, timeout=5)
    except: pass

def auto_delete_old_bookings():
    threshold_time = (datetime.now() - timedelta(hours=24)).isoformat()
    try: supabase.table("bookings").delete().lt("end_time", threshold_time).execute()
    except: pass

# --- 3. ตั้งค่าหน้าจอและ CSS (คงเดิม 100%) ---
st.set_page_config(page_title="ระบบจองรถ & ห้องประชุม", layout="wide")
st.markdown("""
    <style>
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"], .stNumberInput input {
        background-color: #E3F2FD !important; color: #0D47A1 !important; border: 1px solid #BBDEFB !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus { border: 2px solid #2196F3 !important; background-color: #E1F5FE !important; }
    </style>
""", unsafe_allow_html=True)

auto_delete_old_bookings()
st.title("ระบบจองรถยนต์และห้องประชุม Online")
menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin (อนุมัติ)"]
choice = st.sidebar.selectbox("เมนู", menu)

# --- หน้าจองใหม่ (คงเดิม) ---
if choice == "📝 จองใหม่":
    st.subheader("รายละเอียดการจอง")
    col1, col2 = st.columns(2)
    with col1:
        cat = st.radio("ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"])
        res = st.selectbox("เลือกรายการ", ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"] if cat == "รถยนต์" else ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"])
        destination = st.text_input("สถานที่ปลายทาง", placeholder="เช่น บริษัท ABC") if cat == "รถยนต์" else "Office"
        name, phone, dept = st.text_input("ชื่อผู้จอง"), st.text_input("เบอร์โทรศัพท์"), st.text_input("แผนก")
    with col2:
        t_start = st.datetime_input("เวลาเริ่ม", datetime.now())
        t_end = st.datetime_input("เวลาสิ้นสุด", datetime.now() + timedelta(hours=1))
        reason = st.text_area("วัตถุประสงค์การใช้งาน")

    if st.button("ยืนยันการส่งคำขอจอง"):
        if not name or not reason: st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")
        else:
            data = {"resource": res, "requester": name, "phone": phone, "dept": dept, "start_time": t_start.isoformat(), "end_time": t_end.isoformat(), "purpose": reason, "destination": destination, "status": "Pending"}
            resp = supabase.table("bookings").insert(data).execute()
            if resp.data:
                send_line_notification(resp.data[0]['id'], res, name, dept, t_start, t_end, reason, destination)
                st.success("✅ ส่งคำขอเรียบร้อยแล้ว!")

# --- หน้าตารางงาน (ดึง "แก้ไข" และ "หัวข้อภาษาคู่" กลับมา) ---
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางงานปัจจุบันและล่วงหน้า")
    view_cat = st.radio("เลือกประเภท", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"], horizontal=True)
    res_db = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", datetime.now().isoformat()).order("start_time").execute()
    df = pd.DataFrame(res_db.data)
    
    if not df.empty:
        if view_cat == "รถยนต์": df = df[df['resource'].isin(["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"])]
        elif view_cat == "ห้องประชุม": df = df[df['resource'].isin(["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"])]

        if not df.empty:
            df_show = df.copy().reset_index(drop=True)
            df_show.index += 1
            df_show.insert(0, 'ลำดับ/No.', df_show.index)
            df_show['start_fmt'] = pd.to_datetime(df_show['start_time']).dt.strftime('%d/%m/%Y %H:%M')
            df_show['end_fmt'] = pd.to_datetime(df_show['end_time']).dt.strftime('%d/%m/%Y %H:%M')
            
            df_disp = df_show[['ลำดับ/No.', 'resource', 'start_fmt', 'end_fmt', 'requester', 'purpose', 'destination']]
            df_disp.columns = ['ลำดับ / No.', 'รายการ / Resource', 'เวลาเริ่ม / Start Time', 'เวลาสิ้นสุด / End Time', 'ผู้จอง / Name', 'วัตถุประสงค์ / Purpose', 'ปลายทาง / Destination']
            st.dataframe(df_disp, use_container_width=True)

            # --- ส่วนแก้ไขข้อมูล (ที่หายไป) ---
            st.markdown("---")
            st.subheader("🛠️ แก้ไขข้อมูล (Admin Only)")
            with st.expander("คลิกเพื่อแก้ไขรายการ"):
                edit_id = st.selectbox("เลือก ID ที่ต้องการแก้ไข", df['id'].tolist())
                row = df[df['id'] == edit_id].iloc[0]
                with st.form("edit_form"):
                    c_e1, c_e2 = st.columns(2)
                    n_res = c_e1.text_input("รายการ", str(row['resource']))
                    n_req = c_e1.text_input("ผู้จอง", str(row['requester']))
                    n_start = c_e2.text_input("เริ่ม (ISO)", str(row['start_time']))
                    n_end = c_e2.text_input("สิ้นสุด (ISO)", str(row['end_time']))
                    pw = st.text_input("รหัสผ่าน (1234)", type="password")
                    if st.form_submit_button("💾 บันทึก"):
                        if pw == "1234":
                            supabase.table("bookings").update({"resource": n_res, "requester": n_req, "start_time": n_start, "end_time": n_end}).eq("id", edit_id).execute()
                            st.rerun()

# --- หน้า Admin อนุมัติ (คงโครงสร้างเดิมที่ Admin แก้ไขได้ก่อนกด ✅) ---
elif choice == "🔑 Admin (อนุมัติ)":
    st.subheader("🔑 ระบบจัดการการจอง (Admin Dashboard)")
    if st.text_input("🔒 รหัสผ่าน Admin", type="password") == "s1234":
        items = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute().data
        for item in items:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 2, 2])
                with col1:
                    edit_res = st.text_input("รายการ", str(item['resource']), key=f"res_{item['id']}")
                    edit_req = st.text_input("ผู้ขอ", str(item['requester']), key=f"req_{item['id']}")
                with col2:
                    edit_start = st.text_input("เริ่ม", str(item['start_time']), key=f"s_{item['id']}")
                    edit_purp = st.text_area("เหตุผล", str(item['purpose']), key=f"p_{item['id']}")
                with col3:
                    st.write("")
                    b_app, b_rej, b_can = st.columns(3)
                    if b_app.button("✅", key=f"app_{item['id']}"):
                        up_data = {"resource": edit_res, "requester": edit_req, "start_time": edit_start, "status": "Approved"}
                        supabase.table("bookings").update(up_data).eq("id", item['id']).execute()
                        st.rerun()
                    if b_rej.button("❌", key=f"rej_{item['id']}"):
                        supabase.table("bookings").update({"status": "Rejected"}).eq("id", item['id']).execute()
                        st.rerun()
                    if b_can.button("🗑️", key=f"can_{item['id']}"):
                        supabase.table("bookings").delete().eq("id", item['id']).execute()
                        st.rerun()
