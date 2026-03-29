import yfinance as yf
import pandas as pd
import numpy as np
import math
from datetime import datetime, timedelta

class ShadowStrategyAnalyzer:
    def __init__(self, ticker, start_date="2010-01-01", end_date="2026-03-29", initial_seed=100000):
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.initial_seed = initial_seed
        self.data = None

    def fetch(self):
        print(f"Fetching 16 years of data for {self.ticker}...")
        df = yf.download(self.ticker, start=self.start_date, end=self.end_date, auto_adjust=True)
        if df.empty: raise Exception("No data found")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        self.data = df

    def simulate(self, is_shadow=False):
        """
        is_shadow=False: 사용자님의 현재 V23.5 (Gears, Sniper, Infinite Energy)
        is_shadow=True:  V23.5 + Shadow-Trailing (가격 보정 기능 추가)
        """
        cash = self.initial_seed
        holdings = 0
        avg_price = 0.0
        split_count = 40
        target_profit_pct = 0.10
        
        history = []
        df = self.data
        
        for date, row in df.iterrows():
            curr_price = row['Close']
            high = row['High']
            low = row['Low']
            prev_close = df.shift(1).loc[date, 'Close'] if date in df.index else curr_price
            
            # --- [V23.5 CORE ENGINE] ---
            # 1. Dynamic Gears (T-Value based)
            base_portion = self.initial_seed / split_count
            t_val = (holdings * avg_price) / base_portion if base_portion > 0 else 0
            
            dynamic_split = split_count
            if t_val < (split_count * 0.5): dynamic_split = split_count
            elif t_val < (split_count * 0.75): dynamic_split = split_count * 1.5
            elif t_val < (split_count * 0.9): dynamic_split = split_count * 2.0
            else: dynamic_split = split_count * 2.5
            
            one_portion_amt = self.initial_seed / dynamic_split

            # 2. V17 Sniper (1/4 Exit at Star Price)
            depreciation_factor = 2.0 / split_count
            star_ratio = target_profit_pct - (target_profit_pct * depreciation_factor * t_val)
            star_price = avg_price * (1 + star_ratio) if avg_price > 0 else 0
            
            if holdings > 4 and high >= star_price and star_price > 0:
                sell_qty = math.ceil(holdings / 4.0)
                cash += (star_price * sell_qty)
                holdings -= sell_qty
                # Infinite Energy: Buy Back 1 Portion immediately
                if cash >= one_portion_amt:
                    buy_qty = math.floor(one_portion_amt / star_price)
                    holdings += buy_qty
                    avg_price = ((holdings - buy_qty) * avg_price + buy_qty * star_price) / holdings
                    cash -= (buy_qty * star_price)

            # 3. Graduation (Full Exit)
            target_price = avg_price * (1 + target_profit_pct) if avg_price > 0 else 0
            if holdings > 0 and high >= target_price:
                cash += holdings * target_price
                holdings = 0
                avg_price = 0.0
                t_val = 0

            # 4. Standard Daily Buy
            if cash >= one_portion_amt:
                # [V24 Evolution: Shadow-Trailing Price Optimization]
                if is_shadow:
                    # Always buy, but try to get lower than avg_price if low is deep
                    # shadow_buy_price = min(avg_price, low * 1.015)
                    # If current_price is already very low, use it.
                    shadow_buy_price = min(avg_price, low * 1.015) if avg_price > 0 else curr_price
                    buy_price = max(0.01, round(shadow_buy_price, 2))
                else:
                    # V23.5 Standard: Buy at avg_price (LOC)
                    buy_price = avg_price if avg_price > 0 else curr_price
                
                # Check if buy_price is reachable today
                if low <= buy_price:
                    qty = math.floor(one_portion_amt / buy_price)
                    if qty > 0:
                        new_total = holdings + qty
                        avg_price = ((holdings * avg_price) + (qty * buy_price)) / new_total
                        holdings = new_total
                        cash -= (qty * buy_price)

            history.append(cash + holdings * curr_price)

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
        analyzer = ShadowStrategyAnalyzer(t)
        analyzer.fetch()
        
        # Scenario A: User's Current Engine (V23.5)
        v235_ret, v235_mdd = analyzer.simulate(is_shadow=False)
        # Scenario B: V24 Evolution (Shadow-Trailing)
        v24_ret, v24_mdd = analyzer.simulate(is_shadow=True)
        
        results[t] = {
            "V23.5": {"R": v235_ret, "M": v235_mdd},
            "V24": {"R": v24_ret, "M": v24_mdd}
        }
    
    print("\n" + "="*70)
    print("V23.5 vs V24 (SHADOW-TRAILING) IMPACT ANALYSIS (16-YEAR)")
    print("="*70)
    for t, res in results.items():
        print(f"[{t}]")
        print(f"  - V23.5 (Baseline): Return {res['V23.5']['R']}% | MDD {res['V23.5']['M']}%")
        print(f"  - V24 (Shadow):    Return {res['V24']['R']}% | MDD {res['V24']['M']}%")
        diff_ret = res['V24']['R'] - res['V23.5']['R']
        diff_mdd = res['V23.5']['M'] - res['V24']['M']
        print(f"  >> NET IMPROVEMENT: PROFIT {diff_ret:+.2f}%, MDD REDUCTION {diff_mdd:+.2f}%")
        print("-" * 50)
