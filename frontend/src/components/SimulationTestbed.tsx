import { useState } from 'react'
import axios from 'axios'
import { 
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line
} from 'recharts'
import { 
  FlaskConical, Play, TrendingUp, AlertCircle, 
  Settings2, Activity, Diff
} from 'lucide-react'

export default function SimulationTestbed() {
  const sixteenYearsAgo = new Date()
  sixteenYearsAgo.setFullYear(sixteenYearsAgo.getFullYear() - 16)
  
  const [ticker, setTicker] = useState('TQQQ')
  const [startDate, setStartDate] = useState(sixteenYearsAgo.toISOString().split('T')[0])
  const [endDate] = useState(new Date().toISOString().split('T')[0])
  const [seed, setSeed] = useState(10000)
  const [split, setSplit] = useState(40)
  const [target, setTarget] = useState(10.0)
  const [version, setVersion] = useState('V24')
  
  const [compareMode, setCompareMode] = useState(false)
  const [versionB, setVersionB] = useState('V14')

  const [loading, setLoading] = useState(false)
  const [resultA, setResultA] = useState<any>(null)
  const [resultB, setResultB] = useState<any>(null)
  const [error, setError] = useState('')

  const runSimulation = async () => {
    setLoading(true)
    setError('')
    try {
      const resA = await axios.post('/api/simulation/run', {
        ticker, start_date: startDate, end_date: endDate,
        seed, split, target, version
      })
      
      let resB = null
      if (compareMode) {
        resB = await axios.post('/api/simulation/run', {
          ticker, start_date: startDate, end_date: endDate,
          seed, split, target, version: versionB
        })
      }

      if (resA.data.status === 'ok') {
        setResultA(resA.data.result)
        if (resB && resB.data.status === 'ok') {
            setResultB(resB.data.result)
        } else {
            setResultB(null)
        }
      } else {
        setError(resA.data.message)
      }
    } catch (e) {
      setError('시뮬레이션 서버 통신 오류')
    }
    setLoading(false)
  }

  const combinedData = resultA?.equity_curve.map((item: any, idx: number) => ({
    date: item.date,
    ScenarioA: item.total,
    ScenarioB: resultB?.equity_curve[idx]?.total || null,
    Benchmark: item.benchmark
  }))

  return (
    <div className="space-y-6 pb-20 animate-fade-in">
      <div className="bg-gradient-to-br from-[#1a1a1e] to-[#09090b] p-8 rounded-3xl border border-[#27272a] shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 right-0 w-64 h-64 bg-purple-500/5 blur-[100px] rounded-full -mr-32 -mt-32"></div>
        <div className="relative z-10">
          <h2 className="text-2xl font-black text-white mb-2 flex items-center gap-3">
            <FlaskConical className="text-purple-400 w-6 h-6" />
            무한 시뮬레이터 Lab <span className="text-[10px] bg-purple-500/20 text-purple-400 px-2 py-0.5 rounded-full uppercase">High Fidelity</span>
          </h2>
          <p className="text-gray-400 text-xs leading-relaxed max-w-xl">
             V17 Sniper(1/4 익절) 및 V24 Turbo 로직이 통합된 고정밀 시뮬레이터입니다.<br/>
             두 개의 전략을 동시에 비교하여 최적의 수익 곡선을 찾아내세요.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-[#121214] p-6 rounded-2xl border border-[#27272a] space-y-5">
           <div className="flex justify-between items-center mb-2">
            <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest flex items-center gap-2">
              <Settings2 className="w-3.5 h-3.5" />
              공통 설정 (Base)
            </h3>
            <button 
              onClick={() => setCompareMode(!compareMode)}
              className={`text-[9px] font-black px-2 py-1 rounded-md transition-all flex items-center gap-1 ${
                compareMode ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30' : 'bg-[#18181b] text-gray-500 border border-[#27272a]'
              }`}
            >
              <Diff className="w-3 h-3" />
              {compareMode ? '비교 모드 ON' : '비교 모드 OFF'}
            </button>
          </div>
          
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-[10px] font-black text-gray-400 uppercase">Ticker</label>
              <select value={ticker} onChange={(e) => setTicker(e.target.value)} className="w-full bg-[#18181b] border border-[#27272a] rounded-xl px-3 py-2 text-sm text-white font-bold outline-none focus:border-purple-500 transition-all">
                <option value="TQQQ">TQQQ</option>
                <option value="SOXL">SOXL</option>
                <option value="UPRO">UPRO</option>
                <option value="NVDA">NVDA</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-[10px] font-black text-gray-400 uppercase">Start Date</label>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-full bg-[#18181b] border border-[#27272a] rounded-xl px-3 py-2 text-sm text-white outline-none focus:border-purple-500 [color-scheme:dark]" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-[10px] font-black text-gray-400 uppercase">Scenario A</label>
              <select value={version} onChange={(e) => setVersion(e.target.value)} className="w-full bg-purple-900/10 border border-purple-500/30 rounded-xl px-3 py-2 text-sm text-purple-300 font-bold outline-none">
                <option value="V24">V24 (Turbo + Sniper)</option>
                <option value="V17">V17 (Sniper Only)</option>
                <option value="V14">V14 (Shield Only)</option>
                <option value="V13">V13 (Classic)</option>
              </select>
            </div>
            {compareMode ? (
              <div className="space-y-1.5 animate-fade-in">
                <label className="text-[10px] font-black text-orange-400 uppercase">Scenario B</label>
                <select value={versionB} onChange={(e) => setVersionB(e.target.value)} className="w-full bg-orange-900/10 border border-orange-500/30 rounded-xl px-3 py-2 text-sm text-orange-300 font-bold outline-none">
                  <option value="V14">V14 (Shield Only)</option>
                  <option value="V13">V13 (Classic)</option>
                  <option value="V17">V17 (Sniper Only)</option>
                  <option value="V24">V24 (Turbo + Sniper)</option>
                </select>
              </div>
            ) : (
                <div className="space-y-1.5 opacity-30">
                    <label className="text-[10px] font-black text-gray-600 uppercase">Scenario B</label>
                    <div className="w-full bg-[#18181b] border border-[#27272a] rounded-xl px-3 py-2 text-sm text-gray-600 font-bold">–</div>
                </div>
            )}
          </div>
        </div>

        <div className="bg-[#121214] p-6 rounded-2xl border border-[#27272a] space-y-5">
           <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest flex items-center gap-2 mb-2">
            <Activity className="w-3.5 h-3.5" />
            자본 및 리스크 설정
          </h3>
          
          <div className="grid grid-cols-3 gap-3">
             <div className="space-y-1.5">
              <label className="text-[10px] font-black text-gray-400 uppercase">Seed ($)</label>
              <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} className="w-full bg-[#18181b] border border-[#27272a] rounded-xl px-3 py-2 text-sm text-white font-bold outline-none" />
            </div>
            <div className="space-y-1.5">
              <label className="text-[10px] font-black text-gray-400 uppercase">Splits</label>
              <input type="number" value={split} onChange={(e) => setSplit(Number(e.target.value))} className="w-full bg-[#18181b] border border-[#27272a] rounded-xl px-3 py-2 text-sm text-white font-bold outline-none" />
            </div>
            <div className="space-y-1.5">
              <label className="text-[10px] font-black text-gray-400 uppercase">Target %</label>
              <input type="number" value={target} onChange={(e) => setTarget(Number(e.target.value))} className="w-full bg-[#18181b] border border-[#27272a] rounded-xl px-3 py-2 text-sm text-white font-bold outline-none" />
            </div>
          </div>

          <button onClick={runSimulation} disabled={loading} className={`w-full py-4 rounded-2xl flex items-center justify-center gap-2 font-black text-white transition-all shadow-xl active:scale-95 ${loading ? 'bg-purple-900/50' : 'bg-gradient-to-r from-purple-600 to-indigo-600 shadow-purple-900/20'}`}>
            {loading ? <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div> : <><Play className="w-4 h-4 fill-current" /> 분석 가공 (Backtest)</>}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 p-4 rounded-2xl flex items-center gap-3 text-red-400 text-sm font-bold animate-shake">
          <AlertCircle className="w-5 h-5" /> {error}
        </div>
      )}

      {resultA && (
        <div className="space-y-6 animate-fade-in-up">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
             <div className="bg-[#121214] border-l-4 border-purple-500 p-5 rounded-2xl shadow-xl space-y-4">
                <div className="flex justify-between items-center">
                    <span className="text-[10px] font-black text-purple-400 uppercase tracking-widest">Scenario A: {resultA.summary.version}</span>
                    <span className="text-xl font-black text-white tabular-nums">${resultA.summary.final_total.toLocaleString()}</span>
                </div>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <p className="text-[9px] text-gray-500 font-bold">Total Return</p>
                        <p className="text-lg font-black text-green-400">+{resultA.summary.total_return}%</p>
                    </div>
                    <div>
                        <p className="text-[9px] text-gray-500 font-bold">Max Drawdown</p>
                        <p className="text-lg font-black text-red-500">-{resultA.summary.mdd}%</p>
                    </div>
                </div>
             </div>

             {resultB ? (
                <div className="bg-[#121214] border-l-4 border-orange-500 p-5 rounded-2xl shadow-xl space-y-4 animate-fade-in">
                    <div className="flex justify-between items-center">
                        <span className="text-[10px] font-black text-orange-400 uppercase tracking-widest">Scenario B: {resultB.summary.version}</span>
                        <span className="text-xl font-black text-white tabular-nums">${resultB.summary.final_total.toLocaleString()}</span>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <p className="text-[9px] text-gray-500 font-bold">Total Return</p>
                            <p className="text-lg font-black text-green-400">+{resultB.summary.total_return}%</p>
                        </div>
                        <div>
                            <p className="text-[9px] text-gray-500 font-bold">Max Drawdown</p>
                            <p className="text-lg font-black text-red-500">-{resultB.summary.mdd}%</p>
                        </div>
                    </div>
                </div>
             ) : (
                <div className="bg-[#121214]/50 border-2 border-dashed border-[#27272a] p-5 rounded-2xl flex items-center justify-center text-gray-600 text-xs font-bold uppercase tracking-widest">
                    Compare scenario inactive
                </div>
             )}
          </div>

          <div className="bg-[#121214] border border-[#27272a] p-6 rounded-3xl shadow-xl">
             <div className="flex justify-between items-center mb-6">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-emerald-400" />
                성과 비교 차트 (16-Year Tracking)
              </h3>
              <div className="flex items-center gap-4 text-[9px] font-black uppercase">
                <span className="flex items-center gap-1.5 text-purple-400"><span className="w-2 h-2 bg-purple-500 rounded-full"></span> Scenario A</span>
                {resultB && <span className="flex items-center gap-1.5 text-orange-400"><span className="w-2 h-2 bg-orange-500 rounded-full"></span> Scenario B</span>}
                <span className="flex items-center gap-1.5 text-gray-600"><span className="w-2 h-2 bg-gray-600 rounded-full"></span> S&P 500</span>
              </div>
            </div>
            
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={combinedData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#27272a" />
                  <XAxis dataKey="date" hide />
                  <YAxis domain={['auto', 'auto']} hide />
                  <Tooltip contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '12px', fontSize: '10px' }} />
                  <Line type="monotone" dataKey="ScenarioA" stroke="#8b5cf6" strokeWidth={3} dot={false} animationDuration={1000} />
                  {resultB && <Line type="monotone" dataKey="ScenarioB" stroke="#f97316" strokeWidth={3} dot={false} animationDuration={1000} />}
                  <Line type="monotone" dataKey="Benchmark" stroke="#3f3f46" strokeWidth={1} dot={false} opacity={0.5} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      <div className="bg-[#121214] border border-[#27272a] p-6 rounded-2xl border-dashed">
        <h4 className="flex items-center gap-2 text-[10px] font-black text-gray-500 uppercase mb-3"> 전략 고도화 인사이트 💡</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-[0.7rem] text-gray-400 leading-relaxed italic">
            <p>"V24 Turbo는 급격한 하락장에서 시드를 적극적으로 투입하여 평단을 낮추는 효과가 탁월합니다. MDD는 소폭 상승할 수 있으나 하락장 탈출 속도는 V14 대비 최대 40% 이상 빠를 수 있습니다."</p>
            <p>"V17 Sniper는 전량 익절을 기다리기보다 1/4 단위의 부분 익절을 통해 현금 비중을 선제적으로 확보합니다. 이는 지하실이 없는 폭락장에서 시드 고갈을 막는 강력한 방어선이 됩니다."</p>
        </div>
      </div>
    </div>
  )
}
