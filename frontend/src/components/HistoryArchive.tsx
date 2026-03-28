import { useEffect, useState } from 'react'
import axios from 'axios'

export default function HistoryArchive() {
  const [history, setHistory] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const api = axios.create({ baseURL: '/api' })
        const res = await api.get('/history')
        setHistory(res.data.history || [])
      } catch (e) { console.error(e) }
      setLoading(false)
    }
    fetchHistory()
  }, [])

  if (loading) return <div className="flex justify-center items-center h-40"><p className="text-gray-400">Loading Archive...</p></div>

  const totalProfit = history.reduce((s, h) => s + (h.profit || 0), 0)
  const totalYield = history.length > 0 ? history.reduce((s, h) => s + (h.yield || 0), 0) / history.length : 0

  return (
    <div className="space-y-4 animate-fade-in-up pb-8">
      {/* Summary Header */}
      {history.length > 0 && (
        <div className="bg-[#121214] rounded-2xl border border-yellow-500/30 p-5 shadow-lg">
          <div className="flex justify-between items-center mb-2">
            <span className="text-gray-400 text-sm font-bold">🏆 누적 졸업 실적</span>
            <span className="text-yellow-500 text-xs font-bold">{history.length}회 졸업</span>
          </div>
          <div className="flex justify-between items-baseline">
            <div>
              <div className="text-green-500 text-2xl font-black drop-shadow-[0_0_10px_rgba(34,197,94,0.4)] tabular-nums">
                +${totalProfit.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </div>
              <div className="text-gray-500 text-xs mt-1">총 누적 수익</div>
            </div>
            <div className="text-right">
              <div className="text-green-500/80 text-lg font-bold tabular-nums">{totalYield.toFixed(2)}%</div>
              <div className="text-gray-500 text-xs mt-1">평균 수익률</div>
            </div>
          </div>
        </div>
      )}

      {/* Individual Records */}
      {history.length > 0 ? history.slice().reverse().map((h, i) => (
        <div key={i} className="bg-[#121214] rounded-xl border border-[#27272a] shadow-lg p-5 flex justify-between items-center hover:border-yellow-500/30 transition-colors group">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-2xl font-black text-white">{h.ticker}</span>
              <span className="bg-yellow-900/20 text-yellow-500 text-[10px] font-bold px-2 py-0.5 rounded border border-yellow-900/30">명예졸업</span>
            </div>
            <div className="text-gray-500 text-xs flex items-center gap-1">
              <span>📅 {h.end_date}</span>
            </div>
          </div>
          <div className="text-right">
            <div className="text-2xl font-black text-green-500 drop-shadow-[0_0_8px_rgba(34,197,94,0.4)] truncate tabular-nums">
              +${h.profit.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </div>
            <div className="text-green-500/80 text-xs font-bold mt-0.5">({h.yield.toFixed(2)}%)</div>
          </div>
        </div>
      )) : (
        <div className="text-center py-16 text-gray-500 bg-[#121214] rounded-xl border border-[#27272a] shadow-inner">
          <span className="text-5xl block mb-3 opacity-40">🏆</span>
          <p className="font-bold text-base">아직 기록된 졸업 역사가 없습니다.</p>
          <p className="text-xs text-gray-600 mt-2">종목이 목표수익률에 도달하여 졸업하면 이곳에 기록됩니다.</p>
        </div>
      )}
    </div>
  )
}
