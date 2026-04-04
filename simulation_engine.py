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
