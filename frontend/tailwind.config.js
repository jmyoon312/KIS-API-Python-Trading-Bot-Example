/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        neon: {
          blue: '#14fdfc',
          pink: '#fe01b1',
          green: '#39ff14',
          purple: '#b92b27',
        },
        dark: {
          900: '#0a0a0f',
          800: '#13131a',
          700: '#1c1c24',
          600: '#282936',
        }
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(20, 253, 252, 0.2)' },
          '100%': { boxShadow: '0 0 20px rgba(20, 253, 252, 0.6)' }
        }
      }
    },
  },
  plugins: [],
}
