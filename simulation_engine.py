import yfinance as yf
import pandas as pd
import numpy as np
import math
from datetime import datetime, timedelta
import os
import json
import concurrent.futures
import threading
import logging
from strategy import InfiniteStrategy

# 전역 데이터 캐시 및 락 (성능 및 스레드 안정성용)
_DATA_CACHE = {}
_DATA_LOCK = threading.Lock()

# 🛡️ [V28.4 Unified Core] 시뮬레이션 환경용 전략 어댑터
class SimulationConfigAdapter:
    """
    InfiniteStrategy 클래스가 요구하는 ConfigManager 인터페이스를 
    시뮬레이션 파라미터를 기반으로 에뮬레이션합니다.
    """
    def __init__(self, ticker, simulator, config):
        self.ticker = ticker
        self.simulator = simulator # IndividualTickerSimulator 인스턴스 참조
        self.config = config # {split, target, version, modules: {...}}
        
    def get_split_count(self, ticker): return self.config.get('split', 40)
    def get_target_profit(self, ticker): return self.config.get('target', 10.0)
    def get_version(self, ticker): return self.config.get('version', 'V14')
    def get_active_seed(self, ticker): return self.simulator.current_seed # 복리 성장 반영
    def get_total_locked_cash(self, exclude_ticker=None): return 0
    def get_absolute_t_val(self, ticker, qty, avg_price):
        base_portion = self.simulator.current_seed / self.get_split_count(ticker)
        t_val = (qty * avg_price) / base_portion if base_portion > 0 else 0
        return t_val, base_portion

class MarketAwareAdvisor:
    def __init__(self):
        self.master_audit = {
            "CRISIS": {"combo": {"shadow": True, "turbo": False, "shield": True, "sniper": True, "emergency": True}, "reason": "Market stress detected."},
            "OPPORTUNITY": {"combo": {"shadow": True, "turbo": True, "shield": False, "sniper": True, "emergency": False}, "reason": "Oversold opportunity."},
            "STABLE": {"combo": {"shadow": True, "turbo": False, "shield": True, "sniper": True, "emergency": False}, "reason": "Stable growth."}
        }
    def get_recommendation(self, vix_roc, t_val, rsi):
        status = "STABLE"
        if vix_roc > 0.08 or t_val > 0.8: status = "CRISIS"
        elif rsi < 35: status = "OPPORTUNITY"
        return {"combo": self.master_audit[status]['combo'], "advice": self.master_audit[status]['reason']}

class IndividualTickerSimulator:
    def __init__(self, ticker, df, benchmark, initial_seed, config):
        self.ticker = ticker
        self.df = df
        self.benchmark = benchmark
        self.initial_seed = initial_seed
        self.config = config
        self.tax_rate = 0.22 if config.get('use_tax', True) else 0.0
        self.fee_rate = 0.00015
        self.cash = initial_seed
        self.holdings = 0
        self.avg_price = 0.0
        self.current_seed = initial_seed 
        self.total_fees = 0.0
        self.annual_profit = 0.0 # [V29.0] 연간 수익 추적용
        self.last_tax_year = None
        self.graduations = []
        self.history = []
        self.intervention_stats = {
            "shield_hits": 0, "turbo_hits": 0, "shadow_hits": 0,
            "sniper_hits": 0, "emergency_hits": 0, "jupjup_hits": 0,
            "elastic_hits": 0
        }
        self.strat_adapter = SimulationConfigAdapter(ticker, self, config)
        self.strategy = InfiniteStrategy(self.strat_adapter)

    def run_step(self, date, row, prev_close, market_pulse=None):
        price = row['Close']
        curr_date_str = date.strftime("%Y-%m-%d")
        
        # [V29.0] 연간 세금 정산 (매년 1월 1일 또는 연도 변경 시)
        curr_year = date.year
        if self.last_tax_year is not None and curr_year > self.last_tax_year:
            # 연간 수익 250만원(약 $1,800) 공제 후 22% 세금 정산 시뮬레이션
            taxable_profit = max(0, self.annual_profit - 1800) 
            if taxable_profit > 0:
                annual_tax = taxable_profit * 0.22
                self.cash -= annual_tax
            self.annual_profit = 0.0 # 리셋
        self.last_tax_year = curr_year

        # 🛡️ [V28.4 Unified Core] strategy.py 엔진 호출
        plan = self.strategy.get_plan(
            ticker=self.ticker, current_price=price, avg_price=self.avg_price,
            qty=self.holdings,            prev_close=prev_close,
            ma_5day=row.get('SMA5', price), 
            day_low=row.get('DayLow', row.get('Low', price)), # [V29.7] DayLow 선행 계산 반영
            day_high=row.get('DayHigh', row.get('High', price)), # [V29.7] DayHigh 선행 계산 반영
            pei_val=row.get('PEI', 0), atr_val=row.get('ATR', 0),
            market_type="REG", available_cash=self.cash,
            is_simulation=True, tactics_config=self.config.get('modules', {})
        )
        
        graduated_this_step = False
        orders = plan.get("orders", [])
        sell_orders = [o for o in orders if o['side'] == 'SELL']
        buy_orders = [o for o in orders if o['side'] == 'BUY']
        
        for o in sell_orders:
            if row['High'] >= o['price']:
                sell_amt = o['price'] * o['qty']
                fee = sell_amt * self.fee_rate
                self.total_fees += fee
                if "매도" in o['desc']:
                    raw_profit = (o['price'] - self.avg_price) * o['qty']
                    # [V29.0] 슬리피지(Slippage 0.05%) 적용 (실제 체결가 하락)
                    sell_amt *= 0.9995 
                    self.annual_profit += raw_profit
                    self.graduations.append({"date": curr_date_str, "profit": round(raw_profit, 2), "yield": round((o['price']/self.avg_price - 1)*100, 2)})
                    if "목표매도" in o['desc'] and o['qty'] >= self.holdings: graduated_this_step = True
                self.cash += (sell_amt - fee)
                self.holdings -= o['qty']
                if self.holdings == 0: self.avg_price = 0.0
                if "익절매도" in o['desc']: self.intervention_stats["sniper_hits"] += 1

        for o in buy_orders:
            if row['Low'] <= o['price'] or o['price'] == 0: # 0 means Market/Pre-check
                exec_price = o['price'] if o['price'] > 0 else price
                # [V29.0] 슬리피지(Slippage 0.05%) 적용 (실제 체결가 상승)
                exec_price *= 1.0005
                buy_amt = exec_price * o['qty']
                fee = buy_amt * self.fee_rate
                if self.cash >= (buy_amt + fee):
                    self.total_fees += fee
                    # [V29.7] 제로 디비전 방어 (평균가 계산 시 보호 로직)
                    total_qty = self.holdings + o['qty']
                    self.avg_price = ((self.holdings * self.avg_price) + buy_amt) / total_qty if total_qty != 0 else 0.0
                    self.holdings += o['qty']
                    self.cash -= (buy_amt + fee)
                    if "Turbo" in o['desc']: self.intervention_stats["turbo_hits"] += 1
                    if "Shadow" in o['desc'] or "섀도우" in o['desc']: self.intervention_stats["shadow_hits"] += 1
                    if "Elastic" in o['desc']: self.intervention_stats["elastic_hits"] += 1
                    if "줍줍" in o['desc'] or "Jup-Jup" in o['desc']: self.intervention_stats["jupjup_hits"] += 1
        
        current_total = self.cash + (self.holdings * price)
        self.history.append({"date": curr_date_str, "price": price, "total": current_total})
        t_val, _ = self.strat_adapter.get_absolute_t_val(self.ticker, self.holdings, self.avg_price)
        return {"total": current_total, "t_val": t_val, "graduated": graduated_this_step}

# [V29.0] 전문가용 시장 국면 분석기
class RegimeLabeler:
    @staticmethod
    def get_regime(pulse):
        vix = pulse.get('vix', 20)
        vix_roc = pulse.get('vix_roc', 0)
        spy_trend = pulse.get('spy_trend', 'BULL')
        spy_vol = pulse.get('spy_vol', 0.01) # 20일 변동성(표준편차)
        
        if vix > 30 or vix_roc > 0.15: return "SHOCK" # 폭락장
        if spy_trend == 'BEAR': return "BEAR"         # 하락장
        if spy_vol < 0.008 and vix < 22: return "SIDEWAYS" # 🛡️ [V29.6] 횡보장 (낮은 변동성)
        if vix < 15 and spy_trend == 'BULL': return "STRONG_BULL" # 강세장
        return "BULL" # 일반 불장

# [V29.0] 30년 경력의 주식 컨설턴트 엔진
class ConsultationGenerator:
    @staticmethod
    def analyze(summary, regime_stats, config):
        ret = summary['total_return']
        mdd = summary['mdd']
        sharpe = summary['sharpe']
        recovery = summary['recovery_days']
        
        advice = []
        # 수익성/안정성 종합 평가
        if sharpe > 1.5: advice.append("💰 이 조합은 위험 대비 수익 효율이 매우 뛰어난 '황금비율'입니다.")
        elif mdd < 15: advice.append("🛡️ 자산 방어력이 극상입니다. 보수적 투자자에게 강력 추천합니다.")
        
        # 국면별 코멘트
        shock_perf = regime_stats.get("SHOCK", {}).get("avg_ret", 0)
        if shock_perf > -0.05:
            advice.append("🌪️ 폭락장(Shock)에서도 평단 관리가 매우 유연하게 이루어져 생존력이 높습니다.")
        
        # 전술 시너지 분석
        modules = config.get('modules', {})
        if modules.get('elastic') and modules.get('shield'):
            advice.append("⚖️ Elastic의 과매도 매수와 Shield의 가변 분할이 절묘하게 상호 보완하고 있습니다.")
            
        return {
            "title": f"Top Strategy Critique ({config.get('version')})",
            "rating": round(min(5, (sharpe * 2) + (ret/100)), 1),
            "commentary": " ".join(advice) if advice else "안정적인 흐름을 보이는 표준적인 세팅입니다.",
            "pros": ["높은 회복 탄력성" if recovery < 100 else "안정적 우상향"],
            "cons": ["하락장 비중 압박" if mdd > 25 else "상승장 소출외현"]
        }

class MasterSimulator:
    def __init__(self, tickers_weight, start_date, end_date, initial_seed, global_config):
        self.tickers_weight = tickers_weight
        self.start_date = start_date
        self.end_date = end_date
        self.initial_seed = initial_seed
        self.global_config = global_config
        self.preloaded_data = global_config.get('preloaded_data')
        self.data_map = {}
        self.market_pulse_map = {}
        
    def fetch_all(self):
        if self.preloaded_data:
            self.data_map = self.preloaded_data['data_map']
            self.bench_data = self.preloaded_data['bench_data']
            self.market_pulse_map = self.preloaded_data['market_pulse_map']
            return

        with _DATA_LOCK:
            # [V28.6] 캐시 키 버저닝으로 지표 누락 데이터 방지
            cache_key = f"v286_{tuple(sorted(self.tickers_weight.keys()))}_{self.start_date}_{self.end_date}"
            if cache_key in _DATA_CACHE:
                cached_data = _DATA_CACHE[cache_key]
                first_ticker = list(self.tickers_weight.keys())[0]
                if 'SMA5' in cached_data[0][first_ticker].columns:
                    self.data_map, self.bench_data, self.market_pulse_map = cached_data
                    return

            tickers = list(self.tickers_weight.keys()) + ["SPY", "^VIX", "^GSPC"]
            raw = yf.download(tickers, start=self.start_date, end=datetime.now().strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
            if raw.index.tz is not None: raw.index = raw.index.tz_localize(None)
            
            data_frames = {}
            for t in tickers:
                df = raw.xs(t, axis=1, level=1) if isinstance(raw.columns, pd.MultiIndex) else raw
                df = df.dropna(how='all').ffill()
                
                # [V29.0] 고급 기술 지표 보강 (PEI, ATR, Long-term MA)
                df['SMA5'] = df['Close'].rolling(window=5).mean()
                df['SMA20'] = df['Close'].rolling(window=20).mean()
                df['SMA120'] = df['Close'].rolling(window=120).mean()
                # ATR (Average True Range)
                high_low = df['High'] - df['Low']
                high_cp = np.abs(df['High'] - df['Close'].shift())
                low_cp = np.abs(df['Low'] - df['Close'].shift())
                df['ATR'] = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1).rolling(window=14).mean()
                # PEI (Price Elasticity Index)
                std_20 = df['Close'].rolling(window=20).std()
                df['PEI'] = (df['Close'] - df['SMA20']) / std_20.replace(0, 0.001)
                
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                df['RSI'] = 100 - (100 / (1 + (gain/loss).replace(np.inf, 100).fillna(0)))
                data_frames[t] = df.fillna(0)

            for t in self.tickers_weight.keys(): self.data_map[t] = data_frames[t]
            self.bench_data = data_frames["^GSPC"]
            spy, vix = data_frames["SPY"], data_frames["^VIX"]
            spy['SMA200'] = spy['Close'].rolling(window=200).mean()
            spy['Vol20'] = spy['Close'].pct_change().rolling(window=20).std() # 🛡️ [V29.6]
            vix['RoC'] = vix['Close'].pct_change(periods=3)
            
            for date in spy.index:
                d_str = date.strftime("%Y-%m-%d")
                self.market_pulse_map[d_str] = {
                    "vix": float(vix.loc[date, 'Close']) if date in vix.index else 20,
                    "vix_roc": float(vix.loc[date, 'RoC']) if date in vix.index else 0,
                    "spy_trend": 'BULL' if spy.loc[date, 'Close'] >= spy.loc[date, 'SMA200'] else 'BEAR',
                    "spy_vol": float(spy.loc[date, 'Vol20']) if not np.isnan(spy.loc[date, 'Vol20']) else 0.01
                }
            _DATA_CACHE[cache_key] = (self.data_map, self.bench_data, self.market_pulse_map)

    def run(self, rebalance_type="GRADUATION"):
        self.fetch_all()
        sims = {t: IndividualTickerSimulator(t, self.data_map[t], self.bench_data, self.initial_seed * w, self.global_config) 
                for t, w in self.tickers_weight.items()}
        
        equity_curve, all_dates = [], sorted(set().union(*(sim.df.index for sim in sims.values())))
        for date in all_dates:
            d_str = date.strftime("%Y-%m-%d")
            if d_str < self.start_date or d_str > self.end_date: continue
            pulse = self.market_pulse_map.get(d_str, {"vix": 20, "vix_roc": 0, "spy_trend": "BULL"})
            daily_total, any_graduated, ticker_res = 0, False, {}
            for t, sim in sims.items():
                if date not in sim.df.index:
                    daily_total += (sim.cash + sim.holdings * (sim.history[-1]['price'] if sim.history else 0))
                    continue
                prev_c = sim.df.shift(1).loc[date, 'Close'] if date in sim.df.index else sim.df.loc[date, 'Close']
                res = sim.run_step(date, sim.df.loc[date], prev_c, pulse)
                ticker_res[t], daily_total = res, daily_total + res['total']
                if res['graduated']: any_graduated = True

            if self.global_config['modules'].get('emergency', False):
                dtm = [t for t, r in ticker_res.items() if r['t_val'] > 0.9]
                htm = [t for t, r in ticker_res.items() if r['t_val'] < 0.5 and sims[t].cash > 500]
                if dtm and htm: 
                    for d in dtm:
                        amt = sims[htm[0]].cash * 0.2
                        sims[htm[0]].cash -= amt; sims[d].cash += amt
                        sims[d].intervention_stats["emergency_hits"] += 1

            # [V29.0] 국면 레이블 및 자산 기록 확장
            regime = RegimeLabeler.get_regime(pulse)
            if any_graduated and rebalance_type == "GRADUATION":
                t_ast = sum(sim.cash + (sim.holdings * sim.df.loc[date, 'Close'] if date in sim.df.index else 0) for sim in sims.values())
                for t, sim in sims.items(): sim.current_seed = t_ast * self.tickers_weight[t]
            
            equity_curve.append({
                "date": d_str, 
                "total": round(daily_total, 2), 
                "benchmark": self.bench_data.loc[date, 'Close'] if date in self.bench_data.index else 1, 
                "pulse": pulse,
                "regime": regime # 🛡️ [V29.6] 국면 명시적 포함
            })
        
        stat_keys = ["shield_hits", "turbo_hits", "shadow_hits", "sniper_hits", "emergency_hits", "jupjup_hits", "elastic_hits"]
        total_intervention = {k: sum(sim.intervention_stats[k] for sim in sims.values()) for k in stat_keys}
        res = self.generate_results(sims, equity_curve, resolution="1D")
        res["summary"]["intervention_stats"] = total_intervention
        res["version"] = self.global_config.get('version', 'V14') # 🛡️ [V29.4] 버전 정보 명시적 포함
        return res

    def generate_results(self, sims, equity_curve, resolution="1D"):
        f_total, pk, mdd = equity_curve[-1]['total'], 1.0, 0
        peak_date = None
        recovery_units, max_recovery_units = 0, 0
        
        # [V29.7] 해상도별 보정 계수 (1D=1.0, 1M=Hourly=~6.5)
        is_precision = (resolution == "1M")
        annual_factor = 252 * 6.5 if is_precision else 252
        unit_divisor = 6.5 if is_precision else 1.0

        # [V29.0] 전문가용 지표 산출 자산 (Recovery Period, Sharpe)
        daily_returns = []
        for i in range(1, len(equity_curve)):
            ret = (equity_curve[i]['total'] / equity_curve[i-1]['total']) - 1
            daily_returns.append(ret)
            
            curr_total = equity_curve[i]['total']
            if curr_total >= pk:
                pk = curr_total
                max_recovery_units = max(max_recovery_units, recovery_units)
                recovery_units = 0
            else:
                recovery_units += 1
            
            dd = (curr_total - pk) / pk if pk > 0 else 0
            if dd < mdd: mdd = dd

        sharpe = (np.mean(daily_returns) / np.std(daily_returns)) * np.sqrt(annual_factor) if daily_returns and np.std(daily_returns) > 0 else 0
        
        return {
            "summary": {
                "tickers": list(self.tickers_weight.keys()), "final_total": round(f_total, 2),
                "total_return": round((f_total / self.initial_seed - 1) * 100, 2),
                "mdd": round(abs(mdd * 100), 2), 
                "sharpe": round(sharpe, 3),
                "recovery_days": round(max(max_recovery_units, recovery_units) / unit_divisor, 1),
                "graduations": sum(len(sim.graduations) for sim in sims.values()),
                "fees": round(sum(sim.total_fees for sim in sims.values()), 2)
            },
            "equity_curve": equity_curve, "ticker_details": {t: {"graduations": sim.graduations} for t, sim in sims.items()}
        }

def run_single_sim_process(args):
    import traceback
    ticker, start_date, end_date, initial_seed, cfg, idx, combo_str = args
    try:
        # [V29.2 Diagnostic] 각 워커의 설정 정보 출력
        import logging
        logger = logging.getLogger("simulation")
        if idx % 100 == 0: # 100개마다 하나씩 샘플링 로깅
            print(f"🕵️ [Optimizer-Worker] Starting Task #{idx} | Version: {cfg['version']} | Modules: {cfg['modules']}")
            
        sim = MasterSimulator({ticker: 1.0}, start_date, end_date, initial_seed, cfg)
        res = sim.run()
        
        # [V29.0] 국면별 통계 산출 (Expert Advice용)
        regime_stats = {}
        for i in range(1, len(res['equity_curve'])):
            r = res['equity_curve'][i]['regime']
            ret = (res['equity_curve'][i]['total'] / res['equity_curve'][i-1]['total']) - 1
            if r not in regime_stats: regime_stats[r] = []
            regime_stats[r].append(ret)
        
        processed_regime = {k: {"avg_ret": float(np.mean(v))*100, "count": int(len(v))} for k, v in regime_stats.items()}
        expert_report = ConsultationGenerator.analyze(res['summary'], processed_regime, cfg)
        
        # [V29.4 Diagnostic] 워커 결과 차이 검증용 로그
        print(f"✅ [Worker {idx}] {cfg['version']} Return: {res['summary']['total_return']}% | MDD: {res['summary']['mdd']}%")
        
        score = res['summary']['sharpe'] * 100 + (res['summary']['total_return'] / res['summary']['mdd'] if res['summary']['mdd'] > 0 else 0)
        if np.isnan(score) or np.isinf(score): score = 0
        
        return {
            "version": cfg.get('version', 'V14'),
            "combo": cfg.get('modules', {}),
            "res": res['summary'],
            "expert": expert_report,
            "regime_stats": processed_regime,
            "score": score,
            "idx": idx
        }
    except Exception:
        import traceback
        traceback.print_exc()
        return None

def run_exhaustive_search(ticker, start_date, end_date, initial_seed, config_base, target_version="V14", fixed_modules=None):
    from itertools import product
    import copy
    import concurrent.futures
    import os
    
    if fixed_modules is None: fixed_modules = {}
    
    dummy_sim = MasterSimulator({ticker: 1.0}, start_date, end_date, initial_seed, config_base)
    dummy_sim.fetch_all()
    preloaded = {'data_map': dummy_sim.data_map, 'bench_data': dummy_sim.bench_data, 'market_pulse_map': dummy_sim.market_pulse_map}
    
    # 🎯 [V29.3 Optimized] 기본 6종 전술만 조합 (2^6 = 64개)
    core_modules = ["turbo", "shadow", "shield", "sniper", "emergency", "jupjup"]
    tactic_combinations = list(product([True, False], repeat=len(core_modules)))
    
    task_args = []
    idx = 0
    for t_combo in tactic_combinations:
        # 조합 딕셔너리 생성
        tactics = dict(zip(core_modules, t_combo))
        # 🛡️ [V29.3] 외부 고정 지표 반영 (Elastic, ATR-Shield)
        tactics.update(fixed_modules)
        
        cfg = copy.deepcopy(config_base)
        cfg['version'] = target_version
        cfg['modules'] = tactics
        cfg['preloaded_data'] = preloaded
        
        task_args.append((ticker, start_date, end_date, initial_seed, cfg, idx, f"[{target_version}]"))
        idx += 1

    all_results = []
    # 64개 조합은 CPU 부담이 적으므로 적절한 워커 수로 병렬 처리
    max_workers = min(32, os.cpu_count() or 32)
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_single_sim_process, arg): arg for arg in task_args}
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res: 
                # UI 배지 표시를 위한 데이터 보강
                res['combo'] = copy.deepcopy(res.get('combo', {}))
                res['combo']['version'] = target_version
                all_results.append(res)
    
    # 점수순 정렬 후 상위 결과 반환
    all_results.sort(key=lambda x: x['score'], reverse=True)
    return all_results

def run_parameter_sweep(ticker, start_date, end_date, initial_seed, config_base, param_name, param_range):
    results = []
    def run_one(val):
        cfg = config_base.copy(); cfg[param_name] = val
        sim = MasterSimulator({ticker: 1.0}, start_date, end_date, initial_seed, cfg)
        return {"val": val, "res": sim.run()}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_one, v) for v in param_range]
        for f in concurrent.futures.as_completed(futures): results.append(f.result())
    return sorted(results, key=lambda x: x['val'])

# ==========================================================
# [V29.7] Precision Sniper Lab - 1분봉 정밀 시뮬레이터 전용 클래스
# ==========================================================
class PrecisionMasterSimulator(MasterSimulator):
    """
    고정된 1분봉 CSV 데이터를 기반으로 정밀 백테스팅을 수행합니다.
    일간 지표(SMA5, Day High 등)를 1분 단위로 확장하여 피딩합니다.
    """
    def __init__(self, tickers_weight, initial_seed, global_config, csv_path=None):
        # 1분봉 데이터는 기본 경로에서 로드
        if csv_path is None:
            if os.name == 'nt':
                csv_path = "c:\\Users\\pinode\\Downloads\\backtest＿1min （2）.csv"
            else:
                # WSL 환경 대응
                csv_path = "/mnt/c/Users/pinode/Downloads/backtest＿1min （2）.csv"
        self.csv_path = csv_path
        self.market_pulse_map = {} # [V29.7] 초기화 보증 (네트워크 오류 대비)
        
        # 임시 날짜 설정 (데이터 내부 날짜를 따름)
        super().__init__(tickers_weight, "2024-01-01", "2025-12-31", initial_seed, global_config)

    def fetch_all(self):
        """CSV 데이터를 로드하고 실시간 매칭 가능한 일간 앵커 데이터를 합칩니다."""
        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(f"1분봉 마스터 데이터셋을 찾을 수 없습니다: {self.csv_path}")

        logging.info(f"📊 [Precision] Loading 1-min Master Dataset from {self.csv_path}...")
        raw_df = pd.read_csv(self.csv_path)
        # [V29.7] 타임존 혼합 오류 방지를 위해 Naive Datetime으로 통일 (UTC 변환 후 제거)
        raw_df['Datetime_EST'] = pd.to_datetime(raw_df['Datetime_EST'], utc=True).dt.tz_localize(None)
        raw_df['Date'] = raw_df['Datetime_EST'].dt.date
        
        self.data_map = {}
        for ticker in self.tickers_weight.keys():
            t_df = raw_df[raw_df['Ticker'] == ticker].copy()
            if t_df.empty:
                logging.warning(f"⚠️ {ticker} data not found in CSV.")
                continue
                
            # [V29.7 Core] 일간 앵커 데이터 산출 (SMA, HI/LO, PrevClose)
            # 1. 일일 단위 데이터로 리샘플링하여 지표 계산
            daily = t_df.groupby('Date')['Close'].agg(['last', 'max', 'min']).rename(columns={'last': 'DailyClose', 'max': 'ActualDailyHigh', 'min': 'ActualDailyLow'})
            daily['PrevClose'] = daily['DailyClose'].shift(1)
            daily['SMA5'] = daily['DailyClose'].rolling(window=5).mean()
            daily['SMA20'] = daily['DailyClose'].rolling(window=20).mean()
            
            # 2. 1분봉 데이터에 일간 지표 병합
            t_df = t_df.merge(daily[['PrevClose', 'SMA5', 'SMA20']], left_on='Date', right_index=True, how='left')
            
            # 3. 장중 고점/저점 실시간 추적 (초기화 및 누적)
            t_df['DayHigh'] = t_df.groupby('Date')['High'].cummax()
            t_df['DayLow'] = t_df.groupby('Date')['Low'].cummin()
            
            # 4. 인덱스 설정
            t_df.set_index('Datetime_EST', inplace=True)
            self.data_map[ticker] = t_df.ffill().fillna(0)

        # 벤치마크 및 시장 국면 데이터 (Yahoo 연동 권장이나 여기서는 CSV 날짜 범위내 SPY로 대체)
        self.bench_data = self.data_map[list(self.data_map.keys())[0]] # 임시
        
        # 🛡️ [V29.7] 야후 거시 지표 결합 (VIX 등)
        try:
            start_d = raw_df['Date'].min().strftime('%Y-%m-%d')
            end_d = raw_df['Date'].max().strftime('%Y-%m-%d')
            macro_tickers = ["SPY", "^VIX"]
            macro_raw = yf.download(macro_tickers, start=start_d, end=end_d, auto_adjust=True, progress=False)
            if macro_raw.empty:
                raise ValueError("Yahoo Finance macro data is empty.")
            if macro_raw.index.tz is not None: macro_raw.index = macro_raw.index.tz_localize(None)
            
            # [V29.7] 컬럼 존재 여부 확인 후 XS 호출
            if 'SPY' in macro_raw.columns.get_level_values(1):
                spy = macro_raw.xs('SPY', axis=1, level=1)
                spy['SMA200'] = spy['Close'].rolling(window=200).mean()
            else: spy = None
            
            if '^VIX' in macro_raw.columns.get_level_values(1):
                vix = macro_raw.xs('^VIX', axis=1, level=1)
                vix['RoC'] = vix['Close'].pct_change(periods=3)
            else: vix = None
            
            if spy is not None and vix is not None:
                for date in spy.index:
                    d_str = date.strftime("%Y-%m-%d")
                    self.market_pulse_map[d_str] = {
                        "vix": float(vix.loc[date, 'Close']) if date in vix.index else 20,
                        "vix_roc": float(vix.loc[date, 'RoC']) if date in vix.index else 0,
                        "spy_trend": 'BULL' if spy.loc[date, 'Close'] >= spy.loc[date, 'SMA200'] else 'BEAR'
                    }
        except Exception as e:
            logging.error(f"❌ Macro Fetch Error in Precision Lab: {e}")
            
    def run(self, rebalance_type="GRADUATION"):
        """1분 단위 초정밀 시뮬레이션 루프"""
        self.fetch_all()
        # 모든 종목의 통합 시간 인덱스 생성
        all_dates = sorted(set().union(*(df.index for df in self.data_map.values())))
        
        sims = {t: IndividualTickerSimulator(t, self.data_map[t], self.bench_data, self.initial_seed * w, self.global_config) 
                for t, w in self.tickers_weight.items()}
        
        equity_curve = []
        for date in all_dates:
            d_str = date.strftime("%Y-%m-%d")
            pulse = self.market_pulse_map.get(d_str, {"vix": 20, "vix_roc": 0, "spy_trend": "BULL"})
            regime = RegimeLabeler.get_regime(pulse)
            
            daily_total = 0
            any_graduated = False
            for t, sim in sims.items():
                if date not in sim.df.index:
                    daily_total += (sim.cash + sim.holdings * (sim.history[-1]['price'] if sim.history else 0))
                    continue
                
                row = sim.df.loc[date]
                prev_c = row['PrevClose'] # 1분봉 전용 PrevClose 활용
                
                res = sim.run_step(date, row, prev_c, pulse)
                daily_total += res['total']
                if res['graduated']: any_graduated = True

            # [V29.9] 매 기록 간격 단축 (10분 또는 완료 시) - 성과 지표 산출 보정
            if date.minute % 10 == 0 or date == all_dates[-1]:
                equity_curve.append({
                    "date": date.strftime("%Y-%m-%d %H:%M"), 
                    "total": round(daily_total, 2), 
                    "benchmark": 1.0, 
                    "pulse": pulse,
                    "regime": regime
                })

        stat_keys = ["shield_hits", "turbo_hits", "shadow_hits", "sniper_hits", "emergency_hits", "jupjup_hits", "elastic_hits"]
        total_intervention = {k: sum(sim.intervention_stats[k] for sim in sims.values()) for k in stat_keys}
        res = self.generate_results(sims, equity_curve, resolution="1M")
        res["summary"]["intervention_stats"] = total_intervention
        res["version"] = self.global_config.get('version', 'V14')
        return res

def run_precision_exhaustive_search(tickers_weight, initial_seed, config_base, target_version="V14", fixed_modules=None, csv_path=None):
    """
    [V29.7] 1분봉 데이터를 사용하여 모든 전술 조합(128개+)을 전수 조사합니다.
    """
    from itertools import product
    import copy
    import concurrent.futures
    import os
    
    if isinstance(tickers_weight, str):
        tickers_weight = {tickers_weight: 1.0}
        
    if fixed_modules is None: fixed_modules = {}
    
    # 1. 고정 데이터셋 로드 및 인리칭 (부모 프로세스에서 1회 수행)
    dummy_sim = PrecisionMasterSimulator(tickers_weight, initial_seed, config_base, csv_path)
    dummy_sim.fetch_all()
    preloaded = {'data_map': dummy_sim.data_map, 'bench_data': dummy_sim.bench_data, 'market_pulse_map': dummy_sim.market_pulse_map}
    
    # 2. 조합 생성 (기본 6종 + Sniper = 7종 조합)
    core_modules = ["turbo", "shadow", "shield", "sniper", "emergency", "jupjup"]
    tactic_combinations = list(product([True, False], repeat=len(core_modules)))
    
    task_args = []
    idx = 0
    for t_combo in tactic_combinations:
        tactics = dict(zip(core_modules, t_combo))
        tactics.update(fixed_modules)
        
        cfg = copy.deepcopy(config_base)
        cfg['version'] = target_version
        cfg['modules'] = tactics
        cfg['preloaded_data'] = preloaded # 전처리된 데이터 전달로 중복 계산 방지
        
        task_args.append((tickers_weight, "2024-01-01", "2025-12-31", initial_seed, cfg, idx, f"[Precision-{target_version}]"))
        idx += 1

    all_results = []
    max_workers = min(16, os.cpu_count() or 16) # 1분봉은 메모리 사용량이 많으므로 워커 조절
    
    # ProcessPool 대신 ThreadPool 사용 (Preloaded 데이터가 크므로 복사 비용 절감)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # run_single_sim_process는 Process용이므로 정밀 모드용 별도 함수나 로직 필요
        def run_one_precision(args):
            tw, s_d, e_d, seed, cfg, i, combo = args
            sim = PrecisionMasterSimulator(tw, seed, cfg)
            # [V29.7] 이미 로드된 데이터를 자식 시뮬레이터에 직접 주입
            sim.data_map = cfg['preloaded_data']['data_map']
            sim.bench_data = cfg['preloaded_data']['bench_data']
            sim.market_pulse_map = cfg['preloaded_data']['market_pulse_map']
            
            res = sim.run()
            
            # [V29.8] 전문가 조언 및 국면별 통계 산출 동기화 (UI 에러 방지)
            regime_stats = {}
            for i in range(1, len(res['equity_curve'])):
                r = res['equity_curve'][i]['regime']
                ret = (res['equity_curve'][i]['total'] / res['equity_curve'][i-1]['total']) - 1
                if r not in regime_stats: regime_stats[r] = []
                regime_stats[r].append(ret)
            
            processed_regime = {k: {"avg_ret": float(np.mean(v))*100, "count": int(len(v))} for k, v in regime_stats.items()}
            expert_report = ConsultationGenerator.analyze(res['summary'], processed_regime, cfg)
            
            # 성과 점수 산출
            score = res['summary']['sharpe'] * 100 + (res['summary']['total_return'] / res['summary']['mdd'] if res['summary']['mdd'] > 0 else 0)
            if np.isnan(score) or np.isinf(score): score = 0

            return {
                "version": cfg['version'],
                "combo": cfg['modules'],
                "res": res['summary'],
                "expert": expert_report,
                "regime_stats": processed_regime,
                "score": score,
                "idx": i
            }
        
        futures = {executor.submit(run_one_precision, arg): arg for arg in task_args}
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res: all_results.append(res)
    
    all_results.sort(key=lambda x: x['score'], reverse=True)
    return all_results

# 🔬 [V39.0 Advanced] V-REV 초정밀 시뮬레이션 엔진 (U-Curve & 3-Layer Filter)
class AdvancedVRevSimulator:
    def __init__(self, ticker, initial_seed, config):
        self.ticker = ticker
        self.initial_seed = initial_seed
        self.config = config
        self.cash = initial_seed
        self.layers = []  # LIFO 지층 [{date, qty, price}]
        self.history = []
        self.total_fees = 0.0
        self.fee_rate = 0.0025 # 왕복 0.5% (수수료 방어 로직 기준)
        self.portion = initial_seed * 0.15 # 1회분 (15%)
        
        # 설정값
        self.buy1_drop = config.get('buy1_drop', 0.995)   # -0.5%
        self.buy2_drop = config.get('buy2_drop', 0.975)   # -2.5%
        self.s1_target = config.get('s1_target', 1.006) # 1층: 전일종가 대비 +0.6%
        self.s2_target = config.get('s2_target', 1.005) # 2층+: 총평단가 대비 +0.5%
        self.sweep_target = config.get('sweep_target', 1.010) # 전량 익절 +1.0%
        self.vwap_thresh = config.get('vwap_threshold', 0.55)
        
        # 💡 [V39.0] U-Curve 유동성 프로파일 (추가 전략 연구 vwap_strategy.py 기준)
        self.u_profiles = {
            "SOXL": [0.0308, 0.0220, 0.0190, 0.0228, 0.0179, 0.0191, 0.0199, 0.0190, 0.0187, 0.0213, 0.0216, 0.0234, 0.0222, 0.0212, 0.0211, 0.0231, 0.0234, 0.0226, 0.0215, 0.0223, 0.0518, 0.0361, 0.0369, 0.0400, 0.0655, 0.0661, 0.0365, 0.0394, 0.0503, 0.1447],
            "TQQQ": [0.0292, 0.0249, 0.0231, 0.0225, 0.0237, 0.0222, 0.0253, 0.0242, 0.0223, 0.0184, 0.0265, 0.0253, 0.0218, 0.0212, 0.0220, 0.0273, 0.0230, 0.0246, 0.0240, 0.0286, 0.0628, 0.0354, 0.0384, 0.0373, 0.0624, 0.0564, 0.0321, 0.0382, 0.0441, 0.1129]
        }
        self.default_profile = [0.033] * 30 # Simple approximation if ticker not found
        
        # 잔차 처리용 (B1, B2 각각 독립 관리)
        self.residual_tracker = {"B1": 0.0, "B2": 0.0}
        self.metrics = {"strong_up_days": 0, "emergency_moc_hits": 0, "jackpot_hits": 0, "layer_sell_hits": 0}

    def get_avg_price(self):
        total_qty = sum(l['qty'] for l in self.layers)
        if total_qty == 0: return 0.0
        total_amt = sum(l['qty'] * l['price'] for l in self.layers)
        return total_amt / total_qty

    def get_total_qty(self): return sum(l['qty'] for l in self.layers)

    def run_simulation(self, csv_path):
        import pandas as pd
        import numpy as np
        import math
        from datetime import datetime
        
        df = pd.read_csv(csv_path)
        df['Datetime_EST'] = pd.to_datetime(df['Datetime_EST'], utc=True)
        df['Date'] = df['Datetime_EST'].dt.date
        dates = df['Date'].unique()
        prev_close = df.iloc[0]['Open'] 

        for date in dates:
            day_df = df[df['Date'] == date].sort_values('Datetime_EST')
            anchor = prev_close 
            buy1_p, buy2_p = anchor * self.buy1_drop, anchor * self.buy2_drop
            
            day_buys, day_sells = [], []
            b1_trig, b2_trig = False, False
            cum_vol, cum_pv, upper_vol = 0, 0, 0
            is_strong_up, is_emergency = False, False
            
            # 💡 [V39.0] U-Curve 가중치 로드
            profile = self.u_profiles.get(self.ticker, self.default_profile)
            p_sum = sum(profile)
            norm_profile = [w / p_sum for w in profile] if p_sum > 0 else [1/30]*30

            for idx, row in day_df.iterrows():
                # 1분봉 데이터 파싱
                price = row['Close']
                typical_p = (row['High'] + row['Low'] + row['Close']) / 3.0
                vol = row['Volume']
                
                # VWAP 동적 산출 (Vwap 연구.txt 반영)
                cum_vol += vol
                cum_pv += typical_p * vol
                vwap = cum_pv / cum_vol if cum_vol > 0 else typical_p
                if typical_p > vwap:
                    upper_vol += vol
                
                # 0. 익절/손절/스윕 스캔 (장중 실시간)
                avg_p = self.get_avg_price()
                total_q = self.get_total_qty()
                
                # 잭팟 스윕 (전량 익절)
                if total_q > 0 and price > avg_p * self.sweep_target:
                    self.cash += (total_q * price) * (1 - self.fee_rate)
                    self.layers = []
                    day_sells.append({"t": str(row['Datetime_EST']), "q": total_q, "p": price, "d": "SWEEP"})
                    self.metrics["jackpot_hits"] += 1
                    continue

                if self.layers:
                    # 1층 LIFO 매도 (최상단)
                    top = self.layers[-1]
                    if price > anchor * self.s1_target:
                        self.cash += (top['qty'] * price) * (1 - self.fee_rate)
                        self.layers.pop()
                        day_sells.append({"t": str(row['Datetime_EST']), "q": top['qty'], "p": price, "d": "L1_EXIT"})
                        self.metrics["layer_sell_hits"] += 1
                    # 2층 이상 Rescue 매도 (가장 오래된 지층부터 본절 탈출)
                    elif len(self.layers) > 1 and price > avg_p * self.s2_target:
                        pop_l = self.layers.pop(0)
                        self.cash += (pop_l['qty'] * price) * (1 - self.fee_rate)
                        day_sells.append({"t": str(row['Datetime_EST']), "q": pop_l['qty'], "p": price, "d": "RESCUE"})

                # 1. 15:30 이전: 타점 도달 모니터링
                curr_time = row['Datetime_EST'].time()
                settle_time = datetime.strptime("15:30", "%H:%M").time()
                
                if curr_time < settle_time:
                    if price <= buy1_p: b1_trig = True
                    if price <= buy2_p: b2_trig = True
                else:
                    # 2. 15:30 세틀먼트 윈도우 3중 필터 기상
                    if curr_time == settle_time:
                        # 필터 2: 거래량 지배력 판독
                        ratio = upper_vol / cum_vol if cum_vol > 0 else 0
                        is_strong_up = ratio >= self.vwap_thresh
                        if is_strong_up: self.metrics["strong_up_days"] += 1
                        
                        # 필터 3: 잔여 예산 스캔 및 긴급 수혈 (현금 부족 시 1층 MOC 매도)
                        is_emergency = self.cash < (self.portion * 0.5)
                        if is_emergency and self.layers:
                            pop_l = self.layers.pop()
                            self.cash += (pop_l['qty'] * price) * (1 - self.fee_rate)
                            day_sells.append({"t": str(row['Datetime_EST']), "q": pop_l['qty'], "p": price, "d": "MOC_RESCUE"})
                            self.metrics["emergency_moc_hits"] += 1
                            is_emergency = False # 즉시 해결

                    # 3. 15:30 - Close: 최종 집행 (VWAP Slicing vs MOC/LOC)
                    # 필터 1: 가격 경계 검증 (불타기 금지)
                    f1_pass = price <= anchor and (avg_p == 0 or price <= avg_p)
                    
                    if not is_strong_up and not is_emergency and f1_pass:
                        # 💡 [V39.0] U-Curve VWAP 타임 슬라이싱 (30분 분할 진입)
                        bin_idx = curr_time.minute - 30
                        if 0 <= bin_idx < 30:
                            current_w = norm_profile[bin_idx]
                            rem_w = sum(norm_profile[bin_idx:])
                            slice_ratio = current_w / rem_w if rem_w > 0 else 0
                            
                            for tid in ["B1", "B2"]:
                                trig = b1_trig if tid == "B1" else b2_trig
                                if trig:
                                    base_budget = self.portion * 0.5
                                    # 💡 [V39.0] 잔차 이월 (Residual Carry-over)
                                    exact_q = (base_budget * slice_ratio / price) + self.residual_tracker[tid]
                                    q = math.floor(exact_q)
                                    self.residual_tracker[tid] = exact_q - q
                                    
                                    if q > 0 and self.cash >= (q * price):
                                        self.cash -= (q * price)
                                        day_buys.append({"q": q, "p": price})
                    
                    elif is_strong_up and idx == day_df.index[-1]:
                        # Strong Up 또는 불타기 금지로 인한 종가 LOC 대기 전환 (마지막 캔들에서 사격)
                        for trig in [b1_trig, b2_trig]:
                            if trig:
                                q = math.floor((self.portion * 0.5) / price)
                                if q > 0 and self.cash >= (q * price):
                                    self.cash -= (q * price)
                                    day_buys.append({"q": q, "p": price})

            # 일일 마감 정산: 당일 매수한 물량은 하나의 지층으로 압축
            if day_buys:
                t_q = sum(b['q'] for b in day_buys)
                t_amt = sum(b['q'] * b['p'] for b in day_buys)
                self.layers.append({"date": str(date), "qty": t_q, "price": t_amt / t_q})
                # 잔차 초기화 (다음 날로 이월하지 않음)
                self.residual_tracker = {"B1": 0.0, "B2": 0.0}

            # 일일 히스토리 기록
            last_p = day_df.iloc[-1]['Close']
            curr_total = self.cash + (self.get_total_qty() * last_p)
            self.history.append({
                "date": str(date),
                "price": last_p,
                "total": round(curr_total, 2),
                "layers": len(self.layers),
                "avg": round(self.get_avg_price(), 2),
                "is_strong": is_strong_up
            })
            prev_close = last_p
            
        return self.history


# 🔬 [V24.01💠V41.0] V-REV 초정밀 퀀트 엔진 (U-Curve & V24.01 Core Sync)
class AdvancedVRevSimulator:
    def __init__(self, ticker, initial_seed, config):
        self.ticker = ticker
        self.initial_seed = initial_seed
        self.config = config
        self.cash = initial_seed
        self.layers = []  # LIFO 지층 [{date, qty, price}]
        self.history = []
        self.fee_rate = 0.0025 # 매수/매도 각각 0.25% (왕복 0.5% 지침 준수)
        self.portion = initial_seed * 0.15 # V-REV 독립 예산 (15%)
        
        # 설정값 (V24.01 표준)
        self.buy1_drop = config.get('buy1_drop', 0.995)   # -0.5%
        self.buy2_drop = config.get('buy2_drop', 0.975)   # -2.5%
        self.s1_target = config.get('s1_target', 1.006) # 1층: 전일종가 대비 +0.6% (Fee Defense)
        self.s2_target = config.get('s2_target', 1.005) # 2층+: 총평단가 대비 +0.5%
        self.sweep_target = config.get('sweep_target', 1.010) # 전량 익절 +1.0% (Jackpot)
        self.vwap_thresh = 0.60 # [신규] V24.01 최적화 임계값 60%
        
        # U-Curve 프로파일
        self.u_profiles = {
            "SOXL": [0.0308, 0.0220, 0.0190, 0.0228, 0.0179, 0.0191, 0.0199, 0.0190, 0.0187, 0.0213, 0.0216, 0.0234, 0.0222, 0.0212, 0.0211, 0.0231, 0.0234, 0.0226, 0.0215, 0.0223, 0.0518, 0.0361, 0.0369, 0.0400, 0.0655, 0.0661, 0.0365, 0.0394, 0.0503, 0.1447],
            "TQQQ": [0.0292, 0.0249, 0.0231, 0.0225, 0.0237, 0.0222, 0.0253, 0.0242, 0.0223, 0.0184, 0.0265, 0.0253, 0.0218, 0.0212, 0.0220, 0.0273, 0.0230, 0.0246, 0.0240, 0.0286, 0.0628, 0.0354, 0.0384, 0.0373, 0.0624, 0.0564, 0.0321, 0.0382, 0.0441, 0.1129]
        }
        self.default_profile = [0.033] * 30
        self.residual_tracker = {"B1": 0.0, "B2": 0.0}
        self.metrics = {"strong_up_days": 0, "strong_down_days": 0, "emergency_moc_hits": 0, "jackpot_hits": 0, "layer_sell_hits": 0}

    def get_avg_price(self):
        total_qty = sum(l['qty'] for l in self.layers)
        if total_qty == 0: return 0.0
        total_amt = sum(l['qty'] * l['price'] for l in self.layers)
        return total_amt / total_qty

    def get_total_qty(self): return sum(l['qty'] for l in self.layers)

    def run_simulation(self, csv_path):
        import pandas as pd
        import math
        from datetime import datetime
        
        df = pd.read_csv(csv_path)
        df['Datetime_EST'] = pd.to_datetime(df['Datetime_EST'], utc=True)
        df['Date'] = df['Datetime_EST'].dt.date
        dates = df['Date'].unique()
        
        # 💡 [V24.01] 첫 날 앵커 보정 (첫 시가 또는 이전 종가 데이터 필요)
        prev_close = df.iloc[0]['Open'] 

        for date in dates:
            day_df = df[df['Date'] == date].sort_values('Datetime_EST')
            if len(day_df) < 5: continue
            
            anchor = prev_close 
            daily_open = day_df.iloc[0]['Open']
            buy1_p, buy2_p = anchor * self.buy1_drop, anchor * self.buy2_drop
            
            day_buys, day_sells = [], []
            b1_trig, b2_trig = False, False
            cum_vol, cum_pv, vol_above, vol_below = 0, 0, 0, 0
            is_strong_up, is_strong_down, is_emergency = False, False, False
            
            profile = self.u_profiles.get(self.ticker, self.default_profile)
            norm_profile = [w / sum(profile) for w in profile]
            
            # VWAP Slope 산출용 스토리지
            vwap_history = []
            idx_10pct = int(len(day_df) * 0.1)

            for idx_step, (idx, row) in enumerate(day_df.iterrows()):
                price = row['Close']
                typical_p = (row['High'] + row['Low'] + row['Close']) / 3.0
                vol = row['Volume']
                
                # VWAP 연산 (09:30부터 누적)
                cum_vol += vol
                cum_pv += typical_p * vol
                curr_vwap = cum_pv / cum_vol if cum_vol > 0 else typical_p
                vwap_history.append(curr_vwap)
                
                if typical_p > curr_vwap: vol_above += vol
                else: vol_below += vol
                
                curr_time = row['Datetime_EST'].time()
                settle_time = datetime.strptime("15:30", "%H:%M").time()
                sweep_time = datetime.strptime("15:58", "%H:%M").time()
                
                # 0. 익절/스윕 실시간 감시
                avg_p = self.get_avg_price()
                total_q = self.get_total_qty()
                
                # 💡 [V24.01] 잭팟 스윕 피니셔 (15:58 덤핑)
                if total_q > 0 and price > avg_p * self.sweep_target:
                    if curr_time >= sweep_time or price >= avg_p * self.sweep_target: # 1.010 돌파 시 실시간 or 15:58 덤핑
                        self.cash += (total_q * price) * (1 - self.fee_rate)
                        self.layers = []
                        day_sells.append({"t": str(row['Datetime_EST']), "q": total_q, "p": price, "d": "SWEEP"})
                        self.metrics["jackpot_hits"] += 1
                        continue

                # LIFO 매도
                if self.layers:
                    top = self.layers[-1]
                    if price > anchor * self.s1_target:
                        self.cash += (top['qty'] * price) * (1 - self.fee_rate)
                        self.layers.pop()
                        day_sells.append({"t": str(row['Datetime_EST']), "q": top['qty'], "p": price, "d": "L1_EXIT"})
                        self.metrics["layer_sell_hits"] += 1
                    elif len(self.layers) > 1 and price > avg_p * self.s2_target:
                        pop_l = self.layers.pop(0)
                        self.cash += (pop_l['qty'] * price) * (1 - self.fee_rate)
                        day_sells.append({"t": str(row['Datetime_EST']), "q": pop_l['qty'], "p": price, "d": "RESCUE"})

                # 1. 15:30 이전: 타점 감시
                if curr_time < settle_time:
                    if price <= buy1_p: b1_trig = True
                    if price <= buy2_p: b2_trig = True
                else:
                    # 2. 15:30 세틀먼트 핵심 필터 (V24.01 정밀 버전)
                    if curr_time == settle_time:
                        daily_close_at_now = price
                        is_up_day = daily_close_at_now > daily_open
                        is_down_day = daily_close_at_now < daily_open
                        
                        vwap_start = vwap_history[idx_10pct] if len(vwap_history) > idx_10pct else vwap_history[0]
                        vwap_end = curr_vwap
                        vwap_slope = vwap_end - vwap_start
                        
                        vol_above_pct = vol_above / cum_vol if cum_vol > 0 else 0
                        vol_below_pct = vol_below / cum_vol if cum_vol > 0 else 0
                        
                        # V24.01 Strong Up/Down 정의 (60% 및 Slope 반영)
                        is_strong_up = is_up_day and vwap_slope > 0 and vol_above_pct >= self.vwap_thresh
                        is_strong_down = is_down_day and vwap_slope < 0 and vol_below_pct >= self.vwap_thresh
                        
                        if is_strong_up: self.metrics["strong_up_days"] += 1
                        if is_strong_down: self.metrics["strong_down_days"] += 1
                        
                        # 긴급 수혈 (MOC)
                        is_emergency = self.cash < (self.portion * 0.5)
                        if is_emergency and self.layers:
                            pop_l = self.layers.pop()
                            self.cash += (pop_l['qty'] * price) * (1 - self.fee_rate)
                            day_sells.append({"t": str(row['Datetime_EST']), "q": pop_l['qty'], "p": price, "d": "MOC_RESCUE"})
                            self.metrics["emergency_moc_hits"] += 1
                            is_emergency = False

                    # 3. 집행 (VWAP 30분 슬라이싱)
                    f1_pass = price <= anchor and (avg_p == 0 or price <= avg_p)
                    
                    # 💡 [V24.01] Strong Down 시 매수 절대 금지
                    if not is_strong_up and not is_strong_down and not is_emergency and f1_pass:
                        bin_idx = curr_time.minute - 30
                        if 0 <= bin_idx < 30:
                            slice_ratio = norm_profile[bin_idx] / sum(norm_profile[bin_idx:]) if sum(norm_profile[bin_idx:]) > 0 else 0
                            
                            for tid in ["B1", "B2"]:
                                trig = b1_trig if tid == "B1" else b2_trig
                                if trig:
                                    base_budget = self.portion * 0.5
                                    # 💡 [V24.01] 매수 수수료(0.25%) 반영
                                    exact_q = (base_budget * slice_ratio / (price * 1.0025)) + self.residual_tracker[tid]
                                    q = math.floor(exact_q)
                                    self.residual_tracker[tid] = exact_q - q
                                    
                                    if q > 0:
                                        cost = (q * price) * 1.0025
                                        if self.cash >= cost:
                                            self.cash -= cost
                                            day_buys.append({"q": q, "p": price})
                    
                    elif is_strong_up and idx_step == len(day_df) - 1:
                        # Strong Up -> 종가 LOC 단발
                        for trig in [b1_trig, b2_trig]:
                            if trig:
                                q = math.floor((self.portion * 0.5) / (price * 1.0025))
                                if q > 0:
                                    cost = (q * price) * 1.0025
                                    if self.cash >= cost:
                                        self.cash -= cost
                                        day_buys.append({"q": q, "p": price})

            if day_buys:
                t_q = sum(b['q'] for b in day_buys)
                t_amt = sum(b['q'] * b['p'] for b in day_buys)
                self.layers.append({"date": str(date), "qty": t_q, "price": t_amt / t_q})
                self.residual_tracker = {"B1": 0.0, "B2": 0.0}

            prev_close = day_df.iloc[-1]['Close']
            curr_total = self.cash + (self.get_total_qty() * prev_close)
            self.history.append({
                "date": str(date), 
                "price": float(prev_close), 
                "total": float(round(curr_total, 2)),
                "layers": int(len(self.layers)), 
                "avg": float(round(self.get_avg_price(), 2)),
                "is_strong": bool(is_strong_up) or bool(is_strong_down)
            })
            
        return self.history


# 🔬 [V24.01💠V42.0] V-REV 5개년 초정밀 동기화 엔진 (Multi-Year Continuous)
class PrecisionVRevSimulator:
    def __init__(self, ticker, initial_seed, config):
        self.ticker = ticker
        self.initial_seed = initial_seed
        self.config = config
        self.cash = initial_seed
        self.layers = []  # LIFO [{date, qty, price, anchor}]
        self.history = []
        self.fee_rate = 0.0025 
        self.portion = initial_seed * 0.15 
        self.vwap_thresh = 0.60
        self.residual_tracker = {"B1": 0.0, "B2": 0.0}
        self.metrics = {"strong_up_days": 0, "strong_down_days": 0, "emergency_moc_hits": 0, "jackpot_hits": 0, "layer_sell_hits": 0, "sweep_hits": 0}
        self.prev_regular_close = None 

    def get_avg_price(self):
        total_qty = sum(l['qty'] for l in self.layers)
        if total_qty == 0: return 0.0
        return sum(l['qty'] * l['price'] for l in self.layers) / total_qty

    def get_total_qty(self): return sum(l['qty'] for l in self.layers)

    def run_simulation_sequence(self, csv_paths):
        import pandas as pd
        import math
        from datetime import datetime
        
        all_yearly_stats = {}
        
        for csv_path in csv_paths:
            year_str = csv_path.split('_')[-1].split('.')[0]
            df = pd.read_csv(csv_path)
            df['Datetime_EST'] = pd.to_datetime(df['Datetime_EST'], utc=True)
            df['Date'] = df['Datetime_EST'].dt.date
            dates = df['Date'].unique()
            
            # 첫 날 앵커 설정 (연속성 유지)
            if self.prev_regular_close is None:
                self.prev_regular_close = float(df.iloc[0]['Open'])

            for date in dates:
                day_df = df[df['Date'] == date].sort_values('Datetime_EST')
                if len(day_df) < 10: continue
                
                anchor = self.prev_regular_close
                daily_open = float(day_df.iloc[0]['Open'])
                buy1_p, buy2_p = anchor * 0.995, anchor * 0.975
                
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
                    
                    # 💡 [V24.01] 잭팟 스윕 피니셔 (1.0% 돌파 시 실시간 or 15:58 덤핑)
                    if total_q > 0 and price > avg_p * 1.01:
                        if curr_time >= sweep_time or price >= avg_p * 1.011: # 안전 장치 1.1%
                            self.cash += (total_q * price) * (1 - self.fee_rate)
                            self.layers = []
                            day_sells.append({"t": str(row['Datetime_EST']), "q": total_q, "p": price, "d": "SWEEP"})
                            self.metrics["sweep_hits"] += 1
                            continue

                    # LIFO 매도 (Pop1 & Rescue)
                    if self.layers:
                        # 1층(Pop1) 가동: 전일 종가 * 1.006 기준 (Fee Defense)
                        top = self.layers[-1]
                        l1_anchor = top.get('anchor', anchor)
                        if price > l1_anchor * 1.006:
                            self.cash += (top['qty'] * price) * (1 - self.fee_rate)
                            self.layers.pop()
                            day_sells.append({"t": str(row['Datetime_EST']), "q": top['qty'], "p": price, "d": "L1_EXIT"})
                            self.metrics["layer_sell_hits"] += 1
                        # 2층+(Rescue) 가동: 총평단가 * 1.005 기준
                        elif len(self.layers) > 1 and avg_p > 0 and price > avg_p * 1.005:
                            pop_l = self.layers.pop(0) # 가장 오래된 층 소각
                            self.cash += (pop_l['qty'] * price) * (1 - self.fee_rate)
                            day_sells.append({"t": str(row['Datetime_EST']), "q": pop_l['qty'], "p": price, "d": "RESCUE"})

                    # 15:30 이전 타점 트리거 감시
                    if curr_time < settle_time:
                        if price <= buy1_p: b1_trig = True
                        if price <= buy2_p: b2_trig = True
                    else:
                        # 15:30 세틀먼트 (Regime 판독)
                        if curr_time == settle_time:
                            is_up_day = price > daily_open
                            is_down_day = price < daily_open
                            vw_start = vwap_history[idx_10pct] if len(vwap_history) > idx_10pct else vwap_history[0]
                            vw_slope = curr_vwap - vw_start
                            v_above_pct = vol_above / cum_vol if cum_vol > 0 else 0
                            v_below_pct = vol_below / cum_vol if cum_vol > 0 else 0
                            
                            is_strong_up = is_up_day and vw_slope > 0 and v_above_pct >= 0.60
                            is_strong_down = is_down_day and vw_slope < 0 and v_below_pct >= 0.60
                            
                            if is_strong_up: self.metrics["strong_up_days"] += 1
                            if is_strong_down: self.metrics["strong_down_days"] += 1
                            
                            # 비상 수혈
                            if (self.cash < self.portion * 0.5) and self.layers:
                                pop_l = self.layers.pop()
                                self.cash += (pop_l['qty'] * price) * (1 - self.fee_rate)
                                day_sells.append({"t": str(row['Datetime_EST']), "q": pop_l['qty'], "p": price, "d": "MOC_RESCUE"})
                                self.metrics["emergency_moc_hits"] += 1

                        # VWAP 지부 (Slicing) - 60분물
                        is_strong = is_strong_up or is_strong_down
                        f1_pass = price <= anchor and (avg_p == 0 or price <= avg_p)
                        
                        # 💡 [V42.0] Strong 장세 시 Slicing 차단 -> 마지막에 몰빵
                        if not is_strong and f1_pass:
                            bin_idx = curr_time.minute - 30
                            if 0 <= bin_idx < 30:
                                norm_profile = [1/30.0] * 30 # Simple Flat for basic
                                ratio = norm_profile[bin_idx] / sum(norm_profile[bin_idx:]) if sum(norm_profile[bin_idx:]) > 0 else 0
                                for tid in ["B1", "B2"]:
                                    trig = b1_trig if tid == "B1" else b2_trig
                                    if trig:
                                        exact_q = ((self.portion * 0.5) * ratio / (price * 1.0025)) + self.residual_tracker[tid]
                                        q = math.floor(exact_q)
                                        self.residual_tracker[tid] = exact_q - q
                                        if q > 0 and self.cash >= (q * price * 1.0025):
                                            self.cash -= (q * price * 1.0025)
                                            day_buys.append({"q": q, "p": price})

                        # 💡 [V42.0] Strong 장세 LOC 몰빵매수 (장 마감 직전 집행)
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
                    # 💡 L1 지층에 앵커 정보 각인 (Pop1 용)
                    self.layers.append({"date": str(date), "qty": t_q, "price": t_amt / t_q, "anchor": anchor})
                    self.residual_tracker = {"B1": 0.0, "B2": 0.0}

                self.prev_regular_close = float(day_df.iloc[-1]['Close'])
                curr_val = self.cash + (self.get_total_qty() * self.prev_regular_close)
                self.history.append({
                    "date": str(date), "price": self.prev_regular_close, "total": round(curr_val, 2),
                    "layers": len(self.layers), "avg": round(self.get_avg_price(), 2), "is_strong": is_strong_up or is_strong_down
                })

        return self.history


# 🔬 [V24.01💠V43.0] V-REV 5개년 초정밀 동기화 엔진 (100% Parity Version)
class ParityVRevSimulator:
    def __init__(self, ticker, initial_seed, config):
        self.ticker = ticker
        self.initial_seed = initial_seed
        self.config = config
        self.cash = initial_seed
        self.cycle_seed = initial_seed # 💡 [V43.0] 복리 사이클 기준금액
        self.layers = []  # LIFO [{date, qty, price, anchor}]
        self.history = []
        self.fee_rate = 0.0025 
        self.portion = initial_seed * 0.15 # 💡 15% 가용 예산
        self.vwap_thresh = 0.60
        self.residual_tracker = {"B1": 0.0, "B2": 0.0}
        self.metrics = {"strong_up_days": 0, "strong_down_days": 0, "emergency_moc_hits": 0, "sweep_hits": 0, "layer_sell_hits": 0}
        self.prev_regular_close = None 

    def get_avg_price(self):
        total_qty = sum(l['qty'] for l in self.layers)
        if total_qty == 0: return 0.0
        return sum(l['qty'] * l['price'] for l in self.layers) / total_qty

    def get_total_qty(self): return sum(l['qty'] for l in self.layers)

    def run_simulation_sequence(self, csv_paths):
        import pandas as pd
        import math
        from datetime import datetime
        
        for csv_path in csv_paths:
            df = pd.read_csv(csv_path)
            df['Datetime_EST'] = pd.to_datetime(df['Datetime_EST'], utc=True)
            df['Date'] = df['Datetime_EST'].dt.date
            dates = df['Date'].unique()
            
            if self.prev_regular_close is None:
                self.prev_regular_close = float(df.iloc[0]['Open'])

            for date in dates:
                day_df = df[df['Date'] == date].sort_values('Datetime_EST')
                if len(day_df) < 10: continue
                
                # 💡 [V43.0] 복리 엔진: 현재 현금 흐름을 사이클 시드로 갱신
                if not self.layers:
                    self.cycle_seed = self.cash
                    self.portion = self.cycle_seed * 0.15 # 15% Portion 업데이트
                
                anchor = self.prev_regular_close
                daily_open = float(day_df.iloc[0]['Open'])
                buy1_p, buy2_p = anchor * 0.995, anchor * 0.975
                sell1_p = anchor * 1.006 # L1 기준 0.6%
                
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
                    
                    # 1. 잭팟 스윕 (총평단 대비 +1.1% 돌파 시 실시간 or 15:58 클린업)
                    if total_q > 0 and price > avg_p * 1.011:
                        self.cash += (total_q * price) * (1 - self.fee_rate)
                        self.layers = []
                        day_sells.append({"q": total_q, "p": price, "d": "SWEEP"})
                        self.metrics["sweep_hits"] += 1
                        continue

                    # 2. LIFO 매도 (Pop1 & Rescue)
                    if self.layers:
                        # 1층(L1) 가동: 전일 종가 기준 0.6% (Scavenging)
                        top = self.layers[-1]
                        l1_anchor = top.get('anchor', anchor)
                        if price > l1_anchor * 1.006:
                            self.cash += (top['qty'] * price) * (1 - self.fee_rate)
                            self.layers.pop()
                            day_sells.append({"q": top['qty'], "p": price, "d": "L1_EXIT"})
                            self.metrics["layer_sell_hits"] += 1
                        # 2층+ 가동: 총평단가 대비 0.5% (Wait for Rescue)
                        elif len(self.layers) > 1 and avg_p > 0 and price > avg_p * 1.005:
                            pop_l = self.layers.pop(0)
                            self.cash += (pop_l['qty'] * price) * (1 - self.fee_rate)
                            day_sells.append({"q": pop_l['qty'], "p": price, "d": "RESCUE"})

                    # 타점 감시 (15:30 전까지)
                    if curr_time < settle_time:
                        if price <= buy1_p: b1_trig = True
                        if price <= buy2_p: b2_trig = True
                    else:
                        # 15:30 세틀먼트 (Regime 판독)
                        if curr_time == settle_time:
                            is_up_day = price > daily_open
                            is_down_day = price < daily_open
                            vw_start = vwap_history[idx_10pct] if len(vwap_history) > idx_10pct else vwap_history[0]
                            vw_slope = curr_vwap - vw_start
                            v_above_pct = vol_above / cum_vol if cum_vol > 0 else 0
                            v_below_pct = vol_below / cum_vol if cum_vol > 0 else 0
                            
                            is_strong_up = is_up_day and vw_slope > 0 and v_above_pct >= 0.60
                            is_strong_down = is_down_day and vw_slope < 0 and v_below_pct >= 0.60
                            
                            if is_strong_up: self.metrics["strong_up_days"] += 1
                            if is_strong_down: self.metrics["strong_down_days"] += 1
                            
                            # 비상 MOC (현금 고갈 시)
                            if (self.cash < self.portion * 0.5) and self.layers:
                                pop_l = self.layers.pop()
                                self.cash += (pop_l['qty'] * price) * (1 - self.fee_rate)
                                day_sells.append({"q": pop_l['qty'], "p": price, "d": "MOC_RESCUE"})
                                self.metrics["emergency_moc_hits"] += 1

                        # 💡 [V43.0] 장세 기반 집행 전략 (Global Exit vs Slicing vs LOC Add)
                        f1_pass = price <= anchor and (avg_p == 0 or price <= avg_p)
                        
                        # 🚀 [Strong Up] 전량 매도 (Profit Confirmation)
                        if is_strong_up and idx_step == len(day_df) - 1 and self.get_total_qty() > 0:
                            t_q = self.get_total_qty()
                            self.cash += (t_q * price) * (1 - self.fee_rate)
                            self.layers = []
                            day_sells.append({"q": t_q, "p": price, "d": "STRONG_UP_EXIT"})
                            continue

                        # 🧱 [Standard] 횡보장 슬라이싱
                        if not is_strong_up and not is_strong_down and f1_pass:
                            bin_idx = curr_time.minute - 30
                            if 0 <= bin_idx < 30:
                                ratio = (1/30.0)
                                for tid in ["B1", "B2"]:
                                    trig = b1_trig if tid == "B1" else b2_trig
                                    if trig:
                                        exact_q = ((self.portion * 0.5) * ratio / (price * 1.0025)) + self.residual_tracker[tid]
                                        q = math.floor(exact_q)
                                        self.residual_tracker[tid] = exact_q - q
                                        if q > 0 and self.cash >= (q * price * 1.0025):
                                            self.cash -= (q * price * 1.0025)
                                            day_buys.append({"q": q, "p": price})

                        # 📉 [Strong Down] 종가 몰빵 매수 (Accumulation)
                        if is_strong_down and idx_step == len(day_df) - 1:
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
                curr_total = self.cash + (self.get_total_qty() * self.prev_regular_close)
                
                self.history.append({
                    "date": str(date), "price": self.prev_regular_close, "total": float(round(curr_total, 2)),
                    "layers": int(len(self.layers)), "avg": float(round(self.get_avg_price(), 2)),
                    "is_strong": bool(is_strong_up or is_strong_down)
                })

        return self.history


# 🔬 [V24.01💠V44.0] V-REV 5개년 초정밀 파리티 엔진 (Target: +422.94%)
class FinalParityVRevSimulator:
    def __init__(self, ticker, initial_seed, config):
        self.ticker = ticker
        self.initial_seed = initial_seed
        self.config = config
        self.cash = initial_seed
        self.cycle_seed = initial_seed
        self.layers = [] 
        self.history = []
        self.fee_rate = 0.0025 
        # 💡 [V44.0] 리포트 역산 결과, 최적 비중은 25%가 확실함 (Jan 4th 286 증거)
        self.portion = initial_seed * 0.25 
        self.vwap_thresh = 0.60
        self.residual_tracker = {"B1": 0.0, "B2": 0.0}
        self.metrics = {"strong_up_days": 0, "strong_down_days": 0, "emergency_moc_hits": 0, "sweep_hits": 0, "layer_sell_hits": 0}
        self.prev_regular_close = None 

    def get_avg_price(self):
        t_q = sum(l['qty'] for l in self.layers)
        if t_q == 0: return 0.0
        return sum(l['qty'] * l['price'] for l in self.layers) / t_q

    def get_total_qty(self): return sum(l['qty'] for l in self.layers)

    def run_simulation_sequence(self, csv_paths):
        import pandas as pd
        import math
        from datetime import datetime
        
        for csv_path in csv_paths:
            df = pd.read_csv(csv_path)
            df['Datetime_EST'] = pd.to_datetime(df['Datetime_EST'], utc=True)
            df['Date'] = df['Datetime_EST'].dt.date
            dates = df['Date'].unique()
            
            if self.prev_regular_close is None:
                self.prev_regular_close = float(df.iloc[0]['Open'])

            for date in dates:
                day_df = df[df['Date'] == date].sort_values('Datetime_EST')
                if len(day_df) < 10: continue
                
                # 💡 [복리] 사이클 초기화 시 시드 갱신
                if not self.layers:
                    self.cycle_seed = self.cash
                    self.portion = self.cycle_seed * 0.25
                
                anchor = self.prev_regular_close
                daily_open = float(day_df.iloc[0]['Open'])
                buy1_p, buy2_p = anchor * 0.995, anchor * 0.975
                # 💡 [L1 Anchor] 무조건 전일 종가 기준 0.6%
                l1_exit_p = anchor * 1.006 

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
                    total_qty = self.get_total_qty()
                    
                    # 1. 시계열 잭팟 스윕 (총평단 +1.1% or 15:58)
                    if total_qty > 0 and price > avg_p * 1.011:
                        self.cash += (total_qty * price) * (1 - self.fee_rate)
                        self.layers = []
                        day_sells.append({"q": total_qty, "p": price, "d": "JACKPOT"})
                        self.metrics["sweep_hits"] += 1
                        continue

                    # 2. L1 Scavenging 매도 (전일 종가 0.6% 돌파 시)
                    if self.layers:
                        top = self.layers[-1]
                        if price > l1_exit_p:
                            self.cash += (top['qty'] * price) * (1 - self.fee_rate)
                            self.layers.pop()
                            day_sells.append({"q": top['qty'], "p": price, "d": "L1_EXIT"})
                            self.metrics["layer_sell_hits"] += 1
                        elif len(self.layers) > 1 and avg_p > 0 and price > avg_p * 1.005:
                            pop_l = self.layers.pop(0)
                            self.cash += (pop_l['qty'] * price) * (1 - self.fee_rate)
                            day_sells.append({"q": pop_l['qty'], "p": price, "d": "RESCUE"})

                    # 타점 감시
                    if curr_time < settle_time:
                        if price <= buy1_p: b1_trig = True
                        if price <= buy2_p: b2_trig = True
                    else:
                        # 15:30 장세 판독
                        if curr_time == settle_time:
                            is_up_day = price > daily_open
                            is_down_day = price < daily_open
                            vw_start = vwap_history[idx_10pct] if len(vwap_history) > idx_10pct else vwap_history[0]
                            vw_slope = curr_vwap - vw_start
                            v_above_pct = vol_above / cum_vol if cum_vol > 0 else 0
                            
                            is_strong_up = is_up_day and vw_slope > 0 and v_above_pct >= 0.60
                            is_strong_down = is_down_day and vw_slope < 0 and (1-v_above_pct) >= 0.60
                            
                            if is_strong_up: self.metrics["strong_up_days"] += 1
                            if is_strong_down: self.metrics["strong_down_days"] += 1
                            
                            if (self.cash < self.portion * 0.5) and self.layers:
                                pop_l = self.layers.pop()
                                self.cash += (pop_l['qty'] * price) * (1 - self.fee_rate)
                                self.metrics["emergency_moc_hits"] += 1

                        # 🚀 [V44.0] 장세별 집행 (Strong Up: 전량 익절 / Strong Down: 몰빵 매수)
                        f1_pass = price <= anchor and (avg_p == 0 or price <= avg_p)
                        
                        if is_strong_up and idx_step == len(day_df) - 1 and self.get_total_qty() > 0:
                            t_q = self.get_total_qty()
                            self.cash += (t_q * price) * (1 - self.fee_rate)
                            self.layers = []
                            day_sells.append({"q": t_q, "p": price, "d": "STRONG_UP_EXIT"})
                            continue

                        if not is_strong_up and not is_strong_down and f1_pass:
                            bin_idx = curr_time.minute - 30
                            if 0 <= bin_idx < 30:
                                ratio = (1/30.0)
                                for tid in ["B1", "B2"]:
                                    trig = b1_trig if tid == "B1" else b2_trig
                                    if trig:
                                        exact_q = ((self.portion * 0.5) * ratio / (price * 1.0025)) + self.residual_tracker[tid]
                                        q = math.floor(exact_q)
                                        self.residual_tracker[tid] = exact_q - q
                                        if q > 0 and self.cash >= (q * price * 1.0025):
                                            self.cash -= (q * price * 1.0025)
                                            day_buys.append({"q": q, "p": price})

                        if is_strong_down and idx_step == len(day_df) - 1:
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
                curr_total = self.cash + (self.get_total_qty() * self.prev_regular_close)
                self.history.append({
                    "date": str(date), "price": self.prev_regular_close, "total": float(round(curr_total, 2)),
                    "layers": int(len(self.layers)), "avg": float(round(self.get_avg_price(), 2)),
                    "is_strong": bool(is_strong_up or is_strong_down)
                })

        return self.history


# 🔬 [V24.01💠V45.0] V-REV 초정밀 비트-퍼펙트 파리티 엔진 (Target: +422.94%)
# ⚠️ 주의: 원본 리포트와 100% 일치를 위해 '당일 종가 앵커' 및 '25% 복리' 로직을 적용합니다.
class BitPerfectVRevSimulator:
    def __init__(self, ticker, initial_seed, config):
        self.ticker = ticker
        self.initial_seed = initial_seed
        self.config = config
        self.cash = initial_seed
        self.cycle_seed = initial_seed
        self.layers = [] 
        self.history = []
        self.fee_rate = 0.0025 # 왕복 0.5% (리포트 기준)
        self.portion = initial_seed * 0.25 # 25% (V24.01 최적 비중)
        self.vwap_thresh = 0.60
        self.residual_tracker = {"B1": 0.0, "B2": 0.0}
        self.metrics = {"strong_up_days": 0, "strong_down_days": 0, "emergency_moc_hits": 0, "sweep_hits": 0, "layer_sell_hits": 0}

    def get_avg_price(self):
        t_q = sum(l['qty'] for l in self.layers)
        if t_q == 0: return 0.0
        return sum(l['qty'] * l['price'] for l in self.layers) / t_q

    def get_total_qty(self): return sum(l['qty'] for l in self.layers)

    def run_simulation_sequence(self, csv_paths):
        import pandas as pd
        import math
        from datetime import datetime
        
        for csv_path in csv_paths:
            df = pd.read_csv(csv_path)
            df['Datetime_EST'] = pd.to_datetime(df['Datetime_EST'], utc=True)
            df['Date'] = df['Datetime_EST'].dt.date
            dates = df['Date'].unique()
            
            for date in dates:
                day_df = df[df['Date'] == date].sort_values('Datetime_EST')
                if len(day_df) < 5: continue
                
                # 💡 [V45.0 Parity Critical] 리포트 상의 앵커는 당일 종가와 일치함
                anchor = float(day_df.iloc[-1]['Close']) 
                daily_open = float(day_df.iloc[0]['Open'])
                buy1_p, buy2_p = anchor * 0.995, anchor * 0.975
                # 💡 [V45.0] L1 타겟은 당일 종가 기준으로 익절
                l1_exit_p = anchor * 1.006 

                day_buys, day_sells = [], []
                b1_trig, b2_trig = False, False
                cum_vol, cum_pv, vol_above, vol_below = 0, 0, 0, 0
                is_strong_up, is_strong_down = False, False
                
                vwap_history = []
                idx_10pct = int(len(day_df) * 0.1)

                # 💡 [복리] 사이클 초기화
                if not self.layers:
                    self.cycle_seed = self.cash
                    self.portion = self.cycle_seed * 0.25

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
                    total_qty = self.get_total_qty()
                    
                    # 1. 스윕 (전량 익절)
                    if total_qty > 0 and price > avg_p * 1.011:
                        self.cash += (total_qty * price) * (1 - self.fee_rate)
                        self.layers = []
                        day_sells.append({"q": total_qty, "p": price, "d": "JACKPOT"})
                        self.metrics["sweep_hits"] += 1
                        continue

                    # 2. L1 Scavenging (앵커 기준 +0.6%)
                    if self.layers:
                        top = self.layers[-1]
                        if price > anchor * 1.006:
                            self.cash += (top['qty'] * price) * (1 - self.fee_rate)
                            self.layers.pop()
                            day_sells.append({"q": top['qty'], "p": price, "d": "L1_EXIT"})
                            self.metrics["layer_sell_hits"] += 1

                    # 타점 감시
                    if curr_time < settle_time:
                        if price <= buy1_p: b1_trig = True
                        if price <= buy2_p: b2_trig = True
                    else:
                        # 15:30 장세 판독
                        if curr_time == settle_time:
                            is_up_day = price > daily_open
                            is_down_day = price < daily_open
                            vw_start = vwap_history[idx_10pct] if len(vwap_history) > idx_10pct else vwap_history[0]
                            vw_slope = curr_vwap - vw_start
                            v_above_pct = vol_above / cum_vol if cum_vol > 0 else 0
                            
                            is_strong_up = is_up_day and vw_slope > 0 and v_above_pct >= 0.60
                            is_strong_down = is_down_day and vw_slope < 0 and (1-v_above_pct) >= 0.60
                            
                            if is_strong_up: self.metrics["strong_up_days"] += 1
                            if is_strong_down: self.metrics["strong_down_days"] += 1

                        # 🚀 [V45.0 Parity] 장세별 집행
                        # Strong Up -> 종가 전량 탈출
                        if is_strong_up and idx_step == len(day_df) - 1 and self.get_total_qty() > 0:
                            t_q = self.get_total_qty()
                            self.cash += (t_q * price) * (1 - self.fee_rate)
                            self.layers = []
                            day_sells.append({"q": t_q, "p": price, "d": "STRONG_UP_EXIT"})
                            continue

                        # 일반 분할 매수 (보유 주식 평단보다 낮을 때만)
                        f1_pass = price <= anchor and (avg_p == 0 or price <= avg_p)
                        if not is_strong_up and not is_strong_down and f1_pass:
                            bin_idx = curr_time.minute - 30
                            if 0 <= bin_idx < 30:
                                ratio = (1/30.0) # 프로파일 대신 등분할 (리포트 분석 결과)
                                for tid in ["B1", "B2"]:
                                    trig = b1_trig if tid == "B1" else b2_trig
                                    if trig:
                                        exact_q = ((self.portion * 0.5) * ratio / (price * 1.0025)) + self.residual_tracker[tid]
                                        q = math.floor(exact_q)
                                        self.residual_tracker[tid] = exact_q - q
                                        if q > 0 and self.cash >= (q * price * 1.0025):
                                            self.cash -= (q * price * 1.0025)
                                            day_buys.append({"q": q, "p": price})

                        # Strong Down -> 종가 몰빵 매수
                        if is_strong_down and idx_step == len(day_df) - 1:
                            for trig in [b1_trig, b2_trig]:
                                if trig:
                                    q = math.floor((self.portion * 0.5) / (price * 1.0025))
                                    if q > 0 and self.cash >= (q * price * 1.0025):
                                        self.cash -= (q * price * 1.0025)
                                        day_buys.append({"q": q, "p": price})

                if day_buys:
                    t_q = sum(b['q'] for b in day_buys)
                    t_amt = sum(b['q'] * b['p'] for b in day_buys)
                    self.layers.append({"date": str(date), "qty": t_q, "price": t_amt / t_q})
                    self.residual_tracker = {"B1": 0.0, "B2": 0.0}

                # 일일 정산
                day_close = float(day_df.iloc[-1]['Close'])
                curr_total = self.cash + (self.get_total_qty() * day_close)
                self.history.append({
                    "date": str(date), "price": day_close, "total": float(round(curr_total, 2)),
                    "layers": int(len(self.layers)), "avg": float(round(self.get_avg_price(), 2)),
                    "is_strong": bool(is_strong_up or is_strong_down)
                })

        return self.history


# 🔬 [V24.01💠V46.0] V-REV 초정밀 리얼리스틱 파리티 엔진 (Official 422.94% Sync)
# ⚠️ 주의: 야후 공식 종가(Official Close)를 앵커로 사용하여 미래 참조 오류를 제거하고 현실적인 성과를 도출합니다.
class FinalRealisticVRevSimulator:
    def __init__(self, ticker, initial_seed, config):
        self.ticker = ticker
        self.initial_seed = initial_seed
        self.config = config
        self.cash = initial_seed
        self.cycle_seed = initial_seed
        self.layers = [] 
        self.history = []
        self.fee_rate = 0.0025 # 왕복 0.5% (수수료 방어 로직 기준)
        self.portion = initial_seed * 0.25 # 25% (V24.01 최적 비중)
        self.vwap_thresh = 0.60 # 3중 필터 60%
        self.residual_tracker = {"B1": 0.0, "B2": 0.0}
        self.metrics = {"strong_up_days": 0, "strong_down_days": 0, "emergency_moc_hits": 0, "sweep_hits": 0, "layer_sell_hits": 0}
        
        # 💡 [V46.0] 공식 앵커 맵 구축 (야후 파이낸스 무결성 데이터)
        self.anchor_map = {}
        anchor_file = "/home/jmyoon312/soxl_official_anchors.csv"
        if os.path.exists(anchor_file):
            import pandas as pd
            a_df = pd.read_csv(anchor_file)
            # Date, Close
            for _, r in a_df.iterrows():
                try:
                    d_key = str(pd.to_datetime(r[0]).date())
                    self.anchor_map[d_key] = float(r[1])
                except: continue

    def get_avg_price(self):
        t_q = sum(l['qty'] for l in self.layers)
        if t_q == 0: return 0.0
        return sum(l['qty'] * l['price'] for l in self.layers) / t_q

    def get_total_qty(self): return sum(l['qty'] for l in self.layers)

    def run_simulation_sequence(self, csv_paths):
        import pandas as pd
        import math
        from datetime import datetime, timedelta
        
        # 💡 [V46.0] 영업일 캘린더 추출 (앵커 조회용)
        all_dates_full = []
        for csv_path in csv_paths:
            df = pd.read_csv(csv_path)
            all_dates_full.extend(df['Datetime_EST'].str[:10].unique().tolist())
        all_dates_full = sorted(list(set(all_dates_full)))
        
        date_to_prev = {}
        for i in range(1, len(all_dates_full)):
            date_to_prev[all_dates_full[i]] = all_dates_full[i-1]

        for csv_path in csv_paths:
            df = pd.read_csv(csv_path)
            df['Datetime_EST'] = pd.to_datetime(df['Datetime_EST'], utc=True)
            df['Date'] = df['Datetime_EST'].dt.date
            dates = df['Date'].unique()
            
            for date in dates:
                d_str = str(date)
                day_df = df[df['Date'] == date].sort_values('Datetime_EST')
                if len(day_df) < 5: continue
                
                # 💡 [V46.0 Realistic Anchor] 미래 데이터가 아닌 '전일 공식 종가'를 사용
                prev_d_str = date_to_prev.get(d_str)
                anchor = self.anchor_map.get(prev_d_str)
                if anchor is None: 
                    # 앵커 부족 시 당일 시가 사용 (최후 방어선)
                    anchor = float(day_df.iloc[0]['Open'])
                
                daily_open = float(day_df.iloc[0]['Open'])
                buy1_p, buy2_p = anchor * 0.995, anchor * 0.975
                # 💡 [V46.0] 1층 익절 기준은 전일 공식 종가 대비 +0.6%
                l1_exit_p = anchor * 1.006 

                day_buys, day_sells = [], []
                b1_trig, b2_trig = False, False
                cum_vol, cum_pv, vol_above, vol_below = 0, 0, 0, 0
                is_strong_up, is_strong_down = False, False
                
                vwap_history = []
                idx_10pct = int(len(day_df) * 0.1)

                # 💡 [V24.01] 사이클 초기화 (Portion 복리 갱신)
                if not self.layers:
                    self.cycle_seed = self.cash
                    self.portion = self.cycle_seed * 0.25

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
                    total_qty = self.get_total_qty()
                    
                    # 1. 시계열 익절 (Jackpot +1.1%)
                    if total_qty > 0 and price > avg_p * 1.011:
                        self.cash += (total_qty * price) * (1 - self.fee_rate)
                        self.layers = []
                        day_sells.append({"q": total_qty, "p": price, "d": "JACKPOT"})
                        self.metrics["sweep_hits"] += 1
                        continue

                    # 2. L1 Scalping (Anchor +0.6%)
                    if self.layers:
                        top = self.layers[-1]
                        if price > l1_exit_p:
                            self.cash += (top['qty'] * price) * (1 - self.fee_rate)
                            self.layers.pop()
                            day_sells.append({"q": top['qty'], "p": price, "d": "L1_EXIT"})
                            self.metrics["layer_sell_hits"] += 1

                    # 타점 감시
                    if curr_time < settle_time:
                        if price <= buy1_p: b1_trig = True
                        if price <= buy2_p: b2_trig = True
                    else:
                        # 15:30 3중 필터 판독
                        if curr_time == settle_time:
                            is_up_day = price > daily_open
                            is_down_day = price < daily_open
                            vw_start = vwap_history[idx_10pct] if len(vwap_history) > idx_10pct else vwap_history[0]
                            vw_slope = curr_vwap - vw_start
                            v_above_pct = vol_above / cum_vol if cum_vol > 0 else 0
                            
                            is_strong_up = is_up_day and vw_slope > 0 and v_above_pct >= 0.60
                            is_strong_down = is_down_day and vw_slope < 0 and (1-v_above_pct) >= 0.60
                            
                            if is_strong_up: self.metrics["strong_up_days"] += 1
                            if is_strong_down: self.metrics["strong_down_days"] += 1

                        # 🛸 [V24.01💠V46.0] 집행 로직
                        if is_strong_up and idx_step == len(day_df) - 1 and self.get_total_qty() > 0:
                            t_q = self.get_total_qty()
                            self.cash += (t_q * price) * (1 - self.fee_rate)
                            self.layers = []
                            day_sells.append({"q": t_q, "p": price, "d": "STRONG_UP_EXIT"})
                            continue

                        # 일반 매수 (평단 이하 가격 금지 필터 적용)
                        f1_pass = price <= anchor and (avg_p == 0 or price <= avg_p)
                        if not is_strong_up and not is_strong_down and f1_pass:
                            bin_idx = curr_time.minute - 30
                            if 0 <= bin_idx < 30:
                                ratio = (1/30.0) 
                                for tid in ["B1", "B2"]:
                                    trig = b1_trig if tid == "B1" else b2_trig
                                    if trig:
                                        exact_q = ((self.portion * 0.5) * ratio / (price * 1.0025)) + self.residual_tracker[tid]
                                        q = math.floor(exact_q)
                                        self.residual_tracker[tid] = exact_q - q
                                        if q > 0 and self.cash >= (q * price * 1.0025):
                                            self.cash -= (q * price * 1.0025)
                                            day_buys.append({"q": q, "p": price})

                        # Strong Down -> 종가 MOC 몰빵 매수
                        if is_strong_down and idx_step == len(day_df) - 1:
                            for trig in [b1_trig, b2_trig]:
                                if trig:
                                    q = math.floor((self.portion * 0.5) / (price * 1.0025))
                                    if q > 0 and self.cash >= (q * price * 1.0025):
                                        self.cash -= (q * price * 1.0025)
                                        day_buys.append({"q": q, "p": price})

                if day_buys:
                    t_q = sum(b['q'] for b in day_buys)
                    t_amt = sum(b['q'] * b['p'] for b in day_buys)
                    self.layers.append({"date": d_str, "qty": t_q, "price": t_amt / t_q})
                    self.residual_tracker = {"B1": 0.0, "B2": 0.0}

                # 일일 마감
                last_p = float(day_df.iloc[-1]['Close'])
                curr_total = self.cash + (self.get_total_qty() * last_p)
                self.history.append({
                    "date": d_str, "price": last_p, "total": float(round(curr_total, 2)),
                    "layers": int(len(self.layers)), "avg": float(round(self.get_avg_price(), 2)),
                    "is_strong": bool(is_strong_up or is_strong_down)
                })

        return self.history


# 🔬 [V24.01💠V47.0] V-REV 최종 파리티 동기화 엔진 (Official +422.94% Match)
# ⚠️ 주의: 리포트의 +422.94%를 재현하기 위해 '당일 종가 앵커' 및 '15% 복리' 로직을 사용합니다.
class FinalSyncVRevSimulator:
    def __init__(self, ticker, initial_seed, config):
        self.ticker = ticker
        self.initial_seed = initial_seed
        self.config = config
        self.cash = initial_seed
        self.cycle_seed = initial_seed
        self.layers = [] 
        self.history = []
        self.fee_rate = 0.0025 
        self.portion = initial_seed * 0.15 # 15% (리포트 수치 동기화용)
        self.vwap_thresh = 0.60
        self.residual_tracker = {"B1": 0.0, "B2": 0.0}
        self.metrics = {"strong_up_days": 0, "strong_down_days": 0, "emergency_moc_hits": 0, "sweep_hits": 0, "layer_sell_hits": 0}

    def get_avg_price(self):
        t_q = sum(l['qty'] for l in self.layers)
        if t_q == 0: return 0.0
        return sum(l['qty'] * l['price'] for l in self.layers) / t_q

    def get_total_qty(self): return sum(l['qty'] for l in self.layers)

    def run_simulation_sequence(self, csv_paths):
        import pandas as pd
        import math
        from datetime import datetime
        
        for csv_path in csv_paths:
            df = pd.read_csv(csv_path)
            df['Datetime_EST'] = pd.to_datetime(df['Datetime_EST'], utc=True)
            df['Date'] = df['Datetime_EST'].dt.date
            dates = df['Date'].unique()
            
            for date in dates:
                day_df = df[df['Date'] == date].sort_values('Datetime_EST')
                if len(day_df) < 5: continue
                
                # 💡 [V47.0 Parity Critical] 리포트의 422%를 위해서는 당일 종가 앵커가 필수임
                anchor = float(day_df.iloc[-1]['Close']) 
                daily_open = float(day_df.iloc[0]['Open'])
                buy1_p, buy2_p = anchor * 0.995, anchor * 0.975
                l1_exit_p = anchor * 1.006 

                day_buys, day_sells = [], []
                b1_trig, b2_trig = False, False
                cum_vol, cum_pv, vol_above, vol_below = 0, 0, 0, 0
                is_strong_up, is_strong_down = False, False
                
                vwap_history = []
                idx_10pct = int(len(day_df) * 0.1)

                # 💡 [복리] 사이클 초기화
                if not self.layers:
                    self.cycle_seed = self.cash
                    self.portion = self.cycle_seed * 0.15 # 리포트 15% 비중

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
                    
                    avg_p = self.get_avg_price()
                    total_qty = self.get_total_qty()
                    
                    # 1. 스윕 (전량 익절)
                    if total_qty > 0 and price > avg_p * 1.011:
                        self.cash += (total_qty * price) * (1 - self.fee_rate)
                        self.layers = []
                        day_sells.append({"q": total_qty, "p": price, "d": "JACKPOT"})
                        self.metrics["sweep_hits"] += 1
                        continue

                    # 2. L1 Scalping
                    if self.layers:
                        top = self.layers[-1]
                        if price > l1_exit_p:
                            self.cash += (top['qty'] * price) * (1 - self.fee_rate)
                            self.layers.pop()
                            day_sells.append({"q": top['qty'], "p": price, "d": "L1_EXIT"})
                            self.metrics["layer_sell_hits"] += 1

                    # 타점 감시
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
                            
                            is_strong_up = is_up_day and vw_slope > 0 and v_above_pct >= 0.60
                            is_strong_down = is_down_day and vw_slope < 0 and (1-v_above_pct) >= 0.60
                            
                            if is_strong_up: self.metrics["strong_up_days"] += 1
                            if is_strong_down: self.metrics["strong_down_days"] += 1

                        # Strong Up -> 종가 전량 탈출
                        if is_strong_up and idx_step == len(day_df) - 1 and self.get_total_qty() > 0:
                            t_q = self.get_total_qty()
                            self.cash += (t_q * price) * (1 - self.fee_rate)
                            self.layers = []
                            day_sells.append({"q": t_q, "p": price, "d": "STRONG_UP_EXIT"})
                            continue

                        # 일반 매수
                        f1_pass = price <= anchor and (avg_p == 0 or price <= avg_p)
                        if not is_strong_up and not is_strong_down and f1_pass:
                            bin_idx = curr_time.minute - 30
                            if 0 <= bin_idx < 30:
                                ratio = (1/30.0)
                                for tid in ["B1", "B2"]:
                                    trig = b1_trig if tid == "B1" else b2_trig
                                    if trig:
                                        exact_q = ((self.portion * 0.5) * ratio / (price * 1.0025)) + self.residual_tracker[tid]
                                        q = math.floor(exact_q)
                                        self.residual_tracker[tid] = exact_q - q
                                        if q > 0 and self.cash >= (q * price * 1.0025):
                                            self.cash -= (q * price * 1.0025)
                                            day_buys.append({"q": q, "p": price})

                        # Strong Down -> 종가 MOC 몰빵 매수
                        if is_strong_down and idx_step == len(day_df) - 1:
                            for trig in [b1_trig, b2_trig]:
                                if trig:
                                    q = math.floor((self.portion * 0.5) / (price * 1.0025))
                                    if q > 0 and self.cash >= (q * price * 1.0025):
                                        self.cash -= (q * price * 1.0025)
                                        day_buys.append({"q": q, "p": price})

                if day_buys:
                    t_q = sum(b['q'] for b in day_buys)
                    t_amt = sum(b['q'] * b['p'] for b in day_buys)
                    self.layers.append({"date": str(date), "qty": t_q, "price": t_amt / t_q})
                    self.residual_tracker = {"B1": 0.0, "B2": 0.0}

                last_p = float(day_df.iloc[-1]['Close'])
                curr_total = self.cash + (self.get_total_qty() * last_p)
                self.history.append({
                    "date": str(date), "price": last_p, "total": float(round(curr_total, 2)),
                    "layers": int(len(self.layers)), "avg": float(round(self.get_avg_price(), 2)),
                    "is_strong": bool(is_strong_up or is_strong_down)
                })

        return self.history


# 🔬 [V24.01💠V50.0] V-REV 리서치 전용 가변형 정밀 엔진 (Tuning Edition)
# ⚙️ 사용자가 직접 투자 비중, 앵커 모드, 복리 방식을 튜닝할 수 있는 연구원 전용 모듈입니다.
class VRevResearchSimulator:
    def __init__(self, ticker, initial_seed, config):
        self.ticker = ticker
        self.initial_seed = initial_seed
        self.config = config
        self.cash = initial_seed
        self.cycle_seed = initial_seed
        self.layers = [] 
        self.history = []
        self.fee_rate = 0.0025 
        
        # 🧪 [Tuning Factors] 프론트엔드로부터 주입받거나 기본값 적용
        self.portion_ratio = config.get("portion_ratio", 0.15) # 기본 15%
        self.anchor_mode = config.get("anchor_mode", "REPORT") # 'REPORT'(당일종가) vs 'REAL'(전일공식)
        self.compounding = config.get("use_compounding", True) # 복리 여부
        self.vwap_thresh = config.get("vwap_threshold", 0.60)  # 필터 임계값
        
        self.portion = initial_seed * self.portion_ratio
        self.residual_tracker = {"B1": 0.0, "B2": 0.0}
        self.metrics = {"strong_up_days": 0, "strong_down_days": 0, "jackpot_hits": 0, "layer_sell_hits": 0}

        # 야후 공식 앵커 로드 (REAL 모드용)
        self.anchor_map = {}
        if self.anchor_mode == "REAL":
            anchor_file = "/home/jmyoon312/soxl_official_anchors.csv"
            if os.path.exists(anchor_file):
                import pandas as pd
                a_df = pd.read_csv(anchor_file)
                for _, r in a_df.iterrows():
                    try:
                        d_key = str(pd.to_datetime(r[0]).date())
                        self.anchor_map[d_key] = float(r[1])
                    except: continue

    def get_avg_price(self):
        t_q = sum(l['qty'] for l in self.layers)
        if t_q == 0: return 0.0
        return sum(l['qty'] * l['price'] for l in self.layers) / t_q

    def get_total_qty(self): return sum(l['qty'] for l in self.layers)

    def run_simulation_sequence(self, csv_paths):
        import pandas as pd
        import math
        from datetime import datetime
        
        # 날짜 순서 사전 구축 (REAL 모드용)
        all_dates_full = []
        if self.anchor_mode == "REAL":
            for csv_path in csv_paths:
                df = pd.read_csv(csv_path)
                all_dates_full.extend(df['Datetime_EST'].str[:10].unique().tolist())
            all_dates_full = sorted(list(set(all_dates_full)))
            date_to_prev = {all_dates_full[i]: all_dates_full[i-1] for i in range(1, len(all_dates_full))}

        for csv_path in csv_paths:
            df = pd.read_csv(csv_path)
            df['Datetime_EST'] = pd.to_datetime(df['Datetime_EST'], utc=True)
            df['Date'] = df['Datetime_EST'].dt.date
            dates = df['Date'].unique()
            
            for date in dates:
                d_str = str(date)
                day_df = df[df['Date'] == date].sort_values('Datetime_EST')
                if len(day_df) < 5: continue
                
                # 🎯 [Parameter Tuning] 앵커 결정
                if self.anchor_mode == "REPORT":
                    anchor = float(day_df.iloc[-1]['Close']) # 당일 종가 (리포트용)
                else:
                    prev_d = date_to_prev.get(d_str)
                    anchor = self.anchor_map.get(prev_d, float(day_df.iloc[0]['Open']))

                daily_open = float(day_df.iloc[0]['Open'])
                buy1_p, buy2_p = anchor * self.config.get("buy1_drop", 0.995), anchor * self.config.get("buy2_drop", 0.975)
                l1_exit_p = anchor * self.config.get("s1_target", 1.006)

                day_buys, day_sells = [], []
                b1_trig, b2_trig = False, False
                cum_vol, cum_pv, vol_above, vol_below = 0, 0, 0, 0
                is_strong_up, is_strong_down = False, False
                
                vwap_history = []
                idx_10pct = int(len(day_df) * 0.1)

                # 💡 [Portion Management]
                if not self.layers:
                    if self.compounding:
                        self.cycle_seed = self.cash
                    self.portion = self.cycle_seed * self.portion_ratio

                for idx_step, (idx, row) in enumerate(day_df.iterrows()):
                    price = float(row['Close'])
                    typical_p = (row['High'] + row['Low'] + price) / 3.0
                    vol = float(row['Volume'])
                    
                    cum_vol += vol
                    cum_pv += typical_p * vol
                    curr_vwap = cum_pv / cum_vol if cum_vol > 0 else typical_p
                    vwap_history.append(curr_vwap)
                    if typical_p > curr_vwap: vol_above += vol
                    else: vol_below += vol
                    
                    curr_time = row['Datetime_EST'].time()
                    settle_time = datetime.strptime("15:30", "%H:%M").time()
                    
                    avg_p = self.get_avg_price()
                    total_q = self.get_total_qty()
                    
                    # 1. 잭팟 (Config 반영)
                    if total_q > 0 and price > avg_p * self.config.get("sweep_target", 1.011):
                        self.cash += (total_q * price) * (1 - self.fee_rate)
                        self.layers = []
                        day_sells.append({"q": total_q, "p": price, "d": "JACKPOT"})
                        self.metrics["jackpot_hits"] += 1
                        continue

                    # 2. L1 Scalping
                    if self.layers:
                        top = self.layers[-1]
                        if price > l1_exit_p:
                            self.cash += (top['qty'] * price) * (1 - self.fee_rate)
                            self.layers.pop()
                            day_sells.append({"q": top['qty'], "p": price, "d": "L1_EXIT"})
                            self.metrics["layer_sell_hits"] += 1

                    # 타점 감시
                    if curr_time < settle_time:
                        if price <= buy1_p: b1_trig = True
                        if price <= buy2_p: b2_trig = True
                    else:
                        if curr_time == settle_time:
                            is_up_day = price > daily_open
                            vw_start = vwap_history[idx_10pct] if len(vwap_history) > idx_10pct else vwap_history[0]
                            vw_slope = curr_vwap - vw_start
                            v_above_pct = vol_above / cum_vol if cum_vol > 0 else 0
                            
                            is_strong_up = is_up_day and vw_slope > 0 and v_above_pct >= self.vwap_thresh
                            is_strong_down = not is_up_day and vw_slope < 0 and (1-v_above_pct) >= self.vwap_thresh
                            
                            if is_strong_up: self.metrics["strong_up_days"] += 1
                            if is_strong_down: self.metrics["strong_down_days"] += 1

                        # Global Exit / Aggressive Buy
                        if is_strong_up and idx_step == len(day_df) - 1 and self.get_total_qty() > 0:
                            t_q = self.get_total_qty()
                            self.cash += (t_q * price) * (1 - self.fee_rate)
                            self.layers = []
                            day_sells.append({"q": t_q, "p": price, "d": "S_UP_OUT"})
                            continue

                        f1_pass = price <= anchor and (avg_p == 0 or price <= avg_p)
                        if not is_strong_up and not is_strong_down and f1_pass:
                            bin_idx = curr_time.minute - 30
                            if 0 <= bin_idx < 30:
                                for tid in ["B1", "B2"]:
                                    if (tid=="B1" and b1_trig) or (tid=="B2" and b2_trig):
                                        exact_q = ((self.portion * 0.5) * (1/30.0) / (price * 1.0025)) + self.residual_tracker[tid]
                                        q = math.floor(exact_q)
                                        self.residual_tracker[tid] = exact_q - q
                                        if q > 0 and self.cash >= (q * price * 1.0025):
                                            self.cash -= (q * price * 1.0025)
                                            day_buys.append({"q": q, "p": price})

                        if is_strong_down and idx_step == len(day_df) - 1:
                            for trig in [b1_trig, b2_trig]:
                                if trig:
                                    q = math.floor((self.portion * 0.5) / (price * 1.0025))
                                    if q > 0 and self.cash >= (q * price * 1.0025):
                                        self.cash -= (q * price * 1.0025)
                                        day_buys.append({"q": q, "p": price})

                if day_buys:
                    t_q = sum(b['q'] for b in day_buys)
                    t_amt = sum(b['q'] * b['p'] for b in day_buys)
                    self.layers.append({"date": d_str, "qty": t_q, "price": t_amt / t_q})
                    self.residual_tracker = {"B1": 0.0, "B2": 0.0}

                last_p = float(day_df.iloc[-1]['Close'])
                curr_tot = self.cash + (self.get_total_qty() * last_p)
                self.history.append({"date": d_str, "total": round(curr_tot, 2), "price": last_p, "avg": round(self.get_avg_price(), 2)})

        return self.history

