import { useEffect, useState } from 'react'
import axios from 'axios'
import { 
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, PieChart, Pie, Cell
} from 'recharts'
import { 
  TrendingUp, PieChart as PieIcon, 
  RefreshCw, Receipt, BarChart3, Calendar, Activity,
  Wallet, Landmark, Coins
} from 'lucide-react'

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4']

interface AnalyticsData {
  current_valuation: {
    total: number
    cash: number
    holdings: number
    ticker_eval: Record<string, number>
  }
  snapshots: any[]
  capital_flows: any[]
  history: any[]
  metrics: {
    win_rate: number
    profit_factor: number
    total_trades: number
    gross_profit: number
    gross_loss: number
    avg_holding_days: number
  }
  ticker_performance: Record<string, { profit: number, trades: number, win_rate: number }>
  periodical: any
  tax: {
    year: string
    total_profit: number
    allowance: number
    taxable_profit: number
    estimated_tax: number
  }
}

export default function PerformanceAnalytics({ mode }: { mode: 'mock' | 'real' }) {
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'summary' | 'period' | 'tax'>('summary')

  const fetchData = async () => {
    try {
      const res = await axios.get(`/api/analytics?mode=${mode}`)
      setData(res.data.analytics)
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  useEffect(() => {
    fetchData()
  }, [mode])

  if (loading) return (
    <div className="flex flex-col justify-center items-center h-64 space-y-4">
      <div className="w-10 h-10 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin"></div>
      <p className="text-gray-500 font-bold animate-pulse">심층 분석 데이터 로딩 중...</p>
    </div>
  )

  if (!data) return <div className="text-center py-20 text-gray-500">데이터를 불러오지 못했습니다.</div>

  // 🎯 [Bug Fix] 피드백: 실시간 자산 배분이 정확히 나타나야 함
  // 백엔드에서 제공하는 current_valuation을 최우선으로 사용합니다.
  const cur = data.current_valuation
  const allocationData = []
  
  if (cur.ticker_eval && Object.keys(cur.ticker_eval).length > 0) {
    Object.entries(cur.ticker_eval).forEach(([name, value]) => {
      allocationData.push({ name, value })
    })
    if (cur.cash > 0) allocationData.push({ name: 'Cash', value: cur.cash })
  } else {
    if (cur.cash > 0) allocationData.push({ name: 'Cash', value: cur.cash })
    if (cur.holdings > 0) allocationData.push({ name: 'Stocks', value: cur.holdings })
  }

  // MDD calculation from snapshots
  let maxTotal = 0
  let maxDD = 0
  data.snapshots.forEach(s => {
    if (s.total > maxTotal) maxTotal = s.total
    if (maxTotal > 0) {
      const dd = ((maxTotal - s.total) / maxTotal) * 100
      if (dd > maxDD) maxDD = dd
    }
  })

  const years = Object.keys(data.periodical || {}).sort().reverse()
  const monthKeys = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']

  return (
    <div className="space-y-6 animate-fade-in pb-20">
      {/* 🚀 Tactical Header */}
      <div className="flex justify-between items-center px-1">
        <div>
          <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
            <BarChart3 className="text-blue-400 w-5 h-5" />
            성과 분석 리포트
          </h2>
          <p className="text-[10px] text-gray-500 font-black uppercase tracking-widest mt-0.5">Strategy Performance Archive</p>
        </div>
        <button 
          onClick={fetchData}
          className="bg-[#121214] text-gray-400 border border-[#27272a] p-2 rounded-xl hover:text-white transition-all active:scale-90"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* 💎 [New] Top High-Visibility Asset Summary Bar */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
         <div className="bg-gradient-to-br from-blue-600/20 to-transparent p-6 rounded-3xl border border-blue-500/30 flex justify-between items-center">
            <div>
                <p className="text-[10px] font-black text-blue-400 uppercase mb-1 flex items-center gap-1.5"><Wallet className="w-3 h-3"/> Total Net Worth</p>
                <h4 className="text-2xl font-black text-white tabular-nums">${cur.total.toLocaleString()}</h4>
            </div>
            <div className="bg-blue-500/10 p-3 rounded-2xl border border-blue-500/10">
                <TrendingUp className="w-6 h-6 text-blue-400"/>
            </div>
         </div>
         <div className="bg-[#121214] p-6 rounded-3xl border border-[#27272a] flex justify-between items-center">
            <div>
                <p className="text-[10px] font-black text-emerald-400 uppercase mb-1 flex items-center gap-1.5"><Landmark className="w-3 h-3"/> Available Cash</p>
                <h4 className="text-2xl font-black text-white tabular-nums">${cur.cash.toLocaleString()}</h4>
            </div>
            <div className="bg-emerald-500/10 p-3 rounded-2xl border border-emerald-500/10">
                <Coins className="w-6 h-6 text-emerald-400"/>
            </div>
         </div>
         <div className="bg-[#121214] p-6 rounded-3xl border border-[#27272a] flex justify-between items-center">
            <div>
                <p className="text-[10px] font-black text-orange-400 uppercase mb-1 flex items-center gap-1.5"><PieIcon className="w-3 h-3"/> Equity Valuation</p>
                <h4 className="text-2xl font-black text-white tabular-nums">${cur.holdings.toLocaleString()}</h4>
            </div>
            <div className="bg-orange-500/10 p-3 rounded-2xl border border-orange-500/10">
                <Activity className="w-6 h-6 text-orange-400"/>
            </div>
         </div>
      </div>

      {/* 📑 Internal Tabs */}
      <div className="flex bg-[#121214] p-1 rounded-2xl border border-[#27272a]">
        {[
          { id: 'summary', label: '📊 요약', icon: TrendingUp },
          { id: 'period', label: '📅 기간별', icon: Calendar },
          { id: 'tax', label: '🛡️ 리스크/세금', icon: Receipt },
        ].map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id as any)}
            className={`flex-1 py-2.5 rounded-xl text-xs font-black flex items-center justify-center gap-2 transition-all ${
              activeTab === t.id ? 'bg-[#27272a] text-white shadow-lg' : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            <t.icon className="w-3.5 h-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === 'summary' && (
        <div className="space-y-6 animate-fade-in-up">
          {/* Detailed Metric Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-[#121214] p-5 rounded-2xl border border-[#27272a]">
              <p className="text-[9px] font-black text-gray-500 uppercase mb-2">Win Rate</p>
              <div className="text-xl font-black text-white tabular-nums">{data.metrics.win_rate}%</div>
            </div>
            <div className="bg-[#121214] p-5 rounded-2xl border border-[#27272a]">
              <p className="text-[9px] font-black text-gray-500 uppercase mb-2">Profit Factor</p>
              <div className="text-xl font-black text-white tabular-nums">{data.metrics.profit_factor}</div>
            </div>
            <div className="bg-[#121214] p-5 rounded-2xl border border-[#27272a] text-red-400">
              <p className="text-[9px] font-black text-gray-500 uppercase mb-2">Max DD</p>
              <div className="text-xl font-black tabular-nums">-{maxDD.toFixed(2)}%</div>
            </div>
            <div className="bg-[#121214] p-5 rounded-2xl border border-[#27272a] text-yellow-500">
              <p className="text-[9px] font-black text-gray-500 uppercase mb-2">Avg Holding</p>
              <div className="text-xl font-black tabular-nums">{data.metrics.avg_holding_days?.toFixed(1) || '0'} Days</div>
            </div>
          </div>

          {/* [V23.5] Ticker Summary Table */}
          {data.ticker_performance && Object.keys(data.ticker_performance).length > 0 && (
            <div className="bg-[#121214] rounded-3xl border border-[#27272a] p-6 shadow-lg overflow-hidden">
                <h3 className="text-[10px] font-black text-gray-500 uppercase mb-4 flex items-center gap-2 tracking-widest">
                    <Activity className="w-4 h-4 text-cyan-400" />
                    종목별 성과 통계 <span className="text-[7px] text-gray-600 font-normal lowercase">(Ticker Performance)</span>
                </h3>
                <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                        <thead>
                            <tr className="text-gray-500 border-b border-[#27272a]">
                                <th className="pb-2 font-black">종목</th>
                                <th className="pb-2 font-black text-right">총 수익</th>
                                <th className="pb-2 font-black text-right">매매 횟수</th>
                                <th className="pb-2 font-black text-right">승률</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-[#27272a]">
                            {Object.entries(data.ticker_performance).sort((a,b) => b[1].profit - a[1].profit).map(([ticker, stats]) => (
                                <tr key={ticker} className="group hover:bg-[#18181b] transition-colors">
                                    <td className="py-3 font-black text-white">{ticker}</td>
                                    <td className={`py-3 text-right font-black tabular-nums ${stats.profit >= 0 ? 'text-red-400' : 'text-blue-400'}`}>
                                        ${stats.profit.toLocaleString()}
                                    </td>
                                    <td className="py-3 text-right text-gray-400 tabular-nums">{stats.trades}회</td>
                                    <td className="py-3 text-right font-black text-emerald-400 tabular-nums">{stats.win_rate}%</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Asset Allocation Pie */}
            <div className="bg-[#121214] rounded-3xl border border-[#27272a] p-6 shadow-lg">
                <h3 className="text-[10px] font-black text-gray-500 uppercase mb-6 flex items-center gap-2 tracking-widest">
                <PieIcon className="w-4 h-4 text-orange-400" />
                적시적 자산 배분 <span className="text-[7px] text-gray-600 font-normal lowercase">(Ticker Breakdown)</span>
                </h3>
                <div className="flex items-center">
                <div className="w-1/2 h-40">
                    <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                        <Pie data={allocationData} cx="50%" cy="50%" innerRadius={35} outerRadius={55} paddingAngle={5} dataKey="value">
                        {allocationData.map((_, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                        </Pie>
                    </PieChart>
                    </ResponsiveContainer>
                </div>
                <div className="w-1/2 space-y-3">
                    {allocationData.map((entry, index) => (
                    <div key={entry.name} className="flex items-center justify-between group/item">
                        <div className="flex items-center gap-2">
                        <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLORS[index % COLORS.length] }}></div>
                        <span className="text-[11px] font-black text-gray-400">{entry.name}</span>
                        </div>
                        <span className="text-[12px] font-black text-white tabular-nums">
                        {cur.total > 0 ? ((entry.value / cur.total) * 100).toFixed(1) : 0}%
                        </span>
                    </div>
                    ))}
                </div>
                </div>
            </div>

            {/* Equity Trajectory Summary Chart */}
            <div className="bg-[#121214] rounded-3xl border border-[#27272a] p-6 shadow-xl relative overflow-hidden">
                <h3 className="text-[10px] font-black text-gray-500 uppercase mb-6 flex items-center gap-2 tracking-widest">
                <Activity className="w-4 h-4 text-blue-400" />
                자산 추이 모니터링 <span className="text-[7px] text-gray-600 font-normal lowercase">(Equity Curve)</span>
                </h3>
                <div className="h-40 w-full">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={data.snapshots}>
                    <defs>
                        <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#27272a" />
                    <XAxis dataKey="date" hide={true} />
                    <YAxis domain={['auto', 'auto']} hide={true} />
                    <Tooltip contentStyle={{ backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '12px', fontSize: '10px' }} />
                    <Area type="monotone" dataKey="total" stroke="#3b82f6" strokeWidth={3} fillOpacity={1} fill="url(#colorTotal)" />
                    </AreaChart>
                </ResponsiveContainer>
                </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'period' && (
        <div className="space-y-6 animate-fade-in-up">
          {years.length > 0 ? years.map(year => (
            <div key={year} className="bg-[#121214] p-6 rounded-3xl border border-[#27272a] shadow-xl">
              <div className="flex justify-between items-center mb-6">
                <h3 className="text-lg font-black text-white">{year} <span className="text-gray-500 font-bold ml-1 text-sm">Performance Grid</span></h3>
                <div className="text-sm font-black text-emerald-400 tabular-nums">
                  +${data.periodical[year].profit.toLocaleString()}
                </div>
              </div>
              
              <div className="grid grid-cols-4 md:grid-cols-6 gap-2">
                {monthKeys.map(month => {
                  const profit = data.periodical[year].months[month] || 0
                  const isProfit = profit > 0
                  const isLoss = profit < 0
                  
                  return (
                    <div 
                      key={month} 
                      className={`h-16 rounded-xl border flex flex-col items-center justify-center p-2 transition-all group relative overflow-hidden ${
                        isProfit ? 'bg-green-500/10 border-green-500/20' : 
                        isLoss ? 'bg-red-500/10 border-red-500/20' : 
                        'bg-[#09090b] border-[#27272a] opacity-30 shadow-inner'
                      }`}
                    >
                      <div className="text-[8px] font-black text-gray-500 uppercase mb-1">{month}월</div>
                      <div className={`text-[10px] font-black tabular-nums ${isProfit ? 'text-green-400' : isLoss ? 'text-red-400' : 'text-gray-700'}`}>
                        {profit !== 0 ? `${isProfit ? '+' : ''}${Math.round(profit)}` : '-'}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )) : (
            <div className="bg-[#121214] p-12 rounded-3xl border border-[#27272a] border-dashed text-center space-y-4">
                <Calendar className="w-12 h-12 text-gray-700 mx-auto" />
                <div>
                    <h3 className="text-gray-400 font-black">데이터 수집 중입니다.</h3>
                    <p className="text-[10px] text-gray-600 mt-1 uppercase font-bold tracking-widest">Waiting for first graduation history</p>
                </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'tax' && (
        <div className="space-y-6 animate-fade-in-up">
          <div className="bg-gradient-to-br from-[#1a1a1e] to-[#09090b] p-8 rounded-3xl border border-blue-500/30 shadow-2xl relative overflow-hidden">
            <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/5 blur-[100px] rounded-full -mr-32 -mt-32"></div>
            <div className="relative z-10">
              <h3 className="text-xl font-black text-white mb-6 flex items-center gap-3 tracking-tight">
                <Receipt className="text-blue-400 w-6 h-6" />
                {data.tax?.year || '2026'}년 양도소득세 추산
              </h3>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
                <div className="space-y-5">
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-gray-400 font-bold tracking-tight">올해 확정 수익 (Total)</span>
                    <span className="text-white font-black tabular-nums">${data.tax?.total_profit.toLocaleString() || '0'}</span>
                  </div>
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-gray-400 font-bold tracking-tight">기비용 공제액 (Allowance)</span>
                    <span className="text-gray-500 font-black tabular-nums">-${data.tax?.allowance.toLocaleString() || '0'}</span>
                  </div>
                  <div className="h-[1px] bg-[#27272a]"></div>
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-blue-400 font-black tracking-tight uppercase">Taxable Basis</span>
                    <span className="text-blue-400 font-black tabular-nums">${data.tax?.taxable_profit.toLocaleString() || '0'}</span>
                  </div>
                </div>
                
                <div className="bg-[#09090b]/80 p-6 rounded-2xl border border-blue-500/20 backdrop-blur-sm self-center">
                  <p className="text-[10px] font-bold text-gray-500 uppercase mb-2">Estimated Tax (22%)</p>
                  <div className="text-3xl font-black text-white tabular-nums tracking-tighter shadow-blue-500/20">
                    ${data.tax?.estimated_tax.toLocaleString() || '0'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
