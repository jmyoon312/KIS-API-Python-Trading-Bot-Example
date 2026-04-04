import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import logging

class MarketIntelligence:
    """🛰️ 실시간 시장 지각 및 심리 분석 엔진 (Expert Pulse)"""
    
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        self.cnn_url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/"

    def get_fear_and_greed(self):
        """CNN Fear & Greed Index 실시간 데이터 획득"""
        try:
            response = requests.get(self.cnn_url, headers=self.headers, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            current_val = data['fear_and_greed']['rating'] # 'fear', 'neutral', 'greed', 'extreme greed'
            score = data['fear_and_greed']['score']
            
            return {
                "score": round(score, 1),
                "rating": current_val.upper(),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logging.error(f"Fear & Greed Fetch Error: {e}")
            return {"score": 50, "rating": "NEUTRAL", "error": str(e)}

    def get_vix_status(self):
        """VIX(공포 지수) 및 S&P 500 추세 분석"""
        try:
            # VIX 지수
            vix = yf.Ticker("^VIX")
            vix_price = vix.history(period="1d")['Close'].iloc[-1]
            
            # S&P 500 (SPY) 200일 이동평균선 상단 여부
            spy = yf.Ticker("SPY")
            spy_hist = spy.history(period="1y")
            spy_200d = spy_hist['Close'].rolling(window=200).mean().iloc[-1]
            spy_curr = spy_hist['Close'].iloc[-1]
            
            trend = "BULL" if spy_curr > spy_200d else "BEAR"
            
            return {
                "vix": float(round(vix_price, 2)), # 🔩 NumPy 타입 직렬화 호환성 처리
                "spy_trend": trend,
                "spy_200d": float(round(spy_200d, 2)),
                "is_volatile": bool(vix_price > 25)
            }
        except Exception as e:
            logging.error(f"VIX Fetch Error: {e}")
            return {"vix": 15, "spy_trend": "BULL", "error": str(e)}

    def get_market_pulse(self):
        """종합 시장 맥락(Market Pulse) 반환"""
        fg = self.get_fear_and_greed()
        vix = self.get_vix_status()
        
        # 종합 진단 메세지 생성 (Expert Logic)
        logic_msg = ""
        if fg['score'] < 30:
            logic_msg = "시장이 심한 공포에 빠져 있습니다. 역사적으로 'V24 Turbo' 모드가 빛을 발하는 구간입니다."
        elif fg['score'] > 70:
            logic_msg = "시장이 극도로 낙관적입니다. 'Sniper'를 활성화하여 익절금을 미리 챙기는 전략이 현명할 수 있습니다."
        else:
            logic_msg = "시장이 중립적인 위치에 있습니다. 백테스트의 통계적 우위를 따르는 '기본 모듈 조합'이 권장됩니다."

        return {
            "fear_greed": fg,
            "vix_vitals": vix,
            "expert_advice": logic_msg
        }

if __name__ == "__main__":
    mi = MarketIntelligence()
    print(mi.get_market_pulse())
