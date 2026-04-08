import pandas as pd
import math
from datetime import datetime

class ParityVRevSimulatorDiag:
    def __init__(self, ticker, initial_seed, config):
        self.ticker = ticker
        self.initial_seed = initial_seed
        self.config = config
        self.cash = initial_seed
        self.cycle_seed = initial_seed 
        self.layers = [] 
        self.history = []
        self.fee_rate = 0.0025 
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
            self.prev_regular_close = float(df.iloc[0]['Open'])

        diag_log = []
        for date in dates:
            day_df = df[df['Date'] == date].sort_values('Datetime_EST')
            if len(day_df) < 10: continue
            
            if not self.layers:
                self.cycle_seed = self.cash
                self.portion = self.cycle_seed * 0.15
            
            anchor = self.prev_regular_close
            daily_open = float(day_df.iloc[0]['Open'])
            buy1_p, buy2_p = anchor * 0.995, anchor * 0.975
            sell1_p = anchor * 1.006
            
            is_strong_up, is_strong_down = False, False
            vwap_history = []
            idx_10pct = int(len(day_df) * 0.1)
            day_buys, day_sells = [], []
            cum_vol, cum_pv, vol_above, vol_below = 0, 0, 0, 0

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
                
                if total_q > 0 and price > avg_p * 1.011:
                    self.cash += (total_q * price) * (1 - self.fee_rate)
                    self.layers = []
                    day_sells.append({"q": total_q, "p": price, "d": "SWEEP"})
                    continue

                if self.layers:
                    top = self.layers[-1]
                    l1_anchor = top.get('anchor', anchor)
                    if price > l1_anchor * 1.006:
                        self.cash += (top['qty'] * price) * (1 - self.fee_rate)
                        self.layers.pop()
                        day_sells.append({"q": top['qty'], "p": price})
                    elif len(self.layers) > 1 and avg_p > 0 and price > avg_p * 1.005:
                        pop_l = self.layers.pop(0)
                        self.cash += (pop_l['qty'] * price) * (1 - self.fee_rate)
                        day_sells.append({"q": pop_l['qty'], "p": price})

                if curr_time < settle_time:
                    if price <= buy1_p: b1_trig_val = True
                    if price <= buy2_p: b2_trig_val = True
                else:
                    if curr_time == settle_time:
                        is_up_day = price > daily_open
                        is_down_day = price < daily_open
                        vw_start = vwap_history[idx_10pct] if len(vwap_history) > idx_10pct else vwap_history[0]
                        vw_slope = curr_vwap - vw_start
                        v_above_pct = vol_above / cum_vol if cum_vol > 0 else 0
                        is_strong_up = is_up_day and vw_slope > 0 and v_above_pct >= 0.60
                        is_strong_down = is_down_day and vw_slope < 0 and (1-v_above_pct) >= 0.60
                    
                    if is_strong_up and idx_step == len(day_df) - 1 and self.get_total_qty() > 0:
                        t_q = self.get_total_qty()
                        self.cash += (t_q * price) * (1 - self.fee_rate)
                        self.layers = []
                        day_sells.append({"q": t_q, "p": price})
                        continue

                    # Slicing logic simplified for diag
                    if not is_strong_up and not is_strong_down and price <= anchor:
                        # (Assume b1_trig/b2_trig were hit)
                        pass

                    if is_strong_down and idx_step == len(day_df) - 1:
                        # Strong down LOC buy
                        q1 = math.floor((self.portion * 0.5) / (price * 1.0025))
                        q2 = math.floor((self.portion * 0.5) / (price * 1.0025))
                        for q in [q1, q2]:
                            if q > 0 and self.cash >= (q * price * 1.0025):
                                self.cash -= (q * price * 1.0025)
                                day_buys.append({"q": q, "p": price})

            if day_buys:
                t_q = sum(b['q'] for b in day_buys)
                t_amt = sum(b['q'] * b['p'] for b in day_buys)
                self.layers.append({"date": str(date), "qty": t_q, "price": t_amt / t_q, "anchor": anchor})

            self.prev_regular_close = float(day_df.iloc[-1]['Close'])
            total_val = self.cash + (self.get_total_qty() * self.prev_regular_close)
            diag_log.append({"Date": str(date), "Total": round(total_val, 2), "Qty": self.get_total_qty(), "Cash": round(self.cash, 2)})

        return pd.DataFrame(diag_log)

if __name__ == "__main__":
    sim = ParityVRevSimulatorDiag("SOXL", 10000, {})
    res = sim.run_simulation("/home/jmyoon312/벡테스트 데이터/1min＿2022.csv")
    print(res.head(20))
