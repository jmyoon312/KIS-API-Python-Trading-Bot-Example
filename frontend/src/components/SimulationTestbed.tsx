import { useState, useEffect } from 'react'
import axios from 'axios'
import { 
  Play, RotateCcw, Zap, TrendingUp, AlertTriangle, 
  ArrowRightLeft, ShieldAlert, Target,
  Compass, Rocket, AlertOctagon, Cpu
} from 'lucide-react'
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer 
} from 'recharts'
// import { toast } from 'react-hot-toast'
const toast = {
  success: (msg: string, _opt?: any) => alert(`✅ ${msg}`),
  error: (msg: string, _opt?: any) => alert(`❌ ${msg}`),
  loading: (msg: string, _opt?: any) => { console.log(`⏳ ${msg}`); return "loading_id"; }
};

interface SimulationResult {
  summary: {
    total_return: number
    final_total: number
    mdd: number
    sharpe: number
    win_rate: number
    recovery_days: number
    total_trades: number
    annual_return: number
  }
  equity_curve: any[]
}

interface ExhaustiveResult {
  best_path: any
  top_candidates: any[]
  all_candidates: any[] // 🛡️ [V29.6] 전체 64개 랭킹
  analysis_date: string
}

// --- 컴포넌트: 고급 게이지 바 (Expert Rating Gauge) ---
const ExpertGauge = ({ value, max, label = "", color = "border-amber-500", shadow = "shadow-[0_0_15px_rgba(245,158,11,0.5)]" }: { value: number, max: number, label?: string, color?: string, shadow?: string }) => {
  const percentage = Math.min(100, (value / max) * 100);
  return (
    <div className="relative w-48 h-24 overflow-hidden">
      <div className="absolute inset-0 border-[10px] border-slate-800 rounded-t-full" />
      <div 
        className={`absolute inset-0 border-[10px] ${color} rounded-t-full transition-all duration-1000 ease-out ${shadow}`} 
        style={{ 
          clipPath: `inset(0 ${100 - percentage}% 0 0)`,
          transform: `rotate(0deg)` 
        }} 
      />
      <div className="absolute bottom-0 w-full text-center">
        <span className="text-3xl font-black italic text-white tracking-tighter">{value.toFixed(0)}</span>
        {label && <span className="text-[10px] text-slate-500 font-bold ml-1">{label}</span>}
        <div className="text-[8px] text-slate-600 font-black uppercase tracking-widest mt-0.5">범위: 0 - {max}</div>
      </div>
    </div>
  )
}

// --- 컴포넌트: 상황실 규격 정밀 토글 스위치 (Switch) ---
const ToggleSwitch = ({ active, onChange, label, desc, themeColor }: any) => {
  return (
    <div className="flex items-center justify-between p-4 bg-slate-900/40 rounded-2xl border border-white/5 hover:border-white/10 transition-all group">
      <div className="flex flex-col text-left">
        <span className="text-[10px] font-black text-white uppercase tracking-tighter mb-1">{label}</span>
        <p className="text-[9px] text-slate-500 font-bold leading-tight">{desc}</p>
      </div>
      <button 
        onClick={() => onChange(!active)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${active ? themeColor || 'bg-blue-600' : 'bg-slate-800'}`}
      >
        <span className={`${active ? 'translate-x-6' : 'translate-x-1'} inline-block h-4 w-4 transform rounded-full bg-white transition-transform`} />
      </button>
    </div>
  )
}

const SimulationTestbed = () => {
  const [ticker, setTicker] = useState('MIXED')
  const [seed, setSeed] = useState(10000)
  const [split, setSplit] = useState(40)
  const [target, setTarget] = useState(10)
  const [version, setVersion] = useState('V14')
  
  // Tactical Toggles
  const [useElastic, setUseElastic] = useState(true)
  const [useAtrShield, setUseAtrShield] = useState(true)
  const [useTurbo, setUseTurbo] = useState(true)
  const [useShadow, setUseShadow] = useState(true)
  const [useShield, setUseShield] = useState(true)
  const [useSniper, setUseSniper] = useState(true)
  const [useEmergency, setUseEmergency] = useState(true)
  const [useJupjup, setUseJupjup] = useState(false)
  
  // 🛡️ [V29.7] Precision Lab Extensions
  const [resolution, setResolution] = useState<'1D' | '1M'>('1D')
  const [sniperDrop, setSniperDrop] = useState(1.5)

  const [loading, setLoading] = useState(false)
  const [exhaustiveLoading, setExhaustiveLoading] = useState(false)
  const [result, setResult] = useState<SimulationResult | null>(null)
  const [intervention, setIntervention] = useState<any>(null)
  const [exhaustiveResult, setExhaustiveResult] = useState<ExhaustiveResult | null>(null)
  const [activeRegimeFilter, setActiveRegimeFilter] = useState<'ALL' | 'SIDEWAYS' | 'BEAR' | 'SHOCK' | 'STRONG_BULL'>('ALL')
  const [deployLoading, setDeployLoading] = useState(false)

  // 🛰️ 실시간 시장 국면 분석 데이터
  const [marketPulse, setMarketPulse] = useState<any>(null)
  const [pulseLoading, setPulseLoading] = useState(true)

  useEffect(() => {
    fetchMarketPulse()
  }, [])

  const fetchMarketPulse = async () => {
    setPulseLoading(true)
    try {
      const res = await axios.get('/api/market/pulse')
      if (res.data.status === 'ok') {
        setMarketPulse(res.data.pulse)
      }
    } catch (e) {
      console.error("Market Pulse Fetch Error", e)
    } finally {
      setPulseLoading(false)
    }
  }

  const runSimulation = async () => {
    setLoading(true)
    setResult(null)
    const t = toast.loading(`${ticker} 전략 시뮬레이션 가동 중...`)
    try {
      const endpoint = resolution === '1M' ? '/api/simulation/precision' : '/api/simulation/run'
      const resp = await axios.post(endpoint, {
        ticker: ticker === 'MIXED' ? 'TQQQ' : ticker,
        tickers_weight: ticker === 'MIXED' ? { "TQQQ": 0.55, "SOXL": 0.45 } : { [ticker]: 1.0 },
        seed, split, target, version,
        use_turbo: useTurbo,
        use_shadow: useShadow,
        use_shield: useShield,
        use_sniper: useSniper,
        use_emergency: useEmergency,
        use_jupjup: useJupjup,
        sniper_drop: sniperDrop
      })

      if (resp.data.status === 'error') {
        toast.error(`시뮬레이션 실패: ${resp.data.message}`, { id: t })
        return
      }

      setResult(resp.data.result)
      setIntervention(resp.data.intervention || {})
      toast.success('시뮬레이션 완료!', { id: t })
    } catch (e) {
      toast.error('시뮬레이션 서버 통신 실패', { id: t })
    } finally {
      setLoading(false)
    }
  }

  const runExhaustive = async () => {
    setExhaustiveLoading(true)
    setExhaustiveResult(null)
    const t = toast.loading('64가지 전술 조합 전수 조사 중... (약 10초)')
    try {
      const endpoint = resolution === '1M' ? '/api/simulation/precision-exhaustive' : '/api/simulation/exhaustive'
      const res = await axios.post(endpoint, {
        ticker: ticker === 'MIXED' ? 'TQQQ' : ticker,
        tickers_weight: ticker === 'MIXED' ? { "TQQQ": 0.55, "SOXL": 0.45 } : { [ticker]: 1.0 },
        seed, version, split, target,
        sniper_drop: sniperDrop
      })

      if (res.data.status === 'error') {
        toast.error(`최적화 실패: ${res.data.message}`, { id: t })
        return
      }

      setExhaustiveResult(res.data)
      toast.success('전술 최적화 완료!', { id: t })
    } catch (e) {
      console.error(e)
      toast.error('전수 조사 중 오류가 발생했습니다.', { id: t })
    }
    setExhaustiveLoading(false)
  }

  const applyStrategy = (cand: any) => {
    if (!cand.combo) return
    const modules = cand.combo
    if (modules.turbo !== undefined) setUseTurbo(modules.turbo)
    if (modules.shadow !== undefined) setUseShadow(modules.shadow)
    if (modules.shield !== undefined) setUseShield(modules.shield)
    if (modules.sniper !== undefined) setUseSniper(modules.sniper)
    if (modules.emergency !== undefined) setUseEmergency(modules.emergency)
    if (modules.jupjup !== undefined) setUseJupjup(modules.jupjup)
    
    if (cand.version) setVersion(cand.version)
    
    toast.success(`${cand.idx + 1}위 전략 설정이 시뮬레이터에 동기화되었습니다.`)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const deployToBot = async (cand: any, isReal: boolean) => {
    const confirmMsg = `최적화된 전략을 ${isReal ? '실전(REAL)' : '모의(MOCK)'} 봇에 즉시 투입하시겠습니까?\n\n- 버전: ${cand.version}\n- 전술: ${Object.keys(cand.combo).filter(k => cand.combo[k] === true).join(', ')}`
    if (!window.confirm(confirmMsg)) return
 
    setDeployLoading(true)
    try {
      const res = await axios.post('/api/simulation/deploy', {
        is_real: isReal,
        version: cand.version,
        modules: cand.combo
      })
      if (res.data.status === 'success') {
        toast.success(res.data.msg)
      } else {
        toast.error(res.data.msg)
      }
    } catch (e) {
      toast.error('배포 중 서버 오류가 발생했습니다.')
    }
    setDeployLoading(false)
  }

  const getFilteredCandidates = () => {
    if (!exhaustiveResult?.all_candidates) return []
    let list = [...exhaustiveResult.all_candidates]
    
    if (activeRegimeFilter !== 'ALL') {
      list.sort((a, b) => {
        const aRet = a.regime_stats?.[activeRegimeFilter]?.avg_ret || -999
        const bRet = b.regime_stats?.[activeRegimeFilter]?.avg_ret || -999
        return bRet - aRet
      })
    } else {
      list.sort((a, b) => b.score - a.score)
    }
    return list
  }

  const filteredCandidates = getFilteredCandidates()

  return (
    <div className="space-y-4 animate-fade-in-up pb-12">
        <header className="flex justify-between items-center mb-4 px-1">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-black text-white italic tracking-tight flex items-center gap-2">
              🔬 전술 연구소
              <span className="text-blue-500/50 font-black text-[9px] uppercase tracking-widest border border-blue-500/20 px-1.5 py-0.5 rounded leading-none">v29.9 Precision</span>
            </h2>
          </div>
          <div className="text-[9px] text-slate-500 font-bold uppercase tracking-widest">정밀 전략 시뮬레이션 시스템</div>
        </header>

        {/* 🛡️ [V29.6 Restoration] 실전 시장 상황 및 전문가 조언 (Top Assessment Section) */}
        <section className="bg-slate-900/40 rounded-3xl border border-white/10 p-6 backdrop-blur-3xl relative overflow-hidden group shadow-2xl">
          <div className="absolute inset-0 bg-gradient-to-br from-blue-500/[0.03] to-indigo-500/[0.03] pointer-events-none" />
          
          <div className="flex flex-col lg:flex-row justify-between items-center gap-6 relative z-10 text-left">
            <div className="flex-1 space-y-4">
              <div className="flex items-center gap-2">
                <div className="p-1.5 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                  <Compass className="w-4 h-4 text-blue-400" />
                </div>
                <h3 className="text-sm font-black text-white italic tracking-tight uppercase">시장 진단 및 전문가 조언</h3>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* 전문가 리포트 카드 */}
                <div className="bg-white/5 rounded-2xl p-4 border border-white/5 shadow-inner">
                  <div className="flex items-start gap-3">
                    <div className="p-2 bg-blue-500/20 rounded-lg"><Rocket className="w-4 h-4 text-blue-400" /></div>
                    <div className="flex flex-col text-left">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[9px] font-black text-blue-400 uppercase tracking-widest italic leading-none">전문가 분석 리포트</span>
                        {!pulseLoading && (
                          <span className={`px-2 py-0.5 rounded text-[8px] font-black uppercase ${marketPulse?.vix_vitals?.spy_trend === 'BULL' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                            추세: {marketPulse?.vix_vitals?.spy_trend === 'BULL' ? '상승(BULL)' : '하락(BEAR)'}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-slate-100 font-bold leading-relaxed italic">
                        {pulseLoading ? "분석 중..." : `"${marketPulse?.expert_advice || '서버 연결 중입니다.'}"`}
                      </div>
                    </div>
                  </div>
                </div>

                {/* 지표 요약 카드 */}
                <div className="bg-slate-950/40 rounded-2xl p-4 border border-white/5 flex flex-col justify-center">
                  <div className="grid grid-cols-2 gap-6">
                     <div className="space-y-1">
                        <span className="text-[8px] font-black text-slate-500 uppercase tracking-widest">현재 공포 지수 (VIX)</span>
                        <div className="flex items-center gap-2">
                          <div className="text-base font-black text-white tabular-nums tracking-tight">{marketPulse?.vix_vitals?.vix?.toFixed(2) || '0.00'}</div>
                          <span className={`text-[9px] font-bold ${marketPulse?.vix_vitals?.vix > 25 ? 'text-rose-500' : 'text-emerald-500'}`}>
                            {marketPulse?.vix_vitals?.vix > 25 ? '▼ 변동성 높음' : '▲ 안정적'}
                          </span>
                        </div>
                     </div>
                     <div className="space-y-1">
                        <span className="text-[8px] font-black text-slate-500 uppercase tracking-widest">시장 심리 (Sentiment)</span>
                        <div className={`text-base font-black uppercase tracking-tight ${marketPulse?.fear_greed?.rating?.includes('FEAR') ? 'text-rose-400' : 'text-emerald-400'}`}>
                           {marketPulse?.fear_greed?.rating === 'EXTREME FEAR' ? '극도 공포' : 
                            marketPulse?.fear_greed?.rating === 'FEAR' ? '공포' : 
                            marketPulse?.fear_greed?.rating === 'NEUTRAL' ? '중립' : 
                            marketPulse?.fear_greed?.rating === 'GREED' ? '탐욕' : 
                            marketPulse?.fear_greed?.rating === 'EXTREME GREED' ? '극도 탐욕' : '분석 중'}
                        </div>
                     </div>
                  </div>
                  <button onClick={fetchMarketPulse} disabled={pulseLoading} className="mt-4 flex items-center justify-center gap-2 w-full py-1.5 bg-white/5 hover:bg-white/10 rounded-xl border border-white/10 transition-all text-[9px] font-black text-slate-400">
                    <RotateCcw className={`w-3 h-3 ${pulseLoading ? 'animate-spin' : ''}`} />
                    데이터 수동 갱신
                  </button>
                </div>
              </div>
            </div>
            
            <div className="w-full lg:w-auto flex flex-col items-center gap-2 bg-slate-950/30 p-4 rounded-3xl border border-white/5 shadow-2xl">
              <ExpertGauge 
                value={marketPulse?.fear_greed?.score || 50} 
                max={100} 
                label="Greed" 
                color={marketPulse?.fear_greed?.score > 70 ? "border-rose-500" : marketPulse?.fear_greed?.score < 30 ? "border-emerald-500" : "border-blue-500"}
                shadow={marketPulse?.fear_greed?.score > 70 ? "shadow-[0_0_15px_rgba(244,63,94,0.5)]" : marketPulse?.fear_greed?.score < 30 ? "shadow-[0_0_15px_rgba(16,185,129,0.5)]" : "shadow-[0_0_15px_rgba(59,130,246,0.5)]"}
              />
              <div className="text-[9px] font-black text-slate-500 uppercase tracking-widest leading-none">실시간 시장 탐욕 지수</div>
            </div>
          </div>
        </section>

        {/* 📊 Ticker & Simulation Context Bar */}
        <div className="flex flex-col md:flex-row justify-between items-center gap-4 bg-[#0c0c0e] p-2 rounded-2xl border border-white/5">
          <div className="flex bg-slate-900/60 p-1 rounded-xl border border-white/5">
              <button onClick={() => setTicker('TQQQ')} className={`px-6 py-2 rounded-lg text-xs font-black transition-all ${ticker === 'TQQQ' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-500 hover:text-white'}`}>TQQQ</button>
              <button onClick={() => setTicker('SOXL')} className={`px-6 py-2 rounded-lg text-xs font-black transition-all ${ticker === 'SOXL' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-500 hover:text-white'}`}>SOXL</button>
              <button onClick={() => setTicker('MIXED')} className={`px-6 py-2 rounded-lg text-xs font-black transition-all ${ticker === 'MIXED' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-500 hover:text-white'}`}>혼합(MIXED)</button>
          </div>
          <div className="flex items-center gap-2 px-4 py-2 bg-slate-900/40 rounded-xl">
             <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
             <p className="text-[10px] text-slate-400 font-bold uppercase tracking-tight">전 시뮬레이션은 <span className="text-white italic">2010.02.11 - 현재</span> 데이터를 참조합니다.</p>
          </div>
        </div>

        {/* Global Simulation Config (v29.7) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 bg-[#0c0c0e] p-6 rounded-[2.5rem] border border-white/5 shadow-2xl relative overflow-hidden">
           <div className="lg:col-span-8 flex flex-col md:flex-row items-stretch gap-4">
              <div className="flex-1 space-y-4">
                <div className="flex justify-between items-center mb-2">
                  <h2 className="text-xl font-black text-white flex items-center gap-2 italic uppercase tracking-tighter">
                    <Target className="w-5 h-5 text-blue-500" />
                    전술 제언 및 제어 센터
                  </h2>
                  <div className="flex bg-slate-900/50 p-1 rounded-xl border border-white/5">
                    <button onClick={() => setResolution('1D')} className={`px-4 py-1 rounded-lg text-[10px] font-black transition-all ${resolution === '1D' ? 'bg-blue-500 text-white' : 'text-slate-500 hover:text-white'}`}>1D (거시적)</button>
                    <button onClick={() => setResolution('1M')} className={`px-4 py-1 rounded-lg text-[10px] font-black transition-all ${resolution === '1M' ? 'bg-purple-500 text-white' : 'text-slate-500 hover:text-white'}`}>1M (정밀)</button>
                  </div>
                </div>
                <div className="flex gap-4 h-14">
                   <CompactInput label="초기 자산 (Seed)" value={seed} onChange={setSeed} />
                   <CompactInput label="분할 횟수 (Split)" value={split} onChange={setSplit} />
                   <CompactInput label="TARGET %" value={target} onChange={setTarget} />
                   {resolution === '1M' && (
                    <div className="flex-1 bg-purple-500/10 px-3 py-1.5 rounded-xl border border-purple-500/30 flex flex-col justify-center h-full group focus-within:border-purple-500/50 transition-all text-left">
                      <label className="text-[8px] font-black text-purple-400 uppercase mb-0.5 ml-1">SNIPER DROP %</label>
                      <input 
                        type="number" step="0.1" value={sniperDrop} onChange={e => setSniperDrop(Number(e.target.value))}
                        className="bg-transparent border-none w-full text-xs font-black focus:ring-0 text-white p-0 h-4"
                      />
                    </div>
                  )}
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2">
                   <ToggleSwitch active={useElastic} onChange={setUseElastic} label="변동성 보정" desc="자산 비중 보정" themeColor="bg-cyan-600" />
                   <ToggleSwitch active={useAtrShield} onChange={setUseAtrShield} label="충격 감쇄" desc="ATR-Shield" themeColor="bg-emerald-600" />
                   <ToggleSwitch active={useTurbo} onChange={setUseTurbo} label="터보 부스터" desc="다중 매수" themeColor="bg-orange-500" />
                   <ToggleSwitch active={useShadow} onChange={setUseShadow} label="새도우 스트라이크" desc="저점 추격" themeColor="bg-indigo-600" />
                   <ToggleSwitch active={useShield} onChange={setUseShield} label="쉴드 (MDD)" desc="자산 방어" themeColor="bg-blue-600" />
                   <ToggleSwitch active={useSniper} onChange={setUseSniper} label="정밀 익절" desc="Sniper 모드" themeColor="bg-amber-600" />
                   <ToggleSwitch active={useEmergency} onChange={setUseEmergency} label="급락 구출" desc="패닉 복구" themeColor="bg-rose-600" />
                   <ToggleSwitch active={useJupjup} onChange={setUseJupjup} label="줍줍 거미줄" desc="하락장 매집" themeColor="bg-teal-600" />
                </div>
              </div>
           </div>
           <div className="lg:col-span-4 flex flex-col justify-between gap-4">
              <div className="flex bg-slate-900/60 p-1 rounded-2xl border border-white/10 h-14">
                 {['V13', 'V14', 'V24'].map(v => (
                   <button key={v} onClick={() => setVersion(v)} className={`flex-1 rounded-xl text-[10px] font-black transition-all ${version === v ? 'bg-white text-black' : 'text-slate-500 hover:text-white'}`}>{v} 코어</button>
                 ))}
              </div>
              <button 
                onClick={runSimulation}
                disabled={loading}
                className="w-full h-24 rounded-[1.8rem] bg-gradient-to-br from-blue-600 to-indigo-700 text-white text-base font-black italic tracking-widest uppercase hover:scale-[1.02] active:scale-95 transition-all shadow-[0_15px_40px_rgba(37,99,235,0.25)] disabled:opacity-50 relative overflow-hidden group"
              >
                <div className="absolute inset-0 bg-white/10 translate-y-full group-hover:translate-y-0 transition-transform duration-500" />
                <span className="relative z-10 flex items-center justify-center gap-3">
                  {loading ? <RotateCcw className="w-6 h-6 animate-spin" /> : <Play className="w-6 h-6 fill-current" />}
                  전략 테스트 가동
                </span>
              </button>
            </div>
         </div>

        {result && (
          <section className="animate-in fade-in slide-in-from-bottom-10 space-y-8 mt-12 pt-8 border-t border-white/10">
             <div className="flex items-center gap-3 mb-6">
                <div className="p-2 bg-blue-500 rounded-xl shadow-[0_0_15px_rgba(59,130,246,0.2)]"><TrendingUp className="w-5 h-5 text-black" /></div>
                <h3 className="text-lg font-black italic tracking-tight text-white uppercase">시뮬레이션 분석 보고서 (Analysis Report)</h3>
             </div>
             
             <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div className="lg:col-span-4 space-y-4">
                   <div className="bg-slate-900/60 p-6 rounded-[2rem] border border-white/5 backdrop-blur-xl relative overflow-hidden group">
                      <div className="absolute top-0 right-0 p-4 opacity-[0.03] group-hover:opacity-10 transition-opacity"><AlertOctagon className="w-16 h-16" /></div>
                      <h4 className="text-[10px] font-black text-amber-500 italic mb-5 uppercase text-left">지표 개입 감사 (Metric Audit)</h4>
                      <div className="grid grid-cols-2 gap-3">
                         <DetailMetric label="쉴드 개입" value={intervention?.shield_hits || 0} unit="회" color="text-blue-400" />
                         <DetailMetric label="스나이퍼 익절" value={intervention?.sniper_hits || 0} unit="회" color="text-amber-400" />
                         <DetailMetric label="터보 가속" value={intervention?.turbo_hits || 0} unit="회" color="text-cyan-400" />
                         <DetailMetric label="급락 구출" value={intervention?.emergency_hits || 0} unit="회" color="text-rose-400" />
                      </div>
                   </div>

                   <StatBox label="최종 자산" value={`$${result.summary.final_total.toLocaleString()}`} unit="USD" />
                   <div className="grid grid-cols-2 gap-4">
                      <StatBox 
                        label="누적 수익률" 
                        value={`${result.summary.total_return >= 0 ? '+' : ''}${result.summary.total_return}`} 
                        unit="%" 
                        color={result.summary.total_return >= 0 ? "text-emerald-400" : "text-rose-500"} 
                        compact 
                      />
                      <StatBox label="샤프 지수" value={result.summary.sharpe} unit="e" color="text-blue-400" compact />
                      <StatBox label="최대 낙폭 (MDD)" value={`-${result.summary.mdd}`} unit="%" color="text-rose-500" compact />
                      <StatBox label="회복 기간" value={result.summary.recovery_days} unit="일" color="text-slate-300" compact />
                   </div>
                </div>
                
                <div className="lg:col-span-8 bg-slate-950/80 p-6 rounded-[2.5rem] border border-blue-500/10 min-h-[500px] w-full shadow-2xl relative text-left">
                   <div className="flex justify-between items-center mb-6">
                      <div className="text-[9px] font-black text-slate-500 uppercase tracking-[0.3em]">자산 성장 추이 분석 (Performance Analysis)</div>
                   </div>
                   <div className="h-[400px] w-full">
                     <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={result.equity_curve}>
                           <defs>
                              <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                                 <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4}/>
                                 <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                              </linearGradient>
                           </defs>
                           <CartesianGrid strokeDasharray="3 3" stroke="#ffffff05" vertical={false} />
                           <XAxis dataKey="date" hide />
                           <YAxis domain={['auto', 'auto']} stroke="#475569" fontSize={9} />
                           <Tooltip contentStyle={{backgroundColor: '#070709', borderRadius: '16px', border: '1px solid #27272a', fontWeight: 'bold', fontSize: '10px', color: '#fff'}} />
                           <Area type="monotone" dataKey="total" stroke="#3b82f6" strokeWidth={3} fillOpacity={1} fill="url(#colorTotal)" />
                        </AreaChart>
                     </ResponsiveContainer>
                   </div>
                </div>
             </div>
          </section>
        )}

        {/* 🚀 지능형 전술 최적화 섹션 (한글 명칭 동기화) */}
        <section className={`bg-gradient-to-br from-[#121214] to-black p-6 rounded-[2rem] border border-white/5 relative overflow-hidden shadow-2xl ${result ? 'mt-12' : ''}`}>
           <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center text-left">
              <div className="lg:col-span-7">
                 <div className="flex items-center gap-3 mb-3">
                    <div className="p-2 bg-amber-500 rounded-xl shadow-[0_0_15px_rgba(245,158,11,0.2)]"><Cpu className="w-5 h-5 text-black" /></div>
                    <h3 className="text-lg font-black italic tracking-tight text-white uppercase">지능형 전술 최적화 (Targeted Optimizer)</h3>
                 </div>
                 <p className="text-[11px] text-slate-400 font-medium leading-relaxed max-w-2xl text-left">
                    <span className="text-white font-bold">{ticker}</span> 환경에서 가장 완벽한 성과를 내는 전술 조합을 인공지능이 탐색합니다.
                    <span className="text-amber-500 ml-1">64종 조합 고속 인공지능 탐색 (High-Speed Sweep)</span>
                 </p>
              </div>
              <div className="lg:col-span-5 space-y-4">
                <div className="flex gap-2">
                  <button onClick={() => setUseElastic(!useElastic)}
                      className={`flex-1 py-3 px-4 rounded-xl text-[9px] font-black tracking-widest transition-all border ${useElastic ? 'bg-emerald-600/20 text-emerald-400 border-emerald-500/50' : 'bg-slate-950/40 text-slate-700 border-white/5'}`}>
                      ELASTIC {useElastic ? 'ON' : 'OFF'}
                  </button>
                  <button onClick={() => setUseAtrShield(!useAtrShield)}
                      className={`flex-1 py-3 px-4 rounded-xl text-[9px] font-black tracking-widest transition-all border ${useAtrShield ? 'bg-emerald-600/20 text-emerald-400 border-emerald-500/50' : 'bg-slate-950/40 text-slate-700 border-white/5'}`}>
                      ATR-SHIELD {useAtrShield ? 'ON' : 'OFF'}
                  </button>
                  <button 
                      onClick={runExhaustive}
                      disabled={exhaustiveLoading}
                      className="flex-[1.5] py-3 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 text-black text-[10px] font-black tracking-widest uppercase italic shadow-2xl hover:scale-105 active:scale-95 transition-all disabled:opacity-50"
                  >
                      {exhaustiveLoading ? "연산 중..." : "최적 전술 탐색 시작"}
                  </button>
                </div>
              </div>
           </div>
        </section>

        {exhaustiveResult && exhaustiveResult.best_path && (
          <section className="space-y-12 animate-in slide-in-from-bottom-10">
              {/* 🛡️ [V29.6] 최적 전략 추천 & 게이지 바 */}
              <div className="bg-gradient-to-br from-slate-900 to-black rounded-3xl border border-white/10 p-10 backdrop-blur-2xl relative overflow-hidden group shadow-2xl">
                 <div className="absolute inset-0 bg-gradient-to-br from-amber-500/[0.03] to-indigo-500/[0.03] pointer-events-none" />
                 
                 <div className="flex flex-col lg:flex-row justify-between items-start gap-12 relative z-10 text-left">
                    <div className="flex-1 space-y-6">
                       <div className="flex items-center gap-3">
                          <span className="p-2.5 bg-amber-500/10 border border-amber-500/20 rounded-2xl">
                             <Zap className="w-6 h-6 text-amber-500" />
                          </span>
                          <div>
                             <h3 className="text-xl font-black text-white italic tracking-tight uppercase">전문가 선정 최적 전술 <span className="text-amber-500 ml-2">랭킹 #1</span></h3>
                             <p className="text-slate-500 font-bold text-xs uppercase tracking-widest mt-1">{ticker} 전용 추천 전략</p>
                          </div>
                       </div>
                       
                       <div className="bg-white/5 rounded-2xl p-6 border border-white/5 shadow-inner">
                          <div className="flex items-start gap-4">
                             <div className="p-2 bg-amber-500/20 rounded-lg mt-1"><Compass className="w-4 h-4 text-amber-500" /></div>
                             <div>
                                <div className="text-[10px] font-black text-amber-500 uppercase tracking-widest mb-1 italic">컨설턴트 조언</div>
                                <div className="text-sm text-slate-100 font-black leading-relaxed italic">"{exhaustiveResult.best_path.expert?.commentary || '분석된 최상의 조합입니다.'}"</div>
                             </div>
                          </div>
                       </div>

                       <div className="flex flex-wrap gap-2 justify-start">
                         <div className="px-4 py-2 bg-amber-500/10 border border-amber-500/30 rounded-xl flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
                            <span className="text-xs font-black text-amber-400 uppercase italic">{exhaustiveResult.best_path.version || 'V14'}</span>
                         </div>
                         {Object.entries(exhaustiveResult.best_path.combo).map(([key, val]) => (
                            val === true && (
                              <div key={key} className="px-4 py-2 bg-white/5 border border-white/10 rounded-xl flex items-center gap-2">
                                 <span className="text-xs font-black text-slate-400 uppercase">{key}</span>
                              </div>
                            )
                         ))}
                       </div>
                    </div>
                    <div className="w-full lg:w-auto flex flex-col items-center gap-5">
                        <ExpertGauge value={exhaustiveResult.best_path.expert?.rating || 0} max={5.0} label="/ 5.0" />
                        <div className="grid grid-cols-2 gap-x-8 gap-y-4 text-left w-full lg:w-48">
                            <ExpertMetric label="복합 점수" value={exhaustiveResult.best_path.score.toFixed(2)} color="text-white" />
                            <ExpertMetric label="기대 ROI" value={`+${exhaustiveResult.best_path.res?.total_return.toFixed(1) || 0}%`} color="text-emerald-400" />
                        </div>
                    </div>
                 </div>
              </div>

              {/* 🛡️ [V29.6] Tactical Leaderboard */}
               <div className="mt-12 pt-8 border-t border-white/10">
                <div className="flex flex-col md:flex-row justify-between items-end gap-4 mb-6 text-left">
                  <div className="text-left">
                    <h3 className="text-lg font-black text-white flex items-center gap-2 mb-1 uppercase italic tracking-tighter">
                      <Target className="w-4 h-4 text-amber-400" />
                      전술 통합 리더보드
                    </h3>
                    <p className="text-[10px] text-slate-500 font-medium">64개 전술 시나리오별 시뮬레이션 랭킹</p>
                  </div>

                  <div className="flex flex-wrap gap-1.5 p-1 bg-white/5 backdrop-blur-md rounded-xl border border-white/10 shrink-0">
                    {[
                      { id: 'ALL', label: 'ALL', icon: <TrendingUp className="w-3 h-3" /> },
                      { id: 'SIDEWAYS', label: 'SIDEWAYS', icon: <ArrowRightLeft className="w-3 h-3" /> },
                      { id: 'BEAR', label: 'BEAR', icon: <ShieldAlert className="w-3 h-3" /> },
                      { id: 'STRONG_BULL', label: 'BULL', icon: <Zap className="w-3 h-3" /> },
                      { id: 'SHOCK', label: 'SHOCK', icon: <AlertTriangle className="w-3 h-3" /> },
                    ].map((btn) => (
                      <button
                        key={btn.id}
                        onClick={() => setActiveRegimeFilter(btn.id as any)}
                        className={`flex items-center gap-2 px-3 py-1 rounded-lg text-[9px] font-black transition-all ${
                          activeRegimeFilter === btn.id 
                          ? 'bg-amber-500 text-black' 
                          : 'text-slate-400 hover:text-white hover:bg-white/5'
                        }`}
                      >
                        {btn.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="bg-black/40 rounded-2xl border border-white/5 overflow-hidden backdrop-blur-xl shadow-2xl">
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-white/10 bg-white/5">
                          <th className="px-6 py-3 text-[9px] uppercase tracking-widest font-black text-slate-500">순위</th>
                          <th className="px-6 py-3 text-[9px] uppercase tracking-widest font-black text-slate-500">전술 조합</th>
                          <th className="px-6 py-3 text-[9px] uppercase tracking-widest font-black text-slate-500">성과 분석</th>
                          <th className="px-6 py-3 text-[9px] uppercase tracking-widest font-black text-slate-500">통합 점수</th>
                          <th className="px-6 py-3 text-right text-[9px] uppercase tracking-widest font-black text-slate-500">실행</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {filteredCandidates.map((cand, idx) => (
                          <tr key={cand.idx} className={`group hover:bg-white/[0.03] transition-colors ${idx === 0 && activeRegimeFilter === 'ALL' ? 'bg-amber-500/5' : ''}`}>
                            <td className="px-6 py-4">
                              <span className={`text-base font-black italic ${idx < 3 ? 'text-amber-500' : 'text-slate-600'}`}>#{idx + 1}</span>
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex flex-wrap gap-1 max-w-xs">
                                <span className="px-1.5 py-0.5 bg-indigo-500/20 text-indigo-400 rounded text-[8px] font-black">{cand.version}</span>
                                {Object.entries(cand.combo).map(([key, val]) => (
                                  val === true && (
                                    <span key={key} className="px-1.5 py-0.5 bg-slate-800 text-slate-400 rounded text-[8px] font-black uppercase">{key}</span>
                                  )
                                ))}
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-4">
                                 <div className="flex flex-col">
                                   <span className="text-[7px] text-slate-500 font-black uppercase">ROI</span>
                                   <span className="text-[11px] font-black text-emerald-400">+{cand.res?.total_return.toFixed(1)}%</span>
                                 </div>
                                 <div className="flex flex-col border-l border-white/10 pl-3">
                                   <span className="text-[7px] text-slate-500 font-black uppercase">Max DD</span>
                                   <span className="text-[11px] font-black text-rose-400">-{cand.res?.mdd.toFixed(1)}%</span>
                                 </div>
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <span className="text-xs font-black text-white">{cand.score.toFixed(2)}</span>
                            </td>
                            <td className="px-6 py-4 text-right">
                              <div className="flex items-center justify-end gap-2">
                                <button onClick={() => applyStrategy(cand)} className="px-3 py-1.5 bg-white/5 hover:bg-amber-500/20 border border-white/10 hover:border-amber-500/50 rounded-lg text-[9px] font-black transition-all">LAB APPLY</button>
                                <button onClick={() => deployToBot(cand, true)} disabled={deployLoading} className="px-3 py-1.5 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/20 rounded-lg text-[9px] font-black text-emerald-400 disabled:opacity-50">DEPLOY REAL</button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
          </section>
        )}
      </div>
  )
}

function CompactInput({ label, value, onChange }: any) {
  return (
    <div className="flex-1 bg-slate-800/80 px-3 py-1.5 rounded-xl border border-white/10 flex flex-col justify-center h-full group focus-within:border-blue-500/50 transition-all text-left">
      <label className="text-[8px] font-black text-slate-500 uppercase mb-0.5 ml-1">{label}</label>
      <input 
        type="number" value={value} onChange={e => onChange(Number(e.target.value))}
        className="bg-transparent border-none w-full text-xs font-black focus:ring-0 text-white p-0 h-4"
      />
    </div>
  )
}

function StatBox({ label, value, unit, color = "text-white", compact = false }: any) {
  return (
    <div className={`bg-slate-900/60 border border-white/5 rounded-[1.8rem] shadow-inner relative overflow-hidden text-left ${compact ? 'p-3' : 'p-5'}`}>
      <p className="text-[8px] font-black text-slate-500 uppercase tracking-widest mb-1 ml-1">{label}</p>
      <div className="flex items-baseline gap-1">
        <span className={`${compact ? 'text-base' : 'text-xl'} font-black italic tracking-tighter ${color}`}>{value}</span>
        <span className="text-[7px] font-black text-slate-700 uppercase italic leading-none">{unit}</span>
      </div>
    </div>
  )
}

function DetailMetric({ label, value, unit, color }: any) {
    return (
        <div className="p-2 bg-slate-950/50 rounded-xl border border-white/5 text-left">
            <span className="text-[8px] text-slate-500 font-bold block uppercase mb-0.5">{label}</span>
            <span className={`text-lg font-black ${color}`}>{value}<span className="text-[8px] ml-0.5">{unit}</span></span>
        </div>
    )
}

function ExpertMetric({ label, value, color }: any) {
   return (
      <div className="flex flex-col text-left">
         <span className="text-[7px] font-black text-slate-500 uppercase mb-0.5 tracking-widest leading-none">{label}</span>
         <span className={`text-lg font-black italic tracking-tighter ${color}`}>{value}</span>
      </div>
   )
}

export default SimulationTestbed
