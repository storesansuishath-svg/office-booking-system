import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests
import json
import io

# ==========================================
# 1. การเชื่อมต่อ DATABASE & CONFIGURATION
# ==========================================
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co" 
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ตั้งค่าหน้าจอ (Wide Mode)
st.set_page_config(page_title="ระบบจองรถยนต์และห้องประชุม - Sansuisha", layout="wide")

# CSS สำหรับตกแต่ง UI และไฟกระพริบสีแดง (Blinking Alert)
st.markdown("""
    <style>
    @keyframes blinker { 50% { opacity: 0; } }
    .blink { animation: blinker 1s linear infinite; color: #FF0000; font-weight: bold; font-size: 18px; }
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        background-color: #E3F2FD !important; color: #0D47A1 !important; border: 1px solid #BBDEFB !important;
    }
    .main-header { font-size: 32px; font-weight: bold; color: #1E88E5; margin-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. ฟังก์ชันช่วยการทำงาน (HELPER FUNCTIONS)
# ==========================================

# ฟังก์ชันจัดการรูปแบบเวลา (เช่น 0800 -> 08:00)
def format_time_string(t_raw):
    clean = str(t_raw).replace(":", "").strip()
    if len(clean) == 4:
        return f"{clean[:2]}:{clean[2:]}"
    return clean

# ระบบเช็กคิวชนกัน (Conflict Checker)
def check_booking_conflict(resource, start_time_iso, end_time_iso):
    # ดึงเฉพาะรายการที่ได้รับการอนุมัติแล้วมาตรวจสอบ
    res = supabase.table("bookings").select("*").eq("resource", resource).eq("status", "Approved").execute()
    new_s = datetime.fromisoformat(start_time_iso).replace(tzinfo=None)
    new_e = datetime.fromisoformat(end_time_iso).replace(tzinfo=None)
    
    for item in res.data:
        ex_s = pd.to_datetime(item['start_time']).replace(tzinfo=None)
        ex_e = pd.to_datetime(item['end_time']).replace(tzinfo=None)
        
        # สูตรการทับซ้อนของเวลา
        if new_s < ex_e and new_e > ex_s:
            return True, item['requester']
    return False, None

# ระบบแจ้งเตือนผ่าน LINE (ผ่าน Render Proxy)
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
        st.toast("🔔 ส่งข้อมูลแจ้งเตือน LINE เรียบร้อย", icon="✅")
    except:
        pass

# ระบบลบข้อมูลเก่าอัตโนมัติ (เกิน 45 วัน)
def auto_delete_old_bookings():
    threshold_delete = (datetime.now() - timedelta(days=45)).isoformat()
    try:
        supabase.table("bookings").delete().lt("end_time", threshold_delete).execute()
    except:
        pass

# ==========================================
# 3. ส่วนประมวลผล SIDEBAR & ALERT
# ==========================================
auto_delete_old_bookings()
# ดึงจำนวนรายการที่รออนุมัติ
pending_check = supabase.table("bookings").select("id").eq("status", "Pending").execute().data
pending_count = len(pending_check)

# โลโก้บริษัท (พี่สามารถเปลี่ยน URL ได้เลยครับ)
LOGO_URL = "https://lh3.googleusercontent.com/d/1zCjSjSbCO-mbsaGoDI6g0G-bfmyVfqFV"
st.sidebar.image(LOGO_URL, use_container_width=True)

# ไฟกระพริบเตือนถ้ามีรายการค้าง
if pending_count > 0:
    st.sidebar.markdown(f'<p class="blink">⚠️ ค้างอนุมัติ: {pending_count} รายการ</p>', unsafe_allow_html=True)

st.sidebar.markdown("---")
menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin (อนุมัติ)", "📊 รายงานประจำเดือน"]
choice = st.sidebar.selectbox("เลือกเมนูหลัก", menu)

# ==========================================
# 4. หน้าจองใหม่ (BOOKING PAGE)
# ==========================================
if choice == "📝 จองใหม่":
    st.markdown('<div class="main-header">📝 บันทึกคำขอจองรถยนต์และห้องประชุม</div>', unsafe_allow_html=True)
    
    # Dashboard สรุปภาพรวมสั้นๆ
    t_today = datetime.now().date().isoformat()
    today_approved = supabase.table("bookings").select("id").eq("status", "Approved").gte("start_time", t_today).execute().data
    
    dash1, dash2, dash3 = st.columns(3)
    dash1.metric("คิวงานวันนี้", f"{len(today_approved)} รายการ")
    dash2.metric("รออนุมัติ", f"{pending_count} รายการ", delta=pending_count, delta_color="inverse")
    dash3.metric("สถานะระบบ", "Online")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        cat = st.radio("ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"], horizontal=True)
        res_list = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG"] if cat == "รถยนต์" else ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]
        res = st.selectbox("เลือกรายการที่จะจอง", res_list)
        dest = st.text_input("สถานที่ปลายทาง") if cat == "รถยนต์" else "Office"
        
        if cat == "รถยนต์" and dest:
            st.link_button(f"🔍 ดูแผนที่ '{dest}'", f"https://www.google.com/maps/search/{dest}")
            
        name = st.text_input("ชื่อผู้จอง")
        phone = st.text_input("เบอร์โทรศัพท์ติดต่อ")
        dept = st.text_input("แผนก / ฝ่าย")

    with col2:
        d_start = st.date_input("วันที่เริ่มใช้งาน", datetime.now().date())
        t_start_raw = st.text_input("เวลาเริ่ม (เช่น 0800)", value="0800", max_chars=4)
        
        st.markdown("---")
        
        d_end = st.date_input("วันที่สิ้นสุดใช้งาน", value=d_start, min_value=d_start)
        t_end_raw = st.text_input("เวลาสิ้นสุด (เช่น 1700)", value="1700", max_chars=4)
        
        reason = st.text_area("วัตถุประสงค์ในการจอง")
        
        # แปลงเวลา
        try:
            ts_f, te_f = format_time_string(t_start_raw), format_time_string(t_end_raw)
            t_start = datetime.combine(d_start, datetime.strptime(ts_f, "%H:%M").time())
            t_end = datetime.combine(d_end, datetime.strptime(te_f, "%H:%M").time())
        except:
            t_start, t_end = None, None

    if st.button("ยืนยันการส่งคำขอจอง", use_container_width=True):
        if not name or not dept or t_start is None:
            st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")
        elif t_start >= t_end:
            st.error("❌ เวลาเริ่มต้องมาก่อนเวลาสิ้นสุด")
        else:
            # เช็กคิวชนกันก่อนบันทึก
            is_conflict, user_conflict = check_booking_conflict(res, t_start.isoformat(), t_end.isoformat())
            if is_conflict:
                st.error(f"❌ คิวชนกัน! {res} ถูกจองแล้วโดยคุณ {user_conflict} ในช่วงเวลานี้")
            else:
                data = {
                    "resource": res, "requester": name, "phone": phone, "dept": dept, 
                    "start_time": t_start.isoformat(), "end_time": t_end.isoformat(), 
                    "purpose": reason, "destination": dest, "status": "Pending"
                }
                resp = supabase.table("bookings").insert(data).execute()
                if resp.data:
                    send_line_notification(resp.data[0]['id'], res, name, dept, t_start, t_end, reason, dest)
                    st.success("✅ บันทึกข้อมูลและส่งคำขอรออนุมัติเรียบร้อย!")
                    st.balloons()

# ==========================================
# 5. หน้าตารางงาน (REAL-TIME TABLE & EDIT)
# ==========================================
elif choice == "📅 ตารางงาน (Real-time)":
    st.markdown('<div class="main-header">📅 ตารางการใช้งานปัจจุบันและล่วงหน้า</div>', unsafe_allow_html=True)
    
    # ระบบค้นหาและฟิลเตอร์ขั้นสูง (Advanced Filter)
    f_col1, f_col2 = st.columns([2, 1])
    search_query = f_col1.text_input("🔍 พิมพ์ชื่อ หรือ สถานที่ เพื่อค้นหา...")
    view_cat = f_col2.selectbox("กรองตามประเภท", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
    
    now_iso = datetime.now().isoformat()
    res_db = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).order("start_time").execute()
    df = pd.DataFrame(res_db.data)
    
    if df.empty:
        st.info("ไม่มีรายการจองที่กำลังใช้งานหรือรอคิวในขณะนี้")
    else:
        # กรองตามประเภท
        if view_cat == "รถยนต์":
            df = df[df['resource'].isin(["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG"])]
        elif view_cat == "ห้องประชุม":
            df = df[~df['resource'].isin(["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG"])]
        
        # กรองตาม Keyword การค้นหา
        if search_query:
            df = df[df['requester'].str.contains(search_query, case=False, na=False) | 
                    df['destination'].str.contains(search_query, case=False, na=False)]

        if not df.empty:
            # แสดงตารางผลลัพธ์
            df_show = df.copy().reset_index(drop=True)
            df_show.index += 1
            df_show.insert(0, 'ลำดับ/No.', df_show.index)
            df_show['start_fmt'] = pd.to_datetime(df_show['start_time'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M')
            df_show['end_fmt'] = pd.to_datetime(df_show['end_time'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M')
            
            df_disp = df_show[['ลำดับ/No.', 'resource', 'start_fmt', 'end_fmt', 'requester', 'purpose', 'destination']]
            df_disp.columns = ['No.', 'รายการ', 'เริ่ม', 'สิ้นสุด', 'ผู้จอง', 'วัตถุประสงค์', 'ปลายทาง']
            st.dataframe(df_disp, use_container_width=True)

            # ✅ ส่วนแก้ไข/ลบ ข้อมูล (Complete Version)
            st.markdown("---")
            st.subheader("🛠️ เมนูจัดการข้อมูล (สำหรับ Admin)")
            with st.expander("คลิกที่นี่เพื่อแก้ไขหรือลบรายการ"):
                sel_no = st.selectbox("เลือก No. ที่ต้องการจัดการ", df_show['ลำดับ/No.'].tolist(), key="sel_edit")
                row = df_show[df_show['ลำดับ/No.'] == sel_no].iloc[0]
                edit_id = row['id']
                
                with st.form("edit_full_form"):
                    e_col1, e_col2 = st.columns(2)
                    
                    # ข้อมูลพื้นฐาน
                    res_opts = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG", "ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]
                    n_res = e_col1.selectbox("รายการ / Resource", res_opts, index=res_opts.index(row['resource']) if row['resource'] in res_opts else 0)
                    n_req = e_col1.text_input("ผู้จอง / Name", str(row['requester']))
                    n_dept = e_col1.text_input("แผนก / Dept", str(row.get('dept', '-')))
                    n_dest = e_col1.text_input("ปลายทาง / Destination", str(row.get('destination', '-')))
                    
                    # เวลาการจอง (ครบถ้วนตามสั่ง)
                    dt_s = pd.to_datetime(row['start_time'], errors='coerce')
                    dt_e = pd.to_datetime(row['end_time'], errors='coerce')
                    
                    n_d_s = e_col2.date_input("วันที่เริ่ม", dt_s.date() if pd.notnull(dt_s) else datetime.now().date())
                    n_t_s = e_col2.text_input("เวลาเริ่ม (4 หลัก)", dt_s.strftime("%H%M") if pd.notnull(dt_s) else "0800")
                    n_d_e = e_col2.date_input("วันที่สิ้นสุด", dt_e.date() if pd.notnull(dt_e) else datetime.now().date())
                    n_t_e = e_col2.text_input("เวลาสิ้นสุด (4 หลัก)", dt_e.strftime("%H%M") if pd.notnull(dt_e) else "1700")
                    
                    # วัตถุประสงค์ (เพิ่มตามสั่ง)
                    n_purp = st.text_area("วัตถุประสงค์ / Purpose", str(row.get('purpose', '-')))
                    
                    pw = st.text_input("รหัสผ่าน Admin", type="password")
                    b_save, b_del = st.columns(2)
                    
                    if b_save.form_submit_button("💾 บันทึกการแก้ไข", use_container_width=True):
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
                                st.success("อัปเดตข้อมูลเรียบร้อย!"); st.rerun()
                            except: st.error("❌ รูปแบบเวลาไม่ถูกต้อง")
                        else: st.error("❌ รหัสผ่านผิด")
                        
                    if b_del.form_submit_button("🗑️ ลบรายการนี้", use_container_width=True):
                        if pw == "s1234":
                            supabase.table("bookings").delete().eq("id", edit_id).execute()
                            st.warning("ลบรายการแล้ว"); st.rerun()
                        else: st.error("❌ รหัสผ่านผิด")
        else:
            st.warning("ไม่พบข้อมูลที่ตรงกับเงื่อนไขการค้นหา")

# ==========================================
# 6. หน้า ADMIN (อนุมัติรายการ)
# ==========================================
elif choice == "🔑 Admin (อนุมัติ)":
    st.markdown('<div class="main-header">🔑 ระบบจัดการอนุมัติคำขอ</div>', unsafe_allow_html=True)
    admin_pw = st.text_input("กรุณาระบุรหัสผ่าน Admin", type="password")
    
    if admin_pw == "s1234":
        items = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute().data
        if not items:
            st.info("ไม่มีรายการคำขอจองค้างอยู่")
        else:
            for item in items:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        st.markdown(f"**🚗 {item['resource']}** | 👤 {item['requester']} ({item['dept']})")
                        st.write(f"📍 ปลายทาง: {item.get('destination','-')} | 🎯 วัตถุประสงค์: {item.get('purpose','-')}")
                        # ให้ Admin ปรับวันที่/เวลาก่อนก้อนอนุมัติได้
                        curr_dt = pd.to_datetime(item['start_time'])
                        a_d = st.date_input("ยืนยันวันที่", curr_dt.date(), key=f"d_{item['id']}")
                        a_t = st.text_input("ยืนยันเวลาเริ่ม (4 หลัก)", curr_dt.strftime("%H%M"), key=f"t_{item['id']}", max_chars=4)
                    
                    with c2:
                        if st.button("อนุมัติ ✅", key=f"ap_{item['id']}", use_container_width=True):
                            try:
                                ft = format_time_string(a_t)
                                final_t = datetime.combine(a_d, datetime.strptime(ft, "%H:%M").time()).isoformat()
                                # อัปเดตสถานะเป็น Approved
                                supabase.table("bookings").update({"status": "Approved", "start_time": final_t}).eq("id", item['id']).execute()
                                # ส่งแจ้งเตือน LINE
                                send_line_notification(item['id'], item['resource'], item['requester'], item['dept'], final_t, item['end_time'], item['purpose'], item['destination'], "Approved")
                                st.rerun()
                            except: st.error("เวลาผิด")
                        
                        if st.button("ลบ 🗑️", key=f"dl_{item['id']}", use_container_width=True):
                            supabase.table("bookings").delete().eq("id", item['id']).execute()
                            st.rerun()

# ==========================================
# 7. หน้ารายงานประจำเดือน (ครบทั้งรถและห้อง)
# ==========================================
elif choice == "📊 รายงานประจำเดือน":
    st.markdown('<div class="main-header">📊 รายงานสรุปประจำเดือน</div>', unsafe_allow_html=True)
    if st.text_input("รหัสผ่านดูรายงาน", type="password", key="r_pw") == "s1234":
        res_rep = supabase.table("bookings").select("*").eq("status", "Approved").execute()
        if res_rep.data:
            df_rep = pd.DataFrame(res_rep.data)
            df_rep['start_time'] = pd.to_datetime(df_rep['start_time'])
            df_rep['Month-Year'] = df_rep['start_time'].dt.strftime('%m/%Y')
            
            c1, c2 = st.columns(2)
            sel_m = c1.selectbox("📅 เลือกเดือน/ปี", sorted(df_rep['Month-Year'].unique(), reverse=True))
            rep_type = c2.selectbox("🔎 กรองประเภททรัพยากร", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
            
            f_df = df_rep[df_rep['Month-Year'] == sel_m].copy()
            # กรองตามประเภท (ใช้ Keyword กรองตามชื่อที่พี่ใช้)
            if rep_type == "รถยนต์":
                f_df = f_df[f_df['resource'].str.contains("Civic|Camry|MG", na=False)]
            elif rep_type == "ห้องประชุม":
                f_df = f_df[f_df['resource'].str.contains("ห้อง", na=False)]
                
            if not f_df.empty:
                f_df['เวลาเริ่ม'] = f_df['start_time'].dt.strftime('%d/%m/%Y %H:%M')
                disp = f_df[['resource', 'requester', 'dept', 'เวลาเริ่ม', 'destination', 'purpose']]
                disp.columns = ['รายการ', 'ผู้จอง', 'แผนก', 'เวลาเริ่มใช้งาน', 'สถานที่', 'วัตถุประสงค์']
                st.dataframe(disp, use_container_width=True)
                
                # ปุ่มโหลด Excel
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='xlsxwriter') as w:
                    disp.to_excel(w, index=False)
                st.download_button(f"📥 Download Report ({rep_type})", buf.getvalue(), f"Sansuisha_Report_{sel_m}.xlsx")
            else:
                st.warning("ไม่มีข้อมูลในหมวดหมู่นี้")
        else:
            st.info("ไม่มีข้อมูลที่ได้รับการอนุมัติ")
