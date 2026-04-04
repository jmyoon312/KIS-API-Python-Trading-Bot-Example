import { useState } from 'react';
import axios from 'axios';

interface ControlPanelProps {
  ticker: string;
  config: any;
  seedVal: number;
  holdings: number; // 📦 [V26.6] 현재 보유 수량 추가
  mode: 'mock' | 'real';
  onClose: () => void;
  onRefresh: () => void;
}

export default function ControlPanel({ ticker, config, seedVal, holdings, mode, onClose, onRefresh }: ControlPanelProps) {
  const [seed, setSeed] = useState(seedVal || config.seed || 0);
  const [split, setSplit] = useState(config.split || 40);
  const [target, setTarget] = useState(config.target || 10);
  const [compound, setCompound] = useState(config.compound || 70);
  const [force, setForce] = useState(false); 
  const [sellQty, setSellQty] = useState<string>(''); // 📉 [V26.6] 매도 수량 상태
  const [loading, setLoading] = useState(false);

  const api = axios.create({ baseURL: '/api' });

  const handleSaveSettings = async () => {
    setLoading(true);
    try {
      await Promise.all([
        api.post('/settings/seed', { ticker, value: seed, mode, force }),
        api.post('/settings/split', { ticker, value: split, mode }),
        api.post('/settings/target', { ticker, value: target, mode }),
        api.post('/settings/compound', { ticker, value: compound, mode }),
      ]);
      await api.get(`/refresh?mode=${mode}`);
      setTimeout(() => {
        onRefresh();
        onClose();
      }, 800);
    } catch (e) {
      console.error(e);
      setLoading(false);
    }
  };

  const handleManualExec = async () => {
    // 🔔 [V26.6] 사용자 피드백 반영: 확인 창 추가
    if (!window.confirm(`[${ticker}] 수동 즉시 매수를 실행하시겠습니까? (잠금 해제 및 다음 사이클 집행)\n\n※ 매수는 시장 상황에 따라 다음 엔진 회전 때 최적가로 집행됩니다.`)) return;
    setLoading(true);
    try {
      await api.post(`/action/exec`, { ticker, mode });
      alert(`[${ticker}] 즉시 매수 요청이 성공적으로 전송되었습니다.`);
      setTimeout(() => {
        onRefresh();
        onClose();
      }, 1000);
    } catch (e) {
      console.error(e);
      setLoading(false);
    }
  };

  const handleManualSell = async () => {
    const qty = parseInt(sellQty);
    if (!qty || qty <= 0) {
      alert("매도 수량을 입력해주세요.");
      return;
    }
    if (qty > holdings) {
      if (!window.confirm(`입력한 수량(${qty})이 현재 보유량(${holdings})보다 많습니다. 계속하시겠습니까?`)) return;
    }

    // 🔔 [V26.6] 사용자 피드백 반영: 확인 창 추가
    if (!window.confirm(`[${ticker}] ${qty}주를 즉시 수동 매도하시겠습니까?\n\n※ 매도는 현재가(매수1호가)로 즉시 주문이 전송됩니다.`)) return;
    
    setLoading(true);
    try {
      await api.post(`/action/sell`, { ticker, qty, mode });
      alert(`[${ticker}] ${qty}주 매도 주문이 성공적으로 접수되었습니다.`);
      setTimeout(() => {
        onRefresh();
        onClose();
      }, 1000);
    } catch (e) {
      console.error(e);
      setLoading(false);
    }
  };

  return (
    <div className="animate-fade-in mt-4 border border-[#27272a] bg-[#121214] rounded-2xl py-5 px-5 overflow-hidden shadow-2xl relative">
      {/* 🏷️ [V26.8] 상단 헤더 및 닫기 버튼 (완벽한 겹침 방지 레이아웃) */}
      <div className="flex justify-between items-center mb-6 pb-4 border-b border-[#27272a]">
        <div className="flex flex-col">
          <h3 className="text-sm font-black text-blue-400 tracking-tighter flex items-center gap-2">
            <span className="text-xs">⚙️</span> {ticker} 설정 제어
          </h3>
          <p className="text-[0.6rem] text-gray-500 mt-0.5 font-bold uppercase tracking-widest">Manual Control Center</p>
        </div>
        <button 
          onClick={onClose}
          className="text-gray-400 hover:text-white transition-all p-1.5 bg-[#18181b] rounded-lg border border-[#3f3f46] flex-shrink-0 shadow-sm active:scale-90"
          title="닫기"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="w-full space-y-6">
        {/* Capital Control */}
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <div className="flex flex-col">
              <label className="text-[0.7rem] font-black text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
                <span className="text-[0.6rem]">💰</span> 운용 시드머니 ($)
              </label>
              <span className="text-[0.65rem] text-gray-500 mt-0.5">
                현재 투입액: <span className="text-blue-400 font-bold">${seedVal.toLocaleString()}</span>
              </span>
            </div>
            <input 
              type="number" 
              value={seed} 
              onChange={(e) => setSeed(Number(e.target.value))}
              className="bg-[#09090b] border border-[#27272a] rounded-lg px-3 py-1.5 text-right w-28 focus:outline-none focus:border-blue-500 font-black text-white tabular-nums transition-colors"
            />
          </div>
          
          <div className="flex items-center gap-2 mt-1">
            <input 
              type="checkbox" 
              id="forceApply" 
              checked={force} 
              onChange={(e) => setForce(e.target.checked)}
              className="w-4 h-4 rounded border-[#3f3f46] text-blue-600 focus:ring-blue-500 bg-[#09090b]"
            />
            <label htmlFor="forceApply" className="text-[0.65rem] text-gray-400 cursor-pointer hover:text-gray-200 transition-colors flex items-center gap-1">
              ⚠️ <span className="underline decoration-dotted text-red-500/70">즉시 적용 (강제)</span> - 활동 중인 자본 즉각 변경
            </label>
          </div>
        </div>

        {/* Parameters */}
        <div className="space-y-4 pt-4 border-t border-[#27272a]">
          <div className="flex justify-between items-center">
            <label className="text-[0.7rem] font-bold text-gray-400 flex items-center gap-1.5">
              <span className="text-[0.6rem]">⏱️</span> 분할 횟수
            </label>
            <div className="flex items-center gap-3">
              <input type="range" min="10" max="100" step="10" value={split} onChange={(e) => setSplit(Number(e.target.value))} className="w-20 accent-blue-500 h-1" />
              <span className="text-xs w-8 text-right font-mono text-white font-bold">{split}회</span>
            </div>
          </div>

          <div className="flex justify-between items-center">
            <label className="text-[0.7rem] font-bold text-gray-400 flex items-center gap-1.5">
              <span className="text-[0.6rem]">🎯</span> 목표 수익률
            </label>
            <div className="flex items-center gap-3">
              <input type="range" min="5" max="30" step="1" value={target} onChange={(e) => setTarget(Number(e.target.value))} className="w-20 accent-green-500 h-1" />
              <span className="text-xs w-8 text-right font-mono text-white font-bold">{target}%</span>
            </div>
          </div>

          <div className="flex justify-between items-center">
            <label className="text-[0.7rem] font-bold text-gray-400 flex items-center gap-1.5">
              <span className="text-[0.6rem]">💸</span> 자동복리율
            </label>
            <div className="flex items-center gap-3">
              <input type="range" min="0" max="100" step="10" value={compound} onChange={(e) => setCompound(Number(e.target.value))} className="w-20 accent-indigo-500 h-1" />
              <span className="text-xs w-8 text-right font-mono text-white font-bold">{compound}%</span>
            </div>
          </div>
        </div>
        
        {/* Buttons Section */}
        <div className="pt-2 space-y-4">
          <button 
            onClick={handleSaveSettings} 
            disabled={loading}
            className="w-full py-3 bg-blue-600 hover:bg-blue-500 active:scale-[0.98] transition-all rounded-xl text-xs font-black text-white shadow-lg disabled:opacity-50 flex justify-center items-center gap-2"
          >
            {loading ? <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin"></div> : '💾 운용 설정 저장 및 창 닫기'}
          </button>

          {/* Manual Trade Area */}
          <div className="bg-[#18181b] p-4 rounded-xl border border-[#27272a] space-y-3">
             <button 
                onClick={handleManualExec}
                className="w-full py-2.5 bg-green-500/10 border border-green-500/30 text-green-400 text-xs font-black rounded-lg hover:bg-green-500/20 transition-all flex justify-center items-center gap-2"
              >
                🛒 수동 즉시 매수
              </button>

              <div className="space-y-2 mt-2">
                <div className="flex flex-col gap-2">
                  <div className="relative">
                    <input 
                      type="number"
                      placeholder="매도 수량 입력"
                      value={sellQty}
                      onChange={(e) => setSellQty(e.target.value)}
                      className="w-full bg-[#09090b] border border-[#27272a] rounded-lg pl-3 pr-16 py-2 text-xs text-white focus:outline-none focus:border-red-500 font-bold"
                    />
                    <button 
                      onClick={() => setSellQty(holdings.toString())}
                      className="absolute right-1.5 top-1.5 px-2 py-1 bg-[#27272a] text-[0.6rem] text-gray-300 font-bold rounded hover:text-white transition-colors border border-[#3f3f46]"
                    >
                      전체 선택
                    </button>
                  </div>
                  <button 
                    onClick={handleManualSell}
                    disabled={loading || !sellQty}
                    className="w-full py-2.5 bg-red-600 hover:bg-red-500 text-white text-xs font-black rounded-lg transition-all active:scale-[0.98] disabled:opacity-50 shadow-md shadow-red-900/20"
                  >
                    📉 수동 즉시 매도
                  </button>
                </div>
                <div className="flex justify-between items-center px-1">
                   <p className="text-[0.6rem] text-gray-500 italic">
                      * 현재 보유량: <span className="text-gray-300 font-bold">{holdings}</span>주
                   </p>
                </div>
              </div>
          </div>
        </div>

        <div className="flex justify-center pt-2">
           <button 
            onClick={onClose} 
            className="flex items-center gap-1.5 text-gray-500 hover:text-white text-[0.65rem] font-bold py-2 px-4 rounded-full border border-[#27272a] transition-all hover:bg-[#18181b]"
           >
             ✖️ 설정 도구 닫기
           </button>
        </div>

        <p className="text-[0.55rem] text-gray-600 text-center leading-relaxed mt-4 opacity-50">
          ※ 수동 매수/매도는 즉시 시장가 형태(매수/매도 1호가)로 집행됩니다.<br/>
          전략 정비 및 버전 관리는 [제어] 탭에서 가능합니다.
        </p>
      </div>
    </div>

  );
}
