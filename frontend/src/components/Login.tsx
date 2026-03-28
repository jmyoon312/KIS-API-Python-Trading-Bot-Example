import { useState } from 'react'
import axios from 'axios'

export default function Login({ onLogin }: { onLogin: (mode: string) => void }) {
  const [id, setId] = useState('')
  const [password, setPassword] = useState('')
  const [mode, setMode] = useState<'mock' | 'real'>('mock')
  const [errorMsg, setErrorMsg] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrorMsg('')
    
    if (!id || !password) {
      setErrorMsg('ID와 비밀번호를 모두 입력해주세요.')
      return
    }

    try {
      setIsLoading(true)
      const api = axios.create({ baseURL: '/api' })
      const res = await api.post('/auth', { user_id: id, password: password })
      
      if (res.data.status === 'ok') {
        localStorage.setItem('inf_token', res.data.token)
        localStorage.setItem('inf_mode', mode) // 🌐 V23.1 선택한 모드 기억
        onLogin(mode)
      }
    } catch (err: any) {
      if (err.response && err.response.status === 401) {
        setErrorMsg('접근 거부: 총사령관 ID 또는 암호가 일치하지 않습니다.')
      } else {
        setErrorMsg('API 서버(포트 5050)에 연결할 수 없습니다.')
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#09090b] flex flex-col items-center justify-center p-6 font-sans">
      <div className="w-full max-w-sm space-y-8 animate-fade-in-up">
        
        {/* Shield Icon Area */}
        <div className="flex justify-center mb-6">
          <div className="text-7xl drop-shadow-[0_0_15px_rgba(255,255,255,0.3)]">🛡️</div>
        </div>

        {/* Titles */}
        <div className="text-center space-y-4 mb-10">
          <h1 className="text-3xl font-black tracking-widest text-white drop-shadow-md">
            SNIPER COMMAND
          </h1>
          <h2 className="text-2xl font-bold text-neon-blue drop-shadow-[0_0_10px_rgba(59,130,246,0.8)]">
            ✨ Infinity Quant Hub ✨
          </h2>
          <div className="pt-4 text-gray-400 text-sm leading-relaxed">
            <p>V22.2 다이내믹 스노우볼 TrueSync</p>
            <p><strong className="text-yellow-500">인가된 총사령관</strong>만 접근을 허가합니다.</p>
          </div>
        </div>

        {/* Login Form */}
        <form onSubmit={handleLogin} className="space-y-4 w-full">
          <div>
            <label className="block text-gray-400 text-xs font-bold mb-2 ml-1">
              총사령관 ID
            </label>
            <input 
              type="text" 
              placeholder="인가된 총사령관 ID" 
              className="w-full bg-[#1c1c1e] text-white border border-[#2c2c2e] rounded-xl px-4 py-3.5 focus:outline-none focus:border-gray-500 transition-colors text-sm"
              value={id}
              onChange={e => setId(e.target.value)}
              required
            />
          </div>
          <div className="relative">
            <input 
              type={showPassword ? "text" : "password"}
              placeholder="보안 암호를 입력하세요" 
              className="w-full bg-[#1c1c1e] text-white border border-[#2c2c2e] rounded-xl px-4 py-3.5 focus:outline-none focus:border-gray-500 transition-colors text-sm pr-12"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
            />
            <button 
              type="button" 
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-4 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-white transition-colors"
            >
              {showPassword ? '🙈' : '👁️'}
            </button>
          </div>
          
          {/* 🌐 [V23.1] 매매 모드 선택기 */}
          <div className="flex bg-[#1c1c1e] p-1 rounded-2xl border border-[#2c2c2e] gap-1">
            <button
              type="button"
              onClick={() => setMode('mock')}
              className={`flex-1 py-3 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 ${
                mode === 'mock' 
                ? 'bg-[#10b981] text-white shadow-[0_0_15px_rgba(16,185,129,0.3)]' 
                : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              <span className="text-base">🧪</span> 모의 투자
            </button>
            <button
              type="button"
              onClick={() => setMode('real')}
              className={`flex-1 py-3 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 ${
                mode === 'real' 
                ? 'bg-[#3b82f6] text-white shadow-[0_0_15px_rgba(59,130,246,0.3)]' 
                : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              <span className="text-base">🚀</span> 실전 투자
            </button>
          </div>
          
          <div className="pt-2 min-h-[24px]">
            {errorMsg && <p className="text-red-500 text-xs font-bold text-center animate-pulse">{errorMsg}</p>}
          </div>

          <div className="pt-2">
            <button 
              type="submit" 
              disabled={isLoading}
              className={`w-full bg-[#1c1c1e] text-white font-bold py-3.5 px-4 rounded-xl border border-[#2c2c2e] transition-colors text-sm flex justify-center items-center shadow-lg ${isLoading ? 'opacity-50 cursor-not-allowed' : 'hover:bg-[#2c2c2e]'}`}
            >
              <span className="mr-2 text-lg">🚀</span> {isLoading ? '시스템 검증 중...' : '시스템 접근 허가 요청'}
            </button>
          </div>
        </form>

      </div>
    </div>
  )
}
