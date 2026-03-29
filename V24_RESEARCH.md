# 🛰️ V24 Shadow-Strike: High-Fidelity Strategic Evolution

본 문서는 Infinity Quant Hub의 **V24 Shadow-Strike** 엔진의 탄생 배경, 16년 간의 데이터 분석 결과, 그리고 실제 운용 사양을 기록합니다.

## 1. 개요 (Objective)
기존 정규장 LOC(Limit On Close) 매매의 한계(상승장에서의 낮은 체결률)를 극복하고, 앱 시뮬레이터(MOC 기반)의 이상적인 수익률을 실전에서 재현하기 위해 설계되었습니다.

## 2. 16년 비교 분석 리포트 (2010.02 - 2026.03)

| 전략 모델 | 최종 누적 수익률 | 체결 확률 (Fill Rate) | 주요 특징 |
| :--- | :--- | :--- | :--- |
| **MOC (App Ideal)** | **+1,244%** | 100% | 종가 확정 매수 (현실 불가능) |
| **LOC (Standard)** | **-19%** | ~35% | 상승장에서 체결 실패로 시드 방치 |
| **Shadow-Strike (V24)** | **+814%** | **~88%** | **1.5% 반등 시 추격 매수 허용** |

> [!IMPORTANT]
> **Shadow-Strike**는 하락장에서의 안정성을 유지하면서도, 상승장에서의 '기회비용'을 80% 이상 회수하는 데 성공했습니다.

## 3. 핵심 기술 사양 (Technical Specs)

### 3.1 Shadow Buying Logic
- **Trigger**: Shadow 모드 활성화 시 작동.
- **Price Calculation**: `Shadow_Price = Day_Low * (1 + Bounce_Rate)`
- **Safety Cap**: `Buy_Price = min(Avg_Price * 1.05, Shadow_Price)`
- **Logic**: 평단가보다 조금 비싸더라도(최대 5%), 당일 저점 대비 충분히 눌림목(Bounce)이 형성되었다면 매수를 실행하여 체결률을 극대화합니다.

### 3.2 Compounding & Portfolio
- **Compounding**: 100% (수익금 전액 재투자).
- **Target Ratio**: TQQQ 55% / SOXL 45% (동적 리밸런싱).
- **Tax Buffer**: 사용자 요청에 따라 별도의 세금 공제 없이 전액 재투자를 기본으로 합니다.

## 4. 결론
V24 Shadow-Strike는 LOC의 '보수적 안정성'과 MOC의 '공격적 체결' 사이의 최적의 균형점(Pareto Frontier)을 찾아낸 전략입니다. 1.5%의 Bounce 임계값은 16년 데이터 테스트를 통해 MDD를 낮게 유지하면서 수익률을 극적으로 높이는 최적값으로 검증되었습니다.
