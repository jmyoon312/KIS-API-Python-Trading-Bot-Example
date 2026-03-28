# 🚀 Infinity Quant Hub [V23.5]

**Infinity Quant Hub**는 한국투자증권(KIS) Open API를 기반으로 한 프리미엄 미국 주식 자동매매 솔루션입니다. 단순한 거래 도구를 넘어, 리액트 기반의 스마트 대시보드와 자가 치유(Self-Healing) 엔진을 결합하여 프로페셔널한 트레이딩 경험을 제공합니다.

---

## ✨ 핵심 기술적 특징 (Key Features)

### 🖥️ 프리미엄 웹 대시보드 (Premium Web Dashboard)
- **상황실(Control Unit)**: React + Vite + Tailwind CSS 기반의 세련된 UI로 실시간 체결 현황, 포트폴리오 비중, 마켓 타임라인을 한눈에 관제합니다.
*   **PWA 지원**: 모바일에서도 앱처럼 설치하여 언제 어디서든 서버를 제어할 수 있습니다.

### 🛡️ 불독 엔진 (Bulldog Retry Engine)
- **장애 극복**: KIS API의 일시적 장애(500)나 유량 제한(429) 발생 시, 5단계 지연 재시도 알고리즘을 가동하여 주문 누락을 원천 차단합니다.
- **자전거래 방어 (Dual Wash-Trade Shield)**: 전략 로직과 브로커 통신 양단에서 의도치 않은 자전거래 실수를 완벽히 방어합니다.

### 📊 장부 사이클 분석 (Cycle Analytics - V23.5)
- **입체적 분석**: 거래 하나하나를 넘어, '첫 매수부터 졸업까지'의 전체 주기를 사이클로 정의하여 승률, 평균 보유 기간, 최종 Yield를 정밀하게 분석합니다.

### 🔄 TrueSync & 듀얼 코어 (Dual-Core Sync)
- **데이터 격리**: 실전 투자와 모의 투자 환경을 완벽히 분리하여 동시에 운용할 수 있습니다.
- **자동 동기화**: 미국 시장 휴장일과 서머타임(DST)을 자동 감지하며, 실제 잔고와 가상 장부의 1원 단위 오차까지 실시간으로 보정합니다.

---

## 🛠️ 설치 및 실행 방법 (Installation & Usage)

### 1. 필수 환경 (Requirements)
*   **Python 3.12+** (Backend Engine)
*   **Node.js 20+** (Frontend Dashboard Build)
*   **한국투자증권 API Key** (실전/모의 별도)
*   **Telegram Bot Token & Chat ID**

### 2. 패키지 설치 및 빌드
```bash
# 백엔드 의존성 설치
pip install requests yfinance pytz fastapi uvicorn python-dotenv "python-telegram-bot[job-queue]"

# 프론트엔드 빌드 (선택 사항)
cd frontend
npm install
npm run build
```

### 3. 환경 변수 설정 (.env)
프로젝트 최상단 폴더에 `.env` 파일을 생성하고 본인의 키를 입력합니다. (보안을 위해 `.gitignore`에 등록되어 있습니다.)
```env
TELEGRAM_TOKEN=나의_토큰
ADMIN_CHAT_ID=나의_채팅방ID
APP_KEY_REAL=실전_APP_KEY
APP_SECRET_REAL=실전_APP_SECRET
... (기타 설정)
```

### 4. 프로그램 실행
```bash
python main.py
```

---

## 🚨 원작자 저작권 및 면책 조항

*   **저작권 명시**: 본 프로젝트의 핵심 매매 로직(무한매수법) 아이디어는 원작자 **'라오어'**님에게 있습니다. 본 코드는 기술적 학습 및 데이터 시각화를 위한 자동화 도구일 뿐이며, 원작자의 공식 인증을 받은 프로그램이 아닙니다.
*   **면책 조항**: 실제 투자에 따른 금전적 손실 책임은 전적으로 사용자 본인에게 있습니다. 반드시 충분한 모의 테스트 후에 운용하십시오.

---

## 📂 파일 구조 (Structure)
- `main.py`: 통합 스케줄러 및 엔진 진입점
- `broker.py`: KIS API 통신 및 Bulldog 엔진
- `strategy.py`: 무한매수 기반 분할 매수/매도 로직
- `web_server.py`: FastAPI 기반 대시보드 API 서버
- `frontend/`: React + Vite 개발 환경
- `config.py`: 데이터 영속성 및 사이클 분석 매니저
