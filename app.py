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

# --- HÀM LẤY LỊCH HỌC HIỆU LỰC CHO MỘT NGÀY (CÓ XỬ LÝ LỊCH TẠM THỜI ĐÚNG CA & NGÀY) ---
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
                if loai == 'Nghỉ tạm thời trong khoảng thời gian này':
                    exclude_pairs.add((hs_id, ca_tam))
                elif loai == 'Đổi ca / Học bù':
                    exclude_pairs.add((hs_id, ca_tam))
                elif loai == 'Học thêm buổi':
                    additional_rows.append({
                        'hoc_sinh_id': hs_id,
                        'ho_ten': r['ho_ten'],
                        'lop_hoc': r['lop_hoc'],
                        'mon_hoc': r['mon_hoc'],
                        'ca_hoc': ca_tam,
                        'nguon': 'Học thêm'
                    })

    if not df_base.empty and len(exclude_pairs) > 0:
        mask = df_base.apply(lambda row: (row['hoc_sinh_id'], row['ca_hoc']) not in exclude_pairs, axis=1)
        df_base = df_base[mask]

    df_additions = pd.DataFrame(additional_rows)

    cols = ['hoc_sinh_id', 'ho_ten', 'lop_hoc', 'mon_hoc', 'ca_hoc', 'nguon']
    df_combined = pd.concat([
        df_base[cols] if not df_base.empty else pd.DataFrame(columns=cols),
        df_additions[cols] if not df_additions.empty else pd.DataFrame(columns=cols)
    ], ignore_index=True)

    return df_combined

# --- HÀM TỰ ĐỘNG ĐỒNG BỘ LỊCH 7 NGÀY SANG GOOGLE CALENDAR ---
def sync_weekly_schedule_to_google(calendar_id='a.luongxdnb@gmail.com', days_ahead=7):
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return False, "⚠️ Chưa cài đặt thư viện Google trong requirements.txt"

    try:
        scopes = ['https://www.googleapis.com/auth/calendar']
        
        creds_info = json.loads(st.secrets["GOOGLE_CREDENTIALS_JSON"])
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        
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
            "14h00 - 16h00": ("14:00:00", "16:00:00"),
            "15h30 - 17h30": ("15:30:00", "17:30:00"),
            "17h30 - 19h30": ("17:30:00", "19:30:00"),
            "19h30 - 21h30": ("19:30:00", "21:30:00")
        }

        for i in range(days_ahead):
            current_date = today + timedelta(days=i)
            df_day = get_active_schedule_for_date(engine, current_date)

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

# --- HÀM LẤY MA TRẬN LỊCH HỌC ---
def get_schedule_matrix_df(engine, filter_lop=None, filter_hs_id=None, ref_date=None):
    if ref_date is None:
        ref_date = date.today()
    cac_thu = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
    start_monday = ref_date - timedelta(days=ref_date.weekday())
    
    day_schedules = {}
    for i, t in enumerate(cac_thu):
        current_d = start_monday + timedelta(days=i)
        df_day = get_active_schedule_for_date(engine, current_d)
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
                                name_str += f" ({nguon})"
                            names_list.append(name_str)
                        
                        if filter_lop or filter_hs_id:
                            for ns in names_list:
                                items.append(ns)
                        else:
                            names_str = "<br>".join(names_list)
                            items.append(f"<b>[{lop}]</b><br>{names_str}")
                    row_dict[t] = "<br>".join(items)
        matrix_rows.append(row_dict)

    df_matrix = pd.DataFrame(matrix_rows)
    cols = ["Buổi", "Ca học"] + cac_thu
    return df_matrix[cols]

def render_schedule_matrix(engine, ref_date=None):
    df_matrix = get_schedule_matrix_df(engine, ref_date=ref_date)
    if df_matrix.empty:
        st.info("💡 Chưa có lịch học tuần nào được thiết lập trong hệ thống cho mốc thời gian này.")
        return
    st.write(df_matrix.to_html(index=False, escape=False), unsafe_allow_html=True)

# --- HÀM TẠO FILE ẢNH PNG LỊCH HỌC HÀNG TUẦN ---
def create_weekly_schedule_image(title_target, df_matrix, ref_date=None, prefix="Học sinh / Lớp: "):
    if ref_date is None:
        ref_date = date.today()
        
    table_data = [df_matrix.columns.tolist()] + df_matrix.values.tolist()
    
    max_lines_overall = 1
    cleaned_data = []
    for row in table_data:
        cleaned_row = []
        row_max_lines = 1
        for col_idx, cell in enumerate(row):
            clean_cell = str(cell).replace("<br>", "\n").replace("<br/>", "\n")
            clean_cell = clean_cell.replace("<b>", "").replace("</b>", "")
            clean_cell = re.sub(r'<[^>]+>', '', clean_cell)
            
            lines = clean_cell.count('\n') + 1
            if lines > row_max_lines:
                row_max_lines = lines
            cleaned_row.append(clean_cell)
        cleaned_data.append(cleaned_row)
        if row_max_lines > max_lines_overall:
            max_lines_overall = row_max_lines
            
    fig, ax = plt.subplots(figsize=(24, len(df_matrix) * max(1.8, max_lines_overall * 0.65) + 5.0))
    ax.axis('off')
    ax.axis('tight')
    
    start_w = ref_date - timedelta(days=ref_date.weekday())
    end_w = start_w + timedelta(days=6)
    week_text = f"(Tuần từ {start_w.strftime('%d/%m/%Y')} đến {end_w.strftime('%d/%m/%Y')})"
        
    col_widths = [0.08, 0.12, 0.12, 0.12, 0.12, 0.12, 0.12, 0.12, 0.12]
    
    table = ax.table(cellText=cleaned_data, loc='center', cellLoc='center', colWidths=col_widths)
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    
    v_scale = max(3.2, max_lines_overall * 1.15)
    table.scale(1, v_scale)
    
    ax.text(0.5, 1.15, "THỜI KHÓA BIỂU LỊCH HỌC HÀNG TUẦN", transform=ax.transAxes, 
            fontsize=17, fontweight='bold', color='#1E3A8A', ha='center', va='bottom')
    ax.text(0.5, 1.08, f"{prefix}{title_target}", transform=ax.transAxes, 
            fontsize=14, fontweight='bold', color='#0F172A', ha='center', va='bottom')
    ax.text(0.5, 1.02, week_text, transform=ax.transAxes, 
            fontsize=11.5, fontweight='normal', color='#475569', ha='center', va='bottom')
    
    plt.figtext(0.5, 0.02, "Ghi chú: Lịch học được áp dụng ổn định cho các tuần tiếp theo nếu không có thay đổi tạm thời.", ha='center', fontsize=10.5, style='italic', color='#475569', weight='bold')
    
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#CBD5E1')
        cell.PAD = 0.15 
        
        if row == 0:
            cell.set_facecolor('#1E3A8A')
            cell.set_text_props(color='white', weight='bold', size=12.5)
        else:
            if col == 0:
                cell.set_facecolor('#FEF3C7')
                cell.set_text_props(weight='bold', color='#B45309', size=12)
            elif col == 1:
                cell.set_facecolor('#E0F2FE')
                cell.set_text_props(weight='bold', color='#0369A1', size=11.5)
            else:
                cell.set_text_props(color='#1E293B', size=12, weight='normal')
                if row % 2 == 0:
                    cell.set_facecolor('#F8FAFC')
                else:
                    cell.set_facecolor('white')
                    
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig)
    buffer.seek(0)
    return buffer

# --- HÀM TẠO FILE ẢNH HÓA ĐƠN HỌC PHÍ (HỖ TRỢ CẢ 1 THÁNG VÀ NHIỀU THÁNG) ---
def create_tuition_slip_image(student_name, lop_hoc, subject, price_per_lesson, month_year, total_lessons, total_fee, status, qr_path, is_multi=False, details_list=None):
    fig, ax = plt.subplots(figsize=(8, 11 if is_multi else 10))
    ax.axis('off')
    
    ax.text(0.5, 0.94, "PHIẾU BÁO HỌC PHÍ DẠY THÊM", fontsize=16, fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    ax.text(0.5, 0.90, f"Thời gian: {month_year}", fontsize=12, fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    
    details = [
        f"Họ và tên học sinh: {student_name}",
        f"Lớp / Nhóm học: {lop_hoc}",
        f"Môn học: {subject}"
    ]
    
    y_pos = 0.83
    for line in details:
        fontweight = 'bold' if 'Họ và tên' in line else 'normal'
        ax.text(0.1, y_pos, line, fontsize=11.5, fontweight=fontweight, color='#1E293B', transform=ax.transAxes)
        y_pos -= 0.05
        
    if is_multi and details_list:
        ax.text(0.1, y_pos, "Chi tiết học phí các tháng:", fontsize=11.5, fontweight='bold', color='#1E3A8A', transform=ax.transAxes)
        y_pos -= 0.05
        for d in details_list:
            line_d = f"• Tháng {d['thang_key']}: {d['so_ca']} ca x {d['don_gia']:,.0f}đ = {d['thanh_tien']:,.0f}đ [{d['trang_thai']}]"
            ax.text(0.12, y_pos, line_d, fontsize=10.5, fontweight='normal', color='#1E293B', transform=ax.transAxes)
            y_pos -= 0.045
    
    summary_lines = [
        f"Học phí cơ bản / ca: {price_per_lesson:,.0f} VNĐ",
        f"Tổng số ca học: {total_lessons} ca",
        f"TỔNG CỘNG HỌC PHÍ: {total_fee:,.0f} VNĐ",
        f"Trạng thái thanh toán: {status}"
    ]
    
    y_pos -= 0.02
    for line in summary_lines:
        fontweight = 'bold' if 'TỔNG CỘNG' in line else 'normal'
        color = '#B91C1C' if 'TỔNG CỘNG' in line else '#1E293B'
        ax.text(0.1, y_pos, line, fontsize=11.5, fontweight=fontweight, color=color, transform=ax.transAxes)
        y_pos -= 0.055
        
    if qr_path and os.path.exists(qr_path):
        try:
            img_arr = plt.imread(qr_path)
            ax_inset = fig.add_axes([0.35, 0.12, 0.3, 0.3])
            ax_inset.imshow(img_arr)
            ax_inset.axis('off')
            ax.text(0.5, 0.44, "Mã QR Thanh Toán Chuyển Khoản", fontsize=10.5, fontweight='bold', color='#1E3A8A', ha='center', transform=ax.transAxes)
        except Exception:
            pass
            
    ax.text(0.5, 0.04, "Trân trọng cảm ơn sự đồng hành của Quý phụ huynh!", fontsize=11, style='italic', fontweight='bold', color='#1E3A8A', ha='center', transform=ax.transAxes)
    
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig)
    buffer.seek(0)
    return buffer

# --- HÀM TẠO FILE ẢNH LỊCH SỬ ĐIỂM DANH THÁNG ---
def create_student_attendance_history_image(student_name, lop_hoc, month_year, df_history, total_present):
    fig, ax = plt.subplots(figsize=(10, max(4, len(df_history) * 0.5 + 3.5)))
    ax.axis('off')
    ax.axis('tight')
    
    ax.text(0.5, 0.94, "LỊCH SỬ ĐIỂM DANH & NHẬN XÉT HỌC SINH", fontsize=15, fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    ax.text(0.5, 0.89, f"Học sinh: {student_name} - Lớp: {lop_hoc} ({month_year})", fontsize=12, fontweight='bold', color='#0F172A', ha='center', va='center', transform=ax.transAxes)
    ax.text(0.5, 0.84, f"Tổng số buổi đi học (Có mặt): {total_present} buổi", fontsize=11, fontweight='bold', color='#B91C1C', ha='center', va='center', transform=ax.transAxes)
    
    table_data = [df_history.columns.tolist()] + df_history.values.tolist()
    table = ax.table(cellText=table_data, loc='center', cellLoc='center', colWidths=[0.18, 0.22, 0.22, 0.38])
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1, 2.2)
    
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#CBD5E1')
        if row == 0:
            cell.set_facecolor('#1E3A8A')
            cell.set_text_props(color='white', weight='bold', size=11)
        else:
            cell.set_text_props(color='#1E293B', size=9.5)
            if row % 2 == 0:
                cell.set_facecolor('#F8FAFC')
            else:
                cell.set_facecolor('white')
                
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig)
    buffer.seek(0)
    return buffer

# --- 1. KHỞI TẠO BẢNG TRÊN SUPABASE & TỰ ĐỘNG BỔ SUNG CỘT ---
with engine.begin() as conn:
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS hoc_sinh (
            id SERIAL PRIMARY KEY,
            ho_ten TEXT NOT NULL,
            lop_hoc TEXT DEFAULT 'Lớp chung',
            mon_hoc TEXT,
            hoc_phi_buoi REAL NOT NULL,
            thong_tin_phu_huynh TEXT
        )
    '''))
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS diem_danh (
            id SERIAL PRIMARY KEY,
            hoc_sinh_id INTEGER,
            ngay DATE,
            ca_hoc TEXT DEFAULT '7h00 - 9h00',
            trang_thai TEXT DEFAULT 'Có mặt',
            nhan_xet TEXT
        )
    '''))
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS thanh_toan (
            id SERIAL PRIMARY KEY,
            hoc_sinh_id INTEGER,
            thang_nam TEXT,
            trang_thai TEXT DEFAULT 'Chưa đóng',
            ngay_thu TEXT,
            UNIQUE(hoc_sinh_id, thang_nam)
        )
    '''))
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS lich_hoc_tuan (
            id SERIAL PRIMARY KEY,
            hoc_sinh_id INTEGER,
            thu TEXT,
            ca_hoc TEXT,
            UNIQUE(hoc_sinh_id, thu, ca_hoc)
        )
    '''))
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS lich_hoc_tam_thoi (
            id SERIAL PRIMARY KEY,
            hoc_sinh_id INTEGER,
            ngay_bat_dau DATE,
            ngay_ket_thuc DATE,
            thu TEXT,
            ca_hoc TEXT,
            loai_thay_doi TEXT DEFAULT 'Đổi ca / Học bù'
        )
    '''))
    try:
        conn.execute(text("ALTER TABLE hoc_sinh RENAME COLUMN sdt_phu_huynh TO thong_tin_phu_huynh"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE hoc_sinh ADD COLUMN IF NOT EXISTS thong_tin_phu_huynh TEXT"))
    except Exception:
        pass

# --- 2. GIAO DIỆN CHÍNH ---
st.title("📚 Phần Mềm Quản Lý Dạy Thêm Tại Nhà (Supabase)")

if st.sidebar.button("🚪 Đăng xuất", type="secondary", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

menu = [
    "0. 📊 Trang Chủ Dashboard",
    "1. Điểm danh & Nhận xét", 
    "2. 🗺️ Quản Lý & Lịch Học Tổng Quan",
    "3. 💳 Thống Kê Số Ca & Quản Lý Học Phí", 
    "4. Sửa & Xóa dữ liệu"
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

st.sidebar.markdown("---")
st.sidebar.info("☁️ Dữ liệu đang được kết nối trực tiếp và lưu trữ vĩnh viễn trên **Supabase Cloud**.")

# =========================================================
# --- CHỨC NĂNG 0: TRANG CHỦ DASHBOARD TỔNG QUAN ---
# =========================================================
if choice == "0. 📊 Trang Chủ Dashboard":
    st.subheader("📊 Trang Chủ Dashboard Tổng Quan Trong Ngày")
    today = date.today()
    thu_hom_nay = get_vietnamese_weekday(today)
    st.info(f"🗓️ Hôm nay: **{today.strftime('%d/%m/%Y')} ({thu_hom_nay})**")
    
    df_today = get_active_schedule_for_date(engine, today)
    
    curr_y, curr_m = today.year, today.month
    past_y, past_m = curr_y - 1, curr_m
    start_date_str = f"{past_y}-{past_m:02d}-01"
    end_date_str = f"{curr_y}-{curr_m:02d}-01"
    
    query_unpaid_details = f'''
        SELECT h.id, h.ho_ten, h.lop_hoc, h.hoc_phi_buoi,
               TO_CHAR(d.ngay, 'MM/YYYY') AS thang_nam,
               COUNT(d.id) AS so_ca
        FROM hoc_sinh h
        JOIN diem_danh d ON h.id = d.hoc_sinh_id
        WHERE d.trang_thai = 'Có mặt'
          AND d.ngay >= '{start_date_str}' 
          AND d.ngay < '{end_date_str}'
          AND NOT EXISTS (
              SELECT 1 FROM thanh_toan t 
              WHERE t.hoc_sinh_id = h.id 
                AND t.thang_nam = TO_CHAR(d.ngay, 'MM/YYYY') 
                AND t.trang_thai = 'Đã đóng'
          )
        GROUP BY h.id, h.ho_ten, h.lop_hoc, h.hoc_phi_buoi, TO_CHAR(d.ngay, 'MM/YYYY')
        ORDER BY thang_nam DESC, h.ho_ten ASC
    '''
    df_unpaid_details = pd.read_sql_query(query_unpaid_details, engine)
    
    if not df_unpaid_details.empty:
        df_unpaid_details['tien_no'] = df_unpaid_details['so_ca'] * df_unpaid_details['hoc_phi_buoi']
        total_debt_amount = df_unpaid_details['tien_no'].sum()
        unique_unpaid_students = df_unpaid_details['id'].nunique()
    else:
        total_debt_amount = 0
        unique_unpaid_students = 0

    col1, col2, col3 = st.columns(3)
    with col1:
        total_ca = df_today['ca_hoc'].nunique() if not df_today.empty else 0
        total_hs_today = len(df_today) if not df_today.empty else 0
        st.metric("🏫 Ca dạy hôm nay", f"{total_ca} ca", f"{total_hs_today} lượt học sinh")
    with col2:
        st.metric("💳 Học sinh chưa đóng phí", f"{unique_unpaid_students} em", f"Trong 1 năm qua (trừ tháng này)")
    with col3:
        st.metric("💰 Tổng tiền còn cần thu", f"{total_debt_amount:,.0f} đ", f"Các tháng trước")

    st.markdown("---")
    st.markdown("#### 📋 Chi Tiết Danh Sách Học Sinh Chưa Đóng Học Phí (1 Năm Qua, Trừ Tháng Này):")
    if df_unpaid_details.empty:
        st.success("✅ Tuyệt vời! Tất cả học sinh trong 1 năm qua (trừ tháng này) đã hoàn thành học phí.")
    else:
        display_debt_df = df_unpaid_details[['ho_ten', 'lop_hoc', 'thang_nam', 'so_ca', 'tien_no']].copy()
        display_debt_df.columns = ['Họ và Tên', 'Lớp', 'Tháng Chưa Đóng', 'Số Ca Học', 'Số Tiền Cần Thu (VNĐ)']
        display_debt_df['Số Tiền Cần Thu (VNĐ)'] = display_debt_df['Số Tiền Cần Thu (VNĐ)'].map('{:,.0f} đ'.format)
        st.dataframe(display_debt_df, use_container_width=True)
        
    st.markdown("---")
    st.markdown("#### 🏫 Chi Tiết Lịch Dạy & Học Sinh Hôm Nay (Sắp xếp từ sớm đến muộn):")
    if df_today.empty:
        st.info("💡 Hôm nay không có ca dạy nào được lên lịch.")
    else:
        sorted_cas_today = sorted(df_today['ca_hoc'].unique().tolist(), key=ca_hoc_sort_key)
        for ca in sorted_cas_today:
            group_ca = df_today[df_today['ca_hoc'] == ca]
            with st.expander(f"⏰ Ca: {ca} ({len(group_ca)} học sinh)", expanded=True):
                for lop, g_lop in group_ca.groupby('lop_hoc'):
                    ds_names = ", ".join(g_lop['ho_ten'].tolist())
                    st.write(f"• **Lớp {lop}:** {ds_names}")

# =========================================================
# --- CHỨC NĂNG 1: ĐIỂM DANH & NHẬN XÉT ---
# =========================================================
elif choice == "1. Điểm danh & Nhận xét":
    st.subheader("📝 Điểm Danh & Nhận Xét Buổi Học")
    
    tab_dd_moi, tab_dd_quanly, tab_dd_lich_su = st.tabs([
        "📝 Điểm danh mới & Xem kết quả", 
        "⚙️ Quản lý, Sửa & Xóa Nhật ký Điểm danh",
        "📊 Lịch sử Điểm danh & Xuất Ảnh"
    ])
    
    with tab_dd_moi:
        ngay_hoc = st.date_input("🗓️ Chọn ngày điểm danh", date.today())
        thu_hom_nay = get_vietnamese_weekday(ngay_hoc)
        date_str = ngay_hoc.strftime("%Y-%m-%d")
        st.caption(f"Ngày được chọn: **{ngay_hoc.strftime('%d/%m/%Y')} ({thu_hom_nay})**")
        
        df_active_today = get_active_schedule_for_date(engine, ngay_hoc)
        df_all_hs = pd.read_sql_query("SELECT id AS hoc_sinh_id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", engine)
        
        mo_rong_hs = st.checkbox("➕ Cho phép điểm danh cả học sinh KHÔNG CÓ LỊCH HỌC trong ngày (Học bù, phát sinh,...)", value=False)
        
        if mo_rong_hs:
            if not df_all_hs.empty:
                df_source = df_all_hs.copy()
                df_source['ca_hoc'] = "17h30 - 19h30"
                df_source['nguon'] = "Ngoài lịch"
            else:
                df_source = pd.DataFrame(columns=['hoc_sinh_id', 'ho_ten', 'lop_hoc', 'mon_hoc', 'ca_hoc', 'nguon'])
        else:
            df_source = df_active_today

        type_mode = st.radio("Chế độ điểm danh", ["🏫 Điểm danh theo LỚP", "👤 Điểm danh từng HỌC SINH"], horizontal=True)
        st.divider()

        target_students = pd.DataFrame()

        if df_all_hs.empty:
            st.warning("⚠️ Chưa có học sinh nào trong hệ thống!")
        else:
            if type_mode == "🏫 Điểm danh theo LỚP":
                available_classes = sorted(df_all_hs['lop_hoc'].dropna().unique().tolist())
                options_class = ["🌟 All Lớp (Tất cả học sinh)"] + available_classes if mo_rong_hs else ["🌟 All Lớp (Tất cả học sinh có lịch học hôm nay)"] + available_classes
                selected_class_opt = st.selectbox("Chọn Lớp cần điểm danh", options_class)

                if selected_class_opt.startswith("🌟 All Lớp"):
                    target_students = df_source
                else:
                    target_students = df_source[df_source['lop_hoc'] == selected_class_opt] if not df_source.empty else pd.DataFrame()
            else:
                student_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['hoc_sinh_id']}": row['hoc_sinh_id'] for _, row in df_all_hs.iterrows()}
                options_hs = ["🌟 All Học sinh (Tất cả học sinh)"] + list(student_dict.keys()) if mo_rong_hs else ["🌟 All Học sinh (Tất cả học sinh có lịch học hôm nay)"] + list(student_dict.keys())
                selected_hs_opt = st.selectbox("Chọn học sinh điểm danh", options_hs)

                if selected_hs_opt.startswith("🌟 All Học sinh"):
                    target_students = df_source
                else:
                    selected_hs_id = student_dict[selected_hs_opt]
                    target_students = df_source[df_source['hoc_sinh_id'] == selected_hs_id] if not df_source.empty else pd.DataFrame()

            if target_students.empty:
                st.info("ℹ️ Không tìm thấy học sinh nào phù hợp trong danh sách.")
            else:
                st.markdown(f"#### 📋 Bảng Điểm Danh ({len(target_students)} lượt học ca)")
                with st.form("form_diem_danh_execution"):
                    danh_sach_ca_mau_dd = DANH_SACH_CA_MAU + ["⏱️ Tự nhập giờ tùy chỉnh..."]
                    danh_sach_luu = []

                    for idx, row in target_students.iterrows():
                        st.markdown(f"**👤 {row['ho_ten']}** [{row.get('lop_hoc', 'N/A')}] - *Ca: {row.get('ca_hoc', '17h30 - 19h30')}*")
                        c1, c2, c3 = st.columns([2, 2.5, 4.5])
                        
                        default_ca = row['ca_hoc'] if ('ca_hoc' in row and pd.notna(row['ca_hoc']) and row['ca_hoc'] in DANH_SACH_CA_MAU) else "17h30 - 19h30"

                        with c1:
                            ca_val = st.selectbox("Ca học", danh_sach_ca_mau_dd, index=danh_sach_ca_mau_dd.index(default_ca) if default_ca in danh_sach_ca_mau_dd else 5, key=f"ca_cls_{row['hoc_sinh_id']}_{idx}")
                            if ca_val == "⏱️ Tự nhập giờ tùy chỉnh...":
                                custom_ca = st.text_input("Nhập giờ", value="18h00 - 20h00", key=f"custom_ca_{row['hoc_sinh_id']}_{idx}")
                                ca_final = custom_ca.strip()
                            else:
                                ca_final = ca_val

                        with c2:
                            stt_val = st.radio("Trạng thái", ["Có mặt", "Vắng có phép", "Vắng không phép"], index=0, key=f"stt_cls_{row['hoc_sinh_id']}_{idx}", horizontal=False)
                        
                        with c3:
                            tags_options = ["🌟 Chăm chú", "💪 Có tiến bộ", "⚠️ Quên làm bài tập", "💤 Buồn ngủ/Mất tập trung"]
                            selected_tags = st.multiselect("🏷️ Chọn nhanh thẻ thái độ:", tags_options, key=f"tags_cls_{row['hoc_sinh_id']}_{idx}")
                            custom_nx = st.text_input("Ghi chú thêm", key=f"nx_cls_{row['hoc_sinh_id']}_{idx}", placeholder="Nhận xét bài học...")
                            
                            tag_str = " ".join([f"[{t}]" for t in selected_tags])
                            if tag_str and custom_nx.strip():
                                nx_val = f"{tag_str} - {custom_nx.strip()}"
                            elif tag_str:
                                nx_val = tag_str
                            else:
                                nx_val = custom_nx.strip()

                        danh_sach_luu.append((row['hoc_sinh_id'], date_str, ca_final, stt_val, nx_val))
                        st.divider()

                    if st.form_submit_button(f"💾 LƯU ĐIỂM DANH", type="primary", use_container_width=True):
                        success_count = 0
                        with engine.begin() as conn:
                            for item in danh_sach_luu:
                                try:
                                    existing_record = conn.execute(text('''
                                        SELECT id FROM diem_danh 
                                        WHERE hoc_sinh_id = :hs_id AND ngay = :ngay AND ca_hoc = :ca
                                    '''), {"hs_id": item[0], "ngay": item[1], "ca": item[2]}).fetchone()

                                    if existing_record:
                                        conn.execute(text('''
                                            UPDATE diem_danh 
                                            SET trang_thai = :stt, nhan_xet = :nx 
                                            WHERE id = :id
                                        '''), {"stt": item[3], "nx": item[4], "id": existing_record[0]})
                                    else:
                                        conn.execute(text('''
                                            INSERT INTO diem_danh (hoc_sinh_id, ngay, ca_hoc, trang_thai, nhan_xet) 
                                            VALUES (:hs_id, :ngay, :ca, :stt, :nx)
                                        '''), {"hs_id": item[0], "ngay": item[1], "ca": item[2], "stt": item[3], "nx": item[4]})
                                    success_count += 1
                                except Exception as e:
                                    st.error(f"❌ Lỗi lưu điểm danh HS ID {item[0]}: {e}")
                        if success_count > 0:
                            st.success(f"✅ Đã lưu thành công {success_count} bản ghi điểm danh lên Supabase!")
                            st.rerun()

        st.markdown("---")
        st.subheader(f"📊 Kết quả & Thống kê điểm danh ngày {ngay_hoc.strftime('%d/%m/%Y')}")

        df_dd_today = pd.read_sql_query(f'''
            SELECT d.id, h.ho_ten AS "Họ và Tên", h.lop_hoc AS "Lớp", d.ca_hoc AS "Ca Học", d.trang_thai AS "Trạng Thái", d.nhan_xet AS "Nhận Xét"
            FROM diem_danh d
            JOIN hoc_sinh h ON d.hoc_sinh_id = h.id
            WHERE d.ngay = '{date_str}'
            ORDER BY d.id DESC
        ''', engine)

        if not df_dd_today.empty:
            co_mat = len(df_dd_today[df_dd_today['Trạng Thái'] == 'Có mặt'])
            vang_phep = len(df_dd_today[df_dd_today['Trạng Thái'] == 'Vắng có phép'])
            vang_khong_phep = len(df_dd_today[df_dd_today['Trạng Thái'] == 'Vắng không phép'])

            m1, m2, m3 = st.columns(3)
            m1.metric("🟢 Tổng đi học (Có mặt)", f"{co_mat} HS")
            m2.metric("🟡 Vắng có phép", f"{vang_phep} HS")
            m3.metric("🔴 Vắng không phép", f"{vang_khong_phep} HS")

            st.dataframe(df_dd_today[['Họ và Tên', 'Lớp', 'Ca Học', 'Trạng Thái', 'Nhận Xét']], use_container_width=True)
        else:
            st.info("ℹ️ Chưa có dữ liệu điểm danh nào được ghi nhận cho ngày này.")

    with tab_dd_quanly:
        st.subheader("⚙️ Quản Lý, Sửa Hoặc Xóa Nhật Ký Điểm Danh")
        sel_date_filter = st.date_input("🗓️ Chọn ngày cần sửa/xóa điểm danh", date.today(), key="filter_log_date_picker")
        date_filter_str = sel_date_filter.strftime("%Y-%m-%d")
        
        df_logs = pd.read_sql_query(f'''
            SELECT d.id AS "Mã Lịch", h.id AS hoc_sinh_id, h.ho_ten AS "Họ Tên", h.lop_hoc AS "Lớp", d.ngay AS "Ngày", d.ca_hoc AS "Ca Học", d.trang_thai AS "Trạng Thái", d.nhan_xet AS "Nhận Xét" 
            FROM diem_danh d 
            JOIN hoc_sinh h ON d.hoc_sinh_id = h.id 
            WHERE d.ngay = '{date_filter_str}'
            ORDER BY d.id DESC
        ''', engine)
        
        if not df_logs.empty:
            st.write(f"📋 Danh sách điểm danh trong ngày **{sel_date_filter.strftime('%d/%m/%Y')}** ({len(df_logs)} bản ghi):")
            st.dataframe(df_logs[['Mã Lịch', 'Họ Tên', 'Lớp', 'Ca Học', 'Trạng Thái', 'Nhận Xét']], use_container_width=True)
            
            st.markdown("---")
            st.subheader("🏫 Sửa / Xóa Hàng Loạt Theo Lớp Trong Ngày")
            available_classes = sorted(df_logs['Lớp'].dropna().unique().tolist())
            sel_class_action = st.selectbox("Chọn Lớp cần thao tác:", available_classes, key="sel_class_action_key")
            
            df_class_logs = df_logs[df_logs['Lớp'] == sel_class_action]
            
            with st.form(f"form_class_batch_edit_{sel_class_action}"):
                st.markdown(f"**Danh sách tất cả học sinh lớp {sel_class_action} ({len(df_class_logs)} em):**")
                class_updates = []
                for idx, r in df_class_logs.iterrows():
                    st.markdown(f"**👤 {r['Họ Tên']}** - *Ca: {r['Ca Học']}*")
                    c_stt, c_nx = st.columns([1, 2])
                    
                    stt_options = ["Có mặt", "Vắng có phép", "Vắng không phép"]
                    current_stt_idx = stt_options.index(r['Trạng Thái']) if r['Trạng Thái'] in stt_options else 0
                    
                    with c_stt:
                        new_stt = st.selectbox("Trạng thái", stt_options, index=current_stt_idx, key=f"batch_stt_{r['Mã Lịch']}")
                    with c_nx:
                        new_nx = st.text_input("Nhận xét", value=r['Nhận Xét'] or "", key=f"batch_nx_{r['Mã Lịch']}")
                    
                    class_updates.append((r['Mã Lịch'], new_stt, new_nx))
                    st.divider()
                    
                col_sub1, col_sub2 = st.columns(2)
                with col_sub1:
                    submit_batch = st.form_submit_button("💾 Lưu Cập Nhật Cho Lớp Này", type="primary", use_container_width=True)
                with col_sub2:
                    submit_del_class = st.form_submit_button("❌ Xóa Toàn Bộ Điểm Danh Lớp Này", type="secondary", use_container_width=True)
                    
                if submit_batch:
                    with engine.begin() as conn:
                        for rec_id, stt, nx in class_updates:
                            conn.execute(text('''
                                UPDATE diem_danh 
                                SET trang_thai = :stt, nhan_xet = :nx 
                                WHERE id = :id
                            '''), {"stt": stt, "nx": nx.strip(), "id": rec_id})
                    st.success(f"✅ Đã cập nhật thành công điểm danh cho lớp {sel_class_action}!")
                    st.rerun()
                    
                if submit_del_class:
                    with engine.begin() as conn:
                        for rec_id, _, _ in class_updates:
                            conn.execute(text("DELETE FROM diem_danh WHERE id = :id"), {"id": rec_id})
                    st.success(f"✅ Đã xóa toàn bộ điểm danh của lớp {sel_class_action} trong ngày!")
                    st.rerun()

            st.markdown("---")
            with st.expander("⚙️ Hoặc sửa / xóa từng bản ghi lẻ riêng biệt"):
                log_dict = {f"Mã ID: {row['Mã Lịch']} - {row['Họ Tên']} [{row['Lớp']}] (Ca: {row['Ca Học']} - {row['Trạng Thái']})": row['Mã Lịch'] for _, row in df_logs.iterrows()}
                selected_log_label = st.selectbox("Chọn bản ghi (Mã Lịch) cần sửa hoặc xóa:", list(log_dict.keys()), key="log_sel_id_by_date")
                log_to_edit_del = log_dict[selected_log_label]
                row_log_item = df_logs[df_logs['Mã Lịch'] == log_to_edit_del].iloc[0]
                
                with st.form("form_edit_delete_diem_danh_record"):
                    st.write(f"Đang thao tác Mã Lịch **{log_to_edit_del}**: {row_log_item['Họ Tên']} [{row_log_item['Lớp']}] - Ngày: {row_log_item['Ngày']} - Ca: {row_log_item['Ca Học']}")
                    stt_options = ["Có mặt", "Vắng có phép", "Vắng không phép"]
                    default_stt_idx = stt_options.index(row_log_item['Trạng Thái']) if row_log_item['Trạng Thái'] in stt_options else 0
                    edit_stt_val = st.selectbox("Trạng thái mới:", stt_options, index=default_stt_idx, key="edit_log_stt")
                    edit_nx_val = st.text_input("Nhận xét mới:", value=row_log_item['Nhận Xét'] or "", key="edit_log_nx")
                    
                    col_eb1, col_eb2 = st.columns(2)
                    with col_eb1:
                        submit_update_log = st.form_submit_button("💾 Cập Nhật Điểm Danh", type="primary")
                    with col_eb2:
                        submit_delete_log = st.form_submit_button("❌ Xóa Bản Ghi Này", type="secondary")
                        
                    if submit_update_log:
                        with engine.begin() as conn:
                            conn.execute(text('''
                                UPDATE diem_danh 
                                SET trang_thai = :stt, nhan_xet = :nx 
                                WHERE id = :id
                            '''), {"stt": edit_stt_val, "nx": edit_nx_val.strip(), "id": log_to_edit_del})
                        st.success(f"✅ Đã cập nhật thành công Mã Lịch {log_to_edit_del}!")
                        st.rerun()
                        
                    if submit_delete_log:
                        with engine.begin() as conn:
                            conn.execute(text("DELETE FROM diem_danh WHERE id = :id"), {"id": log_to_edit_del})
                        st.success(f"✅ Đã xóa thành công Mã Lịch {log_to_edit_del}!")
                        st.rerun()
        else:
            st.info(f"💡 Không có bản ghi điểm danh nào trong ngày {sel_date_filter.strftime('%d/%m/%Y')}.")

    with tab_dd_lich_su:
        st.subheader("📊 Xem Lịch Sử Điểm Danh & Xuất Ảnh Theo Học Sinh Trong Tháng")
        df_hs_ls = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh ORDER BY id DESC", engine)
        if df_hs_ls.empty:
            st.warning("Chưa có học sinh nào trong hệ thống.")
        else:
            c_y_ls, c_m_ls, c_hs_ls = st.columns([1, 1, 2])
            with c_y_ls:
                nam_ls = st.number_input("Năm", min_value=2020, max_value=2035, value=datetime.now().year, key="nam_ls_pick")
            with c_m_ls:
                thang_ls = st.selectbox("Tháng", list(range(1, 13)), index=datetime.now().month - 1, format_func=lambda x: f"Tháng {x}", key="thang_ls_pick")
            with c_hs_ls:
                hs_dict_ls = {f"{r['ho_ten']} [{r['lop_hoc']}] - ID:{r['id']}": r['id'] for _, r in df_hs_ls.iterrows()}
                sel_hs_ls_lbl = st.selectbox("Chọn học sinh", list(hs_dict_ls.keys()), key="sel_hs_ls_key")
                sel_hs_id_ls = hs_dict_ls[sel_hs_ls_lbl]
                sel_hs_row_ls = df_hs_ls[df_hs_ls['id'] == sel_hs_id_ls].iloc[0]
            
            thang_nam_q = f"{nam_ls}-{thang_ls:02d}"
            thang_nam_k = f"{thang_ls:02d}/{nam_ls}"
            
            df_hs_att_history = pd.read_sql_query(f'''
                SELECT 
                    TO_CHAR(d.ngay, 'DD/MM/YYYY') AS "Ngày",
                    d.ca_hoc AS "Ca học",
                    d.trang_thai AS "Trạng thái",
                    COALESCE(d.nhan_xet, '') AS "Nhận xét"
                FROM diem_danh d
                WHERE d.hoc_sinh_id = {sel_hs_id_ls} AND TO_CHAR(d.ngay, 'YYYY-MM') = '{thang_nam_q}'
                ORDER BY d.ngay ASC, d.id ASC
            ''', engine)
            
            if df_hs_att_history.empty:
                st.info(f"ℹ️ Học sinh {sel_hs_row_ls['ho_ten']} chưa có lịch sử điểm danh trong Tháng {thang_nam_k}.")
            else:
                total_co_mat = len(df_hs_att_history[df_hs_att_history['Trạng thái'] == 'Có mặt'])
                st.metric("🟢 Tổng số buổi đi học (Có mặt)", f"{total_co_mat} buổi", f"Tổng số bản ghi: {len(df_hs_att_history)} buổi")
                st.dataframe(df_hs_att_history, use_container_width=True)
                
                if HAS_MATPLOTLIB:
                    img_ls_bytes = create_student_attendance_history_image(
                        student_name=sel_hs_row_ls['ho_ten'],
                        lop_hoc=sel_hs_row_ls['lop_hoc'],
                        month_year=thang_nam_k,
                        df_history=df_hs_att_history,
                        total_present=total_co_mat
                    )
                    safe_name_hs = re.sub(r'[\\/*?:"<>|]', "", f"{sel_hs_row_ls['ho_ten']}_{sel_hs_row_ls['lop_hoc']}".replace(" ", "_"))
                    st.download_button(
                        label=f"🖼️ Tải Ảnh Lịch Sử Điểm Danh ({sel_hs_row_ls['ho_ten']})",
                        data=img_ls_bytes,
                        file_name=f"Lich_Su_Diem_Danh_{safe_name_hs}_Thang_{thang_ls}_{nam_ls}.png",
                        mime="image/png",
                        type="primary",
                        key="btn_download_student_att_img"
                    )

# =========================================================
# --- CHỨC NĂNG 2: QUẢN LÝ & LỊCH HỌC TỔNG QUAN ---
# =========================================================
elif choice == "2. 🗺️ Quản Lý & Lịch Học Tổng Quan":
    st.subheader("🗺️ Trung Tâm Quản Lý Thời Khóa Biểu & Lịch Học")

    tab_matrix, tab_goc, tab_tam, tab_export = st.tabs([
        "🗺️ Lịch Học Tổng Quan", 
        "📅 1. Lịch Gốc Hàng Tuần", 
        "⏳ 2. Lịch Học Tạm Thời", 
        "📥 Xuất Ảnh Lịch Học"
    ])

    with tab_matrix:
        st.markdown("##### 🗓️ Chọn mốc tuần cần xem lịch học tổng quan:")
        sel_date_matrix = st.date_input("Xem tuần chứa ngày:", date.today(), key="sel_date_matrix_main")
        st.divider()
        render_schedule_matrix(engine, ref_date=sel_date_matrix)

    with tab_goc:
        st.subheader("📅 Xếp Lịch Học Cố Định Hàng Tuần (Lịch Gốc)")
        sub_tab_goc_tao, sub_tab_goc_sua = st.tabs(["➕ Thêm lịch gốc mới", "✏️ Sửa lịch học gốc"])
        
        df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", engine)
        
        with sub_tab_goc_tao:
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

                if "last_goc_target" not in st.session_state:
                    st.session_state.last_goc_target = target_name_label

                if st.session_state.last_goc_target != target_name_label:
                    st.session_state.last_goc_target = target_name_label
                    cac_thu_reset = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
                    for t_res in cac_thu_reset:
                        st.session_state[f"chk_goc_lop_{t_res}"] = False
                        st.session_state[f"multi_ca_{t_res}"] = []
                        st.session_state[f"custom_ca_multi_{t_res}"] = ""
                    if hasattr(st, "rerun"):
                        st.rerun()

                cac_thu = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
                
                schedule_dict_to_save = {}
                for t in cac_thu:
                    with st.expander(f"🗓️ Cấu hình ca học cho **{t}**", expanded=False):
                        has_class = st.checkbox(f"Có lịch học vào {t}", key=f"chk_goc_lop_{t}")
                        if has_class:
                            cas_chon = st.multiselect(f"Chọn các ca chuẩn vào {t}:", DANH_SACH_CA_MAU, default=["17h30 - 19h30"] if t != "Chủ Nhật" else [], key=f"multi_ca_{t}")
                            custom_ca_them = st.text_input(f"Thêm ca giờ tùy chỉnh vào {t} (nếu có, cách nhau bằng dấu phẩy):", placeholder="VD: 08h00 - 10h00", key=f"custom_ca_multi_{t}")
                            
                            all_cas_for_day = list(cas_chon)
                            if custom_ca_them.strip():
                                extra_cas = [c_item.strip() for c_item in custom_ca_them.split(",") if c_item.strip()]
                                all_cas_for_day.extend(extra_cas)
                            
                            if all_cas_for_day:
                                schedule_dict_to_save[t] = list(set(all_cas_for_day))

                if st.button(f"💾 Lưu Lịch Học Gốc Cho {target_name_label}", type="primary"):
                    with engine.begin() as conn:
                        for hs_id in target_hs_ids:
                            conn.execute(text("DELETE FROM lich_hoc_tuan WHERE hoc_sinh_id = :id"), {"id": hs_id})
                            for t_val, list_ca in schedule_dict_to_save.items():
                                for ca_val in list_ca:
                                    conn.execute(text('''
                                        INSERT INTO lich_hoc_tuan (hoc_sinh_id, thu, ca_hoc) 
                                        VALUES (:hs_id, :thu, :ca)
                                        ON CONFLICT (hoc_sinh_id, thu, ca_hoc) DO NOTHING
                                    '''), {"hs_id": hs_id, "thu": t_val, "ca": ca_val})
                    st.success(f"✅ Đã lưu lịch gốc cho {target_name_label} thành công lên Supabase!")
                    st.rerun()

        with sub_tab_goc_sua:
            st.subheader("🗑️ Xóa Lịch Học Gốc Theo Lớp Hoặc Học Sinh")
            df_goc_all = pd.read_sql_query('''
                SELECT l.id, l.hoc_sinh_id, h.ho_ten, h.lop_hoc, l.thu, l.ca_hoc
                FROM lich_hoc_tuan l
                JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
                ORDER BY h.lop_hoc ASC, h.ho_ten ASC
            ''', engine)
            
            if df_goc_all.empty:
                st.info("💡 Chưa có lịch học gốc nào được thiết lập trong hệ thống.")
            else:
                xoa_mode = st.radio("Chọn phạm vi xóa lịch gốc:", ["Xóa theo Lớp", "Xóa theo Học sinh cụ thể"], horizontal=True, key="xoa_mode_goc_scope")
                
                if xoa_mode == "Xóa theo Lớp":
                    all_lops_goc = sorted(df_goc_all['lop_hoc'].dropna().unique().tolist())
                    selected_lop_xoa = st.selectbox("Chọn Lớp cần xóa lịch gốc:", all_lops_goc, key="sel_lop_xoa_goc")
                    df_lop_goc_records = df_goc_all[df_goc_all['lop_hoc'] == selected_lop_xoa]
                    
                    st.write(f"📋 Danh sách các ca học gốc của lớp **{selected_lop_xoa}** ({len(df_lop_goc_records)} bản ghi):")
                    if not df_lop_goc_records.empty:
                        st.dataframe(df_lop_goc_records[['id', 'ho_ten', 'thu', 'ca_hoc']], use_container_width=True)
                        
                        with st.form(f"form_xoa_goc_lop_{selected_lop_xoa}"):
                            # Tự động lấy danh sách các ngày học (Thứ) và ca học thực tế của lớp này để chọn
                            unique_slots = df_lop_goc_records[['thu', 'ca_hoc']].drop_duplicates().values.tolist()
                            slot_options = [f"{thu} | {ca}" for thu, ca in unique_slots]
                            
                            sel_slots_to_delete = st.multiselect(
                                "📌 Chọn ngày học và ca học cần xóa:",
                                options=slot_options,
                                default=slot_options,
                                key="sel_slots_lop_del"
                            )
                            
                            confirm_del_lop = st.checkbox(f"Tôi xác nhận muốn xóa các ca học đã chọn của lớp {selected_lop_xoa}")
                            sub_btn_del_lop = st.form_submit_button("❌ Xóa Lịch Học Gốc Đã Chọn", type="primary")
                            
                            if sub_btn_del_lop:
                                if confirm_del_lop:
                                    if not sel_slots_to_delete:
                                        st.warning("⚠️ Vui lòng chọn ít nhất một ngày và ca học để xóa!")
                                    else:
                                        hs_ids_in_lop = df_lop_goc_records['hoc_sinh_id'].unique().tolist()
                                        with engine.begin() as conn:
                                            for slot_str in sel_slots_to_delete:
                                                parts = slot_str.split(" | ")
                                                if len(parts) == 2:
                                                    t_val, c_val = parts[0].strip(), parts[1].strip()
                                                    for hs_id_item in hs_ids_in_lop:
                                                        conn.execute(text('''
                                                            DELETE FROM lich_hoc_tuan 
                                                            WHERE hoc_sinh_id = :id AND thu = :thu AND ca_hoc = :ca
                                                        '''), {"id": hs_id_item, "thu": t_val, "ca": c_val})
                                        st.success(f"✅ Đã xóa các ngày và ca học đã chọn của lớp {selected_lop_xoa}!")
                                        st.rerun()
                                else:
                                    st.warning("⚠️ Vui lòng tích chọn xác nhận để thực hiện xóa.")
                    else:
                        st.info("Lớp này không có lịch gốc nào.")
                else:
                    hs_with_schedule_ids = df_goc_all['hoc_sinh_id'].unique().tolist()
                    df_hs_goc = df_hs[df_hs['id'].isin(hs_with_schedule_ids)]
                    
                    if df_hs_goc.empty:
                        st.info("Không có học sinh nào có lịch gốc.")
                    else:
                        hs_dict_xoa_goc = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row['id'] for _, row in df_hs_goc.iterrows()}
                        sel_hs_xoa_goc_lbl = st.selectbox("Chọn học sinh cụ thể cần xóa lịch học gốc:", list(hs_dict_xoa_goc.keys()), key="sel_hs_xoa_goc_key")
                        sel_hs_id_goc = hs_dict_xoa_goc[sel_hs_xoa_goc_lbl]
                        
                        df_single_goc = df_goc_all[df_goc_all['hoc_sinh_id'] == sel_hs_id_goc]
                        st.write(f"📋 Lịch gốc hiện tại của học sinh:")
                        st.dataframe(df_single_goc[['id', 'thu', 'ca_hoc']], use_container_width=True)
                        
                        with st.form(f"form_xoa_goc_hs_{sel_hs_id_goc}"):
                            # Tự động lấy danh sách các ngày học (Thứ) và ca học thực tế của học sinh này để chọn
                            unique_slots_hs = df_single_goc[['thu', 'ca_hoc']].drop_duplicates().values.tolist()
                            slot_options_hs = [f"{thu} | {ca}" for thu, ca in unique_slots_hs]
                            
                            sel_slots_hs_to_delete = st.multiselect(
                                "📌 Chọn ngày học và ca học cần xóa:",
                                options=slot_options_hs,
                                default=slot_options_hs,
                                key="sel_slots_hs_del"
                            )
                            
                            confirm_del_hs = st.checkbox("Tôi xác nhận muốn xóa các ca học đã chọn của học sinh này")
                            sub_btn_del_hs = st.form_submit_button("❌ Xóa Lịch Học Gốc Đã Chọn", type="primary")
                            
                            if sub_btn_del_hs:
                                if confirm_del_hs:
                                    if not sel_slots_hs_to_delete:
                                        st.warning("⚠️ Vui lòng chọn ít nhất một ngày và ca học để xóa!")
                                    else:
                                        with engine.begin() as conn:
                                            for slot_str in sel_slots_hs_to_delete:
                                                parts = slot_str.split(" | ")
                                                if len(parts) == 2:
                                                    t_val, c_val = parts[0].strip(), parts[1].strip()
                                                    conn.execute(text('''
                                                        DELETE FROM lich_hoc_tuan 
                                                        WHERE hoc_sinh_id = :id AND thu = :thu AND ca_hoc = :ca
                                                    '''), {"id": sel_hs_id_goc, "thu": t_val, "ca": c_val})
                                        st.success("✅ Đã xóa các ngày và ca học đã chọn của học sinh!")
                                        st.rerun()
                                else:
                                    st.warning("⚠️ Vui lòng tích chọn xác nhận để thực hiện xóa.")

    with tab_tam:
        sub_tab_add_t, sub_tab_manage_t = st.tabs(["➕ Thêm lịch tạm thời mới", "📋 Danh sách, Sửa & Xóa lịch tạm thời"])
        
        with sub_tab_add_t:
            df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", engine)
            if df_hs.empty:
                st.warning("Chưa có học sinh trong hệ thống.")
            else:
                all_lops = sorted(df_hs['lop_hoc'].dropna().unique().tolist())
                sel_lop_tam = st.selectbox("Chọn Lớp / Nhóm", all_lops, key="sel_lop_tam_key")
                
                hs_in_lop = df_hs[df_hs['lop_hoc'] == sel_lop_tam]
                hs_dict_tam = {f"{row['ho_ten']} - ID:{row['id']}": row['id'] for _, row in hs_in_lop.iterrows()}
                
                chon_doi_tuong = st.radio("Áp dụng cho:", ["Toàn bộ lớp", "Từng học sinh cụ thể"], horizontal=True, key="chon_doi_tuong_tam")
                target_hs_ids_tam = hs_in_lop['id'].tolist() if chon_doi_tuong == "Toàn bộ lớp" else [hs_dict_tam[st.selectbox("Chọn học sinh:", list(hs_dict_tam.keys()), key="sel_hs_lbl_tam")]]

                with st.form("form_lich_tam_thoi"):
                    d_start = st.date_input("🗓️ Hiệu lực TỪ ngày", date.today(), key="d_start_tam")
                    d_end = st.date_input("🗓️ Hiệu lực ĐẾN ngày", date.today(), key="d_end_tam")
                    loai_td = st.selectbox("Loại thay đổi", ["Đổi ca / Học bù", "Học thêm buổi", "Nghỉ tạm thời trong khoảng thời gian này"], key="loai_td_tam")
                    thu_tam = st.selectbox("Vào Thứ", ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật'], key="thu_tam_sel")
                    ca_tam_chon = st.multiselect("Chọn các ca học tạm thời:", DANH_SACH_CA_MAU, default=["17h30 - 19h30"], key="ca_tam_multiselect")
                    
                    if st.form_submit_button("💾 Thiết Lập Lịch Tạm Thời", type="primary"):
                        total_saved = 0
                        with engine.begin() as conn:
                            for hs_id_item in target_hs_ids_tam:
                                for ca_item in ca_tam_chon:
                                    try:
                                        conn.execute(text('''
                                            INSERT INTO lich_hoc_tam_thoi (hoc_sinh_id, ngay_bat_dau, ngay_ket_thuc, thu, ca_hoc, loai_thay_doi)
                                            VALUES (:hs_id, :start, :end, :thu, :ca, :loai)
                                        '''), {"hs_id": hs_id_item, "start": d_start.strftime("%Y-%m-%d"), "end": d_end.strftime("%Y-%m-%d"), "thu": thu_tam, "ca": ca_item, "loai": loai_td})
                                        total_saved += 1
                                    except Exception:
                                        pass
                        if total_saved > 0:
                            st.success(f"✅ Đã lưu thành công {total_saved} thiết lập lịch tạm thời lên Supabase!")
                            st.rerun()

        with sub_tab_manage_t:
            st.subheader("📋 Danh Sách & Quản Lý Lịch Học Tạm Thời Theo Lớp")
            df_temp_manage = pd.read_sql_query('''
                SELECT t.id, t.hoc_sinh_id, h.ho_ten, h.lop_hoc, t.ngay_bat_dau, t.ngay_ket_thuc, t.thu, t.ca_hoc, t.loai_thay_doi
                FROM lich_hoc_tam_thoi t
                JOIN hoc_sinh h ON t.hoc_sinh_id = h.id
                ORDER BY t.ngay_bat_dau DESC
            ''', engine)
            
            if df_temp_manage.empty:
                st.info("💡 Chưa có thiết lập lịch tạm thời nào.")
            else:
                st.dataframe(df_temp_manage[['id', 'ho_ten', 'lop_hoc', 'ngay_bat_dau', 'ngay_ket_thuc', 'thu', 'ca_hoc', 'loai_thay_doi']], use_container_width=True)
                
                st.markdown("---")
                st.subheader("🏫 Sửa / Xóa Hàng Loạt Lịch Tạm Thời Theo Lớp")
                available_classes_temp = sorted(df_temp_manage['lop_hoc'].dropna().unique().tolist())
                sel_class_temp_action = st.selectbox("Chọn Lớp cần thao tác:", available_classes_temp, key="sel_class_temp_action_key")
                
                df_class_temp_logs = df_temp_manage[df_temp_manage['lop_hoc'] == sel_class_temp_action]
                
                with st.form(f"form_class_batch_edit_temp_{sel_class_temp_action}"):
                    st.markdown(f"**Danh sách thiết lập lịch tạm thời của lớp {sel_class_temp_action} ({len(df_class_temp_logs)} bản ghi):**")
                    class_temp_updates = []
                    for idx, r in df_class_temp_logs.iterrows():
                        st.markdown(f"**👤 {r['ho_ten']}** - Từ: {r['ngay_bat_dau']} đến {r['ngay_ket_thuc']} ({r['thu']} - Ca: {r['ca_hoc']})")
                        c_s, c_e, c_l, c_t, c_c = st.columns(5)
                        
                        loai_options = ["Đổi ca / Học bù", "Học thêm buổi", "Nghỉ tạm thời trong khoảng thời gian này"]
                        curr_loai_idx = loai_options.index(r['loai_thay_doi']) if r['loai_thay_doi'] in loai_options else 0
                        
                        thu_options = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
                        curr_thu_idx = thu_options.index(r['thu']) if r['thu'] in thu_options else 0
                        
                        with c_s:
                            new_start = st.date_input("Từ ngày", value=datetime.strptime(str(r['ngay_bat_dau']), "%Y-%m-%d").date(), key=f"t_start_{r['id']}")
                        with c_e:
                            new_end = st.date_input("Đến ngày", value=datetime.strptime(str(r['ngay_ket_thuc']), "%Y-%m-%d").date(), key=f"t_end_{r['id']}")
                        with c_l:
                            new_loai = st.selectbox("Loại thay đổi", loai_options, index=curr_loai_idx, key=f"t_loai_{r['id']}")
                        with c_t:
                            new_thu = st.selectbox("Thứ", thu_options, index=curr_thu_idx, key=f"t_thu_{r['id']}")
                        with c_c:
                            new_ca = st.text_input("Ca học", value=r['ca_hoc'], key=f"t_ca_{r['id']}")
                        
                        class_temp_updates.append((r['id'], new_start, new_end, new_loai, new_thu, new_ca))
                        st.divider()
                        
                    col_sub1, col_sub2 = st.columns(2)
                    with col_sub1:
                        submit_batch_temp = st.form_submit_button("💾 Lưu Cập Nhật Lịch Tạm Thời Cho Lớp Này", type="primary", use_container_width=True)
                    with col_sub2:
                        submit_del_class_temp = st.form_submit_button("❌ Xóa Toàn Bộ Lịch Tạm Thời Lớp Này", type="secondary", use_container_width=True)
                        
                    if submit_batch_temp:
                        with engine.begin() as conn:
                            for rec_id, start, end, loai, thu, ca in class_temp_updates:
                                conn.execute(text('''
                                    UPDATE lich_hoc_tam_thoi 
                                    SET ngay_bat_dau = :start, ngay_ket_thuc = :end, loai_thay_doi = :loai, thu = :thu, ca_hoc = :ca 
                                    WHERE id = :id
                                '''), {
                                    "start": start.strftime("%Y-%m-%d"),
                                    "end": end.strftime("%Y-%m-%d"),
                                    "loai": loai,
                                    "thu": thu,
                                    "ca": ca.strip(),
                                    "id": rec_id
                                })
                        st.success(f"✅ Đã cập nhật thành công lịch tạm thời cho lớp {sel_class_temp_action}!")
                        st.rerun()
                        
                    if submit_del_class_temp:
                        with engine.begin() as conn:
                            for rec_id, _, _, _, _, _ in class_temp_updates:
                                conn.execute(text("DELETE FROM lich_hoc_tam_thoi WHERE id = :id"), {"id": rec_id})
                        st.success(f"✅ Đã xóa toàn bộ lịch tạm thời của lớp {sel_class_temp_action}!")
                        st.rerun()

                st.markdown("---")
                with st.expander("⚙️ Hoặc sửa / xóa từng bản ghi lẻ riêng biệt"):
                    temp_dict = {f"ID: {row['id']} - {row['ho_ten']} [{row['lop_hoc']}] ({row['ngay_bat_dau']} -> {row['ngay_ket_thuc']}, {row['thu']}, Ca: {row['ca_hoc']})": row['id'] for _, row in df_temp_manage.iterrows()}
                    selected_temp_label = st.selectbox("Chọn bản ghi cần sửa hoặc xóa:", list(temp_dict.keys()), key="temp_sel_id_indiv")
                    temp_to_edit_del = temp_dict[selected_temp_label]
                    row_temp_item = df_temp_manage[df_temp_manage['id'] == temp_to_edit_del].iloc[0]
                    
                    with st.form("form_edit_delete_temp_record"):
                        st.write(f"Đang thao tác Bản ghi ID **{temp_to_edit_del}**: {row_temp_item['ho_ten']} [{row_temp_item['lop_hoc']}]")
                        e_start = st.date_input("🗓️ Hiệu lực TỪ ngày", value=datetime.strptime(str(row_temp_item['ngay_bat_dau']), "%Y-%m-%d").date(), key="e_start_date_indiv")
                        e_end = st.date_input("🗓️ Hiệu lực ĐẾN ngày", value=datetime.strptime(str(row_temp_item['ngay_ket_thuc']), "%Y-%m-%d").date(), key="e_end_date_indiv")
                        
                        loai_options = ["Đổi ca / Học bù", "Học thêm buổi", "Nghỉ tạm thời trong khoảng thời gian này"]
                        default_loai_idx = loai_options.index(row_temp_item['loai_thay_doi']) if row_temp_item['loai_thay_doi'] in loai_options else 0
                        e_loai = st.selectbox("Loại thay đổi", loai_options, index=default_loai_idx, key="e_loai_td_indiv")
                        
                        thu_options = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
                        default_thu_idx = thu_options.index(row_temp_item['thu']) if row_temp_item['thu'] in thu_options else 0
                        e_thu = st.selectbox("Vào Thứ", thu_options, index=default_thu_idx, key="e_thu_sel_indiv")
                        
                        e_ca = st.text_input("Ca học:", value=row_temp_item['ca_hoc'], key="e_ca_input_indiv")
                        
                        col_eb1, col_eb2 = st.columns(2)
                        with col_eb1:
                            submit_update_temp = st.form_submit_button("💾 Cập Nhật Bản Ghi Này", type="primary")
                        with col_eb2:
                            submit_delete_temp = st.form_submit_button("❌ Xóa Bản Ghi Này", type="secondary")
                            
                        if submit_update_temp:
                            with engine.begin() as conn:
                                conn.execute(text('''
                                    UPDATE lich_hoc_tam_thoi
                                    SET ngay_bat_dau = :start, ngay_ket_thuc = :end, thu = :thu, ca_hoc = :ca, loai_thay_doi = :loai
                                    WHERE id = :id
                                '''), {
                                    "start": e_start.strftime("%Y-%m-%d"),
                                    "end": e_end.strftime("%Y-%m-%d"),
                                    "thu": e_thu,
                                    "ca": e_ca.strip(),
                                    "loai": e_loai,
                                    "id": temp_to_edit_del
                                })
                            st.success(f"✅ Đã cập nhật thành công bản ghi ID {temp_to_edit_del}!")
                            st.rerun()
                            
                        if submit_delete_temp:
                            with engine.begin() as conn:
                                conn.execute(text("DELETE FROM lich_hoc_tam_thoi WHERE id = :id"), {"id": temp_to_edit_del})
                            st.success(f"✅ Đã xóa thành công bản ghi ID {temp_to_edit_del}!")
                            st.rerun()

    with tab_export:
        st.markdown("### 📥 Xuất File Lịch Học Hàng Tuần Dạng Ảnh PNG")
        df_hs_all = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", engine)

        if df_hs_all.empty:
            st.warning("Chưa có dữ liệu học sinh.")
        else:
            sel_date_export = st.date_input("🗓️ Chọn tuần để xuất ảnh:", date.today(), key="sel_date_export_img_m")
            filter_mode = st.radio("Chọn phạm vi xuất lịch học:", ["Theo Lớp cụ thể", "Theo Học sinh cụ thể"], horizontal=True, key="filter_mode_exp_m")
            
            target_title = "Lớp học"
            selected_lop_exp = None
            selected_hs_exp = None
            prefix_label = "Học sinh / Lớp: "
            file_name_download = "Lich_Hoc.png"

            if filter_mode == "Theo Lớp cụ thể":
                lop_list = sorted(df_hs_all['lop_hoc'].dropna().unique().tolist())
                selected_lop_exp = st.selectbox("Chọn Lớp:", lop_list, key="sel_lop_exp_m")
                target_title = f"Lớp {selected_lop_exp}"
                prefix_label = "Học sinh / Lớp: "
                safe_lop_name = re.sub(r'[\\/*?:"<>|]', "", f"{selected_lop_exp}".replace(" ", "_"))
                file_name_download = f"Lich_Hoc_Lop_{safe_lop_name}.png"
            elif filter_mode == "Theo Học sinh cụ thể":
                hs_dict_exp = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row for _, row in df_hs_all.iterrows()}
                sel_hs_label = st.selectbox("Chọn Học sinh:", list(hs_dict_exp.keys()), key="sel_hs_label_exp_m")
                selected_hs_row = hs_dict_exp[sel_hs_label]
                selected_hs_exp = selected_hs_row['id']
                target_title = f"{selected_hs_row['ho_ten']} ({selected_hs_row['lop_hoc']})"
                prefix_label = "Học sinh / Lớp: "
                safe_hs_name = re.sub(r'[\\/*?:"<>|]', "", f"{selected_hs_row['ho_ten']}_{selected_hs_row['lop_hoc']}".replace(" ", "_"))
                file_name_download = f"Lich_Hoc_{safe_hs_name}.png"

            df_export_matrix = get_schedule_matrix_df(engine, filter_lop=selected_lop_exp, filter_hs_id=selected_hs_exp, ref_date=sel_date_export)

            if df_export_matrix.empty:
                st.info("ℹ️ Không tìm thấy lịch học phù hợp đối với lựa chọn này.")
            else:
                if HAS_MATPLOTLIB:
                    col_ex1, col_ex2 = st.columns(2)
                    with col_ex1:
                        img_bytes = create_weekly_schedule_image(target_title, df_export_matrix, ref_date=sel_date_export, prefix=prefix_label)
                        st.download_button(
                            label=f"🖼️ Tải Ảnh Lịch Học ({target_title})",
                            data=img_bytes,
                            file_name=file_name_download,
                            mime="image/png",
                            type="primary"
                        )
                    with col_ex2:
                        st.markdown("##### 📦 Xuất File ZIP Hàng Loạt")
                        zip_choice = st.radio("Chọn nội dung file ZIP:", ["Tất cả học sinh", "Tất cả các lớp"], horizontal=True, key="zip_choice_schedule")
                        
                        if zip_choice == "Tất cả học sinh":
                            if st.button("📦 Tải ZIP Lịch Học TẤT CẢ Học Sinh", type="secondary"):
                                zip_buffer_s = io.BytesIO()
                                with zipfile.ZipFile(zip_buffer_s, "w", zipfile.ZIP_DEFLATED) as zf:
                                    for _, hs_r in df_hs_all.iterrows():
                                        hs_id_val = hs_r['id']
                                        hs_name_val = hs_r['ho_ten']
                                        hs_lop_val = hs_r['lop_hoc']
                                        
                                        df_hs_mat = get_schedule_matrix_df(engine, filter_hs_id=hs_id_val, ref_date=sel_date_export)
                                        if not df_hs_mat.empty:
                                            img_hs_b = create_weekly_schedule_image(f"{hs_name_val} ({hs_lop_val})", df_hs_mat, ref_date=sel_date_export, prefix="Học sinh: ")
                                            safe_n = re.sub(r'[\\/*?:"<>|]', "", f"{hs_name_val}_{hs_lop_val}".replace(" ", "_"))
                                            zf.writestr(f"Lich_Hoc_{safe_n}.png", img_hs_b.getvalue())
                                zip_buffer_s.seek(0)
                                st.download_button(
                                    label="📥 Bấm Tải Xuống ZIP Tất Cả Học Sinh",
                                    data=zip_buffer_s,
                                    file_name=f"Tat_Ca_Lich_Hoc_Hoc_Sinh_{sel_date_export.strftime('%Y%m%d')}.zip",
                                    mime="application/zip",
                                    type="primary",
                                    key="btn_download_zip_schedule_hs"
                                )
                        else:
                            if st.button("📦 Tải ZIP Lịch Học TẤT CẢ Các Lớp", type="secondary"):
                                zip_buffer_l = io.BytesIO()
                                all_lops_list = sorted(df_hs_all['lop_hoc'].dropna().unique().tolist())
                                with zipfile.ZipFile(zip_buffer_l, "w", zipfile.ZIP_DEFLATED) as zf_l:
                                    for lop_val in all_lops_list:
                                        df_lop_mat = get_schedule_matrix_df(engine, filter_lop=lop_val, ref_date=sel_date_export)
                                        if not df_lop_mat.empty:
                                            img_lop_b = create_weekly_schedule_image(f"Lớp {lop_val}", df_lop_mat, ref_date=sel_date_export, prefix="Lớp: ")
                                            safe_lop_n = re.sub(r'[\\/*?:"<>|]', "", f"{lop_val}".replace(" ", "_"))
                                            zf_l.writestr(f"Lich_Hoc_Lop_{safe_lop_n}.png", img_lop_b.getvalue())
                                zip_buffer_l.seek(0)
                                st.download_button(
                                    label="📥 Bấm Tải Xuống ZIP Tất Cả Các Lớp",
                                    data=zip_buffer_l,
                                    file_name=f"Tat_Ca_Lich_Hoc_Cac_Lop_{sel_date_export.strftime('%Y%m%d')}.zip",
                                    mime="application/zip",
                                    type="primary",
                                    key="btn_download_zip_schedule_lop"
                                )

# =========================================================
# --- CHỨC NĂNG 3: THỐNG KÊ SỐ CA & QUẢN LÝ HỌC PHÍ ---
# =========================================================
elif choice == "3. 💳 Thống Kê Số Ca & Quản Lý Học Phí":
    st.subheader("💳 Thống Kê Số Ca & Quản Lý Học Phí")
    
    che_do_xem = st.radio("⏱️ Chọn chế độ xem thống kê:", ["Theo Tháng", "Theo Tuần", "Theo Ngày"], horizontal=True)
    
    combined_df = pd.DataFrame()
    qr_path = "qr_code.png" if os.path.exists("qr_code.png") else None
    
    if che_do_xem == "Theo Tháng":
        col_y, col_m = st.columns([1, 3])
        with col_y:
            nam_selected = st.number_input("Chọn Năm", min_value=2020, max_value=2035, value=datetime.now().year)
        with col_m:
            selected_thangs = st.multiselect("Chọn Tháng:", list(range(1, 13)), default=[datetime.now().month], format_func=lambda x: f"Tháng {x}")
        
        if selected_thangs:
            if len(selected_thangs) == 1:
                th = selected_thangs[0]
                thang_nam_query = f"{nam_selected}-{th:02d}"
                thang_nam_key = f"{th:02d}/{nam_selected}"
                
                q = f'''
                    SELECT 
                        h.id AS hoc_sinh_id, 
                        h.ho_ten AS "Họ và Tên", 
                        h.lop_hoc AS "Lớp", 
                        h.mon_hoc AS "Môn Học", 
                        h.hoc_phi_buoi AS "Đơn Giá/Ca (VNĐ)",
                        '{thang_nam_key}' AS "Thời gian",
                        SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS "Số Ca Có Mặt",
                        (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS "Tổng Tiền (VNĐ)",
                        COALESCE(t.trang_thai, 'Chưa đóng') AS "Trạng Thái"
                    FROM hoc_sinh h
                    LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND TO_CHAR(d.ngay, 'YYYY-MM') = '{thang_nam_query}'
                    LEFT JOIN thanh_toan t ON h.id = t.hoc_sinh_id AND t.thang_nam = '{thang_nam_key}'
                    GROUP BY h.id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi, t.trang_thai
                '''
                combined_df = pd.read_sql_query(q, engine)
                combined_df['is_multi'] = False
                combined_df['details'] = [[] for _ in range(len(combined_df))]
            else:
                df_hs_all = pd.read_sql_query("SELECT id AS hoc_sinh_id, ho_ten AS \"Họ và Tên\", lop_hoc AS \"Lớp\", mon_hoc AS \"Môn Học\", hoc_phi_buoi AS \"Đơn Giá/Ca (VNĐ)\" FROM hoc_sinh", engine)
                rows_aggregated = []
                
                for _, hs in df_hs_all.iterrows():
                    hs_id = hs['hoc_sinh_id']
                    valid_month_details = []
                    total_ca_agg = 0
                    total_tien_agg = 0
                    
                    for th in sorted(selected_thangs):
                        thang_nam_query = f"{nam_selected}-{th:02d}"
                        thang_nam_key = f"{th:02d}/{nam_selected}"
                        
                        q_att = f'''
                            SELECT COUNT(*) AS so_ca
                            FROM diem_danh
                            WHERE hoc_sinh_id = {hs_id} AND TO_CHAR(ngay, 'YYYY-MM') = '{thang_nam_query}' AND trang_thai = 'Có mặt'
                        '''
                        df_att = pd.read_sql_query(q_att, engine)
                        so_ca = int(df_att.iloc[0]['so_ca']) if not df_att.empty else 0
                        
                        if so_ca == 0:
                            continue
                            
                        q_pay = f'''
                            SELECT trang_thai FROM thanh_toan
                            WHERE hoc_sinh_id = {hs_id} AND thang_nam = '{thang_nam_key}'
                        '''
                        df_pay = pd.read_sql_query(q_pay, engine)
                        trang_thai_th = df_pay.iloc[0]['trang_thai'] if not df_pay.empty else 'Chưa đóng'
                        
                        thanh_tien = so_ca * hs['Đơn Giá/Ca (VNĐ)']
                        total_ca_agg += so_ca
                        total_tien_agg += thanh_tien
                        
                        valid_month_details.append({
                            'thang_key': thang_nam_key,
                            'so_ca': so_ca,
                            'don_gia': hs['Đơn Giá/Ca (VNĐ)'],
                            'thanh_tien': thanh_tien,
                            'trang_thai': trang_thai_th
                        })
                    
                    if len(valid_month_details) == 0:
                        continue
                    elif len(valid_month_details) == 1:
                        m_info = valid_month_details[0]
                        rows_aggregated.append({
                            'hoc_sinh_id': hs_id,
                            'Họ và Tên': hs['Họ và Tên'],
                            'Lớp': hs['Lớp'],
                            'Môn Học': hs['Môn Học'],
                            'Đơn Giá/Ca (VNĐ)': hs['Đơn Giá/Ca (VNĐ)'],
                            'Thời gian': m_info['thang_key'],
                            'Số Ca Có Mặt': m_info['so_ca'],
                            'Tổng Tiền (VNĐ)': m_info['thanh_tien'],
                            'Trạng Thái': m_info['trang_thai'],
                            'is_multi': False,
                            'details': []
                        })
                    else:
                        status_str_parts = [f"Tháng {d['thang_key']}: {d['trang_thai']}" for d in valid_month_details]
                        status_combined = ", ".join(status_str_parts)
                        thangs_str = " - ".join([d['thang_key'] for d in valid_month_details])
                        
                        rows_aggregated.append({
                            'hoc_sinh_id': hs_id,
                            'Họ và Tên': hs['Họ và Tên'],
                            'Lớp': hs['Lớp'],
                            'Môn Học': hs['Môn Học'],
                            'Đơn Giá/Ca (VNĐ)': hs['Đơn Giá/Ca (VNĐ)'],
                            'Thời gian': thangs_str,
                            'Số Ca Có Mặt': total_ca_agg,
                            'Tổng Tiền (VNĐ)': total_tien_agg,
                            'Trạng Thái': status_combined,
                            'is_multi': True,
                            'details': valid_month_details
                        })
                
                combined_df = pd.DataFrame(rows_aggregated)

    elif che_do_xem == "Theo Ngày":
        ngay_chon = st.date_input("Chọn ngày thống kê:", date.today())
        ngay_str = ngay_chon.strftime("%Y-%m-%d")
        thang_nam_key = ngay_chon.strftime("%m/%Y")
        
        q = f'''
            SELECT 
                h.id AS hoc_sinh_id, 
                h.ho_ten AS "Họ và Tên", 
                h.lop_hoc AS "Lớp", 
                h.mon_hoc AS "Môn Học", 
                h.hoc_phi_buoi AS "Đơn Giá/Ca (VNĐ)",
                '{ngay_chon.strftime("%d/%m/%Y")}' AS "Thời gian",
                SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS "Số Ca Có Mặt",
                (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS "Tổng Tiền (VNĐ)",
                COALESCE(t.trang_thai, 'Chưa đóng') AS "Trạng Thái"
            FROM hoc_sinh h
            LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND d.ngay = '{ngay_str}'
            LEFT JOIN thanh_toan t ON h.id = t.hoc_sinh_id AND t.thang_nam = '{thang_nam_key}'
            GROUP BY h.id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi, t.trang_thai
        '''
        combined_df = pd.read_sql_query(q, engine)
        combined_df['is_multi'] = False
        combined_df['details'] = [[] for _ in range(len(combined_df))]

    else:
        tuan_chon = st.date_input("Chọn ngày thuộc tuần cần xem:", date.today())
        start_w = tuan_chon - timedelta(days=tuan_chon.weekday())
        end_w = start_w + timedelta(days=6)
        start_str = start_w.strftime("%Y-%m-%d")
        end_str = end_w.strftime("%Y-%m-%d")
        thang_nam_key = start_w.strftime("%m/%Y")
        
        st.info(f"📅 Thống kê tuần từ **{start_w.strftime('%d/%m/%Y')}** đến **{end_w.strftime('%d/%m/%Y')}**")
        
        q = f'''
            SELECT 
                h.id AS hoc_sinh_id, 
                h.ho_ten AS "Họ và Tên", 
                h.lop_hoc AS "Lớp", 
                h.mon_hoc AS "Môn Học", 
                h.hoc_phi_buoi AS "Đơn Giá/Ca (VNĐ)",
                'Tuần {start_w.strftime("%d/%m")} - {end_w.strftime("%d/%m")}' AS "Thời gian",
                SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS "Số Ca Có Mặt",
                (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS "Tổng Tiền (VNĐ)",
                COALESCE(t.trang_thai, 'Chưa đóng') AS "Trạng Thái"
            FROM hoc_sinh h
            LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND d.ngay >= '{start_str}' AND d.ngay <= '{end_str}'
            LEFT JOIN thanh_toan t ON h.id = t.hoc_sinh_id AND t.thang_nam = '{thang_nam_key}'
            GROUP BY h.id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi, t.trang_thai
        '''
        combined_df = pd.read_sql_query(q, engine)
        combined_df['is_multi'] = False
        combined_df['details'] = [[] for _ in range(len(combined_df))]

    search_query = st.text_input("🔍 Tìm kiếm học sinh theo tên:")
    st.divider()

    if not combined_df.empty and search_query.strip():
        combined_df = combined_df[combined_df['Họ và Tên'].str.contains(search_query.strip(), case=False, na=False)]

    if combined_df.empty:
        st.info("ℹ️ Không tìm thấy dữ liệu thống kê phù hợp.")
    else:
        total_ca_all = combined_df['Số Ca Có Mặt'].sum()
        total_tien_all = combined_df['Tổng Tiền (VNĐ)'].sum()
        
        st.markdown("#### 📊 Tổng Hợp Thống Kê Chung")
        c_sum1, c_sum2 = st.columns(2)
        c_sum1.metric("📚 Tổng số ca học", f"{int(total_ca_all)} ca")
        c_sum2.metric("💰 Tổng tiền học phí", f"{total_tien_all:,.0f} đ")
        st.markdown("---")

        if HAS_MATPLOTLIB:
            if st.button("📦 Xuất ZIP Hàng Loạt Phiếu Thống Kê / Hóa Đơn", type="primary"):
                zip_buffer_f = io.BytesIO()
                with zipfile.ZipFile(zip_buffer_f, "w", zipfile.ZIP_DEFLATED) as zf_fee:
                    for _, row_fee in combined_df.iterrows():
                        img_fee_b = create_tuition_slip_image(
                            student_name=row_fee['Họ và Tên'],
                            lop_hoc=row_fee['Lớp'],
                            subject=row_fee['Môn Học'] or 'Chung',
                            price_per_lesson=row_fee['Đơn Giá/Ca (VNĐ)'],
                            month_year=row_fee['Thời gian'],
                            total_lessons=row_fee['Số Ca Có Mặt'],
                            total_fee=row_fee['Tổng Tiền (VNĐ)'],
                            status=row_fee['Trạng Thái'],
                            qr_path=qr_path,
                            is_multi=row_fee.get('is_multi', False),
                            details_list=row_fee.get('details', [])
                        )
                        safe_filename_time = str(row_fee['Thời gian']).replace('/', '_').replace(' - ', '_').replace(' ', '_')
                        safe_n_fee = re.sub(r'[\\/*?:"<>|]', "", f"{row_fee['Họ và Tên']}_{row_fee['Lớp']}_{safe_filename_time}".replace(" ", "_"))
                        zf_fee.writestr(f"Phieu_{safe_n_fee}.png", img_fee_b.getvalue())
                zip_buffer_f.seek(0)
                st.download_button(
                    label="📥 Bấm Tải Xuống File ZIP Hóa Đơn",
                    data=zip_buffer_f,
                    file_name=f"Tong_Hop_Thong_Ke_{datetime.now().strftime('%Y%m%d')}.zip",
                    mime="application/zip",
                    type="primary",
                    key="btn_download_zip_fee"
                )
            st.divider()

        for idx, row in combined_df.iterrows():
            c1, c2, c3, c4, c5, c6, c7 = st.columns([2.2, 1.2, 1.2, 1.2, 1.5, 1.8, 1.8])
            c1.write(f"**{row['Họ và Tên']}**\n\n*Lớp: {row['Lớp']} ({row['Thời gian']})*")
            c2.write(f"{row['Số Ca Có Mặt']} ca")
            c3.write(f"{row['Đơn Giá/Ca (VNĐ)']:,.0f} đ")
            c4.write(f"**{row['Tổng Tiền (VNĐ)']:,.0f} đ**")
            
            is_multi = row.get('is_multi', False)
            details_list = row.get('details', [])
            
            if is_multi:
                all_paid = all(d['trang_thai'] == 'Đã đóng' for d in details_list)
                c5.write("🟢 Đã đóng tất cả" if all_paid else ("🟡 Đóng một phần" if any(d['trang_thai'] == 'Đã đóng' for d in details_list) else "🔴 Chưa đóng"))
                btn_lbl = "Xác nhận Đã đóng tất cả" if not all_paid else "Chuyển Chưa đóng tất cả"
            else:
                is_paid = (row['Trạng Thái'] == 'Đã đóng')
                c5.write("🟢 Đã đóng" if is_paid else "🔴 Chưa đóng")
                btn_lbl = "Chuyển Chưa đóng" if is_paid else "Xác nhận Đã đóng"
                
            if c6.button(btn_lbl, key=f"btn_pay_{row['hoc_sinh_id']}_{idx}"):
                if is_multi:
                    new_stt = 'Chưa đóng' if all_paid else 'Đã đóng'
                    t_str = date.today().strftime("%Y-%m-%d") if new_stt == 'Đã đóng' else ""
                    with engine.begin() as conn:
                        for d in details_list:
                            conn.execute(text('''
                                INSERT INTO thanh_toan (hoc_sinh_id, thang_nam, trang_thai, ngay_thu)
                                VALUES (:hs_id, :thang, :stt, :ngay)
                                ON CONFLICT (hoc_sinh_id, thang_nam) 
                                DO UPDATE SET trang_thai = EXCLUDED.trang_thai, ngay_thu = EXCLUDED.ngay_thu
                            '''), {"hs_id": row['hoc_sinh_id'], "thang": d['thang_key'], "stt": new_stt, "ngay": t_str})
                else:
                    new_stt = 'Chưa đóng' if (row['Trạng Thái'] == 'Đã đóng') else 'Đã đóng'
                    t_str = date.today().strftime("%Y-%m-%d") if new_stt == 'Đã đóng' else ""
                    thang_nam_key_save = row['Thời gian'] if '/' in str(row['Thời gian']) and len(str(row['Thời gian'])) <= 7 else datetime.now().strftime("%m/%Y")
                    with engine.begin() as conn:
                        conn.execute(text('''
                            INSERT INTO thanh_toan (hoc_sinh_id, thang_nam, trang_thai, ngay_thu)
                            VALUES (:hs_id, :thang, :stt, :ngay)
                            ON CONFLICT (hoc_sinh_id, thang_nam) 
                            DO UPDATE SET trang_thai = EXCLUDED.trang_thai, ngay_thu = EXCLUDED.ngay_thu
                        '''), {"hs_id": row['hoc_sinh_id'], "thang": thang_nam_key_save, "stt": new_stt, "ngay": t_str})
                st.rerun()

            with c7:
                if HAS_MATPLOTLIB:
                    img_bytes = create_tuition_slip_image(
                        student_name=row['Họ và Tên'],
                        lop_hoc=row['Lớp'],
                        subject=row['Môn Học'] or 'Chung',
                        price_per_lesson=row['Đơn Giá/Ca (VNĐ)'],
                        month_year=row['Thời gian'],
                        total_lessons=row['Số Ca Có Mặt'],
                        total_fee=row['Tổng Tiền (VNĐ)'],
                        status=row['Trạng Thái'],
                        qr_path=qr_path,
                        is_multi=is_multi,
                        details_list=details_list
                    )
                    safe_filename_time = str(row['Thời gian']).replace('/', '_').replace(' - ', '_').replace(' ', '_')
                    st.download_button(
                        label="🖼️ Tải Ảnh Phiếu",
                        data=img_bytes,
                        file_name=f"Phieu_{row['Họ và Tên']}_{row['Lớp']}_{safe_filename_time}.png",
                        mime="application/png",
                        key=f"img_fee_{row['hoc_sinh_id']}_{idx}"
                    )
            st.divider()

# =========================================================
# --- CHỨC NĂNG 4: SỬA & XÓA DỮ LIỆU (QUẢN LÝ HỌC SINH) ---
# =========================================================
elif choice == "4. Sửa & Xóa dữ liệu":
    st.subheader("⚙️ Quản Lý Dữ Liệu Học Sinh")
    
    sub_tab_them, sub_tab_sua, sub_tab_xoa = st.tabs(["➕ Thêm Học Sinh", "✏️ Sửa Thông Tin", "❌ Xóa Học Sinh"])
    
    with sub_tab_them:
        with st.form("form_add_student_full"):
            c1, c2 = st.columns(2)
            with c1:
                ten_new = st.text_input("Họ và tên học sinh (*)")
                lop_new = st.text_input("Lớp / Nhóm học", value="Toán 9")
                mon_new = st.text_input("Môn học", value="Toán")
            with c2:
                hoc_phi_new = st.number_input("Học phí mỗi ca (VNĐ)", min_value=0, step=10000, value=150000)
                thong_tin_phu_huynh_new = st.text_input("Thông tin phụ huynh")
            
            if st.form_submit_button("💾 Thêm Học Sinh Mới", type="primary"):
                if ten_new.strip():
                    with engine.begin() as conn:
                        conn.execute(text('''
                            INSERT INTO hoc_sinh (ho_ten, lop_hoc, mon_hoc, hoc_phi_buoi, thong_tin_phu_huynh)
                            VALUES (:ten, :lop, :mon, :hp, :ttph)
                        '''), {"ten": ten_new.strip(), "lop": lop_new.strip(), "mon": mon_new.strip(), "hp": hoc_phi_new, "ttph": thong_tin_phu_huynh_new.strip()})
                    st.success(f"✅ Đã thêm học sinh **{ten_new}** thành công!")
                    st.rerun()

    with sub_tab_sua:
        df_hs_edit = pd.read_sql_query("SELECT * FROM hoc_sinh ORDER BY id DESC", engine)
        if not df_hs_edit.empty:
            hs_edit_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row for _, row in df_hs_edit.iterrows()}
            selected_edit_label = st.selectbox("Chọn học sinh cần sửa:", list(hs_edit_dict.keys()), key="select_edit_hs")
            selected_hs_row = hs_edit_dict[selected_edit_label]
            
            with st.form("form_edit_student"):
                c1, c2 = st.columns(2)
                with c1:
                    ten_edit = st.text_input("Họ và tên", value=selected_hs_row['ho_ten'])
                    lop_edit = st.text_input("Lớp", value=selected_hs_row['lop_hoc'] or "")
                    mon_edit = st.text_input("Môn", value=selected_hs_row['mon_hoc'] or "")
                with c2:
                    hoc_phi_edit = st.number_input("Học phí mỗi ca", min_value=0, step=10000, value=int(selected_hs_row['hoc_phi_buoi'] or 150000))
                    thong_tin_phu_huynh_edit = st.text_input("Thông tin phụ huynh", value=selected_hs_row['thong_tin_phu_huynh'] or "")
                
                if st.form_submit_button("💾 Lưu Thay Đổi", type="primary"):
                    with engine.begin() as conn:
                        conn.execute(text('''
                            UPDATE hoc_sinh 
                            SET ho_ten = :ten, lop_hoc = :lop, mon_hoc = :mon, hoc_phi_buoi = :hp, thong_tin_phu_huynh = :ttph
                            WHERE id = :id
                        '''), {"ten": ten_edit.strip(), "lop": lop_edit.strip(), "mon": mon_edit.strip(), "hp": hoc_phi_edit, "ttph": thong_tin_phu_huynh_edit.strip(), "id": int(selected_hs_row['id'])})
                    st.success("✅ Đã cập nhật!")
                    st.rerun()

    with sub_tab_xoa:
        df_hs_del = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh ORDER BY id DESC", engine)
        if not df_hs_del.empty:
            hs_del_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row['id'] for _, row in df_hs_del.iterrows()}
            selected_del_id = hs_del_dict[st.selectbox("Chọn học sinh cần xóa:", list(hs_del_dict.keys()), key="select_del_hs")]
            confirm_check = st.checkbox("Tôi xác nhận muốn xóa học sinh này")
            
            if st.button("❌ XÓA HỌC SINH NÀY", type="primary") and confirm_check:
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM diem_danh WHERE hoc_sinh_id = :id"), {"id": selected_del_id})
                    conn.execute(text("DELETE FROM thanh_toan WHERE hoc_sinh_id = :id"), {"id": selected_del_id})
                    conn.execute(text("DELETE FROM lich_hoc_tuan WHERE hoc_sinh_id = :id"), {"id": selected_del_id})
                    conn.execute(text("DELETE FROM lich_hoc_tam_thoi WHERE hoc_sinh_id = :id"), {"id": selected_del_id})
                    conn.execute(text("DELETE FROM hoc_sinh WHERE id = :id"), {"id": selected_del_id})
                st.success("✅ Đã xóa thành công!")
                st.rerun()

    st.markdown("### 📋 Danh Sách Học Sinh")
    st.dataframe(pd.read_sql_query("SELECT id AS \"Mã HS\", ho_ten AS \"Họ và tên\", lop_hoc AS \"Lớp\", mon_hoc AS \"Môn\", hoc_phi_buoi AS \"Học phí/Ca (VNĐ)\", thong_tin_phu_huynh AS \"Thông tin phụ huynh\" FROM hoc_sinh ORDER BY id DESC", engine), use_container_width=True)
