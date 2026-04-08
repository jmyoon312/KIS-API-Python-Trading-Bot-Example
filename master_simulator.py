import yfinance as yf
import pandas as pd
import numpy as np
import math
from datetime import datetime

class MasterSimulator:
    def __init__(self, tickers, start_date="2010-02-11", end_date="2026-03-29", initial_seed=10000):
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.initial_seed_per_ticker = initial_seed
        self.compounding_rate = 0.78 # 100% - 22% (양도세)
        self.data = {}

    def fetch_data(self):
        for t in self.tickers:
            print(f"Fetching {t} data...")
            df = yf.download(t, start=self.start_date, end=self.end_date, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            self.data[t] = df

    def run(self, ticker, mode="baseline", shadow_bounce=0.015):
        df = self.data[ticker]
        seed = self.initial_seed_per_ticker
        cash = seed
        holdings = 0
        avg_price = 0.0
        
        base_split = 40
        target_profit = 0.10 # 10%
        
        history = []
        
        for date, row in df.iterrows():
            close = row['Close']
            high = row['High']
            low = row['Low']
            prev_close = df.shift(1).loc[date, 'Close'] if date in df.index else close
            
            # 1. Dynamic Gear Shift
            one_portion_base = seed / base_split
            t_val = (holdings * avg_price) / one_portion_base if one_portion_base > 0 else 0
            
            if t_val < (base_split * 0.5): dynamic_split = base_split
            elif t_val < (base_split * 0.75): dynamic_split = base_split * 1.5
            elif t_val < (base_split * 0.9): dynamic_split = base_split * 2.0
            else: dynamic_split = base_split * 2.5
            
            one_portion_amt = seed / dynamic_split

            # 2. Sniper Defense (1/4 Exit) & Star Price
            star_ratio = target_profit - (target_profit * (2.0 / base_split) * t_val)
            star_price = avg_price * (1 + star_ratio) if avg_price > 0 else 0
            
            # --- SELL LOGIC ---
            sale_happened = False
            # 2.1 Sniper Sell
            if holdings >= 4 and high >= star_price and star_price > 0:
                sell_qty = math.ceil(holdings / 4.0)
                cash += (star_price * sell_qty)
                holdings -= sell_qty
                
                # Infinite Energy (Immediate Buyback)
                if mode != "none": # V17 logic
                    buy_back_price = star_price
                    if low <= buy_back_price:
                        # Buy back 1 portion
                        bb_qty = math.floor(one_portion_amt / buy_back_price)
                        if bb_qty > 0:
                            avg_price = ((holdings * avg_price) + (bb_qty * buy_back_price)) / (holdings + bb_qty)
                            holdings += bb_qty
                            cash -= (bb_qty * buy_back_price)

            # 2.2 Graduation (Full Exit)
            target_p = avg_price * (1+target_profit) if avg_price > 0 else 0
            if holdings > 0 and high >= target_p:
                profit = (holdings * target_p) + cash - seed
                if profit > 0:
                    seed += (profit * self.compounding_rate) # Compounding
                else:
                    seed += profit # Loss subtracts directly
                
                cash = seed
                holdings = 0
                avg_price = 0.0
                sale_happened = True

            # --- BUY LOGIC ---
            if not sale_happened:
                # 3. Turbo Booster (-5%)
                if t_val < (base_split * 0.9): # Not last lap
                    turbo_ref = min(avg_price, prev_close) if avg_price > 0 else prev_close
                    turbo_price = turbo_ref * 0.95
                    if low <= turbo_price:
                        t_qty = math.floor(one_portion_amt / turbo_price)
                        if t_qty > 0:
                            avg_price = ((holdings * avg_price) + (t_qty * turbo_price)) / (holdings + t_qty)
                            holdings += t_qty
                            cash -= (t_qty * turbo_price)

                # 4. Standard Daily Buy
                if cash >= one_portion_amt:
                    # Choose Buy Price
                    if mode == "shadow":
                        # Optimized Entry
                        raw_buy_price = min(avg_price, low * (1 + shadow_bounce)) if avg_price > 0 else close
                    else:
                        # Baseline (LOC/Avg)
                        raw_buy_price = avg_price if avg_price > 0 else close
                    
                    if low <= raw_buy_price:
                        qty = math.floor(one_portion_amt / raw_buy_price)
                        if qty > 0:
                            avg_price = ((holdings * avg_price) + (qty * raw_buy_price)) / (holdings + qty)
                            holdings += qty
                            cash -= (qty * raw_buy_price)

            history.append(cash + holdings * close)
            
        return history

if __name__ == "__main__":
    sim = MasterSimulator(["TQQQ", "SOXL"])
    sim.fetch_data()
    
    # --- Date Alignment ---
    # Intersection of all dates for all tickers
    common_dates = sim.data["TQQQ"].index
    for t in ["SOXL"]:
        common_dates = common_dates.intersection(sim.data[t].index)
    
    print(f"Analyzing {len(common_dates)} common trading days from {common_dates[0].date()} to {common_dates[-1].date()}")
    
    for t in ["TQQQ", "SOXL"]:
        sim.data[t] = sim.data[t].loc[common_dates]
    # ----------------------

    results = {}
    for t in ["TQQQ", "SOXL"]:
        # Baseline (V23.5)
        hist_base = sim.run(t, mode="baseline")
        # Shadow (V24)
        hist_shadow = sim.run(t, mode="shadow")
        
        results[t] = {"baseline": hist_base, "shadow": hist_shadow}

    # Combined Portfolio (5:5)
    port_base = [ (results["TQQQ"]["baseline"][i] + results["SOXL"]["baseline"][i]) / 20000 for i in range(len(results["TQQQ"]["baseline"])) ]
    port_shadow = [ (results["TQQQ"]["shadow"][i] + results["SOXL"]["shadow"][i]) / 20000 for i in range(len(results["TQQQ"]["shadow"])) ]

    def metrics(hist):
        ret = (hist[-1] / hist[0]) - 1
        peak = hist[0]
        mdd = 0
        for x in hist:
            if x > peak: peak = x
            dd = (x - peak) / peak
            if dd < mdd: mdd = dd
        return ret * 100, abs(mdd * 100)

    print("\n" + "="*70)
    print("FINAL 16-YEAR STRATEGY PERFORMANCE REPORT (78% COMPOUNDING)")
    print("="*70)
    for t in ["TQQQ", "SOXL"]:
        rb, mb = metrics(results[t]["baseline"])
        rs, ms = metrics(results[t]["shadow"])
        print(f"[{t}]")
        print(f"  - V23.5 Baseline: Return {rb:,.2f}% | MDD {mb:.2f}%")
        print(f"  - V24 Shadow-Strike: Return {rs:,.2f}% | MDD {ms:.2f}%")
        print(f"  >> Delta: Profit {rs-rb:+.2f}% | MDD {mb-ms:+.2f}%")
        print("-" * 50)

    rb_p, mb_p = metrics(port_base)
    rs_p, ms_p = metrics(port_shadow)
    print(f"[Combined 5:5 Portfolio]")
    print(f"  - V23.5 Baseline: Return {rb_p*100:,.2f}% | MDD {mb_p:.2f}%")
    print(f"  - V24 Shadow-Strike: Return {rs_p*100:,.2f}% | MDD {ms_p:.2f}%")
    print(f"  >> Delta: Profit {(rs_p-rb_p)*100:+.2f}% | MDD {mb_p-ms_p:+.2f}%")
    print("="*70)
