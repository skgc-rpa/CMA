import os
import smtplib
from email.message import EmailMessage
import requests
import warnings
import urllib3
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timedelta
from io import StringIO
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

warnings.filterwarnings('ignore')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# 1. Session / Headers (멀티스레딩 & GitHub Actions 최적화)
# =========================================================
session = requests.Session()
session.verify = False

# GitHub Actions의 일시적 네트워크 오류와 멀티스레드 환경을 위한 어댑터 설정
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=retries)
session.mount('http://', adapter)
session.mount('https://', adapter)

headers = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Content-Type': 'application/x-www-form-urlencoded',
    'Referer': 'https://www.ccfgroup.com/member/member.php',
}

BASE_URL = "https://www.ccfgroup.com"

# =========================================================
# 2. Login Function
# =========================================================
def login_ccfgroup(session, headers, login_data):
    login_url = "https://www.ccfgroup.com/member/member.php"
    resp = session.post(login_url, data=login_data, headers=headers, timeout=30)
    resp.raise_for_status()
    return session

# =========================================================
# 3. Daily / Weekly Finder (lxml 파서 적용)
# =========================================================
today_date = datetime.today().date()
offset_days = 1
target_date = today_date - timedelta(days=offset_days)

def find_market_daily(list_url: str, title_prefix: str):
    resp = session.get(list_url, headers=headers, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    candidates = []

    for a in soup.find_all("a"):
        text = a.get_text(strip=True)
        if not text.startswith(title_prefix):
            continue
        try:
            date_str = text[text.find("(") + 1 : text.find(")")]
            post_date = datetime.strptime(date_str, "%b %d, %Y").date()
        except Exception:
            continue

        if post_date <= target_date:
            full_url = urljoin(BASE_URL, a.get("href"))
            candidates.append((post_date, full_url))

    if not candidates: return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]

def find_market_weekly(list_url: str, title_prefix: str):
    resp = session.get(list_url, headers=headers, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    for a in soup.find_all("a"):
        if a.get_text(strip=True).startswith(title_prefix):
            return urljoin(BASE_URL, a.get("href"))
    return None

# =========================================================
# 4. URL Extract (멀티스레딩 병렬 처리)
# =========================================================
url_tasks = {
    "pta_daily": ("daily", "https://www.ccfgroup.com/newscenter/index.php?Class_ID=100000&subclassid=100000&Prod_ID=100001", "PTA market daily"),
    "meg_daily": ("daily", "https://www.ccfgroup.com/newscenter/index.php?Class_ID=100000&subclassid=100000&Prod_ID=100002", "MEG market daily"),
    "yarn_daily": ("daily", "https://www.ccfgroup.com/newscenter/index.php?Class_ID=100000&subclassid=100000&Prod_ID=100005", "Polyester filament yarn market daily"),
    "fiber_daily": ("daily", "https://www.ccfgroup.com/newscenter/index.php?Class_ID=100000&subclassid=100000&Prod_ID=100006", "Polyester staple fiber market daily"),
    "bottle_daily": ("daily", "https://www.ccfgroup.com/newscenter/index.php?Class_ID=100000&subclassid=100000&Prod_ID=100004", "PET bottle chip market daily"),
    "px_weekly": ("weekly", "https://www.ccfgroup.com/newscenter/index.php?Class_ID=200000&subclassid=100000&Prod_ID=100001", "PX market weekly"),
    "yarn_weekly": ("weekly", "https://www.ccfgroup.com/newscenter/index.php?Class_ID=200000&subclassid=100000&Prod_ID=100005", "Polyester filament yarn market weekly"),
    "fiber_weekly": ("weekly", "https://www.ccfgroup.com/newscenter/index.php?Class_ID=200000&subclassid=100000&Prod_ID=100006", "Polyester staple fiber market weekly")
}

urls = {}
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {}
    for name, (type_, link, prefix) in url_tasks.items():
        if type_ == "daily":
            futures[executor.submit(find_market_daily, link, prefix)] = name
        else:
            futures[executor.submit(find_market_weekly, link, prefix)] = name
            
    for future in as_completed(futures):
        name = futures[future]
        urls[name] = future.result()

pta_daily = urls.get("pta_daily")
meg_daily = urls.get("meg_daily")
yarn_daily = urls.get("yarn_daily")
fiber_daily = urls.get("fiber_daily")
bottle_daily = urls.get("bottle_daily")
px_weekly = urls.get("px_weekly")
yarn_weekly = urls.get("yarn_weekly")
fiber_weekly = urls.get("fiber_weekly")

print("=== Extracted URLs (Parallel, No Login) ===")
for k, v in urls.items():
    print(f"{k}: {v}")
df_url = pd.Series(urls).to_frame(name='URL')

# =========================================================
# 5. Login (GitHub Secrets 환경변수 적용)
# =========================================================
USERNAME = os.environ.get("CCF_USER")
PASSWORD = os.environ.get("CCF_PASSWORD")

login_data = {
    'custlogin': '1',
    'action': 'login',
    'username': USERNAME,
    'password': PASSWORD,
    'savecookie': 'savecookie'
}

session = login_ccfgroup(session, headers, login_data)
print("✅ 로그인 완료 (session 유지됨)")

# =========================================================
# 6. 테이블 및 텍스트 데이터 추출 
# =========================================================
def fetch_tables_as_df(session, url, headers):
    if not url: return []
    resp = session.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    html_file_like = StringIO(resp.text)
    return pd.read_html(html_file_like, flavor='lxml')
    
def fetch_average_from_text(session, url, headers, start_marker, end_marker):
    if not url: return None
    try:
        # 웹 페이지 요청
        resp = session.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'lxml')
        content = soup.find('div', id='fontzoom')
        if not content: return None
        
        # 텍스트 추출 (줄바꿈을 공백으로 변환하여 연속된 문장으로 처리)
        text = content.get_text(separator=' ', strip=True)
        
        # 정규표현식 구성:
        # start_marker(assessed to) 뒤에 공백이 0개 이상(\s*) 올 수 있게 설정
        # (.*?)는 숫자 부분을 캡처
        # end_marker(near) 앞에 공백이 0개 이상(\s*) 올 수 있게 설정
        pattern = re.escape(start_marker.strip()) + r'\s*(.*?)\s*' + re.escape(end_marker.strip())
        
        match = re.search(pattern, text, re.IGNORECASE)
        
        if match:
            target_part = match.group(1)
            # 소수점을 포함한 모든 숫자 추출 (예: 10-20% -> 10.0, 20.0)
            nums = [float(n) for n in re.findall(r'\d+\.?\d*', target_part)]
            
            # 숫자 리스트의 평균 반환
            return sum(nums) / len(nums) if nums else None

        return None

    except Exception as e:
        # 에러 발생 시 로그를 남기고 None을 반환하여 전체 프로세스 중단 방지
        print(f"Error fetching average: {e}")
        return None
        
# =========================================================
# 8. 데이터 추출 (멀티스레딩 병렬 처리)
# =========================================================
fetch_tasks = {
    "pta_daily": pta_daily, "meg_daily": meg_daily, "yarn_daily": yarn_daily,
    "fiber_daily": fiber_daily, "bottle_daily": bottle_daily,
    "px_weekly": px_weekly, "yarn_weekly": yarn_weekly, "fiber_weekly": fiber_weekly
}

extracted_dfs = {}
yarn_avg = None

with ThreadPoolExecutor(max_workers=4) as executor:
    future_to_name = {executor.submit(fetch_tables_as_df, session, url, headers): name 
                      for name, url in fetch_tasks.items()}
    future_yarn_avg = executor.submit(fetch_average_from_text, session, yarn_daily, headers, 'assessed to ', ' near')
    
    for future in as_completed(future_to_name):
        name = future_to_name[future]
        extracted_dfs[name] = future.result()
        
    yarn_avg = future_yarn_avg.result()

df_pta_daily = extracted_dfs.get("pta_daily", [])
df_meg_daily = extracted_dfs.get("meg_daily", [])
df_yarn_daily = extracted_dfs.get("yarn_daily", [])
df_fiber_daily = extracted_dfs.get("fiber_daily", [])
df_bottle_daily = extracted_dfs.get("bottle_daily", [])
df_px_weekly = extracted_dfs.get("px_weekly", [])
df_yarn_weekly = extracted_dfs.get("yarn_weekly", [])
df_fiber_weekly = extracted_dfs.get("fiber_weekly", [])

print("✅ 본문 테이블 및 텍스트 데이터 병렬 수집 완료")

# =========================================================
# 9. 데이터프레임 처리 
# =========================================================
df_pta_daily_f = df_pta_daily[1].iloc[:4,:-1].reset_index(drop=True).pipe(lambda d: d.rename(columns=d.iloc[0]).drop(d.index[0]).reset_index(drop=True))
df_meg_daily_f = df_meg_daily[1].iloc[:-1,:].reset_index(drop=True).pipe(lambda d: d.rename(columns=d.iloc[0]).drop(d.index[0]).reset_index(drop=True))
df_yarn_daily_f = df_yarn_daily[1].iloc[:-1,:].reset_index(drop=True).pipe(lambda d: d.rename(columns=d.iloc[0]).drop(d.index[0]).reset_index(drop=True))
df_fiber_daily_f = df_fiber_daily[1].iloc[:-1,:].reset_index(drop=True).pipe(lambda d: d.rename(columns=d.iloc[0]).drop(d.index[0]).reset_index(drop=True))
df_bottle_daily_f = df_bottle_daily[1].iloc[:-1,:].reset_index(drop=True).pipe(lambda d: d.rename(columns=d.iloc[0]).drop(d.index[0]).reset_index(drop=True))

df_px_weekly_f = df_px_weekly[3].iloc[1:].T.drop_duplicates(keep='first').T.pipe(lambda d: d.set_axis(d.iloc[0], axis=1).iloc[1:]).reset_index(drop=True).rename(columns={None: 'Operating rate', 'NaN': 'Operating rate'}).rename(columns=lambda x: 'Operating rate' if pd.isna(x) or x == 'nan' else x)
df_yarn_weekly_f = df_yarn_weekly[3].T.drop_duplicates(keep='first').T.pipe(lambda df: df.set_axis(df.iloc[0], axis=1)).iloc[1:].reset_index(drop=True)
df_fiber_weekly_f = df_fiber_weekly[2].iloc[1:, :].T.drop_duplicates(keep='first').T.pipe(lambda df: df.set_axis(df.iloc[0], axis=1)).iloc[1:].reset_index(drop=True).pipe(lambda df: df.rename(columns={df.columns[0]: 'Index'}))

# 1. Margin Backdata
data_map_margin_backdata_1 = {
    "RMB | by cash, ex-CMP (yuan/mt)": df_pta_daily_f.iloc[0, 2],
    "Spot, East China": df_meg_daily_f.iloc[1, 1],
    "SD POY white | 150D/48F": df_yarn_daily_f.iloc[3, 4],
    "SD FDY white | 150D/96F": df_yarn_daily_f.iloc[11, 4],
    "SD DTY large companies white | 150D/48F,   non-intermingled": df_yarn_daily_f.iloc[19, 4],
    "Virgin   PSF 1.4D*38mm | Daily average(yuan/mt by cash ex-works)": df_fiber_daily_f.iloc[0, 1],
    "PET water/hot fill bottle chip, by cash EXW": df_bottle_daily_f.iloc[0, 2],
}
df_px_margin_backdata = pd.Series(data_map_margin_backdata_1).to_frame(name='Value')
data_map_margin_backdata_2 = {
    "RMB | by cash, ex-CMP (yuan/mt)": df_pta_daily[0].iloc[0, 0].split('(')[1].split(')')[0],
    "Spot, East China": df_meg_daily[0].iloc[0, 0].split('(')[1].split(')')[0],
    "SD POY white | 150D/48F": df_yarn_daily_f.columns[4],
    "SD FDY white | 150D/96F": df_yarn_daily_f.columns[4],
    "SD DTY large companies white | 150D/48F,   non-intermingled": df_yarn_daily_f.columns[4],
    "Virgin   PSF 1.4D*38mm | Daily average(yuan/mt by cash ex-works)": df_fiber_daily[0].iloc[0, 0].split('(')[1].split(')')[0],
    "PET water/hot fill bottle chip, by cash EXW": df_bottle_daily[0].iloc[0, 0].split('(')[1].split(')')[0],
}
df_px_margin_backdata['Date'] = df_px_margin_backdata.index.map(data_map_margin_backdata_2)
df_px_margin_backdata['Value'] = df_px_margin_backdata['Value'].astype(float)

# 2. Margin
px_margin_calc = (0.855*df_px_margin_backdata.iloc[0, 0]) + (0.335*df_px_margin_backdata.iloc[1, 0])
data_map_margin_1 = {
    "POY margin": df_px_margin_backdata.iloc[2, 0] - (px_margin_calc + 1150),
    "FDY margin": df_px_margin_backdata.iloc[3, 0] - (px_margin_calc + 1550),
    "DTY margin": df_px_margin_backdata.iloc[4, 0] - (px_margin_calc + 2450),
    "PSF margin": df_px_margin_backdata.iloc[5, 0] - (px_margin_calc + 900),
    "PET Bottle Chip margin": df_px_margin_backdata.iloc[6, 0] - (px_margin_calc + 700),
    "Polyester 복합 margin": 0
}
df_px_margin = pd.Series(data_map_margin_1).to_frame(name='Value')
df_px_margin.iloc[5,0] = (0.16 * df_px_margin.iloc[0, 0]) + (0.28 * df_px_margin.iloc[1, 0]) + (0.16 * df_px_margin.iloc[2, 0]) + (0.22 * df_px_margin.iloc[3, 0]) + (0.17 * df_px_margin.iloc[4, 0])

# 3. Final Result
data_map_px_1 = {
    "중국 PX": df_px_weekly_f.iloc[0, 1],
    "중국 PTA": df_px_weekly_f.iloc[2, 1],
    "중국 Polyester": df_px_weekly_f.iloc[3, 1],
    "Polyester Filament Yarn": df_yarn_weekly_f.iloc[2, 3],
    "Polyester Staple Fiber": df_fiber_weekly_f.iloc[1, 4],
    "강소/절강 Texturing machine": df_yarn_weekly_f.iloc[8, 3],
    "강소/절강 DTY Machine": df_yarn_weekly_f.iloc[7, 3],
    "중국 Polyester Fiber Yarn": yarn_avg,
    "POY": df_yarn_weekly_f.iloc[4, 3],
    "FDY": df_yarn_weekly_f.iloc[5, 3],
    "DTY": df_yarn_weekly_f.iloc[6, 3],
    "PSF": df_fiber_weekly_f.iloc[0, 4],
    "Polyester 복합": df_px_margin.iloc[5,0],
    "장섬유": df_px_margin.iloc[0,0],
    "단섬유": df_px_margin.iloc[3,0],
    "Bottle Chip": df_px_margin.iloc[4,0]
}
df_px_result = pd.Series(data_map_px_1).to_frame(name='Value')
data_map_px_2 = {
    "중국 PX": df_px_weekly_f.columns[1],
    "중국 PTA": df_px_weekly_f.columns[1],
    "중국 Polyester": df_px_weekly_f.columns[1],
    "Polyester Filament Yarn": df_yarn_weekly_f.columns[3],
    "Polyester Staple Fiber": df_fiber_weekly_f.columns[4],
    "강소/절강 Texturing machine": df_yarn_weekly_f.columns[3],
    "강소/절강 DTY Machine": df_yarn_weekly_f.columns[3],
    "중국 Polyester Fiber Yarn": df_yarn_daily_f.columns[4],
    "POY": df_yarn_weekly_f.columns[3],
    "FDY": df_yarn_weekly_f.columns[3],
    "DTY": df_yarn_weekly_f.columns[3],
    "PSF": df_fiber_weekly_f.columns[4],
    "Polyester 복합": "",
    "장섬유": "",
    "단섬유": "",
    "Bottle Chip": ""
}
df_px_result['Date'] = df_px_result.index.map(data_map_px_2)
df_px_result['Value'] = df_px_result['Value'].astype(float).round(2)

today_str = datetime.now().strftime('%Y-%m-%d')
file_name = f"px_result_{today_str}.xlsx"

targets = {"px_result": df_px_result, "px_margin": df_px_margin, 
           "px_margin_backdata": df_px_margin_backdata, "url": df_url}

with pd.ExcelWriter(file_name, engine='xlsxwriter') as writer:
    workbook = writer.book
    
    border_format = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
    header_format = workbook.add_format({'bold': True, 'bg_color': '#BCD1E4', 'border': 1, 'align': 'center'})

    for sheet_name, df in targets.items():
        df.to_excel(writer, sheet_name=sheet_name, index=True)
        worksheet = writer.sheets[sheet_name]
        
        rows, cols = df.shape
        worksheet.conditional_format(0, 0, rows, cols, {
            'type': 'formula',
            'criteria': '=1',
            'format': border_format
        })
        
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num + 1, value, header_format)
        worksheet.write(0, 0, df.index.name or 'Index', header_format)

        idx_max_len = max(df.index.astype(str).map(len).max(), len(str(df.index.name or "Index"))) + 3
        worksheet.set_column(0, 0, idx_max_len)
        
        for i, col in enumerate(df.columns):
            column_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 3
            worksheet.set_column(i + 1, i + 1, column_len)

print(f"✅ '{file_name}' 저장 완료!")

# =========================================================
# 10. 이메일 발송 (Gmail 앱 비밀번호 사용)
# =========================================================
print("=== 메일 발송 준비 ===")

sender_email = os.environ.get("GMAIL_USER")
app_password = os.environ.get("GMAIL_APP_PASSWORD")

# 수신처(To)와 참조처(Cc) 설정 
# to_emails = "jp_lee@sk.com"
# cc_emails = "jp_lee@sk.com"
to_emails = "michael.park@sk.com, jsoh@sk.com, hoseok@sk.com, hyo548@sk.com"
cc_emails = "youngchoi@sk.com, carly1206@sk.com, rchangjo@sk.com, cr7@sk.com, jp_lee@sk.com"

# 메일 제목 (yyyy-mm-dd 형식)
subject = f"PX CCF {today_str}"

# 1. 데이터프레임을 HTML 표로 변환
html_table = df_px_result.to_html(justify='center', index=True)

# 2. Pandas가 자동 생성한 table 태그를 원하는 인라인 스타일이 적용된 태그로 교체
# (이메일 클라이언트는 외부 CSS나 style 태그보다 인라인 스타일을 더 잘 인식합니다)
custom_table_tag = '<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse; text-align:center; font-family:Calibri, Arial, sans-serif; font-size:13px;">'
html_table = html_table.replace('<table border="1" class="dataframe">', custom_table_tag)

# 3. HTML 이메일 본문 생성
html_body = f"""
<html>
<body style="margin:0; padding:0;">

    <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
            <td style="padding:20px;
                       font-family:Calibri, Arial, sans-serif;
                       font-size:14px;
                       color:#000000;">

                안녕하세요,<br><br>

                오늘자 CCF 추출 결과입니다.<br>
                상세 내용은 첨부파일을 확인해 주시기 바랍니다.<br><br>

                {html_table}

            </td>
        </tr>
    </table>

</body>
</html>
"""

# 메일 객체 생성 및 설정
msg = EmailMessage()
msg['Subject'] = subject
msg['From'] = sender_email
msg['To'] = to_emails    # 수신처 변수 할당
msg['Cc'] = cc_emails    # 참조처 변수 할당
msg.set_content("HTML 뷰어를 지원하는 메일 클라이언트를 사용해 주세요.") # Fallback 텍스트
msg.add_alternative(html_body, subtype='html')

# 작성된 엑셀 파일 첨부
with open(file_name, 'rb') as f:
    excel_data = f.read()
    
msg.add_attachment(
    excel_data, 
    maintype='application', 
    subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
    filename=file_name
)

# SMTP 서버 연결 및 전송
if sender_email and app_password:
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(sender_email, app_password)
            smtp.send_message(msg)
        print("✅ 이메일 발송 완료!")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")
else:
    print("⚠️ GMAIL_USER 또는 GMAIL_APP_PASSWORD 환경변수가 설정되지 않아 메일을 발송하지 않았습니다.")
