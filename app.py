import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import os
import io
import re
import json
from sqlalchemy import create_engine, text

# Thử import thư viện ReportLab xuất PDF
try:
    from reportlab.lib.pagesizes import A5, portrait
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# --- CẤU HÌNH TRANG WEB ---
st.set_page_config(page_title="Quản Lý Học Sinh Học Thêm", layout="wide", page_icon="📚")

# --- KẾT NỐI CƠ SỞ DỮ LIỆU ĐÁM MÂY SUPABASE (POSTGRESQL) / SQLITE LOCAL ---
@st.cache_resource
def get_db_engine():
    if "postgres" in st.secrets and "url" in st.secrets["postgres"]:
        db_url = st.secrets["postgres"]["url"].strip()
        
        # Tự động chuyển đổi tiền tố sang driver psycopg2 chuẩn
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
            
        return create_engine(
            db_url,
            pool_pre_ping=True,  # Tự động kiểm tra & kết nối lại nếu bị rớt mạng
            pool_recycle=300,    # Làm mới kết nối sau mỗi 5 phút
            connect_args={"connect_timeout": 15}
        )
    else:
        return create_engine("sqlite:///quan_ly_hoc_sinh.db")

engine = get_db_engine()

# =========================================================
# 🔐 HỆ THỐNG ĐĂNG NHẬP BẢO VỆ ỨNG DỤNG
# =========================================================
def check_password():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if st.session_state.logged_in:
        return True

    st.markdown("<h2 style='text-align: center; color: #1E3A8A;'>📚 Phần Mềm Quản Lý Dạy Thêm Tại Nhà</h2>", unsafe_allow_html=True)
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("🔐 Đăng Nhập Hệ Thống")
        username_input = st.text_input("👤 Tên đăng nhập:", value="admin")
        password_input = st.text_input("🔑 Mật khẩu:", type="password")
        
        if st.button("🚀 Đăng Nhập", type="primary", use_container_width=True):
            valid_user = st.secrets.get("USERNAME", "admin")
            valid_pass = st.secrets.get("PASSWORD", "120809")
            
            if username_input == valid_user and password_input == valid_pass:
                st.session_state.logged_in = True
                st.success("✅ Đăng nhập thành công!")
                st.rerun()
            else:
                st.error("❌ Mật khẩu hoặc Tên đăng nhập không chính xác!")
    return False

if not check_password():
    st.stop()

# --- HÀM HỖ TRỢ THỨ TRONG TUẦN ---
def get_vietnamese_weekday(dt):
    days = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ Nhật"]
    return days[dt.weekday()]

# --- HÀM LẤY LỊCH HỌC HIỆU LỰC CHO MỘT NGÀY ---
def get_active_schedule_for_date(check_date):
    target_day_str = get_vietnamese_weekday(check_date)
    date_str = check_date.strftime("%Y-%m-%d")

    query_temp = text('''
        SELECT t.hoc_sinh_id, h.ho_ten, h.lop_hoc, h.mon_hoc, t.thu, t.ca_hoc, t.loai_thay_doi
        FROM lich_hoc_tam_thoi t
        JOIN hoc_sinh h ON t.hoc_sinh_id = h.id
        WHERE t.ngay_bat_dau <= :d_str AND t.ngay_ket_thuc >= :d_str
    ''')
    df_temp = pd.read_sql_query(query_temp, engine, params={"d_str": date_str})
    temp_hs_ids = df_temp['hoc_sinh_id'].unique() if not df_temp.empty else []

    query_base = text('''
        SELECT l.hoc_sinh_id, h.ho_ten, h.lop_hoc, h.mon_hoc, l.ca_hoc
        FROM lich_hoc_tuan l
        JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
        WHERE l.thu = :thu
    ''')
    df_base = pd.read_sql_query(query_base, engine, params={"thu": target_day_str})
    if not df_base.empty and len(temp_hs_ids) > 0:
        df_base = df_base[~df_base['hoc_sinh_id'].isin(temp_hs_ids)]

    df_temp_today = pd.DataFrame()
    if not df_temp.empty:
        df_temp_today = df_temp[(df_temp['thu'] == target_day_str) & (df_temp['loai_thay_doi'] != 'Nghỉ tạm thời')]

    cols = ['hoc_sinh_id', 'ho_ten', 'lop_hoc', 'mon_hoc', 'ca_hoc']
    df_combined = pd.concat([
        df_base[cols] if not df_base.empty else pd.DataFrame(columns=cols),
        df_temp_today[cols] if not df_temp_today.empty else pd.DataFrame(columns=cols)
    ], ignore_index=True)

    return df_combined

# --- HÀM TỰ ĐỘNG ĐỒNG BỘ LỊCH 7 NGÀY SANG GOOGLE CALENDAR ---
def sync_weekly_schedule_to_google(calendar_id='a.luongxdnb@gmail.com', days_ahead=7):
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return False, "⚠️ Chưa cài đặt thư viện Google trong requirements.txt"

    service_account_file = 'credentials.json'

    try:
        scopes = ['https://www.googleapis.com/auth/calendar']
        
        if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
            creds_data = st.secrets["GOOGLE_CREDENTIALS_JSON"]
            if isinstance(creds_data, str):
                creds_data = creds_data.strip()
                if creds_data.startswith("```json"):
                    creds_data = creds_data[7:]
                if creds_data.startswith("```"):
                    creds_data = creds_data[3:]
                if creds_data.endswith("```"):
                    creds_data = creds_data[:-3]
                info = json.loads(creds_data.strip())
            else:
                info = dict(creds_data)
            creds = Credentials.from_service_account_info(info, scopes=scopes)
        elif os.path.exists(service_account_file):
            creds = Credentials.from_service_account_file(service_account_file, scopes=scopes)
        else:
            return False, "⚠️ Không tìm thấy cấu hình Google Credentials."

        service = build('calendar', 'v3', credentials=creds)

        today = date.today()
        end_date = today + timedelta(days=days_ahead)

        time_min = f"{today.strftime('%Y-%m-%d')}T00:00:00Z"
        time_max = f"{end_date.strftime('%Y-%m-%d')}T23:59:59Z"

        events_result = service.events().list(
            calendarId=calendar_id, 
            timeMin=time_min, 
            timeMax=time_max, 
            singleEvents=True
        ).execute()

        old_events = events_result.get('items', [])
        for evt in old_events:
            if evt.get('summary', '').startswith("🏫 Dạy Thêm Ca"):
                try:
                    service.events().delete(calendarId=calendar_id, eventId=evt['id']).execute()
                except Exception:
                    pass

        count_events = 0
        ca_hoc_time = {
            "7h00 - 9h00": ("07:00:00", "09:00:00"),
            "9h00 - 11h00": ("09:00:00", "11:00:00"),
            "13h30 - 15h30": ("13:30:00", "15:30:00"),
            "15h30 - 17h30": ("15:30:00", "17:30:00"),
            "17h30 - 19h30": ("17:30:00", "19:30:00"),
            "19h30 - 21h30": ("19:30:00", "21:30:00")
        }

        for i in range(days_ahead):
            current_date = today + timedelta(days=i)
            df_day = get_active_schedule_for_date(current_date)

            if df_day.empty:
                continue

            date_str = current_date.strftime("%Y-%m-%d")

            for ca, group_ca in df_day.groupby('ca_hoc'):
                start_time_str, end_time_str = ca_hoc_time.get(ca, ("17:30:00", "19:30:00"))
                start_datetime = f"{date_str}T{start_time_str}+07:00"
                end_datetime = f"{date_str}T{end_time_str}+07:00"

                details = []
                for lop, g in group_ca.groupby('lop_hoc'):
                    ds_hs = ", ".join(g['ho_ten'].tolist())
                    details.append(f"• Lớp {lop}: {ds_hs}")

                description_text = "📚 DANH SÁCH HỌC SINH:\n" + "\n".join(details)
                summary_title = f"🏫 Dạy Thêm Ca {ca} ({len(group_ca)} HS)"

                event = {
                    'summary': summary_title,
                    'description': description_text,
                    'start': {'dateTime': start_datetime, 'timeZone': 'Asia/Ho_Chi_Minh'},
                    'end': {'dateTime': end_datetime, 'timeZone': 'Asia/Ho_Chi_Minh'},
                    'reminders': {
                        'useDefault': False,
                        'overrides': [
                            {'method': 'popup', 'minutes': 30},
                            {'method': 'popup', 'minutes': 10},
                        ],
                    },
                }

                service.events().insert(calendarId=calendar_id, body=event).execute()
                count_events += 1

        return True, f"✅ Đã dọn dẹp lịch cũ & đồng bộ thành công {count_events} ca dạy trong {days_ahead} ngày tới lên iPhone!"

    except Exception as e:
        return False, f"❌ Lỗi khi đồng bộ lịch tuần: {str(e)}"

# --- HÀM SẮP XẾP CA HỌC THEO GIỜ ---
def ca_hoc_sort_key(ca_str):
    predefined = ["7h00 - 9h00", "9h00 - 11h00", "13h30 - 15h30", "15h30 - 17h30", "17h30 - 19h30", "19h30 - 21h30"]
    if ca_str in predefined:
        return (0, predefined.index(ca_str))
    match = re.search(r'(\d+)h?(\d*)', str(ca_str))
    if match:
        h = int(match.group(1))
        m = int(match.group(2)) if match.group(2) else 0
        return (1, h * 60 + m)
    return (2, str(ca_str))

# --- HÀM LẤY BUỔI (SÁNG, CHIỀU, TỐI) ---
def get_buoi_from_ca(ca_str):
    predefined = {
        "7h00 - 9h00": "🌅 Sáng", "9h00 - 11h00": "🌅 Sáng",
        "13h30 - 15h30": "☀️ Chiều", "15h30 - 17h30": "☀️ Chiều",
        "17h30 - 19h30": "🌙 Tối", "19h30 - 21h30": "🌙 Tối"
    }
    if ca_str in predefined:
        return predefined[ca_str]
    match = re.search(r'(\d+)h?(\d*)', str(ca_str))
    if match:
        h = int(match.group(1))
        return "🌅 Sáng" if h < 12 else ("☀️ Chiều" if h < 18 else "🌙 Tối")
    return "☀️ Chiều"

# --- HÀM HIỂN THỊ MA TRẬN LỊCH HỌC ---
def render_schedule_matrix():
    query_mindmap = text('''
        SELECT l.thu, l.ca_hoc, h.lop_hoc, h.mon_hoc, h.ho_ten
        FROM lich_hoc_tuan l
        JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
        ORDER BY 
            CASE l.thu
                WHEN 'Thứ 2' THEN 1 WHEN 'Thứ 3' THEN 2 WHEN 'Thứ 4' THEN 3
                WHEN 'Thứ 5' THEN 4 WHEN 'Thứ 6' THEN 5 WHEN 'Thứ 7' THEN 6 WHEN 'Chủ Nhật' THEN 7
            END, l.ca_hoc, h.lop_hoc
    ''')
    df_mindmap = pd.read_sql_query(query_mindmap, engine)
    
    if df_mindmap.empty:
        st.info("💡 Chưa có lịch học tuần nào được thiết lập.")
        return

    cac_thu = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
    cac_ca = sorted(df_mindmap['ca_hoc'].unique().tolist(), key=ca_hoc_sort_key)
    
    matrix_rows = []
    for ca in cac_ca:
        buoi = get_buoi_from_ca(ca)
        row_dict = {"Buổi": buoi, "Ca học": ca}
        for t in cac_thu:
            matched = df_mindmap[(df_mindmap['thu'] == t) & (df_mindmap['ca_hoc'] == ca)]
            if matched.empty:
                row_dict[t] = "-"
            else:
                items = []
                for lop, g in matched.groupby('lop_hoc'):
                    names = ", ".join(g['ho_ten'].tolist())
                    items.append(f"<b>[{lop}]</b>: {names}")
                row_dict[t] = "<br>".join(items)
        matrix_rows.append(row_dict)
    
    df_matrix = pd.DataFrame(matrix_rows)
    cols = ["Buổi", "Ca học"] + cac_thu
    df_matrix = df_matrix[cols]
    st.write(df_matrix.to_html(index=False, escape=False), unsafe_allow_html=True)

# --- MENU CHÍNH ---
if st.sidebar.button("🚪 Đăng xuất", type="secondary", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

menu = [
    "1. Điểm danh & Nhận xét", 
    "2. 🗺️ Ma Trận Lịch Học & Mindmap Tuần",
    "3. 📅 Lên Lịch Học (Gốc & Tạm Thời)",
    "4. 💡 Gợi ý Smart Assistant",
    "5. Thống kê & Học phí (Lọc Tháng / Xuất Excel)", 
    "6. Quản lý & Thống kê Học phí (Xuất PDF)", 
    "7. Sửa & Xóa dữ liệu"
]
choice = st.sidebar.selectbox("📋 Danh mục chức năng", menu)

# --- SIDEBAR: ĐỒNG BỘ LỊCH SANG IPHONE ---
st.sidebar.markdown("---")
st.sidebar.subheader("📲 Đồng Bổ Lịch Sang iPhone")
user_gmail = st.sidebar.text_input("Địa chỉ Gmail trên iPhone:", value="a.luongxdnb@gmail.com")

if st.sidebar.button("🔄 Đồng Bổ Lịch 7 Ngày Tới Sang iPhone", type="primary"):
    target_cal_id = user_gmail.strip() if user_gmail.strip() else 'primary'
    success, msg = sync_weekly_schedule_to_google(calendar_id=target_cal_id, days_ahead=7)
    if success: st.sidebar.success(msg)
    else: st.sidebar.error(msg)

# --- SIDEBAR: CÀI ĐẶT MÃ QR ---
st.sidebar.markdown("---")
st.sidebar.subheader("📷 Cài đặt Mã QR Thanh Toán")
qr_file = st.sidebar.file_uploader("Tải lên ảnh Mã QR (VietQR/STK)", type=["png", "jpg", "jpeg"])
if qr_file is not None:
    with open("qr_code.png", "wb") as f: f.write(qr_file.getbuffer())
    st.sidebar.success("✅ Đã lưu mã QR!")

if os.path.exists("qr_code.png"):
    st.sidebar.image("qr_code.png", caption="Mã QR thanh toán hiện tại", use_container_width=True)

# --- CHỨC NĂNG 1: ĐIỂM DANH & NHẬN XÉT ---
if choice == "1. Điểm danh & Nhận xét":
    st.subheader("📝 Điểm Danh & Nhận Xét Buổi Học")
    ngay_hoc = st.date_input("🗓️ Chọn ngày điểm danh", date.today())
    thu_hom_nay = get_vietnamese_weekday(ngay_hoc)
    st.caption(f"Ngày được chọn: **{ngay_hoc.strftime('%d/%m/%Y')} ({thu_hom_nay})**")
    
    df_active_today = get_active_schedule_for_date(ngay_hoc)
    type_mode = st.radio("Chế độ điểm danh", ["🏫 Điểm danh theo LỚP (Tự động mặc định Có Mặt)", "👤 Điểm danh từng HỌC SINH"], horizontal=True)
    st.divider()
    
    if type_mode.startswith("🏫"):
        sub_mode_class = st.radio("Tùy chọn danh sách Lớp:", ["🏫 Lớp có lịch hôm nay", "📚 Tất cả các lớp trong hệ thống"], horizontal=True)
        df_all_hs = pd.read_sql_query("SELECT id AS hoc_sinh_id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", engine)
        
        if df_all_hs.empty:
            st.warning("⚠️ Chưa có học sinh nào!")
        else:
            available_classes = df_active_today['lop_hoc'].unique().tolist() if (sub_mode_class == "🏫 Lớp có lịch hôm nay" and not df_active_today.empty) else df_all_hs['lop_hoc'].unique().tolist()
            if available_classes:
                selected_class = st.selectbox("Chọn Lớp cần điểm danh", available_classes)
                target_students = df_active_today[df_active_today['lop_hoc'] == selected_class] if sub_mode_class == "🏫 Lớp có lịch hôm nay" else df_all_hs[df_all_hs['lop_hoc'] == selected_class]
                
                st.markdown(f"#### 📋 Bảng Điểm Danh Lớp: **{selected_class}** ({len(target_students)} HS)")
                
                with st.form("mass_class_attendance"):
                    danh_sach_luu = []
                    danh_sach_ca_mau = ["7h00 - 9h00", "9h00 - 11h00", "13h30 - 15h30", "15h30 - 17h30", "17h30 - 19h30", "19h30 - 21h30"]
                    
                    for idx, row in target_students.iterrows():
                        st.markdown(f"**👤 {row['ho_ten']}**")
                        c1, c2, c3 = st.columns([2, 3, 4])
                        default_ca = row['ca_hoc'] if 'ca_hoc' in row and row['ca_hoc'] in danh_sach_ca_mau else "17h30 - 19h30"
                        
                        with c1: ca_val = st.selectbox("Ca học", danh_sach_ca_mau, index=danh_sach_ca_mau.index(default_ca) if default_ca in danh_sach_ca_mau else 4, key=f"ca_cls_{row['hoc_sinh_id']}")
                        with c2: stt_val = st.radio("Trạng thái", ["Có mặt", "Vắng có phép", "Vắng không phép"], index=0, key=f"stt_cls_{row['hoc_sinh_id']}", horizontal=True)
                        with c3: nx_val = st.text_input("Nhận xét nhanh", key=f"nx_cls_{row['hoc_sinh_id']}", placeholder="Nhận xét bài học...")
                        
                        danh_sach_luu.append({"hs_id": int(row['hoc_sinh_id']), "ngay": ngay_hoc.strftime("%Y-%m-%d"), "ca": ca_val, "stt": stt_val, "nx": nx_val})
                        st.divider()
                        
                    if st.form_submit_button(f"💾 LƯU ĐIỂM DANH CHO CẢ LỚP ({len(target_students)} HS)", type="primary"):
                        with engine.begin() as conn:
                            for item in danh_sach_luu:
                                conn.execute(text("INSERT INTO diem_danh (hoc_sinh_id, ngay, ca_hoc, trang_thai, nhan_xet) VALUES (:hs_id, :ngay, :ca, :stt, :nx)"), item)
                        st.success(f"✅ Đã lưu điểm danh Lớp {selected_class}!")
                        st.rerun()

    else:
        df_all_hs = pd.read_sql_query("SELECT id AS hoc_sinh_id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", engine)
        if not df_all_hs.empty:
            student_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['hoc_sinh_id']}": row['hoc_sinh_id'] for _, row in df_all_hs.iterrows()}
            selected_label = st.selectbox("Chọn học sinh điểm danh", list(student_dict.keys()))
            selected_hs_id = student_dict[selected_label]
            
            with st.form("single_student_attendance"):
                col1, col2 = st.columns(2)
                with col1:
                    danh_sach_ca = ["7h00 - 9h00", "9h00 - 11h00", "13h30 - 15h30", "15h30 - 17h30", "17h30 - 19h30", "19h30 - 21h30"]
                    ca_hoc_final = st.selectbox("Chọn ca học", danh_sach_ca, index=4)
                with col2:
                    trang_thai = st.radio("Trạng thái", ["Có mặt", "Vắng có phép", "Vắng không phép"], horizontal=True)
                    nhan_xet_text = st.text_area("Nhận xét", placeholder="Nhận xét bài làm...", height=80)
                    
                if st.form_submit_button("💾 Lưu Điểm Danh Học Sinh Này", type="primary"):
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO diem_danh (hoc_sinh_id, ngay, ca_hoc, trang_thai, nhan_xet) VALUES (:hs_id, :ngay, :ca, :st, :nx)"),
                                     {"hs_id": int(selected_hs_id), "ngay": ngay_hoc.strftime("%Y-%m-%d"), "ca": ca_hoc_final, "st": trang_thai, "nx": nhan_xet_text})
                    st.success("✅ Đã ghi nhận thành công!")

# --- CHỨC NĂNG 2: MA TRẬN LỊCH HỌC TỔNG QUAN & MINDMAP ---
elif choice == "2. 🗺️ Ma Trận Lịch Học & Mindmap Tuần":
    st.subheader("🗺️ Thời Khóa Biểu Tuần & Sơ Đồ Mindmap")
    df_mindmap = pd.read_sql_query(text('''
        SELECT l.thu, l.ca_hoc, h.lop_hoc, h.mon_hoc, h.ho_ten
        FROM lich_hoc_tuan l
        JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
        ORDER BY 
            CASE l.thu
                WHEN 'Thứ 2' THEN 1 WHEN 'Thứ 3' THEN 2 WHEN 'Thứ 4' THEN 3
                WHEN 'Thứ 5' THEN 4 WHEN 'Thứ 6' THEN 5 WHEN 'Thứ 7' THEN 6 WHEN 'Chủ Nhật' THEN 7
            END, l.ca_hoc, h.lop_hoc
    '''), engine)
    
    if df_mindmap.empty:
        st.info("💡 Chưa có lịch học tuần nào được thiết lập.")
    else:
        st.markdown("### 📊 Bảng Thời Khóa Biểu Ma Trận Theo Tuần")
        render_schedule_matrix()

# --- CHỨC NĂNG 3: LÊN LỊCH HỌC ---
elif choice == "3. 📅 Lên Lịch Học (Gốc & Tạm Thời)":
    tab_goc, tab_tam = st.tabs(["📅 1. Lịch Học Gốc Hàng Tuần", "⏳ 2. Lịch Học Tạm Thời"])
    
    with tab_goc:
        st.subheader("📅 Xếp Lịch Học Cố Định Hàng Tuần (Lịch Gốc)")
        df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", engine)
        
        if df_hs.empty:
            st.warning("Chưa có học sinh.")
        else:
            all_lops = df_hs['lop_hoc'].unique().tolist()
            selected_lop = st.selectbox("Chọn Lớp để xếp lịch gốc", all_lops, key="select_goc_lop")
            target_hs_ids = df_hs[df_hs['lop_hoc'] == selected_lop]['id'].tolist()
            
            cac_thu = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
            danh_sach_ca_mau = ["7h00 - 9h00", "9h00 - 11h00", "13h30 - 15h30", "15h30 - 17h30", "17h30 - 19h30", "19h30 - 21h30"]
            
            new_schedules_class = []
            for t in cac_thu:
                col_chk, col_ca = st.columns([2, 4])
                with col_chk: has_class = st.checkbox(f"Lớp học vào **{t}**", key=f"chk_goc_lop_{t}")
                with col_ca:
                    if has_class:
                        ca_val = st.selectbox(f"Ca học {t}", danh_sach_ca_mau, index=4, key=f"ca_goc_lop_{t}")
                        new_schedules_class.append((t, ca_val))
                        
            if st.button(f"💾 Lưu Lịch Học Gốc Cho Lớp {selected_lop}", type="primary"):
                with engine.begin() as conn:
                    for hs_id in target_hs_ids:
                        conn.execute(text("DELETE FROM lich_hoc_tuan WHERE hoc_sinh_id = :id"), {"id": int(hs_id)})
                        for t_val, ca_val in new_schedules_class:
                            conn.execute(text("INSERT INTO lich_hoc_tuan (hoc_sinh_id, thu, ca_hoc) VALUES (:hs_id, :thu, :ca)"),
                                         {"hs_id": int(hs_id), "thu": t_val, "ca": ca_val})
                st.success(f"✅ Đã lưu lịch gốc cho Lớp {selected_lop}!")
                st.rerun()

    with tab_tam:
        st.subheader("⏳ Lịch Học Tạm Thời")
        df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", engine)
        if not df_hs.empty:
            all_lops = df_hs['lop_hoc'].unique().tolist()
            sel_lop_tam = st.selectbox("Chọn Lớp", all_lops)
            target_hs_ids_tam = df_hs[df_hs['lop_hoc'] == sel_lop_tam]['id'].tolist()
            
            with st.form("form_lich_tam_thoi"):
                d_start = st.date_input("🗓️ Hiệu lực TỪ ngày", date.today())
                d_end = st.date_input("🗓️ Hiệu lực ĐẾN ngày", date.today())
                loai_td = st.radio("Loại thay đổi", ["Đổi ca / Học bù", "Nghỉ tạm thời trong khoảng thời gian này"], horizontal=True)
                thu_tam = st.selectbox("Vào Thứ", ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật'])
                ca_tam = st.selectbox("Vào Ca", ["7h00 - 9h00", "9h00 - 11h00", "13h30 - 15h30", "15h30 - 17h30", "17h30 - 19h30", "19h30 - 21h30"])
                
                if st.form_submit_button("💾 Thiết Lập Lịch Tạm Thời", type="primary"):
                    with engine.begin() as conn:
                        for hs_id_item in target_hs_ids_tam:
                            conn.execute(text('''
                                INSERT INTO lich_hoc_tam_thoi (hoc_sinh_id, ngay_bat_dau, ngay_ket_thuc, thu, ca_hoc, loai_thay_doi)
                                VALUES (:hs_id, :st, :et, :thu, :ca, :loai)
                            '''), {"hs_id": int(hs_id_item), "st": d_start.strftime("%Y-%m-%d"), "et": d_end.strftime("%Y-%m-%d"), "thu": thu_tam, "ca": ca_tam, "loai": loai_td})
                    st.success("✅ Đã lưu lịch tạm thời!")
                    st.rerun()

# --- CHỨC NĂNG 4: GỢI Ý SMART ASSISTANT ---
elif choice == "4. 💡 Gợi ý Smart Assistant":
    st.subheader("💡 Gợi Ý Smart Assistant")
    st.info("🤖 Trợ lý thông minh đang hỗ trợ phân tích lịch học và nhắc nhở học phí tự động.")

# --- CHỨC NĂNG 5: THỐNG KÊ & XUẤT EXCEL ---
elif choice == "5. Thống kê & Học phí (Lọc Tháng / Xuất Excel)":
    st.subheader("📊 Thống Kê Điểm Danh & Tính Học Phí Theo Tháng")
    col_t, col_n = st.columns(2)
    with col_t: thang_selected = st.selectbox("Chọn Tháng", list(range(1, 13)), index=datetime.now().month - 1)
    with col_n: nam_selected = st.number_input("Chọn Năm", min_value=2020, max_value=2035, value=datetime.now().year)
    
    thang_nam_query = f"{nam_selected}-{thang_selected:02d}"
    is_postgres = "postgres" in st.secrets and "url" in st.secrets["postgres"]
    date_format_func = f"to_char(d.ngay, 'YYYY-MM')" if is_postgres else "strftime('%Y-%m', d.ngay)"
    
    query_thang = f'''
        SELECT 
            h.id AS "Mã HS",
            h.ho_ten AS "Họ tên",
            h.lop_hoc AS "Lớp",
            h.mon_hoc AS "Môn học",
            h.hoc_phi_buoi AS "Đơn giá/Buổi (VNĐ)",
            SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS "Số buổi có mặt",
            SUM(CASE WHEN d.trang_thai = 'Vắng có phép' THEN 1 ELSE 0 END) AS "Vắng có phép",
            SUM(CASE WHEN d.trang_thai = 'Vắng không phép' THEN 1 ELSE 0 END) AS "Vắng không phép",
            (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS "Tổng học phí (VNĐ)"
        FROM hoc_sinh h
        LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND {date_format_func} = :ym
        GROUP BY h.id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi
    '''
    df_thong_ke = pd.read_sql_query(text(query_thang), engine, params={"ym": thang_nam_query})
    st.dataframe(df_thong_ke, use_container_width=True)

# --- CHỨC NĂNG 6: QUẢN LÝ & THỐNG KÊ HỌC PHÍ (PDF) ---
elif choice == "6. Quản lý & Thống kê Học phí (Xuất PDF)":
    st.subheader("💳 Đánh Dấu Trạng Thái Đóng Học Phí Theo Tháng")
    thang = st.selectbox("Chọn Tháng", list(range(1, 13)), index=datetime.now().month - 1)
    nam = st.number_input("Chọn Năm", min_value=2020, max_value=2035, value=datetime.now().year)
    
    thang_nam_key = f"{thang:02d}/{nam}"
    thang_nam_query = f"{nam}-{thang:02d}"
    is_postgres = "postgres" in st.secrets and "url" in st.secrets["postgres"]
    date_format_func = f"to_char(d.ngay, 'YYYY-MM')" if is_postgres else "strftime('%Y-%m', d.ngay)"
    
    query_status = f'''
        SELECT 
            h.id AS hoc_sinh_id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi,
            SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS so_buoi,
            (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS tong_tien,
            COALESCE(t.trang_thai, 'Chưa đóng') AS trang_thai_dong
        FROM hoc_sinh h
        LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND {date_format_func} = :ym
        LEFT JOIN thanh_toan t ON h.id = t.hoc_sinh_id AND t.thang_nam = :tn
        GROUP BY h.id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi, t.trang_thai
    '''
    df_status = pd.read_sql_query(text(query_status), engine, params={"ym": thang_nam_query, "tn": thang_nam_key})
    
    for _, row in df_status.iterrows():
        c1, c2, c3, c4, c5 = st.columns([2, 1, 2, 2, 2])
        c1.write(f"**{row['ho_ten']}**")
        c2.write(f"{row['so_buoi']} buổi")
        c3.write(f"**{row['tong_tien']:,.0f} VNĐ**")
        is_paid = (row['trang_thai_dong'] == 'Đã đóng')
        c4.write("🟢 Đã đóng" if is_paid else "🔴 Chưa đóng")
        
        btn_label = "Chuyển sang Chưa đóng" if is_paid else "Xác nhận Đã đóng"
        if c5.button(btn_label, key=f"btn_{row['hoc_sinh_id']}"):
            new_status = 'Chưa đóng' if is_paid else 'Đã đóng'
            today_str = date.today().strftime("%Y-%m-%d") if new_status == 'Đã đóng' else ""
            with engine.begin() as conn:
                conn.execute(text('''
                    INSERT INTO thanh_toan (hoc_sinh_id, thang_nam, trang_thai, ngay_thu)
                    VALUES (:hs_id, :tn, :st, :nt)
                    ON CONFLICT(hoc_sinh_id, thang_nam) 
                    DO UPDATE SET trang_thai = EXCLUDED.trang_thai, ngay_thu = EXCLUDED.ngay_thu
                '''), {"hs_id": int(row['hoc_sinh_id']), "tn": thang_nam_key, "st": new_status, "nt": today_str})
            st.rerun()

# --- CHỨC NĂNG 7: SỬA & XÓA DỮ LIỆU ---
elif choice == "7. Sửa & Xóa dữ liệu":
    st.subheader("➕ Thêm Học Sinh Mới")
    with st.form("add_student"):
        ten = st.text_input("Họ và tên học sinh")
        lop = st.text_input("Lớp / Nhóm học", value="Toán 9")
        mon = st.text_input("Môn học", value="Toán")
        hoc_phi = st.number_input("Học phí mỗi buổi (VNĐ)", min_value=0, step=10000, value=150000)
        
        if st.form_submit_button("Thêm mới"):
            if ten:
                with engine.begin() as conn:
                    conn.execute(
                        text("INSERT INTO hoc_sinh (ho_ten, lop_hoc, mon_hoc, hoc_phi_buoi) VALUES (:ten, :lop, :mon, :hp)"),
                        {"ten": ten, "lop": lop, "mon": mon, "hp": hoc_phi}
                    )
                st.success(f"✅ Đã thêm học sinh {ten}!")
                st.rerun()
