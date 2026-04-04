export default function StrategyGuide() {
  return (
    <div className="space-y-10 animate-fade-in pb-20">
      {/* 🏅 Premium Header: The Origin Story */}
      <div className="bg-gradient-to-br from-[#1a1a1e] via-[#121214] to-[#09090b] p-10 rounded-3xl border border-[#27272a] shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 right-0 w-80 h-80 bg-blue-500/5 blur-[120px] rounded-full -mr-30 -mt-30"></div>
        <div className="relative z-10">
          <h2 className="text-4xl font-black text-white mb-3 tracking-tight">
            Infinity Quant Hub <span className="text-gray-500">전략 가이드</span>
          </h2>
          <p className="text-gray-400 text-sm max-w-3xl leading-relaxed">
            무한매수법(Infinity Trading)의 근본 설계부터, 시장의 물리적 한계를 극복하기 위해 단계별로 진화된 <strong>[하이브리드 생존 아키텍처]</strong>를 공개합니다.
          </p>
        </div>
      </div>

      {/* 🛡️ Step 0 & 1: The Core & The Shield */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Step 0: The Base Rules */}
        <div className="bg-[#18181b] rounded-2xl border border-[#27272a] p-8 hover:border-blue-500/20 transition-all group">
          <div className="flex items-center gap-4 mb-5">
            <span className="text-3xl font-black text-[#27272a] group-hover:text-blue-500/50 transition-colors">00</span>
            <h3 className="text-xl font-bold text-white tracking-tight">Step 0: 무한매수 원칙 (The Base)</h3>
          </div>
          <p className="text-gray-400 text-xs leading-relaxed mb-6">
            모든 여정은 '하락장에서의 평균 단가 우위'에서 시작됩니다. 기계적인 **40분할 매수**와 **LOC(장마감 지정가)**를 통해 인간의 심리가 개입할 틈을 없앱니다.
          </p>
          <div className="bg-red-950/20 p-4 rounded-xl border border-red-900/30">
            <h4 className="text-red-400 text-[0.65rem] font-bold uppercase mb-2">🚨 치명적 한계점 (The Problem)</h4>
            <p className="text-[0.65rem] text-gray-400 leading-normal italic">
              "40일 이상의 장기 하락장이 지속되면 시드가 고갈(Seed Exhaustion)되어 최저점에서 강제로 매매가 중단됩니다."
            </p>
          </div>
        </div>

        {/* Step 1: Resistance (T-Value) */}
        <div className="bg-[#18181b] rounded-2xl border border-blue-500/30 p-8 shadow-[0_0_30px_rgba(59,130,246,0.05)] relative group overflow-hidden">
           <div className="absolute top-0 right-0 p-4 opacity-5 pointer-events-none group-hover:scale-150 transition-transform duration-700">
            <span className="text-9xl font-black italic">V22</span>
          </div>
          <div className="flex items-center gap-4 mb-5">
            <span className="text-3xl font-black text-blue-500/30">01</span>
            <h3 className="text-xl font-bold text-white tracking-tight">Step 1: 동적 방어 (The Shield)</h3>
          </div>
          <p className="text-gray-400 text-xs leading-relaxed mb-6">
            시드 고갈 문제를 해결하기 위해 고안된 **V22 T-Value 엔진**입니다. 자금 소진율에 따라 매수 속도를 자동으로 늦추어 하락장에서의 수명을 2.5배 연장합니다.
          </p>
          <div className="bg-[#09090b] p-4 rounded-xl border border-[#27272a] font-mono text-[0.65rem] space-y-2 relative z-10">
            <div className="flex justify-between"><span>🌓 Normal (T 0~50%)</span> <span className="text-green-400">1.0배 (40분할)</span></div>
            <div className="flex justify-between"><span>🛡️ Defense (T 50~75%)</span> <span className="text-yellow-400">1.5배 (60분할)</span></div>
            <div className="flex justify-between"><span>🚨 Crash (T 75~90%)</span> <span className="text-orange-400">2.0배 (80분할)</span></div>
            <div className="flex justify-between"><span>☠️ Hell (T 90%+)</span> <span className="text-red-400">2.5배 (100분할)</span></div>
          </div>
        </div>
      </div>

      {/* ⚔️ Step 2 & 3: The Sword & The Engine */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Step 2: Booster & Star Price */}
        <div className="bg-[#18181b] rounded-2xl border border-orange-500/30 p-8 shadow-[0_0_30px_rgba(249,115,22,0.05)] group">
          <div className="flex items-center gap-4 mb-5">
            <span className="text-3xl font-black text-orange-500/30">02</span>
            <h3 className="text-xl font-bold text-white tracking-tight">Step 2: 탈출 가속 (The Sword)</h3>
          </div>
          <p className="text-gray-400 text-xs leading-relaxed mb-6">
            단순히 버티는 것을 넘어, 수익권 도달 시간을 단축시킵니다. **부스터 가속(Turbo)**과 **별값(Star Price)**을 통해 평단가보다 훨씬 낮은 지점에서 강력한 한 방을 노립니다.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-[#121214] p-3.5 rounded-xl border border-orange-900/20">
              <span className="text-orange-400 text-[0.6rem] font-black block mb-1">🐎 TURBO</span>
              <p className="text-[0.6rem] text-gray-500 leading-normal">-5% 급락 지점 선제 매매로 탈출 기회 창출</p>
            </div>
            <div className="bg-[#121214] p-3.5 rounded-xl border border-orange-900/20">
              <span className="text-yellow-500 text-[0.6rem] font-black block mb-1">💫 STAR PRICE</span>
              <p className="text-[0.6rem] text-gray-500 leading-normal">황금 비율 타겟 매수로 불필요한 매치 최소화</p>
            </div>
          </div>
        </div>

        {/* Step 3: Secret Sniper */}
        <div className="bg-[#18181b] rounded-2xl border border-purple-500/30 p-8 shadow-[0_0_30px_rgba(168,85,247,0.05)] group">
          <div className="flex items-center gap-4 mb-5">
            <span className="text-3xl font-black text-purple-500/30">03</span>
            <h3 className="text-xl font-bold text-white tracking-tight">Step 3: 무한 동력 (The Engine)</h3>
          </div>
          <p className="text-gray-400 text-xs leading-relaxed mb-6">
            원금을 늘리지 않고 수익을 불리는 **V17 시크릿 스나이퍼**입니다. 1/4 익절 후 즉각적인 저점 재매수를 통해 시드 효율을 1.5배 이상 끌어올립니다.
          </p>
          <div className="bg-purple-950/10 p-4 rounded-xl border border-purple-900/20 italic text-[0.65rem] text-gray-400 leading-relaxed">
             "고점에서 팔고, 그 수익으로 저점에서 다시 주워 담는 이 과정은 계좌의 심장박동과도 같습니다. 시드가 늘어나지 않아도 수익은 무한히 순환됩니다."
          </div>
        </div>
      </div>

      {/* 👑 Step 4: Shadow-Strike (V24 Evolution) */}
      <div className="bg-[#18181b] rounded-3xl border border-indigo-500/40 p-10 shadow-2xl relative overflow-hidden group">
        <div className="absolute top-0 right-0 p-10 opacity-5 group-hover:opacity-10 transition-opacity font-serif">
          <span className="text-9xl font-black italic">V24</span>
        </div>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-4xl font-black text-indigo-500/40 tracking-tighter uppercase italic">Next Gen</span>
          <h3 className="text-2xl font-black text-indigo-400 tracking-tight">Step 4: 섀도우 스트라이크 (Shadow-Strike)</h3>
        </div>
        <p className="text-gray-300 text-sm leading-relaxed mb-8 max-w-4xl">
          LOC 매매의 물리적 한계를 정밀 데이터 분석으로 극복한 **V24 Shadow-Strike** 엔진입니다. 단순히 종가에 사는 것이 아니라, 장중 저점 대비 **1.5% 반등(Bounce)** 지점을 추적하여 최적의 눌림목에서 공격적으로 물량을 확보합니다.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-[#121214] p-5 rounded-2xl border border-[#27272a] hover:border-indigo-500/20 transition-colors">
            <h4 className="text-indigo-400 font-bold text-xs mb-3 flex items-center gap-2">👤 저점 추격 (Shadow Pricing)</h4>
            <p className="text-[0.7rem] text-gray-500 leading-relaxed italic">
              "평단가보다 조금 비싸더라도, 당일 저점 대비 충분히 눌림목이 형성되었다면 매수를 실행합니다. 이는 상승장에서 체결을 놓치는 기회비용을 80% 이상 회수합니다."
            </p>
          </div>
          <div className="bg-[#121214] p-5 rounded-2xl border border-[#27272a] hover:border-indigo-500/20 transition-colors">
            <h4 className="text-indigo-400 font-bold text-xs mb-3 flex items-center gap-2">⚖️ 스마트 시드 리밸런싱</h4>
            <p className="text-[0.7rem] text-gray-500 leading-relaxed italic">
              "전략 중단 없이 수익 실현(졸업) 시점에 전체 자산을 재계산하여 타겟 비중(TQQQ 55: SOXL 45)대로 시드를 즉시 재배치, 복합 성장을 무한히 유도합니다."
            </p>
          </div>
        </div>
      </div>

      {/* 🔐 System Integrity Signal Guide */}
      <div className="bg-[#18181b] rounded-2xl border border-gray-700/20 p-8">
        <h3 className="text-white font-bold text-xs mb-6 uppercase tracking-widest flex items-center gap-2">
           🕹️ 전술 시그널 해설 <span className="text-[0.6rem] text-gray-500 font-normal">(Icon Legend)</span>
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div><span className="text-red-400 font-bold text-[0.65rem] block mb-1">⚓ 평단매수</span><p className="text-[0.6rem] text-gray-600">안정적 기초 물량</p></div>
          <div><span className="text-yellow-400 font-bold text-[0.65rem] block mb-1">💫 별값매수</span><p className="text-[0.6rem] text-gray-600">최적의 탈출 지점</p></div>
          <div><span className="text-orange-400 font-bold text-[0.65rem] block mb-1">🏎️ 가속매수</span><p className="text-[0.6rem] text-gray-600">위기 상황 돌파구</p></div>
          <div><span className="text-green-400 font-bold text-[0.65rem] block mb-1">🧹 줍줍(1~5)</span><p className="text-[0.6rem] text-gray-600">물량 확장 거미줄</p></div>
        </div>
      </div>
    </div>
  )
}
