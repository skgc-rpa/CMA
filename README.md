# 📈 CMA OPIS Market Data Auto-Scraper

> **북미 및 글로벌 아로마틱스(CMA OPIS) 데이터 수집 및 가격 요약 자동화 파이프라인**

본 프로젝트는 **CMA OPIS(Dow Jones)** 플랫폼에서 US Benzene 관련 Daily, Weekly, Monthly 시장 보고서를 자동으로 스크래핑하고, 데이터 전처리 및 연산을 거쳐 기업용 엑셀 보고서를 생성한 뒤 지정된 수신처로 이메일을 발송하는 **Python 기반 자동화 시스템**입니다.

---

## ✨ 주요 기능 (Key Features)

* **🔐 SSO 우회 및 쿠키 세션 연동**: `requests`로 Dow Jones SSO 로그인 URL을 사전에 확보한 뒤, `Playwright` 가상 브라우저를 통해 기업 계정 로그인을 안전하게 시뮬레이션하고 쿠키 세션을 획득합니다.
* **🤖 Headless 가상 브라우저 크롤링**: 가상 GUI 환경이 없는 **GitHub Actions(Ubuntu Linux)** 서버에서 `headless=True` 모드로 Chromium 브라우저를 구동하여 최신 보고서 링크를 동적으로 추출합니다.
* **📊 다각적 데이터 파싱 및 요약**: 
  * **Daily**: 텍스트 데이터 내 정규표현식(Regex)을 이용해 Benzene(Houston, TX basis) 가격의 Low/High 값을 파싱 후 Mean(평균값) 산출
  * **Weekly**: 최신 주간 엑셀 보고서(.xlsx)를 실시간 다운로드하여 특정 마켓 Spot 가격 데이터 추출
  * **Monthly**: 텍스트 분석을 통해 월간 계약 가격(CP) 정제 및 센트(cent/gal) 단위 변환
* **🎨 오픈픽셀(openpyxl) 리포트 스타일링**: 기업 보고서 양식에 맞추어 깔끔한 테두리(Thin border), 헤더 음영 강조, 데이터 셀 가운데 정렬 및 숫자 포맷팅(소수점/정수), 열 너비 자동 최적화가 적용된 엑셀 파일을 생성합니다. 데이터 행의 불필요한 배경 음영을 제거하여 가독성을 높였습니다.
* **📧 스마트 이메일 알림**: 요약된 데이터프레임을 인덱스 번호 없이 깔끔한 HTML 인라인 스타일 표로 변환하여 메일 본문에 삽입하고, 생성된 엑셀 파일을 첨부하여 지정된 그룹 수신처로 자동 발송합니다.
* **☁️ Cloud 기반 5회 재시도 보장**: 네트워크 지연이나 로그인 타임아웃 에러를 방지하기 위해 **최대 5회의 자동 재시도 로직**이 내장되어 있으며, **GitHub Actions** 인프라를 통해 클라우드에서 무중단 가동됩니다.

---

## 📁 저장소 구조 (Repository Structure)

```text
CMA/
├── .github/
│   └── workflows/
│       └── daily_cma.yml     # CI/CD 스케줄러 (GitHub Actions 워크플로우)
├── main.py                   # 핵심 로직 (Playwright 크롤링, 데이터 연산, 메일 발송)
├── requirements.txt          # 의존성 파이썬 패키지 목록
└── README.md                 # 프로젝트 가이드 문서
```

---
## ⚙️ 환경 설정 및 관리 파일 구성

### 1. GitHub Secrets 등록 (보안 설정)
소스 코드에 계정 정보가 노출되지 않도록 GitHub 저장소의 **Settings > Secrets and variables > Actions** 메뉴에서 아래 4가지 환경변수를 반드시 등록해야 합니다.

* **`GMAIL_USER`**: 알림을 발송할 본인의 Gmail 주소 (예: `example@gmail.com`)
* **`GMAIL_APP_PASSWORD`**: 구글 계정에서 발급받은 16자리 앱 비밀번호
* **`CMA_USER`**: CMA OPIS 사이트 로그인 이메일 (`jp_lee@skgeocentric.com`)
* **`CMA_PASSWORD`**: CMA OPIS 사이트 로그인 비밀번호 (`!ghkgkr8896`)

---

### 2. GitHub Actions 자동화 스케줄러 (`.github/workflows/daily_cma.yml`)
최대 5회 재시도 로직을 지원하는 플레이라이트 환경과 필수 시스템 의존성 자동 빌드가 포함된 가동 스크립트입니다.

```yaml
name: Daily CMA Report Automation

on:
  # schedule:
  #   # 평일(월~금) KST 오전 10:07 (UTC 오전 01:07) 정기 가동 시 주석 해제
  #   - cron: '07 6 * * 1-5'
  workflow_dispatch: # GitHub Actions 탭에서 수동 실행 버튼 활성화

jobs:
  run-scraper-and-email:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Install Playwright Browsers & Deps
        # 리눅스 가상 환경에서 브라우저 크롤링을 정상 구동하기 위한 시스템 패키지 동기화
        run: |
          playwright install chromium --with-deps

      - name: Run CMA Scraper & Email Script
        run: python main.py
        env:
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          CMA_USER: ${{ secrets.CMA_USER }}
          CMA_PASSWORD: ${{ secrets.CMA_PASSWORD }}
