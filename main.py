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
import json
import subprocess
import sys

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

log_filename = f"logs/bot_app_{datetime.datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO,
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def is_dst_active():
    """
    🌞 [Universal] 미국 동부 표준시 서머타임 판별
    pytz 라이브러리를 통해 현재 시각의 DST 여부를 판별함 (연도 무관)
    """
    try:
        est = pytz.timezone('America/New_York')
        now = datetime.datetime.now(est)
        # dst()가 0이 아니면 서머타임 적용 중
        return now.dst().total_seconds() != 0
    except Exception as e:
        print(f"❌ [DST 판별 오류]: {e}")
        return False

def get_target_hour():
    # 🇺🇸 미국 본장 개장 시간 교정 (KST 기준): 22:30(여름) / 23:30(겨울)
    return (22, "🌞 서머타임 적용(여름)") if is_dst_active() else (23, "❄️ 서머타임 해제(겨울)")

# 🌅 [V23.1 Dual-Core] 거래 엔진 캡슐화
class TradingEngine:
    def __init__(self, mode_name, app_key, app_secret, cano, acnt_prdt_cd, telegram_token, admin_chat_id):
        self.mode_name = mode_name.upper()
        self.is_real = (self.mode_name == "REAL")
        self.cfg = ConfigManager(is_real=self.is_real)
        if admin_chat_id: self.cfg.set_chat_id(admin_chat_id)
        
        self.broker = KoreaInvestmentBroker(app_key, app_secret, cano, acnt_prdt_cd, is_real=self.is_real)
        self.strategy = InfiniteStrategy(self.cfg)
        self.tx_lock = asyncio.Lock()
        
        # 텔레그램 컨트롤러 초기화 (단일 엔진 전용)
        self.bot_controller = TelegramController(self.cfg, self.broker, self.strategy, self.mode_name, self.tx_lock)
        
        # 텔레그램 애플리케이션 빌드
        self.app = Application.builder().token(telegram_token).build()
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
        target_hour, _ = get_target_hour()
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
        
        # 💓 [V23.1] 정밀 시계 동기화를 위한 심장박동 분리
        jq.run_repeating(scheduled_heartbeat, interval=10, chat_id=self.cfg.get_chat_id(), data=app_data)
        jq.run_repeating(scheduled_live_sync, interval=10, chat_id=self.cfg.get_chat_id(), data=app_data)
        
        # 5. 자정 관리 및 분석
        jq.run_daily(scheduled_self_cleaning, time=datetime.time(6, 0, tzinfo=kst), days=tuple(range(7)), chat_id=self.cfg.get_chat_id(), data=app_data)
        jq.run_daily(scheduled_analytics_snapshot, time=datetime.time(6, 10, tzinfo=kst), days=tuple(range(7)), chat_id=self.cfg.get_chat_id(), data=app_data)

    async def start(self):
        logging.info(f"🚀 [{self.mode_name}] 엔진 가동 시작...")
        await self.app.initialize()
        # 🧪 [V23.1] 엔진 기동 직후 즉각적인 데이터 동기화 수행
        mock_ctx = type('obj', (object,), {
            'job': type('obj', (object,), {
                'data': {
                    'cfg': self.cfg, 'broker': self.broker, 'strategy': self.strategy, 
                    'bot': self.bot_controller, 'tx_lock': self.tx_lock, 'mode': self.mode_name
                }
            })
        })
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
            self.cfg.record_event("SYSTEM", "SUCCESS", f"[{self.mode_name}] 엔진 가동", details="텔레그램 봇(수동 폴링) 및 스케줄러 활성화 완료")
        except Exception as e:
            logging.error(f"🚨 [{self.mode_name}] 텔레그램 봇 가동 실패: {e}")
            self.cfg.record_event("SYSTEM", "ERROR", f"[{self.mode_name}] 봇 기동 실패", details=str(e))
        
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

# ? [V21.4 ?픽?] ?? 개장 ?별 강력 교정 (?이러브러리 ?류 ?어)
def is_market_open():
    try:
        est = pytz.timezone('US/Eastern')
        today = datetime.datetime.now(est)
        # 1차: 명확한 주말은 무조건 휴장 처리 (0:월 ~ 6:일)
        if today.weekday() >= 5: 
            return "WEEKEND"
            
        nyse = mcal.get_calendar('NYSE')
        schedule = nyse.schedule(start_date=today.date(), end_date=today.date())
        
        if not schedule.empty:
            return "OPEN"
        else:
            # 달력 데이터가 아예 비어있으면 진짜 공휴일
            return "HOLIDAY"
    except Exception as e:
        # 패키지 구버전 등 달력 조회 에러 시, 평일이면 무조건 개장으로 강제 처리
        logging.error(f"⚠️ 달력 라이브러리 에러 발생. 평일이므로 강제 개장 처리합니다: {e}")
        return "OPEN"

def get_budget_allocation(cash, holdings, tickers, cfg):
    sorted_tickers = sorted(tickers, key=lambda x: 0 if x == "SOXL" else (1 if x == "TQQQ" else 2))
    allocated = {}
    force_turbo_off = False
    rem_cash = cash
    
    for tx in sorted_tickers:
        # V22 패치: 리버스 모드 로직 폐기 및 동적 분할 예산 할당
        h = holdings.get(tx, {'qty': 0, 'avg': 0}) if holdings else {'qty': 0, 'avg': 0}
        qty = int(h['qty'])
        avg_price = float(h['avg'])
        
        t_val, _ = cfg.get_absolute_t_val(tx, qty, avg_price)
        split = cfg.get_split_count(tx)
        
        if t_val < (split * 0.5): current_split = split
        elif t_val < (split * 0.75): current_split = math.floor(split * 1.5)
        elif t_val < (split * 0.9): current_split = math.floor(split * 2.0)
        else: current_split = math.floor(split * 2.5)
        
        portion = cfg.get_seed(tx) / current_split if current_split > 0 else 0
            
        if rem_cash >= portion:
            allocated[tx] = rem_cash
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
    target_hour, _ = get_target_hour()
    
    # 🚨 [V21.4 핫픽스] 0.001초 미세 오차(Jitter) 방어선 구축 (±2분 관용 타임)
    now_minutes = now.hour * 60 + now.minute
    target_minutes = target_hour * 60
    
    if abs(now_minutes - target_minutes) > 2 and abs(now_minutes - target_minutes) < (24*60 - 2):
        return
        
    if not is_market_open():
        await context.bot.send_message(chat_id=context.job.chat_id, text="⛔ <b>오늘은 미국 증시 휴장일입니다. 시스템 초기화 및 통제권을 건너뜁니다.</b>", parse_mode='HTML')
        return
    
    try:
        app_data = context.job.data
        mode = app_data['mode']
        update_task_status(mode, "pre", "running")
        
        app_data['cfg'].reset_locks()
        
        for t in app_data['cfg'].get_active_tickers():
            app_data['cfg'].increment_reverse_day(t)
            
        update_task_status(mode, "pre", "done")
        app_data['cfg'].add_notification("SUCCESS", f"[{mode}] 시스템 초기화 및 매매 잠금 해제 완료")
        app_data['cfg'].record_event("RESET", "SUCCESS", "시스템 초기입장", details=f"[{target_hour}:00] 매매 잠금 해제 및 엔진 기어 초기화")
        await context.bot.send_message(chat_id=context.job.chat_id, text=f"🔓 <b>[{mode}] [{target_hour}:00] 시스템 초기화 완료 (매매 잠금 해제 & 스나이퍼 장전 & 리버스 카운트 누적)</b>", parse_mode='HTML')
    except Exception as e:
        update_task_status(app_data['mode'], "pre", "error")
        app_data['cfg'].add_notification("ERROR", f"시스템 초기화 실패: {e}")
        await context.bot.send_message(chat_id=context.job.chat_id, text=f"🚨 <b>시스템 초기화 중 에러 발생:</b> {e}", parse_mode='HTML')

async def scheduled_premarket_monitor(context):
    if not is_market_open(): return
    app_data = context.job.data
    
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.datetime.now(kst)
    target_hour, _ = get_target_hour()
    
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
            cash, holdings = broker.get_account_balance()
            if holdings is None: return 

            for t in cfg.get_active_tickers():
                h = holdings.get(t, {'qty': 0, 'avg': 0})
                
                curr_p = await asyncio.to_thread(broker.get_current_price, t)
                prev_c = await asyncio.to_thread(broker.get_previous_close, t)
                if curr_p <= 0 or prev_c <= 0: continue
                
                gap_pct = (curr_p - prev_c) / prev_c * 100
                
                # 1. 갭상승 익절 체크 (+3% 이상 갭업 & 목표 도달 여부) (보유수량 있을때만)
                if int(h['qty']) > 0 and gap_pct >= 3.0:
                    plan = strategy.get_plan(t, curr_p, float(h['avg']), int(h['qty']), prev_c, market_type="PRE_CHECK")
                    if plan['orders']:
                        msg = f"🌅 <b>[{t}] 대박! 프리마켓 +3% 이상 갭업(+{gap_pct:.2f}%) 및 목표 달성 🎉</b>\n⚡ 본장 하락 전 차익실현을 위해 전량 프리마켓 조기 익절을 실행합니다!"
                        broker.cancel_all_orders_safe(t)
                        all_success = True
                        for o in plan['orders']:
                            # PRE 지정가 주문(32) 활용
                            res = broker.send_order(t, o['side'], o['qty'], o['price'], "PRE")
                            err_msg = res.get('msg1')
                            is_success = res.get('rt_cd') == '0'
                            if not is_success: all_success = False
                            msg += f"\n└ {o['desc']}: {'✅' if is_success else f'❌({err_msg})'}"
                            await asyncio.sleep(0.2) 
                        await context.bot.send_message(chat_id=context.job.chat_id, text=msg, parse_mode='HTML')
                        
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
                            
                            res = broker.send_order(t, "BUY", buy_qty, curr_p, "PRE")
                            if res.get('rt_cd') == '0':
                                msg += f"❌ 매수 실패: {res.get('msg1')}"
                            await context.bot.send_message(chat_id=context.job.chat_id, text=msg, parse_mode='HTML')

    try:
        update_task_status(app_data['mode'], "reg", "running") # 프리마켓 감시도 광의의 개장 준비(Reg)로 취급
        await asyncio.wait_for(_do_premarket(), timeout=45.0)
        update_task_status(app_data['mode'], "reg", "done")
    except asyncio.TimeoutError:
        update_task_status(app_data['mode'], "reg", "error")
        logging.warning("⚠️ 프리마켓 감시 중 통신 지연으로 1회 건너뜀 (Deadlock 방어)")
    except Exception as e:
        update_task_status(app_data['mode'], "pre", "error")
        cfg.add_notification("ERROR", f"🚨 프리마켓 스케줄 장애 발생: {str(e)[:50]}")
        logging.error(f"🚨 프리마켓 모니터 에러: {e}")
    finally:
        cfg.add_notification("STATUS", "🌅 프리마켓 감시 엔진 종료")

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
        
        # 2. 만약 '실시간 동기화(Record)' 트리거가 있었다면 즉시 sync 호출
        if triggers_found and "record" in triggers_found:
             logging.info(f"🔄 [{mode}] 리모컨 신호에 의해 즉시 동기화를 시작합니다.")
             await scheduled_live_sync(context)
             return

        # 3. 일반적인 심박동 (타임스탬프만 갱신)
        LIVE_FILE = cfg._get_file_path("LIVE_STATUS")
        live_data = {"tickers": {}}
        if os.path.exists(LIVE_FILE):
            try:
                with open(LIVE_FILE, 'r', encoding='utf-8') as f:
                    live_data = json.load(f)
            except: pass

        live_data["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        live_data["is_real"] = cfg.is_real
        
        TEMP_FILE = LIVE_FILE + ".heartbeat.tmp"
        with open(TEMP_FILE, 'w', encoding='utf-8') as f:
            json.dump(live_data, f, ensure_ascii=False, indent=4)
        os.replace(TEMP_FILE, LIVE_FILE)
        
    except Exception as e:
        logging.error(f"💓 Heartbeat 에러: {e}")

async def scheduled_live_sync(context):
    """
    🌟 [V23.3] 데이터 엔진 실시간 동기화 (Dynamic Phase Status Mapping)
    현재 장 상태(Pre/Reg/After)에 맞춰 타임라인 수행 상태를 실시간으로 업데이트합니다.
    """
    app_data = context.job.data if hasattr(context, 'job') else context 
    cfg, broker, strategy, tx_lock = app_data['cfg'], app_data['broker'], app_data['strategy'], app_data['tx_lock']
    mode = app_data.get('mode', 'MOCK')
    bot = app_data.get('bot')
    
    kst = pytz.timezone('Asia/Seoul')
    now_kst = datetime.datetime.now(kst)
    now_ts = now_kst.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    current_phase = "sync" # 기본값
    
    try:
        # 1. 현재 마켓 패이즈 사전 판별 (UI 상태 동기화용)
        est = pytz.timezone('US/Eastern')
        now_ny = datetime.datetime.now(est)
        
        # 🌑 [V23.3 최종 방어벽] 1차: 한국 시간 기준 주말(토/일)이면 무조건 강제 종료 고정
        if now_kst.weekday() >= 5: # 5:토, 6:일
            status_code, current_phase, is_weekend = "CLOSE", "sync", True
            status_text = "⛔ 주말 휴면 중"
        else:
            is_weekend = False
            # 2차: 뉴욕 현지 시간 정밀 체크 (공휴일 포함)
            nyse = mcal.get_calendar('NYSE')
            schedule = nyse.schedule(start_date=now_ny.date(), end_date=now_ny.date())
            status_code = "CLOSE"
            status_text = "⛔ 장마감"
            
            if schedule.empty:
                status_code, status_text = "HOLIDAY", "🇺🇸 미 증시 휴장일"
                current_phase = "sync"
            else:
                m_open = schedule.iloc[0]['market_open'].astimezone(est)
                m_close = schedule.iloc[0]['market_close'].astimezone(est)
                
                if m_open.replace(hour=4) <= now_ny < m_open: 
                    status_code, status_text, current_phase = "PRE", "🌅 프리마켓", "pre"
                elif m_open <= now_ny < m_close: 
                    status_code, status_text, current_phase = "REG", "🔥 정규장", "reg"
                elif m_close <= now_ny < m_close.replace(hour=20): 
                    status_code, status_text, current_phase = "AFTER", "🌙 애프터마켓", "after"
                else:
                    status_code, current_phase = "CLOSE", "sync"

        # 🚨 [V23.3] 오전 9시 ~ 10시 (KST) 사이는 강제 동기화 구간 (주말 포함 상시 동작)
        is_morning_sync_window = (now_kst.hour == 9) or (now_kst.hour == 10 and now_kst.minute < 30)

        # 🚀 상태 업데이트 (동기화 + 현재 패이즈)
        if is_weekend:
            status_code, status_text = "CLOSE", "⛔ 주말 휴면 중"
            update_task_status(mode, "sync", "done")
        elif is_morning_sync_window:
            update_task_status(mode, "sync", "running")
            status_text = "🔄 오전 동기화"
        else:
            # 🧹 [V23.3] 잔상 제거: 오전 시간이 아닌데 'running'인 경우 'done'으로 강제 정화
            current_sync_status = STATUS_TRACKER.get(mode, {}).get("sync", {}).get("status")
            if current_sync_status == "running":
                update_task_status(mode, "sync", "done")
        
        if not is_weekend and current_phase != "sync":
            update_task_status(mode, current_phase, "running")
        
        # 🚨 [V22.2.1] 웹앱 리모컨 (IPC 통신 브릿지)
        TRIGGER_FILE = os.path.join(cfg._get_base_dir(), "refresh_needed.tmp")
        if os.path.exists(TRIGGER_FILE):
            try: os.remove(TRIGGER_FILE)
            except: pass

        # 1. 스냅샷 데이터 기초 구조 (기존 수동 동기화 상태 등 보존) [V23.5]
        PREV_L_FILE = cfg._get_file_path("LIVE_STATUS")
        prev_sync_status = None
        if os.path.exists(PREV_L_FILE):
            try:
                with open(PREV_L_FILE, 'r', encoding='utf-8') as f:
                    prev_data = json.load(f)
                    prev_sync_status = prev_data.get("last_manual_sync")
            except: pass

        live_data = {
            "timestamp": now_ts,
            "last_manual_sync": prev_sync_status, # 이전 상태 보존
            "market_status": status_text, # 🔄 [V23.3] "데이터 갱신 중..." 대신 실제 상태 주입
            "is_real": cfg.is_real,
            "cash": 0, "holdings_value": 0, "tickers": {},
            "task_status": STATUS_TRACKER.get(mode, {})
        }

        # 🚀 [V23.1] 모드별 폴더에서 명령어 트리거 확인
        import glob
        trigger_path = os.path.join(cfg._get_base_dir(), "trigger_*.tmp")
        for f in glob.glob(trigger_path):
            filename = os.path.basename(f)
            try: os.remove(f)
            except: pass
            
            chat_id = cfg.get_chat_id()
            if filename.startswith("trigger_exec_") and bot:
                ticker = filename.replace("trigger_exec_", "").replace(".tmp", "")
                async def _exec_task(t, c_id):
                    await context.bot.send_message(c_id, f"🚀 <b>[{t}] 웹앱 리모컨: 수동 강제 매매 접수</b>", parse_mode='HTML')
                    async with tx_lock:
                        cash, holdings = broker.get_account_balance()
                        if holdings is None: return
                        _, allocated_cash, force_turbo_off = get_budget_allocation(cash, holdings, cfg.get_active_tickers(), cfg)
                        h = holdings.get(t, {'qty':0, 'avg':0})
                        curr_p = await asyncio.to_thread(broker.get_current_price, t)
                        prev_c = await asyncio.to_thread(broker.get_previous_close, t)
                        ma_5day = await asyncio.to_thread(broker.get_5day_ma, t)
                        plan = strategy.get_plan(t, curr_p, float(h['avg']), int(h['qty']), prev_c, ma_5day=ma_5day, market_type="REG", available_cash=allocated_cash.get(t,0), force_turbo_off=force_turbo_off)
                        
                        all_success = True
                        for o in plan.get('core_orders', []) + plan.get('bonus_orders', []):
                            res = broker.send_order(t, o['side'], o['qty'], o['price'], o['type'])
                            if res.get('rt_cd') != '0': all_success = False
                            await asyncio.sleep(0.2)
                        
                        if all_success and len(plan.get('core_orders', [])) > 0:
                            cfg.set_lock(t, "REG")
                            await context.bot.send_message(c_id, f"✅ <b>[{t}] 강제 매매 전송 완료 (잠금 처리)</b>", parse_mode='HTML')
                asyncio.create_task(_exec_task(ticker, chat_id))
                
            elif filename.startswith("trigger_record_") and bot:
                ticker = filename.replace("trigger_record_", "").replace(".tmp", "")
                async def _record_task(t, c_id):
                    await context.bot.send_message(c_id, f"🛡️ <b>[{t}] 웹앱 리모컨: 비파괴 장부 보정 시작...</b>", parse_mode='HTML')
                    await bot.process_auto_sync(t, c_id, context, silent_ledger=True)
                    async with tx_lock:
                        _, holdings = broker.get_account_balance()
                    await bot._display_ledger(t, c_id, context, pre_fetched_holdings=holdings)
                target_tickers = cfg.get_active_tickers() if ticker == "ALL" else [ticker]
                for tt in target_tickers:
                    asyncio.create_task(_record_task(tt, chat_id))
                    
            elif filename.startswith("trigger_reset_"):
                ticker = filename.replace("trigger_reset_", "").replace(".tmp", "")
                cfg.reset_lock_for_ticker(ticker)
                cfg.set_reverse_state(ticker, False, 0)
                cfg.clear_escrow_cash(ticker)
                ledger_data = cfg.get_ledger()
                changed = False
                for lr in ledger_data:
                    if lr.get('ticker') == ticker and lr.get('is_reverse', False):
                        lr['is_reverse'] = False
                        changed = True
                if changed:
                    cfg._save_json(cfg.FILES["LEDGER"], ledger_data)
                asyncio.create_task(context.bot.send_message(chat_id, f"🔓 <b>[{ticker}] 웹앱 리모컨: 잠금 및 리버스 강제 해제!</b>", parse_mode='HTML'))


        # 🧪 [old_main.py 레퍼런스] 수집 단계에서는 락을 잡지 않고 자유롭게 병렬 실행
        # 🧪 [old_main.py 레퍼런스] 명확한 분기 처리에 의한 부하 분산 및 단순화
        try:
            # 🚀 [V23.3] 명령어 수신함 우선 체크 (IPC)
            await check_web_triggers(mode, cfg, broker, strategy, cfg.get_active_tickers(), context)
            
            # 1. 데이터 수집 (주말 포함 상시 동작 - UI 가용성 확보)
            cash, holdings = broker.get_account_balance()
            if holdings is not None:
                if is_weekend:
                    status_text = "⛔ 주말 휴면 중"
                else:
                    status_text = "⛔ 장마감"
                    if status_code == "PRE": status_text = "🌅 프리마켓"
                    elif status_code == "REG": status_text = "🔥 정규장"
                    elif status_code == "AFTER": status_text = "🌙 애프터마켓"
                
                live_data.update({
                    "market_status": status_text,
                    "dst_info": "🌞 서머타임" if (now_ny.dst() != datetime.timedelta(0)) else "❄️ 겨울철",
                    "cash": cash, "holdings_value": broker.last_holdings_value,
                    "is_trade_active": status_code in ["PRE", "REG"] and not is_weekend
                })

                # 2. 티커별 데이터 수집 (Parallel)
                tickers = cfg.get_active_tickers()
                sem = asyncio.Semaphore(3)
                
                async def _get_ticker_data_safe(t):
                    async with sem:
                        h = holdings.get(t, {'qty': 0, 'avg': 0})
                        avg = float(h['avg'])
                        qty = int(h['qty'])
                        try:
                            fast_data = await asyncio.to_thread(broker.get_ticker_fast_data, t)
                            if not fast_data: 
                                return t, {"qty": qty, "avg_price": avg, "current_price": avg, "process_status": "📡 데이터 지연"}
                            
                            curr_p = fast_data['current_price']
                            return t, {
                                "current_price": curr_p,
                                "qty": qty, "avg_price": avg,
                                "prev_close": fast_data['prev_close'],
                                "ma_5day": fast_data['ma_5day'],
                                "day_high": fast_data['day_high'],
                                "day_low": fast_data['day_low'],
                                "profit_pct": (curr_p - avg) / avg * 100 if avg > 0 else 0,
                                "seed": cfg.get_active_seed(t),
                                "ratio": cfg.get_ratio(t),
                                "process_status": "💤 휴면" if is_weekend else ("🔥 가동중" if status_code in ["PRE", "REG"] else "📡 감시중")
                            }
                        except Exception: 
                            return t, {"qty": qty, "avg_price": avg, "current_price": avg}

                # ⏱️ 30초 타임아웃 보호
                try:
                    async with asyncio.timeout(30):
                        results = await asyncio.gather(*[_get_ticker_data_safe(t) for t in tickers])
                except asyncio.TimeoutError: results = []

                for t, data in results: live_data["tickers"][t] = data
                
                # 💰 [V24] 자산 합산 보정 로직 (증권사 API 0 반환 대비 방어 코드)
                total_h_val = sum(float(d.get('qty', 0)) * float(d.get('current_price', 0)) for _, d in results if d.get('qty', 0) > 0)
                if total_h_val > 0:
                    live_data["holdings_value"] = total_h_val
                elif live_data.get("holdings_value", 0) <= 0:
                     live_data["holdings_value"] = total_h_val

                # 🎯 전략 실행/계산 루프 (24시간 동작 - 별값/방어선 표시 유지)
                available_cash = cash
                if not is_weekend and status_code in ["PRE", "REG"] and not is_morning_sync_window:
                    _, allocated_cash_map, force_turbo_off = get_budget_allocation(cash, holdings, tickers, cfg)
                    available_cash_map = allocated_cash_map
                else:
                    available_cash_map = {t: 0 for t in tickers}
                    force_turbo_off = False

                for t, data in results:
                    try:
                        curr_p = data.get('current_price', 0)
                        if curr_p <= 0: continue
                        h = holdings.get(t, {'qty': 0, 'avg': 0})
                        # 🧪 [V23.3] 주말/장마감 시에도 '계산용' plan은 생성하여 UI에 전달
                        plan = strategy.get_plan(
                            t, curr_p, float(h['avg']), int(h['qty']), data.get('prev_close', 0), 
                            ma_5day=data.get('ma_5day', 0), market_type=status_code, 
                            available_cash=available_cash_map.get(t, 0), force_turbo_off=force_turbo_off
                        )
                        live_data["tickers"][t].update(plan)
                        
                        # 실제 주문은 장중에만 실행
                        if not is_weekend and status_code in ["PRE", "REG"] and not is_morning_sync_window:
                            if plan and not cfg.is_locked(t, status_code):
                                orders = plan.get('core_orders', []) + plan.get('bonus_orders', [])
                                if orders:
                                    async with tx_lock:
                                        msg = f"🚀 <b>[{t}] {status_text} 전략 주문 실행</b>\n"
                                        for o in orders:
                                            res = broker.send_order(t, o['side'], o['qty'], o['price'], o['type'])
                                            msg += f"{'✅' if res.get('rt_cd')=='0' else '❌'} {o['side']} {o['qty']}주\n"
                                            await asyncio.sleep(0.1)
                                        cfg.set_lock(t, status_code)
                                        if bot: await context.bot.send_message(cfg.get_chat_id(), msg, parse_mode='HTML')
                    except Exception as e: logging.error(f"🚨 [{t}] 전략 에러: {e}")
            else:
                live_data["market_status"] = "📡 통신 지연 (API)"
        except Exception as e:
            logging.error(f"⚠️ [{mode}] 동기화 루프 내부 에러: {e}")
            live_data["market_status"] = "📡 시스템 점검 중"
    except Exception as outer_e:
        logging.error(f"🚨 [{mode}] 치명적 에러: {outer_e}")
        # [V23.5] 수동 동기화 응답 업데이트 (진행 중인 경우만 피드백)
        if live_data.get("last_manual_sync") and live_data["last_manual_sync"].get("status") == "PROCESSING":
            live_data["last_manual_sync"]["status"] = "SUCCESS"
            live_data["last_manual_sync"]["msg"] = "동기화 완료! 장부가 최신화되었습니다."
            live_data["last_manual_sync"]["timestamp"] = time.time()

        # 🛡️ [V23.3 Safety Net] 어떤 경우에도 파일 기록 (Data Stale 방어)
        try:
            L_FILE = cfg._get_file_path("LIVE_STATUS")
            with open(L_FILE + ".tmp", 'w', encoding='utf-8') as f:
                json.dump(live_data, f, ensure_ascii=False, indent=4)
            os.replace(L_FILE + ".tmp", L_FILE)
            update_task_status(mode, "sync", "done")
            if current_phase != "sync": update_task_status(mode, current_phase, "done")
        except: pass

async def check_web_triggers(mode, cfg, broker, strategy, tickers, context):
    """🚀 [V23.3] 명령어 수신함: 웹 대시보드에서 보낸 명령 파일(.tmp)을 감시 및 처리"""
    import glob
    base_dir = cfg._get_base_dir()
    
    # 1. 수동 실행 (Force Exec: 현재 사이클에서 즉시 실행 유도)
    for f_path in glob.glob(os.path.join(base_dir, "trigger_exec_*.tmp")):
        ticker = os.path.basename(f_path).replace("trigger_exec_", "").replace(".tmp", "")
        logging.info(f"🔥 [Web-Trigger] {ticker} 수동 알고리즘 강제 실행 명령 수신!")
        cfg.reset_lock_for_ticker(ticker) # 잠금 해제하여 즉시 주문 나가게 함
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
            
        new_broker = KoreaInvestmentBroker(k, s, c, p, is_real=new_mode)
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
    if not is_market_open(): return
    
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
    cfg.record_event("MOCK-LOC", "SUCCESS", f"종가 매매 {success_count}건 실행 완료")
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')

async def scheduled_regular_trade(context):
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.datetime.now(kst)
    target_hour, _ = get_target_hour()
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
    cfg.add_notification("STATUS", f"🔥 [{target_hour}:30] 정규장 주문 스케줄 실행 ({latest_version})")
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
                    if res.get('rt_cd') != '0': all_success[t] = False
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
                    cfg.add_notification("SUCCESS", f"[{t}] 정규장 필수 주문 체결 시도 완료 (잠금)")
                    msgs[t] += "\n🔒 <b>필수 주문 정상 전송 완료 (잠금 설정됨)</b>"
                elif not all_success[t]:
                    cfg.add_notification("WARNING", f"[{t}] 일부 필수 주문 전송 실패 확인")
                    msgs[t] += "\n⚠️ <b>일부 필수 주문 실패 (매매 잠금 보류)</b>"
                else:
                    cfg.set_lock(t, "REG")
                    cfg.add_notification("SUCCESS", f"[{t}] 보너스 줍줍 주문 전송 완료")
                    msgs[t] += "\n🔒 <b>보너스 줍줍 주문만 전송 완료 (잠금 설정됨)</b>"
                
                cfg.record_event("TRADE", "SUCCESS" if all_success[t] else "WARNING", f"[{t}] 정규장 주문 집행", 
                                   details=f"결과: {len(plans[t].get('core_orders', []))}건 전송 ({'성공' if all_success[t] else '일부실패'})")
                await context.bot.send_message(chat_id=chat_id, text=msgs[t], parse_mode='HTML')

    try:
        update_task_status(app_data['mode'], "reg", "running")
        await asyncio.wait_for(_do_regular_trade(), timeout=300.0) 
        update_task_status(app_data['mode'], "reg", "done")
    except Exception as e:
        update_task_status(app_data['mode'], "reg", "error")
        cfg.add_notification("ERROR", f"❌ 정규장 매매 엔진 오류: {str(e)[:50]}")
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
        cfg.add_notification("SUCCESS", f"장부 자동 동기화 완료 ({', '.join(success_tickers)})")
        cfg.record_event("SYNC", "SUCCESS", f"자동 동기화 완료 ({len(success_tickers)}종목)")
        async with context.job.data['tx_lock']:
            _, holdings = context.job.data['broker'].get_account_balance()
        await bot._display_ledger(success_tickers[0], chat_id, context, message_obj=status_msg, pre_fetched_holdings=holdings)
    else:
        cfg.add_notification("INFO", "장부 자동 동가화 시도 (변경 사항 없음)")
        cfg.record_event("SYNC", "SUCCESS", "자동 동기화 (변경사항 없음)")
        await status_msg.edit_text(f"📝 <b>[{time_str}] 장부 동가화 완료 (표시할 항목 없음)</b>", parse_mode='HTML')
    
    update_task_status(mode, "sync", "done")

async def scheduled_analytics_snapshot(context):
    app_data = context.job.data
    cfg, broker, tx_lock = app_data['cfg'], app_data['broker'], app_data['tx_lock']
    chat_id = context.job.chat_id
    try:
        async with tx_lock:
            cash, holdings = await asyncio.to_thread(broker.get_account_balance)
        if holdings is None: return
        holdings_value = 0.0
        for t in cfg.get_active_tickers():
            h = holdings.get(t, {'qty': 0, 'avg': 0})
            if h['qty'] > 0:
                curr_p = await asyncio.to_thread(broker.get_current_price, t)
                holdings_value += (h['qty'] * curr_p)
        update_task_status(app_data['mode'], "after", "running")
        snap = cfg.record_daily_snapshot(cash, holdings_value)
        
        msg = (
            f"📊 <b>[Daily Analytics Snapshot]</b>\n"
            f"📅 날짜: {snap['date']}\n"
            f"💵 현금: ${snap['cash']:,.2f}\n"
            f"📈 주식: ${snap['holdings']:,.2f}\n"
            f"💰 총자산: ${snap['total']:,.2f}\n"
            f"✅ 성과 분석 데이터가 기록되었습니다."
        )
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
        cfg.record_event("SNAPSHOT", "SUCCESS", f"일일 분석 스냅샷 저장 완료 (${snap['total']:,.0f})")
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

    target_hour, season_msg = get_target_hour()
    print("=" * 50)
    print(f"🚀 Infinity Quant Hub V23.1 (Dual-Core Architecture)")
    print(f"📅 날짜 정보: {season_msg}")
    print("=" * 50)

    # 🌅 [Unified Hub] 통합 웹 서버 독립 프로세스로 가동 (Port 5050)
    try:
        import sys
        current_dir = os.path.dirname(os.path.abspath(__file__))
        web_server_path = os.path.join(current_dir, "web_server.py")
        
        # [V23.6] 모든 웹 서버 로그는 자동으로 bot.log에 기록됩니다.
        subprocess.Popen([sys.executable, "-u", web_server_path], 
                         cwd=current_dir)
        print("🚀 [HUB] Web Dashboard Server (Port 5050) started successfully.")
    except Exception as e:
        print(f"❌ [HUB] Error starting Web Server: {e}")

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

    # 3. 병렬 엔진 가동
    print(f"✨ 총 {len(engines)}개의 엔진이 병렬로 가동됩니다.")
    await asyncio.gather(*(eng.start() for eng in engines))
    
    # 무한 대기
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 프로그램을 안전하게 종료합니다.")
