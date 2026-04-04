# ==========================================================
# [strategy.py]
# ⚠️ 이 주석 및 파일명 표기는 절대 지우지 마세요.
# ==========================================================
import math
from datetime import datetime

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
        
        slots["slot_1"] = {"side": "BUY", "price": p_avg, "qty": qty, "type": "LOC", "desc": "[1차] V14:평단매수", "slot_id": 1}
        slots["slot_2"] = {"side": "BUY", "price": 0, "qty": 0, "type": "LOC", "desc": "-", "slot_id": 2}
        
        return slots

    # 📋 [Base Strategy] V24 [Shadow-Strike] - 눌림목 정밀 포격 엔진
    def _get_base_v24(self, ticker, split, t_val, available_cash, avg_price, day_low, bounce_pct, can_buy):
        slots = {}
        # 1. 시드 분할 정책 (남은 회차 기반 동적 분할)
        remaining_splits = max(1, split - t_val)
        dynamic_one_portion = available_cash / remaining_splits if remaining_splits > 0 else 0
        
        # 🎯 [V24 Core] Shadow Price 산출
        # Shadow Price = Day Low * (1 + Bounce%)
        # Final limit = min(Avg Price * 1.05, Shadow Price)
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
    def _apply_tactic_jupjup(self, avg_price, one_portion_amt, can_buy):
        base_qty = self._get_smart_qty(one_portion_amt, avg_price)
        orders = []
        for i in range(1, 3): # 슬롯 고정 위해 최대 2개만
            jup_price = self._floor(one_portion_amt / (base_qty + i))
            safe_jup_p = max(0.01, round(min(jup_price, avg_price - 0.01), 2))
            q = 1 if can_buy else 0
            orders.append({"side": "BUY", "price": safe_jup_p, "qty": q, "type": "LOC", "desc": f"[3차] 전술매수(줍줍{i})", "slot_id": 3})
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
            "slot_4": {"desc": f"[4차] {version}:익절매도", "price": 0, "qty": 0, "status": "WAITING", "side": "SELL", "result": ""},
            "slot_5": {"desc": f"[5차] {version}:목표매도", "price": 0, "qty": 0, "status": "WAITING", "side": "SELL", "result": ""}
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

        # 4. 전술(Tactics) 슬롯 할당 (Slot 3)
        if not is_v4_reverse:
            if tactics_config.get("elastic", False): # [V29.0] Elastic 우선 적용
                e_order = self._apply_tactic_elastic(current_price, avg_price, ma_5day, pei_val, one_portion_amt, can_buy)
                if e_order: plan_slots["slot_3"].update(e_order)
            
            if not plan_slots["slot_3"].get('qty'): # Elastic/Sniper 미발동 시 기존 전술
                if tactics_config.get("sniper", False): # [V29.7] Sniper 격발 체크
                    s_drop = tactics_config.get("sniper_drop", 1.5)
                    s_order = self._apply_tactic_sniper(current_price, avg_price, day_high, s_drop, qty)
                    if s_order: plan_slots["slot_3"].update(s_order)
                
                if not plan_slots["slot_3"].get('qty'): # 스나이퍼 미격발 시 하위 전술 감시
                    if tactics_config.get("shadow", False):
                        plan_slots["slot_3"].update(self._apply_tactic_shadow(avg_price, day_low, base_price, one_portion_amt, can_buy))
                    elif tactics_config.get("turbo", False):
                        plan_slots["slot_3"].update(self._apply_tactic_turbo(avg_price, prev_close, safe_ceiling, one_portion_amt, can_buy))
                    elif tactics_config.get("jupjup", False):
                        j_orders = self._apply_tactic_jupjup(avg_price, one_portion_amt, can_buy)
                        if j_orders: plan_slots["slot_3"].update(j_orders[0])

        # 5. 매도 로직 슬롯 할당 (Slot 4, 5)
        if qty > 0 and not is_v4_reverse:
            q_qty = math.ceil(qty / 4)
            rem_qty = qty - q_qty
            if tactics_config.get("sniper", False) or version == "V24":
                if star_price > 0:
                    plan_slots["slot_4"].update({"side": "SELL", "price": star_price, "qty": q_qty, "type": "LOC", "desc": f"[4차] {version}:익절매도", "slot_id": 4})
                if target_price > 0:
                    plan_slots["slot_5"].update({"side": "SELL", "price": target_price, "qty": rem_qty, "type": "LIMIT", "desc": f"[5차] {version}:목표매도", "slot_id": 5})
            else:
                if target_price > 0:
                    plan_slots["slot_5"].update({"side": "SELL", "price": target_price, "qty": qty, "type": "LIMIT", "desc": f"[5차] {version}:목표매도", "slot_id": 5})

        # 6. 실 주문 리스트 생성
        all_orders = [o for k, o in plan_slots.items() if o.get('qty', 0) > 0]
        
        v4_star_price = rev_star_price if is_v4_reverse else star_price
        
        return {
            "orders": all_orders,
            "slots": plan_slots,
            "t_val": t_val, "split": split, "dynamic_split": dynamic_split, 
            "one_portion": one_portion_amt, "process_status": process_status,
            "star_price": v4_star_price, "star_ratio": star_ratio,
            "version": version
        }

