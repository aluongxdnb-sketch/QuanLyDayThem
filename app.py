import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, datetime, timedelta
import os
import io
import re

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
            # Mật khẩu thiết lập: admin / 120809
            valid_user = st.secrets.get("USERNAME", "admin")
            valid_pass = st.secrets.get("PASSWORD", "120809")
            
            if username_input == valid_user and password_input == valid_pass:
                st.session_state.logged_in = True
                st.success("✅ Đăng nhập thành công!")
                st.rerun()
            else:
                st.error("❌ Mật khẩu hoặc Tên đăng nhập không chính xác!")
    return False

# Dừng chương trình nếu chưa đăng nhập đúng
if not check_password():
    st.stop()

# --- HÀM HỖ TRỢ THỨ TRONG TUẦN ---
def get_vietnamese_weekday(dt):
    days = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ Nhật"]
    return days[dt.weekday()]

# --- HÀM LẤY LỊCH HỌC HIỆU LỰC CHO MỘT NGÀY (CẢ LỊCH GỐC & TẠM THỜI) ---
def get_active_schedule_for_date(conn, check_date):
    target_day_str = get_vietnamese_weekday(check_date)
    date_str = check_date.strftime("%Y-%m-%d")

    query_temp = f'''
        SELECT t.hoc_sinh_id, h.ho_ten, h.lop_hoc, h.mon_hoc, t.thu, t.ca_hoc, t.loai_thay_doi
        FROM lich_hoc_tam_thoi t
        JOIN hoc_sinh h ON t.hoc_sinh_id = h.id
        WHERE t.ngay_bat_dau <= '{date_str}' AND t.ngay_ket_thuc >= '{date_str}'
    '''
    df_temp = pd.read_sql_query(query_temp, conn)
    temp_hs_ids = df_temp['hoc_sinh_id'].unique() if not df_temp.empty else []

    query_base = f'''
        SELECT l.hoc_sinh_id, h.ho_ten, h.lop_hoc, h.mon_hoc, l.ca_hoc
        FROM lich_hoc_tuan l
        JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
        WHERE l.thu = '{target_day_str}'
    '''
    df_base = pd.read_sql_query(query_base, conn)
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

# --- HÀM TỰ ĐỘNG ĐỒNG BỘ LỊCH 7 NGÀY SANG GOOGLE CALENDAR (IPHONE) ---
def sync_weekly_schedule_to_google(calendar_id='a.luongxdnb@gmail.com', days_ahead=7):
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return False, "⚠️ Chưa cài đặt thư viện Google. Vui lòng mở CMD gõ: pip install google-api-python-client google-auth"

    service_account_file = 'credentials.json'
    if not os.path.exists(service_account_file):
        return False, "⚠️ Không tìm thấy file `credentials.json` trong thư mục."

    try:
        scopes = ['https://www.googleapis.com/auth/calendar']
        creds = Credentials.from_service_account_file(service_account_file, scopes=scopes)
        service = build('calendar', 'v3', credentials=creds)

        today = date.today()
        end_date = today + timedelta(days=days_ahead)

        # 🧹 BƯỚC 1: XÓA CÁC LỊCH DẠY CŨ TRONG 7 NGÀY TỚI ĐỂ TRÁNH TRÙNG LẶP
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

        # 📤 BƯỚC 2: ĐẨY LỊCH MỚI NHẤT CỦA 7 NGÀY TỚI LÊN GOOGLE CALENDAR
        conn_sync = sqlite3.connect('quan_ly_hoc_sinh.db')
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
            df_day = get_active_schedule_for_date(conn_sync, current_date)

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

        conn_sync.close()
        return True, f"✅ Đã dọn dẹp lịch cũ & đồng bộ thành công {count_events} ca dạy trong {days_ahead} ngày tới lên iPhone!"

    except Exception as e:
        return False, f"❌ Lỗi khi đồng bộ lịch tuần: {str(e)}"

# --- HÀM SẮP XẾP CA HỌC THEO GIỜ ---
def ca_hoc_sort_key(ca_str):
    predefined = [
        "7h00 - 9h00", "9h00 - 11h00", "13h30 - 15h30", 
        "15h30 - 17h30", "17h30 - 19h30", "19h30 - 21h30"
    ]
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
        "7h00 - 9h00": "🌅 Sáng",
        "9h00 - 11h00": "🌅 Sáng",
        "13h30 - 15h30": "☀️ Chiều",
        "15h30 - 17h30": "☀️ Chiều",
        "17h30 - 19h30": "🌙 Tối",
        "19h30 - 21h30": "🌙 Tối"
    }
    if ca_str in predefined:
        return predefined[ca_str]
    
    match = re.search(r'(\d+)h?(\d*)', str(ca_str))
    if match:
        h = int(match.group(1))
        if h < 12:
            return "🌅 Sáng"
        elif h < 18:
            return "☀️ Chiều"
        else:
            return "🌙 Tối"
    return "☀️ Chiều"

# --- HÀM KIỂM TRA TRÙNG CA HỌC ---
def check_schedule_conflicts(conn, thu, ca_hoc, exclude_lop=None, exclude_hs_id=None):
    query = '''
        SELECT DISTINCT h.lop_hoc, GROUP_CONCAT(h.ho_ten, ', ') as ds_hs
        FROM lich_hoc_tuan l
        JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
        WHERE l.thu = ? AND l.ca_hoc = ?
    '''
    params = [thu, ca_hoc]
    if exclude_lop:
        query += " AND h.lop_hoc != ?"
        params.append(exclude_lop)
    if exclude_hs_id:
        query += " AND h.id != ?"
        params.append(exclude_hs_id)
    query += " GROUP BY h.lop_hoc"
    return pd.read_sql_query(query, conn, params=params)

# --- HÀM HiỂN THỊ MA TRẬN LỊCH HỌC KÈM CỘT BUỔI SÁNG/CHIỀU/TỐI ---
def render_schedule_matrix(conn):
    query_mindmap = '''
        SELECT l.thu, l.ca_hoc, h.lop_hoc, h.mon_hoc, h.ho_ten
        FROM lich_hoc_tuan l
        JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
        ORDER BY 
            CASE l.thu
                WHEN 'Thứ 2' THEN 1 WHEN 'Thứ 3' THEN 2 WHEN 'Thứ 4' THEN 3
                WHEN 'Thứ 5' THEN 4 WHEN 'Thứ 6' THEN 5 WHEN 'Thứ 7' THEN 6 WHEN 'Chủ Nhật' THEN 7
            END, l.ca_hoc, h.lop_hoc
    '''
    df_mindmap = pd.read_sql_query(query_mindmap, conn)
    
    if df_mindmap.empty:
        st.info("💡 Chưa có lịch học tuần nào được thiết lập trong hệ thống.")
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

# --- HÀM TẠO FILE PDF PHIẾU HỌC PHÍ ---
def create_tuition_pdf(student_name, lop_hoc, subject, price_per_lesson, month_year, total_lessons, total_fee, status, qr_path):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=portrait(A5),
        rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20
    )
    story = []
    
    font_path = "C:\\Windows\\Fonts\\arial.ttf"
    font_bold_path = "C:\\Windows\\Fonts\\arialbd.ttf"
    
    if os.path.exists(font_path):
        try:
            pdfmetrics.registerFont(TTFont('ArialCustom', font_path))
            f_normal = 'ArialCustom'
        except:
            f_normal = 'Helvetica'
    else:
        f_normal = 'Helvetica'
        
    if os.path.exists(font_bold_path):
        try:
            pdfmetrics.registerFont(TTFont('ArialCustomBold', font_bold_path))
            f_bold = 'ArialCustomBold'
        except:
            f_bold = 'Helvetica-Bold'
    else:
        f_bold = 'Helvetica-Bold'
        
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'TitleStyle', parent=styles['Normal'],
        fontName=f_bold, fontSize=15, leading=18, alignment=1, textColor=colors.HexColor('#1E3A8A')
    )
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontName=f_normal, fontSize=10, leading=14)
    bold_style = ParagraphStyle('BoldStyle', parent=styles['Normal'], fontName=f_bold, fontSize=10, leading=14)
    center_style = ParagraphStyle('CenterStyle', parent=styles['Normal'], fontName=f_normal, fontSize=9, leading=12, alignment=1)

    story.append(Paragraph("PHIẾU BÁO HỌC PHÍ DẠY THÊM", title_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Tháng / Năm:</b> {month_year}", ParagraphStyle('Sub', parent=center_style, fontName=f_bold, fontSize=11, leading=15)))
    story.append(Spacer(1, 10))
    
    info_data = [
        [Paragraph("<b>Họ và tên học sinh:</b>", normal_style), Paragraph(student_name, bold_style)],
        [Paragraph("<b>Lớp / Nhóm học:</b>", normal_style), Paragraph(lop_hoc, normal_style)],
        [Paragraph("<b>Môn học:</b>", normal_style), Paragraph(subject, normal_style)],
        [Paragraph("<b>Học phí / buổi:</b>", normal_style), Paragraph(f"{price_per_lesson:,.0f} VNĐ", normal_style)],
        [Paragraph("<b>Số buổi học trong tháng:</b>", normal_style), Paragraph(f"{total_lessons} buổi", normal_style)],
        [Paragraph("<b>TỔNG CỘNG HỌC PHÍ:</b>", bold_style), Paragraph(f"<b>{total_fee:,.0f} VNĐ</b>", ParagraphStyle('RedText', parent=bold_style, textColor=colors.HexColor('#B91C1C'), fontSize=11))],
        [Paragraph("<b>Trạng thái thanh toán:</b>", normal_style), Paragraph(f"<b>{status}</b>", bold_style)]
    ]
    
    info_table = Table(info_data, colWidths=[130, 230])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    
    story.append(info_table)
    story.append(Spacer(1, 8))
    
    if qr_path and os.path.exists(qr_path):
        story.append(Paragraph("<b>MÃ QR THANH TOÁN CHUYỂN KHỎAN</b>", ParagraphStyle('QRTitle', parent=center_style, fontName=f_bold, fontSize=10)))
        story.append(Spacer(1, 4))
        try:
            img = RLImage(qr_path, width=110, height=110)
            img.hAlign = 'CENTER'
            story.append(img)
            story.append(Spacer(1, 3))
            story.append(Paragraph("<i>(Vui lòng quét mã QR bằng ứng dụng Ngân hàng để chuyển khoản)</i>", center_style))
        except Exception:
            story.append(Paragraph("<i>(Lỗi hiển thị mã QR)</i>", center_style))
    else:
        story.append(Paragraph("<i>(Chưa tải lên mã QR thanh toán trong ứng dụng)</i>", center_style))
        
    story.append(Spacer(1, 10))
    story.append(Paragraph("Trân trọng cảm ơn sự đồng hành của Quý phụ huynh!", ParagraphStyle('Thanks', parent=center_style, fontName=f_bold, fontSize=10, textColor=colors.HexColor('#1E3A8A'))))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# --- 1. KHỞI TẠO CƠ SỞ DỮ LIỆU ---
conn = sqlite3.connect('quan_ly_hoc_sinh.db', check_same_thread=False)
c = conn.cursor()

c.execute('''
    CREATE TABLE IF NOT EXISTS hoc_sinh (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ho_ten TEXT NOT NULL,
        lop_hoc TEXT DEFAULT 'Lớp chung',
        mon_hoc TEXT,
        hoc_phi_buoi REAL NOT NULL
    )
''')

c.execute('''
    CREATE TABLE IF NOT EXISTS diem_danh (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hoc_sinh_id INTEGER,
        ngay DATE,
        ca_hoc TEXT DEFAULT '7h00 - 9h00',
        trang_thai TEXT DEFAULT 'Có mặt',
        nhan_xet TEXT,
        FOREIGN KEY (hoc_sinh_id) REFERENCES hoc_sinh (id)
    )
''')

c.execute('''
    CREATE TABLE IF NOT EXISTS thanh_toan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hoc_sinh_id INTEGER,
        thang_nam TEXT,
        trang_thai TEXT DEFAULT 'Chưa đóng',
        ngay_thu TEXT,
        UNIQUE(hoc_sinh_id, thang_nam)
    )
''')

c.execute('''
    CREATE TABLE IF NOT EXISTS lich_hoc_tuan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hoc_sinh_id INTEGER,
        thu TEXT,
        ca_hoc TEXT,
        UNIQUE(hoc_sinh_id, thu, ca_hoc),
        FOREIGN KEY (hoc_sinh_id) REFERENCES hoc_sinh (id)
    )
''')

c.execute('''
    CREATE TABLE IF NOT EXISTS lich_hoc_tam_thoi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hoc_sinh_id INTEGER,
        ngay_bat_dau DATE,
        ngay_ket_thuc DATE,
        thu TEXT,
        ca_hoc TEXT,
        loai_thay_doi TEXT DEFAULT 'Đổi ca / Học bù',
        FOREIGN KEY (hoc_sinh_id) REFERENCES hoc_sinh (id)
    )
''')

try:
    c.execute("ALTER TABLE hoc_sinh ADD COLUMN lop_hoc TEXT DEFAULT 'Lớp chung'")
except:
    pass

try:
    c.execute("ALTER TABLE diem_danh ADD COLUMN trang_thai TEXT DEFAULT 'Có mặt'")
except:
    pass

try:
    c.execute("ALTER TABLE diem_danh ADD COLUMN ca_hoc TEXT DEFAULT '7h00 - 9h00'")
except:
    pass

conn.commit()

# --- 2. GIAO DIỆN CHÍNH ---
st.title("📚 Phần Mềm Quản Lý Dạy Thêm Tại Nhà")

# NÚT ĐĂNG XUẤT TRÊN SIDEBAR
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
user_gmail = st.sidebar.text_input("Địa chỉ Gmail trên iPhone:", value="a.luongxdnb@gmail.com", help="Gmail đăng nhập trên ứng dụng Google Calendar trên điện thoại iPhone")

if st.sidebar.button("🔄 Đồng Bổ Lịch 7 Ngày Tới Sang iPhone", type="primary"):
    target_cal_id = user_gmail.strip() if user_gmail.strip() else 'primary'
    success, msg = sync_weekly_schedule_to_google(calendar_id=target_cal_id, days_ahead=7)
    if success:
        st.sidebar.success(msg)
    else:
        st.sidebar.error(msg)

# --- SIDEBAR: CÀI ĐẶT MÃ QR ---
st.sidebar.markdown("---")
st.sidebar.subheader("📷 Cài đặt Mã QR Thanh Toán")
qr_file = st.sidebar.file_uploader("Tải lên ảnh Mã QR (VietQR/STK)", type=["png", "jpg", "jpeg"])
if qr_file is not None:
    with open("qr_code.png", "wb") as f:
        f.write(qr_file.getbuffer())
    st.sidebar.success("✅ Đã lưu mã QR thành công!")

if os.path.exists("qr_code.png"):
    st.sidebar.image("qr_code.png", caption="Mã QR thanh toán hiện tại", use_container_width=True)

# --- CHỨC NĂNG 1: ĐIỂM DANH & NHẬN XÉT ---
if choice == "1. Điểm danh & Nhận xét":
    st.subheader("📝 Điểm Danh & Nhận Xét Buổi Học")
    
    ngay_hoc = st.date_input("🗓️ Chọn ngày điểm danh", date.today())
    thu_hom_nay = get_vietnamese_weekday(ngay_hoc)
    st.caption(f"Ngày được chọn: **{ngay_hoc.strftime('%d/%m/%Y')} ({thu_hom_nay})**")
    
    df_active_today = get_active_schedule_for_date(conn, ngay_hoc)
    type_mode = st.radio("Chế độ điểm danh", ["🏫 Điểm danh theo LỚP (Tự động mặc định Có Mặt)", "👤 Điểm danh từng HỌC SINH"], horizontal=True)
    st.divider()
    
    if type_mode.startswith("🏫"):
        sub_mode_class = st.radio("Tùy chọn danh sách Lớp:", ["🏫 Lớp có lịch hôm nay", "📚 Tất cả các lớp trong hệ thống"], horizontal=True)
        df_all_hs = pd.read_sql_query("SELECT id AS hoc_sinh_id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", conn)
        
        if df_all_hs.empty:
            st.warning("⚠️ Chưa có học sinh nào trong cơ sở dữ liệu!")
        else:
            if sub_mode_class == "🏫 Lớp có lịch hôm nay":
                available_classes = df_active_today['lop_hoc'].unique().tolist() if not df_active_today.empty else []
                if not available_classes:
                    st.info(f"💡 Hôm nay ({thu_hom_nay}) không có lớp nào có lịch học theo thời khóa biểu. Bạn có thể chọn 'Tất cả các lớp' nếu dạy bù!")
            else:
                available_classes = df_all_hs['lop_hoc'].unique().tolist()
                
            if available_classes:
                selected_class = st.selectbox("Chọn Lớp cần điểm danh", available_classes)
                
                if sub_mode_class == "🏫 Lớp có lịch hôm nay":
                    target_students = df_active_today[df_active_today['lop_hoc'] == selected_class]
                else:
                    target_students = df_all_hs[df_all_hs['lop_hoc'] == selected_class]
                    
                st.markdown(f"#### 📋 Bảng Điểm Danh Lớp: **{selected_class}** ({len(target_students)} học sinh)")
                st.info("💡 Tất cả học sinh trong lớp được mặc định **'Có mặt'**. Bạn chỉ cần thay đổi những bạn vắng học!")
                
                with st.form("mass_class_attendance"):
                    danh_sach_luu = []
                    danh_sach_ca_mau = ["7h00 - 9h00", "9h00 - 11h00", "13h30 - 15h30", "15h30 - 17h30", "17h30 - 19h30", "19h30 - 21h30"]
                    
                    for idx, row in target_students.iterrows():
                        st.markdown(f"**👤 {row['ho_ten']}**")
                        c1, c2, c3 = st.columns([2, 3, 4])
                        default_ca = row['ca_hoc'] if 'ca_hoc' in row and row['ca_hoc'] in danh_sach_ca_mau else "17h30 - 19h30"
                        
                        with c1:
                            ca_val = st.selectbox("Ca học", danh_sach_ca_mau, index=danh_sach_ca_mau.index(default_ca) if default_ca in danh_sach_ca_mau else 4, key=f"ca_cls_{row['hoc_sinh_id']}")
                        with c2:
                            stt_val = st.radio("Trạng thái", ["Có mặt", "Vắng có phép", "Vắng không phép"], index=0, key=f"stt_cls_{row['hoc_sinh_id']}", horizontal=True)
                        with c3:
                            nx_val = st.text_input("Nhận xét nhanh", key=f"nx_cls_{row['hoc_sinh_id']}", placeholder="Nhận xét bài học...")
                        
                        danh_sach_luu.append((row['hoc_sinh_id'], ngay_hoc.strftime("%Y-%m-%d"), ca_val, stt_val, nx_val))
                        st.divider()
                        
                    if st.form_submit_button(f"💾 LƯU ĐIỂM DANH CHO CẢ LỚP ({len(target_students)} HS)", type="primary"):
                        for item in danh_sach_luu:
                            c.execute("INSERT INTO diem_danh (hoc_sinh_id, ngay, ca_hoc, trang_thai, nhan_xet) VALUES (?, ?, ?, ?, ?)", item)
                        conn.commit()
                        st.success(f"✅ Đã ghi nhận điểm danh thành công cho Lớp {selected_class} ngày {ngay_hoc.strftime('%d/%m/%Y')}!")
                        st.rerun()

    else:
        sub_mode_student = st.radio("Tùy chọn danh sách Học sinh:", ["📅 Học sinh có lịch hôm nay", "👥 Tất cả học sinh trong hệ thống"], horizontal=True)
        df_all_hs = pd.read_sql_query("SELECT id AS hoc_sinh_id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", conn)
        
        if df_all_hs.empty:
            st.warning("Chưa có học sinh nào!")
        else:
            if sub_mode_student == "📅 Học sinh có lịch hôm nay":
                target_hs = df_active_today
                if target_hs.empty:
                    st.info(f"💡 Hôm nay ({thu_hom_nay}) không có học sinh nào có lịch theo thời khóa biểu.")
            else:
                target_hs = df_all_hs
                
            if not target_hs.empty:
                student_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['hoc_sinh_id']}": row['hoc_sinh_id'] for _, row in target_hs.iterrows()}
                selected_label = st.selectbox("Chọn học sinh điểm danh", list(student_dict.keys()))
                selected_hs_id = student_dict[selected_label]
                
                hs_row = target_hs[target_hs['hoc_sinh_id'] == selected_hs_id].iloc[0]
                default_ca = hs_row['ca_hoc'] if 'ca_hoc' in hs_row else "17h30 - 19h30"
                
                with st.form("single_student_attendance"):
                    col1, col2 = st.columns(2)
                    with col1:
                        danh_sach_ca = ["7h00 - 9h00", "9h00 - 11h00", "13h30 - 15h30", "15h30 - 17h30", "17h30 - 19h30", "19h30 - 21h30", "⏰ Tùy chỉnh (Nhập giờ khác)"]
                        ca_hoc_selected = st.selectbox("Chọn ca học", danh_sach_ca, index=danh_sach_ca.index(default_ca) if default_ca in danh_sach_ca else 4)
                        if ca_hoc_selected == "⏰ Tùy chỉnh (Nhập giờ khác)":
                            ca_hoc_final = st.text_input("Nhập giờ tùy chỉnh", value="8h00 - 10h00")
                        else:
                            ca_hoc_final = ca_hoc_selected
                    with col2:
                        trang_thai = st.radio("Trạng thái", ["Có mặt", "Vắng có phép", "Vắng không phép"], horizontal=True)
                        nhan_xet_text = st.text_area("Nhận xét", placeholder="Nhận xét bài làm...", height=80)
                        
                    if st.form_submit_button("💾 Lưu Điểm Danh Học Sinh Này", type="primary"):
                        c.execute("INSERT INTO diem_danh (hoc_sinh_id, ngay, ca_hoc, trang_thai, nhan_xet) VALUES (?, ?, ?, ?, ?)",
                                  (selected_hs_id, ngay_hoc.strftime("%Y-%m-%d"), ca_hoc_final, trang_thai, nhan_xet_text))
                        conn.commit()
                        st.success(f"✅ Đã ghi nhận cho học sinh {selected_label.split(' [')[0]}!")

# --- CHỨC NĂNG 2: MA TRẬN LỊCH HỌC TỔNG QUAN & MINDMAP ---
elif choice == "2. 🗺️ Ma Trận Lịch Học & Mindmap Tuần":
    st.subheader("🗺️ Thời Khóa Biểu Tuần & Sơ Đồ Mindmap")
    
    query_mindmap = '''
        SELECT l.thu, l.ca_hoc, h.lop_hoc, h.mon_hoc, h.ho_ten
        FROM lich_hoc_tuan l
        JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
        ORDER BY 
            CASE l.thu
                WHEN 'Thứ 2' THEN 1 WHEN 'Thứ 3' THEN 2 WHEN 'Thứ 4' THEN 3
                WHEN 'Thứ 5' THEN 4 WHEN 'Thứ 6' THEN 5 WHEN 'Thứ 7' THEN 6 WHEN 'Chủ Nhật' THEN 7
            END, l.ca_hoc, h.lop_hoc
    '''
    df_mindmap = pd.read_sql_query(query_mindmap, conn)
    
    if df_mindmap.empty:
        st.info("💡 Chưa có lịch học tuần nào được thiết lập. Vui lòng vào mục **'3. 📅 Lên Lịch Học'** để xếp ca!")
    else:
        tab_matrix, tab_graph = st.tabs(["📊 1. Ma Trận Lịch Học (Phân Loại Buổi Sáng / Chiều / Tối)", "🌳 2. Mindmap Đồ Họa Cây (Zoom To / Nhỏ)"])
        
        with tab_matrix:
            st.markdown("### 📊 Bảng Thời Khóa Biểu Ma Trận Theo Tuần")
            render_schedule_matrix(conn)

        with tab_graph:
            col_z1, col_z2 = st.columns([2, 3])
            with col_z1:
                zoom_level = st.slider("🔍 Kích thước / Thu phóng Mindmap (%)", min_value=50, max_value=250, value=100, step=10)
            
            dpi_val = int(96 * (zoom_level / 100))
            
            dot_code = f"""
            digraph MindmapLichHoc {{
                rankdir=LR;
                graph [dpi={dpi_val}];
                node [shape=rectangle, style="filled,rounded", fontname="Arial", color="#0284C7", fillcolor="#E0F2FE", fontsize=10];
                edge [color="#0284C7", arrowhead=vee];
                ROOT [label="📚 LỊCH DẠY THÊM\\nTỔNG QUAN", fillcolor="#0284C7", fontcolor="white", fontsize=12, style="filled,bold"];
            """
            node_id = 0
            for thu, group_thu in df_mindmap.groupby('thu', sort=False):
                node_id += 1
                thu_node = f"thu_{node_id}"
                dot_code += f'\n    "{thu_node}" [label="{thu}", fillcolor="#0284C7", fontcolor="white", style="filled,bold"];'
                dot_code += f'\n    ROOT -> "{thu_node}";'
                
                for ca, group_ca in group_thu.groupby('ca_hoc', sort=False):
                    node_id += 1
                    ca_node = f"ca_{node_id}"
                    dot_code += f'\n    "{ca_node}" [label="⏰ Ca: {ca}", fillcolor="#BAE6FD", fontcolor="#0369A1", style="filled,bold"];'
                    dot_code += f'\n    "{thu_node}" -> "{ca_node}";'
                    
                    for lop, group_lop in group_ca.groupby('lop_hoc', sort=False):
                        node_id += 1
                        lop_node = f"lop_{node_id}"
                        ds_hs = "\\n• " + "\\n• ".join(group_lop['ho_ten'].tolist())
                        label_lop = f"🏫 Lớp: {lop} ({len(group_lop)} HS){ds_hs}"
                        
                        dot_code += f'\n    "{lop_node}" [label="{label_lop}", fillcolor="#F1F5F9", fontcolor="#0F172A", align="left"];'
                        dot_code += f'\n    "{ca_node}" -> "{lop_node}";'
            
            dot_code += "\n}"
            
            st.markdown('<div style="overflow-x: auto; overflow-y: auto; max-height: 850px; border: 1px solid #CBD5E1; padding: 15px; border-radius: 8px; background-color: #FFFFFF;">', unsafe_allow_html=True)
            st.graphviz_chart(dot_code, use_container_width=(zoom_level <= 100))
            st.markdown('</div>', unsafe_allow_html=True)

# --- CHỨC NĂNG 3: LÊN LỊCH HỌC ---
elif choice == "3. 📅 Lên Lịch Học (Gốc & Tạm Thời)":
    tab_goc, tab_tam = st.tabs(["📅 1. Lịch Học Gốc Hàng Tuần", "⏳ 2. Lịch Học Tạm Thời (Có Hiệu Lực Tự Động)"])
    
    with tab_goc:
        st.subheader("📅 Xếp Lịch Học Cố Định Hàng Tuần (Lịch Gốc)")
        df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", conn)
        
        if df_hs.empty:
            st.warning("Chưa có học sinh nào. Hãy thêm học sinh trước!")
        else:
            mode_goc = st.radio("Chế độ thiết lập lịch gốc:", ["🏫 Theo LỚP (Áp dụng cho tất cả HS trong lớp)", "👤 Theo từng HỌC SINH"], horizontal=True)
            cac_thu = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
            danh_sach_ca_mau = ["7h00 - 9h00", "9h00 - 11h00", "13h30 - 15h30", "15h30 - 17h30", "17h30 - 19h30", "19h30 - 21h30"]

            if mode_goc.startswith("🏫"):
                all_lops = df_hs['lop_hoc'].unique().tolist()
                selected_lop = st.selectbox("Chọn Lớp để xếp lịch gốc", all_lops, key="select_goc_lop")
                target_hs_ids = df_hs[df_hs['lop_hoc'] == selected_lop]['id'].tolist()
                st.info(f"💡 Lịch học này sẽ được áp dụng đồng thời cho **{len(target_hs_ids)} học sinh** thuộc lớp **{selected_lop}**.")
                
                sample_hs_id = target_hs_ids[0]
                df_curr_schedule = pd.read_sql_query(f"SELECT thu, ca_hoc FROM lich_hoc_tuan WHERE hoc_sinh_id={sample_hs_id}", conn)
                
                new_schedules_class = []
                st.markdown("#### ⚙️ Chọn các ngày học cố định cho lớp:")
                for t in cac_thu:
                    curr_row = df_curr_schedule[df_curr_schedule['thu'] == t]
                    is_checked = not curr_row.empty
                    curr_ca = curr_row.iloc[0]['ca_hoc'] if is_checked else "17h30 - 19h30"
                    
                    col_chk, col_ca = st.columns([2, 4])
                    with col_chk:
                        has_class = st.checkbox(f"Lớp học vào **{t}**", value=is_checked, key=f"chk_goc_lop_{t}")
                    with col_ca:
                        if has_class:
                            ca_val = st.selectbox(f"Ca học {t}", danh_sach_ca_mau, index=danh_sach_ca_mau.index(curr_ca) if curr_ca in danh_sach_ca_mau else 4, key=f"ca_goc_lop_{t}")
                            new_schedules_class.append((t, ca_val))
                            
                            conflicts = check_schedule_conflicts(conn, t, ca_val, exclude_lop=selected_lop)
                            if not conflicts.empty:
                                for _, cf in conflicts.iterrows():
                                    st.warning(f"⚠️ **CẢNH BÁO TRÙNG CA:** Vào **{t} ({ca_val})**, lớp **{cf['lop_hoc']}** ({cf['ds_hs']}) cũng đang chọn ca này!")
                            
                if st.button(f"💾 Lưu Lịch Học Gốc Cho Lớp {selected_lop}", type="primary"):
                    for hs_id in target_hs_ids:
                        c.execute("DELETE FROM lich_hoc_tuan WHERE hoc_sinh_id=?", (hs_id,))
                        for t_val, ca_val in new_schedules_class:
                            c.execute("INSERT INTO lich_hoc_tuan (hoc_sinh_id, thu, ca_hoc) VALUES (?, ?, ?)", (hs_id, t_val, ca_val))
                    conn.commit()
                    st.success(f"✅ Đã lưu thành công lịch học gốc cho cả lớp {selected_lop}!")
                    st.rerun()

            else:
                hs_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row['id'] for _, row in df_hs.iterrows()}
                selected_hs_label = st.selectbox("Chọn học sinh cần xếp lịch gốc", list(hs_dict.keys()), key="select_goc_hs")
                selected_hs_id = hs_dict[selected_hs_label]
                df_curr_schedule = pd.read_sql_query(f"SELECT thu, ca_hoc FROM lich_hoc_tuan WHERE hoc_sinh_id={selected_hs_id}", conn)
                
                new_schedules = []
                st.markdown("#### ⚙️ Chọn các ngày học cố định:")
                for t in cac_thu:
                    curr_row = df_curr_schedule[df_curr_schedule['thu'] == t]
                    is_checked = not curr_row.empty
                    curr_ca = curr_row.iloc[0]['ca_hoc'] if is_checked else "17h30 - 19h30"
                    
                    col_chk, col_ca = st.columns([2, 4])
                    with col_chk:
                        has_class = st.checkbox(f"Học vào **{t}**", value=is_checked, key=f"chk_goc_{t}")
                    with col_ca:
                        if has_class:
                            ca_val = st.selectbox(f"Ca học {t}", danh_sach_ca_mau, index=danh_sach_ca_mau.index(curr_ca) if curr_ca in danh_sach_ca_mau else 4, key=f"ca_goc_{t}")
                            new_schedules.append((selected_hs_id, t, ca_val))
                            
                            conflicts = check_schedule_conflicts(conn, t, ca_val, exclude_hs_id=selected_hs_id)
                            if not conflicts.empty:
                                for _, cf in conflicts.iterrows():
                                    st.warning(f"⚠️ **CẢNH BÁO TRÙNG CA:** Vào **{t} ({ca_val})**, lớp **{cf['lop_hoc']}** ({cf['ds_hs']}) đang học!")
                            
                if st.button("💾 Lưu Lịch Học Gốc", type="primary"):
                    c.execute("DELETE FROM lich_hoc_tuan WHERE hoc_sinh_id=?", (selected_hs_id,))
                    for item in new_schedules:
                        c.execute("INSERT INTO lich_hoc_tuan (hoc_sinh_id, thu, ca_hoc) VALUES (?, ?, ?)", item)
                    conn.commit()
                    st.success("✅ Đã lưu lịch học gốc thành công!")
                    st.rerun()

        st.divider()
        st.markdown("### 📊 MA TRẬN LỊCH HỌC TOÀN HỆ THỐNG (Cập nhật trực tiếp)")
        st.caption("*(Dưới đây là ma trận lịch học tổng quan giúp cô theo dõi ca trống / trùng ngay khi chọn ca cho lớp)*")
        render_schedule_matrix(conn)

    with tab_tam:
        st.subheader("⏳ Thiết Lập Lịch Học Tạm Thời (Đổi Ca / Học Bù / Nghỉ Tạm Thời)")
        df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", conn)
        
        if df_hs.empty:
            st.warning("Chưa có học sinh.")
        else:
            mode_tam = st.radio("Chế độ thiết lập lịch tạm thời:", ["🏫 Theo LỚP", "👤 Theo từng HỌC SINH"], horizontal=True)
            
            with st.form("form_lich_tam_thoi"):
                if mode_tam.startswith("🏫"):
                    all_lops = df_hs['lop_hoc'].unique().tolist()
                    sel_lop_tam = st.selectbox("Chọn Lớp", all_lops)
                    target_hs_ids_tam = df_hs[df_hs['lop_hoc'] == sel_lop_tam]['id'].tolist()
                else:
                    hs_dict_tam = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row['id'] for _, row in df_hs.iterrows()}
                    sel_hs_tam = st.selectbox("Chọn học sinh", list(hs_dict_tam.keys()))
                    target_hs_ids_tam = [hs_dict_tam[sel_hs_tam]]
                
                c_d1, c_d2 = st.columns(2)
                with c_d1:
                    d_start = st.date_input("🗓️ Hiệu lực TỪ ngày", date.today())
                with c_d2:
                    d_end = st.date_input("🗓️ Hiệu lực ĐẾN ngày", date.today())
                    
                loai_td = st.radio("Loại thay đổi", ["Đổi ca / Học bù", "Nghỉ tạm thời trong khoảng thời gian này"], horizontal=True)
                
                if loai_td == "Đổi ca / Học bù":
                    c_t1, c_t2 = st.columns(2)
                    with c_t1:
                        thu_tam = st.selectbox("Vào Thứ", ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật'])
                    with c_t2:
                        ca_tam = st.selectbox("Vào Ca", ["7h00 - 9h00", "9h00 - 11h00", "13h30 - 15h30", "15h30 - 17h30", "17h30 - 19h30", "19h30 - 21h30"])
                    
                    ex_lop = sel_lop_tam if mode_tam.startswith("🏫") else None
                    ex_hs = None if mode_tam.startswith("🏫") else target_hs_ids_tam[0]
                    conflicts_tam = check_schedule_conflicts(conn, thu_tam, ca_tam, exclude_lop=ex_lop, exclude_hs_id=ex_hs)
                    if not conflicts_tam.empty:
                        for _, cf in conflicts_tam.iterrows():
                            st.warning(f"⚠️ **CẢNH BÁO TRÙNG CA:** Lớp **{cf['lop_hoc']}** ({cf['ds_hs']}) đang có lịch gốc ca **{thu_tam} - {ca_tam}**!")
                else:
                    thu_tam = "Cả tuần"
                    ca_tam = "Nghỉ"
                    
                if st.form_submit_button("💾 Thiết Lập Lịch Tạm Thời", type="primary"):
                    for hs_id_item in target_hs_ids_tam:
                        c.execute('''
                            INSERT INTO lich_hoc_tam_thoi (hoc_sinh_id, ngay_bat_dau, ngay_ket_thuc, thu, ca_hoc, loai_thay_doi)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (hs_id_item, d_start.strftime("%Y-%m-%d"), d_end.strftime("%Y-%m-%d"), thu_tam, ca_tam, loai_td))
                    conn.commit()
                    st.success("✅ Đã thêm lịch học tạm thời!")
                    st.rerun()

            st.divider()
            st.markdown("#### 📋 Danh sách Lịch Học Tạm Thời Đang Có:")
            df_tam_list = pd.read_sql_query('''
                SELECT t.id AS 'Mã', h.ho_ten AS 'Họ tên', h.lop_hoc AS 'Lớp', t.ngay_bat_dau AS 'Từ ngày', t.ngay_ket_thuc AS 'Đến ngày', 
                       t.thu AS 'Thứ', t.ca_hoc AS 'Ca', t.loai_thay_doi AS 'Loại thay đổi'
                FROM lich_hoc_tam_thoi t
                JOIN hoc_sinh h ON t.hoc_sinh_id = h.id
                ORDER BY t.id DESC
            ''', conn)
            
            if df_tam_list.empty:
                st.info("Chưa có lịch học tạm thời nào.")
            else:
                st.dataframe(df_tam_list, use_container_width=True)
                del_tam_id = st.selectbox("Chọn 'Mã' lịch tạm thời muốn XÓA", df_tam_list['Mã'].tolist())
                if st.button("❌ Xóa Lịch Tạm Thời Này"):
                    c.execute("DELETE FROM lich_hoc_tam_thoi WHERE id=?", (del_tam_id,))
                    conn.commit()
                    st.success(f"Đã xóa lịch tạm thời Mã {del_tam_id}")
                    st.rerun()

# --- CHỨC NĂNG 4: GỢI Ý SMART ASSISTANT ---
elif choice == "4. 💡 Gợi ý Smart Assistant":
    st.subheader("💡 Trợ Lý Thông Minh & Gợi Ý Dạy Học")
    
    tab_sug_shift, tab_sug_student, tab_sug_teacher = st.tabs([
        "🔄 1. Gợi Ý Đổi Ca & Lên Lịch Học", 
        "📊 2. Phân Loại & Đánh Giá Học Sinh", 
        "☕ 3. Gợi Ý Thời Gian Làm Việc / Nghỉ Ngơi Cô Giáo"
    ])
    
    with tab_sug_shift:
        st.markdown("### 💡 Gợi Ý Đổi Ca & Ghép Lớp Tối Ưu")
        df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", conn)
        
        if df_hs.empty:
            st.warning("Chưa có dữ liệu học sinh.")
        else:
            hs_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row['id'] for _, row in df_hs.iterrows()}
            sel_hs_label = st.selectbox("Chọn học sinh muốn đổi ca / xếp lịch:", list(hs_dict.keys()), key="sug_hs")
            sel_hs_id = hs_dict[sel_hs_label]
            hs_info = df_hs[df_hs['id'] == sel_hs_id].iloc[0]
            
            df_hs_curr = pd.read_sql_query(f"SELECT thu, ca_hoc FROM lich_hoc_tuan WHERE hoc_sinh_id = {sel_hs_id}", conn)
            curr_slots = set(zip(df_hs_curr['thu'], df_hs_curr['ca_hoc'])) if not df_hs_curr.empty else set()
            
            st.info(f"📌 **Học sinh:** {hs_info['ho_ten']} | **Lớp:** {hs_info['lop_hoc']}")
            if curr_slots:
                slot_str = ", ".join([f"{t} ({c})" for t, c in curr_slots])
                st.caption(f"🗓️ **Lịch học hiện tại:** {slot_str}")
            else:
                st.caption("🗓️ **Lịch học hiện tại:** Chưa được xếp lịch gốc")
            
            query_same_class = f'''
                SELECT l.thu, l.ca_hoc, COUNT(l.hoc_sinh_id) as so_luong
                FROM lich_hoc_tuan l
                JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
                WHERE h.lop_hoc = '{hs_info['lop_hoc']}' AND l.hoc_sinh_id != {sel_hs_id}
                GROUP BY l.thu, l.ca_hoc
                ORDER BY so_luong DESC
            '''
            df_class_slots = pd.read_sql_query(query_same_class, conn)
            
            query_all_slots = '''
                SELECT thu, ca_hoc, COUNT(hoc_sinh_id) as tong_hs
                FROM lich_hoc_tuan
                GROUP BY thu, ca_hoc
            '''
            df_all_slots = pd.read_sql_query(query_all_slots, conn)
            
            cac_thu = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
            cac_ca = ["7h00 - 9h00", "9h00 - 11h00", "13h30 - 15h30", "15h30 - 17h30", "17h30 - 19h30", "19h30 - 21h30"]
            
            col_p1, col_p2, col_p3 = st.columns(3)
            
            with col_p1:
                st.markdown("#### 🥇 1. Ghép ca CÙNG LỚP")
                st.caption("*(Ưu tiên hàng đầu: Giúp cô dạy đồng bộ bài học)*")
                if df_class_slots.empty:
                    st.write("Chưa có bạn cùng lớp nào được xếp lịch.")
                else:
                    for _, r in df_class_slots.iterrows():
                        t_val, c_val, cnt = r['thu'], r['ca_hoc'], r['so_luong']
                        if (t_val, c_val) in curr_slots:
                            st.success(f"✅ **{t_val} | Ca {c_val}**\n\n*(Đang học cùng {cnt} bạn lớp {hs_info['lop_hoc']})*")
                        else:
                            st.info(f"👉 **{t_val} | Ca {c_val}**\n\n*(Gợi ý đổi sang ca này: Đang có {cnt} bạn cùng lớp {hs_info['lop_hoc']} học)*")

            with col_p2:
                st.markdown("#### 🥈 2. Ca VẮNG (1 - 2 HS)")
                st.caption("*(Thích hợp kèm riêng / dạy tập trung)*")
                sparse_slots = []
                for t in cac_thu:
                    for c_slot in cac_ca:
                        if (t, c_slot) in curr_slots:
                            continue
                        matched = df_all_slots[(df_all_slots['thu'] == t) & (df_all_slots['ca_hoc'] == c_slot)]
                        cnt = matched.iloc[0]['tong_hs'] if not matched.empty else 0
                        if 1 <= cnt <= 2:
                            sparse_slots.append((t, c_slot, cnt))
                
                if sparse_slots:
                    for t_item, c_item, cnt_item in sparse_slots[:5]:
                        st.warning(f"👉 **{t_item} | Ca {c_item}**\n\n*(Hiện có {cnt_item} học sinh đang học ca này)*")
                else:
                    st.write("Không có ca vắng 1-2 HS.")

            with col_p3:
                st.markdown("#### 🥉 3. Ca TRỐNG HOÀN TOÀN")
                st.caption("*(Chưa có HS nào - Tiện mở ca mới)*")
                empty_slots = []
                for t in cac_thu:
                    for c_slot in cac_ca:
                        if (t, c_slot) in curr_slots:
                            continue
                        matched = df_all_slots[(df_all_slots['thu'] == t) & (df_all_slots['ca_hoc'] == c_slot)]
                        cnt = matched.iloc[0]['tong_hs'] if not matched.empty else 0
                        if cnt == 0:
                            empty_slots.append((t, c_slot))
                
                if empty_slots:
                    for t_item, c_item in empty_slots[:5]:
                        st.success(f"🍃 **{t_item} | Ca {c_item}**\n\n*(Ca trống 0 HS - Rất thoải mái thời gian)*")
                else:
                    st.write("Tất cả các ca đều đã có HS.")

    with tab_sug_student:
        st.markdown("### 📊 Phân Loại Học Sinh Theo Mức Độ Chăm Chỉ & Học Lực")
        
        query_eval = '''
            SELECT 
                h.id, h.ho_ten, h.lop_hoc,
                COUNT(d.id) AS tong_buoi,
                SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS co_mat,
                SUM(CASE WHEN d.trang_thai = 'Vắng không phép' THEN 1 ELSE 0 END) AS vang_kp,
                GROUP_CONCAT(d.nhan_xet, ' ') AS tat_ca_nhan_xet
            FROM hoc_sinh h
            LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id
            GROUP BY h.id
        '''
        df_eval = pd.read_sql_query(query_eval, conn)
        
        if df_eval.empty or df_eval['tong_buoi'].sum() == 0:
            st.info("Chưa đủ dữ liệu điểm danh để phân tích. Hãy điểm danh thêm một vài buổi học!")
        else:
            good_list, lazy_list, weak_list, normal_list = [], [], [], []
            good_kw = ['tốt', 'giỏi', 'chăm', 'hiểu bài', 'sáng tạo', 'ngoan', 'tiến bộ', 'xuất sắc', 'tích cực']
            weak_kw = ['yếu', 'kém', 'mất căn bản', 'chưa hiểu', 'chậm', 'hổng']
            lazy_kw = ['lười', 'chưa làm', 'quên', 'không làm', 'mất tập trung', 'chơi']
            
            for _, r in df_eval.iterrows():
                total = r['tong_buoi']
                if total == 0:
                    continue
                
                rate = (r['co_mat'] / total) * 100
                notes = str(r['tat_ca_nhan_xet']).lower() if r['tat_ca_nhan_xet'] else ""
                
                cnt_good = sum(notes.count(k) for k in good_kw)
                cnt_weak = sum(notes.count(k) for k in weak_kw)
                cnt_lazy = sum(notes.count(k) for k in lazy_kw)
                
                if r['vang_kp'] >= 2 or rate < 70 or cnt_lazy >= 2:
                    lazy_list.append((r['ho_ten'], r['lop_hoc'], f"Đi học {rate:.0f}%, Vắng không phép {r['vang_kp']} buổi, Nhận xét lười/quên BTVN"))
                elif cnt_weak >= 2:
                    weak_list.append((r['ho_ten'], r['lop_hoc'], f"Có nhiều nhận xét chưa nắm vững bài/kiến thức yếu ({cnt_weak} lần)"))
                elif rate >= 85 and cnt_good >= cnt_lazy:
                    good_list.append((r['ho_ten'], r['lop_hoc'], f"Đi học đều {rate:.0f}%, hái phát biểu, nhận xét rất tốt"))
                else:
                    normal_list.append((r['ho_ten'], r['lop_hoc'], f"Đi học {rate:.0f}%, học lực ổn định"))

            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric("🌟 Chăm chỉ / Học tốt", f"{len(good_list)} HS")
            col_m2.metric("⚠️ Lười học / Vắng nhiều", f"{len(lazy_list)} HS")
            col_m3.metric("📉 Học kém / Cần bổ trợ", f"{len(weak_list)} HS")
            col_m4.metric("🟢 Học lực Ổn định", f"{len(normal_list)} HS")
            
            st.divider()
            
            st.markdown("#### 🌟 Nhóm 1: Học Sinh Chăm Chỉ / Học Tốt")
            if good_list:
                for item in good_list:
                    st.success(f"**{item[0]}** [{item[1]}] — *{item[2]}*")
                    st.caption("💡 *Lời khuyên:* Tăng cường cho bài tập nâng cao hoặc khen thưởng để động viên tinh thần.")
            else:
                st.write("Chưa có học sinh nào trong nhóm này.")
                
            st.markdown("#### ⚠️ Nhóm 2: Học Sinh Lười Học / Vắng Nhắc Nhở")
            if lazy_list:
                for item in lazy_list:
                    st.error(f"**{item[0]}** [{item[1]}] — *{item[2]}*")
                    st.caption("💡 *Lời khuyên:* Cô nên gửi tin nhắn báo cáo phụ huynh sát sao về tình hình BTVN và đi học.")
            else:
                st.write("Không có học sinh nào lười học.")

            st.markdown("#### 📉 Nhóm 3: Học Sinh Học Kém / Cần Bổ Trợ Kiến Thức")
            if weak_list:
                for item in weak_list:
                    st.warning(f"**{item[0]}** [{item[1]}] — *{item[2]}*")
                    st.caption("💡 *Lời khuyên:* Sắp xếp 1-2 buổi dạy phụ đạo/ kèm riêng ca vắng người cho học sinh này.")
            else:
                st.write("Không có học sinh nào cần hỗ trợ đặc biệt.")

    with tab_sug_teacher:
        st.markdown("### ☕ Phân Tích Cường Độ Dạy Học & Gợi Ý Nghỉ Ngơi")
        
        query_teacher = '''
            SELECT thu, ca_hoc, COUNT(hoc_sinh_id) as so_hs
            FROM lich_hoc_tuan
            GROUP BY thu, ca_hoc
        '''
        df_teacher = pd.read_sql_query(query_teacher, conn)
        
        cac_thu = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
        thu_slots = {t: 0 for t in cac_thu}
        for _, r in df_teacher.iterrows():
            thu_slots[r['thu']] += 1
            
        tong_ca_tuan = sum(thu_slots.values())
        tong_gio_tuan = tong_ca_tuan * 2
        ngay_nghi = [t for t, count in thu_slots.items() if count == 0]
        ngay_cao_dien = [t for t, count in thu_slots.items() if count >= 3]
        
        c_t1, c_t2, c_t3 = st.columns(3)
        c_t1.metric("⏱️ Tổng số giờ dạy / tuần", f"{tong_gio_tuan} Giờ ({tong_ca_tuan} ca)")
        c_t2.metric("🌴 Số ngày nghỉ hoàn toàn", f"{len(ngay_nghi)} Ngày")
        c_t3.metric("🔥 Ngày cường độ cao (≥3 ca/ngày)", f"{len(ngay_cao_dien)} Ngày")
        
        st.divider()
        st.markdown("#### 🧘 Lời Khuyên Cân Bằng Công Việc (Work-Life Balance):")
        
        if tong_gio_tuan > 24:
            st.error(f"⚠️ **CẢNH BÁO QUÁ TẢI:** Cô đang dạy {tong_gio_tuan} giờ/tuần. Cường độ này quá cao dễ gây kiệt sức!")
            st.caption("💡 *Gợi ý:* Cô nên xem xét gộp bớt các ca ít học sinh lại với nhau để tiết kiệm thời gian.")
        elif tong_gio_tuan >= 12:
            st.success(f"🟢 **CƯỜNG ĐỘ LÝ TƯỞNG:** Cô đang dạy {tong_gio_tuan} giờ/tuần ({tong_ca_tuan} ca). Mức làm việc rất cân bằng!")
        else:
            st.info(f"🍃 **LỊCH DẠY NHẸ NHÀNG:** Cô đang dạy {tong_gio_tuan} giờ/tuần. Vẫn còn nhiều khoảng trống để nhận thêm học sinh mới.")
            
        st.markdown("#### 📅 Chi tiết phân bổ theo ngày:")
        for t in cac_thu:
            count = thu_slots[t]
            if count == 0:
                st.write(f"• **{t}:** 🌴 **NGHỈ HOÀN TOÀN** (Dành thời gian soạn giáo án, nghỉ ngơi bên gia đình)")
            elif count >= 3:
                st.write(f"• **{t}:** 🔥 **DẠY {count} CA ({count*2} TIẾNG)** — *Lưu ý uống đủ nước và nghỉ 15 phút giữa các ca!*")
            else:
                st.write(f"• **{t}:** 🟢 Dạy {count} ca ({count*2} tiếng)")

# --- CHỨC NĂNG 5: THỐNG KÊ & XUẤT EXCEL ---
elif choice == "5. Thống kê & Học phí (Lọc Tháng / Xuất Excel)":
    st.subheader("📊 Thống Kê Điểm Danh & Tính Học Phí Theo Tháng")
    
    col_t, col_n = st.columns(2)
    with col_t:
        thang_selected = st.selectbox("Chọn Tháng", list(range(1, 13)), index=datetime.now().month - 1)
    with col_n:
        nam_selected = st.number_input("Chọn Năm", min_value=2020, max_value=2035, value=datetime.now().year)
    
    thang_nam_str = f"{thang_selected:02d}/{nam_selected}"
    thang_nam_query = f"{nam_selected}-{thang_selected:02d}"
    
    st.markdown(f"### 🗓️ Báo cáo Tháng {thang_nam_str}")
    
    query_thang = f'''
        SELECT 
            h.id AS 'Mã HS',
            h.ho_ten AS 'Họ tên',
            h.lop_hoc AS 'Lớp',
            h.mon_hoc AS 'Môn học',
            h.hoc_phi_buoi AS 'Đơn giá/Buổi (VNĐ)',
            SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS 'Số buổi có mặt',
            SUM(CASE WHEN d.trang_thai = 'Vắng có phép' THEN 1 ELSE 0 END) AS 'Vắng có phép',
            SUM(CASE WHEN d.trang_thai = 'Vắng không phép' THEN 1 ELSE 0 END) AS 'Vắng không phép',
            (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS 'Tổng học phí (VNĐ)'
        FROM hoc_sinh h
        LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND strftime('%Y-%m', d.ngay) = '{thang_nam_query}'
        GROUP BY h.id
    '''
    df_thong_ke = pd.read_sql_query(query_thang, conn)
    st.dataframe(df_thong_ke, use_container_width=True)
    
    csv_data = df_thong_ke.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
    st.download_button(
        label="📥 Tải Báo Cáo Tháng Này (Mở bằng Excel)",
        data=csv_data,
        file_name=f"Bao_Cao_Hoc_Phi_Thang_{thang_selected}_{nam_selected}.csv",
        mime="text/csv"
    )
    
    st.divider()
    
    st.subheader("🔍 Xem Chi Tiết Lịch Học & Nhận Xét")
    df_hs = pd.read_sql_query("SELECT id, ho_ten FROM hoc_sinh", conn)
    if not df_hs.empty:
        student_dict = {row['ho_ten']: row['id'] for _, row in df_hs.iterrows()}
        selected_hs = st.selectbox("Chọn học sinh xem lịch sử", list(student_dict.keys()))
        
        query_chi_tiet = f'''
            SELECT ngay AS 'Ngày học', ca_hoc AS 'Ca học', trang_thai AS 'Trạng thái', nhan_xet AS 'Nhận xét buổi học'
            FROM diem_danh
            WHERE hoc_sinh_id = {student_dict[selected_hs]} AND strftime('%Y-%m', ngay) = '{thang_nam_query}'
            ORDER BY ngay DESC, id DESC
        '''
        df_chi_tiet = pd.read_sql_query(query_chi_tiet, conn)
        st.table(df_chi_tiet)

# --- CHỨC NĂNG 6: QUẢN LÝ & THỐNG KÊ HỌC PHÍ (PDF) ---
elif choice == "6. Quản lý & Thống kê Học phí (Xuất PDF)":
    tab_thang, tab_hoc_sinh = st.tabs(["📅 Đóng Học Phí Theo Tháng", "👤 Thống Kê Chi Tiết Theo Học Sinh (In PDF)"])
    
    with tab_thang:
        st.subheader("💳 Đánh Dấu Trạng Thái Đóng Học Phí Theo Tháng")
        
        col1, col2 = st.columns(2)
        with col1:
            thang = st.selectbox("Chọn Tháng", list(range(1, 13)), index=datetime.now().month - 1, key="tab1_thang")
        with col2:
            nam = st.number_input("Chọn Năm", min_value=2020, max_value=2035, value=datetime.now().year, key="tab1_nam")
        
        thang_nam_key = f"{thang:02d}/{nam}"
        thang_nam_query = f"{nam}-{thang:02d}"
        
        df_hs = pd.read_sql_query("SELECT id, ho_ten, hoc_phi_buoi FROM hoc_sinh", conn)
        
        if df_hs.empty:
            st.warning("Chưa có học sinh.")
        else:
            query_status = f'''
                SELECT 
                    h.id AS hoc_sinh_id,
                    h.ho_ten,
                    SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS so_buoi,
                    (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS tong_tien,
                    COALESCE(t.trang_thai, 'Chưa đóng') AS trang_thai_dong
                FROM hoc_sinh h
                LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND strftime('%Y-%m', d.ngay) = '{thang_nam_query}'
                LEFT JOIN thanh_toan t ON h.id = t.hoc_sinh_id AND t.thang_nam = '{thang_nam_key}'
                GROUP BY h.id
            '''
            df_status = pd.read_sql_query(query_status, conn)
            
            for _, row in df_status.iterrows():
                c1, c2, c3, c4, c5 = st.columns([2, 1, 2, 2, 2])
                c1.write(f"**{row['ho_ten']}**")
                c2.write(f"{row['so_buoi']} buổi")
                c3.write(f"**{row['tong_tien']:,.0f} VNĐ**")
                
                is_paid = (row['trang_thai_dong'] == 'Đã đóng')
                status_color = "🟢 Đã đóng" if is_paid else "🔴 Chưa đóng"
                c4.write(status_color)
                
                btn_label = "Chuyển sang Chưa đóng" if is_paid else "Xác nhận Đã đóng"
                if c5.button(btn_label, key=f"btn_{row['hoc_sinh_id']}"):
                    new_status = 'Chưa đóng' if is_paid else 'Đã đóng'
                    today_str = date.today().strftime("%Y-%m-%d") if new_status == 'Đã đóng' else ""
                    
                    c.execute('''
                        INSERT INTO thanh_toan (hoc_sinh_id, thang_nam, trang_thai, ngay_thu)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(hoc_sinh_id, thang_nam) 
                        DO UPDATE SET trang_thai = excluded.trang_thai, ngay_thu = excluded.ngay_thu
                    ''', (row['hoc_sinh_id'], thang_nam_key, new_status, today_str))
                    conn.commit()
                    st.rerun()

    with tab_hoc_sinh:
        st.subheader("👤 Thống Kê & Xuất Phiếu Học Phí PDF Chi Tiết")
        
        df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc, mon_hoc, hoc_phi_buoi FROM hoc_sinh", conn)
        if df_hs.empty:
            st.warning("Chưa có học sinh trong hệ thống.")
        else:
            student_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row['id'] for _, row in df_hs.iterrows()}
            selected_hs_label = st.selectbox("Chọn học sinh cần xem thống kê học phí", list(student_dict.keys()), key="stat_hs_select")
            selected_hs_id = student_dict[selected_hs_label]
            
            hs_info = df_hs[df_hs['id'] == selected_hs_id].iloc[0]
            
            query_individual = f'''
                SELECT 
                    strftime('%m/%Y', d.ngay) AS thang_nam,
                    strftime('%Y-%m', d.ngay) AS ym_sort,
                    SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS so_buoi,
                    (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * {hs_info['hoc_phi_buoi']}) AS tong_tien
                FROM diem_danh d
                WHERE d.hoc_sinh_id = {selected_hs_id}
                GROUP BY strftime('%Y-%m', d.ngay)
                ORDER BY ym_sort DESC
            '''
            df_indiv_attendance = pd.read_sql_query(query_individual, conn)
            
            query_payments = f'''
                SELECT thang_nam, trang_thai, ngay_thu 
                FROM thanh_toan 
                WHERE hoc_sinh_id = {selected_hs_id}
            '''
            df_payments = pd.read_sql_query(query_payments, conn)
            
            if df_indiv_attendance.empty:
                st.info("Học sinh này chưa có lịch sử điểm danh buổi học nào.")
            else:
                df_merged = pd.merge(df_indiv_attendance, df_payments, on='thang_nam', how='left')
                df_merged['trang_thai'] = df_merged['trang_thai'].fillna('Chưa đóng')
                df_merged['ngay_thu'] = df_merged['ngay_thu'].fillna('-')
                
                tong_buoi_all = df_merged['so_buoi'].sum()
                tong_tien_all = df_merged['tong_tien'].sum()
                thang_da_dong = len(df_merged[df_merged['trang_thai'] == 'Đã đóng'])
                thang_chua_dong = len(df_merged[df_merged['trang_thai'] == 'Chưa đóng'])
                
                st.divider()
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Tổng buổi đã học", f"{tong_buoi_all} buổi")
                m2.metric("Tổng học phí tích lũy", f"{tong_tien_all:,.0f} VNĐ")
                m3.metric("Số tháng ĐÃ ĐÓNG", f"{thang_da_dong} tháng")
                m4.metric("Số tháng CHƯA ĐÓNG", f"{thang_chua_dong} tháng")
                st.divider()
                
                df_display = df_merged[['thang_nam', 'so_buoi', 'tong_tien', 'trang_thai', 'ngay_thu']].copy()
                df_display.columns = ['Tháng/Năm', 'Số buổi học', 'Tổng học phí (VNĐ)', 'Trạng thái', 'Ngày thu tiền']
                df_display['Tổng học phí (VNĐ)'] = df_display['Tổng học phí (VNĐ)'].apply(lambda x: f"{x:,.0f}")
                df_display['Trạng thái'] = df_display['Trạng thái'].apply(lambda x: "🟢 Đã đóng" if x == 'Đã đóng' else "🔴 Chưa đóng")
                
                st.dataframe(df_display, use_container_width=True)
                
                st.divider()
                st.markdown("#### 📄 Xuất Phiếu Báo Học Phí PDF (Kèm Mã QR)")
                
                if not HAS_REPORTLAB:
                    st.error("Chưa cài đặt `reportlab`. Hãy gõ `py -m pip install reportlab pillow` trong CMD.")
                else:
                    col_pdf1, col_pdf2 = st.columns([2, 2])
                    with col_pdf1:
                        selected_thang_pdf = st.selectbox("Chọn Tháng xuất PDF", df_merged['thang_nam'].tolist())
                    
                    with col_pdf2:
                        st.write(" ")
                        st.write(" ")
                        row_pdf = df_merged[df_merged['thang_nam'] == selected_thang_pdf].iloc[0]
                        
                        pdf_bytes = create_tuition_pdf(
                            student_name=hs_info['ho_ten'],
                            lop_hoc=hs_info['lop_hoc'],
                            subject=hs_info['mon_hoc'],
                            price_per_lesson=hs_info['hoc_phi_buoi'],
                            month_year=selected_thang_pdf,
                            total_lessons=int(row_pdf['so_buoi']),
                            total_fee=float(row_pdf['tong_tien']),
                            status=row_pdf['trang_thai'],
                            qr_path="qr_code.png" if os.path.exists("qr_code.png") else None
                        )
                        
                        file_pdf_name = f"Phieu_Hoc_Phi_{hs_info['ho_ten'].replace(' ', '_')}_Thang_{selected_thang_pdf.replace('/', '_')}.pdf"
                        
                        st.download_button(
                            label=f"📥 Tải Phiếu Học Phí PDF - Tháng {selected_thang_pdf}",
                            data=pdf_bytes,
                            file_name=file_pdf_name,
                            mime="application/pdf"
                        )

# --- CHỨC NĂNG 7: SỬA & XÓA DỮ LIỆU ---
elif choice == "7. Sửa & Xóa dữ liệu":
    tab1, tab2 = st.tabs(["👤 Quản lý Học sinh", "🗓️ Quản lý Nhật ký Điểm danh"])
    
    with tab1:
        st.subheader("➕ Thêm Học Sinh Mới")
        with st.form("add_student"):
            col_a, col_b = st.columns(2)
            with col_a:
                ten = st.text_input("Họ và tên học sinh")
                lop = st.text_input("Lớp / Nhóm học (VD: Toán 9A, Tiếng Anh K6)", value="Toán 9")
            with col_b:
                mon = st.text_input("Môn học (VD: Toán)", value="Toán")
                hoc_phi = st.number_input("Học phí mỗi buổi (VNĐ)", min_value=0, step=10000, value=150000)
            
            if st.form_submit_button("Thêm mới"):
                if ten:
                    c.execute("INSERT INTO hoc_sinh (ho_ten, lop_hoc, mon_hoc, hoc_phi_buoi) VALUES (?, ?, ?, ?)", (ten, lop, mon, hoc_phi))
                    conn.commit()
                    st.success(f"Đã thêm học sinh {ten}")
                    st.rerun()

        st.divider()
        st.subheader("✏️ Sửa / ❌ Xóa Học Sinh")
        df_hs = pd.read_sql_query("SELECT * FROM hoc_sinh", conn)
        if not df_hs.empty:
            hs_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] (ID:{row['id']})": row['id'] for _, row in df_hs.iterrows()}
            selected_hs_label = st.selectbox("Chọn học sinh cần thao tác", list(hs_dict.keys()))
            selected_id = hs_dict[selected_hs_label]
            
            curr_info = df_hs[df_hs['id'] == selected_id].iloc[0]
            
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                new_ten = st.text_input("Tên mới", value=curr_info['ho_ten'])
                new_lop = st.text_input("Lớp mới", value=curr_info['lop_hoc'])
                new_mon = st.text_input("Môn mới", value=curr_info['mon_hoc'])
                new_hp = st.number_input("Học phí mới", value=float(curr_info['hoc_phi_buoi']), step=10000.0)
                if st.button("💾 Cập nhật thông tin"):
                    c.execute("UPDATE hoc_sinh SET ho_ten=?, lop_hoc=?, mon_hoc=?, hoc_phi_buoi=? WHERE id=?", 
                              (new_ten, new_lop, new_mon, new_hp, selected_id))
                    conn.commit()
                    st.success("Đã cập nhật!")
                    st.rerun()
            
            with col_e2:
                st.warning("⚠️ Xóa học sinh sẽ xóa toàn bộ lịch sử của học sinh này!")
                if st.button("❌ XÓA HỌC SINH NÀY", type="primary"):
                    c.execute("DELETE FROM diem_danh WHERE hoc_sinh_id=?", (selected_id,))
                    c.execute("DELETE FROM thanh_toan WHERE hoc_sinh_id=?", (selected_id,))
                    c.execute("DELETE FROM lich_hoc_tuan WHERE hoc_sinh_id=?", (selected_id,))
                    c.execute("DELETE FROM lich_hoc_tam_thoi WHERE hoc_sinh_id=?", (selected_id,))
                    c.execute("DELETE FROM hoc_sinh WHERE id=?", (selected_id,))
                    conn.commit()
                    st.success("Đã xóa!")
                    st.rerun()

    with tab2:
        st.subheader("🗑️ Xóa Buổi Điểm Danh Nhầm")
        df_logs = pd.read_sql_query('''
            SELECT d.id AS 'Mã Lịch', h.ho_ten AS 'Họ Tên', h.lop_hoc AS 'Lớp', d.ngay AS 'Ngày', d.ca_hoc AS 'Ca Học', d.trang_thai AS 'Trạng Thái', d.nhan_xet AS 'Nhận Xét' 
            FROM diem_danh d 
            JOIN hoc_sinh h ON d.hoc_sinh_id = h.id 
            ORDER BY d.ngay DESC, d.id DESC
        ''', conn)
        
        if df_logs.empty:
            st.info("Chưa có dữ liệu điểm danh.")
        else:
            st.dataframe(df_logs, use_container_width=True)
            log_ids = df_logs['Mã Lịch'].tolist()
            log_to_delete = st.selectbox("Chọn 'Mã Lịch' cần xóa nhầm", log_ids)
            if st.button("❌ Xóa dòng điểm danh này"):
                c.execute("DELETE FROM diem_danh WHERE id=?", (log_to_delete,))
                conn.commit()
                st.success(f"Đã xóa điểm danh Mã Lịch {log_to_delete}")
                st.rerun()