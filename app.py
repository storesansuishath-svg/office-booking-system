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
    clean = t_raw.replace(":", "").strip()
    if len(clean) == 4:
        return f"{clean[:2]}:{clean[2:]}"
    return t_raw

def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination, status_text="Pending"):
    render_url = "https://line-booking-system.onrender.com/notify"
    
    # แปลงเวลาเป็น String สำหรับส่งเข้า LINE
    start_str = t_start.strftime("%d/%m/%Y %H:%M") if isinstance(t_start, datetime) else str(t_start)
    end_str = t_end.strftime("%H:%M") if isinstance(t_end, datetime) else str(t_end)

    payload = {
        "id": booking_id,
        "resource": resource,
        "name": name,
        "dept": dept,
        "date": start_str,
        "end_date": end_str,
        "purpose": purpose,
        "destination": destination
    }
    
    try:
        resp = requests.post(render_url, json=payload, timeout=15)
        if resp.status_code == 200:
            st.toast("🔔 ส่งแจ้งเตือนเข้า LINE แล้ว", icon="✅")
    except:
        st.error("⚠️ ไม่สามารถส่งแจ้งเตือน LINE ได้ (Server อาจจะหลับ)")

# --- 2. ฟังก์ชันลบข้อมูลอัตโนมัติ (ขยายเป็น 45 วัน เพื่อทำรายงาน) ---
def auto_delete_old_bookings():
    threshold_time = (datetime.now() - timedelta(days=45)).isoformat()
    try:
        supabase.table("bookings").delete().lt("end_time", threshold_time).execute()
    except:
        pass

# --- 3. ตั้งค่าหน้าจอและ Sidebar ---
st.set_page_config(page_title="ระบบจองรถ & ห้องประชุม", layout="wide")
st.markdown("""
    <style>
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        background-color: #E3F2FD !important;
        color: #0D47A1 !important;
        border: 1px solid #BBDEFB !important;
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
        # ส่วนวันที่และเวลา (พิมพ์เลข 4 หลัก)
        d_start = st.date_input("วันที่เริ่ม", datetime.now().date())
        t_start_raw = st.text_input("เวลาเริ่ม (เช่น 0800)", value="0800", max_chars=4)
        
        st.markdown("---")
        
        d_end = st.date_input("วันที่สิ้นสุด", value=d_start, min_value=d_start)
        t_end_raw = st.text_input("เวลาสิ้นสุด (เช่น 1700)", value="1700", max_chars=4)
        
        reason = st.text_area("วัตถุประสงค์การใช้งาน")

        # Logic แปลงค่า 4 หลัก -> HH:mm
        try:
            t_s_fmt = format_time_string(t_start_raw)
            t_e_fmt = format_time_string(t_end_raw)
            t_start = datetime.combine(d_start, datetime.strptime(t_s_fmt, "%H:%M").time())
            t_end = datetime.combine(d_end, datetime.strptime(t_e_fmt, "%H:%M").time())
        except:
            t_start, t_end = None, None

    if st.button("ยืนยันการส่งคำขอจอง"):
        if not name or not dept or not t_start or not t_end:
            st.warning("⚠️ กรุณากรอกข้อมูลและรูปแบบเวลาให้ถูกต้อง (เช่น 0800)")
        elif t_start >= t_end:
            st.error("❌ เวลาเริ่มต้องก่อนเวลาสิ้นสุด")
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
                st.error(f"❌ ไม่ว่าง: {res} ถูกจองไปแล้วในช่วงเวลานี้")
            else:
                data = {
                    "resource": res, "requester": name, "phone": phone, "dept": dept, 
                    "start_time": t_start.isoformat(), "end_time": t_end.isoformat(), 
                    "purpose": reason, "destination": destination, "status": "Pending"
                }
                response = supabase.table("bookings").insert(data).execute()
                if response.data:
                    send_line_notification(response.data[0]['id'], res, name, dept, t_start, t_end, reason, destination, "Pending")
                    st.success("✅ ส่งคำขอเรียบร้อยแล้ว!")

# --- หน้า Admin (อนุมัติ) ---
elif choice == "🔑 Admin (อนุมัติ)":
    st.subheader("🔑 ระบบจัดการการจอง (Admin Dashboard)")
    admin_pw = st.text_input("🔒 ใส่รหัสผ่าน Admin", type="password")
    if admin_pw == "s1234":
        res_pending = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute()
        pending_items = res_pending.data

        if not pending_items:
            st.info("✅ ไม่มีรายการรออนุมัติ")
        else:
            for item in pending_items:
                with st.container(border=True):
                    col1, col2, col3 = st.columns([3, 2, 2])
                    with col1:
                        edit_res = st.text_input("รายการ", str(item['resource']), key=f"res_{item['id']}")
                        edit_req = st.text_input("ผู้ขอ", str(item['requester']), key=f"req_{item['id']}")
                        edit_dept = st.text_input("แผนก", str(item['dept']), key=f"dept_{item['id']}")
                    with col2:
                        # แยก วัน-เวลา ออกมาให้ Admin แก้แบบ 4 หลัก
                        c_s = datetime.fromisoformat(item['start_time'])
                        c_e = datetime.fromisoformat(item['end_time'])
                        
                        a_d_s = st.date_input("วันที่เริ่ม", c_s.date(), key=f"ds_{item['id']}")
                        a_t_s = st.text_input("เวลาเริ่ม (4 หลัก)", value=c_s.strftime("%H%M"), key=f"ts_{item['id']}", max_chars=4)
                        
                        a_d_e = st.date_input("วันที่สิ้นสุด", c_e.date(), key=f"de_{item['id']}")
                        a_t_e = st.text_input("เวลาสิ้นสุด (4 หลัก)", value=c_e.strftime("%H%M"), key=f"te_{item['id']}", max_chars=4)
                        
                        edit_dest = st.text_input("ปลายทาง", str(item.get('destination', '-')), key=f"dest_{item['id']}")
                        edit_purp = st.text_area("เหตุผล", str(item['purpose']), key=f"purp_{item['id']}")
                    with col3:
                        st.write("")
                        # แปลงค่ากลับเพื่อบันทึก
                        try:
                            f_s = format_time_string(a_t_s)
                            f_e = format_time_string(a_t_e)
                            final_s = datetime.combine(a_d_s, datetime.strptime(f_s, "%H:%M").time()).isoformat()
                            final_e = datetime.combine(a_d_e, datetime.strptime(f_e, "%H:%M").time()).isoformat()
                        except:
                            final_s, final_e = item['start_time'], item['end_time']

                        btn_app, btn_rej = st.columns(2)
                        if btn_app.button("✅", key=f"app_{item['id']}", use_container_width=True):
                            up_data = {"resource": edit_res, "requester": edit_req, "dept": edit_dept, "destination": edit_dest, "start_time": final_s, "end_time": final_e, "purpose": edit_purp, "status": "Approved"}
                            supabase.table("bookings").update(up_data).eq("id", item['id']).execute()
                            send_line_notification(item['id'], edit_res, edit_req, edit_dept, final_s, final_e, edit_purp, edit_dest, "Approved")
                            st.rerun()
                        if btn_rej.button("❌", key=f"rej_{item['id']}", use_container_width=True):
                            supabase.table("bookings").update({"status": "Rejected"}).eq("id", item['id']).execute()
                            st.rerun()

# --- หน้าตารางงาน (Real-time) ---
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางงานปัจจุบันและล่วงหน้า")
    now_iso = datetime.now().isoformat()
    res_db = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).order("start_time").execute()
    df = pd.DataFrame(res_db.data)
    
    if df.empty:
        st.info("ขณะนี้ไม่มีรายการจอง")
    else:
        df_show = df.copy().reset_index(drop=True)
        df_show.index += 1
        df_show['start_fmt'] = pd.to_datetime(df_show['start_time']).dt.strftime('%d/%m/%Y %H:%M')
        df_show['end_fmt'] = pd.to_datetime(df_show['end_time']).dt.strftime('%d/%m/%Y %H:%M')
        
        df_disp = df_show[['resource', 'start_fmt', 'end_fmt', 'requester', 'purpose', 'destination']]
        df_disp.columns = ['รายการ', 'เวลาเริ่ม', 'เวลาสิ้นสุด', 'ผู้จอง', 'วัตถุประสงค์', 'ปลายทาง']
        st.dataframe(df_disp, use_container_width=True)

        st.markdown("---")
        st.subheader("🛠️ แก้ไขข้อมูล (Admin Only)")
        with st.expander("คลิกเพื่อแก้ไขรายการ"):
            edit_id = st.selectbox("เลือก ID ที่ต้องการแก้ไข", df['id'].tolist(), key="sel_id_table")
            row = df[df['id'] == edit_id].iloc[0]
            
            with st.form("edit_form_table"):
                col_e1, col_e2 = st.columns(2)
                n_res = col_e1.text_input("รายการ", str(row['resource']))
                n_req = col_e1.text_input("ผู้จอง", str(row['requester']))
                n_dept = col_e1.text_input("แผนก", str(row.get('dept', '-')))

                # แยก วัน-เวลา แบบ 4 หลัก
                dt_s = pd.to_datetime(row['start_time'])
                dt_e = pd.to_datetime(row['end_time'])
                n_d_s = col_e2.date_input("วันที่เริ่ม", dt_s.date())
                n_t_s = col_e2.text_input("เวลาเริ่ม (4 หลัก)", value=dt_s.strftime("%H%M"), max_chars=4)
                n_d_e = col_e2.date_input("วันที่สิ้นสุด", dt_e.date())
                n_t_e = col_e2.text_input("เวลาสิ้นสุด (4 หลัก)", value=dt_e.strftime("%H%M"), max_chars=4)
                
                n_purp = col_e2.text_area("วัตถุประสงค์", str(row.get('purpose', '-')))
                n_dest = col_e2.text_input("ปลายทาง", str(row.get('destination', '-')))
                
                pw = st.text_input("รหัสผ่านบันทึก", type="password")
                if st.form_submit_button("💾 บันทึก"):
                    if pw == "1234":
                        try:
                            f_s = format_time_string(n_t_s)
                            f_e = format_time_string(n_t_e)
                            final_s = datetime.combine(n_d_s, datetime.strptime(f_s, "%H:%M").time()).isoformat()
                            final_e = datetime.combine(n_d_e, datetime.strptime(f_e, "%H:%M").time()).isoformat()
                            
                            update_payload = {"resource": n_res, "requester": n_req, "dept": n_dept, "start_time": final_s, "end_time": final_e, "purpose": n_purp, "destination": n_dest}
                            supabase.table("bookings").update(update_payload).eq("id", edit_id).execute()
                            st.success("บันทึกเรียบร้อย!")
                            st.rerun()
                        except: st.error("เวลาไม่ถูกต้อง")
                    else: st.error("รหัสผ่านไม่ถูกต้อง")

# --- หน้าสรุปรายงานประจำเดือน ---
elif choice == "📊 รายงานประจำเดือน":
    st.subheader("📊 รายงานการใช้รถยนต์ประจำเดือน (ข้อมูล 45 วัน)")
    admin_pw = st.text_input("🔒 รหัส Admin สำหรับรายงาน", type="password")
    if admin_pw == "s1234":
        car_list = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"]
        res_rep = supabase.table("bookings").select("*").in_("resource", car_list).eq("status", "Approved").execute()
        
        if res_rep.data:
            df_rep = pd.DataFrame(res_rep.data)
            df_rep['start_time'] = pd.to_datetime(df_rep['start_time'])
            df_rep['Month-Year'] = df_rep['start_time'].dt.strftime('%m/%Y')
            
            sel_m = st.selectbox("เลือกเดือนที่ต้องการ", df_rep['Month-Year'].unique())
            final_df = df_rep[df_rep['Month-Year'] == sel_m].copy()
            final_df = final_df[['resource', 'requester', 'dept', 'start_time', 'end_time', 'destination', 'purpose']]
            final_df.columns = ['รถยนต์', 'ผู้จอง', 'แผนก', 'เวลาเริ่ม', 'เวลาสิ้นสุด', 'สถานที่', 'วัตถุประสงค์']
            
            st.dataframe(final_df, use_container_width=True)
            
            # ปุ่ม Download Excel
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, sheet_name='Report', index=False)
            st.download_button("📥 Download รายงาน Excel", buffer.getvalue(), f"Car_Report_{sel_m}.xlsx", "application/vnd.ms-excel")
    elif admin_pw != "": st.error("รหัสผ่านไม่ถูกต้อง")
