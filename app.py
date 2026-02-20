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

# ฟังก์ชันช่วยจัดการรูปแบบเวลา (0800 -> 08:00)
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

# --- 2. ฟังก์ชันลบข้อมูลอัตโนมัติ (เก็บข้อมูลไว้ 45 วันเพื่อรายงาน) ---
def auto_delete_old_bookings():
    threshold_delete = (datetime.now() - timedelta(days=45)).isoformat()
    try:
        supabase.table("bookings").delete().lt("end_time", threshold_delete).execute()
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
        if cat == "รถยนต์":
            if dest:
                st.link_button(f"🔍 ค้นหา '{dest}' บนแผนที่", f"https://www.google.com/maps/search/{dest}")
            else:
                st.link_button("📍 เปิด Google Maps", "https://www.google.com/maps")
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
            ts_f = format_time_string(t_start_raw); te_f = format_time_string(t_end_raw)
            t_start = datetime.combine(d_start, datetime.strptime(ts_f, "%H:%M").time())
            t_end = datetime.combine(d_end, datetime.strptime(te_f, "%H:%M").time())
        except: t_start, t_end = None, None

    # แก้ไขจุดที่ 1: การเยื้อง (Indentation) ของปุ่มบันทึก
    if st.button("ยืนยันการส่งคำขอจอง"):
        if not name or not dept or t_start is None: st.warning("⚠️ ข้อมูลไม่ครบ")
        elif t_start >= t_end: st.error("❌ เวลาเริ่มต้องก่อนเวลาสิ้นสุด")
        else:
            data = {"resource": res, "requester": name, "phone": phone, "dept": dept, "start_time": t_start.isoformat(), "end_time": t_end.isoformat(), "purpose": reason, "destination": dest, "status": "Pending"}
            resp = supabase.table("bookings").insert(data).execute()
            if resp.data:
                send_line_notification(resp.data[0]['id'], res, name, dept, t_start, t_end, reason, dest)
                st.success("✅ ส่งคำขอเรียบร้อย!")

# --- หน้าตารางงาน (Real-time) ---
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางงานปัจจุบัน (แสดงย้อนหลัง 24 ชม.)")
    # 💡 แก้ไขจุดที่ 2: ใช้ errors='coerce' ป้องกันหน้าจอสีแดง ValueError
    threshold_show = (datetime.now() - timedelta(hours=24)).isoformat()
    res_db = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", threshold_show).order("start_time").execute()
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
                        c_s = pd.to_datetime(item['start_time'], errors='coerce')
                        a_d = st.date_input("วันที่", c_s.date() if pd.notnull(c_s) else datetime.now().date(), key=f"d_{item['id']}")
                        a_t = st.text_input("เวลาเริ่ม (4 หลัก)", c_s.strftime("%H%M") if pd.notnull(c_s) else "0800", key=f"t_{item['id']}", max_chars=4)
                        st.write(f"🚗 {item['resource']} | 👤 {item['requester']} | 📍 {item.get('destination','-')}")
                    if col2.button("อนุมัติ ✅", key=f"app_{item['id']}"):
                        try:
                            f_t = format_time_string(a_t)
                            final_t = datetime.combine(a_d, datetime.strptime(f_t, "%H:%M").time()).isoformat()
                            supabase.table("bookings").update({"status": "Approved", "start_time": final_t}).eq("id", item['id']).execute()
                            st.rerun()
                        except: st.error("รูปแบบเวลาผิด")

# --- หน้ารายงานประจำเดือน ---
elif choice == "📊 รายงานประจำเดือน":
    st.subheader("📊 รายงาน (เก็บย้อนหลัง 45 วัน)")
    admin_pw = st.text_input("รหัสผ่านดูรายงาน", type="password")
    if admin_pw == "s1234":
        cars = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"]
        res_rep = supabase.table("bookings").select("*").in_("resource", cars).eq("status", "Approved").execute()
        if res_rep.data:
            df_rep = pd.DataFrame(res_rep.data)
            df_rep['start_time'] = pd.to_datetime(df_rep['start_time'], errors='coerce')
            df_rep['Month-Year'] = df_rep['start_time'].dt.strftime('%m/%Y')
            sel_m = st.selectbox("เลือกเดือน", df_rep['Month-Year'].unique())
            final_df = df_rep[df_rep['Month-Year'] == sel_m].copy()
            st.dataframe(final_df[['resource', 'requester', 'dept', 'start_time', 'destination', 'purpose']], use_container_width=True)
            
            # 💡 แก้ไขจุดที่ 3: ป้องกัน ModuleNotFoundError
            buffer = io.BytesIO()
            try:
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    final_df.to_excel(writer, index=False)
                st.download_button("📥 Download Excel", buffer.getvalue(), f"Car_Report_{sel_m}.xlsx")
            except:
                # ถ้ายังไม่ได้ลง xlsxwriter ให้ใช้ CSV แทนชั่วคราวเพื่อไม่ให้เว็บค้าง
                st.download_button("📥 Download CSV (สำรอง)", final_df.to_csv(index=False).encode('utf-8-sig'), "report.csv")
