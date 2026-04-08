"""
[Infinity Quant Hub V4 Strategy Lab]
글로벌 퀀트 커뮤니티(Reddit r/LETFs, Bogleheads, Seeking Alpha)에서 검증된
하락장 방어 전술 3종을 무한매수법 베이스 위에 레이어링합니다.

실전 봇(strategy.py, main.py)을 전혀 건드리지 않는 격리 실험실입니다.
"""
import math
import logging
import pandas as pd
from datetime import datetime
from strategy import InfiniteStrategy

logger = logging.getLogger("strategy_lab")


class CustomStrategyLab(InfiniteStrategy):

    # 🛡️ [V23.12 패치] VWAP 시장 미시구조 거래량 지배력 분석 엔진
    def analyze_vwap_dominance(self, df):
        """
        1분봉 데이터프레임을 받아 당일 VWAP 지배력을 연산합니다.
        """
        if df is None or len(df) < 10:
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

    def get_plan(self, ticker, current_price, avg_price, qty, prev_close,
                 ma_5day=0.0, day_low=0.0, day_high=0.0, pei_val=0.0, atr_val=0.0,
                 market_type="REG", available_cash=0,
                 is_simulation=False, tactics_config=None, force_turbo_off=False):

        if tactics_config is None: tactics_config = {}

        # ──────────────────────────────────────────────
        # [V-REV] 역추세 리버스 상태 확인
        # ──────────────────────────────────────────────
        is_reverse = tactics_config.get("is_reverse", False)
        rev_day = tactics_config.get("rev_day", 0)
        
        vix = tactics_config.get("_vix", 20.0)
        spy_trend = tactics_config.get("_spy_trend", "BULL")
        vwap_df = tactics_config.get("vwap_df", None)
        
        # VWAP 지배력 실시간 분석
        vwap_info = self.analyze_vwap_dominance(vwap_df) if tactics_config.get("vwap_dominance", False) else {}
        is_strong_up = vwap_info.get("is_strong_up", False)

        # ──────────────────────────────────────────────
        # [Tactic 1] TREND FILTER
        # ──────────────────────────────────────────────
        trend_blocked = (tactics_config.get("trend_filter", False) and spy_trend == "BEAR")

        # ──────────────────────────────────────────────
        # [Tactic 2] VIX-AWARE SIZING
        # ──────────────────────────────────────────────
        vix_multiplier = 1.0
        if tactics_config.get("vix_aware", False):
            if vix >= 45: vix_multiplier = 0.0
            elif vix >= 35: vix_multiplier = 0.4
            elif vix >= 25: vix_multiplier = 0.7

        if vix_multiplier == 0.0 and tactics_config.get("vix_aware", False):
            return {"orders": [], "process_status": f"🚨VIX={vix:.1f} 전면 매수보이콧", "slots": {}}

        # ──────────────────────────────────────────────
        # 베이스 전략 실행 (핵심 로직 호출)
        # ──────────────────────────────────────────────
        base_plan = super().get_plan(
            ticker, current_price, avg_price, qty, prev_close,
            ma_5day, day_low, day_high, pei_val, atr_val,
            market_type, available_cash, is_simulation,
            tactics_config, force_turbo_off
        )

        if "orders" not in base_plan: return base_plan

        process_status = base_plan.get("process_status", "")
        final_orders = []
        one_portion = base_plan.get("one_portion", 0)

        # ==========================================================
        # 🔄 [V-REV] 리버스 순환 매매 로직 오버라이드
        # ==========================================================
        if is_reverse:
            final_orders = []
            process_status = f"🔄리버스({rev_day}일차)"
            
            sell_qty = max(4, math.floor(qty / 20)) if qty >= 4 else qty
            if rev_day == 1:
                final_orders.append({"side": "SELL", "price": 0, "qty": sell_qty, "type": "MOC", "desc": "🚨리버스(의무매도)"})
            else:
                star_p = round(ma_5day, 2) if ma_5day > 0 else round(avg_price, 2)
                final_orders.append({"side": "SELL", "price": star_p, "qty": sell_qty, "type": "LOC", "desc": "🌟리버스별값매도"})
                buy_price = round(star_p - 0.01, 2)
                buy_qty = math.floor(one_portion / buy_price) if buy_price > 0 else 0
                if buy_qty > 0:
                    final_orders.append({"side": "BUY", "price": buy_price, "qty": buy_qty, "type": "LOC", "desc": "⚓리버스평단매수"})
            
            base_plan["orders"] = final_orders
            base_plan["process_status"] = process_status
            return base_plan

        # ==========================================================
        # 🛡️ 전략 레이어링 (BUY 필터링 및 수량 조정)
        # ==========================================================
        for order in base_plan["orders"]:
            slot_id = order.get("slot_id", -1)
            side = order.get("side", "")
            desc = order.get("desc", "")

            if side == "BUY" and is_strong_up:
                process_status += " | ⛔VWAP-FOMO 차단"
                continue

            if trend_blocked and side == "BUY" and slot_id == 1:
                process_status += " | 🔻TREND-BEAR 차단"
                continue

            if tactics_config.get("vix_aware", False) and side == "BUY" and vix_multiplier < 1.0:
                original_qty = order.get("qty", 0)
                order["qty"] = max(1, math.floor(original_qty * vix_multiplier))
                process_status += f" | ⚡VIX{vix:.0f}매수{int(vix_multiplier*100)}%"

            if tactics_config.get("smart_jup", False) and "줍줍" in desc:
                if current_price < avg_price and current_price > ma_5day:
                    order["qty"] = order["qty"] * 2
                    order["desc"] = "[Lab] 스마트 줍줍(x2)"
                    process_status += " | 🎯스마트 줍줍"

            final_orders.append(order)

        base_plan["orders"] = final_orders
        base_plan["process_status"] = process_status
        return base_plan

