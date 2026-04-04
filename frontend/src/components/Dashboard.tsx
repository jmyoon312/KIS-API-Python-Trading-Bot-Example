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
  const [tactics, setTactics] = useState<any>(null) // 🛡️ [V25] 글로벌 전술 정보
  const [logSearch, setLogSearch] = useState('')
  const [logDateFilter, setLogDateFilter] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    try {
      const api = axios.create({ baseURL: '/api' })
      const [resConf, resLedger, resTactics, resLogs] = await Promise.all([
        api.get(`/config?mode=${mode}`),
        api.get(`/ledger?mode=${mode}`),
        api.get(`/settings/tactics?mode=${mode}`),
        api.get(`/logs?mode=${mode}`)
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

      if (resLogs.data.logs) {
        setLogs(resLogs.data.logs) 
      }

      // 🏹 [V25] 글로벌 전술 데이터 세팅
      if (resTactics.data.tactics) {
        setTactics(resTactics.data.tactics)
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
      // 🚀 [V26.9] 반응형 폴링: 동기화 진행 중일 때는 2초마다, 평소에는 10초마다 갱신
      const pollInterval = syncStatus?.status === 'PROCESSING' ? 2000 : 10000;
      interval = setInterval(fetchData, pollInterval)
    }
    return () => clearInterval(interval)
  }, [isAutoRefresh, mode, syncStatus?.status])

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
      
      {/* 📡 Market Schedule Timeline */}
      <MarketTimeline 
        marketStatus={account?.market_status || '조회 중'} 
        dstInfo={account?.dst_info || ''}
        isSummer={account?.is_summer}
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
            tactics={tactics}
            syncStatus={syncStatus}
            onRefresh={fetchData}
          />
        ))}
      </div>

      {/* 📊 실시간 거래 알림 피드 (Trade Alert Feed) - V33 통일 형식 */}
      <div className="bg-[#09090b] rounded-2xl border border-[#27272a] overflow-hidden shadow-2xl mt-8">
        <div className="flex flex-wrap justify-between items-center gap-2 p-4 bg-[#121214] border-b border-[#27272a]">
          <h3 className="text-white font-bold text-xs flex items-center gap-2 whitespace-nowrap">
            <span className="text-green-500 animate-pulse">●</span> 실시간 거래 알림 피드
            <span className="text-[0.55rem] text-gray-500 font-normal tracking-wider uppercase hidden sm:inline">(Trade Alert Feed)</span>
          </h3>
          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="flex items-center gap-2 bg-[#27272a] rounded-full px-3 py-1 border border-[#3f3f46]">
              <input 
                type="text" 
                placeholder="결과 검색..." 
                value={logSearch}
                onChange={(e) => setLogSearch(e.target.value)}
                className="bg-transparent text-[0.6rem] text-white outline-none w-20 focus:w-32 transition-all placeholder:text-gray-600"
              />
              <input 
                type="text" 
                placeholder="MM/DD" 
                value={logDateFilter}
                onChange={(e) => setLogDateFilter(e.target.value)}
                className="bg-transparent text-[0.6rem] text-white outline-none w-10 placeholder:text-gray-600 border-l border-[#3f3f46] pl-2"
              />
            </div>
            <button 
              onClick={async () => {
                if (window.confirm("거래 내역을 영구적으로 초기화하시겠습니까?")) {
                  try {
                    await axios.post('/api/logs/clear', { mode });
                    setLogSearch('');
                    setLogDateFilter('');
                    fetchData();
                  } catch (e) {
                    console.error("초기화 실패:", e);
                  }
                }
              }}
              className="text-[0.6rem] text-gray-500 hover:text-red-400 font-bold transition-colors bg-[#27272a] px-2 py-0.5 rounded-full whitespace-nowrap"
            >
              내역 비우기
            </button>
          </div>
        </div>
        <div className="max-h-80 overflow-y-auto scrollbar-thin scrollbar-thumb-[#3f3f46]">
          {logs && logs.length > 0 && typeof logs[0] === 'object' ? (
            <table className="w-full text-left text-[0.65rem] border-collapse">
              <thead className="sticky top-0 bg-[#18181b] border-b border-[#27272a] z-10 text-gray-500 font-bold">
                <tr>
                  <th className="px-3 py-2 w-12">DATE</th>
                  <th className="px-2 py-2 w-16">TIME</th>
                  <th className="px-2 py-2 w-20">TASK</th>
                  <th className="px-3 py-2">SUMMARY</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#27272a]">
                {logs
                  .filter((ev: any) => {
                    const searchStr = logSearch.toLowerCase();
                    const dateStr = logDateFilter;
                    return (
                      (ev.msg?.toLowerCase().includes(searchStr) || ev.task?.toLowerCase().includes(searchStr)) &&
                      (!dateStr || ev.date === dateStr)
                    );
                  })
                  .map((ev: any, idx: number) => {
                    // 🚀 [V33.4] 중요 거래 로그(BUY/SELL) 시각적 강조
                    const isTrade = ev.task?.includes('BUY') || ev.task?.includes('SELL') || ev.msg?.includes('체결');
                    return (
                    <tr key={idx} className={`hover:bg-[#18181b]/50 transition-colors ${
                      isTrade ? 'bg-blue-500/10 border-l border-blue-500/50 shadow-[inset_2px_0_0_0_#3b82f6]' : 
                      idx === 0 ? 'bg-green-950/10' : ''
                    }`}>
                    <td className="px-3 py-2.5 text-gray-600 font-mono tracking-tighter text-[0.6rem]">{ev.date}</td>
                    <td className="px-2 py-2.5 text-gray-500 font-mono tracking-tighter">{ev.time}</td>
                    <td className="px-2 py-2.5">
                      <span className={`px-1.5 py-0.5 rounded-md font-bold text-[0.55rem] ${
                        ev.status === 'SUCCESS' ? 'text-green-500 bg-green-500/10' : 
                        ev.status === 'ERROR' ? 'text-red-500 bg-red-500/10' : 
                        ev.status === 'WARNING' ? 'text-yellow-500 bg-yellow-500/10' :
                        'text-blue-500 bg-blue-500/10'
                      }`}>
                        {ev.task}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-gray-300 font-medium">
                      <span className="mr-1">{ev.icon}</span>{ev.msg}
                    </td>
                  </tr>
                );
              })}
              </tbody>
            </table>
          ) : logs && logs.length > 0 ? (
            /* Fallback: 기존 문자열 배열 호환 */
            <div className="p-3 space-y-2">
              {logs.map((log: any, i: number) => (
                <div key={i} className="p-2.5 rounded-lg bg-[#18181b] border border-[#27272a] text-gray-400 text-[0.7rem]">{typeof log === 'string' ? log : JSON.stringify(log)}</div>
              ))}
            </div>
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
