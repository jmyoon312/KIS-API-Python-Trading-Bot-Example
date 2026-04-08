import { useState } from 'react'
import axios from 'axios'
import { 
  Zap, BarChart3, Settings2, Play, Activity, Sliders, ShieldCheck, Database, Sparkles, X, BookOpen, Target, TrendingUp, AlertTriangle
} from 'lucide-react'
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer 
} from 'recharts'
import toast from 'react-hot-toast'

const VRevAdvancedResearch = () => {
  const [loading, setLoading] = useState(false)
  const [year, setYear] = useState('2022')
  const [seed, setSeed] = useState(10000)
  const [showManual, setShowManual] = useState(false)
  
  const [config, setConfig] = useState<any>({
    buy1_drop: 0.995,
    buy2_drop: 0.975,
    s1_target: 1.006,
    s2_target: 1.005,
    sweep_target: 1.011,
    vwap_threshold: 0.60,
    portion_ratio: 0.15,
    anchor_mode: 'REPORT', 
    use_compounding: true
  })

  const [result, setResult] = useState<any>(null)

  const runVrevSim = async () => {
    setLoading(true)
    const t = toast.loading(`${year}년 데이터 분석 가동...`)
    try {
      const res = await axios.post('/api/simulation/vrev-advanced', {
        ticker: 'SOXL',
        year,
        seed,
        config
      })
      if (res.data.status === 'success') {
        setResult(res.data)
        toast.success(`${year}년 분석 완료!`, { id: t })
      } else {
        toast.error(res.data.message, { id: t })
      }
    } catch (_) {
      toast.error('통신 오류', { id: t })
    } finally {
      setLoading(false)
    }
  }

  const updateConfig = (key: string, val: any) => {
    setConfig((prev: any) => ({ ...prev, [key]: val }))
  }

  const applyGoldenPreset = () => {
    setConfig((prev: any) => ({
      ...prev,
      buy1_drop: 0.980,   // -2.0%
      buy2_drop: 0.940,   // -6.0%
      vwap_threshold: 0.70, // 70% Filter
      anchor_mode: 'REAL'
    }))
    toast.success('현실 모드 생존용 골든 넘버가 적용되었습니다!')
  }

  const applyReportPreset = () => {
    setConfig((prev: any) => ({
      ...prev,
      buy1_drop: 0.995,   // -0.5%
      buy2_drop: 0.975,   // -2.5%
      vwap_threshold: 0.60, 
      anchor_mode: 'REPORT'
    }))
    toast.success('원본 리포트(+) 동기화 모드로 설정되었습니다.')
  }

  return (
    <div className="space-y-6 pb-12 animate-in fade-in relative">
      {/* 📘 Strategy Manual Modal */}
      {showManual && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
          <div className="bg-slate-900 border border-white/10 w-full max-w-4xl max-h-[85vh] overflow-y-auto rounded-[2.5rem] shadow-2xl relative">
            <button 
              onClick={() => setShowManual(false)}
              className="absolute top-6 right-6 p-2 bg-slate-800 hover:bg-slate-700 rounded-full transition-all"
            >
              <X className="w-5 h-5 text-white" />
            </button>
            
            <div className="p-8 md:p-12 space-y-12">
              <header className="space-y-4 border-b border-white/5 pb-8">
                <div className="flex items-center gap-3">
                  <BookOpen className="w-8 h-8 text-indigo-400" />
                  <h1 className="text-3xl font-black italic tracking-tighter uppercase text-white">V-REV Strategy Master Manual</h1>
                </div>
                <p className="text-slate-400 font-bold leading-relaxed max-w-2xl">
                  본 매뉴얼은 V-REV 전술 연구 데이터를 기반으로 작성되었으며, 초보자부터 전문가까지 이 전략의 수학적 원리와 실전 조작법을 완벽히 이해하도록 돕습니다.
                </p>
              </header>

              <section className="space-y-6">
                <h2 className="text-xl font-black uppercase tracking-widest text-indigo-400 flex items-center gap-2">
                  <Target className="w-5 h-5" /> PART 1. 전략의 핵심 원리
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-slate-950/50 p-6 rounded-3xl border border-white/5 space-y-3">
                    <h3 className="text-sm font-black text-white uppercase italic">1. VWAP 3중 필터링</h3>
                    <p className="text-[11px] text-slate-400 leading-relaxed font-medium">
                      단순히 가격이 떨어진다고 매수하지 않습니다. **거래량 가중 평균 가격(VWAP)** 대비 하부 영역에 있으면서, 기울기가 마이너스이며, 거래량 밀집도가 정해진 임계값(Threshold)을 넘는 '상승 전환 직전의 응축' 상태만 포착합니다.
                    </p>
                  </div>
                  <div className="bg-slate-950/50 p-6 rounded-3xl border border-white/5 space-y-3">
                    <h3 className="text-sm font-black text-white uppercase italic">2. LIFO 지층 구조 (Layering)</h3>
                    <p className="text-[11px] text-slate-400 leading-relaxed font-medium">
                      **후입선출(Last-In First-Out)** 구조를 통해 가장 최근에 매수한 지층(Layer)을 짧은 반등(0.6% 등)에 즉시 익절하여 회전율을 높이고, 전체 자본의 평단가를 낮추는 '스캘핑형 물타기'를 수행합니다.
                    </p>
                  </div>
                </div>
              </section>

              <section className="space-y-6">
                <h2 className="text-xl font-black uppercase tracking-widest text-emerald-400 flex items-center gap-2">
                  <Settings2 className="w-5 h-5" /> PART 2. 파라미터 상세 가이드
                </h2>
                <div className="space-y-3">
                  <ParameterRow label="BUY 1/2 DROP" desc="기준가 대비 매수 진입점. -0.5%/-2.5%가 표준이며, 변동성이 큰 날에는 더 깊게 설정하는 것이 생존의 핵심입니다." />
                  <ParameterRow label="VWAP THRESHOLD" desc="전체 거래량 중 VWAP 아래에서 발생한 거래의 비율. 60% 이상일 때 '과매도'로 판단하며, 70%로 높일수록 더 확실한 기회만 잡습니다." />
                  <ParameterRow label="S1 TARGET / JACKPOT" desc="S1은 상단 지층의 단기 탈출 목표, JACKPOT은 전체 지층을 일시에 정리하여 수익을 극대화하는 임계점입니다." />
                  <ParameterRow label="PORTION RATIO" desc="1회 매수 시 투입할 자본의 비율. 15%가 표준이며, 자본 규모가 클수록 10% 내외의 보수적 운영을 추천합니다." />
                </div>
              </section>

              <section className="space-y-6">
                <h2 className="text-xl font-black uppercase tracking-widest text-amber-400 flex items-center gap-2">
                  <TrendingUp className="w-5 h-5" /> PART 3. 이상(Report) vs 현실(Realistic)
                </h2>
                <div className="bg-amber-500/5 p-8 rounded-[2.5rem] border border-amber-500/10 space-y-6">
                  <div className="flex items-start gap-4">
                    <div className="p-3 bg-amber-500/20 rounded-2xl">
                      <AlertTriangle className="w-6 h-6 text-amber-500" />
                    </div>
                    <div>
                      <h3 className="text-lg font-black text-amber-500 uppercase italic mb-2">리포트 수익률(+422.94%)의 진실</h3>
                      <p className="text-xs text-slate-300 leading-relaxed font-bold">
                        원본 데이터 리포트의 경이로운 수익률은 '당일 종가'를 매수 시점에 미리 참조하는 **Report Anchor** 방식을 사용합니다. 이는 이론적 잠재력을 보여주지만, 실전에서는 불가능합니다.
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start gap-4">
                    <div className="p-3 bg-cyan-500/20 rounded-2xl">
                      <ShieldCheck className="w-6 h-6 text-cyan-500" />
                    </div>
                    <div>
                      <h3 className="text-lg font-black text-cyan-500 uppercase italic mb-2">실전 생존 전략 (Golden Survival)</h3>
                      <p className="text-xs text-slate-300 leading-relaxed font-bold">
                        현실에서는 '전일 종가'를 기준으로 싸워야 합니다. 이때는 타점을 **-2.0%/-6.0%**까지 훨씬 깊게 파야 2022년과 같은 폭락장에서 살아남고, 반등 시에 더 큰 수익을 낼 수 있습니다.
                      </p>
                    </div>
                  </div>
                </div>
              </section>

              <footer className="pt-8 border-t border-white/5 text-center">
                <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">
                  V-REV Advanced Quant Engine V56.0 • Prepared for Commander JMY
                </p>
              </footer>
            </div>
          </div>
        </div>
      )}

      {/* 🚀 Header */}
      <section className="bg-gradient-to-br from-indigo-900/40 to-slate-900/40 p-6 rounded-[2rem] border border-indigo-500/20 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-500 rounded-xl shadow-[0_0_15px_rgba(99,102,241,0.4)]">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <h2 className="text-xl font-black italic tracking-tighter uppercase flex items-center gap-2 text-white">
              V-REV Research Center
              <span className="text-[9px] not-italic bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded-full border border-emerald-500/30 font-bold">V56.5 STABLE</span>
            </h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button 
              onClick={() => setShowManual(true)}
              className="px-4 py-2 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/40 border border-indigo-500/30 text-[10px] font-black text-indigo-300 uppercase flex items-center gap-2 transition-all group whitespace-nowrap active:scale-95"
            >
              <BookOpen className="w-3.5 h-3.5 group-hover:scale-110 transition-all" />
              전략 매뉴얼
            </button>
            <button 
              onClick={applyReportPreset}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[10px] font-black text-slate-300 uppercase transition-all whitespace-nowrap active:scale-95"
            >
              Report Mode
            </button>
            <button 
              onClick={applyGoldenPreset}
              className="px-4 py-2 rounded-xl bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-400 hover:to-orange-500 text-[10px] font-black text-white uppercase flex items-center gap-2 shadow-lg shadow-amber-500/20 transition-all whitespace-nowrap active:scale-95"
            >
              <Sparkles className="w-3.5 h-3.5" />
              Golden
            </button>
          </div>
        </div>
        <p className="text-xs text-slate-400 font-bold leading-relaxed border-t border-white/5 pt-4">
          통합 매뉴얼과 실전 골든 넘버가 탑재된 V-REV 리서치 시스템입니다. <br/>
          하락장에서도 버틸 수 있는 전략적 파라미터를 가이드를 통해 습득하고 직접 튜닝하십시오.
        </p>
      </section>

      {/* 🧪 Tuning Lab */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Panel 1 */}
        <div className="bg-slate-900/60 p-5 rounded-3xl border border-white/5 space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <Sliders className="w-4 h-4 text-emerald-400" />
            <span className="text-[10px] font-black uppercase text-emerald-400 tracking-widest text-white">운영 자본 & 복리</span>
          </div>
          <div className="space-y-4">
            <div className="space-y-1">
              <div className="flex justify-between items-center text-[10px] font-bold text-slate-400 uppercase">
                <span>Portion Ratio</span>
                <span className="text-emerald-400">{Math.round(config.portion_ratio * 100)}%</span>
              </div>
              <input type="range" min="0.05" max="0.4" step="0.01" value={config.portion_ratio} onChange={e => updateConfig('portion_ratio', parseFloat(e.target.value))} className="w-full h-1 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500" />
            </div>
            <div className="flex items-center justify-between p-3 bg-slate-950/50 rounded-xl border border-white/5">
              <span className="text-[10px] font-bold text-white uppercase">연속 복리 가동</span>
              <input type="checkbox" checked={config.use_compounding} onChange={e => updateConfig('use_compounding', e.target.checked)} className="w-4 h-4 accent-indigo-500 cursor-pointer" />
            </div>
          </div>
        </div>

        {/* Panel 2 */}
        <div className="bg-slate-900/60 p-5 rounded-3xl border border-white/5 space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <Database className="w-4 h-4 text-cyan-400" />
            <span className="text-[10px] font-black uppercase text-cyan-400 tracking-widest text-white">데이터 앵커 & 필터</span>
          </div>
          <div className="space-y-4">
            <div className="flex flex-col gap-2">
              <span className="text-[10px] font-black text-slate-400 uppercase">Anchor Mode</span>
              <div className="grid grid-cols-2 gap-2">
                <button 
                  onClick={() => updateConfig('anchor_mode', 'REPORT')}
                  className={`py-2 px-3 rounded-xl text-[10px] font-black transition-all ${config.anchor_mode === 'REPORT' ? 'bg-indigo-600 text-white shadow-lg' : 'bg-slate-950 text-slate-500 border border-white/5 hover:bg-slate-800'}`}
                >
                  리포트 (이론)
                </button>
                <button 
                  onClick={() => updateConfig('anchor_mode', 'REAL')}
                  className={`py-2 px-3 rounded-xl text-[10px] font-black transition-all ${config.anchor_mode === 'REAL' ? 'bg-cyan-600 text-white shadow-lg' : 'bg-slate-950 text-slate-500 border border-white/5 hover:bg-slate-800'}`}
                >
                  현실적 (실전)
                </button>
              </div>
            </div>
            <div className="space-y-1">
              <div className="flex justify-between items-center text-[10px] font-bold text-slate-400 uppercase">
                <span>VWAP Threshold</span>
                <span className="text-cyan-400">{Math.round(config.vwap_threshold * 100)}%</span>
              </div>
              <input type="range" min="0.4" max="0.8" step="0.05" value={config.vwap_threshold} onChange={e => updateConfig('vwap_threshold', parseFloat(e.target.value))} className="w-full h-1 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-500" />
            </div>
          </div>
        </div>

        {/* Panel 3 */}
        <div className="bg-slate-900/60 p-5 rounded-3xl border border-white/5 space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <Settings2 className="w-4 h-4 text-rose-400" />
            <span className="text-[10px] font-black uppercase text-rose-400 tracking-widest text-white">정밀 타점 설정</span>
          </div>
          <div className="grid grid-cols-2 gap-3">
             {[
               { id: 'buy1_drop', label: 'BUY 1', step: 0.001 },
               { id: 'buy2_drop', label: 'BUY 2', step: 0.001 },
               { id: 's1_target', label: 'EXIT 1', step: 0.001 },
               { id: 'sweep_target', label: 'JACKPOT', step: 0.001 },
             ].map(item => (
               <div key={item.id} className="flex flex-col gap-1">
                 <label className="text-[8px] font-black text-slate-500 uppercase">{item.label}</label>
                 <input 
                   type="number" step={item.step} 
                   value={config[item.id]} 
                   onChange={e => updateConfig(item.id, Number(e.target.value))} 
                   className="bg-slate-950 border border-white/5 rounded-lg px-2 py-1.5 text-[10px] font-black text-white focus:outline-none focus:border-rose-500/50" 
                 />
               </div>
             ))}
          </div>
        </div>
      </section>

      {/* Period & Execution */}
      <section className="bg-slate-950 p-4 rounded-3xl border border-white/10 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
           <select 
             value={year} onChange={e => setYear(e.target.value)}
             className="bg-slate-900 border-none rounded-xl text-xs font-black px-5 py-3 text-white focus:ring-1 focus:ring-emerald-500 w-44"
           >
             {['2022', '2023', '2024', '2025', '2026', '5y'].map(y => (
               <option key={y} value={y}>{y === '5y' ? '5개년 전체 (22-26)' : `${y}년 (1M Tick)`}</option>
             ))}
           </select>
           <div className="h-10 w-px bg-white/5" />
           <input 
             type="number" value={seed} onChange={e => setSeed(Number(e.target.value))}
             className="bg-slate-900 border-none rounded-xl text-xs font-black px-5 py-3 text-white w-32 focus:ring-1 focus:ring-emerald-500"
           />
        </div>
        <button 
          onClick={runVrevSim} disabled={loading}
          className="flex-1 md:flex-none flex items-center justify-center gap-3 bg-gradient-to-r from-emerald-600 to-teal-700 px-12 py-3.5 rounded-2xl text-sm font-black italic tracking-widest uppercase shadow-lg shadow-emerald-500/20 active:scale-95 transition-all disabled:opacity-50 text-white"
        >
          {loading ? <Activity className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5 fill-current" />}
          V-REV 연구용 분석 가동
        </button>
      </section>

      {/* Results */}
      {result && (
        <div className="space-y-6 animate-in slide-in-from-bottom-5">
           {result.summary.yearly && (
             <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
               {Object.entries(result.summary.yearly).sort().map(([y, stats]: [string, any]) => (
                 <div key={y} className="bg-slate-900/80 p-4 rounded-2xl border border-white/5 text-center relative overflow-hidden group">
                    <div className={`absolute top-0 left-0 w-full h-1 ${stats.return >= 0 ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                    <span className="text-[9px] font-black text-slate-400 block mb-1">{y}년 실적</span>
                    <div className={`text-base font-black italic ${stats.return >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {stats.return >= 0 ? '+' : ''}{stats.return}%
                    </div>
                    <div className="text-[9px] font-bold text-slate-500 mt-1 uppercase">MDD {stats.mdd_pct}%</div>
                 </div>
               ))}
             </div>
           )}

           <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <StatCard label="누적 수익률" value={`${result.summary.total_return}%`} color="text-emerald-400" />
              <StatCard label="최대 낙폭 (MDD)" value={`${result.summary.mdd_pct}%`} color="text-rose-400" />
              <StatCard label="최종 평가금" value={`$${result.summary.final_total.toLocaleString()}`} color="text-white" />
              <StatCard label="데이터 분석일" value={`${result.summary.total_days}일`} color="text-slate-400" />
           </div>

           <div className="bg-slate-900/40 p-8 rounded-[3.5rem] border border-white/5 h-[480px]">
              <div className="flex items-center gap-2 mb-8">
                 <BarChart3 className="w-5 h-5 text-indigo-500" />
                 <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 italic">Analytical Growth Curve</span>
              </div>
              <ResponsiveContainer width="100%" height="85%">
                <AreaChart data={result.history}>
                  <defs>
                    <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                  <XAxis dataKey="date" hide />
                  <YAxis domain={['auto', 'auto']} hide />
                  <Tooltip 
                    contentStyle={{ background: '#09090b', border: '1px solid #27272a', borderRadius: '16px', color: 'white' }}
                    itemStyle={{ fontWeight: 'bold' }}
                    labelStyle={{ display: 'none' }}
                  />
                  <Area type="monotone" dataKey="total" stroke="#6366f1" fillOpacity={1} fill="url(#colorTotal)" strokeWidth={4} />
                </AreaChart>
              </ResponsiveContainer>
           </div>
        </div>
      )}
    </div>
  )
}

const ParameterRow = ({ label, desc }: { label: string, desc: string }) => (
  <div className="p-4 bg-slate-950/40 rounded-2xl border border-white/5 hover:border-indigo-500/20 transition-all">
    <h4 className="text-[10px] font-black text-indigo-300 uppercase mb-1">{label}</h4>
    <p className="text-[11px] text-slate-400 leading-relaxed font-medium">{desc}</p>
  </div>
)

const StatCard = ({ label, value, color }: any) => (
  <div className="bg-slate-900/80 p-6 rounded-[2rem] border border-white/5 shadow-2xl relative overflow-hidden group">
    <div className="absolute -right-4 -bottom-4 opacity-5 group-hover:scale-110 transition-all">
       <TrendingUp className="w-24 h-24" />
    </div>
    <span className="text-[9px] font-black text-slate-500 uppercase tracking-widest mb-1 block leading-none">{label}</span>
    <span className={`text-2xl font-black italic tracking-tighter ${color} tabular-nums leading-none`}>{value}</span>
  </div>
)

export default VRevAdvancedResearch
