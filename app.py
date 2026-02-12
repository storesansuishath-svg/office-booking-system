import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests  # เพิ่มสำหรับ LINE
import json      # เพิ่มสำหรับ LINE

# --- 1. การเชื่อมต่อ Supabase ---
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co" 
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- [ส่วนที่เพิ่ม] ตั้งค่า LINE Messaging API ---
LINE_ACCESS_TOKEN = "BMEKLnhpRvRzArHJsnTzulIyqefXrwYo6QDBroRLMbGcV16/Ca+8eI5v5H5AfgTEOCwMD47HldTFuCBve9JRa1uAlAuq24sK2Iv/C5T/+p8Qrf3rxQKbOiaiH4CDQWf64AYuUbzSiuiPYdnrSWhm0gdB04t89/1O/w1cDnyilFU="
GROUP_ID = "Cd762a95cecb9396d5a4f9e328159c46b"

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

# --- 2. ฟังก์ชันลบข้อมูลอัตโนมัติ (จบงานเกิน 24 ชม.) ---
def auto_delete_old_bookings():
    threshold_time = (datetime.now() - timedelta(hours=24)).isoformat()
    try:
        supabase.table("bookings").delete().lt("end_time", threshold_time).execute()
    except:
        pass

# --- 3. ตั้งค่าหน้าจอและ Logo บริษัท ---
st.set_page_config(page_title="ระบบจองรถ & ห้องประชุม", layout="wide")

# ลิงก์โลโก้แบบ Direct Link
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
            destination = st.text_input("สถานที่ปลายทาง", placeholder="เช่น บริษัท ABC")
        else:
            res = st.selectbox("เลือกห้อง", ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"])
            destination = "Office"
        name = st.text_input("ชื่อผู้จอง")
        phone = st.text_input("เบอร์โทรศัพท์")
        dept = st.text_input("แผนก")
    with col2:
        t_start = st.datetime_input("เวลาเริ่ม", datetime.now())
        t_end = st.datetime_input("เวลาสิ้นสุด", datetime.now())
        reason = st.text_area("วัตถุประสงค์การใช้งาน")

    if st.button("ยืนยันการส่งคำขอจอง"):
        if not name or not phone or not reason or not dept:
            st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")
        elif t_start >= t_end:
            st.error("❌ เวลาเริ่มต้นต้องก่อนเวลาสิ้นสุด")
        else:
            check_res = supabase.table("bookings").select("*").eq("resource", res).eq("status", "Approved").execute()
            df_check = pd.DataFrame(check_res.data)
            is_overlap = False
            if not df_check.empty:
                df_check['start_time'] = pd.to_datetime(df_check['start_time']).dt.tz_localize(None)
                df_check['end_time'] = pd.to_datetime(df_check['end_time']).dt.tz_localize(None)
                overlap = df_check[~((df_check['start_time'] >= t_end) | (df_check['end_time'] <= t_start))]
                if not overlap.empty: is_overlap = True

            if is_overlap:
                st.error(f"❌ ไม่ว่าง: {res} ถูกจองไปแล้วในช่วงเวลานี้")
            else:
                data = {"resource": res, "requester": name, "phone": phone, "dept": dept, 
                        "start_time": t_start.isoformat(), "end_time": t_end.isoformat(), 
                        "purpose": reason, "destination": destination, "status": "Pending"}
                supabase.table("bookings").insert(data).execute()
                
                # --- [ส่วนที่เพิ่ม] แจ้งเตือน LINE เมื่อจองใหม่ ---
                send_line_notification("มีคำขอจองใหม่!", res, name, "Pending", f"📍 ปลายทาง: {destination}")
                
                st.success("✅ ส่งคำขอเรียบร้อยแล้ว!")

elif choice == "🔑 Admin (อนุมัติ)":
    st.subheader("🔑 ระบบจัดการการจอง (Admin Dashboard)")
    
    # 1. เช็ค Password
    admin_pw = st.text_input("🔒 ใส่รหัสผ่าน Admin", type="password")
    
    if admin_pw == "1234": # <--- แก้รหัสผ่านของคุณตรงนี้
        st.success("Login สำเร็จ!")
        st.markdown("---")

        # 2. ดึงข้อมูลที่รออนุมัติ (Pending)
        try:
            res = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute()
            pending_items = res.data
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
            pending_items = []

        # 3. แสดงผลแบบ Card (การ์ดรายการ)
        if not pending_items:
            st.info("✅ เยี่ยมมาก! ไม่มีรายการรออนุมัติในขณะนี้")
        else:
            st.write(f"📌 มีรายการรอตรวจสอบทั้งหมด **{len(pending_items)}** รายการ")
            
            for item in pending_items:
                with st.container(border=True): # สร้างกรอบล้อมรอบ
                    col1, col2, col3 = st.columns([3, 2, 2])
                    
                    with col1:
                        st.markdown(f"**🚗/🏢 : {item['resource']}**")
                        st.text(f"👤 ผู้ขอ: {item['requester']} ({item['dept']})")
                        st.caption(f"📝 เหตุผล: {item['purpose']}")
                    
                    with col2:
                        try:
                            start_dt = datetime.fromisoformat(item['start_time'])
                            end_dt = datetime.fromisoformat(item['end_time'])
                            date_str = start_dt.strftime("%d/%m/%Y")
                            time_str = f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
                        except:
                            date_str, time_str = "-", "-"
                            
                        st.markdown(f"📅 **{date_str}**")
                        st.markdown(f"⏰ **{time_str}**")
                        st.caption(f"📍 {item['destination']}")

                    with col3:
                        st.write("") # เว้นระยะ
                        btn_approve, btn_reject = st.columns(2)
                        
                        # ปุ่มอนุมัติ (สีเขียว)
                        if btn_approve.button("✅", key=f"app_{item['id']}", help="อนุมัติ", use_container_width=True):
                            supabase.table("bookings").update({"status": "Approved"}).eq("id", item['id']).execute()
                            st.toast(f"✅ อนุมัติคุณ {item['requester']} เรียบร้อย!", icon="🎉")
                            st.rerun()

                        # ปุ่มปฏิเสธ (สีแดง)
                        if btn_reject.button("❌", key=f"rej_{item['id']}", help="ปฏิเสธ", use_container_width=True):
                            supabase.table("bookings").update({"status": "Rejected"}).eq("id", item['id']).execute()
                            st.toast(f"❌ ปฏิเสธรายการแล้ว", icon="🗑️")
                            st.rerun()
    
    elif admin_pw != "":
        st.error("❌ รหัสผ่านไม่ถูกต้อง")

# --- หน้าตารางงาน (แสดงทุกรายการที่ยังไม่จบงาน) ---
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางงานปัจจุบันและล่วงหน้า")
    view_cat = st.radio("เลือกประเภทที่จะแสดง", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"], horizontal=True)
    now = datetime.now().isoformat()
    res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now).order("start_time").execute()
    df = pd.DataFrame(res.data)
    
    if df.empty:
        st.info("ขณะนี้ไม่มีรายการจอง")
    else:
        if view_cat == "รถยนต์":
            car_list = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"]
            df = df[df['resource'].isin(car_list)]
        elif view_cat == "ห้องประชุม":
            room_list = ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]
            df = df[df['resource'].isin(room_list)]

        if df.empty:
            st.info(f"ไม่มีรายการจองในหมวด {view_cat}")
        else:
            df = df.reset_index(drop=True)
            df.index += 1
            df.insert(0, 'ลำดับ/No.', df.index)
            df['start_time'] = pd.to_datetime(df['start_time']).dt.strftime('%d/%m/%Y %H:%M')
            df['end_time'] = pd.to_datetime(df['end_time']).dt.strftime('%d/%m/%Y %H:%M')
            df_display = df[['ลำดับ/No.', 'resource', 'start_time', 'end_time', 'requester', 'purpose', 'destination']]
            df_display.columns = [
                'ลำดับ / No.', 'รายการ / Resource', 'เวลาเริ่ม / Start Time', 
                'เวลาสิ้นสุด / End Time', 'ผู้จอง / Name', 'วัตถุประสงค์ / Purpose', 'ปลายทาง / Destination'
            ]
            st.dataframe(df_display, use_container_width=True)
