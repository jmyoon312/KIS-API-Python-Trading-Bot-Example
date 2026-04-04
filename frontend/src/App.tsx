import { useState } from 'react'
import Dashboard from './components/Dashboard'
import SystemControl from './components/SystemControl'
import PerformanceAnalytics from './components/PerformanceAnalytics'
import LedgerExplorer from './components/LedgerExplorer'
import SimulationTestbed from './components/SimulationTestbed'
import Login from './components/Login'
import { Toaster } from 'react-hot-toast'

type TabKey = 'terminal' | 'system' | 'ledger' | 'archive' | 'simulator'

const TABS: { key: TabKey; icon: string; label: string }[] = [
  { key: 'terminal',  icon: '💻', label: '상황실' },
  { key: 'system',    icon: '⚙️', label: '제어' },
  { key: 'ledger',    icon: '📒', label: '장부' },
  { key: 'archive',   icon: '📊', label: '분석' },
  { key: 'simulator', icon: '🧪', label: '연구소' },
]

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(!!localStorage.getItem('inf_token'))
  const [activeTab, setActiveTab] = useState<TabKey>('terminal')
  const [isAutoRefresh, setIsAutoRefresh] = useState(true)
  const [activeMode, setActiveMode] = useState<'mock' | 'real'>(
    (localStorage.getItem('inf_mode') as 'mock' | 'real') || 'mock'
  )

  if (!isAuthenticated) {
    return <Login onLogin={(mode) => {
      setActiveMode(mode as any)
      setIsAuthenticated(true)
    }} />
  }

  const handleLogout = () => {
    localStorage.removeItem('inf_token')
    setIsAuthenticated(false)
  }

  return (
    <div className="min-h-screen bg-[#09090b] text-white font-sans selection:bg-yellow-500 selection:text-black pb-24 max-w-md mx-auto relative shadow-2xl">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[#09090b]/95 backdrop-blur-md border-b border-[#27272a]/50 px-4 pt-4 pb-0">
        {/* Title Row */}
        <div className="flex justify-between items-center mb-3">
          <h1 className="text-lg font-black flex items-center text-white tracking-tight">
            <span className="mr-1.5 text-lg">♾️</span>Infinity Quant Hub
          </h1>
          <div className="flex items-center gap-2">
            {/* Mode Toggle Button (V23.1 New) */}
            <button 
              onClick={() => {
                const next = activeMode === 'real' ? 'mock' : 'real'
                setActiveMode(next)
                localStorage.setItem('inf_mode', next)
              }}
              className={`text-[0.65rem] font-bold px-2 py-1 rounded-full border transition-all ${
                activeMode === 'real' 
                ? 'border-blue-500 text-blue-400 bg-blue-900/40 shadow-[0_0_10px_rgba(59,130,246,0.5)]' 
                : 'border-emerald-500 text-emerald-400 bg-emerald-900/40'
              }`}
            >
              {activeMode === 'real' ? '🚀 REAL' : '🧪 MOCK'}
            </button>

            {/* Auto refresh toggle */}
            <button 
              onClick={() => setIsAutoRefresh(!isAutoRefresh)}
              className={`flex items-center gap-1.5 text-[0.65rem] font-bold px-2 py-1 rounded-full border transition-all ${
                isAutoRefresh 
                ? (activeMode === 'real' ? 'border-blue-500/50 text-blue-400 bg-blue-900/20' : 'border-emerald-500/50 text-emerald-400 bg-emerald-900/20') 
                : 'border-[#3f3f46] text-gray-500 bg-transparent'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${
                isAutoRefresh 
                ? (activeMode === 'real' ? 'bg-blue-500 animate-pulse' : 'bg-emerald-500 animate-pulse') 
                : 'bg-gray-600'
              }`}></span>
              LIVE
            </button>
            {/* Logout */}
            <button 
              onClick={handleLogout}
              className="text-gray-500 hover:text-red-400 transition-colors text-xs font-bold px-2 py-1 rounded-full border border-[#27272a] hover:border-red-500/30"
              title="로그아웃"
            >
              🔓
            </button>
          </div>
        </div>

        {/* Navigation Tabs - Bottom Tab Bar Style */}
        <nav className="flex -mx-4 px-1">
          {TABS.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex-1 py-2.5 text-xs font-bold flex flex-col items-center gap-0.5 transition-all relative ${
                activeTab === tab.key ? 'text-white' : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              <span className="text-base">{tab.icon}</span>
              <span className="tracking-wider">{tab.label}</span>
              {activeTab === tab.key && (
                <div className={`absolute bottom-0 left-1/4 right-1/4 h-[2px] rounded-full ${
                  activeMode === 'real' ? 'bg-gradient-to-r from-blue-500 to-cyan-400' : 'bg-gradient-to-r from-emerald-500 to-teal-400'
                }`}></div>
              )}
            </button>
          ))}
        </nav>
      </header>

      {/* Main Content */}
      <main className="px-4 mt-4 animate-fade-in-up">
        {activeTab === 'terminal' && <Dashboard isAutoRefresh={isAutoRefresh} mode={activeMode} />}
        {activeTab === 'system' && <SystemControl mode={activeMode} />}
        {activeTab === 'ledger' && <LedgerExplorer mode={activeMode} />}
        {activeTab === 'archive' && <PerformanceAnalytics mode={activeMode} />}
        {activeTab === 'simulator' && <SimulationTestbed />}
      </main>

      <Toaster 
        position="top-right" 
        toastOptions={{ 
          style: { background: '#18181b', color: '#fff', border: '1px solid #27272a', fontSize: '12px', fontWeight: 'bold' } 
        }} 
      />
    </div>
  )
}

export default App
