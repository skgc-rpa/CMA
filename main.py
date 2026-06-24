import os
import asyncio
import requests
import nest_asyncio
import re
import urllib3
import io
import smtplib
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from openpyxl.styles import Border, Side, PatternFill, Alignment, Font
from email.message import EmailMessage

# SSL 경고 메세지 무시
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
nest_asyncio.apply()

def get_dow_jones_sso_url():
    """requests를 사용하여 로그인 버튼 클릭을 시뮬레이션하고 SSO 리다이렉트 URL을 가져옵니다."""
    session = requests.Session()
    session.verify = False 
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    target_url = "https://cma.opisnet.com" 
    try:
        print(f"[{target_url}] 접속하여 SSO 리다이렉트 URL 확인 중...")
        response = session.get(target_url, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        form = soup.find('form')
        if not form:
            return None

        payload = {}
        for hidden_input in form.find_all('input', type='hidden'):
            name = hidden_input.get('name')
            value = hidden_input.get('value', '')
            if name:
                payload[name] = value
                
        payload['dow_jones_idp'] = 'Log in with Dow Jones'
        
        action_url = form.get('action')
        if not action_url or action_url == '/':
            action_url = target_url
        elif action_url.startswith('/'):
            action_url = target_url.rstrip('/') + action_url

        post_response = session.post(action_url, data=payload, allow_redirects=False, timeout=30)
        
        if post_response.status_code in (301, 302, 303, 307):
            return post_response.headers.get('Location')
    except Exception as e:
        print(f"⚠️ SSO URL 획득 실패: {e}")
    return None

async def get_links_and_cookies_with_retry(max_retries=5):
    attempt = 0
    while attempt < max_retries:
        attempt += 1
        print(f"\n[{attempt}/{max_retries}] 전체 프로세스 시도 중 (브라우저 재시작 포함)...")
        
        try:
            # 1. requests로 SSO URL을 미리 따옴
            sso_url = get_dow_jones_sso_url()
            if not sso_url:
                print("   ⚠️ SSO URL을 가져오지 못했습니다. 잠시 후 다시 시도합니다.")
                await asyncio.sleep(5)
                if attempt < max_retries: continue
                else: raise Exception("SSO URL 획득 최종 실패")

            # 2. 브라우저 실행 단계 (깃허브 액션즈 환경을 위해 headless=True 고정)
            async with async_playwright() as p:
                print(f"브라우저를 실행합니다 (headless=True)...")
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                # 3. 획득한 SSO URL로 직접 접속
                print(f"SSO 페이지로 직접 접속합니다...")
                await page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
                
                # 4. 로그인 정보 입력 (환경변수 로드)
                cma_user = os.environ.get("CMA_USER")
                cma_password = os.environ.get("CMA_PASSWORD")
                
                # 만약 GitHub Secrets 설정 전이라면 로컬 테스트용 백업 계정 사용
                if not cma_user or not cma_password:
                    print("⚠️ 환경변수가 확인되지 않아 하드코딩된 계정 정보로 로그인을 시도합니다.")
                    cma_user = 'jp_lee@skgeocentric.com'
                    cma_password = '!ghkgkr8896'

                email_selector = 'input[name="emailOrUserID"], #email'
                await page.wait_for_selector(email_selector, state="visible", timeout=30000)
                
                print("계정 정보 입력 중...")
                await page.fill(email_selector, cma_user)
                password_selector = 'input[type="password"], #password-form-item'
                await page.wait_for_selector(password_selector, state="visible", timeout=15000)
                await page.fill(password_selector, cma_password)
                await page.press(password_selector, 'Enter')

                print("로그인 완료 대기 중...")
                await page.wait_for_url(lambda url: "cma.opisnet.com" in url and "login" not in url.lower(), timeout=45000)
                
                # 5. 목록 페이지 이동 및 링크 추출
                list_url = "https://cma.opisnet.com/publications/market-advisory-service?page=1&itemsPerPage=100"
                print(f"목록 페이지 로딩 중... ({list_url})")
                await page.goto(list_url, wait_until="domcontentloaded", timeout=60000)
                
                await page.wait_for_selector('a:has-text("Daily North America")', timeout=30000)
                await page.wait_for_timeout(2000)

                print("최신 보고서 링크 추출 중...")
                daily_node = page.locator('a:has-text("Daily North America")').first
                weekly_node = page.locator('a:has-text("Global Aromatics - Weekly Market Report")').first
                monthly_node = page.locator('a:has-text("North America Aromatics - Benzene Contract Price")').first
                
                daily_url = await daily_node.get_attribute("href")
                weekly_url = await weekly_node.get_attribute("href")
                monthly_url = await monthly_node.get_attribute("href")
                
                base_url = "https://cma.opisnet.com"
                data = {
                    "daily_url": base_url + daily_url if daily_url.startswith('/') else daily_url,
                    "weekly_url": base_url + weekly_url if weekly_url.startswith('/') else weekly_url,
                    "monthly_url": base_url + monthly_url if monthly_url.startswith('/') else monthly_url,
                    "cookies": await context.cookies()
                }
                
                await browser.close()
                return data

        except Exception as e:
            print(f"⚠️ {attempt}회차 시도 중 에러 발생: {e}")
            if attempt < max_retries:
                wait_time = 5 * attempt
                print(f"{wait_time}초 후 다시 시도합니다...")
                await asyncio.sleep(wait_time)
            else:
                print("❌ 모든 재시도 횟수를 초과했습니다.")
                raise e

def convert_to_yyyymmdd(text):
    """다양한 날짜 형식을 'YYYYMMDD'로 변환"""
    date_match = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', str(text))
    if date_match:
        try: return datetime.strptime(date_match.group(1), '%d %b %Y').strftime('%Y%m%d')
        except: pass
    iso_match = re.search(r'(\d{4}-\d{2}-\d{2})', str(text))
    if iso_match:
        try: return datetime.strptime(iso_match.group(1), '%Y-%m-%d').strftime('%Y%m%d')
        except: pass
    return str(text)[:10]

def apply_excel_style(ws):
    """시트 스타일 적용"""
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    header_fill = PatternFill(start_color='D3D3D3', end_color='D3D3D3', fill_type='solid')
    # data_fill = PatternFill(start_color='F5F5F5', end_color='F5F5F5', fill_type='solid')
    
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
        for cell in row:
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='center', vertical='center')
            if cell.row == 1:
                cell.fill = header_fill
                cell.font = Font(bold=True)
            else:
                # cell.fill = data_fill
                if ws.title == 'Summary':
                    if cell.column == 3:
                        try:
                            cell.value = float(cell.value)
                            cell.number_format = '0.0'
                        except: pass
                    if cell.column == 4:
                        try:
                            cell.value = int(str(cell.value).strip())
                            cell.number_format = '0'
                        except: pass

    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if cell.value:
                    if len(str(cell.value)) > max_length: max_length = len(str(cell.value))
            except: pass
        ws.column_dimensions[column].width = max_length + 5

def process_data(data):
    session = requests.Session()
    session.verify = False 
    for cookie in data['cookies']:
        session.cookies.set(name=cookie['name'], value=cookie['value'], domain=cookie['domain'], path=cookie['path'])
    
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })

    summary_data = {"daily_means": [], "daily_date": None, "weekly_mean": None, "weekly_date": None, "monthly_cents": None, "monthly_date": None}

    # 1. Daily
    print("\n" + "="*20 + " [1] Daily 분석 시작 " + "="*20)
    d_resp = session.get(data['daily_url'])
    d_soup = BeautifulSoup(d_resp.text, 'html.parser')
    page_text_daily = d_soup.get_text(separator='\n', strip=True)
    try:
        summary_data["daily_date"] = convert_to_yyyymmdd(page_text_daily)
        benzene_start = re.search(r'Benzene\s*\(Houston,\s*TX\s*basis\)', page_text_daily, re.IGNORECASE)
        if benzene_start:
            section = page_text_daily[benzene_start.start():]
            pattern = r'(?<=Cents per gallon)(.*?)(?=USD per metric ton \(converted\))'
            match = re.search(pattern, section, re.DOTALL | re.IGNORECASE)
            if match:
                raw_text = match.group(1).strip()
                rows = []
                for line in raw_text.split('\n'):
                    m = re.search(r'^([A-Za-z]+)\s+([\d\.,]+)\s+to\s+([\d\.,]+)', line.strip())
                    if m: rows.append([m.group(1), float(m.group(2).replace(',', '')), float(m.group(3).replace(',', ''))])
                if rows:
                    benzene_df = pd.DataFrame(rows, columns=['Month', 'Low', 'High'])
                    benzene_df['Mean'] = (benzene_df['Low'] + benzene_df['High']) / 2
                    summary_data["daily_means"] = benzene_df['Mean'].tolist()
                    print(f"📅 Daily Date: {summary_data['daily_date']}")
                    print(benzene_df)
    except Exception as e: print(f"⚠️ Daily 에러: {e}")

    # 2. Weekly
    print("\n" + "="*20 + " [2] Weekly 분석 시작 " + "="*20)
    w_resp = session.get(data['weekly_url'])
    w_soup = BeautifulSoup(w_resp.text, 'html.parser')
    excel_url = None
    for a in w_soup.find_all('a', href=True):
        if ".xlsx" in a['href'] or ".xlsx" in a.get_text():
            excel_url = "https://cma.opisnet.com" + a['href'] if a['href'].startswith('/') else a['href']
            break
    if excel_url:
        e_resp = session.get(excel_url)
        if e_resp.status_code == 200:
            try:
                df_raw = pd.read_excel(io.BytesIO(e_resp.content), header=None)
                row_market, row_type = -1, -1
                for r in range(min(20, df_raw.shape[0])):
                    cell_val = str(df_raw.iloc[r, 0]).strip().upper()
                    if "MARKET" in cell_val: row_market = r
                    if "TYPE" in cell_val: row_type = r
                if row_market != -1:
                    target_col = -1
                    for col in range(df_raw.shape[1]):
                        if "Benzene" in str(df_raw.iloc[row_market, col]) and "Spot" in str(df_raw.iloc[row_type, col]):
                            target_col = col; break
                    if target_col != -1:
                        final_df = pd.concat([df_raw.iloc[0:9, [0, target_col, target_col+1]], df_raw.iloc[-2:, [0, target_col, target_col+1]]])
                        final_df = final_df.reset_index(drop=True)
                        final_df.columns = range(final_df.shape[1])
                        def calculate_mean(row):
                            try: return (float(row[1]) + float(row[2])) / 2
                            except: return None
                        final_df[3] = final_df.apply(calculate_mean, axis=1)
                        summary_data["weekly_mean"] = final_df.iloc[-1, 3]
                        summary_data["weekly_date"] = convert_to_yyyymmdd(final_df.iloc[-1, 0])
                        print(f"📅 Weekly Date: {summary_data['weekly_date']}")
                        print(final_df)
            except Exception as e: print(f"⚠️ Weekly 에러: {e}")

    # 3. Monthly
    print("\n" + "="*20 + " [3] Monthly 분석 시작 " + "="*20)
    m_resp = session.get(data['monthly_url'])
    m_soup = BeautifulSoup(m_resp.text, 'html.parser')
    page_text_monthly = m_soup.get_text(separator='\n', strip=True)
    try:
        summary_data["monthly_date"] = convert_to_yyyymmdd(page_text_monthly)
        price_match = re.search(r'settlement price of\s*\$(\d+(?:\.\d+)?)\s*per gallon', page_text_monthly, re.IGNORECASE)
        if price_match:
            summary_data["monthly_cents"] = round(float(price_match.group(1)) * 100, 2)
            print(f"📅 Monthly Date: {summary_data['monthly_date']}")
            print(f"💰 CP: {summary_data['monthly_cents']} cents")
    except Exception as e: print(f"⚠️ Monthly 에러: {e}")

    # 4. Final Excel
    print("\n" + "="*20 + " [4] Excel 보고서 생성 " + "="*20)
    today_str = datetime.now().strftime('%Y-%m-%d')
    quot_no_list = ["60M60681", "60M60682", "60M60683", "60M60686", "60M60684"]
    marker_names = ["US BZ DDP Spot Daily(M월)", "US BZ DDP Spot Daily(M+1월)", "US BZ DDP Spot Daily(M+2월)", "US BZ DDP Spot Weekly", "US BZ Monthly Contract Price(CP) cent/gal"]
    
    final_rows = []
    for i in range(3):
        final_rows.append([marker_names[i], quot_no_list[i], summary_data["daily_means"][i] if i < len(summary_data["daily_means"]) else "N/A", summary_data["daily_date"]])
    final_rows.append([marker_names[3], quot_no_list[3], summary_data["weekly_mean"] if summary_data["weekly_mean"] is not None else "N/A", summary_data["weekly_date"]])
    final_rows.append([marker_names[4], quot_no_list[4], summary_data["monthly_cents"] if summary_data["monthly_cents"] is not None else "N/A", summary_data["monthly_date"]])

    final_summary_df = pd.DataFrame(final_rows, columns=['Marker 가격', 'Quot. No', today_str, '기준 날짜'])
    url_df = pd.DataFrame([["Daily", data["daily_url"]], ["Weekly", data["weekly_url"]], ["Monthly", data["monthly_url"]]], columns=["Category", "URL"])

    xlsx_file_name = f"CMA_OPIS_{datetime.now().strftime('%Y%m%d')}.xlsx"
    with pd.ExcelWriter(xlsx_file_name, engine='openpyxl') as writer:
        final_summary_df.to_excel(writer, sheet_name='Summary', index=False)
        url_df.to_excel(writer, sheet_name='URL', index=False)
        workbook = writer.book
        for sheet_name in ['Summary', 'URL']:
            ws = workbook[sheet_name]
            apply_excel_style(ws)
            if sheet_name == 'URL':
                for i, url in enumerate([data["daily_url"], data["weekly_url"], data["monthly_url"]], start=2):
                    cell = ws.cell(row=i, column=2)
                    cell.hyperlink = url
                    cell.font = Font(color="0000FF", underline="single")

    print(f"💾 저장 완료: {xlsx_file_name}")
    print("\n" + "★"*20 + " [최종 요약 결과] " + "★"*20)
    print(final_summary_df)
    print("★"*57 + "\n")
    
    return xlsx_file_name, final_summary_df


async def main():
    try:
        data = await get_links_and_cookies_with_retry(max_retries=5)
        file_name, df_cma_result = process_data(data)
        
        today_str = datetime.now().strftime('%Y-%m-%d')

        # =========================================================
        # 10. 이메일 발송 (지메일 전송 환경변수 연동)
        # =========================================================
        print("=== 메일 발송 준비 ===")

        sender_email = os.environ.get("GMAIL_USER")
        app_password = os.environ.get("GMAIL_APP_PASSWORD")

        to_emails = "rchangjo@sk.com, hyo548@sk.com"
        # to_emails = "jp_lee@sk.com"
        cc_emails = "jp_lee@sk.com"

        subject = f"CMA {today_str}"

        html_table = df_cma_result.to_html(justify='center', index=False)

        custom_table_tag = '<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse; text-align:center; font-family:Calibri, Arial, sans-serif; font-size:13px;">'
        html_table = html_table.replace('<table border="1" class="dataframe">', custom_table_tag)

        html_body = f"""
        <html>
        <body style="margin:0; padding:0;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                    <td style="padding:20px; font-family:Calibri, Arial, sans-serif; font-size:14px; color:#000000;">
                        안녕하세요,<br><br>
                        오늘자 CMA 추출 결과입니다.<br>
                        상세 내용은 첨부파일을 확인해 주시기 바랍니다.<br><br>
                        {html_table}
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = to_emails    
        msg['Cc'] = cc_emails    
        msg.set_content("HTML 뷰어를 지원하는 메일 클라이언트를 사용해 주세요.") 
        msg.add_alternative(html_body, subtype='html')

        with open(file_name, 'rb') as f:
            excel_data = f.read()
            
        msg.add_attachment(
            excel_data, 
            maintype='application', 
            subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
            filename=file_name
        )

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

    except Exception as e: 
        print(f"\n❌ 최종 에러 발생: {e}")

if __name__ == "__main__":
    asyncio.run(main())
