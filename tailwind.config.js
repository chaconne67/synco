/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './accounts/templates/**/*.html',
    './candidates/templates/**/*.html',
    './candidates/static/**/*.js',
    './clients/templates/**/*.html',
    './projects/templates/**/*.html',
    './projects/static/**/*.js',
  ],
  theme: {
    extend: {
      fontFamily: {
        // Plus Jakarta Sans for Latin glyphs, Pretendard for Korean (auto fallback by glyph coverage)
        sans: [
          '"Plus Jakarta Sans"',
          'Pretendard',
          '-apple-system',
          'BlinkMacSystemFont',
          'system-ui',
          'sans-serif',
        ],
      },
      fontSize: {
        'display': ['32px', { lineHeight: '1.2', letterSpacing: '-0.02em', fontWeight: '700' }],
        'heading': ['24px', { lineHeight: '1.3', fontWeight: '700' }],
        'subheading': ['18px', { lineHeight: '1.4', fontWeight: '600' }],
        'micro': ['12px', { lineHeight: '1.4', fontWeight: '400', letterSpacing: '0.05em' }],
      },
      keyframes: {
        'pulse-hint': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.2' },
        },
      },
      animation: {
        'pulse-hint': 'pulse-hint 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      colors: {
        // Dashboard-based design tokens (synco-dashboard.zip as source of truth)
        primary: {
          DEFAULT: '#2563EB', // blue-600
          dark: '#1D4ED8',    // blue-700
          light: '#DBEAFE',   // blue-100
        },
        sidebar: '#0F172A',   // slate-900
        canvas: '#F8FAFC',    // slate-50
        ink: {
          DEFAULT: '#0F172A', // slate-900
          muted: '#64748B',   // slate-500
          soft: '#94A3B8',    // slate-400
        },
      },
    },
  },
  plugins: [],
}
