import os
import json
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import datetime
from pydantic import BaseModel
from config import ConfigManager
from simulation_engine import InfinitySimulator 

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
    """최신 알림 피드(notifications.json) 또는 시스템 로그를 반환합니다."""
    log_dir = os.path.join("logs", mode)
    if not os.path.exists(log_dir):
        return {"status": "ok", "logs": [f"[{mode.upper()}] 기록된 활동이 없습니다."]}
        
    # 🚀 [V23.1] 1차 순위: 정제된 알림 피드 (JSON 형식)
    notif_path = os.path.join(log_dir, "notifications.json")
    if os.path.exists(notif_path):
        try:
            with open(notif_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 프론트엔드 호환성을 위해 문자열 배열로 변환 (역순으로 최신순)
                formatted_logs = [f"{n['icon']} {n['message']}" for n in reversed(data)]
                return {"status": "ok", "logs": formatted_logs}
        except: pass
    
    # 2차 순위: 기존 시스템 로그 (Fallback)
    import glob
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
    log_dir = os.path.join("logs", mode)
    notif_path = os.path.join(log_dir, "notifications.json")
    if os.path.exists(notif_path):
        try:
            with open(notif_path, 'w', encoding='utf-8') as f:
                json.dump([], f)
        except: pass
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
    
    try:
        # [V23.5] 상태 기록 (동기화 시작 알림용)
        l_status = load_json(cfg._get_file_path("LIVE_STATUS"))
        if not l_status: l_status = {"tickers": {}}
        l_status["last_manual_sync"] = {
            "timestamp": time.time(),
            "status": "PROCESSING",
            "msg": "데이터 동기화 요청 중..."
        }
        # 파일에 직접 기록 (엔진이 읽기 전 UI가 먼저 볼 수 있게)
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
    return {"status": "ok"}

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
    
    try:
        # [V23.5] 상태 기록
        l_status = load_json(cfg._get_file_path("LIVE_STATUS"))
        if not l_status: l_status = {"tickers": {}}
        l_status["last_manual_sync"] = {
            "timestamp": time.time(),
            "status": "PROCESSING",
            "msg": f"[{ticker}] 장부 보정 요청 중..."
        }
        with open(cfg._get_file_path("LIVE_STATUS"), 'w', encoding='utf-8') as f:
            json.dump(l_status, f, ensure_ascii=False, indent=4)

        with open(os.path.join(cfg._get_base_dir(), f"trigger_record_{ticker}.tmp"), 'w') as f:
            f.write(str(time.time()))
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

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
def get_analytics_api(mode: str = "mock"):
    cfg = get_cfg(mode)
    return {"status": "ok", "analytics": cfg.get_analytics_data()}

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
    """지정된 기간과 종목에 대해 무한매수법 시뮬레이션을 수행합니다."""
    ticker = req.get("ticker", "TQQQ")
    start_date = req.get("start_date", "2020-01-01")
    end_date = req.get("end_date", datetime.datetime.now().strftime("%Y-%m-%d"))
    seed = float(req.get("seed", 10000))
    split = int(req.get("split", 40))
    target = float(req.get("target", 10.0))
    version = req.get("version", "V14")
    
    try:
        sim = InfinitySimulator(ticker, start_date, end_date, seed, split, target, version)
        result = sim.run()
        return {"status": "ok", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ----------------- [프론트엔드 정적 파일 서빙] -----------------
# frontend/dist 경로 설정 (Windows/WSL 호환)
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.exists(frontend_dist):
    # assets 폴더 (JS, CSS) 마운트
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # API 경로는 무시 (이미 위에서 정의됨)
        if full_path.startswith("api"):
            return None
        
        # dist 폴더 내 실제 파일 존재 여부 확인 (favicon, manifest 등)
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        
        # 그 외 모든 경로는 index.html로 리다이렉트 (SPA 라우팅 지원)
        return FileResponse(os.path.join(frontend_dist, "index.html"))

if __name__ == "__main__":
    print("🚀 Infinity Quant Hub - Core API Server is starting on port 5050...")
    uvicorn.run("web_server:app", host="0.0.0.0", port=5050, reload=False)
