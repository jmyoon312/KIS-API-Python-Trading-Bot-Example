import { useState } from 'react';
import axios from 'axios';

interface ControlPanelProps {
  ticker: string;
  config: any;
  seedVal: number;
  mode: 'mock' | 'real'; // 🌐 [V23.1] 모드 명시화
  onClose: () => void;
  onRefresh: () => void;
}

export default function ControlPanel({ ticker, config, seedVal, mode, onClose, onRefresh }: ControlPanelProps) {
  const [seed, setSeed] = useState(seedVal || config.seed || 0);
  const [split, setSplit] = useState(config.split || 40);
  const [target, setTarget] = useState(config.target || 10);
  const [compound, setCompound] = useState(config.compound || 70);
  const [version, setVersion] = useState(config.version || "V14");
  const [force, setForce] = useState(false); // 🔥 [V23.1] 즉시 적용 (강제 모드)
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
        api.post('/settings/version', { ticker, value: version, mode }),
      ]);
      await api.get(`/refresh?mode=${mode}`); // 트리거 생성
      setTimeout(() => {
        onRefresh();
        onClose();
      }, 1000);
    } catch (e) {
      console.error(e);
      setLoading(false);
    }
  };

  const handleAction = async (actionPath: string) => {
    if (!window.confirm(`[${ticker}] 정말 실행하시겠습니까?`)) return;
    setLoading(true);
    try {
      await api.post(`/action/${actionPath}`, { ticker, mode });
      await api.get(`/refresh?mode=${mode}`);
      setTimeout(() => {
        onRefresh();
        onClose();
      }, 1500);
    } catch (e) {
      console.error(e);
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="bg-[#121214] border border-[#27272a] rounded-2xl w-full max-w-md overflow-hidden shadow-2xl relative">
        {/* Header */}
        <div className="p-4 border-b border-[#27272a] flex justify-between items-center bg-gradient-to-r from-gray-900 to-[#121214]">
          <h2 className="text-xl font-bold tracking-wider text-gray-100 flex items-center">
            <span className="text-blue-500 mr-2">⚙️</span> {ticker} <span className="text-xs text-gray-500 ml-2 font-light">QUANT SETTINGS</span>
          </h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">✕</button>
        </div>

        {/* Scrollable Body */}
        <div className="p-5 space-y-6 max-h-[70vh] overflow-y-auto">
          {/* Capital Control */}
          <div className="space-y-3">
            <div className="text-xs font-bold text-gray-500 uppercase tracking-widest border-b border-[#27272a] pb-1">Capital Control</div>
            <div className="flex justify-between items-center">
              <div className="flex flex-col">
                <label className="text-sm font-medium text-gray-300">운용 시드머니 ($)</label>
                <span className="text-[0.65rem] text-gray-500">
                  현재 현장 투입액: <span className="text-blue-400">${seedVal.toLocaleString()}</span>
                </span>
              </div>
              <input 
                type="number" 
                value={seed} 
                onChange={(e) => setSeed(Number(e.target.value))}
                className="bg-[#18181b] border border-[#27272a] rounded-lg px-3 py-1.5 text-right w-32 focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>
            
            <div className="flex items-center gap-2 mt-1">
              <input 
                type="checkbox" 
                id="forceApply" 
                checked={force} 
                onChange={(e) => setForce(e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 bg-[#18181b]"
              />
              <label htmlFor="forceApply" className="text-[0.7rem] text-gray-400 cursor-pointer hover:text-gray-200 transition-colors">
                ⚠️ <span className="underline decoration-dotted">즉시 적용 (강제)</span> - 매매 진행 중이라도 시드를 즉각 변경합니다.
              </label>
            </div>
            {!force && (
              <p className="text-[0.6rem] text-blue-500/70 ml-6 italic">
                * 체크 해제 시, 현재 보유 중인 수량이 0원(졸업)이 된 시점부터 새로운 시드가 적용됩니다.
              </p>
            )}
          </div>

          {/* Algo Settings */}
          <div className="space-y-4">
            <div className="text-xs font-bold text-gray-500 uppercase tracking-widest border-b border-[#27272a] pb-1">Algorithm Parameters</div>
            
            <div className="flex justify-between items-center">
              <label className="text-sm font-medium text-gray-300 flex items-center gap-1">⏱️ 분할 횟수</label>
              <div className="flex items-center gap-2">
                <input type="range" min="10" max="100" step="10" value={split} onChange={(e) => setSplit(Number(e.target.value))} className="w-24 accent-blue-500" />
                <span className="text-sm w-10 text-right">{split}회</span>
              </div>
            </div>

            <div className="flex justify-between items-center">
              <label className="text-sm font-medium text-gray-300 flex items-center gap-1">🎯 목표 수익률</label>
              <div className="flex items-center gap-2">
                <input type="range" min="5" max="30" step="1" value={target} onChange={(e) => setTarget(Number(e.target.value))} className="w-24 accent-green-500" />
                <span className="text-sm w-10 text-right">{target}%</span>
              </div>
            </div>

            <div className="flex justify-between items-center">
              <label className="text-sm font-medium text-gray-300 flex items-center gap-1">💸 자동복리율</label>
              <div className="flex items-center gap-2">
                <input type="range" min="0" max="100" step="10" value={compound} onChange={(e) => setCompound(Number(e.target.value))} className="w-24 accent-indigo-500" />
                <span className="text-sm w-10 text-right">{compound}%</span>
              </div>
            </div>

            <div className="flex flex-col gap-2 pt-2 pb-2">
              <label className="text-sm font-medium text-gray-300">엔진 버전</label>
              <div className="grid grid-cols-1 gap-2">
                <label className={`cursor-pointer flex flex-col p-3 rounded-xl border transition-colors ${version === 'V13' ? 'border-blue-500 bg-blue-500/10' : 'border-[#27272a] bg-[#18181b] hover:border-[#3f3f46]'}`}>
                  <div className="flex items-center gap-2">
                    <input type="radio" name="version" value="V13" checked={version === 'V13'} onChange={(e) => setVersion(e.target.value)} className="hidden" />
                    <span className="font-bold text-white text-sm">💎 무한매수법 V22 (V13)</span>
                  </div>
                  <span className="text-[0.65rem] text-gray-400 mt-1">100% 동적분할 시스템 적용. 보수적이고 안정적인 스윙 트레이딩.</span>
                </label>
                <label className={`cursor-pointer flex flex-col p-3 rounded-xl border transition-colors ${version === 'V14' ? 'border-blue-500 bg-blue-500/10' : 'border-[#27272a] bg-[#18181b] hover:border-[#3f3f46]'}`}>
                  <div className="flex items-center gap-2">
                    <input type="radio" name="version" value="V14" checked={version === 'V14'} onChange={(e) => setVersion(e.target.value)} className="hidden" />
                    <span className="font-bold text-white text-sm">💎 무한매수법 V22.2 (V14)</span>
                  </div>
                  <span className="text-[0.65rem] text-gray-400 mt-1">최신 융합 알고리즘. 하락장 방어력과 상승장 추세추종의 시너지 극대화.</span>
                </label>
                <label className={`cursor-pointer flex flex-col p-3 rounded-xl border transition-colors ${version === 'V17' ? 'border-purple-500 bg-purple-500/10' : 'border-[#27272a] bg-[#18181b] hover:border-[#3f3f46]'}`}>
                  <div className="flex items-center gap-2">
                    <input type="radio" name="version" value="V17" checked={version === 'V17'} onChange={(e) => setVersion(e.target.value)} className="hidden" />
                    <span className="font-bold text-white text-sm">🦇 시크릿 스나이퍼 (V17)</span>
                  </div>
                  <span className="text-[0.65rem] text-purple-400/80 mt-1">극단적 하방 변동성에서만 발동되는 야수 전용 공격형 매집.</span>
                </label>
              </div>
            </div>
            
            <button 
              onClick={handleSaveSettings} 
              disabled={loading}
              className="w-full mt-2 py-2.5 bg-[#27272a] hover:bg-[#3f3f46] active:scale-95 transition-all rounded-xl text-sm font-bold shadow-md border border-[#3f3f46]/50 disabled:opacity-50"
            >
              {loading ? '저장 중...' : '💾 설정 저장 및 적용'}
            </button>
          </div>

          {/* Command Protocol (IPC Action) */}
          <div className="space-y-3 pt-4 border-t border-[#27272a]">
            <div className="text-xs font-bold text-red-500/80 uppercase tracking-widest border-b border-red-900/30 pb-1 mb-2">Command Protocol (Danger)</div>
            
            <div className="grid grid-cols-2 gap-3">
              <button 
                onClick={() => handleAction('record')}
                disabled={loading}
                className="flex flex-col items-center justify-center p-3 rounded-xl border border-blue-900/50 bg-blue-500/10 hover:bg-blue-500/20 active:scale-95 transition-all group"
              >
                <span className="text-xl mb-1 group-hover:scale-110 transition-transform">🔄</span>
                <span className="text-[0.65rem] text-blue-300 font-bold tracking-tight text-center">증권사 실시간<br/>잔고 동기화 (복구)</span>
              </button>

              <button 
                onClick={() => handleAction('reset')}
                disabled={loading}
                className="flex flex-col items-center justify-center p-3 rounded-xl border border-orange-900/50 bg-orange-500/10 hover:bg-orange-500/20 active:scale-95 transition-all group"
              >
                <span className="text-xl mb-1 group-hover:scale-110 transition-transform">🔓</span>
                <span className="text-[0.65rem] text-orange-300 font-bold tracking-tight text-center">엔진 잠금 해제<br/>(에스크로 초기화)</span>
              </button>
            </div>
            
            <button 
              onClick={() => handleAction('exec')}
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 p-3 mt-2 rounded-xl border border-red-500/50 bg-red-900/20 hover:bg-red-900/40 hover:shadow-[0_0_15px_rgba(239,68,68,0.3)] active:scale-95 transition-all group"
            >
              <span className="text-xl group-hover:-translate-y-1 transition-transform">🔥</span>
              <span className="text-sm font-bold text-red-400">알고리즘 수동 실행 (즉시 강제 체결)</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
