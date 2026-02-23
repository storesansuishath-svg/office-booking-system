import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests
import json
import io

# ==========================================
# 1. การเชื่อมต่อ DATABASE & CONFIG
# ==========================================
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co" 
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ตั้งค่าหน้าจอแบบกว้าง
st.set_page_config(page_title="ระบบจองรถและห้องประชุม - Sansuisha", layout="wide")

# CSS สำหรับไฟกระพริบสีแดงและปรับแต่งสี Input
st.markdown("""
    <style>
    @keyframes blinker { 50% { opacity: 0; } }
    .blink { animation: blinker 1s linear infinite; color: #FF0000; font-weight: bold; font-size: 18px; }
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        background-color: #E3F2FD !important; color: #0D47A1 !important; border: 1px solid #BBDEFB !important;
    }
    .main-title { font-size: 35px; font-weight: bold; color: #1E88E5; text-align: center; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. ฟังก์ชันหลัก (CORE FUNCTIONS)
# ==========================================

# ฟังก์ชันจัดการรูปแบบเวลา (เช่น 0800 -> 08:00)
def format_time_string(t_raw):
    clean = str(t_raw).replace(":", "").strip()
    if len(clean) == 4:
        return f"{clean[:2]}:{clean[2:]}"
    return clean

# [FIX] ระบบเช็กคิวชนกัน (Conflict Checker) แม่นยำ 100%
def check_booking_conflict(resource, start_time_iso, end_time_iso):
    # ดึงเฉพาะรายการที่อนุมัติแล้วมาตรวจสอบ
    res = supabase.table("bookings").select("*").eq("resource", resource).eq("status", "Approved").execute()
    # แปลงเป็น Naive Datetime เพื่อใช้เปรียบเทียบ (กัน Error image.png)
    new_s = datetime.fromisoformat(start_time_iso).replace(tzinfo=None)
    new_e = datetime.fromisoformat(end_time_iso).replace(tzinfo=None)
    
    for item in res.data:
        ex_s = pd.to_datetime(item['start_time']).replace(tzinfo=None)
        ex_e = pd.to_datetime(item['end_time']).replace(tzinfo=None)
        
        # Logic: (เริ่มใหม่ < จบเก่า) AND (จบใหม่ > เริ่มเก่า)
        if new_s < ex_e and new_e > ex_s:
            return True, item['requester']
    return False, None

# ฟังก์ชันส่งแจ้งเตือน LINE (มีระบบดัก Error โควตาเต็ม)
def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination, status_text="Pending"):
    render_url = "https://line-booking-system.onrender.com/notify"
    GROUP_ID = "Cad74a32468ca40051bd7071a6064660d" 
    
    try:
        # เตรียม Format วันที่ให้ LINE อ่านง่าย
        s_dt = pd.to_datetime(t_start)
        s_str = s_dt.strftime("%d/%m/%Y %H:%M")
        e_str = t_end if isinstance(t_end, str) else t_end.strftime("%H:%M")
        
        payload = {
            "id": booking_id, "target_id": GROUP_ID, "resource": resource, 
            "name": name, "dept": dept, "date": s_str, "end_date": e_str, 
            "purpose": purpose, "destination": destination, "status": status_text
        }
        r = requests.post(render_url, json=payload, timeout=10)
        
        if r.status_code == 200:
            st.toast(f"🔔 LINE: ส่งข้อมูล {status_text} สำเร็จ", icon="✅")
        elif r.status_code == 429:
            st.error("⚠️ แจ้งเตือนไม่เด้ง: โควตา LINE รายเดือนของพี่เต็มแล้วครับ (Error 429)")
    except Exception as e:
        st.error(f"📡 เชื่อมต่อเซิร์ฟเวอร์แจ้งเตือนไม่ได้: {e}")

# ลบข้อมูลเก่าเกิน 45 วัน
def auto_delete_old_bookings():
    threshold = (datetime.now() - timedelta(days=45)).isoformat()
    try: supabase.table("bookings").delete().lt("end_time", threshold).execute()
    except: pass

# ==========================================
# 3. SIDEBAR & NAVIGATION
# ==========================================
auto_delete_old_bookings()
# ดึงยอด Pending มาทำไฟกระพริบ
pending_items = supabase.table("bookings").select("id").eq("status", "Pending").execute().data
pending_count = len(pending_items)

st.sidebar.image("https://lh3.googleusercontent.com/d/1zCjSjSbCO-mbsaGoDI6g0G-bfmyVfqFV", use_container_width=True)

# ไฟกระพริบเตือนถ้ามีงานค้าง
if pending_count > 0:
    st.sidebar.markdown(f'<p class="blink">📢 มีรายการรออนุมัติ: {pending_count}</p>', unsafe_allow_html=True)

st.sidebar.markdown("---")
menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin (อนุมัติ)", "📊 รายงานประจำเดือน"]
choice = st.sidebar.selectbox("เมนูจัดการระบบ", menu)

# ==========================================
# 4. หน้าจองใหม่ (BOOKING)
# ==========================================
if choice == "📝 จองใหม่":
    st.markdown('<div class="main-title">ระบบจองรถยนต์และห้องประชุม Online</div>', unsafe_allow_html=True)
    
    # Quick Stats Dashboard
    t_start_day = datetime.now().replace(hour=0, minute=0, second=0).isoformat()
    today_approved = supabase.table("bookings").select("id").eq("status", "Approved").gte("start_time", t_start_day).execute().data
    
    d1, d2, d3 = st.columns(3)
    d1.metric("รายการจองวันนี้", f"{len(today_approved)} รายการ")
    d2.metric("รอพี่อนุมัติ", f"{pending_count} รายการ")
    d3.metric("สถานะฐานข้อมูล", "Connected")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        cat = st.radio("ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"], horizontal=True)
        res_list = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG"] if cat == "รถยนต์" else ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]
        res = st.selectbox("เลือกรายการ", res_list)
        dest = st.text_input("สถานที่ปลายทาง") if cat == "รถยนต์" else "Office"
        name = st.text_input("ชื่อผู้จอง")
        phone = st.text_input("เบอร์โทรศัพท์")
        dept = st.text_input("แผนก")

    with col2:
        d_start = st.date_input("วันที่เริ่ม", datetime.now().date())
        t_start_raw = st.text_input("เวลาเริ่ม (4 หลัก เช่น 0800)", "0800", max_chars=4)
        st.markdown("---")
        d_end = st.date_input("วันที่สิ้นสุด", d_start)
        t_end_raw = st.text_input("เวลาสิ้นสุด (4 หลัก เช่น 1700)", "1700", max_chars=4)
        reason = st.text_area("วัตถุประสงค์การใช้งาน")
        
        try:
            ts_f, te_f = format_time_string(t_start_raw), format_time_string(t_end_raw)
            ts = datetime.combine(d_start, datetime.strptime(ts_f, "%H:%M").time())
            te = datetime.combine(d_end, datetime.strptime(te_f, "%H:%M").time())
        except: ts, te = None, None

    if st.button("ยืนยันการส่งคำขอจอง", use_container_width=True):
        if not name or not dept or ts is None:
            st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")
        elif ts >= te:
            st.error("❌ เวลาเริ่มต้องมาก่อนเวลาสิ้นสุด")
        else:
            # ระบบเช็กคิวชนกัน (Conflict Checker)
            is_conf, user_conf = check_booking_conflict(res, ts.isoformat(), te.isoformat())
            if is_conf:
                st.error(f"❌ คิวชนกัน! {res} ถูกจองแล้วโดยคุณ {user_conf} ในเวลานี้")
            else:
                data = {"resource": res, "requester": name, "phone": phone, "dept": dept, "start_time": ts.isoformat(), "end_time": te.isoformat(), "purpose": reason, "destination": dest, "status": "Pending"}
                resp = supabase.table("bookings").insert(data).execute()
                if resp.data:
                    send_line_notification(resp.data[0]['id'], res, name, dept, ts, te, reason, dest)
                    st.success("✅ ส่งคำขอเรียบร้อย! โปรดรอ Admin อนุมัติ")
                    st.balloons()

# ==========================================
# 5. หน้าตารางงาน (TABLE & COMPLETE EDIT)
# ==========================================
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางการใช้งานปัจจุบันและล่วงหน้า")
    
    # Advanced Filter
    f_c1, f_c2 = st.columns([2, 1])
    search_q = f_c1.text_input("🔍 ค้นหาชื่อผู้จอง / สถานที่")
    view_cat = f_c2.selectbox("กรองตามประเภท", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
    
    now_iso = datetime.now().isoformat()
    db_res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).order("start_time").execute()
    df = pd.DataFrame(db_res.data)
    
    if df.empty:
        st.info("ขณะนี้ไม่มีรายการจอง")
    else:
        # กรองข้อมูล
        if view_cat == "รถยนต์": df = df[df['resource'].str.contains("Civic|Camry|MG", na=False)]
        elif view_cat == "ห้องประชุม": df = df[df['resource'].str.contains("ห้อง", na=False)]
        if search_q: df = df[df['requester'].str.contains(search_q, case=False) | df['destination'].str.contains(search_q, case=False)]
        
        if not df.empty:
            df_show = df.copy().reset_index(drop=True)
            df_show.index += 1
            df_show.insert(0, 'ลำดับ/No.', df_show.index)
            df_show['เริ่ม'] = pd.to_datetime(df_show['start_time']).dt.strftime('%d/%m/%Y %H:%M')
            st.dataframe(df_show[['ลำดับ/No.', 'resource', 'เริ่ม', 'requester', 'destination', 'purpose']], use_container_width=True)

            # ✅ ส่วนแก้ไขข้อมูลแบบ 100% (เพิ่มช่องที่พี่ต้องการครบถ้วน)
            st.markdown("---")
            with st.expander("🛠️ จัดการข้อมูล (แก้ไข/ลบ โดย Admin)"):
                sel_no = st.selectbox("เลือก No. ที่ต้องการจัดการ", df_show['ลำดับ/No.'].tolist(), key="s_no")
                row = df_show[df_show['ลำดับ/No.'] == sel_no].iloc[0]
                
                with st.form("edit_full_form"):
                    e_col1, e_col2 = st.columns(2)
                    n_req = e_col1.text_input("ชื่อผู้จอง", row['requester'])
                    n_dest = e_col1.text_input("ปลายทาง", row.get('destination', '-'))
                    
                    # แก้ไขเวลาสิ้นสุด
                    dt_e = pd.to_datetime(row['end_time'])
                    n_d_e = e_col2.date_input("วันที่สิ้นสุด", dt_e.date())
                    n_t_e = e_col2.text_input("เวลาสิ้นสุด (4 หลัก)", dt_e.strftime("%H%M"))
                    
                    # แก้ไขวัตถุประสงค์
                    n_purp = st.text_area("วัตถุประสงค์", row.get('purpose', '-'))
                    
                    pw = st.text_input("รหัสผ่าน Admin", type="password")
                    b1, b2 = st.columns(2)
                    if b1.form_submit_button("💾 บันทึกการเปลี่ยนแปลง", use_container_width=True):
                        if pw == "s1234":
                            fe = format_time_string(n_t_e)
                            f_end = datetime.combine(n_d_e, datetime.strptime(fe, "%H:%M").time()).isoformat()
                            supabase.table("bookings").update({"requester": n_req, "destination": n_dest, "purpose": n_purp, "end_time": f_end}).eq("id", row['id']).execute()
                            st.success("อัปเดตเรียบร้อย!"); st.rerun()
                        else: st.error("รหัสผ่านผิด")
                    if b2.form_submit_button("🗑️ ลบรายการนี้", use_container_width=True):
                        if pw == "s1234":
                            supabase.table("bookings").delete().eq("id", row['id']).execute(); st.rerun()
                        else: st.error("รหัสผ่านผิด")

# ==========================================
# 6. หน้า ADMIN (APPROVAL)
# ==========================================
elif choice == "🔑 Admin (อนุมัติ)":
    st.subheader("🔑 ระบบจัดการคำขอจอง")
    if st.text_input("กรอกรหัสผ่านเพื่ออนุมัติ", type="password") == "s1234":
        items = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute().data
        if not items:
            st.info("ไม่มีรายการรออนุมัติ")
        else:
            for i in items:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    curr_start = pd.to_datetime(i['start_time'])
                    with c1:
                        st.write(f"🚗 **{i['resource']}** | 👤 {i['requester']} | 🏢 {i['dept']}")
                        st.write(f"📍 {i['destination']} | 🎯 {i['purpose']}")
                        a_d = st.date_input("ยืนยันวันที่", curr_start.date(), key=f"d_{i['id']}")
                        a_t = st.text_input("ยืนยันเวลาเริ่ม (4 หลัก)", curr_start.strftime("%H%M"), key=f"t_{i['id']}")
                    
                    if c2.button("อนุมัติ ✅", key=f"ap_{i['id']}", use_container_width=True):
                        try:
                            f_time = format_time_string(a_t)
                            final_start = datetime.combine(a_d, datetime.strptime(f_time, "%H:%M").time()).isoformat()
                            supabase.table("bookings").update({"status": "Approved", "start_time": final_start}).eq("id", i['id']).execute()
                            # ✅ เรียกส่งแจ้งเตือน LINE ทันที
                            send_line_notification(i['id'], i['resource'], i['requester'], i['dept'], final_start, i['end_time'], i['purpose'], i['destination'], "Approved")
                            st.rerun()
                        except: st.error("รูปแบบเวลาผิด")
                    if c2.button("ลบ 🗑️", key=f"dl_{i['id']}", use_container_width=True):
                        supabase.table("bookings").delete().eq("id", i['id']).execute(); st.rerun()

# ==========================================
# 7. หน้ารายงาน (REPORT & EXCEL FIX)
# ==========================================
elif choice == "📊 รายงานประจำเดือน":
    st.subheader("📊 รายงานสรุปการใช้ทรัพยากร")
    if st.text_input("รหัสผ่านรายงาน", type="password") == "s1234":
        data = supabase.table("bookings").select("*").eq("status", "Approved").execute().data
        if data:
            df_rep = pd.DataFrame(data)
            df_rep['start_time'] = pd.to_datetime(df_rep['start_time'])
            df_rep['Month-Year'] = df_rep['start_time'].dt.strftime('%m/%Y')
            
            c1, c2 = st.columns(2)
            sel_m = c1.selectbox("เลือกเดือน", sorted(df_rep['Month-Year'].unique(), reverse=True))
            v_type = c2.selectbox("ประเภทรายงาน", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
            
            f_df = df_rep[df_rep['Month-Year'] == sel_m].copy()
            if v_type == "รถยนต์": f_df = f_df[f_df['resource'].str.contains("Civic|Camry|MG", na=False)]
            elif v_type == "ห้องประชุม": f_df = f_df[f_df['resource'].str.contains("ห้อง", na=False)]
            
            # [FIX] แปลงวันที่เป็นข้อความก่อนโชว์และโหลด กัน Error image_ad3433.png
            f_df['เวลาเริ่ม'] = f_df['start_time'].dt.strftime('%d/%m/%Y %H:%M')
            out_df = f_df[['resource', 'requester', 'dept', 'เวลาเริ่ม', 'destination', 'purpose']]
            st.dataframe(out_df, use_container_width=True)
            
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as w:
                out_df.to_excel(w, index=False)
            st.download_button("📥 ดาวน์โหลดรายงาน (Excel)", buf.getvalue(), f"Report_{v_type}_{sel_m}.xlsx")
