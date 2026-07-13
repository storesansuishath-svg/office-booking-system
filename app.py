import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests
import time
import io
import difflib

# ==========================================
# 1. การเชื่อมต่อ DATABASE (Supabase คงเดิม 100%)
# ==========================================
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co" 
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. การตั้งค่าระบบ (แก้ไขรายชื่อได้ที่นี่โดยตรง)
# ==========================================
CURRENT_BOT_ID = "@851jrsed"  
LINE_ADD_FRIEND_URL = f"https://line.me/R/ti/p/{CURRENT_BOT_ID}"
GROUP_ID = "Cad74a32468ca40051bd7071a6064660d" # ไอดีกลุ่มแจ้งเตือน

# 🚗 ตั้งค่ารายชื่อรถยนต์ (ใช้ในการจองและประเมิน)
SYS_CARS = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG", "MG (เนก)"]

# 🏢 ตั้งค่ารายชื่อห้องประชุม
SYS_ROOMS = ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]

# 👥 ตั้งค่ารายชื่อแผนก
SYS_DEPTS = [
    "AC", "HR", "Sales", "QA", "PE", "Fac", "Loading", "Unload", 
    "Coating", "Repair", "Delivery", "Assembly", "QC - MS", 
    "Metal sheet", "Factory 1", "Factory 2", "Admin (JP)", "SAP"
]

# ==========================================
# 3. ตั้งค่าหน้าเพจและ CSS หลัก
# ==========================================
st.set_page_config(page_title="ระบบจองรถและห้องประชุม - Sansuisha", layout="wide")

st.markdown("""
    <style>
    @keyframes blinker { 50% { opacity: 0; } }
    .blink { animation: blinker 1s linear infinite; color: #FF0000; font-weight: bold; font-size: 18px; }
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        background-color: #E3F2FD !important; color: #0D47A1 !important; border: 1px solid #BBDEFB !important;
    }
    .main-title { font-size: 35px; font-weight: bold; color: #1E88E5; text-align: center; margin-bottom: 20px;}
    
    [data-testid="stLinkButton"] a {
        background-color: #8BC34A !important; color: white !important;
        border-radius: 8px !important; font-weight: bold !important;
        border: none !important; text-align: center !important;
    }
    [data-testid="stLinkButton"] a:hover { background-color: #4CAF50 !important; }
    [data-testid="stLinkButton"] a:active { background-color: #2E7D32 !important; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 4. ฟังก์ชันหลัก (CORE FUNCTIONS)
# ==========================================
def format_time_string(t_raw):
    clean = str(t_raw).replace(":", "").strip()
    if len(clean) == 4: return f"{clean[:2]}:{clean[2:]}"
    return clean

def check_booking_conflict(resource, start_time_iso, end_time_iso):
    res = supabase.table("bookings").select("*").eq("resource", resource).in_("status", ["Approved", "Pending"]).execute()
    new_s = datetime.fromisoformat(start_time_iso).replace(tzinfo=None)
    new_e = datetime.fromisoformat(end_time_iso).replace(tzinfo=None)
    for item in res.data:
        ex_s = pd.to_datetime(item['start_time']).replace(tzinfo=None)
        ex_e = pd.to_datetime(item['end_time']).replace(tzinfo=None)
        if new_s < ex_e and new_e > ex_s:
            return True, item['requester'], item['status']
    return False, None, None

def get_unrated_bookings(name, dept):
    # ยาแรง: ล็อกทั้งแผนก หากมีใครคนใดคนหนึ่งในแผนกนี้ค้างประเมิน จะไม่ให้คนในแผนกนี้จองรถใหม่เด็ดขาด
    try:
        now_iso = (datetime.utcnow() + timedelta(hours=7)).isoformat()
        res = supabase.table("bookings").select("*").eq("dept", dept).eq("status", "Approved").in_("resource", SYS_CARS).lt("end_time", now_iso).gte("end_time", "2026-07-01T00:00:00").execute()
        
        matched_unrated = []
        for d in res.data:
            if not d.get("is_rated"):
                matched_unrated.append(d)
        return matched_unrated
    except:
        return []
    
def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination, status_text="Pending"):
    render_url = "https://line-booking-system.onrender.com/notify"
    try:
        s_dt = pd.to_datetime(t_start)
        s_str = s_dt.strftime("%d/%m/%Y %H:%M")
        e_str = t_end if isinstance(t_end, str) else pd.to_datetime(t_end).strftime("%H:%M")
        payload = {
            "id": booking_id, "target_id": GROUP_ID, 
            "resource": resource, "name": name, "dept": dept, "date": s_str, "end_date": e_str, 
            "purpose": purpose, "destination": destination, "status": status_text
        }
        requests.post(render_url, json=payload, timeout=30)
    except: pass

def auto_delete_old_bookings():
    threshold = (datetime.now() - timedelta(days=45)).isoformat()
    try: supabase.table("bookings").delete().lt("end_time", threshold).execute()
    except: pass

# ==========================================
# 5. ระบบ LOGIN & AUTHENTICATION (เชื่อม app_admins)
# ==========================================
if "admin_logged_in" not in st.session_state:
    st.session_state["admin_logged_in"] = False
if "admin_user" not in st.session_state:
    st.session_state["admin_user"] = ""

def check_admin_login():
    if st.session_state["admin_logged_in"]:
        return True
    
    st.subheader("🔐 เข้าสู่ระบบผู้ดูแลระบบ (Admin)")
    try:
        admins_data = supabase.table("app_admins").select("*").execute().data
    except Exception as e:
        st.error(f"ไม่สามารถเชื่อมต่อฐานข้อมูลแอดมินได้: {e}")
        return False

    if not admins_data:
        st.info("👋 ยินดีต้อนรับ! ระบบตรวจพบว่ายังไม่มี Admin กรุณาสร้างบัญชี Admin คนแรก")
        with st.form("first_admin_form"):
            new_u = st.text_input("ตั้ง Username (แนะนำ: administrator)")
            new_p = st.text_input("ตั้ง Password", type="password")
            if st.form_submit_button("บันทึก Admin คนแรก", type="primary"):
                if new_u and new_p:
                    try:
                        supabase.table("app_admins").insert({"username": new_u, "password": new_p}).execute()
                        st.success("✅ สร้าง Admin สำเร็จ! กรุณาเข้าสู่ระบบ")
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as ex:
                        st.error(f"เกิดข้อผิดพลาดในการสร้าง Admin: {ex}")
                else:
                    st.error("⚠️ กรุณากรอก Username และ Password ให้ครบ")
        return False
    else:
        with st.form("login_form"):
            login_u = st.text_input("Username")
            login_p = st.text_input("Password", type="password")
            if st.form_submit_button("เข้าสู่ระบบ", type="primary"):
                match = [a for a in admins_data if a['username'] == login_u and a['password'] == login_p]
                if match:
                    st.session_state["admin_logged_in"] = True
                    st.session_state["admin_user"] = match[0]['username']
                    st.success("✅ เข้าสู่ระบบสำเร็จ!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Username หรือ Password ไม่ถูกต้อง")
        return False

# ==========================================
# 6. SIDEBAR & NAVIGATION
# ==========================================
auto_delete_old_bookings()
try:
    pending_items = supabase.table("bookings").select("id").eq("status", "Pending").execute().data
    pending_count = len(pending_items)
except:
    pending_count = 0

st.sidebar.image("https://lh3.googleusercontent.com/d/1zCjSjSbCO-mbsaGoDI6g0G-bfmyVfqFV", use_container_width=True)
st.sidebar.link_button(label="เพิ่มเพื่อน LINE (ดูคิว/สถานะ)", url=LINE_ADD_FRIEND_URL, use_container_width=True, type="primary")
st.sidebar.markdown(f"<p style='text-align: center; color: gray; font-size: 12px;'>Line ID: {CURRENT_BOT_ID}</p>", unsafe_allow_html=True)

if pending_count > 0:
    st.sidebar.markdown(f'<p class="blink">📢 มีรายการรออนุมัติ: {pending_count}</p>', unsafe_allow_html=True)

st.sidebar.markdown("---")

if st.session_state["admin_logged_in"]:
    st.sidebar.success(f"👤 เข้าสู่ระบบแล้ว:\n**{st.session_state['admin_user']}**")
    if st.sidebar.button("🚪 ออกจากระบบ (Logout)", use_container_width=True):
        st.session_state["admin_logged_in"] = False
        st.session_state["admin_user"] = ""
        st.rerun()
    st.sidebar.markdown("---")

# เมนูหลัก (ลบเมนูตั้งค่าระบบออกแล้ว)
menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "⭐ ประเมินการใช้งาน", "🔑 Admin (อนุมัติ)", "📊 รายงานประจำเดือน"]
choice = st.sidebar.selectbox("เมนูจัดการระบบ", menu)

# ==========================================
# 7. หน้าจองใหม่ (BOOKING)
# ==========================================
if choice == "📝 จองใหม่":
    st.markdown('<div class="main-title">ระบบจองรถยนต์และห้องประชุม Online</div>', unsafe_allow_html=True)
    st.markdown('##### 📋 ข้อมูลรถและคนขับ')
    
    # --- คำนวณสถานะ Real-time ---
    now_dt = datetime.utcnow() + timedelta(hours=7)
    t_today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    t_today_end = now_dt.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
    
    try:
        today_bookings = supabase.table("bookings").select("resource, start_time, end_time").eq("status", "Approved").gte("start_time", t_today_start).lte("start_time", t_today_end).execute()
    except:
        today_bookings = type('obj', (object,), {'data': []})
        
    car_status = {
        "Civic (ตุ้ม)": {"text": "🟢 ปัจจุบันว่าง", "time": "", "class": "status-free"},
        "Civic (บอล)": {"text": "🟢 ปัจจุบันว่าง", "time": "", "class": "status-free"},
        "Camry (เนก)": {"text": "🟢 ปัจจุบันว่าง", "time": "", "class": "status-free"},
        "MG": {"text": "🟢 ปัจจุบันว่าง", "time": "", "class": "status-free"}
    }

    room_status = {
        "ห้องชั้น 1 (ห้องใหญ่)": {"text": "🟢 ปัจจุบันว่าง", "time": "", "class": "status-free"},
        "ห้องชั้น 2": {"text": "🟢 ปัจจุบันว่าง", "time": "", "class": "status-free"},
        "ห้อง VIP": {"text": "🟢 ปัจจุบันว่าง", "time": "", "class": "status-free"},
        "ห้องชั้นลอย": {"text": "🟢 ปัจจุบันว่าง", "time": "", "class": "status-free"},
        "ห้อง Production": {"text": "🟢 ปัจจุบันว่าง", "time": "", "class": "status-free"}
    }

    if today_bookings.data:
        for b in today_bookings.data:
            res_name = b['resource']
            key = "MG" if "MG" in res_name else res_name
            st_dt = pd.to_datetime(b['start_time']).tz_localize(None)
            en_dt = pd.to_datetime(b['end_time']).tz_localize(None)
            
            if st_dt <= now_dt <= en_dt:
                if key in car_status:
                    car_status[key]["text"] = "🔴 ไม่ว่าง"
                    car_status[key]["time"] = f"{st_dt.strftime('%H:%M')} - {en_dt.strftime('%H:%M')}"
                    car_status[key]["class"] = "status-busy"
                elif key in room_status:
                    room_status[key]["text"] = "🔴 ไม่ว่าง"
                    room_status[key]["time"] = f"{st_dt.strftime('%H:%M')} - {en_dt.strftime('%H:%M')}"
                    room_status[key]["class"] = "status-busy"

    # --- โค้ด CSS และ HTML ดั้งเดิม ---
    css_style = """
    <style>
    .driver-grid-container { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin-bottom: 25px; }
    .driver-card { background-color: #ffffff; border: 1px solid #E3F2FD; border-top: 4px solid #1E88E5; border-radius: 8px; padding: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
    .card-header { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px dashed #BBDEFB; padding-bottom: 8px; margin-bottom: 12px; }
    .card-header h4 { margin: 0; color: #0D47A1; font-size: 16px; font-weight: bold; }
    .driver-card p { margin: 5px 0; font-size: 14px; color: #424242; }
    .highlight-text { color: #1565C0; font-weight: bold; }
    .room-flex-container { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 25px; }
    .room-badge-wrapper { background-color: #ffffff; border: 1px solid #F3E5F5; border-left: 4px solid #8E24AA; border-radius: 8px; padding: 10px; display: flex; flex-direction: column; align-items: center; justify-content: center; min-width: 150px; flex: 1; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .room-name { font-size: 13px; font-weight: bold; color: #4A148C; margin-bottom: 6px; text-align: center; }
    .status-badge { text-align: center; font-size: 12px; padding: 4px 10px; border-radius: 20px; font-weight: bold; min-width: 85px; }
    .status-free { background-color: #E8F5E9; color: #2E7D32; border: 1px solid #A5D6A7; }
    .status-busy { background-color: #FFEBEE; color: #C62828; border: 1px solid #EF9A9A; }
    .status-time { font-size: 11px; margin-top: 3px; font-weight: normal; }
    </style>
    """

    html_content = f"""
    <div class="driver-grid-container">
    <div class="driver-card">
        <div class="card-header">
            <h4>🚗 Civic <span style="color:#666; font-size:14px;">(ตุ้ม)</span></h4>
            <div class="status-badge {car_status['Civic (ตุ้ม)']['class']}">
                <div>{car_status['Civic (ตุ้ม)']['text']}</div>
                <div class="status-time">{car_status['Civic (ตุ้ม)']['time']}</div>
            </div>
        </div>
        <p><b>ทะเบียน:</b> 5ขฬ-4317-กทม</p><p><b>โทร:</b> <span class="highlight-text">098-8388055</span></p>
    </div>
    <div class="driver-card">
        <div class="card-header">
            <h4>🚗 Civic <span style="color:#666; font-size:14px;">(บอล)</span></h4>
            <div class="status-badge {car_status['Civic (บอล)']['class']}">
                <div>{car_status['Civic (บอล)']['text']}</div>
                <div class="status-time">{car_status['Civic (บอล)']['time']}</div>
            </div>
        </div>
        <p><b>ทะเบียน:</b> 5ขฬ-7680-กทม</p><p><b>โทร:</b> <span class="highlight-text">063-9305458</span></p>
    </div>
    <div class="driver-card">
        <div class="card-header">
            <h4>🚙 Camry <span style="color:#666; font-size:14px;">(เนก)</span></h4>
            <div class="status-badge {car_status['Camry (เนก)']['class']}">
                <div>{car_status['Camry (เนก)']['text']}</div>
                <div class="status-time">{car_status['Camry (เนก)']['time']}</div>
            </div>
        </div>
        <p><b>ทะเบียน:</b> 6ขข-4068-กทม</p><p><b>โทร:</b> <span class="highlight-text">081-0402527</span></p>
    </div>
    <div class="driver-card">
        <div class="card-header">
            <h4>🚙 MG-EP</h4>
            <div class="status-badge {car_status['MG']['class']}">
                <div>{car_status['MG']['text']}</div>
                <div class="status-time">{car_status['MG']['time']}</div>
            </div>
        </div>
        <p><b>ทะเบียน:</b> 5ขก-7378-กทม</p><p><b>โทร:</b> <span style="color:#9E9E9E;">-</span></p>
    </div>
    </div>

    <h5 style="margin-top: 20px;">🏢 สถานะห้องประชุม</h5>
    <div class="room-flex-container">
    <div class="room-badge-wrapper">
        <div class="room-name">ห้องชั้น 1 (ห้องใหญ่)</div>
        <div class="status-badge {room_status['ห้องชั้น 1 (ห้องใหญ่)']['class']}">
            <div>{room_status['ห้องชั้น 1 (ห้องใหญ่)']['text']}</div>
            <div class="status-time">{room_status['ห้องชั้น 1 (ห้องใหญ่)']['time']}</div>
        </div>
    </div>
    <div class="room-badge-wrapper">
        <div class="room-name">ห้องชั้น 2</div>
        <div class="status-badge {room_status['ห้องชั้น 2']['class']}">
            <div>{room_status['ห้องชั้น 2']['text']}</div>
            <div class="status-time">{room_status['ห้องชั้น 2']['time']}</div>
        </div>
    </div>
    <div class="room-badge-wrapper">
        <div class="room-name">ห้อง VIP</div>
        <div class="status-badge {room_status['ห้อง VIP']['class']}">
            <div>{room_status['ห้อง VIP']['text']}</div>
            <div class="status-time">{room_status['ห้อง VIP']['time']}</div>
        </div>
    </div>
    <div class="room-badge-wrapper">
        <div class="room-name">ห้องชั้นลอย</div>
        <div class="status-badge {room_status['ห้องชั้นลอย']['class']}">
            <div>{room_status['ห้องชั้นลอย']['text']}</div>
            <div class="status-time">{room_status['ห้องชั้นลอย']['time']}</div>
        </div>
    </div>
    <div class="room-badge-wrapper">
        <div class="room-name">ห้อง Production</div>
        <div class="status-badge {room_status['ห้อง Production']['class']}">
            <div>{room_status['ห้อง Production']['text']}</div>
            <div class="status-time">{room_status['ห้อง Production']['time']}</div>
        </div>
    </div>
    </div>
    """
    st.markdown(css_style + html_content, unsafe_allow_html=True)
    
    # --- สถิติ ---
    try:
        today_approved_res = supabase.table("bookings").select("id").eq("status", "Approved").gte("start_time", t_today_start).lte("start_time", t_today_end).execute()
        today_approved_count = len(today_approved_res.data) if today_approved_res.data else 0
    except: today_approved_count = 0
    
    d1, d2, d3 = st.columns(3)
    d1.metric("รายการจองวันนี้", f"{today_approved_count} รายการ")
    d2.metric("รอพี่อนุมัติ", f"{pending_count} รายการ")
    d3.metric("สถานะฐานข้อมูล", "Connected")
    st.markdown("---")

    st.markdown('<div class="blink" style="text-align:center; font-size:22px; margin-bottom: 20px;">หลังการใช้งานเสร็จกลับมาให้คะแนนคนขับรถทุกครั้ง!!</div>', unsafe_allow_html=True)

    # +++ โค้ดกระพริบโชว์รายชื่อผู้ค้างประเมินเพื่อกดดัน +++
    try:
        now_iso_alert = (datetime.utcnow() + timedelta(hours=7)).isoformat()
        res_alert = supabase.table("bookings").select("requester, dept, is_rated").eq("status", "Approved").in_("resource", SYS_CARS).lt("end_time", now_iso_alert).gte("end_time", "2026-07-01T00:00:00").execute()
        
        if res_alert.data:
            unrated_list = set()
            for d in res_alert.data:
                if not d.get("is_rated"):
                    req = str(d.get("requester", "")).strip()
                    dpt = str(d.get("dept", "")).strip()
                    if req: unrated_list.add(f"{req} ({dpt})")
            
            if unrated_list:
                alert_text = ", ".join(sorted(unrated_list))
                st.markdown(f'<div class="blink" style="text-align:center; font-size:26px; margin-bottom: 20px;">⚠️ รายชื่อผู้ที่ค้างการประเมิน: {alert_text} ⚠️</div>', unsafe_allow_html=True)
    except: pass

    col1, col2 = st.columns(2)
    with col1:
        cat = st.radio("ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"], horizontal=True)
        res_list = SYS_CARS if cat == "รถยนต์" else SYS_ROOMS
        res = st.selectbox("เลือกรายการ", res_list)
        dest = st.text_input("สถานที่ปลายทาง") if cat == "รถยนต์" else "Office"
        name = st.text_input("ชื่อผู้จอง")
        phone = st.text_input("เบอร์โทรศัพท์")
        dept = st.selectbox("แผนก", SYS_DEPTS)

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
        unrated_pending = get_unrated_bookings(name, dept) if name and dept else []
        if not name or not dept or ts is None:
            st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")
        elif unrated_pending:
            car_names = ", ".join(sorted(set(d['resource'] for d in unrated_pending)))
            st.error(f"❌ คุณ {name} ({dept}) มีรายการที่ยังไม่ได้ให้คะแนนคนขับ ({car_names}) กรุณาไปที่เมนู '⭐ ประเมินการใช้งาน' เพื่อให้คะแนนก่อน แล้วค่อยกลับมาจองใหม่นะครับ")
        elif ts < datetime.now(): 
            st.error("❌ ไม่สามารถจองย้อนหลังได้ กรุณาเลือกเวลาปัจจุบันหรือล่วงหน้า")
        elif ts >= te:
            st.error("❌ เวลาเริ่มต้องมาก่อนเวลาสิ้นสุด")
        else:
            is_conf, user_conf, status_conf = check_booking_conflict(res, ts.isoformat(), te.isoformat())
            if is_conf:
                msg = "ถูกจองแล้ว" if status_conf == "Approved" else "มีคนกำลังรออนุมัติ"
                st.error(f"❌ คิวชนกัน! {res} {msg} โดยคุณ {user_conf} ในเวลานี้")
            else:
                try:
                    data = {
                        "resource": res, "requester": name, "phone": phone, "dept": dept, 
                        "start_time": ts.isoformat(), "end_time": te.isoformat(), "purpose": reason, 
                        "destination": dest, "status": "Pending", "is_rated": False
                    }
                    res_insert = supabase.table("bookings").insert(data).execute()
                    
                    if res_insert.data:
                        new_id = res_insert.data[0]['id']
                        send_line_notification(new_id, res, name, dept, ts, te, reason, dest)
                        
                    st.success("✅ ส่งคำขอเรียบร้อย! โปรดรอ Admin อนุมัติ")
                    st.markdown('<div class="blink" style="text-align:center; padding:15px; background-color:#FFF9C4; border-radius:10px; border: 2px solid #FBC02D;">⭐ อย่าลืมเข้ามาให้คะแนนพนักงานขับรถหลังใช้งานเสร็จนะครับ ⭐</div>', unsafe_allow_html=True)
                    st.balloons()
                    time.sleep(3)
                    st.rerun()
                except Exception as e: st.error(f"เกิดข้อผิดพลาดในการจอง: {e}")

# ==========================================
# 8. หน้าตารางงาน 
# ==========================================
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางการใช้งานปัจจุบันและล่วงหน้า")
    f_c1, f_c2 = st.columns([2, 1])
    search_q = f_c1.text_input("🔍 ค้นหาชื่อผู้จอง / สถานที่")
    view_cat = f_c2.selectbox("กรองตามประเภท", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
    
    t_today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    try:
        res = supabase.table("bookings").select("*").eq("status", "Approved").gte("start_time", t_today_start).execute()
        df = pd.DataFrame(res.data)
        if not df.empty: df = df.sort_values(by="start_time")
    except: df = pd.DataFrame()
    
    if df.empty: st.info("ขณะนี้ไม่มีรายการจอง")
    else:
        if view_cat == "รถยนต์": df = df[df['resource'].isin(SYS_CARS)]
        elif view_cat == "ห้องประชุม": df = df[df['resource'].isin(SYS_ROOMS)]
        if search_q: df = df[df['requester'].str.contains(search_q, case=False, na=False) | df['destination'].str.contains(search_q, case=False, na=False)]
        
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
                if not st.session_state["admin_logged_in"]:
                    st.warning("⚠️ เฉพาะผู้ดูแลระบบเท่านั้น กรุณาเข้าสู่ระบบผ่านเมนู '🔑 Admin' ทางซ้ายมือก่อนใช้งานส่วนนี้")
                else:
                    sel_no = st.selectbox("เลือก No. ลำดับที่ต้องการจัดการ", df_show['ลำดับ/No.'].tolist())
                    row = df_show[df_show['ลำดับ/No.'] == sel_no].iloc[0]
                    
                    with st.form("edit_full_form"):
                        e_col1, e_col2 = st.columns(2)
                        all_res = SYS_CARS + SYS_ROOMS
                        try: res_idx = all_res.index(row['resource'])
                        except: res_idx = 0 
                        
                        n_res = e_col1.selectbox("รายการ / Resource", all_res, index=res_idx)
                        n_req = e_col1.text_input("ผู้จอง / Name", str(row['requester']))
                        n_dest = e_col1.text_input("ปลายทาง / Destination", str(row.get('destination', '-')))
                        try: dept_idx = SYS_DEPTS.index(row.get('dept', ''))
                        except: dept_idx = 0
                        n_dept = e_col1.selectbox("แผนก / Department", SYS_DEPTS, index=dept_idx)
                        
                        dt_s = pd.to_datetime(row['start_time'])
                        dt_e = pd.to_datetime(row['end_time'])
                        n_d_s = e_col2.date_input("วันที่เริ่ม", dt_s.date())
                        n_t_s = e_col2.text_input("เวลาเริ่ม (4 หลัก)", dt_s.strftime("%H%M"))
                        n_d_e = e_col2.date_input("วันที่สิ้นสุด", dt_e.date())
                        n_t_e = e_col2.text_input("เวลาสิ้นสุด (4 หลัก)", dt_e.strftime("%H%M"))
                        
                        n_purp = st.text_area("วัตถุประสงค์ / Purpose", str(row.get('purpose', '-')))
                        
                        b1, b2 = st.columns(2)
                        if b1.form_submit_button("💾 บันทึกการแก้ไข", use_container_width=True):
                            try:
                                fs, fe = format_time_string(n_t_s), format_time_string(n_t_e)
                                f_start = datetime.combine(n_d_s, datetime.strptime(fs, "%H:%M").time()).isoformat()
                                f_end = datetime.combine(n_d_e, datetime.strptime(fe, "%H:%M").time()).isoformat()
                                
                                supabase.table("bookings").update({
                                    "resource": n_res, "requester": n_req, "destination": n_dest,"dept": n_dept,
                                    "purpose": n_purp, "start_time": f_start, "end_time": f_end
                                }).eq("id", row['id']).execute()
                                
                                st.success("อัปเดตเรียบร้อย!"); st.rerun()
                            except Exception as e: st.error(f"❌ ผิดพลาด: {e}")
                        
                        if b2.form_submit_button("🗑️ ลบรายการนี้", use_container_width=True):
                            try:
                                supabase.table("bookings").delete().eq("id", row['id']).execute()
                                st.rerun()
                            except Exception as e: st.error(f"❌ ลบไม่สำเร็จ: {e}")

# ==========================================
# 9. เมนู ⭐ ประเมินการใช้งาน
# ==========================================
elif choice == "⭐ ประเมินการใช้งาน":
    st.subheader("⭐ ประเมินการปฏิบัติงานพนักงานขับรถ")
    now_iso = (datetime.utcnow() + timedelta(hours=7)).isoformat()
    try:
        res = supabase.table("bookings").select("*").eq("status", "Approved").in_("resource", SYS_CARS).lt("end_time", now_iso).gte("end_time", "2026-07-01T00:00:00").execute()
        data = res.data if res.data else []
        unrated = [d for d in data if not d.get("is_rated")]
        
        if not unrated:
            st.success("🎉 ไม่มีรายการที่ต้องประเมินในขณะนี้ครับ ทุกรายการได้รับการให้คะแนนครบถ้วนแล้ว")
        else:
            st.info("💡 กรุณาเลือกรายการจองรถยนต์ที่เพิ่งใช้งานเสร็จสิ้นเพื่อทำการประเมินพนักงานขับรถ")
            options_dict = {}
            for d in sorted(unrated, key=lambda x: x['end_time'], reverse=True):
                end_dt_str = pd.to_datetime(d['end_time']).strftime('%d/%m/%Y %H:%M')
                label = f"วันที่: {end_dt_str} | รถ: {d['resource']} | ผู้จอง: {d['requester']}"
                options_dict[label] = d
                
            selected_label = st.selectbox("เลือกรถที่ต้องการประเมิน", list(options_dict.keys()))
            selected_booking = options_dict[selected_label]
            
            st.markdown("---")
            st.markdown(f"กำลังประเมินพนักงานขับรถสำหรับรายการ **{selected_booking['resource']}**")
            
            with st.form("rating_form"):
                st.write("**หัวข้อประเมิน (1 = ต้องปรับปรุง, 5 = ดีมาก)**")
                q1 = st.radio("พนักงานขับรถมีสภาพร่างกายพร้อมปฏิบัติงาน", [1, 2, 3, 4, 5], index=4, horizontal=True)
                q2 = st.radio("สภาพรถพร้อมใช้งานมีความสะอาดและปลอดภัย", [1, 2, 3, 4, 5], index=4, horizontal=True)
                q3 = st.radio("ขับรถด้วยความระมัดระวังและปลอดภัย", [1, 2, 3, 4, 5], index=4, horizontal=True)
                q4 = st.radio("กิริยาวาจาและพฤติกรรมมีความเหมาะสม", [1, 2, 3, 4, 5], index=4, horizontal=True)
                suggestion = st.text_area("ข้อเสนอแนะอื่นๆ")
                
                st.warning("⚠️ โปรดตรวจสอบข้อมูลให้ครบถ้วนก่อนส่ง (ไม่สามารถแก้ไขข้อมูลได้ภายหลังการให้คะแนน)")
                confirm = st.checkbox("แน่ใจ / ยืนยันข้อมูล")
                
                if st.form_submit_button("ส่งผลการประเมิน", type="primary"):
                    if not confirm:
                        st.error("❌ กรุณากดยืนยัน (ติ๊กถูกที่ช่อง แน่ใจ / ยืนยันข้อมูล) ก่อนส่งผลประเมินครับ")
                    else:
                        supabase.table("bookings").update({
                            "is_rated": True, "q1": q1, "q2": q2, "q3": q3, "q4": q4, "suggestion": suggestion
                        }).eq("id", selected_booking['id']).execute()
                        
                        st.success("✅ บันทึกผลการประเมินเรียบร้อยแล้ว ขอบคุณที่ใช้บริการครับ!")
                        time.sleep(2)
                        st.rerun()
    except Exception as e: st.error(f"เกิดข้อผิดพลาดในการประเมิน: {e}")

# ==========================================
# 10. หน้า ADMIN (APPROVAL) + ระบบ APP_ADMINS 
# ==========================================
elif choice == "🔑 Admin (อนุมัติ)":
    if check_admin_login():
        st.subheader("🔑 ระบบจัดการคำขอ (อนุมัติการจอง)")
        try: 
            res = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute()
            items = res.data if res.data else []
        except: items = []
        
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
                        except Exception as e: st.error(f"❌ ผิดพลาด: {e}")
                    
                    if c2.button("ลบ 🗑️", key=f"dl_{item['id']}", use_container_width=True):
                        try:
                            supabase.table("bookings").delete().eq("id", item['id']).execute()
                            st.rerun()
                        except: pass

        # ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        # ส่วนหน้าต่างจัดการแอดมิน (app_admins) คงลอจิกเดิม 100% 
        # ย้ายมาต่อท้ายเมนูนี้แทนเมนู "⚙️ ตั้งค่าระบบ" ที่ลบไป
        # ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        st.markdown("---")
        st.markdown("##### 📋 รายชื่อผู้ดูแลระบบ (Admin List)")
        
        try:
            admins_res = supabase.table("app_admins").select("*").execute()
            admins = admins_res.data if admins_res.data else []
        except:
            admins = []
            
        for idx, adm in enumerate(admins):
            col_u, col_d = st.columns([4, 1])
            col_u.write(f"• **{adm['username']}**")
            
            # ลอจิกเดิม: ให้สิทธิ์ลบเฉพาะ user: administrator
            if st.session_state["admin_user"] == "administrator":
                if adm['username'] != "administrator":
                    if col_d.button("🗑️ ลบแอดมิน", key=f"del_adm_{idx}"):
                        try:
                            supabase.table("app_admins").delete().eq("id", adm['id']).execute()
                            st.success(f"ลบ {adm['username']} สำเร็จ")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e: st.error(f"ลบไม่สำเร็จ: {e}")

        st.markdown("---")
        # ลอจิกเดิม: ให้สิทธิ์เพิ่มเฉพาะ user: administrator
        if st.session_state["admin_user"] == "administrator":
            st.markdown("##### ➕ เพิ่ม Admin ใหม่")
            with st.form("add_admin_form"):
                n_user = st.text_input("Username ใหม่")
                n_pass = st.text_input("Password ใหม่", type="password")
                if st.form_submit_button("บันทึก Admin ใหม่"):
                    if not n_user or not n_pass:
                        st.error("กรุณากรอกข้อมูลให้ครบถ้วน")
                    else:
                        is_dup = any(x['username'] == n_user for x in admins)
                        if is_dup:
                            st.error("❌ Username นี้มีอยู่แล้วในระบบ")
                        else:
                            try:
                                supabase.table("app_admins").insert({"username": n_user, "password": n_pass}).execute()
                                st.success(f"✅ เพิ่ม Admin {n_user} สำเร็จ!")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e: st.error(f"เพิ่มไม่สำเร็จ: {e}")
        else:
            st.info("🔒 สิทธิ์การ 'เพิ่ม' หรือ 'ลบ' ผู้ดูแลระบบ สงวนไว้สำหรับ Username: **administrator** เท่านั้น")

# ==========================================
# 11. หน้ารายงาน (REPORT) 
# ==========================================
elif choice == "📊 รายงานประจำเดือน":
    if check_admin_login():
        st.subheader("📊 รายงานสรุปการใช้ทรัพยากรและการประเมิน")
        try: 
            res = supabase.table("bookings").select("*").eq("status", "Approved").execute()
            data = res.data if res.data else []
        except: data = []
        
        if data:
            df_rep = pd.DataFrame(data)
            df_rep['start_time'] = pd.to_datetime(df_rep['start_time'])
            df_rep['Month-Year'] = df_rep['start_time'].dt.strftime('%m/%Y')
            
            c1, c2 = st.columns(2)
            sel_m = c1.selectbox("เลือกเดือน", sorted(df_rep['Month-Year'].unique(), reverse=True))
            rep_type = st.selectbox("ประเภทรายงาน", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
            
            f_df = df_rep[df_rep['Month-Year'] == sel_m].copy()
            if rep_type == "รถยนต์": f_df = f_df[f_df['resource'].isin(SYS_CARS)]
            elif rep_type == "ห้องประชุม": f_df = f_df[f_df['resource'].isin(SYS_ROOMS)]
            
            f_df['เวลาเริ่ม'] = f_df['start_time'].dt.strftime('%d/%m/%Y %H:%M')
            out_df = f_df[['resource', 'requester', 'dept', 'เวลาเริ่ม', 'destination', 'purpose']].copy()
            
            if 'is_rated' in f_df.columns:
                out_df['ประเมิน'] = f_df['is_rated'].apply(lambda x: 'ใช่' if x == True else 'ยัง')
                out_df['ร่างกาย'] = f_df.get('q1', '-')
                out_df['ความสะอาด'] = f_df.get('q2', '-')
                out_df['ขับปลอดภัย'] = f_df.get('q3', '-')
                out_df['มารยาท'] = f_df.get('q4', '-')
                out_df['ข้อเสนอแนะ'] = f_df.get('suggestion', '-')
                
                if rep_type in ["ทั้งหมด", "รถยนต์"]:
                    st.markdown("---")
                    st.markdown("#### ⭐ สรุปเปอร์เซ็นต์ความพึงพอใจพนักงานขับรถเฉลี่ย ประจำเดือน")
                    rated_cars = f_df[(f_df['resource'].isin(SYS_CARS)) & (f_df['is_rated'] == True)]
                    
                    if not rated_cars.empty:
                        avg1, avg2, avg3, avg4 = (rated_cars['q1'].mean()/5)*100, (rated_cars['q2'].mean()/5)*100, (rated_cars['q3'].mean()/5)*100, (rated_cars['q4'].mean()/5)*100
                        total_avg = (avg1 + avg2 + avg3 + avg4) / 4
                        st.success(f"📈 ภาพรวมเฉลี่ยความพึงพอใจ: **{total_avg:.2f}%**")
                        sc1, sc2, sc3, sc4 = st.columns(4)
                        sc1.metric("1. สภาพร่างกาย", f"{avg1:.2f}%")
                        sc2.metric("2. สภาพรถ/ความสะอาด", f"{avg2:.2f}%")
                        sc3.metric("3. การขับรถปลอดภัย", f"{avg3:.2f}%")
                        sc4.metric("4. มารยาท", f"{avg4:.2f}%")
                    else: st.info("ยังไม่มีข้อมูลการประเมินในเดือนที่เลือก")
            
            st.markdown("---")
            st.dataframe(out_df, use_container_width=True)
            
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as w: out_df.to_excel(w, index=False)
            st.download_button("📥 ดาวน์โหลดรายงาน (Excel)", buf.getvalue(), f"Report_{rep_type}_{sel_m.replace('/', '-')}.xlsx")
        else: st.info("ยังไม่มีข้อมูลในระบบฐานข้อมูล")
