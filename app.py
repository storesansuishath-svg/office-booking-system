import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import plotly.express as px
import requests
import io

# -----------------------------
# CONFIG
# -----------------------------

SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co"
SUPABASE_KEY = "YOUR_KEY"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

CURRENT_BOT_ID = "@212djmfz"
LINE_ADD_FRIEND_URL = f"https://line.me/R/ti/p/{CURRENT_BOT_ID}"

st.set_page_config(page_title="ระบบจองรถและห้องประชุม", layout="wide")

# -----------------------------
# STYLE
# -----------------------------

st.markdown("""
<style>

.main-title {
font-size:34px;
font-weight:bold;
color:#1E88E5;
text-align:center;
}

.line-btn {
background-color:#06C755;
padding:10px;
border-radius:8px;
text-align:center;
}

.line-btn a{
color:white;
font-weight:bold;
text-decoration:none;
}

</style>
""", unsafe_allow_html=True)

# -----------------------------
# FUNCTION
# -----------------------------

def validate_time(t):

    if len(t) != 4 or not t.isdigit():
        return False

    hh = int(t[:2])
    mm = int(t[2:])

    return 0 <= hh <= 23 and 0 <= mm <= 59


def format_time(t):

    return f"{t[:2]}:{t[2:]}"


def check_conflict(resource, start, end):

    res = supabase.table("bookings").select("*")\
        .eq("resource", resource)\
        .in_("status", ["Approved","Pending"])\
        .execute()

    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end)

    for r in res.data:

        es = pd.to_datetime(r['start_time'])
        ee = pd.to_datetime(r['end_time'])

        if s < ee and e > es:
            return True

    return False


# -----------------------------
# SIDEBAR
# -----------------------------

st.sidebar.markdown(
f"""
<div class="line-btn">
<a href="{LINE_ADD_FRIEND_URL}" target="_blank">
➕ เพิ่มเพื่อน LINE
</a>
</div>
""",
unsafe_allow_html=True
)

menu = st.sidebar.selectbox(
"เมนูระบบ",
[
"Dashboard",
"จองใหม่",
"ตารางงาน",
"Admin",
"รายงาน"
]
)

# -----------------------------
# DASHBOARD
# -----------------------------

if menu == "Dashboard":

    st.markdown('<div class="main-title">Dashboard การใช้งาน</div>', unsafe_allow_html=True)

    data = supabase.table("bookings").select("*").eq("status","Approved").execute().data

    if data:

        df = pd.DataFrame(data)

        car_df = df[df['resource'].str.contains("Civic|Camry|MG", na=False)]
        room_df = df[df['resource'].str.contains("ห้อง", na=False)]

        c1,c2 = st.columns(2)

        if not car_df.empty:

            car = car_df['resource'].value_counts().reset_index()
            car.columns = ['รถ','จำนวน']

            fig = px.bar(car,x='รถ',y='จำนวน',title="การใช้รถ")

            c1.plotly_chart(fig,use_container_width=True)

        if not room_df.empty:

            room = room_df['resource'].value_counts().reset_index()
            room.columns = ['ห้อง','จำนวน']

            fig = px.bar(room,x='ห้อง',y='จำนวน',title="การใช้ห้อง")

            c2.plotly_chart(fig,use_container_width=True)

# -----------------------------
# BOOKING
# -----------------------------

if menu == "จองใหม่":

    st.markdown('<div class="main-title">จองรถ / ห้องประชุม</div>', unsafe_allow_html=True)

    col1,col2 = st.columns(2)

    with col1:

        cat = st.radio("ประเภท",["รถยนต์","ห้องประชุม"])

        if cat=="รถยนต์":
            resources=[
            "Civic (ตุ้ม)",
            "Civic (บอล)",
            "Camry (เนก)",
            "MG",
            "MG (เนก)"
            ]
        else:
            resources=[
            "ห้องชั้น 1",
            "ห้องชั้น 2",
            "ห้อง VIP",
            "ห้องชั้นลอย",
            "ห้อง Production"
            ]

        resource = st.selectbox("รายการ",resources)

        name = st.text_input("ชื่อผู้จอง")
        dept = st.text_input("แผนก")

        phone = st.text_input("เบอร์โทร")

    with col2:

        date_start = st.date_input("วันที่เริ่ม")

        t_start = st.text_input("เวลาเริ่ม เช่น 0800")

        date_end = st.date_input("วันที่สิ้นสุด")

        t_end = st.text_input("เวลาสิ้นสุด เช่น 1700")

        purpose = st.text_area("วัตถุประสงค์")

    if st.button("ส่งคำขอจอง"):

        if not validate_time(t_start) or not validate_time(t_end):

            st.error("รูปแบบเวลาไม่ถูกต้อง")

        else:

            ts = datetime.combine(
            date_start,
            datetime.strptime(format_time(t_start),"%H:%M").time()
            )

            te = datetime.combine(
            date_end,
            datetime.strptime(format_time(t_end),"%H:%M").time()
            )

            if check_conflict(resource, ts.isoformat(), te.isoformat()):

                st.error("เวลาชนกับรายการอื่น")

            else:

                supabase.table("bookings").insert({

                "resource":resource,
                "requester":name,
                "dept":dept,
                "phone":phone,
                "start_time":ts.isoformat(),
                "end_time":te.isoformat(),
                "purpose":purpose,
                "status":"Pending"

                }).execute()

                st.success("ส่งคำขอเรียบร้อย")

# -----------------------------
# ตารางงาน
# -----------------------------

if menu == "ตารางงาน":

    data = supabase.table("bookings").select("*")\
    .eq("status","Approved")\
    .order("start_time")\
    .execute().data

    if data:

        df = pd.DataFrame(data)

        df['start'] = pd.to_datetime(df['start_time']).dt.strftime('%d/%m/%Y %H:%M')

        df['end'] = pd.to_datetime(df['end_time']).dt.strftime('%d/%m/%Y %H:%M')

        show = df[['resource','start','end','requester','purpose']]

        st.dataframe(show,use_container_width=True)

# -----------------------------
# ADMIN
# -----------------------------

if menu == "Admin":

    if st.text_input("รหัสผ่าน", type="password") == "s1234":

        data = supabase.table("bookings").select("*")\
        .eq("status","Pending")\
        .execute().data

        for r in data:

            st.write(r['resource'], r['requester'])

            if st.button(f"อนุมัติ {r['id']}"):

                supabase.table("bookings").update({
                "status":"Approved"
                }).eq("id",r['id']).execute()

                st.success("อนุมัติแล้ว")

# -----------------------------
# REPORT
# -----------------------------

if menu == "รายงาน":

    data = supabase.table("bookings").select("*")\
    .eq("status","Approved")\
    .execute().data

    if data:

        df = pd.DataFrame(data)

        df['start'] = pd.to_datetime(df['start_time'])

        df['month'] = df['start'].dt.strftime('%m/%Y')

        m = st.selectbox("เดือน", df['month'].unique())

        rep = df[df['month']==m]

        st.dataframe(rep)

        buf = io.BytesIO()

        with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:

            rep.to_excel(writer,index=False)

        st.download_button(
        "ดาวน์โหลด Excel",
        buf.getvalue(),
        "report.xlsx"
        )
