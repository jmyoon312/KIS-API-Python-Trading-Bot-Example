import { useEffect, useState } from 'react';
import axios from 'axios';
import { 
  Search, Clock, Receipt, TrendingUp, Calendar, ChevronRight, Activity, CheckCircle2
} from 'lucide-react';

interface Trade {
  date: string;
  side: string;
  price: number;
  qty: number;
  desc?: string;
}

interface CycleEntry {
  ticker: string;
  status: 'ACTIVE' | 'GRADUATED';
  start_date: string;
  end_date: string;
  invested: number;
  revenue: number;
  profit: number;
  yield: number;
  trade_count: number;
  trades: Trade[];
}

interface LedgerEntry {
  date: string;
  ticker: string;
  side: string;
  qty: number;
  price: number;
  total: number;
  status: string;
  note: string;
}

export default function LedgerExplorer({ mode }: { mode: 'mock' | 'real' }) {
  const [viewMode, setViewMode] = useState<'cycles' | 'raw'>('cycles');
  const [cycles, setCycles] = useState<CycleEntry[]>([]);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedCycle, setExpandedCycle] = useState<number | null>(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [resCycles, resExplorer] = await Promise.all([
        axios.get(`/api/ledger/cycles?mode=${mode}`),
        axios.get(`/api/ledger/explorer?mode=${mode}`)
      ]);
      setCycles(resCycles.data.cycles || []);
      setLedger(resExplorer.data.ledger || []);
    } catch (e) {
      console.error("Ledger fetch error:", e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchData();
  }, [mode]);

  const filteredCycles = cycles.filter(c => 
    c.ticker.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredLedger = ledger.filter(l => 
    l.ticker.toLowerCase().includes(searchTerm.toLowerCase()) ||
    l.note.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6 animate-fade-in pb-20">
      {/* 🚀 Header & Navigation */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 px-1">
        <div>
          <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
            <Receipt className="text-blue-400 w-5 h-5" />
            통합 거래 장부 분석
          </h2>
          <div className="flex items-center gap-2 mt-1">
            <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded ${mode === 'real' ? 'bg-blue-500/10 text-blue-500 border border-blue-500/20' : 'bg-orange-500/10 text-orange-500 border border-orange-500/20'}`}>
              {mode.toUpperCase()} Operational
            </span>
            <p className="text-[10px] text-gray-500 font-bold">Cycle-based Intelligence Explorer</p>
          </div>
        </div>

        <div className="flex items-center gap-2 bg-[#121214] p-1 rounded-2xl border border-[#27272a]">
          <button 
            onClick={() => setViewMode('cycles')}
            className={`px-4 py-1.5 rounded-xl text-[10px] font-black transition-all ${viewMode === 'cycles' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-gray-300'}`}
          >
            사이클별 분석
          </button>
          <button 
            onClick={() => setViewMode('raw')}
            className={`px-4 py-1.5 rounded-xl text-[10px] font-black transition-all ${viewMode === 'raw' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-gray-300'}`}
          >
            전체 내역 조회
          </button>
        </div>
      </div>

      {/* 🔍 Search & Stats Mini-Bar */}
      <div className="flex flex-col md:flex-row items-center gap-3">
        <div className="relative flex-1 w-full">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-600" />
          <input 
            type="text" 
            placeholder="종목명 또는 메모 검색..." 
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-[#121214] border border-[#27272a] rounded-2xl py-3 pl-11 pr-4 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50 transition-all font-bold shadow-xl"
          />
        </div>
        <button 
          onClick={fetchData}
          className="bg-[#121214] text-gray-400 border border-[#27272a] p-3 rounded-2xl hover:text-white transition-all active:scale-95 shadow-lg group"
          title="새로고침"
        >
          <Clock className={`w-4 h-4 ${loading ? 'animate-spin text-blue-400' : 'group-hover:rotate-180 transition-transform duration-500'}`} />
        </button>
      </div>

      {viewMode === 'cycles' ? (
        /* 🔄 Cycle Analysis View */
        <div className="space-y-4">
          {filteredCycles.length > 0 ? filteredCycles.map((cycle, idx) => (
            <div 
              key={`${cycle.ticker}-${idx}`}
              className={`bg-[#121214] border transition-all duration-300 rounded-3xl overflow-hidden shadow-2xl ${
                expandedCycle === idx ? 'border-blue-500/40 ring-1 ring-blue-500/10' : 'border-[#27272a] hover:border-gray-700'
              }`}
            >
              {/* Cycle Header Card */}
              <div 
                className="p-5 flex flex-col md:flex-row items-center gap-6 cursor-pointer select-none"
                onClick={() => setExpandedCycle(expandedCycle === idx ? null : idx)}
              >
                <div className="flex items-center gap-4 min-w-[140px]">
                  <div className={`w-12 h-12 rounded-2xl flex items-center justify-center font-black transition-colors ${
                    cycle.status === 'ACTIVE' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                  }`}>
                    {cycle.ticker}
                  </div>
                  <div>
                    <h4 className="text-sm font-black text-white">{cycle.ticker}</h4>
                    <span className={`text-[9px] font-black uppercase tracking-tighter flex items-center gap-1 ${cycle.status === 'ACTIVE' ? 'text-blue-500' : 'text-emerald-500'}`}>
                      {cycle.status === 'ACTIVE' ? <Activity className="w-3 h-3" /> : <CheckCircle2 className="w-3 h-3" />}
                      {cycle.status}
                    </span>
                  </div>
                </div>

                <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-4 w-full">
                  <div>
                    <p className="text-[8px] font-black text-gray-600 uppercase mb-0.5 tracking-widest">Duration</p>
                    <div className="text-[11px] font-bold text-gray-300 flex items-center gap-1.5 tabular-nums">
                      <Calendar className="w-3 h-3 text-gray-700" />
                      {cycle.start_date.split(' ')[0]} {cycle.end_date !== '-' && `→ ${cycle.end_date.split(' ')[0]}`}
                    </div>
                  </div>
                  <div>
                    <p className="text-[8px] font-black text-gray-600 uppercase mb-0.5 tracking-widest">Total Invested</p>
                    <div className="text-[11px] font-black text-white tabular-nums">${cycle.invested.toLocaleString()}</div>
                  </div>
                  <div>
                    <p className="text-[8px] font-black text-gray-600 uppercase mb-0.5 tracking-widest">Profit / Yield</p>
                    <div className={`text-[11px] font-black flex items-center gap-1.5 tabular-nums ${cycle.profit >= 0 ? 'text-red-400' : 'text-blue-400'}`}>
                      <TrendingUp className={`w-3 h-3 ${cycle.profit < 0 && 'rotate-180'}`} />
                      {cycle.status === 'GRADUATED' ? (
                        <>+${cycle.profit.toLocaleString()} ({cycle.yield}%)</>
                      ) : (
                        <span className="text-gray-500">In Progress</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center justify-end">
                    <span className="text-[10px] font-black px-2 py-0.5 bg-gray-800 text-gray-500 rounded-full border border-gray-700 tabular-nums">
                      {cycle.trade_count} Tx
                    </span>
                    <ChevronRight className={`ml-3 w-4 h-4 text-gray-700 transition-transform duration-300 ${expandedCycle === idx ? 'rotate-90 text-blue-500' : ''}`} />
                  </div>
                </div>
              </div>

              {/* Expansion Area: Trades */}
              {expandedCycle === idx && (
                <div className="border-t border-[#27272a] bg-[#0c0c0e]/50 p-6 animate-slide-down">
                  <div className="bg-[#121214] border border-[#27272a] rounded-2xl overflow-hidden overflow-x-auto">
                    <table className="w-full text-[10px] text-left">
                      <thead>
                        <tr className="bg-[#18181b] text-gray-600 border-b border-[#27272a]">
                          <th className="px-5 py-3 font-black">Date</th>
                          <th className="px-5 py-3 font-black">Side</th>
                          <th className="px-5 py-3 font-black text-right">Price</th>
                          <th className="px-5 py-3 font-black text-right">Qty</th>
                          <th className="px-5 py-3 font-black text-right">Total</th>
                          <th className="px-5 py-3 font-black">Note</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#27272a]">
                        {cycle.trades.map((t, ti) => (
                          <tr key={ti} className="hover:bg-[#18181b] transition-colors group">
                            <td className="px-5 py-3 tabular-nums font-bold text-gray-400">{t.date}</td>
                            <td className="px-5 py-3">
                              <span className={`px-1.5 py-0.5 rounded-[4px] font-black uppercase text-[8px] ${t.side === 'BUY' ? 'bg-red-500/10 text-red-500' : 'bg-blue-500/10 text-blue-500'}`}>
                                {t.side}
                              </span>
                            </td>
                            <td className="px-5 py-3 text-right tabular-nums font-bold text-gray-200">${t.price.toFixed(2)}</td>
                            <td className="px-5 py-3 text-right tabular-nums font-bold text-gray-200">{t.qty}</td>
                            <td className="px-5 py-3 text-right tabular-nums font-black text-white">${(t.price * t.qty).toLocaleString(undefined, {minimumFractionDigits:2})}</td>
                            <td className="px-5 py-3 text-gray-500 font-medium italic">{t.desc || 'System Trade'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )) : (
            <div className="py-20 text-center opacity-30">
               <Receipt className="w-12 h-12 mx-auto mb-3" />
               <p className="font-black text-sm">기록된 거래 사이클이 없습니다.</p>
            </div>
          )}
        </div>
      ) : (
        /* 📜 Raw Transactions View */
        <div className="bg-[#121214] rounded-3xl border border-[#27272a] overflow-hidden shadow-2xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[10px] border-collapse">
              <thead>
                <tr className="bg-[#18181b] text-gray-500 border-b border-[#27272a]">
                  <th className="px-6 py-4 font-black">Date</th>
                  <th className="px-6 py-4 font-black">Ticker</th>
                  <th className="px-6 py-4 font-black">Side</th>
                  <th className="px-6 py-4 font-black text-right">Qty</th>
                  <th className="px-6 py-4 font-black text-right">Price</th>
                  <th className="px-6 py-4 font-black text-right">Total</th>
                  <th className="px-6 py-4 font-black">Status</th>
                  <th className="px-6 py-4 font-black text-right">Note</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#27272a]">
                {filteredLedger.length > 0 ? filteredLedger.map((entry, idx) => (
                  <tr key={`${entry.date}-${entry.ticker}-${idx}`} className="group hover:bg-[#18181b] transition-colors border-l-2 border-transparent hover:border-blue-500/50">
                    <td className="px-6 py-3 whitespace-nowrap">
                      <span className="text-gray-400 font-bold tabular-nums">{entry.date}</span>
                    </td>
                    <td className="px-6 py-3 font-black text-blue-400">{entry.ticker}</td>
                    <td className="px-6 py-3">
                      <span className={`px-1.5 py-0.5 rounded font-black text-[8px] ${entry.side === 'BUY' ? 'bg-red-500/10 text-red-500' : 'bg-blue-500/10 text-blue-500'}`}>
                        {entry.side}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-right font-bold text-gray-300 tabular-nums">{entry.qty}</td>
                    <td className="px-6 py-3 text-right font-bold text-gray-300 tabular-nums">${entry.price.toFixed(2)}</td>
                    <td className="px-6 py-3 text-right font-black text-white tabular-nums">${(entry.price * entry.qty).toLocaleString(undefined, {minimumFractionDigits:2})}</td>
                    <td className="px-6 py-3">
                      <span className={`text-[8px] font-black rounded-full px-2 py-0.5 border ${entry.status === 'ACTIVE' ? 'border-blue-500/30 text-blue-500 bg-blue-500/5' : 'border-emerald-500/30 text-emerald-500 bg-emerald-500/5'}`}>
                        {entry.status}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-right text-gray-600 font-medium">{entry.note}</td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={8} className="px-6 py-20 text-center grayscale opacity-30">
                      <div className="flex flex-col items-center gap-3">
                          <Receipt className="w-12 h-12" />
                          <span className="font-black">조건에 맞는 거래 내역이 없습니다.</span>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
