import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, datetime, timedelta
import os
import io
import re
import urllib.request
import shutil

# Thử import Matplotlib để xuất lịch học & phiếu học phí dạng ảnh PNG
try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# --- CẤU HÌNH TRANG WEB ---
st.set_page_config(page_title="Quản Lý Học Sinh Học Thêm", layout="wide", page_icon="📚")

# --- DANH SÁCH CA HỌC MẪU TOÀN HỆ THỐNG ---
DANH_SACH_CA_MAU = [
    "7h00 - 9h00", 
    "9h00 - 11h00", 
    "13h30 - 15h30", 
    "14h00 - 16h00", 
    "15h30 - 17h30", 
    "17h30 - 19h30", 
    "19h30 - 21h30"
]

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

# --- HÀM LẤY LỊCH HỌC HIỆU LỰC CHO MỘT NGÀY (CÓ XỬ LÝ LỊCH TẠM THỜI) ---
def get_active_schedule_for_date(conn, check_date):
    target_day_str = get_vietnamese_weekday(check_date)
    date_str = check_date.strftime("%Y-%m-%d")

    query_temp = f'''
        SELECT t.hoc_sinh_id, h.ho_ten, h.lop_hoc, h.mon_hoc, t.thu, t.ca_hoc, t.loai_thay_doi, t.ngay_bat_dau, t.ngay_ket_thuc
        FROM lich_hoc_tam_thoi t
        JOIN hoc_sinh h ON t.hoc_sinh_id = h.id
        WHERE t.ngay_bat_dau <= '{date_str}' AND t.ngay_ket_thuc >= '{date_str}'
    '''
    df_temp = pd.read_sql_query(query_temp, conn)
    
    nghidai_ids = []
    doica_ids = []
    
    if not df_temp.empty:
        df_temp_today_weekday = df_temp[df_temp['thu'] == target_day_str]
        if not df_temp_today_weekday.empty:
            nghi_df = df_temp_today_weekday[df_temp_today_weekday['loai_thay_doi'] == 'Nghỉ tạm thời trong khoảng thời gian này']
            nghidai_ids = nghi_df['hoc_sinh_id'].unique().tolist()
            
            doica_df = df_temp_today_weekday[df_temp_today_weekday['loai_thay_doi'] == 'Đổi ca / Học bù']
            doica_ids = doica_df['hoc_sinh_id'].unique().tolist()

    query_base = f'''
        SELECT l.hoc_sinh_id, h.ho_ten, h.lop_hoc, h.mon_hoc, l.ca_hoc, 'Lịch gốc' AS nguon
        FROM lich_hoc_tuan l
        JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
        WHERE l.thu = '{target_day_str}'
    '''
    df_base = pd.read_sql_query(query_base, conn)
    
    exclude_ids = list(set(nghidai_ids + doica_ids))
    if not df_base.empty and len(exclude_ids) > 0:
        df_base = df_base[~df_base['hoc_sinh_id'].isin(exclude_ids)]

    df_temp_additions = pd.DataFrame()
    if not df_temp.empty:
        valid_temp = df_temp[(df_temp['thu'] == target_day_str) & (df_temp['loai_thay_doi'].isin(['Đổi ca / Học bù', 'Học thêm buổi']))]
        if not valid_temp.empty:
            df_temp_additions = valid_temp[['hoc_sinh_id', 'ho_ten', 'lop_hoc', 'mon_hoc', 'ca_hoc', 'loai_thay_doi']].copy()
            df_temp_additions.rename(columns={'loai_thay_doi': 'nguon'}, inplace=True)

    cols = ['hoc_sinh_id', 'ho_ten', 'lop_hoc', 'mon_hoc', 'ca_hoc', 'nguon']
    df_combined = pd.concat([
        df_base[cols] if not df_base.empty else pd.DataFrame(columns=cols),
        df_temp_additions[cols] if not df_temp_additions.empty else pd.DataFrame(columns=cols)
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
            "14h00 - 16h00": ("14:00:00", "16:00:00"),
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
    predefined = ["7h00 - 9h00", "9h00 - 11h00", "13h30 - 15h30", "14h00 - 16h00", "15h30 - 17h30", "17h30 - 19h30", "19h30 - 21h30"]
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
        "13h30 - 15h30": "☀️ Chiều", "14h00 - 16h00": "☀️ Chiều", "15h30 - 17h30": "☀️ Chiều",
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

# --- HÀM LẤY MA TRẬN LỊCH HỌC (ĐÃ TÍCH HỢP LỊCH TẠM THỜI CHO TUẦN CHỌN) ---
def get_schedule_matrix_df(conn, filter_lop=None, filter_hs_id=None, ref_date=None):
    if ref_date is None:
        ref_date = date.today()
    cac_thu = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
    start_monday = ref_date - timedelta(days=ref_date.weekday())
    
    day_schedules = {}
    for i, t in enumerate(cac_thu):
        current_d = start_monday + timedelta(days=i)
        df_day = get_active_schedule_for_date(conn, current_d)
        if not df_day.empty:
            if filter_lop:
                df_day = df_day[df_day['lop_hoc'] == filter_lop]
            elif filter_hs_id:
                df_day = df_day[df_day['hoc_sinh_id'] == filter_hs_id]
        day_schedules[t] = df_day

    all_cas = set()
    for t in cac_thu:
        df_d = day_schedules[t]
        if not df_d.empty and 'ca_hoc' in df_d.columns:
            all_cas.update(df_d['ca_hoc'].unique().tolist())
    
    if not all_cas:
        return pd.DataFrame()
        
    cac_ca = sorted(list(all_cas), key=ca_hoc_sort_key)

    matrix_rows = []
    for ca in cac_ca:
        buoi = get_buoi_from_ca(ca)
        row_dict = {"Buổi": buoi, "Ca học": ca}
        for t in cac_thu:
            df_d = day_schedules[t]
            if df_d.empty:
                row_dict[t] = "-"
            else:
                matched = df_d[df_d['ca_hoc'] == ca]
                if matched.empty:
                    row_dict[t] = "-"
                else:
                    items = []
                    for lop, g in matched.groupby('lop_hoc'):
                        names_list = []
                        for _, row_item in g.iterrows():
                            name_str = row_item['ho_ten']
                            nguon = row_item.get('nguon', 'Lịch gốc')
                            if nguon != 'Lịch gốc':
                                name_str += f" <span style='color: #B91C1C; font-size: 11px;'>({nguon})</span>"
                            names_list.append(name_str)
                        names_str = ", ".join(names_list)
                        if filter_lop or filter_hs_id:
                            items.append(names_str)
                        else:
                            items.append(f"<b>[{lop}]</b>: {names_str}")
                    row_dict[t] = "<br>".join(items)
        matrix_rows.append(row_dict)

    df_matrix = pd.DataFrame(matrix_rows)
    cols = ["Buổi", "Ca học"] + cac_thu
    return df_matrix[cols]

# --- HÀM HIỂN THỊ MA TRẬN LỊCH HỌC ---
def render_schedule_matrix(conn, ref_date=None):
    df_matrix = get_schedule_matrix_df(conn, ref_date=ref_date)
    if df_matrix.empty:
        st.info("💡 Chưa có lịch học tuần nào được thiết lập trong hệ thống cho mốc thời gian này.")
        return
    st.write(df_matrix.to_html(index=False, escape=False), unsafe_allow_html=True)

# --- HÀM TẠO FILE ẢNH PNG LỊCH HỌC HÀNG TUẦN ---
def create_weekly_schedule_image(title_target, df_matrix, ref_date=None, prefix="Đối tượng / Lớp: "):
    if ref_date is None:
        ref_date = date.today()
    fig, ax = plt.subplots(figsize=(16, len(df_matrix) * 1.0 + 4.0))
    ax.axis('off')
    ax.axis('tight')
    
    start_w = ref_date - timedelta(days=ref_date.weekday())
    end_w = start_w + timedelta(days=6)
    week_text = f"(Tuần từ {start_w.strftime('%d/%m/%Y')} đến {end_w.strftime('%d/%m/%Y')})"
    
    table_data = [df_matrix.columns.tolist()] + df_matrix.values.tolist()
    cleaned_data = []
    for row in table_data:
        cleaned_row = []
        for cell in row:
            clean_cell = str(cell).replace("<br>", "\n").replace("<br/>", "\n")
            clean_cell = clean_cell.replace("<b>", "").replace("</b>", "")
            clean_cell = re.sub(r'<[^>]+>', '', clean_cell)
            cleaned_row.append(clean_cell)
        cleaned_data.append(cleaned_row)
        
    table = ax.table(cellText=cleaned_data, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2.2)
    
    ax.text(0.5, 1.14, "THỜI KHÓA BIỂU LỊCH HỌC HÀNG TUẦN", transform=ax.transAxes, 
            fontsize=14, fontweight='bold', color='#1E3A8A', ha='center', va='bottom')
    ax.text(0.5, 1.07, f"{prefix}{title_target}", transform=ax.transAxes, 
            fontsize=12, fontweight='bold', color='#1E3A8A', ha='center', va='bottom')
    ax.text(0.5, 1.01, week_text, transform=ax.transAxes, 
            fontsize=10, fontweight='normal', color='#475569', ha='center', va='bottom')
    
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

# --- HÀM TẠO FILE ẢNH HÓA ĐƠN HỌC PHÍ (PNG) ---
def create_tuition_slip_image(student_name, lop_hoc, subject, price_per_lesson, month_year, total_lessons, total_fee, status, qr_path):
    fig, ax = plt.subplots(figsize=(8, 10))
    ax.axis('off')
    
    ax.text(0.5, 0.93, "PHIẾU BÁO HỌC PHÍ DẠY THÊM", fontsize=16, fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    ax.text(0.5, 0.88, f"Tháng / Năm: {month_year}", fontsize=13, fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    
    details = [
        f"Họ và tên học sinh: {student_name}",
        f"Lớp / Nhóm học: {lop_hoc}",
        f"Môn học: {subject}",
        f"Học phí / ca: {price_per_lesson:,.0f} VNĐ",
        f"Tổng số ca học: {total_lessons} ca",
        f"TỔNG CỘNG HỌC PHÍ: {total_fee:,.0f} VNĐ",
        f"Trạng thái thanh toán: {status}"
    ]
    
    y_pos = 0.78
    for line in details:
        fontweight = 'bold' if 'TỔNG CỘNG' in line or 'Họ và tên' in line else 'normal'
        color = '#B91C1C' if 'TỔNG CỘNG' in line else '#1E293B'
        ax.text(0.1, y_pos, line, fontsize=12, fontweight=fontweight, color=color, transform=ax.transAxes)
        y_pos -= 0.06
        
    if qr_path and os.path.exists(qr_path):
        try:
            img_arr = plt.imread(qr_path)
            ax_inset = fig.add_axes([0.35, 0.15, 0.3, 0.3])
            ax_inset.imshow(img_arr)
            ax_inset.axis('off')
            ax.text(0.5, 0.48, "Mã QR Thanh Toán Chuyển Khoản", fontsize=11, fontweight='bold', color='#1E3A8A', ha='center', transform=ax.transAxes)
        except Exception:
            pass
            
    ax.text(0.5, 0.05, "Trân trọng cảm ơn sự đồng hành của Quý phụ huynh!", fontsize=11, style='italic', fontweight='bold', color='#1E3A8A', ha='center', transform=ax.transAxes)
    
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig)
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
        UNIQUE(hoc_sinh_id, ngay, ca_hoc),
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
    "2. 🗺️ Quản Lý & Ma Trận Lịch Học",
    "3. 💡 Gợi ý Smart Assistant",
    "4. 💳 Quản Lý Học Phí & Thống Kê (Lọc Đa Tháng / Xuất Ảnh)", 
    "5. Sửa & Xóa dữ liệu"
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

# --- SAO LƯU & KHÔI PHỤC DỮ LIỆU TRỰC TIẾP TRÊN SIDEBAR ---
st.sidebar.markdown("---")
st.sidebar.subheader("💾 Sao Lưu & Khôi Phục Dữ Liệu")

if os.path.exists("quan_ly_hoc_sinh.db"):
    with open("quan_ly_hoc_sinh.db", "rb") as f:
        st.sidebar.download_button(
            label="📥 Tải Backup Database (.db)",
            data=f,
            file_name=f"quan_ly_hoc_sinh_backup_{date.today().strftime('%Y%m%d')}.db",
            mime="application/octet-stream",
            use_container_width=True
        )

uploaded_backup_file = st.sidebar.file_uploader("📤 Tải lên file backup để khôi phục (.db)", type=["db"])
if uploaded_backup_file is not None:
    if st.sidebar.button("⚠️ Xác nhận khôi phục database", type="primary", use_container_width=True):
        try:
            with open("quan_ly_hoc_sinh.db", "wb") as f:
                f.write(uploaded_backup_file.getbuffer())
            st.sidebar.success("✅ Khôi phục thành công! Đang tải lại ứng dụng...")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"❌ Lỗi khôi phục: {e}")

# =========================================================
# --- KIỂM TRA CẢNH BÁO QUÁ HẠN LỊCH TẠM THỜI / NGHỈ DÀI HẠN ---
# =========================================================
today_date_str = date.today().strftime("%Y-%m-%d")
expired_temp_df = pd.read_sql_query(f"SELECT * FROM lich_hoc_tam_thoi WHERE ngay_ket_thuc < '{today_date_str}'", conn)
if not expired_temp_df.empty:
    st.sidebar.warning(f"⚠️ Có {len(expired_temp_df)} thiết lập lịch tạm thời / nghỉ dài hạn đã hết hạn!")

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
    
    pending_nghi = pd.read_sql_query(f"SELECT * FROM lich_hoc_tam_thoi WHERE loai_thay_doi = 'Nghỉ tạm thời trong khoảng thời gian này' AND ngay_ket_thuc < '{date_str}'", conn)
    if not pending_nghi.empty:
        st.error("⚠️ **CẢNH BÁO: HỌC SINH ĐÃ HẾT HẠN NGHỈ DÀI HẠN!**")
        for _, r_p in pending_nghi.iterrows():
            hs_info = pd.read_sql_query(f"SELECT ho_ten, lop_hoc FROM hoc_sinh WHERE id = {r_p['hoc_sinh_id']}", conn)
            if not hs_info.empty:
                name_p = hs_info.iloc[0]['ho_ten']
                lop_p = hs_info.iloc[0]['lop_hoc']
                st.write(f"• Học sinh **{name_p}** (Lớp {lop_p}) đã hết hạn xin nghỉ từ ngày {r_p['ngay_ket_thuc']}.")
                col_b1, col_b2 = st.columns(2)
                if col_b1.button(f"✅ Cho học sinh {name_p} TRỞ LẠI HỌC", key=f"back_{r_p['id']}"):
                    c.execute("DELETE FROM lich_hoc_tam_thoi WHERE id = ?", (r_p['id'],))
                    conn.commit()
                    st.success(f"Đã cập nhật học sinh {name_p} đi học trở lại!")
                    st.rerun()
                if col_b2.button(f"🛑 Tiếp tục VẪN NGHỈ", key=f"keep_{r_p['id']}"):
                    new_end_ext = (datetime.strptime(r_p['ngay_ket_thuc'], "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d")
                    c.execute("UPDATE lich_hoc_tam_thoi SET ngay_ket_thuc = ? WHERE id = ?", (new_end_ext, r_p['id']))
                    conn.commit()
                    st.warning(f"Đã gia hạn nghỉ cho học sinh {name_p} thêm 1 tuần!")
                    st.rerun()

    df_all_hs = pd.read_sql_query("SELECT id AS hoc_sinh_id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", conn)
    
    type_mode = st.radio("Chế độ điểm danh", ["🏫 Điểm danh theo LỚP", "👤 Điểm danh từng HỌC SINH"], horizontal=True)
    st.divider()

    target_students = pd.DataFrame()

    if df_all_hs.empty:
        st.warning("⚠️ Chưa có học sinh nào trong hệ thống! Hãy sang mục 'Sửa & Xóa dữ liệu' để thêm học sinh mới.")
    else:
        if type_mode == "🏫 Điểm danh theo LỚP":
            available_classes = sorted(df_all_hs['lop_hoc'].dropna().unique().tolist())
            options_class = ["🌟 All Lớp (Tất cả học sinh có lịch học hôm nay)"] + available_classes
            selected_class_opt = st.selectbox("Chọn Lớp cần điểm danh", options_class)

            if selected_class_opt.startswith("🌟 All Lớp"):
                target_students = df_active_today
            else:
                target_students = df_active_today[df_active_today['lop_hoc'] == selected_class_opt] if not df_active_today.empty else pd.DataFrame()

        else:
            student_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['hoc_sinh_id']}": row['hoc_sinh_id'] for _, row in df_all_hs.iterrows()}
            options_hs = ["🌟 All Học sinh (Tất cả học sinh có lịch học hôm nay)"] + list(student_dict.keys())
            selected_hs_opt = st.selectbox("Chọn học sinh điểm danh", options_hs)

            if selected_hs_opt.startswith("🌟 All Học sinh"):
                target_students = df_active_today
            else:
                selected_hs_id = student_dict[selected_hs_opt]
                target_students = df_active_today[df_active_today['hoc_sinh_id'] == selected_hs_id] if not df_active_today.empty else pd.DataFrame()

        if target_students.empty:
            st.info("ℹ️ Không tìm thấy học sinh nào có lịch học hợp lệ trong ngày hôm nay.")
        else:
            st.markdown(f"#### 📋 Bảng Điểm Danh ({len(target_students)} lượt học ca)")
            with st.form("form_diem_danh_execution"):
                danh_sach_ca_mau_dd = DANH_SACH_CA_MAU + ["⏱️ Tự nhập giờ tùy chỉnh..."]
                danh_sach_luu = []

                for idx, row in target_students.iterrows():
                    st.markdown(f"**👤 {row['ho_ten']}** [{row.get('lop_hoc', 'N/A')}] - *Ca: {row.get('ca_hoc', 'N/A')} (Nguồn: {row.get('nguon', 'Lịch gốc')})*")
                    c1, c2, c3 = st.columns([2.5, 3, 3.5])
                    
                    default_ca = row['ca_hoc'] if ('ca_hoc' in row and pd.notna(row['ca_hoc']) and row['ca_hoc'] in DANH_SACH_CA_MAU) else "17h30 - 19h30"

                    with c1:
                        ca_val = st.selectbox("Ca học", danh_sach_ca_mau_dd, index=danh_sach_ca_mau_dd.index(default_ca) if default_ca in danh_sach_ca_mau_dd else 5, key=f"ca_cls_{row['hoc_sinh_id']}_{idx}")
                        if ca_val == "⏱️ Tự nhập giờ tùy chỉnh...":
                            custom_ca = st.text_input("Nhập giờ (VD: 08h30 - 10h30)", value="18h00 - 20h00", key=f"custom_ca_{row['hoc_sinh_id']}_{idx}")
                            ca_final = custom_ca.strip()
                        else:
                            ca_final = ca_val

                    with c2:
                        stt_val = st.radio("Trạng thái", ["Có mặt", "Vắng có phép", "Vắng không phép"], index=0, key=f"stt_cls_{row['hoc_sinh_id']}_{idx}", horizontal=True)
                    with c3:
                        nx_val = st.text_input("Nhận xét nhanh", key=f"nx_cls_{row['hoc_sinh_id']}_{idx}", placeholder="Nhận xét bài học...")

                    danh_sach_luu.append((row['hoc_sinh_id'], date_str, ca_final, stt_val, nx_val))
                    st.divider()

                if st.form_submit_button(f"💾 LƯU ĐIỂM DANH", type="primary", use_container_width=True):
                    success_count = 0
                    duplicate_count = 0
                    for item in danh_sach_luu:
                        try:
                            c.execute("INSERT INTO diem_danh (hoc_sinh_id, ngay, ca_hoc, trang_thai, nhan_xet) VALUES (?, ?, ?, ?, ?)", item)
                            success_count += 1
                        except sqlite3.IntegrityError:
                            duplicate_count += 1
                    conn.commit()
                    if success_count > 0:
                        st.success(f"✅ Đã lưu thành công {success_count} bản ghi điểm danh!")
                    if duplicate_count > 0:
                        st.warning(f"⚠️ Có {duplicate_count} bản ghi bị bỏ qua do học sinh không thể điểm danh 2 lần trong cùng 1 ca / 1 ngày.")
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
# --- CHỨC NĂNG 2: QUẢN LÝ & MA TRẬN LỊCH HỌC ---
# =========================================================
elif choice == "2. 🗺️ Quản Lý & Ma Trận Lịch Học":
    st.subheader("🗺️ Trung Tâm Quản Lý Thời Khóa Biểu & Lịch Học")

    tab_matrix, tab_goc, tab_tam, tab_export = st.tabs([
        "🗺️ Ma Trận Tổng Quan", 
        "📅 1. Lịch Gốc Hàng Tuần", 
        "⏳ 2. Lịch Học Tạm Thời", 
        "📥 Xuất Ảnh Lịch Học"
    ])

    with tab_matrix:
        st.markdown("##### 🗓️ Chọn mốc tuần cần xem ma trận tổng quan:")
        sel_date_matrix = st.date_input("Xem tuần chứa ngày:", date.today(), key="sel_date_matrix_main")
        st.divider()
        render_schedule_matrix(conn, ref_date=sel_date_matrix)

    with tab_goc:
        st.subheader("📅 Xếp Lịch Học Cố Định Hàng Tuần (Lịch Gốc)")
        df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", conn)
        
        if df_hs.empty:
            st.warning("Chưa có học sinh.")
        else:
            mode_goc = st.radio("Phạm vi xếp lịch gốc:", ["Theo Lớp (Áp dụng chung cả lớp)", "Theo Từng Học Sinh Riêng Biệt"], horizontal=True, key="mode_goc_sched")
            
            target_hs_ids = []
            target_name_label = ""
            if mode_goc == "Theo Lớp (Áp dụng chung cả lớp)":
                all_lops = sorted(df_hs['lop_hoc'].dropna().unique().tolist())
                selected_lop = st.selectbox("Chọn Lớp để xếp lịch gốc", all_lops, key="select_goc_lop")
                target_hs_ids = df_hs[df_hs['lop_hoc'] == selected_lop]['id'].tolist()
                target_name_label = f"Lớp {selected_lop}"
            else:
                hs_dict_goc = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row['id'] for _, row in df_hs.iterrows()}
                selected_hs_label = st.selectbox("Chọn Học sinh cụ thể:", list(hs_dict_goc.keys()), key="select_goc_hs_indiv")
                target_hs_ids = [hs_dict_goc[selected_hs_label]]
                target_name_label = selected_hs_label

            cac_thu = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
            
            st.info(f"💡 Đang cấu hình lịch gốc cho: **{target_name_label}**. Bạn có thể chọn nhiều ca/ngày.")
            
            schedule_dict_to_save = {}
            for t in cac_thu:
                with st.expander(f"🗓️ Cấu hình ca học cho **{t}**", expanded=False):
                    has_class = st.checkbox(f"Có lịch học vào {t}", key=f"chk_goc_lop_{t}")
                    if has_class:
                        cas_chon = st.multiselect(
                            f"Chọn các ca chuẩn vào {t}:", 
                            DANH_SACH_CA_MAU, 
                            default=["17h30 - 19h30"] if t != "Chủ Nhật" else [],
                            key=f"multi_ca_{t}"
                        )
                        custom_ca_them = st.text_input(
                            f"Thêm ca giờ tùy chỉnh vào {t} (nếu có, cách nhau bằng dấu phẩy):", 
                            placeholder="VD: 08h00 - 10h00, 14h00 - 16h00", 
                            key=f"custom_ca_multi_{t}"
                        )
                        
                        all_cas_for_day = list(cas_chon)
                        if custom_ca_them.strip():
                            extra_cas = [c_item.strip() for c_item in custom_ca_them.split(",") if c_item.strip()]
                            all_cas_for_day.extend(extra_cas)
                        
                        if all_cas_for_day:
                            schedule_dict_to_save[t] = list(set(all_cas_for_day))
                            st.success(f"✅ Đã chọn {len(schedule_dict_to_save[t])} ca cho {t}: {', '.join(schedule_dict_to_save[t])}")
                        else:
                            st.warning("⚠️ Chưa chọn ca học nào cho ngày này.")

            if st.button(f"💾 Lưu Lịch Học Gốc Cho {target_name_label}", type="primary"):
                for hs_id in target_hs_ids:
                    c.execute("DELETE FROM lich_hoc_tuan WHERE hoc_sinh_id=?", (hs_id,))
                    for t_val, list_ca in schedule_dict_to_save.items():
                        for ca_val in list_ca:
                            c.execute("INSERT OR IGNORE INTO lich_hoc_tuan (hoc_sinh_id, thu, ca_hoc) VALUES (?, ?, ?)", (hs_id, t_val, ca_val))
                conn.commit()
                st.success(f"✅ Đã lưu lịch gốc cho {target_name_label} thành công!")
                st.rerun()

    with tab_tam:
        st.subheader("⏳ Quản Lý Lịch Học Tạm Thời (Đổi ca / Học bù / Học thêm / Nghỉ tạm thời trong khoảng thời gian)")
        
        sub_tab_add_t, sub_tab_list_t = st.tabs(["➕ Thêm lịch tạm thời mới", "📋 Danh sách & Sửa / Xóa lịch tạm thời"])
        
        with sub_tab_add_t:
            df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", conn)
            if not df_hs.empty:
                all_lops = sorted(df_hs['lop_hoc'].dropna().unique().tolist())
                sel_lop_tam = st.selectbox("Chọn Lớp / Nhóm", all_lops, key="sel_lop_tam_key")
                
                hs_in_lop = df_hs[df_hs['lop_hoc'] == sel_lop_tam]
                hs_dict_tam = {f"{row['ho_ten']} - ID:{row['id']}": row['id'] for _, row in hs_in_lop.iterrows()}
                
                chon_doi_tuong = st.radio("Áp dụng cho:", ["Toàn bộ lớp", "Từng học sinh cụ thể"], horizontal=True, key="chon_doi_tuong_tam")
                target_hs_ids_tam = []
                if chon_doi_tuong == "Toàn bộ lớp":
                    target_hs_ids_tam = hs_in_lop['id'].tolist()
                else:
                    sel_hs_lbl = st.selectbox("Chọn học sinh:", list(hs_dict_tam.keys()), key="sel_hs_lbl_tam")
                    target_hs_ids_tam = [hs_dict_tam[sel_hs_lbl]]

                with st.form("form_lich_tam_thoi"):
                    d_start = st.date_input("🗓️ Hiệu lực TỪ ngày", date.today(), key="d_start_tam")
                    d_end = st.date_input("🗓️ Hiệu lực ĐẾN ngày", date.today(), key="d_end_tam")
                    loai_td = st.selectbox("Loại thay đổi", [
                        "Đổi ca / Học bù", 
                        "Học thêm buổi", 
                        "Nghỉ tạm thời trong khoảng thời gian này"
                    ], key="loai_td_tam")
                    
                    selected_thu_list = []
                    shifts_to_apply = []
                    cac_thu_all = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']

                    if loai_td == "Nghỉ tạm thời trong khoảng thời gian này":
                        st.markdown("##### ⚙️ Cấu hình ngày nghỉ trong khoảng thời gian")
                        nghi_ngay_mode = st.radio(
                            "Lựa chọn ngày nghỉ:", 
                            [
                                "📅 Tự chọn các ngày trong tuần cần nghỉ", 
                                "🌟 Tất cả các ngày có học sinh đó học trong khoảng thời gian này"
                            ], 
                            key="nghi_ngay_mode_r"
                        )
                        
                        if nghi_ngay_mode == "📅 Tự chọn các ngày trong tuần cần nghỉ":
                            selected_thu_list = st.multiselect("Chọn các ngày trong tuần:", cac_thu_all, default=["Thứ 2"], key="sel_thu_nghi_multi")
                        else:
                            selected_thu_list = ["__AUTO__"]
                        
                        shifts_to_apply = ["Nghỉ cả ngày"]
                    else:
                        st.markdown("##### ⚙️ Cấu hình ngày và ca học tạm thời")
                        thu_tam = st.selectbox("Vào Thứ", cac_thu_all, key="thu_tam_sel")
                        selected_thu_list = [thu_tam]
                        ca_tam_chon = st.multiselect(
                            "Chọn các ca học tạm thời:", 
                            DANH_SACH_CA_MAU, 
                            default=["17h30 - 19h30"],
                            key="ca_tam_multiselect"
                        )
                        custom_ca_tam_input = st.text_input("Thêm ca giờ tùy chỉnh (nhiều ca cách nhau bằng dấu phẩy):", placeholder="VD: 08h00 - 10h00", key="custom_ca_tam_in")
                        shifts_to_apply = list(ca_tam_chon)
                        if custom_ca_tam_input.strip():
                            shifts_to_apply.extend([c.strip() for c in custom_ca_tam_input.split(",") if c.strip()])
                    
                    if st.form_submit_button("💾 Thiết Lập Lịch Tạm Thời", type="primary"):
                        if not target_hs_ids_tam:
                            st.warning("⚠️ Chưa chọn đối tượng học sinh!")
                        else:
                            total_saved = 0
                            for hs_id_item in target_hs_ids_tam:
                                current_thu_to_apply = []
                                if loai_td == "Nghỉ tạm thời trong khoảng thời gian này" and "__AUTO__" in selected_thu_list:
                                    base_thu_df = pd.read_sql_query(f"SELECT DISTINCT thu FROM lich_hoc_tuan WHERE hoc_sinh_id = {hs_id_item}", conn)
                                    if not base_thu_df.empty:
                                        current_thu_to_apply = base_thu_df['thu'].tolist()
                                else:
                                    current_thu_to_apply = selected_thu_list

                                if not current_thu_to_apply:
                                    continue
                                if not shifts_to_apply:
                                    continue

                                for t_item in current_thu_to_apply:
                                    for ca_item in shifts_to_apply:
                                        try:
                                            c.execute('''
                                                INSERT INTO lich_hoc_tam_thoi (hoc_sinh_id, ngay_bat_dau, ngay_ket_thuc, thu, ca_hoc, loai_thay_doi)
                                                VALUES (?, ?, ?, ?, ?, ?)
                                            ''', (hs_id_item, d_start.strftime("%Y-%m-%d"), d_end.strftime("%Y-%m-%d"), t_item, ca_item, loai_td))
                                            total_saved += 1
                                        except Exception:
                                            pass
                            conn.commit()
                            if total_saved > 0:
                                st.success(f"✅ Đã lưu thành công {total_saved} thiết lập lịch tạm thời! Lịch tổng quan đã được cập nhật.")
                                st.rerun()
                            else:
                                st.warning("⚠️ Không có thiết lập nào được lưu. Vui lòng kiểm tra lại ngày học hoặc ca học.")

        with sub_tab_list_t:
            st.markdown("##### 📋 Danh sách học sinh đang có thay đổi tạm thời & Ghi chú lịch gốc")
            df_temp_manage = pd.read_sql_query('''
                SELECT t.id, h.ho_ten, h.lop_hoc, t.ngay_bat_dau, t.ngay_ket_thuc, t.thu, t.ca_hoc, t.loai_thay_doi, t.hoc_sinh_id
                FROM lich_hoc_tam_thoi t
                JOIN hoc_sinh h ON t.hoc_sinh_id = h.id
                ORDER BY t.ngay_bat_dau DESC
            ''', conn)
            
            if df_temp_manage.empty:
                st.info("💡 Hiện tại chưa có thiết lập lịch tạm thời nào trong hệ thống.")
            else:
                notes = []
                for _, r in df_temp_manage.iterrows():
                    orig = pd.read_sql_query(f"SELECT ca_hoc FROM lich_hoc_tuan WHERE hoc_sinh_id = {r['hoc_sinh_id']} AND thu = '{r['thu']}'", conn)
                    orig_ca = ", ".join(orig['ca_hoc'].tolist()) if not orig.empty else "Không có lịch gốc"
                    if r['loai_thay_doi'] == 'Đổi ca / Học bù':
                        notes.append(f"🔄 Chiếm chỗ/thay thế ca gốc: {orig_ca}")
                    elif r['loai_thay_doi'] == 'Học thêm buổi':
                        notes.append(f"➕ Phát sinh thêm (Lịch gốc giữ nguyên: {orig_ca})")
                    else:
                        notes.append(f"🛑 Nghỉ toàn bộ vào {r['thu']}")
                
                df_temp_manage['Ghi chú lịch gốc'] = notes
                
                display_df = df_temp_manage[['id', 'ho_ten', 'lop_hoc', 'ngay_bat_dau', 'ngay_ket_thuc', 'thu', 'loai_thay_doi', 'Ghi chú lịch gốc']]
                display_df.columns = ['ID', 'Họ tên', 'Lớp', 'Từ ngày', 'Đến ngày', 'Thứ', 'Loại thay đổi', 'Ghi chú lịch gốc']
                st.dataframe(display_df, use_container_width=True)
                
                st.markdown("---")
                st.markdown("##### ⚙️ Sửa hoặc Xóa thiết lập lịch tạm thời")
                
                action_mode = st.radio("Chọn thao tác:", ["✏️ Sửa thiết lập", "❌ Xóa thiết lập"], horizontal=True, key="action_mode_tmp_merged")
                
                if action_mode == "✏️ Sửa thiết lập":
                    edit_tmp_id = st.selectbox("Chọn ID thiết lập lịch tạm thời cần sửa:", df_temp_manage['id'].tolist(), key="sel_edit_tmp_id_merged")
                    selected_tmp_row = df_temp_manage[df_temp_manage['id'] == edit_tmp_id].iloc[0]
                    
                    with st.form("form_edit_lich_tam_thoi_merged"):
                        st.markdown(f"**Đang sửa cho học sinh:** {selected_tmp_row['ho_ten']} (Lớp {selected_tmp_row['lop_hoc']})")
                        
                        try:
                            def_d_start = datetime.strptime(selected_tmp_row['ngay_bat_dau'], "%Y-%m-%d").date()
                        except:
                            def_d_start = date.today()
                        try:
                            def_d_end = datetime.strptime(selected_tmp_row['ngay_ket_thuc'], "%Y-%m-%d").date()
                        except:
                            def_d_end = date.today()
                            
                        ed_d_start = st.date_input("🗓️ Hiệu lực TỪ ngày", value=def_d_start, key="ed_d_start_m")
                        ed_d_end = st.date_input("🗓️ Hiệu lực ĐẾN ngày", value=def_d_end, key="ed_d_end_m")
                        
                        loai_td_options = [
                            "Đổi ca / Học bù", 
                            "Học thêm buổi", 
                            "Nghỉ tạm thời trong khoảng thời gian này"
                        ]
                        def_loai_idx = loai_td_options.index(selected_tmp_row['loai_thay_doi']) if selected_tmp_row['loai_thay_doi'] in loai_td_options else 0
                        ed_loai_td = st.selectbox("Loại thay đổi", loai_td_options, index=def_loai_idx, key="ed_loai_td_m")
                        
                        cac_thu_list = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
                        def_thu_idx = cac_thu_list.index(selected_tmp_row['thu']) if selected_tmp_row['thu'] in cac_thu_list else 0
                        ed_thu_tam = st.selectbox("Vào Thứ", cac_thu_list, index=def_thu_idx, key="ed_thu_tam_m")
                        
                        ed_ca_tam_final = ""
                        if ed_loai_td == "Nghỉ tạm thời trong khoảng thời gian này":
                            ed_ca_tam_final = "Nghỉ cả ngày"
                        else:
                            def_ca = selected_tmp_row['ca_hoc']
                            def_ca_idx = DANH_SACH_CA_MAU.index(def_ca) if def_ca in DANH_SACH_CA_MAU else 5
                            ed_ca_tam_sel = st.selectbox("Vào Ca", DANH_SACH_CA_MAU + ["⏱️ Tự nhập giờ tùy chỉnh..."], index=def_ca_idx if def_ca_idx < len(DANH_SACH_CA_MAU) else len(DANH_SACH_CA_MAU), key="ed_ca_tam_sel_m")
                            custom_ca_edit_input = st.text_input("Nếu chọn tự nhập giờ, nhập vào đây:", value=def_ca if def_ca_idx >= len(DANH_SACH_CA_MAU) else "18h00 - 20h00", key="custom_ca_edit_input_m")
                            ed_ca_tam_final = custom_ca_edit_input.strip() if (ed_ca_tam_sel == "⏱️ Tự nhập giờ tùy chỉnh..." and custom_ca_edit_input.strip()) else ed_ca_tam_sel
                        
                        if st.form_submit_button("💾 Cập Nhật Lịch Tạm Thời", type="primary"):
                            c.execute('''
                                UPDATE lich_hoc_tam_thoi 
                                SET ngay_bat_dau = ?, ngay_ket_thuc = ?, thu = ?, ca_hoc = ?, loai_thay_doi = ?
                                WHERE id = ?
                            ''', (ed_d_start.strftime("%Y-%m-%d"), ed_d_end.strftime("%Y-%m-%d"), ed_thu_tam, ed_ca_tam_final, ed_loai_td, int(edit_tmp_id)))
                            conn.commit()
                            st.success(f"✅ Đã cập nhật thiết lập lịch tạm thời (ID: {edit_tmp_id}) thành công! Lịch tổng quan đã được làm mới.")
                            st.rerun()
                else:
                    selected_del_id = st.selectbox("Chọn ID thiết lập lịch tạm thời cần xóa:", df_temp_manage['id'].tolist(), key="sel_del_tmp_id_merged")
                    
                    if st.button("❌ Xóa thiết lập tạm thời này", type="primary"):
                        c.execute("DELETE FROM lich_hoc_tam_thoi WHERE id = ?", (selected_del_id,))
                        conn.commit()
                        st.success(f"✅ Đã xóa thiết lập (ID: {selected_del_id}) thành công! Lịch tổng quan đã được cập nhật lại.")
                        st.rerun()

    with tab_export:
        st.markdown("### 🖼️ Xuất File Lịch Học Hàng Tuần Dạng Ảnh PNG (Không Lỗi Font)")
        df_hs_all = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", conn)

        if df_hs_all.empty:
            st.warning("Chưa có dữ liệu học sinh.")
        else:
            sel_date_export = st.date_input("🗓️ Chọn tuần để xuất ảnh:", date.today(), key="sel_date_export_img_m")
            filter_mode = st.radio("Chọn phạm vi xuất lịch học:", ["Toàn bộ các Lớp", "Theo Lớp cụ thể", "Theo Học sinh cụ thể"], horizontal=True, key="filter_mode_exp_m")
            
            target_title = "Tất Cả Các Lớp"
            selected_lop_exp = None
            selected_hs_exp = None
            prefix_label = "Đối tượng / Lớp: "

            if filter_mode == "Toàn bộ các Lớp":
                target_title = "Tất Cả Các Lớp"
                prefix_label = "Đối tượng / Lớp: "
            elif filter_mode == "Theo Lớp cụ thể":
                lop_list = sorted(df_hs_all['lop_hoc'].dropna().unique().tolist())
                selected_lop_exp = st.selectbox("Chọn Lớp:", lop_list, key="sel_lop_exp_m")
                target_title = f"{selected_lop_exp}"
                prefix_label = "Lớp: "
            elif filter_mode == "Theo Học sinh cụ thể":
                hs_dict_exp = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row for _, row in df_hs_all.iterrows()}
                sel_hs_label = st.selectbox("Chọn Học sinh:", list(hs_dict_exp.keys()), key="sel_hs_label_exp_m")
                selected_hs_row = hs_dict_exp[sel_hs_label]
                selected_hs_exp = selected_hs_row['id']
                target_title = f"{selected_hs_row['ho_ten']} ({selected_hs_row['lop_hoc']})"
                prefix_label = "Học sinh/Lớp: "

            df_export_matrix = get_schedule_matrix_df(conn, filter_lop=selected_lop_exp, filter_hs_id=selected_hs_exp, ref_date=sel_date_export)

            if df_export_matrix.empty:
                st.info("ℹ️ Không tìm thấy lịch học phù hợp đối với lựa chọn này.")
            else:
                start_w = sel_date_export - timedelta(days=sel_date_export.weekday())
                end_w = start_w + timedelta(days=6)
                week_text = f"(Tuần từ {start_w.strftime('%d/%m/%Y')} đến {end_w.strftime('%d/%m/%Y')})"

                st.markdown(f"#### 📋 Xem trước Lịch Học Tuần ({prefix_label} {target_title})")
                st.markdown(f"<p style='font-size: 14px; color: #475569; margin-bottom: 5px;'>{week_text}</p>", unsafe_allow_html=True)
                st.write(df_export_matrix.to_html(index=False, escape=False), unsafe_allow_html=True)
                st.markdown("<p style='font-style: italic; color: #475569; font-size: 14px;'>Ghi chú: Áp dụng cho các tuần tiếp nếu không có thay đổi</p>", unsafe_allow_html=True)
                st.divider()

                if HAS_MATPLOTLIB:
                    img_bytes = create_weekly_schedule_image(target_title, df_export_matrix, ref_date=sel_date_export, prefix=prefix_label)
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
# --- CHỨC NĂNG 3: GỢI Ý SMART ASSISTANT ---
# =========================================================
elif choice == "3. 💡 Gợi ý Smart Assistant":
    st.subheader("💡 Gợi Ý Smart Assistant")
    st.info("🤖 Trợ lý thông minh đang hỗ trợ phân tích lịch học và nhắc nhở học phí tự động.")

# =========================================================
# --- CHỨC NĂNG 4: QUẢN LÝ HỌC PHÍ & THỐNG KÊ (LỌC ĐA THÁNG, TÌM KIẾM, XUẤT ẢNH) ---
# =========================================================
elif choice == "4. 💳 Quản Lý Học Phí & Thống Kê (Lọc Đa Tháng / Xuất Ảnh)":
    st.subheader("💳 Thống Kê Điểm Danh, Quản Lý Học Phí & Xuất Hóa Đơn Ảnh PNG")
    
    col_y, col_m = st.columns([1, 3])
    with col_y:
        nam_selected = st.number_input("Chọn Năm", min_value=2020, max_value=2035, value=datetime.now().year)
    with col_m:
        thang_options = list(range(1, 13))
        selected_thangs = st.multiselect(
            "Chọn Tháng (Có thể chọn 1 hoặc nhiều tháng để lọc):", 
            thang_options, 
            default=[datetime.now().month],
            format_func=lambda x: f"Tháng {x}"
        )
        
    search_query = st.text_input("🔍 Tìm kiếm học phí của học sinh theo tên:", placeholder="Nhập tên học sinh cần tìm...")
    st.divider()

    if not selected_thangs:
        st.warning("⚠️ Vui lòng chọn ít nhất một tháng để xem thống kê học phí.")
    else:
        qr_path = "qr_code.png" if os.path.exists("qr_code.png") else None
        
        all_dfs = []
        for th in selected_thangs:
            thang_nam_query = f"{nam_selected}-{th:02d}"
            thang_nam_key = f"{th:02d}/{nam_selected}"
            
            q = f'''
                SELECT 
                    h.id AS hoc_sinh_id, 
                    h.ho_ten AS 'Họ và Tên', 
                    h.lop_hoc AS 'Lớp', 
                    h.mon_hoc AS 'Môn Học', 
                    h.hoc_phi_buoi AS 'Đơn Giá/Ca (VNĐ)',
                    '{thang_nam_key}' AS 'Tháng/Năm',
                    SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS 'Số Ca Có Mặt',
                    SUM(CASE WHEN d.trang_thai = 'Vắng có phép' THEN 1 ELSE 0 END) AS 'Vắng Có Phép',
                    SUM(CASE WHEN d.trang_thai = 'Vắng không phép' THEN 1 ELSE 0 END) AS 'Vắng Không Phép',
                    (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS 'Tổng Tiền (VNĐ)',
                    COALESCE(t.trang_thai, 'Chưa đóng') AS 'Trạng Thái'
                FROM hoc_sinh h
                LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND strftime('%Y-%m', d.ngay) = '{thang_nam_query}'
                LEFT JOIN thanh_toan t ON h.id = t.hoc_sinh_id AND t.thang_nam = '{thang_nam_key}'
                GROUP BY h.id
            '''
            df_th = pd.read_sql_query(q, conn)
            all_dfs.append(df_th)
            
        combined_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
        
        if not combined_df.empty and search_query.strip():
            combined_df = combined_df[combined_df['Họ và Tên'].str.contains(search_query.strip(), case=False, na=False)]

        if combined_df.empty:
            st.info("ℹ️ Không tìm thấy dữ liệu học phí phù hợp với bộ lọc.")
        else:
            st.markdown("#### 📋 Bảng Chi Tiết Học Phí & Trạng Thái Thanh Toán")
            
            for idx, row in combined_df.iterrows():
                c1, c2, c3, c4, c5, c6, c7 = st.columns([2.2, 1.2, 1.2, 1.2, 1.5, 1.8, 1.8])
                c1.write(f"**{row['Họ và Tên']}**\n\n*Lớp: {row['Lớp']} ({row['Tháng/Năm']})*")
                c2.write(f"{row['Số Ca Có Mặt']} ca")
                c3.write(f"{row['Đơn Giá/Ca (VNĐ)']:,.0f} đ")
                c4.write(f"**{row['Tổng Tiền (VNĐ)']:,.0f} đ**")
                
                is_paid = (row['Trạng Thái'] == 'Đã đóng')
                c5.write("🟢 Đã đóng" if is_paid else "🔴 Chưa đóng")
                
                btn_lbl = "Chuyển Chưa đóng" if is_paid else "Xác nhận Đã đóng"
                if c6.button(btn_lbl, key=f"btn_pay_{row['hoc_sinh_id']}_{row['Tháng/Năm']}"):
                    new_stt = 'Chưa đóng' if is_paid else 'Đã đóng'
                    t_str = date.today().strftime("%Y-%m-%d") if new_stt == 'Đã đóng' else ""
                    c.execute('''
                        INSERT INTO thanh_toan (hoc_sinh_id, thang_nam, trang_thai, ngay_thu)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(hoc_sinh_id, thang_nam) 
                        DO UPDATE SET trang_thai = excluded.trang_thai, ngay_thu = excluded.ngay_thu
                    ''', (row['hoc_sinh_id'], row['Tháng/Năm'], new_stt, t_str))
                    conn.commit()
                    st.rerun()

                with c7:
                    if HAS_MATPLOTLIB:
                        img_bytes = create_tuition_slip_image(
                            student_name=row['Họ và Tên'],
                            lop_hoc=row['Lớp'],
                            subject=row['Môn Học'] or 'Chung',
                            price_per_lesson=row['Đơn Giá/Ca (VNĐ)'],
                            month_year=row['Tháng/Năm'],
                            total_lessons=row['Số Ca Có Mặt'],
                            total_fee=row['Tổng Tiền (VNĐ)'],
                            status=row['Trạng Thái'],
                            qr_path=qr_path
                        )
                        st.download_button(
                            label="🖼️ Tải Ảnh Phiếu",
                            data=img_bytes,
                            file_name=f"Hoa_Don_{row['Họ và Tên'].replace(' ', '_')}_{row['Tháng/Năm'].replace('/', '_')}.png",
                            mime="image/png",
                            key=f"img_fee_{row['hoc_sinh_id']}_{row['Tháng/Năm']}"
                        )
                st.divider()

            st.markdown("### 📊 Bảng Tổng Hợp Học Phí Toàn Bộ Danh Sách")
            total_ca_all = combined_df['Số Ca Có Mặt'].sum()
            total_money_all = combined_df['Tổng Tiền (VNĐ)'].sum()
            total_paid_count = len(combined_df[combined_df['Trạng Thái'] == 'Đã đóng'])
            total_unpaid_count = len(combined_df[combined_df['Trạng Thái'] == 'Chưa đóng'])

            sum_data = {
                "Chỉ số tổng hợp": [
                    "Tổng số lượt học sinh lọc",
                    "Tổng số ca học (có mặt)",
                    "Tổng doanh thu học phí",
                    "Số suất đã hoàn thành đóng",
                    "Số suất chưa đóng"
                ],
                "Giá trị": [
                    f"{len(combined_df)} bản ghi",
                    f"{total_ca_all} ca",
                    f"{total_money_all:,.0f} VNĐ",
                    f"{total_paid_count} suất",
                    f"{total_unpaid_count} suất"
                ]
            }
            st.dataframe(pd.DataFrame(sum_data), use_container_width=True, hide_index=True)

# =========================================================
# --- CHỨC NĂNG 5: SỬA & XÓA DỮ LIỆU ---
# =========================================================
elif choice == "5. Sửa & Xóa dữ liệu":
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
                    hoc_phi_new = st.number_input("Học phí mỗi ca (VNĐ)", min_value=0, step=10000, value=150000)
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
                        hoc_phi_edit = st.number_input("Học phí mỗi ca (VNĐ)", min_value=0, step=10000, value=int(selected_hs_row['hoc_phi_buoi'] or 150000))
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
                hoc_phi_buoi AS "Học phí/Ca (VNĐ)", 
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
