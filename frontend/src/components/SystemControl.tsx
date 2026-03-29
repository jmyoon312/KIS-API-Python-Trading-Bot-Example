import { useEffect, useState, useRef } from 'react'
import axios from 'axios'
import StrategyGuide from './StrategyGuide'

const AVAILABLE_TICKERS = ['SOXL', 'TQQQ', 'UPRO', 'TECL', 'QLD', 'SPXL', 'FAS', 'LABU', 'FNGU', 'TNA'];

export default function SystemControl({ mode }: { mode: 'mock' | 'real' }) {
  const [config, setConfig] = useState<any>(null)
  const [account, setAccount] = useState<any>(null)
  const [turbo, setTurbo] = useState(false)
  const [engineOn, setEngineOn] = useState(false)
  const [activeTickers, setActiveTickers] = useState<string[]>([])
  const [rebalancing, setRebalancing] = useState(false)
  const [forceRebalance, setForceRebalance] = useState(false) // 🔥 [V23.1] 즉시 강제 적용 여부
  const [showGuide, setShowGuide] = useState(false)
  const [statusMsg, setStatusMsg] = useState('')
  const [localRatios, setLocalRatios] = useState<Record<string, number>>({})
  const [events, setEvents] = useState<any[]>([])
  const timerRef = useRef<any>(null)

  const api = axios.create({ baseURL: '/api' })

  const fetchData = async () => {
    try {
      const [resConf, resLedger] = await Promise.all([
        api.get(`/config?mode=${mode}`), 
        api.get(`/ledger?mode=${mode}`)
      ])
      const cfg = resConf.data.config
      setConfig(cfg)
      const cfgTickers = cfg.ACTIVE_TICKERS || ['SOXL', 'TQQQ']
      setActiveTickers(cfgTickers)
      setTurbo(cfg.TURBO_MODE === true)
      setEngineOn(cfg.ENGINE_STATUS === true)
      if (resLedger.data.account) {
        setAccount(resLedger.data.account)
        // 🌐 [V24] 로컬 비중 초기화 (State Sync 버그 수정)
        const ratios: Record<string, number> = {}
        cfgTickers.forEach((t: string) => {
          ratios[t] = resLedger.data.account.tickers?.[t]?.ratio || (1 / cfgTickers.length)
        })
        setLocalRatios(ratios)
      }
      
      // 📋 [V24] 최근 운영 이벤트 로그 가져오기
      const resAnalytics = await api.get(`/analytics?mode=${mode}`)
      if (resAnalytics.data.events) {
        setEvents(resAnalytics.data.events)
      }
    } catch (e) { console.error(e) }
  }

  useEffect(() => { fetchData() }, [mode])

  const toggleEngine = async () => {
    const next = !engineOn
    if (!window.confirm(`⚠️ [${mode.toUpperCase()}] 엔진을 ${next ? '가동' : '정지'}하시겠습니까?`)) return
    setEngineOn(next)
    try {
      await api.post('/settings/engine-status', { mode, value: next })
      setStatusMsg(next ? `🚀 [${mode.toUpperCase()}] 엔진 가동 시작` : `🛑 [${mode.toUpperCase()}] 엔진 일시 정지`)
    } catch { setStatusMsg('❌ 엔진 제어 실패') }
    setTimeout(() => setStatusMsg(''), 3000)
  }

  const toggleTurbo = async () => {
    const next = !turbo
    setTurbo(next)
    try {
      await api.post('/settings/mode', { mode, value: next })
      setStatusMsg(next ? '🏎️ 가속 모드 활성화' : '⏸️ 가속 모드 비활성화')
    } catch { setStatusMsg('❌ 모드 변경 실패') }
    setTimeout(() => setStatusMsg(''), 3000)
  }

  const toggleTicker = async (t: string) => {
    let next: string[]
    if (activeTickers.includes(t)) {
      if (activeTickers.length <= 1) {
        setStatusMsg('⚠️ 최소 1개 이상의 종목이 필요합니다')
        setTimeout(() => setStatusMsg(''), 3000)
        return
      }
      next = activeTickers.filter((x: string) => x !== t)
    } else {
      next = [...activeTickers, t]
    }
    setActiveTickers(next)
    try {
      await api.post('/settings/tickers', { mode, tickers: next })
      setStatusMsg(`✅ [${mode.toUpperCase()}] 운용 종목 변경: ${next.join(', ')}`)
    } catch { setStatusMsg('❌ 종목 변경 실패') }
    setTimeout(() => setStatusMsg(''), 3000)
  }

  const handleRebalance = async () => {
    // 안전 경고: 보유 주식이 있는 종목이 있는지 확인
    let hasHoldings = false
    if (account?.tickers) {
      for (const t of activeTickers) {
        if (account.tickers[t]?.qty > 0) {
          hasHoldings = true
          break
        }
      }
    }

    let confirmMsg = '⚖️ 계좌 총자산을 기준으로 모든 활성 종목의 시드를 재분배합니다.\n\n'
    if (hasHoldings) {
      confirmMsg += '⚠️ 주의: 현재 보유 중인 주식이 있습니다.\n'
      confirmMsg += '시드 변경은 다음 사이클부터 적용되며, 기존 보유 주식에는 영향 없습니다.\n\n'
    }
    confirmMsg += '정말 실행하시겠습니까?'
    
    if (!window.confirm(confirmMsg)) return
    
    setRebalancing(true)
    setStatusMsg('⏳ 리밸런싱 처리 중...')
    try {
      // 서버가 live_status.json에서 직접 총 자산을 읽어서 리밸런싱함
      const res = await api.post('/settings/seed', { mode, action: 'rebalance', force: forceRebalance })
      if (res.data.status === 'ok') {
        setStatusMsg(`✅ ${res.data.message}`)
        // 설정 데이터 리프레시하여 새 시드 반영
        await fetchData()
      } else {
        setStatusMsg(`❌ ${res.data.message || '리밸런싱 실패'}`)
      }
    } catch (e: any) {
      setStatusMsg(`❌ 리밸런싱 오류: ${e.response?.data?.message || e.message}`)
    }
    setRebalancing(false)
    setTimeout(() => setStatusMsg(''), 5000)
  }

  // 🌐 [V24] 비중 조절 엔진 (합계 100% 제한 및 실시간 배분액 계산용)
  const updateRatio = (ticker: string, delta: number) => {
    setLocalRatios(prev => {
      const current = prev[ticker] || 0
      let next = Math.max(0, Math.min(1, current + delta))
      
      // 전체 합계가 100%를 초과하지 않도록 보정
      const otherSum = Object.entries(prev)
        .filter(([t]) => t !== ticker)
        .reduce((sum, [_, r]) => sum + r, 0)
      
      if (otherSum + next > 1.001) {
        next = Math.max(0, 1 - otherSum)
      }

      const updated = { ...prev, [ticker]: next }
      
      // 백엔드 즉시 저장 (Debounced or Async)
      api.post('/settings/portfolio-ratios', { mode, ratios: { [ticker]: next } })
      
      return updated
    })
  }

  const startAdjusting = (ticker: string, delta: number) => {
    updateRatio(ticker, delta)
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = setInterval(() => updateRatio(ticker, delta), 150)
  }

  const stopAdjusting = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  // 👤 [V24] Shadow-Strike 설정 업데이트 핸들러
  const handleShadowToggle = async (ticker: string, currentActive: boolean, bounce: number) => {
    try {
      await api.post('/settings/shadow', { mode, ticker, active: !currentActive, bounce })
      await fetchData() // UI 갱신
    } catch { setStatusMsg(`❌ [${ticker}] Shadow 모드 변경 실패`) }
  }

  const handleShadowBounce = async (ticker: string, active: boolean, newBounce: number) => {
    try {
      await api.post('/settings/shadow', { mode, ticker, active, bounce: newBounce })
      // 성능을 위해 local config만 업데이트 (debounce 처리가 좋으나 여기선 단순화)
      setConfig((prev: any) => ({
        ...prev,
        [ticker]: { ...prev[ticker], shadow: { active, bounce: newBounce } }
      }))
    } catch { setStatusMsg(`❌ [${ticker}] Bounce 비율 변경 실패`) }
  }

  // 🌐 [V24] 총 자산 실시간 보정 계산 (현금 + ∑(종목별 수량 * 현재가))
  const calculatedHoldingsVal = account?.tickers ? Object.values(account.tickers).reduce((sum: number, t: any) => {
    return sum + (Number(t.qty || 0) * Number(t.current_price || 0))
  }, 0) : 0
  const totalAsset = account ? (account.cash || 0) + (calculatedHoldingsVal || account.holdings_value || 0) : 0

  // Per-ticker seed info (from ConfigManager aggregated config)
  const tickerSeeds = activeTickers.map((t: string) => ({
    ticker: t,
    seed: config?.[t]?.seed || 0,
    version: config?.[t]?.version || 'V22',
    ratio: config?.[t]?.portfolio_ratio || 0,
    holdingQty: account?.tickers?.[t]?.qty || 0,
    shadow: config?.[t]?.shadow || { active: false, bounce: 1.5 }
  }))

  const totalSeed = tickerSeeds.reduce((s: number, ts: any) => s + ts.seed, 0)

  return (
    <div className="space-y-4 animate-fade-in-up pb-12">

      {/* Status message toast */}
      {statusMsg && (
        <div className="bg-[#18181b] border border-[#3f3f46] rounded-xl px-4 py-2.5 text-sm font-medium text-white animate-fade-in shadow-lg">
          {statusMsg}
        </div>
      )}

      {/* Section 0: Engine Power (NEW [V23.1]) */}
      <div className="bg-[#121214] rounded-2xl border border-[#27272a] p-5 shadow-lg overflow-hidden relative">
        <div className="flex justify-between items-start relative z-10">
          <div>
            <h3 className="text-white font-bold text-sm flex items-center gap-2">
              🔌 엔진 가동 상태 <span className="text-[0.55rem] text-gray-500 font-normal tracking-wider uppercase">({mode.toUpperCase()} Engine)</span>
            </h3>
            <div className="mt-2 flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded text-[0.6rem] font-black tracking-tighter ${engineOn ? 'bg-green-600/20 text-green-400 border border-green-500/40' : 'bg-red-600/20 text-red-400 border border-red-500/40'}`}>
                {engineOn ? 'RUNNING' : 'STOPPED'}
              </span>
            </div>
          </div>
          <button 
            onClick={toggleEngine}
            className={`flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-black transition-all border ${
              engineOn 
                ? 'bg-red-900/20 border-red-500/50 text-red-500 shadow-[0_0_15px_rgba(239,68,68,0.2)]' 
                : 'bg-green-900/20 border-green-500/50 text-green-400 shadow-[0_0_15px_rgba(16,185,129,0.2)]'
            }`}
          >
            {engineOn ? '⏹️ 정지' : '▶️ 가동'}
          </button>
        </div>
        <p className="text-gray-500 text-[0.65rem] mt-3 bg-[#18181b] p-2 rounded-lg border border-[#27272a]">
          ※ <b>전원 제어</b>: 해당 엔진의 모든 자동매매 스케줄을 즉시 중단하거나 재개합니다. 
        </p>
      </div>

      {/* Section 1: Turbo Mode */}
      <div className="bg-[#121214] rounded-2xl border border-[#27272a] p-5 shadow-lg">
        <div className="flex justify-between items-center">
          <div>
            <h3 className="text-white font-bold text-sm flex items-center gap-2">
              🚀 부스터 가속 모드 <span className="text-[0.55rem] text-gray-500 font-normal tracking-wider uppercase">(Turbo)</span>
            </h3>
            <p className="text-gray-500 text-xs mt-1">LOC 매수 외에 추가 가속 매수를 동시 주문합니다.</p>
          </div>
          <button 
            onClick={toggleTurbo}
            className={`relative w-14 h-7 rounded-full transition-all duration-300 shadow-inner flex-shrink-0 ${turbo ? 'bg-red-600 shadow-[0_0_12px_rgba(239,68,68,0.5)]' : 'bg-[#27272a]'}`}
          >
            <div className={`w-5 h-5 rounded-full bg-white absolute top-1 transition-transform duration-300 shadow-md ${turbo ? 'translate-x-8' : 'translate-x-1'}`}></div>
          </button>
        </div>
        {turbo && (
          <div className="mt-3 bg-red-900/20 border border-red-800/40 rounded-lg px-3 py-2 text-red-400 text-xs font-medium">
            ⚡ 가속 활성 — 평단 -5% 선제 저가 매수가 추가로 주문됩니다
          </div>
        )}
      </div>

      {/* Section 2: Rebalance - SMART [V24] */}
      <div className="bg-[#121214] rounded-2xl border border-[#27272a] p-5 shadow-lg">
        <h3 className="text-white font-bold text-sm flex items-center gap-2 mb-3">
          ⚖️ 스마트 시드 재분배 <span className="text-[0.55rem] text-gray-500 font-normal tracking-wider uppercase">(Smart Rebalance)</span>
        </h3>
        <p className="text-gray-500 text-xs mb-3">전체 평가 자산을 기준으로 각 종목별 타겟 비중에 맞춰 시드를 재계산합니다.</p>
        
        <div className="bg-[#18181b] rounded-xl border border-[#27272a] p-4 mb-4">
          <div className="flex justify-between items-center mb-1 pb-2 border-b border-[#27272a]/50">
            <span className="text-gray-400 text-[0.6rem] font-bold uppercase tracking-widest">💰 자산 구성 요약</span>
            <span className="text-white font-black text-sm tabular-nums">${totalAsset.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
          </div>
          <div className="flex justify-between text-[0.6rem] py-1 text-gray-500">
            <span>현금(Cash)</span>
            <span className="text-gray-400">${(account?.cash || 0).toLocaleString()}</span>
          </div>
          <div className="flex justify-between text-[0.6rem] py-1 text-gray-500">
            <span>주식(Holdings)</span>
            <span className="text-gray-400">${(account?.holdings_value || 0).toLocaleString()}</span>
          </div>
          <div className="flex justify-between text-[0.6rem] py-1 text-yellow-600/70 font-bold border-t border-[#27272a] mt-1 pt-1">
            <span>총 시드 합계</span>
            <span>${totalSeed.toLocaleString()}</span>
          </div>

          <div className="text-[0.65rem] font-bold text-gray-400 mb-3 mt-4 border-t border-[#27272a] pt-3 flex justify-between">
            <span>📊 종목별 타겟 비중 (%)</span>
            <span className={`px-1.5 py-0.5 rounded ${Math.abs(tickerSeeds.reduce((a, b) => a + (b.ratio || 0), 0) - 1) < 0.001 ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'} font-black`}>
               합계: {(tickerSeeds.reduce((a, b) => a + (b.ratio || 0), 0) * 100).toFixed(0)}%
            </span>
          </div>
          
          <div className="space-y-3">
            {tickerSeeds.map(ts => (
              <div key={ts.ticker} className="space-y-1 bg-[#121214] p-3 rounded-xl border border-[#27272a]/40">
                <div className="flex justify-between items-center text-xs">
                  <div className="flex flex-col">
                    <span className="text-gray-100 font-bold flex items-center gap-1">
                      {ts.ticker}
                      {ts.holdingQty > 0 && <span className="text-[0.6rem] bg-yellow-500/10 text-yellow-500 px-1 rounded border border-yellow-500/20">{ts.holdingQty}주</span>}
                    </span>
                    {/* 👤 [V24] Shadow-Strike 제어 유닛 */}
                    <div className="flex items-center gap-2 mt-1">
                      <button 
                        onClick={() => handleShadowToggle(ts.ticker, ts.shadow.active, ts.shadow.bounce)}
                        className={`text-[0.55rem] px-1.5 py-0.5 rounded transition-all font-bold ${ts.shadow.active ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-500'}`}
                      >
                        👤 SHADOW {ts.shadow.active ? 'ON' : 'OFF'}
                      </button>
                      {ts.shadow.active && (
                        <div className="flex items-center gap-1">
                          <input 
                            type="range" min="0.5" max="5.0" step="0.1" 
                            value={ts.shadow.bounce} 
                            onChange={(e) => handleShadowBounce(ts.ticker, ts.shadow.active, parseFloat(e.target.value))}
                            className="w-12 h-1 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                          />
                          <span className="text-[0.55rem] text-indigo-400 font-mono">{ts.shadow.bounce}%</span>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-yellow-500 font-bold tabular-nums text-[0.65rem]">
                      ${Math.round(totalAsset * (localRatios[ts.ticker] || 0)).toLocaleString()}
                    </span>
                    <div className="flex items-center bg-[#09090b] rounded-lg border border-[#3f3f46] p-0.5 overflow-hidden">
                      <button 
                        onMouseDown={() => startAdjusting(ts.ticker, -0.01)}
                        onMouseUp={stopAdjusting}
                        onMouseLeave={stopAdjusting}
                        className="w-5 h-5 flex items-center justify-center text-gray-500 hover:text-white hover:bg-[#27272a] transition-colors rounded"
                      >
                        <span className="text-sm">−</span>
                      </button>
                      <input 
                        type="number"
                        value={Math.round((localRatios[ts.ticker] || 0) * 100)}
                        onChange={(e) => {
                          const val = Number(e.target.value) / 100
                          updateRatio(ts.ticker, val - (localRatios[ts.ticker] || 0))
                        }}
                        className="w-7 bg-transparent text-center text-xs focus:outline-none focus:text-blue-400 font-bold [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                      />
                      <button 
                        onMouseDown={() => startAdjusting(ts.ticker, 0.01)}
                        onMouseUp={stopAdjusting}
                        onMouseLeave={stopAdjusting}
                        className="w-5 h-5 flex items-center justify-center text-gray-500 hover:text-white hover:bg-[#27272a] transition-colors rounded"
                      >
                        <span className="text-sm">+</span>
                      </button>
                    </div>
                  </div>
                </div>
                <div className="w-full bg-[#09090b] h-1 rounded-full overflow-hidden">
                  <div className="bg-blue-500 h-full transition-all duration-500" style={{ width: `${ts.ratio * 100}%` }}></div>
                </div>
              </div>
            ))}
          </div>
        </div>
        
        <button 
          onClick={handleRebalance}
          disabled={rebalancing}
          className="w-full py-3 rounded-xl font-bold text-sm transition-all border border-blue-500/50 bg-blue-900/20 text-blue-400 hover:bg-blue-800/30 hover:shadow-[0_0_20px_rgba(59,130,246,0.25)] active:scale-[0.98] disabled:opacity-40 flex justify-center items-center gap-2"
        >
          {rebalancing ? '⏳ 재분배 중...' : '⚖️ 설정된 비중으로 시드 일괄 재분배'}
        </button>
        
        <div className="mt-3 flex items-center gap-2 justify-center">
          <input 
            type="checkbox" 
            id="forceRebalance" 
            checked={forceRebalance} 
            onChange={(e) => setForceRebalance(e.target.checked)}
            className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 bg-[#18181b]"
          />
          <label htmlFor="forceRebalance" className="text-[0.65rem] text-gray-400 cursor-pointer hover:text-gray-200 transition-colors">
            ⚠️ <span className="underline decoration-dotted text-red-500/70">즉시 강제 적용</span> (활동 중인 매매에도 즉각 반영)
          </label>
        </div>

        <p className="text-gray-600 text-[0.6rem] mt-2 text-center">
          {forceRebalance 
            ? "※ 주의: 현재 진행 중인 매매의 평단가 및 분할 매수 계산이 즉시 변경됩니다." 
            : "※ 권장: 보유 수량이 0원(졸업)이 된 시점부터 새로운 시드가 순차 적용됩니다."}
        </p>
      </div>

      {/* Section 3: Active Tickers */}
      <div className="bg-[#121214] rounded-2xl border border-[#27272a] p-5 shadow-lg">
        <h3 className="text-white font-bold text-sm flex items-center gap-2 mb-3">
          🎯 운용 종목 선택 <span className="text-[0.55rem] text-gray-500 font-normal tracking-wider uppercase">(Tickers)</span>
        </h3>
        <p className="text-gray-500 text-xs mb-3">엔진이 매일 자동 매매하는 대상 종목을 선택합니다.</p>
        <div className="grid grid-cols-2 gap-2">
          {AVAILABLE_TICKERS.map(t => {
            const isActive = activeTickers.includes(t)
            return (
              <button
                key={t}
                onClick={() => toggleTicker(t)}
                className={`py-2.5 rounded-xl text-sm font-bold transition-all border ${
                  isActive
                    ? 'bg-green-900/20 border-green-500/50 text-green-400 shadow-[0_0_10px_rgba(34,197,94,0.15)]'
                    : 'bg-[#18181b] border-[#27272a] text-gray-600 hover:text-gray-400 hover:border-[#3f3f46]'
                } active:scale-95`}
              >
                {isActive ? '✅ ' : ''}{t}
              </button>
            )
          })}
        </div>
      </div>
      
      {/* 📋 Section 3.1: Event Log Console (NEW [V24]) */}
      <div className="bg-[#121214] rounded-2xl border border-[#27272a] p-5 shadow-lg">
        <h3 className="text-white font-bold text-sm flex items-center gap-2 mb-3">
          📋 시스템 운영 아카이브 <span className="text-[0.55rem] text-gray-500 font-normal tracking-wider uppercase">(Event Archive)</span>
        </h3>
        <div className="bg-[#09090b] rounded-xl border border-[#27272a] p-0 overflow-hidden">
          <div className="max-h-[250px] overflow-y-auto scrollbar-thin scrollbar-thumb-[#3f3f46]">
            {events.length === 0 ? (
              <div className="p-8 text-center text-gray-600 text-[0.65rem]">지정된 작업 기록이 아직 없습니다.</div>
            ) : (
              <table className="w-full text-left text-[0.65rem] border-collapse">
                <thead className="sticky top-0 bg-[#18181b] border-b border-[#27272a] z-10 text-gray-500 font-bold">
                  <tr>
                    <th className="px-3 py-2 w-16">TIME</th>
                    <th className="px-3 py-2 w-20">TASK</th>
                    <th className="px-3 py-2">SUMMARY</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#27272a]">
                  {[...events].reverse().map((ev, idx) => (
                    <tr key={idx} className="hover:bg-[#18181b]/50 transition-colors">
                      <td className="px-3 py-2.5 text-gray-500 font-mono tracking-tighter">{ev.time}</td>
                      <td className="px-3 py-2.5">
                        <span className={`px-1.5 py-0.5 rounded-md font-bold text-[0.55rem] ${
                          ev.status === 'SUCCESS' ? 'text-green-500 bg-green-500/10' : 
                          ev.status === 'ERROR' ? 'text-red-500 bg-red-500/10' : 
                          'text-yellow-500 bg-yellow-500/10'
                        }`}>
                          {ev.task}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-gray-300 font-medium">
                        {ev.msg}
                        {ev.details && <div className="text-gray-500 mt-0.5 text-[0.6rem] leading-tight italic">{ev.details}</div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
        <p className="text-gray-600 text-[0.55rem] mt-2 italic px-1">
          ※ <b>운영 아카이브</b>: 자율 주행 엔진이 수행한 모든 스케줄과 제어 이력을 영구 보존하며, 실시간 상황실과 연동됩니다.
        </p>
      </div>

      {/* Section 4: Strategy Guide (collapsible) */}
      <div className="bg-[#121214] rounded-2xl border border-[#27272a] shadow-lg overflow-hidden">
        <button
          onClick={() => setShowGuide(!showGuide)}
          className="w-full p-5 flex justify-between items-center hover:bg-[#18181b] transition-colors"
        >
          <h3 className="text-white font-bold text-sm flex items-center gap-2">
            📖 전략 백서 & 가이드
          </h3>
          <span className={`text-gray-400 text-xl transition-transform duration-300 ${showGuide ? 'rotate-180' : ''}`}>▼</span>
        </button>
        {showGuide && (
          <div className="border-t border-[#27272a] p-5 animate-fade-in-up">
            <StrategyGuide />
          </div>
        )}
      </div>
    </div>
  )
}
