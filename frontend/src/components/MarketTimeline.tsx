import { useEffect, useState } from 'react'
import axios from 'axios'

interface MarketTimelineProps {
  marketStatus: string   // e.g. "🔥 정규장", "🌅 프리마켓", "⛔ 장마감"
  dstInfo: string        // e.g. "🌞 서머타임(17:30)", "❄️ 겨울(18:30)"
  isSummer?: boolean     // 🆕 신규: 명시적 서머타임 플래그 (V24+ 대응)
  isTradeActive: boolean
  isReal?: boolean       // [V22.2] 실전투자 여부
  taskStatus: Record<string, { status: string, time: string }>
}

// ET 계산 도우미 (KST 기준)
function getET(kstTime: string, isSummer: boolean): string {
  const [h, m] = kstTime.split(':').map(Number)
  let eth = h - (isSummer ? 13 : 14)
  if (eth < 0) eth += 24
  return `${String(eth).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

const SCHEDULE_SUMMER = [
  { time: '08:30', label: '🔄 동기화', desc: '증권사 잔고 대조', phase: 'sync' },
  { time: '17:00', label: '🌅 프리마켓', desc: '가격 모니터링 시작', phase: 'pre' },
  { time: '22:30', label: '🔥 정규장', desc: 'LOC 및 스나이퍼 가동', phase: 'reg' },
  { time: '05:00', label: '🌙 애프터마켓', desc: '잔여 물량 관리', phase: 'after' },
  { time: '06:00', label: '🧹 정리', desc: '로그 및 장부 청소', phase: 'idle' },
]

const SCHEDULE_WINTER = [
  { time: '09:30', label: '🔄 동기화', desc: '증권사 잔고 대조', phase: 'sync' },
  { time: '18:00', label: '🌅 프리마켓', desc: '가격 모니터링 시작', phase: 'pre' },
  { time: '23:30', label: '🔥 정규장', desc: 'LOC 및 스나이퍼 가동', phase: 'reg' },
  { time: '06:00', label: '🌙 애프터마켓', desc: '잔여 물량 관리', phase: 'after' },
  { time: '07:00', label: '🧹 정리', desc: '로그 및 장부 청소', phase: 'idle' },
]

function getCurrentPhase(_marketStatus: string, now: Date, isSummer: boolean): string {
  // 🚀 [V26.5 Fix] 강조 원칙: 'OPEN' 문자열에 의존하지 않고 실제 KST 시간표에 따라 하이라이트를 이동시킵니다.
  // 미국 휴장일(WEEKEND, HOLIDAY)인 경우에도 엔진은 동기화(Sync)나 정리(Idle) 작업을 수행할 수 있으므로 시간 기반으로 표시합니다.

  const tot = now.getHours() * 60 + now.getMinutes()
  
  // 스케줄 설정 (KST 기준 분 단위 계산)
  const S = {
    sync: isSummer ? (8*60+30) : (9*60+30),
    pre: isSummer ? (17*60) : (18*60),
    reg: isSummer ? (22*60+30) : (23*60+30),
    after: isSummer ? (5*60) : (6*60),
    idle: isSummer ? (6*60) : (7*60)
  }

  // 🚀 [V26.5] 시간 기반 자동 하이라이트 알고리즘 (UTC/EST 관계없이 KST 직관성 유지)
  if (isSummer) {
    if (tot >= S.sync && tot < S.pre) return 'sync'
    if (tot >= S.pre && tot < S.reg) return 'pre'
    if (tot >= S.reg || tot < S.after) return 'reg' 
    if (tot >= S.after && tot < S.idle) return 'after'
    if (tot >= S.idle && tot < S.sync) return 'idle'
  } else {
    // 겨울철 (Winter)
    if (tot >= S.sync && tot < S.pre) return 'sync'
    if (tot >= S.pre && tot < S.reg) return 'pre'
    if (tot >= S.reg || tot < S.after) return 'reg'
    if (tot >= S.after && tot < S.idle) return 'after'
    if (tot >= S.idle && tot < S.sync) return 'idle'
  }
  
  return 'none'
}

// 🚀 [V23.3] 서버 시간 파싱 함수 (ISO 8601 표준 대응 강화)
const parseServerTime = (ts: string) => {
  if (!ts) return new Date()
  try {
    // 1. 표준 ISO 규격 파싱 시도 (T 구분자 및 타임존 포함 대응)
    const isoStr = ts.includes('T') ? ts : ts.replace(' ', 'T')
    const d = new Date(isoStr)
    if (!isNaN(d.getTime())) return d
    
    // 2. 수동 정규식 폴백 (브라우저 호환성 방어)
    const m = ts.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/)
    if (m) {
        return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]), Number(m[6]))
    }
    return new Date()
  } catch (e) {
    console.warn("[TrueSync] Timestamp parse error:", ts, e)
    return new Date()
  }
}

export default function MarketTimeline({ marketStatus, dstInfo, isSummer: propIsSummer, isTradeActive, isReal, taskStatus }: MarketTimelineProps) {
  const [localNow, setLocalNow] = useState(new Date());
  const [serverOffset, setServerOffset] = useState<number | null>(null);
  const [isSynced, setIsSynced] = useState(false);
  
  // 🔍 [V24] 페이즈별 상세 기록 모달 상태
  const [selectedPhase, setSelectedPhase] = useState<any>(null);
  const [phaseEvents, setPhaseEvents] = useState<any[]>([]);
  const [loadingEvents, setLoadingEvents] = useState(false);

  // 🕒 [V23.2 TrueSync] 리얼타임 OS 시계 동기화 (파일 스냅샷 지연 해결)
  useEffect(() => {
    const syncWithOSClock = async () => {
      try {
        const startFetch = Date.now();
        const response = await fetch('/api/server-time');
        const data = await response.json();
        const endFetch = Date.now();
        const latency = (endFetch - startFetch) / 2; // 네트워크 지연 보정

        if (data.server_time) {
          const serverT = parseServerTime(data.server_time).getTime();
          const localT = endFetch; 
          const offset = (serverT + latency) - localT;
          setServerOffset(offset);
          setIsSynced(true);
          console.log(`[TrueSync] Server OS Clock Connected. Offset: ${offset}ms`);
        }
      } catch (error) {
        console.error("[TrueSync] Connection error:", error);
      }
    };
    syncWithOSClock();
  }, []);

  // 🚀 시계 고기능 ticker (서밋타임 실시간 반영)
  useEffect(() => {
    const ticker = setInterval(() => {
      const now = new Date();
      if (serverOffset !== null) {
        setLocalNow(new Date(now.getTime() + serverOffset));
      } else {
        setLocalNow(now);
      }
    }, 1000);
    return () => clearInterval(ticker);
  }, [serverOffset]);

  // 🚀 [V24] 서머타임 판별: 명시적 플래그가 있으면 우선 사용, 없으면 문자열 파싱 (하위 호환성)
  const isSummer = typeof propIsSummer === 'boolean' 
    ? propIsSummer 
    : (dstInfo?.includes('서머') || dstInfo?.includes('17:30') || dstInfo?.includes('Summer'))
  const schedule = isSummer ? SCHEDULE_SUMMER : SCHEDULE_WINTER
  const effectiveNow = localNow
  const currentPhase = getCurrentPhase(marketStatus, effectiveNow, isSummer)
  const nowMinutes = effectiveNow.getHours() * 60 + effectiveNow.getMinutes()
  const nyTime = new Date(effectiveNow.getTime() - (isSummer ? 13 : 14) * 60 * 60 * 1000)

  const openPhaseDetail = async (item: any) => {
    setSelectedPhase(item);
    setLoadingEvents(true);
    try {
      const mode = isReal ? 'real' : 'mock';
      const res = await axios.get(`/api/analytics?mode=${mode}`);
      if (res.data.events) {
        // 해당 페이즈와 관련된 키워드로 필터링 (간이 필터링)
        const taskMap: Record<string, string> = {
          'sync': 'SYNC',
          'pre': 'PRE',    // RESET -> PRE (to match log_event)
          'reg': 'REG',    // TRADE -> REG (to match log_event)
          'after': 'SNAPSHOT',
          'idle': 'SYSTEM'
        };
        const targetTask = taskMap[item.phase] || '';
        const filtered = res.data.events.filter((ev: any) => 
          ev.task.includes(targetTask) || ev.msg.includes(item.label)
        );
        setPhaseEvents(filtered.reverse());
      }
    } catch (e) { console.error(e); }
    setLoadingEvents(false);
  }

  const timeFormatOptions: Intl.DateTimeFormatOptions = { 
    hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' 
  };

  return (
    <div className="bg-[#121214] rounded-2xl border border-[#27272a] p-4 mb-4 shadow-lg overflow-hidden relative">
      <div className="flex justify-between items-center mb-4 pb-3 border-b border-[#27272a]/50">
        <div className="flex flex-col">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[0.5rem] text-gray-500 uppercase tracking-widest">Seoul (KST)</span>
            <div className={`flex items-center gap-1 px-1.5 py-0.5 rounded-full border ${isSynced ? 'bg-green-500/5 border-green-500/10' : 'bg-gray-500/5 border-gray-500/10'}`}>
              <div className={`w-1 h-1 rounded-full ${isSynced ? 'bg-green-500 animate-pulse' : 'bg-gray-600'}`}></div>
              <span className={`text-[0.4rem] font-bold uppercase tracking-tighter ${isSynced ? 'text-green-500/70' : 'text-gray-500'}`}>
                {isSynced ? 'Live Sync' : 'Connecting'}
              </span>
            </div>
          </div>
          <span className="text-white font-mono text-xl font-bold tabular-nums">
            {effectiveNow.toLocaleTimeString('en-US', timeFormatOptions)}
          </span>
        </div>
        
        <div className="flex flex-col items-center">
          <div className="w-8 h-px bg-gradient-to-r from-transparent via-[#27272a] to-transparent"></div>
          <span className="text-[0.6rem] text-blue-400 font-bold py-1">{(isSummer ? 'SUMMER -13h' : 'WINTER -14h')}</span>
          <div className="flex items-center gap-1">
            {isReal ? (
              <span className="text-[0.45rem] px-1.5 py-0.5 bg-red-500/10 text-red-500 border border-red-500/20 rounded font-black uppercase tracking-tighter">Real Trading</span>
            ) : (
              <span className="text-[0.45rem] px-1.5 py-0.5 bg-orange-500/10 text-orange-500 border border-orange-500/20 rounded font-black uppercase tracking-tighter">MOCK Active</span>
            )}
          </div>
          <div className="w-8 h-px bg-gradient-to-r from-transparent via-[#27272a] to-transparent"></div>
        </div>

        <div className="flex flex-col text-right">
          <span className="text-[0.5rem] text-blue-500 uppercase tracking-widest mb-1">New York (ET)</span>
          <span className="text-blue-400 font-mono text-xl font-bold tabular-nums">
            {nyTime.toLocaleTimeString('en-US', timeFormatOptions)}
          </span>
        </div>
      </div>

      <div className={`rounded-xl px-4 py-3 mb-4 border flex justify-between items-center transition-all ${
        currentPhase === 'reg' ? 'border-red-500/50 bg-red-900/10' :
        currentPhase === 'pre' ? 'border-yellow-500/50 bg-yellow-900/10' :
        currentPhase === 'after' ? 'border-purple-500/50 bg-purple-900/10' :
        'border-[#27272a] bg-[#18181b]'
      }`}>
        <div className="flex flex-col">
          <span className={`text-sm font-black tracking-tight ${
            currentPhase === 'reg' ? 'text-red-400' :
            currentPhase === 'pre' ? 'text-yellow-400' :
            currentPhase === 'after' ? 'text-purple-400' :
            (marketStatus === 'WEEKEND' || marketStatus === 'HOLIDAY') ? 'text-blue-400' :
            'text-gray-400'
          }`}>
            {marketStatus === 'OPEN' ? '🔥 실시간 정규장' :
             marketStatus === 'WEEKEND' ? '⛱️ 주말 휴장' :
             marketStatus === 'HOLIDAY' ? '🎉 공휴일 휴장' :
             marketStatus || '⛔ 시장 종료'}
          </span>
          <span className="text-[0.6rem] text-gray-500 mt-0.5">
            {currentPhase === 'reg' ? '🔥 실시간 LOC 및 스나이퍼 매수 작동 중' :
             currentPhase === 'pre' ? '👀 프리마켓 가격 변동성 모니터링 중' :
             '💤 현재 자동 매매 대기 상태입니다.'}
          </span>
        </div>
        {isTradeActive && (
          <div className="flex items-center gap-2 bg-green-500/10 px-2 py-1 rounded-full border border-green-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></span>
            <span className="text-[0.55rem] font-bold text-green-500 uppercase">Engine Running</span>
          </div>
        )}
      </div>

      <div className="space-y-1 relative">
        {schedule.map((item, idx) => {
          const etTime = getET(item.time, isSummer)
          const status = taskStatus?.[item.phase] || { status: 'pending', time: '' }
          const isPast = (() => {
            const [h, m] = item.time.split(':').map(Number)
            return nowMinutes > h * 60 + m
          })()
          const isCurrent = currentPhase === item.phase

          return (
            <div 
              key={idx} 
              onClick={() => openPhaseDetail(item)}
              className={`relative flex items-center gap-4 p-2 rounded-xl border transition-all cursor-pointer group hover:bg-white/5 ${
                isCurrent ? 'bg-white/5 border-white/10 shadow-inner' : 'border-transparent'
              }`}
            >
              <div className="flex flex-col items-center min-w-[3.5rem] border-r border-[#27272a] pr-3 group-hover:border-blue-500/30 transition-colors">
                <span className={`text-[0.7rem] font-bold font-mono tabular-nums ${isCurrent ? 'text-white' : 'text-gray-400'}`}>
                  {item.time}
                </span>
                <span className="text-[0.5rem] font-mono text-gray-600">ET {etTime}</span>
              </div>

              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className={`text-[0.7rem] font-bold ${isCurrent ? 'text-white' : isPast ? 'text-gray-400' : 'text-gray-500'}`}>
                    {item.label}
                  </span>
                  {status.status === 'done' && (
                    <span className="text-[0.5rem] bg-green-500/10 text-green-500 px-1.5 py-0.5 rounded flex items-center gap-1 font-bold">
                      <span className="w-1 h-1 bg-green-500 rounded-full"></span>
                      성공 {status.time}
                    </span>
                  )}
                  {status.status === 'running' && (
                    <span className="text-[0.5rem] bg-blue-500/10 text-blue-400 px-1.5 py-0.5 rounded flex items-center gap-1 font-bold animate-pulse">
                      <span className="w-1 h-1 bg-blue-500 rounded-full"></span>
                      진행 중
                    </span>
                  )}
                  {status.status === 'error' && (
                    <span className="text-[0.5rem] bg-red-500/10 text-red-500 px-1.5 py-0.5 rounded flex items-center gap-1 animate-pulse font-bold">
                      <span className="w-1 h-1 bg-red-500 rounded-full"></span>
                      오류발생
                    </span>
                  )}
                </div>
                <div className={`text-[0.55rem] leading-tight ${isCurrent ? 'text-gray-300' : 'text-gray-600'}`}>
                  {item.desc}
                </div>
              </div>

              {isCurrent && (
                <div className="absolute left-[-2px] top-0 bottom-0 w-1 bg-blue-500 rounded-full"></div>
              )}
            </div>
          )
        })}
      </div>

      <div className="mt-3 pt-3 border-t border-[#27272a] flex justify-between items-center text-[0.55rem]">
        <span className="text-gray-600 italic">
          * 모든 작업은 서버 스케줄러에 의해 <span className="text-gray-400 font-bold">오차 없이 자동 수행</span>됩니다.
        </span>
        <div className="flex gap-2 text-gray-500">
          <div className="flex items-center gap-1"><span className="w-1 h-1 rounded-full bg-green-500"></span> 성공</div>
          <div className="flex items-center gap-1"><span className="w-1 h-1 rounded-full bg-red-500"></span> 오류</div>
          <div className="flex items-center gap-1"><span className="w-1 h-1 rounded-full bg-gray-500"></span> 대기</div>
        </div>
      </div>

      {/* 🚀 [V26.5] 페이즈 상세 기록 (Situation Room Inline View) */}
      {selectedPhase && (
        <div className="mt-4 border-t border-[#27272a] pt-4 animate-fade-in">
          <div className="bg-[#09090b]/50 rounded-2xl border border-[#27272a] overflow-hidden shadow-2xl">
            <div className="px-4 py-3 border-b border-[#27272a] flex justify-between items-center bg-gradient-to-r from-blue-900/10 to-transparent">
              <div>
                <h4 className="text-white font-black text-xs flex items-center gap-2">
                  <span className="w-1.5 h-3 bg-blue-500 rounded-full"></span>
                  {selectedPhase.label} <span className="text-[0.6rem] text-gray-500 font-normal">상세 운영 아카이브</span>
                </h4>
              </div>
              <button 
                onClick={() => setSelectedPhase(null)}
                className="text-[0.6rem] text-gray-500 hover:text-white transition-colors"
              >
                닫기 ✕
              </button>
            </div>
            
            <div className="max-h-[300px] overflow-y-auto scrollbar-thin scrollbar-thumb-[#3f3f46]">
              {loadingEvents ? (
                <div className="py-8 flex flex-col items-center gap-2">
                  <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                  <span className="text-[0.6rem] text-gray-500">데이터 동기화 중...</span>
                </div>
              ) : phaseEvents.length === 0 ? (
                <div className="py-8 text-center">
                  <p className="text-gray-600 text-[0.6rem]">해당 단계의 상세 작업 기록이 비어있습니다.</p>
                </div>
              ) : (
                <table className="w-full text-left border-collapse">
                  <thead className="sticky top-0 bg-[#0c0c0e] text-[0.55rem] text-gray-500 uppercase font-bold">
                    <tr>
                      <th className="px-4 py-2 border-b border-[#27272a] w-16">시간</th>
                      <th className="px-2 py-2 border-b border-[#27272a] w-20">작업</th>
                      <th className="px-2 py-2 border-b border-[#27272a]">내용</th>
                      <th className="px-4 py-2 border-b border-[#27272a] w-12 text-center">상태</th>
                    </tr>
                  </thead>
                  <tbody className="text-[0.65rem]">
                    {phaseEvents.map((ev: any, i: number) => (
                      <tr key={i} className="border-b border-[#27272a]/30 hover:bg-white/[0.02] transition-colors group">
                        <td className="px-4 py-2 text-gray-500 font-mono text-[0.6rem] whitespace-nowrap">{ev.time}</td>
                        <td className="px-2 py-2 text-blue-400 font-bold tracking-tighter">{ev.task}</td>
                        <td className="px-2 py-2 text-white/90 leading-snug">
                          {ev.msg}
                          {ev.details && (
                            <div className="text-[0.55rem] text-gray-500 mt-0.5 font-light italic">
                              {ev.details}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-2 text-center">
                          <span className={`inline-block w-1.5 h-1.5 rounded-full ${
                            ev.status === 'SUCCESS' ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]' : 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)]'
                          }`}></span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
