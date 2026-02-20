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
    # ลบข้อมูลที่จบไปแล้วเกิน 45 วัน (เพื่อประหยัดพื้นที่ฐานข้อมูล)
    threshold_delete = (datetime.now() - timedelta(days=45)).isoformat()
    try:
        supabase.table("bookings").delete().lt("end_time", threshold_delete).execute()
    except:
        pass

# --- 3. ตั้งค่าหน้าจอและ Sidebar ---
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
        res = st.selectbox("เลือกรายการ", ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"] if cat == "รถยนต์" else ["ห้องชั้น 1", "ห้อง VIP", "ห้องชั้น 2"])
        dest = st.text_input("สถานที่ปลายทาง") if cat == "รถยนต์" else "Office"
        name = st.text_input("ชื่อผู้จอง")
        phone = st.text_input("เบอร์โทรศัพท์")
        dept = st.text_input("แผนก")
    with col2:
        d_start = st.date_input("วันที่เริ่ม", datetime.now().date())
        t_start_raw = st.text_input("เวลาเริ่ม (พิมพ์ 4 หลัก เช่น 0800)", value="0800", max_chars=4)
        st.markdown("---")
        d_end = st.date_input("วันที่สิ้นสุด", value=d_start, min_value=d_start)
        t_end_raw = st.text_input("เวลาสิ้นสุด (พิมพ์ 4 หลัก เช่น 1700)", value="1700", max_chars=4)
        reason = st.text_area("วัตถุประสงค์")

        try:
            ts_fmt = format_time_string(t_start_raw)
            te_fmt = format_time_string(t_end_raw)
            t_start = datetime.combine(d_start, datetime.strptime(ts_fmt, "%H:%M").time())
            t_end = datetime.combine(d_end, datetime.strptime(te_fmt, "%H:%M").time())
        except: t_start, t_end = None, None

    if st.button("ยืนยันการส่งคำขอจอง"):
        if not name or not dept or not t_start: st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")
        elif t_start >= t_end: st.error("❌ เวลาเริ่มต้องก่อนเวลาสิ้นสุด")
        else:
            data = {"resource": res, "requester": name, "phone": phone, "dept": dept, "start_time": t_start.isoformat(), "end_time": t_end.isoformat(), "purpose": reason, "destination": dest, "status": "Pending"}
            resp = supabase.table("bookings").insert(data).execute()
            if resp.data:
                send_line_notification(resp.data[0]['id'], res, name, dept, t_start, t_end, reason, dest)
                st.success("✅ ส่งคำขอเรียบร้อย!")

# --- หน้าตารางงาน (Real-time) ---
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางงานปัจจุบัน (รายการจะหายไปหลังจากจบงาน 24 ชม.)")
    # 💡 Logic: กรองเฉพาะงานที่จบไปแล้วไม่เกิน 24 ชม. (gt = มากกว่า เวลาปัจจุบันลบออก 24 ชม.)
    show_threshold = (datetime.now() - timedelta(hours=24)).isoformat()
    res_db = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", show_threshold).order("start_time").execute()
    df = pd.DataFrame(res_db.data)
    
    if df.empty: st.info("ขณะนี้ไม่มีรายการจอง")
    else:
        df['start_fmt'] = pd.to_datetime(df['start_time'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M')
        df['end_fmt'] = pd.to_datetime(df['end_time'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M')
        st.dataframe(df[['resource', 'start_fmt', 'end_fmt', 'requester', 'purpose', 'destination']], use_container_width=True)

# --- หน้า Admin (อนุมัติ) ---
elif choice == "🔑 Admin (อนุมัติ)":
    st.subheader("🔑 ระบบอนุมัติการจอง")
    pw = st.text_input("รหัสผ่าน Admin", type="password")
    if pw == "s1234":
        items = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute().data
        if not items: st.info("ไม่มีรายการรออนุมัติ")
        else:
            for item in items:
                with st.container(border=True):
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        # แยกปฏิทินและเวลาให้ Admin แก้ไขได้
                        c_s = pd.to_datetime(item['start_time'])
                        a_d = st.date_input("วันที่", c_s.date(), key=f"d_{item['id']}")
                        a_t = st.text_input("เวลาเริ่ม (4 หลัก)", c_s.strftime("%H%M"), key=f"t_{item['id']}", max_chars=4)
                        st.write(f"🚗 {item['resource']} | 👤 {item['requester']} | 📍 {item.get('destination','-')}")
                    if col2.button("อนุมัติ ✅", key=f"app_{item['id']}"):
                        supabase.table("bookings").update({"status": "Approved"}).eq("id", item['id']).execute()
                        st.rerun()

# --- หน้ารายงานประจำเดือน (เฉพาะรถยนต์ 45 วัน) ---
elif choice == "📊 รายงานประจำเดือน":
    st.subheader("📊 รายงานการใช้รถยนต์ (ย้อนหลัง 45 วัน)")
    admin_pw = st.text_input("รหัสผ่านเข้าดูรายงาน", type="password")
    if admin_pw == "s1234":
        cars = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"]
        # ดึงข้อมูลย้อนหลังทั้งหมดที่อยู่ในฐานข้อมูล (ซึ่งเราลบทุก 45 วัน)
        res_rep = supabase.table("bookings").select("*").in_("resource", cars).eq("status", "Approved").execute()
        if res_rep.data:
            df_rep = pd.DataFrame(res_rep.data)
            df_rep['start_time'] = pd.to_datetime(df_rep['start_time'])
            df_rep['Month-Year'] = df_rep['start_time'].dt.strftime('%m/%Y')
            sel_m = st.selectbox("เลือกเดือน", df_rep['Month-Year'].unique())
            final_df = df_rep[df_rep['Month-Year'] == sel_m].copy()
            st.dataframe(final_df[['resource', 'requester', 'dept', 'start_time', 'destination', 'purpose']], use_container_width=True)
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("📥 Download Excel (เฉพาะรถยนต์)", buffer.getvalue(), f"Car_Report_{sel_m}.xlsx")
    elif admin_pw != "": st.error("รหัสผ่านไม่ถูกต้อง")
