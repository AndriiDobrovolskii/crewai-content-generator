/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // REACTOR dark theme palette
        void:    '#070710',
        surface: '#0e0e1a',
        panel:   '#13131f',
        border:  '#1e1e30',
        muted:   '#2a2a40',
        // Text
        ink:     '#e2e2f0',
        dim:     '#8888aa',
        ghost:   '#44445a',
        // Accents
        violet: {
          DEFAULT: '#7c3aed',
          light:   '#a78bfa',
          glow:    'rgba(124,58,237,0.25)',
        },
        cyan: {
          DEFAULT: '#06b6d4',
          light:   '#67e8f9',
          glow:    'rgba(6,182,212,0.2)',
        },
        emerald: { DEFAULT: '#10b981' },
        rose:    { DEFAULT: '#f43f5e' },
        amber:   { DEFAULT: '#f59e0b' },
      },
      fontFamily: {
        ui:   ['DM Sans', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      boxShadow: {
        panel:   '0 0 0 1px rgba(124,58,237,0.15), 0 4px 24px rgba(0,0,0,0.4)',
        glow:    '0 0 20px rgba(124,58,237,0.3)',
        'glow-cyan': '0 0 20px rgba(6,182,212,0.25)',
      },
      animation: {
        'pulse-slow':  'pulse 3s cubic-bezier(0.4,0,0.6,1) infinite',
        'slide-in':    'slideIn 0.2s ease-out',
        'fade-in':     'fadeIn 0.3s ease-out',
        'blink':       'blink 1s step-end infinite',
      },
      keyframes: {
        slideIn: {
          '0%':   { transform: 'translateX(-8px)', opacity: '0' },
          '100%': { transform: 'translateX(0)',    opacity: '1' },
        },
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        blink: {
          '0%,100%': { opacity: '1' },
          '50%':     { opacity: '0' },
        },
      },
    },
  },
  plugins: [],
}
