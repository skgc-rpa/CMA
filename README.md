# 📈 PX CCF Market Data Auto-Scraper

> **중국 화학/섬유 시장(CCFGroup) 데이터 수집 및 마진 분석 자동화 파이프라인**

본 프로젝트는 **CCFGroup**에서 PX, PTA, MEG 및 폴리에스터 관련 시장 데이터를 자동으로 수집하고, 비즈니스 로직에 따른 마진(Margin) 계산 후 엑셀 리포트를 생성하여 이메일로 전송하는 **Python 기반 자동화 시스템**입니다.

---

## ✨ 주요 기능 (Key Features)

* **⚡ 고성능 병렬 스크래핑**: `ThreadPoolExecutor`와 `lxml` 파서를 결합하여 다수의 리포트 URL을 멀티스레딩으로 빠르게 수집합니다.
* **📊 지능형 데이터 전처리**: Pandas를 활용해 Raw 데이터를 정제하며, 복잡한 마진 산출 공식(예: `0.855*PTA + 0.335*MEG`)을 자동 적용합니다.
* **🎨 맞춤형 엑셀 리포트**: `xlsxwriter`를 통해 기업용 포맷(조건부 서식, 헤더 강조, 셀 너비 최적화)이 적용된 보고서를 자동 생성합니다.
* **📧 스마트 이메일 알림**: 생성된 엑셀 파일 첨부 및 본문 요약 표를 포함하여 지정된 수신처(`jp_lee@sk.com`)로 자동 발송합니다.
* **🤖 Cloud 기반 무중단 운영**: **GitHub Actions**를 통해 매주 평일(월~금) 오전 10시(KST)에 별도의 로컬 서버 없이 클라우드에서 자동 실행됩니다.

---

## 📁 저장소 구조 (Repository Structure)

```text
PX/
├── .github/
│   └── workflows/
│       └── px_daily_report.yml   # CI/CD 스케줄러 (GitHub Actions)
├── main.py                       # 핵심 로직 (스크래핑, 연산, 메일 발송)
├── requirements.txt              # 의존성 패키지 목록
└── README.md                     # 프로젝트 가이드
```

---

## ⚙️ 환경 설정 (Setup & Installation)

### 1. GitHub Secrets 등록 (필수)
자동 이메일 발송 기능을 위해 GitHub 저장소의 `Settings > Secrets and variables > Actions` 메뉴에 아래 두 가지 변수를 반드시 등록해야 합니다.

| 변수명 | 설명 | 비고 |
| :--- | :--- | :--- |
| **`GMAIL_USER`** | 발송용 Gmail 주소 | 예: `example@gmail.com` |
| **`GMAIL_APP_PASSWORD`** | Gmail 앱 비밀번호 | 16자리 (띄어쓰기 없이 입력) |

### 2. 로컬 개발 환경 구축
로컬 PC에서 스크립트를 수동으로 테스트하거나 수정할 경우 아래 라이브러리들을 설치해야 합니다.

```bash
# 의존성 패키지 설치
pip install requests pandas beautifulsoup4 lxml xlsxwriter urllib3
```
> **Note:** 실행 시 환경 변수가 로컬에 설정되어 있지 않으면 메일 발송은 건너뛰고 엑셀 파일만 생성됩니다.

---

## ⏰ 실행 스케줄 (Schedule)

GitHub Actions를 통해 설정된 자동 실행 주기입니다.

* **실행 주기**: 매주 월요일 ~ 금요일 (평일)
* **실행 시간**: KST 오전 10:00 (UTC 01:00)
* **구동 방식**: GitHub Actions Ubuntu 서버 워크플로우를 통한 자동 실행
* **Cron 설정**: `0 1 * * 1-5`

---

## 🛠 기술 스택 (Tech Stack)

* **Language**: Python 3.x
* **Data Analysis**: Pandas, NumPy
* **Scraping**: Requests, BeautifulSoup4, Lxml
* **Reporting**: XlsxWriter, SMTPLib
* **Automation**: GitHub Actions
