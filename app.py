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

# ฟังก์ชันแจ้งเตือน LINE (ปรับให้รองรับสถานะ)
def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination, status_text="ส่งคำขอใหม่"):
    render_url = "https://line-booking-system.onrender.com/notify"
    
    # ตรวจสอบประเภทข้อมูลเวลาก่อนแปลงเป็น String
    start_str = t_start.strftime("%d/%m/%Y %H:%M") if isinstance(t_start, datetime) else str(t_start)
    end_str = t_end.strftime("%H:%M") if isinstance(t_end, datetime) else str(t_end)

    payload = {
        "id": booking_id,
        "resource": resource,
        "name": name,
        "dept": dept,
        "date": start_str,
        "end_date": end_str,
        "purpose": f"[{status_text}] {purpose}" 
    }
    
    try:
        requests.post(render_url, json=payload, timeout=5)
    except Exception as e:
        print(f"LINE Error: {e}")

# --- 2. ฟังก์ชันลบข้อมูลอัตโนมัติ (จบงานเกิน 24 ชม.) ---
def auto_delete_old_bookings():
    threshold_time = (datetime.now() - timedelta(hours=24)).isoformat()
    try:
        supabase.table("bookings").delete().lt("end_time", threshold_time).execute()
    except:
        pass

# --- 3. ตั้งค่าหน้าจอและ Sidebar ---
st.set_page_config(page_title="ระบบจองรถ & ห้องประชุม", layout="wide")
# --- ส่วนการปรับแต่งสี (CSS) ---
st.markdown("""
    <style>
    /* เปลี่ยนสีพื้นหลังของช่อง Input, Text Area และ Selectbox */
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"], .stNumberInput input {
        background-color: #E3F2FD !important; /* สีฟ้าอ่อน */
        color: #0D47A1 !important;           /* สีตัวอักษรน้ำเงินเข้มเพื่อให้ตัดกับพื้นหลัง */
        border: 1px solid #BBDEFB !important;
    }

    /* ปรับสีตอนเอาเมาส์ไปวาง (Hover) หรือกำลังพิมพ์ (Focus) */
    .stTextInput input:focus, .stTextArea textarea:focus {
        border: 2px solid #2196F3 !important;
        background-color: #E1F5FE !important;
    }
    </style>
""", unsafe_allow_html=True)
LOGO_URL = "https://lh3.googleusercontent.com/d/1zCjSjSbCO-mbsaGoDI6g0G-bfmyVfqFV"
st.sidebar.image(LOGO_URL, use_container_width=True)
st.sidebar.markdown("---")

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
            destination = st.text_input("สถานที่ปลายทาง", placeholder="เช่น บริษัท ABC"),"(f"[📍 เปิด Google Maps เพื่อค้นหาเส้นทาง](https://www.google.com/maps)")"
                        
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
        elif t_start < (datetime.now() - timedelta(minutes=5)):
            st.error("❌ ห้ามจองเวลาย้อนหลัง")
        elif t_start >= t_end:
            st.error("❌ เวลาเริ่มต้นต้องก่อนเวลาสิ้นสุด")
        else:
            # เช็คเวลาซ้อน
            check_res = supabase.table("bookings").select("*").eq("resource", res).eq("status", "Approved").execute()
            df_check = pd.DataFrame(check_res.data)
            is_overlap = False
            if not df_check.empty:
                df_check['start_time'] = pd.to_datetime(df_check['start_time']).dt.tz_localize(None)
                df_check['end_time'] = pd.to_datetime(df_check['end_time']).dt.tz_localize(None)
                overlap = df_check[~((df_check['start_time'] >= t_end) | (df_check['end_time'] <= t_start))]
                if not overlap.empty:
                    is_overlap = True

            if is_overlap:
                st.error(f"❌ ไม่ว่าง: {res} ถูกจองไปแล้วในช่วงเวลานี้")
            else:
                # แก้ไข Syntax Error: ปิดปีกกาให้ครบถ้วนสมบูรณ์
                data = {
                    "resource": res, 
                    "requester": name, 
                    "phone": phone, 
                    "dept": dept, 
                    "start_time": t_start.isoformat(), 
                    "end_time": t_end.isoformat(), 
                    "purpose": reason, 
                    "destination": destination, 
                    "status": "Pending"
                }
                response = supabase.table("bookings").insert(data).execute()
                if response.data:
                    booking_id = response.data[0]['id']
                    send_line_notification(booking_id, res, name, dept, t_start, t_end, reason, destination, "Pending")
                    st.success("✅ ส่งคำขอเรียบร้อยแล้ว!")

# --- หน้า Admin (อนุมัติ) ---
elif choice == "🔑 Admin (อนุมัติ)":
    st.subheader("🔑 ระบบจัดการการจอง (Admin Dashboard)")
    admin_pw = st.text_input("🔒 ใส่รหัสผ่าน Admin", type="password")
    
    if admin_pw == "s1234":
        st.success("Login สำเร็จ!")
        st.markdown("---")
        try:
            res_pending = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute()
            pending_items = res_pending.data
        except Exception as e:
            st.error(f"Error: {e}")
            pending_items = []

        if not pending_items:
            st.info("✅ ไม่มีรายการรออนุมัติ")
        else:
            for item in pending_items:
                with st.container(border=True):
                    col1, col2, col3 = st.columns([3, 2, 2])
                    with col1:
                        # Admin สามารถแก้ไขข้อมูลได้ทันทีก่อนอนุมัติ
                        edit_res = st.text_input("รายการ", str(item['resource']), key=f"res_{item['id']}")
                        edit_req = st.text_input("ผู้ขอ", str(item['requester']), key=f"req_{item['id']}")
                        edit_dept = st.text_input("แผนก", str(item['dept']), key=f"dept_{item['id']}")
                    with col2:
                        edit_start = st.text_input("เริ่ม", str(item['start_time']), key=f"start_{item['id']}")
                        edit_end = st.text_input("สิ้นสุด", str(item['end_time']), key=f"end_{item['id']}")
                        edit_purp = st.text_area("เหตุผล", str(item['purpose']), key=f"purp_{item['id']}")
                    with col3:
                        st.write("")
                        btn_app, btn_rej, btn_can = st.columns(3)
                        # ปุ่มอนุมัติ
                        if btn_app.button("✅", key=f"app_{item['id']}", help="อนุมัติ", use_container_width=True):
                            up_data = {"resource": edit_res, "requester": edit_req, "dept": edit_dept, "start_time": edit_start, "end_time": edit_end, "purpose": edit_purp, "status": "Approved"}
                            supabase.table("bookings").update(up_data).eq("id", item['id']).execute()
                            send_line_notification(item['id'], edit_res, edit_req, edit_dept, edit_start, edit_end, edit_purp, "-", "Approved")
                            st.rerun()
                        # ปุ่มปฏิเสธ
                        if btn_rej.button("❌", key=f"rej_{item['id']}", help="ปฏิเสธ", use_container_width=True):
                            supabase.table("bookings").update({"status": "Rejected"}).eq("id", item['id']).execute()
                            send_line_notification(item['id'], edit_res, edit_req, edit_dept, edit_start, edit_end, edit_purp, "-", "Rejected")
                            st.rerun()
                        # ปุ่มลบรายการ
                        if btn_can.button("🗑️", key=f"can_{item['id']}", help="ลบรายการ", use_container_width=True):
                            supabase.table("bookings").delete().eq("id", item['id']).execute()
                            st.rerun()
    elif admin_pw != "":
        st.error("❌ รหัสผ่านไม่ถูกต้อง")

# --- หน้าตารางงาน (Real-time) ---
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางงานปัจจุบันและล่วงหน้า")
    view_cat = st.radio("เลือกประเภทที่จะแสดง", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"], horizontal=True)
    now_iso = datetime.now().isoformat()
    # ดึงข้อมูลที่อนุมัติแล้วและยังไม่จบงาน
    res_db = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).order("start_time").execute()
    df = pd.DataFrame(res_db.data)
    
    if df.empty:
        st.info("ขณะนี้ไม่มีรายการจอง")
    else:
        # กรองข้อมูลตามประเภท
        if view_cat == "รถยนต์":
            df = df[df['resource'].isin(["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"])]
        elif view_cat == "ห้องประชุม":
            df = df[df['resource'].isin(["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"])]

        if not df.empty:
            df_show = df.copy().reset_index(drop=True)
            df_show.index += 1
            df_show.insert(0, 'ลำดับ/No.', df_show.index)
            # จัดรูปแบบเวลาสำหรับการแสดงในตาราง
            df_show['start_fmt'] = pd.to_datetime(df_show['start_time']).dt.strftime('%d/%m/%Y %H:%M')
            df_show['end_fmt'] = pd.to_datetime(df_show['end_time']).dt.strftime('%d/%m/%Y %H:%M')
            
            # รักษาหัวข้อตารางภาษาไทย/อังกฤษ ตามรูปแบบเดิม
            df_disp = df_show[['ลำดับ/No.', 'resource', 'start_fmt', 'end_fmt', 'requester', 'purpose', 'destination']]
            df_disp.columns = ['ลำดับ / No.', 'รายการ / Resource', 'เวลาเริ่ม / Start Time', 'เวลาสิ้นสุด / End Time', 'ผู้จอง / Name', 'วัตถุประสงค์ / Purpose', 'ปลายทาง / Destination']
            st.dataframe(df_disp, use_container_width=True)

            # --- ส่วนแก้ไขข้อมูลโดย Admin ---
            st.markdown("---")
            st.subheader("🛠️ แก้ไขข้อมูล (Admin Only)")
            with st.expander("คลิกเพื่อแก้ไขรายการ"):
                edit_id = st.selectbox("เลือก ID ที่ต้องการแก้ไข", df['id'].tolist(), key="sel_id_table")
                # ดึงข้อมูลแถวที่เลือก
                row = df[df['id'] == edit_id].iloc[0]
                
                with st.form("edit_form_table"):
                    col_e1, col_e2 = st.columns(2)
                    n_res = col_e1.text_input("รายการ / Resource", str(row['resource']))
                    n_req = col_e1.text_input("ผู้จอง / Name", str(row['requester']))
                    n_start = col_e2.text_input("เริ่ม (ISO Format)", str(row['start_time']))
                    n_end = col_e2.text_input("สิ้นสุด (ISO Format)", str(row['end_time']))
                    
                    pw = st.text_input("ใส่รหัสผ่านเพื่อบันทึก (1234)", type="password")
                    b_save, b_del, b_cls = st.columns(3)
                    
                    if b_save.form_submit_button("💾 บันทึก"):
                        if pw == "1234":
                            supabase.table("bookings").update({"resource": n_res, "requester": n_req, "start_time": n_start, "end_time": n_end}).eq("id", edit_id).execute()
                            st.success("บันทึกข้อมูลเรียบร้อย!")
                            st.rerun()
                        else: st.error("รหัสผ่านไม่ถูกต้อง")
                    
                    if b_del.form_submit_button("🗑️ ลบรายการ"):
                        if pw == "s1234":
                            supabase.table("bookings").delete().eq("id", edit_id).execute()
                            st.rerun()
                        else: st.error("รหัสผ่านไม่ถูกต้อง")

                    if b_cls.form_submit_button("✖️ ปิด"):
                        st.rerun()
