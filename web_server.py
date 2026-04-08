import os
import json
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import datetime
import asyncio
from pydantic import BaseModel
from config import ConfigManager
from simulation_engine import MasterSimulator, run_parameter_sweep, MarketAwareAdvisor
from market_intelligence import MarketIntelligence # 🛰️ 신규 시장 지능 모듈
import logging

# 🔎 [V27-Unified] 로깅은 메인 엔진(main.py)의 설정을 그대로 상속받습니다.

DATA_DIR = "/home/jmyoon312/data"
if os.name == 'nt':
    DATA_DIR = "data"
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")

app = FastAPI(title="Infinity Quant Hub API")

# 🕒 [V23.2 TrueSync] 리얼타임 서버 시간 전용 엔드포인트
@app.get("/api/server-time")
async def get_server_time():
    """파일 스냅샷 지연 없이 서버의 OS 시계를 즉시 반환 (ISO 8601 표준 규격)"""
    now = datetime.datetime.now()
    return {
        "status": "ok",
        "server_time": now.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    }

# React(Vite) 프론트엔드 포트(3050)와의 통신을 위한 CORS 허용 세팅
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- [V23.1 Dual-Core] 경로 및 모드 관리 -----------------
def get_cfg(mode="real"):
    return ConfigManager(is_real=(mode=="real"))

def get_live_file(mode="real"):
    cfg = get_cfg(mode)
    return cfg._get_file_path("LIVE_STATUS")

# 봇 설정 파일 연동 (기존 하드코딩 제거)

def load_json(filepath):
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}

# ----------------- [보안 추가] 로그인 인증 엔드포인트 -----------------
class AuthRequest(BaseModel):
    user_id: str
    password: str

def get_valid_users():
    """accounts.json에서 계정 정보를 읽어옵니다. 없으면 기본 관리자 생성"""
    if not os.path.exists(ACCOUNTS_FILE):
        default_accounts = {
            "pipiosbot": "admin1234!",
            "hambot": "admin1234!",
            "infinity": "v22.2!"
        }
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_accounts, f, indent=4)
        except:
            pass
        return default_accounts
    return load_json(ACCOUNTS_FILE)

@app.post("/api/auth")
def authenticate(req: AuthRequest):
    """프론트엔드에서 전달받은 ID/PW를 검증하고 세션 토큰을 발급합니다."""
    VALID_USERS = get_valid_users()
    if req.user_id in VALID_USERS and VALID_USERS.get(req.user_id) == req.password:
        return {"status": "ok", "token": "infinity_v22_secure_token_9999_abxc"}
    
    raise HTTPException(status_code=401, detail="보안 암호 또는 총사령관 ID가 일치하지 않습니다.")
# -------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    """백엔드 서버 헬스 체크용 엔드포인트"""
    return {"status": "ok", "message": "FastAPI is running flawlessly on port 5050"}

# 🛡️ [V27] 프로세스 통합으로 인해 부모 감시 워치독이 제거되었습니다.

@app.get("/api/config")
def get_config_api(mode: str = "real"):
    """봇의 제어용 파라미터(시드, 버전 등) 및 설정 반환"""
    cfg = get_cfg(mode)
    tickers = cfg.get_active_tickers()
    turbo = cfg.get_turbo_mode()
    engine_status = cfg.get_engine_status()
    
    config = {
        "ACTIVE_TICKERS": tickers,
        "TURBO_MODE": turbo,
        "ENGINE_STATUS": engine_status,
        "SHADOW_STRIKE": cfg.get_shadow_strike(),
        "SHADOW_BOUNCE": cfg.get_shadow_bounce(),
        "SNIPER_DEFENSE": cfg.get_sniper_defense(),
        "ENGINE_VERSION": cfg.get_version(tickers[0]) if tickers else "V24",
        "MODE": mode.upper()
    }
    for t in tickers:
        config[t] = {
            "seed": cfg.get_seed(t),
            "split": cfg.get_split_count(t),
            "target_pct": cfg.get_target_profit(t),
            "compound_rate": cfg.get_compound_rate(t),
            "version": cfg.get_version(t),
            "portfolio_ratio": cfg.get_portfolio_ratio(t),
        }
    return {"status": "ok", "config": config, "is_real": cfg.is_real}

@app.post("/api/settings/engine-status")
def update_engine_status(req: dict):
    """엔진 가동/정지 상태를 토글합니다. (V23.1)"""
    mode = req.get("mode", "real")
    val = req.get("value") == True
    cfg = get_cfg(mode)
    cfg.set_engine_status(val)
    return {"status": "ok", "mode": mode, "is_on": val}

@app.get("/api/logs")
def get_logs_api(mode: str = "real"):
    # 🚀 [V33.1] 통합 데이터 폴더 내 알림 피드 (notifications.json)
    notif_path = os.path.join(DATA_DIR, mode, "notifications.json")
    if os.path.exists(notif_path):
        try:
            with open(notif_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {"status": "ok", "logs": list(reversed(data))}
        except: pass
    
    # 2차 순위: 기존 시스템 로그 (Fallback)
    import glob
    log_dir = os.path.join("logs", mode)
    log_files = sorted(glob.glob(os.path.join(log_dir, "bot_app_*.log")), reverse=True)
    if not log_files:
        return {"status": "ok", "logs": ["기록된 로그 파일이 없습니다."]}
        
    try:
        with open(log_files[0], 'r', encoding='utf-8') as f:
            lines = f.readlines()
            recent_logs = [line.strip() for line in lines[-100:]]
            return {"status": "ok", "logs": recent_logs}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/logs/clear")
def clear_logs_api(req: dict):
    """지정된 모드(mock/real)의 알림 내역을 영구히 초기화합니다."""
    mode = req.get("mode", "real")
    
    notif_path = os.path.join(DATA_DIR, mode, "notifications.json")
    if os.path.exists(notif_path):
        try:
            with open(notif_path, 'w', encoding='utf-8') as f:
                json.dump([], f)
        except: pass
    return {"status": "ok"}

@app.post("/api/events/clear")
def clear_events_api(req: dict):
    """지정된 모드(mock/real)의 운영 아카이브(이벤트 로그)를 영구히 초기화합니다."""
    mode = req.get("mode", "real")
    cfg = get_cfg(mode)
    cfg.clear_events()
    return {"status": "ok"}

@app.get("/api/ledger")
def get_ledger_api(mode: str = "real"):
    """실시간 동기화된 데이터(live_status.json) 또는 기본 장부를 반환"""
    cfg = get_cfg(mode)
    live_file = cfg._get_file_path("LIVE_STATUS")
    
    if os.path.exists(live_file):
        data = load_json(live_file)
        # 🔥 [V23.1] 모드별 자산 데이터를 0이 아닌 실제 값으로 반환하도록 경로 정합성 확보
        return {"status": "ok", "ledger": data.get("tickers", {}), "account": data}
    
    ledger = cfg.get_ledger()
    return {"status": "ok", "ledger": ledger}

@app.get("/api/refresh")
def force_refresh_api(mode: str = "mock"):
    """수동 새로고침 시 봇 엔진이 즉시 파일을 갱신하도록 트리거 파일 생성"""
    cfg = get_cfg(mode)
    
    # 🌙 [V24 Stable] 휴장 기간 수동 동기화 차단 (데이터 오염 방지)
    # [V26.9] 사용자 요청으로 수동 갱신은 항시 허용 (기록 보정 목적)
    # if cfg.is_market_open() != "OPEN":
    #     return {"status": "error", "message": "🚫 휴장 데이터 보호 모드(Snapshot) 가동 중입니다. 주말 및 야간에는 수동 갱신이 제한됩니다."}
    
    try:
        # [V23.5] 상태 기록 (동기화 시작 알림용)
        l_status = load_json(cfg._get_file_path("LIVE_STATUS"))
        if not l_status: l_status = {"tickers": {}}
        l_status["last_manual_sync"] = {
            "timestamp": time.time(),
            "status": "PROCESSING",
            "msg": "데이터 동기화 진행 중 (약 1~2초 소요)..."
        }
        # 파일에 직접 기록 (엔진이 즉시 감지하도록 유도)
        with open(cfg._get_file_path("LIVE_STATUS"), 'w', encoding='utf-8') as f:
            json.dump(l_status, f, ensure_ascii=False, indent=4)

        TRIGGER_FILE = os.path.join(cfg._get_base_dir(), "refresh_needed.tmp")
        with open(TRIGGER_FILE, 'w') as f:
            f.write("1")
        return {"status": "ok", "message": f"[{mode.upper()}] 실시간 데이터 동기화 명령이 전달되었습니다."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/tickers/{ticker}")
def get_ticker_info(ticker: str, mode: str = "mock"):
    """특정 종목의 상세 장부 및 설정을 브릿징하여 반환"""
    cfg = get_cfg(mode)
    live_file = cfg._get_file_path("LIVE_STATUS")
    
    live = load_json(live_file) if os.path.exists(live_file) else {}
    t_ledger = live.get("tickers", {}).get(ticker, {})
    
    t_cfg = {
        "seed": cfg.get_seed(ticker),
        "split": cfg.get_split_count(ticker),
        "target_pct": cfg.get_target_profit(ticker),
        "version": cfg.get_version(ticker),
    }
    
    return {
        "status": "ok",
        "ticker": ticker,
        "mode": mode,
        "ledger": t_ledger,
        "config": t_cfg
    }

# --- 신규 제어 API (ConfigManager 연동) ---
@app.post("/api/settings/seed")
def update_seed(req: dict):
    mode = req.get("mode", "real")
    cfg = get_cfg(mode)
    action = req.get("action")
    
    force = req.get("force", False)
    
    if action == "rebalance":
        live_file = cfg._get_file_path("LIVE_STATUS")
        live = load_json(live_file) if os.path.exists(live_file) else {}
        
        # 🌐 [V24] 계좌 총 자산 파악 (현금 + 보정된 실시간 보유 주식 합계)
        tickers_data = live.get("tickers", {})
        total_holdings_val = sum(
            float(t_val.get("qty", 0)) * float(t_val.get("current_price", 0))
            for t_val in tickers_data.values()
            if t_val.get("qty", 0) > 0
        )
        total_asset = float(live.get("cash", 0)) + total_holdings_val
        
        active_tickers = cfg.get_active_tickers()
        ratios = cfg._load_json("PORTFOLIO_RATIO", {})
        
        if not active_tickers:
            return {"status": "error", "message": "활성화된 종목이 없습니다."}
            
        for t in active_tickers:
            # 🎯 사용자가 설정한 비중이 있으면 사용, 없으면 균등 분배
            ratio = float(ratios.get(t, 1.0 / len(active_tickers)))
            new_seed = total_asset * ratio
            
            # 🎯 기본값은 '예약(Reserved)' 시드 업데이트 (다음 회차 적용)
            cfg.set_seed(t, new_seed)
            if force:
                cfg.set_active_seed(t, new_seed) # 🔥 강제 즉시 적용
            
        # ✅ 즉시 동기화 트리거
        cfg._save_file("REFRESH_TRIGGER", str(time.time()))
        
        msg = f"[{mode.upper()}] 총 자산 ${total_asset:,.2f} (현금+주식) 기준, 설정된 비중에 따라 시드 재분배 완료."
        if not force: msg += " (졸업 시점에 새로운 시드가 적용됩니다)"
        return {"status": "ok", "message": msg}
    else:
        ticker = req.get("ticker")
        val = float(req.get("value", 0))
        if ticker and val > 0:
            cfg.set_seed(ticker, val)
            if force:
                cfg.set_active_seed(ticker, val)
            return {"status": "ok"}
    return {"status": "error"}

@app.post("/api/settings/split")
def update_split(req: dict):
    mode = req.get("mode", "real")
    cfg = get_cfg(mode)
    cfg.set_split_count(req.get("ticker"), float(req.get("value", 0)))
    return {"status": "ok"}

@app.post("/api/settings/target")
def update_target(req: dict):
    mode = req.get("mode", "real")
    cfg = get_cfg(mode)
    cfg.set_target_profit(req.get("ticker"), float(req.get("value", 0)))
    return {"status": "ok"}

@app.post("/api/settings/compound")
def update_compound(req: dict):
    mode = req.get("mode", "real")
    cfg = get_cfg(mode)
    cfg.set_compound_rate(req.get("ticker"), float(req.get("value", 0)))
    return {"status": "ok"}

@app.post("/api/settings/version")
def update_version(req: dict):
    mode = req.get("mode", "real")
    cfg = get_cfg(mode)
    cfg.set_version(req.get("ticker"), req.get("value"))
    return {"status": "ok"}

@app.post("/api/settings/mode")
def update_mode(req: dict):
    mode = req.get("mode", "real")
    cfg = get_cfg(mode)
    cfg.set_turbo_mode(req.get("value") == True)
    # 엔진 즉시 동기화 트리거
    try:
        with open(os.path.join(cfg._get_base_dir(), "refresh_needed.tmp"), 'w') as f:
            f.write(str(time.time()))
    except: pass
    return {"status": "ok"}

@app.post("/api/settings/global-strategy")
def update_global_strategy(req: dict):
    """
    🌐 [V25] 통합 전략 제어 엔드포인트 (개별 키 대응)
    """
    mode = req.get("mode", "mock")
    key = req.get("key")
    val = req.get("value")
    cfg = get_cfg(mode)
    
    # 신규 모듈 구조 호환성 유지
    tactics = cfg.get_global_tactics()
    if key in tactics:
        tactics[key] = (val == True)
        cfg.set_global_tactics(tactics)
    
    # 레거시 호환성 및 전역 버전 관리
    if key == "version":
        # 🌐 [V25] 베이스 전략 변경 시 모든 가용 종목에 즉시 반영 (영속성 해결)
        tickers = ['SOXL', 'TQQQ', 'UPRO', 'TECL', 'QLD', 'SPXL', 'FAS', 'LABU', 'FNGU', 'TNA']
        for t in tickers:
            cfg.set_version(t, val)
        
        # 🔥 [V26.7] 상황실(UI) 버전 표시 즉시 동기화 (live_status.json 강제 업데이트)
        live_file = cfg._get_file_path("LIVE_STATUS")
        logging.info(f"🔄 [SYNC] Updating global strategy to {val} for mode: {mode}")
        if os.path.exists(live_file):
            try:
                live_data = load_json(live_file)
                if "tickers" in live_data:
                    for t in live_data["tickers"]:
                        live_data["tickers"][t]["version"] = val
                        # 🚀 [V26.8] 슬롯 명칭도 즉시 동기화 (Instant UI Feedback)
                        slots = live_data["tickers"][t].get("slots", {})
                        for sid in ["slot_1", "slot_2", "slot_3", "slot_4", "slot_5"]:
                            if sid in slots:
                                old_desc = slots[sid]["desc"]
                                # 버전 문자열 교체 (예: V13 -> V14)
                                if ":" in old_desc:
                                    prefix, suffix = old_desc.split(":", 1)
                                    if " " in prefix:
                                        p1, p2 = prefix.rsplit(" ", 1)
                                        new_desc = f"{p1} {val}:{suffix}"
                                    else:
                                        new_desc = f"{val}:{suffix}"
                                    
                                    # [V14 대응] 2차 슬롯 특수 명칭 처리
                                    if val == "V14" and sid == "slot_2":
                                        new_desc = "[2차] 가변보류(Bypass)"
                                    elif val == "V13" and sid == "slot_1":
                                        new_desc = "[1차] V13:평단매수"
                                    elif val == "V14" and sid == "slot_1":
                                        new_desc = "[1차] V14:평단집중"
                                        
                                    slots[sid]["desc"] = new_desc
                        
                    with open(live_file, 'w', encoding='utf-8') as f:
                        json.dump(live_data, f, ensure_ascii=False, indent=4)
                logging.info(f"✅ [SYNC] live_status.json updated successfully.")
            except Exception as e:
                logging.error(f"❌ Error syncing live_status version: {e}")
                
        # 엔진 즉시 동기화 트리거 생성
        try:
            with open(os.path.join(cfg._get_base_dir(), "refresh_needed.tmp"), 'w') as f:
                f.write(str(time.time()))
        except: pass
                
    elif key == "turbo":
        cfg.set_turbo_mode(val == True)
    elif key == "shadow":
        cfg.set_shadow_strike(val == True)
    elif key == "sniper":
        cfg.set_sniper_defense(val == True)
    elif key == "shadow_bounce":
        cfg.set_shadow_bounce(float(val))
    elif key == "sniper_drop":
        cfg.set_sniper_drop(float(val))
    elif key == "jupjup_density":
        cfg.set_jupjup_density(int(val))
    elif key == "rev_day":
        cfg.set_rev_day(int(val))
    elif key == "is_reverse":
        current_tactics = cfg.get_global_tactics()
        current_tactics["is_reverse"] = (val == True)
        cfg.set_global_tactics(current_tactics)
    elif key == "vix_aware":
        current_tactics = cfg.get_global_tactics()
        current_tactics["vix_aware"] = (val == True)
        cfg.set_global_tactics(current_tactics)
    elif key == "trend_filter":
        current_tactics = cfg.get_global_tactics()
        current_tactics["trend_filter"] = (val == True)
        cfg.set_global_tactics(current_tactics)
    elif key == "vwap_dominance":
        current_tactics = cfg.get_global_tactics()
        current_tactics["vwap_dominance"] = (val == True)
        cfg.set_global_tactics(current_tactics)
    
    return {"status": "ok", "key": key, "value": val}

@app.get("/api/settings/tactics")
def get_tactics_api(mode: str = "real"):
    """🌐 [V25] 글로벌 전술 설정 뭉치 반환"""
    cfg = get_cfg(mode)
    return {"status": "ok", "tactics": cfg.get_global_tactics()}

@app.post("/api/settings/tactics")
def update_tactics_api(req: dict):
    """🌐 [V25] 글로벌 전술 설정 뭉치 업데이트"""
    mode = req.get("mode", "real")
    tactics = req.get("tactics", {})
    cfg = get_cfg(mode)
    cfg.set_global_tactics(tactics)
    return {"status": "ok", "tactics": tactics}

@app.post("/api/settings/tickers")
def update_tickers(req: dict):
    mode = req.get("mode", "mock")
    cfg = get_cfg(mode)
    cfg.set_active_tickers(req.get("tickers", []))
    return {"status": "ok"}

@app.post("/api/settings/stock-split")
def apply_stock_split(req: dict):
    mode = req.get("mode", "mock")
    cfg = get_cfg(mode)
    cfg.apply_stock_split(req.get("ticker"), float(req.get("ratio", 1.0)))
    return {"status": "ok"}

@app.post("/api/settings/portfolio-ratios")
def update_portfolio_ratios(req: dict):
    """모든 활성 종목의 포트폴리오 비중을 한꺼번에 업데이트합니다."""
    mode = req.get("mode", "real")
    ratios = req.get("ratios", {}) # { "SOXL": 0.5, "TQQQ": 0.5 }
    cfg = get_cfg(mode)
    
    for ticker, val in ratios.items():
        cfg.set_portfolio_ratio(ticker, float(val))
    return {"status": "ok"}

# --- 신규 액션 API (IPC 통신 브릿지) ---
@app.post("/api/action/exec")
def action_exec(req: dict):
    mode = req.get("mode", "mock")
    ticker = req.get("ticker", "")
    cfg = get_cfg(mode)
    if ticker:
        with open(os.path.join(cfg._get_base_dir(), f"trigger_exec_{ticker}.tmp"), 'w') as f:
            f.write(str(time.time()))
        return {"status": "ok"}
    return {"status": "error"}

@app.post("/api/action/record")
def action_record(req: dict):
    mode = req.get("mode", "mock")
    ticker = req.get("ticker", "ALL")
    cfg = get_cfg(mode)
    
    # 🌙 [V24 Stable] 휴면 시 장부 보정(Record) 차단
    # [V26.9] 사용자 요청으로 수동 보정은 항시 허용 (실시간 잔고 확인 목적)
    # if cfg.is_market_open() != "OPEN":
    #     return {"status": "error", "message": "🚫 주말 및 휴장일에는 수동 장부 갱신(Record)이 제한됩니다."}
    
    try:
        # [V23.5] 상태 기록
        l_status = load_json(cfg._get_file_path("LIVE_STATUS"))
        if not l_status: l_status = {"tickers": {}}
        l_status["last_manual_sync"] = {
            "timestamp": time.time(),
            "status": "PROCESSING",
            "msg": f"[{ticker}] 장부 보정 및 동기화 진행 중..."
        }
        with open(cfg._get_file_path("LIVE_STATUS"), 'w', encoding='utf-8') as f:
            json.dump(l_status, f, ensure_ascii=False, indent=4)

        with open(os.path.join(cfg._get_base_dir(), f"trigger_record_{ticker}.tmp"), 'w') as f:
            f.write(str(time.time()))
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/action/sell")
def action_sell(req: dict):
    mode = req.get("mode", "mock")
    ticker = req.get("ticker", "")
    qty = req.get("qty", 0)
    cfg = get_cfg(mode)
    
    if ticker and qty > 0:
        # [V26.6] 수동 즉시 매매 트리거 생성
        trigger_path = os.path.join(cfg._get_base_dir(), f"trigger_sell_{ticker}_{qty}.tmp")
        with open(trigger_path, 'w') as f:
            f.write(str(time.time()))
        return {"status": "ok"}
    return {"status": "error", "message": "필수 파라미터(ticker, qty)가 누락되었습니다."}

@app.get("/api/ledger/explorer")
def get_ledger_explorer_api(mode: str = "mock"):
    """장부 탐색기를 위한 통합 거래 내역 반환 (활성 + 과거)"""
    cfg = get_cfg(mode)
    return {"status": "ok", "ledger": cfg.get_ledger_explorer_data()}

@app.get("/api/ledger/cycles")
def get_ledger_cycles_api(mode: str = "mock"):
    """장부 분석을 위한 사이클(매수~졸업) 단위 요약 데이터 반환"""
    cfg = get_cfg(mode)
    return {"status": "ok", "cycles": cfg.get_cycle_analytics()}

@app.get("/api/ledger/stats")
def get_ledger_stats_api(mode: str = "real"):
    """📊 [V29.7] 장부의 핵심 성과 지표(PnL, 승률, 세금 등) 통합 반환"""
    try:
        cfg = get_cfg(mode)
        stats = cfg.get_ledger_stats()
        return {"status": "ok", "stats": stats}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/ledger/export/excel")
async def export_ledger_excel_api(mode: str = "real"):
    """📁 [V29.7] 전문가용 엑셀 리포트 생성 및 다운로드"""
    try:
        cfg = get_cfg(mode)
        
        # 임시 파일 경로 생성
        import tempfile
        temp_dir = tempfile.gettempdir()
        file_name = f"Infinity_Trading_Report_{mode.upper()}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        output_path = os.path.join(temp_dir, file_name)
        
        # 엑셀 파일 생성 실행
        cfg.export_ledger_excel(output_path)
        
        # 파일 전송 (다운로드 후 서버에서는 파일 유지 - 관리자가 확인 가능하게 /tmp/ 활용)
        return FileResponse(
            path=output_path,
            filename=file_name,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        import traceback
        logging.error(f"❌ Excel Export Error: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": f"엑셀 생성 실패: {str(e)}"}


@app.post("/api/action/implant")
def action_implant(req: dict):
    mode = req.get("mode", "mock")
    ticker = req.get("ticker", "")
    cfg = get_cfg(mode)
    if ticker:
        with open(os.path.join(cfg._get_base_dir(), f"trigger_implant_{ticker}.tmp"), 'w') as f:
            f.write(str(time.time()))
        return {"status": "ok", "message": f"[{mode.upper()}] 전략 이식 명령 하달 완료."}
    return {"status": "error"}

@app.post("/api/action/reset")
def action_reset(req: dict):
    mode = req.get("mode", "mock")
    ticker = req.get("ticker", "")
    cfg = get_cfg(mode)
    if ticker:
        with open(os.path.join(cfg._get_base_dir(), f"trigger_reset_{ticker}.tmp"), 'w') as f:
            f.write(str(time.time()))
        return {"status": "ok"}
    return {"status": "error"}

@app.get("/api/analytics")
def get_analytics_api(mode: str = "mock", category: str = None, start_date: str = None, end_date: str = None):
    cfg = get_cfg(mode)
    data = cfg.get_analytics_data()
    events = data.get("events", [])
    
    # 🔍 [V33 Search] 백엔드 필터링 로직 추가
    if category:
        events = [ev for ev in events if ev.get("category") == category.upper()]
    
    if start_date:
        # date 형식: "04/02" (MM/DD) 또는 "2024-04-02" 등 유연하게 대응 필요
        # 현재는 MM/DD 형식이므로 간단 버전으로 필터링
        events = [ev for ev in events if ev.get("date") >= start_date]

    if end_date:
        events = [ev for ev in events if ev.get("date") <= end_date]

    return {
        "status": "ok", 
        "events": events, 
        "analytics": data
    }

@app.post("/api/capital")
def add_capital_api(req: dict):
    mode = req.get("mode", "mock")
    cfg = get_cfg(mode)
    amount = float(req.get("amount", 0))
    flow_type = req.get("type", "DEPOSIT")
    if amount != 0:
        cfg.add_capital_flow(amount, flow_type)
        return {"status": "ok"}
    return {"status": "error"}

@app.get("/api/history")
def get_history_api(mode: str = "mock"):
    cfg = get_cfg(mode)
    return {"status": "ok", "history": cfg.get_history()}

@app.post("/api/simulation/run")
def run_simulation(req: dict):
    """지정된 기간과 종목에 대해 무한매수법 시뮬레이션을 수행합니다 (Master Edition)."""
    is_portfolio = req.get("is_portfolio", False)
    tickers_weight = req.get("tickers_weight", {"TQQQ": 1.0})
    if not is_portfolio:
        ticker = req.get("ticker", "TQQQ")
        tickers_weight = {ticker: 1.0}
        
    start_date = req.get("start_date", "2010-02-11")
    end_date = req.get("end_date", datetime.datetime.now().strftime("%Y-%m-%d"))
    seed = float(req.get("seed", 10000))
    split = int(req.get("split", 40))
    target = float(req.get("target", 10.0))
    
    # 전략 모듈 구성
    version = req.get("version", "V14")
    modules = {
        "turbo": req.get("use_turbo", True),
        "shadow": req.get("use_shadow", True),
        "shield": req.get("use_shield", True),
        "sniper": req.get("use_sniper", True),
        "emergency": req.get("use_emergency", True),
        "jupjup": req.get("use_jupjup", False),
        "v_shield": req.get("use_v_shield", False),
        "micro_bounce": req.get("use_micro_bounce", False),
        "smart_jup": req.get("use_smart_jup", False),
        "trend_filter": req.get("use_trend_filter", False),
        "vix_aware": req.get("use_vix_aware", False),
        "vol_harvest": req.get("use_vol_harvest", False),
        "vwap_dominance": req.get("use_vwap_dominance", False),
        "v_rev": req.get("use_v_rev", False),
    }
    
    global_config = {
        "split": split,
        "target": target,
        "version": version,
        "shadow_bounce": float(req.get("shadow_bounce", 1.5)),
        "use_tax": req.get("use_tax", True),
        "modules": modules
    }
    
    try:
        # 마스터 시뮬레이터 가동
        sim = MasterSimulator(tickers_weight, start_date, end_date, seed, global_config)
        
        # 시뮬레이션 실행 (리밸런싱 타입 포함)
        rebalance_type = req.get("rebalance_type", "GRADUATION")
        result = sim.run(rebalance_type=rebalance_type)
        
        # [V8.7] 지표 개입 분석 데이터 추출
        intervention = result.get('summary', {}).get('intervention_stats', {})
        
        # [V26.3] NumPy 등 특수 형식을 표준 JSON 규격으로 변환
        safe_result = to_json_serializable(result)
        safe_intervention = to_json_serializable(intervention)
        
        return {
            "status": "success",
            "result": safe_result,
            "intervention": safe_intervention
        }
    except Exception as e:
        import traceback
        logging.error(f"❌ Simulation Error: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": str(e)}

def to_json_serializable(obj):
    """[V26.4] NumPy 및 특수 float 값(NaN, Inf)을 표준 JSON 규격으로 재귀적 변환"""
    import numpy as np
    import math
    import datetime
    
    if isinstance(obj, dict):
        return {k: to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_json_serializable(i) for i in obj]
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        # 🚨 [Critical] JSON은 NaN, Infinity를 지원하지 않으므로 None으로 처리
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return to_json_serializable(obj.tolist())
    elif isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj

@app.post("/api/simulation/exhaustive")
async def api_exhaustive_simulation(req: dict):
    """[V8.7] 32가지 모든 전략 조합을 전수 조사하여 최적 경로 도출"""
    try:
        from simulation_engine import run_exhaustive_search, MasterSimulator
        
        # [V26.3 Meta] 분석 시작 로깅
        logging.info("🚀 [API] Starting Exhaustive Search Request...")
        
        # [V29.3 Target-Optimizer] 요청 정보 추출
        tickers_weight = req.get("tickers_weight", {"TQQQ": 0.55, "SOXL": 0.45})
        seed = float(req.get("seed", 10000))
        target_version = req.get("version", "V14")
        
        fixed_modules = {
            "elastic": req.get("use_elastic", False),
            "atr_shield": req.get("use_atr_shield", False)
        }
        
        # 대표 종목 선정 (Mixed인 경우 TQQQ 기준)
        ticker = "TQQQ"
        if isinstance(tickers_weight, dict) and len(tickers_weight) > 0:
            ticker = list(tickers_weight.keys())[0]
            
        config_base = {
            "split": int(req.get("split", 40)),
            "target": float(req.get("target", 10.0)),
            "use_tax": True,
            "modules": {} # 조합 테스트를 위해 빈 슬롯
        }
        
        start_date = "2010-02-11"
        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        ranking = await asyncio.to_thread(
            run_exhaustive_search, ticker, start_date, end_date, seed, config_base, target_version, fixed_modules
        )
        
        # [V26.3 Log-Optimized] 응답 데이터 JSON 표준화 및 로그
        logging.info(f"📊 [API] Calculation Finished. Converting {len(ranking)} items to JSON-SAFE format...")
        
        safe_ranking = to_json_serializable(ranking)
        
        response_data = {
            "status": "success",
            "best_path": safe_ranking[0] if safe_ranking else None,
            "top_candidates": safe_ranking[:5],
            "all_candidates": safe_ranking, # 🛡️ [V29.6] 전체 64개 랭킹 전송
            "analysis_date": end_date
        }
        
        logging.info("✅ [API] Exhaustive search results sent successfully to frontend.")
        return response_data
        
    except Exception as e:
        import traceback
        logging.error(f"❌ Exhaustive Search Error: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": str(e)}

@app.post("/api/simulation/precision")
async def api_precision_run(req: dict):
    """[V29.7] 1분봉 고정 데이터셋 기반 정밀 시뮬레이션 1회 실행"""
    from simulation_engine import PrecisionMasterSimulator
    try:
        ticker = req.get("ticker", "SOXL")
        seed = float(req.get("seed", 10000))
        version = req.get("version", "V14")
        
        # UI에서 보낸 개별 use_xxx 파라미터를 modules 딕셔너리로 통합
        modules = {
            "turbo": req.get("use_turbo", True),
            "shadow": req.get("use_shadow", True),
            "shield": req.get("use_shield", True),
            "sniper": req.get("use_sniper", True),
            "emergency": req.get("use_emergency", True),
            "jupjup": req.get("use_jupjup", False),
            "v_shield": req.get("use_v_shield", False),
            "micro_bounce": req.get("use_micro_bounce", False),
            "smart_jup": req.get("use_smart_jup", False),
            "trend_filter": req.get("use_trend_filter", False),
            "vix_aware": req.get("use_vix_aware", False),
            "vol_harvest": req.get("use_vol_harvest", False),
        }
        
        cfg = {
            "split": int(req.get("split", 20)),
            "target": float(req.get("target", 12.0)),
            "version": version,
            "modules": modules,
            "use_tax": True,
            "sniper_drop": float(req.get("sniper_drop", 1.5))
        }
        
        tickers_weight = req.get("tickers_weight", {ticker: 1.0})
        sim = PrecisionMasterSimulator(tickers_weight, seed, cfg)
        result = await asyncio.to_thread(sim.run)
        
        return {
            "status": "success",
            "result": to_json_serializable(result),
            "intervention": result["summary"].get("intervention_stats", {})
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/simulation/precision-exhaustive")
async def api_precision_exhaustive(req: dict):
    """[V29.7] 1분봉 고정 데이터셋 기반 128개 전술 조합 전수 조사"""
    from simulation_engine import run_precision_exhaustive_search
    try:
        ticker = req.get("ticker", "SOXL")
        seed = float(req.get("seed", 10000))
        version = req.get("version", "V14")
        
        config_base = {
            "split": int(req.get("split", 20)),
            "target": float(req.get("target", 12.0)),
            "use_tax": True
        }
        tickers_weight = req.get("tickers_weight", {ticker: 1.0})
        
        results = await asyncio.to_thread(
            run_precision_exhaustive_search, tickers_weight, seed, config_base, version
        )
        
        return {
            "status": "success",
            "best_path": to_json_serializable(results[0]) if results else None,
            "top_candidates": to_json_serializable(results[:5]),
            "all_candidates": to_json_serializable(results)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/simulation/wfo")
def run_walk_forward(req: dict):
    """베테랑 표준 학습 구간(2010~2018) -> 미래 검증(2019~현재) 프로세스를 실행합니다."""
    tickers_weight = req.get("tickers_weight", {"TQQQ": 0.55, "SOXL": 0.45})
    seed = float(req.get("seed", 10000))
    
    # 전략 모듈 구성
    modules = {
        "turbo": req.get("use_turbo", True),
        "shadow": req.get("use_shadow", True),
        "shield": req.get("use_shield", True),
        "sniper": req.get("use_sniper", True),
        "emergency": req.get("use_emergency", True)
    }
    
    global_config = {
        "split": int(req.get("split", 40)),
        "target": float(req.get("target", 10.0)),
        "shadow_bounce": float(req.get("shadow_bounce", 1.5)),
        "use_tax": req.get("use_tax", True),
        "modules": modules
    }
    
    try:
        from simulation_engine import WalkForwardRunner
        wfo = WalkForwardRunner(tickers_weight, seed, global_config)
        result = wfo.run_validation()
        # [V26.3] 표준 JSON 변환
        safe_result = to_json_serializable(result)
        return {"status": "ok", "result": safe_result}
    except Exception as e:
        return {"status": "error", "message": f"WFO 검증 연구 실패: {str(e)}"}

@app.post("/api/simulation/deploy")
async def api_deploy_strategy(req: dict):
    """
    🚀 [V29.6] 최적화된 전략을 실전/모의 봇에 즉각 투입
    """
    try:
        is_real = req.get("is_real", False)
        target_version = req.get("version", "V14")
        modules = req.get("modules", {})
        
        cfg = ConfigManager(is_real=is_real)
        active_tickers = cfg.get_active_tickers()
        
        # 1. 전역 전술 설정 업데이트 (The Shield, Shadow, Turbo 등)
        current_tactics = cfg.get_global_tactics()
        current_tactics.update(modules)
        cfg.set_global_tactics(current_tactics)
        
        # 2. 모든 액티브 종목의 버전 통일
        for t in active_tickers:
            cfg.set_version(t, target_version)
            
        # 3. UI 즉시 동기화 트리거 (Fast Sync)
        # main.py의 app_data 접근이 어려우므로, 파일을 통해 FastSync 유도
        cfg.record_event("DEPLOY", "SUCCESS", f"전략 일괄 배포 완료", details=f"버전: {target_version}, 모듈: {list(modules.keys())}")
        
        logging.info(f"✅ [DEPLOY] Strategy {target_version} applied to {'REAL' if is_real else 'MOCK'} mode.")
        return {"status": "success", "msg": f"{'실전' if is_real else '모의'} 엔진에 전략 배포 완료!"}
    except Exception as e:
        logging.error(f"❌ [DEPLOY] Error: {e}")
        return {"status": "error", "msg": str(e)}

@app.post("/api/simulation/parameter_sweep")
def run_sweep(req: dict):
    """최적 지점 탐색기(Heatmap)를 위한 파라미터 스윕 실행"""
    ticker = req.get("ticker", "TQQQ")
    param_name = req.get("param_name", "split")
    param_range = req.get("param_range", [40, 60, 80, 100])
    
    start_date = req.get("start_date", "2010-02-11")
    end_date = req.get("end_date", "2024-01-01")
    seed = float(req.get("seed", 10000))
    
    config_base = {
        "split": int(req.get("split", 40)),
        "target": float(req.get("target", 10.0)),
        "shadow_bounce": 1.5,
        "use_tax": True,
        "modules": {"turbo": True, "shadow": True, "shield": True, "sniper": True}
    }
    
    try:
        results = run_parameter_sweep(ticker, start_date, end_date, seed, config_base, param_name, param_range)
        return {"status": "ok", "results": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/market/pulse")
def get_market_pulse_api():
    """실시간 시장 지능(Fear & Greed, VIX 등)을 반환합니다."""
    try:
        mi = MarketIntelligence()
        return {"status": "ok", "pulse": mi.get_market_pulse()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/ping")
def ping():
    return {"status": "ok", "message": "Pong! Connection to WSL Backend is Successful."}

@app.get("/api/simulation/advisor")
async def get_simulation_advisor(vix_roc: float = 0, t_val: float = 0, rsi: float = 50):
    """
    현재 시장 상황(VIX, T-Val, RSI)을 기반으로 최적의 전략 조합을 제안합니다. (V8.8 AI Core)
    """
    try:
        advisor = MarketAwareAdvisor()
        recommendation = advisor.get_recommendation(vix_roc, t_val, rsi)
        return {"status": "ok", "recommendation": recommendation}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ----------------- [프론트엔드 정적 파일 서빙] -----------------
# [V26.2] SPA 대응형 표준 서빙 로직
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
# 만약 frontend/dist가 없으면 루트의 dist 확인 (심볼릭 링크 대응)
if not os.path.exists(frontend_dist):
    frontend_dist = os.path.join(os.path.dirname(__file__), "dist")

if os.path.exists(frontend_dist):
    # 1. assets 폴더 우선 마운트
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # 2. 기타 모든 정적 파일 및 SPA 라우팅 처리
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # API 및 자산 경로는 건너뜀
        if full_path.startswith("api") or full_path.startswith("assets"):
            return None
        
        # 파일이 실제로 존재하면 해당 파일 반환 (favicon.ico 등)
        target_file = os.path.join(frontend_dist, full_path)
        if full_path and os.path.isfile(target_file):
            return FileResponse(target_file)
            
        # 그 외 모든 요청(루트 포함)은 index.html 반환
        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        
        return {"detail": "Frontend assets not found. Please build the UI."}
else:
    @app.get("/")
    def no_dist():
        return {"error": "UI build (dist) folder missing. Please run 'npm run build' in frontend folder."}

# 🚀 [V27-Unified] 이제 main.py에서 한 몸으로 실행됩니다.
# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=5050)

# 🛰️ [V36.0 Advanced] V-REV 전용 초정밀 시뮬레이션 API
@app.post("/api/simulation/vrev-advanced")
async def run_vrev_advanced(req: dict):
    from simulation_engine import VRevResearchSimulator
    import os
    import math
    
    ticker = req.get("ticker", "SOXL")
    year = req.get("year", "2022")
    seed = float(req.get("seed", 10000))
    config = req.get("config", {})
    
    csv_paths = []
    if year == "5y":
        years = ["2022", "2023", "2024", "2025", "2026"]
        for y in years:
            p = f"/home/jmyoon312/벡테스트 데이터/1min＿{y}.csv"
            if os.path.exists(p): csv_paths.append(p)
    else:
        csv_file = f"/home/jmyoon312/벡테스트 데이터/1min＿{year}.csv"
        if os.path.exists(csv_file): csv_paths.append(csv_file)
    
    if not csv_paths: return {"status": "error", "message": f"데이터 부족: {year}"}

    try:
        sim = VRevResearchSimulator(ticker, seed, config)
        history = sim.run_simulation_sequence(csv_paths)
        
        if not history: return {"status": "error", "message": "시뮬레이션 결과 데이터가 구성되지 않았습니다."}
        
        initial = seed
        final = float(history[-1]["total"])
        total_return = ((final - initial) / initial) * 100
        
        # 📊 [V50.0] 글로벌 MDD 및 연간 성과 연산
        peak = 0
        global_mdd = 0
        yearly_summary = {}
        
        for h in history:
            val = float(h["total"])
            if val > peak: peak = val
            dd = (peak - val) / peak if peak > 0 else 0
            if dd > global_mdd: global_mdd = dd
            
            y_key = h["date"].split("-")[0]
            if y_key not in yearly_summary:
                yearly_summary[y_key] = {"start_total": val, "final_total": val, "peak": 0, "mdd": 0}
            
            y_s = yearly_summary[y_key]
            y_s["final_total"] = val
            if val > y_s["peak"]: y_s["peak"] = val
            y_dd = (y_s["peak"] - val) / y_s["peak"] if y_s["peak"] > 0 else 0
            if y_dd > y_s["mdd"]: y_s["mdd"] = y_dd

        for y in yearly_summary:
            y_s = yearly_summary[y]
            y_ret = ((y_s["final_total"] - y_s["start_total"]) / y_s["start_total"]) * 100
            y_s["return"] = round(y_ret, 2)
            y_s["mdd_pct"] = round(y_s["mdd"] * 100, 2)

        return to_json_serializable({
            "status": "success",
            "summary": {
                "total_return": round(total_return, 2),
                "final_total": round(final, 2),
                "mdd_pct": round(global_mdd * 100, 2),
                "total_days": len(history),
                "metrics": sim.metrics,
                "yearly": yearly_summary
            },
            "history": history
        })
    except Exception as e:
        import traceback
        logging.error(f"V-REV Sim Error: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": str(e)}

