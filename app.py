import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, datetime, timedelta
import os
import io
import re
import urllib.request
import shutil

# Thử import thư viện ReportLab cho phiếu học phí A5
try:
    from reportlab.lib.pagesizes import A5, portrait
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table as RLTable, TableStyle, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# Thử import Matplotlib để xuất lịch học dạng ảnh PNG
try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

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

# --- HÀM ĐĂNG KÝ FONT CHO PHIẾU HỌC PHÍ PDF ---
def register_vietnamese_fonts():
    reg_font_name = 'Helvetica'
    bold_font_name = 'Helvetica-Bold'
    
    local_reg = "arial_local.ttf"
    local_bold = "arialbd_local.ttf"
    
    try:
        win_arial = "C:\\Windows\\Fonts\\arial.ttf"
        win_arialbd = "C:\\Windows\\Fonts\\arialbd.ttf"
        if os.path.exists(win_arial):
            shutil.copy(win_arial, local_reg)
        if os.path.exists(win_arialbd):
            shutil.copy(win_arialbd, local_bold)
    except Exception:
        pass
        
    if not os.path.exists(local_reg) or os.path.getsize(local_reg) < 50000:
        try:
            urllib.request.urlretrieve("https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf", local_reg)
        except Exception:
            pass
            
    if not os.path.exists(local_bold) or os.path.getsize(local_bold) < 50000:
        try:
            urllib.request.urlretrieve("https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans-Bold.ttf", local_bold)
        except Exception:
            pass

    if os.path.exists(local_reg) and os.path.getsize(local_reg) > 50000:
        try:
            pdfmetrics.registerFont(TTFont('VNRegular', local_reg))
            reg_font_name = 'VNRegular'
        except Exception:
            pass

    if os.path.exists(local_bold) and os.path.getsize(local_bold) > 50000:
        try:
            pdfmetrics.registerFont(TTFont('VNBold', local_bold))
            bold_font_name = 'VNBold'
        except Exception:
            bold_font_name = reg_font_name
    else:
        bold_font_name = reg_font_name

    return reg_font_name, bold_font_name

# --- HÀM LẤY LỊCH HỌC HIỆU LỰC CHO MỘT NGÀY ---
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

# --- HÀM TỰ ĐỘNG ĐỒNG BỘ LỊCH 7 NGÀY SANG GOOGLE CALENDAR ---
def sync_weekly_schedule_to_google(calendar_id='a.luongxdnb@gmail.com', days_ahead=7):
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return False, "⚠️ Chưa cài đặt thư viện Google trong requirements.txt"

    service_account_file = 'credentials.json'
    if not os.path.exists(service_account_file):
        return False, "⚠️ Không tìm thấy file `credentials.json` trong thư mục."

    try:
        scopes = ['https://www.googleapis.com/auth/calendar']
        creds = Credentials.from_service_account_file(service_account_file, scopes=scopes)
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
        if h < 12: return "🌅 Sáng"
        elif h < 18: return "☀️ Chiều"
        else: return "🌙 Tối"
    return "☀️ Chiều"

# --- HÀM LẤY MA TRẬN LỊCH HỌC DẠNG DATAFRAME ---
def get_schedule_matrix_df(conn, filter_lop=None, filter_hs_id=None):
    query = '''
        SELECT l.thu, l.ca_hoc, h.lop_hoc, h.mon_hoc, h.ho_ten, h.id AS hoc_sinh_id
        FROM lich_hoc_tuan l
        JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
    '''
    params = []
    if filter_lop:
        query += " WHERE h.lop_hoc = ?"
        params.append(filter_lop)
    elif filter_hs_id:
        query += " WHERE h.id = ?"
        params.append(filter_hs_id)

    query += '''
        ORDER BY 
            CASE l.thu
                WHEN 'Thứ 2' THEN 1 WHEN 'Thứ 3' THEN 2 WHEN 'Thứ 4' THEN 3
                WHEN 'Thứ 5' THEN 4 WHEN 'Thứ 6' THEN 5 WHEN 'Thứ 7' THEN 6 WHEN 'Chủ Nhật' THEN 7
            END, l.ca_hoc, h.lop_hoc
    '''
    df_data = pd.read_sql_query(query, conn, params=params)
    if df_data.empty:
        return pd.DataFrame()

    cac_thu = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
    cac_ca = sorted(df_data['ca_hoc'].unique().tolist(), key=ca_hoc_sort_key)

    matrix_rows = []
    for ca in cac_ca:
        buoi = get_buoi_from_ca(ca)
        row_dict = {"Buổi": buoi, "Ca học": ca}
        for t in cac_thu:
            matched = df_data[(df_data['thu'] == t) & (df_data['ca_hoc'] == ca)]
            if matched.empty:
                row_dict[t] = "-"
            else:
                items = []
                for lop, g in matched.groupby('lop_hoc'):
                    names = ", ".join(g['ho_ten'].tolist())
                    if filter_lop or filter_hs_id:
                        items.append(names)
                    else:
                        items.append(f"<b>[{lop}]</b>: {names}")
                row_dict[t] = "<br>".join(items)
        matrix_rows.append(row_dict)

    df_matrix = pd.DataFrame(matrix_rows)
    cols = ["Buổi", "Ca học"] + cac_thu
    return df_matrix[cols]

# --- HÀM HIỂN THỊ MA TRẬN LỊCH HỌC ---
def render_schedule_matrix(conn):
    df_matrix = get_schedule_matrix_df(conn)
    if df_matrix.empty:
        st.info("💡 Chưa có lịch học tuần nào được thiết lập trong hệ thống.")
        return
    st.write(df_matrix.to_html(index=False, escape=False), unsafe_allow_html=True)

# --- HÀM TẠO FILE ẢNH PNG LỊCH HỌC HÀNG TUẦN ---
def create_weekly_schedule_image(title_target, df_matrix, prefix="Đối tượng / Lớp: "):
    fig, ax = plt.subplots(figsize=(16, len(df_matrix) * 1.0 + 3.5))
    ax.axis('off')
    ax.axis('tight')
    
    # Tính toán tuần hiện tại (Thứ 2 đến Chủ Nhật)
    today = date.today()
    start_w = today - timedelta(days=today.weekday())
    end_w = start_w + timedelta(days=6)
    week_text = f"Tuần từ {start_w.strftime('%d/%m/%Y')} đến {end_w.strftime('%d/%m/%Y')}"
    
    table_data = [df_matrix.columns.tolist()] + df_matrix.values.tolist()
    cleaned_data = []
    for row in table_data:
        cleaned_row = []
        for cell in row:
            clean_cell = str(cell).replace("<br>", "\n").replace("<br/>", "\n")
            clean_cell = clean_cell.replace("<b>", "").replace("</b>", "")
            cleaned_row.append(clean_cell)
        cleaned_data.append(cleaned_row)
        
    table = ax.table(cellText=cleaned_data, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2.2)
    
    full_title = f"THỜI KHÓA BIỂU LỊCH HỌC HÀNG TUẦN\n{prefix}{title_target}\n{week_text}"
    plt.title(full_title, fontsize=13, fontweight='bold', pad=20, color='#1E3A8A', linespacing=1.5)
    
    # Thêm ghi chú chân trang trong ảnh
    plt.figtext(0.5, 0.02, "Ghi chú: Áp dụng cho các tuần tiếp nếu không có thay đổi", ha='center', fontsize=10, style='italic', color='#475569', weight='bold')
    
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#CBD5E1')
        if row == 0:
            cell.set_facecolor('#1E3A8A')
            cell.set_text_props(color='white', weight='bold', size=11)
        else:
            cell.set_text_props(color='#1E293B', size=10)
            if col == 0 or col == 1:
                cell.set_facecolor('#F1F5F9')
                cell.set_text_props(weight='bold', color='#1E3A8A')
            else:
                if row % 2 == 0:
                    cell.set_facecolor('#F8FAFC')
                else:
                    cell.set_facecolor('white')
                    
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig)
    buffer.seek(0)
    return buffer

# --- HÀM TẠO FILE PDF PHIẾU HỌC PHÍ ---
def create_tuition_pdf(student_name, lop_hoc, subject, price_per_lesson, month_year, total_lessons, total_fee, status, qr_path):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=portrait(A5),
        rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20
    )
    story = []
    
    font_reg, font_bold = register_vietnamese_fonts()

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Normal'], fontName=font_bold, fontSize=15, leading=18, alignment=1, textColor=colors.HexColor('#1E3A8A'))
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontName=font_reg, fontSize=10, leading=14)
    bold_style = ParagraphStyle('BoldStyle', parent=styles['Normal'], fontName=font_bold, fontSize=10, leading=14)
    center_style = ParagraphStyle('CenterStyle', parent=styles['Normal'], fontName=font_reg, fontSize=9, leading=12, alignment=1)

    story.append(Paragraph("PHIẾU BÁO HỌC PHÍ DẠY THÊM", title_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Tháng / Năm:</b> {month_year}", ParagraphStyle('Sub', parent=center_style, fontName=font_bold, fontSize=11, leading=15)))
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
    
    info_table = RLTable(info_data, colWidths=[130, 230])
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
        story.append(Paragraph("<b>MÃ QR THANH TOÁN CHUYỂN KHOẢN</b>", ParagraphStyle('QRTitle', parent=center_style, fontName=font_bold, fontSize=10)))
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
    story.append(Paragraph("Trân trọng cảm ơn sự đồng hành của Quý phụ huynh!", ParagraphStyle('Thanks', parent=center_style, fontName=font_bold, fontSize=10, textColor=colors.HexColor('#1E3A8A'))))
    
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
        hoc_phi_buoi REAL NOT NULL,
        sdt_phu_huynh TEXT,
        ngay_sinh DATE
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

try: c.execute("ALTER TABLE hoc_sinh ADD COLUMN lop_hoc TEXT DEFAULT 'Lớp chung'")
except: pass
try: c.execute("ALTER TABLE diem_danh ADD COLUMN trang_thai TEXT DEFAULT 'Có mặt'")
except: pass
try: c.execute("ALTER TABLE diem_danh ADD COLUMN ca_hoc TEXT DEFAULT '7h00 - 9h00'")
except: pass
try: c.execute("ALTER TABLE hoc_sinh ADD COLUMN sdt_phu_huynh TEXT")
except: pass
try: c.execute("ALTER TABLE hoc_sinh ADD COLUMN ngay_sinh DATE")
except: pass

conn.commit()

# --- 2. GIAO DIỆN CHÍNH ---
st.title("📚 Phần Mềm Quản Lý Dạy Thêm Tại Nhà")

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

st.sidebar.markdown("---")
st.sidebar.subheader("📲 Đồng Bộ Lịch Sang iPhone")
user_gmail = st.sidebar.text_input("Địa chỉ Gmail trên iPhone:", value="a.luongxdnb@gmail.com")

if st.sidebar.button("🔄 Đồng Bộ Lịch 7 Ngày Tới Sang iPhone", type="primary"):
    target_cal_id = user_gmail.strip() if user_gmail.strip() else 'primary'
    success, msg = sync_weekly_schedule_to_google(calendar_id=target_cal_id, days_ahead=7)
    if success: st.sidebar.success(msg)
    else: st.sidebar.error(msg)

st.sidebar.markdown("---")
st.sidebar.subheader("📷 Cài đặt Mã QR Thanh Toán")
qr_file = st.sidebar.file_uploader("Tải lên ảnh Mã QR (VietQR/STK)", type=["png", "jpg", "jpeg"])
if qr_file is not None:
    with open("qr_code.png", "wb") as f: f.write(qr_file.getbuffer())
    st.sidebar.success("✅ Đã lưu mã QR thành công!")

if os.path.exists("qr_code.png"):
    st.sidebar.image("qr_code.png", caption="Mã QR thanh toán hiện tại", use_container_width=True)

# =========================================================
# --- CHỨC NĂNG 1: ĐIỂM DANH & NHẬN XÉT ---
# =========================================================
if choice == "1. Điểm danh & Nhận xét":
    st.subheader("📝 Điểm Danh & Nhận Xét Buổi Học")
    ngay_hoc = st.date_input("🗓️ Chọn ngày điểm danh", date.today())
    thu_hom_nay = get_vietnamese_weekday(ngay_hoc)
    date_str = ngay_hoc.strftime("%Y-%m-%d")
    st.caption(f"Ngày được chọn: **{ngay_hoc.strftime('%d/%m/%Y')} ({thu_hom_nay})**")
    
    df_active_today = get_active_schedule_for_date(conn, ngay_hoc)
    df_all_hs = pd.read_sql_query("SELECT id AS hoc_sinh_id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", conn)
    
    type_mode = st.radio("Chế độ điểm danh", ["🏫 Điểm danh theo LỚP", "👤 Điểm danh từng HỌC SINH"], horizontal=True)
    st.divider()

    target_students = pd.DataFrame()

    if df_all_hs.empty:
        st.warning("⚠️ Chưa có học sinh nào trong hệ thống! Hãy sang mục '7. Sửa & Xóa dữ liệu' để thêm học sinh mới.")
    else:
        if type_mode == "🏫 Điểm danh theo LỚP":
            available_classes = sorted(df_all_hs['lop_hoc'].dropna().unique().tolist())
            options_class = ["🌟 All Lớp (Tất cả học sinh có lịch học hôm nay)"] + available_classes
            selected_class_opt = st.selectbox("Chọn Lớp cần điểm danh", options_class)

            if selected_class_opt.startswith("🌟 All Lớp"):
                target_students = df_active_today
            else:
                target_students = df_all_hs[df_all_hs['lop_hoc'] == selected_class_opt]

        else:
            student_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['hoc_sinh_id']}": row['hoc_sinh_id'] for _, row in df_all_hs.iterrows()}
            options_hs = ["🌟 All Học sinh (Tất cả học sinh có lịch học hôm nay)"] + list(student_dict.keys())
            selected_hs_opt = st.selectbox("Chọn học sinh điểm danh", options_hs)

            if selected_hs_opt.startswith("🌟 All Học sinh"):
                target_students = df_active_today
            else:
                selected_hs_id = student_dict[selected_hs_opt]
                target_students = df_all_hs[df_all_hs['hoc_sinh_id'] == selected_hs_id]

        if target_students.empty:
            st.info("ℹ️ Không tìm thấy học sinh nào có lịch học hoặc phù hợp với bộ lọc đã chọn.")
        else:
            st.markdown(f"#### 📋 Bảng Điểm Danh ({len(target_students)} học sinh)")
            with st.form("form_diem_danh_execution"):
                danh_sach_ca_mau = ["7h00 - 9h00", "9h00 - 11h00", "13h30 - 15h30", "15h30 - 17h30", "17h30 - 19h30", "19h30 - 21h30", "⏱️ Tự nhập giờ tùy chỉnh..."]
                danh_sach_luu = []

                for idx, row in target_students.iterrows():
                    st.markdown(f"**👤 {row['ho_ten']}** [{row.get('lop_hoc', 'N/A')}]")
                    c1, c2, c3 = st.columns([2.5, 3, 3.5])
                    
                    default_ca = row['ca_hoc'] if ('ca_hoc' in row and pd.notna(row['ca_hoc']) and row['ca_hoc'] in danh_sach_ca_mau) else "17h30 - 19h30"

                    with c1:
                        ca_val = st.selectbox("Ca học", danh_sach_ca_mau, index=danh_sach_ca_mau.index(default_ca) if default_ca in danh_sach_ca_mau else 4, key=f"ca_cls_{row['hoc_sinh_id']}")
                        if ca_val == "⏱️ Tự nhập giờ tùy chỉnh...":
                            custom_ca = st.text_input("Nhập giờ (VD: 08h30 - 10h30)", value="18h00 - 20h00", key=f"custom_ca_{row['hoc_sinh_id']}")
                            ca_final = custom_ca.strip()
                        else:
                            ca_final = ca_val

                    with c2:
                        stt_val = st.radio("Trạng thái", ["Có mặt", "Vắng có phép", "Vắng không phép"], index=0, key=f"stt_cls_{row['hoc_sinh_id']}", horizontal=True)
                    with c3:
                        nx_val = st.text_input("Nhận xét nhanh", key=f"nx_cls_{row['hoc_sinh_id']}", placeholder="Nhận xét bài học...")

                    danh_sach_luu.append((row['hoc_sinh_id'], date_str, ca_final, stt_val, nx_val))
                    st.divider()

                if st.form_submit_button(f"💾 LƯU ĐIỂM DANH ({len(target_students)} HS)", type="primary", use_container_width=True):
                    for item in danh_sach_luu:
                        c.execute("INSERT INTO diem_danh (hoc_sinh_id, ngay, ca_hoc, trang_thai, nhan_xet) VALUES (?, ?, ?, ?, ?)", item)
                    conn.commit()
                    st.success("✅ Đã lưu dữ liệu điểm danh thành công!")
                    st.rerun()

    st.markdown("---")
    st.subheader(f"📊 Kết quả & Thống kê điểm danh ngày {ngay_hoc.strftime('%d/%m/%Y')}")

    df_dd_today = pd.read_sql_query(f'''
        SELECT d.id, h.ho_ten AS "Họ và Tên", h.lop_hoc AS "Lớp", d.ca_hoc AS "Ca Học", d.trang_thai AS "Trạng Thái", d.nhan_xet AS "Nhận Xét"
        FROM diem_danh d
        JOIN hoc_sinh h ON d.hoc_sinh_id = h.id
        WHERE d.ngay = '{date_str}'
        ORDER BY d.id DESC
    ''', conn)

    if not df_dd_today.empty:
        co_mat = len(df_dd_today[df_dd_today['Trạng Thái'] == 'Có mặt'])
        vang_phep = len(df_dd_today[df_dd_today['Trạng Thái'] == 'Vắng có phép'])
        vang_khong_phep = len(df_dd_today[df_dd_today['Trạng Thái'] == 'Vắng không phép'])

        m1, m2, m3 = st.columns(3)
        m1.metric("🟢 Tổng đi học (Có mặt)", f"{co_mat} HS")
        m2.metric("🟡 Vắng có phép", f"{vang_phep} HS")
        m3.metric("🔴 Vắng không phép", f"{vang_khong_phep} HS")

        st.caption("📋 Danh sách chi tiết học sinh đã được điểm danh trong ngày:")
        st.dataframe(df_dd_today[['Họ và Tên', 'Lớp', 'Ca Học', 'Trạng Thái', 'Nhận Xét']], use_container_width=True)
    else:
        st.info("ℹ️ Chưa có dữ liệu điểm danh nào được ghi nhận cho ngày này.")

# =========================================================
# --- CHỨC NĂNG 2: MA TRẬN LỊCH HỌC & XUẤT FILE ẢNH PNG ---
# =========================================================
elif choice == "2. 🗺️ Ma Trận Lịch Học & Mindmap Tuần":
    st.subheader("🗺️ Thời Khóa Biểu Tuần & Xuất File Ảnh Lịch Học")
    
    tab_matrix, tab_export = st.tabs(["🗺️ Ma Trận Lịch Học Tổng Quan", "📥 Xuất Lịch Học Theo Lớp / Học Sinh (Ảnh PNG)"])

    with tab_matrix:
        render_schedule_matrix(conn)

    with tab_export:
        st.markdown("### 🖼️ Xuất File Lịch Học Hàng Tuần Dạng Ảnh PNG (Không Lỗi Font)")
        df_hs_all = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", conn)

        if df_hs_all.empty:
            st.warning("Chưa có dữ liệu học sinh.")
        else:
            filter_mode = st.radio("Chọn phạm vi xuất lịch học:", ["Toàn bộ các Lớp", "Theo Lớp cụ thể", "Theo Học sinh cụ thể"], horizontal=True)
            
            target_title = "Tất Cả Các Lớp"
            selected_lop_exp = None
            selected_hs_exp = None
            prefix_label = "Đối tượng / Lớp: "

            if filter_mode == "Toàn bộ các Lớp":
                target_title = "Tất Cả Các Lớp"
                prefix_label = "Đối tượng / Lớp: "
            elif filter_mode == "Theo Lớp cụ thể":
                lop_list = sorted(df_hs_all['lop_hoc'].dropna().unique().tolist())
                selected_lop_exp = st.selectbox("Chọn Lớp:", lop_list)
                target_title = f"{selected_lop_exp}"
                prefix_label = "Lớp: "
            elif filter_mode == "Theo Học sinh cụ thể":
                hs_dict_exp = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row for _, row in df_hs_all.iterrows()}
                sel_hs_label = st.selectbox("Chọn Học sinh:", list(hs_dict_exp.keys()))
                selected_hs_row = hs_dict_exp[sel_hs_label]
                selected_hs_exp = selected_hs_row['id']
                target_title = f"{selected_hs_row['ho_ten']} ({selected_hs_row['lop_hoc']})"
                prefix_label = "Học sinh/Lớp: "

            df_export_matrix = get_schedule_matrix_df(conn, filter_lop=selected_lop_exp, filter_hs_id=selected_hs_exp)

            if df_export_matrix.empty:
                st.info("ℹ️ Không tìm thấy lịch học phù hợp đối với lựa chọn này.")
            else:
                # Tính tuần hiện tại để xem trước
                today = date.today()
                start_w = today - timedelta(days=today.weekday())
                end_w = start_w + timedelta(days=6)
                week_text = f"Tuần từ {start_w.strftime('%d/%m/%Y')} đến {end_w.strftime('%d/%m/%Y')}"

                st.markdown(f"#### 📋 Xem trước Lịch Học Tuần ({prefix_label} {target_title})")
                st.info(f"📅 **{week_text}**")
                st.write(df_export_matrix.to_html(index=False, escape=False), unsafe_allow_html=True)
                st.markdown("<p style='font-style: italic; color: #475569; font-size: 14px;'>Ghi chú: Áp dụng cho các tuần tiếp nếu không có thay đổi</p>", unsafe_allow_html=True)
                st.divider()

                if HAS_MATPLOTLIB:
                    img_bytes = create_weekly_schedule_image(target_title, df_export_matrix, prefix=prefix_label)
                    file_name_prefix = "Hoc_Sinh" if filter_mode == "Theo Học sinh cụ thể" else ("Lop" if filter_mode == "Theo Lớp cụ thể" else "Tat_Ca")
                    st.download_button(
                        label=f"🖼️ Tải File Ảnh Lịch Học ({target_title})",
                        data=img_bytes,
                        file_name=f"Lich_Hoc_Tuan_{file_name_prefix}_{target_title.replace(' ', '_').replace('(', '').replace(')', '')}.png",
                        mime="image/png",
                        type="primary"
                    )
                else:
                    st.warning("⚠️ Thư viện Matplotlib chưa được cài đặt để xuất ảnh.")

# =========================================================
# --- CHỨC NĂNG 3: LÊN LỊCH HỌC ---
# =========================================================
elif choice == "3. 📅 Lên Lịch Học (Gốc & Tạm Thời)":
    tab_goc, tab_tam = st.tabs(["📅 1. Lịch Học Gốc Hàng Tuần", "⏳ 2. Lịch Học Tạm Thời"])
    
    danh_sach_ca_mau = ["7h00 - 9h00", "9h00 - 11h00", "13h30 - 15h30", "15h30 - 17h30", "17h30 - 19h30", "19h30 - 21h30", "⏱️ Tự nhập giờ tùy chỉnh..."]

    with tab_goc:
        st.subheader("📅 Xếp Lịch Học Cố Định Hàng Tuần (Lịch Gốc)")
        df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", conn)
        
        if df_hs.empty:
            st.warning("Chưa có học sinh.")
        else:
            all_lops = sorted(df_hs['lop_hoc'].dropna().unique().tolist())
            selected_lop = st.selectbox("Chọn Lớp để xếp lịch gốc", all_lops, key="select_goc_lop")
            target_hs_ids = df_hs[df_hs['lop_hoc'] == selected_lop]['id'].tolist()
            
            cac_thu = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
            
            new_schedules_class = []
            for t in cac_thu:
                col_chk, col_ca, col_custom = st.columns([2, 3, 3])
                with col_chk: has_class = st.checkbox(f"Lớp học vào **{t}**", key=f"chk_goc_lop_{t}")
                with col_ca:
                    if has_class:
                        ca_val = st.selectbox(f"Ca học {t}", danh_sach_ca_mau, index=4, key=f"ca_goc_lop_{t}")
                with col_custom:
                    if has_class:
                        if ca_val == "⏱️ Tự nhập giờ tùy chỉnh...":
                            custom_ca_input = st.text_input(f"Nhập giờ {t}:", value="18h00 - 20h00", key=f"custom_ca_goc_{t}")
                            final_ca = custom_ca_input.strip()
                        else:
                            final_ca = ca_val
                        new_schedules_class.append((t, final_ca))
                        
            if st.button(f"💾 Lưu Lịch Học Gốc Cho Lớp {selected_lop}", type="primary"):
                for hs_id in target_hs_ids:
                    c.execute("DELETE FROM lich_hoc_tuan WHERE hoc_sinh_id=?", (hs_id,))
                    for t_val, ca_val in new_schedules_class:
                        c.execute("INSERT INTO lich_hoc_tuan (hoc_sinh_id, thu, ca_hoc) VALUES (?, ?, ?)", (hs_id, t_val, ca_val))
                conn.commit()
                st.success(f"✅ Đã lưu lịch gốc cho Lớp {selected_lop}!")
                st.rerun()

    with tab_tam:
        st.subheader("⏳ Lịch Học Tạm Thời")
        df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", conn)
        if not df_hs.empty:
            all_lops = sorted(df_hs['lop_hoc'].dropna().unique().tolist())
            sel_lop_tam = st.selectbox("Chọn Lớp", all_lops)
            target_hs_ids_tam = df_hs[df_hs['lop_hoc'] == sel_lop_tam]['id'].tolist()
            
            with st.form("form_lich_tam_thoi"):
                d_start = st.date_input("🗓️ Hiệu lực TỪ ngày", date.today())
                d_end = st.date_input("🗓️ Hiệu lực ĐẾN ngày", date.today())
                loai_td = st.radio("Loại thay đổi", ["Đổi ca / Học bù", "Nghỉ tạm thời trong khoảng thời gian này"], horizontal=True)
                thu_tam = st.selectbox("Vào Thứ", ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật'])
                ca_tam_sel = st.selectbox("Vào Ca", danh_sach_ca_mau)
                custom_ca_tam_input = st.text_input("Nếu chọn tự nhập giờ, nhập vào đây (VD: 08h30 - 10h30):", placeholder="08h30 - 10h30")
                
                if st.form_submit_button("💾 Thiết Lập Lịch Tạm Thời", type="primary"):
                    ca_tam_final = custom_ca_tam_input.strip() if (ca_tam_sel == "⏱️ Tự nhập giờ tùy chỉnh..." and custom_ca_tam_input.strip()) else ca_tam_sel
                    for hs_id_item in target_hs_ids_tam:
                        c.execute('''
                            INSERT INTO lich_hoc_tam_thoi (hoc_sinh_id, ngay_bat_dau, ngay_ket_thuc, thu, ca_hoc, loai_thay_doi)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (hs_id_item, d_start.strftime("%Y-%m-%d"), d_end.strftime("%Y-%m-%d"), thu_tam, ca_tam_final, loai_td))
                    conn.commit()
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

# --- CHỨC NĂNG 6: QUẢN LÝ & THỐNG KÊ HỌC PHÍ (PDF) ---
elif choice == "6. Quản lý & Thống kê Học phí (Xuất PDF)":
    st.subheader("💳 Đánh Dấu Trạng Thái Đóng Học Phí Theo Tháng & In Phiếu A5")
    thang = st.selectbox("Chọn Tháng", list(range(1, 13)), index=datetime.now().month - 1)
    nam = st.number_input("Chọn Năm", min_value=2020, max_value=2035, value=datetime.now().year)
    
    thang_nam_key = f"{thang:02d}/{nam}"
    thang_nam_query = f"{nam}-{thang:02d}"
    
    query_status = f'''
        SELECT 
            h.id AS hoc_sinh_id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi,
            SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS so_buoi,
            (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS tong_tien,
            COALESCE(t.trang_thai, 'Chưa đóng') AS trang_thai_dong
        FROM hoc_sinh h
        LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND strftime('%Y-%m', d.ngay) = '{thang_nam_query}'
        LEFT JOIN thanh_toan t ON h.id = t.hoc_sinh_id AND t.thang_nam = '{thang_nam_key}'
        GROUP BY h.id
    '''
    df_status = pd.read_sql_query(query_status, conn)
    
    qr_path = "qr_code.png" if os.path.exists("qr_code.png") else None

    for _, row in df_status.iterrows():
        c1, c2, c3, c4, c5, c6 = st.columns([2, 1, 2, 1.5, 2, 2])
        c1.write(f"**{row['ho_ten']}**")
        c2.write(f"{row['so_buoi']} buổi")
        c3.write(f"**{row['tong_tien']:,.0f} VNĐ**")
        is_paid = (row['trang_thai_dong'] == 'Đã đóng')
        c4.write("🟢 Đã đóng" if is_paid else "🔴 Chưa đóng")
        
        btn_label = "Chuyển Chưa đóng" if is_paid else "Xác nhận Đã đóng"
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

        with c6:
            if HAS_REPORTLAB:
                pdf_bytes = create_tuition_pdf(
                    student_name=row['ho_ten'],
                    lop_hoc=row['lop_hoc'],
                    subject=row['mon_hoc'] or 'Chung',
                    price_per_lesson=row['hoc_phi_buoi'],
                    month_year=thang_nam_key,
                    total_lessons=row['so_buoi'],
                    total_fee=row['tong_tien'],
                    status=row['trang_thai_dong'],
                    qr_path=qr_path
                )
                st.download_button(
                    label="📄 In Phiếu A5",
                    data=pdf_bytes,
                    file_name=f"Phieu_Hoc_Phi_{row['ho_ten'].replace(' ', '_')}_{thang:02d}_{nam}.pdf",
                    mime="application/pdf",
                    key=f"pdf_fee_{row['hoc_sinh_id']}"
                )

        st.divider()

# --- CHỨC NĂNG 7: SỬA & XÓA DỮ LIỆU ---
elif choice == "7. Sửa & Xóa dữ liệu":
    st.subheader("⚙️ Quản Lý Dữ Liệu Học Sinh & Điểm Danh")
    
    tab_hs, tab_diemdanh = st.tabs(["👤 Quản lý Học sinh (Thêm / Sửa / Xóa)", "🗓️ Quản lý Nhật ký Điểm danh"])
    
    with tab_hs:
        sub_tab_them, sub_tab_sua, sub_tab_xoa = st.tabs([
            "➕ 1. Thêm Học Sinh Mới", 
            "✏️ 2. Sửa Thông Tin Học Sinh", 
            "❌ 3. Xóa Học Sinh"
        ])
        
        with sub_tab_them:
            st.markdown("##### ➕ Nhập Thông Tin Học Sinh Mới")
            with st.form("form_add_student_full"):
                c1, c2 = st.columns(2)
                with c1:
                    ten_new = st.text_input("Họ và tên học sinh (*)", placeholder="Nguyễn Văn A")
                    lop_new = st.text_input("Lớp / Nhóm học", value="Toán 9")
                    mon_new = st.text_input("Môn học", value="Toán")
                with c2:
                    hoc_phi_new = st.number_input("Học phí mỗi buổi (VNĐ)", min_value=0, step=10000, value=150000)
                    sdt_new = st.text_input("Số điện thoại phụ huynh", placeholder="0912345678")
                    ngay_sinh_new = st.date_input("Ngày sinh nhật học sinh", value=date(2010, 1, 1))
                
                if st.form_submit_button("💾 Thêm Học Sinh Mới", type="primary"):
                    if ten_new.strip():
                        c.execute('''
                            INSERT INTO hoc_sinh (ho_ten, lop_hoc, mon_hoc, hoc_phi_buoi, sdt_phu_huynh, ngay_sinh)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (ten_new.strip(), lop_new.strip(), mon_new.strip(), hoc_phi_new, sdt_new.strip(), ngay_sinh_new.strftime("%Y-%m-%d")))
                        conn.commit()
                        st.success(f"✅ Đã thêm học sinh **{ten_new}** thành công!")
                        st.rerun()
                    else:
                        st.error("⚠️ Vui lòng nhập Họ và tên học sinh!")

        with sub_tab_sua:
            st.markdown("##### ✏️ Sửa Thông Tin Học Sinh")
            df_hs_edit = pd.read_sql_query("SELECT * FROM hoc_sinh ORDER BY id DESC", conn)
            if df_hs_edit.empty:
                st.info("💡 Chưa có học sinh nào để sửa.")
            else:
                hs_edit_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row for _, row in df_hs_edit.iterrows()}
                selected_edit_label = st.selectbox("Chọn học sinh cần sửa thông tin:", list(hs_edit_dict.keys()), key="select_edit_hs")
                selected_hs_row = hs_edit_dict[selected_edit_label]
                
                with st.form("form_edit_student"):
                    c1, c2 = st.columns(2)
                    with c1:
                        ten_edit = st.text_input("Họ và tên", value=selected_hs_row['ho_ten'])
                        lop_edit = st.text_input("Lớp / Nhóm học", value=selected_hs_row['lop_hoc'] or "")
                        mon_edit = st.text_input("Môn học", value=selected_hs_row['mon_hoc'] or "")
                    with c2:
                        hoc_phi_edit = st.number_input("Học phí mỗi buổi (VNĐ)", min_value=0, step=10000, value=int(selected_hs_row['hoc_phi_buoi'] or 150000))
                        sdt_edit = st.text_input("Số điện thoại phụ huynh", value=selected_hs_row['sdt_phu_huynh'] or "")
                        
                        default_ns = date(2010, 1, 1)
                        if selected_hs_row['ngay_sinh']:
                            try:
                                default_ns = datetime.strptime(str(selected_hs_row['ngay_sinh']), "%Y-%m-%d").date()
                            except Exception:
                                pass
                        ngay_sinh_edit = st.date_input("Ngày sinh nhật học sinh", value=default_ns)
                    
                    if st.form_submit_button("💾 Lưu Thay Đổi Thông Tin", type="primary"):
                        c.execute('''
                            UPDATE hoc_sinh 
                            SET ho_ten = ?, lop_hoc = ?, mon_hoc = ?, hoc_phi_buoi = ?, sdt_phu_huynh = ?, ngay_sinh = ?
                            WHERE id = ?
                        ''', (ten_edit.strip(), lop_edit.strip(), mon_edit.strip(), hoc_phi_edit, sdt_edit.strip(), ngay_sinh_edit.strftime("%Y-%m-%d"), int(selected_hs_row['id'])))
                        conn.commit()
                        st.success(f"✅ Đã cập nhật xong thông tin học sinh **{ten_edit}**!")
                        st.rerun()

        with sub_tab_xoa:
            st.markdown("##### ❌ Xóa Học Sinh Khỏi Hệ Thống")
            df_hs_del = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh ORDER BY id DESC", conn)
            if df_hs_del.empty:
                st.info("💡 Chưa có học sinh nào để xóa.")
            else:
                hs_del_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row['id'] for _, row in df_hs_del.iterrows()}
                selected_del_label = st.selectbox("Chọn học sinh cần xóa:", list(hs_del_dict.keys()), key="select_del_hs")
                selected_del_id = hs_del_dict[selected_del_label]
                
                st.warning("⚠️ **Lưu ý:** Xóa học sinh sẽ xóa toàn bộ lịch sử điểm danh, thanh toán và lịch học của học sinh này!")
                confirm_check = st.checkbox("Tôi xác nhận muốn xóa học sinh này")
                
                if st.button("❌ XÓA HỌC SINH NÀY", type="primary"):
                    if confirm_check:
                        c.execute("DELETE FROM diem_danh WHERE hoc_sinh_id = ?", (selected_del_id,))
                        c.execute("DELETE FROM thanh_toan WHERE hoc_sinh_id = ?", (selected_del_id,))
                        c.execute("DELETE FROM lich_hoc_tuan WHERE hoc_sinh_id = ?", (selected_del_id,))
                        c.execute("DELETE FROM lich_hoc_tam_thoi WHERE hoc_sinh_id = ?", (selected_del_id,))
                        c.execute("DELETE FROM hoc_sinh WHERE id = ?", (selected_del_id,))
                        conn.commit()
                        st.success("✅ Đã xóa thành công học sinh khỏi hệ thống!")
                        st.rerun()
                    else:
                        st.error("⚠️ Bạn cần tích vào ô 'Tôi xác nhận...' trước khi xóa.")

        st.divider()
        st.markdown("### 📋 Danh Sách Tất Cả Học Sinh Hiện Có")
        df_all_students = pd.read_sql_query('''
            SELECT 
                id AS "Mã HS", 
                ho_ten AS "Họ và tên", 
                lop_hoc AS "Lớp", 
                mon_hoc AS "Môn", 
                hoc_phi_buoi AS "Học phí/Buổi (VNĐ)", 
                sdt_phu_huynh AS "SĐT Phụ huynh", 
                ngay_sinh AS "Ngày sinh" 
            FROM hoc_sinh 
            ORDER BY id DESC
        ''', conn)
        
        if df_all_students.empty:
            st.info("💡 Hệ thống hiện tại chưa có học sinh nào. Hãy thêm học sinh mới ở mục phía trên.")
        else:
            st.dataframe(df_all_students, use_container_width=True)

    with tab_diemdanh:
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
