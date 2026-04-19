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
  safelist: [
    // 동적 클래스명 (Django 템플릿에서 col-pill/col-container-{{ column_key }} 형태로 생성)
    'col-pill-searching',
    'col-pill-screening',
    'col-pill-closed',
    'col-container-searching',
    'col-container-screening',
    'col-container-closed',
    // av-{{ forloop.counter }} 동적 생성
    'av-1', 'av-2', 'av-3', 'av-4', 'av-5', 'av-6',
    // Client logo tile gradients — 8 variations
    'client-logo-1', 'client-logo-2', 'client-logo-3', 'client-logo-4',
    'client-logo-5', 'client-logo-6', 'client-logo-7', 'client-logo-8',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          '"Pretendard Variable"',
          'Pretendard',
          '-apple-system',
          'BlinkMacSystemFont',
          'system-ui',
          'sans-serif',
        ],
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
        // synco design tokens — ui-sample/*.html 기준
        canvas:   '#F8FAFC',  // 페이지 배경
        surface:  '#FFFFFF',  // 카드/시트
        ink:      '#0F172A',  // 주 텍스트, dark 사이드바
        ink2:     '#1E293B',  // 보조 dark
        ink3:     '#334155',  // 버튼/강조 텍스트
        muted:    '#64748B',  // 본문 보조 텍스트
        faint:    '#94A3B8',  // 약한 라벨·아이콘
        hair:     '#E2E8F0',  // 카드 외곽선
        line:     '#F1F5F9',  // 구분선, 옅은 배경
        success:  '#10B981',
        warning:  '#F59E0B',
        info:     '#6366F1',
        danger:   '#EF4444',
      },
      boxShadow: {
        'card': '0 1px 2px 0 rgba(15,23,42,0.04), 0 1px 3px 0 rgba(15,23,42,0.06)',
        'lift': '0 4px 6px -1px rgba(15,23,42,0.08), 0 2px 4px -2px rgba(15,23,42,0.04)',
        'fab':  '0 10px 15px -3px rgba(15,23,42,0.15), 0 4px 6px -2px rgba(15,23,42,0.08)',
        'searchbar': '0 10px 40px -10px rgba(15,23,42,0.18), 0 4px 12px -4px rgba(15,23,42,0.08)',
      },
      borderRadius: {
        'card': '16px',
      },
    },
  },
  plugins: [],
}
