# ==========================================================
# [strategy.py]
# ⚠️ 이 주석 및 파일명 표기는 절대 지우지 마세요.
# ==========================================================
import math
import pandas as pd
import logging
import datetime
import pytz

logger = logging.getLogger("strategy")

class InfiniteStrategy:
    def __init__(self, config):
        self.cfg = config

    def _ceil(self, val): return math.ceil(val * 100) / 100.0
    def _floor(self, val): return math.floor(val * 100) / 100.0

    def _get_smart_qty(self, amt, price):
        if price <= 0: return 0
        raw_qty = amt / price
        base_qty = math.floor(raw_qty)
        fraction = raw_qty - base_qty
        now = datetime.now()
        pseudo_rand = ((now.day * 13) + (now.month * 7) + (now.year * 3)) % 100 / 100.0
        if pseudo_rand < fraction:
            base_qty += 1
        return base_qty

    # 🛡️ [V23.12 패치] VWAP 시장 미시구조 거래량 지배력 분석 엔진
    def analyze_vwap_dominance(self, df):
        """
        1분봉 데이터프레임을 받아 당일 VWAP 지배력을 연산합니다.
        """
        if df is None or (isinstance(df, pd.DataFrame) and len(df) < 10):
            return {"vwap_price": 0.0, "is_strong_up": False, "is_strong_down": False}
            
        try:
            # 대표 가격 (Typical Price) 산출
            if 'High' in df.columns and 'Low' in df.columns:
                typical_price = (df['High'] + df['Low'] + df['Close']) / 3.0
            else:
                typical_price = df['Close']
                
            vol_x_price = typical_price * df['Volume']
            total_vol = df['Volume'].sum()
            
            if total_vol == 0: return {"vwap_price": 0.0, "is_strong_up": False, "is_strong_down": False}
                
            vwap_price = vol_x_price.sum() / total_vol
            
            # 누적 VWAP 기울기 (Slope)
            df_temp = pd.DataFrame()
            df_temp['Volume'] = df['Volume']
            df_temp['Vol_x_Price'] = vol_x_price
            df_temp['Cum_Vol'] = df_temp['Volume'].cumsum()
            df_temp['Cum_Vol_Price'] = df_temp['Vol_x_Price'].cumsum()
            df_temp['Running_VWAP'] = df_temp['Cum_Vol_Price'] / df_temp['Cum_Vol']
            
            idx_10pct = int(len(df_temp) * 0.1)
            vwap_start = df_temp['Running_VWAP'].iloc[idx_10pct]
            vwap_end = df_temp['Running_VWAP'].iloc[-1]
            vwap_slope = vwap_end - vwap_start
            
            # 거래량 지배력 (VWAP 위/아래 체결 비중)
            vol_above = df[df['Close'] > vwap_price]['Volume'].sum()
            vol_above_pct = vol_above / total_vol if total_vol > 0 else 0
            
            daily_open = df['Open'].iloc[0] if 'Open' in df.columns else df['Close'].iloc[0]
            daily_close = df['Close'].iloc[-1]
            
            is_strong_up = (daily_close > daily_open) and (vwap_slope > 0) and (vol_above_pct > 0.55)
            is_strong_down = (daily_close < daily_open) and (vwap_slope < 0) and (vol_above_pct < 0.45)
            
            return {
                "vwap_price": round(vwap_price, 2),
                "is_strong_up": bool(is_strong_up),
                "is_strong_down": bool(is_strong_down),
                "vol_above_pct": round(vol_above_pct, 4)
            }
        except Exception as e:
            logger.error(f"VWAP 분석 오류: {e}")
            return {"vwap_price": 0.0, "is_strong_up": False, "is_strong_down": False}

    # 🛡️ [V18.13 패치] KIS 자전거래(Wash-Trade) 원천 차단 방어벽 엔진
    def _apply_wash_trade_shield(self, c_orders, b_orders, sc_orders, sb_orders):
        all_o = c_orders + b_orders + sc_orders + sb_orders
        has_sell_moc = any(o['type'] in ['MOC', 'MOO'] and o['side'] == 'SELL' for o in all_o)
        s_prices = [o['price'] for o in all_o if o['side'] == 'SELL' and o['price'] > 0]
        min_s = min(s_prices) if s_prices else 0.0

        def _clean(lst):
            res = []
            for o in lst:
                if o['side'] == 'BUY':
                    if has_sell_moc and o['type'] in ['LOC', 'MOC']: continue 
                    if min_s > 0 and o['price'] >= min_s:
                        o['price'] = round(min_s - 0.01, 2)
                        if "🛡️" not in o['desc']: o['desc'] = f"🛡️{o['desc'].replace('👻', '').replace('🧹', '')}"
                    o['price'] = max(0.01, o['price'])
                res.append(o)
            return res
        return _clean(c_orders), _clean(b_orders), _clean(sc_orders), _clean(sb_orders)

    # 📋 [Base Strategy] V13 Classic - 고정 분할 기반 (V1 원본 정석)
    def _get_base_v13(self, ticker, split, one_portion_amt, avg_price, star_price, can_buy):
        slots = {}
        p_avg = max(0.01, round(avg_price - 0.01, 2))
        p_star = max(0.01, round(star_price - 0.01, 2)) if star_price > 0 else p_avg
        
        # 기본 원칙: 0.5회분 평단 LOC + 0.5회분 별값 LOC
        q_avg = self._get_smart_qty(one_portion_amt * 0.5, p_avg) if can_buy else 0
        q_star = self._get_smart_qty(one_portion_amt * 0.5, p_star) if can_buy else 0
        
        slots["slot_1"] = {"side": "BUY", "price": p_avg, "qty": q_avg, "type": "LOC", "desc": "[1차] V13:평단매수", "slot_id": 1}
        slots["slot_2"] = {"side": "BUY", "price": p_star, "qty": q_star, "type": "LOC", "desc": "[2차] V13:보조매수", "slot_id": 2}
        
        return slots

    # 📋 [Base Strategy] V14 Modular - 가변 방어 (V2.1 가변 방어)
    def _get_base_v14(self, ticker, split, t_val, available_cash, avg_price, star_price, can_buy):
        slots = {}
        # 남은 회차에 따라 매수량을 동적으로 결정 (가변 핵심)
        remaining_splits = max(1, split - t_val)
        dynamic_one_portion = available_cash / remaining_splits if remaining_splits > 0 else 0
        p_avg = max(0.01, round(avg_price - 0.01, 2))
        
        # V14는 사용자 요청에 따라 평단(Avg)에서 1.0 분량 집중 매수하여 방어력 확보
        qty = self._get_smart_qty(dynamic_one_portion, p_avg) if can_buy else 0
        
        slots["slot_1"] = {"side": "BUY", "price": p_avg, "qty": qty, "type": "LOC", "desc": "[1차] V14:평단집중", "slot_id": 1}
        slots["slot_2"] = {"side": "BUY", "price": 0, "qty": 0, "type": "LOC", "desc": "[2차] 가변보류(Bypass)", "slot_id": 2}
        
        return slots

    # 📋 [Base Strategy] V24 [Shadow-Strike] - 눌림목 정밀 포격 엔진
    def _get_base_v24(self, ticker, split, t_val, available_cash, avg_price, day_low, bounce_pct, can_buy):
        slots = {}
        # 1. 시드 분할 정책 (남은 회차 기반 동적 분할)
        remaining_splits = max(1, split - t_val)
        dynamic_one_portion = available_cash / remaining_splits if remaining_splits > 0 else 0
        
        # 🎯 [V24 Core] Shadow Price 산출
        bounce_ratio = (bounce_pct / 100.0) if bounce_pct > 0 else 0.015
        shadow_p = day_low * (1 + bounce_ratio) if day_low > 0 else avg_price
        
        # 안전 장치: 평단 대비 5% 캡 적용
        p_avg = max(0.01, round(avg_price - 0.01, 2))
        p_shadow = min(avg_price * 1.05, shadow_p)
        p_shadow = max(0.01, round(p_shadow - 0.01, 2))
        
        # V24 Shadow-Strike: 0.5회분 평단 LOC + 0.5회분 섀도우(눌림목) LOC
        q_avg = self._get_smart_qty(dynamic_one_portion * 0.5, p_avg) if can_buy else 0
        q_shadow = self._get_smart_qty(dynamic_one_portion * 0.5, p_shadow) if can_buy else 0
        
        slots["slot_1"] = {"side": "BUY", "price": p_avg, "qty": q_avg, "type": "LOC", "desc": "[1차] V24:평단매수", "slot_id": 1}
        slots["slot_2"] = {"side": "BUY", "price": p_shadow, "qty": q_shadow, "type": "LOC", "desc": "[2차] V24:섀도우포격", "slot_id": 2}
        
        return slots

    def _apply_tactic_shield(self, split, t_val):
        dynamic_split = split
        status = ""
        if t_val < (split * 0.5):
            dynamic_split = split
            status = "🌓전반전"
        elif t_val < (split * 0.75):
            dynamic_split = math.floor(split * 1.5)
            status = "🛡️방어전(2단)"
        elif t_val < (split * 0.9):
            dynamic_split = math.floor(split * 2.0)
            status = "🚨대폭락(3단)"
        else:
            dynamic_split = math.floor(split * 2.5)
            status = "☠️지옥장(4단)"
        return dynamic_split, status

    # 🛠 [Tactic] Shadow-Strike - 저점 반등 기습 매수
    def _apply_tactic_shadow(self, avg_price, day_low, base_price, one_portion_amt, can_buy):
        ref_day_low = day_low if day_low > 0 else base_price
        shadow_price = self._ceil(ref_day_low * 1.015)
        # 평단보다 너무 높게 사지 않도록 캡핑
        final_shadow = min(self._ceil(avg_price * 1.05), shadow_price)
        
        f_shadow_p = max(0.01, round(final_shadow - 0.01, 2))
        s_qty = self._get_smart_qty(one_portion_amt, f_shadow_p) if (can_buy and f_shadow_p > 0) else 0
        return {"side": "BUY", "price": f_shadow_p, "qty": s_qty, "type": "LOC", "desc": "[3차] 전술매수(Shadow)", "slot_id": 3}

    # 🛠 [Tactic] Turbo Booster - 급락 시 매칭 물량 증폭
    def _apply_tactic_turbo(self, avg_price, prev_close, safe_ceiling, one_portion_amt, can_buy):
        ref_price = min(avg_price, prev_close)
        turbo_price = max(0.01, round(min(self._ceil(ref_price * 0.95) - 0.01, safe_ceiling - 0.01), 2))
        turbo_qty = self._get_smart_qty(one_portion_amt, turbo_price) if can_buy else 0
        return {"side": "BUY", "price": turbo_price, "qty": turbo_qty, "type": "LOC", "desc": "[3차] 전술매수(Turbo)", "slot_id": 3}

    # 🛠 [Tactic] Jup-Jup Grid - 자투리 현금 거미줄 매수
    def _apply_tactic_jupjup(self, avg_price, one_portion_amt, can_buy, density=10):
        base_qty = self._get_smart_qty(one_portion_amt, avg_price)
        orders = []
        # [V33.1] 설정된 밀도(density)만큼 거미줄 주문 생성
        for i in range(1, density + 1):
            # 간격: 평단 대비 약 0.5%씩 하락하며 배치 (밀도에 따라 조정 가능)
            price_step = 1.0 - (0.005 * i)
            jup_price = self._floor(avg_price * price_step)
            safe_jup_p = max(0.01, round(min(jup_price, avg_price - 0.01), 2))
            q = 1 if can_buy else 0
            orders.append({"side": "BUY", "price": safe_jup_p, "qty": q, "type": "LOC", "desc": f"[3차] 전술매칭(줍줍{i})", "slot_id": 3})
        return orders

    # 🛠 [V29.0 Tactic] Elastic Snap-back - 이격도(PEI) 기반 과매도 역발상 매수
    def _apply_tactic_elastic(self, current_price, avg_price, ma_5day, pei_val, one_portion_amt, can_buy):
        # PEI가 -2.0 미만(2표준편차 하단 돌파)일 때 공격적 매수
        if pei_val < -2.0 and current_price < ma_5day:
            bonus_amt = one_portion_amt * 1.5 # 1.5배 물량 투입
            elastic_p = max(0.01, round(current_price * 1.01, 2)) # 현재가 부근 LOC
            qty = self._get_smart_qty(bonus_amt, elastic_p) if can_buy else 0
            return {"side": "BUY", "price": elastic_p, "qty": qty, "type": "LOC", "desc": "[3차] 전술매수(Elastic)", "slot_id": 3}
        return None

    # 🛠 [V29.0 Tactic] ATR-Dynamic Shield - ATR(변동성) 기반 가변 분할 보정
    def _apply_tactic_atr_shield(self, split, t_val, atr_val, avg_price):
        # ATR이 평단 대비 5% 이상이면 시장 변동성 극심으로 판단, 분할수 1.2배 가중
        volatility_ratio = (atr_val / avg_price) if avg_price > 0 else 0
        if volatility_ratio > 0.05:
            return math.floor(split * 1.2), "🛡️ATR-Shield"
        return split, ""

    # 🛠 [V29.7 Tactic] Upward Sniper - 장중 휩소(속임수 하락) 방어용 상방 스나이퍼
    def _apply_tactic_sniper(self, current_price, avg_price, day_high, drop_pct=1.5, qty=0):
        """
        [상방 스나이퍼 핵심 로직]
        1. 감기(Locked-on): 주가가 평단가(Avg Price) 보다 높아야 함 (수익권)
        2. 격발(Trigger): 현재가가 장중 고점(Day High) 대비 drop_pct(1.5%) 이상 하락 시
        3. 보상: 보유 수량의 25% (1/4)를 즉시 매도하여 수익 확정
        """
        if qty <= 0 or current_price <= avg_price or day_high <= 0:
            return None
            
        trigger_price = day_high * (1 - (drop_pct / 100.0))
        if current_price <= trigger_price:
            sell_qty = math.ceil(qty / 4)
            # 스나이퍼는 장중 대응이므로 MARKET 또는 LOC로 즉시 처리 지시
            return {"side": "SELL", "price": current_price, "qty": sell_qty, "type": "LOC", "desc": "[3차] 전술매도(스나이퍼-격발)", "slot_id": 3}
            
        return None

    def _get_empty_slots(self, version="V"):
        return {
            "slot_1": {"desc": f"[1차] {version}:평단매수", "price": 0, "qty": 0, "status": "WAITING", "side": "BUY", "result": ""},
            "slot_2": {"desc": f"[2차] {version}:보조매수", "price": 0, "qty": 0, "status": "WAITING", "side": "BUY", "result": ""},
            "slot_3": {"desc": f"[3차] {version}:전술매수", "price": 0, "qty": 0, "status": "WAITING", "side": "BUY", "result": ""},
            "slot_4": {"desc": f"[4차] {version}:익절대기", "price": 0, "qty": 0, "status": "WAITING", "side": "SELL", "result": ""},
            "slot_5": {"desc": f"[5차] {version}:목표대기", "price": 0, "qty": 0, "status": "WAITING", "side": "SELL", "result": ""}
        }

    def get_plan(self, ticker, current_price, avg_price, qty, prev_close, 
                 ma_5day=0.0, day_low=0.0, day_high=0.0, pei_val=0.0, atr_val=0.0,
                 market_type="REG", available_cash=0, 
                 is_simulation=False, tactics_config=None, force_turbo_off=False):
        
        # 0. 초기화 및 기본 정보 획득
        if tactics_config is None: tactics_config = {}
        process_status = ""
        
        other_locked_cash = self.cfg.get_total_locked_cash(exclude_ticker=ticker)
        real_available_cash = max(0, available_cash - other_locked_cash)
        
        split = self.cfg.get_split_count(ticker)      
        target_pct = self.cfg.get_target_profit(ticker) 
        target_ratio = target_pct / 100.0
        version = self.cfg.get_version(ticker)
        
        plan_slots = self._get_empty_slots(version)
        
        t_val, base_portion = self.cfg.get_absolute_t_val(ticker, qty, avg_price)
        target_price = self._ceil(avg_price * (1 + target_ratio)) if avg_price > 0 else 0
        
        # 별값(Star Price) 계산 (Sniper Exit 용)
        depreciation_factor = 2.0 / split if split > 0 else 0.1
        star_ratio = target_ratio - (target_ratio * depreciation_factor * t_val)
        star_price = self._ceil(avg_price * (1 + star_ratio)) if avg_price > 0 else 0
        
        base_price = current_price if current_price > 0 else prev_close
        if base_price <= 0: return {"orders": [], "process_status": "⛔가격오류", "slots": plan_slots}

        # ──────────────────────────────────────────────
        # [V-REV] 역추세 리버스 상태 및 지능형 필터 확인
        # ──────────────────────────────────────────────
        is_reverse = tactics_config.get("is_reverse", False)
        rev_day = tactics_config.get("rev_day", self.cfg.get_rev_day())
        
        vix = tactics_config.get("_vix", 20.0) # 외부에서 공급받는 VIX (없으면 20.0)
        spy_trend = tactics_config.get("_spy_trend", "BULL")
        vwap_df = tactics_config.get("vwap_df", None)
        
        # VWAP 지배력 분석
        vwap_info = self.analyze_vwap_dominance(vwap_df) if tactics_config.get("vwap_dominance", False) else {}
        is_strong_up = vwap_info.get("is_strong_up", False)

        # [Tactic] TREND FILTER
        trend_blocked = (tactics_config.get("trend_filter", False) and spy_trend == "BEAR")

        # [Tactic] VIX-AWARE SIZING
        vix_multiplier = 1.0
        if tactics_config.get("vix_aware", False):
            if vix >= 45: vix_multiplier = 0.0
            elif vix >= 35: vix_multiplier = 0.4
            elif vix >= 25: vix_multiplier = 0.7

        if vix_multiplier == 0.0 and tactics_config.get("vix_aware", False):
            return {"orders": [], "process_status": f"🚨VIX={vix:.1f} 전면 매수차단", "slots": plan_slots}

        # 1. 전술: [The Shield] 가변 분할 적용
        dynamic_split = split
        shield_status = ""
        if tactics_config.get("shield", False):
            dynamic_split, shield_status = self._apply_tactic_shield(split, t_val)
            
            # [V29.0] ATR 변동성 보정 추가 (선행 지표 결합)
            if tactics_config.get("atr_shield", False):
                dynamic_split, atr_status = self._apply_tactic_atr_shield(dynamic_split, t_val, atr_val, avg_price)
                if atr_status: shield_status += f"({atr_status})"
            
            process_status = shield_status
        elif version == "V14":
            process_status = "💎가변(Modular)"
        elif version == "V13":
            process_status = "⚓클래식(Classic)"
        else:
            process_status = "✨기본전략"

        one_portion_amt = self.cfg.get_active_seed(ticker) / dynamic_split if dynamic_split > 0 else base_portion
        is_money_short = False if is_simulation else (real_available_cash < one_portion_amt)
        is_last_lap = (split - 1) < t_val < split
        can_buy = not is_money_short and not is_last_lap
        safe_ceiling = min(avg_price, star_price) if star_price > 0 else avg_price

        # 2. 시장 상황별 분기 (프리마켓 등)
        if market_type == "PRE_CHECK":
            if qty > 0 and target_price > 0 and current_price >= target_price:
                plan_slots["slot_5"] = {"side": "SELL", "price": current_price, "qty": qty, "type": "LIMIT", "desc": "🌅프리:목표돌파", "slot_id": 5, "status": "WAITING", "result": ""}
            return {"orders": [v for k,v in plan_slots.items() if v.get('qty', 0) > 0], "process_status": "🌅프리마켓", "slots": plan_slots}

        # [새출발 로직]
        if qty == 0:
            buy_price = max(0.01, round(self._ceil(base_price * 1.05) - 0.01, 2))
            buy_qty = self._get_smart_qty(one_portion_amt, buy_price) if not is_money_short else 0
            # 새출발 시에는 모든 슬롯 초기화 상태로 1번 슬롯만 채움
            plan_slots["slot_1"] = {"side": "BUY", "price": buy_price, "qty": buy_qty, "type": "LOC", "desc": f"[1차] {version}:평단매수(새출발)", "slot_id": 1, "status": "WAITING", "result": ""}
            return {"orders": [plan_slots["slot_1"]] if buy_qty > 0 else [], "process_status": "✨새출발", "slots": plan_slots, "version": version}

        # 3. 베이스 전략별 슬롯 할당
        is_v4_reverse = False
        rev_star_price = 0
        if version == "V24" and t_val >= (split - 1):
            is_v4_reverse = True
            process_status = "🚨제로_리버스(소진)"
            safe_floor_price = self._ceil(avg_price * 1.005)
            rev_star_price = max(self._ceil(ma_5day), safe_floor_price) if ma_5day > 0 else safe_floor_price
            rev_qty = max(1, math.floor(qty / 20))
            plan_slots["slot_4"] = {"side": "SELL", "price": rev_star_price, "qty": rev_qty, "type": "LOC", "desc": "[4차] 리버스테크(매도)", "slot_id": 4, "status": "WAITING", "result": ""}
            plan_slots["slot_1"] = {"side": "BUY", "price": rev_star_price, "qty": rev_qty, "type": "LOC", "desc": "[1차] 리버스테크(매칭)", "slot_id": 1, "status": "WAITING", "result": ""}
        else:
            if version == "V24":
                bounce_val = tactics_config.get("shadow_bounce", 1.5) if tactics_config else 1.5
                base_slots = self._get_base_v24(ticker, split, t_val, real_available_cash, avg_price, day_low, bounce_val, can_buy)
            elif version == "V14":
                base_slots = self._get_base_v14(ticker, split, t_val, real_available_cash, avg_price, star_price, can_buy)
            else:
                base_slots = self._get_base_v13(ticker, split, one_portion_amt, avg_price, star_price, can_buy)
            
            for k, v in base_slots.items():
                plan_slots[k].update(v)

        # 4. 전술(Tactics) 슬롯 할당 (Slot 3) 및 다중 전술 수집
        tactical_orders = []
        if not is_v4_reverse:
            # [V33.1] 모든 활성 전술을 독립적으로 평가하여 중복 허용
            # 1) Elastic
            if tactics_config.get("elastic", False):
                e_order = self._apply_tactic_elastic(current_price, avg_price, ma_5day, pei_val, one_portion_amt, can_buy)
                if e_order: tactical_orders.append(e_order)
            
            # 2) Sniper (상방 스나이퍼 격발)
            if tactics_config.get("sniper", False):
                s_drop = tactics_config.get("sniper_drop", self.cfg.get_sniper_drop())
                s_order = self._apply_tactic_sniper(current_price, avg_price, day_high, s_drop, qty)
                if s_order: tactical_orders.append(s_order)
                
            # 3) Shadow (V24가 아닐 때만 독립 전술로 동작)
            if tactics_config.get("shadow", False) and version != "V24":
                shadow_order = self._apply_tactic_shadow(avg_price, day_low, base_price, one_portion_amt, can_buy)
                if shadow_order: tactical_orders.append(shadow_order)
                
            # 4) Turbo
            if tactics_config.get("turbo", False):
                turbo_order = self._apply_tactic_turbo(avg_price, prev_close, safe_ceiling, one_portion_amt, can_buy)
                if turbo_order: tactical_orders.append(turbo_order)
                
            # 5) JupJup (거미줄)
            if tactics_config.get("jupjup", False):
                j_density = tactics_config.get("jupjup_density", self.cfg.get_jupjup_density())
                j_orders = self._apply_tactic_jupjup(avg_price, one_portion_amt, can_buy, j_density)
                if j_orders: tactical_orders.extend(j_orders)

            # Slot 3 UI 표시: 여러 전술 중 가장 중요도가 높은 하나를 대표로 표시 (UI 레이아웃 유지)
            if tactical_orders:
                # 주문 리스트 중 첫 번째(우선순위: Elastic > Sniper > ...)를 슬롯3에 매칭
                # (orders 리스트에는 append된 모든 주문이 담김)
                plan_slots["slot_3"].update(tactical_orders[0])
                if len(tactical_orders) > 1:
                    plan_slots["slot_3"]["desc"] = f"[3차] 다중전술({len(tactical_orders)}건)"

        # 5. 매도 로직 슬롯 할당 (Slot 4, 5)
        # 🛡️ [V26.9] 당일 보호 원칙: 오늘 매수한 종목은 목표가에 상관없이 졸업(전량매도)하지 않음 (최소 1박 숙성 보장)
        today_str = datetime.datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d')
        last_buy_date = self.cfg.get_last_split_date(ticker)
        is_protected_today = (last_buy_date == today_str)

        if qty > 0 and not is_v4_reverse and not is_protected_today:
            q_qty = math.ceil(qty / 4)
            rem_qty = qty - q_qty
            if tactics_config.get("sniper", False) or version == "V24":
                if star_price > 0:
                    plan_slots["slot_4"].update({"side": "SELL", "price": star_price, "qty": q_qty, "type": "LOC", "desc": f"[4차] {version}:익절매도", "slot_id": 4})
                if target_price > 0:
                    plan_slots["slot_5"].update({"side": "SELL", "price": target_price, "qty": rem_qty, "type": "LIMIT", "desc": f"[5차] {version}:목표매도", "slot_id": 5})
            else:
                # 스나이퍼 미사용 클래식 모드: 5차에 전량 할당
                if target_price > 0:
                    plan_slots["slot_4"].update({"desc": f"[4차] {version}:익절보류", "price": 0, "qty": 0})
                    plan_slots["slot_5"].update({"side": "SELL", "price": target_price, "qty": qty, "type": "LIMIT", "desc": f"[5차] {version}:전량목표매도", "slot_id": 5})
        elif is_protected_today and qty > 0:
            logging.info(f"🛡️ [{ticker}] 당일 매수 보호 중 (최소 1박 숙성 원칙). 익절 주문을 대기합니다.")

        # 6. 실 주문 리스트 생성
        all_orders = [o for k, o in plan_slots.items() if o.get('qty', 0) > 0 and k != "slot_3"]
        # 슬롯3 대신 수집된 tactical_orders 전체를 실제 주문에 포함
        all_orders.extend([o for o in tactical_orders if o.get('qty', 0) > 0])
        
        # 🔄 [V-REV] 리버스 순환 매매 로직 오버라이드 (최우선 순위)
        if is_reverse:
            # 프리마켓(PRE_CHECK) 단계에서는 실제 주문을 내지 않고 상태만 표시하여 스케줄 장애 방지
            is_active_trading_time = (market_type == "REG")
            
            all_orders = []
            process_status = f"🔄리버스({rev_day}일차)"
            
            # 리버스 시에는 물량을 작게 나누어 순환 (평균 1/20)
            rev_sell_qty = max(1, math.floor(qty / 20)) if qty >= 1 else 0
            if rev_day == 1:
                # 1일차: 시장가 또는 MOC로 의무적 물량 덜어내기
                if rev_sell_qty > 0 and is_active_trading_time:
                    all_orders.append({"side": "SELL", "price": base_price, "qty": rev_sell_qty, "type": "LOC", "desc": "🚨리버스(의무매도)", "slot_id": 4})
            else:
                # 2일차 이후: 평단가(또는 MA5) 부근에서 매도와 매수 동시 배치 (Zero-Reverse 고도화)
                star_p = round(ma_5day, 2) if ma_5day > 0 else round(avg_price, 2)
                if rev_sell_qty > 0 and is_active_trading_time:
                    all_orders.append({"side": "SELL", "price": star_p, "qty": rev_sell_qty, "type": "LOC", "desc": "🌟리버스별값매도", "slot_id": 4})
                
                # 매수: 별값 바로 아래에서 1회분 매수 대기
                buy_price = round(star_p - 0.01, 2)
                buy_qty = self._get_smart_qty(one_portion_amt, buy_price) if (can_buy and buy_price > 0) else 0
                if buy_qty > 0 and is_active_trading_time:
                    all_orders.append({"side": "BUY", "price": buy_price, "qty": buy_qty, "type": "LOC", "desc": "⚓리버스평단매수", "slot_id": 1})
            
            # 리버스 시에는 전용 슬롯만 갱신하여 반환
            plan_slots = self._get_empty_slots("REV")
            for o in all_orders:
                sid = f"slot_{o.get('slot_id', 1)}"
                if sid in plan_slots: plan_slots[sid].update(o)
            
            return {
                "orders": all_orders, "slots": plan_slots, "process_status": process_status,
                "t_val": t_val, "split": split, "dynamic_split": dynamic_split, "version": "REV"
            }

        # 🛡️ 지능형 필터링 레이어링 (BUY 주문 보정)
        final_orders = []
        for order in all_orders:
            if order.get("side") == "BUY":
                # FOMO 차단
                if is_strong_up and tactics_config.get("vwap_dominance", False):
                    process_status += " | ⛔VWAP-FOMO 차단"
                    continue
                # 트렌드 차단
                if trend_blocked and order.get("slot_id") == 1:
                    process_status += " | 🔻TREND-BEAR 차단"
                    continue
                # VIX 비중 조절
                if tactics_config.get("vix_aware", False) and vix_multiplier < 1.0:
                    order["qty"] = max(1, math.floor(order.get("qty", 0) * vix_multiplier))
                    process_status += f" | ⚡VIX조절({int(vix_multiplier*100)}%)"
            
            final_orders.append(order)

        v4_star_price = rev_star_price if is_v4_reverse else star_price
        
        return {
            "orders": final_orders,
            "slots": plan_slots,
            "t_val": t_val, "split": split, "dynamic_split": dynamic_split, 
            "one_portion": one_portion_amt, "process_status": process_status,
            "star_price": v4_star_price, "star_ratio": star_ratio,
            "version": version
        }

