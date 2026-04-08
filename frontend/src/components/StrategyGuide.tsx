export default function StrategyGuide() {
  return (
    <div className="space-y-16 animate-fade-in pb-32 max-w-6xl mx-auto px-2">
      
      {/* 🏆 마스터 헤더: 알고리즘 엔진의 정수 */}
      <div className="bg-gradient-to-br from-[#1a1a1e] via-[#121214] to-[#09090b] p-12 rounded-[2rem] border border-[#27272a] shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-2 bg-gradient-to-r from-blue-600 via-indigo-500 to-emerald-500"></div>
        <div className="absolute -top-32 -right-32 w-96 h-96 bg-blue-500/10 blur-[130px] rounded-full"></div>
        <div className="relative z-10 text-center">
          <h2 className="text-5xl font-black text-white mb-6 tracking-tighter leading-none">
            QUANTUM <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400 uppercase italic">Core Strategy Guide</span>
          </h2>
          <div className="w-20 h-1 bg-blue-500 mx-auto mb-8 rounded-full opacity-50"></div>
          <p className="text-gray-400 text-sm max-w-2xl mx-auto leading-relaxed font-medium">
            본 가이드는 시스템의 단순 소개가 아닌, 실제 소스코드(`strategy.py`)에 구현된 수학적 로직과 하이 레벨 알고리즘을 상세히 설명합니다.<br/>
            모든 설정값은 무한매수법의 물리적 생존력과 자금 회전율을 극대화하기 위해 설계되었습니다.
          </p>
        </div>
      </div>

      {/* 🚀 섹션 1: 3대 핵심 기초 전략 (Deep Backbone) */}
      <section className="space-y-8">
        <div className="flex items-center gap-4 mb-4 px-3">
          <span className="text-2xl font-black text-white px-3 py-1 bg-blue-600/20 border border-blue-500/40 rounded-xl">01</span>
          <h3 className="text-2xl font-black text-white tracking-tight uppercase">Base Strategy Analysis <span className="text-xs text-gray-500 font-normal ml-3 lowercase bg-[#27272a] px-2 py-1 rounded">알고리즘 기반 구조</span></h3>
        </div>
        
        <div className="grid grid-cols-1 gap-8">
          {/* V13: Classic */}
          <div className="bg-[#18181b] p-10 rounded-3xl border border-[#27272a] hover:border-blue-500/30 transition-all shadow-inner relative overflow-hidden">
            <div className="flex flex-col md:flex-row justify-between items-start gap-6 border-b border-[#27272a] pb-8 mb-8">
              <div className="space-y-2">
                <h4 className="text-blue-400 font-extrabold text-2xl tracking-tighter">V13 CLASSIC [원본 정석]</h4>
                <p className="text-gray-300 text-sm font-bold">라오어 무한매수법의 원리를 충실히 따르는 고정 분할 모델</p>
              </div>
              <div className="px-4 py-2 bg-blue-500/10 rounded-xl border border-blue-500/20">
                <span className="text-[0.65rem] text-blue-400 font-black uppercase tracking-widest block mb-1">Portion Policy</span>
                <span className="text-white font-bold text-xs italic">Fixed Split (Initial Seed / Split)</span>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
              <div className="space-y-4">
                <h5 className="text-white text-xs font-black uppercase tracking-widest flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-blue-500 rounded-full"></span> 동작 메커니즘 (Mechanism)
                </h5>
                <p className="text-gray-400 text-[0.8rem] leading-relaxed">
                  초기 입력된 분할 횟수(`Split`)를 기준으로 전체 예산을 등분하여 매일 동일한 금액을 투입합니다. 
                  대형 기술주와 같은 변동성이 일정 범위 내에 있는 종목에 최적화되어 있으며, 
                  **가장 기계적이고 심리적 흔들림이 적은 정석적인 모델**입니다.
                </p>
              </div>
              <div className="space-y-4">
                <h5 className="text-white text-xs font-black uppercase tracking-widest flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-blue-500 rounded-full"></span> 기술적 디테일 (Specs)
                </h5>
                <ul className="space-y-2 text-[0.75rem] text-gray-400">
                  <li className="flex justify-between items-center"><span className="text-gray-500">분할 정책</span> <span className="text-gray-200">고정 분할 (평단가/별값 5:5 하이브리드)</span></li>
                  <li className="flex justify-between items-center"><span className="text-gray-500">매수 가격</span> <span className="text-gray-200">LOC(Avg - 0.01) + LOC(Star - 0.01)</span></li>
                  <li className="flex justify-between items-center"><span className="text-gray-500">핵심 강점</span> <span className="text-gray-200">MDD 방어의 표준화, 감정 배제율 100%</span></li>
                </ul>
              </div>
            </div>
          </div>

          {/* V14: Modular */}
          <div className="bg-[#18181b] p-10 rounded-3xl border border-[#27272a] hover:border-emerald-500/30 transition-all shadow-inner relative overflow-hidden">
             <div className="flex flex-col md:flex-row justify-between items-start gap-6 border-b border-[#27272a] pb-8 mb-8">
              <div className="space-y-2">
                <h4 className="text-emerald-400 font-extrabold text-2xl tracking-tighter">V14 MODULAR [가변 집중]</h4>
                <p className="text-gray-300 text-sm font-bold">남은 회차를 실시간 계산하여 평단가에 화력을 집중하는 대응형 모델</p>
              </div>
              <div className="px-4 py-2 bg-emerald-500/10 rounded-xl border border-emerald-500/20">
                <span className="text-[0.65rem] text-emerald-400 font-black uppercase tracking-widest block mb-1">Portion Policy</span>
                <span className="text-white font-bold text-xs italic">Cash / (Split - T_Val)</span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
              <div className="space-y-4">
                <h5 className="text-white text-xs font-black uppercase tracking-widest flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full"></span> 동작 메커니즘 (Mechanism)
                </h5>
                <p className="text-gray-400 text-[0.8rem] leading-relaxed">
                  자산 소진율(`T-Value`)을 매 순간 체크하여 가동 가능한 현금을 남은 회차로 나눈 **가변 1분량**을 매일 산출합니다. 
                  주가가 평단 아래로 내려갔을 때 평단가(Avg) 지점에 1.0분량의 화력을 집중 투입하여 **평단가 하강 속도를 비약적으로 높이는 것**이 핵심입니다.
                </p>
              </div>
              <div className="space-y-4">
                <h5 className="text-white text-xs font-black uppercase tracking-widest flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full"></span> 기술적 디테일 (Specs)
                </h5>
                <ul className="space-y-2 text-[0.75rem] text-gray-400">
                  <li className="flex justify-between items-center"><span className="text-gray-500">분할 정책</span> <span className="text-gray-200">가변 분할 (Bypass 활용 집중 매수)</span></li>
                  <li className="flex justify-between items-center"><span className="text-gray-500">매수 가격</span> <span className="text-gray-200">LOC(Avg - 0.01) [1.0회분 몰빵]</span></li>
                  <li className="flex justify-between items-center"><span className="text-gray-500">핵심 강점</span> <span className="text-gray-200">하락 국면에서의 빠른 평단 캐치업 및 기회 창출</span></li>
                </ul>
              </div>
            </div>
             <div className="mt-8 p-4 bg-emerald-500/5 rounded-2xl text-[0.7rem] text-emerald-400/80 italic">
               💡 Expert Tip: 횡보장에서 지루한 시간을 버티기보다는 평단가 근처에서 수량을 확보하여 빠른 탈출 기회를 잡고 싶을 때 강력 추천합니다.
             </div>
          </div>

          {/* V24: Shadow-Strike */}
          <div className="bg-[#18181b] p-10 rounded-3xl border border-[#27272a] hover:border-indigo-500/30 transition-all shadow-inner relative overflow-hidden">
            <div className="flex flex-col md:flex-row justify-between items-start gap-6 border-b border-[#27272a] pb-8 mb-8">
              <div className="space-y-2">
                <h4 className="text-indigo-400 font-extrabold text-2xl tracking-tighter">V24 SHADOW-STRIKE [눌림목 정밀]</h4>
                <p className="text-gray-300 text-sm font-bold">장중 저점 반등(Bounce)을 자동 추적하는 인공지능형 타격 엔진</p>
              </div>
              <div className="px-4 py-2 bg-indigo-500/10 rounded-xl border border-indigo-500/20">
                <span className="text-[0.65rem] text-indigo-400 font-black uppercase tracking-widest block mb-1">Portion Policy</span>
                <span className="text-white font-bold text-xs italic">Day_Low * (1 + 1.5%) Logic</span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
              <div className="space-y-4">
                <h5 className="text-white text-xs font-black uppercase tracking-widest flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full"></span> 동작 메커니즘 (Mechanism)
                </h5>
                <p className="text-gray-400 text-[0.8rem] leading-relaxed">
                  단순한 종가 매매를 넘어 **물리적인 저점 반등 지점**을 공략합니다. 당일 기록한 최저점 대비 1.5% 상승하는 시점을 격발(Shadow Strike) 가격으로 설정합니다. 
                  과매도 국면에서 튀어 오르는 구간만을 골라 사기 때문에 **체결 즉시 수익권**에 들어설 확률이 매우 높습니다.
                </p>
              </div>
              <div className="space-y-4">
                <h5 className="text-white text-xs font-black uppercase tracking-widest flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full"></span> 기술적 디테일 (Specs)
                </h5>
                <ul className="space-y-2 text-[0.75rem] text-gray-400">
                  <li className="flex justify-between items-center"><span className="text-gray-500">분할 정책</span> <span className="text-gray-200">5:5 눌림목 포격 (평단 매칭 병행)</span></li>
                  <li className="flex justify-between items-center"><span className="text-gray-500">매수 가격</span> <span className="text-gray-200">LOC(Low * 1.015) | 캡핑 5% 적용</span></li>
                  <li className="flex justify-between items-center"><span className="text-gray-500">전매 기능</span> <span className="text-gray-200">제로 리버스(Zero-Reverse) 자동 소진 모드 내장</span></li>
                </ul>
              </div>
            </div>
            <div className="mt-8 p-4 bg-indigo-500/5 rounded-2xl text-[0.7rem] text-indigo-400/80 italic">
               💡 Expert Tip: 시드 소진이 극심한 지옥장에서도 끝까지 평단을 사수하며 탈출 각을 재는 최강의 생존형 공격 엔진입니다.
             </div>
          </div>
        </div>
      </section>

      {/* ⚔️ 섹션 2: 8대 실전 전술 명령 (Tactical Matrix) */}
      <section className="space-y-10">
        <div className="flex items-center gap-4 mb-4 px-3">
          <span className="text-2xl font-black text-white px-3 py-1 bg-red-600/20 border border-red-500/40 rounded-xl">02</span>
          <h3 className="text-2xl font-black text-white tracking-tight uppercase">Tactical Matrix <span className="text-xs text-gray-500 font-normal ml-3 lowercase bg-[#27272a] px-2 py-1 rounded">8대 실전 전술 모듈</span></h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
           {/* 공격 전술 그룹 */}
           <div className="bg-[#121214] p-8 rounded-[2rem] border border-red-500/20 relative overflow-hidden">
             <div className="absolute top-0 right-0 p-8 opacity-5 font-black text-6xl italic text-red-500 pointer-events-none">OFFENSE</div>
             <h4 className="text-red-400 font-black text-base uppercase tracking-widest mb-8 flex items-center gap-3">
               <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></span> ⚔️ 공격 유닛 (Aggressive)
             </h4>
             
             <div className="space-y-6">
                <div className="bg-[#18181b] p-6 rounded-2xl border border-[#27272a] hover:bg-[#1d1d21] transition-colors group">
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-sm font-black text-white group-hover:text-red-400 transition-colors">새도우 스트라이크 (Shadow)</span>
                    <span className="text-[0.6rem] text-gray-500 font-mono tracking-tighter">BOUNCE-ENTRY</span>
                  </div>
                  <p className="text-[0.7rem] text-gray-500 leading-relaxed">
                    실시간 저점(`Day Low`) 대비 **1.5% 반등 시 격격발**. <br/>
                    <span className="text-gray-400 italic">"바닥이 확인된 시점에서만 진입하여 체결 즉시 유리한 포지션을 선점합니다."</span>
                  </p>
                </div>

                <div className="bg-[#18181b] p-6 rounded-2xl border border-[#27272a] hover:bg-[#1d1d21] transition-colors group">
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-sm font-black text-white group-hover:text-red-400 transition-colors">스나이퍼 익절 (Sniper Exit)</span>
                    <span className="text-[0.6rem] text-gray-500 font-mono tracking-tighter">QUARTER-TAKING</span>
                  </div>
                  <p className="text-[0.7rem] text-gray-500 leading-relaxed">
                    `Day High` 대비 **-1.5% 하락** 시 보유량 **1/4 강제 매도**. <br/>
                    <span className="text-gray-400 italic">"수익권에서 휩소(Screech) 발생 시 중간 수익을 확정하여 하락장 시드를 마련합니다."</span>
                  </p>
                </div>

                <div className="bg-[#18181b] p-6 rounded-2xl border border-[#27272a] hover:bg-[#1d1d21] transition-colors group">
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-sm font-black text-white group-hover:text-red-400 transition-colors">터보 부스터 (Turbo)</span>
                    <span className="text-[0.6rem] text-gray-500 font-mono tracking-tighter">CRASH-ACCEL</span>
                  </div>
                  <p className="text-[0.7rem] text-gray-500 leading-relaxed">
                    전일 종가 대비 **-5% 폭락 지점**에서 추가 예산(1.0 Port) 즉시 투입. <br/>
                    <span className="text-gray-400 italic">"시장의 공포가 극에 달한 순간, 평단가를 수직으로 끌어내리는 가속 엔진입니다."</span>
                  </p>
                </div>

                <div className="bg-[#18181b] p-6 rounded-2xl border border-[#27272a] hover:bg-[#1d1d21] transition-colors group">
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-sm font-black text-white group-hover:text-red-400 transition-colors">줍줍 거미줄 (Jup-Jup)</span>
                    <span className="text-[0.6rem] text-gray-500 font-mono tracking-tighter">RESIDUE-GRID</span>
                  </div>
                  <p className="text-[0.7rem] text-gray-500 leading-relaxed">
                    자투리 현금을 평단 하단 0.5% 간격으로 **10~20단계 주문 배치**. <br/>
                    <span className="text-gray-400 italic">"알고리즘 매매 특성상 발생하는 잔여금을 고효율 물량 확보로 치환합니다."</span>
                  </p>
                </div>
             </div>
           </div>

           {/* 방어 전술 그룹 */}
           <div className="bg-[#121214] p-8 rounded-[2rem] border border-blue-500/20 relative overflow-hidden">
             <div className="absolute top-0 right-0 p-8 opacity-5 font-black text-6xl italic text-blue-500 pointer-events-none">DEFENSE</div>
             <h4 className="text-blue-400 font-black text-base uppercase tracking-widest mb-8 flex items-center gap-3">
               <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></span> 🛡️ 방어 및 분석 (Stability)
             </h4>

             <div className="space-y-6">
                <div className="bg-[#18181b] p-6 rounded-2xl border border-[#27272a] hover:bg-[#1d1d21] transition-colors group">
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-sm font-black text-white group-hover:text-blue-400 transition-colors">다이내믹 쉴드 (Shield)</span>
                    <span className="text-[0.6rem] text-gray-500 font-mono tracking-tighter">T-VAL SCALING</span>
                  </div>
                  <p className="text-[0.7rem] text-gray-500 leading-relaxed">
                    소진율에 따른 분할 배수 조정: **50%(1.5x) / 75%(2.0x) / 90%(2.5x)**. <br/>
                    <span className="text-gray-400 italic">"자금이 바닥나기 전 분할 수를 물리적으로 늘려 생존 수명을 무한히 확장합니다."</span>
                  </p>
                </div>

                <div className="bg-[#18181b] p-6 rounded-2xl border border-[#27272a] hover:bg-[#1d1d21] transition-colors group">
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-sm font-black text-white group-hover:text-blue-400 transition-colors">V-REV 리버스 (Reversion)</span>
                    <span className="text-[0.6rem] text-gray-500 font-mono tracking-tighter">CYCLE-REBOOT</span>
                  </div>
                  <p className="text-[0.7rem] text-gray-500 leading-relaxed">
                    시드 전량 소진(Hell) 국면 가동. **1/20 물량의 기계적 순환**. <br/>
                    <span className="text-gray-400 italic">"매몰된 계좌를 순환 매매로 풀어내어 기회비용을 수익으로 환원합니다."</span>
                  </p>
                </div>

                <div className="bg-[#18181b] p-6 rounded-2xl border border-[#27272a] hover:bg-[#1d1d21] transition-colors group">
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-sm font-black text-white group-hover:text-blue-400 transition-colors">VIX-Aware Sizing</span>
                    <span className="text-[0.6rem] text-gray-500 font-mono tracking-tighter">FEAR-INDEX WEIGHT</span>
                  </div>
                  <p className="text-[0.7rem] text-gray-500 leading-relaxed">
                    VIX 지수 기준 물량 조절: **25(100%) &rarr; 35(70%) &rarr; 45(40%) &rarr; Stop**. <br/>
                    <span className="text-gray-400 italic">"극도의 패닉장에서는 지갑을 닫아 폭락의 칼날을 정면으로 받지 않습니다."</span>
                  </p>
                </div>

                <div className="bg-[#18181b] p-6 rounded-2xl border border-[#27272a] hover:bg-[#1d1d21] transition-colors group">
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-sm font-black text-white group-hover:text-blue-400 transition-colors">VWAP Dominance 분석</span>
                    <span className="text-[0.6rem] text-gray-500 font-mono tracking-tighter">VOLUME-SLOPE FILTER</span>
                  </div>
                  <p className="text-[0.7rem] text-gray-500 leading-relaxed">
                    VWAP 상단 거래량 **55% 돌파 시 BUY 주문 자동 차단**. <br/>
                    <span className="text-gray-400 italic">"상승장의 단기 과열 구간에서 발생하는 '포모(FOMO) 매수'를 원천적으로 차단합니다."</span>
                  </p>
                </div>
             </div>
           </div>
        </div>
      </section>

      {/* 📊 섹션 3: 설정값 마스터 레퍼런스 (Advanced Calibration) */}
      <section className="bg-[#09090b] rounded-[2.5rem] border border-[#27272a] overflow-hidden shadow-2xl relative">
        <div className="p-8 border-b border-[#27272a] bg-[#121214]/80 backdrop-blur-md flex justify-between items-center z-10 relative">
            <h3 className="text-white font-black text-sm uppercase tracking-[0.3em] flex items-center gap-4">
              <span className="w-3 h-3 bg-emerald-500 rounded-full animate-pulse shadow-[0_0_10px_rgba(16,185,129,0.5)]"></span> 
              마스터 파라미터 기술 가이드 <span className="text-[0.65rem] text-gray-500 font-normal lowercase tracking-normal bg-[#27272a] px-2 py-0.5 rounded">Technical Reference Table</span>
            </h3>
        </div>
        
        {/* [V41 패치] 컬럼 비율 밸런싱 최적화 레이아웃 */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[0.75rem] border-collapse min-w-[900px]">
            <thead className="bg-[#18181b] text-gray-500 font-bold border-b border-[#27272a]/50">
              <tr className="flex">
                <th className="px-6 py-5 flex-[1.5] flex items-center">핵심 구분</th>
                <th className="px-6 py-5 flex-[1.5] flex items-center">변수명 (Config)</th>
                <th className="px-6 py-5 flex-[5.5] flex items-center">알고리즘 상세 로직 및 기술 명세</th>
                <th className="px-6 py-5 flex-[1.5] flex items-center text-emerald-400">최적 권장값</th>
              </tr>
            </thead>
            <tbody className="bg-[#0c0c0e] text-gray-400 font-medium">
              <tr className="flex border-b border-[#27272a]/30 hover:bg-[#121214] transition-colors group">
                <td className="px-6 py-6 flex-[1.5] text-white font-black group-hover:text-emerald-400">목표 수익률</td>
                <td className="px-6 py-6 flex-[1.5] font-mono text-gray-500">targetPct</td>
                <td className="px-6 py-6 flex-[5.5] leading-relaxed text-gray-400">
                  전체 사이클의 리셋 포인트를 결정합니다. `(Avg_Price * (1 + targetPct))`가 매도 격발 가격이며, 무한 순환 사이클의 복리 회전율의 핵심 엔진 역할을 합니다.
                </td>
                <td className="px-6 py-6 flex-[1.5] font-black text-emerald-500 italic">10% (기준)</td>
              </tr>
              <tr className="flex border-b border-[#27272a]/30 hover:bg-[#121214] transition-colors group">
                <td className="px-6 py-6 flex-[1.5] text-white font-black group-hover:text-emerald-400">기본 분할 횟수</td>
                <td className="px-6 py-6 flex-[1.5] font-mono text-gray-500">split</td>
                <td className="px-6 py-6 flex-[5.5] leading-relaxed text-gray-400">
                  시장 하방 변동성에 대한 물리적 체력(Capital Endurance)을 정의합니다. `Initial_Seed / Split`을 통해 1일 기본 매수량을 결정하며, T-Value 산출의 절대적 기준값입니다.
                </td>
                <td className="px-6 py-6 flex-[1.5] font-black text-emerald-500 italic">40 ~ 50 회</td>
              </tr>
              <tr className="flex border-b border-[#27272a]/30 hover:bg-[#121214] transition-colors group">
                <td className="px-6 py-6 flex-[1.5] text-white font-black group-hover:text-emerald-400">스나이퍼 낙폭</td>
                <td className="px-6 py-6 flex-[1.5] font-mono text-gray-500">sniper_drop</td>
                <td className="px-6 py-6 flex-[5.5] leading-relaxed text-gray-400">
                  상승 국면에서 매수 타점을 잡는 감도입니다. 당일 고점(`Day_High`) 대비 특정 % 하락 시 **'휩소'로 판단하여 1/4 익절 또는 선제 매수**를 격발시키는 트리거 수치입니다.
                </td>
                <td className="px-6 py-6 flex-[1.5] font-black text-emerald-500 italic">1.5%</td>
              </tr>
              <tr className="flex border-b border-[#27272a]/30 hover:bg-[#121214] transition-colors group">
                <td className="px-6 py-6 flex-[1.5] text-white font-black group-hover:text-emerald-400">VIX 매수 한계</td>
                <td className="px-6 py-6 flex-[1.5] font-mono text-gray-500">vix_limit</td>
                <td className="px-6 py-6 flex-[5.5] leading-relaxed text-gray-400">
                  시장의 총체적인 공포 수치를 감지합니다. VIX가 이 임계치를 초과할 경우 시스템은 **자동으로 모든 BUY 주문을 보류**하여 폭락장 전면 기습에서 자산을 전면 보존합니다.
                </td>
                <td className="px-6 py-6 flex-[1.5] font-black text-emerald-500 italic">45.0 (Crash)</td>
              </tr>
              <tr className="flex border-b border-[#27272a]/30 hover:bg-[#121214] transition-colors group">
                <td className="px-6 py-6 flex-[1.5] text-white font-black group-hover:text-emerald-400">줍줍 거미줄 밀도</td>
                <td className="px-6 py-6 flex-[1.5] font-mono text-gray-500">jup_density</td>
                <td className="px-6 py-6 flex-[5.5] leading-relaxed text-gray-400">
                  잔여 현금을 활용한 마이크로 분할의 겹수입니다. 평단가 하단 0.5% 간격으로 총 몇 단계의 거미줄 매수를 배치하여 시장의 소음을 흡수할 것인지 결정합니다.
                </td>
                <td className="px-6 py-6 flex-[1.5] font-black text-emerald-500 italic">10 ~ 20 단계</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* 🧭 전문가 결론: 마인드셋 섹션 */}
      <div className="p-12 rounded-[3rem] bg-gradient-to-r from-blue-600/5 to-indigo-600/5 border border-indigo-500/20 text-center relative overflow-hidden group">
        <div className="absolute top-0 left-0 w-1 h-full bg-indigo-500/30 group-hover:bg-indigo-500 transition-colors"></div>
        <p className="text-gray-400 text-sm italic leading-relaxed relative z-10 font-bold max-w-3xl mx-auto">
           "퀀트 매매의 승리 공식은 시장을 맞히는 예측력이 아니라, 무너지는 상황에서도 시스템이 스스로를 방어할 수 있도록 설계된 **이중 삼중의 안전장치(Redundancy)**에 있습니다.<br/><br/>
           위 백서에 기술된 모든 수치들은 수만 번의 백테스팅과 실전 데이터를 통해 최적화되었음을 보증합니다."
        </p>
      </div>
    </div>
  )
}
