import { useEffect, useState } from 'react';
import axios from 'axios';
import { 
  Search, Clock, Receipt, Calendar, ChevronRight, Activity, CheckCircle2,
  FileSpreadsheet, RefreshCw, Database, Layers
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

interface LedgerStats {
  total_realized_profit: number;
  total_revenue: number;
  total_invested: number;
  win_rate: number;
  unrealized_profit: number;
  active_value: number;
  total_cycles: number;
  tax_liability: number;
  net_profit: number;
}

export default function LedgerExplorer({ mode }: { mode: 'mock' | 'real' }) {
  const [viewMode, setViewMode] = useState<'cycles' | 'raw'>('cycles');
  const [cycles, setCycles] = useState<CycleEntry[]>([]);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [stats, setStats] = useState<LedgerStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [collapsedCycles, setCollapsedCycles] = useState<number[]>([]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [resCycles, resExplorer, resStats] = await Promise.all([
        axios.get(`/api/ledger/cycles?mode=${mode}`),
        axios.get(`/api/ledger/explorer?mode=${mode}`),
        axios.get(`/api/ledger/stats?mode=${mode}`)
      ]);
      setCycles(resCycles.data.cycles || []);
      setLedger(resExplorer.data.ledger || []);
      setStats(resStats.data.stats || null);
    } catch (e) {
      console.error("Ledger fetch error:", e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchData();
  }, [mode]);

  const handleExportExcel = async () => {
    setExporting(true);
    try {
      const response = await axios({
        url: `/api/ledger/export/excel?mode=${mode}`,
        method: 'GET',
        responseType: 'blob',
      });
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      const fileName = `Infinity_Trading_Report_${mode.toUpperCase()}_${new Date().toISOString().split('T')[0]}.xlsx`;
      link.setAttribute('download', fileName);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (e) {
      console.error("Excel Export Error:", e);
      alert("엑셀 리포트 생성 중 에러가 발생했습니다.");
    }
    setExporting(false);
  };

  const filteredCycles = cycles.filter(c => 
    c.ticker.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredLedger = ledger.filter(l => 
    l.ticker.toLowerCase().includes(searchTerm.toLowerCase()) ||
    l.note.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const activeCycleCount = cycles.filter(c => c.status === 'ACTIVE').length;
  const totalRecords = ledger.length;

  return (
    <div className="space-y-4 animate-fade-in-up pb-12">

      {/* ═══ Section 0: 장부 헤더 (제어 메뉴 스타일 통일) ═══ */}
      <div className="bg-[#121214] rounded-2xl border border-[#27272a] p-4 shadow-lg">
        <div className="flex justify-between items-center">
          <div>
            <h3 className="text-white font-bold text-sm flex items-center gap-2">
              📒 통합 거래 장부
              <span className="text-[0.55rem] text-gray-500 font-normal tracking-wider uppercase">({mode.toUpperCase()} Ledger)</span>
            </h3>
            <div className="mt-1.5 flex items-center gap-3 text-[10px] text-gray-500 font-bold tabular-nums">
              <span className="flex items-center gap-1"><Layers className="w-3 h-3 text-blue-400" /> 활성 {activeCycleCount}개</span>
              <span className="opacity-30">|</span>
              <span className="flex items-center gap-1"><Database className="w-3 h-3 text-gray-600" /> 기록 {totalRecords}건</span>
              {stats && stats.unrealized_profit !== 0 && (
                <>
                  <span className="opacity-30">|</span>
                  <span className={`flex items-center gap-1 ${stats.unrealized_profit >= 0 ? 'text-red-400' : 'text-blue-400'}`}>
                    미실현 {stats.unrealized_profit >= 0 ? '+' : ''}${stats.unrealized_profit.toFixed(2)}
                  </span>
                </>
              )}
            </div>
          </div>
          <button 
            onClick={fetchData}
            className="bg-[#18181b] text-gray-400 border border-[#27272a] p-2 rounded-xl hover:text-white transition-all active:scale-90"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-blue-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* ═══ Section 1: 컴팩트 탭 + 엑셀 출력 (한 줄 배치) ═══ */}
      <div className="bg-[#121214] rounded-2xl border border-[#27272a] p-3 shadow-lg">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 bg-[#18181b] p-1 rounded-xl border border-[#27272a] flex-1">
            <button 
              onClick={() => setViewMode('cycles')}
              className={`flex-1 px-3 py-2 rounded-lg text-[10px] font-black transition-all whitespace-nowrap ${viewMode === 'cycles' ? 'bg-[#27272a] text-white shadow' : 'text-gray-500 hover:text-gray-300'}`}
            >
              📋 사이클
            </button>
            <button 
              onClick={() => setViewMode('raw')}
              className={`flex-1 px-3 py-2 rounded-lg text-[10px] font-black transition-all whitespace-nowrap ${viewMode === 'raw' ? 'bg-[#27272a] text-white shadow' : 'text-gray-500 hover:text-gray-300'}`}
            >
              📜 전체 내역
            </button>
          </div>
          <button 
            onClick={handleExportExcel}
            disabled={exporting}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-[10px] font-black transition-all whitespace-nowrap border ${
              exporting 
                ? 'bg-gray-800 text-gray-600 border-[#27272a]' 
                : 'bg-emerald-600/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-600/20 active:scale-95'
            }`}
          >
            {exporting ? <Clock className="w-3.5 h-3.5 animate-spin" /> : <FileSpreadsheet className="w-3.5 h-3.5" />}
            Excel
          </button>
        </div>
      </div>

      {/* ═══ Section 2: 검색 바 ═══ */}
      <div className="relative">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-600" />
        <input 
          type="text" 
          placeholder="종목명 또는 메모 검색..." 
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full bg-[#121214] border border-[#27272a] rounded-2xl py-3 pl-10 pr-4 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50 transition-all font-bold"
        />
      </div>

      {viewMode === 'cycles' ? (
        /* ═══ Cycle Analysis View (최근 3개 노출, 나머지 스크롤) ═══ */
        <div className="space-y-3 max-h-[65vh] overflow-y-auto pr-1" style={{ scrollbarWidth: 'thin', scrollbarColor: '#27272a transparent' }}>
          {filteredCycles.length > 0 ? filteredCycles.map((cycle, idx) => (
            <div 
              key={`${cycle.ticker}-${idx}`}
              className={`bg-[#121214] border transition-all duration-300 rounded-2xl overflow-hidden shadow-lg ${
                !collapsedCycles.includes(idx) ? 'border-blue-500/40 ring-1 ring-blue-500/10' : 'border-[#27272a] hover:border-gray-700'
              }`}
            >
              {/* Cycle Header */}
              <div 
                className="p-4 flex items-center gap-3 cursor-pointer select-none"
                onClick={() => setCollapsedCycles(prev => prev.includes(idx) ? prev.filter(i => i !== idx) : [...prev, idx])}
              >
                {/* Ticker Badge */}
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-xs font-black shrink-0 ${
                  cycle.status === 'ACTIVE' 
                    ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' 
                    : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                }`}>
                  {cycle.ticker.substring(0, 4)}
                </div>

                {/* Info Grid */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-black text-white">{cycle.ticker}</span>
                    <span className={`text-[9px] font-black uppercase flex items-center gap-1 ${cycle.status === 'ACTIVE' ? 'text-blue-500' : 'text-emerald-500'}`}>
                      {cycle.status === 'ACTIVE' ? <Activity className="w-3 h-3" /> : <CheckCircle2 className="w-3 h-3" />}
                      {cycle.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-gray-500 tabular-nums">
                    <span className="flex items-center gap-1 truncate">
                      <Calendar className="w-3 h-3 text-gray-700 shrink-0" />
                      {cycle.start_date?.split(' ')[0]}
                    </span>
                    <span className="font-black text-gray-300 whitespace-nowrap">${cycle.invested.toLocaleString()}</span>
                    {cycle.status === 'GRADUATED' && (
                      <span className={`font-black whitespace-nowrap ${cycle.profit >= 0 ? 'text-red-400' : 'text-blue-400'}`}>
                        {cycle.profit >= 0 ? '+' : ''}${cycle.profit.toLocaleString()} ({cycle.yield}%)
                      </span>
                    )}
                  </div>
                </div>

                {/* Right Side */}
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[9px] font-black px-2 py-1 bg-[#18181b] text-gray-500 rounded-lg border border-[#27272a] tabular-nums whitespace-nowrap">
                    {cycle.trade_count} Tx
                  </span>
                  <ChevronRight className={`w-4 h-4 text-gray-700 transition-transform duration-300 ${!collapsedCycles.includes(idx) ? 'rotate-90 text-blue-500' : ''}`} />
                </div>
              </div>

              {/* Expansion: Trade Table */}
              {!collapsedCycles.includes(idx) && (
                <div className="border-t border-[#27272a] bg-[#0c0c0e]/80 p-3 animate-slide-down">
                  <div className="bg-[#121214] border border-[#27272a] rounded-xl overflow-hidden overflow-x-auto">
                    <table className="w-full text-[10px] text-left">
                      <thead>
                        <tr className="bg-[#18181b] text-gray-600 border-b border-[#27272a]">
                          <th className="px-3 py-2.5 font-black">일자</th>
                          <th className="px-3 py-2.5 font-black">구분</th>
                          <th className="px-3 py-2.5 font-black text-right">단가</th>
                          <th className="px-3 py-2.5 font-black text-right">수량</th>
                          <th className="px-3 py-2.5 font-black text-right">금액</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#27272a]">
                        {cycle.trades.map((t, ti) => (
                          <tr key={ti} className="hover:bg-blue-500/[0.02] transition-colors">
                            <td className="px-3 py-2.5 tabular-nums text-gray-400 whitespace-nowrap">{t.date}</td>
                            <td className="px-3 py-2.5">
                              <span className={`px-1.5 py-0.5 rounded text-[8px] font-black uppercase ${
                                t.side === 'BUY' ? 'bg-red-500/10 text-red-500' : 'bg-blue-500/10 text-blue-500'
                              }`}>
                                {t.side}
                              </span>
                            </td>
                            <td className="px-3 py-2.5 text-right tabular-nums font-bold text-gray-200">${t.price.toFixed(2)}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums text-gray-400">{t.qty}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums font-black text-white">${(t.price * t.qty).toLocaleString(undefined, {minimumFractionDigits:2})}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )) : (
            <div className="bg-[#121214] rounded-2xl border border-[#27272a] border-dashed py-16 text-center">
              <Receipt className="w-10 h-10 mx-auto text-gray-700 mb-3" />
              <p className="font-black text-sm text-gray-500 tracking-tight">거래 기록이 없습니다</p>
              <p className="text-[10px] text-gray-700 font-bold mt-1">시스템 가동 후 거래가 발생하면 이곳에 기록됩니다.</p>
            </div>
          )}
        </div>
      ) : (
        /* ═══ Raw Transactions View ═══ */
        <div className="bg-[#121214] rounded-2xl border border-[#27272a] overflow-hidden shadow-lg">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[10px] border-collapse">
              <thead>
                <tr className="bg-[#18181b] text-gray-600 border-b border-[#27272a]">
                  <th className="px-3 py-3 font-black uppercase tracking-wider">일자</th>
                  <th className="px-3 py-3 font-black uppercase tracking-wider">종목</th>
                  <th className="px-3 py-3 font-black uppercase tracking-wider">구분</th>
                  <th className="px-3 py-3 font-black uppercase tracking-wider text-right">수량</th>
                  <th className="px-3 py-3 font-black uppercase tracking-wider text-right">단가</th>
                  <th className="px-3 py-3 font-black uppercase tracking-wider text-right">금액</th>
                  <th className="px-3 py-3 font-black uppercase tracking-wider">상태</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#27272a]">
                {filteredLedger.length > 0 ? filteredLedger.map((entry, idx) => (
                  <tr key={`${entry.date}-${entry.ticker}-${idx}`} className="hover:bg-blue-500/[0.03] transition-colors">
                    <td className="px-3 py-2.5 whitespace-nowrap text-gray-400 tabular-nums">{entry.date}</td>
                    <td className="px-3 py-2.5 font-black text-blue-400">{entry.ticker}</td>
                    <td className="px-3 py-2.5">
                      <span className={`px-1.5 py-0.5 rounded text-[8px] font-black uppercase ${
                        entry.side === 'BUY' ? 'bg-red-500/10 text-red-500' : 'bg-blue-500/10 text-blue-500'
                      }`}>
                        {entry.side}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-right text-gray-300 tabular-nums">{entry.qty}</td>
                    <td className="px-3 py-2.5 text-right text-gray-300 tabular-nums">${entry.price.toFixed(2)}</td>
                    <td className="px-3 py-2.5 text-right font-black text-white tabular-nums">${(entry.price * entry.qty).toLocaleString(undefined, {minimumFractionDigits:2})}</td>
                    <td className="px-3 py-2.5">
                      <span className={`text-[9px] font-black rounded px-1.5 py-0.5 border ${
                        entry.status === 'ACTIVE' ? 'border-blue-500/20 text-blue-500 bg-blue-500/5' : 'border-emerald-500/20 text-emerald-500 bg-emerald-500/5'
                      }`}>
                        {entry.status}
                      </span>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={7} className="px-3 py-16 text-center">
                      <Receipt className="w-10 h-10 text-gray-700 mx-auto mb-3" />
                      <p className="font-black text-sm text-gray-500">기록된 트랜잭션이 없습니다</p>
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
