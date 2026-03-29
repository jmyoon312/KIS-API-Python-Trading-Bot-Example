import yfinance as yf
import pandas as pd
import numpy as np
import math
from datetime import datetime, timedelta

class StrategyAnalyzer:
    def __init__(self, ticker, start_date="2010-01-01", end_date="2026-03-29", initial_seed=100000):
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.initial_seed = initial_seed
        self.data = None

    def fetch(self):
        print(f"Fetching 16 years of data for {self.ticker}...")
        self.data = yf.download(self.ticker, start=self.start_date, end=self.end_date, auto_adjust=True)
        if self.data.empty: raise Exception("No data found")

    def simulate(self, mode="NORMAL", bounce_threshold=0.015, drop_trigger=0.03):
        """
        NORMAL: 평단가 근처 LOC 매수
        TRAILING: 트리거 하락 후 반등 확인 시 매수
        """
        cash = self.initial_seed
        holdings = 0
        avg_price = 0.0
        split_count = 40
        target_profit = 0.10
        
        history = []
        tracking_low = 0.0
        is_tracking = False
        
        df = self.data
        if isinstance(df.columns, pd.MultiIndex):
            df = df.xs(self.ticker, axis=1, level=1)
            
        for date, row in df.iterrows():
            price = row['Close']
            high = row['High']
            low = row['Low']
            
            # --- SELL LOGIC (Graduation) ---
            if holdings > 0 and high >= avg_price * (1 + target_profit):
                sell_price = avg_price * (1 + target_profit)
                cash += holdings * sell_price
                holdings = 0
                avg_price = 0.0
                is_tracking = False
                tracking_low = 0.0

            # --- BUY LOGIC ---
            one_portion = self.initial_seed / split_count
            if cash >= one_portion:
                do_buy = False
                buy_price = price
                
                if mode == "NORMAL":
                    # 단순 평단가 이하(혹은 새출발) 시 매수
                    if holdings == 0 or price <= avg_price:
                        do_buy = True
                
                elif mode == "TRAILING":
                    # 1. 트리거 확인 (평단가 대비 일정 하락 시 추적 시작)
                    trigger_price = avg_price * (1 - drop_trigger) if avg_price > 0 else price
                    if not is_tracking and price <= trigger_price:
                        is_tracking = True
                        tracking_low = price
                    
                    if is_tracking:
                        # 2. 당일 저점 갱신
                        if low < tracking_low: tracking_low = low
                        
                        # 3. 반등 확인 (저점 대비 bounce_threshold 이상 상승 시)
                        if price >= tracking_low * (1 + bounce_threshold):
                            do_buy = True
                            is_tracking = False # 매수 성공 시 추적 종료
                
                if do_buy:
                    qty = math.floor(one_portion / buy_price)
                    if qty > 0:
                        avg_price = (holdings * avg_price + qty * buy_price) / (holdings + qty)
                        holdings += qty
                        cash -= qty * buy_price
            
            history.append(cash + holdings * price)

        returns = (history[-1] / self.initial_seed - 1) * 100
        mdd = self.calculate_mdd(history)
        return round(returns, 2), round(mdd, 2)

    def calculate_mdd(self, history):
        peak = history[0]
        mdd = 0
        for val in history:
            if val > peak: peak = val
            drawdown = (val - peak) / peak
            if drawdown < mdd: mdd = drawdown
        return abs(mdd * 100)

if __name__ == "__main__":
    tickers = ["TQQQ", "SOXL"]
    results = {}
    
    for t in tickers:
        analyzer = StrategyAnalyzer(t)
        analyzer.fetch()
        
        normal_ret, normal_mdd = analyzer.simulate(mode="NORMAL")
        trail_ret, trail_mdd = analyzer.simulate(mode="TRAILING", bounce_threshold=0.015, drop_trigger=0.03)
        
        results[t] = {
            "NORMAL": {"Return": normal_ret, "MDD": normal_mdd},
            "TRAILING": {"Return": trail_ret, "MDD": trail_mdd}
        }
    
    print("\n" + "="*50)
    print("16-YEAR STRATEGY ANALYSIS REPORT (2010-2026)")
    print("="*50)
    for t, res in results.items():
        print(f"[{t}]")
        print(f"  - Normal Mode:   Return {res['NORMAL']['Return']}% | MDD {res['NORMAL']['MDD']}%")
        print(f"  - Trailing Mode: Return {res['TRAILING']['Return']}% | MDD {res['TRAILING']['MDD']}%")
        diff_ret = res['TRAILING']['Return'] - res['NORMAL']['Return']
        diff_mdd = res['NORMAL']['MDD'] - res['TRAILING']['MDD']
        print(f"  IMPACT: Profit {diff_ret:+.2f}%, MDD IMPROVEMENT {diff_mdd:+.2f}%")
        print("-" * 30)
