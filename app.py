import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date, datetime, timedelta
import os
import json
import re
import io
import textwrap
import zipfile

# Thử import Matplotlib để xuất lịch học, phiếu học phí & lịch sử điểm danh dạng ảnh PNG
try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# --- CẤU HÌNH TRANG WEB ---
st.set_page_config(page_title="Quản Lý Học Sinh Học Thêm", layout="wide", page_icon="📚")

# --- KẾT NỐI SUPABASE (POSTGRESQL) QUA DATABASE_URL TRONG SECRETS ---
db_url = st.secrets["DATABASE_URL"]
engine = create_engine(db_url)

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

# --- HÀM LẤY LỊCH HỌC HIỆU LỰC CHO MỘT NGÀY ---
def get_active_schedule_for_date(engine, check_date):
    target_day_str = get_vietnamese_weekday(check_date)
    date_str = check_date.strftime("%Y-%m-%d")

    query_base = f'''
        SELECT l.hoc_sinh_id, h.ho_ten, h.lop_hoc, h.mon_hoc, l.ca_hoc, 'Lịch gốc' AS nguon
        FROM lich_hoc_tuan l
        JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
        WHERE l.thu = '{target_day_str}'
    '''
    df_base = pd.read_sql_query(query_base, engine)

    query_temp = f'''
        SELECT t.id, t.hoc_sinh_id, h.ho_ten, h.lop_hoc, h.mon_hoc, t.thu, t.ca_hoc, t.loai_thay_doi, t.ngay_bat_dau, t.ngay_ket_thuc
        FROM lich_hoc_tam_thoi t
        JOIN hoc_sinh h ON t.hoc_sinh_id = h.id
        WHERE t.ngay_bat_dau <= '{date_str}' AND t.ngay_ket_thuc >= '{date_str}'
    '''
    df_temp = pd.read_sql_query(query_temp, engine)

    exclude_pairs = set()
    additional_rows = []

    if not df_temp.empty:
        for _, r in df_temp.iterrows():
            hs_id = r['hoc_sinh_id']
            loai = r['loai_thay_doi']
            thu_tam = r['thu']
            ca_tam = r['ca_hoc']
            
            if thu_tam == target_day_str:
                if loai in ['Nghỉ tạm thời trong khoảng thời gian này', 'Đổi ca / Học bù']:
                    exclude_pairs.add((hs_id, ca_tam))
                elif loai == 'Học thêm buổi':
                    additional_rows.append({
                        'hoc_sinh_id': hs_id, 'ho_ten': r['ho_ten'], 'lop_hoc': r['lop_hoc'],
                        'mon_hoc': r['mon_hoc'], 'ca_hoc': ca_tam, 'nguon': 'Học thêm'
                    })

    if not df_base.empty and len(exclude_pairs) > 0:
        mask = df_base.apply(lambda row: (row['hoc_sinh_id'], row['ca_hoc']) not in exclude_pairs, axis=1)
        df_base = df_base[mask]

    df_additions = pd.DataFrame(additional_rows)
    cols = ['hoc_sinh_id', 'ho_ten', 'lop_hoc', 'mon_hoc', 'ca_hoc', 'nguon']
    return pd.concat([
        df_base[cols] if not df_base.empty else pd.DataFrame(columns=cols),
        df_additions[cols] if not df_additions.empty else pd.DataFrame(columns=cols)
    ], ignore_index=True)

# --- HÀM ĐỒNG BỘ LỊCH SANG GOOGLE CALENDAR ---
def sync_weekly_schedule_to_google(calendar_id='a.luongxdnb@gmail.com', days_ahead=7):
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return False, "⚠️ Chưa cài đặt thư viện Google trong requirements.txt"

    try:
        scopes = ['https://www.googleapis.com/auth/calendar']
        creds = Credentials.from_service_account_info(json.loads(st.secrets["GOOGLE_CREDENTIALS_JSON"]), scopes=scopes)
        service = build('calendar', 'v3', credentials=creds)

        today = date.today()
        end_date = today + timedelta(days=days_ahead)
        time_min = f"{today.strftime('%Y-%m-%d')}T00:00:00Z"
        time_max = f"{end_date.strftime('%Y-%m-%d')}T23:59:59Z"

        events_result = service.events().list(calendarId=calendar_id, timeMin=time_min, timeMax=time_max, singleEvents=True).execute()
        for evt in events_result.get('items', []):
            if evt.get('summary', '').startswith("🏫 Dạy Thêm Ca"):
                try: service.events().delete(calendarId=calendar_id, eventId=evt['id']).execute()
                except Exception: pass

        count_events = 0
        ca_hoc_time = {
            "7h00 - 9h00": ("07:00:00", "09:00:00"), "9h00 - 11h00": ("09:00:00", "11:00:00"),
            "13h30 - 15h30": ("13:30:00", "15:30:00"), "14h00 - 16h00": ("14:00:00", "16:00:00"),
            "15h30 - 17h30": ("15:30:00", "17:30:00"), "17h30 - 19h30": ("17:30:00", "19:30:00"),
            "19h30 - 21h30": ("19:30:00", "21:30:00")
        }

        for i in range(days_ahead):
            current_date = today + timedelta(days=i)
            df_day = get_active_schedule_for_date(engine, current_date)
            if df_day.empty: continue
            date_str = current_date.strftime("%Y-%m-%d")

            for ca, group_ca in df_day.groupby('ca_hoc'):
                st_time, en_time = ca_hoc_time.get(ca, ("17:30:00", "19:30:00"))
                details = [f"• Lớp {lop}: {', '.join(g['ho_ten'].tolist())}" for lop, g in group_ca.groupby('lop_hoc')]
                event = {
                    'summary': f"🏫 Dạy Thêm Ca {ca} ({len(group_ca)} HS)",
                    'description': "📚 DANH SÁCH HỌC SINH:\n" + "\n".join(details),
                    'start': {'dateTime': f"{date_str}T{st_time}+07:00", 'timeZone': 'Asia/Ho_Chi_Minh'},
                    'end': {'dateTime': f"{date_str}T{en_time}+07:00", 'timeZone': 'Asia/Ho_Chi_Minh'},
                    'reminders': {'useDefault': False, 'overrides': [{'method': 'popup', 'minutes': 30}]}
                }
                service.events().insert(calendarId=calendar_id, body=event).execute()
                count_events += 1

        return True, f"✅ Đã đồng bộ thành công {count_events} ca dạy!"
    except Exception as e:
        return False, f"❌ Lỗi đồng bộ: {str(e)}"

# --- HÀM SẮP XẾP CA HỌC & LẤY BUỔI ---
def ca_hoc_sort_key(ca_str):
    predefined = ["7h00 - 9h00", "9h00 - 11h00", "13h30 - 15h30", "14h00 - 16h00", "15h30 - 17h30", "17h30 - 19h30", "19h30 - 21h30"]
    if ca_str in predefined: return (0, predefined.index(ca_str))
    match = re.search(r'(\d+)h?(\d*)', str(ca_str))
    if match: return (1, int(match.group(1)) * 60 + (int(match.group(2)) if match.group(2) else 0))
    return (2, str(ca_str))

def get_buoi_from_ca(ca_str):
    predefined = {
        "7h00 - 9h00": "🌅 Sáng", "9h00 - 11h00": "🌅 Sáng",
        "13h30 - 15h30": "☀️ Chiều", "14h00 - 16h00": "☀️ Chiều", "15h30 - 17h30": "☀️ Chiều",
        "17h30 - 19h30": "🌙 Tối", "19h30 - 21h30": "🌙 Tối"
    }
    if ca_str in predefined: return predefined[ca_str]
    match = re.search(r'(\d+)h?(\d*)', str(ca_str))
    if match:
        h = int(match.group(1))
        return "🌅 Sáng" if h < 12 else ("☀️ Chiều" if h < 18 else "🌙 Tối")
    return "☀️ Chiều"

# --- HÀM MA TRẬN LỊCH HỌC & XUẤT ẢNH LỊCH ---
def get_schedule_matrix_df(engine, filter_lop=None, filter_hs_id=None, ref_date=None):
    if ref_date is None: ref_date = date.today()
    cac_thu = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
    start_monday = ref_date - timedelta(days=ref_date.weekday())
    
    day_schedules = {}
    for i, t in enumerate(cac_thu):
        current_d = start_monday + timedelta(days=i)
        df_day = get_active_schedule_for_date(engine, current_d)
        if not df_day.empty:
            if filter_lop: df_day = df_day[df_day['lop_hoc'] == filter_lop]
            elif filter_hs_id: df_day = df_day[df_day['hoc_sinh_id'] == filter_hs_id]
        day_schedules[t] = df_day

    all_cas = set()
    for t in cac_thu:
        df_d = day_schedules[t]
        if not df_d.empty and 'ca_hoc' in df_d.columns:
            all_cas.update(df_d['ca_hoc'].unique().tolist())
    if not all_cas: return pd.DataFrame()

    matrix_rows = []
    for ca in sorted(list(all_cas), key=ca_hoc_sort_key):
        row_dict = {"Buổi": get_buoi_from_ca(ca), "Ca học": ca}
        for t in cac_thu:
            df_d = day_schedules[t]
            if df_d.empty: row_dict[t] = "-"
            else:
                matched = df_d[df_d['ca_hoc'] == ca]
                if matched.empty: row_dict[t] = "-"
                else:
                    items = []
                    for lop, g in matched.groupby('lop_hoc'):
                        names_list = [f"{row['ho_ten']}" + (f" ({row['nguon']})" if row.get('nguon') != 'Lịch gốc' else "") for _, row in g.iterrows()]
                        items.append(", ".join(names_list) if (filter_lop or filter_hs_id) else f"<b>[{lop}]</b><br>" + "<br>".join(names_list))
                    row_dict[t] = "<br>".join(items)
        matrix_rows.append(row_dict)
    return pd.DataFrame(matrix_rows)[["Buổi", "Ca học"] + cac_thu]

def render_schedule_matrix(engine, ref_date=None):
    df_matrix = get_schedule_matrix_df(engine, ref_date=ref_date)
    if df_matrix.empty: st.info("💡 Chưa có lịch học tuần nào được thiết lập.")
    else: st.write(df_matrix.to_html(index=False, escape=False), unsafe_allow_html=True)

def create_weekly_schedule_image(title_target, df_matrix, ref_date=None, prefix="Học sinh / Lớp: "):
    if ref_date is None: ref_date = date.today()
    fig, ax = plt.subplots(figsize=(24, len(df_matrix) * 0.8 + 5.0))
    ax.axis('off'); ax.axis('tight')
    start_w, end_w = ref_date - timedelta(days=ref_date.weekday()), ref_date - timedelta(days=ref_date.weekday()) + timedelta(days=6)
    
    table_data = [df_matrix.columns.tolist()] + df_matrix.values.tolist()
    table = ax.table(cellText=table_data, loc='center', cellLoc='center', colWidths=[0.08, 0.12, 0.12, 0.12, 0.12, 0.12, 0.12, 0.12, 0.12])
    table.auto_set_font_size(False); table.set_fontsize(12); table.scale(1, 2.5)
    
    ax.text(0.5, 1.15, "THỜI KHÓA BIỂU LỊCH HỌC HÀNG TUẦN", transform=ax.transAxes, fontsize=17, fontweight='bold', color='#1E3A8A', ha='center')
    ax.text(0.5, 1.08, f"{prefix}{title_target}", transform=ax.transAxes, fontsize=14, fontweight='bold', color='#0F172A', ha='center')
    ax.text(0.5, 1.02, f"(Tuần từ {start_w.strftime('%d/%m/%Y')} đến {end_w.strftime('%d/%m/%Y')})", transform=ax.transAxes, fontsize=11.5, color='#475569', ha='center')
    
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#CBD5E1')
        if row == 0: cell.set_facecolor('#1E3A8A'); cell.set_text_props(color='white', weight='bold')
        else: cell.set_facecolor('#FEF3C7' if col == 0 else ('#E0F2FE' if col == 1 else ('#F8FAFC' if row % 2 == 0 else 'white')))
        
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig); buffer.seek(0)
    return buffer

# --- HÀM TẠO ẢNH HÓA ĐƠN HỌC PHÍ (TỰ ĐỘNG LỌC BỎ THÁNG 0 CA) ---
def create_tuition_slip_image_multi(student_name, lop_hoc, subject, month_details, total_lessons, total_fee, status, qr_path):
    valid_months = [md for md in month_details if md['so_ca'] > 0]
    is_multi = len(valid_months) > 1
    
    fig, ax = plt.subplots(figsize=(8, 10 + (len(valid_months) * 0.4 if is_multi else 0)))
    ax.axis('off')
    
    ax.text(0.5, 0.95, "PHIẾU BÁO HỌC PHÍ NHIỀU THÁNG" if is_multi else "PHIẾU BÁO HỌC PHÍ DẠY THÊM", fontsize=16, fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    
    if is_multi:
        ax.text(0.5, 0.91, f"Tổng hợp {len(valid_months)} tháng có phát sinh", fontsize=13, fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    else:
        display_month = valid_months[0]['thang'] if valid_months else (month_details[0]['thang'] if month_details else "")
        ax.text(0.5, 0.91, f"Thời gian: {display_month}", fontsize=13, fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    
    y_pos = 0.84
    ax.text(0.1, y_pos, f"Họ và tên học sinh: {student_name}", fontsize=11.5, fontweight='bold', color='#1E293B', transform=ax.transAxes); y_pos -= 0.045
    ax.text(0.1, y_pos, f"Lớp / Nhóm học: {lop_hoc}", fontsize=11.5, color='#1E293B', transform=ax.transAxes); y_pos -= 0.045
    ax.text(0.1, y_pos, f"Môn học: {subject}", fontsize=11.5, color='#1E293B', transform=ax.transAxes); y_pos -= 0.055
    
    if is_multi:
        ax.text(0.1, y_pos, "Chi tiết học phí theo từng tháng:", fontsize=11.5, fontweight='bold', color='#1E3A8A', transform=ax.transAxes); y_pos -= 0.045
        for md in valid_months:
            ax.text(0.12, y_pos, f" • Tháng {md['thang']}: {md['so_ca']} ca x {md['don_gia']:,.0f} đ = {md['thanh_tien']:,.0f} VNĐ", fontsize=10.5, color='#334155', transform=ax.transAxes)
            y_pos -= 0.04
        y_pos -= 0.02
        actual_total_lessons = sum([md['so_ca'] for md in valid_months])
        actual_total_fee = sum([md['thanh_tien'] for md in valid_months])
    else:
        md = valid_months[0] if valid_months else (month_details[0] if month_details else {'don_gia': 0, 'so_ca': 0, 'thanh_tien': 0})
        ax.text(0.1, y_pos, f"Học phí / ca: {md['don_gia']:,.0f} VNĐ", fontsize=11.5, transform=ax.transAxes); y_pos -= 0.045
        ax.text(0.1, y_pos, f"Tổng số ca học: {md['so_ca']} ca", fontsize=11.5, transform=ax.transAxes); y_pos -= 0.055
        actual_total_lessons = md['so_ca']
        actual_total_fee = md['thanh_tien']
        
    ax.text(0.1, y_pos, f"TỔNG SỐ CA: {actual_total_lessons} ca", fontsize=12, fontweight='bold', color='#1E3A8A', transform=ax.transAxes); y_pos -= 0.045
    ax.text(0.1, y_pos, f"TỔNG CỘNG HỌC PHÍ: {actual_total_fee:,.0f} VNĐ", fontsize=13, fontweight='bold', color='#B91C1C', transform=ax.transAxes); y_pos -= 0.045
    ax.text(0.1, y_pos, f"Trạng thái thanh toán: {status}", fontsize=11.5, fontweight='bold', color='#1E293B', transform=ax.transAxes)
        
    if qr_path and os.path.exists(qr_path):
        try:
            ax_inset = fig.add_axes([0.35, 0.08, 0.3, 0.28])
            ax_inset.imshow(plt.imread(qr_path)); ax_inset.axis('off')
            ax.text(0.5, 0.38, "Mã QR Thanh Toán Chuyển Khoản", fontsize=10.5, fontweight='bold', color='#1E3A8A', ha='center', transform=ax.transAxes)
        except Exception: pass
            
    ax.text(0.5, 0.02, "Trân trọng cảm ơn sự đồng hành của Quý phụ huynh!", fontsize=10.5, style='italic', fontweight='bold', color='#1E3A8A', ha='center', transform=ax.transAxes)
    
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig); buffer.seek(0)
    return buffer

def create_student_attendance_history_image(student_name, lop_hoc, month_year, df_history, total_present):
    fig, ax = plt.subplots(figsize=(10, max(4, len(df_history) * 0.5 + 3.5)))
    ax.axis('off'); ax.axis('tight')
    ax.text(0.5, 0.94, "LỊCH SỬ ĐIỂM DANH & NHẬN XÉT HỌC SINH", fontsize=15, fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    ax.text(0.5, 0.89, f"Học sinh: {student_name} - Lớp: {lop_hoc} ({month_year})", fontsize=12, fontweight='bold', color='#0F172A', ha='center', va='center', transform=ax.transAxes)
    ax.text(0.5, 0.84, f"Tổng số buổi đi học (Có mặt): {total_present} buổi", fontsize=11, fontweight='bold', color='#B91C1C', ha='center', va='center', transform=ax.transAxes)
    
    table = ax.table(cellText=[df_history.columns.tolist()] + df_history.values.tolist(), loc='center', cellLoc='center', colWidths=[0.18, 0.22, 0.22, 0.38])
    table.auto_set_font_size(False); table.set_fontsize(9.5); table.scale(1, 2.2)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#CBD5E1')
        if row == 0: cell.set_facecolor('#1E3A8A'); cell.set_text_props(color='white', weight='bold')
        else: cell.set_facecolor('#F8FAFC' if row % 2 == 0 else 'white')
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig); buffer.seek(0)
    return buffer

# --- 1. KHỞI TẠO BẢNG TRÊN SUPABASE ---
with engine.begin() as conn:
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS hoc_sinh (
            id SERIAL PRIMARY KEY, ho_ten TEXT NOT NULL, lop_hoc TEXT DEFAULT 'Lớp chung',
            mon_hoc TEXT, hoc_phi_buoi REAL NOT NULL, thong_tin_phu_huynh TEXT
        )
    '''))
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS diem_danh (
            id SERIAL PRIMARY KEY, hoc_sinh_id INTEGER, ngay DATE,
            ca_hoc TEXT DEFAULT '7h00 - 9h00', trang_thai TEXT DEFAULT 'Có mặt', nhan_xet TEXT
        )
    '''))
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS thanh_toan (
            id SERIAL PRIMARY KEY, hoc_sinh_id INTEGER, thang_nam TEXT,
            trang_thai TEXT DEFAULT 'Chưa đóng', ngay_thu TEXT, UNIQUE(hoc_sinh_id, thang_nam)
        )
    '''))
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS lich_hoc_tuan (
            id SERIAL PRIMARY KEY, hoc_sinh_id INTEGER, thu TEXT, ca_hoc TEXT, UNIQUE(hoc_sinh_id, thu, ca_hoc)
        )
    '''))
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS lich_hoc_tam_thoi (
            id SERIAL PRIMARY KEY, hoc_sinh_id INTEGER, ngay_bat_dau DATE,
            ngay_ket_thuc DATE, thu TEXT, ca_hoc TEXT, loai_thay_doi TEXT DEFAULT 'Đổi ca / Học bù'
        )
    '''))
    try: conn.execute(text("ALTER TABLE hoc_sinh ADD COLUMN IF NOT EXISTS thong_tin_phu_huynh TEXT"))
    except Exception: pass

# --- 2. GIAO DIỆN CHÍNH ---
st.title("📚 Phần Mềm Quản Lý Dạy Thêm Tại Nhà (Supabase)")

if st.sidebar.button("🚪 Đăng xuất", type="secondary", use_container_width=True):
    st.session_state.logged_in = False; st.rerun()

menu = [
    "0. 📊 Trang Chủ Dashboard", "1. Điểm danh & Nhận xét", 
    "2. 🗺️ Quản Lý & Ma Trận Lịch Học", "3. 💳 Thống Kê Số Ca & Quản Lý Học Phí", "4. Sửa & Xóa dữ liệu"
]
choice = st.sidebar.selectbox("📋 Danh mục chức năng", menu)

st.sidebar.markdown("---")
st.sidebar.subheader("📲 Đồng Bộ Lịch Sang iPhone")
user_gmail = st.sidebar.text_input("Địa chỉ Gmail trên iPhone:", value="a.luongxdnb@gmail.com")
if st.sidebar.button("🔄 Đồng Bộ Lịch 7 Ngày Tới", type="primary"):
    success, msg = sync_weekly_schedule_to_google(calendar_id=user_gmail.strip() or 'primary', days_ahead=7)
    if success: st.sidebar.success(msg)
    else: st.sidebar.error(msg)

st.sidebar.markdown("---")
st.sidebar.subheader("📷 Cài đặt Mã QR Thanh Toán")
qr_file = st.sidebar.file_uploader("Tải lên ảnh Mã QR", type=["png", "jpg", "jpeg"])
if qr_file is not None:
    with open("qr_code.png", "wb") as f: f.write(qr_file.getbuffer())
    st.sidebar.success("✅ Đã lưu mã QR thành công!")
if os.path.exists("qr_code.png"): st.sidebar.image("qr_code.png", caption="Mã QR hiện tại", use_container_width=True)

# =========================================================
# --- CHỨC NĂNG 0: TRANG CHỦ DASHBOARD ---
# =========================================================
if choice == "0. 📊 Trang Chủ Dashboard":
    st.subheader("📊 Trang Chủ Dashboard Tổng Quan Trong Ngày")
    today = date.today()
    st.info(f"🗓️ Hôm nay: **{today.strftime('%d/%m/%Y')} ({get_vietnamese_weekday(today)})**")
    
    df_today = get_active_schedule_for_date(engine, today)
    curr_y, curr_m = today.year, today.month
    start_date_str = f"{curr_y - 1}-{curr_m:02d}-01"
    end_date_str = f"{curr_y}-{curr_m:02d}-01"
    
    df_unpaid_details = pd.read_sql_query(f'''
        SELECT h.id, h.ho_ten, h.lop_hoc, h.hoc_phi_buoi, TO_CHAR(d.ngay, 'MM/YYYY') AS thang_nam, COUNT(d.id) AS so_ca
        FROM hoc_sinh h
        JOIN diem_danh d ON h.id = d.hoc_sinh_id
        WHERE d.trang_thai = 'Có mặt' AND d.ngay >= '{start_date_str}' AND d.ngay < '{end_date_str}'
          AND NOT EXISTS (SELECT 1 FROM thanh_toan t WHERE t.hoc_sinh_id = h.id AND t.thang_nam = TO_CHAR(d.ngay, 'MM/YYYY') AND t.trang_thai = 'Đã đóng')
        GROUP BY h.id, h.ho_ten, h.lop_hoc, h.hoc_phi_buoi, TO_CHAR(d.ngay, 'MM/YYYY')
        ORDER BY thang_nam DESC, h.ho_ten ASC
    ''', engine)
    
    total_debt_amount = (df_unpaid_details['so_ca'] * df_unpaid_details['hoc_phi_buoi']).sum() if not df_unpaid_details.empty else 0
    unique_unpaid_students = df_unpaid_details['id'].nunique() if not df_unpaid_details.empty else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("🏫 Ca dạy hôm nay", f"{df_today['ca_hoc'].nunique() if not df_today.empty else 0} ca", f"{len(df_today) if not df_today.empty else 0} lượt HS")
    c2.metric("💳 Học sinh chưa đóng phí", f"{unique_unpaid_students} em", "1 năm qua (trừ tháng này)")
    c3.metric("💰 Tổng tiền còn cần thu", f"{total_debt_amount:,.0f} đ", "Các tháng trước")

    st.markdown("---")
    st.markdown("#### 📋 Chi Tiết Danh Sách Học Sinh Chưa Đóng Học Phí:")
    if df_unpaid_details.empty: st.success("✅ Tuyệt vời! Tất cả học sinh trong 1 năm qua (trừ tháng này) đã hoàn thành học phí.")
    else:
        disp_df = df_unpaid_details[['ho_ten', 'lop_hoc', 'thang_nam', 'so_ca']].copy()
        disp_df.columns = ['Họ và Tên', 'Lớp', 'Tháng Chưa Đóng', 'Số Ca Học']
        st.dataframe(disp_df, use_container_width=True)

# =========================================================
# --- CHỨC NĂNG 1: ĐIỂM DANH & NHẬN XÉT ---
# =========================================================
elif choice == "1. Điểm danh & Nhận xét":
    st.subheader("📝 Điểm Danh & Nhận Xét Buổi Học")
    ngay_hoc = st.date_input("🗓️ Chọn ngày điểm danh", date.today())
    date_str = ngay_hoc.strftime("%Y-%m-%d")
    
    df_active_today = get_active_schedule_for_date(engine, ngay_hoc)
    df_all_hs = pd.read_sql_query("SELECT id AS hoc_sinh_id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", engine)
    mo_rong_hs = st.checkbox("➕ Điểm danh cả học sinh không có lịch học trong ngày", value=False)
    
    df_source = df_all_hs.copy() if mo_rong_hs and not df_all_hs.empty else df_active_today
    if mo_rong_hs and not df_source.empty: df_source['ca_hoc'] = "17h30 - 19h30"

    type_mode = st.radio("Chế độ điểm danh", ["🏫 Điểm danh theo LỚP", "👤 Điểm danh từng HỌC SINH"], horizontal=True)
    st.divider()

    if df_all_hs.empty: st.warning("⚠️ Chưa có học sinh nào!")
    else:
        target_students = df_source if type_mode == "🏫 Điểm danh theo LỚP" and st.selectbox("Chọn Lớp", ["🌟 All Lớp"] + sorted(df_all_hs['lop_hoc'].dropna().unique().tolist())).startswith("🌟") \
                          else (df_source if type_mode == "🏫 Điểm danh theo LỚP" else df_source[df_source['hoc_sinh_id'] == {f"{r['ho_ten']} [{r['lop_hoc']}]": r['hoc_sinh_id'] for _, r in df_all_hs.iterrows()}[st.selectbox("Chọn học sinh", ["🌟 All Học sinh"] + list({f"{r['ho_ten']} [{r['lop_hoc']}]": r['hoc_sinh_id'] for _, r in df_all_hs.iterrows()}.keys()))]])
        
        if target_students.empty: st.info("ℹ️ Không tìm thấy học sinh phù hợp.")
        else:
            with st.form("form_diem_danh"):
                danh_sach_luu = []
                for idx, row in target_students.iterrows():
                    st.markdown(f"**👤 {row['ho_ten']}** [{row.get('lop_hoc', 'N/A')}]")
                    c1, c2, c3 = st.columns([2, 2.5, 4.5])
                    ca_val = c1.selectbox("Ca học", DANH_SACH_CA_MAU + ["⏱️ Tự nhập..."], key=f"ca_{row['hoc_sinh_id']}_{idx}")
                    ca_final = c1.text_input("Nhập giờ", value="18h00 - 20h00", key=f"cus_{row['hoc_sinh_id']}_{idx}").strip() if ca_val == "⏱️ Tự nhập..." else ca_val
                    stt_val = c2.radio("Trạng thái", ["Có mặt", "Vắng có phép", "Vắng không phép"], index=0, key=f"stt_{row['hoc_sinh_id']}_{idx}")
                    tags = c3.multiselect("Thẻ thái độ:", ["🌟 Chăm chú", "💪 Có tiến bộ", "⚠️ Quên bài tập", "💤 Buồn ngủ"], key=f"tag_{row['hoc_sinh_id']}_{idx}")
                    nx = c3.text_input("Nhận xét", key=f"nx_{row['hoc_sinh_id']}_{idx}")
                    danh_sach_luu.append((row['hoc_sinh_id'], date_str, ca_final, stt_val, f"{' '.join([f'[{t}]' for t in tags])} - {nx.strip()}".strip()))
                    st.divider()

                if st.form_submit_button("💾 LƯU ĐIỂM DANH", type="primary", use_container_width=True):
                    with engine.begin() as conn:
                        for item in danh_sach_luu:
                            rec = conn.execute(text("SELECT id FROM diem_danh WHERE hoc_sinh_id = :h AND ngay = :n AND ca_hoc = :c"), {"h": item[0], "n": item[1], "c": item[2]}).fetchone()
                            if rec: conn.execute(text("UPDATE diem_danh SET trang_thai = :stt, nhan_xet = :nx WHERE id = :id"), {"stt": item[3], "nx": item[4], "id": rec[0]})
                            else: conn.execute(text("INSERT INTO diem_danh (hoc_sinh_id, ngay, ca_hoc, trang_thai, nhan_xet) VALUES (:h, :n, :c, :stt, :nx)"), {"h": item[0], "n": item[1], "c": item[2], "stt": item[3], "nx": item[4]})
                    st.success("✅ Đã lưu thành công điểm danh!"); st.rerun()

# =========================================================
# --- CHỨC NĂNG 2: QUẢN LÝ & MA TRẬN LỊCH HỌC ---
# =========================================================
elif choice == "2. 🗺️ Quản Lý & Ma Trận Lịch Học":
    st.subheader("🗺️ Quản Lý Lịch Học")
    tab_m, tab_g, tab_t, tab_e = st.tabs(["🗺️ Ma Trận", "📅 Lịch Gốc", "⏳ Lịch Tạm Thời", "📥 Xuất Ảnh"])
    with tab_m: render_schedule_matrix(engine, ref_date=st.date_input("Xem tuần chứa ngày:", date.today()))
    with tab_g:
        df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", engine)
        if not df_hs.empty:
            mode = st.radio("Phạm vi:", ["Theo Lớp", "Theo Học Sinh"], horizontal=True)
            target_ids = df_hs[df_hs['lop_hoc'] == st.selectbox("Chọn Lớp", sorted(df_hs['lop_hoc'].dropna().unique()))]['id'].tolist() if mode == "Theo Lớp" else [df_hs.set_index(df_hs.apply(lambda r: f"{r['ho_ten']} [{r['lop_hoc']}]", axis=1)).loc[st.selectbox("Chọn HS", df_hs.apply(lambda r: f"{r['ho_ten']} [{r['lop_hoc']}]", axis=1))]['id']]
            sched = {t: st.multiselect(f"Ca vào {t}:", DANH_SACH_CA_MAU, default=["17h30 - 19h30"] if t != "Chủ Nhật" else [], key=f"g_{t}") for t in ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật'] if st.checkbox(f"Có lịch {t}", key=f"chk_{t}")}
            if st.button("💾 Lưu Lịch Gốc", type="primary"):
                with engine.begin() as conn:
                    for h_id in target_ids:
                        conn.execute(text("DELETE FROM lich_hoc_tuan WHERE hoc_sinh_id = :id"), {"id": h_id})
                        for thu, cas in sched.items():
                            for c in cas: conn.execute(text("INSERT INTO lich_hoc_tuan (hoc_sinh_id, thu, ca_hoc) VALUES (:h, :t, :c) ON CONFLICT DO NOTHING"), {"h": h_id, "t": thu, "c": c})
                st.success("✅ Đã lưu lịch gốc!"); st.rerun()
    with tab_t:
        with st.form("form_tam"):
            s_d, e_d = st.date_input("Từ ngày", date.today()), st.date_input("Đến ngày", date.today())
            loai = st.selectbox("Loại", ["Đổi ca / Học bù", "Học thêm buổi", "Nghỉ tạm thời trong khoảng thời gian này"])
            thu = st.selectbox("Thứ", ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật'])
            cas = st.multiselect("Ca", DANH_SACH_CA_MAU, default=["17h30 - 19h30"])
            if st.form_submit_button("Lưu lịch tạm thời", type="primary"):
                with engine.begin() as conn:
                    for _, r in pd.read_sql_query("SELECT id FROM hoc_sinh", engine).iterrows():
                        for c in cas: conn.execute(text("INSERT INTO lich_hoc_tam_thoi (hoc_sinh_id, ngay_bat_dau, ngay_ket_thuc, thu, ca_hoc, loai_thay_doi) VALUES (:h, :s, :e, :t, :c, :l)"), {"h": r['id'], "s": s_d, "e": e_d, "t": thu, "c": c, "l": loai})
                st.success("✅ Đã lưu!"); st.rerun()
    with tab_e:
        df_hs_all = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", engine)
        if not df_hs_all.empty:
            sel_d = st.date_input("Tuần xuất ảnh:", date.today())
            f_mode = st.radio("Phạm vi xuất:", ["Tất cả", "Theo Lớp", "Theo Học Sinh"], horizontal=True)
            l_sel = st.selectbox("Chọn lớp:", sorted(df_hs_all['lop_hoc'].dropna().unique())) if f_mode == "Theo Lớp" else None
            h_dict = {f"{r['ho_ten']} [{r['lop_hoc']}]": r['id'] for _, r in df_hs_all.iterrows()}
            h_sel = h_dict[st.selectbox("Chọn HS:", list(h_dict.keys()))] if f_mode == "Theo Học Sinh" else None
            df_mat = get_schedule_matrix_df(engine, filter_lop=l_sel, filter_hs_id=h_sel, ref_date=sel_d)
            if not df_mat.empty and HAS_MATPLOTLIB:
                st.download_button("🖼️ Tải Ảnh Lịch Học", create_weekly_schedule_image("Tất cả" if f_mode=="Tất cả" else (l_sel if f_mode=="Theo Lớp" else list(h_dict.keys())[0]), df_mat, ref_date=sel_d), file_name="Lich_Hoc.png", mime="image/png", type="primary")

# =========================================================
# --- CHỨC NĂNG 3: THỐNG KÊ SỐ CA & QUẢN LÝ HỌC PHÍ ---
# =========================================================
elif choice == "3. 💳 Thống Kê Số Ca & Quản Lý Học Phí":
    st.subheader("💳 Thống Kê Số Ca & Quản Lý Học Phí")
    che_do_xem = st.radio("⏱️ Chế độ xem:", ["Theo Tháng (Hỗ trợ chọn nhiều tháng)", "Theo Tuần", "Theo Ngày"], horizontal=True)
    qr_path = "qr_code.png" if os.path.exists("qr_code.png") else None
    combined_df = pd.DataFrame()

    if che_do_xem == "Theo Tháng (Hỗ trợ chọn nhiều tháng)":
        c_y, c_m = st.columns([1, 3])
        nam_sel = c_y.number_input("Năm", 2020, 2035, datetime.now().year)
        sel_thangs = c_m.multiselect("Chọn Tháng:", list(range(1, 13)), default=[datetime.now().month], format_func=lambda x: f"Tháng {x}")

        if sel_thangs:
            thang_queries = [f"'{nam_sel}-{th:02d}'" for th in sel_thangs]
            if len(sel_thangs) == 1:
                th_key = f"{sel_thangs[0]:02d}/{nam_sel}"
                q = f'''
                    SELECT h.id AS hoc_sinh_id, h.ho_ten AS "Họ và Tên", h.lop_hoc AS "Lớp", h.mon_hoc AS "Môn Học", h.hoc_phi_buoi AS "Đơn Giá/Ca (VNĐ)",
                           '{th_key}' AS "Thời gian",
                           SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS "Số Ca Có Mặt",
                           (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS "Tổng Tiền (VNĐ)",
                           COALESCE(t.trang_thai, 'Chưa đóng') AS "Trạng Thái"
                    FROM hoc_sinh h
                    LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND TO_CHAR(d.ngay, 'YYYY-MM') = '{nam_sel}-{sel_thangs[0]:02d}'
                    LEFT JOIN thanh_toan t ON h.id = t.hoc_sinh_id AND t.thang_nam = '{th_key}'
                    GROUP BY h.id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi, t.trang_thai
                '''
            else:
                q = f'''
                    SELECT h.id AS hoc_sinh_id, h.ho_ten AS "Họ và Tên", h.lop_hoc AS "Lớp", h.mon_hoc AS "Môn Học", h.hoc_phi_buoi AS "Đơn Giá/Ca (VNĐ)",
                           '{", ".join([f"Tháng {th}/{nam_sel}" for th in sel_thangs])}' AS "Thời gian",
                           SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS "Số Ca Có Mặt",
                           (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS "Tổng Tiền (VNĐ)",
                           'Chưa đóng' AS "Trạng Thái"
                    FROM hoc_sinh h
                    LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND TO_CHAR(d.ngay, 'YYYY-MM') IN ({",".join(thang_queries)})
                    GROUP BY h.id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi
                '''
            combined_df = pd.read_sql_query(q, engine)

    elif che_do_xem == "Theo Ngày":
        ngay_chon = st.date_input("Chọn ngày:", date.today())
        combined_df = pd.read_sql_query(f'''
            SELECT h.id AS hoc_sinh_id, h.ho_ten AS "Họ và Tên", h.lop_hoc AS "Lớp", h.mon_hoc AS "Môn Học", h.hoc_phi_buoi AS "Đơn Giá/Ca (VNĐ)",
                   '{ngay_chon.strftime("%d/%m/%Y")}' AS "Thời gian",
                   SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS "Số Ca Có Mặt",
                   (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS "Tổng Tiền (VNĐ)",
                   'Chưa đóng' AS "Trạng Thái"
            FROM hoc_sinh h LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND d.ngay = '{ngay_chon.strftime("%Y-%m-%d")}'
            GROUP BY h.id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi
        ''', engine)
    else:
        tuan_chon = st.date_input("Chọn tuần:", date.today())
        s_w, e_w = tuan_chon - timedelta(days=tuan_chon.weekday()), tuan_chon - timedelta(days=tuan_chon.weekday()) + timedelta(days=6)
        combined_df = pd.read_sql_query(f'''
            SELECT h.id AS hoc_sinh_id, h.ho_ten AS "Họ và Tên", h.lop_hoc AS "Lớp", h.mon_hoc AS "Môn Học", h.hoc_phi_buoi AS "Đơn Giá/Ca (VNĐ)",
                   'Tuần {s_w.strftime("%d/%m")} - {e_w.strftime("%d/%m")}' AS "Thời gian",
                   SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS "Số Ca Có Mặt",
                   (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS "Tổng Tiền (VNĐ)",
                   'Chưa đóng' AS "Trạng Thái"
            FROM hoc_sinh h LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND d.ngay >= '{s_w}' AND d.ngay <= '{e_w}'
            GROUP BY h.id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi
        ''', engine)

    search_query = st.text_input("🔍 Tìm kiếm học sinh:")
    st.divider()

    if not combined_df.empty and search_query.strip():
        combined_df = combined_df[combined_df['Họ và Tên'].str.contains(search_query.strip(), case=False, na=False)]

    if combined_df.empty: st.info("ℹ️ Không tìm thấy dữ liệu thống kê.")
    else:
        c_sum1, c_sum2 = st.columns(2)
        c_sum1.metric("📚 Tổng số ca học", f"{int(combined_df['Số Ca Có Mặt'].sum())} ca")
        c_sum2.metric("💰 Tổng tiền học phí", f"{combined_df['Tổng Tiền (VNĐ)'].sum():,.0f} đ")
        st.markdown("---")

        # Nút xuất ZIP hàng loạt hóa đơn các học sinh có phát sinh
        if HAS_MATPLOTLIB:
            if st.button("📦 Xuất ZIP Hàng Loạt Hóa Đơn Các Học Sinh Có Phát Sinh", type="primary"):
                df_active_students = combined_df[combined_df['Số Ca Có Mặt'] > 0]
                if df_active_students.empty:
                    st.warning("⚠️ Không có học sinh nào phát sinh ca học trong khoảng thời gian này.")
                else:
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        for _, row in df_active_students.iterrows():
                            hs_id = row['hoc_sinh_id']
                            month_details = []
                            if che_do_xem == "Theo Tháng (Hỗ trợ chọn nhiều tháng)" and sel_thangs:
                                for th in sel_thangs:
                                    t_str, t_key = f"{nam_sel}-{th:02d}", f"{th:02d}/{nam_sel}"
                                    sc_res = pd.read_sql_query(f"SELECT COUNT(id) as sc FROM diem_danh WHERE hoc_sinh_id = {hs_id} AND TO_CHAR(ngay, 'YYYY-MM') = '{t_str}' AND trang_thai = 'Có mặt'", engine)
                                    sc_val = int(sc_res.iloc[0]['sc']) if not sc_res.empty else 0
                                    month_details.append({'thang': t_key, 'so_ca': sc_val, 'don_gia': row['Đơn Giá/Ca (VNĐ)'], 'thanh_tien': sc_val * row['Đơn Giá/Ca (VNĐ)']})
                            else:
                                month_details.append({'thang': row['Thời gian'], 'so_ca': int(row['Số Ca Có Mặt']), 'don_gia': row['Đơn Giá/Ca (VNĐ)'], 'thanh_tien': row['Tổng Tiền (VNĐ)']})
                            
                            img_buf = create_tuition_slip_image_multi(
                                row['Họ và Tên'], row['Lớp'], row['Môn Học'] or 'Chung',
                                month_details, int(row['Số Ca Có Mặt']), row['Tổng Tiền (VNĐ)'], row['Trạng Thái'], qr_path
                            )
                            
                            clean_name = re.sub(r'[^\w\s-]', '', str(row['Họ và Tên'])).strip().replace(' ', '_')
                            clean_lop = re.sub(r'[^\w\s-]', '', str(row['Lớp'])).strip().replace(' ', '_')
                            clean_time = str(row['Thời gian']).replace(', ', '_').replace('/', '-').replace(' ', '_')
                            file_name = f"Phieu_{clean_name}_{clean_lop}_{clean_time}.png"
                            zip_file.writestr(file_name, img_buf.getvalue())
                    
                    zip_buffer.seek(0)
                    st.download_button(
                        label="📥 Tải Xuống File ZIP Hóa Đơn Hàng Loạt",
                        data=zip_buffer,
                        file_name="Tat_Ca_Hoa_Don_Hoc_Sinh.zip",
                        mime="application/zip",
                        key="download_zip_all_invoices"
                    )
            st.markdown("---")

        for idx, row in combined_df.iterrows():
            hs_id = row['hoc_sinh_id']
            month_details = []
            
            if che_do_xem == "Theo Tháng (Hỗ trợ chọn nhiều tháng)" and sel_thangs:
                for th in sel_thangs:
                    t_str, t_key = f"{nam_sel}-{th:02d}", f"{th:02d}/{nam_sel}"
                    sc_res = pd.read_sql_query(f"SELECT COUNT(id) as sc FROM diem_danh WHERE hoc_sinh_id = {hs_id} AND TO_CHAR(ngay, 'YYYY-MM') = '{t_str}' AND trang_thai = 'Có mặt'", engine)
                    sc_val = int(sc_res.iloc[0]['sc']) if not sc_res.empty else 0
                    month_details.append({'thang': t_key, 'so_ca': sc_val, 'don_gia': row['Đơn Giá/Ca (VNĐ)'], 'thanh_tien': sc_val * row['Đơn Giá/Ca (VNĐ)']})
            else:
                month_details.append({'thang': row['Thời gian'], 'so_ca': int(row['Số Ca Có Mặt']), 'don_gia': row['Đơn Giá/Ca (VNĐ)'], 'thanh_tien': row['Tổng Tiền (VNĐ)']})

            c1, c2, c3, c4, c5, c6, c7 = st.columns([2.2, 1.2, 1.2, 1.2, 1.5, 1.8, 1.8])
            c1.write(f"**{row['Họ và Tên']}**\n\n*Lớp: {row['Lớp']} ({row['Thời gian']})*")
            c2.write(f"{int(row['Số Ca Có Mặt'])} ca")
            c3.write(f"{row['Đơn Giá/Ca (VNĐ)']:,.0f} đ")
            c4.write(f"**{row['Tổng Tiền (VNĐ)']:,.0f} đ**")
            
            is_paid = (row['Trạng Thái'] == 'Đã đóng')
            c5.write("🟢 Đã đóng" if is_paid else "🔴 Chưa đóng")
            
            btn_lbl = "Chuyển Chưa đóng" if is_paid else "Xác nhận Đã đóng"
            if c6.button(btn_lbl, key=f"pay_{hs_id}_{idx}"):
                new_stt = 'Chưa đóng' if is_paid else 'Đã đóng'
                t_str = date.today().strftime("%Y-%m-%d") if new_stt == 'Đã đóng' else ""
                save_key = f"{sel_thangs[0]:02d}/{nam_sel}" if (che_do_xem == "Theo Tháng (Hỗ trợ chọn nhiều tháng)" and len(sel_thangs) == 1) else row['Thời gian']
                with engine.begin() as conn:
                    conn.execute(text('''
                        INSERT INTO thanh_toan (hoc_sinh_id, thang_nam, trang_thai, ngay_thu) VALUES (:h, :t, :s, :n)
                        ON CONFLICT (hoc_sinh_id, thang_nam) DO UPDATE SET trang_thai = EXCLUDED.trang_thai, ngay_thu = EXCLUDED.ngay_thu
                    '''), {"h": hs_id, "t": save_key, "s": new_stt, "n": t_str})
                st.rerun()

            with c7:
                if HAS_MATPLOTLIB:
                    clean_name = re.sub(r'[^\w\s-]', '', str(row['Họ và Tên'])).strip().replace(' ', '_')
                    clean_lop = re.sub(r'[^\w\s-]', '', str(row['Lớp'])).strip().replace(' ', '_')
                    clean_time = str(row['Thời gian']).replace(', ', '_').replace('/', '-').replace(' ', '_')
                    file_name_img = f"Phieu_{clean_name}_{clean_lop}_{clean_time}.png"

                    st.download_button(
                        label="🖼️ Tải Ảnh Phiếu",
                        data=create_tuition_slip_image_multi(row['Họ và Tên'], row['Lớp'], row['Môn Học'] or 'Chung', month_details, int(row['Số Ca Có Mặt']), row['Tổng Tiền (VNĐ)'], row['Trạng Thái'], qr_path),
                        file_name=file_name_img, mime="image/png", key=f"img_{hs_id}_{idx}"
                    )
            st.divider()

# =========================================================
# --- CHỨC NĂNG 4: SỬA & XÓA DỮ LIỆU ---
# =========================================================
elif choice == "4. Sửa & Xóa dữ liệu":
    st.subheader("⚙️ Quản Lý Dữ Liệu")
    tab_hs, tab_dd = st.tabs(["👤 Học sinh", "🗓️ Nhật ký điểm danh"])
    with tab_hs:
        sub1, sub2, sub3 = st.tabs(["➕ Thêm", "✏️ Sửa", "❌ Xóa"])
        with sub1:
            with st.form("add_hs"):
                ten, lop, mon, hp = st.text_input("Họ tên (*)"), st.text_input("Lớp", "Toán 9"), st.text_input("Môn", "Toán"), st.number_input("Học phí/ca", min_value=0, value=150000, step=10000)
                if st.form_submit_button("Thêm", type="primary") and ten.strip():
                    with engine.begin() as conn: conn.execute(text("INSERT INTO hoc_sinh (ho_ten, lop_hoc, mon_hoc, hoc_phi_buoi) VALUES (:t, :l, :m, :hp)"), {"t": ten.strip(), "l": lop.strip(), "m": mon.strip(), "hp": hp})
                    st.success("✅ Đã thêm!"); st.rerun()
        with sub2:
            df_e = pd.read_sql_query("SELECT * FROM hoc_sinh", engine)
            if not df_e.empty:
                h_dict = {f"{r['ho_ten']} [{r['lop_hoc']}]": r for _, r in df_e.iterrows()}
                sel = h_dict[st.selectbox("Chọn HS:", list(h_dict.keys()))]
                with st.form("edit_hs"):
                    e_t, e_l, e_hp = st.text_input("Họ tên", sel['ho_ten']), st.text_input("Lớp", sel['lop_hoc']), st.number_input("Học phí", value=int(sel['hoc_phi_buoi']))
                    if st.form_submit_button("Lưu", type="primary"):
                        with engine.begin() as conn: conn.execute(text("UPDATE hoc_sinh SET ho_ten = :t, lop_hoc = :l, hoc_phi_buoi = :hp WHERE id = :id"), {"t": e_t, "l": e_l, "hp": e_hp, "id": sel['id']})
                        st.success("✅ Đã cập nhật!"); st.rerun()
        with sub3:
            df_d = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", engine)
            if not df_d.empty:
                d_dict = {f"{r['ho_ten']} [{r['lop_hoc']}]": r['id'] for _, r in df_d.iterrows()}
                d_id = d_dict[st.selectbox("Chọn HS xóa:", list(d_dict.keys()))]
                if st.button("❌ Xóa học sinh này", type="primary") and st.checkbox("Xác nhận xóa"):
                    with engine.begin() as conn:
                        for tbl in ["diem_danh", "thanh_toan", "lich_hoc_tuan", "lich_hoc_tam_thoi", "hoc_sinh"]:
                            conn.execute(text(f"DELETE FROM {tbl} WHERE {'hoc_sinh_id' if tbl != 'hoc_sinh' else 'id'} = :id"), {"id": d_id})
                    st.success("✅ Đã xóa!"); st.rerun()
        st.dataframe(pd.read_sql_query("SELECT id AS \"Mã HS\", ho_ten AS \"Họ tên\", lop_hoc AS \"Lớp\", mon_hoc AS \"Môn\", hoc_phi_buoi AS \"Học phí/ca\" FROM hoc_sinh", engine), use_container_width=True)
    with tab_dd:
        sel_d_log = st.date_input("Chọn ngày:", date.today())
        df_l = pd.read_sql_query(f"SELECT d.id, h.ho_ten, h.lop_hoc, d.ca_hoc, d.trang_thai, d.nhan_xet FROM diem_danh d JOIN hoc_sinh h ON d.hoc_sinh_id = h.id WHERE d.ngay = '{sel_d_log}'", engine)
        if not df_l.empty:
            st.dataframe(df_l, use_container_width=True)
            log_dict = {f"ID {r['id']}: {r['ho_ten']} ({r['ca_hoc']})": r['id'] for _, r in df_l.iterrows()}
            if st.button("❌ Xóa bản ghi điểm danh", type="primary"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM diem_danh WHERE id = :id"), {"id": log_dict[st.selectbox("Chọn bản ghi:", list(log_dict.keys()))]})
                st.success("✅ Đã xóa!"); st.rerun()
        else: st.info("Không có dữ liệu điểm danh.")
