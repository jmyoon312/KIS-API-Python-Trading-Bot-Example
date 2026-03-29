import yfinance as yf
import pandas as pd
import numpy as np
import math
from datetime import datetime, timedelta

class AdvancedStrategyAnalyzer:
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
        
        # Flatten MultiIndex if necessary
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        self.data = df
        
        # Calculate ATR (14-day)
        high_low = self.data['High'] - self.data['Low']
        high_cp = np.abs(self.data['High'] - self.data['Close'].shift())
        low_cp = np.abs(self.data['Low'] - self.data['Close'].shift())
        tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
        self.data['ATR'] = tr.rolling(window=14).mean()
        self.data['ATR_Pct'] = self.data['ATR'] / self.data['Close']
        self.data['Volume_MA20'] = self.data['Volume'].rolling(window=20).mean()

    def simulate(self, mode="NORMAL", hybrid_threshold=0.25, base_bounce=0.015):
        """
        NORMAL: Baseline LOC Buy
        HYBRID: Early (Normal) -> Late (Trailing)
        ADAPTIVE: Trailing with ATR-linked bounce
        """
        cash = self.initial_seed
        holdings = 0
        avg_price = 0.0
        split_count = 40
        target_profit = 0.10
        
        history = []
        is_tracking = False
        tracking_low = 0.0
        
        df = self.data
        if isinstance(df.columns, pd.MultiIndex):
            df = df.xs(self.ticker, axis=1, level=1)
            
        for date, row in df.iterrows():
            if pd.isna(row['ATR']): continue
            
            price = row['Close']
            high = row['High']
            low = row['Low']
            atr_pct = row['ATR_Pct']
            vol = row['Volume']
            vol_ma = row['Volume_MA20']
            
            # --- SELL LOGIC ---
            if holdings > 0 and high >= avg_price * (1 + target_profit):
                sell_price = avg_price * (1 + target_profit)
                cash += holdings * sell_price
                holdings = 0
                avg_price = 0.0
                is_tracking = False

            # --- BUY LOGIC ---
            one_portion = self.initial_seed / split_count
            t_val = (holdings * avg_price) / one_portion if one_portion > 0 else 0
            
            if cash >= one_portion:
                do_buy = False
                
                # Logic Selection
                current_mode = "NORMAL"
                if mode == "HYBRID" and t_val >= (split_count * hybrid_threshold):
                    current_mode = "TRAILING"
                elif mode == "ADAPTIVE":
                    current_mode = "TRAILING"
                elif mode == "NORMAL":
                    current_mode = "NORMAL"
                else: # if mode == "TRAILING"
                    current_mode = "TRAILING"

                if current_mode == "NORMAL":
                    if holdings == 0 or price <= avg_price:
                        do_buy = True
                
                else: # TRAILING
                    # Adaptive factor: In high volatility, wait for bigger bounce
                    # Use base_bounce or ATR scaling
                    final_bounce = max(0.01, atr_pct * 0.5) if mode == "ADAPTIVE" else base_bounce
                    
                    trigger_drop = 0.03
                    trigger_price = avg_price * (1 - trigger_drop) if avg_price > 0 else price
                    
                    if not is_tracking and price <= trigger_price:
                        is_tracking = True
                        tracking_low = price
                    
                    if is_tracking:
                        if low < tracking_low: tracking_low = low
                        if price >= tracking_low * (1 + final_bounce):
                            # Volume filter: RVOL > 0.8
                            if vol >= vol_ma * 0.8:
                                do_buy = True
                                is_tracking = False
                
                if do_buy:
                    qty = math.floor(one_portion / price)
                    if qty > 0:
                        avg_price = (holdings * avg_price + qty * price) / (holdings + qty)
                        holdings += qty
                        cash -= qty * price
            
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
        analyzer = AdvancedStrategyAnalyzer(t)
        analyzer.fetch()
        
        n_ret, n_mdd = analyzer.simulate(mode="NORMAL")
        h_ret, h_mdd = analyzer.simulate(mode="HYBRID", hybrid_threshold=0.25)
        a_ret, a_mdd = analyzer.simulate(mode="ADAPTIVE")
        
        results[t] = {
            "NORMAL": {"R": n_ret, "M": n_mdd},
            "HYBRID": {"R": h_ret, "M": h_mdd},
            "ADAPTIVE": {"R": a_ret, "M": a_mdd}
        }
    
    print("\n" + "="*60)
    print("V24+ ADVANCED HYBRID ANALYTICS (2010-2026)")
    print("="*60)
    for t, res in results.items():
        print(f"[{t}]")
        print(f"  - NORMAL:   Return {res['NORMAL']['R']:>7}% | MDD {res['NORMAL']['M']:>6}%")
        print(f"  - HYBRID:   Return {res['HYBRID']['R']:>7}% | MDD {res['HYBRID']['M']:>6}%")
        print(f"  - ADAPTIVE: Return {res['ADAPTIVE']['R']:>7}% | MDD {res['ADAPTIVE']['M']:>6}%")
        print("-" * 40)
