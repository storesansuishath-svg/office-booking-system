import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests
import json

# --- 1. การเชื่อมต่อ Supabase ---
# (ใช้ URL และ Key เดิมที่คุณให้มา)
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co"
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. ฟังก์ชันส่ง LINE Notification (ส่งได้ทั้งตอนจองและตอนอนุมัติ) ---
def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination, status="Pending"):
    render_url = "https://line-booking-system.onrender.com/notify"
    
    # จัด Format วันที่ให้สวยงาม
    if isinstance(t_start, str):
        date_display = t_start # กรณีส่งเป็น string มาอยู่แล้ว
    else:
        date_display = t_start.strftime("%d/%m/%Y %H:%M")

    payload = {
        "id": booking_id,
        "resource": resource,
        "name": name,
        "dept": dept,
        "date": date_display,
        "end_date": t_end if isinstance(t_end, str) else t_end.strftime("%H:%M"),
        "purpose": f"[{status}] {purpose}", # เพิ่มสถานะเข้าไปในวัตถุประสงค์เพื่อให้บอทตัวเดิมแสดงผลได้เลย
        "status": status # ส่งแยกไปด้วยเผื่อบอทเวอร์ชันใหม่รองรับ
    }
    
    try:
        requests.post(render_url, json=payload, timeout=5)
    except Exception as e:
        st.error(f"LINE Notification Error: {e}")

# --- 3. ฟังก์ชันลบข้อมูลอัตโนมัติ (จบงานเกิน 24 ชม.) ---
def auto_delete_old_bookings():
    threshold_time = (datetime.now() - timedelta(hours=24)).isoformat()
    try:
        supabase.table("bookings").delete().lt("end_time", threshold_time).execute()
    except:
        pass

# --- 4. ตั้งค่าหน้าจอและ UI ---
st.set_page_config(page_title="ระบบจองรถ & ห้องประชุม", layout="wide")
auto_delete_old_bookings()

# Sidebar
LOGO_URL = "https://lh3.googleusercontent.com/d/1zCjSjSbCO-mbsaGoDI6g0G-bfmyVfqFV" 
st.sidebar.image(LOGO_URL, use_container_width=True)
st.sidebar.markdown("---")
menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin Control"]
choice = st.sidebar.selectbox("เมนู", menu)

# --- [หน้าจองใหม่] ---
if choice == "📝 จองใหม่":
    st.title("📝 ระบบส่งคำขอจองทรัพยากร")
    
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            cat = st.radio("ประเภท", ["รถยนต์", "ห้องประชุม"], horizontal=True)
            if cat == "รถยนต์":
                res = st.selectbox("เลือกคัน", ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"])
                destination = st.text_input("สถานที่ปลายทาง", placeholder="เช่น บริษัท ABC")
            else:
                res = st.selectbox("เลือกห้อง", ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"])
                destination = "Office"
            name = st.text_input("ชื่อผู้จอง")
            dept = st.text_input("แผนก")
            phone = st.text_input("เบอร์โทรศัพท์")

        with col2:
            t_start = st.datetime_input("เวลาเริ่ม", datetime.now(), step=15)
            t_end = st.datetime_input("เวลาสิ้นสุด", datetime.now() + timedelta(hours=1), step=15)
            reason = st.text_area("วัตถุประสงค์การใช้งาน")

        if st.button("🚀 ยืนยันการจอง", use_container_width=True):
            now = datetime.now()
            # 1. เช็กค่าว่าง
            if not name or not phone or not reason or not dept:
                st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")
            # 2. เช็กจองย้อนหลัง (เผื่อเวลาให้ 5 นาที)
            elif t_start < (now - timedelta(minutes=5)):
                st.error("❌ ไม่สามารถจองเวลาย้อนหลังได้")
            # 3. เช็กเวลาเริ่มต้น-สิ้นสุด
            elif t_start >= t_end:
                st.error("❌ เวลาเริ่มต้นต้องก่อนเวลาสิ้นสุด")
            else:
                # 4. เช็ก Overlap (เฉพาะที่ Approved แล้ว)
                check_res = supabase.table("bookings").select("*").eq("resource", res).eq("status", "Approved").execute()
                df_check = pd.DataFrame(check_res.data)
                is_overlap = False
                if not df_check.empty:
                    df_check['start_time'] = pd.to_datetime(df_check['start_time']).dt.tz_localize(None)
                    df_check['end_time'] = pd.to_datetime(df_check['end_time']).dt.tz_localize(None)
                    overlap = df_check[~((df_check['start_time'] >= t_end) | (df_check['end_time'] <= t_start))]
                    if not overlap.empty: is_overlap = True

                if is_overlap:
                    st.error(f"❌ ช่วงเวลานี้ {res} ถูกจองไปแล้ว")
                else:
                    data = {
                        "resource": res, "requester": name, "phone": phone, "dept": dept, 
                        "start_time": t_start.isoformat(), "end_time": t_end.isoformat(), 
                        "purpose": reason, "destination": destination, "status": "Pending"
                    }
                    resp = supabase.table("bookings").insert(data).execute()
                    if resp.data:
                        send_line_notification(resp.data[0]['id'], res, name, dept, t_start, t_end, reason, destination, "Pending")
                        st.success("✅ ส่งคำขอเรียบร้อย! กรุณารอ Admin อนุมัติ")

# --- [หน้าตารางงาน + ระบบแก้ไข] ---
elif choice == "📅 ตารางงาน (Real-time)":
    st.title("📅 ตารางการใช้งาน")
    tab_view, tab_edit = st.tabs(["📋 ดูตารางงาน", "🛠️ แก้ไขข้อมูล (Admin Only)"])
    
    # ดึงข้อมูลเฉพาะที่อนุมัติแล้วและยังไม่หมดเวลา
    now_iso = datetime.now().isoformat()
    res_data = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).order("start_time").execute()
    df = pd.DataFrame(res_data.data)

    with tab_view:
        if df.empty:
            st.info("ไม่มีรายการจองในขณะนี้")
        else:
            df_display = df.copy()
            df_display['เวลา'] = pd.to_datetime(df_display['start_time']).dt.strftime('%d/%m %H:%M') + " - " + pd.to_datetime(df_display['end_time']).dt.strftime('%H:%M')
            st.dataframe(df_display[['resource', 'เวลา', 'requester', 'dept', 'destination', 'purpose']], use_container_width=True)

    with tab_edit:
        if df.empty:
            st.write("ไม่มีข้อมูลให้อัปเดต")
        else:
            selected_id = st.selectbox("เลือกรายการที่จะแก้ไข (อ้างอิงจาก ID)", df['id'])
            item = df[df['id'] == selected_id].iloc[0]
            
            with st.form("edit_schedule_form"):
                c1, c2 = st.columns(2)
                e_res = c1.text_input("ทรัพยากร", item['resource'])
                e_name = c1.text_input("ชื่อผู้จอง", item['requester'])
                e_dest = c1.text_input("ปลายทาง", item['destination'])
                e_start = c2.text_input("เริ่ม (YYYY-MM-DD HH:MM)", item['start_time'])
                e_end = c2.text_input("สิ้นสุด (YYYY-MM-DD HH:MM)", item['end_time'])
                e_purp = c2.text_area("วัตถุประสงค์", item['purpose'])
                
                edit_pw = st.text_input("🔑 ใส่รหัสผ่านเพื่อบันทึก", type="password")
                if st.form_submit_button("💾 บันทึกการเปลี่ยนแปลง"):
                    if edit_pw == "1234":
                        up_data = {"resource": e_res, "requester": e_name, "destination": e_dest, "start_time": e_start, "end_time": e_end, "purpose": e_purp}
                        supabase.table("bookings").update(up_data).eq("id", selected_id).execute()
                        st.success("แก้ไขข้อมูลเรียบร้อยแล้ว!")
                        st.rerun()
                    else:
                        st.error("❌ รหัสผ่านไม่ถูกต้อง")

# --- [หน้า Admin Control] ---
elif choice == "🔑 Admin Control":
    st.title("🔑 ระบบอนุมัติและจัดการ")
    admin_pw = st.text_input("🔒 ใส่รหัสผ่าน Admin", type="password")
    
    if admin_pw == "1234":
        pending_res = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute()
        if not pending_res.data:
            st.info("ไม่มีรายการรออนุมัติ")
        else:
            for item in pending_res.data:
                with st.expander(f"📥 คำขอจากคุณ {item['requester']} - {item['resource']}"):
                    col_a, col_b = st.columns(2)
                    # Admin สามารถแก้ไขข้อมูลก่อนกดอนุมัติได้ที่นี่
                    adm_res = col_a.text_input("ทรัพยากร", item['resource'], key=f"adm_res_{item['id']}")
                    adm_name = col_a.text_input("ชื่อผู้จอง", item['requester'], key=f"adm_name_{item['id']}")
                    adm_dest = col_a.text_input("ปลายทาง", item['destination'], key=f"adm_dest_{item['id']}")
                    adm_start = col_b.text_input("เริ่ม", item['start_time'], key=f"adm_s_{item['id']}")
                    adm_end = col_b.text_input("สิ้นสุด", item['end_time'], key=f"adm_e_{item['id']}")
                    adm_purp = col_b.text_area("วัตถุประสงค์", item['purpose'], key=f"adm_p_{item['id']}")
                    
                    btn_app, btn_rej, _ = st.columns([1,1,2])
                    if btn_app.button("✅ อนุมัติ", key=f"btn_app_{item['id']}"):
                        final_data = {
                            "resource": adm_res, "requester": adm_name, "destination": adm_dest,
                            "start_time": adm_start, "end_time": adm_end, "purpose": adm_purp, "status": "Approved"
                        }
                        supabase.table("bookings").update(final_data).eq("id", item['id']).execute()
                        # แจ้งเตือนกลับไปที่ LINE ว่าอนุมัติแล้ว
                        send_line_notification(item['id'], adm_res, adm_name, item['dept'], adm_start, adm_end, adm_purp, adm_dest, "Approved")
                        st.rerun()
                    
                    if btn_rej.button("❌ ปฏิเสธ", key=f"btn_rej_{item['id']}"):
                        supabase.table("bookings").update({"status": "Rejected"}).eq("id", item['id']).execute()
                        # แจ้งเตือนกลับไปที่ LINE ว่าถูกปฏิเสธ
                        send_line_notification(item['id'], adm_res, adm_name, item['dept'], adm_start, adm_end, adm_purp, adm_dest, "Rejected")
                        st.rerun()
    elif admin_pw != "":
        st.error("รหัสผ่านไม่ถูกต้อง")
