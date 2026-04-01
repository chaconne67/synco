# synco Design System

## Typography

**Font:** Pretendard (웹폰트 CDN)
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.min.css">
```

**Tailwind config:**
```js
fontFamily: {
  sans: ['Pretendard', '-apple-system', 'BlinkMacSystemFont', 'system-ui', 'sans-serif'],
}
```

**Scale:**
- Display: 28px / bold / -0.02em
- Heading: 20px / bold
- Subheading: 16px / semibold
- Body: 14px / regular
- Caption: 12px / regular
- Micro: 10px / regular / tracking-wider

## Colors

**Primary:** `#5B6ABF` (synco indigo)
**Primary Dark:** `#4A59AE` (hover/active)
**Primary Light:** `#E8EAFF` (backgrounds)

**Semantic:**
- Success: `#22C55E` (green-500)
- Warning: `#F59E0B` (amber-500)
- Error: `#EF4444` (red-500)
- Info: `#3B82F6` (blue-500)

**Neutral:**
- Text Primary: `#111827` (gray-900)
- Text Secondary: `#6B7280` (gray-500)
- Text Tertiary: `#9CA3AF` (gray-400)
- Border: `#E5E7EB` (gray-200)
- Background: `#F9FAFB` (gray-50)
- Surface: `#FFFFFF`

**Relationship Health (Contact staleness):**
- Fresh (< 7일): `#22C55E` (green)
- Warm (7-30일): `#F59E0B` (amber)
- Cold (30일+): `#EF4444` (red)

## Spacing

4px 배수 시스템. Tailwind 기본 scale 사용.
- 4px (p-1), 8px (p-2), 12px (p-3), 16px (p-4), 20px (p-5), 24px (p-6), 32px (p-8)

**Component 내부:** p-3 ~ p-5
**섹션 간격:** mb-4 ~ mb-6
**페이지 패딩:** px-4

## Border Radius

용도별 차별화:
- Card: `rounded-2xl` (16px)
- Button: `rounded-lg` (12px)
- Input: `rounded-lg` (8px)
- Badge/Chip: `rounded-full`
- Modal bottom sheet: `rounded-t-2xl`

## Components

### Card
```
bg-white rounded-2xl border border-gray-100 p-4
```
hover 시: `hover:bg-gray-50 transition`

### Button (Primary)
```
bg-primary text-white font-semibold py-3 px-5 rounded-lg text-sm
```
hover: `hover:bg-primary-dark`

### Button (Secondary)
```
border border-gray-200 text-gray-700 font-semibold py-3 px-5 rounded-lg text-sm
```

### Input
```
w-full px-4 py-3 border border-gray-200 rounded-lg text-sm
focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20
```

### Bottom Nav
4탭 고정: 홈 / 연락처 / 매칭 / 설정
Active: `text-primary font-semibold`
Inactive: `text-gray-400`

### Toast (Success)
```
fixed bottom-24 left-1/2 -translate-x-1/2 bg-gray-900 text-white px-5 py-3 rounded-lg text-sm
```
3초 후 자동 사라짐.

### Skeleton Loading
```
animate-pulse bg-gray-200 rounded-lg
```

## Responsive Breakpoints

- **Mobile (default):** max-w-md mx-auto (< 768px)
- **Tablet (md):** max-w-2xl, 2-column where appropriate
- **Desktop (lg):** max-w-5xl, sidebar nav + main content

Mobile은 bottom nav, tablet/desktop은 left sidebar nav로 전환.

## Accessibility

- Touch target: 최소 44px
- Color contrast: WCAG AA (4.5:1)
- ARIA landmarks: `<nav>`, `<main>`, `<header>`
- Keyboard: Tab 순서, Enter/Space 활성화
- `user-scalable=yes` (줌 허용)
- Focus visible: `focus-visible:ring-2 focus-visible:ring-primary`
