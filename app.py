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
            calendarId=calendar_id, timeMin=time_min, timeMax=time_max, singleEvents=True
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
                    'reminders': {'useDefault': False, 'overrides': [{'method': 'popup', 'minutes': 30}]},
                }
                service.events().insert(calendarId=calendar_id, body=event).execute()
                count_events += 1

        return True, f"✅ Đã đồng bộ thành công {count_events} ca dạy trong {days_ahead} ngày tới!"
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
        for cell in row:
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
    table.scale(1, max(3.2, max_lines_overall * 1.15))
    
    ax.text(0.5, 1.15, "THỜI KHÓA BIỂU LỊCH HỌC HÀNG TUẦN", transform=ax.transAxes, fontsize=17, fontweight='bold', color='#1E3A8A', ha='center', va='bottom')
    ax.text(0.5, 1.08, f"{prefix}{title_target}", transform=ax.transAxes, fontsize=14, fontweight='bold', color='#0F172A', ha='center', va='bottom')
    ax.text(0.5, 1.02, week_text, transform=ax.transAxes, fontsize=11.5, color='#475569', ha='center', va='bottom')
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
                cell.set_facecolor('#F8FAFC' if row % 2 == 0 else 'white')
                    
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig)
    buffer.seek(0)
    return buffer

# --- HÀM TẠO FILE ẢNH HÓA ĐƠN HỌC PHÍ (HỖ TRỢ 1 THÁNG HOẶC NHIỀU THÁNG) ---
def create_tuition_slip_image_multi(student_name, lop_hoc, subject, month_details, total_lessons, total_fee, status, qr_path):
    is_multi = len(month_details) > 1
    fig_height = 10 + (len(month_details) * 0.4 if is_multi else 0)
    fig, ax = plt.subplots(figsize=(8, fig_height))
    ax.axis('off')
    
    title_str = "PHIẾU BÁO HỌC PHÍ NHIỀU THÁNG" if is_multi else "PHIẾU BÁO HỌC PHÍ DẠY THÊM"
    time_str = f"Tổng hợp {len(month_details)} tháng" if is_multi else f"Thời gian: {month_details[0]['thang']}"
    
    ax.text(0.5, 0.95, title_str, fontsize=16, fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    ax.text(0.5, 0.91, time_str, fontsize=13, fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    
    y_pos = 0.84
    ax.text(0.1, y_pos, f"Họ và tên học sinh: {student_name}", fontsize=11.5, fontweight='bold', color='#1E293B', transform=ax.transAxes)
    y_pos -= 0.045
    ax.text(0.1, y_pos, f"Lớp / Nhóm học: {lop_hoc}", fontsize=11.5, fontweight='normal', color='#1E293B', transform=ax.transAxes)
    y_pos -= 0.045
    ax.text(0.1, y_pos, f"Môn học: {subject}", fontsize=11.5, fontweight='normal', color='#1E293B', transform=ax.transAxes)
    y_pos -= 0.055
    
    if is_multi:
        ax.text(0.1, y_pos, "Chi tiết học phí theo từng tháng:", fontsize=11.5, fontweight='bold', color='#1E3A8A', transform=ax.transAxes)
        y_pos -= 0.045
        for md in month_details:
            detail_line = f" • Tháng {md['thang']}: {md['so_ca']} ca x {md['don_gia']:,.0f} đ = {md['thanh_tien']:,.0f} VNĐ"
            ax.text(0.12, y_pos, detail_line, fontsize=10.5, fontweight='normal', color='#334155', transform=ax.transAxes)
            y_pos -= 0.04
        y_pos -= 0.02
    else:
        md = month_details[0]
        ax.text(0.1, y_pos, f"Học phí / ca: {md['don_gia']:,.0f} VNĐ", fontsize=11.5, transform=ax.transAxes)
        y_pos -= 0.045
        ax.text(0.1, y_pos, f"Tổng số ca học: {md['so_ca']} ca", fontsize=11.5, transform=ax.transAxes)
        y_pos -= 0.055
        
    ax.text(0.1, y_pos, f"TỔNG SỐ CA: {total_lessons} ca", fontsize=12, fontweight='bold', color='#1E3A8A', transform=ax.transAxes)
    y_pos -= 0.045
    ax.text(0.1, y_pos, f"TỔNG CỘNG HỌC PHÍ: {total_fee:,.0f} VNĐ", fontsize=13, fontweight='bold', color='#B91C1C', transform=ax.transAxes)
    y_pos -= 0.045
    ax.text(0.1, y_pos, f"Trạng thái thanh toán: {status}", fontsize=11.5, fontweight='bold', color='#1E293B', transform=ax.transAxes)
        
    if qr_path and os.path.exists(qr_path):
        try:
            img_arr = plt.imread(qr_path)
            ax_inset = fig.add_axes([0.35, 0.08, 0.3, 0.28])
            ax_inset.imshow(img_arr)
            ax_inset.axis('off')
            ax.text(0.5, 0.38, "Mã QR Thanh Toán Chuyển Khoản", fontsize=10.5, fontweight='bold', color='#1E3A8A', ha='center', transform=ax.transAxes)
        except Exception:
            pass
            
    ax.text(0.5, 0.02, "Trân trọng cảm ơn sự đồng hành của Quý phụ huynh!", fontsize=10.5, style='italic', fontweight='bold', color='#1E3A8A', ha='center', transform=ax.transAxes)
    
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
            cell.set_facecolor('#F8FAFC' if row % 2 == 0 else 'white')
                
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig)
    buffer.seek(0)
    return buffer

# --- 1. KHỞI TẠO BẢNG TRÊN SUPABASE (POSTGRESQL) & TỰ ĐỘNG BỔ SUNG CỘT ---
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
    "2. 🗺️ Quản Lý & Ma Trận Lịch Học",
    "3. 💳 Thống Kê Số Ca & Quản Lý Học Phí", 
    "4. Sửa & Xóa dữ liệu"
]
choice = st.sidebar.selectbox("📋 Danh mục chức năng", menu)

st.sidebar.markdown("---")
st.sidebar.subheader("📲 Đồng Bộ Lịch Sang iPhone")
user_gmail = st.sidebar.text_input("Địa chỉ Gmail trên iPhone:", value="a.luongxdnb@gmail.com")

if st.sidebar.button("🔄 Đồng Bộ Lịch 7 Ngày Tới Sang iPhone", type="primary"):
    success, msg = sync_weekly_schedule_to_google(calendar_id=user_gmail.strip() or 'primary', days_ahead=7)
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
    st.markdown("#### 🏫 Chi Tiết Lịch Dạy & Học Sinh Hôm Nay:")
    if df_today.empty:
        st.info("💡 Hôm nay không có ca dạy nào được lên lịch.")
    else:
        for ca in sorted(df_today['ca_hoc'].unique().tolist(), key=ca_hoc_sort_key):
            group_ca = df_today[df_today['ca_hoc'] == ca]
            with st.expander(f"⏰ Ca: {ca} ({len(group_ca)} học sinh)", expanded=True):
                for lop, g_lop in group_ca.groupby('lop_hoc'):
                    st.write(f"• **Lớp {lop}:** {', '.join(g_lop['ho_ten'].tolist())}")

# =========================================================
# --- CHỨC NĂNG 1: ĐIỂM DANH & NHẬN XÉT ---
# =========================================================
elif choice == "1. Điểm danh & Nhận xét":
    st.subheader("📝 Điểm Danh & Nhận Xét Buổi Học")
    ngay_hoc = st.date_input("🗓️ Chọn ngày điểm danh", date.today())
    date_str = ngay_hoc.strftime("%Y-%m-%d")
    st.caption(f"Ngày được chọn: **{ngay_hoc.strftime('%d/%m/%Y')} ({get_vietnamese_weekday(ngay_hoc)})**")
    
    df_active_today = get_active_schedule_for_date(engine, ngay_hoc)
    df_all_hs = pd.read_sql_query("SELECT id AS hoc_sinh_id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", engine)
    mo_rong_hs = st.checkbox("➕ Cho phép điểm danh cả học sinh KHÔNG CÓ LỊCH HỌC trong ngày (Học bù, phát sinh,...)", value=False)
    
    df_source = df_all_hs.copy() if mo_rong_hs and not df_all_hs.empty else df_active_today
    if mo_rong_hs and not df_source.empty:
        df_source['ca_hoc'] = "17h30 - 19h30"

    type_mode = st.radio("Chế độ điểm danh", ["🏫 Điểm danh theo LỚP", "👤 Điểm danh từng HỌC SINH"], horizontal=True)
    st.divider()

    if df_all_hs.empty:
        st.warning("⚠️ Chưa có học sinh nào trong hệ thống!")
    else:
        if type_mode == "🏫 Điểm danh theo LỚP":
            options_class = ["🌟 All Lớp (Tất cả học sinh)"] + sorted(df_all_hs['lop_hoc'].dropna().unique().tolist())
            selected_class_opt = st.selectbox("Chọn Lớp cần điểm danh", options_class)
            target_students = df_source if selected_class_opt.startswith("🌟 All Lớp") else df_source[df_source['lop_hoc'] == selected_class_opt]
        else:
            student_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['hoc_sinh_id']}": row['hoc_sinh_id'] for _, row in df_all_hs.iterrows()}
            options_hs = ["🌟 All Học sinh"] + list(student_dict.keys())
            selected_hs_opt = st.selectbox("Chọn học sinh điểm danh", options_hs)
            target_students = df_source if selected_hs_opt.startswith("🌟 All Học sinh") else df_source[df_source['hoc_sinh_id'] == student_dict[selected_hs_opt]]

        if target_students.empty:
            st.info("ℹ️ Không tìm thấy học sinh nào phù hợp trong danh sách.")
        else:
            with st.form("form_diem_danh_execution"):
                danh_sach_ca_mau_dd = DANH_SACH_CA_MAU + ["⏱️ Tự nhập giờ tùy chỉnh..."]
                danh_sach_luu = []

                for idx, row in target_students.iterrows():
                    st.markdown(f"**👤 {row['ho_ten']}** [{row.get('lop_hoc', 'N/A')}]")
                    c1, c2, c3 = st.columns([2, 2.5, 4.5])
                    default_ca = row.get('ca_hoc', '17h30 - 19h30')
                    if default_ca not in DANH_SACH_CA_MAU: default_ca = "17h30 - 19h30"

                    with c1:
                        ca_val = st.selectbox("Ca học", danh_sach_ca_mau_dd, index=DANH_SACH_CA_MAU.index(default_ca), key=f"ca_{row['hoc_sinh_id']}_{idx}")
                        ca_final = st.text_input("Nhập giờ", value="18h00 - 20h00", key=f"custom_{row['hoc_sinh_id']}_{idx}").strip() if ca_val == "⏱️ Tự nhập giờ tùy chỉnh..." else ca_val
                    with c2:
                        stt_val = st.radio("Trạng thái", ["Có mặt", "Vắng có phép", "Vắng không phép"], index=0, key=f"stt_{row['hoc_sinh_id']}_{idx}")
                    with c3:
                        selected_tags = st.multiselect("🏷️ Thẻ thái độ:", ["🌟 Chăm chú", "💪 Có tiến bộ", "⚠️ Quên bài tập", "💤 Buồn ngủ"], key=f"tags_{row['hoc_sinh_id']}_{idx}")
                        custom_nx = st.text_input("Ghi chú", key=f"nx_{row['hoc_sinh_id']}_{idx}", placeholder="Nhận xét...")
                        tag_str = " ".join([f"[{t}]" for t in selected_tags])
                        nx_val = f"{tag_str} - {custom_nx.strip()}" if tag_str and custom_nx.strip() else (tag_str or custom_nx.strip())

                    danh_sach_luu.append((row['hoc_sinh_id'], date_str, ca_final, stt_val, nx_val))
                    st.divider()

                if st.form_submit_button("💾 LƯU ĐIỂM DANH", type="primary", use_container_width=True):
                    with engine.begin() as conn:
                        for item in danh_sach_luu:
                            rec = conn.execute(text("SELECT id FROM diem_danh WHERE hoc_sinh_id = :h AND ngay = :n AND ca_hoc = :c"), {"h": item[0], "n": item[1], "c": item[2]}).fetchone()
                            if rec:
                                conn.execute(text("UPDATE diem_danh SET trang_thai = :stt, nhan_xet = :nx WHERE id = :id"), {"stt": item[3], "nx": item[4], "id": rec[0]})
                            else:
                                conn.execute(text("INSERT INTO diem_danh (hoc_sinh_id, ngay, ca_hoc, trang_thai, nhan_xet) VALUES (:h, :n, :c, :stt, :nx)"), {"h": item[0], "n": item[1], "c": item[2], "stt": item[3], "nx": item[4]})
                    st.success("✅ Đã lưu thành công điểm danh!")
                    st.rerun()

# =========================================================
# --- CHỨC NĂNG 2: QUẢN LÝ & MA TRẬN LỊCH HỌC ---
# =========================================================
elif choice == "2. 🗺️ Quản Lý & Ma Trận Lịch Học":
    st.subheader("🗺️ Trung Tâm Quản Lý Thời Khóa Biểu & Lịch Học")
    tab_matrix, tab_goc, tab_tam, tab_export = st.tabs(["🗺️ Ma Trận Tổng Quan", "📅 1. Lịch Gốc", "⏳ 2. Lịch Tạm Thời", "📥 Xuất Ảnh Lịch Học"])

    with tab_matrix:
        render_schedule_matrix(engine, ref_date=st.date_input("Xem tuần chứa ngày:", date.today()))

    with tab_goc:
        df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", engine)
        if not df_hs.empty:
            mode_goc = st.radio("Phạm vi:", ["Theo Lớp", "Theo Học Sinh"], horizontal=True)
            target_ids = df_hs[df_hs['lop_hoc'] == st.selectbox("Chọn Lớp", sorted(df_hs['lop_hoc'].dropna().unique()))]['id'].tolist() if mode_goc == "Theo Lớp" else [df_hs.set_index(df_hs.apply(lambda r: f"{r['ho_ten']} [{r['lop_hoc']}]", axis=1)).loc[st.selectbox("Chọn HS", df_hs.apply(lambda r: f"{r['ho_ten']} [{r['lop_hoc']}]", axis=1))]['id']]
            
            sched_save = {}
            for t in ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']:
                if st.checkbox(f"Có lịch học vào {t}", key=f"g_{t}"):
                    sched_save[t] = st.multiselect(f"Ca vào {t}:", DANH_SACH_CA_MAU, default=["17h30 - 19h30"] if t != "Chủ Nhật" else [], key=f"mc_{t}")
            
            if st.button("💾 Lưu Lịch Gốc", type="primary"):
                with engine.begin() as conn:
                    for h_id in target_ids:
                        conn.execute(text("DELETE FROM lich_hoc_tuan WHERE hoc_sinh_id = :id"), {"id": h_id})
                        for thu, cas in sched_save.items():
                            for c in cas:
                                conn.execute(text("INSERT INTO lich_hoc_tuan (hoc_sinh_id, thu, ca_hoc) VALUES (:h, :t, :c) ON CONFLICT DO NOTHING"), {"h": h_id, "t": thu, "c": c})
                st.success("✅ Đã lưu lịch gốc thành công!")
                st.rerun()

    with tab_tam:
        sub_t1, sub_t2 = st.tabs(["➕ Thêm lịch tạm thời", "📋 Danh sách & Quản lý"])
        with sub_t1:
            df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", engine)
            if not df_hs.empty:
                with st.form("form_tam"):
                    s_date = st.date_input("Từ ngày", date.today())
                    e_date = st.date_input("Đến ngày", date.today())
                    loai = st.selectbox("Loại", ["Đổi ca / Học bù", "Học thêm buổi", "Nghỉ tạm thời trong khoảng thời gian này"])
                    thu = st.selectbox("Thứ", ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật'])
                    cas = st.multiselect("Ca", DANH_SACH_CA_MAU, default=["17h30 - 19h30"])
                    if st.form_submit_button("Lưu lịch tạm thời", type="primary"):
                        with engine.begin() as conn:
                            for _, r in df_hs.iterrows():
                                for c in cas:
                                    conn.execute(text("INSERT INTO lich_hoc_tam_thoi (hoc_sinh_id, ngay_bat_dau, ngay_ket_thuc, thu, ca_hoc, loai_thay_doi) VALUES (:h, :s, :e, :t, :c, :l)"), {"h": r['id'], "s": s_date, "e": e_date, "t": thu, "c": c, "l": loai})
                        st.success("✅ Đã lưu!")
                        st.rerun()
        with sub_t2:
            df_t = pd.read_sql_query("SELECT t.id, h.ho_ten, t.ngay_bat_dau, t.ngay_ket_thuc, t.thu, t.ca_hoc, t.loai_thay_doi FROM lich_hoc_tam_thoi t JOIN hoc_sinh h ON t.hoc_sinh_id = h.id", engine)
            if not df_t.empty: st.dataframe(df_t, use_container_width=True)

    with tab_export:
        df_hs_all = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", engine)
        if not df_hs_all.empty:
            sel_d = st.date_input("Tuần xuất ảnh:", date.today(), key="exp_d")
            f_mode = st.radio("Phạm vi xuất:", ["Tất cả", "Theo Lớp", "Theo Học Sinh"], horizontal=True)
            t_title, l_sel, h_sel = ("Tất cả", None, None)
            if f_mode == "Theo Lớp":
                l_sel = st.selectbox("Chọn lớp:", sorted(df_hs_all['lop_hoc'].dropna().unique()))
                t_title = f"Lớp {l_sel}"
            elif f_mode == "Theo Học Sinh":
                h_dict = {f"{r['ho_ten']} [{r['lop_hoc']}]": r['id'] for _, r in df_hs_all.iterrows()}
                h_lbl = st.selectbox("Chọn HS:", list(h_dict.keys()))
                h_sel = h_dict[h_lbl]
                t_title = h_lbl

            df_mat = get_schedule_matrix_df(engine, filter_lop=l_sel, filter_hs_id=h_sel, ref_date=sel_d)
            if not df_mat.empty and HAS_MATPLOTLIB:
                st.download_button("🖼️ Tải Ảnh Lịch Học", create_weekly_schedule_image(t_title, df_mat, ref_date=sel_d), file_name="Lich_Hoc.png", mime="image/png", type="primary")

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
        with c_y: nam_sel = st.number_input("Năm", 2020, 2035, datetime.now().year)
        with c_m: sel_thangs = st.multiselect("Chọn Tháng:", list(range(1, 13)), default=[datetime.now().month], format_func=lambda x: f"Tháng {x}")

        if sel_thangs:
            # Truy vấn gom nhóm theo học sinh qua các tháng được chọn để tính tổng dồn
            thang_queries = [f"'{nam_sel}-{th:02d}'" for th in sel_thangs]
            thang_keys = [f"{th:02d}/{nam_sel}" for th in sel_thangs]
            
            q = f'''
                SELECT 
                    h.id AS hoc_sinh_id, 
                    h.ho_ten AS "Họ và Tên", 
                    h.lop_hoc AS "Lớp", 
                    h.mon_hoc AS "Môn Học", 
                    h.hoc_phi_buoi AS "Đơn Giá/Ca (VNĐ)",
                    SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS "Số Ca Có Mặt",
                    (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS "Tổng Tiền (VNĐ)"
                FROM hoc_sinh h
                LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND TO_CHAR(d.ngay, 'YYYY-MM') IN ({",".join(thang_queries)})
                GROUP BY h.id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi
            '''
            combined_df = pd.read_sql_query(q, engine)
            combined_df['Thời gian'] = ", ".join([f"Tháng {th}/{nam_sel}" for th in sel_thangs])

    elif che_do_xem == "Theo Ngày":
        ngay_chon = st.date_input("Chọn ngày:", date.today())
        q = f'''
            SELECT h.id AS hoc_sinh_id, h.ho_ten AS "Họ và Tên", h.lop_hoc AS "Lớp", h.mon_hoc AS "Môn Học", h.hoc_phi_buoi AS "Đơn Giá/Ca (VNĐ)",
                   SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS "Số Ca Có Mặt",
                   (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS "Tổng Tiền (VNĐ)",
                   '{ngay_chon.strftime("%d/%m/%Y")}' AS "Thời gian"
            FROM hoc_sinh h LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND d.ngay = '{ngay_chon.strftime("%Y-%m-%d")}'
            GROUP BY h.id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi
        '''
        combined_df = pd.read_sql_query(q, engine)
    else:
        tuan_chon = st.date_input("Chọn tuần:", date.today())
        start_w, end_w = tuan_chon - timedelta(days=tuan_chon.weekday()), tuan_chon - timedelta(days=tuan_chon.weekday()) + timedelta(days=6)
        q = f'''
            SELECT h.id AS hoc_sinh_id, h.ho_ten AS "Họ và Tên", h.lop_hoc AS "Lớp", h.mon_hoc AS "Môn Học", h.hoc_phi_buoi AS "Đơn Giá/Ca (VNĐ)",
                   SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS "Số Ca Có Mặt",
                   (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS "Tổng Tiền (VNĐ)",
                   'Tuần {start_w.strftime("%d/%m")} - {end_w.strftime("%d/%m")}' AS "Thời gian"
            FROM hoc_sinh h LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND d.ngay >= '{start_w}' AND d.ngay <= '{end_w}'
            GROUP BY h.id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi
        '''
        combined_df = pd.read_sql_query(q, engine)

    search_query = st.text_input("🔍 Tìm kiếm học sinh:")
    st.divider()

    if not combined_df.empty and search_query.strip():
        combined_df = combined_df[combined_df['Họ và Tên'].str.contains(search_query.strip(), case=False, na=False)]

    if combined_df.empty:
        st.info("ℹ️ Không tìm thấy dữ liệu thống kê.")
    else:
        st.metric("💰 Tổng tiền toàn bộ", f"{combined_df['Tổng Tiền (VNĐ)'].sum():,.0f} đ")
        st.divider()

        for idx, row in combined_df.iterrows():
            hs_id = row['hoc_sinh_id']
            
            # Lấy chi tiết từng tháng cho học sinh này nếu đang ở chế độ nhiều tháng
            month_details = []
            if che_do_xem == "Theo Tháng (Hỗ trợ chọn nhiều tháng)" and sel_thangs:
                for th in sel_thangs:
                    t_str = f"{nam_sel}-{th:02d}"
                    t_key = f"{th:02d}/{nam_sel}"
                    sub_q = f'''
                        SELECT COUNT(id) as sc FROM diem_danh 
                        WHERE hoc_sinh_id = {hs_id} AND TO_CHAR(ngay, 'YYYY-MM') = '{t_str}' AND trang_thai = 'Có mặt'
                    ''']
                    sc_res = pd.read_sql_query(sub_q, engine)
                    sc_val = int(sc_res.iloc[0]['sc']) if not sc_res.empty else 0
                    don_gia = row['Đơn Giá/Ca (VNĐ)']
                    month_details.append({
                        'thang': t_key,
                        'so_ca': sc_val,
                        'don_gia': don_gia,
                        'thanh_tien': sc_val * don_gia
                    })
            else:
                month_details.append({
                    'thang': row['Thời gian'],
                    'so_ca': int(row['Số Ca Có Mặt']),
                    'don_gia': row['Đơn Giá/Ca (VNĐ)'],
                    'thanh_tien': row['Tổng Tiền (VNĐ)']
                })

            c1, c2, c3, c4, c5 = st.columns([2.5, 1.2, 1.5, 1.8, 1.8])
            c1.write(f"**{row['Họ와 Tên']}**\n\n*Lớp: {row['Lớp']}*")
            c2.write(f"{int(row['Số Ca Có Mặt'])} ca")
            c3.write(f"**{row['Tổng Tiền (VNĐ)']:,.0f} đ**")
            
            if c4.button("🖼️ Tải Hóa Đơn Ảnh", key=f"img_{hs_id}_{idx}"):
                if HAS_MATPLOTLIB:
                    img_b = create_tuition_slip_image_multi(
                        student_name=row['Họ và Tên'],
                        lop_hoc=row['Lớp'],
                        subject=row['Môn Học'] or 'Chung',
                        month_details=month_details,
                        total_lessons=int(row['Số Ca Có Mặt']),
                        total_fee=row['Tổng Tiền (VNĐ)'],
                        status="Đã tổng hợp",
                        qr_path=qr_path
                    )
                    st.download_button(
                        label=f"📥 Tải Về Ngay",
                        data=img_b,
                        file_name=f"Hoa_Don_{row['Họ và Tên'].replace(' ', '_')}.png",
                        mime="image/png",
                        key=f"dl_{hs_id}_{idx}"
                    )
            st.divider()

# =========================================================
# --- CHỨC NĂNG 4: SỬA & XÓA DỮ LIỆU ---
# =========================================================
elif choice == "4. Sửa & Xóa dữ liệu":
    st.subheader("⚙️ Quản Lý Dữ Liệu Học Sinh & Điểm Danh")
    tab_hs, tab_diemdanh = st.tabs(["👤 Quản lý Học sinh", "🗓️ Quản lý Nhật ký Điểm danh"])
    
    with tab_hs:
        sub_t_add, sub_t_edit, sub_t_del = st.tabs(["➕ Thêm", "✏️ Sửa", "❌ Xóa"])
        with sub_t_add:
            with st.form("f_add_hs"):
                ten = st.text_input("Họ tên (*)")
                lop = st.text_input("Lớp", value="Toán 9")
                mon = st.text_input("Môn", value="Toán")
                hp = st.number_input("Học phí/ca", min_value=0, value=150000, step=10000)
                if st.form_submit_button("Thêm học sinh", type="primary") and ten.strip():
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO hoc_sinh (ho_ten, lop_hoc, mon_hoc, hoc_phi_buoi) VALUES (:t, :l, :m, :hp)"), {"t": ten.strip(), "l": lop.strip(), "m": mon.strip(), "hp": hp})
                    st.success("✅ Đã thêm học sinh thành công!")
                    st.rerun()
        with sub_t_edit:
            df_edit = pd.read_sql_query("SELECT * FROM hoc_sinh", engine)
            if not df_edit.empty:
                h_dict = {f"{r['ho_ten']} [{r['lop_hoc']}]": r for _, r in df_edit.iterrows()}
                sel_h = h_dict[st.selectbox("Chọn học sinh cần sửa:", list(h_dict.keys()))]
                with st.form("f_edit_hs"):
                    e_ten = st.text_input("Họ tên", value=sel_h['ho_ten'])
                    e_lop = st.text_input("Lớp", value=sel_h['lop_hoc'])
                    e_hp = st.number_input("Học phí", value=int(sel_h['hoc_phi_buoi']))
                    if st.form_submit_button("Lưu thay đổi", type="primary"):
                        with engine.begin() as conn:
                            conn.execute(text("UPDATE hoc_sinh SET ho_ten = :t, lop_hoc = :l, hoc_phi_buoi = :hp WHERE id = :id"), {"t": e_ten, "l": e_lop, "hp": e_hp, "id": sel_h['id']})
                        st.success("✅ Đã cập nhật!")
                        st.rerun()
        with sub_t_del:
            df_del = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", engine)
            if not df_del.empty:
                d_dict = {f"{r['ho_ten']} [{r['lop_hoc']}]": r['id'] for _, r in df_del.iterrows()}
                d_id = d_dict[st.selectbox("Chọn học sinh cần xóa:", list(d_dict.keys()))]
                if st.button("❌ Xóa học sinh này", type="primary") and st.checkbox("Xác nhận xóa"):
                    with engine.begin() as conn:
                        for tbl in ["diem_danh", "thanh_toan", "lich_hoc_tuan", "lich_hoc_tam_thoi", "hoc_sinh"]:
                            conn.execute(text(f"DELETE FROM {tbl} WHERE {'hoc_sinh_id' if tbl != 'hoc_sinh' else 'id'} = :id"), {"id": d_id})
                    st.success("✅ Đã xóa!")
                    st.rerun()
        st.dataframe(pd.read_sql_query("SELECT id AS \"Mã HS\", ho_ten AS \"Họ tên\", lop_hoc AS \"Lớp\", mon_hoc AS \"Môn\", hoc_phi_buoi AS \"Học phí/ca\" FROM hoc_sinh", engine), use_container_width=True)

    with tab_diemdanh:
        sel_d_log = st.date_input("Chọn ngày xem/sửa điểm danh:", date.today())
        df_l = pd.read_sql_query(f"SELECT d.id, h.ho_ten, h.lop_hoc, d.ca_hoc, d.trang_thai, d.nhan_xet FROM diem_danh d JOIN hoc_sinh h ON d.hoc_sinh_id = h.id WHERE d.ngay = '{sel_d_log}'", engine)
        if not df_l.empty:
            st.dataframe(df_l, use_container_width=True)
            log_dict = {f"ID {r['id']}: {r['ho_ten']} ({r['ca_hoc']})": r['id'] for _, r in df_l.iterrows()}
            sel_l_id = log_dict[st.selectbox("Chọn bản ghi điểm danh cần xóa:", list(log_dict.keys()))]
            if st.button("❌ Xóa bản ghi điểm danh này", type="primary"):
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM diem_danh WHERE id = :id"), {"id": sel_l_id})
                st.success("✅ Đã xóa!")
                st.rerun()
        else:
            st.info("Không có dữ liệu điểm danh trong ngày này.")
