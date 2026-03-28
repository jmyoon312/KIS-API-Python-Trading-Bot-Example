@echo off
title Infinity Quant Hub - PWA Deploy
echo ==========================================
echo Deploying PWA Feature to Production Server
echo ==========================================

set USER_NAME=jmyoon312
set DISTRO=Ubuntu-24.04
set FRONTEND=/home/%USER_NAME%/frontend

echo [1/6] Copying updated vite.config.ts...
wsl -d %DISTRO% -u %USER_NAME% bash -c "cat > %FRONTEND%/vite.config.ts << 'VITEEOF'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'apple-touch-icon.png', 'mask-icon.svg'],
      manifest: {
        name: 'Infinity Quant Hub',
        short_name: 'InfinityHub',
        description: 'V22 Quant Dashboard System',
        theme_color: '#000000',
        background_color: '#000000',
        display: 'standalone',
        icons: [
          {
            src: 'pwa-192x192.png',
            sizes: '192x192',
            type: 'image/png'
          },
          {
            src: 'pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png'
          }
        ]
      }
    })
  ],
  server: {
    allowedHosts: true,
  }
})
VITEEOF"

echo [2/6] Patching App.tsx for auto-login...
wsl -d %DISTRO% -u %USER_NAME% bash -c "cd %FRONTEND%/src && sed -i \"s/import { useState } from 'react'/import { useState, useEffect } from 'react'/\" App.tsx"
wsl -d %DISTRO% -u %USER_NAME% bash -c "cd %FRONTEND%/src && sed -i '/const \[isAutoRefresh/a\\n  \/\/ Auto-login: restore token from localStorage (1-person optimization)\n  useEffect(() => {\n    const savedToken = localStorage.getItem(\"inf_token\")\n    if (savedToken) {\n      setIsAuthenticated(true)\n    }\n  }, [])' App.tsx"

echo [3/6] Installing vite-plugin-pwa in production...
wsl -d %DISTRO% -u %USER_NAME% bash -c "cd %FRONTEND% && npm install vite-plugin-pwa --save-dev --no-fund --no-audit"

echo [4/6] Removing legacy Tailwind v3 config files...
wsl -d %DISTRO% -u %USER_NAME% bash -c "cd %FRONTEND% && rm -f tailwind.config.js postcss.config.js"

echo [5/6] Updating web_server.py token expiry to 1 year...
wsl -d %DISTRO% -u %USER_NAME% bash -c "cd /home/%USER_NAME% && sed -i 's/ACCESS_TOKEN_EXPIRE_MINUTES = 120/ACCESS_TOKEN_EXPIRE_MINUTES = 525600  # 1 year/' web_server.py 2>/dev/null; exit 0"

echo [6/6] Generating PWA icon placeholder...
wsl -d %DISTRO% -u %USER_NAME% bash -c "cd %FRONTEND%/public && python3 -c \"
import base64, os
# Create a simple blue shield SVG as PWA icon
svg = '''<svg xmlns='http://www.w3.org/2000/svg' width='512' height='512' viewBox='0 0 512 512'>
<rect width='512' height='512' fill='#000000'/>
<path d='M256 48l160 80v160c0 88-64 168-160 192C160 456 96 376 96 288V128L256 48z' fill='#1e40af' stroke='#3b82f6' stroke-width='8'/>
<text x='256' y='310' text-anchor='middle' fill='white' font-size='120' font-weight='bold' font-family='Arial'>∞</text>
</svg>'''
with open('pwa-512x512.png', 'w') as f:
    f.write(svg.replace('.png','.svg'))
os.rename('pwa-512x512.png', 'pwa-512x512.svg')
\" 2>/dev/null; exit 0"

echo.
echo ==========================================
echo PWA DEPLOYMENT COMPLETE!
echo ==========================================
echo Now restart the frontend server using 1_run_infinity_hub.bat
echo Then access the site on your phone and look for "Install App" prompt!
echo ==========================================
pause
