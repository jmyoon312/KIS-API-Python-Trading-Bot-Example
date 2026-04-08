# ==========================================================
# [main.py]
# ⚠️ 이 주석 및 파일명 표기는 절대 지우지 마세요.
# ==========================================================
import os
import logging
import datetime
import pytz
import time
import math
import asyncio
import glob
import pandas_market_calendars as mcal
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from dotenv import load_dotenv

from config import ConfigManager
from broker import KoreaInvestmentBroker
from strategy import InfiniteStrategy
from telegram_bot import TelegramController
import signal
import atexit
import threading
import uvicorn
from web_server import app as web_app
import sys
import json

if not os.path.exists('data'):
    os.makedirs('data')
if not os.path.exists('logs'):
    os.makedirs('logs')

load_dotenv() 

# [V23.1] 전역 TELEGRAM_TOKEN 체크 제거 (엔진 내부에서 개별 체크)
try:
    ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID")) if os.getenv("ADMIN_CHAT_ID") else None
except ValueError:
    ADMIN_CHAT_ID = None

import logging.handlers

log_filename = f"logs/bot_app.log" # 고정된 파일명으로 변경 (로테이션용)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO,
    handlers=[
        logging.handlers.TimedRotatingFileHandler(
            log_filename, when="midnight", interval=1, backupCount=7, encoding='utf-8'
        ),
        logging.StreamHandler()
    ]
)

def is_dst_active():
    """
    🌞 [Universal] 미국 동부 표준시 서머타임 판별 (V24 Robust)
    - pytz 라이브러리의 dst() 정보를 우선적으로 신뢰하며, 
    - 오류 발생 시 3월~11월을 서머타임으로 간주하는 Fallback 로직을 유지합니다.
    """
    try:
        est = pytz.timezone('America/New_York')
        now = datetime.datetime.now(est)
        # pytz의 dst()가 timedelta(0)이 아니면 서머타임이 적용 중인 상태임
        return now.dst() != datetime.timedelta(0)
    except Exception as e:
        # 환경적 요인으로 pytz 오류 시 월 기반 Fallback (3월~11월)
        m = datetime.datetime.now().month
        return 3 <= m <= 11

def get_target_hour():
    """
    🇺🇸 미국 본장 개장 시간 및 시즌 정보 반환 (KST 기준)
    - 22:30(여름) / 23:30(겨울)
    - 리턴: (target_hour, season_msg, is_summer)
    """
    is_summer = is_dst_active()
    # ⚠️ 중요: 프론트엔드 오판 방지를 위해 겨울철 메시지에서 '서머' 단어를 제거함 (원본 저장소 방식 준수)
    msg = "🌞 서머타임(Summer)" if is_summer else "❄️ 겨울철(Winter)"
    target_hr = 22 if is_summer else 23
    return target_hr, msg, is_summer

# 🌅 [V23.1 Dual-Core] 거래 엔진 캡슐화
class TradingEngine:
    def __init__(self, mode_name, app_key, app_secret, cano, acnt_prdt_cd, telegram_token, admin_chat_id):
        self.mode_name = mode_name.upper()
        self.is_real = (self.mode_name == "REAL")
        self.cfg = ConfigManager(is_real=self.is_real)
        if admin_chat_id: self.cfg.set_chat_id(admin_chat_id)
        
        self.broker = KoreaInvestmentBroker(self.cfg, app_key, app_secret, cano, acnt_prdt_cd, is_real=self.is_real)
        self.strategy = InfiniteStrategy(self.cfg)
        self.tx_lock = asyncio.Lock()
        
        # 텔레그램 컨트롤러 초기화 (단일 엔진 전용)
        self.bot_controller = TelegramController(self.cfg, self.broker, self.strategy, self.mode_name, self.tx_lock)
        
        # 텔레그램 애플리케이션 빌드 (타임아웃 강화)
        self.app = Application.builder().token(telegram_token).connect_timeout(30.0).read_timeout(30.0).build()
        
        # [V24] 백그라운드 발송을 위해 봇 객체 주입
        self.bot_controller.set_bot(self.app.bot)
        
        self._setup_handlers()
        self._setup_jobs()

    def _setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.bot_controller.cmd_start))
        self.app.add_handler(CommandHandler("sync", self.bot_controller.cmd_sync))
        self.app.add_handler(CommandHandler("record", self.bot_controller.cmd_record))
        self.app.add_handler(CommandHandler("history", self.bot_controller.cmd_history))
        self.app.add_handler(CommandHandler("mode", self.bot_controller.cmd_mode))
        self.app.add_handler(CommandHandler("reset", self.bot_controller.cmd_reset))
        self.app.add_handler(CommandHandler("seed", self.bot_controller.cmd_seed))
        self.app.add_handler(CommandHandler("ticker", self.bot_controller.cmd_ticker))
        self.app.add_handler(CommandHandler("settlement", self.bot_controller.cmd_settlement))
        self.app.add_handler(CommandHandler("version", self.bot_controller.cmd_version))
        self.app.add_handler(CommandHandler("v17", self.bot_controller.cmd_v17))
        self.app.add_handler(CommandHandler("v4", self.bot_controller.cmd_v4))
        self.app.add_handler(CallbackQueryHandler(self.bot_controller.handle_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.bot_controller.handle_message))

    def _setup_jobs(self):
        jq = self.app.job_queue
        if not self.cfg.get_chat_id(): return
        
        kst = pytz.timezone('Asia/Seoul')
        app_data = {
            'cfg': self.cfg, 'broker': self.broker, 'strategy': self.strategy, 
            'bot': self.bot_controller, 'tx_lock': self.tx_lock, 'mode': self.mode_name
        }
        
        # 1. 토큰 갱신
        for tt in [datetime.time(7,0,tzinfo=kst), datetime.time(11,0,tzinfo=kst), datetime.time(16,30,tzinfo=kst), datetime.time(22,0,tzinfo=kst)]:
            jq.run_daily(scheduled_token_check, time=tt, days=tuple(range(7)), chat_id=self.cfg.get_chat_id(), data=app_data)
        
        # 2. 자동 동기화
        sync_time = datetime.time(8,30,tzinfo=kst) if is_dst_active() else datetime.time(9,30,tzinfo=kst)
        jq.run_daily(scheduled_auto_sync_summer if is_dst_active() else scheduled_auto_sync_winter, 
                    time=sync_time, days=tuple(range(7)), chat_id=self.cfg.get_chat_id(), data=app_data)
        
        # 3. 정적 스케줄링 (정규장 초기화 및 매매 시작)
        target_hour, _, _ = get_target_hour()
        jq.run_daily(scheduled_force_reset, time=datetime.time(target_hour, 0, tzinfo=kst), days=(0,1,2,3,4), chat_id=self.cfg.get_chat_id(), data=app_data)
        jq.run_daily(scheduled_regular_trade, time=datetime.time(target_hour, 30, tzinfo=kst), days=(0,1,2,3,4), chat_id=self.cfg.get_chat_id(), data=app_data)

        # 🚀 [V23.1] 모의투자 전용 LOC 지연 실행 스케줄러 (04:55 ET)
        if not self.is_real:
            # 서머타임: 03:55 KST, 겨울철: 04:55 KST
            mock_loc_h = 3 if is_dst_active() else 4
            jq.run_daily(scheduled_mock_loc_execution, time=datetime.time(mock_loc_h, 55, tzinfo=kst), days=(0,1,2,3,4,5), chat_id=self.cfg.get_chat_id(), data=app_data)

        # 4. 감시 루프
        jq.run_repeating(scheduled_premarket_monitor, interval=60, chat_id=self.cfg.get_chat_id(), data=app_data)
        jq.run_repeating(scheduled_sniper_monitor, interval=60, chat_id=self.cfg.get_chat_id(), data=app_data)
        
        # 💓 [V28-Unified] 모듈 통합 및 비동기 큐 도입으로 하트비트 주기를 3초로 조정 (안정성 극대화)
        jq.run_repeating(scheduled_heartbeat, interval=3, chat_id=self.cfg.get_chat_id(), data=app_data)
        # 정기 싱크는 10초를 유지하여 API 부하 분산 (웹 트리거 시에는 즉시 실행됨)
        jq.run_repeating(scheduled_live_sync, interval=10, chat_id=self.cfg.get_chat_id(), data=app_data)
        
        # 5. 자정 관리 및 분석 (최종 확정 고정 스냅샷 포함)
        jq.run_daily(scheduled_self_cleaning, time=datetime.time(6, 0, tzinfo=kst), days=tuple(range(7)), chat_id=self.cfg.get_chat_id(), data=app_data)
        
        # 🚀 [V24] 애프터마켓까지 종료된 뉴욕 20:05분(한국 오전 9/10시)에 최종 정산 박제
        snapshot_time = datetime.time(9, 5, tzinfo=kst) if is_dst_active() else datetime.time(10, 5, tzinfo=kst)
        jq.run_daily(scheduled_analytics_snapshot, time=snapshot_time, days=tuple(range(7)), chat_id=self.cfg.get_chat_id(), data=app_data)

    async def start(self):
        logging.info(f"🚀 [{self.mode_name}] 엔진 가동 시작...")
        
        # 🛡️ [V29.8] 텔레그램 초기화 타임아웃을 대비한 재시도 래퍼
        for attempt in range(3):
            try:
                await self.app.initialize()
                break
            except Exception as e:
                logging.warning(f"⚠️ [{self.mode_name}] 텔레그램 통신 초기화 실패 (시도 {attempt+1}/3): {str(e)[:50]}")
                if attempt == 2:
                    logging.error("🚨 텔레그램 통신 불가. 엔진 가동을 중단하거나 타임아웃을 연장하세요.")
                await asyncio.sleep(2)
        
        # 🧪 [V23.1] 엔진 기동 직후 즉각적인 데이터 동기화 수행
        # 🚨 [V26.4 Fix] type('obj',...)은 클래스를 생성하므로 인스턴스 속성 접근 시 에러 발생.
        # 이를 보완하기 위해 명시적인 객체 구조를 생성합니다.
        class MockBot:
            async def send_message(self, *args, **kwargs): pass
        
        class MockContext:
            def __init__(self, data, bot):
                self.bot = bot
                class MockJob:
                    def __init__(self, d): self.data = d
                self.job = MockJob(data)

        app_data = {
            'cfg': self.cfg, 'broker': self.broker, 'strategy': self.strategy, 
            'bot': self.bot_controller, 'tx_lock': self.tx_lock, 'mode': self.mode_name
        }
        mock_ctx = MockContext(app_data, MockBot())
        
        await scheduled_heartbeat(mock_ctx)
        await scheduled_live_sync(mock_ctx)
        
        # 🤖 [V23.1] 텔레그램 봇 폴링 시작 (수동 방식 - 비동기 루프 지원)
        # ⚠️ Application.run_polling()은 내부적으로 루프를 자동 시작하므로, 이미 가동 중인 루프에서는 
        # initialize() -> start() -> start_polling()의 점진적 시퀀스를 충실히 따라야 합니다.
        try:
            await self.app.initialize()
            await self.app.start()
            if self.app.updater:
                await self.app.updater.start_polling(drop_pending_updates=True)
            # 🚀 [V33 Unified] 엔진 가동 알림
            self.cfg.log_event("SCHEDULE", "INIT", "SUCCESS", f"[{self.mode_name}] 엔진 가동", details="텔레그램 봇(수동 폴링) 및 스케줄러 활성화 완료")
        except Exception as e:
            logging.error(f"🚨 [{self.mode_name}] 텔레그램 봇 가동 실패: {e}")
            self.cfg.log_event("SCHEDULE", "INIT", "ERROR", f"[{self.mode_name}] 봇 기동 실패", details=str(e))
        
    async def stop(self):
        logging.info(f"🛑 [{self.mode_name}] 엔진 정지 중...")
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()

STATUS_TRACKER = {
    "REAL": {"idle": {"status": "pending", "time": ""}, "sync": {"status": "pending", "time": ""}, "pre": {"status": "pending", "time": ""}, "reg": {"status": "pending", "time": ""}, "after": {"status": "pending", "time": ""}},
    "MOCK": {"idle": {"status": "pending", "time": ""}, "sync": {"status": "pending", "time": ""}, "pre": {"status": "pending", "time": ""}, "reg": {"status": "pending", "time": ""}, "after": {"status": "pending", "time": ""}}
}

def update_task_status(mode, phase, status):
    global STATUS_TRACKER
    STATUS_TRACKER[mode][phase] = {
        "status": status,
        "time": datetime.datetime.now().strftime("%H:%M")
    }

def get_budget_allocation(cash, holdings, tickers, cfg):
    sorted_tickers = sorted(tickers, key=lambda x: 0 if x == "SOXL" else (1 if x == "TQQQ" else 2))
    allocated = {}
    force_turbo_off = False
    rem_cash = cash
    
    # 🎯 [V25] 글로벌 전술 설정 로드
    tactics = cfg.get_global_tactics()
    use_shield = tactics.get("shield", False)
    
    for tx in sorted_tickers:
        h = holdings.get(tx, {'qty': 0, 'avg': 0}) if holdings else {'qty': 0, 'avg': 0}
        qty = int(h['qty'])
        avg_price = float(h['avg'])
        
        t_val, _ = cfg.get_absolute_t_val(tx, qty, avg_price)
        split = cfg.get_split_count(tx)
        
        # 🛡️ [V25] 전술 제어: 쉴드(Shield) 활성화 여부에 따른 동적 분할 적용
        if use_shield:
            if t_val < (split * 0.5): current_split = split
            elif t_val < (split * 0.75): current_split = math.floor(split * 1.5)
            elif t_val < (split * 0.9): current_split = math.floor(split * 2.0)
            else: current_split = math.floor(split * 2.5)
        else:
            current_split = split
        
        # 🎯 [V26.2] 예산 할당: 전체 현금이 아닌 해당 종목의 남은 가용 예산만 할당
        portion = cfg.get_seed(tx) / current_split if current_split > 0 else 0
        portions_needed = max(1, current_split - t_val)
        ticker_budget = min(rem_cash, portion * portions_needed)
            
        if rem_cash >= portion:
            allocated[tx] = ticker_budget
            rem_cash -= portion
        else: 
            allocated[tx] = 0
            force_turbo_off = True 
                
    return sorted_tickers, allocated, force_turbo_off

def get_actual_execution_price(execs, target_qty, side_cd):
    if not execs: return 0.0
    
    execs.sort(key=lambda x: x.get('ord_tmd', '000000'), reverse=True)
    matched_qty = 0
    total_amt = 0.0
    for ex in execs:
        if ex.get('sll_buy_dvsn_cd') == side_cd: 
            eqty = int(float(ex.get('ft_ccld_qty', '0')))
            eprice = float(ex.get('ft_ccld_unpr3', '0'))
            if matched_qty + eqty <= target_qty:
                total_amt += eqty * eprice
                matched_qty += eqty
            elif matched_qty < target_qty:
                rem = target_qty - matched_qty
                total_amt += rem * eprice
                matched_qty += rem
            
            if matched_qty >= target_qty:
                break
    
    if matched_qty > 0:
        return math.floor((total_amt / matched_qty) * 100) / 100.0
    return 0.0

def perform_self_cleaning():
    try:
        now = time.time()
        seven_days = 7 * 24 * 3600
        one_day = 24 * 3600
        
        for f in glob.glob("logs/*.log"):
            if os.path.isfile(f) and os.stat(f).st_mtime < now - seven_days:
                try: os.remove(f)
                except: pass
                
        for f in glob.glob("data/*.bak_*"):
            if os.path.isfile(f) and os.stat(f).st_mtime < now - seven_days:
                try: os.remove(f)
                except: pass
                
        for directory in ["data", "logs"]:
            for f in glob.glob(f"{directory}/tmp*"):
                if os.path.isfile(f) and os.stat(f).st_mtime < now - one_day:
                    try: os.remove(f)
                    except: pass
    except Exception as e:
        logging.error(f"🧹 자정(Self-Cleaning) 작업 중 오류 발생: {e}")

async def scheduled_self_cleaning(context):
    mode = context.job.data['mode']
    update_task_status(mode, "idle", "running")
    await asyncio.to_thread(perform_self_cleaning)
    update_task_status(mode, "idle", "done")
    logging.info("🧹 [시스템 자정 작업 완료] 7일 초과 로그/백업 및 24시간 초과 임시 파일 소각 완료")

async def scheduled_token_check(context):
    context.job.data['broker']._get_access_token(force=True)

async def scheduled_force_reset(context):
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.datetime.now(kst)
    target_hour, _, _ = get_target_hour()
    
    # 🚨 [V21.4 핫픽스] 0.001초 미세 오차(Jitter) 방어선 구축 (±2분 관용 타임)
    now_minutes = now.hour * 60 + now.minute
    target_minutes = target_hour * 60
    
    if abs(now_minutes - target_minutes) > 2 and abs(now_minutes - target_minutes) < (24*60 - 2):
        return
        
    if context.job.data['cfg'].is_market_open() != "OPEN":
        await context.bot.send_message(chat_id=context.job.chat_id, text="⛔ <b>오늘은 미국 증시 휴장일입니다. 시스템 초기화 및 통제권을 건너뜁니다.</b>", parse_mode='HTML')
        return
    
    try:
        app_data = context.job.data
        mode = app_data['mode']
        update_task_status(mode, "pre", "running")
        
        # 🧹 [V26.5] 일일 사이클 시작 시 이전 기록 초기화
        app_data['cfg'].clear_events()
        app_data['cfg'].reset_locks()
        
        # 🧹 [V26.9] 상황실 주문 및 체결 내역 초기화 (새로운 거래일 시작)
        try:
            live_file = app_data['cfg']._get_file_path("LIVE_STATUS")
            if os.path.exists(live_file):
                with open(live_file, 'r', encoding='utf-8') as f:
                    live_data = json.load(f)
                if "tickers" in live_data:
                    for t in live_data["tickers"]:
                        live_data["tickers"][t]["slots"] = {}
                with open(live_file, 'w', encoding='utf-8') as f:
                    json.dump(live_data, f, ensure_ascii=False, indent=2)
                logging.info(f"✨ [{mode}] 상황실 주문 및 매매 내역 초기화 완료")
        except Exception as reset_e:
            logging.error(f"⚠️ 상황실 초기화 중 오류: {reset_e}")
        
        for t in app_data['cfg'].get_active_tickers():
            app_data['cfg'].increment_reverse_day(t)
            
        update_task_status(mode, "pre", "done")
        # 🚀 [V33 Unified] 시스템 초기화 알림
        app_data['cfg'].log_event("SCHEDULE", "INIT", "SUCCESS", f"[{mode}] 시스템 초기화 완료", details=f"[{target_hour}:00] 매매 잠금 해제 및 엔진 기어 초기화 완료")
        await context.bot.send_message(chat_id=context.job.chat_id, text=f"🔓 <b>[{mode}] [{target_hour}:00] 시스템 초기화 완료 (매매 잠금 해제 & 스나이퍼 장전 & 리버스 카운트 누적)</b>", parse_mode='HTML')
    except Exception as e:
        update_task_status(app_data['mode'], "pre", "error")
        app_data['cfg'].log_event("SCHEDULE", "ERROR", "FAILURE", f"시스템 초기화 실패", details=str(e))
        await context.bot.send_message(chat_id=context.job.chat_id, text=f"🚨 <b>시스템 초기화 중 에러 발생:</b> {e}", parse_mode='HTML')

async def scheduled_premarket_monitor(context):
    if context.job.data['cfg'].is_market_open() != "OPEN": return
    app_data = context.job.data
    
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.datetime.now(kst)
    target_hour, _, _ = get_target_hour()
    
    # 🚨 V22.2 패치: 타겟 시간(22시 또는 23시) 5시간 전(프리마켓 시작점)부터 정규장 오픈 직전까지 전체 모니터링
    start_hour = target_hour - 5
    if not (start_hour <= now.hour <= target_hour):
        return
    # 정규장 오픈 시간(target_hour:30) 이후엔 동작 안함
    if now.hour == target_hour and now.minute >= 30:
        return

    cfg, broker, strategy, tx_lock = app_data['cfg'], app_data['broker'], app_data['strategy'], app_data['tx_lock']

    # 🚨 [V21.4 핫픽스] 비동기 병목(Deadlock) 타임아웃 족쇄 
    async def _do_premarket():
        async with tx_lock:
            # ⚡ [V27] 블로킹 호출을 비동기로 안전하게 수행
            res_balance = await asyncio.to_thread(broker.get_account_balance)
            if not res_balance or res_balance[1] is None: return
            cash, holdings = res_balance

            for t in cfg.get_active_tickers():
                h = holdings.get(t, {'qty': 0, 'avg': 0})
                
                curr_p = await asyncio.to_thread(broker.get_current_price, t)
                prev_c = await asyncio.to_thread(broker.get_previous_close, t)
                if curr_p <= 0 or prev_c <= 0: continue
                
                gap_pct = (curr_p - prev_c) / prev_c * 100
                # 🛡️ [V33 Deduplication] 가격 체크 로그는 log_event 내부 Throttling에 의해 15분에 한 번만 기록됨
                cfg.log_event("SCHEDULE", "PRE", "SUCCESS", f"[{t}] 프리마켓 가격 체크", details=f"현재가: ${curr_p}, 전일종가: ${prev_c} (GAP: {gap_pct:+.2f}%)")
                
                # 1. 갭상승 익절 체크 (+3% 이상 갭업 & 목표 도달 여부) (보유수량 있을때만)
                if int(h['qty']) > 0 and gap_pct >= 3.0:
                    plan = strategy.get_plan(t, curr_p, float(h['avg']), int(h['qty']), prev_c, market_type="PRE_CHECK")
                    if plan['orders']:
                        msg = f"🌅 <b>[{t}] 대박! 프리마켓 +3% 이상 갭업(+{gap_pct:.2f}%) 및 목표 달성 🎉</b>\n⚡ 본장 하락 전 차익실현을 위해 전량 프리마켓 조기 익절을 실행합니다!"
                        await asyncio.to_thread(broker.cancel_all_orders_safe, t)
                        all_success = True
                        for o in plan['orders']:
                            # PRE 지정가 주문(32) 활용
                            res = await asyncio.to_thread(broker.send_order, t, o['side'], o['qty'], o['price'], "PRE")
                            err_msg = res.get('msg1')
                            is_success = res.get('rt_cd') == '0'
                            if not is_success: all_success = False
                            msg += f"\n└ {o['desc']} {o['side']} {o['qty']}주: {'✅' if is_success else f'❌({err_msg})'}"
                            await asyncio.sleep(0.2) 
                        await context.bot.send_message(chat_id=context.job.chat_id, text=msg, parse_mode='HTML')
                        cfg.log_event("SCHEDULE", "SUCCESS" if all_success else "ERROR", f"[{t}] 조기 익절 실행", details=msg.replace('<b>','').replace('</b>',''))
                        
                        if all_success:
                            # 텔레그램 봇의 process_sync를 호출하여 즉각 리밸런싱을 유도할 수 있도록 안내
                            await context.bot.send_message(chat_id=context.job.chat_id, text=f"🔔 <b>[{t}] 전량 익절 완료! 텔레그램 /sync 명령으로 즉각 자동 리밸런싱을 수행해주세요.</b>", parse_mode='HTML')

                # 2. 갭하락 스나이퍼 체크 (-3% 이하 갭락 & 당일 아직 미발동)
                if gap_pct <= -3.0 and not cfg.check_lock(t, "PRE_SNIPER"):
                    split = cfg.get_split_count(t)
                    t_val, _ = cfg.get_absolute_t_val(t, int(h['qty']), float(h['avg']))
                    base_budget = cfg.get_seed(t) / split if split > 0 else 0
                    
                    if t_val < 35: mult = 1.5
                    elif t_val < 50: mult = 1.2
                    else: mult = 1.0
                    
                    sniper_budget = base_budget * mult
                    
                    # [추가] 🚨 잔여 현금 20% 마지노선 락다운 검증
                    total_seed = cfg.get_seed(t)
                    if cash < (total_seed * 0.20):
                        # 현금 고갈 방지를 위해 얼리버드 줍줍(액티브) 강제 중단
                        logging.warning(f"🚨 [{t}] 잔여 현금 20% 미만! 프리마켓 얼리버드 매수 강제 셧다운 (정규장 1배수 생존 모드 가동)")
                        continue
                    
                    if cash >= sniper_budget:
                        buy_qty = math.floor(sniper_budget / curr_p)
                        if buy_qty > 0:
                            msg = f"🦅 <b>[{t}] V22.2 프리마켓 얼리버드 스나이퍼 발동!</b>\n"
                            msg += f"📉 갭하락({gap_pct:.2f}%) 감지. 정규장 초반 반등 통계에 기반하여 본장 오픈 전 투매 구간에서 즉시 선점합니다!\n"
                            
                            res = await asyncio.to_thread(broker.send_order, t, "BUY", buy_qty, curr_p, "PRE")
                            if res.get('rt_cd') != '0':
                                msg += f"❌ 매수 실패: {res.get('msg1')}"
                            await context.bot.send_message(chat_id=context.job.chat_id, text=msg, parse_mode='HTML')

    try:
        update_task_status(app_data['mode'], "pre", "running") # 프리마켓 감시도 광의의 개장 준비(Pre)로 취급
        await asyncio.wait_for(_do_premarket(), timeout=45.0)
        update_task_status(app_data['mode'], "pre", "done")
    except asyncio.TimeoutError:
        update_task_status(app_data['mode'], "pre", "error")
        logging.warning("⚠️ 프리마켓 감시 중 통신 지연으로 1회 건너뜀 (Deadlock 방어)")
    except Exception as e:
        update_task_status(app_data['mode'], "pre", "error")
        cfg.log_event("SCHEDULE", "PRE", "ERROR", f"프리마켓 스케줄 장애", details=str(e)[:50])
        logging.error(f"🚨 프리마켓 모니터 에러: {e}")
    finally:
        pass

async def fast_ui_sync(app_data):
    """
    ⚡ [V24 Fast-Sync] 시세/잔고 조회 없이 UI(주문계획 명칭 등)만 즉시 갱신
    - 전략 버전 변경 시 사용자가 1초 내에 변화를 체감하도록 설계됨
    """
    cfg, strategy = app_data['cfg'], app_data['strategy']
    live_file = cfg._get_file_path("LIVE_STATUS")
    
    if not os.path.exists(live_file): return

    try:
        with open(live_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 기존 데이터를 바탕으로 전략만 재계산
        for t, info in data['tickers'].items():
            # 기존에 저장된 가격과 정보를 그대로 사용 (API 호출 0회)
            curr_p = info['current_price']
            avg_p = info['avg_price']
            qty = info['qty']
            prev_c = info.get('prev_close', curr_p)
            
            # 전략 지시서 재발급 (명칭 업데이트 목적)
            plan = strategy.get_plan(t, curr_p, avg_p, qty, prev_c)
            
            info['version'] = cfg.get_version(t)
            info['orders'] = plan['orders']
            info['slots'] = plan['slots']
            info['process_status'] = plan['process_status']
        
        # 즉시 파일 쓰기 (atomic하지 않아도 UI 로딩이므로 속도 우선)
        with open(live_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        logging.info(f"⚡ [Web-Trigger] Fast UI Sync completed for {app_data['mode']}")
    except Exception as e:
        logging.error(f"❌ [FastSync] Error: {e}")

async def scheduled_heartbeat(context):
    """
    💓 [V23.3] 심장박동 & 리모컨 감시 엔진
    1. 10초마다 대시보드 타임스탬프 갱신 (Data Stale 방지)
    2. 웹 대시보드에서 보낸 실시간 명령(리셋, 갱신 등) 감시 및 즉시 처리
    """
    app_data = context.job.data if hasattr(context, 'job') else context
    cfg, broker, strategy = app_data['cfg'], app_data['broker'], app_data['strategy']
    mode = app_data.get('mode', 'MOCK')
    
    try:
        # 1. 웹 트리거 감시 (잠금 해제, 강제 실행, 실시간 동기화 등)
        triggers_found = await check_web_triggers(mode, cfg, broker, strategy, cfg.get_active_tickers(), context)
        
        # 2. 만약 '실시간 동기화(Record)' 트리거가 있었다면 즉시 처리
        if triggers_found and "record" in triggers_found:
             # ⚡ [V25] 레이스 컨디션 방어: 이미 동기화 중이라면 중복 실행 방지
             if app_data.get('sync_active'):
                 logging.info(f"🔄 [{mode}] 리모컨 신호(Record) 무시: 이미 동기화가 진행 중입니다.")
             else:
                 logging.info(f"🔄 [{mode}] 리모컨 신호(Record) 감지. 즉시 전체 동기화 태스크 생성.")
                 app_data['force_live_sync'] = True
                 asyncio.create_task(scheduled_live_sync(context))
             return

        # 3. [V24 Stable] 휴면 기간에는 live_sync가 전담하여 상태를 관리하므로 심박동 중복 기록을 건너뜁니다.
        m_status = cfg.is_market_open()
        now_ny = datetime.datetime.now(pytz.timezone('America/New_York'))
        h_m = now_ny.strftime("%H:%M")
        # 장마감(20:01~03:59) 또는 주말/공휴일인 경우 대시보드 강제 갱신 차단
        is_dormancy = (h_m >= "20:01" or h_m < "04:00") or (m_status in ["WEEKEND", "HOLIDAY"])
        
        if is_dormancy:
            return

        # 4. 일반적인 심박동 (장중/활성 기간 타임스탬프만 갱신)
        # 🛡️ [V24.5] 레이스 컨디션 방어: 저장 직전에 최신 상태를 로드하여 외부(웹서버) 상태값 보존
        LIVE_FILE = cfg._get_file_path("LIVE_STATUS")
        live_data = {"tickers": {}}
        if os.path.exists(LIVE_FILE):
            try:
                with open(LIVE_FILE, 'r', encoding='utf-8') as f:
                    live_data = json.load(f)
            except: pass

        live_data["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        live_data["is_real"] = cfg.is_real
        
        cfg._save_json("LIVE_STATUS", live_data)
        
    except Exception as e:
        logging.error(f"💓 Heartbeat 에러: {e}")

async def scheduled_live_sync(context):
    """
    🔄 [V23.5 Master Sync] 통합 동기화 엔진 (Trading & Monitoring)
    """
    app_data = context.job.data if hasattr(context, 'job') else context
    cfg, broker, strategy, tx_lock = app_data['cfg'], app_data['broker'], app_data['strategy'], app_data['tx_lock']
    mode = app_data.get('mode', 'MOCK')
    
    # 🛡️ [V25] 동기화 중복 방지 락
    if app_data.get('sync_active'):
        return
    app_data['sync_active'] = True
    
    # [V25] 초기 상태값 방어구
    sync_verified = False
    price_verified = False
    balance_verified = False
    holdings = None
    
    try:
        now_ny = datetime.datetime.now(pytz.timezone('America/New_York'))
        now_ts = now_ny.strftime("%Y-%m-%d %H:%M:%S")
        h_m = now_ny.strftime("%H:%M")
        
        # 1. 시장 상태 및 시간대 판단 (뉴욕 현지 시간 기준)
        m_status = cfg.is_market_open()
        is_weekend_val = (m_status == "WEEKEND")
        is_closed_val = (m_status == "HOLIDAY")
        target_hr, season_msg, is_summer_val = get_target_hour()
        
        if "04:00" <= h_m < "09:30": status_code, status_text = "PRE", "🌅 프리마켓"
        elif "09:30" <= h_m < "16:00": status_code, status_text = "REG", "🔥 정규장"
        elif "16:00" <= h_m < "20:00": status_code, status_text = "AFTER", "🌙 애프터마켓"
        else: status_code, status_text = "CLOSED", "🌙 장마감"
    
        # ⚠️ [Hard Rule] 애프터마켓(AFTER)은 모니터링은 하되, 20:01부터는 휴면으로 진입
        is_dormancy = (status_code == "CLOSED") or (m_status in ["WEEKEND", "HOLIDAY"])
        force_live = app_data.get('force_live_sync', False)
        
        if is_weekend_val: status_text = "⛔ 주말 휴면"
        elif is_dormancy: status_text = f"💤 휴면 ({status_text})"
    
        # 🚀 [V26.5] 현재 패이즈에 따른 상태 실시간 업데이트
        if not is_weekend_val:
            kst_now = datetime.datetime.now(pytz.timezone('Asia/Seoul'))
            is_sync_window = (kst_now.hour == 9) or (kst_now.hour == 10 and kst_now.minute < 30)
            
            if is_sync_window:
                update_task_status(mode, "sync", "running")
            else:
                if STATUS_TRACKER.get(mode, {}).get("sync", {}).get("status") == "running":
                    update_task_status(mode, "sync", "done")
            
            phase_map = {"PRE": "pre", "REG": "reg", "AFTER": "after"}
            if status_code in phase_map:
                p_key = phase_map[status_code]
                current_p_status = STATUS_TRACKER.get(mode, {}).get(p_key, {}).get("status")
                if current_p_status not in ["done", "error"]:
                    update_task_status(mode, p_key, "running")
    
        # 🛡️ [V23.5 Persistence] 기존 데이터 로드
        PREV_L_FILE = cfg._get_file_path("LIVE_STATUS")
        live_data = {"tickers": {}, "cash": 0, "holdings_value": 0}
        if os.path.exists(PREV_L_FILE):
            try:
                with open(PREV_L_FILE, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    if isinstance(loaded_data, dict):
                        live_data = loaded_data
            except: pass
    
        # 🆕 [V33.6 Daily Reset] 새로운 거래일 감지 및 슬롯 초기화
        current_ny_date = now_ny.strftime("%Y-%m-%d")
        stored_ny_date = live_data.get("last_calc_date")
        
        if stored_ny_date and stored_ny_date != current_ny_date:
            logging.info(f"🆕 [Day-Reset] New Trading Day detected ({current_ny_date}). Cleaning old slots state.")
            for t, ticker_info in live_data.get("tickers", {}).items():
                # 1. 주문 슬롯 초기화 (매도 완료 등 상태 제거)
                if "slots" in ticker_info:
                    for sid in ticker_info["slots"]:
                        ticker_info["slots"][sid]["status"] = "WAITING"
                        ticker_info["slots"][sid]["result"] = ""
                # 2. 일일 잠금 해제
                ticker_info["is_locked"] = False
                
        live_data["last_calc_date"] = current_ny_date

        t_total_start = time.time()
        
        live_data.update({
            "timestamp": now_ts,
            "market_status": status_text,
            "dst_info": season_msg,
            "is_summer": is_summer_val,
            "is_real": cfg.is_real,
            "task_status": STATUS_TRACKER.get(mode, {})
        })
    
        tactics_config = cfg.get_global_tactics()
        active_tickers = cfg.get_active_tickers()
    
        for t in active_tickers:
            if t not in live_data["tickers"]:
                live_data["tickers"][t] = {"process_status": "📡 데이터 연동 중..."}
    
        try:
            results = []
            if (is_dormancy or is_weekend_val) and not force_live:
                snapshot_state = cfg.get_latest_ticker_state()
                active_tickers = cfg.get_active_tickers()
                
                total_holdings_val = 0.0
                snapshots = cfg._load_json("SNAPSHOTS", [])
                last_cash = snapshots[-1].get("cash", 0) if snapshots else 0
                
                for t in active_tickers:
                    existing_data = live_data["tickers"].get(t, {})
                    state = snapshot_state.get(t, {})
                    
                    qty = int(state.get("qty", existing_data.get("qty", 0)))
                    avg = float(state.get("avg_price", existing_data.get("avg_price", 0)))
                    
                    ledger_price = float(state.get("current_price", 0))
                    if ledger_price <= 0: ledger_price = float(existing_data.get("current_price", 0))
                    if ledger_price <= 0: ledger_price = float(state.get("prev_close", 0))
                    if ledger_price <= 0: ledger_price = avg
                    
                    prev_c = float(state.get("prev_close", 0))
                    if prev_c <= 0: prev_c = ledger_price
                    
                    t_val, _ = cfg.get_absolute_t_val(t, qty, avg)
                    split = cfg.get_split_count(t)
                    ma5 = float(state.get("ma_5day", existing_data.get("ma_5day", 0)))
                    d_low = float(state.get("day_low", ledger_price))
    
                    slots = existing_data.get("slots")
                    if not slots or not any(s.get('qty', 0) > 0 for s in slots.values()):
                        slots = state.get("slots", {})
    
                    results.append((t, {
                        "current_price": ledger_price, "qty": qty, "avg_price": avg,
                        "prev_close": prev_c,
                        "profit_pct": (ledger_price - avg) / avg * 100 if avg > 0 else 0,
                        "seed": cfg.get_active_seed(t), "ratio": cfg.get_ratio(t),
                        "version": cfg.get_version(t),
                        "t_val": t_val, "split": split,
                        "ma_5day": ma5, "day_low": d_low,
                        "process_status": status_text,
                        "is_locked": cfg.is_locked(t, status_code),
                        "slots": slots
                    }))
                    total_holdings_val += (qty * ledger_price)
                
                live_data.update({
                    "cash": last_cash if last_cash > 0 else live_data.get("cash", 0),
                    "holdings_value": total_holdings_val,
                    "is_trade_active": False
                })
                for t, data in results: live_data["tickers"][t] = data
            else:
                tickers = cfg.get_active_tickers()
                sem = asyncio.Semaphore(10)
    
                def _safe_update_ticker(t, new_fields):
                    if t not in live_data["tickers"]:
                        live_data["tickers"][t] = {"process_status": "📡 동기화 중..."}
                    live_data["tickers"][t].update(new_fields)
    
                async def _fetch_prices_only():
                    async def _get_one(t):
                        async with sem:
                            try:
                                fast_data = await asyncio.to_thread(broker.get_ticker_fast_data, t)
                                if fast_data:
                                    curr_p = fast_data['current_price']
                                    qty = live_data["tickers"].get(t, {}).get("qty", 0)
                                    avg = live_data["tickers"].get(t, {}).get("avg_price", 0)
                                    t_val, _ = cfg.get_absolute_t_val(t, qty, avg)
                                    
                                    _safe_update_ticker(t, {
                                        "current_price": curr_p,
                                        "prev_close": fast_data.get('prev_close', 0),
                                        "ma_5day": fast_data.get('ma_5day', 0),
                                        "day_high": fast_data.get('day_high', 0),
                                        "day_low": fast_data.get('day_low', 0),
                                        "t_val": t_val,
                                        "process_status": "🔥 가동중"
                                    })
                            except: pass
    
                    await asyncio.gather(*[_get_one(t) for t in tickers])
    
                async def _fetch_balance_only():
                    nonlocal holdings
                    try:
                        res_bal = await asyncio.to_thread(broker.get_account_balance)
                        # 🚀 [V29.8] Balance Guard: API 완전 실패 시 None 수신
                        if res_bal[0] is None:
                            logging.warning(f"⚠️ [{mode}] 잔고 조회 실패 (연결 지연). 기존 데이터를 보존합니다.")
                            return

                        cash, holdings_res = res_bal
                        if holdings_res is not None:
                            holdings = holdings_res
                            live_data.update({
                                "cash": cash, "holdings_value": broker.last_holdings_value,
                            })
                            for t in tickers:
                                h = holdings.get(t, {'qty': 0, 'avg': 0})
                                avg, qty = float(h['avg']), int(h['qty'])
                                curr_p = live_data["tickers"].get(t, {}).get("current_price", 0)
                                
                                _safe_update_ticker(t, {
                                    "qty": qty, "avg_price": avg,
                                    "profit_pct": (curr_p - avg) / avg * 100 if avg > 0 and curr_p > 0 else 0
                                })

        # 🚀 [V29.7] 실시간 졸업 감지 및 자동 기록 (Auto-Graduation)
                                # 🛡️ [V29.8] API 성공 시에만 졸업 판정 (방어적 설계)
                                try:
                                    ledger_qty, _, _, _ = cfg.calculate_holdings(t)
                                    if qty == 0 and ledger_qty > 0:
                                        logging.info(f"🎓 [Auto-Graduation] {t} 졸업 감지! (Broker Qty: 0, Ledger Qty: {ledger_qty})")
                                        bot_ctrl = app_data.get('bot')
                                        if bot_ctrl:
                                            asyncio.create_task(bot_ctrl.process_auto_sync(t, cfg.get_chat_id(), context, silent_ledger=True))
                                except Exception as g_e:
                                    logging.error(f"⚠️ [{t}] 졸업 감지 중 에러: {g_e}")
                    except Exception as be:
                        logging.error(f"⚠️ [{mode}] 계좌 병렬 조회 실패: {be}")
    
                t_api_start = time.time()
                await _fetch_prices_only()
                if any(data.get('current_price', 0) > 0 for data in live_data.get('tickers', {}).values()):
                    price_verified = True
                
                await _fetch_balance_only()
                if holdings is not None:
                    balance_verified = True

                # 🎯 [Bug Fix] 모든 API 호출 완료 후 자산 최종 합산 (자산 0원 오류 방지)
                calculated_hv = 0.0
                for tn, tinfo in live_data.get("tickers", {}).items():
                    qty = float(tinfo.get("qty", 0))
                    price = float(tinfo.get("current_price", 0))
                    if qty > 0 and price > 0:
                        calculated_hv += qty * price
                        # 자산 배분용 Profit PCT 보정 (가격이 늦게 뜬 경우 대비)
                        avg = tinfo.get("avg_price", 0)
                        if avg > 0:
                            live_data["tickers"][tn]["profit_pct"] = (price - avg) / avg * 100
                    
                if calculated_hv > 0:
                    live_data["holdings_value"] = round(calculated_hv, 2)
                elif broker.last_holdings_value > 0:
                    live_data["holdings_value"] = broker.last_holdings_value
                
                t_api_end = time.time()
                sync_verified = price_verified or balance_verified
    
                live_data.update({
                    "is_trade_active": status_code in ["PRE", "REG"] and not is_weekend_val
                })
    
            tickers_for_calc = list(live_data["tickers"].keys())
            available_cash_map = {t: 0 for t in tickers_for_calc}
            
            if status_code in ["PRE", "REG"] and not is_dormancy:
                try:
                    _, allocated_cash_map, _ = get_budget_allocation(live_data['cash'], holdings if holdings else {}, tickers_for_calc, cfg)
                    if allocated_cash_map: available_cash_map = allocated_cash_map
                except Exception as b_e: logging.error(f"⚠️ 예산 분배 에러: {b_e}")
    
            for t, data in live_data["tickers"].items():
                try:
                    curr_p = data.get('current_price', 0)
                    if curr_p <= 0: continue
                    qty = data.get('qty', 0)
                    avg = data.get('avg_price', 0)
                    target_cash = live_data['cash'] if is_dormancy else available_cash_map.get(t, 0)
    
                    # 🚀 [V29.8] Balance Guard: 잔고 데이터가 없는 경우(API 지연) 전략 계산 스킵
                    if holdings is None and not is_dormancy:
                        process_status = "⚠️ API 연결 지연"
                        data["process_status"] = process_status
                        continue

                    plan = strategy.get_plan(
                        t, curr_p, float(avg), int(qty), data.get('prev_close', 0), 
                        ma_5day=data.get('ma_5day', 0), day_low=data.get('day_low', 0), market_type=status_code, 
                        available_cash=target_cash, is_simulation=False, 
                        tactics_config=tactics_config
                    )
                    if not plan: continue
    
                    new_slots = plan.get("slots", {})
                    old_slots = data.get("slots", {})
                    
                    # 🛡️ [V29.8] 수량 불일치 누적 방어 (Cumulative Capping) 도입
                    # 매칭된 인덴트: 20 spaces
                    actual_qty = int(data.get('qty', 0))
                    rem_sell_qty = actual_qty
                    
                    for sid in ["slot_1", "slot_2", "slot_3", "slot_4", "slot_5"]:
                        # 1. 기존 슬롯의 FILLED 상태 및 체결 정보 복원 (데이터 동결)
                        if old_slots.get(sid, {}).get("status") == "FILLED":
                            new_slots[sid]["status"] = "FILLED"
                            new_slots[sid]["result"] = old_slots[sid].get("result", "✅체결")
                            new_slots[sid]["price"] = old_slots[sid].get("price", 0)
                            new_slots[sid]["desc"] = old_slots[sid].get("desc", new_slots[sid]["desc"]) # 🛡️ [V26.9] 체결 시점 명칭 보존
                            new_slots[sid]["qty"] = old_slots[sid].get("qty", new_slots[sid]["qty"])   # 🛡️ [V26.9] 체결 시점 수량 보존
                        else:
                            # 2. 미체결 매도 슬롯도 잔여 잔고 임계치 적용
                            if sid in ["slot_4", "slot_5"]:
                                plan_q = int(new_slots[sid].get("qty", 0))
                                allocated_q = min(rem_sell_qty, plan_q)
                                new_slots[sid]["qty"] = allocated_q
                                rem_sell_qty -= max(0, allocated_q)
                    
                    plan["slots"] = new_slots
                    # 🛡️ [V29.8] 🛠️ 중요: 슬롯 업데이트 후 주문 리스트 재동기화 (수량 불일치 최종 방어)
                    # FILLED 상태가 아닌 주문만 재구성하여 거래소로 전송
                    plan["orders"] = [o for sid, o in new_slots.items() if o.get("qty", 0) > 0 and o.get("status") != "FILLED"]
                    
                    live_data["tickers"][t].update(plan)
                    
                    is_trade_active = live_data.get("is_trade_active", False)
                    if is_trade_active and not cfg.is_locked(t, status_code):
                        orders = plan.get('orders', [])
                        if orders:
                            async with tx_lock:
                                msg = f"🚀 <b>[{t}] {status_code} 전략 주문 실행</b>\n"
                                for o in orders:
                                    # 🚀 [V25] 모의투자 LOC 에뮬레이션: 즉시 전송 대신 스테이징
                                    if not broker.is_real and o.get('type') == 'LOC':
                                        cfg.stage_mock_loc_order(t, o)
                                        msg += f"🕒 [MOCK-LOC 예약 완료] {o['desc']} {o['qty']}주\n"
                                        continue
                                        
                                    # 🛑 [MOCK-PRE 방어] 모의투자는 프리마켓(PRE) 주문을 원천 거부하므로 발송 차단 (스팸 방지)
                                    if not broker.is_real and status_code == "PRE":
                                        msg += f"⚠️ [MOCK-PRE] {o['desc']} {o['qty']}주: 모의 프리장 불가 (대기)\n"
                                        continue

                                    res = broker.send_order(t, o['side'], o['qty'], o['price'], o['type'])
                                    is_success = (res.get('rt_cd') == '0')
                                    sid = f"slot_{o.get('slot_id', 1)}"
                                    if is_success and sid in live_data["tickers"][t]["slots"]:
                                        live_data["tickers"][t]["slots"][sid]["status"] = "FILLED"
                                    msg += f"{'✅' if is_success else '❌'} {o['desc']} {o['qty']}주\n"
                                    
                                    # 🔔 [V33.1] 실시간 거래 이벤트 기록 (상황실 피드 + 이벤트 로그)
                                    trade_status = "SUCCESS" if is_success else "WARNING"
                                    trade_detail = f"{o['side']} {o['qty']}주 @ ${o['price']:.2f} ({o.get('type','LIMIT')})"
                                    # 🚀 [V33 Unified] 체결 알림 (log_event 하나로 통합 기록 및 전송)
                                    cfg.log_event("TRADE", "TRADE", trade_status, f"[{t}] {o['side']} {o['qty']}주 체결{'완료' if is_success else '실패'}", details=trade_detail)

                                cfg.set_lock(t, status_code)
                                if bot: await bot.send_message(cfg.get_chat_id(), msg, parse_mode='HTML')
                except: pass
            
            t_calc_end = time.time()
    
        except Exception as inner_e:
            logging.error(f"🚨 [{mode}] 내부 작업 루프 에러: {inner_e}")
    
        # 최종 파일 기록
        try:
            L_FILE = cfg._get_file_path("LIVE_STATUS")
            if os.path.exists(L_FILE):
                try:
                    with open(L_FILE, 'r', encoding='utf-8') as f:
                        disk_data = json.load(f)
                        if disk_data.get("last_manual_sync", {}).get("status") == "PROCESSING":
                           if sync_verified:
                               live_data["last_manual_sync"] = {"status": "SUCCESS", "msg": "동기화 완료", "timestamp": time.time()}
                           else:
                               live_data["last_manual_sync"] = {"status": "ERROR", "msg": "API 지연", "timestamp": time.time()}
                        elif "last_manual_sync" in disk_data:
                           live_data["last_manual_sync"] = disk_data["last_manual_sync"]
                except: pass
            cfg._save_json("LIVE_STATUS", live_data)
            t_save_end = time.time()
            
            # 🚀 [PERF] 지연 원인 판독용 통합 로그
            t_total = (time.time() - t_total_start)
            t_api = (t_api_end - t_api_start) if 't_api_start' in locals() else 0
            t_calc = (t_calc_end - t_api_end) if 't_calc_end' in locals() else 0
            t_save = (t_save_end - t_calc_end) if 't_save_end' in locals() else 0
            logging.info(f"💾 [PERF] {mode} Sync: Total {t_total:.2f}s [API:{t_api:.2f}s, Calc:{t_calc:.2f}s, Save:{t_save:.2f}s]")

            if app_data.get('force_live_sync'):
                app_data['force_live_sync'] = False
                # 🚀 [V28.1] 수동 갱신 시에는 큐를 우회하여 즉시 기록 (UI 즉각 반영 보장)
                cfg.log_event("SCHEDULE", "SYNC", "SUCCESS", "수동 데이터 동기화 완료")
            update_task_status(mode, "sync", "done")
        except: pass
    
    finally:
        app_data['sync_active'] = False

async def check_web_triggers(mode, cfg, broker, strategy, tickers, context):
    """🚀 [V23.3] 명령어 수신함: 웹 대시보드에서 보낸 명령 파일(.tmp)을 감시 및 처리"""
    import glob
    base_dir = cfg._get_base_dir()
    triggered = []
    
    # 1. 수동 실행 (Force Exec: 현재 사이클에서 즉시 실행 유도)
    for f_path in glob.glob(os.path.join(base_dir, "trigger_exec_*.tmp")):
        ticker = os.path.basename(f_path).replace("trigger_exec_", "").replace(".tmp", "")
        logging.info(f"🔥 [Web-Trigger] {ticker} 수동 알고리즘 강제 실행 명령 수신!")
        cfg.reset_lock_for_ticker(ticker) # 잠금 해제하여 즉시 주문 나가게 함
        try: os.remove(f_path)
        except: pass

    # 1.5. 수동 즉시 매도 (Manual Instant Sell)
    for f_path in glob.glob(os.path.join(base_dir, "trigger_sell_*_*.tmp")):
        # trigger_sell_TICKER_QTY.tmp
        parts = os.path.basename(f_path).replace(".tmp", "").split("_")
        if len(parts) >= 4:
            ticker = parts[2]
            try:
                qty = int(parts[3])
                logging.info(f"💥 [Web-Trigger] {ticker} {qty}주 수동 즉시 매도 명령 수신!")
                
                # 즉시 매도를 위해 현재 매수 1호가 조회
                bid_p = await asyncio.to_thread(broker.get_bid_price, ticker)
                if bid_p <= 0:
                    # 호가 조회 실패 시 현재가로 대체
                    bid_p = await asyncio.to_thread(broker.get_current_price, ticker)
                
                if bid_p > 0:
                    # 🛡️ [V26.8] 수동 매도 신뢰성 강화: 기존 미체결 매도 주문 강제 취소 (잔고 확보)
                    unfilled = broker.get_unfilled_orders_detail(ticker)
                    # SLL_BUY_DVSN_CD: 01=Sell, 02=Buy (정정된 기준 적용)
                    existing_sells = [o for o in unfilled if o.get('sll_buy_dvsn_cd') == '01']
                    if existing_sells:
                        logging.info(f"🔓 [Manual-Sell] {ticker} 기존 매도 주문 {len(existing_sells)}건 발견. 자동 취소 후 진행합니다.")
                        for so in existing_sells:
                            broker.cancel_order(ticker, so.get('odno'))
                            time.sleep(0.3)
                        time.sleep(0.5)

                    res = broker.send_order(ticker, "SELL", qty, bid_p, "LIMIT")
                    if res.get('rt_cd') == '0':
                        msg = f"📉 <b>[{ticker}] 수동 즉시 매도 성공</b>\n수량: {qty}주, 단가: ${bid_p:.2f}"
                        cfg.log_event("TRADE", "SUCCESS", "MANUAL_SELL", f"[{ticker}] 수동 즉시 매도 성공", details=f"{qty}주 @ ${bid_p:.2f}")
                    else:
                        msg = f"❌ <b>[{ticker}] 수동 즉시 매도 실패</b>\n사유: {res.get('msg1')}"
                        cfg.log_event("TRADE", "ERROR", "MANUAL_SELL", f"[{ticker}] 수동 즉시 매도 실패", details=res.get('msg1'))
                    
                    try: await context.bot.send_message(cfg.get_chat_id(), msg, parse_mode='HTML')
                    except: pass
            except Exception as e:
                logging.error(f"🚨 수동 매도 처리 중 오류: {e}")
        
        try: os.remove(f_path)
        except: pass

    # 2. 잠금 해제 (Reset Lock / Escrow)
    for f_path in glob.glob(os.path.join(base_dir, "trigger_reset_*.tmp")):
        ticker = os.path.basename(f_path).replace("trigger_reset_", "").replace(".tmp", "")
        logging.info(f"🔓 [Web-Trigger] {ticker} 엔진 잠금 및 에스크로 초기화!")
        cfg.reset_lock_for_ticker(ticker)
        cfg.clear_escrow_cash(ticker)
        try: os.remove(f_path)
        except: pass

    # 3. 실시간 동기화 (Record/Sync)
    triggered = []
    for f_path in glob.glob(os.path.join(base_dir, "trigger_record_*.tmp")):
        ticker = os.path.basename(f_path).replace("trigger_record_", "").replace(".tmp", "")
        logging.info(f"🔄 [Web-Trigger] {ticker} 실시간 잔고 동기화 명령 수신!")
        triggered.append("record")
        try: os.remove(f_path)
        except: pass
    
    # 🌟 [V23.3] '새로고침' 버튼 통합 대응 (refresh_needed.tmp)
    if os.path.exists(os.path.join(base_dir, "refresh_needed.tmp")):
        logging.info("🔄 [Web-Trigger] 전역 새로고침 명령 수신!")
        triggered.append("record")
        try: os.remove(os.path.join(base_dir, "refresh_needed.tmp"))
        except: pass

    return triggered

    # 4. 전략 이식 (Implant: 반대 모드의 설정을 현재 모드로 복사)
    for f_path in glob.glob(os.path.join(base_dir, "trigger_implant_*.tmp")):
        ticker = os.path.basename(f_path).replace("trigger_implant_", "").replace(".tmp", "")
        source_is_real = not cfg.is_real # 내가 MOCK이면 소스는 REAL, 내가 REAL이면 소스는 MOCK
        logging.info(f"🧬 [Web-Trigger] {ticker} 전략 이식 실행! (소스: {'REAL' if source_is_real else 'MOCK'})")
        if cfg.clone_config_from_mode(ticker, source_is_real):
            msg = f"🧬 <b>[{ticker}] 전략 성공적 이식 완료</b>\n{'모의' if source_is_real else '실전'}투자의 설정이 {'실전' if source_is_real else '모의'}투자로 복제되었습니다."
            try: await context.bot.send_message(cfg.get_chat_id(), msg, parse_mode='HTML')
            except: pass
        try: os.remove(f_path)
        except: pass

async def switch_trading_mode(context, new_mode):
    """
    🌟 [V22.2 Hot-Plug] 매매 모드 원자적 전환 엔진
    모든 매매 로직을 일시 중단하고 브로커와 설정을 실시간으로 교체합니다.
    """
    app_data = context.job.data
    tx_lock = app_data['tx_lock']
    cfg = app_data['cfg']
    old_mode_str = "실전투자" if not new_mode else "모의투자"
    new_mode_str = "실전투자" if new_mode else "모의투자"
    
    async with tx_lock:
        print(f"🔄 [Hot-Plug] 매매 모드 전환 시작: {old_mode_str} ➡️ {new_mode_str}")
        await context.bot.send_message(chat_id=context.job.chat_id, text=f"🔄 <b>[Hot-Plug] 매매 환경 전환 중: {old_mode_str} ➡️ {new_mode_str}</b>\n잠시만 기다려주세요...", parse_mode='HTML')
        
        # 1. 이전 모드의 모든 미체결 주문 취소 (안전 우선)
        active_tickers = cfg.get_active_tickers()
        for t in active_tickers:
            try:
                app_data['broker'].cancel_all_orders_safe(t)
            except Exception as e:
                print(f"⚠️ 주문 취소 중 오류 (무시): {e}")

        # 2. 새로운 모드 설정으로 인스턴스 재생성
        cfg.set_is_real_trading(new_mode) # 파일 및 메모리 업데이트
        
        # 키 선택
        if new_mode:
            k, s, c, p = REAL_APP_KEY, REAL_APP_SECRET, REAL_CANO, REAL_ACNT_PRDT_CD
        else:
            k, s, c, p = MOCK_APP_KEY, MOCK_APP_SECRET, MOCK_CANO, MOCK_ACNT_PRDT_CD
            
        new_broker = KoreaInvestmentBroker(cfg, k, s, c, p, is_real=new_mode)
        new_strategy = InfiniteStrategy(cfg)
        
        # 3. 글로벌 app_data 업데이트 (모든 태스크가 이 시점부터 새 브로커 사용)
        app_data['broker'] = new_broker
        app_data['strategy'] = new_strategy
        app_data['last_mode'] = new_mode
        
        # 4. 봇 컨트롤러 내부 인스턴스 갱신
        app_data['bot'].broker = new_broker
        app_data['bot'].strategy = new_strategy
        
        # 5. 상태 초기화 알림
        print(f"✅ [Hot-Plug] 매매 모드 전환 완료! 현재 모드: {new_mode_str}")
        await context.bot.send_message(chat_id=context.job.chat_id, text=f"✅ <b>[Hot-Plug] 매매 모드 전환 완료!</b>\n현재부터 <b>{new_mode_str}</b> 환경에서 모든 로직이 가동됩니다.", parse_mode='HTML')

async def scheduled_sniper_monitor(context):
    if context.job.data['cfg'].is_market_open() != "OPEN": return
    
    est = pytz.timezone('US/Eastern')
    now_est = datetime.datetime.now(est)
    
    try:
        nyse = mcal.get_calendar('NYSE')
        schedule = nyse.schedule(start_date=now_est.date(), end_date=now_est.date())
        if schedule.empty: return
        
        market_open = schedule.iloc[0]['market_open'].astimezone(est)
        market_close = schedule.iloc[0]['market_close'].astimezone(est)
    except Exception:
        if now_est.weekday() < 5:
            market_open = now_est.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = now_est.replace(hour=16, minute=0, second=0, microsecond=0)
        else: return
    
    pre_start = market_open.replace(hour=4, minute=0)
    start_monitor = pre_start + datetime.timedelta(minutes=1)
    end_monitor = market_close - datetime.timedelta(minutes=15)
    
    if not (start_monitor <= now_est <= end_monitor):
        return

    app_data = context.job.data
    cfg, broker, strategy, tx_lock = app_data['cfg'], app_data['broker'], app_data['strategy'], app_data['tx_lock']
    chat_id = context.job.chat_id
    
    target_cache = app_data.setdefault('dynamic_targets', {})
    today_est_str = now_est.strftime('%Y%m%d')
    if target_cache.get('date') != today_est_str:
        target_cache.clear()
        target_cache['date'] = today_est_str
    
    # 🚨 [V21.4 핫픽스] 비동기 병목(Deadlock) 타임아웃 족쇄 
    async def _do_sniper():
        async with tx_lock:
            cash, holdings = broker.get_account_balance()
            if holdings is None: return
            
            sorted_tickers, allocated_cash, force_turbo_off = get_budget_allocation(cash, holdings, cfg.get_active_tickers(), cfg)
            
            for t in cfg.get_active_tickers():
                if cfg.get_version(t) != "V17": continue
                
                lock_buy = cfg.check_lock(t, "SNIPER_BUY")
                lock_sell = cfg.check_lock(t, "SNIPER_SELL")
                
                if lock_buy and lock_sell:
                    continue
                
                h = holdings.get(t, {'qty': 0, 'avg': 0})
                qty = int(h['qty'])
                avg_price = float(h['avg'])
                if qty == 0: continue
                
                curr_p = await asyncio.to_thread(broker.get_current_price, t)
                prev_c = await asyncio.to_thread(broker.get_previous_close, t)
                if curr_p <= 0: continue
                
                idx_ticker = "SOXX" if t == "SOXL" else "QQQ"
                if t not in target_cache:
                    weight = cfg.get_sniper_multiplier(t)
                    tgt = await asyncio.to_thread(broker.get_dynamic_sniper_target, idx_ticker, weight)
                    target_cache[t] = tgt if tgt is not None else (9.0 if t=="SOXL" else 5.0) 

                sniper_pct = target_cache[t]
                raw_target_price = prev_c * (1 - (sniper_pct / 100.0))
                target_buy_price = math.floor(raw_target_price * 100) / 100.0
                
                is_sniper_armed = target_buy_price < avg_price
                trigger_reason = f"-{sniper_pct}% 동적 방어선"
                
                # =========================================================================
                # 1. 하방 스나이퍼 매수 (Intercept)
                # =========================================================================
                if not lock_buy and is_sniper_armed and target_buy_price > 0 and curr_p <= target_buy_price:
                    if cfg.get_secret_mode():
                        # V22.1 패치: 스나이퍼 역동결 가중치(Inverted Weight) 로직 적용
                        split = cfg.get_split_count(t)
                        t_val, _ = cfg.get_absolute_t_val(t, qty, avg_price)
                        
                        base_budget = cfg.get_seed(t) / split if split > 0 else 0
                        
                        # 지옥장 진입 여부에 따른 예산 승수 결정 (안전마진)
                        if t_val < 35: mult = 1.5       # 일반적인 폭락에선 평단가를 확 끌어내리기 위해 1.5배 타격
                        elif t_val < 50: mult = 1.2     # T>=35 위험 구간에서는 1.2배로 줄임
                        else: mult = 1.0                # T>=50 진짜 100분할까지 들어간 나락장에서는 현금 보존을 위해 1배수(원래 1회 분할) 유지
                        
                        sniper_budget = base_budget * mult
                        
                        # [추가] 🚨 잔여 현금 20% 마지노선 락다운 검사
                        total_seed = cfg.get_seed(t)
                        if allocated_cash[t] < (total_seed * 0.20):
                            now_ts = time.time()
                            fail_history = app_data.setdefault('sniper_fail_ts', {})
                            if now_ts - fail_history.get(t+"_20pct", 0) > 3600:
                                msg = f"🚨 <b>[{t}] 잔여 현금 20% 미만 진입! 스나이퍼 강제 락다운 (생존 구역)</b>\n"
                                msg += f"💵 할당 자본의 80%가 소진되었습니다. 모든 액티브(스나이퍼) 매수를 중단하고 정규장 1배수(LOC) 클래식 모드로만 버팁니다!"
                                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
                                fail_history[t+"_20pct"] = now_ts
                            continue
                        
                        if sniper_budget < curr_p: continue 

                        await asyncio.to_thread(broker.cancel_targeted_orders, t, "BUY", "34")
                        await asyncio.sleep(1.0)
                        
                        ask_price = await asyncio.to_thread(broker.get_ask_price, t)
                        exec_price = ask_price if ask_price > 0 else curr_p
                        rem_qty = math.floor(sniper_budget / exec_price)
                        
                        hunt_success = False
                        actual_buy_price = exec_price
                        
                        for attempt in range(3):
                            if rem_qty <= 0:
                                hunt_success = True
                                break

                            ask_price = await asyncio.to_thread(broker.get_ask_price, t)
                            exec_price = ask_price if ask_price > 0 else curr_p
                            
                            res = broker.send_order(t, "BUY", rem_qty, exec_price, "LIMIT")
                            odno = res.get('odno', '')
                            
                            if res.get('rt_cd') == '0' and odno:
                                await asyncio.sleep(2.0)
                                unfilled = await asyncio.to_thread(broker.get_unfilled_orders_detail, t)
                                my_order = next((o for o in unfilled if o.get('odno') == odno), None)
                                
                                if not my_order:
                                    rem_qty = 0
                                    hunt_success = True
                                    actual_buy_price = exec_price
                                    break
                                else:
                                    ord_qty = int(float(my_order.get('ord_qty', 0)))
                                    tot_ccld_qty = int(float(my_order.get('tot_ccld_qty', 0)))
                                    rem_qty = ord_qty - tot_ccld_qty
                                    
                                    await asyncio.to_thread(broker.cancel_order, t, odno)
                                    await asyncio.sleep(1.0)
                            
                            await asyncio.sleep(0.5)
                        
                        if hunt_success:
                            cfg.set_lock(t, "SNIPER_BUY") 
                            msg = f"💥 <b>[{t}] V20.11 시크릿 모드 가로채기(Intercept) 명중!</b>\n"
                            msg += f"📉 실시간 현재가(${curr_p:.2f})가 <b>[{trigger_reason}]</b>(${target_buy_price:.2f})을 터치했습니다!\n"
                            msg += f"🎯 <b>매수 방어선을 해제하고 최적 단가 ${actual_buy_price:.2f}에 즉시 낚아채어 체결을 완료</b>했습니다!\n"
                            msg += "🔫 당일 하방(매수) 스나이퍼 활동만을 종료하며, 상방(익절) 감시는 계속됩니다."
                            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
                            cfg.log_event("TRADE", "SUCCESS", "SNIPER_BUY", f"[{t}] 스나이퍼 매수 성공 💥", details=f"단가: ${actual_buy_price:.2f}, {trigger_reason}")
                            continue

                        now_ts = time.time()
                        fail_history = app_data.setdefault('sniper_fail_ts', {})
                        if now_ts - fail_history.get(t, 0) > 3600:
                            msg = f"🛡️ <b>[{t}] V20.11 가로채기 덫 기습 실패 (1시간 쿨타임 진입)</b>\n"
                            msg += f"📉 동적 방어선(${target_buy_price:.2f})에 3회 지정가 덫을 던졌으나 잔량이 남았습니다.\n"
                            msg += f"🦇 매수 스나이퍼는 1시간 동안 숨을 죽이며, 취소했던 일반 방어 매수(LOC) 주문만 호가창에 정밀 복구합니다."
                            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
                            fail_history[t] = now_ts
                        
                        ma_5day = await asyncio.to_thread(broker.get_5day_ma, t)
                        plan = strategy.get_plan(t, curr_p, avg_price, qty, prev_c, ma_5day=ma_5day, market_type="REG", available_cash=allocated_cash[t], force_turbo_off=force_turbo_off)
                        
                        for o in plan.get('core_orders', []) + plan.get('bonus_orders', []):
                            if o['side'] == 'BUY':
                                broker.send_order(t, o['side'], o['qty'], o['price'], o['type'])
                                await asyncio.sleep(0.2)
                                
                        continue

                # =========================================================================
                # 2. 상방 스나이퍼 매도 (Jackpot)
                # =========================================================================
                target_pct_val = cfg.get_target_profit(t)
                target_price = math.ceil(avg_price * (1 + target_pct_val / 100.0) * 100) / 100.0
                
                split = cfg.get_split_count(t)
                t_val, _ = cfg.get_absolute_t_val(t, qty, avg_price)
                
                depreciation_factor = 2.0 / split if split > 0 else 0.1
                star_ratio = (target_pct_val / 100.0) - ((target_pct_val / 100.0) * depreciation_factor * t_val)
                star_price = math.ceil(avg_price * (1 + star_ratio) * 100) / 100.0
                
                # 🛡️ [V26.9] 당일 보호 원칙: 오늘 매수한 종목은 실시간 목표가 돌파(Jackpot/별값) 감시에서 제외 (최소 1박 숙성)
                kor_today = datetime.datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d')
                last_buy_date = cfg.get_last_split_date(t)
                is_protected_today = (last_buy_date == kor_today)

                if is_protected_today:
                    continue

                if not lock_sell and curr_p >= target_price:
                    await asyncio.to_thread(broker.cancel_all_orders_safe, t, side="SELL")
                    await asyncio.sleep(1.0)
                    
                    rem_qty = qty
                    hunt_success = False
                    actual_sell_price = target_price
                    
                    for attempt in range(3):
                        if rem_qty <= 0:
                            hunt_success = True
                            break
                            
                        bid_price = await asyncio.to_thread(broker.get_bid_price, t)
                        
                        if bid_price > 0 and bid_price >= target_price:
                            res = broker.send_order(t, "SELL", rem_qty, bid_price, "LIMIT")
                            odno = res.get('odno', '')
                            
                            if res.get('rt_cd') == '0' and odno:
                                await asyncio.sleep(2.0)
                                unfilled = await asyncio.to_thread(broker.get_unfilled_orders_detail, t)
                                my_order = next((o for o in unfilled if o.get('odno') == odno), None)
                                
                                if not my_order:
                                    rem_qty = 0
                                    hunt_success = True
                                    actual_sell_price = bid_price
                                    break
                                else:
                                    ord_qty = int(float(my_order.get('ord_qty', 0)))
                                    tot_ccld_qty = int(float(my_order.get('tot_ccld_qty', 0)))
                                    rem_qty = ord_qty - tot_ccld_qty
                                    
                                    await asyncio.to_thread(broker.cancel_order, t, odno)
                                    await asyncio.sleep(1.0)
                                    
                        await asyncio.sleep(0.5)
                        
                    if hunt_success:
                        cfg.set_lock(t, "SNIPER_SELL")
                        msg = f"🔥 <b>[{t}] 스나이퍼 잭팟 터짐! (목표가 돌파)</b>\n"
                        msg += f"🎯 실시간 매수 1호가(${bid_price:.2f})가 목표가(${target_price:.2f})를 돌파하여 <b>실제 단가 ${actual_sell_price:.2f}에 전량 강제 익절</b> 처리했습니다.\n"
                        msg += "🔫 당일 상방(매도) 스나이퍼 활동을 완전 종료합니다."
                        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
                        cfg.log_event("TRADE", "SUCCESS", "SNIPER_SELL", f"[{t}] 스나이퍼 익절 성공 🔥", details=f"단가: ${actual_sell_price:.2f}, 목표가: ${target_price:.2f}")
                        continue
                        
                    now_ts = time.time()
                    fail_history_j = app_data.setdefault('sniper_j_fail_ts', {})
                    if now_ts - fail_history_j.get(t, 0) > 3600:
                        msg = f"🛡️ <b>[{t}] 스나이퍼 잭팟 기습 실패 (방어선 복구)</b>\n"
                        msg += f"🎯 3회에 걸쳐 전량 익절을 시도했으나 체결되지 않았습니다.\n"
                        msg += f"🦇 취소했던 원래의 매도(SELL) 주문을 다시 호가창에 정밀 장전합니다."
                        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
                        fail_history_j[t] = now_ts
                    
                    ma_5day = await asyncio.to_thread(broker.get_5day_ma, t)
                    plan = strategy.get_plan(t, curr_p, avg_price, qty, prev_c, ma_5day=ma_5day, market_type="REG", available_cash=allocated_cash[t], force_turbo_off=force_turbo_off)
                    
                    for o in plan.get('core_orders', []) + plan.get('bonus_orders', []):
                        if o['side'] == 'SELL':
                            broker.send_order(t, o['side'], o['qty'], o['price'], o['type'])
                            await asyncio.sleep(0.2)
                            
                    continue
                
                # =========================================================================
                # 3. 상방 스나이퍼 매도 (Quarter / 별값 익절)
                # =========================================================================
                is_first_half = t_val < (split / 2)
                trigger_price = star_price if is_first_half else math.ceil(avg_price * 1.0025 * 100) / 100.0
                q_qty = math.ceil(qty / 4)
                phase = "전반전(별값 돌파)" if is_first_half else "후반전(본전+수수료 돌파)"
                
                if not lock_sell and curr_p >= trigger_price:
                    unfilled = await asyncio.to_thread(broker.get_unfilled_orders_detail, t)
                    target_odno = None
                    
                    for o in unfilled:
                        if o.get('sll_buy_dvsn_cd') == '01' and o.get('ord_dvsn_cd') == '34': 
                            target_odno = o.get('odno')
                            break
                            
                    if target_odno:
                        await asyncio.to_thread(broker.cancel_order, t, target_odno)
                        await asyncio.sleep(1.0) 
                        
                        rem_qty = q_qty
                        hunt_success = False
                        actual_sell_price = trigger_price
                        
                        for attempt in range(3):
                            if rem_qty <= 0:
                                hunt_success = True
                                break
                                
                            bid_price = await asyncio.to_thread(broker.get_bid_price, t)
                            
                            if bid_price > 0 and bid_price >= trigger_price:
                                res = broker.send_order(t, "SELL", rem_qty, bid_price, "LIMIT")
                                odno = res.get('odno', '')
                                
                                if res.get('rt_cd') == '0' and odno:
                                    await asyncio.sleep(2.0)
                                    unfilled_check = await asyncio.to_thread(broker.get_unfilled_orders_detail, t)
                                    my_order = next((o for o in unfilled_check if o.get('odno') == odno), None)
                                    
                                    if not my_order:
                                        rem_qty = 0
                                        hunt_success = True
                                        actual_sell_price = bid_price
                                        break
                                    else:
                                        ord_qty = int(float(my_order.get('ord_qty', 0)))
                                        tot_ccld_qty = int(float(my_order.get('tot_ccld_qty', 0)))
                                        rem_qty = ord_qty - tot_ccld_qty
                                        
                                        await asyncio.to_thread(broker.cancel_order, t, odno)
                                        await asyncio.sleep(1.0)
                                        
                            await asyncio.sleep(0.5)
                            
                        if hunt_success:
                            cfg.set_lock(t, "SNIPER_SELL")
                            
                            msg = f"🔫 <b>[{t}] V17 시크릿 쿼터 익절 발동! ({phase})</b>\n"
                            msg += f"🎯 실시간 매수 1호가: ${bid_price:.2f} (트리거: ${trigger_price:.2f})\n"
                            msg += f"🛡️ 기존 쿼터 방어선만 해제하고 {q_qty}주를 <b>최적의 단가 ${actual_sell_price:.2f}에 즉시 낚아챘습니다!</b>\n"
                            
                            if is_first_half:
                                await asyncio.to_thread(broker.cancel_targeted_orders, t, "BUY", "34")
                                await asyncio.sleep(1.0)
                                
                                ma_5day = await asyncio.to_thread(broker.get_5day_ma, t)
                                plan = strategy.get_plan(t, curr_p, avg_price, qty, prev_c, ma_5day=ma_5day, market_type="REG", available_cash=allocated_cash[t], force_turbo_off=force_turbo_off)
                                
                                smart_cores = plan.get('smart_core_orders', [])
                                smart_bonus = plan.get('smart_bonus_orders', [])
                                
                                if len(smart_cores) == 0:
                                    msg += "\n🛑 <b>[스마트 밸런싱 발동]</b>\n└ 전반전 종가 관망 모드로 전환 (오늘 추가 매수 안 함)"
                                else:
                                    msg += "\n🦇 <b>[스마트 방어 매수 장전] (플랜 B 전환)</b>\n"
                                    for o in smart_cores:
                                        # 🚀 [V23.1] 모의투자 LOC 에뮬레이션: 스마트 매수 스테이징
                                        if not broker.is_real and o.get('type') == 'LOC':
                                            cfg.stage_mock_loc_order(t, o)
                                            msg += f"└ {o['desc']} {o['qty']}주: 🕒 [MOCK-LOC 예약]\n"
                                            continue

                                        buy_res = broker.send_order(t, o['side'], o['qty'], o['price'], o['type'])
                                        err_msg = buy_res.get('msg1')
                                        msg += f"└ {o['desc']} {o['qty']}주: {'✅' if buy_res.get('rt_cd') == '0' else f'❌({err_msg})'}\n"
                                        await asyncio.sleep(0.2)
                                        
                                    for o in smart_bonus:
                                        # 🚀 [V23.1] 모의투자 LOC 에뮬레이션: 스마트 보너스 스테이징
                                        if not broker.is_real and o.get('type') == 'LOC':
                                            cfg.stage_mock_loc_order(t, o)
                                            msg += f"└ {o['desc']} {o['qty']}주: 🕒 [MOCK-LOC 예약]\n"
                                            continue

                                        buy_res = broker.send_order(t, o['side'], o['qty'], o['price'], o['type'])
                                        msg += f"└ {o['desc']} {o['qty']}주: {'✅' if buy_res.get('rt_cd') == '0' else '❌'}\n"
                                        await asyncio.sleep(0.2)
                            else:
                                msg += "\n🛡️ <b>[공수 완벽 분리 원칙 적용]</b>\n└ 쿼터 익절 성공(후반전)! 기존 하방 매수(LOC) 주문은 연동하여 관리됩니다."
                                
                            msg += "\n🔒 당일 상방(매도) 쿼터 스나이퍼 감시를 종료합니다."
                            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
                            continue
                            
                        now_ts = time.time()
                        fail_history_q = app_data.setdefault('sniper_q_fail_ts', {})
                        if now_ts - fail_history_q.get(t, 0) > 3600:
                            msg = f"🛡️ <b>[{t}] 스나이퍼 쿼터 기습 실패 (방어선 복구)</b>\n"
                            msg += f"🎯 3회에 걸쳐 쿼터 익절을 시도했으나 체결되지 않았습니다.\n"
                            msg += f"🦇 취소했던 원래의 쿼터 방어 주문(LOC 매도)을 다시 장전합니다."
                            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
                            fail_history_q[t] = now_ts
                        
                        ma_5day = await asyncio.to_thread(broker.get_5day_ma, t)
                        plan = strategy.get_plan(t, curr_p, avg_price, qty, prev_c, ma_5day=ma_5day, market_type="REG", available_cash=allocated_cash[t], force_turbo_off=force_turbo_off)
                        
                        for o in plan.get('core_orders', []):
                            if o['side'] == 'SELL' and o['type'] == 'LOC':
                                if not broker.is_real:
                                    cfg.stage_mock_loc_order(t, o)
                                else:
                                    broker.send_order(t, o['side'], o['qty'], o['price'], o['type'])
                                await asyncio.sleep(0.2)
                                
                        continue
    
    try:
        await asyncio.wait_for(_do_sniper(), timeout=45.0)
    except asyncio.TimeoutError:
        pass # 타임아웃 예외 처리 생략 (안정성 확보)
    except Exception as e:
        logging.error(f"🚨 스나이퍼 모니터 에러: {e}")

async def scheduled_mock_loc_execution(context):
    """🚀 [V23.1] 모의투자 전용: 장 마감 직전 스테이징된 LOC 주문들을 일괄 실행"""
    app_data = context.job.data
    cfg, broker = app_data['cfg'], app_data['broker']
    chat_id = context.job.chat_id
    
    staged_orders = cfg.get_staged_mock_loc_orders()
    if not staged_orders:
        return

    msg = f"🕒 <b>[MOCK-LOC] 장 마감 전 에뮬레이션 매매를 실행합니다.</b>\n"
    msg += f"대상: {len(staged_orders)}건의 예약 주문\n"
    
    success_count = 0
    for o in staged_orders:
        ticker = o['ticker']
        # 모의투자이므로 시장가나 다름없는 Limit 주문으로 처리 (체결 보장)
        # 매도면 하방 10% 아래, 매수면 상방 10% 위로 넉넉하게 가격 설정 (실제 종단가 체결 유도)
        curr_p = await asyncio.to_thread(broker.get_current_price, ticker)
        exec_price = curr_p * 1.1 if o['side'] == 'BUY' else curr_p * 0.9
        
        res = broker.send_order(ticker, o['side'], o['qty'], exec_price, "LIMIT")
        is_ok = res.get('rt_cd') == '0'
        if is_ok: success_count += 1
        msg += f"\n└ {ticker} {o['side']} {o['qty']}주: {'✅' if is_ok else '❌'}"
        await asyncio.sleep(0.5)
        
    msg += f"\n\n🏁 총 {success_count}건 매매 성공. 모의투자 종가 매매가 완료되었습니다."
    cfg.clear_staged_mock_loc_orders()
    cfg.log_event("MOCK-LOC", "SUCCESS", "EXEC", f"종가 매매 {success_count}건 실행 완료")
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')

async def scheduled_regular_trade(context):
    if context.job.data['cfg'].is_market_open() != "OPEN":
        return
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.datetime.now(kst)
    target_hour, _, _ = get_target_hour()
    chat_id = context.job.chat_id
    
    # ±2분 이상 차이나면 오작동 방지를 위해 중단
    now_minutes = now.hour * 60 + now.minute
    target_minutes = target_hour * 60 + 30
    if abs(now_minutes - target_minutes) > 2 and abs(now_minutes - target_minutes) < (24*60 - 2):
        return
        
    if not is_market_open():
        await context.bot.send_message(chat_id=chat_id, text="⛔ <b>오늘은 미국 증시 휴장일입니다. 정규장 주문 스케줄을 건너뜁니다.</b>", parse_mode='HTML')
        return
    
    app_data = context.job.data
    cfg, broker, strategy, tx_lock = app_data['cfg'], app_data['broker'], app_data['strategy'], app_data['tx_lock']
    latest_version = cfg.get_latest_version()
    cfg.log_event("SCHEDULE", "REG", "START", f"🔥 [{target_hour}:30] 정규장 주문 스케줄 실행 ({latest_version})")
    await context.bot.send_message(chat_id=chat_id, text=f"🌃 <b>[{target_hour}:30] 다이내믹 스노우볼 {latest_version} 정규장 주문을 준비합니다.</b>", parse_mode='HTML')
    
    async def _do_regular_trade():
        async with tx_lock:
            cash, holdings = broker.get_account_balance()
            if holdings is None: return

            sorted_tickers, allocated_cash, force_turbo_off = get_budget_allocation(cash, holdings, cfg.get_active_tickers(), cfg)
            plans = {}
            msgs = {t: "" for t in sorted_tickers}
            all_success = {t: True for t in sorted_tickers}

            for t in sorted_tickers:
                if cfg.check_lock(t, "REG"): continue
                h = holdings.get(t, {'qty': 0, 'avg': 0})
                curr_p = await asyncio.to_thread(broker.get_current_price, t)
                prev_c = await asyncio.to_thread(broker.get_previous_close, t)
                ma_5day = await asyncio.to_thread(broker.get_5day_ma, t)
                plan = strategy.get_plan(t, curr_p, float(h['avg']), int(h['qty']), prev_c, ma_5day=ma_5day, market_type="REG", available_cash=allocated_cash[t], force_turbo_off=force_turbo_off)
                plans[t] = plan
                if plan['orders']: msgs[t] += f"💎 <b>[{t}] 정규장 주문 실행 (교차 전송)</b>\n"

            for t in sorted_tickers:
                if t not in plans or not plans[t]['orders']: continue
                for o in plans[t].get('core_orders', []):
                    # 🚀 [V23.1] 모의투자 LOC 에뮬레이션: 즉시 전송 대신 스테이징
                    if not broker.is_real and o.get('type') == 'LOC':
                        cfg.stage_mock_loc_order(t, o)
                        msgs[t] += f"└ 1차 필수: {o['desc']} {o['qty']}주: 🕒 [MOCK-LOC 예약 완료]\n"
                        continue

                    res = broker.send_order(t, o['side'], o['qty'], o['price'], o['type'])
                    if res.get('rt_cd') == '888':
                        msgs[t] += "🚫 <b>모의투자 휴장일 감지: 필수 주문 전송 취소</b>\n"
                        all_success[t] = False
                        break
                    
                    if res.get('rt_cd') == '0':
                        # 🛡️ [V26.9] 매수 성공 시 날짜 기록 (당일 보호 로직 연동)
                        kor_today = datetime.datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d')
                        cfg.set_last_split_date(t, kor_today)
                    else:
                        all_success[t] = False

                    msgs[t] += f"└ 1차 필수: {o['desc']} {o['qty']}주: {'✅' if res.get('rt_cd') == '0' else f'❌({res.get('msg1')})'}\n"
                    await asyncio.sleep(0.2) 

            for t in sorted_tickers:
                if t not in plans or not plans[t]['orders']: continue
                for o in plans[t].get('bonus_orders', []):
                    # 🚀 [V23.1] 모의투자 LOC 에뮬레이션: 보너스 주문 스테이징
                    if not broker.is_real and o.get('type') == 'LOC':
                        cfg.stage_mock_loc_order(t, o)
                        msgs[t] += f"└ 2차 보너스: {o['desc']} {o['qty']}주: 🕒 [MOCK-LOC 예약 완료]\n"
                        continue

                    res = broker.send_order(t, o['side'], o['qty'], o['price'], o['type'])
                    msgs[t] += f"└ 2차 보너스: {o['desc']} {o['qty']}주: {'✅' if res.get('rt_cd') == '0' else '❌(잔금패스)'}\n"
                    await asyncio.sleep(0.2) 

            for t in sorted_tickers:
                if not msgs[t]: continue
                if all_success[t] and len(plans[t].get('core_orders', [])) > 0:
                    cfg.set_lock(t, "REG")
                    cfg.log_event("TRADE", "SUCCESS", "REG", f"[{t}] 정규장 필수 주문 체결 시도 완료 (잠금)")
                    msgs[t] += "\n🔒 <b>필수 주문 정상 전송 완료 (잠금 설정됨)</b>"
                elif not all_success[t]:
                    cfg.log_event("TRADE", "WARNING", "REG", f"[{t}] 일부 필수 주문 전송 실패 확인")
                    msgs[t] += "\n⚠️ <b>일부 필수 주문 실패 (매매 잠금 보류)</b>"
                else:
                    cfg.set_lock(t, "REG")
                    cfg.log_event("TRADE", "SUCCESS", "REG", f"[{t}] 보너스 줍줍 주문 전송 완료")
                    msgs[t] += "\n🔒 <b>보너스 줍줍 주문만 전송 완료 (잠금 설정됨)</b>"
                
                cfg.log_event("TRADE", "SUCCESS" if all_success[t] else "WARNING", "REG", f"[{t}] 정규장 주문 집행", 
                                   details=f"결과: {len(plans[t].get('core_orders', []))}건 전송 ({'성공' if all_success[t] else '일부실패'})")
                await context.bot.send_message(chat_id=chat_id, text=msgs[t], parse_mode='HTML')

    try:
        update_task_status(app_data['mode'], "reg", "running")
        await asyncio.wait_for(_do_regular_trade(), timeout=300.0) 
        update_task_status(app_data['mode'], "reg", "done")
    except Exception as e:
        update_task_status(app_data['mode'], "reg", "error")
        cfg.log_event("SCHEDULE", "ERROR", "FAILURE", f"정규장 매매 엔진 오류", details=str(e)[:50])
        logging.error(f"🚨 정규장 매매 에러: {e}")

async def scheduled_auto_sync_summer(context):
    if not is_dst_active(): return 
    await run_auto_sync(context, "08:30")

async def scheduled_auto_sync_winter(context):
    if is_dst_active(): return 
    await run_auto_sync(context, "09:30")

async def run_auto_sync(context, time_str):
    chat_id = context.job.chat_id
    bot = context.job.data['bot']
    cfg = context.job.data['cfg']
    mode = context.job.data['mode']
    
    update_task_status(mode, "sync", "running")
    status_msg = await context.bot.send_message(chat_id=chat_id, text=f"📝 <b>[{time_str}] 장부 자동 동기화 시작...</b>", parse_mode='HTML')
    success_tickers = []
    for t in cfg.get_active_tickers():
        res = await bot.process_auto_sync(t, chat_id, context, silent_ledger=True)
        if res == "SUCCESS": success_tickers.append(t)
    
    if success_tickers:
        # 🚀 [V33 Unified] 동기화 알림 통합
        cfg.log_event("SCHEDULE", "SYNC", "SUCCESS", f"장부 자동 동기화 완료 ({len(success_tickers)}종목)")
        async with context.job.data['tx_lock']:
            _, holdings = context.job.data['broker'].get_account_balance()
        await bot._display_ledger(success_tickers[0], chat_id, context, message_obj=status_msg, pre_fetched_holdings=holdings)
    else:
        cfg.log_event("SCHEDULE", "SYNC", "SUCCESS", "자동 동기화 (변경사항 없음)")
        await status_msg.edit_text(f"📝 <b>[{time_str}] 장부 동기화 완료 (표시할 항목 없음)</b>", parse_mode='HTML')
    
    update_task_status(mode, "sync", "done")

async def scheduled_analytics_snapshot(context):
    app_data = context.job.data
    cfg, broker, tx_lock = app_data['cfg'], app_data['broker'], app_data['tx_lock']
    chat_id = context.job.chat_id
    
    import json
    LIVE_FILE = cfg._get_file_path("LIVE_STATUS")
    live_data = {"tickers": {}}
    if os.path.exists(LIVE_FILE):
        try:
            with open(LIVE_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                if isinstance(loaded_data, dict):
                    live_data = loaded_data
        except: pass

    try:
        async with tx_lock:
            cash, holdings = await asyncio.to_thread(broker.get_account_balance)
        if holdings is None: return
        
        holdings_value = 0.0
        ticker_state = {}
        for t in cfg.get_active_tickers():
            h = holdings.get(t, {'qty': 0, 'avg': 0})
            avg, qty = float(h['avg']), int(h['qty'])
            
            curr_p = await asyncio.to_thread(broker.get_current_price, t)
            # 🛑 [보정] 가격 조회 실패(0) 시 평단가로 대체하여 데이터 오염 방지
            if curr_p <= 0: curr_p = avg
            
            # 🚀 [V24.1] 전략용 보조 지표 항구적 저장 (MA5, Day Low)
            ma_5day = 0
            day_low = curr_p
            try:
                # OHLCV 조회를 통해 지표 산정
                ohlcv = await asyncio.to_thread(broker.get_daily_ohlcv, t, count=5)
                if ohlcv and len(ohlcv) >= 5:
                    ma_5day = sum(float(x['close']) for x in ohlcv) / 5
                    day_low = min(float(x['low']) for x in ohlcv)
            except: pass

            if qty > 0:
                holdings_value += (qty * curr_p)
                
            # 🛡️ [V24.5] 가격 방어: API가 0이면 메모리(live_data)에서 가져옴
            if curr_p <= 0:
                curr_p = float(live_data.get("tickers", {}).get(t, {}).get("current_price", 0))
            if curr_p <= 0: # 최후의 수단으로 평단가
                curr_p = avg

            ticker_state[t] = {
                "qty": qty,
                "avg_price": avg,
                "current_price": curr_p,
                "prev_close": curr_p, 
                "ma_5day": ma_5day,
                "day_low": day_low,
                "slots": live_data.get("tickers", {}).get(t, {}).get("slots", {}) # 📋 주문 계획 박제 보존
            }
            
        update_task_status(app_data['mode'], "after", "running")
        # 구체적인 ticker_state를 넘겨서 임시 장부(daily_snapshots.json)의 정확도를 높임
        snap = cfg.record_daily_snapshot(cash, holdings_value, ticker_state=ticker_state)
        
        msg = (
            f"📊 <b>[Daily Analytics Snapshot] ({app_data['mode']})</b>\n"
            f"📅 날짜: {snap['date']}\n"
            f"💵 현금: ${snap['cash']:,.2f}\n"
            f"📈 주식: ${snap['holdings']:,.2f}\n"
            f"💰 총자산: ${snap['total']:,.2f}\n"
            f"✅ 성과 분석 및 임시 장부 기록이 완료되었습니다."
        )
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
        cfg.log_event("SCHEDULE", "SNAPSHOT", "SUCCESS", f"일일 분석 스냅샷 저장 완료 (${snap['total']:,.0f})")
        update_task_status(app_data['mode'], "after", "done")
        logging.info(f"📊 [Analytics] Daily snapshot recorded: ${snap['total']:,.2f}")
        
    except Exception as e:
        logging.error(f"❌ [Analytics] 스냅샷 기록 중 오류 발생: {e}")


async def main():
    load_dotenv()
    
    # [V23.1 Dual-Core] 환경 변수 전체 로딩
    real_env = {
        "k": os.getenv("REAL_APP_KEY"), "s": os.getenv("REAL_APP_SECRET"),
        "c": os.getenv("REAL_CANO"), "p": os.getenv("REAL_ACNT_PRDT_CD", "01"),
        "token": os.getenv("REAL_TELEGRAM_TOKEN"), "admin": os.getenv("REAL_ADMIN_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")
    }
    mock_env = {
        "k": os.getenv("MOCK_APP_KEY"), "s": os.getenv("MOCK_APP_SECRET"),
        "c": os.getenv("MOCK_CANO"), "p": os.getenv("MOCK_ACNT_PRDT_CD", "01"),
        "token": os.getenv("MOCK_TELEGRAM_TOKEN"), "admin": os.getenv("MOCK_ADMIN_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")
    }

    target_hour, season_msg, _ = get_target_hour()
    print("=" * 50)
    print(f"🚀 Infinity Quant Hub V23.1 (Dual-Core Architecture)")
    print(f"📅 날짜 정보: {season_msg}")
    print("=" * 50)

    # 🌅 [V27-Unified] 통합 웹 서버를 사이드 쓰레드로 가동 (Shared Memory & Logging)
    def run_uvicorn():
        print(f"🚀 [HUB] Web Dashboard Server (Port 5050) starting in background thread...")
        uvicorn.run(web_app, host="0.0.0.0", port=5050, log_level="warning")

    try:
        server_thread = threading.Thread(target=run_uvicorn, daemon=True)
        server_thread.start()
        print(f"✅ [HUB] Web Server thread started successfully.")
    except Exception as e:
        print(f"❌ [HUB] Error starting Web Server thread: {e}")

    engines = []
    
    # 1. 실전 엔진 준비
    if real_env["token"] and real_env["k"]:
        print(f"🚀 [REAL] 실전 투자 엔진 초기화 중...")
        engines.append(TradingEngine("REAL", real_env["k"], real_env["s"], real_env["c"], real_env["p"], real_env["token"], real_env["admin"]))
    
    # 2. 모의 엔진 준비
    if mock_env["token"] and mock_env["k"]:
        print(f"🧪 [MOCK] 모의 투자 엔진 초기화 중...")
        engines.append(TradingEngine("MOCK", mock_env["k"], mock_env["s"], mock_env["c"], mock_env["p"], mock_env["token"], mock_env["admin"]))

    if not engines:
        print("❌ [치명적 오류] 가동 가능한 엔진이 없습니다. .env 파일을 확인하세요.")
        return

    # 4. 병렬 엔진 가동 (무한 루프)
    print(f"✨ 총 {len(engines)}개의 엔진이 병렬로 가동됩니다.")
    await asyncio.gather(*(eng.start() for eng in engines))
    
    # 상시 대기 루프 (엔진은 백그라운드 job_queue에서 동작함)
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 프로그램을 안전하게 종료합니다.")
