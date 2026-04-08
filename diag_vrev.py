import pandas as pd
import math
from datetime import datetime
import json

class PrecisionVRevSimulatorDiag:
    def __init__(self, ticker, initial_seed, config):
        self.ticker = ticker
        self.initial_seed = initial_seed
        self.config = config
        self.cash = initial_seed
        self.layers = [] 
        self.history = []
        self.fee_rate = 0.0025 
        # 💡 [진단] Portion을 고정이 아닌 유동적으로 가져가는지 확인 필요
        self.portion = initial_seed * 0.15 
        self.vwap_thresh = 0.60
        self.residual_tracker = {"B1": 0.0, "B2": 0.0}
        self.metrics = {"strong_up_days": 0, "strong_down_days": 0, "emergency_moc_hits": 0, "sweep_hits": 0, "layer_sell_hits": 0}
        self.prev_regular_close = None 

    def get_avg_price(self):
        total_qty = sum(l['qty'] for l in self.layers)
        if total_qty == 0: return 0.0
        return sum(l['qty'] * l['price'] for l in self.layers) / total_qty

    def get_total_qty(self): return sum(l['qty'] for l in self.layers)

    def run_simulation(self, csv_path):
        df = pd.read_csv(csv_path)
        df['Datetime_EST'] = pd.to_datetime(df['Datetime_EST'], utc=True)
        df['Date'] = df['Datetime_EST'].dt.date
        dates = df['Date'].unique()
        
        if self.prev_regular_close is None:
            # Jan 3rd 2022의 종가를 찾기 위해 노력 (첫 행의 Open으로 대체)
            self.prev_regular_close = float(df.iloc[0]['Open'])

        diag_log = []

        for date in dates:
            day_df = df[df['Date'] == date].sort_values('Datetime_EST')
            if len(day_df) < 10: continue
            
            anchor = self.prev_regular_close
            daily_open = float(day_df.iloc[0]['Open'])
            buy1_p, buy2_p = anchor * 0.995, anchor * 0.975
            sell1_p = anchor * 1.006
            
            day_buys, day_sells = [], []
            b1_trig, b2_trig = False, False
            cum_vol, cum_pv, vol_above, vol_below = 0, 0, 0, 0
            is_strong_up, is_strong_down = False, False
            
            vwap_history = []
            idx_10pct = int(len(day_df) * 0.1)

            for idx_step, (idx, row) in enumerate(day_df.iterrows()):
                price = float(row['Close'])
                typical_p = (float(row['High']) + float(row['Low']) + price) / 3.0
                vol = float(row['Volume'])
                
                cum_vol += vol
                cum_pv += typical_p * vol
                curr_vwap = cum_pv / cum_vol if cum_vol > 0 else typical_p
                vwap_history.append(curr_vwap)
                
                if typical_p > curr_vwap: vol_above += vol
                else: vol_below += vol
                
                curr_time = row['Datetime_EST'].time()
                settle_time = datetime.strptime("15:30", "%H:%M").time()
                sweep_time = datetime.strptime("15:58", "%H:%M").time()
                
                avg_p = self.get_avg_price()
                total_q = self.get_total_qty()
                
                # 잭팟 스윕
                if total_q > 0 and price > avg_p * 1.01:
                    if curr_time >= sweep_time or price >= avg_p * 1.011:
                        self.cash += (total_q * price) * (1 - self.fee_rate)
                        self.layers = []
                        day_sells.append({"q": total_q, "p": price, "d": "SWEEP"})
                        continue

                # LIFO 매도
                if self.layers:
                    top = self.layers[-1]
                    if price > sell1_p:
                        self.cash += (top['qty'] * price) * (1 - self.fee_rate)
                        self.layers.pop()
                        day_sells.append({"q": top['qty'], "p": price, "d": "L1_EXIT"})
                    elif len(self.layers) > 1 and avg_p > 0 and price > avg_p * 1.005:
                        pop_l = self.layers.pop(0)
                        self.cash += (pop_l['qty'] * price) * (1 - self.fee_rate)
                        day_sells.append({"q": pop_l['qty'], "p": price, "d": "RESCUE"})

                if curr_time < settle_time:
                    if price <= buy1_p: b1_trig = True
                    if price <= buy2_p: b2_trig = True
                else:
                    if curr_time == settle_time:
                        is_up_day = price > daily_open
                        is_down_day = price < daily_open
                        vw_start = vwap_history[idx_10pct] if len(vwap_history) > idx_10pct else vwap_history[0]
                        vw_slope = curr_vwap - vw_start
                        v_above_pct = vol_above / cum_vol if cum_vol > 0 else 0
                        v_below_pct = vol_below / cum_vol if cum_vol > 0 else 0
                        is_strong_up = is_up_day and vw_slope > 0 and v_above_pct >= 0.60
                        is_strong_down = is_down_day and vw_slope < 0 and v_below_pct >= 0.60

                    is_strong = is_strong_up or is_strong_down
                    f1_pass = price <= anchor and (avg_p == 0 or price <= avg_p)
                    
                    if not is_strong and f1_pass:
                        bin_idx = curr_time.minute - 30
                        if 0 <= bin_idx < 30:
                            ratio = (1/30.0) / ( (30 - bin_idx) / 30.0 )
                            for tid in ["B1", "B2"]:
                                trig = b1_trig if tid == "B1" else b2_trig
                                if trig:
                                    exact_q = ((self.portion * 0.5) * (1/30.0) / (price * 1.0025)) + self.residual_tracker[tid]
                                    q = math.floor(exact_q)
                                    self.residual_tracker[tid] = exact_q - q
                                    if q > 0 and self.cash >= (q * price * 1.0025):
                                        self.cash -= (q * price * 1.0025)
                                        day_buys.append({"q": q, "p": price})

                    if is_strong and idx_step == len(day_df) - 1:
                        for trig in [b1_trig, b2_trig]:
                            if trig:
                                q = math.floor((self.portion * 0.5) / (price * 1.0025))
                                if q > 0 and self.cash >= (q * price * 1.0025):
                                    self.cash -= (q * price * 1.0025)
                                    day_buys.append({"q": q, "p": price})

            if day_buys:
                t_q = sum(b['q'] for b in day_buys)
                t_amt = sum(b['q'] * b['p'] for b in day_buys)
                self.layers.append({"date": str(date), "qty": t_q, "price": t_amt / t_q, "anchor": anchor})
                self.residual_tracker = {"B1": 0.0, "B2": 0.0}

            self.prev_regular_close = float(day_df.iloc[-1]['Close'])
            total_val = self.cash + (self.get_total_qty() * self.prev_regular_close)
            
            diag_log.append({
                "Date": str(date),
                "Close": round(self.prev_regular_close, 2),
                "Cash": round(self.cash, 2),
                "Qty": self.get_total_qty(),
                "AvgPrice": round(self.get_avg_price(), 2),
                "TotalVal": round(total_val, 2),
                "Buys": sum(b['q'] for b in day_buys),
                "Sells": sum(s['q'] for s in day_sells),
                "Regime": "StrongUp" if is_strong_up else ("StrongDown" if is_strong_down else "Stable")
            })

        return pd.DataFrame(diag_log)

if __name__ == "__main__":
    sim = PrecisionVRevSimulatorDiag("SOXL", 10000, {})
    res = sim.run_simulation("/home/jmyoon312/벡테스트 데이터/1min＿2022.csv")
    res.to_csv("/home/jmyoon312/diag_vrev_2022.csv", index=False)
    print("Diagnosis complete. File saved to diag_vrev_2022.csv")
    print(res.head(20))
