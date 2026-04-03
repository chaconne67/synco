/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './accounts/templates/**/*.html',
    './candidates/templates/**/*.html',
    './candidates/static/**/*.js',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Pretendard', '-apple-system', 'BlinkMacSystemFont', 'system-ui', 'sans-serif'],
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
        primary: {
          DEFAULT: '#4A56A8',
          dark: '#3D4891',
          light: '#E8EAFF',
        },
      },
    },
  },
  plugins: [],
}
