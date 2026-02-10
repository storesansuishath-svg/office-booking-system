import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests
import json

# --- 1. การเชื่อมต่อ (ใส่ข้อมูลจริงของคุณตรงนี้) ---
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co" 
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
# รหัสที่คุณได้มาล่าสุด
LINE_ACCESS_TOKEN = "xEUMxrdi/lmNoq9Mmsh4gnOm7lK7fvQrFTPSN4feHEJ/KsCClHZA6KzaTMm3gdMzOCwMD47HldTFuCBve9JRa1uAlAuq24sK2Iv/C5T/+p97lwL6RGIn/sErc0dqvlzNXOt8ACx3XnKQKXehVBpFyQdB04t89/1O/w1cDnyilFU="
GROUP_ID = "Cd762a95cecb9396d5a4f9e328159c46b" 

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. ฟังก์ชันเสริม (Helper Functions) ---

# ฟังก์ชันส่ง LINE Messaging API (Push Message)
def send_line_message(resource, name, dept, t_start, t_end, dest):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    msg_text = (
        f"🔔 **มีการจองใหม่!**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🔹 รายการ: {resource}\n"
        f"👤 ผู้จอง: {name} ({dept})\n"
        f"⏰ เวลา: {t_start.strftime('%d/%m %H:%M')} - {t_end.strftime('%H:%M')}\n"
        f"📍 ปลายทาง: {dest}\n"
        f"━━━━━━━━━━━━━━━"
    )
    payload = {
        "to": GROUP_ID,
        "messages": [{"type": "text", "text": msg_text}]
    }
    try:
        requests.post(url, headers=headers, data=json.dumps(payload))
    except:
        pass

# ฟังก์ชันลบข้อมูลอัตโนมัติ (จบงานเกิน 24 ชม.)
def auto_delete_old_bookings():
    threshold_time = (datetime.now() - timedelta(hours=24)).isoformat()
    try:
        supabase.table("bookings").delete().lt("end_time", threshold_time).execute()
    except:
        pass

# --- 3. การตั้งค่าหน้าจอและ Sidebar ---
st.set_page_config(page_title="Sansui Booking Online", layout="wide")

# แสดง Logo จากลิงก์ Google Drive
LOGO_URL = "https://drive.google.com/uc?export=view&id=1zCjSjSbCO-mbsaGoDI6g0G-bfmyVfqFV"
st.sidebar.image(LOGO_URL, use_container_width=True)
st.sidebar.markdown("---")

# เรียกฟังก์ชันล้างข้อมูลอัตโนมัติ
auto_delete_old_bookings()

menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin (อนุมัติ)", "📊 สรุปรายงาน"]
choice = st.sidebar.selectbox("เมนูหลัก / Menu", menu)

# ---------------------------------------------------------
# เมนู: จองใหม่
# ---------------------------------------------------------
if choice == "📝 จองใหม่":
    st.title("📝 รายละเอียดการจองใหม่")
    col1, col2 = st.columns(2)
    
    with col1:
        cat = st.radio("ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"], horizontal=True)
        if cat == "รถยนต์":
            res = st.selectbox("เลือกคัน / Car List", ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"])
            dest = st.text_input("สถานที่ปลายทาง / Destination", placeholder="ระบุสถานที่")
        else:
            res = st.selectbox("เลือกห้อง / Room List", ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"])
            dest = "Office / สำนักงาน"
        
        name = st.text_input("ชื่อผู้จอง / Name")
        phone = st.text_input("เบอร์โทรศัพท์ / Phone")
        dept = st.text_input("แผนก / Department")

    with col2:
        t_start = st.datetime_input("เวลาเริ่ม / Start Time", datetime.now())
        t_end = st.datetime_input("เวลาสิ้นสุด / End Time", datetime.now() + timedelta(hours=1))
        reason = st.text_area("วัตถุประสงค์การใช้งาน / Purpose")

    if st.button("🚀 ยืนยันการส่งคำขอจอง"):
        if not name or not dept:
            st.warning("⚠️ กรุณากรอกข้อมูลสำคัญ (ชื่อ/แผนก) ให้ครบถ้วน")
        elif t_start >= t_end:
            st.error("❌ เวลาเริ่มต้นต้องก่อนเวลาสิ้นสุด")
        else:
            # ตรวจสอบการจองทับซ้อน
            check = supabase.table("bookings").select("*").eq("resource", res).eq("status", "Approved").execute()
            df_check = pd.DataFrame(check.data)
            is_overlap = False
            if not df_check.empty:
                df_check['start_time'] = pd.to_datetime(df_check['start_time']).dt.tz_localize(None)
                df_check['end_time'] = pd.to_datetime(df_check['end_time']).dt.tz_localize(None)
                overlap = df_check[~((df_check['start_time'] >= t_end) | (df_check['end_time'] <= t_start))]
                if not overlap.empty: is_overlap = True

            if is_overlap:
                st.error(f"❌ ช่วงเวลานี้ {res} ไม่ว่าง กรุณาเลือกเวลาอื่น")
            else:
                data = {
                    "resource": res, "requester": name, "phone": phone, "dept": dept,
                    "start_time": t_start.isoformat(), "end_time": t_end.isoformat(),
                    "purpose": reason, "destination": dest, "status": "Pending"
                }
                supabase.table("bookings").insert(data).execute()
                
                # ส่ง LINE แจ้งเตือนเข้ากลุ่มทันที
                send_line_message(res, name, dept, t_start, t_end, dest)
                
                st.success("✅ ส่งคำขอแล้ว! แจ้งเตือนเข้ากลุ่ม LINE เรียบร้อย")

# ---------------------------------------------------------
# เมนู: ตารางงาน (Real-time)
# ---------------------------------------------------------
elif choice == "📅 ตารางงาน (Real-time)":
    st.title("📅 ตารางการใช้งานปัจจุบันและล่วงหน้า")
    view_cat = st.radio("เลือกประเภทที่จะแสดง:", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"], horizontal=True)
    
    now = datetime.now().isoformat()
    res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now).order("start_time").execute()
    df = pd.DataFrame(res.data)
    
    if df.empty:
        st.info("ขณะนี้ไม่มีรายการจองที่กำลังดำเนินอยู่หรือล่วงหน้า")
    else:
        # กรองตามประเภท
        car_list = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"]
        if view_cat == "รถยนต์":
            df = df[df['resource'].isin(car_list)]
        elif view_cat == "ห้องประชุม":
            df = df[~df['resource'].isin(car_list)]
            
        if df.empty:
            st.write(f"ไม่มีข้อมูลสำหรับหมวด {view_cat}")
        else:
            # จัดลำดับ No.
            df = df.reset_index(drop=True)
            df.index += 1
            df.insert(0, 'ลำดับ/No.', df.index)
            
            df['start_time'] = pd.to_datetime(df['start_time']).dt.strftime('%d/%m/%Y %H:%M')
            df['end_time'] = pd.to_datetime(df['end_time']).dt.strftime('%d/%m/%Y %H:%M')
            
            df_display = df[['ลำดับ/No.', 'resource', 'start_time', 'end_time', 'requester', 'purpose', 'destination']]
            df_display.columns = ['ลำดับ / No.', 'รายการ / Resource', 'เริ่ม / Start', 'สิ้นสุด / End', 'ผู้จอง / Name', 'วัตถุประสงค์ / Purpose', 'ปลายทาง / Destination']
            st.dataframe(df_display, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# เมนู: Admin (อนุมัติ)
# ---------------------------------------------------------
elif choice == "🔑 Admin (อนุมัติ)":
    st.title("🔑 ระบบจัดการสำหรับ Admin")
    pw = st.text_input("รหัสผ่าน Admin", type="password")
    if pw == "1234":
        res = supabase.table("bookings").select("*").eq("status", "Pending").execute()
        df_pending = pd.DataFrame(res.data)
        if df_pending.empty:
            st.info("ไม่มีรายการรออนุมัติ")
        else:
            st.write("รายการที่รอการตัดสินใจ:")
            st.table(df_pending[['id', 'resource', 'requester', 'dept', 'purpose']])
            target_id = st.number_input("ใส่ ID ที่ต้องการจัดการ", step=1, min_value=1)
            c1, c2 = st.columns(2)
            if c1.button("✅ อนุมัติ (Approve)"):
                supabase.table("bookings").update({"status": "Approved"}).eq("id", target_id).execute()
                st.rerun()
            if c2.button("❌ ปฏิเสธ (Reject)"):
                supabase.table("bookings").update({"status": "Rejected"}).eq("id", target_id).execute()
                st.rerun()

# ---------------------------------------------------------
# เมนู: สรุปรายงาน (Dashboard)
# ---------------------------------------------------------
elif choice == "📊 สรุปรายงาน":
    st.title("📊 สถิติการใช้งานรายเดือน")
    res = supabase.table("bookings").select("*").eq("status", "Approved").execute()
    df_stat = pd.DataFrame(res.data)
    
    if df_stat.empty:
        st.info("ยังไม่มีข้อมูลสถิติในขณะนี้")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.write("**🏎️ ยอดการใช้งานแยกตามทรัพยากร**")
            st.bar_chart(df_stat['resource'].value_counts())
        with col2:
            st.write("**🏢 ยอดการจองแยกตามแผนก**")
            st.bar_chart(df_stat['dept'].value_counts())
            
        st.markdown("---")
        csv = df_stat.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Download Report (CSV)", csv, "report.csv", "text/csv")
