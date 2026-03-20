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

CURRENT_BOT_ID = "@871fsfnr"  
LINE_ADD_FRIEND_URL = f"https://line.me/R/ti/p/{CURRENT_BOT_ID}"

st.set_page_config(page_title="ระบบจองรถและห้องประชุม - Sansuisha", layout="wide")

# ==========================================
# 2. MODERN UI V2 (FIXED CSS) - ปรับปรุงความโค้ง
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;600;700&display=swap');

    /* Global */
    html, body, [class*="css"] { font-family: 'Sarabun', sans-serif; background-color: #F8F9FA; }

    /* Sidebar Fixes */
    [data-testid="stSidebar"] { background-color: #1A237E !important; }
    [data-testid="stSidebar"] .stLinkButton a { background-color: #00B900 !important; color: white !important; border-radius: 8px !important; font-weight: bold !important; border: none !important; }
    [data-testid="stSidebar"] .stSelectbox label p { color: black !important; font-weight: 600 !important; }
    [data-testid="stSidebar"] div[data-baseweb="select"] > div { color: black !important; background-color: #E3F2FD !important; border-radius: 5px !important; }
    [data-testid="stSidebar"] .stMarkdown p { color: black !important; }

    /* Dashboard Cards */
    .card-container { display: flex; gap: 20px; margin-bottom: 30px; }
    .status-card { background-color: white; padding: 30px 20px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); flex: 1; text-align: center; border-bottom: 6px solid #ccc; }
    .card-label { color: #64748B; font-size: 16px; font-weight: 600; margin-bottom: 15px; display: flex; justify-content: center; align-items: center; gap: 8px; }
    .card-value { color: #1E293B; font-size: 36px; font-weight: 700; }
    .card-unit { font-size: 16px; color: #64748B; font-weight: 600; margin-left: 5px; }

    /* Status Grid & Item */
    .res-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; margin-top: 15px; }
    .res-item { background: white; padding: 25px 15px; border-radius: 12px; border: 1px solid #E2E8F0; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.02); display: flex; flex-direction: column; align-items: center; justify-content: center; }
    .res-name { font-weight: 700; color: #1A237E; font-size: 16px; margin-bottom: 15px; }

    /* --- [✅ จุดที่แก้: ป้ายสถานะทรงแคปซูล] --- */
    .badge {
        display: inline-block;
        padding: 8px 25px; /* เพิ่ม padding เพื่อให้ดูมีพื้นที่ */
        border-radius: 50px !important; /* บังคับให้เป็นแคปซูลยาเป๊ะๆ */
        font-size: 14px;
        font-weight: 700;
        border: 2px solid transparent; /* เตรียมขอบไว้ */
    }
    /* ป้ายแดง (ไม่ว่าง) ให้เหมือนรูป */
    .status-busy {
        background-color: #FEE2E2 !important; /* สีแดงอ่อนมาก */
        color: #991B1B !important; /* ตัวหนังสือแดงเข้ม */
        border-color: #FECACA !important; /* ขอบแดงอ่อน */
    }
    /* ป้ายเขียว (ว่าง) ให้เหมือนรูป */
    .status-free {
        background-color: #DCFCE7 !important; /* สีเขียวอ่อนมาก */
        color: #166534 !important; /* ตัวหนังสือเขียวเข้ม */
        border-color: #A7F3D0 !important; /* ขอบเขียวอ่อน */
    }
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
    # แก้ไข: เปลี่ยนจาก .eq("status", "Approved") เป็น .in_("status", ["Approved", "Pending"])
    # เพื่อให้ระบบตรวจสอบทั้งคิวที่คอนเฟิร์มแล้ว และคิวที่กำลังรอพิจารณาอยู่
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
        
        # ตรวจสอบช่วงเวลาที่ซ้อนทับกัน (Overlap logic)
        if new_s < ex_e and new_e > ex_s:
            # คืนค่าสถานะกลับไปด้วยว่าชนกับใคร และสถานะอะไร (เผื่ออยากเอาไปโชว์)
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
        
        # [FIX] ขยายเวลา Timeout เป็น 30 วินาที 
        r = requests.post(render_url, json=payload, timeout=30)
        
        if r.status_code == 200:
            st.toast(f"🔔 แจ้งเตือน {status_text} ผ่าน LINE สำเร็จ", icon="✅")
        elif r.status_code == 429:
            st.error("⚠️ โควตา LINE รายเดือนเต็มแล้ว (Error 429)")
        else:
            st.warning(f"⚠️ ส่งแจ้งเตือนไม่ได้: Status Code {r.status_code}")
    except requests.exceptions.Timeout:
        st.error("📡 เชื่อมต่อเซิร์ฟเวอร์แจ้งเตือนไม่ได้: หมดเวลารอ (Timeout) กรุณาลองใหม่")
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

st.sidebar.link_button(
    label="➕ เพิ่มเพื่อน LINE (ดูคิว/สถานะ)",
    url=LINE_ADD_FRIEND_URL,
    use_container_width=True,
    type="primary"
)
st.sidebar.markdown(f"<p style='text-align: center; color: gray; font-size: 12px;'>Line ID: {CURRENT_BOT_ID}</p>", unsafe_allow_html=True)
# ---------------------------------------

if pending_count > 0:
    st.sidebar.markdown(f'<p class="blink">📢 มีรายการรออนุมัติ: {pending_count}</p>', unsafe_allow_html=True)

st.sidebar.markdown("---")
menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin (อนุมัติ)", "📊 รายงานประจำเดือน"]
choice = st.sidebar.selectbox("เมนูจัดการระบบ", menu)

# ==========================================
# 4. หน้าจองใหม่ (BOOKING)
# ==========================================
if choice == "📝 จองใหม่":
    st.markdown("""
        <div class="v2-header">
            <h1 class="v2-title">Resource Booking Portal</h1>
            <p class="v2-subtitle">ระบบจองรถยนต์และห้องประชุมส่วนกลาง | Sansuisha (Thailand)</p>
        </div>
    """, unsafe_allow_html=True)
    
    # ----------------------------------------------------
    # [แก้ไขตรรกะ: นับเฉพาะรายการของ "วันนี้" จริงๆ]
    # ----------------------------------------------------
    now = datetime.now()
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_today = start_today + timedelta(days=1)
    
    # ดึงข้อมูลที่อนุมัติแล้วทั้งหมดมาไว้ในตัวแปรเดียว
    all_approved_res = supabase.table("bookings").select("*").eq("status", "Approved").execute()
    all_approved_data = all_approved_res.data if all_approved_res.data else []
    
    # นับเฉพาะรายการที่คิวเริ่มใน "วันนี้" เท่านั้น (ไม่นับพรุ่งนี้)
    today_bookings = [b for b in all_approved_data if start_today <= pd.to_datetime(b['start_time']).replace(tzinfo=None) < end_today]
    today_count = len(today_bookings)
    
    # --- [ส่วน Dashboard Cards V2] ---
    card_html = f"""
    <div class="card-container">
        <div class="status-card" style="border-bottom-color: #1A237E;">
            <div class="card-label">📅 รายการจองวันนี้</div>
            <div class="card-value">{today_count}<span class="card-unit">รายการ</span></div>
        </div>
        <div class="status-card" style="border-bottom-color: #F59E0B;">
            <div class="card-label">⏳ รอเพื่ออนุมัติ</div>
            <div class="card-value">{pending_count}<span class="card-unit">รายการ</span></div>
        </div>
        <div class="status-card" style="border-bottom-color: #10B981;">
            <div class="card-label">🖥️ ฐานข้อมูล</div>
            <div class="card-value" style="color: #10B981; font-size: 20px; margin-top: 10px;">● Online</div>
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)
    st.markdown("---")

    # --- [Step 2: แยกกลุ่มแสดงสถานะความว่าง V2 (ปรับเป็น 2 สี แดง/เขียว ตามต้องการ)] ---
    def generate_res_grid(res_list, title_text, icon):
        html = f'<h3 style="color: #1A237E; margin-top: 30px; font-weight: 700;">{icon} {title_text}</h3><div class="res-grid">'
        for r in res_list:
            current_user = None
            today_times = []
            
            # วนลูปเช็คคิวทั้งหมดที่อนุมัติแล้ว
            for b in all_approved_data:
                if b['resource'] == r:
                    s_dt = pd.to_datetime(b['start_time']).replace(tzinfo=None)
                    e_dt = pd.to_datetime(b['end_time']).replace(tzinfo=None)
                    
                    # 1. เช็คว่า "ตอนนี้" (Real-time) กำลังถูกใช้งานอยู่ไหม?
                    if s_dt <= now <= e_dt:
                        current_user = b['requester']
                        
                    # 2. เก็บ "เวลาการใช้งานทั้งหมด" ของวันนี้ (ทั้งอดีต ปัจจุบัน อนาคต)
                    if s_dt.date() == now.date() or e_dt.date() == now.date():
                        today_times.append(f"{s_dt.strftime('%H:%M')}-{e_dt.strftime('%H:%M')}")

            # --- สร้างป้ายสถานะ (Badge) มีแค่ แดง กับ เขียว ---
            if current_user:
                # สถานะ: กำลังใช้งาน -> สีแดง
                html += f'<div class="res-item"><span class="res-name">{r}</span><span class="badge status-busy">❌ ไม่ว่าง ({current_user})</span></div>'
            else:
                # สถานะ: ว่าง -> สีเขียว (ถ้ามีคิววันนี้ให้แสดงเวลาด้วย)
                if today_times:
                    today_times.sort() # เรียงเวลาจากเช้าไปเย็น
                    times_str = ", ".join(today_times)
                    html += f'<div class="res-item"><span class="res-name">{r}</span><span class="badge status-free">✅ ว่าง ({times_str})</span></div>'
                else:
                    html += f'<div class="res-item"><span class="res-name">{r}</span><span class="badge status-free">✅ ว่าง</span></div>'
                
        html += '</div>'
        return html

    car_list = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG", "MG (เนก)"]
    room_list = ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]

    st.markdown(generate_res_grid(car_list, "สถานะรถยนต์", "🚗"), unsafe_allow_html=True)
    st.markdown(generate_res_grid(room_list, "สถานะห้องประชุม", "🏢"), unsafe_allow_html=True)
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
                # ... (โค้ด Insert ข้อมูลเดิมของคุณ) ...
                data = {"resource": res, "requester": name, "phone": phone, "dept": dept, "start_time": ts.isoformat(), "end_time": te.isoformat(), "purpose": reason, "destination": dest, "status": "Pending"}
                resp = supabase.table("bookings").insert(data).execute()
                if resp.data:
                    send_line_notification(resp.data[0]['id'], res, name, dept, ts, te, reason, dest)
                    st.success("✅ ส่งคำขอเรียบร้อย! โปรดรอ Admin อนุมัติ")
                    st.balloons()

# ==========================================
# 5. หน้าตารางงาน (คอลัมน์เต็ม 100% ตามต้นฉบับ)
# ==========================================
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางการใช้งานปัจจุบันและล่วงหน้า")
    
    f_c1, f_c2 = st.columns([2, 1])
    search_q = f_c1.text_input("🔍 ค้นหาชื่อผู้จอง / สถานที่")
    view_cat = f_c2.selectbox("กรองตามประเภท", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
    
    now_iso = datetime.now().isoformat()
    db_res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).order("start_time").execute()
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
            
            # [FIX] คืนชีพรูปแบบเวลาและคอลัมน์เต็มสูบ
            df_show['start_fmt'] = pd.to_datetime(df_show['start_time'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M')
            df_show['end_fmt'] = pd.to_datetime(df_show['end_time'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M')
            
            df_disp = df_show[['ลำดับ/No.', 'resource', 'start_fmt', 'end_fmt', 'requester', 'purpose', 'destination']]
            df_disp.columns = ['ลำดับ / No.', 'รายการ / Resource', 'เวลาเริ่ม / Start Time', 'เวลาสิ้นสุด / End Time', 'ผู้จอง / Name', 'วัตถุประสงค์ / Purpose', 'ปลายทาง / Destination']
            st.dataframe(df_disp, use_container_width=True)

            # ส่วนแก้ไขข้อมูล (Full Form)
            st.markdown("---")
            # --- [จุดแก้ไข: ส่วนดึงข้อมูลมาแสดงในฟอร์ม] ---
            with st.expander("🛠️ จัดการข้อมูล (แก้ไข/ลบ โดย Admin)"):
                sel_no = st.selectbox("เลือก No. ลำดับที่ต้องการจัดการ", df_show['ลำดับ/No.'].tolist())
                # ดึงข้อมูลแถวที่เลือก
                row = df_show[df_show['ลำดับ/No.'] == sel_no].iloc[0]
                
                with st.form("edit_full_form"):
                    e_col1, e_col2 = st.columns(2)
                    
                    # ✅ แก้จุดที่ชื่อรถไม่ขึ้น: ต้องสร้าง List มาตรฐานแล้วหา Index ของค่าเดิมครับ
                    all_res = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG", "MG (เนก)", "ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]
                    try: 
                        res_idx = all_res.index(row['resource'])
                    except: 
                        res_idx = 0 # ถ้าหาไม่เจอให้ไปที่ตัวแรก
                    
                    n_res = e_col1.selectbox("รายการ / Resource", all_res, index=res_idx)
                    n_req = e_col1.text_input("ผู้จอง / Name", str(row['requester']))
                    n_dest = e_col1.text_input("ปลายทาง / Destination", str(row.get('destination', '-')))
                    
                    # ✅ ดึงวันที่และเวลาเดิมมาใส่
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
                        # [FIX] แยกระบบแปลงเวลาออกจากการส่ง LINE ป้องกันบั๊กซ้อนบั๊ก
                        try:
                            f_time = format_time_string(a_t)
                            final_start = datetime.combine(a_d, datetime.strptime(f_time, "%H:%M").time()).isoformat()
                        except Exception as e:
                            st.error(f"❌ รูปแบบเวลาผิด: {e}")
                            st.stop() # หยุดการทำงานถ้าเวลาผิด

                        # 1. บันทึกลง Supabase ก่อน (ชัวร์สุด)
                        supabase.table("bookings").update({"status": "Approved", "start_time": final_start}).eq("id", item['id']).execute()
                        st.success("✅ บันทึกการอนุมัติลงระบบเรียบร้อยแล้ว!")
                        
                        # 2. พยายามส่ง LINE (ถ้าพัง ระบบก็ยังอนุมัติผ่าน)
                        send_line_notification(item['id'], item['resource'], item['requester'], item['dept'], final_start, item['end_time'], item['purpose'], item.get('destination','-'), "Approved")
                        
                        st.rerun()
                        
                    if c2.button("ลบ 🗑️", key=f"dl_{item['id']}", use_container_width=True):
                        supabase.table("bookings").delete().eq("id", item['id']).execute(); st.rerun()

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
