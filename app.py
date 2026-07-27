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

# --- HÀM LẤY CHUỖI KẾT NỐI TỪ SECRETS (TỰ ĐỘNG CHUẨN HÓA CÚ PHÁP) ---
def get_clean_db_url():
    url = st.secrets.get("DATABASE_URL", None)
    if not url and "postgres" in st.secrets:
        pg_sec = st.secrets["postgres"]
        if isinstance(pg_sec, dict):
            url = pg_sec.get("url", None)
        elif isinstance(pg_sec, str):
            url = pg_sec

    if not url:
        return None

    url = str(url).replace("\n", "").replace("\r", "").replace(" ", "").strip()

    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    if "sslmode" not in url:
        url += "?sslmode=require" if "?" not in url else "&sslmode=require"

    return url

# --- KẾT NỐI CƠ SỞ DỮ LIỆU ---
@st.cache_resource
def get_db_engine():
    db_url = get_clean_db_url()
    if db_url:
        return create_engine(
            db_url,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={"connect_timeout": 15}
        )
    else:
        return create_engine("sqlite:///quan_ly_hoc_sinh.db")

engine = get_db_engine()

# --- TỰ ĐỘNG KHỞI TẠO CẤU TRÚC BẢNG TRÊN SUPABASE / SQLITE NẾU CHƯA CÓ ---
def init_db():
    db_url = get_clean_db_url()
    is_postgres = db_url is not None
    pk_type = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    
    with engine.begin() as conn:
        # Bảng cơ bản
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS hoc_sinh (
                id {pk_type},
                ho_ten VARCHAR(255) NOT NULL,
                lop_hoc VARCHAR(100),
                mon_hoc VARCHAR(100),
                hoc_phi_buoi NUMERIC DEFAULT 150000,
                sdt_phu_huynh VARCHAR(50),
                ngay_sinh DATE
            );
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS diem_danh (
                id {pk_type},
                hoc_sinh_id INT,
                ngay DATE,
                ca_hoc VARCHAR(50),
                trang_thai VARCHAR(50),
                nhan_xet TEXT
            );
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS lich_hoc_tuan (
                id {pk_type},
                hoc_sinh_id INT,
                thu VARCHAR(20),
                ca_hoc VARCHAR(50)
            );
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS lich_hoc_tam_thoi (
                id {pk_type},
                hoc_sinh_id INT,
                ngay_bat_dau DATE,
                ngay_ket_thuc DATE,
                thu VARCHAR(20),
                ca_hoc VARCHAR(50),
                loai_thay_doi VARCHAR(100)
            );
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS thanh_toan (
                id {pk_type},
                hoc_sinh_id INT,
                thang_nam VARCHAR(20),
                trang_thai VARCHAR(50),
                ngay_thu VARCHAR(20),
                CONSTRAINT unique_hs_thang UNIQUE(hoc_sinh_id, thang_nam)
            );
        """))
        
        # Bảng tính năng mới 1: Điểm kiểm tra
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS diem_kiem_tra (
                id {pk_type},
                hoc_sinh_id INT,
                ngay_kt DATE,
                ten_bai VARCHAR(255),
                diem NUMERIC,
                ghi_chu TEXT
            );
        """))
        
        # Bảng tính năng mới 2: Bài giảng & Bài tập về nhà
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS bai_giang_btvn (
                id {pk_type},
                lop_hoc VARCHAR(100),
                ngay DATE,
                noi_dung_bai TEXT,
                btvn TEXT,
                link_tai_lieu TEXT
            );
        """))
        
        # Bảng tính năng mới 3: Thu chi khác
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS thu_chi (
                id {pk_type},
                ngay DATE,
                loai VARCHAR(20),
                hang_muc VARCHAR(100),
                so_tien NUMERIC,
                ghi_chu TEXT
            );
        """))

        # Thêm cột bổ sung cho hoc_sinh nếu nâng cấp từ bản cũ
        try:
            conn.execute(text("ALTER TABLE hoc_sinh ADD COLUMN sdt_phu_huynh VARCHAR(50);"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE hoc_sinh ADD COLUMN ngay_sinh DATE;"))
        except Exception:
            pass

try:
    init_db()
except Exception:
    pass

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

    query_temp = text("""
        SELECT t.hoc_sinh_id, h.ho_ten, h.lop_hoc, h.mon_hoc, t.thu, t.ca_hoc, t.loai_thay_doi
        FROM lich_hoc_tam_thoi t
        JOIN hoc_sinh h ON t.hoc_sinh_id = h.id
        WHERE t.ngay_bat_dau <= :d_str AND t.ngay_ket_thuc >= :d_str
    """)
    df_temp = pd.read_sql_query(query_temp, engine, params={"d_str": date_str})
    temp_hs_ids = df_temp['hoc_sinh_id'].unique() if not df_temp.empty else []

    query_base = text("""
        SELECT l.hoc_sinh_id, h.ho_ten, h.lop_hoc, h.mon_hoc, l.ca_hoc
        FROM lich_hoc_tuan l
        JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
        WHERE l.thu = :thu
    """)
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

def render_schedule_matrix():
    query_mindmap = text("""
        SELECT l.thu, l.ca_hoc, h.lop_hoc, h.mon_hoc, h.ho_ten
        FROM lich_hoc_tuan l
        JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
        ORDER BY 
            CASE l.thu
                WHEN 'Thứ 2' THEN 1 WHEN 'Thứ 3' THEN 2 WHEN 'Thứ 4' THEN 3
                WHEN 'Thứ 5' THEN 4 WHEN 'Thứ 6' THEN 5 WHEN 'Thứ 7' THEN 6 WHEN 'Chủ Nhật' THEN 7
            END, l.ca_hoc, h.lop_hoc
    """)
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
    "1. 📝 Điểm danh & Nhận xét", 
    "2. 🗺️ Ma Trận Lịch Học & Mindmap",
    "3. 📅 Lên Lịch Học (Gốc & Tạm Thời)",
    "4. 📈 Sổ Điểm & Tiến Độ Học Tập",
    "5. 📖 Bài Giảng & Bài Tập Về Nhà",
    "6. 💰 Quản Lý Thu - Chi & Tài Chính",
    "7. 📲 Zalo 1-Click & Tra Cứu Phụ Huynh",
    "8. 💡 Gợi Ý & Cảnh Báo Thông Minh",
    "9. 📊 Thống Kê Học Phí theo Tháng", 
    "10. 💳 Quản Lý & Xác Nhận Học Phí", 
    "11. ⚙️ Sửa & Xóa Dữ Liệu (Học Sinh)"
]
choice = st.sidebar.selectbox("📋 Danh mục chức năng", menu)

# --- CHỨC NĂNG 1: ĐIỂM DANH & NHẬN XÉT ---
if choice == "1. 📝 Điểm danh & Nhận xét":
    st.subheader("📝 Điểm Danh & Nhận Xét Buổi Học")
    ngay_hoc = st.date_input("🗓️ Chọn ngày điểm danh", date.today())
    thu_hom_nay = get_vietnamese_weekday(ngay_hoc)
    st.caption(f"Ngày được chọn: **{ngay_hoc.strftime('%d/%m/%Y')} ({thu_hom_nay})**")
    
    df_active_today = get_active_schedule_for_date(ngay_hoc)
    type_mode = st.radio("Chế độ điểm danh", ["🏫 Điểm danh theo LỚP", "👤 Điểm danh từng HỌC SINH"], horizontal=True)
    st.divider()
    
    if type_mode.startswith("🏫"):
        sub_mode_class = st.radio("Tùy chọn danh sách Lớp:", ["🏫 Lớp có lịch hôm nay", "📚 Tất cả các lớp"], horizontal=True)
        df_all_hs = pd.read_sql_query("SELECT id AS hoc_sinh_id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", engine)
        
        if df_all_hs.empty:
            st.warning("⚠️ Chưa có học sinh nào! Hãy sang mục '11. Sửa & Xóa Dữ Liệu' để thêm học sinh.")
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
        df_all_hs = pd.read_sql_query("SELECT id AS hoc_sinh_id, ho_ten, lop_hoc FROM hoc_sinh", engine)
        if not df_all_hs.empty:
            student_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['hoc_sinh_id']}": row['hoc_sinh_id'] for _, row in df_all_hs.iterrows()}
            selected_label = st.selectbox("Chọn học sinh", list(student_dict.keys()))
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
elif choice == "2. 🗺️ Ma Trận Lịch Học & Mindmap":
    st.subheader("🗺️ Thời Khóa Biểu Tuần & Sơ Đồ Mindmap")
    render_schedule_matrix()

# --- CHỨC NĂNG 3: LÊN LỊCH HỌC ---
elif choice == "3. 📅 Lên Lịch Học (Gốc & Tạm Thời)":
    tab_goc, tab_tam = st.tabs(["📅 1. Lịch Học Gốc Hàng Tuần", "⏳ 2. Lịch Học Tạm Thời"])
    
    with tab_goc:
        st.subheader("📅 Xếp Lịch Học Cố Định Hàng Tuần (Lịch Gốc)")
        df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", engine)
        if not df_hs.empty:
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
                            conn.execute(text("""
                                INSERT INTO lich_hoc_tam_thoi (hoc_sinh_id, ngay_bat_dau, ngay_ket_thuc, thu, ca_hoc, loai_thay_doi)
                                VALUES (:hs_id, :st, :et, :thu, :ca, :loai)
                            """), {"hs_id": int(hs_id_item), "st": d_start.strftime("%Y-%m-%d"), "et": d_end.strftime("%Y-%m-%d"), "thu": thu_tam, "ca": ca_tam, "loai": loai_td})
                    st.success("✅ Đã lưu lịch tạm thời!")
                    st.rerun()

# --- CHỨC NĂNG 4: SỔ ĐIỂM & TIẾN ĐỘ HỌC TẬP ---
elif choice == "4. 📈 Sổ Điểm & Tiến Độ Học Tập":
    st.subheader("📈 Sổ Điểm Kiểm Tra & Biểu Đồ Tiến Bộ")
    df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", engine)
    
    if df_hs.empty:
        st.warning("⚠️ Chưa có học sinh nào trong hệ thống.")
    else:
        tab_nhap_diem, tab_xem_diem = st.tabs(["📝 Nhập Điểm Kiểm Tra", "📊 Xem Sổ Điểm & Biểu Đồ Progress"])
        
        with tab_nhap_diem:
            student_dict = {f"{row['ho_ten']} [{row['lop_hoc']}]": row['id'] for _, row in df_hs.iterrows()}
            selected_student_label = st.selectbox("Chọn học sinh nhập điểm", list(student_dict.keys()))
            selected_hs_id = student_dict[selected_student_label]
            
            with st.form("form_nhap_diem"):
                c1, c2 = st.columns(2)
                with c1:
                    ten_bai_kt = st.text_input("Tên bài kiểm tra", placeholder="VD: Kiểm tra 15p Bài 1, Thi giữa kỳ...")
                    diem_kt = st.number_input("Điểm số (Thang điểm 10)", min_value=0.0, max_value=10.0, value=8.0, step=0.5)
                with c2:
                    ngay_kt = st.date_input("Ngày kiểm tra", date.today())
                    ghi_chu_diem = st.text_input("Ghi chú", placeholder="Làm bài cẩn thận, sai câu trắc nghiệm...")
                
                if st.form_submit_button("💾 Lưu Điểm Kiểm Tra", type="primary"):
                    with engine.begin() as conn:
                        conn.execute(text("""
                            INSERT INTO diem_kiem_tra (hoc_sinh_id, ngay_kt, ten_bai, diem, ghi_chu)
                            VALUES (:hs_id, :ngay, :ten, :diem, :gc)
                        """), {"hs_id": int(selected_hs_id), "ngay": ngay_kt.strftime("%Y-%m-%d"), "ten": ten_bai_kt, "diem": diem_kt, "gc": ghi_chu_diem})
                    st.success(f"✅ Đã lưu điểm {diem_kt} cho bài '{ten_bai_kt}'!")
                    st.rerun()

        with tab_xem_diem:
            selected_hs_id_view = student_dict[st.selectbox("Chọn học sinh xem tiến độ", list(student_dict.keys()), key="select_view_progress")]
            query_diem = text("""
                SELECT ngay_kt AS "Ngày KT", ten_bai AS "Tên Bài", diem AS "Điểm Số", ghi_chu AS "Ghi Chú"
                FROM diem_kiem_tra
                WHERE hoc_sinh_id = :hs_id
                ORDER BY ngay_kt ASC
            """)
            df_diem = pd.read_sql_query(query_diem, engine, params={"hs_id": int(selected_hs_id_view)})
            
            if df_diem.empty:
                st.info("💡 Học sinh này chưa có cột điểm nào.")
            else:
                col_left, col_right = st.columns([1, 1])
                with col_left:
                    st.write("#### 📋 Bảng Điểm")
                    st.dataframe(df_diem, use_container_width=True)
                    avg_score = df_diem["Điểm Số"].mean()
                    st.metric("Điểm Trung Bình", f"{avg_score:.2f} / 10")
                    
                    # Gợi ý nhận xét tự động từ AI
                    if avg_score >= 8.0:
                        st.success("🤖 **Đánh giá AI:** Học sinh nắm chắc kiến thức, tư duy tốt. Nên tiếp tục cho làm bài nâng cao.")
                    elif avg_score >= 6.5:
                        st.info("🤖 **Đánh giá AI:** Khá tốt, tuy nhiên còn hổng một số dạng bài nhỏ. Cần rèn thêm kỹ năng tính toán.")
                    else:
                        st.warning("🤖 **Đánh giá AI:** Kiến thức chưa vững. Cần chú ý củng cố bài tập cơ bản & kiểm tra lại BTVN.")
                        
                with col_right:
                    st.write("#### 📉 Biểu Đồ Tiến Bộ")
                    chart_data = df_diem.set_index("Ngày KT")["Điểm Số"]
                    st.line_chart(chart_data)

# --- CHỨC NĂNG 5: BÀI GIẢNG & BÀI TẬP VỀ NHÀ ---
elif choice == "5. 📖 Bài Giảng & Bài Tập Về Nhà":
    st.subheader("📖 Quản Lý Bài Giảng & Bài Tập Về Nhà (BTVN)")
    df_hs = pd.read_sql_query("SELECT DISTINCT lop_hoc FROM hoc_sinh", engine)
    
    if df_hs.empty:
        st.warning("⚠️ Chưa có lớp học nào.")
    else:
        all_lops = df_hs['lop_hoc'].tolist()
        sel_lop = st.selectbox("Chọn Lớp Học", all_lops)
        
        tab_giao_bai, tab_nhat_ky = st.tabs(["✍️ Ghi Nhật Ký / Giao BTVN", "📚 Nhật Ký Tiến Độ Lớp"])
        
        with tab_giao_bai:
            with st.form("form_bai_giang"):
                c1, c2 = st.columns(2)
                with c1:
                    ngay_bg = st.date_input("Ngày học", date.today())
                    noi_dung_bg = st.text_area("Nội dung bài giảng đã dạy", placeholder="Chương 2 - Bài 3: Phương trình bậc hai...", height=100)
                with c2:
                    btvn_text = st.text_area("Bài tập về nhà (BTVN)", placeholder="Làm bài 1, 2, 3 Trang 45 SGK...", height=100)
                    link_tl = st.text_input("Link File Tài Liệu / Đề Thi (Drive / PDF)", placeholder="https://drive.google.com/...")
                    
                if st.form_submit_button("💾 Lưu Nhật Ký Bài Giảng", type="primary"):
                    with engine.begin() as conn:
                        conn.execute(text("""
                            INSERT INTO bai_giang_btvn (lop_hoc, ngay, noi_dung_bai, btvn, link_tai_lieu)
                            VALUES (:lop, :ngay, :nd, :btvn, :link)
                        """), {"lop": sel_lop, "ngay": ngay_bg.strftime("%Y-%m-%d"), "nd": noi_dung_bg, "btvn": btvn_text, "link": link_tl})
                    st.success(f"✅ Đã ghi nhận nhật ký lớp {sel_lop}!")
                    st.rerun()

        with tab_nhat_ky:
            query_bg = text("""
                SELECT ngay AS "Ngày", noi_dung_bai AS "Nội Dung Bài Dạy", btvn AS "BTVN Giao", link_tai_lieu AS "Link Tài Liệu"
                FROM bai_giang_btvn
                WHERE lop_hoc = :lop
                ORDER BY ngay DESC
            """)
            df_bg = pd.read_sql_query(query_bg, engine, params={"lop": sel_lop})
            if df_bg.empty:
                st.info(f"💡 Chưa có nhật ký bài giảng nào cho Lớp {sel_lop}.")
            else:
                st.dataframe(df_bg, use_container_width=True)

# --- CHỨC NĂNG 6: QUẢN LÝ THU - CHI & TÀI CHÍNH ---
elif choice == "6. 💰 Quản Lý Thu - Chi & Tài Chính":
    st.subheader("💰 Quản Lý Thu Chi Nội Bộ (Điện nước, In ấn, Trợ giảng...)")
    
    tab_chi, tab_so_quy = st.tabs(["➕ Ghi Khoản Thu / Chi", "📊 Sổ Quỹ & Báo Cáo Tài Chính"])
    
    with tab_chi:
        with st.form("form_thu_chi"):
            c1, c2, c3 = st.columns(3)
            with c1:
                loai_tc = st.selectbox("Loại giao dịch", ["🔴 Chi phí (Đi ra)", "🟢 Thu khác (Đi vào)"])
                ngay_tc = st.date_input("Ngày giao dịch", date.today())
            with c2:
                hang_muc = st.selectbox("Hạng mục", ["In ấn & Tài liệu", "Tiền điện / Nước", "Mua dụng cụ / Phấn / Bút", "Lương trợ giảng", "Thưởng / Quà học sinh", "Khác"])
                so_tien = st.number_input("Số tiền (VNĐ)", min_value=0, step=10000, value=50000)
            with c3:
                ghi_chu_tc = st.text_input("Ghi chú chi tiết", placeholder="Photo đê thi giữa kỳ...")
                
            if st.form_submit_button("💾 Lưu Giao Dịch", type="primary"):
                loai_val = "Chi" if "Chi" in loai_tc else "Thu"
                with engine.begin() as conn:
                    conn.execute(text("""
                        INSERT INTO thu_chi (ngay, loai, hang_muc, so_tien, ghi_chu)
                        VALUES (:ngay, :loai, :hm, :st, :gc)
                    """), {"ngay": ngay_tc.strftime("%Y-%m-%d"), "loai": loai_val, "hm": hang_muc, "st": so_tien, "gc": ghi_chu_tc})
                st.success("✅ Đã ghi nhận giao dịch thành công!")
                st.rerun()

    with tab_so_quy:
        query_tc = text("SELECT ngay AS 'Ngày', loai AS 'Loại', hang_muc AS 'Hạng Mục', so_tien AS 'Số Tiền (VNĐ)', ghi_chu AS 'Ghi Chú' FROM thu_chi ORDER BY ngay DESC")
        df_tc = pd.read_sql_query(query_tc, engine)
        
        if df_tc.empty:
            st.info("💡 Chưa có dữ liệu thu chi khác.")
        else:
            tong_chi = df_tc[df_tc["Loại"] == "Chi"]["Số Tiền (VNĐ)"].sum()
            tong_thu_khac = df_tc[df_tc["Loại"] == "Thu"]["Số Tiền (VNĐ)"].sum()
            
            c1, c2 = st.columns(2)
            c1.metric("🔴 Tổng Chi Phí Lớp Học", f"{tong_chi:,.0f} VNĐ")
            c2.metric("🟢 Tổng Thu Khác", f"{tong_thu_khac:,.0f} VNĐ")
            
            st.dataframe(df_tc, use_container_width=True)

# --- CHỨC NĂNG 7: ZALO 1-CLICK & TRA CỨU PHỤ HUYNH ---
elif choice == "7. 📲 Zalo 1-Click & Tra Cứu Phụ Huynh":
    st.subheader("📲 Gửi Báo Cáo Zalo 1-Click & Tra Cứu Phụ Huynh")
    
    tab_zalo, tab_lookup = st.tabs(["💬 Gửi Báo Cáo Zalo 1-Click", "🔍 Tra Cứu Thông Tin Học Sinh"])
    
    df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc, mon_hoc, sdt_phu_huynh, hoc_phi_buoi FROM hoc_sinh", engine)
    
    with tab_zalo:
        if df_hs.empty:
            st.warning("⚠️ Chưa có học sinh.")
        else:
            student_dict = {f"{row['ho_ten']} [{row['lop_hoc']}]": row for _, row in df_hs.iterrows()}
            sel_label = st.selectbox("Chọn học sinh cần gửi tin", list(student_dict.keys()))
            hs_info = student_dict[sel_label]
            
            thang_bc = st.selectbox("Chọn tháng báo cáo", list(range(1, 13)), index=datetime.now().month - 1)
            nam_bc = datetime.now().year
            thang_nam_query = f"{nam_bc}-{thang_bc:02d}"
            
            # Tính số buổi & học phí
            query_check = text("""
                SELECT COUNT(*) FROM diem_danh 
                WHERE hoc_sinh_id = :id AND trang_thai = 'Có mặt' 
                AND to_char(ngay, 'YYYY-MM') = :ym
            """) if "postgres" in st.secrets else text("""
                SELECT COUNT(*) FROM diem_danh 
                WHERE hoc_sinh_id = :id AND trang_thai = 'Có mặt' 
                AND strftime('%Y-%m', ngay) = :ym
            """)
            
            try:
                so_buoi = pd.read_sql_query(query_check, engine, params={"id": int(hs_info['id']), "ym": thang_nam_query}).iloc[0, 0]
            except Exception:
                so_buoi = 0
                
            tong_hp = so_buoi * hs_info['hoc_phi_buoi']
            sdt_clean = str(hs_info['sdt_phu_huynh']).strip() if hs_info['sdt_phu_huynh'] else ""
            
            # Mẫu tin nhắn soạn sẵn
            msg_template = f"""Kính gửi Phụ huynh em {hs_info['ho_ten']} (Lớp {hs_info['lop_hoc']}),
Kính gửi báo cáo tình hình học tập Tháng {thang_bc}/{nam_bc}:
- Số buổi cháu tham gia học: {so_buoi} buổi.
- Tổng học phí tháng {thang_bc}: {tong_hp:,.0f} VNĐ.

Rất mong Quý Phụ huynh phối hợp nhắc nhở cháu làm BTVN đầy đủ. Trân trọng cảm ơn!"""
            
            st.text_area("📝 Nội dung tin nhắn tự động tạo:", value=msg_template, height=160)
            
            if sdt_clean:
                # Link Zalo chat 1-Click
                zalo_link = f"https://zalo.me/{sdt_clean}"
                st.markdown(f'<a href="{zalo_link}" target="_blank"><button style="background-color: #0068FF; color: white; padding: 10px 20px; border: none; border-radius: 5px; font-weight: bold; cursor: pointer;">📲 Bấm để Mở Zalo Chat Với Phụ Huynh ({sdt_clean})</button></a>', unsafe_allow_html=True)
            else:
                st.warning("⚠️ Học sinh này chưa được cập nhật Số điện thoại phụ huynh. Hãy cập nhật tại mục '11. Sửa & Xóa Dữ Liệu'.")

    with tab_lookup:
        if not df_hs.empty:
            sel_hs_lk = st.selectbox("Chọn học sinh cần tra cứu", list(student_dict.keys()), key="select_lookup")
            hs_lk = student_dict[sel_hs_lk]
            
            st.markdown(f"### 👤 Báo Cáo Tổng Hợp: **{hs_lk['ho_ten']}**")
            c1, c2, c3 = st.columns(3)
            c1.info(f"**Lớp:** {hs_lk['lop_hoc']}")
            c2.info(f"**Môn học:** {hs_lk['mon_hoc']}")
            c3.info(f"**SĐT PH:** {hs_lk['sdt_phu_huynh'] or 'Chưa có'}")
            
            # Lịch sử điểm danh gần đây
            st.write("#### 🗓️ Lịch Sử Điểm Danh 10 Buổi Gần Nhất")
            df_dd = pd.read_sql_query(text("SELECT ngay AS 'Ngày', ca_hoc AS 'Ca', trang_thai AS 'Trạng Thái', nhan_xet AS 'Nhận Xét' FROM diem_danh WHERE hoc_sinh_id = :id ORDER BY ngay DESC LIMIT 10"), engine, params={"id": int(hs_lk['id'])})
            st.dataframe(df_dd, use_container_width=True)

# --- CHỨC NĂNG 8: GỢI Ý & CẢNH BÁO THÔNG MINH ---
elif choice == "8. 💡 Gợi Ý & Cảnh Báo Thông Minh":
    st.subheader("💡 Trợ Lý Cảnh Báo Thông Minh (Smart Assistant)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🚨 Cảnh Báo Học Sinh Vắng > 1 Buổi Tháng Này")
        query_vang = text("""
            SELECT h.ho_ten AS "Họ Tên", h.lop_hoc AS "Lớp", COUNT(*) AS "Số Buổi Vắng"
            FROM diem_danh d
            JOIN hoc_sinh h ON d.hoc_sinh_id = h.id
            WHERE d.trang_thai LIKE '%Vắng%'
            GROUP BY h.ho_ten, h.lop_hoc
            HAVING COUNT(*) >= 2
        """)
        try:
            df_vang = pd.read_sql_query(query_vang, engine)
            if df_vang.empty:
                st.success("🎉 Tất cả học sinh đều đi học rất chuyên cần!")
            else:
                st.warning("⚠️ Danh sách các em nghỉ nhiều cần nhắc nhở:")
                st.dataframe(df_vang, use_container_width=True)
        except Exception:
            st.info("Chưa có dữ liệu vắng.")

    with col2:
        st.markdown("#### 🎂 Sinh Nhật Học Sinh Trong Tháng")
        thang_curr = datetime.now().month
        query_sn = text("""
            SELECT ho_ten AS "Họ Tên", lop_hoc AS "Lớp", ngay_sinh AS "Ngày Sinh"
            FROM hoc_sinh
            WHERE ngay_sinh IS NOT NULL
        """)
        try:
            df_sn = pd.read_sql_query(query_sn, engine)
            if not df_sn.empty:
                df_sn['Ngày Sinh'] = pd.to_datetime(df_sn['Ngày Sinh'])
                df_sn_thang = df_sn[df_sn['Ngày Sinh'].dt.month == thang_curr]
                if not df_sn_thang.empty:
                    st.balloons()
                    st.success(f"🎉 Có {len(df_sn_thang)} học sinh sinh nhật trong Tháng {thang_curr}:")
                    st.dataframe(df_sn_thang[['Họ Tên', 'Lớp', 'Ngày Sinh']], use_container_width=True)
                else:
                    st.info(f"Không có học sinh nào sinh nhật trong Tháng {thang_curr}.")
            else:
                st.info("Chưa cập nhật ngày sinh học sinh.")
        except Exception:
            st.info("Chưa cập nhật dữ liệu ngày sinh.")

# --- CHỨC NĂNG 9: THỐNG KÊ & XUẤT EXCEL ---
elif choice == "9. 📊 Thống Kê Học Phí theo Tháng":
    st.subheader("📊 Thống Kê Điểm Danh & Tính Học Phí Theo Tháng")
    col_t, col_n = st.columns(2)
    with col_t: thang_selected = st.selectbox("Chọn Tháng", list(range(1, 13)), index=datetime.now().month - 1)
    with col_n: nam_selected = st.number_input("Chọn Năm", min_value=2020, max_value=2035, value=datetime.now().year)
    
    thang_nam_query = f"{nam_selected}-{thang_selected:02d}"
    db_url_check = get_clean_db_url()
    is_postgres = db_url_check is not None
    date_format_func = "to_char(d.ngay, 'YYYY-MM')" if is_postgres else "strftime('%Y-%m', d.ngay)"
    
    query_thang = f"""
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
    """
    df_thong_ke = pd.read_sql_query(text(query_thang), engine, params={"ym": thang_nam_query})
    st.dataframe(df_thong_ke, use_container_width=True)

# --- CHỨC NĂNG 10: QUẢN LÝ & XÁC NHẬN HỌC PHÍ ---
elif choice == "10. 💳 Quản Lý & Xác Nhận Học Phí":
    st.subheader("💳 Đánh Dấu Trạng Thái Đóng Học Phí Theo Tháng")
    thang = st.selectbox("Chọn Tháng", list(range(1, 13)), index=datetime.now().month - 1)
    nam = st.number_input("Chọn Năm", min_value=2020, max_value=2035, value=datetime.now().year)
    
    thang_nam_key = f"{thang:02d}/{nam}"
    thang_nam_query = f"{nam}-{thang:02d}"
    db_url_check = get_clean_db_url()
    is_postgres = db_url_check is not None
    date_format_func = "to_char(d.ngay, 'YYYY-MM')" if is_postgres else "strftime('%Y-%m', d.ngay)"
    
    query_status = f"""
        SELECT 
            h.id AS hoc_sinh_id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi,
            SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) AS so_buoi,
            (SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) * h.hoc_phi_buoi) AS tong_tien,
            COALESCE(t.trang_thai, 'Chưa đóng') AS trang_thai_dong
        FROM hoc_sinh h
        LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND {date_format_func} = :ym
        LEFT JOIN thanh_toan t ON h.id = t.hoc_sinh_id AND t.thang_nam = :tn
        GROUP BY h.id, h.ho_ten, h.lop_hoc, h.mon_hoc, h.hoc_phi_buoi, t.trang_thai
    """
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
                conn.execute(text("""
                    INSERT INTO thanh_toan (hoc_sinh_id, thang_nam, trang_thai, ngay_thu)
                    VALUES (:hs_id, :tn, :st, :nt)
                    ON CONFLICT(hoc_sinh_id, thang_nam) 
                    DO UPDATE SET trang_thai = EXCLUDED.trang_thai, ngay_thu = EXCLUDED.ngay_thu
                """), {"hs_id": int(row['hoc_sinh_id']), "tn": thang_nam_key, "st": new_status, "nt": today_str})
            st.rerun()

# --- CHỨC NĂNG 11: SỬA & XÓA DỮ LIỆU HỌC SINH ---
elif choice == "11. ⚙️ Sửa & Xóa Dữ Liệu (Học Sinh)":
    st.subheader("➕ Thêm Học Sinh Mới & Cập Nhật SĐT")
    with st.form("add_student"):
        c1, c2 = st.columns(2)
        with c1:
            ten = st.text_input("Họ và tên học sinh")
            lop = st.text_input("Lớp / Nhóm học", value="Toán 9")
            mon = st.text_input("Môn học", value="Toán")
        with c2:
            hoc_phi = st.number_input("Học phí mỗi buổi (VNĐ)", min_value=0, step=10000, value=150000)
            sdt = st.text_input("SĐT Phụ huynh (dùng để nhắn Zalo)", placeholder="0912345678...")
            ns = st.date_input("Ngày sinh học sinh", value=date(2010, 1, 1))
        
        if st.form_submit_button("💾 Thêm Học Sinh Mới", type="primary"):
            if ten:
                with engine.begin() as conn:
                    conn.execute(
                        text("INSERT INTO hoc_sinh (ho_ten, lop_hoc, mon_hoc, hoc_phi_buoi, sdt_phu_huynh, ngay_sinh) VALUES (:ten, :lop, :mon, :hp, :sdt, :ns)"),
                        {"ten": ten, "lop": lop, "mon": mon, "hp": hoc_phi, "sdt": sdt, "ns": ns.strftime("%Y-%m-%d")}
                    )
                st.success(f"✅ Đã thêm học sinh {ten}!")
                st.rerun()
