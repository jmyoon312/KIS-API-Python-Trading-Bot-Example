import { useState } from 'react';
import axios from 'axios';
import ControlPanel from './ControlPanel';

export default function SniperCard({ ticker, ledgerData, configData, mode, onRefresh }: { ticker: string, ledgerData: any, configData: any, mode: 'mock' | 'real', onRefresh: () => Promise<void> }) {
  const [showPanel, setShowPanel] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const tVal = ledgerData?.t_val || 0;
  const split = ledgerData?.dynamic_split || configData?.dynamic_split || configData?.split || 40;
  const qty = ledgerData?.qty || 0;
  const avg = ledgerData?.avg_price || 0;
  
  const currP = ledgerData?.current_price || (avg ? avg * 1.0651 : 0); 
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
  const starOrder = ledgerData?.orders?.find((o: any) => (o.desc?.includes('별값') || o.desc?.includes('🌟')) && o.price !== undefined);
  const starPrice = starOrder ? starOrder.price : (avg > 0 ? avg * (1 + (targetPct/100) * 0.85) : 0);
  const starPct = avg > 0 ? ((starPrice - avg) / avg * 100).toFixed(2) : '0.00';

  // Sniper line calculations  
  const sniperDown = avg > 0 ? (avg * (1 - targetPct/100)).toFixed(2) : '0.00';
  const sniperDownPct = avg > 0 ? (-targetPct).toFixed(2) : '0.00';
  const quarterSniper = starPrice > 0 ? starPrice.toFixed(2) : '0.00';

  // Order grouping for display
  const orders = ledgerData?.orders || [];
  const coreOrders = orders.filter((o: any) => !o.desc?.includes('줍줍'));
  const bonusOrders = orders.filter((o: any) => o.desc?.includes('줍줍') && !o.desc?.includes('스마트'));
  const smartOrders = orders.filter((o: any) => o.desc?.includes('스마트'));

  // Color helpers
  const getOrderColor = (o: any) => {
    if (o.side === 'SELL') return o.desc?.includes('목표') ? 'text-purple-400' : 'text-blue-400';
    if (o.desc?.includes('가속')) return 'text-orange-400';
    if (o.desc?.includes('평단') || o.desc?.includes('⚓')) return 'text-red-400';
    if (o.desc?.includes('별값') || o.desc?.includes('💫')) return 'text-yellow-400';
    return 'text-red-400';
  };
  const getOrderDot = (o: any) => {
    if (o.side === 'SELL') return o.desc?.includes('목표') ? 'bg-purple-500' : 'bg-blue-500';
    if (o.desc?.includes('가속')) return 'bg-orange-500';
    if (o.desc?.includes('평단') || o.desc?.includes('⚓')) return 'bg-red-500';
    if (o.desc?.includes('별값') || o.desc?.includes('💫')) return 'bg-yellow-500';
    return 'bg-red-500';
  };

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
              onClick={() => setShowPanel(true)}
              className="bg-[#18181b] border border-[#3f3f46] hover:bg-[#3f3f46] hover:shadow-[0_0_15px_rgba(59,130,246,0.3)] flex items-center justify-center w-8 h-8 rounded-full transition-all active:scale-95"
              title="설정 및 제어 패널"
            >
              <span className="text-sm leading-none drop-shadow-md">⚙️</span>
            </button>
          </div>
          <div className="flex items-center gap-2 text-[0.65rem]">
            <span className={`font-bold px-2 py-0.5 rounded-md border ${
              processStatus.includes('전반전') ? 'bg-green-900/20 text-green-400 border-green-800/30' :
              processStatus.includes('후반전') ? 'bg-yellow-900/20 text-yellow-400 border-yellow-800/30' :
              processStatus.includes('방어') ? 'bg-orange-900/20 text-orange-400 border-orange-800/30' :
              processStatus.includes('폭락') || processStatus.includes('지옥') ? 'bg-red-900/20 text-red-400 border-red-800/30' :
              processStatus.includes('새출발') ? 'bg-cyan-900/20 text-cyan-400 border-cyan-800/30' :
              'bg-[#27272a] text-gray-400 border-[#3f3f46]'
            }`}>
              {processStatus}
            </span>
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

      {/* 스나이퍼/쿼터 방어선 */}
      <div className="bg-[#18181b] rounded-xl border border-[#27272a] p-4 mb-4">
        <h3 className="text-white font-bold text-sm mb-3 flex items-center gap-2">
          🎯 스나이퍼 방어선
          {turboMode === 'ON' && !ledgerData?.is_turbo_forced_off && <span className="text-red-400 text-[0.6rem] font-bold">🏎️가속 ON</span>}
          {turboMode === 'ON' && ledgerData?.is_turbo_forced_off && <span className="text-gray-500 text-[0.6rem] font-bold">🛡️안전차단</span>}
        </h3>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between items-center">
            <span className="text-gray-400">📉 스나이퍼({sniperDownPct}%)</span>
            <span className="text-blue-400 font-bold tabular-nums">${sniperDown} 이하 대기</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-gray-400">🦇 쿼터 스나이퍼</span>
            <span className="text-yellow-500 font-bold tabular-nums">${quarterSniper} 이상 대기</span>
          </div>
        </div>
      </div>

      {/* 📋 주문 계획 (Telegram 포맷 일치) */}
      <div className="bg-[#18181b] rounded-xl border border-[#27272a] p-4 mb-4">
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-white font-bold text-sm flex items-center gap-2">
            📋 주문 계획
            <span className="text-yellow-500 text-xs font-medium">[ {processStatus} ]</span>
          </h3>
          <span className="text-gray-600 text-[0.6rem] font-bold tracking-wider uppercase">{version}</span>
        </div>
        
        {/* Core Orders */}
        {coreOrders.length > 0 && (
          <div className="space-y-2 mb-3">
            {coreOrders.map((o: any, idx: number) => (
              <div key={idx} className="flex items-start gap-2.5">
                <div className={`w-2.5 h-2.5 rounded-full ${getOrderDot(o)} mt-1.5 flex-shrink-0 shadow-sm`}></div>
                <div className="flex-1 min-w-0">
                  <div className={`font-bold text-sm ${getOrderColor(o)}`}>
                    {o.desc}
                  </div>
                  <div className="text-gray-400 text-xs tabular-nums">
                    └ ${o.price?.toFixed(2) || '시장가'} x {o.qty}주
                    <span className="text-gray-600 ml-1.5">({o.type})</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Bonus Orders (줍줍) */}
        {bonusOrders.length > 0 && (
          <div className="border-t border-[#27272a] pt-2.5 mb-2">
            <div className="text-gray-500 text-[0.6rem] font-bold mb-2 tracking-wider uppercase">🧹 줍줍 ({bonusOrders.length}건)</div>
            <div className="text-gray-400 text-xs tabular-nums">
              {bonusOrders.length > 0 && (
                <span>
                  ${bonusOrders[bonusOrders.length - 1]?.price?.toFixed(2)} ~ ${bonusOrders[0]?.price?.toFixed(2)}
                  <span className="text-gray-600 ml-1.5">(LOC)</span>
                </span>
              )}
            </div>
            <div className="flex flex-wrap gap-1 mt-1.5">
              {bonusOrders.map((_: any, idx: number) => (
                <span key={idx} className="text-green-500 text-xs">✅</span>
              ))}
            </div>
          </div>
        )}

        {/* Smart Orders (V17 전용) */}
        {smartOrders.length > 0 && (
          <div className="border-t border-[#27272a] pt-2.5">
            <div className="text-gray-500 text-[0.6rem] font-bold mb-2 tracking-wider uppercase">🦇 스마트 방어 매수 (플랜 B 전환)</div>
            <div className="space-y-1">
              {smartOrders.map((o: any, idx: number) => (
                <div key={idx} className="flex items-center gap-2 text-xs">
                  <span className="text-green-500">✅</span>
                  <span className="text-gray-300">{o.desc} {o.qty}주</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {orders.length === 0 && (
          <div className="text-gray-500 text-sm py-3 text-center">진행 중인 주문 계획이 없습니다.</div>
        )}

        {/* Lock status */}
        {ledgerData?.is_locked && (
          <div className="mt-3 bg-green-900/10 border border-green-800/30 rounded-lg px-3 py-2 text-green-400 text-xs font-medium flex items-center gap-1.5">
            ✅ 금일 주문 완료/잠금
          </div>
        )}
      </div>

      {/* 거래 내역 (간략) */}
      <div className="bg-[#18181b] rounded-xl border border-[#27272a] p-4 text-sm">
        <div className="flex justify-between items-center mb-2">
          <h3 className="text-white font-bold text-sm">📒 거래 장부</h3>
          <span className="text-gray-600 text-[0.6rem]">LIVE 동기화</span>
        </div>
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

      {showPanel && (
        <ControlPanel 
          ticker={ticker}
          config={configData}
          seedVal={Number(seed)}
          mode={mode}
          onClose={() => setShowPanel(false)}
          onRefresh={() => {
            setTimeout(() => window.location.reload(), 800)
          }}
        />
      )}
    </div>
  )
}
