import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date, datetime, timedelta
import os
import json
import re
import io
import textwrap
import random
import calendar
import zipfile

# Thử import Matplotlib để xuất thời khóa biểu, phiếu học phí & lịch sử điểm danh dạng ảnh PNG
try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# --- CẤU HÌNH TRANG WEB ---
st.set_page_config(page_title="Phần Mềm Quản Lý Dạy Thêm", layout="wide", page_icon="📚")

# --- KẾT NỐI SUPABASE (POSTGRESQL) QUA DATABASE_URL TRONG SECRETS ---
try:
    db_url = st.secrets["DATABASE_URL"]
    engine = create_engine(db_url)
except Exception as e:
    st.error(f"⚠️ Lỗi đọc cấu hình `DATABASE_URL` trong Streamlit Secrets: {e}")
    st.stop()

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

# --- KHO 30 CHÂM NGÔN TRUYỀN CẢM HỨNG CHO HỌC SINH ---
THONG_DIEP_LIST = [
    "🌟 'Thất bại chỉ là cơ hội để bắt đầu lại một cách thông minh hơn.' Cố lên các em nhé!",
    "📖 'Không có con đường nào là bằng phẳng nếu thiếu đi những bước chân kiên trì.'",
    "💡 'Mỗi cuốn sách bạn đọc hôm nay là một mảnh ghép cho tương lai ngày mai.'",
    "🌱 'Sự chăm chỉ đánh bại thiên tài khi thiên tài không chịu chăm chỉ.'",
    "✨ 'Tương lai được xây dựng bởi những gì bạn làm hôm nay, chứ không phải ngày mai.'",
    "🎯 'Kiến thức là kho báu mà người chủ sở hữu luôn giữ được nó an toàn nhất.'",
    "🚀 'Đừng sợ những câu hỏi khó, chúng chỉ đang làm não bạn thông minh hơn.'",
    "🔥 'Sự kiên trì là chìa khóa mở mọi cánh cửa thành công.'",
    "📘 'Hôm nay nỗ lực hết mình, ngày mai tự tin ngẩng cao đầu.'",
    "🌈 'Học tập là hành trình khám phá không có điểm dừng.'",
    "⭐ 'Mỗi bước tiến nhỏ mỗi ngày sẽ tạo nên những thay đổi lớn lao.'",
    "📚 'Đừng đo lường thành công bằng vạch xuất phát, hãy đo bằng sự nỗ lực.'",
    "💪 'Sự tập trung cao độ tạo nên những phép màu trong học tập.'",
    "🌻 'Nụ cười của sự thấu hiểu bài toán khó là phần thưởng tuyệt vời nhất.'",
    "✍️ 'Thói quen tốt được hình thành từ những hành động nhỏ nhặt mỗi ngày.'",
    "🏆 'Không có học sinh kém, chỉ có học sinh chưa tìm ra phương pháp đúng.'",
    "🌊 'Sự tự tin bắt đầu từ việc chuẩn bị bài thật chu đáo trước khi đến lớp.'",
    "🎨 'Học hỏi từ những sai lầm là con đường ngắn nhất dẫn đến đỉnh cao.'",
    "🧭 'Trí tuệ giống như cơ bắp, càng rèn luyện nhiều càng trở nên săn chắc.'",
    "⚡ 'Đam mê học tập là ngọn lửa sưởi ấm mọi mùa thi giá lạnh.'",
    "🍀 'Sự chuẩn bị kỹ càng hôm nay là bệ phóng cho thành công ngày mai.'",
    "🎓 'Kiên nhẫn đọc từng trang sách nhỏ sẽ mở ra cả một bầu trời tri thức.'",
    "🔍 'Sự sáng tạo biến những bài học khô khan thành những điều kỳ diệu.'",
    "🎈 'Mỗi câu hỏi bạn đặt ra là một bước tiến trên hành trình chinh phục tri thức.'",
    "🧩 'Đừng để sự trì hoãn đánh cắp đi tương lai tuyệt vời của bạn.'",
    "👑 'Sự đoàn kết trong học tập giúp chúng ta đi xa hơn rất nhiều.'",
    "🎇 'Học tập bằng niềm vui sẽ mang lại kết quả ngọt ngào nhất.'",
    "📘 'Ý chí kiên cường sẽ vượt qua mọi giông bão mùa thi cử.'",
    "🌟 'Mỗi thành công nhỏ hôm nay là bước đệm cho đại thắng ngày mai.'",
    "🚀 'Hãy để tri thức dẫn lối cho tương lai rực rỡ của chính bạn.'"
]

# --- KHO 30 LỜI NHẮC SỨC KHỎE CHO CÔ GIÁO ---
SUC_KHOE_LIST = [
    "💧 Lời nhắc sức khỏe: Cô ơi, hãy uống một ngụm nước ấm để giữ giọng và bảo vệ thanh quản nhé!",
    "🧘‍♀️ Lời nhắc sức khỏe: Đã đứng lớp một lúc rồi, cô hãy thả lỏng vai, vươn vai nhẹ nhàng để giảm mỏi cơ vai gáy nhé.",
    "🍎 Lời nhắc sức khỏe: Đừng bỏ bữa cô nhé! Một cơ thể khỏe mạnh và tràn đầy năng lượng là món quà tuyệt vời nhất.",
    "👁️ Lời nhắc sức khỏe: Hãy chớp mắt và nhìn ra xa vài giây để thư giãn đôi mắt sau khi nhìn máy tính quản lý quá lâu.",
    "🍵 Lời nhắc sức khỏe: Một tách trà ấm hoặc nước chanh mật ong lúc này sẽ giúp cô thanh lọc giọng nói và thư thái tinh thần đấy ạ.",
    "🌿 Lời nhắc sức khỏe: Hãy hít thở thật sâu, nhắm mắt lại 1 phút để tái tạo năng lượng trước khi bắt đầu ca dạy tiếp theo nhé!",
    "🚶‍♀️ Lời nhắc sức khỏe: Đứng lên đi lại nhẹ nhàng vài bước để máu lưu thông tốt hơn, xua tan cảm giác mỏi mệt cô nha.",
    "🌙 Lời nhắc sức khỏe: Hôm nay nếu công việc đã xong xuôi, hãy cố gắng nghỉ ngơi sớm để giữ gìn sức khỏe cho ngày mai cô nhé!",
    "🍉 Lời nhắc sức khỏe: Đừng quên bổ sung thêm một chút trái cây tươi hoặc vitamin để tăng cường đề kháng suốt cả tuần cô nhé.",
    "🌸 Lời nhắc sức khỏe: Cô hãy mỉm cười thật tươi và tự thưởng cho mình vài phút giây thư giãn nhẹ nhàng sau giờ đứng lớp nhé.",
    "🫖 Lời nhắc sức khỏe: Một ly trà gừng ấm sẽ giúp cô giữ ấm cơ thể và cổ họng trong những ngày làm việc vất vả.",
    "🧘 Lời nhắc sức khỏe: Hãy giữ lưng thẳng khi ngồi chấm bài để bảo vệ cột sống và vùng thắt lưng cô nhé.",
    "🍊 Lời nhắc sức khỏe: Bổ sung thêm chút vitamin C từ cam hoặc chanh tươi sẽ giúp cô luôn tràn đầy sức sống.",
    "✨ Lời nhắc sức khỏe: Công việc tuy bận rộn nhưng sức khỏe của cô vẫn là ưu tiên số một. Nhớ đừng làm việc quá sức nha!",
    "📴 Lời nhắc sức khỏe: Hãy dành ra 10 phút hoàn toàn tĩnh lặng, rời xa màn hình để tâm trí được nghỉ ngơi tuyệt đối cô nhé.",
    "✍️ Lời nhắc sức khỏe: Rửa tay sạch sẽ và thả lỏng cơ cổ tay sau những giờ viết bảng liên tục cô nha.",
    "💤 Lời nhắc sức khỏe: Giấc ngủ trưa ngắn dù chỉ 15 phút cũng giúp tinh thần cô sảng khoái và minh mẫn hơn rất nhiều.",
    "☀️ Lời nhắc sức khỏe: Đón một chút ánh nắng ban mai nhẹ nhàng sẽ giúp cô nạp thêm năng lượng tích cực cho cả ngày dài.",
    "🥜 Lời nhắc sức khỏe: Mang theo vài hạt dinh dưỡng hoặc thanh ngũ cốc để ăn nhẹ giữa giờ dạy giữ vững năng lượng cô nhé.",
    "🪟 Lời nhắc sức khỏe: Mở cửa sổ thoáng một chút để hít thở không khí trong lành, tái tạo không gian làm việc tươi mới cô ạ.",
    "💖 Lời nhắc sức khỏe: Hãy tự nhắc bản thân rằng cô đã làm rất tốt ngày hôm nhau, giờ là lúc thả lỏng và yêu chiều bản thân.",
    "🤸‍♀️ Lời nhắc sức khỏe: Thực hiện vài động tác xoay cổ tay, cổ chân và vươn thở sâu để xua tan mọi căng thẳng cơ bắp.",
    "🍵 Lời nhắc sức khỏe: Buổi tối ngâm chân nước ấm với chút gừng muối sẽ giúp cô có giấc ngủ sâu và ngon hơn rất nhiều.",
    "😊 Lời nhắc sức khỏe: Nụ cười của cô là năng lượng của lớp học, nhưng đừng quên chăm sóc bản thân thật chu đáo cô nhé!",
    "🫖 Lời nhắc sức khỏe: Thưởng thức một ngụm trà hoa cúc ấm áp để thư thái tinh thần sau một ca dạy kéo dài.",
    "🌿 Lời nhắc sức khỏe: Đừng quên hít sâu, thở chậm và buông bỏ mọi âu lo ngoài cửa lớp trước khi nghỉ ngơi cô nhé.",
    "🎤 Lời nhắc sức khỏe: Hạn chế nói quá lớn liên tục, hãy dùng micro hỗ trợ để bảo vệ thanh quản vàng của cô nha.",
    "🍫 Lời nhắc sức khỏe: Một chút sô-cô-la đen nhỏ sẽ giúp cô nhanh chóng lấy lại tinh thần và năng lượng tức thì.",
    "⚖️ Lời nhắc sức khỏe: Cân đối giữa công việc và nghỉ ngơi hợp lý chính là chìa khóa để cô luôn giữ mãi ngọn lửa đam mê.",
    "❤️ Lời nhắc sức khỏe: Cô là người truyền lửa tuyệt vời, vì vậy hãy luôn trân trọng và yêu thương cơ thể mình thật nhiều cô nhé!"
]

# --- HÀM HỖ TRỢ LÀM SẠCH VÀ CHUẨN HÓA NHẬN XÉT ---
def clean_nhan_xet(text_input):
    if not text_input:
        return ""
    emoji_pattern = re.compile(
        r"[\U00010000-\U0010ffff\u2600-\u27bf\u2b50\u2b06\u2934\u2935\u2b05\u2b07\u3299\u3227\u00a9\u00ae\u203c\u2049\u2122\u2139\u2194-\u2199\u21a9\u21aa\u2328\u23cf\u23e9-\u23f3\u23f8-\u23fa\u24c2\u25aa-\u25ab\u25b6\u25c0\u25fb-\u25fe\u2600-\u2604\u260e\u2611\u2614-\u2615\u2618\u261d\u2620\u2622-\u2623\u2626\u262a\u262e-\u262f\u2638-\u263a\u2648-\u2653\u2660-\u2668\u267b\u267f\u2692-\u2694\u2696-\u2697\u2699\u269b-\u269c\u26a0-\u26a1\u26aa-\u26ab\u26b0-\u26b1\u26bd-\u26be\u26c4-\u26c5\u26c8\u26ce-\u26cf\u26d1\u26d3-\u26d4\u26e9-\u26ea\u26f0-\u26f5\u26f7-\u26fa\u26fd\u2470\u2702\u2705\u2708-\u270d\u270f\u2712\u2714\u2716\u271d\u2721\u2728\u2733-\u2734\u2744\u2747\u274c\u274e\u2753-\u2755\u2757\u2763-\u2764\u2795-\u2797\u27a1\u27b0\u27bf\u2934-\u2935\u2b05-\u2b07\u2b12-\u2b13\u2b1b-\u2b1c\u2b50\u2b55\u3030\u303d\u3297\u3299]",
        flags=re.UNICODE
    )
    cleaned = emoji_pattern.sub(r'', text_input)
    cleaned = cleaned.replace('[', '').replace(']', '').strip()
    
    if not cleaned:
        return ""

    cleaned = re.sub(r'\bcó giao bài tập\b', 'có giao bài tập mới', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bkhông làm bài tập\b', 'không làm bài tập cũ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bhoàn thành bài tập\b', 'đã làm hết bài tập cũ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bnói chuyện/ mất tập trung\b', 'nói chuyện, chưa tập trung', cleaned, flags=re.IGNORECASE)

    custom_part = ""
    tags_part = cleaned
    if " - " in cleaned:
        parts = cleaned.split(" - ", 1)
        old_tag_keywords = ["chăm chú", "có tiến bộ", "có giao bài tập mới", "không làm bài tập cũ", "nói chuyện", "chưa tập trung", "đã làm hết bài tập cũ", "có làm bài tập nhưng chưa đủ", "buồn ngủ", "chểnh mảng", "lơ là học tập"]
        
        part0_has_tag = any(kw in parts[0].lower() for kw in old_tag_keywords)
        part1_has_tag = any(kw in parts[1].lower() for kw in old_tag_keywords)
        
        if part0_has_tag and not part1_has_tag:
            tags_part = parts[0]
            custom_part = parts[1]
        elif part1_has_tag and not part0_has_tag:
            custom_part = parts[0]
            tags_part = parts[1]
        else:
            custom_part = parts[0]
            tags_part = parts[1]

    tags_list = [t.strip().capitalize() for t in tags_part.split(",") if t.strip()]
    tags_formatted = ", ".join(tags_list)

    if custom_part.strip():
        custom_formatted = custom_part.strip()[0].upper() + custom_part.strip()[1:]
        if tags_formatted:
            final_result = f"{custom_formatted} - {tags_formatted}"
        else:
            final_result = custom_formatted
    else:
        final_result = tags_formatted

    if final_result and not final_result.endswith('.'):
        final_result += '.'

    return final_result

# --- HÀM HỖ TRỢ THỨ TRONG TUẦN ---
def get_vietnamese_weekday(dt):
    days = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ Nhật"]
    return days[dt.weekday()]

# --- HÀM XỬ LÝ GỘP NHÓM HỌC SINH THÔNG MINH ---
def get_base_name(ho_ten):
    name = str(ho_ten).split('(')[0].split('-')[0].strip()
    return name

def get_family_student_ids(engine, hs_id):
    df_curr = pd.read_sql_query(text(f"SELECT ho_ten, thong_tin_phu_huynh FROM hoc_sinh WHERE id = {hs_id}"), engine)
    if df_curr.empty:
        return [hs_id]
    curr_name = df_curr.iloc[0]['ho_ten']
    curr_phone = str(df_curr.iloc[0]['thong_tin_phu_huynh']).strip()
    
    if not curr_phone or curr_phone.lower() in ['none', 'nan', '']:
        return [hs_id]
        
    base_curr = get_base_name(curr_name).lower()
    
    df_all = pd.read_sql_query(text("SELECT id, ho_ten, thong_tin_phu_huynh FROM hoc_sinh"), engine)
    matched_ids = []
    for _, r in df_all.iterrows():
        r_name = r['ho_ten']
        r_phone = str(r['thong_tin_phu_huynh']).strip()
        base_r = get_base_name(r_name).lower()
        
        if r['id'] == hs_id:
            matched_ids.append(r['id'])
        elif curr_phone and r_phone and curr_phone.lower() not in ['none', 'nan', ''] and curr_phone == r_phone and base_curr == base_r:
            matched_ids.append(r['id'])
    return list(set(matched_ids))

# --- HÀM LẤY THỜI KHÓA BIỂU HIỆU LỰC CHO MỘT NGÀY ---
def get_active_schedule_for_date(engine, check_date, hs_ids=None, exclude_hoc_them=False):
    target_day_str = get_vietnamese_weekday(check_date)
    where_clause = f"l.thu = '{target_day_str}'"
    if hs_ids is not None:
        if not hs_ids:
            return pd.DataFrame(columns=['hoc_sinh_id', 'ho_ten', 'lop_hoc', 'mon_hoc', 'ca_hoc', 'nguon'])
        ids_str = ",".join(map(str, hs_ids))
        where_clause += f" AND l.hoc_sinh_id IN ({ids_str})"
        
    if exclude_hoc_them:
        where_clause += " AND LOWER(h.ho_ten) NOT LIKE '%học thêm%'"
        
    query_base = text(f'''
        SELECT l.hoc_sinh_id, h.ho_ten, h.lop_hoc, h.mon_hoc, l.ca_hoc, 'Lịch gốc' AS nguon
        FROM lich_hoc_tuan l
        JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
        WHERE {where_clause}
    ''')
    df_base = pd.read_sql_query(query_base, engine)
    cols = ['hoc_sinh_id', 'ho_ten', 'lop_hoc', 'mon_hoc', 'ca_hoc', 'nguon']
    return df_base[cols] if not df_base.empty else pd.DataFrame(columns=cols)

# --- HÀM ĐỒNG BỘ THỦ CÔNG (XOÁ THÁNG TRƯỚC, THÁNG NÀY, THÁNG SAU & ĐỒNG BỘ MỚI) ---
def sync_from_today_to_end_of_week(calendar_id='a.luongxdnb@gmail.com', ref_date=None):
    if ref_date is None:
        ref_date = date.today()
        
    start_date = ref_date
    
    # Kiểm tra xem hôm nay có phải là ngày cuối tháng hiện tại không
    _, last_day_curr = calendar.monthrange(ref_date.year, ref_date.month)
    is_last_day = (ref_date.day == last_day_curr)
    
    if not is_last_day:
        # Bình thường: đồng bộ đến hết tháng hiện tại
        end_date = date(ref_date.year, ref_date.month, last_day_curr)
    else:
        # Ngày cuối tháng: đồng bộ đến hết tháng tiếp theo
        if ref_date.month == 12:
            next_year = ref_date.year + 1
            next_month = 1
        else:
            next_year = ref_date.year
            next_month = ref_date.month + 1
        _, last_day_next = calendar.monthrange(next_year, next_month)
        end_date = date(next_year, next_month, last_day_next)

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

        # PHẠM VI XÓA LỊCH CŨ: Tháng liền trước, tháng hiện tại và tháng kế tiếp
        curr_y = ref_date.year
        curr_m = ref_date.month
        
        # 1. Tháng liền trước
        if curr_m == 1:
            prev_m = 12
            prev_y = curr_y - 1
        else:
            prev_m = curr_m - 1
            prev_y = curr_y
        clean_start = date(prev_y, prev_m, 1)

        # 2. Tháng kế tiếp (tính từ tháng hiện tại)
        if curr_m == 12:
            next_m = 1
            next_y = curr_y + 1
        else:
            next_m = curr_m + 1
            next_y = curr_y
        _, last_d_next = calendar.monthrange(next_y, next_m)
        clean_end = date(next_y, next_m, last_d_next)

        time_clean_min = f"{clean_start.strftime('%Y-%m-%d')}T00:00:00Z"
        time_clean_max = f"{clean_end.strftime('%Y-%m-%d')}T23:59:59Z"

        events_result = service.events().list(
            calendarId=calendar_id, 
            timeMin=time_clean_min, 
            timeMax=time_clean_max, 
            singleEvents=True
        ).execute()

        old_events = events_result.get('items', [])
        deleted_count = 0
        for evt in old_events:
            summary_evt = evt.get('summary', '')
            if summary_evt.startswith("🏫 Dạy Thêm Ca") or summary_evt.startswith("📚 Lớp"):
                try:
                    service.events().delete(calendarId=calendar_id, eventId=evt['id']).execute()
                    deleted_count += 1
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

        delta_days = (end_date - start_date).days + 1
        for i in range(delta_days):
            current_date = start_date + timedelta(days=i)
            df_day = get_active_schedule_for_date(engine, current_date, exclude_hoc_them=False)

            if df_day.empty:
                continue

            date_str = current_date.strftime("%Y-%m-%d")

            for ca, group_ca in df_day.groupby('ca_hoc'):
                start_time_str, end_time_str = ca_hoc_time.get(ca, ("17:30:00", "19:30:00"))
                start_datetime = f"{date_str}T{start_time_str}+07:00"
                end_datetime = f"{date_str}T{end_time_str}+07:00"

                for lop, g_lop in group_ca.groupby('lop_hoc'):
                    ds_hs = ", ".join(g_lop['ho_ten'].tolist())
                    so_luong_hs = len(g_lop)
                    
                    summary_title = f"📚 Lớp {lop} ({ca}) - {so_luong_hs} HS"
                    description_text = f"⏰ Giờ học: {ca}\n🏫 Lớp: {lop}\n👥 Số học sinh: {so_luong_hs}\n\nDANH SÁCH HỌC SINH:\n• {ds_hs}"

                    event = {
                        'summary': summary_title,
                        'description': description_text,
                        'start': {'dateTime': start_datetime, 'timeZone': 'Asia/Ho_Chi_Minh'},
                        'end': {'dateTime': end_datetime, 'timeZone': 'Asia/Ho_Chi_Minh'},
                    }

                    service.events().insert(calendarId=calendar_id, body=event).execute()
                    count_events += 1

        return True, f"✅ Đã dọn sạch {deleted_count} lịch cũ (từ {clean_start.strftime('%d/%m/%Y')} đến {clean_end.strftime('%d/%m/%Y')}) và đồng bộ mới từ **{start_date.strftime('%d/%m/%Y')}** đến **{end_date.strftime('%d/%m/%Y')}** ({count_events} sự kiện)!"
    except Exception as e:
        return False, f"❌ Lỗi khi đồng bộ: {str(e)}"

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

# --- HÀM LẤY MA TRẬN THỜI KHÓA BIỂU ---
def get_schedule_matrix_df(engine, filter_lop=None, filter_hs_id=None, ref_date=None):
    if ref_date is None:
        ref_date = date.today()
    cac_thu = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
    start_monday = ref_date - timedelta(days=ref_date.weekday())
    
    target_hs_ids = None
    if filter_hs_id:
        target_hs_ids = get_family_student_ids(engine, filter_hs_id)
    
    day_schedules = {}
    exclude_ht = True if filter_lop else False
    for i, t in enumerate(cac_thu):
        current_d = start_monday + timedelta(days=i)
        df_day = get_active_schedule_for_date(engine, current_d, hs_ids=target_hs_ids, exclude_hoc_them=exclude_ht)
        if not df_day.empty:
            if filter_lop:
                df_day = df_day[df_day['lop_hoc'] == filter_lop]
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
                        names_list = g['ho_ten'].tolist()
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

def render_schedule_matrix(engine, filter_lop=None, filter_hs_id=None, ref_date=None):
    df_matrix = get_schedule_matrix_df(engine, filter_lop=filter_lop, filter_hs_id=filter_hs_id, ref_date=ref_date)
    if df_matrix.empty:
        st.info("ℹ️ Không có thời khóa biểu nào trong tuần này.")
    else:
        st.write(df_matrix.to_html(index=False, escape=False), unsafe_allow_html=True)

# --- HÀM LẤY DANH SÁCH LỊCH HỌC DẠNG BẢNG LIỆT KÊ ---
def get_schedule_list_df(engine, filter_lop=None, filter_hs_id=None):
    where_clauses = []
    if filter_lop:
        where_clauses.append(f"h.lop_hoc = '{filter_lop}'")
        where_clauses.append("LOWER(h.ho_ten) NOT LIKE '%học thêm%'")
    if filter_hs_id:
        target_ids = get_family_student_ids(engine, filter_hs_id)
        if target_ids:
            ids_str = ",".join(map(str, target_ids))
            where_clauses.append(f"l.hoc_sinh_id IN ({ids_str})")
        else:
            return pd.DataFrame(columns=['Thứ', 'Ca học'])
    
    where_str = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    query = text(f'''
        SELECT l.thu, l.ca_hoc
        FROM lich_hoc_tuan l
        JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
        {where_str}
    ''')
    df = pd.read_sql_query(query, engine)
    if df.empty:
        return pd.DataFrame(columns=['Thứ', 'Ca học'])
    
    thu_order = {"Thứ 2": 1, "Thứ 3": 2, "Thứ 4": 3, "Thứ 5": 4, "Thứ 6": 5, "Thứ 7": 6, "Chủ Nhật": 7}
    df['thu_rank'] = df['thu'].map(lambda x: thu_order.get(x, 8))
    df = df.sort_values(by=['thu_rank', 'ca_hoc'])
    df = df[['thu', 'ca_hoc']].drop_duplicates().reset_index(drop=True)
    df.columns = ['Thứ', 'Ca học']
    return df

# --- HÀM TẠO FILE ẢNH THỜI KHÓA BIỂU ---
def create_list_schedule_image(title_target, df_list, prefix="Học sinh / Lớp: ", ref_date=None):
    if ref_date is None:
        ref_date = date.today()
    start_monday = ref_date - timedelta(days=ref_date.weekday())
    end_sunday = start_monday + timedelta(days=6)
    week_str = f"(Tuần từ {start_monday.strftime('%d/%m/%Y')} đến {end_sunday.strftime('%d/%m/%Y')})"

    table_data = [df_list.columns.tolist()] + df_list.values.tolist()
    
    fig, ax = plt.subplots(figsize=(8, max(6.0, len(df_list) * 0.9 + 5.0)))
    ax.axis('off')
    ax.axis('tight')
    
    col_widths = [0.4, 0.6]
    table = ax.table(cellText=table_data, loc='center', cellLoc='center', colWidths=col_widths, bbox=[0.1, 0.22, 0.8, 0.53])
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    
    ax.text(0.5, 0.88, "THỜI KHÓA BIỂU LỊCH HỌC HÀNG TUẦN", transform=fig.transFigure, 
            fontsize=17, fontweight='bold', color='#1E3A8A', ha='center', va='center')
    ax.text(0.5, 0.82, f"{prefix}{title_target}", transform=fig.transFigure, 
            fontsize=13, fontweight='bold', color='#0F172A', ha='center', va='center')
    ax.text(0.5, 0.77, week_str, transform=fig.transFigure, 
            fontsize=10.5, style='italic', color='#475569', ha='center', va='center')
    ax.text(0.5, 0.08, "Ghi chú: Lịch học được áp dụng ổn định cho các tuần tiếp theo nếu không có thay đổi tạm thời.", transform=fig.transFigure, 
            fontsize=9, style='italic', color='#64748B', ha='center', va='center')

    from matplotlib.patches import Rectangle
    rect = Rectangle((0.03, 0.03), 0.94, 0.94, transform=fig.transFigure,
                     fill=False, color='#CBD5E1', linewidth=1.5, zorder=10)
    fig.patches.append(rect)
    
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#CBD5E1')
        cell.PAD = 0.3
        if row == 0:
            cell.set_facecolor('#1E3A8A')
            cell.set_text_props(color='white', weight='bold', size=12.5)
        else:
            cell.set_text_props(color='#1E293B', size=11.5)
            if row % 2 == 0:
                cell.set_facecolor('#F8FAFC')
            else:
                cell.set_facecolor('white')
                
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig)
    buffer.seek(0)
    return buffer

# --- HÀM TẠO FILE ẢNH HÓA ĐƠN HỌC PHÍ CHUẨN MẪU ---
def create_tuition_slip_image(student_name, lop_hoc, subject, time_str, total_lessons, total_fee, status, sub_components=None):
    has_multiple_components = sub_components and len(sub_components) > 1
    fig, ax = plt.subplots(figsize=(8, 11 if has_multiple_components else 10))
    ax.axis('off')
    
    ax.text(0.5, 0.93, "PHIẾU BÁO HỌC PHÍ HỌC THÊM", fontsize=16, fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    ax.text(0.5, 0.87, f"Thời gian: {time_str}", fontsize=12, fontweight='normal', color='#1E293B', ha='center', va='center', transform=ax.transAxes)
    
    y_pos = 0.78
    x_label = 0.22 
    x_val = 0.51    
    
    ax.text(x_label, y_pos, "Học sinh:", fontsize=11.5, fontweight='normal', color='#1E293B', ha='left', va='center', transform=ax.transAxes)
    ax.text(x_val, y_pos, f"{student_name}", fontsize=11.5, fontweight='bold', color='#1E293B', ha='left', va='center', transform=ax.transAxes)
    y_pos -= 0.055
    
    ax.text(x_label, y_pos, "Lớp học:", fontsize=11.5, fontweight='normal', color='#1E293B', ha='left', va='center', transform=ax.transAxes)
    ax.text(x_val, y_pos, f"{lop_hoc}", fontsize=11.5, fontweight='bold', color='#1E293B', ha='left', va='center', transform=ax.transAxes)
    y_pos -= 0.055
    
    if has_multiple_components:
        for sc in sub_components:
            line_sc = f"• {sc['ten']}: {sc['so_ca']} buổi"
            ax.text(x_val, y_pos, line_sc, fontsize=11, fontweight='normal', color='#1E293B', ha='left', va='center', transform=ax.transAxes)
            y_pos -= 0.045
        y_pos -= 0.015
        
    ax.text(x_label, y_pos, "Tổng số buổi học:", fontsize=11.5, fontweight='normal', color='#1E293B', ha='left', va='center', transform=ax.transAxes)
    ax.text(x_val, y_pos, f"{total_lessons} buổi", fontsize=11.5, fontweight='bold', color='#1E293B', ha='left', va='center', transform=ax.transAxes)
    y_pos -= 0.065
    
    ax.text(x_label, y_pos, "Tổng cộng học phí:", fontsize=12.5, fontweight='normal', color='#1E293B', ha='left', va='center', transform=ax.transAxes)
    ax.text(x_val, y_pos, f"{total_fee:,.0f} VNĐ", fontsize=12.5, fontweight='bold', color='#1E293B', ha='left', va='center', transform=ax.transAxes)
    y_pos -= 0.065
    
    display_status = "Đã thanh toán" if status == "Đã đóng" else "Chưa thanh toán"
    ax.text(x_label, y_pos, "Trạng thái:", fontsize=11.5, fontweight='normal', color='#1E293B', ha='left', va='center', transform=ax.transAxes)
    ax.text(x_val, y_pos, f"{display_status}", fontsize=11.5, fontweight='bold', color='#1E293B', ha='left', va='center', transform=ax.transAxes)
    
    ax.text(0.5, 0.08, "Trân trọng cảm ơn sự đồng hành của Quý phụ huynh!", fontsize=11, style='italic', fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    
    from matplotlib.patches import Rectangle
    rect = Rectangle((0.03, 0.03), 0.94, 0.94, transform=fig.transFigure,
                     fill=False, color='#CBD5E1', linewidth=1.5, zorder=10)
    fig.patches.append(rect)

    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig)
    buffer.seek(0)
    return buffer

# --- HÀM TẠO FILE ẢNH LỊCH SỬ ĐIỂM DANH TỪNG HỌC SINH ---
def create_student_attendance_history_image(student_name, lop_hoc, month_year, df_history, total_present):
    wrapped_data = []
    max_lines_overall = 1
    for row in [df_history.columns.tolist()] + df_history.values.tolist():
        new_row = []
        row_max_lines = 1
        for col_idx, cell in enumerate(row):
            cell_str = str(cell)
            if col_idx == 3:
                wrapped_text = "\n".join(textwrap.wrap(cell_str, width=35)) if cell_str else ""
                lines = wrapped_text.count('\n') + 1 if wrapped_text else 1
                new_row.append(wrapped_text)
                if lines > row_max_lines:
                    row_max_lines = lines
            else:
                new_row.append(cell_str)
                lines = cell_str.count('\n') + 1
                if lines > row_max_lines:
                    row_max_lines = lines
        wrapped_data.append(new_row)
        if row_max_lines > max_lines_overall:
            max_lines_overall = row_max_lines

    fig, ax = plt.subplots(figsize=(10, max(4, len(df_history) * max(0.8, max_lines_overall * 0.45) + 3.5)))
    ax.axis('off')
    ax.axis('tight')
    
    ax.text(0.5, 0.94, "LỊCH SỬ ĐIỂM DANH & NHẬN XÉT HỌC SINH", fontsize=15, fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    ax.text(0.5, 0.89, f"Học sinh: {student_name} - Lớp: {lop_hoc} ({month_year})", fontsize=12, fontweight='bold', color='#0F172A', ha='center', va='center', transform=ax.transAxes)
    ax.text(0.5, 0.84, f"Tổng số buổi đi học (Có mặt): {total_present} buổi", fontsize=11, fontweight='bold', color='#B91C1C', ha='center', va='center', transform=ax.transAxes)
    
    table = ax.table(cellText=wrapped_data, loc='center', cellLoc='center', colWidths=[0.18, 0.22, 0.22, 0.38])
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    
    v_scale = max(2.2, max_lines_overall * 1.1)
    table.scale(1, v_scale)
    
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#CBD5E1')
        cell.PAD = 0.15
        if row == 0:
            cell.set_facecolor('#1E3A8A')
            cell.set_text_props(color='white', weight='bold', size=11)
        else:
            cell.set_text_props(color='#1E293B', size=9.5)
            if row % 2 == 0:
                cell.set_facecolor('#F8FAFC')
            else:
                cell.set_facecolor('white')

    from matplotlib.patches import Rectangle
    rect = Rectangle((0.03, 0.03), 0.94, 0.94, transform=fig.transFigure,
                     fill=False, color='#CBD5E1', linewidth=1.5, zorder=10)
    fig.patches.append(rect)
            
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig)
    buffer.seek(0)
    return buffer

# --- HÀM TẠO FILE ẢNH LỊCH SỬ ĐIỂM DANH CẢ LỚP ---
def create_class_attendance_history_image(class_name, time_label, df_history):
    raw_table_data = [df_history.columns.tolist()] + df_history.values.tolist()
    
    processed_rows = [raw_table_data[0]]
    last_ngay = None
    last_ca = None
    
    for row in raw_table_data[1:]:
        curr_ngay = row[0]
        curr_ca = row[1]
        
        new_row = list(row)
        if curr_ngay == last_ngay and curr_ca == last_ca:
            new_row[0] = ""
            new_row[1] = ""
        else:
            last_ngay = curr_ngay
            last_ca = curr_ca
        processed_rows.append(new_row)

    wrapped_data = []
    max_lines_overall = 1
    for row in processed_rows:
        new_row = []
        row_max_lines = 1
        for col_idx, cell in enumerate(row):
            cell_str = str(cell)
            if col_idx == 4:
                wrapped_text = "\n".join(textwrap.wrap(cell_str, width=32)) if cell_str else ""
                lines = wrapped_text.count('\n') + 1 if wrapped_text else 1
                new_row.append(wrapped_text)
                if lines > row_max_lines:
                    row_max_lines = lines
            else:
                new_row.append(cell_str)
                lines = cell_str.count('\n') + 1
                if lines > row_max_lines:
                    row_max_lines = lines
        wrapped_data.append(new_row)
        if row_max_lines > max_lines_overall:
            max_lines_overall = row_max_lines

    fig, ax = plt.subplots(figsize=(11, max(6.0, len(df_history) * max(0.8, max_lines_overall * 0.45) + 4.0)))
    ax.axis('off')
    ax.axis('tight')
    
    ax.text(0.5, 0.88, "BẢNG TỔNG HỢP ĐIỂM DANH VÀ NHẬN XÉT CẢ LỚP", transform=fig.transFigure, 
            fontsize=17, fontweight='bold', color='#1E3A8A', ha='center', va='center')
    ax.text(0.5, 0.83, f"Lớp: {class_name}", transform=fig.transFigure, 
            fontsize=13, fontweight='bold', color='#0F172A', ha='center', va='center')
    ax.text(0.5, 0.78, f"({time_label})", transform=fig.transFigure, 
            fontsize=10.5, style='italic', color='#475569', ha='center', va='center')
    
    bbox_coords = [0.05, 0.16, 0.9, 0.59]
    table = ax.table(cellText=wrapped_data, loc='center', cellLoc='center', colWidths=[0.15, 0.18, 0.22, 0.15, 0.30], bbox=bbox_coords)
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#CBD5E1')
        cell.PAD = 0.15
        cell.set_text_props(ha='center', va='center')
        
        if row == 0:
            cell.set_facecolor('#1E3A8A')
            cell.set_text_props(color='white', weight='bold', size=11, ha='center', va='center')
        else:
            cell.set_text_props(color='#1E293B', size=9.5, ha='center', va='center')
            if row % 2 == 0:
                cell.set_facecolor('#F8FAFC')
            else:
                cell.set_facecolor('white')

    total_rows = len(wrapped_data)
    bbox_left, bbox_bottom, bbox_width, bbox_height = bbox_coords
    for idx in range(1, len(raw_table_data)):
        if idx < len(raw_table_data) - 1:
            curr_ngay = raw_table_data[idx][0]
            next_ngay = raw_table_data[idx + 1][0]
            if curr_ngay != next_ngay:
                table_row_idx = idx
                y = bbox_bottom + bbox_height * (1.0 - (table_row_idx + 1) / total_rows)
                ax.plot([bbox_left, bbox_left + bbox_width], [y, y], transform=ax.transAxes, color='#1E3A8A', linewidth=2.0, zorder=15)

    from matplotlib.patches import Rectangle
    rect = Rectangle((0.03, 0.03), 0.94, 0.94, transform=fig.transFigure,
                     fill=False, color='#CBD5E1', linewidth=1.5, zorder=10)
    fig.patches.append(rect)
            
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig)
    buffer.seek(0)
    return buffer

# --- KHỞI TẠO BẢNG TRÊN SUPABASE (AN TOÀN) ---
try:
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
        try:
            conn.execute(text("ALTER TABLE hoc_sinh RENAME COLUMN sdt_phu_huynh TO thong_tin_phu_huynh"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE hoc_sinh ADD COLUMN IF NOT EXISTS thong_tin_phu_huynh TEXT"))
        except Exception:
            pass
except Exception as e:
    st.error(f"❌ Không thể kết nối tới cơ sở dữ liệu Supabase. Vui lòng kiểm tra lại cấu hình `DATABASE_URL` trên Streamlit Cloud hoặc trạng thái dự án trên Supabase. Chi tiết lỗi: {e}")
    st.stop()

# =========================================================
# --- HỆ THỐNG ĐĂNG NHẬP BẢO VỆ ADMIN ---
# =========================================================
def check_password():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if st.session_state.logged_in:
        return True

    st.markdown("<h2 style='text-align: center; color: #1E3A8A;'>📚 Đăng Nhập Quản Trị Hệ Thống</h2>", unsafe_allow_html=True)
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("🔐 Đăng Nhập Admin")
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

# --- GIAO DIỆN CHÍNH (ADMIN) ---
st.title("📚 Phần Mềm Quản Lý Dạy Thêm")

col_logout1, col_logout2 = st.sidebar.columns(2)
if col_logout1.button("🚪 Đăng xuất", type="secondary", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

menu = [
    "📝 Điểm danh & Nhận xét", 
    "📅 Quản lý Thời khoá Biểu",
    "💳 Quản lý học phí", 
    "📋 Thông tin học sinh"
]
choice = st.sidebar.selectbox("📋 Danh mục chức năng", menu)

st.sidebar.markdown("---")
st.sidebar.subheader("📱 Đồng bộ thời khóa biểu tới iPhone")
user_gmail_sidebar = st.sidebar.text_input("Địa chỉ Gmail trên iPhone:", value="a.luongxdnb@gmail.com")
if st.sidebar.button("🔄 Đồng bộ (Dọn sạch 3 tháng & Cập nhật)", type="primary", use_container_width=True):
    with st.spinner("⏳ Đang dọn sạch lịch cũ và đồng bộ lịch học mới..."):
        success_sync, msg_sync = sync_from_today_to_end_of_week(calendar_id=user_gmail_sidebar.strip(), ref_date=date.today())
        if success_sync:
            st.sidebar.success(msg_sync)
        else:
            st.sidebar.error(msg_sync)

st.sidebar.markdown("---")
st.sidebar.info("☁️ Dữ liệu đang được kết nối trực tiếp và lưu trữ vĩnh viễn trên **Supabase Cloud**.")

# =========================================================
# --- ĐIỂM DANH & NHẬN XÉT ---
# =========================================================
if choice == "📝 Điểm danh & Nhận xét":
    quote_today = random.choice(THONG_DIEP_LIST)
    health_today = random.choice(SUC_KHOE_LIST)
    
    st.info(f"💡 **Góc truyền cảm hứng hôm nay:**\n\n{quote_today}")
    st.success(f"💖 **Góc sức khỏe yêu thương:**\n\n{health_today}")
    st.markdown("---")

    with st.expander("🚨 Cảnh Báo Vắng Nhiều Trong Tháng (Từ 3 buổi trở lên)"):
        today_obj_exp = date.today()
        current_month_q_exp = f"{today_obj_exp.year}-{today_obj_exp.month:02d}"
        df_absent_alert = pd.read_sql_query(text(f'''
            SELECT h.ho_ten AS "Họ và Tên", h.lop_hoc AS "Lớp", 
                   (SUM(CASE WHEN d.trang_thai = 'Vắng có phép' THEN 1 ELSE 0 END) + SUM(CASE WHEN d.trang_thai = 'Vắng không phép' THEN 1 ELSE 0 END)) AS "Tổng số ca vắng"
            FROM diem_danh d
            JOIN hoc_sinh h ON d.hoc_sinh_id = h.id
            WHERE TO_CHAR(d.ngay, 'YYYY-MM') = '{current_month_q_exp}' AND d.trang_thai IN ('Vắng có phép', 'Vắng không phép')
            GROUP BY h.id, h.ho_ten, h.lop_hoc
            HAVING (SUM(CASE WHEN d.trang_thai = 'Vắng có phép' THEN 1 ELSE 0 END) + SUM(CASE WHEN d.trang_thai = 'Vắng không phép' THEN 1 ELSE 0 END)) >= 3
            ORDER BY "Tổng số ca vắng" DESC
        '''), engine)
        
        if df_absent_alert.empty:
            st.success("✅ Tháng này chưa có học sinh vắng từ 3 buổi trở lên.")
        else:
            st.dataframe(df_absent_alert, use_container_width=True, hide_index=True)

    with st.expander("📉 Top 5 Học Sinh Học Ít Ca Nhất Trong Tháng"):
        today_obj_exp2 = date.today()
        current_month_q_exp2 = f"{today_obj_exp2.year}-{today_obj_exp2.month:02d}"
        df_fewest_sessions = pd.read_sql_query(text(f'''
            SELECT h.ho_ten AS "Họ và Tên", h.lop_hoc AS "Lớp", 
                   COALESCE(SUM(CASE WHEN d.trang_thai = 'Có mặt' THEN 1 ELSE 0 END), 0) AS "Tổng số ca học"
            FROM hoc_sinh h
            LEFT JOIN diem_danh d ON h.id = d.hoc_sinh_id AND TO_CHAR(d.ngay, 'YYYY-MM') = '{current_month_q_exp2}'
            WHERE LOWER(h.ho_ten) NOT LIKE '%học thêm%'
            GROUP BY h.id, h.ho_ten, h.lop_hoc
            ORDER BY "Tổng số ca học" ASC
            LIMIT 5
        '''), engine)
        
        if df_fewest_sessions.empty:
            st.info("ℹ️ Chưa có dữ liệu học tập trong tháng này.")
        else:
            st.dataframe(df_fewest_sessions, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("📝 Điểm Danh & Nhận Xét Buổi Học")
    
    tab_dd_moi, tab_dd_quanly, tab_dd_lich_su = st.tabs([
        "📝 Điểm danh mới & Xem kết quả", 
        "⚙️ Quản lý, Sửa & Xóa Nhật ký Điểm danh",
        "🖼️ Lịch sử Điểm danh & Xuất Ảnh"
    ])
    
    with tab_dd_moi:
        ngay_hoc = st.date_input("🗓️ Chọn ngày điểm danh", date.today())
        thu_hom_nay = get_vietnamese_weekday(ngay_hoc)
        date_str = ngay_hoc.strftime("%Y-%m-%d")
        st.caption(f"Ngày được chọn: **{ngay_hoc.strftime('%d/%m/%Y')} ({thu_hom_nay})**")
        
        df_active_today = get_active_schedule_for_date(engine, ngay_hoc)
        df_all_hs = pd.read_sql_query(text("SELECT id AS hoc_sinh_id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh"), engine)
        
        che_do_nguon = st.radio(
            "📌 Chọn chế độ điểm danh:",
            [
                "1. Điểm danh tất cả học sinh hôm nay", 
                "2. Điểm danh học sinh / lớp KHÔNG có thời khóa biểu hôm nay (Học bù, phát sinh...)"
            ],
            key="che_do_nguon_diem_danh"
        )
        
        target_students = pd.DataFrame()

        if df_all_hs.empty:
            st.warning("⚠️ Chưa có học sinh nào trong hệ thống!")
        else:
            if che_do_nguon.startswith("1."):
                target_students = df_active_today
            else:
                available_classes = sorted(df_all_hs['lop_hoc'].dropna().unique().tolist())
                class_options_lbl = [f"🏫 Cả Lớp: {cls}" for cls in available_classes]
                student_dict = {f"👤 {row['ho_ten']} [{row['lop_hoc']}] - ID:{row['hoc_sinh_id']}": row['hoc_sinh_id'] for _, row in df_all_hs.iterrows()}
                
                all_options_opt2 = ["-- Vui lòng chọn Lớp hoặc Học sinh cần điểm danh --"] + class_options_lbl + list(student_dict.keys())
                selected_opt2 = st.selectbox("🔍 Tìm kiếm và chọn Lớp hoặc Học sinh:", all_options_opt2, key="sel_opt2_custom")
                
                if selected_opt2.startswith("🏫 Cả Lớp:"):
                    selected_lop_name = selected_opt2.replace("🏫 Cả Lớp: ", "").strip()
                    df_lop_filtered = df_all_hs[df_all_hs['lop_hoc'] == selected_lop_name].copy()
                    df_lop_filtered['ca_hoc'] = "17h30 - 19h30"
                    df_lop_filtered['nguon'] = "Ngoài lịch"
                    target_students = df_lop_filtered
                elif selected_opt2.startswith("👤 "):
                    sel_hs_id_val = student_dict[selected_opt2]
                    df_hs_filtered = df_all_hs[df_all_hs['hoc_sinh_id'] == sel_hs_id_val].copy()
                    df_hs_filtered['ca_hoc'] = "17h30 - 19h30"
                    df_hs_filtered['nguon'] = "Ngoài lịch"
                    target_students = df_hs_filtered

            if target_students.empty:
                st.info("ℹ️ Chưa có đối tượng nào được chọn hoặc không có học sinh trong danh sách thời khóa biểu hôm nay.")
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
                            tags_options = [
                                "chăm chú", "có tiến bộ", "có giao bài tập mới", "không làm bài tập cũ", 
                                "nói chuyện", "chưa tập trung", "đã làm hết bài tập cũ", "có làm bài tập nhưng chưa đủ", 
                                "buồn ngủ", "chểnh mảng", "lơ là học tập"
                            ]
                            custom_nx = st.text_input("Ghi chú thêm (Tự viết - hiển thị ở đầu)", key=f"nx_cls_{row['hoc_sinh_id']}_{idx}", placeholder="Ghi chú riêng sẽ nằm ở đầu...")
                            selected_tags = st.multiselect("🏷️ Chọn nhanh thẻ thái độ:", tags_options, key=f"tags_cls_{row['hoc_sinh_id']}_{idx}")
                            
                            formatted_tags = []
                            for i, t in enumerate(selected_tags):
                                ct = t.strip().lower()
                                if i == 0:
                                    ct = ct.capitalize()
                                formatted_tags.append(ct)
                                
                            tag_str = ", ".join(formatted_tags)
                            
                            if custom_nx.strip() and tag_str:
                                custom_prefix = custom_nx.strip()
                                custom_prefix = custom_prefix[0].upper() + custom_prefix[1:]
                                nx_val = f"{custom_prefix} - {tag_str}"
                            elif custom_nx.strip():
                                nx_val = custom_nx.strip()
                                nx_val = nx_val[0].upper() + nx_val[1:]
                            elif tag_str:
                                nx_val = tag_str
                            else:
                                nx_val = ""
                                    
                            if nx_val and not nx_val.endswith('.'):
                                nx_val += '.'

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

        df_dd_today = pd.read_sql_query(text(f'''
            SELECT d.id, h.ho_ten AS "Họ và Tên", h.lop_hoc AS "Lớp", d.ca_hoc AS "Ca Học", d.trang_thai AS "Trạng Thái", d.nhan_xet AS "Nhận Xét"
            FROM diem_danh d
            JOIN hoc_sinh h ON d.hoc_sinh_id = h.id
            WHERE d.ngay = '{date_str}'
            ORDER BY d.id DESC
        '''), engine)

        if not df_dd_today.empty:
            df_dd_today['Nhận Xét'] = df_dd_today['Nhận Xét'].apply(clean_nhan_xet)
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
        
        df_logs = pd.read_sql_query(text(f'''
            SELECT d.id AS "Mã Lịch", h.id AS hoc_sinh_id, h.ho_ten AS "Họ Tên", h.lop_hoc AS "Lớp", d.ngay AS "Ngày", d.ca_hoc AS "Ca Học", d.trang_thai AS "Trạng Thái", d.nhan_xet AS "Nhận Xét" 
            FROM diem_danh d 
            JOIN hoc_sinh h ON d.hoc_sinh_id = h.id 
            WHERE d.ngay = '{date_filter_str}'
            ORDER BY d.id DESC
        '''), engine)
        
        tags_options_global = [
            "chăm chú", "có tiến bộ", "có giao bài tập mới", "không làm bài tập cũ", 
            "nói chuyện", "chưa tập trung", "đã làm hết bài tập cũ", "có làm bài tập nhưng chưa đủ", 
            "buồn ngủ", "chểnh mảng", "lơ là học tập"
        ]

        if not df_logs.empty:
            df_logs['Nhận Xét'] = df_logs['Nhận Xét'].apply(clean_nhan_xet)
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
                    
                    old_nx_full = r['Nhận Xét'] or ""
                    found_old_tags = []
                    custom_old_part = ""
                    
                    if " - " in old_nx_full:
                        parts = old_nx_full.split(" - ", 1)
                        part0_is_tag = any(t.lower() in parts[0].lower() for t in tags_options_global)
                        part1_is_tag = any(t.lower() in parts[1].lower() for t in tags_options_global)
                        
                        if part0_is_tag and not part1_is_tag:
                            tags_str_part = parts[0]
                            custom_old_part = parts[1]
                        elif part1_is_tag and not part0_is_tag:
                            custom_old_part = parts[0]
                            tags_str_part = parts[1]
                        else:
                            custom_old_part = parts[0]
                            tags_str_part = parts[1]
                    else:
                        is_all_tag = any(t.lower() in old_nx_full.lower() for t in tags_options_global)
                        if is_all_tag:
                            tags_str_part = old_nx_full
                            custom_old_part = ""
                        else:
                            tags_str_part = ""
                            custom_old_part = old_nx_full

                    for t in tags_options_global:
                        if t.lower() in tags_str_part.lower():
                            if t not in found_old_tags:
                                found_old_tags.append(t)

                    c_stt, c_nx, c_tags = st.columns([1.2, 2.3, 2.5])
                    stt_options = ["Có mặt", "Vắng có phép", "Vắng không phép"]
                    current_stt_idx = stt_options.index(r['Trạng Thái']) if r['Trạng Thái'] in stt_options else 0
                    
                    with c_stt:
                        new_stt = st.selectbox("Trạng thái", stt_options, index=current_stt_idx, key=f"batch_stt_{r['Mã Lịch']}")
                    with c_nx:
                        new_custom_nx = st.text_input("Ghi chú thêm (Đầu)", value=custom_old_part.rstrip('.'), key=f"batch_nx_{r['Mã Lịch']}")
                    with c_tags:
                        new_tags = st.multiselect("Thẻ thái độ", tags_options_global, default=found_old_tags, key=f"batch_tags_{r['Mã Lịch']}")
                    
                    formatted_new_tags = []
                    for i, t in enumerate(new_tags):
                        ct = t.strip().lower()
                        if i == 0:
                            ct = ct.capitalize()
                        formatted_new_tags.append(ct)
                        
                    tag_str = ", ".join(formatted_new_tags)
                    
                    if new_custom_nx.strip() and tag_str:
                        custom_prefix = new_custom_nx.strip()
                        custom_prefix = custom_prefix[0].upper() + custom_prefix[1:]
                        new_nx_val = f"{custom_prefix} - {tag_str}"
                    elif new_custom_nx.strip():
                        new_nx_val = new_custom_nx.strip()
                        new_nx_val = new_nx_val[0].upper() + new_nx_val[1:]
                    elif tag_str:
                        new_nx_val = tag_str
                    else:
                        new_nx_val = ""
                            
                    if new_nx_val and not new_nx_val.endswith('.'):
                        new_nx_val += '.'

                    class_updates.append((r['Mã Lịch'], new_stt, new_nx_val))
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
                            '''), {"stt": stt, "nx": nx, "id": rec_id})
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
                
                old_nx_single = row_log_item['Nhận Xét'] or ""
                found_single_tags = []
                custom_single_part = ""
                
                if " - " in old_nx_single:
                    parts_s = old_nx_single.split(" - ", 1)
                    part0_is_tag_s = any(t.lower() in parts_s[0].lower() for t in tags_options_global)
                    part1_is_tag_s = any(t.lower() in parts_s[1].lower() for t in tags_options_global)
                    
                    if part0_is_tag_s and not part1_is_tag_s:
                        tags_str_part_s = parts_s[0]
                        custom_single_part = parts_s[1]
                    elif part1_is_tag_s and not part0_is_tag_s:
                        custom_single_part = parts_s[0]
                        tags_str_part_s = parts_s[1]
                    else:
                        custom_single_part = parts_s[0]
                        tags_str_part_s = parts_s[1]
                else:
                    is_all_tag_s = any(t.lower() in old_nx_single.lower() for t in tags_options_global)
                    if is_all_tag_s:
                        tags_str_part_s = old_nx_single
                        custom_single_part = ""
                    else:
                        tags_str_part_s = ""
                        custom_single_part = old_nx_single

                for t in tags_options_global:
                    if t.lower() in tags_str_part_s.lower():
                        if t not in found_single_tags:
                            found_single_tags.append(t)

                with st.form("form_edit_delete_diem_danh_record"):
                    st.write(f"Đang thao tác Mã Lịch **{log_to_edit_del}**: {row_log_item['Họ Tên']} [{row_log_item['Lớp']}] - Ngày: {row_log_item['Ngày']} - Ca: {row_log_item['Ca Học']}")
                    
                    stt_options = ["Có mặt", "Vắng có phép", "Vắng không phép"]
                    default_stt_idx = stt_options.index(row_log_item['Trạng Thái']) if row_log_item['Trạng Thái'] in stt_options else 0
                    
                    edit_stt_val = st.selectbox("Trạng thái mới:", stt_options, index=default_stt_idx, key="edit_log_stt")
                    edit_custom_nx_val = st.text_input("Ghi chú thêm mới (Đầu):", value=custom_single_part.rstrip('.'), key="edit_log_custom_nx")
                    edit_tags_val = st.multiselect("Thẻ thái độ mới:", tags_options_global, default=found_single_tags, key="edit_log_tags")
                    
                    formatted_edit_tags = []
                    for i, t in enumerate(edit_tags_val):
                        ct = t.strip().lower()
                        if i == 0:
                            ct = ct.capitalize()
                        formatted_edit_tags.append(ct)
                        
                    tag_str_single = ", ".join(formatted_edit_tags)
                    
                    if edit_custom_nx_val.strip() and tag_str_single:
                        custom_prefix = edit_custom_nx_val.strip()
                        custom_prefix = custom_prefix[0].upper() + custom_prefix[1:]
                        edit_nx_val = f"{custom_prefix} - {tag_str_single}"
                    elif edit_custom_nx_val.strip():
                        edit_nx_val = edit_custom_nx_val.strip()
                        edit_nx_val = edit_nx_val[0].upper() + edit_nx_val[1:]
                    elif tag_str_single:
                        edit_nx_val = tag_str_single
                    else:
                        edit_nx_val = ""
                            
                    if edit_nx_val and not edit_nx_val.endswith('.'):
                        edit_nx_val += '.'

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
                            '''), {"stt": edit_stt_val, "nx": edit_nx_val, "id": log_to_edit_del})
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
        st.subheader("🖼️ Xem Lịch Sử Điểm Danh & Xuất Ảnh")
        
        export_mode_type = st.radio("📌 Chọn phạm vi xuất lịch sử điểm danh:", ["🏫 Theo Cả Lớp học (Tổng hợp các ca)", "👤 Theo từng học sinh riêng lẻ"], horizontal=True, key="export_mode_type_radio", index=0)
        
        df_hs_ls = pd.read_sql_query(text("SELECT id, ho_ten, lop_hoc FROM hoc_sinh ORDER BY id DESC"), engine)
        if df_hs_ls.empty:
            st.warning("Chưa có học sinh nào trong hệ thống.")
        else:
            if export_mode_type == "🏫 Theo Cả Lớp học (Tổng hợp các ca)":
                st.markdown("##### 🏫 Xuất Bảng Điểm Danh Tổng Hợp Cả Lớp")
                all_lops_export = sorted(df_hs_ls['lop_hoc'].dropna().unique().tolist())
                if not all_lops_export:
                    st.warning("⚠️ Không có lớp học nào trong hệ thống.")
                else:
                    sel_lop_exp_cls = st.selectbox("Chọn Lớp học cần xuất:", all_lops_export, key="sel_lop_exp_cls_key")
                    option_time_cls = st.radio("Chọn khoảng thời gian xuất:", ["1 ngày", "1 tuần", "1 tháng"], horizontal=True, key="option_time_cls_radio", index=1)
                    
                    df_cls_history_final = pd.DataFrame()
                    time_label_cls = ""
                    file_suffix = ""

                    if option_time_cls == "1 ngày":
                        sel_date_cls = st.date_input("Chọn ngày xuất:", date.today(), key="sel_date_cls_input")
                        date_str_cls = sel_date_cls.strftime("%Y-%m-%d")
                        time_label_cls = f"Ngày {sel_date_cls.strftime('%d/%m/%Y')}"
                        file_suffix = f"Ngay_{sel_date_cls.strftime('%Y%m%d')}"
                        
                        df_cls_history_final = pd.read_sql_query(text(f'''
                            SELECT 
                                TO_CHAR(d.ngay, 'DD/MM/YYYY') AS "Ngày",
                                d.ca_hoc AS "Ca học",
                                h.ho_ten AS "Họ và tên",
                                d.trang_thai AS "Trạng thái",
                                COALESCE(d.nhan_xet, '') AS "Nhận xét"
                            FROM diem_danh d
                            JOIN hoc_sinh h ON d.hoc_sinh_id = h.id
                            WHERE h.lop_hoc = '{sel_lop_exp_cls}' AND d.ngay = '{date_str_cls}'
                              AND LOWER(h.ho_ten) NOT LIKE '%học thêm%'
                            ORDER BY d.ngay ASC, d.ca_hoc ASC, h.ho_ten ASC
                        '''), engine)

                    elif option_time_cls == "1 tuần":
                        sel_tuan_cls = st.date_input("Chọn ngày bất kỳ trong tuần:", date.today(), key="sel_tuan_cls_input")
                        start_w_cls = sel_tuan_cls - timedelta(days=sel_tuan_cls.weekday())
                        end_w_cls = start_w_cls + timedelta(days=6)
                        start_str_cls = start_w_cls.strftime("%Y-%m-%d")
                        end_str_cls = end_w_cls.strftime("%Y-%m-%d")
                        time_label_cls = f"Tuần từ {start_w_cls.strftime('%d/%m/%Y')} đến {end_w_cls.strftime('%d/%m/%Y')}"
                        file_suffix = f"Tuan_{start_w_cls.strftime('%Y%m%d')}"
                        
                        df_cls_history_final = pd.read_sql_query(text(f'''
                            SELECT 
                                TO_CHAR(d.ngay, 'DD/MM/YYYY') AS "Ngày",
                                d.ca_hoc AS "Ca học",
                                h.ho_ten AS "Họ và tên",
                                d.trang_thai AS "Trạng thái",
                                COALESCE(d.nhan_xet, '') AS "Nhận xét"
                            FROM diem_danh d
                            JOIN hoc_sinh h ON d.hoc_sinh_id = h.id
                            WHERE h.lop_hoc = '{sel_lop_exp_cls}' AND d.ngay >= '{start_str_cls}' AND d.ngay <= '{end_str_cls}'
                              AND LOWER(h.ho_ten) NOT LIKE '%học thêm%'
                            ORDER BY d.ngay ASC, d.ca_hoc ASC, h.ho_ten ASC
                        '''), engine)

                    else:
                        c_y_c, c_m_c = st.columns([1, 1])
                        with c_y_c:
                            nam_cls_exp = st.number_input("Năm", min_value=2020, max_value=2035, value=datetime.now().year, key="nam_cls_exp_input")
                        with c_m_c:
                            thang_cls_exp = st.selectbox("Tháng", list(range(1, 13)), index=datetime.now().month - 1, format_func=lambda x: f"Tháng {x}", key="thang_cls_exp_select")
                        
                        thang_nam_q_cls = f"{nam_cls_exp}-{thang_cls_exp:02d}"
                        time_label_cls = f"Tháng {thang_cls_exp:02d}/{nam_cls_exp}"
                        file_suffix = f"Thang_{thang_cls_exp}_{nam_cls_exp}"
                        
                        df_cls_history_final = pd.read_sql_query(text(f'''
                            SELECT 
                                TO_CHAR(d.ngay, 'DD/MM/YYYY') AS "Ngày",
                                d.ca_hoc AS "Ca học",
                                h.ho_ten AS "Họ và tên",
                                d.trang_thai AS "Trạng thái",
                                COALESCE(d.nhan_xet, '') AS "Nhận xét"
                            FROM diem_danh d
                            JOIN hoc_sinh h ON d.hoc_sinh_id = h.id
                            WHERE h.lop_hoc = '{sel_lop_exp_cls}' AND TO_CHAR(d.ngay, 'YYYY-MM') = '{thang_nam_q_cls}'
                              AND LOWER(h.ho_ten) NOT LIKE '%học thêm%'
                            ORDER BY d.ngay ASC, d.ca_hoc ASC, h.ho_ten ASC
                        '''), engine)

                    if df_cls_history_final.empty:
                        st.info(f"ℹ️ Lớp {sel_lop_exp_cls} không có dữ liệu điểm danh trong khoảng thời gian này.")
                    else:
                        df_cls_history_final['Nhận xét'] = df_cls_history_final['Nhận xét'].apply(clean_nhan_xet)
                        st.write(f"📋 Tổng hợp danh sách điểm danh lớp **{sel_lop_exp_cls}** ({len(df_cls_history_final)} bản ghi):")
                        st.dataframe(df_cls_history_final, use_container_width=True)
                        
                        if HAS_MATPLOTLIB:
                            img_class_bytes = create_class_attendance_history_image(
                                class_name=sel_lop_exp_cls,
                                time_label=time_label_cls,
                                df_history=df_cls_history_final
                            )
                            safe_lop_filename = re.sub(r'[\\/*?:"<>|]', "", sel_lop_exp_cls.replace(" ", "_"))
                            st.download_button(
                                label=f"🖼️ Tải Ảnh Tổng Hợp Điểm Danh Lớp {sel_lop_exp_cls}",
                                data=img_class_bytes,
                                file_name=f"TongHop_DiemDanh_Lop_{safe_lop_filename}_{file_suffix}.png",
                                mime="image/png",
                                type="primary",
                                key="btn_download_class_attendance_img"
                            )

            else:
                c_y_ls, c_m_ls = st.columns([1, 1])
                with c_y_ls:
                    nam_ls = st.number_input("Năm", min_value=2020, max_value=2035, value=datetime.now().year, key="nam_ls_pick")
                with c_m_ls:
                    thang_ls = st.selectbox("Tháng", list(range(1, 13)), index=datetime.now().month - 1, format_func=lambda x: f"Tháng {x}", key="thang_ls_pick")
                
                thang_nam_q = f"{nam_ls}-{thang_ls:02d}"
                thang_nam_k = f"{thang_ls:02d}/{nam_ls}"
                
                st.markdown("---")
                st.markdown("##### 👤 Xem & tải chi tiết theo từng học sinh riêng lẻ:")
                hs_dict_ls = {f"{r['ho_ten']} [{r['lop_hoc']}] - ID:{r['id']}": r['id'] for _, r in df_hs_ls.iterrows()}
                sel_hs_ls_lbl = st.selectbox("Chọn học sinh", list(hs_dict_ls.keys()), key="sel_hs_ls_key")
                sel_hs_id_ls = hs_dict_ls[sel_hs_ls_lbl]
                family_ids_ls = get_family_student_ids(engine, sel_hs_id_ls)
                ids_ls_str = ",".join(map(str, family_ids_ls))
                
                sel_hs_row_ls = df_hs_ls[df_hs_ls['id'] == sel_hs_id_ls].iloc[0]
                base_name_ls = get_base_name(sel_hs_row_ls['ho_ten'])
                
                df_hs_att_history = pd.read_sql_query(text(f'''
                    SELECT 
                        TO_CHAR(d.ngay, 'DD/MM/YYYY') AS "Ngày",
                        d.ca_hoc AS "Ca học",
                        d.trang_thai AS "Trạng thái",
                        COALESCE(d.nhan_xet, '') AS "Nhận xét"
                    FROM diem_danh d
                    WHERE d.hoc_sinh_id IN ({ids_ls_str}) AND TO_CHAR(d.ngay, 'YYYY-MM') = '{thang_nam_q}'
                    ORDER BY d.ngay ASC, d.id ASC
                '''), engine)
                
                if df_hs_att_history.empty:
                    st.info(f"ℹ️ Học sinh {base_name_ls} chưa có lịch sử điểm danh trong Tháng {thang_nam_k}.")
                else:
                    df_hs_att_history['Nhận xét'] = df_hs_att_history['Nhận xét'].apply(clean_nhan_xet)
                    total_co_mat = len(df_hs_att_history[df_hs_att_history['Trạng thái'] == 'Có mặt'])
                    st.metric("🟢 Tổng số buổi đi học (Có mặt)", f"{total_co_mat} buổi", f"Tổng số bản ghi: {len(df_hs_att_history)} buổi")
                    st.dataframe(df_hs_att_history, use_container_width=True)
                    
                    if HAS_MATPLOTLIB:
                        img_ls_bytes = create_student_attendance_history_image(
                            student_name=base_name_ls,
                            lop_hoc=sel_hs_row_ls['lop_hoc'],
                            month_year=thang_nam_k,
                            df_history=df_hs_att_history,
                            total_present=total_co_mat
                        )
                        safe_name_hs = re.sub(r'[\\/*?:"<>|]', "", f"{base_name_ls}_{sel_hs_row_ls['lop_hoc']}".replace(" ", "_"))
                        st.download_button(
                            label=f"🖼️ Tải Ảnh Lịch Sử Điểm Danh ({base_name_ls})",
                            data=img_ls_bytes,
                            file_name=f"Lich_Su_Diem_Danh_{safe_name_hs}_Thang_{thang_ls}_{nam_ls}.png",
                            mime="application/png",
                            type="primary",
                            key="btn_download_student_att_img"
                        )

# =========================================================
# --- QUẢN LÝ THỜI KHÓA BIỂU ---
# =========================================================
elif choice == "📅 Quản lý Thời khoá Biểu":
    st.subheader("📅 Quản lý Thời khóa Biểu")

    tab_matrix, tab_goc, tab_export = st.tabs([
        "🗓️ Thời khóa biểu tổng quan", 
        "⏰ Xếp thời khóa biểu mới", 
        "🖼️ Tải ảnh thời khóa biểu"
    ])

    with tab_matrix:
        st.markdown("##### 🗓️ Chọn mốc tuần cần xem thời khóa biểu tổng quan:")
        sel_date_matrix = st.date_input("Xem tuần chứa ngày:", date.today(), key="sel_date_matrix_main")
        st.divider()
        render_schedule_matrix(engine, ref_date=sel_date_matrix)

    with tab_goc:
        st.subheader("📅 Xếp Thời Khóa Biểu Cố Định Hàng Tuần")
        
        df_hs = pd.read_sql_query(text("SELECT id, ho_ten, lop_hoc, mon_hoc FROM hoc_sinh"), engine)
        
        if df_hs.empty:
            st.warning("Chưa có học sinh.")
        else:
            mode_goc = st.radio("Phạm vi xếp thời khóa biểu gốc:", ["Theo Lớp (Áp dụng chung cả lớp)", "Theo Từng Học Sinh Riêng Biệt"], horizontal=True, key="mode_goc_sched")
            
            target_hs_ids = []
            target_name_label = ""
            if mode_goc == "Theo Lớp (Áp dụng chung cả lớp)":
                all_lops = sorted(df_hs['lop_hoc'].dropna().unique().tolist())
                selected_lop = st.selectbox("Chọn Lớp để xếp thời khóa biểu gốc", all_lops, key="select_goc_lop")
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
                    st.session_state[f"multi_ca_{t_res}"] = []
                    st.session_state[f"custom_ca_multi_{t_res}"] = ""
                st.rerun()

            cac_thu = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ Nhật']
            
            st.markdown(f"##### ⏰ Chọn ca học cho từng ngày trong tuần của **{target_name_label}**:")
            schedule_dict_to_save = {}
            
            for t in cac_thu:
                with st.expander(f"🗓️ {t}", expanded=True):
                    cas_chon = st.multiselect(f"Chọn các ca chuẩn vào {t}:", DANH_SACH_CA_MAU, key=f"multi_ca_{t}")
                    custom_ca_them = st.text_input(f"Thêm ca giờ tùy chỉnh vào {t} (nếu có, cách nhau bằng dấu phẩy):", placeholder="VD: 08h00 - 10h00", key=f"custom_ca_multi_{t}")
                    
                    all_cas_for_day = list(cas_chon)
                    if custom_ca_them.strip():
                        extra_cas = [c_item.strip() for c_item in custom_ca_them.split(",") if c_item.strip()]
                        all_cas_for_day.extend(extra_cas)
                    
                    if all_cas_for_day:
                        schedule_dict_to_save[t] = list(set(all_cas_for_day))

            if st.button(f"💾 Lưu Thời Khóa Biểu Gốc Cho {target_name_label}", type="primary"):
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
                
                st.success(f"✅ Đã lưu thành công thời khóa biểu gốc cho {target_name_label} vào cơ sở dữ liệu!")
                st.rerun()

    with tab_export:
        st.markdown("### 🖼️ Tải Ảnh Thời Khóa Biểu Hàng Tuần")
        df_hs_all = pd.read_sql_query(text("SELECT id, ho_ten, lop_hoc FROM hoc_sinh"), engine)

        if df_hs_all.empty:
            st.warning("Chưa có dữ liệu học sinh.")
        else:
            filter_mode = st.radio("Chọn phạm vi tải thời khóa biểu:", ["Theo Lớp cụ thể", "Theo Học sinh cụ thể"], horizontal=True, key="filter_mode_exp_m")
            
            target_title = "Lớp học"
            selected_lop_exp = None
            selected_hs_exp = None
            prefix_label = "Học sinh / Lớp: "
            file_name_download = "Thoi_Khoa_Bieu.png"

            if filter_mode == "Theo Lớp cụ thể":
                lop_list = sorted(df_hs_all['lop_hoc'].dropna().unique().tolist())
                selected_lop_exp = st.selectbox("Chọn Lớp:", lop_list, key="sel_lop_exp_m")
                target_title = f"Lớp {selected_lop_exp}"
                prefix_label = "Lớp: "
                safe_lop_name = re.sub(r'[\\/*?:"<>|]', "", f"{selected_lop_exp}".replace(" ", "_"))
                file_name_download = f"Thoi_Khoa_Bieu_Lop_{safe_lop_name}.png"
            elif filter_mode == "Theo Học sinh cụ thể":
                hs_dict_exp = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row for _, row in df_hs_all.iterrows()}
                sel_hs_label = st.selectbox("Chọn Học sinh:", list(hs_dict_exp.keys()), key="sel_hs_label_exp_m")
                selected_hs_row = hs_dict_exp[sel_hs_label]
                selected_hs_exp = selected_hs_row['id']
                base_n_exp = get_base_name(selected_hs_row['ho_ten'])
                lop_n_exp = selected_hs_row['lop_hoc']
                target_title = f"{base_n_exp} - Lớp {lop_n_exp}"
                prefix_label = "Học sinh / Lớp: "
                safe_hs_name = re.sub(r'[\\/*?:"<>|]', "", f"{base_n_exp}_{lop_n_exp}".replace(" ", "_"))
                file_name_download = f"Thoi_Khoa_Bieu_{safe_hs_name}.png"

            df_export_list = get_schedule_list_df(engine, filter_lop=selected_lop_exp, filter_hs_id=selected_hs_exp)

            if df_export_list.empty:
                st.info("ℹ️ Không tìm thấy thời khóa biểu nào phù hợp đối với lựa chọn này.")
            else:
                st.write("📋 Xem trước danh sách lịch học:")
                st.dataframe(df_export_list, use_container_width=True)
                
                if HAS_MATPLOTLIB:
                    col_ex1, col_ex2 = st.columns(2)
                    with col_ex1:
                        img_bytes = create_list_schedule_image(target_title, df_export_list, prefix=prefix_label)
                        st.download_button(
                            label=f"🖼️ Tải Ảnh Thời Khóa Biểu ({target_title})",
                            data=img_bytes,
                            file_name=file_name_download,
                            mime="image/png",
                            type="primary"
                        )
                    with col_ex2:
                        st.markdown("##### 🖼️ Tải File ZIP Hàng Loạt")
                        zip_choice = st.radio("Chọn nội dung file ZIP:", ["Tất cả học sinh", "Tất cả các lớp"], horizontal=True, key="zip_choice_schedule")
                        
                        if zip_choice == "Tất cả học sinh":
                            if st.button("🖼️ Tải ZIP Thời Khóa Biểu TẤT CẢ Học Sinh", type="secondary"):
                                zip_buffer_s = io.BytesIO()
                                processed_base_names = set()
                                with zipfile.ZipFile(zip_buffer_s, "w", zipfile.ZIP_DEFLATED) as zf:
                                    for _, hs_r in df_hs_all.iterrows():
                                        hs_id_val = hs_r['id']
                                        hs_name_val = get_base_name(hs_r['ho_ten'])
                                        hs_lop_val = hs_r['lop_hoc']
                                        key_check = (hs_name_val.lower(), hs_lop_val.lower())
                                        if key_check in processed_base_names:
                                            continue
                                        processed_base_names.add(key_check)
                                        
                                        df_hs_list_item = get_schedule_list_df(engine, filter_hs_id=hs_id_val)
                                        if not df_hs_list_item.empty:
                                            img_hs_b = create_list_schedule_image(f"{hs_name_val} - Lớp {hs_lop_val}", df_hs_list_item, prefix="Học sinh / Lớp: ")
                                            safe_n = re.sub(r'[\\/*?:"<>|]', "", f"{hs_name_val}_{hs_lop_val}".replace(" ", "_"))
                                            zf.writestr(f"Thoi_Khoa_Bieu_{safe_n}.png", img_hs_b.getvalue())
                                zip_buffer_s.seek(0)
                                st.download_button(
                                    label="🖼️ Bấm Tải Xuống ZIP Tất Cả Học Sinh",
                                    data=zip_buffer_s,
                                    file_name=f"Tat_Ca_Thoi_Khoa_Bieu_Hoc_Sinh_{datetime.now().strftime('%Y%m%d')}.zip",
                                    mime="application/zip",
                                    type="primary",
                                    key="btn_download_zip_schedule_hs"
                                )
                        else:
                            if st.button("🖼️ Tải ZIP Thời Khóa Biểu TẤT CẢ Các Lớp", type="secondary"):
                                zip_buffer_l = io.BytesIO()
                                all_lops_list = sorted(df_hs_all['lop_hoc'].dropna().unique().tolist())
                                with zipfile.ZipFile(zip_buffer_l, "w", zipfile.ZIP_DEFLATED) as zf_l:
                                    for lop_val in all_lops_list:
                                        df_lop_list_item = get_schedule_list_df(engine, filter_lop=lop_val)
                                        if not df_lop_list_item.empty:
                                            img_lop_b = create_list_schedule_image(f"Lớp {lop_val}", df_lop_list_item, prefix="Lớp: ")
                                            safe_lop_n = re.sub(r'[\\/*?:"<>|]', "", f"{lop_val}".replace(" ", "_"))
                                            zf_l.writestr(f"Thoi_Khoa_Bieu_Lop_{safe_lop_n}.png", img_lop_b.getvalue())
                                zip_buffer_l.seek(0)
                                st.download_button(
                                    label="🖼️ Bấm Tải Xuống ZIP Tất Cả Các Lớp",
                                    data=zip_buffer_l,
                                    file_name=f"Tat_Ca_Thoi_Khoa_Bieu_Cac_Lop_{datetime.now().strftime('%Y%m%d')}.zip",
                                    mime="application/zip",
                                    type="primary",
                                    key="btn_download_zip_schedule_lop"
                                )

# =========================================================
# --- QUẢN LÝ HỌC PHÍ ---
# =========================================================
elif choice == "💳 Quản lý học phí":
    st.subheader("💳 Quản lý học phí & Xuất Hóa Đơn")
    st.markdown("---")
    
    df_hs_all = pd.read_sql_query(text("SELECT id, ho_ten, lop_hoc, mon_hoc, hoc_phi_buoi, thong_tin_phu_huynh FROM hoc_sinh ORDER BY id DESC"), engine)
    
    if df_hs_all.empty:
        st.warning("⚠️ Chưa có học sinh nào trong hệ thống.")
    else:
        # --- KHUNG EXPANDER THỐNG KÊ TOÀN BỘ HỌC SINH (THÁNG TRƯỚC & THÁNG NÀY) ---
        with st.expander("📊 Xem tổng hợp thống kê học phí Tháng trước & Tháng này của TOÀN BỘ HỌC SINH (Không liên quan đến trạng thái thanh toán)"):
            today_obj = date.today()
            curr_y_val, curr_m_val = today_obj.year, today_obj.month
            if curr_m_val == 1:
                prev_m_val = 12
                prev_y_val = curr_y_val - 1
            else:
                prev_m_val = curr_m_val - 1
                prev_y_val = curr_y_val

            prev_start = f"{prev_y_val}-{prev_m_val:02d}-01"
            if prev_m_val == 12:
                prev_end = f"{prev_y_val + 1}-01-01"
            else:
                prev_end = f"{prev_y_val}-{prev_m_val + 1:02d}-01"

            curr_start = f"{curr_y_val}-{curr_m_val:02d}-01"
            if curr_m_val == 12:
                curr_end = f"{curr_y_val + 1}-01-01"
            else:
                curr_end = f"{curr_y_val}-{curr_m_val + 1:02d}-01"

            df_all_prev = pd.read_sql_query(text(f'''
                SELECT SUM(h.hoc_phi_buoi) AS tong_tien, COUNT(d.id) AS tong_ca
                FROM diem_danh d
                JOIN hoc_sinh h ON d.hoc_sinh_id = h.id
                WHERE d.trang_thai = 'Có mặt'
                  AND d.ngay >= '{prev_start}' AND d.ngay < '{prev_end}'
            '''), engine)
            total_ca_prev_all = int(df_all_prev.iloc[0]['tong_ca']) if not df_all_prev.empty and pd.notna(df_all_prev.iloc[0]['tong_ca']) else 0
            total_tien_prev_all = float(df_all_prev.iloc[0]['tong_tien']) if not df_all_prev.empty and pd.notna(df_all_prev.iloc[0]['tong_tien']) else 0

            df_all_curr = pd.read_sql_query(text(f'''
                SELECT SUM(h.hoc_phi_buoi) AS tong_tien, COUNT(d.id) AS tong_ca
                FROM diem_danh d
                JOIN hoc_sinh h ON d.hoc_sinh_id = h.id
                WHERE d.trang_thai = 'Có mặt'
                  AND d.ngay >= '{curr_start}' AND d.ngay < '{curr_end}'
            '''), engine)
            total_ca_curr_all = int(df_all_curr.iloc[0]['tong_ca']) if not df_all_curr.empty and pd.notna(df_all_curr.iloc[0]['tong_ca']) else 0
            total_tien_curr_all = float(df_all_curr.iloc[0]['tong_tien']) if not df_all_curr.empty and pd.notna(df_all_curr.iloc[0]['tong_tien']) else 0

            col_st1, col_st2 = st.columns(2)
            with col_st1:
                st.markdown(f"##### 🗓️ Tháng trước ({prev_m_val:02d}/{prev_y_val})")
                st.metric("Tổng số buổi (Toàn bộ HS)", f"{total_ca_prev_all} buổi")
                st.metric("Tổng học phí phát sinh", f"{total_tien_prev_all:,.0f} đ")
            with col_st2:
                st.markdown(f"##### 🗓️ Tháng này ({curr_m_val:02d}/{curr_y_val})")
                st.metric("Tổng số buổi (Toàn bộ HS)", f"{total_ca_curr_all} buổi")
                st.metric("Tổng học phí phát sinh", f"{total_tien_curr_all:,.0f} đ")

        st.markdown("---")

        # --- CHUẨN BỊ DỮ LIỆU GIA ĐÌNH & THANH TOÁN CHO PHẦN TẢI HOÁ ĐƠN ĐỒNG LOẠT ---
        family_groups_summary = {}
        for _, hs_r in df_hs_all.iterrows():
            hs_id = hs_r['id']
            base_n = get_base_name(hs_r['ho_ten'])
            phone = str(hs_r['thong_tin_phu_huynh']).strip()
            if phone and phone.lower() not in ['none', 'nan', '']:
                f_key = (base_n.lower(), phone)
            else:
                f_key = (base_n.lower(), f"id_{hs_id}")
                
            if f_key not in family_groups_summary:
                family_groups_summary[f_key] = {
                    'family_name': base_n,
                    'lop': hs_r['lop_hoc'],
                    'phone': phone if phone and phone.lower() not in ['none', 'nan', ''] else 'Chưa có',
                    'student_ids': []
                }
            family_groups_summary[f_key]['student_ids'].append(hs_id)

        df_all_pay = pd.read_sql_query(text("SELECT hoc_sinh_id, thang_nam, trang_thai FROM thanh_toan"), engine)
        pay_dict_all = {(r['hoc_sinh_id'], r['thang_nam']): r['trang_thai'] for _, r in df_all_pay.iterrows()}

        # --- ĐƯA PHẦN TẢI HOÁ ĐƠN ĐỒNG LOẠT LÊN NGAY DƯỚI PHẦN TỔNG HỢP THỐNG KÊ ---
        st.markdown("#### 📦 Tải Hoá đơn đồng loạt")
        
        curr_date_z = date.today()
        if curr_date_z.month == 1:
            prev_m_z = 12
            prev_y_z = curr_date_z.year - 1
        else:
            prev_m_z = curr_date_z.month - 1
            prev_y_z = curr_date_z.year

        st.caption(f"• Học sinh **nợ học phí**: Hệ thống tự động tổng hợp toàn bộ số ca và học phí các tháng chưa đóng trong 1 năm qua tính đến hết tháng liền trước ({prev_m_z:02d}/{prev_y_z}).\n• Học sinh **không nợ phí**: Hệ thống tự động xuất hóa đơn cho tháng liền trước ({prev_m_z:02d}/{prev_y_z}).")
            
        if HAS_MATPLOTLIB:
            if st.button("🖼️ Tải Hoá đơn đồng loạt", type="primary", key="btn_download_zip_invoices"):
                zip_buffer_invoices = io.BytesIO()
                count_inv_added = 0
                
                curr_m_start_z = date(curr_date_z.year, curr_date_z.month, 1)
                debt_win_end_z = curr_m_start_z - timedelta(days=1)
                debt_win_start_z = debt_win_end_z - timedelta(days=365)
                
                with zipfile.ZipFile(zip_buffer_invoices, "w", zipfile.ZIP_DEFLATED) as zf_inv:
                    for f_key, f_info in family_groups_summary.items():
                        s_ids = f_info['student_ids']
                        s_ids_str_f = ",".join(map(str, s_ids))
                        family_name = f_info['family_name']
                        lop_val = f_info['lop']
                        
                        df_debt_f = pd.read_sql_query(text(f'''
                            SELECT hoc_sinh_id, ngay, TO_CHAR(ngay, 'MM/YYYY') AS thang_nam
                            FROM diem_danh
                            WHERE hoc_sinh_id IN ({s_ids_str_f}) 
                              AND trang_thai = 'Có mặt'
                              AND ngay >= '{debt_win_start_z.strftime("%Y-%m-%d")}'
                              AND ngay <= '{debt_win_end_z.strftime("%Y-%m-%d")}'
                        '''), engine)
                        
                        unpaid_month_set = set()
                        for _, att_r in df_debt_f.iterrows():
                            fid = att_r['hoc_sinh_id']
                            th_k = att_r['thang_nam']
                            p_st = pay_dict_all.get((fid, th_k), 'Chưa đóng')
                            if p_st != 'Đã đóng':
                                unpaid_month_set.add(th_k)
                                
                        target_month_keys_set = set()
                        if unpaid_month_set:
                            target_month_keys_set.update(unpaid_month_set)
                        else:
                            target_month_keys_set.add(f"{prev_m_z:02d}/{prev_y_z}")
                                
                        total_ca_f = 0
                        total_tien_f = 0
                        sub_comps_f_dict = {}
                        
                        sorted_target_months = sorted(list(target_month_keys_set), key=lambda x: (x.split('/')[1], x.split('/')[0]))
                        
                        for th_k_str in sorted_target_months:
                            m_part, y_part = th_k_str.split('/')
                            m_int, y_int = int(m_part), int(y_part)
                            m_start_f = f"{y_int}-{m_int:02d}-01"
                            m_end_f = f"{y_int + 1}-01-01" if m_int == 12 else f"{y_int}-{m_int + 1:02d}-01"
                            
                            for fid in s_ids:
                                f_meta = df_hs_all[df_hs_all['id'] == fid].iloc[0]
                                df_att_f = pd.read_sql_query(text(f'''
                                    SELECT COUNT(*) AS cnt FROM diem_danh
                                    WHERE hoc_sinh_id = {fid} AND trang_thai = 'Có mặt'
                                      AND ngay >= '{m_start_f}' AND ngay < '{m_end_f}'
                                '''), engine)
                                cnt_c = int(df_att_f.iloc[0]['cnt']) if not df_att_f.empty else 0
                                if cnt_c > 0:
                                    total_ca_f += cnt_c
                                    total_tien_f += cnt_c * f_meta['hoc_phi_buoi']
                                    n_key = f_meta["ho_ten"]
                                    sub_comps_f_dict[n_key] = sub_comps_f_dict.get(n_key, 0) + cnt_c
                                    
                        if total_ca_f > 0:
                            sub_comps_f = [{'ten': k, 'so_ca': v} for k, v in sub_comps_f_dict.items()]
                            
                            all_p_f = True
                            for fid in s_ids:
                                for th_k_str in sorted_target_months:
                                    p_match = pay_dict_all.get((fid, th_k_str), 'Chưa đóng')
                                    if p_match != 'Đã đóng':
                                        all_p_f = False
                                        break
                                if not all_p_f:
                                    break
                            stt_f_str = 'Đã đóng' if all_p_f else 'Chưa đóng'
                            
                            year_to_months = {}
                            for th_k_str in sorted_target_months:
                                m_part, y_part = th_k_str.split('/')
                                year_to_months.setdefault(y_part, []).append(m_part)
                            
                            time_str_parts = []
                            for y_p, m_list in year_to_months.items():
                                m_str = ",".join(m_list)
                                time_str_parts.append(f"tháng {m_str} năm {y_p}")
                            time_str_f = ", ".join(time_str_parts)
                            
                            img_inv_bytes = create_tuition_slip_image(
                                student_name=family_name,
                                lop_hoc=lop_val,
                                subject='Toán',
                                time_str=time_str_f,
                                total_lessons=total_ca_f,
                                total_fee=total_tien_f,
                                status=stt_f_str,
                                sub_components=sub_comps_f
                            )
                            safe_f_name = re.sub(r'[\\/*?:"<>|]', "", f"{family_name}_{lop_val}".replace(" ", "_"))
                            zf_inv.writestr(f"HoaDon_{safe_f_name}.png", img_inv_bytes.getvalue())
                            count_inv_added += 1
                            
                zip_buffer_invoices.seek(0)
                if count_inv_added > 0:
                    st.download_button(
                        label=f"📦 Bấm Tải Xuống ZIP Hóa Đơn ({count_inv_added} học sinh/gia đình)",
                        data=zip_buffer_invoices,
                        file_name=f"Tat_Ca_HoaDon_{datetime.now().strftime('%Y%m%d')}.zip",
                        mime="application/zip",
                        type="primary",
                        key="download_zip_invoices_button_final"
                    )
                    st.success(f"✅ Đã tạo file ZIP thành công với {count_inv_added} hóa đơn!")
                else:
                    st.warning("⚠️ Không có học sinh nào có buổi học trong các tháng hoặc khoản nợ để tạo hóa đơn.")

        st.markdown("---")

        c_cust1, c_cust2 = st.columns([2, 1])
        with c_cust1:
            hs_dict_custom = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row['id'] for _, row in df_hs_all.iterrows()}
            sel_cust_hs_label = st.selectbox("Chọn học sinh:", list(hs_dict_custom.keys()), key="sel_custom_invoice_hs")
        with c_cust2:
            cust_year = st.number_input("Chọn Năm", min_value=2020, max_value=2035, value=datetime.now().year, key="sel_custom_invoice_year")
        
        selected_cust_hs_id = hs_dict_custom[sel_cust_hs_label]
        family_ids_cust = get_family_student_ids(engine, selected_cust_hs_id)
        family_ids_cust_str = ",".join(map(str, family_ids_cust))
        
        selected_hs_meta = df_hs_all[df_hs_all['id'] == selected_cust_hs_id].iloc[0]
        
        today = date.today()
        curr_m_start = date(today.year, today.month, 1)
        debt_window_end = curr_m_start - timedelta(days=1)
        debt_window_start = debt_window_end - timedelta(days=365)
        
        df_att_unpaid_check = pd.read_sql_query(text(f'''
            SELECT DISTINCT TO_CHAR(ngay, 'MM') AS thang, TO_CHAR(ngay, 'YYYY') AS nam
            FROM diem_danh
            WHERE hoc_sinh_id IN ({family_ids_cust_str}) 
              AND trang_thai = 'Có mặt'
              AND ngay >= '{debt_window_start.strftime("%Y-%m-%d")}'
              AND ngay <= '{debt_window_end.strftime("%Y-%m-%d")}'
        '''), engine)
        
        df_pay_check = pd.read_sql_query(text(f'''
            SELECT hoc_sinh_id, thang_nam, trang_thai FROM thanh_toan
            WHERE hoc_sinh_id IN ({family_ids_cust_str})
        '''), engine)
        pay_status_dict = {(r['hoc_sinh_id'], r['thang_nam']): r['trang_thai'] for _, r in df_pay_check.iterrows()}

        default_months = []
        if not df_att_unpaid_check.empty:
            unpaid_set = set()
            for _, r in df_att_unpaid_check.iterrows():
                m_int = int(r['thang'])
                y_int = int(r['nam'])
                if y_int == cust_year:
                    th_k = f"{m_int:02d}/{cust_year}"
                    all_paid_m = True
                    for fid in family_ids_cust:
                        if pay_status_dict.get((fid, th_k), 'Chưa đóng') != 'Đã đóng':
                            all_paid_m = False
                            break
                    if not all_paid_m:
                        unpaid_set.add(m_int)
            default_months = sorted(list(unpaid_set))
        
        if not default_months:
            default_months = [today.month] if today.year == cust_year else [1]

        selected_months_list = st.multiselect(
            "Chọn các tháng cần gộp hóa đơn:",
            options=list(range(1, 13)),
            default=default_months,
            format_func=lambda x: f"Tháng {x}",
            key=f"sel_custom_invoice_months_{selected_cust_hs_id}"
        )
        
        if not selected_months_list:
            st.info("ℹ️ Vui lòng chọn ít nhất một tháng để xem và gộp hóa đơn.")
        else:
            sorted_months = sorted(selected_months_list)
            
            months_formatted = ", ".join([f"{m:02d}" for m in sorted_months])
            time_str_custom = f"tháng {months_formatted} năm {cust_year}"
            
            total_ca_cust = 0
            total_tien_cust = 0
            sub_comps_cust_dict = {}
            month_strs_keys = []
            
            for m in sorted_months:
                m_str_key = f"{m:02d}/{cust_year}"
                month_strs_keys.append(m_str_key)
                m_start = f"{cust_year}-{m:02d}-01"
                if m == 12:
                    m_end = f"{cust_year + 1}-01-01"
                else:
                    m_end = f"{cust_year}-{m + 1:02d}-01"
                    
                for fid in family_ids_cust:
                    f_meta = df_hs_all[df_hs_all['id'] == fid].iloc[0]
                    df_att_m = pd.read_sql_query(text(f'''
                        SELECT COUNT(*) AS cnt FROM diem_danh
                        WHERE hoc_sinh_id = {fid} AND trang_thai = 'Có mặt'
                          AND ngay >= '{m_start}' AND ngay < '{m_end}'
                    '''), engine)
                    cnt_ca = int(df_att_m.iloc[0]['cnt']) if not df_att_m.empty else 0
                    if cnt_ca > 0:
                        total_ca_cust += cnt_ca
                        total_tien_cust += cnt_ca * f_meta['hoc_phi_buoi']
                        name_key = f_meta["ho_ten"]
                        sub_comps_cust_dict[name_key] = sub_comps_cust_dict.get(name_key, 0) + cnt_ca

            sub_comps_cust = [{'ten': k, 'so_ca': v} for k, v in sub_comps_cust_dict.items()]
            
            df_pay_cust = pd.read_sql_query(text(f'''
                SELECT hoc_sinh_id, thang_nam, trang_thai FROM thanh_toan
                WHERE hoc_sinh_id IN ({family_ids_cust_str}) AND thang_nam IN ({','.join([f"'{ms}'" for ms in month_strs_keys])})
            '''), engine)
            
            all_paid = True
            for fid in family_ids_cust:
                for ms in month_strs_keys:
                    matched_p = df_pay_cust[(df_pay_cust['hoc_sinh_id'] == fid) & (df_pay_cust['thang_nam'] == ms)]
                    if matched_p.empty or matched_p.iloc[0]['trang_thai'] != 'Đã đóng':
                        all_paid = False
                        break
                if not all_paid:
                    break
                    
            status_cust_str = 'Đã đóng' if all_paid else 'Chưa đóng'
            
            st.markdown("---")
            st.markdown(f"#### 📄 Thông Tin Hóa Đơn Gộp: **{get_base_name(selected_hs_meta['ho_ten'])}**")
            
            col_info_c1, col_info_c2, col_info_c3, col_info_c4 = st.columns(4)
            col_info_c1.metric("⏱️ Thời gian gộp", time_str_custom)
            col_info_c2.metric("📚 Tổng số buổi học", f"{total_ca_cust} buổi")
            col_info_c3.metric("💰 Tổng tiền học phí", f"{total_tien_cust:,.0f} đ")
            col_info_c4.metric("📌 Trạng thái", "🟢 Đã đóng" if all_paid else "🔴 Chưa đóng")
            
            if sub_comps_cust:
                st.markdown("**Chi tiết buổi học theo học sinh:**")
                for sc in sub_comps_cust:
                    st.write(f"• {sc['ten']}: {sc['so_ca']} buổi")
            
            st.markdown("---")
            
            col_btn_c1, col_btn_c2 = st.columns(2)
            with col_btn_c1:
                btn_toggle_lbl = "🔄 Chuyển thành Chưa đóng" if all_paid else "✅ Xác nhận Đã đóng tất cả tháng chọn"
                if st.button(btn_toggle_lbl, type="primary", use_container_width=True, key="btn_toggle_custom_pay"):
                    new_stt_cust = 'Chưa đóng' if all_paid else 'Đã đóng'
                    t_str_cust = date.today().strftime("%Y-%m-%d") if new_stt_cust == 'Đã đóng' else ""
                    with engine.begin() as conn:
                        for fid in family_ids_cust:
                            for ms in month_strs_keys:
                                conn.execute(text('''
                                    INSERT INTO thanh_toan (hoc_sinh_id, thang_nam, trang_thai, ngay_thu)
                                    VALUES (:hs_id, :thang, :stt, :ngay)
                                    ON CONFLICT (hoc_sinh_id, thang_nam) 
                                    DO UPDATE SET trang_thai = EXCLUDED.trang_thai, ngay_thu = EXCLUDED.ngay_thu
                                '''), {"hs_id": fid, "thang": ms, "stt": new_stt_cust, "ngay": t_str_cust})
                    st.success("✅ Đã cập nhật trạng thái thanh toán cho các tháng được chọn!")
                    st.rerun()
                    
            with col_btn_c2:
                if HAS_MATPLOTLIB:
                    img_cust_bytes = create_tuition_slip_image(
                        student_name=get_base_name(selected_hs_meta['ho_ten']),
                        lop_hoc=selected_hs_meta['lop_hoc'],
                        subject=selected_hs_meta['mon_hoc'] or 'Toán',
                        time_str=time_str_custom,
                        total_lessons=total_ca_cust,
                        total_fee=total_tien_cust,
                        status=status_cust_str,
                        sub_components=sub_comps_cust
                    )
                    safe_name_cust = re.sub(r'[\\/*?:"<>|]', "", f"{get_base_name(selected_hs_meta['ho_ten'])}_{selected_hs_meta['lop_hoc']}_Thang_{sorted_months[0]}_den_{sorted_months[-1]}".replace(" ", "_"))
                    st.download_button(
                        label="🖼️ Tải Ảnh Hóa Đơn Gộp Các Tháng",
                        data=img_cust_bytes,
                        file_name=f"HoaDon_Gop_{safe_name_cust}.png",
                        mime="image/png",
                        type="primary",
                        use_container_width=True,
                        key="btn_download_custom_invoice_img"
                    )

            # --- DANH SÁCH TỔNG HỢP HỌC SINH ---
            st.markdown("---")
            st.markdown("#### 📋 Danh Sách Học Sinh & Tổng Hợp Học Phí")
            st.caption("• Học phí chưa đóng: Quét trong 1 năm qua (trừ tháng hiện tại)\n• Học phí tính cả tháng này: Bao gồm cả tháng hiện tại\n• Học sinh đã hoàn thành thanh toán được **in đậm và bôi xanh**.")

            curr_date = date.today()
            curr_m_start = date(curr_date.year, curr_date.month, 1)
            debt_win_end = curr_m_start - timedelta(days=1)
            debt_win_start = debt_win_end - timedelta(days=365)
            
            curr_month_str = f"{curr_date.year}-{curr_date.month:02d}"

            summary_list_data = []
            for f_key, f_info in family_groups_summary.items():
                s_ids = f_info['student_ids']
                s_ids_str = ",".join(map(str, s_ids))
                
                df_debt_1yr = pd.read_sql_query(text(f'''
                    SELECT hoc_sinh_id, ngay, TO_CHAR(ngay, 'MM/YYYY') AS thang_nam
                    FROM diem_danh
                    WHERE hoc_sinh_id IN ({s_ids_str}) 
                      AND trang_thai = 'Có mặt'
                      AND ngay >= '{debt_win_start.strftime("%Y-%m-%d")}'
                      AND ngay <= '{debt_win_end.strftime("%Y-%m-%d")}'
                '''), engine)
                
                debt_1yr_amount = 0
                has_debt_1yr = False
                for _, att_r in df_debt_1yr.iterrows():
                    fid = att_r['hoc_sinh_id']
                    th_k = att_r['thang_nam']
                    p_st = pay_dict_all.get((fid, th_k), 'Chưa đóng')
                    if p_st != 'Đã đóng':
                        has_debt_1yr = True
                        hp_b = df_hs_all[df_hs_all['id'] == fid].iloc[0]['hoc_phi_buoi']
                        debt_1yr_amount += hp_b

                df_att_curr = pd.read_sql_query(text(f'''
                    SELECT hoc_sinh_id, ngay, TO_CHAR(ngay, 'MM/YYYY') AS thang_nam
                    FROM diem_danh
                    WHERE hoc_sinh_id IN ({s_ids_str}) 
                      AND trang_thai = 'Có mặt'
                      AND TO_CHAR(ngay, 'YYYY-MM') = '{curr_month_str}'
                '''), engine)
                
                curr_month_amount = 0
                for _, att_r in df_att_curr.iterrows():
                    fid = att_r['hoc_sinh_id']
                    th_k = att_r['thang_nam']
                    p_st = pay_dict_all.get((fid, th_k), 'Chưa đóng')
                    if p_st != 'Đã đóng':
                        hp_b = df_hs_all[df_hs_all['id'] == fid].iloc[0]['hoc_phi_buoi']
                        curr_month_amount += hp_b
                        
                total_with_curr = debt_1yr_amount + curr_month_amount
                
                df_all_attended_months = pd.read_sql_query(text(f'''
                    SELECT DISTINCT TO_CHAR(ngay, 'MM/YYYY') AS thang_nam
                    FROM diem_danh
                    WHERE hoc_sinh_id IN ({s_ids_str}) 
                      AND trang_thai = 'Có mặt'
                      AND ngay >= '{debt_win_start.strftime("%Y-%m-%d")}'
                      AND ngay <= '{debt_win_end.strftime("%Y-%m-%d")}'
                '''), engine)
                
                all_attended_paid = True
                if not df_all_attended_months.empty:
                    for _, am_r in df_all_attended_months.iterrows():
                        th_k_check = am_r['thang_nam']
                        check_stt = pay_dict_all.get((s_ids[0], th_k_check), 'Chưa đóng')
                        if check_stt != 'Đã đóng':
                            all_attended_paid = False
                            break
                else:
                    all_attended_paid = False

                is_fully_paid = all_attended_paid and (debt_1yr_amount == 0)
                
                summary_list_data.append({
                    'Họ và Tên': f_info['family_name'],
                    'Lớp': f_info['lop'],
                    'SĐT Phụ huynh': f_info['phone'],
                    'Chưa đóng (1 năm trừ tháng này)': debt_1yr_amount,
                    'Tính cả tháng này': total_with_curr,
                    'Đã thanh toán': is_fully_paid
                })

            df_summary_render = pd.DataFrame(summary_list_data)
            if df_summary_render.empty:
                st.info("ℹ️ Không có dữ liệu học sinh.")
            else:
                html_table = "<div style='overflow-x: auto;'><table style='width:100%; border-collapse: collapse; font-size: 14px;'>"
                html_table += "<tr style='background-color: #1E3A8A; color: white; text-align: left;'><th style='padding: 10px; border: 1px solid #CBD5E1;'>Họ và Tên</th><th style='padding: 10px; border: 1px solid #CBD5E1;'>Lớp</th><th style='padding: 10px; border: 1px solid #CBD5E1;'>SĐT Phụ huynh</th><th style='padding: 10px; border: 1px solid #CBD5E1;'>Học phí chưa đóng (1 năm trừ tháng này)</th><th style='padding: 10px; border: 1px solid #CBD5E1;'>Học phí tính cả tháng này</th></tr>"
                
                for _, r in df_summary_render.iterrows():
                    is_paid = r['Đã thanh toán']
                    row_style = "background-color: #d1fae5; font-weight: bold; color: #065f46;" if is_paid else "background-color: white; color: #1e293b;"
                    
                    debt_1yr_str = f"{r['Chưa đóng (1 năm trừ tháng này)']:,.0f} đ"
                    total_curr_str = f"{r['Tính cả tháng này']:,.0f} đ"
                    
                    html_table += f"<tr style='{row_style}'>"
                    html_table += f"<td style='padding: 8px; border: 1px solid #CBD5E1;'>{r['Họ dan Tên'] if 'Họ dan Tên' in r else r['Họ và Tên']} {'(✅ Đã đóng)' if is_paid else ''}</td>"
                    html_table += f"<td style='padding: 8px; border: 1px solid #CBD5E1;'>{r['Lớp']}</td>"
                    html_table += f"<td style='padding: 8px; border: 1px solid #CBD5E1;'>{r['SĐT Phụ huynh']}</td>"
                    html_table += f"<td style='padding: 8px; border: 1px solid #CBD5E1;'>{debt_1yr_str}</td>"
                    html_table += f"<td style='padding: 8px; border: 1px solid #CBD5E1;'>{total_curr_str}</td>"
                    html_table += "</tr>"
                html_table += "</table></div>"
                
                st.markdown(html_table, unsafe_allow_html=True)

# =========================================================
# --- THÔNG TIN HỌC SINH ---
# =========================================================
elif choice == "📋 Thông tin học sinh":
    st.subheader("📋 Quản Lý & Tổng Quan Thông Tin Học Sinh")
    
    sub_tab_tongquan, sub_tab_them, sub_tab_sua, sub_tab_xoa = st.tabs([
        "📋 Tổng Quan Thông Tin", 
        "➕ Thêm Học Sinh", 
        "✏️ Sửa Thông Tin", 
        "❌ Xóa Học Sinh"
    ])
    
    with sub_tab_tongquan:
        st.markdown("##### 🔍 Chọn học sinh và thời gian để xem bảng thông tin tổng quát:")
        df_hs_all_info = pd.read_sql_query(text("SELECT id, ho_ten, lop_hoc, mon_hoc, hoc_phi_buoi, thong_tin_phu_huynh FROM hoc_sinh ORDER BY id DESC"), engine)
        
        if df_hs_all_info.empty:
            st.warning("⚠️ Chưa có học sinh nào trong hệ thống.")
        else:
            c_sel_hs, c_sel_y, c_sel_m = st.columns([2, 1, 2])
            with c_sel_hs:
                hs_info_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row['id'] for _, row in df_hs_all_info.iterrows()}
                selected_info_label = st.selectbox("Chọn học sinh:", list(hs_info_dict.keys()), key="select_hs_info_overview")
            with c_sel_y:
                info_year = st.number_input("Chọn Năm", min_value=2020, max_value=2035, value=datetime.now().year, key="info_year_pick")
            with c_sel_m:
                info_months = st.multiselect("Chọn Tháng xem:", list(range(1, 13)), default=[datetime.now().month], format_func=lambda x: f"Tháng {x}", key="info_months_pick")
            
            selected_hs_id = hs_info_dict[selected_info_label]
            family_ids_all = get_family_student_ids(engine, selected_hs_id)
            family_ids_str = ",".join(map(str, family_ids_all))
            
            selected_hs_row = df_hs_all_info[df_hs_all_info['id'] == selected_hs_id].iloc[0]
            base_name_overview = get_base_name(selected_hs_row['ho_ten'])
            
            st.markdown("---")
            st.markdown(f"### 👤 Bảng Tổng Quan Thông Tin: **{base_name_overview}** (Gộp nhóm gia đình)")
            
            c_info1, c_info2, c_info3 = st.columns(3)
            c_info1.metric("🏫 Lớp học", selected_hs_row['lop_hoc'] or "N/A")
            c_info2.metric("📚 Môn học", selected_hs_row['mon_hoc'] or "N/A")
            c_info3.metric("💵 Học phí/ca", f"{selected_hs_row['hoc_phi_buoi']:,.0f} đ")
            st.write(f"**📞 Số ĐT / Thông tin phụ huynh:** {selected_hs_row['thong_tin_phu_huynh'] or 'Chưa cập nhật'}")
            
            total_ca_selected_months = 0
            selected_month_details = []
            
            if info_months:
                for th in sorted(info_months):
                    th_q = f"{info_year}-{th:02d}"
                    th_k = f"{th:02d}/{info_year}"
                    
                    df_ca_m = pd.read_sql_query(text(f'''
                        SELECT COUNT(*) AS so_ca FROM diem_danh 
                        WHERE hoc_sinh_id IN ({family_ids_str}) AND TO_CHAR(ngay, 'YYYY-MM') = '{th_q}' AND trang_thai = 'Có mặt'
                    '''), engine)
                    so_ca_m = int(df_ca_m.iloc[0]['so_ca']) if not df_ca_m.empty else 0
                    total_ca_selected_months += so_ca_m
                    
                    df_pay_m = pd.read_sql_query(text(f'''
                        SELECT trang_thai FROM thanh_toan 
                        WHERE hoc_sinh_id IN ({family_ids_str}) AND thang_nam = '{th_k}'
                    '''), engine)
                    trang_thai_m = 'Đã đóng' if not df_pay_m.empty and all(df_pay_m['trang_thai'] == 'Đã đóng') else 'Chưa đóng'
                    
                    total_tien_m = sum(
                        pd.read_sql_query(text(f"SELECT COUNT(*) * (SELECT hoc_phi_buoi FROM hoc_sinh WHERE id = {fid}) AS s FROM diem_danh WHERE hoc_sinh_id = {fid} AND TO_CHAR(ngay, 'YYYY-MM') = '{th_q}' AND trang_thai = 'Có mặt'"), engine).iloc[0]['s'] or 0
                        for fid in family_ids_all
                    )
                    
                    selected_month_details.append({
                        'thang_key': th_k,
                        'so_ca': so_ca_m,
                        'thanh_tien': total_tien_m,
                        'trang_thai': trang_thai_m
                    })

            exclude_clauses = []
            for th in info_months:
                exclude_clauses.append(f"TO_CHAR(d.ngay, 'YYYY-MM') != '{info_year}-{th:02d}'")
            exclude_sql = " AND " + " AND ".join(exclude_clauses) if exclude_clauses else ""
            
            df_debt_other = pd.read_sql_query(text(f'''
                SELECT d.hoc_sinh_id, TO_CHAR(d.ngay, 'MM/YYYY') AS thang_nam, COUNT(d.id) AS so_ca
                FROM diem_danh d
                WHERE d.hoc_sinh_id IN ({family_ids_str})
                  AND d.trang_thai = 'Có mặt'
                  {exclude_sql}
                  AND NOT EXISTS (
                      SELECT 1 FROM thanh_toan t 
                      WHERE t.hoc_sinh_id = d.hoc_sinh_id 
                        AND t.thang_nam = TO_CHAR(d.ngay, 'MM/YYYY') 
                        AND t.trang_thai = 'Đã đóng'
                  )
                GROUP BY d.hoc_sinh_id, TO_CHAR(d.ngay, 'MM/YYYY')
            '''), engine)
            
            total_debt_other = 0
            if not df_debt_other.empty:
                for _, r_d in df_debt_other.iterrows():
                    hp_b = pd.read_sql_query(text(f"SELECT hoc_phi_buoi FROM hoc_sinh WHERE id = {r_d['hoc_sinh_id']}"), engine).iloc[0]['hoc_phi_buoi']
                    total_debt_other += r_d['so_ca'] * hp_b
            debt_other_str = f"{total_debt_other:,.0f} đ"
                
            total_fee_selected_months = sum(d['thanh_tien'] for d in selected_month_details)
            fee_selected_str = f"{total_fee_selected_months:,.0f} đ"

            c_stat1, c_stat2, c_stat3 = st.columns(3)
            c_stat1.metric("📚 Tổng số ca học trong tháng đã chọn", f"{total_ca_selected_months} ca")
            c_stat2.metric("💳 Học phí chưa đóng (Không gồm tháng chọn)", debt_other_str)
            c_stat3.metric("💰 Học phí tính đến hiện tại (Bao gồm tháng chọn)", fee_selected_str)
            
            st.markdown("---")
            
            st.markdown("#### 🗓️ Thời Khóa Biểu Cố Định Hàng Tuần (Gộp chung)")
            df_hs_sched = pd.read_sql_query(text(f'''
                SELECT h.ho_ten AS "Hồ sơ", l.thu AS "Thứ", l.ca_hoc AS "Ca học"
                FROM lich_hoc_tuan l
                JOIN hoc_sinh h ON l.hoc_sinh_id = h.id
                WHERE l.hoc_sinh_id IN ({family_ids_str})
                ORDER BY l.id
            '''), engine)
            if df_hs_sched.empty:
                st.info("ℹ️ Học sinh chưa có thời khóa biểu cố định nào.")
            else:
                st.dataframe(df_hs_sched, use_container_width=True)
                
            st.markdown("#### 📝 Lịch Sử Điểm Danh & Nhận Xét (Gộp chung)")
            df_hs_att_all = pd.read_sql_query(text(f'''
                SELECT h.ho_ten AS "Hồ sơ", TO_CHAR(d.ngay, 'DD/MM/YYYY') AS "Ngày", d.ca_hoc AS "Ca học", d.trang_thai AS "Trạng thái", COALESCE(d.nhan_xet, '') AS "Nhận xét"
                FROM diem_danh d
                JOIN hoc_sinh h ON d.hoc_sinh_id = h.id
                WHERE d.hoc_sinh_id IN ({family_ids_str})
                ORDER BY d.ngay DESC, d.id DESC
            '''), engine)
            if df_hs_att_all.empty:
                st.info("ℹ️ Chưa có lịch sử điểm danh nào.")
            else:
                df_hs_att_all['Nhận xét'] = df_hs_att_all['Nhận xét'].apply(clean_nhan_xet)
                st.dataframe(df_hs_att_all, use_container_width=True)

    with sub_tab_them:
        with st.form("form_add_student_full"):
            c1, c2 = st.columns(2)
            with c1:
                ten_new = st.text_input("Họ và tên học sinh (*)")
                lop_new = st.text_input("Lớp / Nhóm học", value="Toán 9")
                mon_new = st.text_input("Môn học", value="Toán")
            with c2:
                hoc_phi_new = st.number_input("Học phí mỗi ca (VNĐ)", min_value=0, step=10000, value=150000)
                thong_tin_phu_huynh_new = st.text_input("Số điện thoại / Thông tin phụ huynh (*)")
            
            if st.form_submit_button("💾 Thêm Học Sinh Mới", type="primary"):
                if ten_new.strip() and thong_tin_phu_huynh_new.strip():
                    with engine.begin() as conn:
                        conn.execute(text('''
                            INSERT INTO hoc_sinh (ho_ten, lop_hoc, mon_hoc, hoc_phi_buoi, thong_tin_phu_huynh)
                            VALUES (:ten, :lop, :mon, :hp, :ttph)
                        '''), {"ten": ten_new.strip(), "lop": lop_new.strip(), "mon": mon_new.strip(), "hp": hoc_phi_new, "ttph": thong_tin_phu_huynh_new.strip()})
                    st.success(f"✅ Đã thêm học sinh **{ten_new}** thành công!")
                    st.rerun()
                else:
                    st.warning("⚠️ Vui lòng nhập đầy đủ Tên học sinh và Số điện thoại phụ huynh!")

        st.markdown("---")
        st.markdown("##### 📋 Danh Sách Toàn Bộ Học Sinh Hiện Tại")
        df_hs_list_current = pd.read_sql_query(text('SELECT id AS "Mã HS", ho_ten AS "Họ và tên", lop_hoc AS "Lớp", mon_hoc AS "Môn", hoc_phi_buoi AS "Học phí/Ca (VNĐ)", thong_tin_phu_huynh AS "Số ĐT/Phụ huynh" FROM hoc_sinh ORDER BY id DESC'), engine)
        if df_hs_list_current.empty:
            st.info("Chưa có học sinh nào.")
        else:
            st.dataframe(df_hs_list_current, use_container_width=True)

    with sub_tab_sua:
        df_hs_edit = pd.read_sql_query(text("SELECT * FROM hoc_sinh ORDER BY id DESC"), engine)
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
                    thong_tin_phu_huynh_edit = st.text_input("Số điện thoại / Thông tin phụ huynh", value=selected_hs_row['thong_tin_phu_huynh'] or "")
                
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
        df_hs_del = pd.read_sql_query(text("SELECT id, ho_ten, lop_hoc FROM hoc_sinh ORDER BY id DESC"), engine)
        if not df_hs_del.empty:
            hs_del_dict = {f"{row['ho_ten']} [{row['lop_hoc']}] - ID:{row['id']}": row['id'] for _, row in df_hs_del.iterrows()}
            selected_del_id = hs_del_dict[st.selectbox("Chọn học sinh cần xóa:", list(hs_del_dict.keys()), key="select_del_hs")]
            confirm_check = st.checkbox("Tôi xác nhận muốn xóa học sinh này")
            
            if st.button("❌ XÓA HỌC SINH NÀY", type="primary") and confirm_check:
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM diem_danh WHERE hoc_sinh_id = :id"), {"id": selected_del_id})
                    conn.execute(text("DELETE FROM thanh_toan WHERE hoc_sinh_id = :id"), {"id": selected_del_id})
                    conn.execute(text("DELETE FROM lich_hoc_tuan WHERE hoc_sinh_id = :id"), {"id": selected_del_id})
                    conn.execute(text("DELETE FROM hoc_sinh WHERE id = :id"), {"id": selected_del_id})
                st.success("✅ Đã xóa thành công!")
                st.rerun()
