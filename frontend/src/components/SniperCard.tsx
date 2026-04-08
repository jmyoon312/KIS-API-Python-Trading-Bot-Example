import { useState } from 'react';
import axios from 'axios';
import ControlPanel from './ControlPanel';

export default function SniperCard({ ticker, ledgerData, configData, mode, tactics, syncStatus, onRefresh }: { ticker: string, ledgerData: any, configData: any, mode: 'mock' | 'real', tactics: any, syncStatus?: any, onRefresh: () => Promise<void> }) {
  const [showPanel, setShowPanel] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const tVal = ledgerData?.t_val || 0;
  const split = ledgerData?.dynamic_split || configData?.dynamic_split || configData?.split || 40;
  const qty = ledgerData?.qty || 0;
  const avg = ledgerData?.avg_price || 0;
  
  const currP = (ledgerData?.current_price && ledgerData.current_price > 0) ? ledgerData.current_price : (avg > 0 ? avg : 0); 
  const profitAmt = ledgerData?.profit_amt || ((currP - avg) * qty);
  const returnPct = avg > 0 ? ((currP - avg) / avg * 100).toFixed(2) : '0.00';
  const isPositive = parseFloat(returnPct) >= 0;
  
  const seed = configData?.seed || ledgerData?.seed || 0;
  const used = avg * qty;
  const onePortion = seed > 0 && split > 0 ? (seed / split) : 0;
  const progressPct = seed > 0 ? ((used / seed) * 100).toFixed(1) : '0.0';
  const targetPct = configData?.target_pct || ledgerData?.target || 12.0;
  const version = configData?.version || ledgerData?.version || 'V22';
  const processStatus = ledgerData?.process_status || '대기';
  const turboMode = ledgerData?.turbo_mode || 'OFF';
  const dayHigh = ledgerData?.day_high || 0;
  const dayLow = ledgerData?.day_low || 0;

  // Star price extraction from orders
  const starOrder = ledgerData?.orders?.find((o: any) => (o.desc?.includes('별값') || o.desc?.includes('🌟') || o.desc?.includes('익절') || o.desc?.includes('보조')) && o.price !== undefined);
  const starPrice = starOrder ? starOrder.price : (avg > 0 ? avg * (1 + (targetPct/100) * 0.85) : 0);
  const starPct = avg > 0 ? ((starPrice - avg) / avg * 100).toFixed(2) : '0.00';

  // Sniper line calculations  
  const sniperDown = avg > 0 ? (avg * (1 - targetPct/100)).toFixed(2) : '0.00';
  const quarterSniper = starPrice > 0 ? starPrice.toFixed(2) : '0.00';


  return (
    <div className="bg-[#121214] rounded-2xl border border-[#27272a] p-5 mb-4">
      {/* 상단 통합 헤더 */}
      <div className="flex justify-between items-start mb-5">
        <div className="flex flex-col gap-2.5">
          <div className="flex items-center gap-2">
            <h2 className="text-3xl font-black text-white leading-none tracking-tight">{ticker}</h2>
            <span className="bg-[#27272a] text-gray-300 text-[0.6rem] font-bold px-2 py-0.5 rounded-md border border-[#3f3f46] shadow-sm uppercase tracking-wider">
              {version}
            </span>
            {turboMode === 'ON' && !ledgerData?.is_turbo_forced_off && (
              <span className="bg-red-900/30 text-red-400 text-[0.55rem] font-bold px-1.5 py-0.5 rounded border border-red-800/30 animate-pulse">🏎️가속</span>
            )}
            {turboMode === 'ON' && ledgerData?.is_turbo_forced_off && (
              <span className="bg-[#27272a] text-gray-500 text-[0.55rem] font-bold px-1.5 py-0.5 rounded border border-[#3f3f46] flex items-center gap-1" title={ledgerData?.turbo_off_reason}>
                🛡️ 안전차단
              </span>
            )}
            <button 
              onClick={() => setShowPanel(!showPanel)}
              className={`bg-[#18181b] border border-[#3f3f46] hover:bg-[#3f3f46] hover:shadow-[0_0_15px_rgba(59,130,246,0.3)] flex items-center justify-center w-8 h-8 rounded-full transition-all active:scale-95 ${showPanel ? 'ring-2 ring-blue-500' : ''}`}
              title="설정 및 제어 패널"
            >
              <span className="text-sm leading-none drop-shadow-md">⚙️</span>
            </button>
          </div>
          <div className="flex items-center gap-2 text-[0.65rem]">
            <span className={`font-bold px-2 py-0.5 rounded-md border ${
              processStatus.includes('Shadow-Strike') ? 'bg-indigo-900/30 text-indigo-400 border-indigo-500/40 animate-pulse' :
              processStatus.includes('Shadow-Crisis') ? 'bg-rose-900/30 text-rose-400 border-rose-500/40 animate-bounce' :
              processStatus.includes('전반전') ? 'bg-green-900/20 text-green-400 border-green-800/30' :
              processStatus.includes('후반전') ? 'bg-yellow-900/20 text-yellow-400 border-yellow-800/30' :
              processStatus.includes('방어') ? 'bg-orange-900/20 text-orange-400 border-orange-800/30' :
              processStatus.includes('폭락') || processStatus.includes('지옥') ? 'bg-red-900/20 text-red-400 border-red-800/30' :
              processStatus.includes('새출발') ? 'bg-cyan-900/20 text-cyan-400 border-cyan-800/30' :
              'bg-[#27272a] text-gray-400 border-[#3f3f46]'
            }`}>
              {processStatus}
            </span>
            
            {/* 🏹 [V25] 글로벌 전술 활성 배지 (Tactical Status Badges) - 한글화 적용 */}
            <div className="flex flex-wrap gap-1">
              {tactics?.shield && <span className="bg-blue-600/20 text-blue-400 text-[0.45rem] px-1 py-0.5 rounded border border-blue-500/30 font-bold uppercase tracking-tighter">쉴드</span>}
              {tactics?.shadow && <span className="bg-purple-600/20 text-purple-400 text-[0.45rem] px-1 py-0.5 rounded border border-purple-500/30 font-bold uppercase tracking-tighter">새도우</span>}
              {tactics?.turbo && <span className="bg-red-600/20 text-red-400 text-[0.45rem] px-1 py-0.5 rounded border border-red-500/30 font-bold uppercase tracking-tighter">터보</span>}
              {tactics?.sniper && <span className="bg-green-600/20 text-green-400 text-[0.45rem] px-1 py-0.5 rounded border border-green-500/30 font-bold uppercase tracking-tighter">스나이퍼</span>}
              {tactics?.jupjup && <span className="bg-yellow-600/20 text-yellow-400 text-[0.45rem] px-1 py-0.5 rounded border border-yellow-500/30 font-bold uppercase tracking-tighter">줍줍</span>}
            </div>
          </div>
        </div>
        <div className="text-right whitespace-nowrap pl-3 flex-shrink-0">
          <div className="text-gray-500 text-[0.6rem] font-bold tracking-widest uppercase mb-0.5">진행도</div>
          <div className="text-white text-2xl font-black tabular-nums">{progressPct}%</div>
          <div className="text-gray-500 text-[0.65rem] mt-0.5 font-medium tabular-nums">{tVal.toFixed(2)}T / {split}</div>
        </div>
      </div>

      {/* 현재가/수익률 */}
      <div className="flex justify-between items-baseline mb-4 pb-4 border-b border-[#27272a]">
        <div>
          <div className={`text-3xl font-black tabular-nums ${isPositive ? 'text-red-500' : 'text-blue-500'}`}>
            ${currP.toFixed(2)}
          </div>
          <div className={`text-sm font-bold tabular-nums ${isPositive ? 'text-red-500' : 'text-blue-500'}`}>
            {isPositive ? '+' : ''}{returnPct}% ({isPositive ? '+' : ''}${profitAmt.toFixed(2)})
          </div>
        </div>
        <div className="text-right text-xs space-y-1">
          {dayHigh > 0 && (
            <div className="text-gray-400">고가 <span className="text-white font-bold tabular-nums">${dayHigh.toFixed(2)}</span></div>
          )}
          {dayLow > 0 && (
            <div className="text-gray-400">저가 <span className="text-white font-bold tabular-nums">${dayLow.toFixed(2)}</span></div>
          )}
        </div>
      </div>

      {/* ⚙️ [V26.6] 설정창 위치 이동 (가격 바로 아래) */}
      {showPanel && (
        <ControlPanel 
          ticker={ticker}
          config={configData}
          seedVal={Number(seed)}
          holdings={Number(qty)}
          mode={mode}
          onClose={() => setShowPanel(false)}
          onRefresh={() => {
            setTimeout(() => onRefresh(), 800)
          }}
        />
      )}

      {/* 핵심 데이터 그리드 */}
      <div className="bg-[#18181b] rounded-xl border border-[#27272a] p-4 mb-4">
        <div className="grid grid-cols-3 gap-3 text-sm mb-3 pb-3 border-b border-[#27272a]">
          <div>
            <div className="text-gray-500 mb-1 text-[0.65rem] flex items-center gap-1">
              💰 총 시드
              {ledgerData?.reserved_seed !== undefined && ledgerData.reserved_seed !== seed && (
                <span className="text-[0.5rem] bg-orange-500/10 text-orange-400 border border-orange-500/20 px-1 rounded animate-pulse" title="Next Cycle Reserved">
                  NEXT: ${ledgerData.reserved_seed.toLocaleString()}
                </span>
              )}
            </div>
            <div className="text-white font-bold tabular-nums">${seed.toLocaleString()}</div>
          </div>
          <div>
            <div className="text-gray-500 mb-1 text-[0.65rem]">📦 오늘 예산</div>
            <div className="text-white font-bold tabular-nums">${onePortion.toFixed(0)}</div>
          </div>
          <div>
            <div className="text-gray-500 mb-1 text-[0.65rem]">🏦 매입 금액</div>
            <div className="text-white font-bold tabular-nums">${used.toLocaleString(undefined, {maximumFractionDigits:0})}</div>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 text-sm">
          <div>
            <div className="text-gray-500 mb-1 text-[0.65rem]">💲 평단 / {qty}주</div>
            <div className="text-white font-bold tabular-nums">${avg.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-gray-500 mb-1 text-[0.65rem]">🎯 목표 수익률</div>
            <div className="text-white font-bold tabular-nums">{targetPct.toFixed(1)}%</div>
          </div>
          <div>
            <div className="text-gray-500 mb-1 text-[0.65rem]">⭐ 별값%</div>
            <div className="text-yellow-500 font-bold tabular-nums">{starPct}%</div>
          </div>
        </div>
      </div>

      {/* 🎯 전술별 조건부 정보 노출 (Tactical Context UI) */}
      
      {/* 1. 스나이퍼 방어선 (Sniper Tactic Only) */}
      {tactics?.sniper && (
        <div className="bg-[#18181b] rounded-xl border border-[#27272a] p-4 mb-4">
          <div className="flex justify-between items-center mb-2">
            <h3 className="text-white font-bold text-sm flex items-center gap-2">
              🎯 스나이퍼 방어선
              {turboMode === 'ON' && !ledgerData?.is_turbo_forced_off && <span className="text-red-400 text-[0.6rem] font-bold">🏎️가속 ON</span>}
            </h3>
            <span className="text-blue-400 font-black text-xs">{(configData?.sniper_drop || 1.5).toFixed(1)}%</span>
          </div>
          
          <div className="mb-4">
            <input 
              type="range" 
              min="0.5" 
              max="5.0" 
              step="0.1" 
              value={configData?.sniper_drop || 1.5} 
              onChange={async (e) => {
                const val = parseFloat(e.target.value);
                await axios.post('/api/settings/global-strategy', { mode, key: 'sniper_drop', value: val });
                onRefresh();
              }}
              className="w-full accent-blue-500 h-1.5 bg-[#27272a] rounded-lg appearance-none cursor-pointer mb-2" 
            />
            <p className="text-[0.6rem] text-gray-500">수익권에서 고점 대비 설정값 하락 시 즉시 1/4 익절 격발</p>
          </div>

          <div className="space-y-2 text-sm border-t border-white/5 pt-3">
            <div className="flex justify-between items-center">
              <span className="text-gray-400">📉 수익방어 격발선</span>
              <span className="text-blue-400 font-bold tabular-nums">${sniperDown} 이하</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">🦇 쿼터 스나이퍼</span>
              <span className="text-yellow-500 font-bold tabular-nums">${quarterSniper} 이상</span>
            </div>
          </div>
        </div>
      )}

      {/* 2. 새도우 스트라이크 반등 비율 조절 (Shadow Tactic OR V24 Hybrid) */}
      {(tactics?.shadow || version === 'V24') && (
        <div className="bg-[#18181b] rounded-xl border border-[#27272a] p-4 mb-4 animate-fade-in">
          <div className="flex justify-between items-center mb-2">
            <h3 className="text-white font-bold text-sm flex items-center gap-2">
              🌓 새도우 반등 조절 <span className="text-[0.6rem] text-purple-400 font-normal underline decoration-dotted">GLOBAL</span>
            </h3>
            <span className="text-purple-400 font-black text-xs">
              {(configData?.shadow_bounce || 1.5).toFixed(1)}%
            </span>
          </div>
          <div className="flex items-center gap-3">
            <input 
              type="range" 
              min="0.5" 
              max="5.0" 
              step="0.1" 
              value={configData?.shadow_bounce || 1.5} 
              onChange={async (e) => {
                const val = parseFloat(e.target.value);
                await axios.post('/api/settings/global-strategy', { mode, key: 'shadow_bounce', value: val });
                onRefresh();
              }}
              className="flex-1 accent-purple-500 h-1.5 bg-[#27272a] rounded-lg appearance-none cursor-pointer" 
            />
            <p className="text-[0.6rem] text-gray-500 leading-tight w-24">최저가 대비 반등 시<br/>실시간 정밀 매수</p>
          </div>
        </div>
      )}

      {/* 3. 터보 부스터 상세 (Turbo Tactic Only) */}
      {tactics?.turbo && turboMode === 'ON' && (
        <div className="bg-red-900/5 rounded-xl border border-red-500/20 p-4 mb-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-2">
              <span className="text-red-400 text-xs font-black animate-pulse">🏎️ 터보 부스터 가동 중</span>
              <span className="text-[0.6rem] text-gray-500">배수: {ledgerData?.turbo_multiplier || 1.0}x</span>
            </div>
            <span className="text-red-500/70 text-[0.6rem] font-bold">급락장 하락 방어</span>
          </div>
        </div>
      )}

      {/* 4. 줍줍 거미줄 현황 (JupJup Tactic Only) */}
      {tactics?.jupjup && (
        <div className="bg-yellow-900/5 rounded-xl border border-yellow-500/20 p-4 mb-4">
          <div className="flex justify-between items-center mb-2">
            <h3 className="text-white font-bold text-sm flex items-center gap-2">
              🧹 줍줍 거미줄 현황
            </h3>
            <span className="text-yellow-500 font-black text-xs">
              {(configData?.jupjup_density || 10)}개 감시 중
            </span>
          </div>

          <div className="mb-4">
            <input 
              type="range" 
              min="1" 
              max="20" 
              step="1" 
              value={configData?.jupjup_density || 10} 
              onChange={async (e) => {
                const val = parseInt(e.target.value);
                await axios.post('/api/settings/global-strategy', { mode, key: 'jupjup_density', value: val });
                onRefresh();
              }}
              className="w-full accent-yellow-500 h-1.5 bg-[#27272a] rounded-lg appearance-none cursor-pointer mb-2" 
            />
            <div className="flex justify-between text-[0.6rem] text-gray-500">
              <span>밀도 낮음</span>
              <span>밀도 높음 (20개)</span>
            </div>
          </div>

          <div className="flex items-center gap-2 border-t border-yellow-500/10 pt-3">
            <div className="flex-1 h-1.5 bg-[#27272a] rounded-full overflow-hidden">
               <div 
                className="h-full bg-yellow-500 transition-all duration-1000" 
                style={{ width: `${Math.min(100, ((configData?.jupjup_density || 10) / 20) * 100)}%` }}
               ></div>
            </div>
            <span className="text-[0.6rem] text-gray-500 font-bold">밀도: { (configData?.jupjup_density || 10) > 15 ? 'High' : ((configData?.jupjup_density || 10) > 7 ? 'Mid' : 'Low')}</span>
          </div>
        </div>
      )}

      {/* 5. V-REV 리버스 순환 모드 (Reverse Mode Only) */}
      {tactics?.is_reverse && (
        <div className="bg-purple-900/10 rounded-xl border border-purple-500/30 p-4 mb-4 animate-pulse">
          <div className="flex justify-between items-center mb-3">
            <h3 className="text-white font-bold text-sm flex items-center gap-2">
              🔄 V-REV 리버스 가동 중
            </h3>
            <div className="flex items-center gap-2 bg-[#1c1c1f] rounded-lg p-1 border border-[#27272a]">
              <button 
                onClick={async () => {
                  const current = tactics?.rev_day || 0;
                  const newVal = Math.max(0, current - 1);
                  await axios.post('/api/settings/global-strategy', { mode, key: 'rev_day', value: newVal });
                  onRefresh();
                }}
                className="w-6 h-6 flex items-center justify-center text-gray-400 hover:text-white hover:bg-[#27272a] rounded transition-colors"
              >-</button>
              <span className="text-purple-400 font-bold text-xs w-12 text-center">
                {tactics?.rev_day || 0}일차
              </span>
              <button 
                onClick={async () => {
                  const current = tactics?.rev_day || 0;
                  const newVal = current + 1;
                  await axios.post('/api/settings/global-strategy', { mode, key: 'rev_day', value: newVal });
                  onRefresh();
                }}
                className="w-6 h-6 flex items-center justify-center text-gray-400 hover:text-white hover:bg-[#27272a] rounded transition-colors"
              >+</button>
            </div>
          </div>
          <p className="text-[0.65rem] text-purple-300 leading-relaxed opacity-80 mb-2">
            현재 평단가 부근에서 물량을 털어내며 순환 매수/매도를 반복하는 탈출 모드입니다. 
            (매일 { (tactics?.rev_day || 0) === 1 ? '시장가 매도' : '별값 매칭 매매' } 진행)
          </p>
          <div className="grid grid-cols-2 gap-2 mt-3">
            <div className={`text-[0.6rem] p-1.5 rounded border ${tactics?.vix_aware ? 'bg-blue-500/10 border-blue-500/30 text-blue-300' : 'bg-gray-800/10 border-gray-700/30 text-gray-500'}`}>
               ⚡ VIX-Aware: {tactics?.vix_aware ? 'ON' : 'OFF'}
            </div>
            <div className={`text-[0.6rem] p-1.5 rounded border ${tactics?.vwap_dominance ? 'bg-orange-500/10 border-orange-500/30 text-orange-300' : 'bg-gray-800/10 border-gray-700/30 text-gray-500'}`}>
               📊 VWAP-Eng: {tactics?.vwap_dominance ? 'ON' : 'OFF'}
            </div>
          </div>
        </div>
      )}

      {/* 📋 주문 계획 (Planned Orders) */}
      <div className="bg-[#18181b] rounded-xl border border-[#27272a] p-4 mb-4">
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-white font-bold text-sm flex items-center gap-2">
            📋 주문 계획
            <span className="text-yellow-500 text-xs font-medium">[ {processStatus} ]</span>
          </h3>
          <span className="text-gray-600 text-[0.6rem] font-bold tracking-wider uppercase">{version}</span>
        </div>
        
        <div className="space-y-4 mb-3">
          {[1, 2, 3, 4, 5].map((num) => {
            const sid = `slot_${num}`;
            const slot = ledgerData?.slots?.[sid];
            
            // 데이터가 없는 초기 상태 대응
            if (!slot) return (
              <div key={sid} className="flex items-center gap-2.5 opacity-20">
                <div className="w-2.5 h-2.5 rounded-full bg-gray-600 mt-1 flex-shrink-0"></div>
                <div className="text-gray-500 text-xs font-bold italic">Slot {num} Initializing...</div>
              </div>
            );

            const isFilled = slot.status === 'FILLED';
            const isActive = slot.qty > 0 || isFilled;
            
            // BUY/SELL 색상 구분
            const isSell = slot.side === 'SELL';
            let dotColor = 'bg-red-500';
            let textColor = 'text-red-400';
            
            if (isFilled) {
              dotColor = 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]';
              textColor = 'text-green-400';
            } else if (isSell) {
              const isGoal = slot.desc?.includes('목표') || slot.desc?.includes('전량');
              dotColor = isGoal ? 'bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.4)]' : 'bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.4)]';
              textColor = isGoal ? 'text-purple-400' : 'text-blue-400';
            } else {
              dotColor = 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.3)]';
              textColor = 'text-red-400';
            }

            return (
              <div key={sid} className={`flex items-start gap-2.5 transition-all duration-500 ${isFilled ? 'bg-green-500/5 -mx-2 px-2 py-1 rounded-lg border border-green-500/20' : ''} ${!isActive ? 'opacity-30 grayscale-[0.5]' : ''}`}>
                <div className={`w-2.5 h-2.5 rounded-full ${dotColor} mt-1.5 flex-shrink-0`}></div>
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between items-center mb-0.5">
                    <div className={`font-bold text-sm ${textColor} flex items-center gap-1.5`}>
                      {slot.desc}
                      {isFilled && <span className="text-[10px] font-black bg-green-500 text-black px-1 rounded animate-bounce">DONE</span>}
                      {slot.result && <span className="text-[10px] opacity-60 font-medium whitespace-nowrap">({slot.result})</span>}
                    </div>
                  </div>
                  <div className="text-gray-400 text-xs tabular-nums">
                    └ ${slot.price?.toFixed(2) || '0.00'} x {slot.qty}주
                    <span className="text-gray-600 ml-1.5 opacity-50">({slot.type || 'LOC'})</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ✅ 당일 매매 완료 (Execution History) */}
      <div className="bg-green-500/5 rounded-xl border border-green-500/10 p-4 mb-4 border-dashed animate-fade-in outline outline-1 outline-green-500/10">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-green-500 font-bold text-[0.7rem] flex items-center gap-2">
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
            </span>
            당일 매매 완료 내역
          </h3>
          <span className="text-[0.55rem] text-green-700/80 font-black uppercase tracking-[0.2em]">EXECUTION SUCCESS</span>
        </div>

        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((num) => {
            const sid = `slot_${num}`;
            const slot = ledgerData?.slots?.[sid];
            if (!slot || slot.status !== 'FILLED') return null;

            return (
              <div key={sid} className="flex items-start gap-2.5 bg-green-500/5 -mx-1 px-2 py-2 rounded-lg border border-green-500/20 transition-all duration-700 shadow-sm">
                <div className="w-2.5 h-2.5 rounded-full bg-green-500 shadow-[0_0_10px_rgba(34,197,94,0.4)] mt-1.5 flex-shrink-0"></div>
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between items-center mb-0.5">
                    <div className="font-bold text-sm text-green-400 flex items-center gap-1.5">
                      {slot.desc}
                      <span className="text-[0.55rem] font-bold text-green-600/60 opacity-80">(Slot {num})</span>
                    </div>
                  </div>
                  <div className="text-green-700/70 text-xs tabular-nums flex justify-between items-center">
                    <span>└ <span className="text-green-500 font-bold">${slot.price?.toFixed(2)}</span> 단가로 <span className="text-green-500 font-bold">{slot.qty}주</span> 체결 완료</span>
                    <span className="text-[0.55rem] font-black bg-green-500/10 px-1 rounded border border-green-500/20 italic">DONE</span>
                  </div>
                </div>
              </div>
            );
          })}
          
          {(!ledgerData?.slots || Object.values(ledgerData.slots).every((s: any) => s.status !== 'FILLED')) && (
            <div className="text-gray-700/50 text-[0.6rem] py-4 text-center border border-dashed border-gray-800/20 rounded-lg italic">
              현재 체결된 내역이 없습니다. (실시간 감시 중)
            </div>
          )}
        </div>
      </div>

      {/* 거래 내역 (간략) */}
      <div className="bg-[#18181b] rounded-xl border border-[#27272a] p-4 text-sm">
        <div className="flex justify-between items-center mb-2">
          <h3 className="text-white font-bold text-sm">📒 거래 장부</h3>
          <span className="text-gray-600 text-[0.6rem]">LIVE 동기화</span>
        </div>
        
        {/* 🔄 [V24.5] 수동 동기화 진행 상태 표시 (완료 시 5초간 노출) */}
        {syncStatus && (
          (syncStatus.status === 'PROCESSING' && (Date.now() / 1000 - syncStatus.timestamp < 60)) ||
          ((syncStatus.status === 'SUCCESS' || syncStatus.status === 'ERROR') && (Date.now() / 1000 - syncStatus.timestamp < 5))
        ) && (
          <div className={`mb-2 px-3 py-2 rounded-xl border flex items-center gap-2.5 transition-all shadow-sm ${
            syncStatus.status === 'PROCESSING' 
            ? 'bg-blue-600/10 border-blue-500/30 text-blue-400 animate-pulse' 
            : (syncStatus.status === 'ERROR' 
               ? 'bg-red-600/10 border-red-500/30 text-red-500' 
               : 'bg-emerald-600/10 border-emerald-500/30 text-emerald-400 border-dashed')
          }`}>
            {syncStatus.status === 'PROCESSING' ? (
              <div className="w-2.5 h-2.5 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
            ) : (
              <span className="text-[10px]">{syncStatus.status === 'ERROR' ? '❌' : '⚡'}</span>
            )}
            <span className="text-[0.65rem] font-black tracking-tight">{syncStatus.msg}</span>
          </div>
        )}

        <button 
          onClick={async () => {
            if (refreshing) return;
            setRefreshing(true);
            try {
              // 1. 증권사 잔고와 현재 장부 강제 동기화 (기록 보정)
              await axios.post('/api/action/record', { ticker, mode });
              // 2. 백엔드 캐시 갱신 트리거
              await axios.get(`/api/refresh?mode=${mode}`);
              // 3. UI 데이터 재호출 (Dashboard에서 전달받은 함수)
              await onRefresh();
            } catch (e) {
              console.error("수동 갱신 실패:", e);
              alert("동기화 중 오류가 발생했습니다.");
            } finally {
              setRefreshing(false);
            }
          }}
          disabled={refreshing}
          className={`w-full bg-[#121214] text-gray-400 border border-[#27272a] py-2.5 rounded-lg flex justify-center items-center hover:bg-[#1a1a1e] hover:text-white transition-colors text-xs font-bold ${refreshing ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          {refreshing ? (
            <>
              <div className="w-3 h-3 border-2 border-gray-400 border-t-transparent rounded-full animate-spin mr-2"></div>
              장부 무결성 검증 중...
            </>
          ) : (
            '🔄 최신 데이터 수동 갱신'
          )}
        </button>
      </div>

    </div>
  )
}
