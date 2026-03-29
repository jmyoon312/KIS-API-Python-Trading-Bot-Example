import yfinance as yf
import pandas as pd
import numpy as np
import math
from datetime import datetime

class HyperFidelitySimulator:
    def __init__(self, tickers, start_date="2010-02-11", end_date="2026-03-29", initial_seed=10000):
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.initial_seed = initial_seed
        self.compounding_rate = 0.78 # 세후 재투자
        self.data = {}

    def fetch_data(self):
        for t in self.tickers:
            df = yf.download(t, start=self.start_date, end=self.end_date, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            self.data[t] = df

    def run(self, ticker, logic="MOC", shadow_bounce=0.015):
        """
        logic="MOC": 앱 시뮬레이터 방식 (종가에 무조건 체결)
        logic="LOC": 현재 strategy.py 방식 (평단가 이하일 때만 체결)
        logic="SHADOW": 제안하는 V24 방식 (저점 대비 반등 시 유연하게 체결)
        """
        df = self.data[ticker]
        curr_seed = self.initial_seed
        cash = curr_seed
        holdings = 0
        avg_price = 0.0
        base_split = 40
        target_profit = 0.10
        
        history = []
        
        for date, row in df.iterrows():
            close = row['Close']
            high = row['High']
            low = row['Low']
            prev_close = df.shift(1).loc[date, 'Close'] if date in df.index else close
            
            # --- Engine Logic ---
            one_p_base = curr_seed / base_split
            t_val = (holdings * avg_price) / one_p_base if one_p_base > 0 else 0
            
            # Dynamic Gears
            if t_val < 20: d_split = base_split
            elif t_val < 30: d_split = base_split * 1.5
            elif t_val < 36: d_split = base_split * 2.0
            else: d_split = base_split * 2.5
            
            one_portion = curr_seed / d_split
            
            # Sniper 1/4 Exit
            star_ratio = target_profit - (target_profit * (2.0 / base_split) * t_val)
            star_price = avg_price * (1 + star_ratio) if avg_price > 0 else 0
            
            sale_done = False
            if holdings >= 4 and high >= star_price and star_price > 0:
                s_qty = math.ceil(holdings / 4.0)
                cash += (star_price * s_qty)
                holdings -= s_qty
                # Energy (Buyback)
                if low <= star_price:
                    bb_qty = math.floor(one_portion / star_price)
                    if bb_qty > 0:
                        avg_price = ((holdings * avg_price) + (bb_qty * star_price)) / (holdings + bb_qty)
                        holdings += bb_qty
                        cash -= (bb_qty * star_price)

            # Graduation (Full)
            tp = avg_price * (1 + target_profit) if avg_price > 0 else 0
            if holdings > 0 and high >= tp:
                profit = (holdings * tp) + cash - curr_seed
                curr_seed += (profit * self.compounding_rate) if profit > 0 else profit
                cash = curr_seed
                holdings = 0
                avg_price = 0.0
                sale_done = True

            # --- BUY LOGIC (THE CORE DIFFERENCE) ---
            if not sale_done and cash >= one_portion:
                if logic == "MOC":
                    # Always buys at close (App Research logic)
                    buy_price = close
                elif logic == "LOC":
                    # Only buys if close <= avg_price (Current strategy.py logic)
                    buy_price = avg_price if avg_price > 0 else close
                elif logic == "SHADOW":
                    # V24: Optimized Entry
                    # Even if above avg_price, if it's a good bounce from low, we take it.
                    buy_price = min(avg_price * 1.05, low * (1 + shadow_bounce)) if avg_price > 0 else close
                
                if low <= buy_price:
                    qty = math.floor(one_portion / buy_price)
                    if qty > 0:
                        avg_price = ((holdings * avg_price) + (qty * buy_price)) / (holdings + qty)
                        holdings += qty
                        cash -= (qty * buy_price)
            
            history.append(cash + holdings * close)
            
        return history

if __name__ == "__main__":
    sim = HyperFidelitySimulator(["TQQQ"])
    sim.fetch_data()
    
    results = {
        "MOC (App Ideal)": sim.run("TQQQ", logic="MOC"),
        "LOC (Current Reality)": sim.run("TQQQ", logic="LOC"),
        "Shadow (V24 Evolution)": sim.run("TQQQ", logic="SHADOW")
    }

    def mtr(h):
        r = (h[-1] / h[0] - 1) * 100
        pk = h[0]
        md = 0
        for x in h:
            if x > pk: pk = x
            if (x-pk)/pk < md: md = (x-pk)/pk
        return r, abs(md*100)

    print("\n" + "="*70)
    print("BRIDGE ANALYSIS: REALITY(LOC) vs IDEAL(MOC) vs V24 SHADOW")
    print("="*70)
    for name, hist in results.items():
        ret, mdd = mtr(hist)
        print(f"[{name}]")
        print(f"  - Cumulative Return: {ret:,.2f}%")
        print(f"  - Max Drawdown (MDD): {mdd:.2f}%")
        print("-" * 50)
    print("="*70)
