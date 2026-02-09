import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime

import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta

# --- 1. ตั้งค่าการเชื่อมต่อ (เดิมของคุณ) ---
SUPABASE_URL = "..."
SUPABASE_KEY = "..."
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. ฟังก์ชันลบข้อมูลอัตโนมัติ (เพิ่มตรงนี้) ---
def auto_delete_old_bookings():
    threshold_time = (datetime.now() - timedelta(hours=24)).isoformat()
    try:
        # สั่งลบรายการที่จบงานไปแล้วเกิน 24 ชม.
        supabase.table("bookings").delete().lt("end_time", threshold_time).execute()
    except:
        pass

# เรียกใช้งานทันทีเพื่อให้แอปสะอาดตลอดเวลา
auto_delete_old_bookings()

# --- 3. ส่วนการตั้งค่าหน้าจอและเมนู (เดิมของคุณ) ---
st.set_page_config(page_title="ระบบจองรถ & ห้องประชุม", layout="wide")
# ... โค้ดที่เหลือของคุณ ...

# --- 2. ตั้งค่าหน้าจอโปรแกรม ---
st.set_page_config(page_title="ระบบจองรถ & ห้องประชุม", layout="wide")
st.title("ระบบจองรถยนต์และห้องประชุม Online")

menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin (อนุมัติ)"]
choice = st.sidebar.selectbox("เมนู", menu)

if choice == "📝 จองใหม่":
    st.subheader("รายละเอียดการจอง")
    col1, col2 = st.columns(2)
    
    with col1:
        cat = st.radio("ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"])
        if cat == "รถยนต์":
            res = st.selectbox("เลือกคัน", ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"])
            destination = st.text_input("สถานที่ปลายทาง / ปักหมุด Google Maps", placeholder="เช่น บริษัท ABC หรือ วางลิงก์แผนที่ที่นี่")
        else:
            res = st.selectbox("เลือกห้อง", ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"])
            destination = "" # ห้องประชุมไม่มีปลายทาง
        
        name = st.text_input("ชื่อผู้จอง")
        phone = st.text_input("เบอร์โทรศัพท์")
        dept = st.text_input("แผนก")

    with col2:
        t_start = st.datetime_input("เวลาเริ่ม", datetime.now())
        t_end = st.datetime_input("เวลาสิ้นสุด", datetime.now())
        reason = st.text_area("วัตถุประสงค์การใช้งาน")

    if st.button("ยืนยันการส่งคำขอจอง"):
        if not name or not phone:
            st.warning("กรุณากรอกชื่อและเบอร์โทรศัพท์")
        elif t_start >= t_end:
            st.error("เวลาเริ่มต้นต้องก่อนเวลาสิ้นสุด")
        else:
            # ตรวจสอบการจองซ้ำ (ชนกับรายการที่ Approved แล้ว)
            check_res = supabase.table("bookings").select("*")\
                .eq("resource", res)\
                .eq("status", "Approved").execute()
            
            df_check = pd.DataFrame(check_res.data)
            is_overlap = False
            
            if not df_check.empty:
                # แปลงเวลาเป็น datetime เพื่อเปรียบเทียบ
                df_check['start_time'] = pd.to_datetime(df_check['start_time'])
                df_check['end_time'] = pd.to_datetime(df_check['end_time'])
                
                # เงื่อนไขการทับซ้อน
                overlap = df_check[~((df_check['start_time'] >= pd.to_datetime(t_end)) | 
                                     (df_check['end_time'] <= pd.to_datetime(t_start)))]
                if not overlap.empty:
                    is_overlap = True

            if is_overlap:
                st.error(f"❌ ไม่ว่าง: {res} ถูกจองไปแล้วในช่วงเวลานี้")
            else:
                data = {
                    "resource": res, "requester": name, "phone": phone, 
                    "dept": dept, "start_time": t_start.isoformat(), 
                    "end_time": t_end.isoformat(), "purpose": reason, 
                    "destination": destination, "status": "Pending"
                }
                supabase.table("bookings").insert(data).execute()
                st.success("✅ ส่งคำขอแล้ว! กรุณารอ Admin อนุมัติ")
                # ส่วนส่ง LINE Notify/Bot สามารถเพิ่มต่อตรงนี้ได้ครับ

elif choice == "🔑 Admin (อนุมัติ)":
    st.subheader("ระบบจัดการสำหรับ Admin")
    admin_pw = st.text_input("รหัสผ่าน Admin", type="password")
    
    if admin_pw == "1234":
        res = supabase.table("bookings").select("*").eq("status", "Pending").execute()
        df_pending = pd.DataFrame(res.data)
        
        if df_pending.empty:
            st.write("ไม่มีรายการรออนุมัติ")
        else:
            st.write("รายการรอการตัดสินใจ:")
            st.dataframe(df_pending[['id', 'resource', 'requester', 'dept', 'start_time', 'end_time']], use_container_width=True)
            
            target_id = st.number_input("ใส่ ID ที่ต้องการจัดการ", step=1, min_value=1)
            col_a, col_b = st.columns(2)
            
            if col_a.button("✅ อนุมัติการจอง"):
                supabase.table("bookings").update({"status": "Approved"}).eq("id", target_id).execute()
                st.success(f"อนุมัติ ID {target_id} เรียบร้อย")
                st.rerun()
            if col_b.button("❌ ปฏิเสธการจอง"):
                supabase.table("bookings").update({"status": "Rejected"}).eq("id", target_id).execute()
                st.warning(f"ปฏิเสธ ID {target_id} แล้ว")
                st.rerun()

elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("ตารางที่ได้รับการอนุมัติแล้ว")
    now = datetime.now().isoformat()
    
    # ดึงข้อมูลจาก Supabase
    res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now).execute()
    df = pd.DataFrame(res.data)
    
    if df.empty:
        st.info("ขณะนี้ไม่มีทรัพยากรที่ถูกใช้งานอยู่")
    else:
        # 1. เลือกคอลัมน์ที่ต้องการโชว์ (เพิ่ม purpose เข้าไปตามที่คุณต้องการ)
        df_display = df[['resource', 'requester', 'dept', 'start_time', 'end_time', 'purpose', 'destination']]
        
        # 2. เปลี่ยนชื่อหัวตารางให้เป็น 2 ภาษา อังกฤษ/ไทย
        df_display.columns = [
            'Resource / รายการ', 
            'Name / ผู้จอง', 
            'Dept / แผนก', 
            'Start / เริ่ม', 
            'End / สิ้นสุด', 
            'Purpose / วัตถุประสงค์', 
            'Destination / ปลายทาง'
        ]
        
        # แสดงผลตารางแบบเต็มความกว้างหน้าจอ
        st.dataframe(df_display, use_container_width=True)
