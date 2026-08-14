import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from supabase import create_client
from supabase.client import ClientOptions
from datetime import datetime, timedelta
from pathlib import Path
import requests
import time
import io
import difflib
import calendar as calendar_module
import html
import re
import os
from zoneinfo import ZoneInfo

# ==========================================
# 1. การเชื่อมต่อ DATABASE (Supabase คงเดิม 100%)
# ==========================================
def get_runtime_setting(name, default=None, required=False):
    """Read a deployment setting from Streamlit Secrets or a local environment."""
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    value = value or os.getenv(name) or default
    if required and not value:
        raise RuntimeError(
            f"Missing {name}. Configure it in Streamlit Secrets before starting the web app."
        )
    return value


SUPABASE_URL = get_runtime_setting(
    "SUPABASE_URL", "https://qejqynbxdflwebzzwfzu.supabase.co"
)
SUPABASE_KEY = get_runtime_setting("SUPABASE_KEY", required=True)
LINE_SERVICE_URL = get_runtime_setting("LINE_SERVICE_URL", required=True).rstrip("/")
INTERNAL_API_TOKEN = get_runtime_setting("INTERNAL_API_TOKEN", required=True)

# Booking start/end times in the legacy database are wall-clock Thailand times.
# Keep that convention when reading existing bookings, while audit timestamps
# are true timezone-aware instants and are always displayed in Asia/Bangkok.
THAILAND_TZ = ZoneInfo("Asia/Bangkok")


def thai_wall_now():
    return datetime.now(THAILAND_TZ).replace(tzinfo=None)


def booking_wall_datetime(value):
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    if getattr(parsed, "tzinfo", None) is not None:
        parsed = parsed.tz_localize(None)
    return parsed.to_pydatetime()


def format_thai_audit_datetime(value):
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return "-"
    return parsed.tz_convert(THAILAND_TZ).strftime("%d/%m/%Y %H:%M")

# ==========================================
# 2. การตั้งค่าระบบ (แก้ไขรายชื่อได้ที่นี่โดยตรง)
# ==========================================
APP_DIR = Path(__file__).resolve().parent
COMPANY_LOGO_PATH = APP_DIR / "assets" / "sansuisha-logo.png"
APP_LOGO_PATH = APP_DIR / "assets" / "book-smarter-plus-logo.png"
APP_ICON_PATH = APP_DIR / "assets" / "book-smarter-plus-favicon.png"

CURRENT_BOT_ID = "@119xqhqx"
APP_VERSION = "1.0.7"
LINE_ADD_FRIEND_URL = f"https://line.me/R/ti/p/{CURRENT_BOT_ID}"

# 🚗 ตั้งค่ารายชื่อรถยนต์ (ใช้ในการจองและประเมิน)
SYS_CARS = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG", "MG (เนก)"]

# รถชื่อแตกต่างกันแต่เป็นรถคันเดียวกัน ต้องใช้คิวร่วมกัน
RESOURCE_CONFLICT_GROUPS = {
    "MG": ["MG", "MG (เนก)"],
    "MG (เนก)": ["MG", "MG (เนก)"],
}

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
st.set_page_config(
    page_title="Book Smarter Plus+ | ระบบจองรถและห้องประชุม",
    page_icon=str(APP_ICON_PATH),
    layout="wide",
)

# ใช้ Client เดียวร่วมกันตลอดอายุของ Streamlit process เพื่อลดการเปิด
# connection pool ใหม่ทุกครั้งที่ผู้ใช้เปลี่ยนเมนูหรือกดปุ่มจนเกิด rerun
@st.cache_resource(show_spinner=False)
def get_supabase_client():
    return create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=ClientOptions(
            postgrest_client_timeout=10,
            storage_client_timeout=10,
            function_client_timeout=10,
            schema="public",
        ),
    )

supabase = get_supabase_client()

# Streamlit ตั้ง favicon ได้โดยตรง แต่ไอคอนติดตั้งบนหน้าจอหลักของ Android/iOS
# ต้องมี Web App Manifest และ apple-touch-icon ใน <head> เพิ่มเติม
components.html(
    """
    <script>
    (() => {
        const doc = window.parent.document;
        const version = "20260804-v1.0.1";
        const staticRoot = `${doc.location.origin}/app/static/`;

        const upsertLink = (id, rel, href, sizes = "") => {
            let link = doc.head.querySelector(`#${id}`);
            if (!link) {
                link = doc.createElement("link");
                link.id = id;
                doc.head.appendChild(link);
            }
            link.rel = rel;
            link.href = `${staticRoot}${href}?v=${version}`;
            if (sizes) {
                link.sizes = sizes;
            }
        };

        const upsertMeta = (name, content) => {
            let meta = doc.head.querySelector(`meta[name="${name}"]`);
            if (!meta) {
                meta = doc.createElement("meta");
                meta.name = name;
                doc.head.appendChild(meta);
            }
            meta.content = content;
        };

        upsertLink(
            "book-smarter-manifest",
            "manifest",
            "manifest.json"
        );
        upsertLink(
            "book-smarter-apple-touch-icon-152",
            "apple-touch-icon",
            "apple-touch-icon-152.png",
            "152x152"
        );
        upsertLink(
            "book-smarter-apple-touch-icon-167",
            "apple-touch-icon",
            "apple-touch-icon-167.png",
            "167x167"
        );
        upsertLink(
            "book-smarter-apple-touch-icon-180",
            "apple-touch-icon",
            "apple-touch-icon.png",
            "180x180"
        );
        upsertLink(
            "book-smarter-browser-icon",
            "icon",
            "favicon-64.png",
            "64x64"
        );

        upsertMeta("theme-color", "#168BD2");
        upsertMeta("msapplication-TileColor", "#168BD2");
        upsertMeta("application-name", "Book Smarter Plus+");
        upsertMeta("mobile-web-app-capable", "yes");
        upsertMeta("apple-mobile-web-app-capable", "yes");
        upsertMeta("apple-mobile-web-app-title", "Book Smarter Plus+");
        upsertMeta("apple-mobile-web-app-status-bar-style", "default");
    })();
    </script>
    """,
    height=0,
    width=0,
)

st.markdown("""
    <style>
    :root {
        --brand-blue: #168BD2;
        --brand-blue-dark: #0866A6;
        --brand-green: #62C96B;
        --brand-ink: #17324D;
    }

    .stApp {
        background:
            radial-gradient(circle at 8% 5%, rgba(98, 201, 107, 0.16), transparent 28%),
            radial-gradient(circle at 92% 12%, rgba(22, 139, 210, 0.16), transparent 30%),
            linear-gradient(145deg, #F8FCFF 0%, #F4FBF7 52%, #F7FAFF 100%);
        background-attachment: fixed;
    }

    [data-testid="stHeader"] {
        background: rgba(248, 252, 255, 0.78);
        backdrop-filter: blur(10px);
    }

    [data-testid="stMainBlockContainer"] {
        max-width: 1420px;
        padding-top: 1.25rem;
        padding-bottom: 4rem;
    }

    /* Surface system: visual-only cards for forms, metrics and tables. */
    [data-testid="stForm"] {
        padding: clamp(1rem, 2vw, 1.5rem);
        border: 1px solid rgba(22, 139, 210, 0.14) !important;
        border-radius: 18px !important;
        background: rgba(255, 255, 255, 0.88);
        box-shadow: 0 12px 30px rgba(24, 73, 105, 0.08);
    }

    [data-testid="stMetric"] {
        min-height: 108px;
        padding: 1rem 1.1rem;
        border: 1px solid rgba(22, 139, 210, 0.14);
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.9);
        box-shadow: 0 8px 22px rgba(24, 73, 105, 0.07);
    }

    [data-testid="stDataFrame"], [data-testid="stTable"] {
        overflow: hidden;
        border: 1px solid rgba(22, 139, 210, 0.14);
        border-radius: 14px;
        background: #FFFFFF;
        box-shadow: 0 8px 22px rgba(24, 73, 105, 0.06);
    }

    [data-testid="stButton"] button,
    [data-testid="stFormSubmitButton"] button {
        min-height: 44px;
        border-radius: 11px;
        font-weight: 700;
    }

    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stDateInput"] input,
    [data-testid="stSelectbox"] > div > div {
        border-radius: 10px !important;
    }

    section[data-testid="stSidebar"] {
        min-width: 270px;
        max-width: 270px;
        background: linear-gradient(180deg, #0A315B 0%, #08294D 55%, #061F3C 100%);
        border-right: 1px solid rgba(118, 187, 236, 0.22);
        box-shadow: 8px 0 28px rgba(5, 31, 58, 0.13);
    }

    section[data-testid="stSidebar"] > div {
        width: 270px;
    }

    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding-top: 0.7rem;
    }

    section[data-testid="stSidebar"] [data-testid="stImage"] {
        padding: 0.55rem;
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.97);
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.12);
    }

    section[data-testid="stSidebar"] hr {
        border-color: rgba(203, 226, 244, 0.18);
    }

    /* ปุ่มยุบ/เปิด Sidebar ให้เห็นชัดทั้ง PC และมือถือ */
[data-testid="stSidebarHeader"] button,
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stExpandSidebarButton"] button,
[data-testid="stExpandSidebarButton"],
button[aria-label*="sidebar" i] {
        width: 48px !important;
        min-width: 48px !important;
        height: 48px !important;
        min-height: 48px !important;
        padding: 0 !important;
        border: 2px solid #4DB8F3 !important;
        border-radius: 12px !important;
        background: #071D36 !important;
        color: #FFFFFF !important;
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.28) !important;
        opacity: 1 !important;
    }

[data-testid="stSidebarHeader"] button:hover,
[data-testid="stSidebarCollapseButton"] button:hover,
[data-testid="stExpandSidebarButton"] button:hover,
[data-testid="stExpandSidebarButton"]:hover,
button[aria-label*="sidebar" i]:hover {
        border-color: #8AD8FF !important;
        background: #0D3B68 !important;
        transform: scale(1.05);
    }

[data-testid="stSidebarHeader"] button span,
[data-testid="stSidebarCollapseButton"] button span,
[data-testid="stExpandSidebarButton"] button span,
[data-testid="stExpandSidebarButton"] span,
button[aria-label*="sidebar" i] span {
        color: #FFFFFF !important;
        font-size: 1.65rem !important;
        font-weight: 900 !important;
        line-height: 1 !important;
    }

    .sidebar-brand-divider {
        height: 1px;
        margin: 0.15rem 0.75rem 0.65rem;
        background: linear-gradient(
            90deg,
            transparent,
            rgba(22, 139, 210, 0.28),
            rgba(98, 201, 107, 0.28),
            transparent
        );
    }

    @keyframes blinker { 50% { opacity: 0; } }
    .blink { animation: blinker 1s linear infinite; color: #FF0000; font-weight: bold; font-size: 18px; }
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        background-color: #E3F2FD !important; color: #0D47A1 !important; border: 1px solid #BBDEFB !important;
    }
    .main-title {
        font-size: clamp(28px, 3vw, 38px);
        font-weight: 800;
        color: var(--brand-blue-dark);
        text-align: center;
        margin: 0.35rem 0 1.5rem;
        letter-spacing: -0.02em;
        text-shadow: 0 2px 12px rgba(22, 139, 210, 0.12);
    }

    /* เมนูหลักแนวตั้งใน Sidebar: ใช้ radio เดิมเพื่อคง choice และลอจิกทุกหน้า */
    section[data-testid="stSidebar"] div[data-testid="stRadio"]:has(div[role="radiogroup"][aria-label="เมนูหลัก"]) {
        margin: 0.25rem 0 0.65rem;
        padding: 0.45rem;
        border: 1px solid rgba(157, 205, 239, 0.12);
        border-radius: 16px;
        background: rgba(3, 25, 48, 0.24);
    }

    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="เมนูหลัก"] {
        display: flex !important;
        flex-direction: column;
        gap: 0.32rem;
        width: 100%;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="เมนูหลัก"] > label {
        position: relative;
        display: flex !important;
        align-items: center;
        justify-content: flex-start;
        min-height: 46px;
        margin: 0 !important;
        padding: 0.68rem 0.72rem !important;
        border: 1px solid transparent;
        border-radius: 11px;
        background: transparent;
        cursor: pointer;
        transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease, background 0.18s ease;
    }

    /* Streamlit รุ่นที่ใช้ BaseWeb (localhost) */
    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="เมนูหลัก"] > label[data-baseweb="radio"] > div:first-child {
        position: absolute;
        opacity: 0;
        pointer-events: none;
    }

    /* Streamlit Cloud รุ่นที่ใช้ React Aria */
    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="เมนูหลัก"] > label[data-testid="stRadioOption"] > div:last-child > div:first-child > div:first-child {
        display: none !important;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="เมนูหลัก"] > label > div:last-child,
    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="เมนูหลัก"] > label [data-testid="stMarkdownContainer"] {
        width: 100%;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="เมนูหลัก"] > label p {
        margin: 0;
        color: #DCEBFA !important;
        font-size: 0.9rem;
        font-weight: 650;
        line-height: 1.25;
        text-align: left;
        white-space: nowrap;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="เมนูหลัก"] > label:hover {
        transform: translateX(3px);
        border-color: rgba(118, 187, 236, 0.24);
        background: rgba(64, 139, 201, 0.16);
    }

    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="เมนูหลัก"] > label:has(input:checked),
    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="เมนูหลัก"] > label[data-selected="true"] {
        border-color: rgba(112, 198, 255, 0.35);
        border-left: 4px solid #61C9FF;
        background: linear-gradient(100deg, rgba(29, 102, 173, 0.95), rgba(27, 89, 151, 0.82));
        box-shadow: 0 8px 18px rgba(0, 0, 0, 0.16);
        transform: none;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="เมนูหลัก"] > label:has(input:checked) p,
    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="เมนูหลัก"] > label[data-selected="true"] p {
        color: #FFFFFF !important;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.16);
    }

    section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="เมนูหลัก"] > label:has(input:focus-visible) {
        outline: 3px solid rgba(97, 201, 255, 0.34);
        outline-offset: 2px;
    }

    @media (max-width: 640px) {
        [data-testid="stMainBlockContainer"] {
            padding-left: 0.65rem;
            padding-right: 0.65rem;
            padding-top: 0.55rem;
            padding-bottom: 2.5rem;
        }

        section[data-testid="stSidebar"] {
            min-width: min(86vw, 300px);
            max-width: min(86vw, 300px);
        }

        section[data-testid="stSidebar"] > div {
            width: min(86vw, 300px);
        }

    [data-testid="stSidebarHeader"] button,
    [data-testid="stSidebarCollapseButton"] button,
    [data-testid="stExpandSidebarButton"] button,
    [data-testid="stExpandSidebarButton"],
    button[aria-label*="sidebar" i] {
            width: 52px !important;
            min-width: 52px !important;
            height: 52px !important;
            min-height: 52px !important;
            border-radius: 13px !important;
        }

        section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="เมนูหลัก"] > label {
            min-height: 48px;
            padding: 0.72rem 0.75rem !important;
        }

        section[data-testid="stSidebar"] div[role="radiogroup"][aria-label="เมนูหลัก"] > label p {
            font-size: 0.92rem;
        }

        .main-title {
            font-size: clamp(1.55rem, 7vw, 1.9rem);
            line-height: 1.25;
            margin-bottom: 1rem;
        }

        [data-testid="stForm"] {
            padding: 0.85rem;
            border-radius: 14px !important;
        }

        [data-testid="stMetric"] {
            min-height: 88px;
            padding: 0.75rem 0.65rem;
        }

        [data-testid="stMetricLabel"] {
            font-size: 0.78rem;
        }

        [data-testid="stDataFrame"], [data-testid="stTable"] {
            border-radius: 10px;
            overflow-x: auto;
        }

        [data-testid="stButton"] button,
        [data-testid="stFormSubmitButton"] button,
        [data-testid="stLinkButton"] a {
            width: 100%;
            min-height: 46px;
        }
    }
    
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

def get_conflict_resources(resource):
    resource_name = str(resource).strip()
    return RESOURCE_CONFLICT_GROUPS.get(resource_name, [resource_name])

def check_booking_conflict(resource, start_time_iso, end_time_iso, exclude_booking_id=None):
    conflict_resources = get_conflict_resources(resource)
    res = supabase.table("bookings").select("*").in_("resource", conflict_resources).in_("status", ["Approved", "Pending"]).execute()
    new_s = datetime.fromisoformat(start_time_iso).replace(tzinfo=None)
    new_e = datetime.fromisoformat(end_time_iso).replace(tzinfo=None)
    for item in res.data:
        if exclude_booking_id is not None and str(item.get('id')) == str(exclude_booking_id):
            continue
        ex_s = pd.to_datetime(item['start_time']).replace(tzinfo=None)
        ex_e = pd.to_datetime(item['end_time']).replace(tzinfo=None)
        if new_s < ex_e and new_e > ex_s:
            return True, item['requester'], item['status'], bool(item.get('is_executive_booking', False))
    return False, None, None, False

def get_unrated_bookings(name, dept):
    # ยาแรง: ล็อกทั้งแผนก หากมีใครคนใดคนหนึ่งในแผนกนี้ค้างประเมิน จะไม่ให้คนในแผนกนี้จองรถใหม่เด็ดขาด
    try:
        now_iso = thai_wall_now().isoformat()
        res = supabase.table("bookings").select("*").eq("dept", dept).eq("status", "Approved").in_("resource", SYS_CARS).lt("end_time", now_iso).gte("end_time", "2026-07-01T00:00:00").execute()
        
        matched_unrated = []
        for d in res.data:
            if not d.get("is_rated"):
                matched_unrated.append(d)
        return matched_unrated
    except:
        return []
    
def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination, status_text="Pending"):
    render_url = f"{LINE_SERVICE_URL}/notify"
    try:
        s_dt = pd.to_datetime(t_start)
        s_str = s_dt.strftime("%d/%m/%Y %H:%M")
        e_str = t_end if isinstance(t_end, str) else pd.to_datetime(t_end).strftime("%H:%M")
        payload = {
            "id": booking_id,
            "resource": resource, "name": name, "dept": dept, "date": s_str, "end_date": e_str, 
            "purpose": purpose, "destination": destination, "status": status_text
        }
        response = requests.post(
            render_url,
            json=payload,
            headers={"X-Internal-Token": INTERNAL_API_TOKEN},
            timeout=30,
        )
        response.raise_for_status()
        return True
    except Exception as exc:
        # Booking data is already stored in Supabase. Do not fail the booking page
        # merely because a notification service is temporarily unavailable.
        print(f"LINE notification failed: {exc}")
        return False

@st.cache_data(ttl=86400, show_spinner=False)
def auto_delete_old_bookings():
    """Delete completed/stale booking rows older than 45 days, once per day."""
    threshold = (thai_wall_now() - timedelta(days=45)).isoformat()
    try:
        # ไม่รับข้อมูลทุกคอลัมน์ของแถวที่ลบกลับมายัง Streamlit Cloud
        # ช่วยลดทั้งหน่วยความจำและปริมาณข้อมูล โดยยังลบ 45 วันเหมือนเดิม
        supabase.table("bookings").delete(returning="minimal").lt("end_time", threshold).execute()
        return {"ok": True, "threshold": threshold}
    except Exception as exc:
        # Keep the web available, but make the failure visible in Render/
        # Streamlit logs instead of silently disabling data retention.
        print(f"[retention] 45-day cleanup failed: {exc}")
        return {"ok": False, "threshold": threshold}

def _to_calendar_datetime(value):
    """Use the exact wall-clock value stored by the existing application.

    The original pages display Supabase timestamps without timezone conversion.
    The calendar must use the same rule; otherwise an ISO value ending in +00:00
    would be shifted by seven hours only on the new calendar page.
    """
    dt = pd.to_datetime(value)
    if getattr(dt, "tzinfo", None) is not None:
        dt = dt.tz_localize(None)
    return dt.to_pydatetime()

def _short_resource_name(resource):
    return resource.replace("ห้อง", "ห.").replace("ชั้น", "ช.")

def get_calendar_resources(calendar_type):
    """Read the active resource list from the database, with safe fallback.

    This keeps the calendar's denominator in sync when an admin changes the
    car_list or room_list in app_settings, instead of relying on old constants.
    """
    field = "car_list" if calendar_type == "รถยนต์" else "room_list"
    fallback = SYS_CARS if calendar_type == "รถยนต์" else SYS_ROOMS
    try:
        settings = supabase.table("app_settings").select(field).eq("id", 1).execute().data
        raw_list = settings[0].get(field, "") if settings else ""
        resources = [item.strip() for item in raw_list.split(",") if item.strip()]
        return resources or fallback
    except Exception:
        return fallback


THAI_DIGIT_TRANSLATION = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
THAI_MONTH_ALIASES = {
    "มกราคม": 1, "ม.ค.": 1, "ม.ค": 1,
    "กุมภาพันธ์": 2, "ก.พ.": 2, "ก.พ": 2,
    "มีนาคม": 3, "มี.ค.": 3, "มี.ค": 3,
    "เมษายน": 4, "เม.ย.": 4, "เม.ย": 4,
    "พฤษภาคม": 5, "พ.ค.": 5, "พ.ค": 5,
    "มิถุนายน": 6, "มิ.ย.": 6, "มิ.ย": 6,
    "กรกฎาคม": 7, "ก.ค.": 7, "ก.ค": 7,
    "สิงหาคม": 8, "ส.ค.": 8, "ส.ค": 8,
    "กันยายน": 9, "ก.ย.": 9, "ก.ย": 9,
    "ตุลาคม": 10, "ต.ค.": 10, "ต.ค": 10,
    "พฤศจิกายน": 11, "พ.ย.": 11, "พ.ย": 11,
    "ธันวาคม": 12, "ธ.ค.": 12, "ธ.ค": 12,
}
RESOURCE_SEARCH_ALIASES = {
    "Civic (ตุ้ม)": ["civic (ตุ้ม)", "civic ตุ้ม", "ซีวิค ตุ้ม", "ตุ้ม"],
    "Civic (บอล)": ["civic (บอล)", "civic บอล", "ซีวิค บอล", "บอล"],
    "Camry (เนก)": ["camry (เนก)", "camry เนก", "แคมรี่ เนก", "คัมรี่ เนก", "camry"],
    "MG (เนก)": ["mg (เนก)", "mg เนก", "เอ็มจี เนก"],
    "MG": ["mg", "เอ็มจี", "mg-ep"],
    "ห้องชั้น 1 (ห้องใหญ่)": ["ห้องชั้น 1", "ห้องใหญ่", "ชั้นหนึ่ง"],
    "ห้องชั้น 2": ["ห้องชั้น 2", "ชั้นสอง"],
    "ห้อง VIP": ["ห้อง vip", "vip"],
    "ห้องชั้นลอย": ["ห้องชั้นลอย", "ชั้นลอย"],
    "ห้อง Production": ["ห้อง production", "production"],
}


def _normalize_search_text(value):
    return re.sub(r"\s+", " ", str(value).translate(THAI_DIGIT_TRANSLATION).strip().lower())


def _normalize_search_year(raw_year, current_year):
    if raw_year is None:
        return current_year
    year = int(raw_year)
    if year >= 2400:
        return year - 543
    if year < 100:
        # คนไทยมักใช้ 69 แทน พ.ศ. 2569 แต่ใช้ 26 แทน ค.ศ. 2026 ได้เช่นกัน
        return 1957 + year if year >= 50 else 2000 + year
    return year


def _parse_search_date_range(text, today):
    if "มะรืน" in text:
        target = today + timedelta(days=2)
        return target, target, None
    if "พรุ่งนี้" in text:
        target = today + timedelta(days=1)
        return target, target, None
    if "วันนี้" in text:
        return today, today, None

    numeric = re.search(r"(?<!\d)(\d{1,2})\s*[/-]\s*(\d{1,2})(?:\s*[/-]\s*(\d{2,4}))?(?!\d)", text)
    if numeric:
        try:
            target = datetime(
                _normalize_search_year(numeric.group(3), today.year),
                int(numeric.group(2)),
                int(numeric.group(1)),
            ).date()
            return target, target, None
        except ValueError:
            return None, None, "วันที่ที่ระบุไม่ถูกต้อง"

    for alias, month in sorted(THAI_MONTH_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        match = re.search(rf"(?<!\d)(\d{{1,2}})\s*{re.escape(alias)}(?:\s*(\d{{2,4}}))?", text)
        if match:
            try:
                target = datetime(
                    _normalize_search_year(match.group(2), today.year), month, int(match.group(1))
                ).date()
                return target, target, None
            except ValueError:
                return None, None, "วันที่ที่ระบุไม่ถูกต้อง"

    if "สัปดาห์หน้า" in text or "อาทิตย์หน้า" in text:
        next_monday = today + timedelta(days=7 - today.weekday())
        return next_monday, next_monday + timedelta(days=6), None
    if "สัปดาห์นี้" in text or "อาทิตย์นี้" in text:
        return today, today + timedelta(days=6 - today.weekday()), None
    if "เดือนหน้า" in text:
        first_this_month = today.replace(day=1)
        first_next_month = (first_this_month.replace(day=28) + timedelta(days=4)).replace(day=1)
        first_after = (first_next_month.replace(day=28) + timedelta(days=4)).replace(day=1)
        return first_next_month, first_after - timedelta(days=1), None
    if "เดือนนี้" in text:
        first_after = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        return today, first_after - timedelta(days=1), None
    if "7 วัน" in text or "เจ็ดวัน" in text:
        return today, today + timedelta(days=6), None
    return None, None, "กรุณาระบุวันที่ เช่น 25/07, พรุ่งนี้, สัปดาห์หน้า หรือเดือนหน้า"


def _parse_clock_pair(text):
    separator = r"(?:-|–|—|ถึง)"
    clock_match = re.search(
        rf"(?<!\d)(\d{{1,2}})(?:[:.](\d{{2}}))?\s*(?:น\.?|โมง)?\s*{separator}\s*"
        rf"(\d{{1,2}})(?:[:.](\d{{2}}))?\s*(?:น\.?|โมง)?(?!\d)", text
    )
    if clock_match:
        values = (
            int(clock_match.group(1)), int(clock_match.group(2) or 0),
            int(clock_match.group(3)), int(clock_match.group(4) or 0),
        )
    else:
        compact_match = re.search(rf"(?<!\d)(\d{{3,4}})\s*{separator}\s*(\d{{3,4}})(?!\d)", text)
        if not compact_match:
            return None
        raw_start, raw_end = compact_match.groups()
        raw_start, raw_end = raw_start.zfill(4), raw_end.zfill(4)
        values = (int(raw_start[:2]), int(raw_start[2:]), int(raw_end[:2]), int(raw_end[2:]))

    start_hour, start_minute, end_hour, end_minute = values
    if start_hour > 23 or end_hour > 23 or start_minute > 59 or end_minute > 59:
        return "invalid"
    return datetime.strptime(f"{start_hour:02d}:{start_minute:02d}", "%H:%M").time(), \
        datetime.strptime(f"{end_hour:02d}:{end_minute:02d}", "%H:%M").time()


def _find_requested_resource(text):
    matches = []
    for resource, aliases in RESOURCE_SEARCH_ALIASES.items():
        if any(alias.lower() in text for alias in sorted(aliases, key=len, reverse=True)):
            matches.append(resource)
    # "MG (เนก)" มีคำว่า MG อยู่ด้วย ให้ใช้ชื่อที่เจาะจงกว่าเพียงรายการเดียว
    if "MG (เนก)" in matches and "MG" in matches:
        matches.remove("MG")
    return matches


def parse_availability_query(query, now=None):
    """Convert common Thai availability questions into validated search criteria."""
    text = _normalize_search_text(query)
    if not text:
        return None, "กรุณาพิมพ์คำถามที่ต้องการค้นหา"
    today = (now or thai_wall_now()).date()
    date_start, date_end, date_error = _parse_search_date_range(text, today)
    if date_error:
        return None, date_error
    if date_end < today:
        return None, "ระบบผู้ช่วยค้นหาสำหรับการจองล่วงหน้า กรุณาระบุวันที่ตั้งแต่วันนี้เป็นต้นไป"

    parsed_times = _parse_clock_pair(text)
    used_default_time = False
    if parsed_times == "invalid":
        return None, "รูปแบบเวลาไม่ถูกต้อง กรุณาใช้ เช่น 09:00-12:00 หรือ 0900-1200"
    if parsed_times:
        start_clock, end_clock = parsed_times
    elif "ช่วงเช้า" in text or "ตอนเช้า" in text:
        start_clock, end_clock = datetime.strptime("08:00", "%H:%M").time(), datetime.strptime("12:00", "%H:%M").time()
    elif "ช่วงบ่าย" in text or "ตอนบ่าย" in text:
        start_clock, end_clock = datetime.strptime("13:00", "%H:%M").time(), datetime.strptime("17:00", "%H:%M").time()
    else:
        start_clock, end_clock = datetime.strptime("08:00", "%H:%M").time(), datetime.strptime("17:00", "%H:%M").time()
        used_default_time = True
    if datetime.combine(today, start_clock) >= datetime.combine(today, end_clock):
        return None, "เวลาเริ่มต้องมาก่อนเวลาสิ้นสุด"

    requested_resources = _find_requested_resource(text)
    category = "ห้องประชุม" if ("ห้อง" in text or any(r in SYS_ROOMS for r in requested_resources)) else "รถยนต์"
    requested_resources = [
        resource for resource in requested_resources
        if resource in (SYS_ROOMS if category == "ห้องประชุม" else SYS_CARS)
    ]
    return {
        "query": str(query).strip(), "category": category,
        "date_start": date_start, "date_end": date_end,
        "start_clock": start_clock, "end_clock": end_clock,
        "requested_resources": requested_resources,
        "used_default_time": used_default_time,
    }, None


def _build_resource_units(resources, requested_resources=None):
    units, seen = [], set()
    requested_resources = requested_resources or []
    for resource in resources:
        members = tuple(dict.fromkeys(get_conflict_resources(resource)))
        group_key = frozenset(members)
        if group_key in seen:
            continue
        seen.add(group_key)
        if requested_resources and not any(item in members for item in requested_resources):
            continue
        booking_resource = next((item for item in requested_resources if item in members), resource)
        label = " / ".join(members)
        if len(members) > 1:
            label += " (รถคันเดียวกัน)"
        units.append({"label": label, "members": members, "booking_resource": booking_resource})
    return units


def _merge_busy_intervals(rows, members, day, window_start=None, window_end=None):
    day_start = datetime.combine(day, window_start or datetime.min.time())
    day_end = datetime.combine(day, window_end or datetime.max.time())
    intervals = []
    for row in rows:
        if row.get("resource") not in members:
            continue
        row_start = _to_calendar_datetime(row.get("start_time"))
        row_end = _to_calendar_datetime(row.get("end_time"))
        start, end = max(row_start, day_start), min(row_end, day_end)
        if start < end:
            intervals.append((start, end, row.get("status", "Approved")))
    intervals.sort(key=lambda item: item[0])
    return intervals


def _format_free_slots(rows, members, day):
    work_start = datetime.combine(day, datetime.strptime("08:00", "%H:%M").time())
    work_end = datetime.combine(day, datetime.strptime("17:00", "%H:%M").time())
    intervals = _merge_busy_intervals(rows, members, day, work_start.time(), work_end.time())
    merged = []
    for start, end, _ in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    cursor, slots = work_start, []
    for start, end in merged:
        if cursor < start:
            slots.append(f"{cursor:%H:%M}-{start:%H:%M}")
        cursor = max(cursor, end)
    if cursor < work_end:
        slots.append(f"{cursor:%H:%M}-{work_end:%H:%M}")
    return slots


def search_resource_availability(criteria):
    """Read only bookings overlapping the requested range and calculate availability locally."""
    resources = get_calendar_resources(criteria["category"])
    units = _build_resource_units(resources, criteria["requested_resources"])
    if not units:
        return None, "ไม่พบรถหรือห้องที่ระบุในรายการทรัพยากรปัจจุบัน"

    database_resources = sorted({member for unit in units for member in unit["members"]})
    query_start = datetime.combine(criteria["date_start"], criteria["start_clock"])
    query_end = datetime.combine(criteria["date_end"], criteria["end_clock"])
    try:
        response = supabase.table("bookings").select(
            "resource,start_time,end_time,status"
        ).in_("resource", database_resources).in_(
            "status", ["Approved", "Pending"]
        ).lt("start_time", query_end.isoformat()).gt(
            "end_time", query_start.isoformat()
        ).execute()
        rows = response.data or []
    except Exception as exc:
        return None, f"ไม่สามารถตรวจสอบฐานข้อมูลได้: {exc}"

    days = []
    day = criteria["date_start"]
    while day <= criteria["date_end"]:
        desired_start = datetime.combine(day, criteria["start_clock"])
        desired_end = datetime.combine(day, criteria["end_clock"])
        free_units, busy_units = [], []
        for unit in units:
            conflicts = _merge_busy_intervals(
                rows, unit["members"], day, criteria["start_clock"], criteria["end_clock"]
            )
            if conflicts:
                busy_units.append({
                    **unit,
                    "conflicts": [
                        {
                            "time": f"{start:%H:%M}-{end:%H:%M}",
                            "status": "อนุมัติแล้ว" if status == "Approved" else "รออนุมัติ",
                        }
                        for start, end, status in conflicts
                    ],
                    "free_slots": _format_free_slots(rows, unit["members"], day),
                })
            else:
                free_units.append(unit)
        days.append({
            "date": day, "desired_start": desired_start, "desired_end": desired_end,
            "free": free_units, "busy": busy_units,
        })
        day += timedelta(days=1)
    return {"criteria": criteria, "days": days}, None


def _set_smart_search_example(example):
    st.session_state["smart_search_query"] = example


def _apply_availability_to_booking(option):
    st.session_state["booking_category"] = option["category"]
    st.session_state["booking_resource"] = option["resource"]
    st.session_state["booking_start_date"] = option["date"]
    st.session_state["booking_end_date"] = option["date"]
    st.session_state["booking_start_time"] = option["start"]
    st.session_state["booking_end_time"] = option["end"]
    st.session_state["top_nav"] = "📝 จองใหม่"


def render_smart_availability_assistant():
    """Free deterministic assistant: it never sends booking data to an external AI."""
    st.markdown("---")
    with st.container(border=True):
        st.subheader("🔎 ผู้ช่วยค้นหารถและห้องว่าง")
        st.caption("ค้นหาจากฐานข้อมูลจริง รวมทั้งรายการที่อนุมัติแล้วและรายการรออนุมัติ โดยไม่ส่งข้อมูลไปยัง AI ภายนอก")
        examples = [
            "รถคันไหนว่างพรุ่งนี้ 09:00-12:00",
            "MG ว่างวันไหนสัปดาห์หน้า ช่วงบ่าย",
            "ห้องประชุมว่างวันที่ 25/07 เวลา 13:00-16:00",
        ]
        example_columns = st.columns(3)
        for index, (column, example) in enumerate(zip(example_columns, examples)):
            column.button(
                example, key=f"smart_example_{index}", width="stretch",
                on_click=_set_smart_search_example, args=(example,),
            )
        with st.form("smart_availability_form"):
            query = st.text_input(
                "ถามผู้ช่วย", key="smart_search_query",
                placeholder="เช่น รถคันไหนว่างวันที่ 25/07 เวลา 09:00-12:00",
            )
            submitted = st.form_submit_button("ค้นหาจากตารางจอง", type="primary", width="stretch")
        if submitted:
            criteria, parse_error = parse_availability_query(query)
            if parse_error:
                st.session_state["smart_search_result"] = None
                st.session_state["smart_search_error"] = parse_error
            else:
                with st.spinner("กำลังตรวจสอบคิวจริง..."):
                    result, search_error = search_resource_availability(criteria)
                st.session_state["smart_search_result"] = result
                st.session_state["smart_search_error"] = search_error

        error = st.session_state.get("smart_search_error")
        result = st.session_state.get("smart_search_result")
        if error:
            st.warning(error)
        if not result:
            return

        criteria = result["criteria"]
        st.markdown(
            f"**ผลค้นหา: {criteria['category']} · "
            f"{criteria['start_clock'].strftime('%H:%M')}-{criteria['end_clock'].strftime('%H:%M')}**"
        )
        if criteria["used_default_time"]:
            st.info("ไม่ได้ระบุเวลา ระบบจึงตรวจช่วงเวลาทำการ 08:00-17:00")

        bookable_options = []
        if len(result["days"]) == 1:
            day_result = result["days"][0]
            st.markdown(f"#### {day_result['date'].strftime('%d/%m/%Y')}")
            if day_result["free"]:
                st.success("✅ ว่างตามช่วงเวลาที่ค้นหา: " + ", ".join(unit["label"] for unit in day_result["free"]))
            else:
                st.error("❌ ไม่มีรายการที่ว่างครบตามช่วงเวลาที่ค้นหา")
            for unit in day_result["busy"]:
                conflicts = ", ".join(f"{item['time']} ({item['status']})" for item in unit["conflicts"])
                alternatives = ", ".join(unit["free_slots"]) or "ไม่มีช่วงว่างระหว่าง 08:00-17:00"
                st.write(f"🔴 **{unit['label']}** ติดคิว {conflicts}")
                st.caption(f"ช่วงอื่นที่ว่าง: {alternatives}")
        else:
            summary_rows = []
            for day_result in result["days"]:
                summary_rows.append({
                    "วันที่": day_result["date"].strftime("%d/%m/%Y"),
                    "ว่าง": ", ".join(unit["label"] for unit in day_result["free"]) or "-",
                    "ติดคิว": ", ".join(unit["label"] for unit in day_result["busy"]) or "-",
                })
            st.dataframe(pd.DataFrame(summary_rows), hide_index=True, width="stretch")

        for day_result in result["days"]:
            for unit in day_result["free"]:
                bookable_options.append({
                    "label": (
                        f"{day_result['date'].strftime('%d/%m/%Y')} · {unit['label']} · "
                        f"{criteria['start_clock'].strftime('%H:%M')}-{criteria['end_clock'].strftime('%H:%M')}"
                    ),
                    "category": criteria["category"], "resource": unit["booking_resource"],
                    "date": day_result["date"],
                    "start": criteria["start_clock"].strftime("%H%M"),
                    "end": criteria["end_clock"].strftime("%H%M"),
                })
        if bookable_options:
            option_labels = [option["label"] for option in bookable_options]
            selected_label = st.selectbox("เลือกรายการเพื่อนำไปหน้าจอง", option_labels, key="smart_booking_choice")
            selected_option = bookable_options[option_labels.index(selected_label)]
            st.button(
                "📝 ไปหน้าจองพร้อมกรอกวัน เวลา และรายการให้",
                type="primary", width="stretch",
                on_click=_apply_availability_to_booking, args=(selected_option,),
            )

def load_month_usage(resources, month_start, next_month):
    """Group approved bookings by date and resource for the month calendar."""
    rows = supabase.table("bookings").select("resource,start_time,end_time").eq("status", "Approved") \
        .in_("resource", resources).gt("end_time", month_start.isoformat()) \
        .lt("start_time", next_month.isoformat()).execute().data
    usage = {}
    for row in rows:
        start = _to_calendar_datetime(row["start_time"])
        end = _to_calendar_datetime(row["end_time"])
        day_cursor = max(start.date(), month_start.date())
        final_day = min(end.date(), (next_month - timedelta(days=1)).date())
        while day_cursor <= final_day:
            day_start = datetime.combine(day_cursor, datetime.min.time())
            day_end = day_start + timedelta(days=1)
            slot_start = max(start, day_start)
            slot_end = min(end, day_end)
            if slot_start < slot_end:
                usage.setdefault(day_cursor, {}).setdefault(row["resource"], []).append(
                    f"{slot_start:%H:%M}-{slot_end:%H:%M}"
                )
            day_cursor += timedelta(days=1)
    return usage

def render_month_calendar():
    """First-page availability calendar; cars are selected by default."""
    st.markdown("---")
    st.markdown('<div class="calendar-section-heading"><span>🗓️</span><div><h2>ปฏิทินการใช้งาน</h2><p>เลือกเดือนและประเภท เพื่อดูช่วงเวลาที่จองแล้ว</p></div></div>', unsafe_allow_html=True)
    left, right = st.columns([1, 2])
    with left:
        chosen_date = st.date_input("เลือกเดือน", value=thai_wall_now().date(), key="calendar_month_picker")
    with right:
        calendar_type = st.radio("แสดงปฏิทิน", ["รถยนต์", "ห้องประชุม"], horizontal=True, key="calendar_type")
    resources = get_calendar_resources(calendar_type)
    month_start = datetime(chosen_date.year, chosen_date.month, 1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    try:
        usage = load_month_usage(resources, month_start, next_month)
    except Exception as exc:
        st.error(f"ไม่สามารถโหลดปฏิทินได้: {exc}")
        return

    calendar_cells = []
    today = thai_wall_now().date()
    for day in [item for week in calendar_module.monthcalendar(chosen_date.year, chosen_date.month) for item in week]:
        if day == 0:
            calendar_cells.append('<div class="booking-calendar__blank" aria-hidden="true"></div>')
            continue

        current_date = datetime(chosen_date.year, chosen_date.month, day).date()
        today_class = " booking-calendar__day--today" if current_date == today else ""
        used_resources = usage.get(current_date, {})
        if not used_resources:
            calendar_cells.append(
                f'<article class="booking-calendar__day booking-calendar__day--free{today_class}">'
                f'<strong>{day}</strong><span>🟢 ว่าง {len(resources)}/{len(resources)}</span></article>'
            )
            continue

        booking_count = sum(len(slots) for slots in used_resources.values())
        detail_lines = []
        for resource, slots in sorted(used_resources.items()):
            detail_lines.append(
                f'<span class="booking-calendar__resource">{html.escape(_short_resource_name(resource))}</span>'
                f'<span class="booking-calendar__time">{html.escape(", ".join(sorted(slots)))}</span>'
            )
        load_ratio = len(used_resources) / max(len(resources), 1)
        load_class = "booking-calendar__day--full" if load_ratio >= 1 else ("booking-calendar__day--high" if load_ratio >= 0.6 else "booking-calendar__day--busy")
        calendar_cells.append(
            f'<article class="booking-calendar__day {load_class}{today_class}">'
            f'<strong>{day}</strong><span class="booking-calendar__count">ใช้งาน {len(used_resources)}/{len(resources)} · {booking_count} รายการ</span>'
            f'<div class="booking-calendar__details">{"".join(detail_lines)}</div></article>'
        )

    weekdays = "".join(f'<span>{label}</span>' for label in ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"])
    thai_months = ["", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    days_in_month = calendar_module.monthrange(chosen_date.year, chosen_date.month)[1]
    busy_days = sum(1 for day_number in range(1, days_in_month + 1) if usage.get(datetime(chosen_date.year, chosen_date.month, day_number).date()))
    calendar_markup = (
        '<style>'
        '.calendar-section-heading{display:flex;align-items:flex-start;gap:.85rem;margin:.4rem 0 1rem}.calendar-section-heading>span{display:grid;place-items:center;width:46px;height:46px;border-radius:14px;background:#e8f4fb;font-size:1.45rem}.calendar-section-heading h2{margin:0;color:#102f45;font-size:clamp(1.45rem,2.5vw,2rem)}.calendar-section-heading p{margin:.25rem 0 0;color:#607887;font-size:.9rem}'
        '.booking-calendar{margin:.45rem 0 .8rem;padding:1rem;border:1px solid #cfe0ea;border-radius:18px;background:rgba(255,255,255,.94);box-shadow:0 12px 32px rgba(24,73,105,.09)}'
        '.booking-calendar__title{display:flex;justify-content:space-between;gap:1rem;align-items:center;margin:0 0 .8rem}.booking-calendar__title h4{margin:0;color:#071d2c;font-size:1.2rem}.booking-calendar__legend{display:flex;gap:.55rem;flex-wrap:wrap}.booking-calendar__legend span,.booking-calendar__summary span{padding:.28rem .55rem;border-radius:999px;background:#edf4f8;color:#183b52;font-size:.75rem;font-weight:750}.booking-calendar__legend .dark{background:#071d2c;color:#fff}'
        '.booking-calendar__summary{display:flex;gap:.45rem;flex-wrap:wrap;margin-bottom:.8rem}.booking-calendar__weekdays,.booking-calendar__grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:.42rem}.booking-calendar__weekdays span{text-align:center;color:#294b61;font-size:.76rem;font-weight:800;padding:.2rem 0}'
        '.booking-calendar__day,.booking-calendar__blank{min-height:116px;padding:.58rem;border-radius:11px;border:1px solid #d3e2eb;background:#fff;overflow:hidden}.booking-calendar__day{transition:transform .15s ease,box-shadow .15s ease}.booking-calendar__day:hover{transform:translateY(-2px);box-shadow:0 8px 18px rgba(10,42,62,.12)}.booking-calendar__day strong{display:block;color:#071d2c;font-size:1rem;margin-bottom:.28rem}.booking-calendar__day--free span{color:#267047;font-size:.75rem;font-weight:750}'
        '.booking-calendar__day--busy,.booking-calendar__day--high,.booking-calendar__day--full{border-color:#17384d;background:#17384d}.booking-calendar__day--high{background:#102f45}.booking-calendar__day--full{background:#071d2c}.booking-calendar__day--busy strong,.booking-calendar__day--high strong,.booking-calendar__day--full strong,.booking-calendar__count,.booking-calendar__resource,.booking-calendar__time{color:#fff}.booking-calendar__day--today{outline:3px solid #f5b82e;outline-offset:1px}.booking-calendar__count{display:block;font-size:.75rem;font-weight:800;line-height:1.35}.booking-calendar__details{display:grid;gap:.12rem;margin-top:.38rem}.booking-calendar__resource{font-size:.72rem;font-weight:800;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.booking-calendar__time{font-size:.69rem;line-height:1.25;color:#dceaf2}'
        '@media(max-width:640px){.calendar-section-heading>span{width:40px;height:40px}.calendar-section-heading h2{font-size:1.45rem}.calendar-section-heading p{font-size:.8rem}.booking-calendar{padding:.72rem;border-radius:14px}.booking-calendar__title{align-items:flex-start;flex-direction:column;gap:.45rem}.booking-calendar__title h4{font-size:1.05rem}.booking-calendar__weekdays{display:none}.booking-calendar__grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:.42rem}.booking-calendar__blank{display:none}.booking-calendar__day{min-height:96px;padding:.52rem}.booking-calendar__day strong{font-size:.92rem}.booking-calendar__resource{font-size:.68rem}.booking-calendar__time{font-size:.65rem}}'
        '</style>'
        f'<section class="booking-calendar" aria-label="ปฏิทินการใช้งาน {html.escape(calendar_type)}">'
        f'<div class="booking-calendar__title"><h4>{thai_months[chosen_date.month]} {chosen_date.year + 543} · {html.escape(calendar_type)}</h4><div class="booking-calendar__legend"><span>🟢 ว่าง</span><span class="dark">มีการใช้งาน</span></div></div>'
        f'<div class="booking-calendar__summary"><span>ทรัพยากร {len(resources)} รายการ</span><span>มีคิว {busy_days} วัน</span><span>ว่างทั้งวัน {days_in_month - busy_days} วัน</span></div>'
        f'<div class="booking-calendar__weekdays">{weekdays}</div>'
        f'<div class="booking-calendar__grid">{"".join(calendar_cells)}</div>'
        '</section>'
    )
    st.markdown(calendar_markup, unsafe_allow_html=True)
    st.caption("ตัวเลข “ใช้งาน” คือจำนวนรถหรือห้องที่มีรายการอนุมัติในวันนั้น; เวลาที่แสดงคือช่วงเวลาที่ถูกจองแล้ว")

# ==========================================
# 4.1 ตารางผู้บริหาร (อ่านข้อมูลจาก Google Sheet เท่านั้น)
# ==========================================
def _parse_management_date(value):
    """Parse Google Sheet dates and normalize Buddhist Era dates when present."""
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    numeric_match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", raw_value)
    if numeric_match:
        day, month, year = (int(part) for part in numeric_match.groups())
        if year >= 2400:
            year -= 543
        try:
            return datetime(year, month, day).date()
        except ValueError:
            return None
    parsed_value = pd.to_datetime(raw_value, errors="coerce", dayfirst=True)
    if pd.isna(parsed_value):
        return None
    parsed_date = parsed_value.date()
    if parsed_date.year >= 2400:
        parsed_date = parsed_date.replace(year=parsed_date.year - 543)
    return parsed_date


def _format_management_time(value):
    """Keep the HR-entered time readable while removing an optional :00 suffix."""
    raw_value = str(value or "").strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", raw_value)
    if match:
        return f"{int(match.group(1)):02d}:{match.group(2)}"
    return raw_value


@st.cache_data(ttl=300, show_spinner=False)
def load_management_schedule():
    """Load the public HR sheet as CSV. This function never performs a write."""
    response = requests.get(
        MANAGEMENT_SHEET_CSV_URL,
        timeout=15,
        headers={"User-Agent": "Book-Smarter-Plus/1.0.1"},
    )
    response.raise_for_status()
    response.encoding = "utf-8-sig"
    schedule_df = pd.read_csv(io.StringIO(response.text), dtype=str).fillna("")
    schedule_df.columns = [str(column).strip() for column in schedule_df.columns]

    required_columns = {"วันที่", "เวลาออกเดินทาง", "ตำแหน่งเริ่มต้น", "เวลาถึง", "จุดหมายสุดท้าย"}
    missing_columns = required_columns.difference(schedule_df.columns)
    if missing_columns:
        raise ValueError("Google Sheet ไม่มีหัวคอลัมน์ที่จำเป็น: " + ", ".join(sorted(missing_columns)))

    schedule_df["_schedule_date"] = schedule_df["วันที่"].map(_parse_management_date)
    schedule_df = schedule_df[schedule_df["_schedule_date"].notna()].copy()
    schedule_df["_departure_time"] = schedule_df["เวลาออกเดินทาง"].map(_format_management_time)
    schedule_df["_arrival_time"] = schedule_df["เวลาถึง"].map(_format_management_time)
    schedule_df["_time_sort"] = schedule_df["_departure_time"].replace("", "99:99")
    return schedule_df


def render_management_schedule():
    """Read-only daily/monthly management schedule, separated from the booking database."""
    st.markdown('<div class="main-title">ตารางผู้บริหาร</div>', unsafe_allow_html=True)
    st.caption("ข้อมูลจากฝ่าย HR · สำหรับดูตารางเท่านั้น ระบบนี้ไม่สามารถแก้ไข Google Sheet ได้")

    controls_left, controls_right, controls_link = st.columns([1.1, 1.1, 1.4])
    with controls_left:
        view_mode = st.radio(
            "รูปแบบการดู", ["รายวัน", "รายเดือน"], horizontal=True, key="management_view_mode"
        )
    with controls_right:
        selected_date = st.date_input(
            "เลือกวันที่" if view_mode == "รายวัน" else "เลือกเดือน",
            value=thai_wall_now().date(),
            key="management_schedule_date",
        )
    with controls_link:
        st.link_button("เปิด Google Sheet ต้นฉบับ (ดูอย่างเดียว)", MANAGEMENT_SHEET_URL, width="stretch")

    try:
        with st.spinner("กำลังโหลดตารางผู้บริหาร..."):
            schedule_df = load_management_schedule()
    except Exception as exc:
        st.error("ไม่สามารถโหลดตารางผู้บริหารได้ในขณะนี้")
        st.caption(f"รายละเอียดสำหรับผู้ดูแล: {exc}")
        return

    if view_mode == "รายวัน":
        filtered_df = schedule_df[schedule_df["_schedule_date"] == selected_date].copy()
        heading = f"ตารางวันที่ {selected_date.strftime('%d/%m/%Y')}"
    else:
        month_start = selected_date.replace(day=1)
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        filtered_df = schedule_df[
            (schedule_df["_schedule_date"] >= month_start)
            & (schedule_df["_schedule_date"] < next_month)
        ].copy()
        heading = f"ตารางเดือน {month_start.strftime('%m/%Y')}"

    st.subheader(heading)
    if filtered_df.empty:
        st.info("ไม่มีรายการในช่วงวันที่เลือก")
        return

    filtered_df = filtered_df.sort_values(["_schedule_date", "_time_sort"], kind="stable")
    display_rows = pd.DataFrame({
        "วันที่": filtered_df["_schedule_date"].map(lambda value: value.strftime("%d/%m/%Y")),
        "วัน": filtered_df.get("วัน", ""),
        "เวลาเดินทาง": filtered_df.apply(
            lambda row: " - ".join(part for part in [row["_departure_time"], row["_arrival_time"]] if part) or "-",
            axis=1,
        ),
        "ต้นทาง": filtered_df["ตำแหน่งเริ่มต้น"],
        "ปลายทาง": filtered_df["จุดหมายสุดท้าย"],
        "รายละเอียด": filtered_df.get("รายละเอียด", ""),
        "หมายเหตุ": filtered_df.get("หมายเหตุ", ""),
    })
    st.metric("จำนวนรายการ", f"{len(display_rows)} รายการ")
    st.dataframe(display_rows, hide_index=True, width="stretch", height=min(680, 120 + len(display_rows) * 38))
    st.caption("แสดงเฉพาะข้อมูลการเดินทาง ไม่แสดง Event ID, Sync ล่าสุด หรือคอลัมน์ระบบภายในของ HR")


# ==========================================
# 4.1 ตารางผู้บริหาร: บันทึกเฉพาะรถยนต์ (แทน Google Sheet เดิม)
# ==========================================
def render_management_schedule():
    """Admin-only executive car schedule; saved in the shared bookings table."""
    st.markdown('<div class="main-title">ตารางผู้บริหาร</div>', unsafe_allow_html=True)
    if not st.session_state.get("admin_logged_in"):
        st.info("เฉพาะ Admin ที่เข้าสู่ระบบแล้วเท่านั้นที่ดูหรือบันทึกรายละเอียดตารางผู้บริหารได้")
        return

    recorder = st.session_state.get("admin_user", "Admin")
    st.caption("บันทึกเฉพาะรถยนต์ · อนุมัติทันที · ไม่มีการแจ้งเตือน LINE · รายละเอียดหน้านี้เห็นได้เฉพาะ Admin")

    with st.form("executive_booking_form", clear_on_submit=True):
        left, right = st.columns(2)
        with left:
            resource = st.selectbox("รถยนต์", SYS_CARS, key="executive_resource")
            st.text_input("ผู้บันทึก", value=recorder, disabled=True)
            destination = st.text_input("สถานที่ปลายทาง / Google Map", key="executive_destination")
            purpose = st.text_area("วัตถุประสงค์การใช้งาน", key="executive_purpose")
        with right:
            today = thai_wall_now().date()
            start_date = st.date_input("วันที่เริ่ม", min_value=today, key="executive_start_date")
            start_raw = st.text_input("เวลาเริ่ม (เช่น 0800)", max_chars=4, key="executive_start_time")
            end_date = st.date_input("วันที่สิ้นสุด", min_value=start_date, key="executive_end_date")
            end_raw = st.text_input("เวลาสิ้นสุด (เช่น 1700)", max_chars=4, key="executive_end_time")
        submitted = st.form_submit_button("บันทึกตารางผู้บริหาร", type="primary", width="stretch")

    if submitted:
        try:
            start_time = datetime.combine(start_date, datetime.strptime(format_time_string(start_raw), "%H:%M").time())
            end_time = datetime.combine(end_date, datetime.strptime(format_time_string(end_raw), "%H:%M").time())
        except ValueError:
            st.error("กรุณากรอกเวลาให้ถูกต้อง เช่น 0800 และ 1700")
        else:
            if start_time < thai_wall_now():
                st.error("ไม่สามารถบันทึกเวลาย้อนหลังได้")
            elif start_time >= end_time:
                st.error("เวลาเริ่มต้องมาก่อนเวลาสิ้นสุด")
            else:
                is_conflict, conflict_user, conflict_status, is_executive_conflict = check_booking_conflict(
                    resource, start_time.isoformat(), end_time.isoformat()
                )
                if is_conflict:
                    detail = "ใช้สำหรับผู้บริหารแล้ว" if is_executive_conflict else (
                        "ถูกจองแล้ว" if conflict_status == "Approved" else "มีคนกำลังรออนุมัติ"
                    )
                    st.error(f"บันทึกไม่ได้: {resource} {detail} ในช่วงเวลานี้")
                else:
                    try:
                        supabase.table("bookings").insert({
                            "resource": resource,
                            "requester": recorder,
                            "phone": "-",
                            "dept": "ผู้บริหาร",
                            "start_time": start_time.isoformat(),
                            "end_time": end_time.isoformat(),
                            "purpose": purpose,
                            "destination": destination,
                            "status": "Approved",
                            "is_rated": True,
                            "is_executive_booking": True,
                            "last_updated_by": recorder,
                            "last_updated_at": datetime.now(THAILAND_TZ).isoformat(),
                        }).execute()
                        st.success("บันทึกตารางผู้บริหารเรียบร้อย รถถูกกันคิวแล้ว")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"บันทึกไม่สำเร็จ: {exc}")

    try:
        active_executive_cutoff = thai_wall_now().isoformat()
        executive_result = (
            supabase.table("bookings").select("*")
            .eq("status", "Approved").eq("is_executive_booking", True)
            .gt("end_time", active_executive_cutoff).in_("resource", SYS_CARS)
            .order("start_time").execute()
        )
        executive_df = pd.DataFrame(executive_result.data or [])
    except Exception as exc:
        st.error(f"ไม่สามารถโหลดตารางผู้บริหารได้: {exc}")
        return

    st.markdown("---")
    st.subheader("รายงานตารางผู้บริหาร")
    if executive_df.empty:
        st.info("ไม่มีรายการผู้บริหารที่กำลังใช้งานหรือกำลังจะมาถึง")
        return

    executive_df["เวลาเริ่ม"] = pd.to_datetime(executive_df["start_time"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")
    executive_df["เวลาสิ้นสุด"] = pd.to_datetime(executive_df["end_time"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")
    executive_df["แก้ไขล่าสุด"] = executive_df.get("last_updated_at").map(format_thai_audit_datetime)
    executive_df["บันทึก/แก้ไขล่าสุดโดย"] = executive_df.get("last_updated_by", executive_df["requester"]).fillna(executive_df["requester"])
    display = executive_df[["id", "resource", "เวลาเริ่ม", "เวลาสิ้นสุด", "requester", "destination", "purpose", "บันทึก/แก้ไขล่าสุดโดย", "แก้ไขล่าสุด"]].copy()
    display.columns = ["รหัสรายการ", "รถยนต์", "เวลาเริ่ม", "เวลาสิ้นสุด", "ผู้บันทึก", "ปลายทาง", "วัตถุประสงค์", "บันทึก/แก้ไขล่าสุดโดย", "เวลาแก้ไขล่าสุด"]
    st.dataframe(display, hide_index=True, width="stretch")

    st.markdown("### แก้ไขรายการ")
    executive_df["label_for_edit"] = executive_df.apply(
        lambda row: (
            f"#{row['id']} | {row['resource']} | {row['เวลาเริ่ม']}–{row['เวลาสิ้นสุด']} "
            f"| {str(row.get('destination', '-'))[:70]} | {str(row.get('purpose', '-'))[:50]}"
        ),
        axis=1,
    )
    labels_by_id = dict(zip(executive_df["id"], executive_df["label_for_edit"]))
    available_ids = executive_df["id"].tolist()
    current_id = st.session_state.get("executive_edit_id")
    if current_id not in available_ids:
        current_id = available_ids[0]
        st.session_state["executive_edit_id"] = current_id

    # Streamlit's dataframe cannot contain action buttons, so provide one
    # clearly labelled edit button per record directly below the report.
    st.caption("เลือกรายการจากรายละเอียดด้านล่าง หรือกดปุ่ม ✏️ แก้ไข ของรายการนั้น")
    for item in executive_df.to_dict("records"):
        row_info, row_action = st.columns([8, 2])
        row_info.markdown(f"**{item['label_for_edit']}**")
        if row_action.button("✏️ แก้ไข", key=f"open_executive_edit_{item['id']}", width="stretch"):
            st.session_state["executive_edit_id"] = item["id"]
            st.session_state["executive_edit_selector"] = item["id"]
            st.rerun()

    selected_id = st.selectbox(
        "รายการที่กำลังแก้ไข",
        available_ids,
        index=available_ids.index(current_id),
        format_func=lambda value: labels_by_id[value],
        key="executive_edit_selector",
    )
    st.session_state["executive_edit_id"] = selected_id
    record = executive_df[executive_df["id"] == selected_id].iloc[0]
    st.info(f"กำลังแก้ไข: {labels_by_id[selected_id]}")
    with st.form("edit_executive_booking_form"):
        edit_left, edit_right = st.columns(2)
        with edit_left:
            car_index = SYS_CARS.index(record["resource"]) if record["resource"] in SYS_CARS else 0
            edit_key = f"edit_executive_{record['id']}"
            edit_resource = st.selectbox("รถยนต์", SYS_CARS, index=car_index, key=f"{edit_key}_resource")
            edit_destination = st.text_input("สถานที่ปลายทาง / Google Map", str(record.get("destination", "")), key=f"{edit_key}_destination")
            edit_purpose = st.text_area("วัตถุประสงค์การใช้งาน", str(record.get("purpose", "")), key=f"{edit_key}_purpose")
        with edit_right:
            old_start = booking_wall_datetime(record["start_time"])
            old_end = booking_wall_datetime(record["end_time"])
            edit_start_date = st.date_input("วันที่เริ่ม", old_start.date(), key=f"{edit_key}_start_date")
            edit_start_raw = st.text_input("เวลาเริ่ม (เช่น 0800)", old_start.strftime("%H%M"), max_chars=4, key=f"{edit_key}_start_time")
            edit_end_date = st.date_input("วันที่สิ้นสุด", old_end.date(), key=f"{edit_key}_end_date")
            edit_end_raw = st.text_input("เวลาสิ้นสุด (เช่น 1700)", old_end.strftime("%H%M"), max_chars=4, key=f"{edit_key}_end_time")
        save_edit = st.form_submit_button("บันทึกการแก้ไข", type="primary", width="stretch")

    if save_edit:
        try:
            updated_start = datetime.combine(edit_start_date, datetime.strptime(format_time_string(edit_start_raw), "%H:%M").time())
            updated_end = datetime.combine(edit_end_date, datetime.strptime(format_time_string(edit_end_raw), "%H:%M").time())
            if updated_start >= updated_end:
                raise ValueError("เวลาเริ่มต้องมาก่อนเวลาสิ้นสุด")
            is_conflict, _, _, _ = check_booking_conflict(
                edit_resource, updated_start.isoformat(), updated_end.isoformat(), exclude_booking_id=record["id"]
            )
            if is_conflict:
                st.error("แก้ไขไม่ได้: รถคันนี้มีคิวชนในช่วงเวลาที่เลือก")
            else:
                supabase.table("bookings").update({
                    "resource": edit_resource, "destination": edit_destination, "purpose": edit_purpose,
                    "start_time": updated_start.isoformat(), "end_time": updated_end.isoformat(),
                    "last_updated_by": recorder, "last_updated_at": datetime.now(THAILAND_TZ).isoformat(),
                }).eq("id", record["id"]).execute()
                st.success("แก้ไขรายการเรียบร้อย")
                st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"แก้ไขไม่สำเร็จ: {exc}")


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
# Retain only the latest 45 days. Caching limits cleanup to once per day per
# running Streamlit instance instead of once per widget interaction/rerun.
auto_delete_old_bookings()
try:
    pending_result = (
        supabase.table("bookings")
        .select("id", count="exact", head=True)
        .eq("status", "Pending")
        .execute()
    )
    pending_count = pending_result.count or 0
except:
    pending_count = 0

st.sidebar.image(str(COMPANY_LOGO_PATH), width="stretch")
st.sidebar.markdown('<div class="sidebar-brand-divider"></div>', unsafe_allow_html=True)
st.sidebar.image(str(APP_LOGO_PATH), width="stretch")
st.sidebar.link_button(label="เพิ่มเพื่อน LINE (ดูคิว/สถานะ)", url=LINE_ADD_FRIEND_URL, width="stretch", type="primary")
st.sidebar.markdown(
    f"<p style='text-align: center; color: #B8CCE0; font-size: 12px;'>"
    f"Book Smarter Plus+ · v{APP_VERSION}<br>Line ID: {CURRENT_BOT_ID}</p>",
    unsafe_allow_html=True,
)

if pending_count > 0:
    st.sidebar.markdown(f'<p class="blink">📢 มีรายการรออนุมัติ: {pending_count}</p>', unsafe_allow_html=True)

# เมนูหลักใน Sidebar (คง key และค่า choice เดิม เพื่อไม่กระทบลอจิกแต่ละหน้า)
menu = ["🏠 หน้าแรก", "📝 จองใหม่", "📅 ตารางงาน (Real-time)", "👔 ตารางผู้บริหาร", "⭐ ประเมินการใช้งาน", "🔑 Admin (อนุมัติ)", "📊 รายงานประจำเดือน"]
nav_labels = {
    "🏠 หน้าแรก": "🏠 หน้าแรก",
    "📝 จองใหม่": "📝 จองใหม่",
    "📅 ตารางงาน (Real-time)": "📅 ตารางงาน",
    "👔 ตารางผู้บริหาร": "👔 ผู้บริหาร",
    "⭐ ประเมินการใช้งาน": "⭐ ประเมิน",
    "🔑 Admin (อนุมัติ)": "🔑 Admin",
    "📊 รายงานประจำเดือน": "📊 รายงาน",
}

if st.session_state.get("top_nav") not in menu:
    st.session_state["top_nav"] = menu[0]

def format_nav_label(menu_item):
    label = nav_labels[menu_item]
    if menu_item == "🔑 Admin (อนุมัติ)" and pending_count > 0:
        return f"{label} · {pending_count}"
    return label

choice = st.sidebar.radio(
    "เมนูหลัก",
    menu,
    key="top_nav",
    horizontal=False,
    format_func=format_nav_label,
    label_visibility="collapsed",
)

st.sidebar.markdown("---")

if st.session_state["admin_logged_in"]:
    st.sidebar.success(f"👤 เข้าสู่ระบบแล้ว:\n**{st.session_state['admin_user']}**")
    if st.sidebar.button("🚪 ออกจากระบบ (Logout)", width="stretch"):
        st.session_state["admin_logged_in"] = False
        st.session_state["admin_user"] = ""
        st.rerun()
    st.sidebar.markdown("---")

# ==========================================
# 7. หน้าจองใหม่ (BOOKING)
# ==========================================
if choice in ["🏠 หน้าแรก", "📝 จองใหม่"]:
    is_home_page = choice == "🏠 หน้าแรก"
    if is_home_page:
        st.markdown('<div class="main-title">ระบบจองรถยนต์และห้องประชุม Online</div>', unsafe_allow_html=True)
        st.markdown('##### 📋 ข้อมูลรถและคนขับ')
    
    # --- คำนวณสถานะ Real-time ---
    now_dt = thai_wall_now()
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
    # --- สถิติ ---
    today_approved_count = len(today_bookings.data or [])
    
    if is_home_page:
        st.markdown(css_style + html_content, unsafe_allow_html=True)
        render_smart_availability_assistant()
        render_month_calendar()
        d1, d2, d3 = st.columns(3)
        d1.metric("รายการจองวันนี้", f"{today_approved_count} รายการ")
        d2.metric("รอพี่อนุมัติ", f"{pending_count} รายการ")
        d3.metric("สถานะฐานข้อมูล", "Connected")
        st.stop()

    st.markdown('<div class="blink" style="text-align:center; font-size:22px; margin-bottom: 20px;">หลังการใช้งานเสร็จกลับมาให้คะแนนคนขับรถทุกครั้ง!!</div>', unsafe_allow_html=True)

    # +++ โค้ดกระพริบโชว์รายชื่อผู้ค้างประเมินเพื่อกดดัน +++
    try:
        now_iso_alert = thai_wall_now().isoformat()
        res_alert = supabase.table("bookings").select("requester, dept, is_rated").eq("status", "Approved").in_("resource", SYS_CARS).lt("end_time", now_iso_alert).gte("end_time", "2026-07-01T00:00:00").execute()
        
        if res_alert.data:
            unrated_list = set()
            for d in res_alert.data:
                if not d.get("is_rated"):
                    req = str(d.get("requester", "")).strip()
                    dpt = str(d.get("dept", "")).strip()
                    if req: unrated_list.add(f"{req} ({dpt})")
            
            if unrated_list:
                alert_text = html.escape(", ".join(sorted(unrated_list)))
                st.markdown(f'<div class="blink" style="text-align:center; font-size:26px; margin-bottom: 20px;">⚠️ รายชื่อผู้ที่ค้างการประเมิน: {alert_text} ⚠️</div>', unsafe_allow_html=True)
    except: pass

    col1, col2 = st.columns(2)
    with col1:
        if st.session_state.get("booking_category") not in ["รถยนต์", "ห้องประชุม"]:
            st.session_state["booking_category"] = "รถยนต์"
        cat = st.radio(
            "ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"],
            horizontal=True, key="booking_category",
        )
        res_list = SYS_CARS if cat == "รถยนต์" else SYS_ROOMS
        if st.session_state.get("booking_resource") not in res_list:
            st.session_state["booking_resource"] = res_list[0]
        res = st.selectbox("เลือกรายการ", res_list, key="booking_resource")
        dest = st.text_input("สถานที่ปลายทาง / Google Map") if cat == "รถยนต์" else "Office"
        name = st.text_input("ชื่อผู้จอง")
        phone = st.text_input("เบอร์โทรศัพท์")
        dept = st.selectbox("แผนก", SYS_DEPTS)

    with col2:
        today = thai_wall_now().date()
        if "booking_start_date" not in st.session_state or st.session_state["booking_start_date"] < today:
            st.session_state["booking_start_date"] = today
        d_start = st.date_input(
            "วันที่เริ่ม", min_value=today, key="booking_start_date"
        )
        if "booking_start_time" not in st.session_state:
            st.session_state["booking_start_time"] = ""
        t_s_raw = st.text_input(
            "เวลาเริ่ม (เช่น 0800)", placeholder="กรอกเวลา เช่น 0800",
            max_chars=4, key="booking_start_time",
        )
        st.markdown("---")
        if "booking_end_date" not in st.session_state or st.session_state["booking_end_date"] < d_start:
            st.session_state["booking_end_date"] = d_start
        d_end = st.date_input(
            "วันที่สิ้นสุด", min_value=d_start, key="booking_end_date"
        )
        if "booking_end_time" not in st.session_state:
            st.session_state["booking_end_time"] = ""
        t_e_raw = st.text_input(
            "เวลาสิ้นสุด (เช่น 1700)", placeholder="กรอกเวลา เช่น 1700",
            max_chars=4, key="booking_end_time",
        )
        reason = st.text_area("วัตถุประสงค์การใช้งาน")
        
        try:
            ts_f, te_f = format_time_string(t_s_raw.strip()), format_time_string(t_e_raw.strip())
            ts = datetime.combine(d_start, datetime.strptime(ts_f, "%H:%M").time())
            te = datetime.combine(d_end, datetime.strptime(te_f, "%H:%M").time())
        except: ts, te = None, None

    if st.button("ยืนยันการส่งคำขอจอง", width="stretch"):
        # Department evaluation locks apply only to a new vehicle booking.
        # Meeting-room bookings must remain available even if the department
        # has a completed vehicle trip awaiting driver evaluation.
        unrated_pending = (
            get_unrated_bookings(name, dept)
            if cat == "รถยนต์" and name and dept
            else []
        )
        if not name or not dept or ts is None:
            st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")
        elif unrated_pending:
            car_names = ", ".join(sorted(set(d['resource'] for d in unrated_pending)))
            st.error(f"❌ คุณ {name} ({dept}) มีรายการที่ยังไม่ได้ให้คะแนนคนขับ ({car_names}) กรุณาไปที่เมนู '⭐ ประเมินการใช้งาน' เพื่อให้คะแนนก่อน แล้วค่อยกลับมาจองใหม่นะครับ")
        elif ts < thai_wall_now(): 
            st.error("❌ ไม่สามารถจองย้อนหลังได้ กรุณาเลือกเวลาปัจจุบันหรือล่วงหน้า")
        elif ts >= te:
            st.error("❌ เวลาเริ่มต้องมาก่อนเวลาสิ้นสุด")
        else:
            is_conf, user_conf, status_conf, is_executive_conflict = check_booking_conflict(res, ts.isoformat(), te.isoformat())
            if is_conf:
                if is_executive_conflict:
                    st.error(f"❌ {res} ไม่ว่าง / ใช้สำหรับผู้บริหาร ในเวลานี้")
                else:
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
elif choice == "👔 ตารางผู้บริหาร":
    render_management_schedule()

# ==========================================
# 8. ตารางงาน REAL-TIME
# ==========================================
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางการใช้งานปัจจุบันและล่วงหน้า")
    f_c1, f_c2 = st.columns([2, 1])
    search_q = f_c1.text_input("🔍 ค้นหาชื่อผู้จอง / สถานที่")
    view_cat = f_c2.selectbox("กรองตามประเภท", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
    
    t_today_start = thai_wall_now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    try:
        res = supabase.table("bookings").select("*").eq("status", "Approved").gte("start_time", t_today_start).execute()
        df = pd.DataFrame(res.data)
        if not df.empty and not st.session_state.get("admin_logged_in", False) and "is_executive_booking" in df.columns:
            # Executive details are visible only to an Admin on the web schedule.
            df = df[~df["is_executive_booking"].fillna(False)]
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
            st.dataframe(df_disp, width="stretch")

            st.markdown("---")
            with st.expander("🛠️ จัดการข้อมูล (แก้ไข/ลบ โดย Admin)"):
                if not st.session_state["admin_logged_in"]:
                    st.warning("⚠️ เฉพาะผู้ดูแลระบบเท่านั้น กรุณาเข้าสู่ระบบผ่านเมนู '🔑 Admin' ด้านบนก่อนใช้งานส่วนนี้")
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
                        if b1.form_submit_button("💾 บันทึกการแก้ไข", width="stretch"):
                            try:
                                fs, fe = format_time_string(n_t_s), format_time_string(n_t_e)
                                f_start = datetime.combine(n_d_s, datetime.strptime(fs, "%H:%M").time()).isoformat()
                                f_end = datetime.combine(n_d_e, datetime.strptime(fe, "%H:%M").time()).isoformat()

                                if datetime.fromisoformat(f_start) >= datetime.fromisoformat(f_end):
                                    st.error("❌ เวลาเริ่มต้องมาก่อนเวลาสิ้นสุด")
                                else:
                                    is_conf, user_conf, status_conf, _ = check_booking_conflict(
                                        n_res, f_start, f_end, exclude_booking_id=row['id']
                                    )
                                    if is_conf:
                                        msg = "ถูกจองแล้ว" if status_conf == "Approved" else "มีคนกำลังรออนุมัติ"
                                        st.error(f"❌ บันทึกไม่ได้ คิวชนกัน! {n_res} {msg} โดยคุณ {user_conf}")
                                    else:
                                        supabase.table("bookings").update({
                                            "resource": n_res, "requester": n_req, "destination": n_dest,"dept": n_dept,
                                            "purpose": n_purp, "start_time": f_start, "end_time": f_end
                                        }).eq("id", row['id']).execute()

                                        st.success("อัปเดตเรียบร้อย!"); st.rerun()
                            except Exception as e: st.error(f"❌ ผิดพลาด: {e}")
                        
                        if b2.form_submit_button("🗑️ ลบรายการนี้", width="stretch"):
                            try:
                                supabase.table("bookings").delete().eq("id", row['id']).execute()
                                st.rerun()
                            except Exception as e: st.error(f"❌ ลบไม่สำเร็จ: {e}")

# ==========================================
# 9. เมนู ⭐ ประเมินการใช้งาน
# ==========================================
elif choice == "⭐ ประเมินการใช้งาน":
    st.subheader("⭐ ประเมินการปฏิบัติงานพนักงานขับรถ")
    now_iso = thai_wall_now().isoformat()
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
                    
                    if c2.button("อนุมัติ ✅", key=f"ap_{item['id']}", width="stretch"):
                        try:
                            f_time = format_time_string(a_t)
                            final_start = datetime.combine(a_d, datetime.strptime(f_time, "%H:%M").time()).isoformat()

                            if datetime.fromisoformat(final_start) >= pd.to_datetime(item['end_time']).to_pydatetime().replace(tzinfo=None):
                                st.error("❌ อนุมัติไม่ได้ เวลาเริ่มต้องมาก่อนเวลาสิ้นสุด")
                            else:
                                is_conf, user_conf, status_conf, is_executive_conflict = check_booking_conflict(
                                    item['resource'], final_start, item['end_time'], exclude_booking_id=item['id']
                                )
                                if is_conf:
                                    msg = "ถูกจองแล้ว" if status_conf == "Approved" else "มีรายการอื่นรออนุมัติ"
                                    st.error(f"❌ อนุมัติไม่ได้ คิวชนกัน! {item['resource']} {msg} โดยคุณ {user_conf}")
                                else:
                                    supabase.table("bookings").update({"status": "Approved", "start_time": final_start}).eq("id", item['id']).execute()
                                    send_line_notification(item['id'], item['resource'], item['requester'], item['dept'], final_start, item['end_time'], item['purpose'], item.get('destination','-'), "Approved")
                                    st.rerun()
                        except Exception as e: st.error(f"❌ ผิดพลาด: {e}")
                    
                    if c2.button("ลบ 🗑️", key=f"dl_{item['id']}", width="stretch"):
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
            st.dataframe(out_df, width="stretch")
            
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as w: out_df.to_excel(w, index=False)
            st.download_button("📥 ดาวน์โหลดรายงาน (Excel)", buf.getvalue(), f"Report_{rep_type}_{sel_m.replace('/', '-')}.xlsx")
        else: st.info("ยังไม่มีข้อมูลในระบบฐานข้อมูล")
