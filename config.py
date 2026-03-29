# ==========================================================
# [config.py]
# ⚠️ 이 주석 및 파일명 표기는 절대 지우지 마세요.
# ==========================================================
import json
import os
import datetime
import pytz
import math
import time
import shutil
import tempfile
import pandas_market_calendars as mcal

try:
    from version_history import VERSION_HISTORY
except ImportError:
    VERSION_HISTORY = ["V14.x [-] 버전 기록 파일(version_history.py)을 찾을 수 없습니다."]

class ConfigManager:
    def __init__(self, is_real=None):
        # ⚠️ [MODE] 파일은 루트의 data/ 폴더에 고정 (UI의 기본 뷰 모드 설정 역할)
        self.MODE_FILE = "data/trading_mode.dat"

        # 🌐 [V23.1 Dual-Core] 인스턴스 생성 시 모드를 강제 지정하거나 파일에서 읽음
        if is_real is not None:
            self.is_real = bool(is_real)
        else:
            self.is_real = self._load_mode_file()
            
        self._ensure_dirs()
        
        self.FILES = {
            "TOKEN": "token.dat",
            "CHAT_ID": "chat_id.dat",
            "LEDGER": "manual_ledger.json",    
            "HISTORY": "manual_history.json",  
            "SPLIT": "split_config.json",
            "TICKER": "active_tickers.json",
            "TURBO": "turbo_mode.dat",
            "ENGINE_STATUS": "engine_status.dat", # 🚀 [V22.3] 엔진 가동 상태 (ON/OFF)
            "SECRET_MODE": "secret_mode.dat",
            "PROFIT_CFG": "profit_config.json",
            "LOCKS": "trade_locks.json",
            "SEED_CFG": "seed_config.json",         
            "COMPOUND_CFG": "compound_config.json",
            "VERSION_CFG": "version_config.json",
            "REVERSE_CFG": "reverse_config.json",
            "ACTIVE_SEED_CFG": "active_seed.json",  # 🌐 [V23.1 Dual-Core] 현재 사이클용 액티브 시드 (qty > 0일 때 고정)
            "SNIPER_MULTIPLIER_CFG": "sniper_multiplier.json",
            "SPLIT_HISTORY": "split_history.json",
            "PORTFOLIO_RATIO": "portfolio_ratio.json",
            "SNAPSHOTS": "daily_snapshots.json",
            "CAPITAL": "capital_flow.json",
            "LIVE_STATUS": "live_status.json",
            "ENGINE_STATUS": "engine_status.dat",
            "REFRESH_TRIGGER": "refresh_needed.tmp",
            "SHADOW_CFG": "shadow_config.json", # 👤 [V24] Shadow-Strike 설정 (ON/OFF, Bounce)
            "EVENT_LOG": "event_log.json"
        }
        
        self.DEFAULT_SEED = {"SOXL": 6720.0, "TQQQ": 6720.0}
        self.DEFAULT_SPLIT = {"SOXL": 40.0, "TQQQ": 40.0}
        self.DEFAULT_TARGET = {"SOXL": 12.0, "TQQQ": 10.0}
        self.DEFAULT_COMPOUND = {"SOXL": 100.0, "TQQQ": 100.0}
        self.DEFAULT_VERSION = {"SOXL": "V14", "TQQQ": "V14"}
        self.DEFAULT_PORTFOLIO_RATIO = {"SOXL": 0.55, "TQQQ": 0.45} # 🌟 [V22 패치] 100% 동적분할 기본 타겟 비중 (예비비 0%)
        
        self.DEFAULT_SNIPER_MULTIPLIER = {"SOXL": 1.0, "TQQQ": 0.9}
        self.DEFAULT_SHADOW_BOUNCE = 1.5 # 🌟 [V24] 기본 반등 비율 (1.5%)

    def _get_base_dir(self):
        """🌟 [V22.2] 현재 모드에 따른 전용 데이터 디렉토리 반환"""
        base = "data/real" if self.is_real else "data/mock"
        if not os.path.exists(base):
            os.makedirs(base, exist_ok=True)
        return base

    def _ensure_dirs(self):
        """기본 디렉토리 생성 보장"""
        if not os.path.exists("data"): os.makedirs("data")
        self._get_base_dir()

    def _get_file_path(self, key):
        """파일명 키값에 대해 현재 모드의 절대 경로를 반환합니다."""
        if key not in self.FILES:
            return f"data/{key}"
        return os.path.join(self._get_base_dir(), self.FILES[key])

    def _load_json(self, key, default=None):
        filename = self._get_file_path(key)
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ [Config] JSON 로드 에러 ({filename}): {e}")
                try:
                    shutil.copy(filename, filename + f".bak_{int(time.time())}")
                except Exception as backup_e:
                    print(f"⚠️ [Config] 백업 실패: {backup_e}")
                return default if default is not None else {}
        return default if default is not None else {}

    def get_ratio(self, ticker):
        """💰 [V24] 종목별 포트폴리오 비중 획득 (기본값: 균등 배분)"""
        try:
            ratios = self._load_json("PORTFOLIO_RATIO", {})
            if not ratios:
                return self.DEFAULT_PORTFOLIO_RATIO.get(ticker, 0.5)
            
            val = ratios.get(ticker)
            if val is None:
                return self.DEFAULT_PORTFOLIO_RATIO.get(ticker, 0.5)
            return float(val)
        except Exception:
            return 0.5

    def _save_json(self, key, data):
        filename = self._get_file_path(key)
        try:
            dir_name = os.path.dirname(filename)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name, exist_ok=True)
                
            fd, temp_path = tempfile.mkstemp(dir=dir_name, text=True)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()         
                os.fsync(fd)      
                
            os.replace(temp_path, filename)
        except Exception as e:
            print(f"❌ [Config] JSON 저장 중 치명적 에러 발생 ({filename}): {e}")
            if 'temp_path' in locals() and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def _load_file(self, key, default=None):
        filename = self._get_file_path(key)
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception as e:
                print(f"⚠️ [Config] 파일 로드 에러 ({filename}): {e}")
        return default

    def _save_file(self, key, content):
        filename = self._get_file_path(key)
        try:
            dir_name = os.path.dirname(filename)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name, exist_ok=True)
                
            fd, temp_path = tempfile.mkstemp(dir=dir_name, text=True)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(str(content))
                f.flush()
                os.fsync(fd)
            os.replace(temp_path, filename)
        except Exception as e:
            print(f"❌ [Config] 텍스트 파일 저장 에러 ({filename}): {e}")

    def get_last_split_date(self, ticker):
        return self._load_json("SPLIT_HISTORY", {}).get(ticker, "")

    def set_last_split_date(self, ticker, date_str):
        d = self._load_json("SPLIT_HISTORY", {})
        d[ticker] = date_str
        self._save_json("SPLIT_HISTORY", d)

    def get_ledger(self):
        return self._load_json("LEDGER", [])

    def get_escrow_cash(self, ticker):
        locks = self._load_json("LOCKS", {})
        return float(locks.get(f"ESCROW_{ticker}", 0.0))

    def set_escrow_cash(self, ticker, amount):
        locks = self._load_json("LOCKS", {})
        locks[f"ESCROW_{ticker}"] = float(amount)
        self._save_json("LOCKS", locks)

    def add_escrow_cash(self, ticker, amount):
        current = self.get_escrow_cash(ticker)
        self.set_escrow_cash(ticker, current + float(amount))

    def clear_escrow_cash(self, ticker):
        locks = self._load_json("LOCKS", {})
        if f"ESCROW_{ticker}" in locks:
            del locks[f"ESCROW_{ticker}"]
            self._save_json("LOCKS", locks)

    def get_total_locked_cash(self, exclude_ticker=None):
        locks = self._load_json(self.FILES["LOCKS"], {})
        total = 0.0
        for k, v in locks.items():
            if k.startswith("ESCROW_"):
                ticker_in_lock = k.replace("ESCROW_", "")
                if ticker_in_lock != exclude_ticker:
                    total += float(v)
        return total

    # ==========================================================
    # 👤 [V24] Shadow-Strike 전용 설정 메서드
    # ==========================================================
    def get_shadow_config(self, ticker):
        """Shadow 모드 활성화 여부 및 반등 비율 획득"""
        cfg = self._load_json("SHADOW_CFG", {})
        return cfg.get(ticker, {"active": False, "bounce": self.DEFAULT_SHADOW_BOUNCE})

    def set_shadow_config(self, ticker, active, bounce):
        """Shadow 모드 설정 저장"""
        cfg = self._load_json("SHADOW_CFG", {})
        cfg[ticker] = {
            "active": bool(active),
            "bounce": float(bounce)
        }
        self._save_json("SHADOW_CFG", cfg)
        self.record_event("STRATEGY", "UPDATE", f"[{ticker}] Shadow-Strike 설정 변경 (Active: {active}, Bounce: {bounce}%)")

    def is_shadow_active(self, ticker):
        return self.get_shadow_config(ticker).get("active", False)

    def get_shadow_bounce(self, ticker):
        return self.get_shadow_config(ticker).get("bounce", self.DEFAULT_SHADOW_BOUNCE)

    def get_absolute_t_val(self, ticker, actual_qty, actual_avg_price):
        seed = self.get_seed(ticker)
        split = self.get_split_count(ticker)
        one_portion = seed / split if split > 0 else 1
        t_val = (actual_qty * actual_avg_price) / one_portion if one_portion > 0 else 0.0
        return round(t_val, 4), one_portion

    def apply_stock_split(self, ticker, ratio):
        if ratio <= 0: return
        ledger = self.get_ledger()
        changed = False
        for r in ledger:
            if r.get('ticker') == ticker:
                new_qty = round(r['qty'] * ratio)
                r['qty'] = new_qty if new_qty > 0 else (1 if r['qty'] > 0 else 0)
                r['price'] = round(r['price'] / ratio, 4)
                if 'avg_price' in r:
                    r['avg_price'] = round(r['avg_price'] / ratio, 4)
                changed = True
        if changed:
            self._save_json("LEDGER", ledger)

    def overwrite_genesis_ledger(self, ticker, genesis_records, actual_avg):
        ledger = self.get_ledger()
        remaining = [r for r in ledger if r['ticker'] != ticker]
        
        for i, rec in enumerate(genesis_records):
            remaining.append({
                "id": i + 1,
                "date": rec['date'],
                "ticker": ticker,
                "side": rec['side'],
                "price": rec['price'],
                "qty": rec['qty'],
                "avg_price": actual_avg, 
                "exec_id": f"GENESIS_{int(time.time())}_{i}",
                "is_reverse": False 
            })
        self._save_json("LEDGER", remaining)

    def overwrite_incremental_ledger(self, ticker, temp_recs, new_today_records):
        ledger = self.get_ledger()
        remaining = [r for r in ledger if r['ticker'] != ticker]
        updated_ticker_recs = list(temp_recs)
        
        current_rev_state = self.get_reverse_state(ticker).get("is_active", False)
        max_id = max([r.get('id', 0) for r in ledger] + [0])
        
        for i, rec in enumerate(new_today_records):
            max_id += 1
            new_row = {
                "id": max_id,
                "date": rec['date'],
                "ticker": ticker,
                "side": rec['side'],
                "price": rec['price'],
                "qty": rec['qty'],
                "avg_price": rec['avg_price'],
                "exec_id": rec.get("exec_id", f"FASTTRACK_{int(time.time())}_{i}"),
                "is_reverse": current_rev_state
            }
            if "desc" in rec:
                new_row["desc"] = rec["desc"]
                
            updated_ticker_recs.append(new_row)
            
        remaining.extend(updated_ticker_recs)
        self._save_json("LEDGER", remaining)

    def overwrite_ledger(self, ticker, actual_qty, actual_avg):
        ledger = self.get_ledger()
        remaining = [r for r in ledger if r['ticker'] != ticker]
        
        kst = pytz.timezone('Asia/Seoul')
        today_str = datetime.datetime.now(kst).strftime('%Y-%m-%d')
        new_id = 1 if not remaining else max(r.get('id', 0) for r in remaining) + 1
        
        remaining.append({
            "id": new_id, "date": today_str, "ticker": ticker, "side": "BUY",
            "price": actual_avg, "qty": actual_qty, "avg_price": actual_avg, 
            "exec_id": f"INIT_{int(time.time())}", "desc": "초기동기화", "is_reverse": False
        })
        self._save_json("LEDGER", remaining)

    def calibrate_avg_price(self, ticker, actual_avg):
        ledger = self.get_ledger()
        target_recs = [r for r in ledger if r['ticker'] == ticker]
        if target_recs:
            for r in target_recs:
                r['avg_price'] = actual_avg
            self._save_json("LEDGER", ledger)

    def clear_ledger_for_ticker(self, ticker):
        ledger = self.get_ledger()
        remaining = [r for r in ledger if r['ticker'] != ticker]
        self._save_json("LEDGER", remaining)
        self.set_reverse_state(ticker, False, 0, 0.0)
        self.clear_escrow_cash(ticker)

    def calculate_holdings(self, ticker, records=None):
        if records is None:
            records = self.get_ledger()
        target_recs = [r for r in records if r['ticker'] == ticker]
        total_qty, total_invested, total_sold = 0, 0.0, 0.0    
        
        for r in target_recs:
            if r['side'] == 'BUY':
                total_qty += r['qty']
                total_invested += (r['price'] * r['qty'])
            elif r['side'] == 'SELL':
                total_qty -= r['qty']
                total_sold += (r['price'] * r['qty'])
        
        total_qty = max(0, int(total_qty))
        invested_up = math.ceil(total_invested * 100) / 100.0
        sold_up = math.ceil(total_sold * 100) / 100.0
        
        if total_qty == 0:
            avg_price = 0.0
        else:
            avg_price = 0.0
            if target_recs:
                avg_price = float(target_recs[-1].get('avg_price', 0.0))
                if avg_price == 0.0:
                    buy_sum = sum(r['price']*r['qty'] for r in target_recs if r['side']=='BUY')
                    buy_qty = sum(r['qty'] for r in target_recs if r['side']=='BUY')
                    if buy_qty > 0:
                        avg_price = buy_sum / buy_qty
        
        return total_qty, avg_price, invested_up, sold_up

    def get_reverse_state(self, ticker):
        d = self._load_json("REVERSE_CFG", {})
        return d.get(ticker, {"is_active": False, "day_count": 0, "exit_target": 0.0, "last_update_date": ""})

    def set_reverse_state(self, ticker, is_active, day_count, exit_target=0.0, last_update_date=None):
        if last_update_date is None:
            est = pytz.timezone('US/Eastern')
            last_update_date = datetime.datetime.now(est).strftime('%Y-%m-%d')
            
        d = self._load_json("REVERSE_CFG", {})
        d[ticker] = {"is_active": is_active, "day_count": day_count, "exit_target": exit_target, "last_update_date": last_update_date}
        self._save_json("REVERSE_CFG", d)

    def update_reverse_day_if_needed(self, ticker):
        return False

    def increment_reverse_day(self, ticker):
        state = self.get_reverse_state(ticker)
        if state.get("is_active"):
            est = pytz.timezone('US/Eastern')
            now_est = datetime.datetime.now(est)
            today_est_str = now_est.strftime('%Y-%m-%d')
            
            if state.get("last_update_date") != today_est_str:
                nyse = mcal.get_calendar('NYSE')
                is_trading_day = not nyse.schedule(start_date=now_est.date(), end_date=now_est.date()).empty
                
                if is_trading_day:
                    new_day = state.get("day_count", 0) + 1
                    self.set_reverse_state(ticker, True, new_day, state.get("exit_target", 0.0), today_est_str)
                    return True
                else:
                    self.set_reverse_state(ticker, True, state.get("day_count", 0), state.get("exit_target", 0.0), today_est_str)
                    return False
        return False

    def calculate_v14_state(self, ticker):
        ledger = self.get_ledger()
        target_recs = sorted([r for r in ledger if r['ticker'] == ticker], key=lambda x: x.get('id', 0))
        
        seed = self.get_seed(ticker)
        split = self.get_split_count(ticker)
        base_portion = seed / split if split > 0 else 1
        
        holdings = 0
        rem_cash = seed
        total_invested = 0.0
        
        for r in target_recs:
            if holdings == 0:
                rem_cash = seed
                total_invested = 0.0
                
            qty = r['qty']
            amt = qty * r['price']
            
            if r['side'] == 'BUY':
                rem_cash -= amt
                holdings += qty
                total_invested += amt
                
            elif r['side'] == 'SELL':
                if qty >= holdings: 
                    holdings = 0
                    rem_cash = seed
                    total_invested = 0.0
                else: 
                    if holdings > 0:
                        avg_price = total_invested / holdings
                        total_invested -= (qty * avg_price)
                    holdings -= qty
                    rem_cash += amt
                    
        avg_price = total_invested / holdings if holdings > 0 else 0.0
        t_val = (holdings * avg_price) / base_portion if base_portion > 0 else 0.0
            
        if holdings > 0:
            safe_denom = max(1.0, split - t_val)
            current_budget = rem_cash / safe_denom
        else:
            current_budget = base_portion
            t_val = 0.0
            
        return max(0.0, round(t_val, 4)), max(0.0, current_budget), max(0.0, rem_cash)

    def archive_graduation(self, ticker, end_date, prev_close=0.0):
        ledger = self.get_ledger()
        target_recs = [r for r in ledger if r['ticker'] == ticker]
        if not target_recs:
            return None, 0
        
        ledger_qty, avg_price, _, _ = self.calculate_holdings(ticker, target_recs)
        
        if ledger_qty > 0:
            split = self.get_split_count(ticker)
            is_reverse = self.get_reverse_state(ticker).get("is_active", False)

            if is_reverse:
                divisor = 10 if split <= 20 else 20
                loc_qty = math.floor(ledger_qty / divisor)
            else:
                loc_qty = math.ceil(ledger_qty / 4)

            limit_qty = ledger_qty - loc_qty
            if limit_qty < 0: 
                loc_qty = ledger_qty
                limit_qty = 0

            target_ratio = self.get_target_profit(ticker) / 100.0
            target_price = math.ceil(avg_price * (1 + target_ratio) * 100) / 100.0
            loc_price = prev_close if prev_close > 0 else avg_price

            new_id = max((r.get('id', 0) for r in ledger), default=0) + 1

            if loc_qty > 0:
                rec_loc = {"id": new_id, "date": end_date, "ticker": ticker, "side": "SELL", "price": loc_price, "qty": loc_qty, "avg_price": avg_price, "exec_id": f"GRAD_LOC_{int(time.time())}", "is_reverse": is_reverse}
                ledger.append(rec_loc)
                target_recs.append(rec_loc)
                new_id += 1

            if limit_qty > 0:
                rec_limit = {"id": new_id, "date": end_date, "ticker": ticker, "side": "SELL", "price": target_price, "qty": limit_qty, "avg_price": avg_price, "exec_id": f"GRAD_LMT_{int(time.time())}", "is_reverse": is_reverse}
                ledger.append(rec_limit)
                target_recs.append(rec_limit)

            self._save_json("LEDGER", ledger)

        total_buy = math.ceil(sum(r['price']*r['qty'] for r in target_recs if r['side']=='BUY') * 100) / 100.0
        total_sell = math.ceil(sum(r['price']*r['qty'] for r in target_recs if r['side']=='SELL') * 100) / 100.0
        
        profit = math.ceil((total_sell - total_buy) * 100) / 100.0
        yield_pct = math.ceil(((profit / total_buy * 100) if total_buy > 0 else 0.0) * 100) / 100.0
        
        compound_rate = self.get_compound_rate(ticker) / 100.0
        added_seed = 0
        if profit > 0 and compound_rate > 0:
            added_seed = math.floor(profit * compound_rate)
            current_seed = self.get_seed(ticker)
            self.set_seed(ticker, current_seed + added_seed)

        history = self._load_json("HISTORY", [])
        new_hist = {
            "id": len(history) + 1, "ticker": ticker, "end_date": end_date,
            "profit": profit, "yield": yield_pct, "revenue": total_sell, "invested": total_buy, "trades": target_recs
        }
        history.append(new_hist)
        self._save_json("HISTORY", history)
        
        self.clear_ledger_for_ticker(ticker)
        
        return new_hist, added_seed

    def get_full_version_history(self):
        return VERSION_HISTORY

    def get_version_history(self):
        return VERSION_HISTORY

    def get_latest_version(self):
        history = self.get_version_history()
        if history and len(history) > 0:
            latest_entry = history[-1]
            if isinstance(latest_entry, dict):
                return latest_entry.get("version", "V14.x")
            elif isinstance(latest_entry, str):
                return latest_entry.split(' ')[0] 
        return "V14.x"

    def get_history(self):
        """졸업(수익확정) 기록을 불러옵니다. manual_history.json이 없으면 ledger.json에서 추출을 시도합니다."""
        history = self._load_json("HISTORY", [])
        if not history:
            # ledger.json에서 '졸업' 또는 큰 규모의 'SELL' 항목을 찾아 history 대용으로 사용
            ledger = self._load_json("LEDGER", [])
            for item in ledger:
                if "졸업" in item.get("desc", "") or "익절" in item.get("desc", ""):
                    history.append({
                        "ticker": item.get("ticker", "UNKNOWN"),
                        "profit": item.get("profit", 0.0),
                        "yield": item.get("yield", 0.0),
                        "end_date": item.get("date", "").split(" ")[0]
                    })
        return history


    def record_daily_snapshot(self, total_cash, holdings_value):
        """매일 장 마감 시 자산 상태를 스냅샷으로 저장합니다. (비중 표시용 개별 종목 평가금 포함)"""
        snapshots = self._load_json("SNAPSHOTS", [])
        est = pytz.timezone('US/Eastern')
        today = datetime.datetime.now(est).strftime('%Y-%m-%d')
        
        # [V24] 실시간 상태에서 종목별 비중 정보를 가져와 함께 저장합니다.
        live_status = self._load_json("LIVE_STATUS", {})
        ticker_eval = {}
        if "tickers" in live_status:
            for t, info in live_status["tickers"].items():
                eval_val = info.get("qty", 0) * info.get("current_price", 0)
                if eval_val > 0: ticker_eval[t] = round(eval_val, 2)
        
        # holdings_value가 0이면 live_status에서 합산 시도 (자산 표시 버그 수정)
        if holdings_value <= 0 and ticker_eval:
            holdings_value = sum(ticker_eval.values())

        new_snap = {
            "date": today,
            "cash": round(total_cash, 2),
            "holdings": round(holdings_value, 2),
            "total": round(total_cash + holdings_value, 2),
            "ticker_eval": ticker_eval
        }
        
        idx = next((i for i, s in enumerate(snapshots) if s['date'] == today), -1)
        if idx >= 0:
            snapshots[idx] = new_snap
        else:
            snapshots.append(new_snap)
            
        self._save_json("SNAPSHOTS", snapshots)
        return new_snap


    def add_capital_flow(self, amount, flow_type="DEPOSIT"):
        """자본금 입출금 기록을 저장합니다 (수익률 계산 보정용)."""
        flows = self._load_json("CAPITAL", [])
        est = pytz.timezone('US/Eastern')
        today = datetime.datetime.now(est).strftime('%Y-%m-%d %H:%M:%S')
        
        flows.append({
            "date": today,
            "amount": float(amount),
            "type": flow_type
        })
        self._save_json("CAPITAL", flows)

    def get_analytics_data(self):
        """프론트엔드 분석 대시보드용 통합 데이터를 반환합니다 (실시간 상태 포함)."""
        snapshots = self._load_json("SNAPSHOTS", [])
        history = self.get_history()
        live_status = self._load_json("LIVE_STATUS", {})
        
        # 실시간 현재 자산 정보 추출 (대시보드 상단 바용)
        # live_status.json 구조: {"cash": 123, "holdings_value": 456, "tickers": {...}}
        current_valuation = {
            "cash": live_status.get("cash", 0),
            "holdings": live_status.get("holdings_value", 0),
            "total": live_status.get("cash", 0) + live_status.get("holdings_value", 0),
            "ticker_eval": {}
        }
        
        if "tickers" in live_status:
            for t, info in live_status["tickers"].items():
                eval_val = info.get("qty", 0) * info.get("current_price", 0)
                if eval_val > 0:
                    current_valuation["ticker_eval"][t] = round(eval_val, 2)

        # 성과 지표 계산
        pos_profits = [h.get('profit', 0) for h in history if h.get('profit', 0) > 0]
        neg_profits = [h.get('profit', 0) for h in history if h.get('profit', 0) < 0]
        
        win_count = len(pos_profits)
        total_trades = len(history)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
        
        total_p = sum(pos_profits)
        total_l = abs(sum(neg_profits))
        profit_factor = (total_p / total_l) if total_l > 0 else (total_p if total_p > 0 else 0)
        
        # [V23.5] Advanced Analytics Calculation
        holding_periods = []
        ticker_performance = {}

        for h in history:
            # 1. Holding Period Analysis
            start_date = h.get("start_date")
            end_date = h.get("end_date")
            if start_date and end_date:
                try:
                    s_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d")
                    e_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d")
                    holding_periods.append(max(0, (e_dt - s_dt).days))
                except: pass
            
            # 2. Ticker-wise Performance
            ticker = h.get("ticker", "UNKNOWN")
            if ticker not in ticker_performance:
                ticker_performance[ticker] = {"profit": 0, "count": 0, "win": 0}
            
            p = h.get("profit", 0)
            ticker_performance[ticker]["profit"] += p
            ticker_performance[ticker]["count"] += 1
            if p > 0: ticker_performance[ticker]["win"] += 1

        avg_holding = round(sum(holding_periods) / len(holding_periods), 1) if holding_periods else 0

        # [V23.5] Manual Sync Tracking
        live_status = self._load_json("LIVE_STATUS", {})
        last_sync = live_status.get("last_manual_sync")
        if not last_sync:
            # Fallback if field is missing but we want to show something
            last_sync = {"timestamp": 0, "status": "IDLE", "msg": "대기 중"}

        return {
            "current_valuation": current_valuation,
            "snapshots": snapshots,
            "capital_flows": self._load_json("CAPITAL", []),
            "history": history,
            "metrics": {
                "win_rate": round(win_rate, 2),
                "profit_factor": round(profit_factor, 2),
                "total_trades": total_trades,
                "gross_profit": round(total_p, 2),
                "gross_loss": round(total_l, 2),
                "avg_holding_days": avg_holding,
                "ticker_performance": ticker_performance
            },
            "last_manual_sync": last_sync,
            "cycles": self.get_cycle_analytics(), # 사이클 분석 데이터 추가
            "periodical": self.get_periodical_analytics(),
            "tax": self.calculate_tax_estimation(),
            "events": self.get_recent_events(limit=15)
        }

    def record_event(self, task_name, status, message, details=None):
        """자율 주행 엔진의 개별 작업 결과를 기록합니다 (상황실 로그용)."""
        events = self._load_json("EVENT_LOG", [])
        
        # 최신 100개까지만 유지 (대기열 관리)
        if len(events) > 100:
            events = events[-100:]
            
        est = pytz.timezone('US/Eastern')
        now = datetime.datetime.now(est).strftime('%H:%M:%S')
        
        events.append({
            "time": now,
            "task": task_name,
            "status": status, # "SUCCESS", "ERROR", "PENDING"
            "msg": message,
            "details": details
        })
        self._save_json("EVENT_LOG", events)

    def get_recent_events(self, limit=10):
        """최근 실행된 작업 로그를 반환합니다."""
        events = self._load_json("EVENT_LOG", [])
        return events[-limit:] if events else []

    def get_ledger_explorer_data(self):
        """장부 탐색기를 위한 평탄화된 모든 거래 내역 반환 (활성 + 과거)"""
        active_ledger = self.get_ledger()
        history = self.get_history()
        
        all_records = []
        
        # 1. 활성 장부 데이터 (현재 진행 중인 매수 분할 내역)
        for t in active_ledger:
            all_records.append({
                "date": t.get("date"),
                "ticker": t.get("ticker"),
                "side": t.get("side", "BUY"),
                "price": t.get("price"),
                "qty": t.get("qty"),
                "status": "ACTIVE",
                "note": t.get("desc", "분할 매수 진행 중")
            })
        
        # 2. 과거 졸업 내역 데이터 (이미 청산 완료된 내역)
        for h in history:
            ticker = h.get("ticker")
            trades = h.get("trades", [])
            for t in trades:
                all_records.append({
                    "date": t.get("date"),
                    "ticker": ticker,
                    "side": t.get("side", "BUY"),
                    "price": t.get("price"),
                    "qty": t.get("qty"),
                    "status": "GRADUATED",
                    "note": t.get("desc", "정상 졸업 청산")
                })
                
        # 날짜 내림차순 정렬
        all_records.sort(key=lambda x: str(x.get("date", "")), reverse=True)
        return all_records

    def get_cycle_analytics(self):
        """거래 내역을 '사이클(매수 시작~졸업)' 단위로 묶어서 요약 데이터를 생성합니다."""
        history = self.get_history()
        active_ledger = self.get_ledger()
        
        cycles = []
        
        # 1. 졸업(완료) 사이클 처리
        # HISTORY의 각 항목은 이미 하나의 졸업된 사이클을 나타냅니다.
        for h in history:
            trades = h.get("trades", [])
            start_date = trades[0].get("date") if trades else h.get("end_date")
            
            cycles.append({
                "ticker": h.get("ticker"),
                "status": "GRADUATED",
                "start_date": start_date,
                "end_date": h.get("end_date"),
                "invested": h.get("invested", 0),
                "revenue": h.get("revenue", 0),
                "profit": h.get("profit", 0),
                "yield": h.get("yield", 0),
                "trade_count": len(trades),
                "trades": trades
            })
            
        # 2. 활성(진행 중) 사이클 처리
        # 종목별로 그룹화하여 현재 진행 상태를 요약합니다.
        active_map = {}
        for t in active_ledger:
            ticker = t.get("ticker")
            if ticker not in active_map:
                active_map[ticker] = []
            active_map[ticker].append(t)
            
        for ticker, trades in active_map.items():
            total_buy = sum(r['price'] * r['qty'] for r in trades if r['side'] == 'BUY')
            total_sell = sum(r['price'] * r['qty'] for r in trades if r['side'] == 'SELL')
            net_invested = total_buy - total_sell
            
            start_date = trades[0].get("date") if trades else "N/A"
            
            cycles.append({
                "ticker": ticker,
                "status": "ACTIVE",
                "start_date": start_date,
                "end_date": "-",
                "invested": round(net_invested, 2),
                "revenue": 0,
                "profit": 0,
                "yield": 0,
                "trade_count": len(trades),
                "trades": trades
            })
            
        # 최신 시작일 순으로 정렬
        cycles.sort(key=lambda x: str(x.get("start_date", "")), reverse=True)
        return cycles

    def get_periodical_analytics(self):
        """기록된 졸업 데이터를 기반으로 연/월별 수익 현황을 집계합니다."""
        history = self.get_history()
        periodical = {}
        for h in history:
            date_str = h.get('end_date', '')
            if not date_str: continue
            try:
                dt = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                year = str(dt.year)
                month = f"{dt.month:02d}"
                
                if year not in periodical: periodical[year] = {"profit": 0, "months": {}}
                if month not in periodical[year]["months"]: periodical[year]["months"][month] = 0
                
                profit = h.get('profit', 0.0)
                periodical[year]["profit"] += profit
                periodical[year]["months"][month] += profit
            except: continue
        return periodical

    def calculate_tax_estimation(self):
        """올해 발생한 수익을 기반으로 미국 주식 양도소득세(22%)를 추산합니다."""
        history = self.get_history()
        this_year = str(datetime.datetime.now().year)
        
        yearly_profit = sum(h.get('profit', 0) for h in history if h.get('end_date', '').startswith(this_year))
        
        # 기본 공제액 (약 $2,000 / 250만원 가정)
        allowance = 2000.0
        taxable = max(0, yearly_profit - allowance)
        estimated_tax = taxable * 0.22
        
        return {
            "year": this_year,
            "total_profit": round(yearly_profit, 2),
            "allowance": allowance,
            "taxable_profit": round(taxable, 2),
            "estimated_tax": round(estimated_tax, 2)
        }


    def check_lock(self, ticker, market_type):
        est = pytz.timezone('US/Eastern')
        today = datetime.datetime.now(est).strftime('%Y-%m-%d')
        locks = self._load_json("LOCKS", {})
        return locks.get(f"{today}_{ticker}_{market_type}", False)

    def set_lock(self, ticker, market_type):
        est = pytz.timezone('US/Eastern')
        today = datetime.datetime.now(est).strftime('%Y-%m-%d')
        locks = self._load_json("LOCKS", {})
        locks[f"{today}_{ticker}_{market_type}"] = True
        self._save_json("LOCKS", locks)

    def reset_locks(self):
        locks = self._load_json("LOCKS", {})
        surviving_locks = {k: v for k, v in locks.items() if k.startswith("ESCROW_")}
        self._save_json("LOCKS", surviving_locks)
        
    def reset_lock_for_ticker(self, ticker):
        est = pytz.timezone('US/Eastern')
        today = datetime.datetime.now(est).strftime('%Y-%m-%d')
        locks = self._load_json("LOCKS", {})
        
        keys_to_delete = [k for k in locks.keys() if k.startswith(f"{today}_{ticker}")]
        if keys_to_delete:
            for k in keys_to_delete:
                del locks[k]
            self._save_json("LOCKS", locks)
    
    def get_seed(self, t):
        """🌟 [V23.1] 사용자가 설정한 '예약(Reserved)' 시드 반환"""
        return float(self._load_json("SEED_CFG", self.DEFAULT_SEED).get(t, 6720.0))

    def set_seed(self, t, v): 
        d = self._load_json("SEED_CFG", self.DEFAULT_SEED)
        d[t] = v
        self._save_json("SEED_CFG", d)

    def get_active_seed(self, t):
        """🚀 [V23.1] 현재 매매 사이클에서 실제로 사용 중인 시드 반환"""
        v = self._load_json("ACTIVE_SEED_CFG")
        # 액티브 시드가 없으면 일단 일반 시드(Reserved)를 가져옴
        return float(v.get(t, self.get_seed(t)))

    def set_active_seed(self, t, v):
        """🚀 [V23.1] 현재 매매 사이클의 시드 저장 (보통 qty=0일 때 호출)"""
        d = self._load_json("ACTIVE_SEED_CFG")
        d[t] = v
        self._save_json("ACTIVE_SEED_CFG", d)

    def get_compound_rate(self, t):
        return float(self._load_json("COMPOUND_CFG", self.DEFAULT_COMPOUND).get(t, 70.0))

    def set_compound_rate(self, t, v):
        d = self._load_json("COMPOUND_CFG", self.DEFAULT_COMPOUND)
        d[t] = v
        self._save_json("COMPOUND_CFG", d)

    def get_version(self, t):
        return self._load_json("VERSION_CFG", self.DEFAULT_VERSION).get(t, "V14")

    def set_version(self, t, v):
        d = self._load_json("VERSION_CFG", self.DEFAULT_VERSION)
        d[t] = v
        self._save_json("VERSION_CFG", d)
        
    def get_portfolio_ratio(self, t):
        # 🌟 [V22 패치] 각 개별 종목이 전체 계좌 총액 중에서 가져가야 할 목표 할당 퍼센티지 (0.0 ~ 1.0)
        return float(self._load_json("PORTFOLIO_RATIO", self.DEFAULT_PORTFOLIO_RATIO).get(t, self.DEFAULT_PORTFOLIO_RATIO.get(t, 0.45)))

    def set_portfolio_ratio(self, t, v):
        d = self._load_json("PORTFOLIO_RATIO", self.DEFAULT_PORTFOLIO_RATIO)
        d[t] = float(v)
        self._save_json("PORTFOLIO_RATIO", d)
        
    def rebalance_seed_on_graduation(self, ticker, total_asset):
        """
        🌟 [V22 패치] 비동기 독립 리밸런싱 엔진
        해당 종목이 "0주"로 익절(졸업) 했을 때, 커져버린 'Total Asset(예비현금+전체주식총 가치)'에 
        자신의 고유 배정 비율을 곱하여 새로운 등치(시드머니)를 영구 갱신시킴. (계단식 복리 메커니즘)
        """
        ratio = self.get_portfolio_ratio(ticker)
        new_seed = math.floor(total_asset * ratio)
        
        # 안전 장치: 시드가 너무 비정상적으로 작거나 0이 되는 것을 방어
        if new_seed < 100:
            print(f"⚠️ [Config] 너무 작은 리벨런싱 시드 감지 (${new_seed}). 리밸런싱 생략.")
            return self.get_seed(ticker)
            
        self.set_seed(ticker, new_seed)
        print(f"🔄 [Config] {ticker} 비동기 졸업 리밸런싱 완료! {ratio*100}% 비율 적용 → 새 시드: ${new_seed:,.0f}")
        return new_seed

    def clone_config_from_mode(self, ticker, source_is_real):
        """🌟 [V23.3] 전략 이식 엔진: 소스 모드의 설정을 현재 인스턴스 모드로 복제"""
        from config import ConfigManager as CM
        source_manager = CM(is_real=source_is_real)
        
        try:
            # 1. 시드 복제 (예약된 시드)
            self.set_seed(ticker, source_manager.get_seed(ticker))
            # 2. 분할 횟수 복제
            self.set_split_count(ticker, source_manager.get_split_count(ticker))
            # 3. 목표 수익률 복제
            self.set_target_profit(ticker, source_manager.get_target_profit(ticker))
            # 4. 복리율 복제
            self.set_compound_rate(ticker, source_manager.get_compound_rate(ticker))
            # 5. 버전 복제
            self.set_version(ticker, source_manager.get_version(ticker))
            # 6. 포트폴리오 비중 복제
            self.set_portfolio_ratio(ticker, source_manager.get_portfolio_ratio(ticker))
            
            print(f"🧬 [Config-Implant] {ticker} 전략 이식 완료 ({'REAL' if source_is_real else 'MOCK'} ➡️ {'REAL' if self.is_real else 'MOCK'})")
            return True
        except Exception as e:
            print(f"❌ [Config-Implant] {ticker} 이식 실패: {e}")
            return False

    def get_split_count(self, t):
        return self._load_json("SPLIT", self.DEFAULT_SPLIT).get(t, 40.0)

    def set_split_count(self, t, v):
        d = self._load_json("SPLIT", self.DEFAULT_SPLIT)
        d[t] = float(v)
        self._save_json("SPLIT", d)

    def get_target_profit(self, t):
        return self._load_json("PROFIT_CFG", self.DEFAULT_TARGET).get(t, 10.0)
        
    def set_target_profit(self, t, v):
        d = self._load_json("PROFIT_CFG", self.DEFAULT_TARGET)
        d[t] = float(v)
        self._save_json("PROFIT_CFG", d)
        
    def get_sniper_multiplier(self, t):
        default_val = self.DEFAULT_SNIPER_MULTIPLIER.get(t, 1.0)
        return float(self._load_json("SNIPER_MULTIPLIER_CFG", self.DEFAULT_SNIPER_MULTIPLIER).get(t, default_val))
        
    def set_sniper_multiplier(self, t, v):
        d = self._load_json("SNIPER_MULTIPLIER_CFG", self.DEFAULT_SNIPER_MULTIPLIER)
        d[t] = float(v)
        self._save_json("SNIPER_MULTIPLIER_CFG", d)

    def get_turbo_mode(self):
        val = self._load_file("TURBO")
        # 🚀 [V23.1] 부스터 모드는 기본적으로 "ON"으로 작동 (저장된 값이 없으면 True 반환)
        if val is None: return True
        return val == 'True'

    def set_turbo_mode(self, v):
        self._save_file("TURBO", str(v))

    def get_secret_mode(self):
        return self._load_file("SECRET_MODE") == 'True'

    def set_secret_mode(self, v):
        self._save_file("SECRET_MODE", str(v))

    def get_active_tickers(self):
        return self._load_json("TICKER", ["SOXL", "TQQQ"])

    def set_active_tickers(self, v):
        self._save_json("TICKER", v)

    def get_chat_id(self): 
        v = self._load_file("CHAT_ID")
        return int(v) if v else None

    def set_chat_id(self, v):
        self._save_file("CHAT_ID", v)

    def _load_mode_file(self):
        """🌟 [V22.2] 루트 data/ 폴더에서 현재 매매 모드를 읽어옵니다."""
        if os.path.exists(self.MODE_FILE):
            try:
                with open(self.MODE_FILE, 'r', encoding='utf-8') as f:
                    return f.read().strip() == 'True'
            except Exception:
                pass
        return False

    def get_is_real_trading(self):
        """전역 매매 모드 반환 (UI 표시용)"""
        return self._load_mode_file()

    def set_is_real_trading(self, v):
        """전역 매매 모드 설정 및 파일 저장 (UI 표시용)"""
        try:
            if not os.path.exists("data"): os.makedirs("data")
            with open(self.MODE_FILE, 'w', encoding='utf-8') as f:
                f.write(str(bool(v)))
        except Exception as e:
            print(f"❌ [Config] 모드 파일 저장 에러: {e}")

    def get_engine_status(self):
        """🚀 [V22.3] 해당 인스턴스의 엔진 가동 상태 반환 (기본값 ON)"""
        v = self._load_file("ENGINE_STATUS", "ON")
        return v == "ON"

    def set_engine_status(self, is_on: bool):
        """🚀 [V23.1] 엔진 작동 상태 저장"""
        self._save_file("ENGINE_STATUS", "ON" if is_on else "OFF")

    def get_market_phase(self):
        """🕒 [V23.1] 현재 미국 시장 개장 상태 및 페이즈 반환"""
        est = pytz.timezone('US/Eastern')
        now = datetime.datetime.now(est)
        
        # 주말 확인 (토=5, 일=6)
        if now.weekday() >= 5:
            return "CLOSED (REST)"
            
        # 시간 계산 (HHMM)
        current_time = int(now.strftime("%H%M"))
        
        # 04:00 ~ 09:30: Pre-market (미국 동부 기준)
        if 400 <= current_time < 930:
            return "PRE-MARKET"
        # 09:30 ~ 16:00: Regular session
        elif 930 <= current_time < 1600:
            return "REGULAR"
        # 16:00 ~ 20:00: Post-market
        elif 1600 <= current_time < 2000:
            return "POST-MARKET"
        else:
            return "CLOSED"

    # 🔔 [V23.1] 알림 피드 전용 로깅 시스템 (시스템 로그와 분리)
    def add_notification(self, level, message):
        """🚀 [V23.1] 대시보드 알림창 전용 고가시성 알림 메시지 기록"""
        import datetime
        import json
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 레벨 아이콘 설정
        icon = "📡"
        if level.upper() == "SUCCESS": icon = "✅"
        elif level.upper() == "ERROR": icon = "❌"
        elif level.upper() == "WARNING": icon = "⚠️"
        elif level.upper() == "INFO": icon = "📡"
        elif level.upper() == "STATUS": icon = "🔔"
        
        entry = {
            "time": timestamp,
            "level": level.upper(),
            "icon": icon,
            "message": message
        }
        
        # 🚀 [V23.1] 모드별 로그 폴더 사용
        log_dir = os.path.join("logs", self._get_base_dir().split('/')[-1] if self._get_base_dir() else "mock")
        if not os.path.exists(log_dir): os.makedirs(log_dir, exist_ok=True)
        
        log_path = os.path.join(log_dir, "notifications.json")
        
        try:
            # 파일 읽기 및 추가
            data = []
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                    except:
                        data = []
            
            data.append(entry)
            
            # 최근 100개만 유지
            if len(data) > 100:
                data = data[-100:]
            
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"❌ [Notification] 저장 에러: {e}")
    # 🕒 [V23.1] 모의투자 LOC 에뮬레이션 전용 스테이징 시스템
    def stage_mock_loc_order(self, ticker, order):
        """🚀 [V23.1] 모의투자에서 지원하지 않는 LOC 주문을 장 마감 전 실행용으로 예약"""
        path = self._get_file_path("MOCK_LOC_STAGING")
        staged = self._load_json_from_path(path, [])
        
        # 중복 제거 (티커와 사이드 기준)
        staged = [o for o in staged if not (o['ticker'] == ticker and o['side'] == order['side'])]
        
        order['ticker'] = ticker
        staged.append(order)
        self._save_json_to_path(path, staged)
        logging.info(f"🕒 [MOCK-LOC] {ticker} {order['side']} 주문이 장 마감 전 실행을 위해 예약되었습니다.")

    def get_staged_mock_loc_orders(self):
        path = self._get_file_path("MOCK_LOC_STAGING")
        return self._load_json_from_path(path, [])

    def clear_staged_mock_loc_orders(self):
        path = self._get_file_path("MOCK_LOC_STAGING")
        self._save_json_to_path(path, [])
        logging.info("🧹 [MOCK-LOC] 모든 예약 주문이 초기화되었습니다.")

    def _get_file_path(self, key):
        """[V23.1] 파일 키에 따른 모드별 절대 경로 반환"""
        base = self._get_base_dir()
        
        # 🧪 [V23.1] FILES 맵에 정의된 키는 무조건 모드별 폴더 강제 사용
        if key in self.FILES:
            return os.path.join(base, self.FILES[key])
            
        # 레거시 또는 확장용 하드코딩 맵 (계속 유지)
        extended_files = {
            "MOCK_LOC_STAGING": os.path.join(base, "mock_loc_staged.json"),
        }
        
        if key in extended_files:
            return extended_files[key]
            
        # 그 외는 루트 data/ 폴더 (공용 설정 등)
        return os.path.join("data", key)

    def _load_json_from_path(self, path, default):
        if not path or not os.path.exists(path): return default
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return default

    def _save_json_to_path(self, path, data):
        if not path: return
        dir_name = os.path.dirname(path)
        if not os.path.exists(dir_name): os.makedirs(dir_name, exist_ok=True)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except: pass
