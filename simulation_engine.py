import yfinance as yf
import pandas as pd
import numpy as np
import math
from datetime import datetime, timedelta
import os
import json

class InfinitySimulator:
    def __init__(self, ticker, start_date, end_date, initial_seed, split_count=40, target_profit=10.0, version="V24"):
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.initial_seed = initial_seed
        self.split_count = split_count
        self.target_profit = target_profit
        self.version = version
        
        self.data = None
        self.benchmark = None
        
    def fetch_data(self):
        """yfinance를 통해 주식 및 벤치마크(^GSPC) 데이터를 가져옵니다."""
        start = (datetime.strptime(self.start_date, "%Y-%m-%d") - timedelta(days=10)).strftime("%Y-%m-%d")
        end = (datetime.strptime(self.end_date, "%Y-%m-%d") + timedelta(days=10)).strftime("%Y-%m-%d")
        
        self.data = yf.download(self.ticker, start=start, end=end, auto_adjust=True)
        self.benchmark = yf.download("^GSPC", start=start, end=end, auto_adjust=True)
        
        if self.data.empty:
            raise Exception(f"Failed to fetch data for {self.ticker}")
            
    def run(self):
        self.fetch_data()
        
        cash = self.initial_seed
        holdings = 0
        avg_price = 0.0
        
        history = []
        equity_curve = []
        graduations = []
        
        df = self.data
        if isinstance(df.columns, pd.MultiIndex):
            df = df.xs(self.ticker, axis=1, level=1) if self.ticker in df.columns.levels[1] else df
            
        bench_df = self.benchmark
        if isinstance(bench_df.columns, pd.MultiIndex):
            bench_df = bench_df.xs("^GSPC", axis=1, level=1)
            
        for date, row in df.iterrows():
            curr_date_str = date.strftime("%Y-%m-%d")
            if curr_date_str < self.start_date or curr_date_str > self.end_date:
                continue
                
            price = row['Close']
            prev_close = df.shift(1).loc[date, 'Close'] if date in df.index else price
            
            # --- [High Fidelity Logic] ---
            # 1. T-Value & Gears
            base_portion = self.initial_seed / self.split_count
            t_val = (holdings * avg_price) / base_portion if base_portion > 0 else 0
            
            dynamic_split = self.split_count
            if self.version != "V13":
                if t_val >= (self.split_count * 0.9): dynamic_split = self.split_count * 2.5
                elif t_val >= (self.split_count * 0.75): dynamic_split = self.split_count * 2.0
                elif t_val >= (self.split_count * 0.5): dynamic_split = self.split_count * 1.5
            
            one_portion_amt = self.initial_seed / dynamic_split
            
            # 2. V17 Sniper (1/4 Exit at Star Price)
            # Star Price Calculation (Simplified)
            depreciation = 2.0 / self.split_count if self.split_count > 0 else 0.05
            star_ratio = (self.target_profit / 100.0) - ((self.target_profit/100.0) * depreciation * t_val)
            star_price = avg_price * (1 + star_ratio) if avg_price > 0 else 0
            
            if self.version in ["V17", "V24"] and holdings > 4 and price >= star_price and star_price > 0:
                sell_qty = math.ceil(holdings / 4.0)
                profit = (price - avg_price) * sell_qty
                cash += (price * sell_qty)
                holdings -= sell_qty
                # Reset 1 portion immediately (Infinite Energy)
                if cash >= one_portion_amt:
                    buy_back_qty = math.floor(one_portion_amt / price)
                    holdings += buy_back_qty
                    cash -= (buy_back_qty * price)
            
            # 3. Graduation (Full Exit)
            target_price = avg_price * (1 + self.target_profit/100.0)
            if holdings > 0 and price >= target_price:
                profit = (price - avg_price) * holdings
                graduations.append({
                    "date": curr_date_str,
                    "profit": round(profit, 2),
                    "yield": round((price/avg_price - 1)*100, 2)
                })
                cash += (price * holdings)
                holdings = 0
                avg_price = 0.0
                t_val = 0
            
            # 4. Standard Buying + V24 Shadow-Strike
            day_buy_amt = one_portion_amt
            
            # ⚓ Default Safe Ceiling (Standard LOC)
            safe_ceiling = min(avg_price, star_price) if star_price > 0 else avg_price
            
            # 👤 [V24] Shadow-Strike Logic (High Fidelity)
            if self.version == "V24":
                day_low = row['Low']
                # 저점 대비 Bounce % 반등한 가격
                shadow_price = day_low * (1 + self.shadow_bounce / 100.0)
                # 평단 + 5% 까지는 공격적 추격 허용
                shadow_ceiling = avg_price * 1.05 if avg_price > 0 else price * 1.05
                shadow_buy_price = min(shadow_ceiling, shadow_price)
                
                # Shadow 가격이 기존 LOC 천장보다 높다면 상향 조정 (체결 성공률 향상)
                if shadow_buy_price > safe_ceiling:
                    safe_ceiling = shadow_buy_price

            # V24 Turbo (Legacy Compat): -5% drop from prev close = 1 extra portion
            if self.version == "V24" and price < (prev_close * 0.95):
                day_buy_amt += one_portion_amt
            
            # 체결 조건: 당일 종가가 Safe Ceiling 이하인 경우 매수 성공으로 간주
            if price <= safe_ceiling or avg_price == 0:
                if cash >= day_buy_amt:
                    buy_qty = math.floor(day_buy_amt / price)
                    if buy_qty > 0:
                        new_total = holdings + buy_qty
                        avg_price = ((holdings * avg_price) + (buy_qty * price)) / new_total
                        holdings = new_total
                        cash -= (buy_qty * price)
            
            # 5. Snapshot
            current_total = cash + (holdings * price)
            bench_val = bench_df.loc[date, 'Close'] if date in bench_df.index else 1
            
            equity_curve.append({
                "date": curr_date_str,
                "total": round(current_total, 2),
                "benchmark": bench_val,
                "t_val": round(t_val, 2)
            })
            
        # KPI Calculation
        if not equity_curve: return {"error": "No data"}
        
        final_total = equity_curve[-1]['total']
        total_return = (final_total / self.initial_seed - 1) * 100
        peak = max(p['total'] for p in equity_curve)
        mdd = min((p['total'] - peak) / peak * 100 for p in equity_curve)
        
        bench_start = equity_curve[0]['benchmark']
        bench_end = equity_curve[-1]['benchmark']
        bench_return = (bench_end / bench_start - 1) * 100 if bench_start > 0 else 0
        
        return {
            "summary": {
                "ticker": self.ticker,
                "version": self.version,
                "initial_seed": self.initial_seed,
                "final_total": round(final_total, 2),
                "total_return": round(total_return, 2),
                "bench_return": round(bench_return, 2),
                "mdd": round(abs(mdd), 2),
                "graduations": len(graduations)
            },
            "equity_curve": equity_curve,
            "graduations": graduations
        }
