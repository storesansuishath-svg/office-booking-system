import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests
import json
import io
import time

# ==========================================
# 1. การเชื่อมต่อ DATABASE & CONFIG
# ==========================================
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co" 
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

CURRENT_BOT_ID = "@250azmkm"  
LINE_ADD_FRIEND_URL = f"https://line.me/R/ti/p/{CURRENT_BOT_ID}"

st.set_page_config(page_title="ระบบจองรถและห้องประชุม - Sansuisha", layout="wide")

st.markdown("""
    <style>
    @keyframes blinker { 50% { opacity: 0; } }
    .blink { animation: blinker 1s linear infinite; color: #FF0000; font-weight: bold; font-size: 18px; }
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        background-color: #E3F2FD !important; color: #0D47A1 !important; border: 1px solid #BBDEFB !important;
    }
    .main-title { font-size: 35px; font-weight: bold; color: #1E88E5; text-align: center; margin-bottom: 20px;}
    
    /* ปุ่ม link_button ใน sidebar */
    [data-testid="stLinkButton"] a {
        background-color: #8BC34A !important;
        color: white !important;
        border-radius: 8px !important;
        font-weight: bold !important;
        border: none !important;
        text-align: center !important;
    }
    /* hover */
    [data-testid="stLinkButton"] a:hover { background-color: #4CAF50 !important; }
    /* click */
    [data-testid="stLinkButton"] a:active { background-color: #2E7D32 !important; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. ฟังก์ชันหลัก (CORE FUNCTIONS)
# ==========================================

def format_time_string(t_raw):
    clean = str(t_raw).replace(":", "").strip()
    if len(clean) == 4:
        return f"{clean[:2]}:{clean[2:]}"
    return clean

def check_booking_conflict(resource, start_time_iso, end_time_iso):
    res = supabase.table("bookings") \
        .select("*") \
        .eq("resource", resource) \
        .in_("status", ["Approved", "Pending"]) \
        .execute()
    
    new_s = datetime.fromisoformat(start_time_iso).replace(tzinfo=None)
    new_e = datetime.fromisoformat(end_time_iso).replace(tzinfo=None)
    
    for item in res.data:
        ex_s = pd.to_datetime(item['start_time']).replace(tzinfo=None)
        ex_e = pd.to_datetime(item['end_time']).replace(tzinfo=None)
        if new_s < ex_e and new_e > ex_s:
            return True, item['requester'], item['status']
            
    return False, None, None
    
def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination, status_text="Pending"):
    render_url = "https://line-booking-system.onrender.com/notify"
    GROUP_ID = "Cad74a32468ca40051bd7071a6064660d" 
    try:
        s_dt = pd.to_datetime(t_start)
        s_str = s_dt.strftime("%d/%m/%Y %H:%M")
        e_str = t_end if isinstance(t_end, str) else pd.to_datetime(t_end).strftime("%H:%M")
        payload = {
            "id": booking_id, "target_id": GROUP_ID, "resource": resource, 
            "name": name, "dept": dept, "date": s_str, "end_date": e_str, 
            "purpose": purpose, "destination": destination, "status": status_text
        }
        r = requests.post(render_url, json=payload, timeout=30)
        if r.status_code == 200:
            st.toast(f"🔔 แจ้งเตือน {status_text} ผ่าน LINE สำเร็จ", icon="✅")
        elif r.status_code == 429:
            st.error("⚠️ โควตา LINE รายเดือนเต็มแล้ว (Error 429)")
        else:
            st.warning(f"⚠️ ส่งแจ้งเตือนไม่ได้: Status Code {r.status_code}")
    except Exception as e:
        st.error(f"📡 เกิดข้อผิดพลาดในการแจ้งเตือน: {e}")

def auto_delete_old_bookings():
    threshold = (datetime.now() - timedelta(days=45)).isoformat()
    try: supabase.table("bookings").delete().lt("end_time", threshold).execute()
    except: pass

# ==========================================
# 3. SIDEBAR & NAVIGATION
# ==========================================
auto_delete_old_bookings()
pending_items = supabase.table("bookings").select("id").eq("status", "Pending").execute().data
pending_count = len(pending_items)

st.sidebar.image("https://lh3.googleusercontent.com/d/1zCjSjSbCO-mbsaGoDI6g0G-bfmyVfqFV", use_container_width=True)
st.sidebar.link_button(label="➕ เพิ่มเพื่อน LINE (ดูคิว/สถานะ)", url=LINE_ADD_FRIEND_URL, use_container_width=True, type="primary")
st.sidebar.markdown(f"<p style='text-align: center; color: gray; font-size: 12px;'>Line ID: {CURRENT_BOT_ID}</p>", unsafe_allow_html=True)

if pending_count > 0:
    st.sidebar.markdown(f'<p class="blink">📢 มีรายการรออนุมัติ: {pending_count}</p>', unsafe_allow_html=True)

st.sidebar.markdown("---")
menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin (อนุมัติ)", "📊 รายงานประจำเดือน"]
choice = st.sidebar.selectbox("เมนูจัดการระบบ", menu)

# ==========================================
# 4. หน้าจองใหม่ (BOOKING) - [แก้ไข Logic วันนี้]
# ==========================================
if choice == "📝 จองใหม่":
    st.markdown('<div class="main-title">ระบบจองรถยนต์และห้องประชุม Online</div>', unsafe_allow_html=True)
    st.markdown('##### 📋 ข้อมูลรถและคนขับ')

    # --- ดัน HTML ให้ชิดขอบซ้ายเพื่อป้องกัน Markdown อ่านเป็น Code Block ---
    html_cards = """
    <style>
    .driver-grid-container {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 15px;
    margin-bottom: 25px;
    }
    .driver-card {
    background-color: #ffffff;
    border: 1px solid #E3F2FD;
    border-top: 4px solid #1E88E5;
    border-radius: 8px;
    padding: 15px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    transition: transform 0.2s;
    }
    .driver-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 4px 10px rgba(0,0,0,0.1);
    }
    .driver-card h4 {
    margin: 0 0 12px 0;
    color: #0D47A1;
    font-size: 16px;
    font-weight: bold;
    border-bottom: 1px dashed #BBDEFB;
    padding-bottom: 8px;
    }
    .driver-card p {
    margin: 5px 0;
    font-size: 14px;
    color: #424242;
    }
    .highlight-text {
    color: #1565C0;
    font-weight: bold;
    }
    </style>

    <div class="driver-grid-container">
    <div class="driver-card">
    <h4>🚗 Civic <span style="color:#666; font-size:14px;">(ตุ้ม)</span></h4>
    <p><b>ทะเบียน:</b> 5ขฬ-4317-กทม</p>
    <p><b>ประเภท:</b> รถรับ-ส่ง คุณคะโต้</p>
    <p><b>คนขับ:</b> ตุ้ม (Tum)</p>
    <p><b>โทร:</b> <span class="highlight-text">098-8388055</span></p>
    </div>

    <div class="driver-card">
    <h4>🚗 Civic <span style="color:#666; font-size:14px;">(บอล)</span></h4>
    <p><b>ทะเบียน:</b> 5ขฬ-7680-กทม</p>
    <p><b>ประเภท:</b> รถรับ-ส่ง คุณเคตะ</p>
    <p><b>คนขับ:</b> บอล (Ball)</p>
    <p><b>โทร:</b> <span class="highlight-text">063-9305458</span></p>
    </div>

    <div class="driver-card">
    <h4>🚙 Camry <span style="color:#666; font-size:14px;">(เนก)</span></h4>
    <p><b>ทะเบียน:</b> 6ขข-4068-กทม</p>
    <p><b>ประเภท:</b> รถรับ-ส่ง MD</p>
    <p><b>คนขับ:</b> เนก (Anek)</p>
    <p><b>โทร:</b> <span class="highlight-text">081-0402527</span></p>
    </div>

    <div class="driver-card">
    <h4>🚙 MG-EP</h4>
    <p><b>ทะเบียน:</b> 5ขก-7378-กทม</p>
    <p><b>ประเภท:</b> -</p>
    <p><b>คนขับ:</b> -</p>
    <p><b>โทร:</b> <span style="color:#9E9E9E;">-</span></p>
    </div>
    </div>
    """
    st.markdown(html_cards, unsafe_allow_html=True)
    # ---------------------------------------------
    
    # --- [FIXED: แก้ไข Logic การนับรายการวันนี้] ---
    now_dt = datetime.now()
    t_today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    t_today_end = now_dt.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
    
    # นับเฉพาะรายการที่ "เริ่ม" ภายในวันนี้เท่านั้น
    today_approved_res = supabase.table("bookings") \
        .select("id") \
        .eq("status", "Approved") \
        .gte("start_time", t_today_start) \
        .lte("start_time", t_today_end) \
        .execute()
    
    today_approved_count = len(today_approved_res.data) if today_approved_res.data else 0
    
    d1, d2, d3 = st.columns(3)
    d1.metric("รายการจองวันนี้", f"{today_approved_count} รายการ")
    d2.metric("รอพี่อนุมัติ", f"{pending_count} รายการ")
    d3.metric("สถานะฐานข้อมูล", "Connected")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        cat = st.radio("ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"], horizontal=True)
        res_list = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG", "MG (เนก)"] if cat == "รถยนต์" else ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]
        res = st.selectbox("เลือกรายการ", res_list)
        dest = st.text_input("สถานที่ปลายทาง") if cat == "รถยนต์" else "Office"
        name = st.text_input("ชื่อผู้จอง")
        phone = st.text_input("เบอร์โทรศัพท์")
        dept = st.text_input("แผนก")

    with col2:
        d_start = st.date_input("วันที่เริ่ม", datetime.now().date(), min_value=datetime.now().date())
        t_s_raw = st.text_input("เวลาเริ่ม (เช่น 0800)", value="", placeholder="กรอกเวลา เช่น 0800", max_chars=4)
        st.markdown("---")
        d_end = st.date_input("วันที่สิ้นสุด", d_start, min_value=d_start)
        t_e_raw = st.text_input("เวลาสิ้นสุด (เช่น 1700)", value="", placeholder="กรอกเวลา เช่น 1700", max_chars=4)
        reason = st.text_area("วัตถุประสงค์การใช้งาน")
        
        try:
            ts_f, te_f = format_time_string(t_s_raw.strip()), format_time_string(t_e_raw.strip())
            ts = datetime.combine(d_start, datetime.strptime(ts_f, "%H:%M").time())
            te = datetime.combine(d_end, datetime.strptime(te_f, "%H:%M").time())
        except: ts, te = None, None

    if st.button("ยืนยันการส่งคำขอจอง", use_container_width=True):
        if not name or not dept or ts is None:
            st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")
        elif ts < datetime.now(): # 👈 เพิ่มจุดนี้: เช็คว่าเวลาเริ่มต้น (ts) น้อยกว่าเวลาปัจจุบันหรือไม่
            st.error("❌ ไม่สามารถจองย้อนหลังได้ กรุณาเลือกเวลาปัจจุบันหรือล่วงหน้า")
        elif ts >= te:
            st.error("❌ เวลาเริ่มต้องมาก่อนเวลาสิ้นสุด")
        else:
            # รับค่า 3 ตัวแปร (เพิ่ม status_conf)
            is_conf, user_conf, status_conf = check_booking_conflict(res, ts.isoformat(), te.isoformat())
            if is_conf:
                msg = "ถูกจองแล้ว" if status_conf == "Approved" else "มีคนกำลังรออนุมัติ"
                st.error(f"❌ คิวชนกัน! {res} {msg} โดยคุณ {user_conf} ในเวลานี้")
            else:
                data = {"resource": res, "requester": name, "phone": phone, "dept": dept, "start_time": ts.isoformat(), "end_time": te.isoformat(), "purpose": reason, "destination": dest, "status": "Pending"}
                resp = supabase.table("bookings").insert(data).execute()
                if resp.data:
                    send_line_notification(resp.data[0]['id'], res, name, dept, ts, te, reason, dest)
                    st.success("✅ ส่งคำขอเรียบร้อย! โปรดรอ Admin อนุมัติ")
                    st.balloons()
                    time.sleep(2)
                    st.rerun()

# ==========================================
# 5. หน้าตารางงาน - [แก้ไขให้โชว์รายการวันนี้ทั้งหมด]
# ==========================================
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางการใช้งานปัจจุบันและล่วงหน้า")
    
    f_c1, f_c2 = st.columns([2, 1])
    search_q = f_c1.text_input("🔍 ค้นหาชื่อผู้จอง / สถานที่")
    view_cat = f_c2.selectbox("กรองตามประเภท", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
    
    # --- [FIXED: เปลี่ยนจากเช็คเวลาปัจจุบัน เป็นเช็คตั้งแต่เริ่มวันนี้ 00:00 น.] ---
    t_today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    db_res = supabase.table("bookings") \
        .select("*") \
        .eq("status", "Approved") \
        .gte("start_time", t_today_start) \
        .order("start_time") \
        .execute()
    
    df = pd.DataFrame(db_res.data)
    
    if df.empty:
        st.info("ขณะนี้ไม่มีรายการจอง")
    else:
        if view_cat == "รถยนต์": df = df[df['resource'].str.contains("Civic|Camry|MG", na=False)]
        elif view_cat == "ห้องประชุม": df = df[df['resource'].str.contains("ห้อง", na=False)]
        if search_q: df = df[df['requester'].str.contains(search_q, case=False) | df['destination'].str.contains(search_q, case=False)]
        
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
            with st.expander("🛠️ จัดการข้อมูล (แก้ไข/ลบ โดย Admin)"):
                sel_no = st.selectbox("เลือก No. ลำดับที่ต้องการจัดการ", df_show['ลำดับ/No.'].tolist())
                row = df_show[df_show['ลำดับ/No.'] == sel_no].iloc[0]
                
                with st.form("edit_full_form"):
                    e_col1, e_col2 = st.columns(2)
                    all_res = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG", "MG (เนก)", "ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]
                    try: res_idx = all_res.index(row['resource'])
                    except: res_idx = 0 
                    
                    n_res = e_col1.selectbox("รายการ / Resource", all_res, index=res_idx)
                    n_req = e_col1.text_input("ผู้จอง / Name", str(row['requester']))
                    n_dest = e_col1.text_input("ปลายทาง / Destination", str(row.get('destination', '-')))
                    
                    dt_s = pd.to_datetime(row['start_time'])
                    dt_e = pd.to_datetime(row['end_time'])
                    n_d_s = e_col2.date_input("วันที่เริ่ม", dt_s.date())
                    n_t_s = e_col2.text_input("เวลาเริ่ม (4 หลัก)", dt_s.strftime("%H%M"))
                    n_d_e = e_col2.date_input("วันที่สิ้นสุด", dt_e.date())
                    n_t_e = e_col2.text_input("เวลาสิ้นสุด (4 หลัก)", dt_e.strftime("%H%M"))
                    
                    n_purp = st.text_area("วัตถุประสงค์ / Purpose", str(row.get('purpose', '-')))
                    pw = st.text_input("รหัสผ่าน Admin", type="password")
                    b1, b2 = st.columns(2)
                    
                    if b1.form_submit_button("💾 บันทึกการแก้ไข", use_container_width=True):
                        if pw == "s1234":
                            try:
                                fs, fe = format_time_string(n_t_s), format_time_string(n_t_e)
                                f_start = datetime.combine(n_d_s, datetime.strptime(fs, "%H:%M").time()).isoformat()
                                f_end = datetime.combine(n_d_e, datetime.strptime(fe, "%H:%M").time()).isoformat()
                                supabase.table("bookings").update({
                                    "resource": n_res, "requester": n_req, "destination": n_dest, 
                                    "purpose": n_purp, "start_time": f_start, "end_time": f_end
                                }).eq("id", row['id']).execute()
                                st.success("อัปเดตเรียบร้อย!"); st.rerun()
                            except: st.error("❌ รูปแบบเวลาผิด")
                        else: st.error("รหัสผ่านไม่ถูกต้อง")
                    
                    if b2.form_submit_button("🗑️ ลบรายการนี้", use_container_width=True):
                        if pw == "s1234":
                            supabase.table("bookings").delete().eq("id", row['id']).execute(); st.rerun()
                        else: st.error("รหัสผ่านไม่ถูกต้อง")

# ==========================================
# 6. หน้า ADMIN (APPROVAL)
# ==========================================
elif choice == "🔑 Admin (อนุมัติ)":
    st.subheader("🔑 ระบบจัดการคำขอ")
    if st.text_input("กรอกรหัสผ่านเพื่ออนุมัติ", type="password") == "s1234":
        items = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute().data
        if not items: st.info("ไม่มีรายการรออนุมัติ")
        else:
            for item in items:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    curr_start = pd.to_datetime(item['start_time'])
                    with c1:
                        st.write(f"🚗 **{item['resource']}** | 👤 {item['requester']}")
                        st.write(f"📍 {item.get('destination','-')} | 🎯 {item.get('purpose','-')}")
                        a_d = st.date_input("ยืนยันวันที่", curr_start.date(), key=f"d_{item['id']}")
                        a_t = st.text_input("ยืนยันเวลาเริ่ม (4 หลัก)", curr_start.strftime("%H%M"), key=f"t_{item['id']}")
                    
                    if c2.button("อนุมัติ ✅", key=f"ap_{item['id']}", use_container_width=True):
                        try:
                            f_time = format_time_string(a_t)
                            final_start = datetime.combine(a_d, datetime.strptime(f_time, "%H:%M").time()).isoformat()
                            supabase.table("bookings").update({"status": "Approved", "start_time": final_start}).eq("id", item['id']).execute()
                            send_line_notification(item['id'], item['resource'], item['requester'], item['dept'], final_start, item['end_time'], item['purpose'], item.get('destination','-'), "Approved")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ รูปแบบเวลาผิด: {e}")
                    
                    if c2.button("ลบ 🗑️", key=f"dl_{item['id']}", use_container_width=True):
                        supabase.table("bookings").delete().eq("id", item['id']).execute(); st.rerun()

# ==========================================
# 7. หน้ารายงาน (REPORT)
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
            rep_type = st.selectbox("ประเภทรายงาน", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
            
            f_df = df_rep[df_rep['Month-Year'] == sel_m].copy()
            if rep_type == "รถยนต์": f_df = f_df[f_df['resource'].str.contains("Civic|Camry|MG", na=False)]
            elif rep_type == "ห้องประชุม": f_df = f_df[f_df['resource'].str.contains("ห้อง", na=False)]
            
            f_df['เวลาเริ่ม'] = f_df['start_time'].dt.strftime('%d/%m/%Y %H:%M')
            out_df = f_df[['resource', 'requester', 'dept', 'เวลาเริ่ม', 'destination', 'purpose']]
            st.dataframe(out_df, use_container_width=True)
            
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as w:
                out_df.to_excel(w, index=False)
            st.download_button("📥 ดาวน์โหลดรายงาน (Excel)", buf.getvalue(), f"Report_{rep_type}_{sel_m}.xlsx")
