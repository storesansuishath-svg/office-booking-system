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

# --- [ADD] CSS สำหรับไฟกระพริบสีแดง ---
st.markdown("""
    <style>
    @keyframes blinker { 50% { opacity: 0; } }
    .blink { animation: blinker 1s linear infinite; color: red; font-weight: bold; }
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        background-color: #E3F2FD !important; color: #0D47A1 !important; border: 1px solid #BBDEFB !important;
    }
    </style>
""", unsafe_allow_html=True)

# ฟังก์ชันจัดการรูปแบบเวลา (0800 -> 08:00)
def format_time_string(t_raw):
    clean = str(t_raw).replace(":", "").strip()
    if len(clean) == 4:
        return f"{clean[:2]}:{clean[2:]}"
    return clean

# --- [ADD] ฟังก์ชันเช็กคิวชนกัน (Conflict Checker) ---
def check_booking_conflict(resource, start_time, end_time):
    # ดึงเฉพาะรายการที่อนุมัติแล้วของทรัพยากรนั้นๆ
    res = supabase.table("bookings").select("*").eq("resource", resource).eq("status", "Approved").execute()
    new_s = datetime.fromisoformat(start_time)
    new_e = datetime.fromisoformat(end_time)
    
    for item in res.data:
        ex_s = datetime.fromisoformat(item['start_time'])
        ex_e = datetime.fromisoformat(item['end_time'])
        # Logic: ถ้า (เวลาเริ่มใหม่ < เวลาจบเก่า) และ (เวลาจบใหม่ > เวลาเริ่มเก่า) แสดงว่าทับกัน
        if new_s < ex_e and new_e > ex_s:
            return True, item['requester']
    return False, None

def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination, status_text="Pending"):
    render_url = "https://line-booking-system.onrender.com/notify"
    GROUP_ID = "Cad74a32468ca40051bd7071a6064660d" 
    try:
        s_str = t_start.strftime("%d/%m/%Y %H:%M") if isinstance(t_start, datetime) else str(t_start)
        e_str = t_end.strftime("%H:%M") if isinstance(t_end, datetime) else str(t_end)
        payload = {
            "id": booking_id, "target_id": GROUP_ID, "resource": resource, 
            "name": name, "dept": dept, "date": s_str, "end_date": e_str, 
            "purpose": purpose, "destination": destination, "status": status_text
        }
        requests.post(render_url, json=payload, timeout=10)
        st.toast("🔔 ส่งแจ้งเตือน LINE แล้ว", icon="✅")
    except: pass

def auto_delete_old_bookings():
    threshold_delete = (datetime.now() - timedelta(days=45)).isoformat()
    try: supabase.table("bookings").delete().lt("end_time", threshold_delete).execute()
    except: pass

# --- เตรียมข้อมูล Dashboard & Alert ---
auto_delete_old_bookings()
pending_data = supabase.table("bookings").select("id").eq("status", "Pending").execute().data
pending_count = len(pending_data)

LOGO_URL = "https://lh3.googleusercontent.com/d/1zCjSjSbCO-mbsaGoDI6g0G-bfmyVfqFV"
st.sidebar.image(LOGO_URL, use_container_width=True)

# --- [ADD] ไฟกระพริบเตือนรออนุมัติใน Sidebar ---
if pending_count > 0:
    st.sidebar.markdown(f'<p class="blink">⚠️ มีรายการรออนุมัติ: {pending_count} รายการ</p>', unsafe_allow_html=True)

st.sidebar.markdown("---")
st.title("ระบบจองรถยนต์และห้องประชุม Online")
menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin (อนุมัติ)", "📊 รายงานประจำเดือน"]
choice = st.sidebar.selectbox("เมนู", menu)

# --- หน้าจองใหม่ ---
if choice == "📝 จองใหม่":
    # --- [ADD] Quick Stats Dashboard ---
    st.subheader("📊 ภาพรวมการใช้งานวันนี้")
    today_start = datetime.now().replace(hour=0, minute=0, second=0).isoformat()
    today_end = datetime.now().replace(hour=23, minute=59, second=59).isoformat()
    today_bookings = supabase.table("bookings").select("id").eq("status", "Approved").gte("start_time", today_start).lte("start_time", today_end).execute().data
    
    m1, m2, m3 = st.columns(3)
    m1.metric("จองวันนี้ (รายการ)", len(today_bookings))
    m2.metric("รออนุมัติ (รายการ)", pending_count)
    m3.metric("สถานะระบบ", "Online", delta="Normal")
    st.markdown("---")

    st.subheader("รายละเอียดการจอง")
    col1, col2 = st.columns(2)
    with col1:
        cat = st.radio("ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"])
        res_list = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG"] if cat == "รถยนต์" else ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]
        res = st.selectbox("เลือกรายการ", res_list)
        dest = st.text_input("สถานที่ปลายทาง") if cat == "รถยนต์" else "Office"
        if cat == "รถยนต์" and dest:
            st.link_button(f"🔍 ค้นหา '{dest}'", f"https://www.google.com/maps/search/{dest}")
        name = st.text_input("ชื่อผู้จอง")
        phone = st.text_input("เบอร์โทรศัพท์")
        dept = st.text_input("แผนก")
    with col2:
        d_start = st.date_input("วันที่เริ่ม", datetime.now().date())
        t_start_raw = st.text_input("เวลาเริ่ม (เช่น 0800)", value="0800", max_chars=4)
        st.markdown("---")
        d_end = st.date_input("วันที่สิ้นสุด", value=d_start, min_value=d_start)
        t_end_raw = st.text_input("เวลาสิ้นสุด (เช่น 1700)", value="1700", max_chars=4)
        reason = st.text_area("วัตถุประสงค์")
        try:
            ts_f, te_f = format_time_string(t_start_raw), format_time_string(t_end_raw)
            t_start = datetime.combine(d_start, datetime.strptime(ts_f, "%H:%M").time())
            t_end = datetime.combine(d_end, datetime.strptime(te_f, "%H:%M").time())
        except: t_start, t_end = None, None

    if st.button("ยืนยันการส่งคำขอจอง"):
        if not name or not dept or t_start is None: st.warning("⚠️ ข้อมูลไม่ครบ")
        elif t_start >= t_end: st.error("❌ เวลาเริ่มต้องก่อนเวลาสิ้นสุด")
        else:
            # --- [ADD] เช็กคิวชนกันก่อน Insert ---
            is_conflict, user_conflict = check_booking_conflict(res, t_start.isoformat(), t_end.isoformat())
            if is_conflict:
                st.error(f"❌ ไม่สามารถจองได้! เนื่องจากเวลานี้ {res} ถูกจองแล้วโดยคุณ {user_conflict}")
            else:
                data = {"resource": res, "requester": name, "phone": phone, "dept": dept, "start_time": t_start.isoformat(), "end_time": t_end.isoformat(), "purpose": reason, "destination": dest, "status": "Pending"}
                resp = supabase.table("bookings").insert(data).execute()
                if resp.data:
                    send_line_notification(resp.data[0]['id'], res, name, dept, t_start, t_end, reason, dest)
                    st.success("✅ ส่งคำขอเรียบร้อย!")

# --- หน้าตารางงาน (Real-time) ---
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางงานปัจจุบันและล่วงหน้า")
    
    # --- [ADD] Advanced Filter ---
    f_col1, f_col2 = st.columns([2, 1])
    search_query = f_col1.text_input("🔍 ค้นหาชื่อผู้จอง / สถานที่", "")
    view_cat = f_col2.selectbox("กรองประเภท", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
    
    now_iso = datetime.now().isoformat()
    res_db = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).order("start_time").execute()
    df = pd.DataFrame(res_db.data)
    
    if df.empty: st.info("ขณะนี้ไม่มีรายการจอง")
    else:
        # กรองตามประเภท
        if view_cat == "รถยนต์": df = df[df['resource'].isin(["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG"])]
        elif view_cat == "ห้องประชุม": df = df[df['resource'].isin(["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"])]
        
        # กรองตามการค้นหา (Advanced Filter)
        if search_query:
            df = df[df['requester'].str.contains(search_query, na=False) | df['destination'].str.contains(search_query, na=False)]

        if not df.empty:
            df_show = df.copy().reset_index(drop=True)
            df_show.index += 1
            df_show.insert(0, 'ลำดับ/No.', df_show.index)
            df_show['start_fmt'] = pd.to_datetime(df_show['start_time'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M')
            df_show['end_fmt'] = pd.to_datetime(df_show['end_time'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M')
            df_disp = df_show[['ลำดับ/No.', 'resource', 'start_fmt', 'end_fmt', 'requester', 'purpose', 'destination']]
            df_disp.columns = ['ลำดับ / No.', 'รายการ / Resource', 'เวลาเริ่ม / Start Time', 'เวลาสิ้นสุด / End Time', 'ผู้จอง / Name', 'วัตถุประสงค์ / Purpose', 'ปลายทาง / Destination']
            st.dataframe(df_disp, use_container_width=True)

            st.markdown("---")
            st.subheader("🛠️ แก้ไข/ลบ ข้อมูล (Admin Only)")
            with st.expander("คลิกเพื่อแก้ไขรายการ"):
                selected_no = st.selectbox("เลือก No. ลำดับที่ต้องการแก้ไข", df_show['ลำดับ/No.'].tolist(), key="sel_no_table")
                row = df_show[df_show['ลำดับ/No.'] == selected_no].iloc[0]
                edit_id = row['id']
                
                with st.form("edit_form_table"):
                    col_e1, col_e2 = st.columns(2)
                    resource_options = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG", "ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]
                    try: current_index = resource_options.index(row['resource'])
                    except ValueError: current_index = 0

                    n_res = col_e1.selectbox("รายการ / Resource", options=resource_options, index=current_index)
                    n_req = col_e1.text_input("ผู้จอง / Name", str(row['requester']))
                    n_dept = col_e1.text_input("แผนก / Dept", str(row.get('dept', '-')))
                    n_dest = col_e1.text_input("ปลายทาง / Destination", str(row.get('destination', '-')))

                    dt_s = pd.to_datetime(row['start_time'], errors='coerce')
                    dt_e = pd.to_datetime(row['end_time'], errors='coerce')
                    n_d_s = col_e2.date_input("วันที่เริ่ม", dt_s.date() if pd.notnull(dt_s) else datetime.now().date())
                    n_t_s = col_e2.text_input("เวลาเริ่ม (4 หลัก)", value=dt_s.strftime("%H%M") if pd.notnull(dt_s) else "0800", max_chars=4)
                    n_d_e = col_e2.date_input("วันที่สิ้นสุด", dt_e.date() if pd.notnull(dt_e) else datetime.now().date())
                    n_t_e = col_e2.text_input("เวลาสิ้นสุด (4 หลัก)", value=dt_e.strftime("%H%M") if pd.notnull(dt_e) else "1700", max_chars=4)
                    n_purp = col_e2.text_area("วัตถุประสงค์ / Purpose", str(row.get('purpose', '-')))
                    
                    pw = st.text_input("รหัสผ่านสำหรับการดำเนินการ", type="password")
                    b_save, b_del, b_cls = st.columns(3)

                    if b_save.form_submit_button("💾 บันทึก"):
                        if pw == "s1234":
                            try:
                                fs, fe = format_time_string(n_t_s), format_time_string(n_t_e)
                                final_s = datetime.combine(n_d_s, datetime.strptime(fs, "%H:%M").time()).isoformat()
                                final_e = datetime.combine(n_d_e, datetime.strptime(fe, "%H:%M").time()).isoformat()
                                supabase.table("bookings").update({
                                    "resource": n_res, "requester": n_req, "dept": n_dept,
                                    "start_time": final_s, "end_time": final_e,
                                    "purpose": n_purp, "destination": n_dest
                                }).eq("id", edit_id).execute()
                                st.success("อัปเดตเรียบร้อย!"); st.rerun()
                            except: st.error("⚠️ เวลาผิดกรุณาตรวจสอบ")
                        else: st.error("❌ รหัสผ่านไม่ถูกต้อง")

                    if b_del.form_submit_button("🗑️ ลบรายการ"):
                        if pw == "s1234":
                            supabase.table("bookings").delete().eq("id", edit_id).execute()
                            st.success("ลบรายการแล้ว!"); st.rerun()
                        else: st.error("❌ รหัสผ่าน Admin สำหรับการลบไม่ถูกต้อง")
                    if b_cls.form_submit_button("✖️ ปิด"): st.rerun()

# --- หน้า Admin (อนุมัติ) ---
elif choice == "🔑 Admin (อนุมัติ)":
    st.subheader("🔑 ระบบจัดการอนุมัติ")
    admin_pw = st.text_input("Password Admin", type="password")
    if admin_pw == "s1234":
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
                            send_line_notification(item['id'], item['resource'], item['requester'], item['dept'], final_t, item['end_time'], item['purpose'], item.get('destination','-'), status_text="Approved")
                            st.success(f"อนุมัติคุณ {item['requester']} เรียบร้อย!")
                            st.rerun()
                        except: st.error("รูปแบบเวลาผิด")

                    if col2.button("ลบรายการ 🗑️", key=f"del_{item['id']}", use_container_width=True):
                        supabase.table("bookings").delete().eq("id", item['id']).execute()
                        st.warning(f"ลบรายการของคุณ {item['requester']} แล้ว")
                        st.rerun()

# --- หน้ารายงานประจำเดือน ---
elif choice == "📊 รายงานประจำเดือน":
    st.subheader("📊 รายงานการใช้รถยนต์ (ย้อนหลัง 45 วัน)")
    admin_pw = st.text_input("รหัสผ่านรายงาน", type="password")
    if admin_pw == "s1234":
        car_list = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG"]
        res_rep = supabase.table("bookings").select("*").in_("resource", car_list).eq("status", "Approved").execute()
        if res_rep.data:
            df_rep = pd.DataFrame(res_rep.data)
            df_rep['start_time'] = pd.to_datetime(df_rep['start_time'], errors='coerce')
            df_rep['Month-Year'] = df_rep['start_time'].dt.strftime('%m/%Y')
            sel_m = st.selectbox("เลือกเดือน", df_rep['Month-Year'].unique())
            final_df = df_rep[df_rep['Month-Year'] == sel_m].copy()
            final_df['เวลาเริ่ม'] = final_df['start_time'].dt.strftime('%d/%m/%Y %H:%M')
            final_df_out = final_df[['resource', 'requester', 'dept', 'เวลาเริ่ม', 'destination', 'purpose']]
            final_df_out.columns = ['รถยนต์', 'ผู้จอง', 'แผนก', 'เวลาเริ่ม', 'สถานที่', 'วัตถุประสงค์']
            st.dataframe(final_df_out, use_container_width=True)
            buffer = io.BytesIO()
            try:
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    final_df_out.to_excel(writer, index=False)
                st.download_button("📥 Download Excel", buffer.getvalue(), f"Car_Report_{sel_m}.xlsx")
            except:
                st.download_button("📥 Download CSV (สำรอง)", final_df_out.to_csv(index=False).encode('utf-8-sig'), "report.csv")
    elif admin_pw != "": st.error("รหัสผ่านไม่ถูกต้อง")
