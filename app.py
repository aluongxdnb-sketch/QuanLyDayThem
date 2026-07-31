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
import random
import calendar

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

# --- KHO 30 THÔNG ĐIỆP TRUYỀN CẢM HỨNG CHO HỌC SINH ---
THONG_DIEP_LIST = [
    "🌟 'Học tập không phải là con đường đi đến hạnh phúc, mà hạnh phúc chính là hành trình học tập.' Chúc các em học sinh một ngày tràn đầy hứng khởi, sáng tạo và tiếp thu thật nhiều kiến thức bổ ích cùng cô!",
    "📖 'Kiến thức là tài sản quý giá nhất mà không ai có thể cướp đi được.' Các em hãy tự tin, chủ động và quyết tâm chinh phục từng bài học hôm hôm nay nhé!",
    "💡 'Không có thất bại, tất cả chỉ là bài học để trưởng thành.' Hãy luôn mạnh dạn đặt câu hỏi và cố gắng hết mình, cô luôn ở đây đồng hành cùng các em!",
    "🌱 'Mỗi ngày đến lớp là một bước tiến gần hơn đến ước mơ lớn của các em.' Chúc các em học sinh có những giờ học thật tập trung, hào hứng và hiệu quả!",
    "✨ 'Tương lai thuộc về những ai tin vào vẻ đẹp của những giấc mơ và nỗ lực vì nó.' Các em hãy tự tin vào bản thân, chăm chỉ rèn luyện mỗi ngày nhé!",
    "🎯 'Thành công không đến từ ngẫu nhiên, mà đến từ sự kiên trì và kỷ luật bản thân.' Cố lên các em học sinh yêu quý của cô!",
    "🚀 'Hãy học tập bằng sự say mê và tò mò khám phá, tri thức sẽ mở ra cho các em những chân trời mới rực rỡ!' Chúc các em một buổi học bùng nổ năng lượng!",
    "🔥 'Sự chăm chỉ và tập trung của các em hôm nay chính là chìa khóa vàng mở cánh cửa thành công trong tương lai. Cô tin tưởng các em sẽ làm được!'",
    "📘 'Mỗi bài toán khó, mỗi trang sách hay đều là thử thách giúp trí tuệ của các em sắc bén hơn.' Đừng ngại khó, hãy cùng cô vượt qua mọi thử thách nhé!",
    "🌈 'Cố gắng một chút mỗi ngày, tích tiểu thành đại, kết quả ngọt ngào sẽ đến với những ai không bao giờ bỏ cuộc. Chúc các em một ngày học tập thật rực rỡ!'",
    "⭐ 'Sự nỗ lực của bạn ngày hôm nay sẽ là nền tảng cho sự thành công của ngày mai. Cố gắng lên các em nhé!'",
    "📚 'Học cho chính mình, biết cho tương lai. Tri thức là sức mạnh giúp các em bay cao bay xa.'",
    "💪 'Đừng sợ những bài toán khó, chúng chỉ đang giúp bộ não của các em thông minh hơn mà thôi!'",
    "🌻 'Hãy tỏa sáng theo cách của riêng mình bằng sự chăm chỉ và ý chí vươn lên trong từng bài học.'",
    "✍️ 'Mỗi nét chữ, mỗi công thức ghi lại hôm nay là một bước chuẩn bị vững chắc cho hành trang tương lai.'",
    "🏆 'Người chiến thắng không phải là người không bao giờ vấp ngã, mà là người không bao giờ bỏ cuộc.'",
    "🌊 'Kiên trì như giọt nước mài mòn đá, sự học tích lũy từng ngày sẽ tạo nên kỳ tích.'",
    "🎨 'Hãy để tri thức tô điểm thêm màu sắc tươi đẹp cho ước mơ tuổi trẻ của các em.'",
    "🧭 'Sách vở là la bàn, còn sự chăm chỉ là con thuyền đưa các em đến bến bờ vinh quang.'",
    "⚡ 'Năng lượng tích cực và sự tập trung cao độ sẽ giúp các em giải quyết mọi bài toán khó nhằn nhất.'",
    "🍀 'Chúc các em học sinh có một buổi học tập hăng say, tiếp thu trọn vẹn những kiến thức mới bổ ích.'",
    "🎓 'Hôm nay chăm chỉ học hành, ngày mai tự tin bước ra thế giới với cái đầu ngẩng cao.'",
    "🔍 'Tò mò, ham học hỏi và dũng cảm đối mặt với khó khăn là bí quyết của những người thành công.'",
    "🎈 'Hãy thả lỏng tinh thần, hít một hơi thật sâu và cùng cô chinh phục những đỉnh cao tri thức mới nhé!'",
    "🧩 'Mỗi kiến thức mới giống mảnh ghép hoàn thiện bức tranh tương lai tuyệt đẹp của các em.'",
    "👑 'Chính sự kiên nhẫn và quyết tâm của các em trong giờ học hôm nay sẽ tạo nên phiên bản tuyệt vời nhất của ngày mai.'",
    "🎇 'Học tập là ánh sáng xua tan bóng tối của sự thiếu hiểu biết. Hãy luôn thắp sáng ngọn lửa ấy nhé!'",
    "📘 'Đừng ngại ngùng khi chưa hiểu bài, cô và các bạn luôn sẵn sàng giúp đỡ các em tiến bộ mỗi ngày.'",
    "🌟 'Mỗi một bài học vượt qua là một lần các em tự phá vỡ giới hạn của bản thân mình.'",
    "🚀 'Sẵn sàng tâm thế, vững vàng ý chí, chúc các em học sinh có một buổi học thật thành công và hứng khởi!'"
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
    "💖 Lời nhắc sức khỏe: Hãy tự nhắc bản thân rằng cô đã làm rất tốt ngày hôm nay, giờ là lúc thả lỏng và yêu chiều bản thân.",
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

# --- HÀM HỖ TRỢ LÀM SẠCH NHẬN XÉT (XÓA EMOJI, ĐỊNH DẠNG HOA/THƯỜNG, DẤU CHẤM) ---
def clean_nhan_xet(text_input):
    if not text_input:
        return ""
    emoji_pattern = re.compile(
        r"[\U00010000-\U0010ffff\u2600-\u27bf\u2b50\u2b06\u2934\u2935\u2b05\u2b07\u3299\u3227\u00a9\u00ae\u203c\u2049\u2122\u2139\u2194-\u2199\u21a9\u21aa\u2328\u23cf\u23e9-\u23f3\u23f8-\u23fa\u24c2\u25aa-\u25ab\u25b6\u25c0\u25fb-\u25fe\u2600-\u2604\u260e\u2611\u2614-\u2615\u2618\u261d\u2620\u2622-\u2623\u2626\u262a\u262e-\u262f\u2638-\u263a\u2648-\u2653\u2660-\u2668\u267b\u267f\u2692-\u2694\u2696-\u2697\u2699\u269b-\u269c\u26a0-\u26a1\u26aa-\u26ab\u26b0-\u26b1\u26bd-\u26be\u26c4-\u26c5\u26c8\u26ce-\u26cf\u26d1\u26d3-\u26d4\u26e9-\u26ea\u26f0-\u26f5\u26f7-\u26fa\u26fd\u2470\u2702\u2705\u2708-\u270d\u270f\u2712\u2714\u2716\u271d\u2721\u2728\u2733-\u2734\u2744\u2747\u274c\u274e\u2753-\u2755\u2757\u2763-\u2764\u2795-\u2797\u27a1\u27b0\u27bf\u2934-\u2935\u2b05-\u2b07\u2b12-\u2b13\u2b1b-\u2b1c\u2b50\u2b55\u3030\u303d\u3297\u3299]",
        flags=re.UNICODE
    )
    cleaned = emoji_pattern.sub(r'', text_input)
    cleaned = cleaned.replace('[', '').replace(']', '').strip()
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
        if not cleaned.endswith('.'):
            cleaned += '.'
    return cleaned

# --- HÀM HỖ TRỢ THỨ TRONG TUẦN ---
def get_vietnamese_weekday(dt):
    days = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ Nhật"]
    return days[dt.weekday()]

# --- HÀM XỬ LÝ GỘP NHÓM HỌC SINH THÔNG MINH (BẮT BUỘC TRÙNG SĐT, LOẠI BỎ TRỐNG) ---
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

# --- HÀM LẤY THỜI KHOÁ BIỂU HIỆU LỰC CHO MỘT NGÀY (LỊCH GỐC) ---
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

# --- HÀM ĐỒNG BỘ TỰ ĐỘNG KHI SANG TUẦN MỚI ---
def sync_weekly_schedule_to_google(calendar_id='a.luongxdnb@gmail.com', ref_date=None):
    if ref_date is None:
        ref_date = date.today()
        
    start_monday = ref_date - timedelta(days=ref_date.weekday())
    end_sunday = start_monday + timedelta(days=6)

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

        time_min = f"{start_monday.strftime('%Y-%m-%d')}T00:00:00Z"
        time_max = f"{end_sunday.strftime('%Y-%m-%d')}T23:59:59Z"

        events_result = service.events().list(
            calendarId=calendar_id, 
            timeMin=time_min, 
            timeMax=time_max, 
            singleEvents=True
        ).execute()

        old_events = events_result.get('items', [])
        for evt in old_events:
            summary_evt = evt.get('summary', '')
            if summary_evt.startswith("🏫 Dạy Thêm Ca") or summary_evt.startswith("📚 Lớp"):
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

        for i in range(7):
            current_date = start_monday + timedelta(days=i)
            df_day = get_active_schedule_for_date(engine, current_date, exclude_hoc_them=True)

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

        return True, f"✅ Đã đồng bộ tuần từ {start_monday.strftime('%d/%m')} đến {end_sunday.strftime('%d/%m/%Y')} ({count_events} sự kiện)!"
    except Exception as e:
        return False, f"❌ Lỗi khi đồng bộ: {str(e)}"

# --- HÀM ĐỒNG BỘ THỦ CÔNG ---
def sync_from_today_to_end_of_week(calendar_id='a.luongxdnb@gmail.com', ref_date=None):
    if ref_date is None:
        ref_date = date.today()
        
    start_monday = ref_date - timedelta(days=ref_date.weekday())
    end_sunday = start_monday + timedelta(days=6)

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

        time_clean_min = f"{start_monday.strftime('%Y-%m-%d')}T00:00:00Z"
        time_clean_max = f"{end_sunday.strftime('%Y-%m-%d')}T23:59:59Z"

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

        delta_days = (end_sunday - ref_date).days + 1
        for i in range(delta_days):
            current_date = ref_date + timedelta(days=i)
            df_day = get_active_schedule_for_date(engine, current_date, exclude_hoc_them=True)

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

        return True, f"✅ Đã dọn sạch {deleted_count} lịch cũ trong tuần này và đồng bộ mới từ {ref_date.strftime('%d/%m')} đến hết tuần ({count_events} sự kiện)!"
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

# --- HÀM LẤY DANH SÁCH LỊCH HỌC DẠNG BẢNG LIỆT KÊ (THỨ & CA HỌC) ---
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

# --- HÀM TẠO FILE ẢNH THỜI KHÓA BIỂU (CÓ ĐỦ THỜI GIAN, GHI CHÚ VÀ VIỀN CHUẨN) ---
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
    
    # Tiêu đề và thông tin thời gian đầy đủ
    ax.text(0.5, 0.88, "THỜI KHÓA BIỂU LỊCH HỌC HÀNG TUẦN", transform=fig.transFigure, 
            fontsize=17, fontweight='bold', color='#1E3A8A', ha='center', va='center')
    ax.text(0.5, 0.82, f"{prefix}{title_target}", transform=fig.transFigure, 
            fontsize=13, fontweight='bold', color='#0F172A', ha='center', va='center')
    ax.text(0.5, 0.77, week_str, transform=fig.transFigure, 
            fontsize=10.5, style='italic', color='#475569', ha='center', va='center')
    
    # Ghi chú dưới cùng chuẩn mẫu
    ax.text(0.5, 0.08, "Ghi chú: Lịch học được áp dụng ổn định cho các tuần tiếp theo nếu không có thay đổi tạm thời.", transform=fig.transFigure, 
            fontsize=9, style='italic', color='#64748B', ha='center', va='center')

    # Đường viền an toàn không bị đè chữ
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

# --- HÀM TẠO FILE ẢNH HÓA ĐƠN HỌC PHÍ (ÁP DỤNG VIỀN CHUẨN) ---
def create_tuition_slip_image(student_name, lop_hoc, subject, price_per_lesson, month_year, total_lessons, total_fee, status, qr_path, is_multi=False, details_list=None, sub_components=None):
    has_multiple_components = sub_components and len(sub_components) > 1
    fig, ax = plt.subplots(figsize=(8, 12 if (has_multiple_components or is_multi) else 10))
    ax.axis('off')
    
    ax.text(0.5, 0.95, "PHIẾU BÁO HỌC PHÍ DẠY THÊM", fontsize=16, fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    ax.text(0.5, 0.91, f"Thời gian: {month_year}", fontsize=12, fontweight='bold', color='#1E3A8A', ha='center', va='center', transform=ax.transAxes)
    
    details = [
        f"Họ và tên học sinh: {student_name}",
        f"Lớp / Nhóm học: {lop_hoc}",
        f"Môn học: {subject}"
    ]
    
    y_pos = 0.85
    for line in details:
        fontweight = 'bold' if 'Họ và tên' in line else 'normal'
        ax.text(0.1, y_pos, line, fontsize=11.5, fontweight=fontweight, color='#1E293B', transform=ax.transAxes)
        y_pos -= 0.045
        
    if has_multiple_components:
        ax.text(0.1, y_pos, "Chi tiết học phí các lớp/nhóm:", fontsize=11, fontweight='bold', color='#1E3A8A', transform=ax.transAxes)
        y_pos -= 0.04
        for sc in sub_components:
            line_sc = f"• {sc['ten']} (Lớp {sc['lop']}): {sc['so_ca']} ca x {sc['don_gia']:,.0f}đ = {sc['thanh_tien']:,.0f}đ"
            ax.text(0.12, y_pos, line_sc, fontsize=10, fontweight='normal', color='#1E293B', transform=ax.transAxes)
            y_pos -= 0.038
            
    if is_multi and details_list:
        ax.text(0.1, y_pos, "Chi tiết học phí các tháng:", fontsize=11, fontweight='bold', color='#1E3A8A', transform=ax.transAxes)
        y_pos -= 0.04
        for d in details_list:
            line_d = f"• Tháng {d['thang_key']}: {d['so_ca']} ca x {d['don_gia']:,.0f}đ = {d['thanh_tien']:,.0f}đ [{d['trang_thai']}]"
            ax.text(0.12, y_pos, line_d, fontsize=10, fontweight='normal', color='#1E293B', transform=ax.transAxes)
            y_pos -= 0.038
    
    summary_lines = [
        f"Tổng số ca học: {total_lessons} ca",
        f"TỔNG CỘNG HỌC PHÍ: {total_fee:,.0f} VNĐ",
        f"Trạng thái thanh toán: {status}"
    ]
    
    y_pos -= 0.02
    for line in summary_lines:
        fontweight = 'bold' if 'TỔNG CỘNG' in line else 'normal'
        color = '#B91C1C' if 'TỔNG CỘNG' in line else '#1E293B'
        ax.text(0.1, y_pos, line, fontsize=11.5, fontweight=fontweight, color=color, transform=ax.transAxes)
        y_pos -= 0.05
        
    if qr_path and os.path.exists(qr_path):
        try:
            img_arr = plt.imread(qr_path)
            ax_inset = fig.add_axes([0.35, 0.10, 0.3, 0.3])
            ax_inset.imshow(img_arr)
            ax_inset.axis('off')
            ax.text(0.5, 0.42, "Mã QR Thanh Toán Chuyển Khoản", fontsize=10, fontweight='bold', color='#1E3A8A', ha='center', transform=ax.transAxes)
        except Exception:
            pass
            
    ax.text(0.5, 0.03, "Trân trọng cảm ơn sự đồng hành của Quý phụ huynh!", fontsize=10.5, style='italic', fontweight='bold', color='#1E3A8A', ha='center', transform=ax.transAxes)
    
    # Viền khung ảnh
    from matplotlib.patches import Rectangle
    rect = Rectangle((0.03, 0.03), 0.94, 0.94, transform=fig.transFigure,
                     fill=False, color='#CBD5E1', linewidth=1.5, zorder=10)
    fig.patches.append(rect)

    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig)
    buffer.seek(0)
    return buffer

# --- HÀM TẠO FILE ẢNH LỊCH SỬ ĐIỂM DANH TỪNG HỌC SINH (ÁP DỤNG VIỀN CHUẨN) ---
def create_student_attendance_history_image(student_name, lop_hoc, month_year, df_history, total_present):
    wrapped_data = []
    max_lines_overall = 1
    for row in [df_history.columns.tolist()] + df_history.values.tolist():
        new_row = []
        row_max_lines = 1
        for col_idx, cell in enumerate(row):
            cell_str = str(cell)
            if col_idx == 3: # Cột Nhận xét
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

    # Viền khung ảnh
    from matplotlib.patches import Rectangle
    rect = Rectangle((0.03, 0.03), 0.94, 0.94, transform=fig.transFigure,
                     fill=False, color='#CBD5E1', linewidth=1.5, zorder=10)
    fig.patches.append(rect)
                
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig)
    buffer.seek(0)
    return buffer

# --- HÀM TẠO FILE ẢNH LỊCH SỬ ĐIỂM DANH CẢ LỚP (ĐÃ CẬP NHẬT KIỂU MỚI & CHỮ ' VÀ ') ---
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
            if col_idx == 4: # Cột Nhận xét
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

    fig, ax = plt.subplots(figsize=(11, max(6.0, len(df_history) * max(0.8, max_lines_overall * 0.45) + 4.5)))
    ax.axis('off')
    ax.axis('tight')
    
    # Tiêu đề và thông tin định dạng 3 dòng chuẩn mẫu
    ax.text(0.5, 0.88, "BẢNG TỔNG HỢP ĐIỂM DANH VÀ NHẬN XÉT CẢ LỚP", transform=fig.transFigure, 
            fontsize=17, fontweight='bold', color='#1E3A8A', ha='center', va='center')
    ax.text(0.5, 0.82, f"Lớp: {class_name}", transform=fig.transFigure, 
            fontsize=13, fontweight='bold', color='#0F172A', ha='center', va='center')
    ax.text(0.5, 0.77, f"({time_label})", transform=fig.transFigure, 
            fontsize=10.5, style='italic', color='#475569', ha='center', va='center')
    
    table = ax.table(cellText=wrapped_data, loc='center', cellLoc='center', colWidths=[0.15, 0.18, 0.22, 0.15, 0.30], bbox=[0.05, 0.12, 0.9, 0.60])
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

    # Viền khung ảnh
    from matplotlib.patches import Rectangle
    rect = Rectangle((0.03, 0.03), 0.94, 0.94, transform=fig.transFigure,
                     fill=False, color='#CBD5E1', linewidth=1.5, zorder=10)
    fig.patches.append(rect)
                
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)
    plt.close(fig)
    buffer.seek(0)
    return buffer

# --- KHỞI TẠO BẢNG TRÊN SUPABASE & TỰ ĐỘNG BỔ SUNG CỘT ---
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

# --- TỰ ĐỘNG CẬP NHẬT LỊCH TUẦN MỚI KHI BƯỚC SANG TUẦN MỚI ---
current_monday_str = (date.today() - timedelta(days=date.today().weekday())).strftime('%Y-%m-%d')
if "last_synced_monday" not in st.session_state or st.session_state.last_synced_monday != current_monday_str:
    with st.spinner("🔄 Đang tự động cập nhật thời khóa biểu tuần mới lên iPhone..."):
        _, _ = sync_weekly_schedule_to_google(calendar_id='a.luongxdnb@gmail.com', ref_date=date.today())
    st.session_state.last_synced_monday = current_monday_str

# --- GIAO DIỆN CHÍNH (ADMIN) ---
st.title("📚 Phần Mềm Quản Lý Dạy Thêm")

col_logout1, col_logout2 = st.sidebar.columns(2)
if col_logout1.button("🚪 Đăng xuất", type="secondary", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

menu = [
    "🏠 Trang chủ",
    "📝 Điểm danh & Nhận xét", 
    "📅 Quản lý Thời khoá Biểu",
    "💳 Quản lý học phí", 
    "📋 Thông tin học sinh"
]
choice = st.sidebar.selectbox("📋 Danh mục chức năng", menu)

# --- NÚT ĐỒNG BỘ THỦ CÔNG TẠI SIDEBAR ---
st.sidebar.markdown("---")
st.sidebar.subheader("📱 Đồng bộ thời khóa biểu tới iPhone")
user_gmail_sidebar = st.sidebar.text_input("Địa chỉ Gmail trên iPhone:", value="a.luongxdnb@gmail.com")
if st.sidebar.button("🔄 Đồng bộ (Dọn sạch tuần hiện tại & Cập nhật)", type="primary", use_container_width=True):
    with st.spinner("⏳ Đang dọn sạch lịch tuần hiện tại và đồng bộ lịch học mới..."):
        success_sync, msg_sync = sync_from_today_to_end_of_week(calendar_id=user_gmail_sidebar.strip(), ref_date=date.today())
        if success_sync:
            st.sidebar.success(msg_sync)
        else:
            st.sidebar.error(msg_sync)

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
# --- TRANG CHỦ ---
# =========================================================
if choice == "🏠 Trang chủ":
    st.subheader("🏠 Tổng Quan Trong Ngày")
    
    quote_today = random.choice(THONG_DIEP_LIST)
    health_today = random.choice(SUC_KHOE_LIST)
    
    st.info(f"💡 **Góc truyền cảm hứng hôm nay:**\n\n{quote_today}")
    st.success(f"💖 **Góc sức khỏe yêu thương:**\n\n{health_today}")
    st.markdown("---")

    today = date.today()
    thu_hom_nay = get_vietnamese_weekday(today)
    st.info(f"🗓️ Hôm nay: **{today.strftime('%d/%m/%Y')} ({thu_hom_nay})**")
    
    df_today = get_active_schedule_for_date(engine, today)
    
    curr_y, curr_m = today.year, today.month
    past_y, past_m = curr_y - 1, curr_m
    start_date_str = f"{past_y}-{past_m:02d}-01"
    end_date_str = f"{curr_y}-{curr_m:02d}-01"
    
    query_unpaid_details = text(f'''
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
    ''')
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
    
    st.markdown("#### 🚨 Cảnh Báo Vắng Nhiều Trong Tháng:")
    current_month_q = f"{today.year}-{today.month:02d}"
    
    df_absent_alert = pd.read_sql_query(text(f'''
        SELECT h.ho_ten AS "Họ và Tên", h.lop_hoc AS "Lớp", 
               SUM(CASE WHEN d.trang_thai = 'Vắng có phép' THEN 1 ELSE 0 END) AS "Vắng có phép",
               SUM(CASE WHEN d.trang_thai = 'Vắng không phép' THEN 1 ELSE 0 END) AS "Vắng không phép",
               (SUM(CASE WHEN d.trang_thai = 'Vắng có phép' THEN 1 ELSE 0 END) + SUM(CASE WHEN d.trang_thai = 'Vắng không phép' THEN 1 ELSE 0 END)) AS "Tổng vắng"
        FROM diem_danh d
        JOIN hoc_sinh h ON d.hoc_sinh_id = h.id
        WHERE TO_CHAR(d.ngay, 'YYYY-MM') = '{current_month_q}' AND d.trang_thai IN ('Vắng có phép', 'Vắng không phép')
        GROUP BY h.id, h.ho_ten, h.lop_hoc
        HAVING (SUM(CASE WHEN d.trang_thai = 'Vắng có phép' THEN 1 ELSE 0 END) + SUM(CASE WHEN d.trang_thai = 'Vắng không phép' THEN 1 ELSE 0 END)) >= 2
        ORDER BY "Vắng không phép" DESC, "Vắng có phép" DESC
    '''), engine)
    
    if df_absent_alert.empty:
        st.success("✅ Tháng này chưa có học sinh vắng nhiều.")
    else:
        st.dataframe(df_absent_alert, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### 📋 Chi Tiết Danh Sách Học Sinh Chưa Đóng Học Phí (1 Năm Qua, Trừ Tháng Này):")
    if df_unpaid_details.empty:
        st.success("✅ Tuyệt vời! Tất cả học sinh trong 1 năm qua (trừ tháng này) đã hoàn thành học phí.")
    else:
        display_debt_df = df_unpaid_details[['ho_ten', 'lop_hoc', 'thang_nam', 'so_ca', 'tien_no']].copy()
        display_debt_df.columns = ['Họ và Tên', 'Lớp', 'Tháng Chưa Đóng', 'Số Ca Học', 'Số Tiền Cần Thu (VNĐ)']
        display_debt_df['Số Tiền Cần Thu (VNĐ)'] = display_debt_df['Số Tiền Cần Thu (VNĐ)'].map('{:,.0f} đ'.format)
        st.dataframe(display_debt_df, use_container_width=True, hide_index=True)
        
    st.markdown("---")
    st.markdown("#### 🏫 Chi Tiết Thời Khóa Biểu & Học Sinh Hôm Nay (Sắp xếp từ sớm đến muộn):")
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
# --- ĐIỂM DANH & NHẬN XÉT ---
# =========================================================
elif choice == "📝 Điểm danh & Nhận xét":
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
                                "chăm chú", 
                                "có tiến bộ", 
                                "có giao bài tập", 
                                "không làm bài tập", 
                                "nói chuyện/ mất tập trung", 
                                "hoàn thành bài tập", 
                                "có làm bài tập nhưng chưa đủ", 
                                "buồn ngủ", 
                                "chểnh mảng", 
                                "lơ là học tập"
                            ]
                            selected_tags = st.multiselect("🏷️ Chọn nhanh thẻ thái độ:", tags_options, key=f"tags_cls_{row['hoc_sinh_id']}_{idx}")
                            custom_nx = st.text_input("Ghi chú thêm (Tự viết)", key=f"nx_cls_{row['hoc_sinh_id']}_{idx}", placeholder="Nhận xét bài học hoặc tự viết...")
                            
                            formatted_tags = []
                            for i, t in enumerate(selected_tags):
                                ct = t.strip().lower()
                                if i == 0:
                                    ct = ct.capitalize()
                                formatted_tags.append(ct)
                                
                            tag_str = ", ".join(formatted_tags)
                            if tag_str and custom_nx.strip():
                                nx_val = f"{tag_str} - {custom_nx.strip()}"
                            elif tag_str:
                                nx_val = tag_str
                            else:
                                nx_val = custom_nx.strip()
                                if nx_val:
                                    nx_val = nx_val[0].upper() + nx_val[1:]
                                    
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
            "chăm chú", 
            "có tiến bộ", 
            "có giao bài tập", 
            "không làm bài tập", 
            "nói chuyện/ mất tập trung", 
            "hoàn thành bài tập", 
            "có làm bài tập nhưng chưa đủ", 
            "buồn ngủ", 
            "chểnh mảng", 
            "lơ là học tập"
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
                    
                    if " - " in old_nx_full:
                        parts = old_nx_full.split(" - ", 1)
                        tags_str_part = parts[0]
                        custom_old_part = parts[1]
                    else:
                        tags_str_part = old_nx_full
                        custom_old_part = ""

                    for t in tags_options_global:
                        if t.lower() in old_nx_full.lower() or (t == "nói chuyện/ mất tập trung" and ("buồn ngủ/mất tập trung" in old_nx_full.lower() or "mất tập trung" in old_nx_full.lower())):
                            if t not in found_old_tags:
                                found_old_tags.append(t)

                    c_stt, c_tags, c_nx = st.columns([1.2, 2.5, 2.3])
                    stt_options = ["Có mặt", "Vắng có phép", "Vắng không phép"]
                    current_stt_idx = stt_options.index(r['Trạng Thái']) if r['Trạng Thái'] in stt_options else 0
                    
                    with c_stt:
                        new_stt = st.selectbox("Trạng thái", stt_options, index=current_stt_idx, key=f"batch_stt_{r['Mã Lịch']}")
                    with c_tags:
                        new_tags = st.multiselect("Thẻ thái độ", tags_options_global, default=found_old_tags, key=f"batch_tags_{r['Mã Lịch']}")
                    with c_nx:
                        new_custom_nx = st.text_input("Ghi chú thêm", value=custom_old_part.rstrip('.') if " - " in old_nx_full else "", key=f"batch_nx_{r['Mã Lịch']}")
                    
                    formatted_new_tags = []
                    for i, t in enumerate(new_tags):
                        ct = t.strip().lower()
                        if i == 0:
                            ct = ct.capitalize()
                        formatted_new_tags.append(ct)
                        
                    tag_str = ", ".join(formatted_new_tags)
                    if tag_str and new_custom_nx.strip():
                        new_nx_val = f"{tag_str} - {new_custom_nx.strip()}"
                    elif tag_str:
                        new_nx_val = tag_str
                    else:
                        new_nx_val = new_custom_nx.strip()
                        if new_nx_val:
                            new_nx_val = new_nx_val[0].upper() + new_nx_val[1:]
                            
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
                
                if " - " in old_nx_single:
                    parts_s = old_nx_single.split(" - ", 1)
                    tags_str_part_s = parts_s[0]
                    custom_single_part = parts_s[1]
                else:
                    tags_str_part_s = old_nx_single
                    custom_single_part = ""

                for t in tags_options_global:
                    if t.lower() in old_nx_single.lower() or (t == "nói chuyện/ mất tập trung" and ("buồn ngủ/mất tập trung" in old_nx_single.lower() or "mất tập trung" in old_nx_single.lower())):
                        if t not in found_single_tags:
                            found_single_tags.append(t)

                with st.form("form_edit_delete_diem_danh_record"):
                    st.write(f"Đang thao tác Mã Lịch **{log_to_edit_del}**: {row_log_item['Họ Tên']} [{row_log_item['Lớp']}] - Ngày: {row_log_item['Ngày']} - Ca: {row_log_item['Ca Học']}")
                    
                    stt_options = ["Có mặt", "Vắng có phép", "Vắng không phép"]
                    default_stt_idx = stt_options.index(row_log_item['Trạng Thái']) if row_log_item['Trạng Thái'] in stt_options else 0
                    
                    edit_stt_val = st.selectbox("Trạng thái mới:", stt_options, index=default_stt_idx, key="edit_log_stt")
                    edit_tags_val = st.multiselect("Thẻ thái độ mới:", tags_options_global, default=found_single_tags, key="edit_log_tags")
                    edit_custom_nx_val = st.text_input("Ghi chú thêm mới:", value=custom_single_part.rstrip('.') if " - " in old_nx_single else "", key="edit_log_custom_nx")
                    
                    formatted_edit_tags = []
                    for i, t in enumerate(edit_tags_val):
                        ct = t.strip().lower()
                        if i == 0:
                            ct = ct.capitalize()
                        formatted_edit_tags.append(ct)
                        
                    tag_str_single = ", ".join(formatted_edit_tags)
                    if tag_str_single and edit_custom_nx_val.strip():
                        edit_nx_val = f"{tag_str_single} - {edit_custom_nx_val.strip()}"
                    elif tag_str_single:
                        edit_nx_val = tag_str_single
                    else:
                        edit_nx_val = edit_custom_nx_val.strip()
                        if edit_nx_val:
                            edit_nx_val = edit_nx_val[0].upper() + edit_nx_val[1:]
                            
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
        st.subheader("🖼️ Xem Lịch Sử Điểm Danh & Xuất Ảnh (Từng học sinh hoặc Cả lớp tổng hợp)")
        
        export_mode_type = st.radio("📌 Chọn phạm vi xuất lịch sử điểm danh:", ["👤 Theo từng học sinh riêng lẻ", "🏫 Theo Cả Lớp học (Tổng hợp các ca)"], horizontal=True, key="export_mode_type_radio")
        
        df_hs_ls = pd.read_sql_query(text("SELECT id, ho_ten, lop_hoc FROM hoc_sinh ORDER BY id DESC"), engine)
        if df_hs_ls.empty:
            st.warning("Chưa có học sinh nào trong hệ thống.")
        else:
            if export_mode_type == "👤 Theo từng học sinh riêng lẻ":
                c_y_ls, c_m_ls = st.columns([1, 1])
                with c_y_ls:
                    nam_ls = st.number_input("Năm", min_value=2020, max_value=2035, value=datetime.now().year, key="nam_ls_pick")
                with c_m_ls:
                    thang_ls = st.selectbox("Tháng", list(range(1, 13)), index=datetime.now().month - 1, format_func=lambda x: f"Tháng {x}", key="thang_ls_pick")
                
                thang_nam_q = f"{nam_ls}-{thang_ls:02d}"
                thang_nam_k = f"{thang_ls:02d}/{nam_ls}"
                
                st.markdown("---")
                st.markdown("##### 🖼️ Xuất ZIP Hàng Loạt Ảnh Lịch Sử Điểm Danh Tất Cả Học Sinh Trong Tháng")
                if HAS_MATPLOTLIB:
                    if st.button("🖼️ Tải ZIP Lịch Sử Điểm Danh TẤT CẢ Học Sinh Có Điểm Danh", type="primary", key="btn_zip_all_attendance"):
                        zip_buffer_att = io.BytesIO()
                        count_added = 0
                        with zipfile.ZipFile(zip_buffer_att, "w", zipfile.ZIP_DEFLATED) as zf_att:
                            for _, hs_r in df_hs_ls.iterrows():
                                hs_id_val = hs_r['id']
                                hs_ids_to_check = get_family_student_ids(engine, hs_id_val)
                                ids_str = ",".join(map(str, hs_ids_to_check))
                                
                                hs_name_val = get_base_name(hs_r['ho_ten'])
                                hs_lop_val = hs_r['lop_hoc']
                                
                                df_hs_att_history = pd.read_sql_query(text(f'''
                                    SELECT 
                                        TO_CHAR(d.ngay, 'DD/MM/YYYY') AS "Ngày",
                                        d.ca_hoc AS "Ca học",
                                        d.trang_thai AS "Trạng thái",
                                        COALESCE(d.nhan_xet, '') AS "Nhận xét"
                                    FROM diem_danh d
                                    WHERE d.hoc_sinh_id IN ({ids_str}) AND TO_CHAR(d.ngay, 'YYYY-MM') = '{thang_nam_q}'
                                    ORDER BY d.ngay ASC, d.id ASC
                                '''), engine)
                                
                                if not df_hs_att_history.empty:
                                    df_hs_att_history['Nhận xét'] = df_hs_att_history['Nhận xét'].apply(clean_nhan_xet)
                                    total_co_mat = len(df_hs_att_history[df_hs_att_history['Trạng thái'] == 'Có mặt'])
                                    img_ls_bytes = create_student_attendance_history_image(
                                        student_name=hs_name_val,
                                        lop_hoc=hs_lop_val,
                                        month_year=thang_nam_k,
                                        df_history=df_hs_att_history,
                                        total_present=total_co_mat
                                    )
                                    safe_name_hs = re.sub(r'[\\/*?:"<>|]', "", f"{hs_name_val}_{hs_lop_val}".replace(" ", "_"))
                                    zf_att.writestr(f"Lich_Su_Diem_Danh_{safe_name_hs}_Thang_{thang_ls}_{nam_ls}.png", img_ls_bytes.getvalue())
                                    count_added += 1
                                    
                        zip_buffer_att.seek(0)
                        if count_added > 0:
                            st.download_button(
                                label=f"🖼️ Bấm Tải Xuống ZIP Lịch Sử Điểm Danh ({count_added} học sinh)",
                                data=zip_buffer_att,
                                file_name=f"Tat_Ca_Lich_Su_Diem_Danh_Thang_{thang_ls}_{nam_ls}.zip",
                                mime="application/zip",
                                type="primary",
                                key="download_zip_all_att_button"
                            )
                            st.success(f"✅ Đã tạo file ZIP thành công với {count_added} học sinh có dữ liệu điểm danh trong tháng!")
                        else:
                            st.warning("⚠️ Không có học sinh nào có lịch sử điểm danh trong tháng này.")

                st.markdown("---")
                st.markdown("##### 👤 Hoặc xem & tải chi tiết theo từng học sinh riêng lẻ:")
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

            else:
                st.markdown("##### 🏫 Xuất Bảng Điểm Danh Tổng Hợp Cả Lớp (Sắp xếp theo ngày, ca và học sinh)")
                all_lops_export = sorted(df_hs_ls['lop_hoc'].dropna().unique().tolist())
                if not all_lops_export:
                    st.warning("⚠️ Không có lớp học nào trong hệ thống.")
                else:
                    sel_lop_exp_cls = st.selectbox("Chọn Lớp học cần xuất:", all_lops_export, key="sel_lop_exp_cls_key")
                    option_time_cls = st.radio("Chọn khoảng thời gian xuất:", ["1 ngày", "1 tuần", "1 tháng"], horizontal=True, key="option_time_cls_radio")
                    
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
        st.markdown("### 🖼️ Tải Ảnh Thời Khóa Biểu Hàng Tuần (Kiểu Bảng Liệt Kê Mới)")
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
                st.dataframe(df_export_list, use_container_width=True, hide_index=True)
                
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
    st.subheader("💳 Quản lý học phí")
    
    che_do_xem = st.radio("⏱️ Chọn chế độ xem thống kê:", ["Theo Tháng", "Theo Tuần", "Theo Ngày"], horizontal=True)
    
    combined_df = pd.DataFrame()
    qr_path = "qr_code.png" if os.path.exists("qr_code.png") else None
    
    def get_aggregated_tuition_df(raw_df):
        if raw_df.empty:
            return raw_df
            
        df_hs_meta = pd.read_sql_query(text("SELECT id, ho_ten, thong_tin_phu_huynh FROM hoc_sinh"), engine)
        meta_dict = {row['id']: {'ho_ten': row['ho_ten'], 'thong_tin_phu_huynh': str(row['thong_tin_phu_huynh']).strip()} for _, row in df_hs_meta.iterrows()}
        
        grouped_dict = {}
        for _, row in raw_df.iterrows():
            hs_id = row['hoc_sinh_id']
            so_ca = int(row['Số Ca Có Mặt'])
            
            meta = meta_dict.get(hs_id, {'ho_ten': row['Họ và Tên'], 'thong_tin_phu_huynh': ''})
            base_n = get_base_name(meta['ho_ten'])
            phone = meta['thong_tin_phu_huynh']
            
            if phone and phone.lower() not in ['none', 'nan', '']:
                group_key = (base_n.lower(), phone)
            else:
                group_key = (base_n.lower(), f"id_{hs_id}")
            
            if group_key not in grouped_dict:
                grouped_dict[group_key] = {
                    'hoc_sinh_id': hs_id,
                    'family_ids': [hs_id],
                    'Họ và Tên': base_n,
                    'Lớp': row['Lớp'],
                    'Môn Học': row['Môn Học'],
                    'Đơn Giá/Ca (VNĐ)': row['Đơn Giá/Ca (VNĐ)'],
                    'Thời gian': row['Thời gian'],
                    'Số Ca Có Mặt': so_ca,
                    'Tổng Tiền (VNĐ)': float(row['Tổng Tiền (VNĐ)']),
                    'Trạng Thái': row['Trạng Thái'],
                    'is_multi': row.get('is_multi', False),
                    'details': row.get('details', []),
                    'sub_components': [] if so_ca == 0 else [{
                        'ten': row['Họ và Tên'],
                        'lop': row['Lớp'],
                        'so_ca': so_ca,
                        'don_gia': row['Đơn Giá/Ca (VNĐ)'],
                        'thanh_tien': float(row['Tổng Tiền (VNĐ)'])
                    }]
                }
            else:
                g = grouped_dict[group_key]
                if hs_id not in g['family_ids']:
                    g['family_ids'].append(hs_id)
                
                if so_ca > 0:
                    g['Số Ca Có Mặt'] += so_ca
                    g['Tổng Tiền (VNĐ)'] += float(row['Tổng Tiền (VNĐ)'])
                    if row['Lớp'] not in g['Lớp']:
                        g['Lớp'] = f"{g['Lớp']}, {row['Lớp']}"
                    g['sub_components'].append({
                        'ten': row['Họ và Tên'],
                        'lop': row['Lớp'],
                        'so_ca': so_ca,
                        'don_gia': row['Đơn Giá/Ca (VNĐ)'],
                        'thanh_tien': float(row['Tổng Tiền (VNĐ)'])
                    })
                    if row['Trạng Thái'] != g['Trạng Thái']:
                        g['Trạng Thái'] = 'Đóng một phần'
                        
        result_rows = []
        for g in grouped_dict.values():
            subs = g['sub_components']
            if len(subs) == 1:
                g['Họ và Tên'] = subs[0]['ten']
                g['Lớp'] = subs[0]['lop']
                g['Đơn Giá/Ca (VNĐ)'] = subs[0]['don_gia']
            elif len(subs) > 1:
                g['Lớp'] = ", ".join([s['lop'] for s in subs])
            result_rows.append(g)
            
        return pd.DataFrame(result_rows)

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
                
                q = text(f'''
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
                ''')
                raw_df = pd.read_sql_query(q, engine)
                raw_df['is_multi'] = False
                raw_df['details'] = [[] for _ in range(len(raw_df))]
                combined_df = get_aggregated_tuition_df(raw_df)
            else:
                df_hs_all = pd.read_sql_query(text("SELECT id AS hoc_sinh_id, ho_ten AS \"Họ và Tên\", lop_hoc AS \"Lớp\", mon_hoc AS \"Môn Học\", hoc_phi_buoi AS \"Đơn Giá/Ca (VNĐ)\" FROM hoc_sinh"), engine)
                rows_aggregated = []
                
                for _, hs in df_hs_all.iterrows():
                    hs_id = hs['hoc_sinh_id']
                    valid_month_details = []
                    total_ca_agg = 0
                    total_tien_agg = 0
                    
                    for th in sorted(selected_thangs):
                        thang_nam_query = f"{nam_selected}-{th:02d}"
                        thang_nam_key = f"{th:02d}/{nam_selected}"
                        
                        q_att = text(f'''
                            SELECT COUNT(*) AS so_ca
                            FROM diem_danh
                            WHERE hoc_sinh_id = {hs_id} AND TO_CHAR(ngay, 'YYYY-MM') = '{thang_nam_query}' AND trang_thai = 'Có mặt'
                        ''')
                        df_att = pd.read_sql_query(q_att, engine)
                        so_ca = int(df_att.iloc[0]['so_ca']) if not df_att.empty else 0
                        
                        if so_ca == 0:
                            continue
                            
                        q_pay = text(f'''
                            SELECT trang_thai FROM thanh_toan
                            WHERE hoc_sinh_id = {hs_id} AND thang_nam = '{thang_nam_key}'
                        ''')
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
                
                raw_df_multi = pd.DataFrame(rows_aggregated)
                combined_df = get_aggregated_tuition_df(raw_df_multi)

    elif che_do_xem == "Theo Ngày":
        ngay_chon = st.date_input("Chọn ngày thống kê:", date.today())
        ngay_str = ngay_chon.strftime("%Y-%m-%d")
        thang_nam_key = ngay_chon.strftime("%m/%Y")
        
        q = text(f'''
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
        ''')
        raw_df = pd.read_sql_query(q, engine)
        raw_df['is_multi'] = False
        raw_df['details'] = [[] for _ in range(len(raw_df))]
        combined_df = get_aggregated_tuition_df(raw_df)

    else:
        tuan_chon = st.date_input("Chọn ngày thuộc tuần cần xem:", date.today())
        start_w = tuan_chon - timedelta(days=tuan_chon.weekday())
        end_w = start_w + timedelta(days=6)
        start_str = start_w.strftime("%Y-%m-%d")
        end_str = end_w.strftime("%Y-%m-%d")
        thang_nam_key = start_w.strftime("%m/%Y")
        
        st.info(f"📅 Thống kê tuần từ **{start_w.strftime('%d/%m/%Y')}** đến **{end_w.strftime('%d/%m/%Y')}**")
        
        q = text(f'''
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
        ''')
        raw_df = pd.read_sql_query(q, engine)
        raw_df['is_multi'] = False
        raw_df['details'] = [[] for _ in range(len(raw_df))]
        combined_df = get_aggregated_tuition_df(raw_df)

    if not combined_df.empty:
        combined_df['lua_chon_lbl'] = combined_df['Họ và Tên'] + " [" + combined_df['Lớp'] + "]"
        all_student_options = sorted(combined_df['lua_chon_lbl'].unique().tolist())
    else:
        all_student_options = []

    selected_students_filter = st.multiselect("🔍 Chọn học sinh từ danh sách (để trống nếu muốn xem tất cả):", options=all_student_options)
    st.divider()

    if not combined_df.empty and selected_students_filter:
        combined_df = combined_df[combined_df['lua_chon_lbl'].isin(selected_students_filter)]

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
            if st.button("🖼️ Xuất ZIP Hàng Loạt Phiếu Thống Kê / Hóa Đơn", type="primary"):
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
                            details_list=row_fee.get('details', []),
                            sub_components=row_fee.get('sub_components', [])
                        )
                        safe_filename_time = str(row_fee['Thời gian']).replace('/', '_').replace(' - ', '_').replace(' ', '_')
                        safe_n_fee = re.sub(r'[\\/*?:"<>|]', "", f"{row_fee['Họ và Tên']}_{row_fee['Lớp']}_{safe_filename_time}".replace(" ", "_"))
                        zf_fee.writestr(f"Phieu_{safe_n_fee}.png", img_fee_b.getvalue())
                zip_buffer_f.seek(0)
                st.download_button(
                    label="🖼️ Bấm Tải Xuống File ZIP Hóa Đơn",
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
            avg_price = row['Tổng Tiền (VNĐ)'] / row['Số Ca Có Mặt'] if row['Số Ca Có Mặt'] > 0 else row['Đơn Giá/Ca (VNĐ)']
            c3.write(f"{avg_price:,.0f} đ (tb)")
            c4.write(f"**{row['Tổng Tiền (VNĐ)']:,.0f} đ**")
            
            is_multi = row.get('is_multi', False)
            details_list = row.get('details', [])
            family_ids = row.get('family_ids', [row['hoc_sinh_id']])
            
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
                        for fid in family_ids:
                            for d in details_list:
                                conn.execute(text('''
                                    INSERT INTO thanh_toan (hoc_sinh_id, thang_nam, trang_thai, ngay_thu)
                                    VALUES (:hs_id, :thang, :stt, :ngay)
                                    ON CONFLICT (hoc_sinh_id, thang_nam) 
                                    DO UPDATE SET trang_thai = EXCLUDED.trang_thai, ngay_thu = EXCLUDED.ngay_thu
                                '''), {"hs_id": fid, "thang": d['thang_key'], "stt": new_stt, "ngay": t_str})
                else:
                    new_stt = 'Chưa đóng' if (row['Trạng Thái'] == 'Đã đóng') else 'Đã đóng'
                    t_str = date.today().strftime("%Y-%m-%d") if new_stt == 'Đã đóng' else ""
                    thang_nam_key_save = row['Thời gian'] if '/' in str(row['Thời gian']) and len(str(row['Thời gian'])) <= 7 else datetime.now().strftime("%m/%Y")
                    with engine.begin() as conn:
                        for fid in family_ids:
                            conn.execute(text('''
                                INSERT INTO thanh_toan (hoc_sinh_id, thang_nam, trang_thai, ngay_thu)
                                VALUES (:hs_id, :thang, :stt, :ngay)
                                ON CONFLICT (hoc_sinh_id, thang_nam) 
                                DO UPDATE SET trang_thai = EXCLUDED.trang_thai, ngay_thu = EXCLUDED.ngay_thu
                            '''), {"hs_id": fid, "thang": thang_nam_key_save, "stt": new_stt, "ngay": t_str})
                st.rerun()

            with c7:
                if HAS_MATPLOTLIB:
                    img_bytes = create_tuition_slip_image(
                        student_name=row['Họ và Tên'],
                        lop_hoc=row['Lớp'],
                        subject=row['Môn Học'] or 'Chung',
                        price_per_lesson=avg_price,
                        month_year=row['Thời gian'],
                        total_lessons=row['Số Ca Có Mặt'],
                        total_fee=row['Tổng Tiền (VNĐ)'],
                        status=row['Trạng Thái'],
                        qr_path=qr_path,
                        is_multi=is_multi,
                        details_list=details_list,
                        sub_components=row.get('sub_components', [])
                    )
                    safe_filename_time = str(row['Thời gian']).replace('/', '_').replace(' - ', '_').replace(' ', '_')
                    safe_n_fee = re.sub(r'[\\/*?:"<>|]', "", f"{row['Họ và Tên']}_{row['Lớp']}_{safe_filename_time}".replace(" ", "_"))
                    st.download_button(
                        label="🖼️ Tải Ảnh Phiếu",
                        data=img_bytes,
                        file_name=f"Phieu_{safe_n_fee}.png",
                        mime="application/png",
                        key=f"img_fee_{row['hoc_sinh_id']}_{idx}"
                    )
            st.divider()

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
