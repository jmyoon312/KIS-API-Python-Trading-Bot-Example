import { useEffect, useState } from 'react'
import axios from 'axios'
import SniperCard from './SniperCard'
import MarketTimeline from './MarketTimeline'

export default function Dashboard({ isAutoRefresh, mode }: { isAutoRefresh: boolean, mode: 'mock' | 'real' }) {
  // Enhanced: Dual-timezone & Task Status support enabled
  const [config, setConfig] = useState<any>(null)
  const [ledger, setLedger] = useState<any>(null)
  const [account, setAccount] = useState<any>(null)
  const [logs, setLogs] = useState<string[]>([]) // 📜 신규: 시스템 로그 상태
  const [syncStatus, setSyncStatus] = useState<any>(null) // 🔄 신규: 동기화 상태 피드백
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    try {
      const api = axios.create({ baseURL: '/api' })
      const [resConf, resLedger] = await Promise.all([
        api.get(`/config?mode=${mode}`),
        api.get(`/ledger?mode=${mode}`)
      ])
      setConfig(resConf.data.config)
      
      const ledgerData = resLedger.data.ledger;
      if (Array.isArray(ledgerData)) {
        const fallbackLedger: any = {};
        ledgerData.forEach((item: any) => {
          if (!fallbackLedger[item.ticker]) fallbackLedger[item.ticker] = [];
          fallbackLedger[item.ticker].push(item);
        });
        setLedger(fallbackLedger);
      } else {
        setLedger(ledgerData);
      }
      
      if (resLedger.data.account) {
        setAccount(resLedger.data.account);
        // [V23.5] 수동 취합 연동 피드백
        if (resLedger.data.account.last_manual_sync) {
           setSyncStatus(resLedger.data.account.last_manual_sync);
        }
      }

      // 📜 로그 데이터 가져오기
      const resLogs = await api.get(`/logs?mode=${mode}`)
      if (resLogs.data.logs) {
        setLogs(resLogs.data.logs.reverse()) 
      }
    } catch (e) {
      console.error("API 연결 실패", e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    let interval: any;
    if (isAutoRefresh) {
      interval = setInterval(fetchData, 10000) // 10초 간격으로 단축 (빠른 피드백)
    }
    return () => clearInterval(interval)
  }, [isAutoRefresh, mode])

  if (loading) {
    return (
      <div className="flex justify-center items-center h-40">
        <div className="w-8 h-8 border-4 border-blue-500/20 border-t-blue-500 rounded-full animate-spin mr-3"></div>
        <p className="text-gray-400">Loading Core Data...</p>
      </div>
    )
  }

  if (!config || !ledger) {
    return (
      <div className="bg-[#121214] border border-[#27272a] rounded-xl p-6 text-center text-red-500 text-sm mt-10">
        <p className="font-bold mb-2">📡 백엔드 API 서버 연결 실패</p>
        <p className="text-gray-400 text-xs">포트 5050의 파이썬 타이머가 켜져있는지, <br/>또는 Nginx Proxy Manager의 [Custom locations]에 /api 프록시 세팅이 잘 되었는지 확인해주세요.</p>
      </div>
    )
  }

  const activeTickers = config.ACTIVE_TICKERS || ['SOXL', 'TQQQ']
  
  // Evaluate total assets strictly matching telegram (cash + holdings total_eval)
  let totalAsset = 0;
  let availableCash = 0;
  
  if (account && account.cash !== undefined) {
    totalAsset += account.cash;
    availableCash = account.available_cash || account.cash;
    if (account.tickers) {
      for (const t of activeTickers) {
        const info = account.tickers[t];
        if (info && info.qty) {
          totalAsset += info.qty * (info.current_price || info.avg_price || 0);
        }
      }
    }
  } else {
    for (const t of activeTickers) {
      totalAsset += (config[t]?.seed || 0);
    }
    availableCash = totalAsset;
  }

  const escrowCash = account && account.escrow_cash ? account.escrow_cash : 0;

  return (
    <div className="space-y-4 animate-fade-in-up pb-10 relative">
      {/* 🔄 [V23.5] Manual Sync Notification Toast */}
      {syncStatus && (Date.now() / 1000 - syncStatus.timestamp < 30) && (
        <div className={`fixed top-24 left-1/2 -translate-x-1/2 z-[100] px-4 py-2.5 rounded-2xl border shadow-2xl flex items-center gap-3 transition-all animate-pulse ${
          syncStatus.status === 'PROCESSING' 
          ? 'bg-blue-600/20 border-blue-500/50 text-blue-400' 
          : 'bg-emerald-600/20 border-emerald-500/50 text-emerald-400 border-dashed'
        }`}>
          {syncStatus.status === 'PROCESSING' ? (
            <div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
          ) : (
            <span className="text-xs">⚡</span>
          )}
          <span className="text-[10px] font-black tracking-tight">{syncStatus.msg}</span>
        </div>
      )}
      
      {/* 📡 Market Schedule Timeline */}
      <MarketTimeline 
        marketStatus={account?.market_status || '조회 중'} 
        dstInfo={account?.dst_info || ''}
        isTradeActive={account?.is_trade_active || false}
        isReal={account?.is_real}
        taskStatus={account?.task_status || {}}
      />

      {/* Account Overview Cards */}
      <div className="bg-[#121214] border border-[#27272a] rounded-xl overflow-hidden shadow-xl">
        <div className="flex justify-between items-center p-4 border-b border-[#27272a]">
          <div className="flex items-center text-gray-300 font-bold text-sm">
            <span className="mr-2 text-green-500">💵</span> 계좌 총액
          </div>
          <div className="text-white font-bold tracking-wider tabular-nums text-lg">${totalAsset > 0 ? totalAsset.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00'}</div>
        </div>
        
        <div className="flex justify-between items-center p-4 border-b border-[#27272a]">
          <div className="flex items-center text-gray-400 font-medium text-sm">
            <span className="mr-2">🔒</span> 에스크로
          </div>
          <div className="text-red-500 font-bold tracking-wider tabular-nums">-${escrowCash.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
            {account?.is_real ? (
              <span className="text-[0.45rem] px-1.5 py-0.5 bg-red-500/10 text-red-500 border border-red-500/20 rounded font-black uppercase tracking-tighter">Real Trading</span>
            ) : (
              <span className="text-[0.45rem] px-1.5 py-0.5 bg-orange-500/10 text-orange-500 border border-orange-500/20 rounded font-black uppercase tracking-tighter shadow-[0_0_8px_rgba(249,115,22,0.2)]">MOCK MODE Active</span>
            )}
        </div>
        
        <div className={`flex justify-between items-center p-4 border rounded-b-xl ${
          mode === 'real' ? 'border-blue-500/50 bg-blue-900/10' : 'border-emerald-500/50 bg-emerald-900/10'
        }`}>
          <div className="flex items-center text-gray-300 font-bold text-sm">
            <span className={`mr-2 ${mode === 'real' ? 'text-blue-500' : 'text-emerald-500'}`}>✅</span> 가용 예산
          </div>
          <div className={`${mode === 'real' ? 'text-blue-500' : 'text-emerald-500'} font-bold tracking-wider tabular-nums text-lg`}>
            ${availableCash > 0 ? availableCash.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00'}
          </div>
        </div>
      </div>
      
      {/* Sniper Cards */}
      <div className="space-y-6 pt-2">
        <h3 className="text-white font-black text-xs px-1 tracking-widest uppercase flex justify-between items-center opacity-70">
          <span>Live Ticker Monitoring</span>
          <span className="text-[0.6rem] font-normal lowercase bg-[#27272a] px-2 py-0.5 rounded-full">Updates every 10s</span>
        </h3>
        {activeTickers.map((ticker: string) => (
          <SniperCard 
            key={ticker} 
            ticker={ticker} 
            ledgerData={ledger[ticker] || {}} 
            configData={config[ticker] || {}} 
            mode={mode}
            onRefresh={fetchData}
          />
        ))}
      </div>

      {/* 📊 실시간 거래 알림 피드 (Trade Alert Feed) - RE-DESIGNED [V24] */}
      <div className="bg-[#09090b] rounded-2xl border border-[#27272a] overflow-hidden shadow-2xl mt-8">
        <div className="flex justify-between items-center p-4 bg-[#121214] border-b border-[#27272a]">
          <h3 className="text-white font-bold text-xs flex items-center gap-2">
            <span className="text-green-500 animate-pulse">●</span> 실시간 거래 알림 피드
          </h3>
          <div className="flex items-center gap-3">
            <button 
              onClick={async () => {
                if (window.confirm("거래 내역을 영구적으로 초기화하시겠습니까?")) {
                  try {
                    await axios.post('/api/logs/clear', { mode });
                    fetchData(); // 즉시 리프레시
                  } catch (e) {
                    console.error("초기화 실패:", e);
                  }
                }
              }}
              className="text-[0.6rem] text-gray-500 hover:text-red-400 font-bold transition-colors bg-[#27272a] px-2 py-0.5 rounded-full"
            >
              내역 비우기
            </button>
            <span className="text-[0.6rem] text-gray-500 font-medium tracking-tighter uppercase opacity-50">Auto-sync active</span>
          </div>
        </div>
        <div className="p-3 max-h-72 overflow-y-auto space-y-2.5 scrollbar-none bg-gradient-to-b from-[#09090b] to-[#121214]">
          {logs && logs.filter(log => /✅|❌|💰|익절|매수|매도|졸업|스나이퍼|🌟|💫|🚨|⚠️|🌅|🔥|🌙|📝|🔄|📡|🔔/.test(log)).length > 0 ? (
            logs.filter(log => /✅|❌|💰|익절|매수|매도|졸업|스나이퍼|🌟|💫|🚨|⚠️|🌅|🔥|🌙|📝|🔄|📡|🔔/.test(log)).map((log, i) => {
              const matches = log.match(/\[(.*?)\] (.*)/);
              const time = matches ? matches[1] : '';
              const content = matches ? matches[2] : log;
              
              const isError = log.includes('❌') || log.includes('⚠️') || log.includes('🚨');
              const isProfit = log.includes('💰') || log.includes('익절') || log.includes('졸업');
              const isAction = log.includes('매수') || log.includes('매도');
              const isNew = i === 0;

              return (
                <div key={i} className={`group relative p-3 rounded-xl border transition-all duration-300 ${isNew ? 'ring-1 ring-green-500/20 shadow-[0_0_15px_rgba(34,197,94,0.1)]' : ''} ${
                  isError ? 'bg-red-950/20 border-red-900/40 text-red-200' :
                  isProfit ? 'bg-green-950/20 border-green-900/40 text-green-200' :
                  isAction ? 'bg-blue-950/20 border-blue-900/40 text-blue-200' :
                  'bg-[#18181b] border-[#27272a] text-gray-400'
                }`}>
                  {isNew && (
                    <div className="absolute -left-1 -top-1">
                      <span className="flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                      </span>
                    </div>
                  )}
                  <div className="flex justify-between items-start mb-1">
                    <span className={`text-[0.55rem] font-black uppercase tracking-widest ${isNew ? 'text-green-500' : 'opacity-40'}`}>
                      {isNew ? 'New Alert' : 'History'}
                    </span>
                    <span className="text-[0.55rem] font-bold opacity-30 tabular-nums">{time || 'RECENT'}</span>
                  </div>
                  <p className="text-[0.7rem] font-medium leading-relaxed">
                    {content}
                  </p>
                </div>
              );
            })
          ) : (
            <div className="flex flex-col items-center justify-center py-12 opacity-20">
              <span className="text-3xl mb-3 grayscale">🔔</span>
              <p className="text-[0.7rem] font-bold tracking-tight">수신된 실시간 거래 알림이 없습니다.</p>
              <p className="text-[0.6rem] mt-1 font-medium">거래가 발생하면 여기에 즉시 표시됩니다.</p>
            </div>
          )}
        </div>
        <div className="p-2.5 text-center bg-[#121214] border-t border-[#27272a]">
          <p className="text-[0.55rem] text-gray-600 font-bold uppercase tracking-tighter space-x-2">
            <span>● Trade Alert Engine Active</span>
            <span className="opacity-30">|</span>
            <span>Mode: {mode.toUpperCase()}</span>
          </p>
        </div>
      </div>
    </div>
  )
}
