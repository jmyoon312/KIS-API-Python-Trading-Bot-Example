import { useEffect, useState, useRef } from 'react'
import axios from 'axios'
import StrategyGuide from './StrategyGuide'

const AVAILABLE_TICKERS = ['SOXL', 'TQQQ', 'UPRO', 'TECL', 'QLD', 'SPXL', 'FAS', 'LABU', 'FNGU', 'TNA'];

export default function SystemControl({ mode }: { mode: 'mock' | 'real' }) {
  const [config, setConfig] = useState<any>(null)
  const [account, setAccount] = useState<any>(null)
  const [engineVersion, setEngineVersion] = useState('V24')
  const [engineOn, setEngineOn] = useState(false)
  const [tactics, setTactics] = useState<any>({
    shield: false,
    shadow: false,
    turbo: false,
    sniper: true,
    jupjup: false,
    is_reverse: false,
    vix_aware: true,
    trend_filter: false,
    vwap_dominance: false
  })
  
  // 🔍 [V33 Search]
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [searchKeyword, setSearchKeyword] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('ALL')
  
  const [activeTickers, setActiveTickers] = useState<string[]>([])
  const [rebalancing, setRebalancing] = useState(false)
  const [forceRebalance, setForceRebalance] = useState(false)
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
      
      // 상태 동기화
      setEngineVersion(cfg.ENGINE_VERSION || 'V24')
      setEngineOn(cfg.ENGINE_STATUS === true)
      
      if (resLedger.data.account) {
        setAccount(resLedger.data.account)
        const ratios: Record<string, number> = {}
        cfgTickers.forEach((t: string) => {
          // 🚀 [V24 패치] 실시간 장부(Ledger)가 아닌 설정값(Config)의 portfolio_ratio를 우선 참조
          ratios[t] = cfg?.[t]?.portfolio_ratio || (1 / cfgTickers.length)
        })
        setLocalRatios(ratios)
      }
      
      const resAnalytics = await api.get(`/analytics?mode=${mode}`)
      if (resAnalytics.data.events) {
        setEvents(resAnalytics.data.events)
      }

      // 🏹 [V25] 글로벌 전술 설정 로드
      const resTactics = await api.get(`/settings/tactics?mode=${mode}`)
      if (resTactics.data.tactics) {
        setTactics(resTactics.data.tactics)
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

  const handleStrategyChange = async (key: string, value: any, label: string) => {
    // [V25.2] 즉각적인 UI 반영을 위해 로컬 상태 선반영
    setTactics((prev: any) => ({ ...prev, [key]: value }))
    
    try {
      if (key === 'version') setEngineVersion(value)

      await api.post('/settings/global-strategy', { mode, key, value })
      setStatusMsg(`✅ ${label} 변경 완료`)
      
      // 저장 후 최신 서버 상태로 최종 싱크
      await fetchData()
    } catch { 
      setStatusMsg(`❌ ${label} 변경 실패`) 
      // 실패 시 원래 데이터로 복구 위해 다시 로드
      fetchData()
    }
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
      const res = await api.post('/settings/seed', { mode, action: 'rebalance', force: forceRebalance })
      if (res.data.status === 'ok') {
        setStatusMsg(`✅ ${res.data.message}`)
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

  const updateRatio = (ticker: string, delta: number) => {
    setLocalRatios(prev => {
      const current = prev[ticker] || 0
      let next = Math.max(0, Math.min(1, current + delta))
      const otherSum = Object.entries(prev)
        .filter(([t]) => t !== ticker)
        .reduce((sum, [_, r]) => sum + r, 0)
      
      if (otherSum + next > 1.001) {
        next = Math.max(0, 1 - otherSum)
      }
      const updated = { ...prev, [ticker]: next }
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

  const calculatedHoldingsVal = account?.tickers ? Object.values(account.tickers).reduce((sum: number, t: any) => {
    return sum + (Number(t.qty || 0) * Number(t.current_price || 0))
  }, 0) : 0
  const totalAsset = account ? (account.cash || 0) + (calculatedHoldingsVal || account.holdings_value || 0) : 0

  const tickerSeeds = activeTickers.map((t: string) => ({
    ticker: t,
    seed: config?.[t]?.seed || 0,
    ratio: config?.[t]?.portfolio_ratio || 0,
    holdingQty: account?.tickers?.[t]?.qty || 0,
  }))

  const totalSeed = tickerSeeds.reduce((s: number, ts: any) => s + ts.seed, 0)

  return (
    <div className="space-y-4 animate-fade-in-up pb-12">
      {statusMsg && (
        <div className="fixed top-20 left-1/2 -translate-x-1/2 z-50 bg-[#18181b] border border-[#3f3f46] rounded-xl px-4 py-2.5 text-sm font-medium text-white animate-fade-in shadow-lg">
          {statusMsg}
        </div>
      )}

      {/* Section 0: 엔진 가동 (Engine Power) */}
      <div className="bg-[#121214] rounded-2xl border border-[#27272a] p-5 shadow-lg relative overflow-hidden">
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
      </div>

      {/* ⚙️ 무한매수법 베이스 전략 선택 (Base Strategy Selection) */}
      <div className="bg-[#121214] rounded-2xl border border-[#27272a] p-5 shadow-lg space-y-4">
        <h4 className="text-white font-bold text-xs uppercase tracking-widest mb-4 flex items-center gap-2">
          ⚙️ 무한매수법 베이스 전략 <span className="text-[0.6rem] text-blue-500 font-normal tracking-wider lowercase">(Laoer Methodology)</span>
        </h4>
        
        <div className="grid grid-cols-1 gap-3">
          {[
            { id: 'V13', name: 'V13 [V1 원본 정석]', sub: '40분할 / 평단·별값 분할 매수', desc: '라오어 원작 방법론의 가장 기본이 되는 정석 분할 매수 전략' },
            { id: 'V14', name: 'V14 [V2.1 가변 방어]', sub: '평단 집중 매체 및 전술 최적화', desc: '평단가(Avg)에서 1.0 분량을 집중 매수하여 방어력을 높이고, 별도 전술로 수익을 극대화' },
            { id: 'V24', name: 'V24 [V4 제로 리버스]', sub: 'T-Value 정밀 운용 및 쿼터 익절', desc: '1/4 쿼터 익절로 현금을 확보하고, 원금 소진 시 리버스(제로) 모드로 자동 전환' }
          ].map(s => (
            <button
              key={s.id}
              onClick={() => handleStrategyChange('version', s.id, '베이스 전략')}
              className={`p-4 rounded-2xl border text-left transition-all relative overflow-hidden group ${
                engineVersion === s.id 
                  ? 'bg-blue-600/10 border-blue-500 shadow-[0_0_20px_rgba(59,130,246,0.15)]' 
                  : 'bg-[#18181b] border-[#27272a] hover:border-gray-600'
              }`}
            >
              {engineVersion === s.id && (
                <div className="absolute top-0 right-0 p-2">
                  <span className="flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                  </span>
                </div>
              )}
              <div className="flex justify-between items-center mb-1">
                <span className={`text-sm font-black ${engineVersion === s.id ? 'text-blue-400' : 'text-white'}`}>{s.name}</span>
              </div>
              <div className="text-gray-300 text-[0.65rem] font-bold mb-1 opacity-80">{s.sub}</div>
              <p className="text-gray-500 text-[0.6rem] leading-relaxed group-hover:text-gray-400 transition-colors">{s.desc}</p>
            </button>
          ))}
        </div>
      </div>

      {/* 🛡️ 전술 명령 센터 (Tactical Command Center) - NEW V25 */}
      <div className="bg-[#121214] rounded-2xl border border-[#27272a] p-5 shadow-lg space-y-4">
        <h3 className="text-white font-bold text-sm flex items-center gap-2">
          🛡️ 전술 명령 센터 <span className="text-[0.55rem] text-blue-500 font-normal tracking-wider uppercase">(Tactical Command Center)</span>
        </h3>
        <p className="text-gray-500 text-[0.65rem] -mt-2">무한매수법 Base 전략 위에 덧씌워지는 상황별 전술들을 일괄 통제합니다.</p>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
          {/* [방어] 쉴드 (MDD 방어) */}
          <div className={`p-4 rounded-xl border transition-all flex justify-between items-center ${tactics.shield ? 'bg-blue-900/10 border-blue-500/40 shadow-[0_0_15px_rgba(59,130,246,0.1)]' : 'bg-[#18181b] border-[#27272a]'}`}>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-white">[방어] 쉴드 (MDD 방어)</span>
                {tactics.shield && <span className="animate-pulse w-1.5 h-1.5 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.8)]"></span>}
              </div>
              <p className="text-[0.6rem] text-gray-500 mt-0.5">T-Value 기반 가변 분할 확장</p>
            </div>
            <button onClick={() => handleStrategyChange('shield', !tactics.shield, '쉴드 (MDD 방어)')} className={`w-10 h-5 rounded-full relative transition-colors ${tactics.shield ? 'bg-blue-600' : 'bg-[#27272a]'}`}>
              <div className={`w-3 h-3 rounded-full bg-white absolute top-1 transition-transform ${tactics.shield ? 'translate-x-6' : 'translate-x-1'}`}></div>
            </button>
          </div>

          {/* [진입] 새도우 스트라이크 */}
          <div className={`p-4 rounded-xl border transition-all flex justify-between items-center ${tactics.shadow ? 'bg-purple-900/10 border-purple-500/40 shadow-[0_0_15px_rgba(168,85,247,0.1)]' : 'bg-[#18181b] border-[#27272a]'}`}>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-white">[진입] 새도우 스트라이크</span>
                {tactics.shadow && <span className="animate-pulse w-1.5 h-1.5 rounded-full bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.8)]"></span>}
              </div>
              <p className="text-[0.6rem] text-gray-500 mt-0.5">최저가 대비 반등 포착 실시간 매수</p>
            </div>
            <button onClick={() => handleStrategyChange('shadow', !tactics.shadow, '새도우 스트라이크')} className={`w-10 h-5 rounded-full relative transition-colors ${tactics.shadow ? 'bg-purple-600' : 'bg-[#27272a]'}`}>
              <div className={`w-3 h-3 rounded-full bg-white absolute top-1 transition-transform ${tactics.shadow ? 'translate-x-6' : 'translate-x-1'}`}></div>
            </button>
          </div>

          {/* [가속] 터보 부스터 */}
          <div className={`p-4 rounded-xl border transition-all flex justify-between items-center ${tactics.turbo ? 'bg-red-900/10 border-red-500/40 shadow-[0_0_15px_rgba(239,68,68,0.1)]' : 'bg-[#18181b] border-[#27272a]'}`}>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-white">[가속] 터보 부스터</span>
                {tactics.turbo && <span className="animate-pulse w-1.5 h-1.5 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]"></span>}
              </div>
              <p className="text-[0.6rem] text-gray-500 mt-0.5">급락장 평단가 하강 가속화</p>
            </div>
            <button onClick={() => handleStrategyChange('turbo', !tactics.turbo, '터보 부스터')} className={`w-10 h-5 rounded-full relative transition-colors ${tactics.turbo ? 'bg-red-600' : 'bg-[#27272a]'}`}>
              <div className={`w-3 h-3 rounded-full bg-white absolute top-1 transition-transform ${tactics.turbo ? 'translate-x-6' : 'translate-x-1'}`}></div>
            </button>
          </div>

          {/* [탈출] 스나이퍼 익절 */}
          <div className={`p-4 rounded-xl border transition-all flex justify-between items-center ${tactics.sniper ? 'bg-green-900/10 border-green-500/40 shadow-[0_0_15px_rgba(34,197,94,0.15)]' : 'bg-[#18181b] border-[#27272a]'}`}>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-white">[탈출] 스나이퍼 익절</span>
                {tactics.sniper && <span className="animate-pulse w-1.5 h-1.5 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.8)]"></span>}
              </div>
              <p className="text-[0.6rem] text-gray-500 mt-0.5">별지점 기반 1/4 선제 익절</p>
            </div>
            <button onClick={() => handleStrategyChange('sniper', !tactics.sniper, '스나이퍼 익절')} className={`w-10 h-5 rounded-full relative transition-colors ${tactics.sniper ? 'bg-green-600' : 'bg-[#27272a]'}`}>
              <div className={`w-3 h-3 rounded-full bg-white absolute top-1 transition-transform ${tactics.sniper ? 'translate-x-6' : 'translate-x-1'}`}></div>
            </button>
          </div>

          {/* [정밀] 줍줍 거미줄 */}
          <div className={`p-4 rounded-xl border transition-all flex justify-between items-center ${tactics.jupjup ? 'bg-yellow-900/10 border-yellow-500/40 shadow-[0_0_15px_rgba(234,179,8,0.1)]' : 'bg-[#18181b] border-[#27272a]'}`}>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-white">[정밀] 줍줍 거미줄</span>
                {tactics.jupjup && <span className="animate-pulse w-1.5 h-1.5 rounded-full bg-yellow-500 shadow-[0_0_8px_rgba(234,179,8,0.8)]"></span>}
              </div>
              <p className="text-[0.6rem] text-gray-500 mt-0.5">자투리 현금 기반 촘촘한 추가 매수</p>
            </div>
            <button onClick={() => handleStrategyChange('jupjup', !tactics.jupjup, '줍줍 거미줄')} className={`w-10 h-5 rounded-full relative transition-colors ${tactics.jupjup ? 'bg-yellow-600' : 'bg-[#27272a]'}`}>
              <div className={`w-3 h-3 rounded-full bg-white absolute top-1 transition-transform ${tactics.jupjup ? 'translate-x-6' : 'translate-x-1'}`}></div>
            </button>
          </div>

          {/* [탈출] V-REV 리버스 모드 */}
          <div className={`p-4 rounded-xl border transition-all flex justify-between items-center ${tactics.is_reverse ? 'bg-purple-900/10 border-purple-500/40 shadow-[0_0_15px_rgba(168,85,247,0.1)]' : 'bg-[#18181b] border-[#27272a]'}`}>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-white">🔄 V-REV 리버스 모드</span>
                {tactics.is_reverse && <span className="animate-pulse w-1.5 h-1.5 rounded-full bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.8)]"></span>}
              </div>
              <p className="text-[0.6rem] text-gray-500 mt-0.5">평단가 부근 순환 매매 탈출 전술</p>
            </div>
            <button onClick={() => handleStrategyChange('is_reverse', !tactics.is_reverse, 'V-REV 리버스 모드')} className={`w-10 h-5 rounded-full relative transition-colors ${tactics.is_reverse ? 'bg-purple-600' : 'bg-[#27272a]'}`}>
              <div className={`w-3 h-3 rounded-full bg-white absolute top-1 transition-transform ${tactics.is_reverse ? 'translate-x-6' : 'translate-x-1'}`}></div>
            </button>
          </div>

          {/* [보조] VIX-Aware Sizing */}
          <div className={`p-4 rounded-xl border transition-all flex justify-between items-center ${tactics.vix_aware ? 'bg-blue-900/10 border-blue-500/40 shadow-[0_0_15px_rgba(59,130,246,0.1)]' : 'bg-[#18181b] border-[#27272a]'}`}>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-white">⚡ VIX-Aware 수량 조절</span>
                {tactics.vix_aware && <span className="animate-pulse w-1.5 h-1.5 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.8)]"></span>}
              </div>
              <p className="text-[0.6rem] text-gray-500 mt-0.5">변동성 기반 매수 물량 자동 최적화</p>
            </div>
            <button onClick={() => handleStrategyChange('vix_aware', !tactics.vix_aware, 'VIX-Aware 조절')} className={`w-10 h-5 rounded-full relative transition-colors ${tactics.vix_aware ? 'bg-blue-600' : 'bg-[#27272a]'}`}>
              <div className={`w-3 h-3 rounded-full bg-white absolute top-1 transition-transform ${tactics.vix_aware ? 'translate-x-6' : 'translate-x-1'}`}></div>
            </button>
          </div>

          {/* [보조] VWAP Dominance 분석 */}
          <div className={`p-4 rounded-xl border transition-all flex justify-between items-center ${tactics.vwap_dominance ? 'bg-orange-900/10 border-orange-500/40 shadow-[0_0_15px_rgba(249,115,22,0.1)]' : 'bg-[#18181b] border-[#27272a]'}`}>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-white">📊 VWAP 지배력 분석</span>
                {tactics.vwap_dominance && <span className="animate-pulse w-1.5 h-1.5 rounded-full bg-orange-500 shadow-[0_0_8px_rgba(249,115,22,0.8)]"></span>}
              </div>
              <p className="text-[0.6rem] text-gray-500 mt-0.5">거래량 기반 FOMO 및 추격 매수 방어</p>
            </div>
            <button onClick={() => handleStrategyChange('vwap_dominance', !tactics.vwap_dominance, 'VWAP 분석')} className={`w-10 h-5 rounded-full relative transition-colors ${tactics.vwap_dominance ? 'bg-orange-600' : 'bg-[#27272a]'}`}>
              <div className={`w-3 h-3 rounded-full bg-white absolute top-1 transition-transform ${tactics.vwap_dominance ? 'translate-x-6' : 'translate-x-1'}`}></div>
            </button>
          </div>
        </div>


      </div>

      {/* Section 2: 시드 재분배 (Smart Rebalance) */}
      <div className="bg-[#121214] rounded-2xl border border-[#27272a] p-5 shadow-lg">
        <h3 className="text-white font-bold text-sm flex items-center gap-2 mb-3">
          ⚖️ 시드 재분배 <span className="text-[0.55rem] text-gray-500 font-normal tracking-wider uppercase">(Seed Rebalance)</span>
        </h3>
        
        <div className="bg-[#18181b] rounded-xl border border-[#27272a] p-4 mb-4">
          <div className="flex justify-between items-center mb-1 pb-2 border-b border-[#27272a]/50">
            <span className="text-gray-400 text-[0.6rem] font-bold uppercase tracking-widest">💰 계좌 총자산</span>
            <span className="text-white font-black text-sm tabular-nums">${totalAsset.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
          </div>
          
          <div className="flex justify-between text-[0.6rem] py-1 text-gray-500">
            <span>현금(Cash)</span>
            <span className="text-gray-400">${(account?.cash || 0).toLocaleString()}</span>
          </div>
          <div className="flex justify-between text-[0.6rem] py-1 text-gray-500">
            <span>주식(Holdings)</span>
            <span className="text-gray-400">${(calculatedHoldingsVal || 0).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</span>
          </div>
          <div className="flex justify-between text-[0.6rem] py-1 text-yellow-600/70 font-bold border-t border-[#27272a] mt-1 pt-1 pb-2">
            <span>보유 시드 합계</span>
            <span>${totalSeed.toLocaleString()}</span>
          </div>
          
          <div className="text-[0.65rem] font-bold text-gray-400 mb-3 mt-2 border-t border-[#27272a]/30 pt-3 flex justify-between">
            <span>📊 종목별 타겟 비중 (%)</span>
            <span className={`px-1.5 py-0.5 rounded ${Math.abs(tickerSeeds.reduce((a, b) => a + (b.ratio || 0), 0) - 1) < 0.001 ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'} font-black`}>
               합계: {(tickerSeeds.reduce((a, b) => a + (b.ratio || 0), 0) * 100).toFixed(0)}%
            </span>
          </div>
          
          <div className="space-y-3">
            {tickerSeeds.map(ts => (
              <div key={ts.ticker} className="space-y-1">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-gray-100 font-bold flex items-center gap-1">
                    {ts.ticker}
                    {ts.holdingQty > 0 && <span className="text-[0.6rem] bg-yellow-500/10 text-yellow-500 px-1 rounded border border-yellow-500/20">{ts.holdingQty}주</span>}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-yellow-500 font-bold tabular-nums text-[0.65rem]">
                      ${Math.round(totalAsset * (localRatios[ts.ticker] || 0)).toLocaleString()}
                    </span>
                    <div className="flex items-center bg-[#09090b] rounded-lg border border-[#3f3f46] p-0.5 overflow-hidden">
                      <button onMouseDown={() => startAdjusting(ts.ticker, -0.01)} onMouseUp={stopAdjusting} onMouseLeave={stopAdjusting} className="w-5 h-5 flex items-center justify-center text-gray-500 hover:text-white hover:bg-[#27272a] transition-colors rounded">
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
                      <button onMouseDown={() => startAdjusting(ts.ticker, 0.01)} onMouseUp={stopAdjusting} onMouseLeave={stopAdjusting} className="w-5 h-5 flex items-center justify-center text-gray-500 hover:text-white hover:bg-[#27272a] transition-colors rounded">
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
          className="w-full py-3 rounded-xl font-bold text-sm transition-all border border-blue-500/50 bg-blue-900/20 text-blue-400 hover:bg-blue-800/30 active:scale-[0.98] disabled:opacity-40 flex justify-center items-center gap-2"
        >
          {rebalancing ? '⏳ 재분배 중...' : '⚖️ 설정된 비중으로 시드 일괄 재분배'}
        </button>
        
        <div className="mt-3 flex items-center gap-2 justify-center">
          <input type="checkbox" id="forceRebalance" checked={forceRebalance} onChange={(e) => setForceRebalance(e.target.checked)} className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 bg-[#18181b]" />
          <label htmlFor="forceRebalance" className="text-[0.65rem] text-gray-400 cursor-pointer hover:text-gray-200 transition-colors">
            ⚠️ <span className="underline decoration-dotted text-red-500/70">즉시 강제 적용</span> (활동 중인 매매에도 즉각 반영)
          </label>
        </div>
      </div>

      {/* Section 3: 운용 종목 선택 (Tickers) */}
      <div className="bg-[#121214] rounded-2xl border border-[#27272a] p-5 shadow-lg">
        <h3 className="text-white font-bold text-sm flex items-center gap-2 mb-3">
          🎯 운용 종목 선택 <span className="text-[0.55rem] text-gray-500 font-normal tracking-wider uppercase">(Active Tickers)</span>
        </h3>
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
      
      {/* 📋 Section 3.1: 운영 아카이브 (Event Archive) */}
      <div className="bg-[#121214] rounded-2xl border border-[#27272a] p-5 shadow-lg">
        <div className="flex flex-wrap justify-between items-center gap-2 mb-3">
          <h3 className="text-white font-bold text-sm flex items-center gap-2">
            📋 운영 아카이브 <span className="text-[0.55rem] text-gray-500 font-normal tracking-wider uppercase">(Event Archive)</span>
          </h3>
          <button
            onClick={async () => {
              if (window.confirm("운영 아카이브 기록을 영구적으로 초기화하시겠습니까?")) {
                try {
                  await api.post('/events/clear', { mode });
                  setSearchKeyword('');
                  setStartDate('');
                  setEndDate('');
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

        {/* 🔍 [V33 Search Bar] */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4 bg-[#09090b] p-3 rounded-xl border border-[#27272a]/50">
          <div className="flex flex-col gap-1">
            <span className="text-[0.5rem] text-gray-600 font-bold ml-1">상태/카테고리</span>
            <select 
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="bg-[#18181b] border border-[#27272a] rounded-lg text-[0.6rem] text-white p-1.5 outline-none focus:border-blue-500/50"
            >
              <option value="ALL">전체 보기</option>
              <option value="TRADE">매매 기록 (TRADE)</option>
              <option value="SCHEDULE">일정 기록 (SCHEDULE)</option>
              <option value="SYSTEM">시스템 로그 (SYSTEM)</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[0.5rem] text-gray-600 font-bold ml-1">검색 키워드</span>
            <input 
              type="text" 
              placeholder="내용 검색..." 
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              className="bg-[#18181b] border border-[#27272a] rounded-lg text-[0.6rem] text-white p-1.5 outline-none focus:border-blue-500/50"
            />
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[0.5rem] text-gray-600 font-bold ml-1">기간 시작 (MM/DD)</span>
            <input 
              type="text" 
              placeholder="04/01" 
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="bg-[#18181b] border border-[#27272a] rounded-lg text-[0.6rem] text-white p-1.5 outline-none focus:border-blue-500/50"
            />
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[0.5rem] text-gray-600 font-bold ml-1">기간 종료 (MM/DD)</span>
            <input 
              type="text" 
              placeholder="04/30" 
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="bg-[#18181b] border border-[#27272a] rounded-lg text-[0.6rem] text-white p-1.5 outline-none focus:border-blue-500/50"
            />
          </div>
        </div>
        <div className="bg-[#09090b] rounded-xl border border-[#27272a] p-0 overflow-hidden">
          <div className="max-h-[250px] overflow-y-auto scrollbar-thin scrollbar-thumb-[#3f3f46]">
            {events.length === 0 ? (
              <div className="p-8 text-center text-gray-600 text-[0.65rem]">기록이 없습니다.</div>
            ) : (
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
                  {[...events]
                    .filter((ev: any) => {
                      const k = searchKeyword.toLowerCase();
                      const match_k = !k || (ev.msg?.toLowerCase().includes(k) || ev.task?.toLowerCase().includes(k));
                      const match_c = categoryFilter === 'ALL' || ev.category === categoryFilter;
                      const match_s = !startDate || ev.date >= startDate;
                      const match_e = !endDate || ev.date <= endDate;
                      return match_k && match_c && match_s && match_e;
                    })
                    .reverse().map((ev, idx) => (
                    <tr key={idx} className="hover:bg-[#18181b]/50 transition-colors">
                      <td className="px-3 py-2.5 text-gray-600 font-mono tracking-tighter text-[0.6rem]">{ev.date || ''}</td>
                      <td className="px-2 py-2.5 text-gray-500 font-mono tracking-tighter">{ev.time}</td>
                      <td className="px-2 py-2.5">
                        <div className="flex flex-col gap-1">
                          <span className={`px-1.5 py-0.5 rounded-md font-bold text-[0.55rem] w-max ${
                            ev.status === 'SUCCESS' ? 'text-green-500 bg-green-500/10' : 
                            ev.status === 'ERROR' ? 'text-red-500 bg-red-500/10' : 
                            ev.status === 'WARNING' ? 'text-yellow-500 bg-yellow-500/10' :
                            'text-blue-500 bg-blue-500/10'
                          }`}>
                            {ev.task}
                          </span>
                          {ev.category && (
                            <span className="text-[0.45rem] text-gray-600 font-black tracking-widest px-1 uppercase">
                              {ev.category}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-gray-300 font-medium leading-relaxed">
                        {ev.msg}
                        {ev.details && <div className="text-gray-500 mt-1 text-[0.6rem] leading-tight italic font-light">{ev.details}</div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {/* Section 4: 전략 가이드 */}
      <div className="bg-[#121214] rounded-2xl border border-[#27272a] shadow-lg overflow-hidden">
        <button onClick={() => setShowGuide(!showGuide)} className="w-full p-5 flex justify-between items-center hover:bg-[#18181b] transition-colors">
          <h3 className="text-white font-bold text-sm flex items-center gap-2">📖 전략 백서 & 가이드</h3>
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
