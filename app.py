import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests, io

# --- 1. CONFIG & DB CONNECTION ---
URL = "https://qejqynbxdflwebzzwfzu.supabase.co"
KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
supabase = create_client(URL, KEY)

st.set_page_config(page_title="Sansuisha Booking", layout="wide")
st.markdown("""<style>
    @keyframes blink { 50% { opacity: 0; } }
    .blink { animation: blink 1s linear infinite; color: red; font-weight: bold; }
    .stTextInput input, .stSelectbox [data-baseweb="select"] { background-color: #E3F2FD !important; }
</style>""", unsafe_allow_html=True)

# --- 2. CORE FUNCTIONS ---
def fmt_t(t): # แปลง 0800 -> 08:00
    t = str(t).replace(":", "").strip()
    return f"{t[:2]}:{t[2:]}" if len(t) == 4 else t

def check_conflict(res, s_iso, e_iso): # ระบบกันคิวชน
    db = supabase.table("bookings").select("*").eq("resource", res).eq("status", "Approved").execute().data
    ns, ne = datetime.fromisoformat(s_iso).replace(tzinfo=None), datetime.fromisoformat(e_iso).replace(tzinfo=None)
    for i in db:
        es, ee = pd.to_datetime(i['start_time']).replace(tzinfo=None), pd.to_datetime(i['end_time']).replace(tzinfo=None)
        if ns < ee and ne > es: return True, i['requester']
    return False, None

def send_line(id, res, name, dept, s, e, purp, dest, stat="Pending"):
    url = "https://line-booking-system.onrender.com/notify"
    s_f = s.strftime("%d/%m/%Y %H:%M") if isinstance(s, datetime) else str(s)
    e_f = e if isinstance(e, str) else e.strftime("%H:%M")
    payload = {"id":id, "target_id":"Cad74a32468ca40051bd7071a6064660d", "resource":res, "name":name, "dept":dept, "date":s_f, "end_date":e_f, "purpose":purp, "destination":dest, "status":stat}
    try: requests.post(url, json=payload, timeout=7)
    except: pass

# --- 3. SIDEBAR & DASHBOARD ---
pend_data = supabase.table("bookings").select("id").eq("status", "Pending").execute().data
p_count = len(pend_data)
st.sidebar.image("https://lh3.googleusercontent.com/d/1zCjSjSbCO-mbsaGoDI6g0G-bfmyVfqFV", use_container_width=True)
if p_count > 0: st.sidebar.markdown(f'<p class="blink">📢 รออนุมัติ: {p_count} รายการ</p>', unsafe_allow_html=True)

menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin (อนุมัติ)", "📊 รายงานประจำเดือน"]
choice = st.sidebar.selectbox("Menu", menu)

# --- 4. NAVIGATION LOGIC ---
if choice == "📝 จองใหม่":
    st.subheader("📊 Dashboard สรุปวันนี้")
    c1, c2, c3 = st.columns(3)
    c1.metric("รออนุมัติ", p_count)
    c2.metric("สถานะ Bot", "Active")
    c3.metric("คิวงานวันนี้", len(supabase.table("bookings").select("id").eq("status", "Approved").gte("start_time", datetime.now().date().isoformat()).execute().data))
    
    with st.container(border=True):
        col1, col2 = st.columns(2)
        cat = col1.radio("ประเภท", ["รถยนต์", "ห้องประชุม"], horizontal=True)
        res_list = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG"] if cat == "รถยนต์" else ["ห้องชั้น 1", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]
        res = col1.selectbox("เลือกรายการ", res_list)
        dest = col1.text_input("ปลายทาง", "" if cat == "รถยนต์" else "Office")
        name, phone, dept = col1.text_input("ชื่อ"), col1.text_input("โทร"), col1.text_input("แผนก")
        
        d_s, t_s = col2.date_input("วันที่เริ่ม"), col2.text_input("เวลาเริ่ม (เช่น 0800)", "0800")
        d_e, t_e = col2.date_input("วันที่จบ", d_s), col2.text_input("เวลาจบ", "1700")
        purp = col2.text_area("วัตถุประสงค์")
        
        if st.button("ยืนยันการจอง", use_container_width=True):
            try:
                ts, te = datetime.combine(d_s, datetime.strptime(fmt_t(t_s), "%H:%M").time()), datetime.combine(d_e, datetime.strptime(fmt_t(t_e), "%H:%M").time())
                conf, u_conf = check_conflict(res, ts.isoformat(), te.isoformat())
                if conf: st.error(f"❌ คิวชนกับคุณ {u_conf}")
                else:
                    item = supabase.table("bookings").insert({"resource":res, "requester":name, "phone":phone, "dept":dept, "start_time":ts.isoformat(), "end_time":te.isoformat(), "purpose":purp, "destination":dest, "status":"Pending"}).execute().data[0]
                    send_line(item['id'], res, name, dept, ts, te, purp, dest)
                    st.success("✅ จองสำเร็จ!"); st.rerun()
            except: st.error("⚠️ ข้อมูลเวลาผิด")

elif choice == "📅 ตารางงาน (Real-time)":
    f1, f2 = st.columns([2, 1])
    search = f1.text_input("🔍 ค้นหาชื่อ/สถานที่")
    v_cat = f2.selectbox("กรองประเภท", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
    
    data = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", datetime.now().isoformat()).order("start_time").execute().data
    if data:
        df = pd.DataFrame(data)
        if v_cat == "รถยนต์": df = df[df['resource'].str.contains("Civic|Camry|MG")]
        elif v_cat == "ห้องประชุม": df = df[df['resource'].str.contains("ห้อง")]
        if search: df = df[df['requester'].str.contains(search, case=False) | df['destination'].str.contains(search, case=False)]
        
        df.insert(0, 'No.', range(1, len(df) + 1))
        df['เวลาเริ่ม'] = pd.to_datetime(df['start_time']).dt.strftime('%d/%m/%Y %H:%M')
        st.dataframe(df[['No.', 'resource', 'เวลาเริ่ม', 'requester', 'destination', 'purpose']], use_container_width=True)
        
        st.markdown("---")
        with st.expander("🛠️ แก้ไข/ลบ ข้อมูล (Admin Only)"):
            sel_no = st.selectbox("เลือก No.", df['No.'].tolist())
            row = df[df['No.'] == sel_no].iloc[0]
            with st.form("edit_form"):
                e1, e2 = st.columns(2)
                n_req = e1.text_input("ชื่อผู้จอง", row['requester'])
                n_dest = e1.text_input("ปลายทาง", row.get('destination', '-'))
                # แก้ไขเวลาสิ้นสุดและวัตถุประสงค์ (เพิ่มกลับมาตามสั่งครับ)
                dt_e = pd.to_datetime(row['end_time'])
                n_d_e = e2.date_input("วันที่สิ้นสุด", dt_e.date())
                n_t_e = e2.text_input("เวลาสิ้นสุด (4 หลัก)", dt_e.strftime("%H%M"))
                n_purp = st.text_area("วัตถุประสงค์", row.get('purpose', '-'))
                pw = st.text_input("Admin Password", type="password")
                if st.form_submit_button("💾 บันทึก"):
                    if pw == "s1234":
                        fe = fmt_t(n_t_e)
                        final_e = datetime.combine(n_d_e, datetime.strptime(fe, "%H:%M").time()).isoformat()
                        supabase.table("bookings").update({"requester":n_req, "destination":n_dest, "purpose":n_purp, "end_time":final_e}).eq("id", row['id']).execute()
                        st.success("อัปเดตแล้ว!"); st.rerun()
                if st.form_submit_button("🗑️ ลบรายการ"):
                    if pw == "s1234":
                        supabase.table("bookings").delete().eq("id", row['id']).execute(); st.rerun()

elif choice == "🔑 Admin (อนุมัติ)":
    if st.text_input("Password Admin", type="password") == "s1234":
        items = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute().data
        if not items: st.info("ไม่มีรายการรออนุมัติ")
        for i in items:
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c_dt = pd.to_datetime(i['start_time'])
                with c1:
                    st.write(f"🚗 **{i['resource']}** | 👤 {i['requester']} | 📍 {i.get('destination','-')}")
                    a_d = st.date_input("วันที่", c_dt.date(), key=f"d_{i['id']}")
                    a_t = st.text_input("เวลาเริ่ม", c_dt.strftime("%H%M"), key=f"t_{i['id']}")
                if c2.button("อนุมัติ ✅", key=f"ap_{i['id']}", use_container_width=True):
                    try:
                        final_t = datetime.combine(a_d, datetime.strptime(fmt_t(a_t), "%H:%M").time()).isoformat()
                        supabase.table("bookings").update({"status":"Approved", "start_time":final_t}).eq("id", i['id']).execute()
                        send_line(i['id'], i['resource'], i['requester'], i['dept'], final_t, i['end_time'], i['purpose'], i['destination'], "Approved")
                        st.rerun()
                    except: st.error("เวลาผิด")
                if c2.button("ลบ 🗑️", key=f"dl_{i['id']}", use_container_width=True):
                    supabase.table("bookings").delete().eq("id", i['id']).execute(); st.rerun()

elif choice == "📊 รายงานประจำเดือน":
    if st.text_input("รหัสผ่านรายงาน", type="password") == "s1234":
        data = supabase.table("bookings").select("*").eq("status", "Approved").execute().data
        if data:
            df = pd.DataFrame(data)
            df['start_time'] = pd.to_datetime(df['start_time'])
            df['M-Y'] = df['start_time'].dt.strftime('%m/%Y')
            c1, c2 = st.columns(2)
            sel_m = c1.selectbox("เดือน", sorted(df['M-Y'].unique(), reverse=True))
            v_type = c2.selectbox("ประเภท", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
            f_df = df[df['M-Y'] == sel_m].copy()
            if v_type == "รถยนต์": f_df = f_df[f_df['resource'].str.contains("Civic|Camry|MG")]
            elif v_type == "ห้องประชุม": f_df = f_df[f_df['resource'].str.contains("ห้อง")]
            st.dataframe(f_df[['resource', 'requester', 'dept', 'start_time', 'destination', 'purpose']], use_container_width=True)
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as w: f_df.to_excel(w, index=False)
            st.download_button("📥 โหลด Excel", buf.getvalue(), f"Report_{sel_m}.xlsx")
