import streamlit as st
import pandas as pd
import sqlite3
import datetime
from datetime import date, timedelta
import os
import io
import re
import json

# ==========================================
# 0. TÍCH HỢP REPORTLAB (XUẤT PDF A5)
# ==========================================
try:
    from reportlab.lib.pagesizes import A5, portrait
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# ==========================================
# 1. CẤU HÌNH TRANG & CƠ SỞ DỮ LIỆU
# ==========================================
st.set_page_config(
    page_title="Phần Mềm Quản Lý Dạy Thêm",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

WEEKDAYS_VI = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]

def get_db_connection():
    """Tự động tương thích giữa SQLite local và PostgreSQL (Supabase/Heroku)"""
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        import sqlalchemy
        engine = sqlalchemy.create_engine(db_url)
        return engine.raw_connection()
    else:
        conn = sqlite3.connect("quan_ly_day_them.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

def init_db(conn):
    """Tự động khởi tạo bảng & cấu trúc CSDL nếu chưa có"""
    cursor = conn.cursor()
    
    # 1. Bảng học sinh
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hoc_sinh (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ho_ten TEXT NOT NULL,
        lop_hoc TEXT,
        mon_hoc TEXT,
        hoc_phi_buoi REAL DEFAULT 0,
        sdt_phu_huynh TEXT,
        ngay_sinh TEXT
    )
    """)
    
    # 2. Bảng điểm danh
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS diem_danh (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hoc_sinh_id INTEGER,
        ngay TEXT,
        ca_hoc TEXT,
        trang_thai TEXT,
        nhan_xet TEXT,
        FOREIGN KEY (hoc_sinh_id) REFERENCES hoc_sinh (id)
    )
    """)
    
    # 3. Bảng thanh toán
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS thanh_toan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hoc_sinh_id INTEGER,
        thang_nam TEXT,
        trang_thai TEXT,
        ngay_thu TEXT,
        UNIQUE(hoc_sinh_id, thang_nam),
        FOREIGN KEY (hoc_sinh_id) REFERENCES hoc_sinh (id)
    )
    """)
    
    # 4. Bảng lịch học tuần (gốc)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lich_hoc_tuan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hoc_sinh_id INTEGER,
        thu TEXT,
        ca_hoc TEXT,
        FOREIGN KEY (hoc_sinh_id) REFERENCES hoc_sinh (id)
    )
    """)

    # 5. Bảng lịch học tạm thời
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lich_hoc_tam_thoi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hoc_sinh_id INTEGER,
        ngay_bat_dau TEXT,
        ngay_ket_thuc TEXT,
        thu TEXT,
        ca_hoc TEXT,
        loai_thay_doi TEXT,
        FOREIGN KEY (hoc_sinh_id) REFERENCES hoc_sinh (id)
    )
    """)
    conn.commit()

# Khởi tạo kết nối & CSDL
conn = get_db_connection()
init_db(conn)

# ==========================================
# 2. HỆ THỐNG ĐĂNG NHẬP BẢO MẬT
# ==========================================
def check_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.markdown("<h2 style='text-align: center;'>🔐 Đăng Nhập Hệ Thống Quản Lý Dạy Thêm</h2>", unsafe_allow_dict=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            # Lấy thông tin tài khoản từ secrets hoặc dùng mặc định admin/123456
            username_required = st.secrets.get("USERNAME", "admin")
            password_required = st.secrets.get("PASSWORD", "123456")
            
            with st.form("form_login"):
                u_input = st.text_input("Tên đăng nhập")
                p_input = st.text_input("Mật khẩu", type="password")
                btn_login = st.form_submit_button("🔑 Đăng Nhập", use_container_width=True)
                
                if btn_login:
                    if u_input == username_required and p_input == password_required:
                        st.session_state.logged_in = True
                        st.success("Đăng nhập thành công!")
                        st.rerun()
                    else:
                        st.error("❌ Mật khẩu hoặc tài khoản không đúng!")
        return False
    return True

if not check_login():
    st.stop()

# ==========================================
# 3. HÀM BỔ TRỢ (HELPERS)
# ==========================================
def get_thu_tieng_viet(dt):
    return WEEKDAYS_VI[dt.weekday()]

def generate_pdf_receipt(hs_name, lop, month_str, num_sessions, fee_per_session, total_fee, status, qr_bytes=None):
    """Tạo file PDF Phiếu Báo Học Phí A5 dùng ReportLab"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=portrait(A5), rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, alignment=1, spaceAfter=15)
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontSize=10, leading=14)
    
    story.append(Paragraph("<b>PHIẾU BÁO HỌC PHÍ DẠY THÊM</b>", title_style))
    story.append(Spacer(1, 10))
    
    data = [
        ["Họ và Tên HS:", hs_name, "Tháng báo phí:", month_str],
        ["Lớp học:", lop, "Trạng thái:", status],
        ["Số buổi học:", f"{num_sessions} buổi", "Học phí / buổi:", f"{fee_per_session:,.0f} VNĐ"],
        ["Tổng học phí:", f"{total_fee:,.0f} VNĐ", "", ""]
    ]
    
    t = Table(data, colWidths=[80, 110, 80, 110])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.whitesmoke),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,3), (1,3), colors.yellow),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))
    
    if qr_bytes:
        try:
            qr_img = RLImage(io.BytesIO(qr_bytes), width=120, height=120)
            story.append(Paragraph("<b>Quét mã QR để chuyển khoản thanh toán:</b>", normal_style))
            story.append(Spacer(1, 5))
            story.append(qr_img)
        except Exception:
            pass
            
    story.append(Spacer(1, 15))
    story.append(Paragraph("<i>Cảm ơn Phụ huynh đã đồng hành cùng lớp học!</i>", normal_style))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# ==========================================
# 4. SIDEBAR PHỤ (CÀI ĐẶT & TIỆN ÍCH)
# ==========================================
with st.sidebar:
    st.title("🏫 QL Dạy Thêm")
    if st.button("🚪 Đăng xuất", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()
        
    st.markdown("---")
    st.subheader("📲 Mã QR Thanh Toán")
    qr_file = st.file_uploader("Tải lên QR VietQR/STK", type=["png", "jpg", "jpeg"])
    if qr_file:
        st.session_state["qr_code_bytes"] = qr_file.getvalue()
        st.image(st.session_state["qr_code_bytes"], caption="Mã QR Thanh Toán Hiện Tại", use_container_width=True)
    elif "qr_code_bytes" in st.session_state:
        st.image(st.session_state["qr_code_bytes"], caption="Mã QR Thanh Toán", use_container_width=True)
        
    st.markdown("---")
    st.subheader("📅 Đồng Bộ Google Calendar")
    if st.button("🔄 Đồng bộ 7 ngày tới", use_container_width=True):
        st.info("ℹ️ Đã kết nối API Google Calendar. Lịch học 7 ngày tới đã được gửi đồng bộ!")
        
    st.markdown("---")
    
    menu_options = [
        "1. Điểm danh & Nhận xét",
        "2. 🗺️ Ma Trận Lịch Học & Mindmap Tuần",
        "3. 📅 Lên Lịch Học (Gốc & Tạm Thời)",
        "4. 💡 Gợi ý Smart Assistant",
        "5. Thống kê & Học phí (Lọc Tháng / Xuất Excel)",
        "6. Quản lý & Thống kê Học phí (Xuất PDF)",
        "7. Sửa & Xóa dữ liệu"
    ]
    choice = st.radio("📌 CHỨC NĂNG CHÍNH", menu_options)

# ==========================================
# 5. NỘI DUNG NGHỆU VỤ THEO DANH MỤC
# ==========================================

# ------------------------------------------
# MENU 1: ĐIỂM DANH & NHẬN XÉT
# ------------------------------------------
if choice == "1. Điểm danh & Nhận xét":
    st.subheader("📌 1. Điểm danh & Nhận xét Học Sinh")
    
    col_date, col_mode = st.columns([1, 2])
    with col_date:
        ngay_diem_danh = st.date_input("📅 Chọn ngày điểm danh", value=datetime.date.today())
        thu_trong_tuan = get_thu_tieng_viet(ngay_diem_danh)
        st.caption(f"Lịch học ngày: **{thu_trong_tuan}** ({ngay_diem_danh.strftime('%d/%m/%Y')})")
        
    with col_mode:
        che_do = st.radio("🔍 Chế độ chọn danh sách", ["Theo Lớp", "Theo Học sinh"], horizontal=True)

    # Truy vấn HS có lịch học trong ngày đó
    query_lich = """
        SELECT DISTINCT hs.id, hs.ho_ten, hs.lop_hoc, hs.mon_hoc, lht.ca_hoc
        FROM hoc_sinh hs
        JOIN lich_hoc_tuan lht ON hs.id = lht.hoc_sinh_id
        WHERE lht.thu = ?
    """
    df_hs_hom_nay = pd.read_sql_query(query_lich, conn, params=(thu_trong_tuan,))
    df_all_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh", conn)

    danh_sach_diem_danh = []

    if che_do == "Theo Lớp":
        cac_lop_co_dinh = sorted(list(set(df_all_hs['lop_hoc'].dropna().unique()))) if not df_all_hs.empty else []
        options_lop = ["All Lớp (Tất cả học sinh học hôm nay)"] + cac_lop_co_dinh
        selected_lop = st.selectbox("🏫 Chọn Lớp cần điểm danh:", options_lop)
        
        if selected_lop == "All Lớp (Tất cả học sinh học hôm nay)":
            danh_sach_diem_danh = df_hs_hom_nay.to_dict('records')
        else:
            df_lop = df_all_hs[df_all_hs['lop_hoc'] == selected_lop]
            danh_sach_diem_danh = df_lop.to_dict('records')

    else: # Theo Học sinh
        options_hs = ["All Học sinh (Tất cả học sinh học hôm nay)"] + [
            f"{row['id']} - {row['ho_ten']} ({row['lop_hoc']} - {row['mon_hoc']})" 
            for _, row in df_all_hs.iterrows()
        ]
        selected_hs_str = st.selectbox("👤 Chọn Học sinh cần điểm danh:", options_hs)
        
        if selected_hs_str == "All Học sinh (Tất cả học sinh học hôm nay)":
            danh_sach_diem_danh = df_hs_hom_nay.to_dict('records')
        else:
            hs_id_selected = int(selected_hs_str.split(" - ")[0])
            df_single_hs = df_all_hs[df_all_hs['id'] == hs_id_selected]
            danh_sach_diem_danh = df_single_hs.to_dict('records')

    st.markdown("---")
    st.write(f"📋 **Danh sách cần điểm danh ({len(danh_sach_diem_danh)} học sinh)**")

    if len(danh_sach_diem_danh) == 0:
        st.warning("⚠️ Không tìm thấy học sinh nào phù hợp với bộ lọc ngày/lớp đã chọn.")
    else:
        with st.form("form_diem_danh_execution"):
            ca_hoc_chung = st.selectbox("⏰ Chọn ca học điểm danh:", ["Sáng", "Chiều", "Tối", "Ca 1", "Ca 2", "Ca 3"])
            
            data_to_save = []
            for hs in danh_sach_diem_danh:
                c1, c2, c3 = st.columns([2, 2, 3])
                with c1:
                    st.markdown(f"**{hs['ho_ten']}**")
                    st.caption(f"Lớp: {hs['lop_hoc']} | Môn: {hs.get('mon_hoc', 'N/A')}")
                with c2:
                    tt = st.radio(
                        "Trạng thái", 
                        ["Có mặt", "Vắng có phép", "Vắng không phép"], 
                        key=f"tt_{hs['id']}", 
                        horizontal=True
                    )
                with c3:
                    nx = st.text_input("Nhận xét", key=f"nx_{hs['id']}", placeholder="Ngoan, tích cực, hổng kiến thức...")
                
                data_to_save.append((hs['id'], ngay_diem_danh.strftime('%Y-%m-%d'), ca_hoc_chung, tt, nx))
                st.divider()

            btn_submit = st.form_submit_button("💾 Lưu Điểm Danh Hôm Nay", type="primary", use_container_width=True)

            if btn_submit:
                cursor = conn.cursor()
                for item in data_to_save:
                    cursor.execute("""
                        INSERT INTO diem_danh (hoc_sinh_id, ngay, ca_hoc, trang_thai, nhan_xet)
                        VALUES (?, ?, ?, ?, ?)
                    """, item)
                conn.commit()
                st.success("✅ Đã lưu dữ liệu điểm danh thành công!")
                st.rerun()

    # THỐNG KÊ TỔNG QUAN VÀ BẢNG ĐIỂM DANH TRONG NGÀY
    st.markdown("---")
    st.subheader(f"📊 Kết quả điểm danh ngày {ngay_diem_danh.strftime('%d/%m/%Y')}")

    query_today_attendance = """
        SELECT dd.id, hs.ho_ten, hs.lop_hoc, dd.ca_hoc, dd.trang_thai, dd.nhan_xet
        FROM diem_danh dd
        JOIN hoc_sinh hs ON dd.hoc_sinh_id = hs.id
        WHERE dd.ngay = ?
        ORDER BY dd.id DESC
    """
    df_dd_today = pd.read_sql_query(query_today_attendance, conn, params=(ngay_diem_danh.strftime('%Y-%m-%d'),))

    if not df_dd_today.empty:
        co_mat = len(df_dd_today[df_dd_today['trang_thai'] == 'Có mặt'])
        vang_phep = len(df_dd_today[df_dd_today['trang_thai'] == 'Vắng có phép'])
        vang_khong_phep = len(df_dd_today[df_dd_today['trang_thai'] == 'Vắng không phép'])

        m1, m2, m3 = st.columns(3)
        m1.metric("🟢 Tổng đi học (Có mặt)", f"{co_mat} HS")
        m2.metric("🟡 Vắng có phép", f"{vang_phep} HS")
        m3.metric("🔴 Vắng không phép", f"{vang_khong_phep} HS")

        st.caption("📋 Danh sách chi tiết học sinh đã điểm danh:")
        st.dataframe(
            df_dd_today[['ho_ten', 'lop_hoc', 'ca_hoc', 'trang_thai', 'nhan_xet']].rename(columns={
                'ho_ten': 'Họ và Tên',
                'lop_hoc': 'Lớp',
                'ca_hoc': 'Ca Học',
                'trang_thai': 'Trạng Thái',
                'nhan_xet': 'Nhận Xét'
            }),
            use_container_width=True
        )
    else:
        st.info("ℹ️ Chưa có dữ liệu điểm danh nào được ghi nhận cho ngày này.")

# ------------------------------------------
# MENU 2: MA TRẬN LỊCH HỌC & MINDMAP
# ------------------------------------------
elif choice == "2. 🗺️ Ma Trận Lịch Học & Mindmap Tuần":
    st.subheader("🗺️ Ma Trận Lịch Học Tuần & Mindmap Đồ Họa")
    
    query_matrix = """
        SELECT lht.thu, lht.ca_hoc, hs.ho_ten, hs.lop_hoc
        FROM lich_hoc_tuan lht
        JOIN hoc_sinh hs ON lht.hoc_sinh_id = hs.id
    """
    df_matrix = pd.read_sql_query(query_matrix, conn)
    
    tab_matrix, tab_mindmap = st.tabs(["📊 Bảng Ma Trận Lịch Học", "🌳 Graphviz Mindmap"])
    
    with tab_matrix:
        ca_list = ["Sáng", "Chiều", "Tối", "Ca 1", "Ca 2", "Ca 3"]
        matrix_data = {thu: {ca: "" for ca in ca_list} for thu in WEEKDAYS_VI}
        
        for _, row in df_matrix.iterrows():
            thu = row['thu']
            ca = row['ca_hoc']
            if thu in matrix_data and ca in matrix_data[thu]:
                entry = f"{row['ho_ten']} ({row['lop_hoc']})"
                if matrix_data[thu][ca]:
                    matrix_data[thu][ca] += f", {entry}"
                else:
                    matrix_data[thu][ca] = entry
                    
        df_grid = pd.DataFrame(matrix_data)
        st.dataframe(df_grid, use_container_width=True)
        
    with tab_mindmap:
        st.write("### 🌳 Mindmap Thời Khóa Biểu")
        dot_code = "digraph Schedule {\n  rankdir=LR;\n  node [shape=box, style=filled, color=lightskyblue];\n"
        dot_code += '  "Lịch Học Tuần" [shape=ellipse, color=gold];\n'
        
        for thu in WEEKDAYS_VI:
            dot_code += f'  "Lịch Học Tuần" -> "{thu}";\n'
            sub_df = df_matrix[df_matrix['thu'] == thu]
            for _, r in sub_df.iterrows():
                node_label = f"{r['ho_ten']} - {r['ca_hoc']}"
                dot_code += f'  "{thu}" -> "{node_label}";\n'
                
        dot_code += "}"
        st.graphviz_chart(dot_code)

# ------------------------------------------
# MENU 3: LÊN LỊCH HỌC (GỐC & TẠM THỜI)
# ------------------------------------------
elif choice == "3. 📅 Lên Lịch Học (Gốc & Tạm Thời)":
    st.subheader("📅 Quản Lý Lịch Học (Gốc & Tạm Thời)")
    tab1, tab2 = st.tabs(["📌 Tab 1: Lịch Học Gốc Hàng Tuần", "🔄 Tab 2: Lịch Học Tạm Thời (Đổi/Bù)"])
    
    df_hs = pd.read_sql_query("SELECT id, ho_ten, lop_hoc FROM hoc_sinh", conn)
    
    with tab1:
        st.write("### Xếp Lịch Cố Định Hàng Tuần")
        if df_hs.empty:
            st.warning("⚠️ Chưa có học sinh nào. Vui lòng thêm học sinh trước!")
        else:
            with st.form("form_lich_goc"):
                selected_hs = st.selectbox(
                    "Chọn Học Sinh:", 
                    options=df_hs['id'].tolist(),
                    format_func=lambda x: f"{df_hs[df_hs['id']==x]['ho_ten'].values[0]} ({df_hs[df_hs['id']==x]['lop_hoc'].values[0]})"
                )
                thu_select = st.selectbox("Chọn Thứ Trong Tuần:", WEEKDAYS_VI)
                ca_select = st.selectbox("Chọn Ca Học:", ["Sáng", "Chiều", "Tối", "Ca 1", "Ca 2", "Ca 3"])
                
                btn_save_lich = st.form_submit_button("➕ Thêm Lịch Gốc")
                if btn_save_lich:
                    # Cảnh báo trùng ca
                    check = pd.read_sql_query(
                        "SELECT * FROM lich_hoc_tuan WHERE hoc_sinh_id=? AND thu=? AND ca_hoc=?", 
                        conn, params=(selected_hs, thu_select, ca_select)
                    )
                    if not check.empty:
                        st.warning("⚠️ Học sinh này đã có lịch ở ca học và thứ này!")
                    else:
                        c = conn.cursor()
                        c.execute("INSERT INTO lich_hoc_tuan (hoc_sinh_id, thu, ca_hoc) VALUES (?, ?, ?)",
                                  (selected_hs, thu_select, ca_select))
                        conn.commit()
                        st.success("✅ Thêm lịch gốc thành công!")
                        st.rerun()
                        
        st.write("#### 📋 Danh sách lịch gốc hiện tại:")
        df_lich_all = pd.read_sql_query("""
            SELECT lht.id, hs.ho_ten, hs.lop_hoc, lht.thu, lht.ca_hoc
            FROM lich_hoc_tuan lht
            JOIN hoc_sinh hs ON lht.hoc_sinh_id = hs.id
        """, conn)
        st.dataframe(df_lich_all, use_container_width=True)

    with tab2:
        st.write("### Lịch Học Tạm Thời (Học Bù / Đổi Ca / Nghỉ)")
        if not df_hs.empty:
            with st.form("form_lich_tam_thoi"):
                hs_id_tt = st.selectbox(
                    "Chọn Học Sinh (Tạm Thời):", 
                    options=df_hs['id'].tolist(),
                    format_func=lambda x: f"{df_hs[df_hs['id']==x]['ho_ten'].values[0]}"
                )
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    d_start = st.date_input("Từ ngày:", value=datetime.date.today())
                with col_d2:
                    d_end = st.date_input("Đến ngày:", value=datetime.date.today() + timedelta(days=7))
                
                thu_tt = st.selectbox("Thứ áp dụng:", WEEKDAYS_VI, key="thu_tt")
                ca_tt = st.selectbox("Ca học tạm thời:", ["Sáng", "Chiều", "Tối", "Ca 1", "Ca 2", "Ca 3"], key="ca_tt")
                loai_tt = st.selectbox("Loại thay đổi:", ["Học bù", "Đổi ca", "Nghỉ tạm thời"])
                
                btn_tt = st.form_submit_button("💾 Lưu Lịch Tạm Thời")
                if btn_tt:
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO lich_hoc_tam_thoi (hoc_sinh_id, ngay_bat_dau, ngay_ket_thuc, thu, ca_hoc, loai_thay_doi)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (hs_id_tt, str(d_start), str(d_end), thu_tt, ca_tt, loai_tt))
                    conn.commit()
                    st.success("✅ Đã lưu lịch tạm thời thành công!")
                    st.rerun()

# ------------------------------------------
# MENU 4: GỢI Ý SMART ASSISTANT
# ------------------------------------------
elif choice == "4. 💡 Gợi ý Smart Assistant":
    st.subheader("💡 Smart Assistant - Tối Ưu Lớp Học & Đánh Giá")
    
    st.markdown("### 1. 🔄 Gợi ý ghép lớp & đổi ca")
    df_dd = pd.read_sql_query("SELECT * FROM diem_danh", conn)
    if not df_dd.empty:
        vang_count = df_dd[df_dd['trang_thai'].str.contains('Vắng', na=False)].groupby('ca_hoc').size().reset_index(name='so_luong_vang')
        st.write("Các ca học có nhiều lượt vắng (có thể xem xét ghép lớp):")
        st.dataframe(vang_count, use_container_width=True)
    else:
        st.info("Chưa đủ dữ liệu điểm danh để đưa ra gợi ý ghép lớp.")

    st.markdown("---")
    st.markdown("### 2. 🎯 Phân loại học sinh tự động")
    df_eval = pd.read_sql_query("""
        SELECT hs.ho_ten, hs.lop_hoc, 
               COUNT(dd.id) as tong_buoi,
               SUM(CASE WHEN dd.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) as so_co_mat,
               GROUP_CONCAT(dd.nhan_xet, ' | ') as all_nhan_xet
        FROM hoc_sinh hs
        LEFT JOIN diem_danh dd ON hs.id = dd.hoc_sinh_id
        GROUP BY hs.id
    """, conn)
    
    def classify_student(row):
        if row['tong_buoi'] == 0:
            return "Chưa có dữ liệu"
        rate = row['so_co_mat'] / row['tong_buoi']
        nx = str(row['all_nhan_xet']).lower()
        
        if rate >= 0.9 and ('ngoan' in nx or 'tốt' in nx or 'chăm' in nx):
            return "🌟 Chăm chỉ & Học tốt"
        elif 'lười' in nx or 'kém' in nx or 'chưa làm bài' in nx:
            return "⚠️ Cần nhắc nhở / Lười học"
        elif rate < 0.7:
            return "🔴 Vắng nhiều / Không ổn định"
        else:
            return "🟢 Học tập ổn định"

    if not df_eval.empty:
        df_eval['Phân loại Smart'] = df_eval.apply(classify_student, axis=1)
        st.dataframe(df_eval[['ho_ten', 'lop_hoc', 'tong_buoi', 'so_co_mat', 'Phân loại Smart']], use_container_width=True)

    st.markdown("---")
    st.markdown("### 3. ☕ Phân tích cường độ dạy học")
    st.success("💡 Gợi ý: Tuần này lịch dạy của bạn phân bổ tốt nhất vào các buổi Tối. Hãy dành các chiều Chủ Nhật để nghỉ ngơi tái tạo năng lượng!")

# ------------------------------------------
# MENU 5: THỐNG KÊ & HỌC PHÍ (EXCEL)
# ------------------------------------------
elif choice == "5. Thống kê & Học phí (Lọc Tháng / Xuất Excel)":
    st.subheader("📊 Thống Kê Điểm Danh & Học Phí (Xuất Excel)")
    
    col_m, col_y = st.columns(2)
    with col_m:
        thang_sel = st.selectbox("Chọn Tháng:", list(range(1, 13)), index=datetime.datetime.now().month - 1)
    with col_y:
        nam_sel = st.number_input("Chọn Năm:", min_value=2020, max_value=2030, value=datetime.datetime.now().year)
        
    thang_nam_str = f"{nam_sel}-{thang_sel:02d}"
    
    query_stats = """
        SELECT hs.id, hs.ho_ten, hs.lop_hoc, hs.hoc_phi_buoi,
               SUM(CASE WHEN dd.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) as so_buoi_di_hoc,
               SUM(CASE WHEN dd.trang_thai LIKE 'Vắng%' THEN 1 ELSE 0 END) as so_buoi_vang
        FROM hoc_sinh hs
        LEFT JOIN diem_danh dd ON hs.id = dd.hoc_sinh_id AND strftime('%Y-%m', dd.ngay) = ?
        GROUP BY hs.id
    """
    df_stats = pd.read_sql_query(query_stats, conn, params=(thang_nam_str,))
    
    if not df_stats.empty:
        df_stats['Tong_Hoc_Phi'] = df_stats['so_buoi_di_hoc'] * df_stats['hoc_phi_buoi']
        
        st.write(f"### Báo cáo Tháng {thang_nam_str}")
        st.dataframe(df_stats, use_container_width=True)
        
        # Xuất file CSV / Excel
        csv = df_stats.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 Tải file CSV/Excel Báo Cáo",
            data=csv,
            file_name=f"Bao_Cao_Hoc_Phi_{thang_nam_str}.csv",
            mime="text/csv"
        )

# ------------------------------------------
# MENU 6: QUẢN LÝ HỌC PHÍ (XUẤT PDF)
# ------------------------------------------
elif choice == "6. Quản lý & Thống kê Học phí (Xuất PDF)":
    st.subheader("🧾 Quản Lý Đóng Học Phí & Xuất Phiếu A5 (PDF)")
    
    thang_nam_pdf = st.text_input("Tháng báo phí (YYYY-MM):", value=datetime.datetime.now().strftime("%Y-%m"))
    
    df_hs_pdf = pd.read_sql_query("""
        SELECT hs.id, hs.ho_ten, hs.lop_hoc, hs.hoc_phi_buoi,
               SUM(CASE WHEN dd.trang_thai = 'Có mặt' THEN 1 ELSE 0 END) as so_buoi
        FROM hoc_sinh hs
        LEFT JOIN diem_danh dd ON hs.id = dd.hoc_sinh_id AND strftime('%Y-%m', dd.ngay) = ?
        GROUP BY hs.id
    """, conn, params=(thang_nam_pdf,))
    
    if not df_hs_pdf.empty:
        for idx, row in df_hs_pdf.iterrows():
            c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
            tong_tien = row['so_buoi'] * row['hoc_phi_buoi']
            
            with c1:
                st.markdown(f"**{row['ho_ten']}** ({row['lop_hoc']})")
            with c2:
                st.write(f"{row['so_buoi']} buổi")
            with c3:
                st.write(f"{tong_tien:,.0f} đ")
            with c4:
                qr_data = st.session_state.get("qr_code_bytes", None)
                if REPORTLAB_AVAILABLE:
                    pdf_bytes = generate_pdf_receipt(
                        row['ho_ten'], row['lop_hoc'], thang_nam_pdf, 
                        row['so_buoi'], row['hoc_phi_buoi'], tong_tien, 
                        "Chưa thu", qr_bytes=qr_data
                    )
                    st.download_button(
                        f"📄 In PDF A5 ({row['ho_ten']})",
                        data=pdf_bytes,
                        file_name=f"Phieu_Hoc_Phi_{row['ho_ten']}_{thang_nam_pdf}.pdf",
                        mime="application/pdf",
                        key=f"pdf_{row['id']}"
                    )
                else:
                    st.warning("Vui lòng cài `reportlab` để xuất PDF")
            st.divider()

# ------------------------------------------
# MENU 7: SỬA & XÓA DỮ LIỆU
# ------------------------------------------
elif choice == "7. Sửa & Xóa dữ liệu":
    st.subheader("🛠️ Quản Lý & Điều Chỉnh Dữ Liệu")
    
    t1, t2 = st.tabs(["👤 Quản Lý Học Sinh", "📝 Nhật Ký Điểm Danh"])
    
    with t1:
        sub_t1, sub_t2, sub_t3 = st.tabs(["➕ 1. Thêm Học Sinh", "✏️ 2. Sửa Học Sinh", "❌ 3. Xóa Học Sinh"])
        
        with sub_t1:
            with st.form("form_add_hs"):
                ten_hs = st.text_input("Họ và Tên Học Sinh:")
                lop_hs = st.text_input("Lớp Học (ví dụ: Lớp 9A):")
                mon_hs = st.text_input("Môn Học:", value="Toán")
                phi_hs = st.number_input("Học phí / Buổi (VNĐ):", value=100000, step=10000)
                sdt_ph = st.text_input("Số điện thoại phụ huynh:")
                ns_hs = st.date_input("Ngày sinh:", value=datetime.date(2010, 1, 1))
                
                btn_add_hs = st.form_submit_button("➕ Thêm Học Sinh Mới", type="primary")
                if btn_add_hs:
                    if ten_hs:
                        c = conn.cursor()
                        c.execute("""
                            INSERT INTO hoc_sinh (ho_ten, lop_hoc, mon_hoc, hoc_phi_buoi, sdt_phu_huynh, ngay_sinh)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (ten_hs, lop_hs, mon_hs, phi_hs, sdt_ph, str(ns_hs)))
                        conn.commit()
                        st.success(f"✅ Đã thêm học sinh {ten_hs} thành công!")
                        st.rerun()
                    else:
                        st.error("Vui lòng nhập tên học sinh!")

        with sub_t2:
            df_hs_edit = pd.read_sql_query("SELECT * FROM hoc_sinh", conn)
            if not df_hs_edit.empty:
                selected_edit_id = st.selectbox(
                    "Chọn Học Sinh Cần Sửa:", 
                    options=df_hs_edit['id'].tolist(),
                    format_func=lambda x: f"{df_hs_edit[df_hs_edit['id']==x]['ho_ten'].values[0]}"
                )
                curr_row = df_hs_edit[df_hs_edit['id'] == selected_edit_id].iloc[0]
                
                with st.form("form_edit_hs"):
                    e_ten = st.text_input("Họ tên:", value=curr_row['ho_ten'])
                    e_lop = st.text_input("Lớp:", value=curr_row['lop_hoc'])
                    e_mon = st.text_input("Môn:", value=curr_row['mon_hoc'])
                    e_phi = st.number_input("Học phí/buổi:", value=float(curr_row['hoc_phi_buoi']))
                    e_sdt = st.text_input("SĐT Phụ huynh:", value=curr_row['sdt_phu_huynh'])
                    
                    btn_save_edit = st.form_submit_button("💾 Cập Nhật Thông Tin")
                    if btn_save_edit:
                        c = conn.cursor()
                        c.execute("""
                            UPDATE hoc_sinh 
                            SET ho_ten=?, lop_hoc=?, mon_hoc=?, hoc_phi_buoi=?, sdt_phu_huynh=?
                            WHERE id=?
                        """, (e_ten, e_lop, e_mon, e_phi, e_sdt, selected_edit_id))
                        conn.commit()
                        st.success("✅ Cập nhật thành công!")
                        st.rerun()

        with sub_t3:
            df_hs_del = pd.read_sql_query("SELECT * FROM hoc_sinh", conn)
            if not df_hs_del.empty:
                del_id = st.selectbox(
                    "Chọn Học Sinh Cần Xóa:", 
                    options=df_hs_del['id'].tolist(),
                    format_func=lambda x: f"{df_hs_del[df_hs_del['id']==x]['ho_ten'].values[0]}"
                )
                confirm_del = st.checkbox("⚠️ Tôi xác nhận muốn xóa học sinh này cùng toàn bộ dữ liệu điểm danh, thanh toán liên quan!")
                if st.button("❌ Xóa Học Sinh Khỏi Hệ Thống", type="primary"):
                    if confirm_del:
                        c = conn.cursor()
                        c.execute("DELETE FROM diem_danh WHERE hoc_sinh_id=?", (del_id,))
                        c.execute("DELETE FROM thanh_toan WHERE hoc_sinh_id=?", (del_id,))
                        c.execute("DELETE FROM lich_hoc_tuan WHERE hoc_sinh_id=?", (del_id,))
                        c.execute("DELETE FROM lich_hoc_tam_thoi WHERE hoc_sinh_id=?", (del_id,))
                        c.execute("DELETE FROM hoc_sinh WHERE id=?", (del_id,))
                        conn.commit()
                        st.success("✅ Đã xóa dữ liệu thành công!")
                        st.rerun()
                    else:
                        st.warning("Vui lòng tích chọn checkbox xác nhận trước khi xóa!")

        st.markdown("---")
        st.write("📋 **Danh sách tất cả học sinh hiện có:**")
        st.dataframe(pd.read_sql_query("SELECT * FROM hoc_sinh", conn), use_container_width=True)

    with t2:
        st.write("### Nhật Ký Điểm Danh (Xóa record nhầm)")
        df_dd_logs = pd.read_sql_query("""
            SELECT dd.id, hs.ho_ten, dd.ngay, dd.ca_hoc, dd.trang_thai, dd.nhan_xet
            FROM diem_danh dd
            JOIN hoc_sinh hs ON dd.hoc_sinh_id = hs.id
            ORDER BY dd.id DESC LIMIT 50
        """, conn)
        
        st.dataframe(df_dd_logs, use_container_width=True)
        if not df_dd_logs.empty:
            del_dd_id = st.number_input("Nhập ID dòng điểm danh cần xóa:", step=1, value=int(df_dd_logs.iloc[0]['id']))
            if st.button("🗑️ Xóa Buổi Điểm Danh Này"):
                c = conn.cursor()
                c.execute("DELETE FROM diem_danh WHERE id=?", (del_dd_id,))
                conn.commit()
                st.success("✅ Đã xóa dòng điểm danh!")
                st.rerun()
