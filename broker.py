# ==========================================================
# [broker.py]
# ⚠️ 이 주석 및 파일명 표기는 절대 지우지 마세요.
# ==========================================================
import logging  # 🔄 모의투자 디버깅용 추가 (실전: 없음)
import requests
import json
import time
import datetime
import os
import math
import yfinance as yf
import pytz
import tempfile
import pandas as pd   # 🔥 V20 추가: 동적 타점 계산용
import numpy as np    # 🔥 V20 추가: 동적 타점 계산용

class KoreaInvestmentBroker:
    # ⚡ [V24 Shared Cache] 모으/실전 간 가격 불일치 해소 및 API 부하 절감을 위한 클래스 레벨 공유 캐시
    _price_cache = {} # {ticker: (timestamp, data)}

    def __init__(self, cfg, app_key, app_secret, cano, acnt_prdt_cd="01", is_real=False):
        self.cfg = cfg # 📋 [V33.5] 통합 로깅 전용 설정 매니저 주입
        self.app_key = app_key
        self.app_secret = app_secret
        self.cano = cano
        self.acnt_prdt_cd = acnt_prdt_cd
        self.is_real = is_real
        self.mode_tag = "🚀 [REAL]" if is_real else "🧪 [MOCK]"
        
        # 🌐 [V22.2] 환경별 베이스 URL 자동 선택
        if is_real:
            self.base_url = "https://openapi.koreainvestment.com:9443"
        else:
            self.base_url = "https://openapivts.koreainvestment.com:29443"
            
        self.token_file = f"data/token_{cano}.dat" 
        self.token = None
        self._excg_cd_cache = {} 
        self.last_holdings_value = 0.0 # 💰 [V23.1] 전체 포트폴리오 평가 금액 (총 자산 계산용)
        
        print(f"✅ [Broker] {self.mode_tag} 엔진 초기화 완료 (계좌: {cano})")
        self._get_access_token()

    def _get_tr_id(self, tr_id):
        """[V22.2] 환경(모의/실전)에 따른 TR ID 접두어 자동 변환기"""
        if not tr_id: return ""
        # 첫 글자가 V나 T인 경우 환경에 맞춰 교체
        if tr_id.startswith('V') or tr_id.startswith('T'):
            prefix = 'T' if self.is_real else 'V'
            return prefix + tr_id[1:]
        return tr_id

    def _get_access_token(self, force=False):
        if not force and os.path.exists(self.token_file):
            try:
                with open(self.token_file, 'r') as f:
                    saved = json.load(f)
                expire_time = datetime.datetime.strptime(saved['expire'], '%Y-%m-%d %H:%M:%S')
                if expire_time > datetime.datetime.now() + datetime.timedelta(hours=1):
                    self.token = saved['token']
                    return
            except Exception: pass

        if force and os.path.exists(self.token_file):
            try: os.remove(self.token_file)
            except Exception: pass

        url = f"{self.base_url}/oauth2/tokenP"
        body = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
        
        try:
            res = requests.post(url, headers={"content-type": "application/json"}, data=json.dumps(body), timeout=5)
            data = res.json()
            if 'access_token' in data:
                self.token = data['access_token']
                expire_str = (datetime.datetime.now() + datetime.timedelta(seconds=int(data['expires_in']))).strftime('%Y-%m-%d %H:%M:%S')
                
                dir_name = os.path.dirname(self.token_file)
                if dir_name and not os.path.exists(dir_name):
                    os.makedirs(dir_name, exist_ok=True)
                fd, temp_path = tempfile.mkstemp(dir=dir_name, text=True)
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump({'token': self.token, 'expire': expire_str}, f)
                    f.flush()
                    os.fsync(fd)
                os.replace(temp_path, self.token_file)
            else:
                print(f"❌ [Broker] {self.mode_tag} 토큰 발급 실패: {data.get('error_description', '알 수 없는 오류')}")
        except Exception as e:
            print(f"❌ [Broker] {self.mode_tag} 토큰 통신 에러: {e}")

    def _get_header(self, tr_id):
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P"
        }

    def _api_request(self, method, url, headers, params=None, data=None):
        """🌟 [V22.2 Bulldog Engine] 5회 리트라이 및 유량 제한 대응용 강화 엔진"""
        # 🚀 [V29.8 Optimization] 모의투자 리트라이 단축 (동기화 병목 방어)
        is_real = getattr(self, 'is_real', True)
        max_retries = 5 if is_real else 2
        req_timeout = 5 if is_real else 3
        
        for attempt in range(max_retries):
            try:
                if method.upper() == "GET":
                    res = requests.get(url, headers=headers, params=params, timeout=req_timeout)
                else:
                    res = requests.post(url, headers=headers, data=json.dumps(data) if data else None, timeout=req_timeout)
                
                # HTTP 상태 코드 확인 (429: 유량제한, 500대: 서버오류)
                if res.status_code == 429 or res.status_code >= 500:
                    # 🚀 [V29.8] 재시도 간격 조정
                    multiplier = 1.0 if not getattr(self, 'is_real', True) else 1.5
                    wait_sec = multiplier * (attempt + 1)
                    print(f"⚠️ [Bulldog] {self.mode_tag} 서버 응답 지연 ({res.status_code}). {wait_sec}초 후 재시도... ({attempt+1}/{max_retries})")
                    time.sleep(wait_sec)
                    continue

                resp_json = res.json()
                rt_cd = resp_json.get('rt_cd', '0')
                msg1 = resp_json.get('msg1', '')

                # KIS 특정 에러 처리 (토큰 만료 등)
                if rt_cd != '0':
                    if any(x in msg1.lower() for x in ['토큰', '접근토큰', 'token', 'expired', '인증', 'authorization']):
                        if attempt < 2: 
                            print(f"🚨 [Bulldog] 토큰 만료 감지! 강제 갱신 중...: {msg1}")
                            self._get_access_token(force=True)
                            headers["authorization"] = f"Bearer {self.token}"
                            time.sleep(1.0)
                            continue
                    
                    # 유량 제한 에러 코드 (상태코드가 200이면서 본문에 에러가 있는 경우)
                    if "초당" in msg1 or "유량" in msg1 or "limit" in msg1.lower():
                        wait_sec = 2.0 * (attempt + 1)
                        print(f"🐢 [Bulldog] API 유량 제한 감지. {wait_sec}초 대기... ({msg1})")
                        time.sleep(wait_sec)
                        continue

                return res, resp_json
            except Exception as e:
                wait_sec = 1.0 * (attempt + 1)
                print(f"⚠️ [Bulldog] {self.mode_tag} 통신 예외 발생 ({type(e).__name__}): {e}. {wait_sec}초 후 재시도... ({attempt+1}/{max_retries})")
                if attempt == max_retries - 1: return None, {}
                time.sleep(wait_sec)
        return None, {}

    def _call_api(self, tr_id, url_path, method="GET", params=None, body=None):
        # 🎯 [V22.2] TR ID를 환경에 맞게 자동 변환
        actual_tr_id = self._get_tr_id(tr_id)
        headers = self._get_header(actual_tr_id)
        url = f"{self.base_url}{url_path}"
        res, resp_json = self._api_request(method, url, headers, params=params, data=body)
        if not resp_json: return {'rt_cd': '999', 'msg1': '통신 오류 또는 최대 재시도 횟수 초과'}
        return resp_json

    def _ceil_2(self, value):
        if value is None: return 0.0
        return math.ceil(value * 100) / 100.0

    def _safe_float(self, value):
        try: return float(str(value).replace(',', ''))
        except Exception: return 0.0

    def _get_exchange_code(self, ticker, target_api="PRICE"):
        if ticker in self._excg_cd_cache:
            codes = self._excg_cd_cache[ticker]
            return codes['PRICE'] if target_api == "PRICE" else codes['ORDER']

        price_cd = "NAS"
        order_cd = "NASD"
        dynamic_success = False

        try:
            for prdt_type in ["512", "513", "529"]:
                params = {
                    "PRDT_TYPE_CD": prdt_type,
                    "PDNO": ticker
                }
                res = self._call_api("CTPF1702R", "/uapi/overseas-price/v1/quotations/search-info", "GET", params=params)
                
                if res.get('rt_cd') == '0' and res.get('output'):
                    excg_name = str(res['output'].get('ovrs_excg_cd', '')).upper()
                    if "NASD" in excg_name or "NASDAQ" in excg_name:
                        price_cd, order_cd = "NAS", "NASD"
                        dynamic_success = True
                        break
                    elif "NYSE" in excg_name or "NEW YORK" in excg_name:
                        price_cd, order_cd = "NYS", "NYSE"
                        dynamic_success = True
                        break
                    elif "AMEX" in excg_name:
                        price_cd, order_cd = "AMS", "AMEX"
                        dynamic_success = True
                        break
        except Exception as e:
            print(f"⚠️ [Broker] 거래소 코드 동적 획득 실패: {ticker} - {e}")

        if not dynamic_success:
            if ticker == "SOXL": price_cd, order_cd = "NAS", "NASD" # SOXL은 NASDAQ 상장이나 KIS에서는 AMEX/NASD 혼용됨. 안전하게 NASD 시도
            elif ticker == "TQQQ": price_cd, order_cd = "NAS", "NASD"

        # 🧪 [V26.7] 모의투자 매도 시 3자리 코드(NAS, NYS, AMS) 필수 대응
        if not self.is_real:
            if order_cd == "NASD": order_cd = "NAS"
            elif order_cd == "NYSE": order_cd = "NYS"
            elif order_cd == "AMEX": order_cd = "AMS"

        self._excg_cd_cache[ticker] = {'PRICE': price_cd, 'ORDER': order_cd}
        return price_cd if target_api == "PRICE" else order_cd

    def get_account_balance(self):
        cash = 0.0
        holdings = {}
        
        # 🧪 [V24.5] 계좌 데이터 수집 성공 여부 판정 로직 강화 (0원 계좌 지원)
        success_count = 0
        
        # 🔄 모의투자: VTTS3007R(해외주식 매수가능금액조회) API로 현금을 직접 조회
        try:
            psamount_params = {
                "CANO": self.cano, "ACNT_PRDT_CD": self.acnt_prdt_cd,
                "OVRS_EXCG_CD": "NASD",  # 나스닥 기준
                "OVRS_ORD_UNPR": "0",    # 0이면 전체 주문가능금액 조회
                "ITEM_CD": "TQQQ"        # 종목코드 필수 (전체 가능금액 반환용)
            }
            res_ps = self._call_api("VTTS3007R", "/uapi/overseas-stock/v1/trading/inquire-psamount", "GET", psamount_params)
            
            if res_ps and res_ps.get('rt_cd') == '0':
                success_count += 1
                output = res_ps.get('output', {})
                cash = self._safe_float(output.get('frcr_ord_psbl_amt1', 0))
                if cash <= 0:
                    cash = self._safe_float(output.get('ovrs_ord_psbl_amt', 0))
            elif res_ps:
                m_str = "REAL" if self.is_real else "MOCK"
                logging.warning(f"⚠️ [Broker] 매수가능금액 API 실패 ({m_str}) - rt_cd: {res_ps.get('rt_cd')}, msg1: {res_ps.get('msg1', '메시지 없음')}")
            else:
                logging.warning("⚠️ [Broker] 매수가능금액 API 응답 없음 (None)")
        except Exception as e:
            logging.warning(f"⚠️ [Broker] 매수가능금액 조회 예외: {e}")

        target_excgs = ["NASD", "AMEX", "NYSE"] 
        for excg in target_excgs:
            try:
                if not self.is_real: time.sleep(1) # 모의투자 초당 제한 회피
                params_hold = {"CANO": self.cano, "ACNT_PRDT_CD": self.acnt_prdt_cd, "OVRS_EXCG_CD": excg, "TR_CRCY_CD": "USD", "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""}
                res_hold = self._call_api("VTTS3012R", "/uapi/overseas-stock/v1/trading/inquire-balance", "GET", params_hold)
                
                if res_hold and res_hold.get('rt_cd') == '0':
                    success_count += 1
                    o2 = res_hold.get('output2', {})
                    if isinstance(o2, list) and len(o2) > 0: o2 = o2[0]
                    
                    # 가용현금 보정
                    new_cash = self._safe_float(o2.get('ovrs_ord_psbl_amt', 0))
                    if new_cash > cash: cash = new_cash

                    # 보유 종목 추출
                    for item in res_hold.get('output1', []):
                        ticker = item.get('ovrs_pdno') or item.get('pdno')
                        if not ticker: continue
                        
                        qty = int(self._safe_float(item.get('ovrs_cblc_qty', 0)) or self._safe_float(item.get('cblc_qty', 0)))
                        avg = self._safe_float(item.get('pchs_avg_pric', 0))
                        
                        if qty > 0:
                            holdings[ticker] = {'qty': qty, 'avg': avg}
                elif res_hold and res_hold.get('rt_cd') not in ['0', '999']:
                    # 999는 통계적 실패(타임아웃)이므로 성공으로 치지 않음
                    pass
            except Exception as e:
                logging.warning(f"⚠️ [Broker] {excg} 잔고 조회 중 예외: {e}")
        
        # 🧪 [V29.8 Persistence] API 통신 실패 시 기존 데이터 보호
        if success_count == 0:
            logging.error(f"🚨 [Broker] {self.mode_tag} 모든 잔고 조회 API 실패. 데이터 보호를 위해 'None'을 반환합니다.")
            return None, None
        
        return cash, holdings

    def get_current_price(self, ticker, is_market_closed=False):
        # ⚡ [V24] 공유 캐시 확인 (5초 이내 데이터면 즉시 반환)
        now = time.time()
        if ticker in KoreaInvestmentBroker._price_cache:
            ts, data = KoreaInvestmentBroker._price_cache[ticker]
            if now - ts < 5:
                print(f"⚡ [Shared-Cache] {self.mode_tag} {ticker} 캐시 히트 (부하 절감!)")
                return data.get("current_price", 0.0)

        try:
            stock = yf.Ticker(ticker)
            if is_market_closed: return float(stock.fast_info['last_price'])
            hist = stock.history(period="1d", interval="1m", prepost=True)
            if not hist.empty: price = float(hist['Close'].iloc[-1])
            else: price = float(stock.fast_info['last_price'])
            
            # 캐시 업데이트 (일부 데이터만이라도 동기화)
            if price > 0:
                KoreaInvestmentBroker._price_cache[ticker] = (now, {"current_price": price})
            return price
        except Exception as e:
            print(f"⚠️ [야후 파이낸스] 현재가 에러, 한투 API 우회 가동: {e}")

        try:
            excg_cd = self._get_exchange_code(ticker, target_api="PRICE")
            params = {"AUTH": "", "EXCD": excg_cd, "SYMB": ticker}
            res = self._call_api("HHDFS76200200", "/uapi/overseas-price/v1/quotations/price", "GET", params=params)
            if res.get('rt_cd') == '0':
                return float(res.get('output', {}).get('last', 0.0))
        except Exception as e:
            print(f"❌ [한투 API] 현재가 우회 조회 실패: {e}")
        return 0.0
        
    def get_ask_price(self, ticker):
        try:
            excg_cd = self._get_exchange_code(ticker, target_api="PRICE")
            params = {"AUTH": "", "EXCD": excg_cd, "SYMB": ticker}
            res = self._call_api("HHDFS76200100", "/uapi/overseas-price/v1/quotations/inquire-asking-price", "GET", params=params)
            if res.get('rt_cd') == '0':
                output2 = res.get('output2', [])
                if isinstance(output2, list) and len(output2) > 0:
                    return float(output2[0].get('pask1', 0.0))
                elif isinstance(output2, dict):
                    return float(output2.get('pask1', 0.0))
        except Exception as e:
            print(f"❌ [한투 API] 매도 1호가 조회 실패: {e}")
        return 0.0

    def get_bid_price(self, ticker):
        try:
            excg_cd = self._get_exchange_code(ticker, target_api="PRICE")
            params = {"AUTH": "", "EXCD": excg_cd, "SYMB": ticker}
            res = self._call_api("HHDFS76200100", "/uapi/overseas-price/v1/quotations/inquire-asking-price", "GET", params=params)
            if res.get('rt_cd') == '0':
                output2 = res.get('output2', [])
                if isinstance(output2, list) and len(output2) > 0:
                    return float(output2[0].get('pbid1', 0.0))
                elif isinstance(output2, dict):
                    return float(output2.get('pbid1', 0.0))
        except Exception as e:
            print(f"❌ [한투 API] 매수 1호가 조회 실패: {e}")
        return 0.0

    def get_previous_close(self, ticker):
        try: return float(yf.Ticker(ticker).fast_info['previous_close'])
        except Exception as e:
            print(f"⚠️ [야후 파이낸스] 전일종가 에러, 한투 API 우회 가동: {e}")

        try:
            excg_cd = self._get_exchange_code(ticker, target_api="PRICE")
            params = {"AUTH": "", "EXCD": excg_cd, "SYMB": ticker}
            res = self._call_api("HHDFS76200200", "/uapi/overseas-price/v1/quotations/price", "GET", params=params)
            if res.get('rt_cd') == '0':
                return float(res.get('output', {}).get('base', 0.0))
        except Exception as e:
            print(f"❌ [한투 API] 전일종가 우회 조회 실패: {e}")
        return 0.0

    def get_5day_ma(self, ticker):
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="10d") 
            if len(hist) >= 5: return float(hist['Close'][-5:].mean())
        except Exception as e:
            print(f"⚠️ [야후 파이낸스] MA5 에러, 한투 API 우회 가동: {e}")
            
        try:
            excg_cd = self._get_exchange_code(ticker, target_api="PRICE")
            params = {
                "AUTH": "", "EXCD": excg_cd, "SYMB": ticker,
                "GUBN": "0", "BYMD": "", "MODP": "1"
            }
            res = self._call_api("HHDFS76240000", "/uapi/overseas-price/v1/quotations/dailyprice", "GET", params=params)
            if res.get('rt_cd') == '0':
                output2 = res.get('output2', [])
                if isinstance(output2, list) and len(output2) >= 5:
                    closes = [float(x['clos']) for x in output2[:5]]
                    return sum(closes) / len(closes)
        except Exception as e:
            print(f"❌ [한투 API] MA5 우회 조회 실패: {e}")
            
        return 0.0

    def get_unfilled_orders(self, ticker):
        excg_cd = self._get_exchange_code(ticker, target_api="ORDER")
        params = {"CANO": self.cano, "ACNT_PRDT_CD": self.acnt_prdt_cd, "OVRS_EXCG_CD": excg_cd, "SORT_SQN": "DS", "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""}
        res = self._call_api("VTTS3018R", "/uapi/overseas-stock/v1/trading/inquire-nccs", "GET", params=params)  # 🔄 모의투자 tr_id (실전: TTTS3018R)
        if res.get('rt_cd') == '0':
            output = res.get('output', [])
            if isinstance(output, dict): output = [output]
            return [item.get('odno') for item in output if item.get('pdno') == ticker]
        return []

    def get_unfilled_orders_detail(self, ticker):
        excg_cd = self._get_exchange_code(ticker, target_api="ORDER")
        params = {"CANO": self.cano, "ACNT_PRDT_CD": self.acnt_prdt_cd, "OVRS_EXCG_CD": excg_cd, "SORT_SQN": "DS", "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""}
        res = self._call_api("VTTS3018R", "/uapi/overseas-stock/v1/trading/inquire-nccs", "GET", params=params)  # 🔄 모의투자 tr_id (실전: TTTS3018R)
        if res.get('rt_cd') == '0':
            output = res.get('output', [])
            if isinstance(output, dict): output = [output]
            return [item for item in output if item.get('pdno') == ticker]
        return []

    def cancel_all_orders_safe(self, ticker, side=None):
        for i in range(3):
            orders = self.get_unfilled_orders_detail(ticker)
            if not orders: return True
            
            target_orders = orders
            if side == "BUY":
                target_orders = [o for o in orders if o.get('sll_buy_dvsn_cd') == '02']
            elif side == "SELL":
                target_orders = [o for o in orders if o.get('sll_buy_dvsn_cd') == '01']
                
            if not target_orders: return True
            
            for o in target_orders: 
                self.cancel_order(ticker, o.get('odno'))
            time.sleep(5)
            
        final_orders = self.get_unfilled_orders_detail(ticker)
        if side == "BUY":
            return not any(o.get('sll_buy_dvsn_cd') == '02' for o in final_orders)
        elif side == "SELL":
            return not any(o.get('sll_buy_dvsn_cd') == '01' for o in final_orders)
        return not bool(final_orders)

    def cancel_targeted_orders(self, ticker, side, target_ord_dvsn):
        sll_buy_cd = '02' if side == "BUY" else '01'
        orders = self.get_unfilled_orders_detail(ticker)
        if not orders: return 0
        
        target_orders = [o for o in orders if o.get('sll_buy_dvsn_cd') == sll_buy_cd and o.get('ord_dvsn_cd') == target_ord_dvsn]
        
        for o in target_orders:
            self.cancel_order(ticker, o.get('odno'))
            time.sleep(0.3)
            
        return len(target_orders)

    def send_order(self, ticker, side, qty, price, order_type="LIMIT"):
        """🛡️ [V22.2 Wash-protect] 워시트레이드 방지 로직이 포함된 주문 엔진"""
        # 1. 워시트레이드 보호: 반대 방향 미체결 주문 존재 시 자동 취소
        opp_side = "SELL" if side == "BUY" else "BUY"
        opp_orders = self.get_unfilled_orders_detail(ticker)
        
        # 반대 방향 주문 필터링
        opp_cd = "01" if side == "BUY" else "02" # 내가 BUY면 상대는 SELL(01), 내가 SELL이면 상대는 BUY(02)
        target_opps = [o for o in opp_orders if o.get('sll_buy_dvsn_cd') == opp_cd]
        
        if target_opps:
            msg = f"⚔️ [Wash-protect] {ticker} {side} 주문 전 반대 주문({len(target_opps)}건) 발견! 자동 취소 후 진행합니다."
            print(msg)
            # 🚀 [V33.5] 워시트레이드 방지 내역도 사용자 알림 피드에 기록
            if self.cfg:
                self.cfg.log_event("TRADE", "WASH", "INFO", f"[{ticker}] 워시트레이드 보호 가동", details=f"반대 주문 {len(target_opps)}건 선제 취소")
            
            for o in target_opps:
                self.cancel_order(ticker, o.get('odno'))
                time.sleep(0.3)
            time.sleep(0.5) # 취소 반영 대기

        # 2. 실제 주문 진행
        # 🚀 [V23.1] 모의/실전 호환 TR ID 동적 전환 (하드코딩 제거)
        if side == "BUY":
            tr_id = self._get_tr_id("TTTT1002U")
        else:
            # 🔄 [V26.7] 모의투자 매도 TR ID 정정 (VTTT1006U -> VTTT1001U)
            # 모의투자 미국주식 매도는 VTTT1001U를 사용해야 "지원하지 않는 방식" 에러를 피할 수 있음
            tr_id = "VTTT1001U" if not self.is_real else "TTTT1006U"
        excg_cd = self._get_exchange_code(ticker, target_api="ORDER")

        # 🎯 [V22.2] 모의투자 LOC 폴백 로직
        if order_type == "LOC": 
            if self.is_real:
                ord_dvsn = "34"
            else:
                ord_dvsn = "00" # 모의투자는 LOC 미지원 → 지정가(Limit)로 시뮬레이션
                print(f"⚠️ [Mock-Logic] 모의투자용 LOC 주문이 지정가(Limit)로 보정되었습니다. (${price})")
        elif order_type == "MOC": ord_dvsn = "33"
        elif order_type == "LOO": ord_dvsn = "02"
        elif order_type == "MOO": ord_dvsn = "31"
        elif order_type == "PRE": ord_dvsn = "32" # 프리마켓 지정가
        else: ord_dvsn = "00"

        final_price = self._ceil_2(price)
        if order_type in ["MOC", "MOO"]: final_price = 0
        
        body = {
            "CANO": self.cano, "ACNT_PRDT_CD": self.acnt_prdt_cd, "OVRS_EXCG_CD": excg_cd,
            "PDNO": ticker, "ORD_QTY": str(int(qty)), "OVRS_ORD_UNPR": f"{final_price:.2f}" if final_price > 0 else "0",
            "SLL_BUY_DVSN_CD": "02" if side == "BUY" else "01",
            "ORD_SVR_DVSN_CD": "0", 
            "ORD_DVSN": ord_dvsn 
        }
        res = self._call_api(tr_id, "/uapi/overseas-stock/v1/trading/order", "POST", body=body)
        
        rt_cd = res.get('rt_cd', '999')
        # 🚀 [V33.5] 모든 개별 주문 내역을 실시간 피드(TRADE)에 기록 (상황실 자동 연동)
        if self.cfg:
            status = "SUCCESS" if rt_cd == "0" else "ERROR"
            order_label = "매수" if side == "BUY" else "매도"
            msg = f"[{ticker}] {order_label} {int(qty)}주 ({order_type})"
            detail = f"단가: ${final_price:.2f} ({res.get('msg1', '응답 없음')})"
            self.cfg.log_event("TRADE", order_type.upper(), status, msg, details=detail)
        msg1 = res.get('msg1', '오류')
        output = res.get('output', {})
        odno = output.get('ODNO', '') if isinstance(output, dict) else ''
        
        if rt_cd == '0':
            print(f"✅ [Order] {self.mode_tag} {ticker} {side} ${final_price} {qty}주 주문 성공 (ODNO: {odno})")
        else:
            if "영업일이 아닙니다" in msg1:
                rt_cd = '888'
                print(f"🚫 [Order] {self.mode_tag} {ticker} {side} 주문 거부: 모의투자 영업일 아님 (우회 차단)")
            else:
                print(f"❌ [Order] {self.mode_tag} {ticker} {side} 주문 실패: {msg1}")
            
        return {'rt_cd': rt_cd, 'msg1': msg1, 'odno': odno}

    def cancel_order(self, ticker, order_id):
        excg_cd = self._get_exchange_code(ticker, target_api="ORDER")
        body = {
            "CANO": self.cano, "ACNT_PRDT_CD": self.acnt_prdt_cd, "OVRS_EXCG_CD": excg_cd,
            "PDNO": ticker, "ORGN_ODNO": order_id, "RVSE_CNCL_DVSN_CD": "02",
            "ORD_QTY": "0", "OVRS_ORD_UNPR": "0", "ORD_SVR_DVSN_CD": "0"
        }
        tr_id = self._get_tr_id("TTTT1004U")
        self._call_api(tr_id, "/uapi/overseas-stock/v1/trading/order-rvsecncl", "POST", body=body)

    def get_execution_history(self, ticker, start_date, end_date):
        excg_cd = self._get_exchange_code(ticker, target_api="ORDER")
        valid_execs = []
        seen_keys = set()
        fk200 = ""
        nk200 = ""
        
        for attempt in range(10): 
            params = {
                "CANO": self.cano, "ACNT_PRDT_CD": self.acnt_prdt_cd, "PDNO": ticker,
                "ORD_STRT_DT": start_date, "ORD_END_DT": end_date, "SLL_BUY_DVSN": "00",      
                "CCLD_NCCS_DVSN": "00", "OVRS_EXCG_CD": excg_cd, "SORT_SQN": "DS",
                "ORD_DT": "", "ORD_GNO_BRNO": "", "ODNO": "", "CTX_AREA_FK200": fk200, "CTX_AREA_NK200": nk200
            }
            
            headers = self._get_header(self._get_tr_id("TTTS3035R"))
            url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-ccnl"
            res, resp_json = self._api_request("GET", url, headers, params=params)
            
            if res and resp_json.get('rt_cd') == '0':
                output = resp_json.get('output', [])
                if isinstance(output, dict): output = [output] 
                for item in output:
                    if float(item.get('ft_ccld_qty', '0')) > 0:
                        unique_key = f"{item.get('odno')}_{item.get('ord_tmd')}_{item.get('ft_ccld_qty')}_{item.get('ft_ccld_unpr3')}"
                        if unique_key not in seen_keys:
                            seen_keys.add(unique_key)
                            valid_execs.append(item)
                        
                tr_cont = res.headers.get('tr_cont', '')
                fk200 = resp_json.get('ctx_area_fk200', '').strip()
                nk200 = resp_json.get('ctx_area_nk200', '').strip()
                
                if tr_cont in ['M', 'F'] and nk200:
                    time.sleep(0.3) 
                    continue
                else: break 
            else:
                error_msg = resp_json.get('msg1') if resp_json else "응답 없음"
                print(f"❌ [{ticker} 체결내역 오류] {error_msg}")
                break
        return valid_execs

    def get_genesis_ledger(self, ticker, limit_date_str=None):
        _, holdings = self.get_account_balance()
        if holdings is None: return None, 0, 0.0
            
        ticker_info = holdings.get(ticker, {'qty': 0, 'avg': 0.0})
        curr_qty = int(ticker_info.get('qty', 0))
        final_qty = curr_qty
        final_avg = float(ticker_info.get('avg', 0.0))
        
        if curr_qty == 0: return [], 0, 0.0
            
        ledger_records = []
        est = pytz.timezone('US/Eastern')
        target_date = datetime.datetime.now(est)
        genesis_reached = False
        loop_counter = 0 
        
        while curr_qty > 0 and not genesis_reached and loop_counter < 365:
            loop_counter += 1
            date_str = target_date.strftime('%Y%m%d')
            
            if limit_date_str and date_str < limit_date_str:
                break 
                
            execs = self.get_execution_history(ticker, date_str, date_str)
            
            if execs:
                execs.sort(key=lambda x: x.get('ord_tmd', '000000'), reverse=True)
                for ex in execs:
                    side_cd = ex.get('sll_buy_dvsn_cd')
                    exec_qty = int(float(ex.get('ft_ccld_qty', '0')))
                    exec_price = float(ex.get('ft_ccld_unpr3', '0'))
                    
                    record_qty = exec_qty
                    
                    if side_cd == "02": 
                        if curr_qty <= exec_qty: 
                            record_qty = curr_qty 
                            curr_qty = 0
                            genesis_reached = True
                        else:
                            curr_qty -= exec_qty
                    else: 
                        curr_qty += exec_qty
                    
                    ledger_records.append({
                        'date': f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}",
                        'side': "BUY" if side_cd == "02" else "SELL",
                        'qty': record_qty,
                        'price': exec_price
                    })
                    
                    if genesis_reached:
                        break
                        
            target_date -= datetime.timedelta(days=1)
            time.sleep(0.1) 
                
        ledger_records.reverse()
        return ledger_records, final_qty, final_avg

    def get_recent_stock_split(self, ticker, last_date_str):
        try:
            stock = yf.Ticker(ticker)
            splits = stock.splits
            if splits is not None and not splits.empty:
                
                if last_date_str == "":
                    est = pytz.timezone('US/Eastern')
                    seven_days_ago = datetime.datetime.now(est) - datetime.timedelta(days=7)
                    safe_last_date = seven_days_ago.strftime('%Y-%m-%d')
                else:
                    safe_last_date = last_date_str
                    
                for split_date_dt, ratio in splits.items():
                    split_date = split_date_dt.strftime('%Y-%m-%d')
                    if split_date > safe_last_date:
                        return float(ratio), split_date
        except Exception as e:
            print(f"⚠️ [야후 파이낸스] 액면분할 조회 에러: {e}")
        return 0.0, ""

    def get_dynamic_sniper_target(self, index_ticker, weight=1.0):
        try:
            df = yf.download(index_ticker, period='1mo', interval='5m', prepost=True, progress=False)
            if df.empty: 
                return None
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
                
            df.index = df.index.tz_convert('America/New_York')
            df = df.between_time('04:00', '16:00')
            
            daily_data = []
            for date, group in df.groupby(df.index.date):
                if group.empty: continue
                daily_data.append({
                    'Date': pd.to_datetime(date),
                    'High': group['High'].max(),
                    'Low': group['Low'].min(),
                    'Close': group['Close'].iloc[-1]
                })
            daily_df = pd.DataFrame(daily_data).set_index('Date')
            
            est = pytz.timezone('America/New_York')
            now_est = datetime.datetime.now(est)
            today_date = now_est.date()
            
            if now_est.hour < 16:
                daily_df = daily_df[daily_df.index.date < today_date]
            else:
                daily_df = daily_df[daily_df.index.date <= today_date]
                
            if len(daily_df) < 15: 
                return None 
                
            prev_c = daily_df['Close'].shift(1)
            tr = pd.concat([
                daily_df['High'] - daily_df['Low'],
                abs(daily_df['High'] - prev_c),
                abs(daily_df['Low'] - prev_c)
            ], axis=1).max(axis=1)
            
            atr_5d = tr.rolling(window=5).mean()
            atr_14d = tr.rolling(window=14).mean()
            
            last_atr_5 = atr_5d.iloc[-1]
            last_atr_14 = atr_14d.iloc[-1]
            last_close = daily_df['Close'].iloc[-1]
            
            exp_5d = (last_atr_5 / last_close) * 100 * 3
            exp_14d = (last_atr_14 / last_close) * 100 * 3
            
            hybrid = max(exp_5d, exp_14d * 0.8)
            final_target = hybrid * weight
            
            return round(final_target, 2)
            
        except Exception as e:
            print(f"⚠️ [Broker] 동적 스나이퍼 타점 계산 실패 ({index_ticker}): {e}")
            return None

    def get_ticker_fast_data(self, ticker):
        """🚀 [V23.3] 초고속 야후 통합 수집기 (현재가/전일비/MA5/고저가 일괄 획득)"""
        # ⚡ [V24] 클래스 레벨 공유 캐시 확인 (모의/실전 가격 통일 및 API 부하 감소)
        now = time.time()
        if ticker in KoreaInvestmentBroker._price_cache:
            ts, data = KoreaInvestmentBroker._price_cache[ticker]
            if now - ts < 5 and "ma_5day" in data: # 풀 데이터가 있을 때만 캐시 사용
                return data

        try:
            stock = yf.Ticker(ticker)
            # 1. 일봉 데이터 (5일 이평선용) - 이게 가장 빠름
            daily_hist = stock.history(period="10d")
            ma_5day = float(daily_hist['Close'][-5:].mean()) if len(daily_hist) >= 5 else 0.0
            
            # 2. 오늘 분봉 데이터 (현재가, 고가, 저가용)
            hist = stock.history(period="1d", interval="1m", prepost=True)
            info = stock.fast_info
            
            # [V23.3 정밀 교정] 장마감(또는 주말) 시 hist가 비어있을 확률이 매우 높음
            curr_p = float(hist['Close'].iloc[-1]) if not hist.empty else float(info.get('last_price', 0.0))
            if curr_p == 0:
                curr_p = float(info.get('previous_close', 0.0))
            
            day_high = float(hist['High'].max()) if not hist.empty else float(info.get('day_high', 0.0))
            day_low = float(hist['Low'].min()) if not hist.empty else float(info.get('day_low', 0.0))
            prev_close = float(info.get('previous_close', 0.0))
            
            # 최종 방어: 여전히 0이라면 이전 종가(ma_5day 근사값 등)라도 활용
            if curr_p <= 0: curr_p = prev_close
            if day_high <= 0: day_high = curr_p
            if day_low <= 0: day_low = curr_p

            result = {
                "current_price": curr_p,
                "prev_close": prev_close,
                "ma_5day": ma_5day,
                "day_high": day_high,
                "day_low": day_low
            }
            
            # ⚡ [V24] 공유 캐시 저장
            KoreaInvestmentBroker._price_cache[ticker] = (now, result)
            return result
        except Exception as e:
            print(f"🚨 [Yahoo-Fast] {ticker} 고속 수집 실패 (한투 우회 시도): {e}")
            # 폴백: 한투 API로 하나씩 가져오기 (안정성 유지)
            p = self.get_current_price(ticker)
            c = self.get_previous_close(ticker)
            m = self.get_5day_ma(ticker)
            h, l = self.get_day_high_low(ticker)
            
            # 한투 폴백에서도 0 방어
            if p <= 0: p = c
            return {
                "current_price": p, "prev_close": c, "ma_5day": m,
                "day_high": h if h > 0 else p, "day_low": l if l > 0 else p
            }

    def get_day_high_low(self, ticker):
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d", interval="1m", prepost=True)
            if not hist.empty:
                day_high = float(hist['High'].max())
                day_low = float(hist['Low'].min())
                return day_high, day_low
            else:
                return float(stock.fast_info.get('dayHigh', 0.0)), float(stock.fast_info.get('dayLow', 0.0))
        except Exception as e:
            print(f"⚠️ [야후 파이낸스] 고가/저가 에러, 한투 API 우회 가동: {e}")

        try:
            excg_cd = self._get_exchange_code(ticker, target_api="PRICE")
            params = {"AUTH": "", "EXCD": excg_cd, "SYMB": ticker}
            res = self._call_api("HHDFS76200200", "/uapi/overseas-price/v1/quotations/price", "GET", params=params)
            if res.get('rt_cd') == '0':
                out = res.get('output', {})
                return float(out.get('high', 0.0)), float(out.get('low', 0.0))
        except Exception as e:
            print(f"❌ [한투 API] 고가/저가 우회 조회 실패: {e}")
            
        return 0.0, 0.0
