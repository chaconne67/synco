# synco UI/UX Review Checklist

**리뷰 일자:** 2026-03-29
**리뷰 범위:** 로그인, 대시보드, 연락처(목록/상세/폼), 미팅, 매칭, 설정, 임포트
**테스트 뷰포트:** Mobile (375x812), Tablet (768x1024), Desktop (1280x720)
**리뷰 방법:** 브라우저 실행(headless) + 소스코드 감사(병렬)

---

## 1. 터치 타깃 (Touch Targets) — DESIGN.md 기준: 최소 44px

| # | 항목 | 현재 상태 | 심각도 | 위치 |
|---|------|----------|--------|------|
| 1.1 | 대시보드 업무 완료 버튼 (체크 원) | **20x20px** — 44px 미달 | **HIGH** | `_task_card.html:2` `w-5 h-5` |
| 1.2 | 대시보드 업무 수정 버튼 | **22x22px** — 44px 미달 (p-1 + w-3.5 = 22px) | **HIGH** | `_task_card.html:15-19` |
| 1.3 | 대시보드 업무 삭제 버튼 | **22x22px** — 44px 미달 | **HIGH** | `_task_card.html:21-27` |
| 1.4 | 대시보드 "+ 추가" 텍스트 버튼 | **36x20px** — 높이 미달 | **HIGH** | `section_tasks.html:9-10` |
| 1.5 | 사이드바 아바타 "김" 링크 | **36x36px** — 44px 미달 | **MEDIUM** | 사이드바 프로필 아이콘 |
| 1.6 | 연락처 필터 칩 (전체/제조/유통 등) | 높이 **28px** — 44px 미달 | **MEDIUM** | `contact_list.html:71-100` `py-1.5` |
| 1.7 | 연락처 상세 탭 버튼 (메모/미팅) | 확인 필요 — 탭 높이가 터치 기준 미달 가능 | **MEDIUM** | `contact_detail.html` |
| 1.8 | 상호작용 타임라인 수정/삭제 아이콘 | **22px** — `p-1` + `w-3.5` = 18px 렌더 | **HIGH** | `interaction_timeline.html:34-48` |

**수정 방법:** 각 버튼에 `min-w-[44px] min-h-[44px]` 적용. 아이콘 버튼은 `p-2.5` 이상으로 패딩 확대. 필터 칩은 `py-2.5`로 높이 확보.

---

## 2. 반응형 디자인 (Responsive)

| # | 항목 | 현재 상태 | 심각도 | 위치 |
|---|------|----------|--------|------|
| 2.1 | 모바일 main content `pb-20` | base.html에 `pb-20 lg:pb-0` 설정됨 — **OK** | PASS | `base.html:52` |
| 2.2 | 미팅/매칭 빈 상태 페이지 — 하단 여백 | 콘텐츠 아래 **회색 빈 영역**이 화면 절반 차지 | **MEDIUM** | `meeting_list_content.html:39-48` |
| 2.3 | 데스크탑 연락처 목록 — 정보 밀도 부족 | 와이드 화면에서 한 줄에 이름+회사만 표시, 공간 낭비 | **LOW** | `contact_list_items.html` |
| 2.4 | 태블릿(768px) 레이아웃 | max-w-md 적용으로 모바일과 동일 — 태블릿 고유 레이아웃 없음 | **LOW** | `base.html:44` |
| 2.5 | `env(safe-area-inset-bottom)` 미적용 | 노치 기기에서 하단 내비가 잘릴 수 있음 | **MEDIUM** | `nav_bottom.html` |
| 2.6 | 연락처 폼 — 모바일 제출 버튼 | 하단 고정 CTA가 bottom nav와 겹침 | **HIGH** | `contact_form.html` |
| 2.7 | 수평 스크롤 없음 | 모든 뷰포트에서 수평 오버플로 없음 — **OK** | PASS | 전체 |
| 2.8 | 데스크탑 사이드바 ↔ 모바일 바텀 내비 전환 | lg 브레이크포인트에서 올바르게 전환 — **OK** | PASS | `base.html:47-58` |

**수정 방법:**
- 2.2: 빈 상태 래퍼에 `min-h-[calc(100vh-200px)]` 또는 `flex-1` 적용
- 2.5: 바텀 내비에 `pb-[env(safe-area-inset-bottom)]` 추가
- 2.6: 제출 버튼에 `mb-20 lg:mb-0` 또는 `sticky bottom-20` 적용

---

## 3. 타이포그래피 (Typography) — DESIGN.md 스케일 준수 여부

| # | 항목 | 현재 상태 | 심각도 | 위치 |
|---|------|----------|--------|------|
| 3.1 | 폰트 통일성 | Pretendard 단일 폰트 — **OK** | PASS | 전체 |
| 3.2 | H1 "synco" 로고 | 20px bold — DESIGN.md Display 28px과 다름 | **LOW** | `nav_sidebar.html:2` |
| 3.3 | H2 인사말 "김문형님, 좋은 아침이에요" | 22px — DESIGN.md Heading 20px과 미세 차이 | **LOW** | 대시보드 |
| 3.4 | H3 섹션 제목 | 16px semibold — Subheading 기준과 일치 — **OK** | PASS | 전체 |
| 3.5 | Body 텍스트 | 14px regular — **OK** | PASS | 전체 |
| 3.6 | 바텀 내비 라벨 | `text-[10px]` = 10px — Micro 기준과 일치 — **OK** | PASS | `nav_bottom.html:9` |
| 3.7 | 연락처 필터 칩 텍스트 | `text-xs` = 12px — **OK** | PASS | `contact_list.html` |
| 3.8 | 데스크탑 본문 줄 길이 | max-w 미설정 시 한 줄이 75자 초과 가능 | **LOW** | 데스크탑 |

---

## 4. 컬러 시스템 (Color System)

| # | 항목 | 현재 상태 | 심각도 | 위치 |
|---|------|----------|--------|------|
| 4.1 | Primary `#5B6ABF` 일관 사용 | Tailwind config로 통일 — **OK** | PASS | `base.html:22-26` |
| 4.2 | 시맨틱 컬러 사용 | 에러에 `text-red-400` (밝은 톤), `text-amber-700` (경고) 적절 사용 | PASS | 전체 |
| 4.3 | 관계 건강도 이모지 | 🔴🟡🟢⚪ 이모지 — 색각 이상자에게는 텍스트 보조 필요 | **MEDIUM** | `contact_list_items.html:10` |
| 4.4 | 비활성 상태 회색 톤 일관성 | gray-400, gray-500 혼용 — 통일 권장 | **LOW** | 전체 |
| 4.5 | 임포트 CTA 비활성 | `bg-primary/50` 처리 — 비활성 의도 전달 적절 | PASS | `import.html` |

---

## 5. 스페이싱 & 레이아웃 (Spacing & Layout)

| # | 항목 | 현재 상태 | 심각도 | 위치 |
|---|------|----------|--------|------|
| 5.1 | 4px 배수 시스템 준수 | 대부분 Tailwind 기본 스케일 사용 — **OK** | PASS | 전체 |
| 5.2 | 페이지 패딩 `px-4` | 전체적으로 일관 — **OK** | PASS | 전체 |
| 5.3 | 섹션 간격 | 대시보드 `mb-6`, 연락처 `mb-3` — 적절 | PASS | 전체 |
| 5.4 | 카드 내부 패딩 | `p-4` ~ `p-5` 일관 — **OK** | PASS | 전체 |
| 5.5 | 연락처 목록 카드 간격 | `mb-3` — 적절 | PASS | `contact_list_items.html:7` |
| 5.6 | 설정 페이지 섹션 간 간격 | 카드 간격 적절, 내부 행간 일관 — **OK** | PASS | 설정 |

---

## 6. Border Radius 위계

| # | 항목 | 현재 상태 | 심각도 | 위치 |
|---|------|----------|--------|------|
| 6.1 | Card = `rounded-2xl` | 일관 적용 — **OK** | PASS | 전체 |
| 6.2 | Button = `rounded-lg` | 일관 적용 — **OK** | PASS | 전체 |
| 6.3 | Input = `rounded-lg` | 일관 적용 — **OK** | PASS | `contact_form.html` |
| 6.4 | Badge/Chip = `rounded-full` | 필터 칩에 일관 적용 — **OK** | PASS | `contact_list.html` |
| 6.5 | Task 완료 버튼 | `rounded-full` — 적절 | PASS | `_task_card.html:3` |

---

## 7. 인터랙션 상태 (Interaction States)

| # | 항목 | 현재 상태 | 심각도 | 위치 |
|---|------|----------|--------|------|
| 7.1 | hover 상태 | 버튼/링크에 `hover:` 클래스 적용 — **OK** | PASS | 전체 |
| 7.2 | `focus-visible` 링 | DESIGN.md에 정의되어 있으나 **실제 구현 없음** | **HIGH** | 전체 |
| 7.3 | active/pressed 상태 | 연락처 카드에 `active:bg-gray-50` — **OK** | PASS | `contact_list_items.html:7` |
| 7.4 | disabled 상태 | 임포트 CTA에 `opacity-50 cursor-not-allowed` — **OK** | PASS | `import.html` |
| 7.5 | 로딩 상태 (버튼) | 전역 스피너 핸들러 적용 — **OK** | PASS | `base.html:73-127` |
| 7.6 | 빈 상태 디자인 | 아이콘+메시지+CTA 구성 — **OK** | PASS | 연락처/미팅/매칭 |
| 7.7 | hx-confirm 삭제 확인 | 업무 삭제 시 `hx-confirm` 적용 — **OK** | PASS | `_task_card.html:22` |
| 7.8 | 업무 완료 시 시각적 피드백 | `hx-swap="outerHTML"` — 요소가 사라지나 성공 토스트 없음 | **MEDIUM** | `_task_card.html:2` |
| 7.9 | 페이지 전환 로딩 상태 | HTMX 네비게이션 시 로딩 인디케이터 없음 | **MEDIUM** | 전체 |

**수정 방법:**
- 7.2: 전역 CSS에 `*:focus-visible { outline: 2px solid #5B6ABF; outline-offset: 2px; }` 추가
- 7.8: 업무 완료 시 토스트 표시 or 체크 애니메이션 추가
- 7.9: `htmx:beforeRequest`에 프로그레스 바 또는 스켈레톤 추가

---

## 8. 접근성 (Accessibility)

| # | 항목 | 현재 상태 | 심각도 | 위치 |
|---|------|----------|--------|------|
| 8.1 | ARIA landmarks `<nav>`, `<main>` | nav 2개, main 1개 — **OK** | PASS | `base.html` |
| 8.2 | `<header>` 요소 | **없음** — 페이지 상단에 header 미사용 | **LOW** | 전체 |
| 8.3 | `aria-label` 속성 | **전무** — 아이콘 버튼에 aria-label 없음 | **HIGH** | 전체 |
| 8.4 | `user-scalable=yes` | 적용 — **OK** | PASS | `base.html:5` |
| 8.5 | 이미지 alt 텍스트 | 이미지 없음 (SVG 아이콘만 사용) — 해당 없음 | PASS | — |
| 8.6 | 아이콘 버튼 `title` 속성 | 수정/삭제에 `title` 있음 — 부분적 OK | PASS | `_task_card.html:16,23` |
| 8.7 | 색상 대비 | 본문 gray-900 on white: 15.3:1 — **OK** | PASS | 전체 |
| 8.8 | 보조 텍스트 대비 | gray-400 (#9CA3AF) on white: **2.9:1** — WCAG AA 미달 | **HIGH** | 전체 |
| 8.9 | `prefers-reduced-motion` 존중 | **미적용** | **LOW** | 전체 |

**수정 방법:**
- 8.3: 모든 아이콘 버튼에 `aria-label="수정"`, `aria-label="삭제"` 등 추가
- 8.8: gray-400 → gray-500 (#6B7280, 대비 4.6:1)으로 변경, 또는 gray-600 사용
- 8.9: `@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: 0.01ms !important; } }` 추가

---

## 9. 폼 UX (Form Usability)

| # | 항목 | 현재 상태 | 심각도 | 위치 |
|---|------|----------|--------|------|
| 9.1 | 필수 필드 표시 | 이름 필드에 `*` 표시 — **OK** | PASS | `contact_form.html` |
| 9.2 | 전화번호 입력 `type="tel"` | 적용 — **OK** | PASS | `contact_form.html` |
| 9.3 | 직원수 `type="number"` | 적용 — **OK** | PASS | `contact_form.html` |
| 9.4 | `autocomplete` 속성 | **미설정** — 브라우저 자동완성 미활용 | **LOW** | `contact_form.html` |
| 9.5 | 에러 메시지 표시 | 서버 validation 에러 시 필드 옆 표시 확인 필요 | **MEDIUM** | `contact_form.html` |
| 9.6 | 제출 후 중복 방지 | 전역 로딩 핸들러로 중복 전송 차단 — **OK** | PASS | `base.html:73-127` |
| 9.7 | 모바일 키보드 최적화 | `inputMode` 속성 미사용 — `tel`, `numeric` 등 권장 | **LOW** | `contact_form.html` |
| 9.8 | Select 드롭다운 모바일 | 네이티브 `<select>` 사용 — iOS/Android 최적 | PASS | `contact_form.html` |

---

## 10. HTMX 패턴 일관성

| # | 항목 | 현재 상태 | 심각도 | 위치 |
|---|------|----------|--------|------|
| 10.1 | 네비게이션 `hx-get` + `hx-target="#main-content"` + `hx-push-url` | 전체 일관 적용 — **OK** | PASS | 전체 |
| 10.2 | 폼 `hx-post` + specific target | 적절 사용 — **OK** | PASS | 업무/상호작용 |
| 10.3 | 필터 칩 URL 반영 | 필터 선택 시 `hx-push-url` **미적용** — 뒤로가기 시 필터 유실 | **MEDIUM** | `contact_list.html:71-100` |
| 10.4 | 무한스크롤 | `hx-trigger="revealed"` 적용 — **OK** | PASS | `contact_list_items.html:46-52` |
| 10.5 | 검색 디바운스 | `delay:300ms` 적용 — **OK** | PASS | `contact_list.html:59-62` |
| 10.6 | CSRF 토큰 | 전역 `hx-headers` 적용 — **OK** | PASS | `base.html:42` |

---

## 11. 성능 & 로딩

| # | 항목 | 현재 상태 | 심각도 | 위치 |
|---|------|----------|--------|------|
| 11.1 | 페이지 로드 성능 | TTFB 60ms, 전체 533ms — **우수** | PASS | 전체 |
| 11.2 | Tailwind CDN 사용 | **프로덕션 비권장** — 빌드 시스템 필요 | **MEDIUM** | `base.html:13` |
| 11.3 | 로그인 페이지 중복 설정 | Tailwind config가 base.html과 login.html에 **중복 정의** | **LOW** | `login.html:14-30` |
| 11.4 | HTMX CDN 버전 고정 | `htmx.org@2.0.4` — 고정 버전 사용 — **OK** | PASS | `base.html:34` |
| 11.5 | 스켈레톤 로딩 | DESIGN.md에 정의되어 있으나 실제 사용 제한적 | **LOW** | 대시보드 일부만 |
| 11.6 | PWA manifest | 존재 — **OK** | PASS | `base.html:37` |

---

## 12. 페이지별 세부 검토

### 12.1 로그인 페이지

| # | 항목 | 현재 상태 | 심각도 |
|---|------|----------|--------|
| 12.1.1 | 카카오 로그인 버튼 | 디자인 적절, 44px 이상 높이 — **OK** | PASS |
| 12.1.2 | 이용약관/개인정보 링크 | `text-xs text-gray-400` — 대비 부족 (2.9:1) | **MEDIUM** |
| 12.1.3 | 비주얼 구성 | 깔끔한 중앙 정렬, 브랜드 명확 — **OK** | PASS |
| 12.1.4 | `base.html` 미사용 | 별도 HTML로 Tailwind config 중복 | **LOW** |

### 12.2 대시보드

| # | 항목 | 현재 상태 | 심각도 |
|---|------|----------|--------|
| 12.2.1 | 인사말 | 시간대별 인사 — 사용자 경험 좋음 — **OK** | PASS |
| 12.2.2 | 오늘의 업무 섹션 | 기능적 OK. **터치 타깃 미달** (항목 1 참조) | **HIGH** |
| 12.2.3 | AI 브리핑 섹션 | 빈 상태: "아직 준비된 브리핑이 없습니다" — 적절 | PASS |
| 12.2.4 | 분석 현황 프로그레스 바 | 색상+퍼센트 표시 — **OK** | PASS |
| 12.2.5 | "주의 필요" 연락처 목록 | 빨간 이모지+행 구성 — 기능적 OK | PASS |
| 12.2.6 | 데스크탑에서 좌측 사이드바 내비 | 배경 gray-50, 적절한 활성 상태 — **OK** | PASS |

### 12.3 연락처 목록

| # | 항목 | 현재 상태 | 심각도 |
|---|------|----------|--------|
| 12.3.1 | 검색 바 | 디바운스 300ms, 즉시 결과 — **OK** | PASS |
| 12.3.2 | 필터 칩 수평 스크롤 | `overflow-x-auto` 적용 — **OK** | PASS |
| 12.3.3 | 필터 칩 높이 | **28px** — 터치 기준 미달 | **MEDIUM** |
| 12.3.4 | 연락처 카드 구성 | 이모지+이름+회사+업종 — 정보 적절 | PASS |
| 12.3.5 | 무한스크롤 로딩 | 스피너 표시 — **OK** | PASS |
| 12.3.6 | 빈 상태 | 아이콘+메시지+"연락처 추가하기" CTA — **OK** | PASS |
| 12.3.7 | "일괄 등록" + "추가" 버튼 | 아웃라인+채움 구분 명확 — **OK** | PASS |

### 12.4 연락처 상세

| # | 항목 | 현재 상태 | 심각도 |
|---|------|----------|--------|
| 12.4.1 | 이름+직함+회사+전화번호 | 계층 구조 적절 — **OK** | PASS |
| 12.4.2 | AI 브리핑 섹션 | "AI 브리핑 생성하기" CTA — **OK** | PASS |
| 12.4.3 | 유사 고객 추천 | 카드형 추천 — 정보량 적절 | PASS |
| 12.4.4 | 메모/미팅 탭 전환 | 탭 구분 명확 — **OK** | PASS |
| 12.4.5 | 뒤로가기 "< 연락처" | 네비게이션 명확 — **OK** | PASS |
| 12.4.6 | 데스크탑 레이아웃 | 넓은 화면에서 컨텐츠가 **좌측 편향**, 우측 빈 공간 | **LOW** |

### 12.5 연락처 폼 (추가/수정)

| # | 항목 | 현재 상태 | 심각도 |
|---|------|----------|--------|
| 12.5.1 | 필드 구성 | 이름*, 전화번호, 회사명, 업종, 지역, 매출규모, 직원수, 메모 — 적절 | PASS |
| 12.5.2 | 필수 입력 표시 | 이름에 * 표시 — **OK** | PASS |
| 12.5.3 | 플레이스홀더 | 모든 필드에 적절한 안내 — **OK** | PASS |
| 12.5.4 | 제출 버튼 | 전체 너비, 44px 높이 — **OK** | PASS |
| 12.5.5 | 모바일에서 버튼-내비 겹침 | 스크롤 최하단에서 "등록하기"와 바텀 내비 겹침 가능 | **MEDIUM** |

### 12.6 미팅 목록

| # | 항목 | 현재 상태 | 심각도 |
|---|------|----------|--------|
| 12.6.1 | "+" 추가 버튼 | 44px, primary 배경 — **OK** | PASS |
| 12.6.2 | 빈 상태 | 캘린더 이모지+메시지+CTA — **OK** | PASS |
| 12.6.3 | 빈 상태 아래 회색 영역 | 콘텐츠 이하 **큰 회색 빈 영역** 표시 | **MEDIUM** |

### 12.7 매칭 목록

| # | 항목 | 현재 상태 | 심각도 |
|---|------|----------|--------|
| 12.7.1 | 빈 상태 메시지 | "연락처가 더 쌓이면 AI가 연결을 찾습니다" — 적절 | PASS |
| 12.7.2 | 빈 상태 아래 회색 영역 | 미팅과 동일한 **회색 빈 영역** 문제 | **MEDIUM** |
| 12.7.3 | CTA 버튼 없음 | 빈 상태에 **주요 행동 유도 버튼 없음** | **MEDIUM** |

### 12.8 설정

| # | 항목 | 현재 상태 | 심각도 |
|---|------|----------|--------|
| 12.8.1 | 내 정보 섹션 | 이름, 역할, 소속, 전화번호 — 적절 | PASS |
| 12.8.2 | 알림 토글 | 3개 토글 스위치 — 시각적 적절 | PASS |
| 12.8.3 | 앱 정보 | 버전, 이용약관, 개인정보 — 적절 | PASS |
| 12.8.4 | 데스크탑 레이아웃 | 너무 넓게 펼쳐져 카드가 **전체 너비 차지** | **LOW** |

### 12.9 엑셀 임포트

| # | 항목 | 현재 상태 | 심각도 |
|---|------|----------|--------|
| 12.9.1 | 파일 업로드 영역 | 점선 박스+아이콘+설명 — 적절 | PASS |
| 12.9.2 | AI 분류 안내 | 보라색 배경 안내 카드 — **OK** | PASS |
| 12.9.3 | "AI 분류 시작" 비활성 | 파일 미선택 시 비활성 — **OK** | PASS |
| 12.9.4 | 파일 사이즈/건수 안내 | "5MB, 1,000건 이하" 명시 — **OK** | PASS |

---

## 13. 크로스 페이지 일관성

| # | 항목 | 현재 상태 | 심각도 |
|---|------|----------|--------|
| 13.1 | 네비게이션 일관성 | 바텀 내비 4탭 전체 페이지 동일 — **OK** | PASS |
| 13.2 | 활성 탭 하이라이트 | 현재 페이지에 맞는 탭 활성화 — **OK** | PASS |
| 13.3 | 페이지 타이틀 위치/스타일 | 모든 페이지 `text-xl font-bold` px-4 pt-6 — 일관 | PASS |
| 13.4 | 카드 스타일 통일 | `rounded-2xl border border-gray-200 shadow-sm` — 전체 일관 | PASS |
| 13.5 | CTA 버튼 스타일 | `bg-primary text-white rounded-lg` — 전체 일관 | PASS |
| 13.6 | 빈 상태 패턴 | 연락처(아이콘), 미팅(이모지), 매칭(아이콘) — **약간 비일관** | **LOW** |

---

## 14. AI Slop 검사

| # | 항목 | 현재 상태 | 심각도 |
|---|------|----------|--------|
| 14.1 | 보라색 그라디언트 배경 | 없음 — **OK** | PASS |
| 14.2 | 3열 Feature 그리드 | 없음 — **OK** | PASS |
| 14.3 | 원형 아이콘 장식 | 없음 — **OK** | PASS |
| 14.4 | 모든 요소 중앙 정렬 | 해당 없음, 좌측 정렬 위주 — **OK** | PASS |
| 14.5 | 균일한 bubbly radius | 용도별 차별화됨 — **OK** | PASS |
| 14.6 | 장식 블롭/웨이브 | 없음 — **OK** | PASS |
| 14.7 | 이모지 디자인 요소 | 관계 건강도에만 사용 — 적절한 용도 | PASS |
| 14.8 | 컬러 좌측 보더 카드 | 없음 — **OK** | PASS |
| 14.9 | 제네릭 히어로 카피 | 없음 — **OK** | PASS |
| 14.10 | 쿠키커터 섹션 리듬 | 없음 — **OK** | PASS |

**AI Slop Score: A** — AI 생성 느낌이 없는 깔끔한 앱 UI

---

## 15. 디자인 토큰 구현 (Tailwind Config)

| # | 항목 | 현재 상태 | 심각도 | 위치 |
|---|------|----------|--------|------|
| 15.1 | fontSize 토큰 미정의 | `text-[22px]`, `text-[28px]`, `text-[15px]` 등 arbitrary value 사용 | **HIGH** | `base.html:14-31` |
| 15.2 | borderRadius 시맨틱 토큰 | card/button/input 구분이 코드에서 명시적이지 않음 | **LOW** | Tailwind config |
| 15.3 | 시맨틱 컬러 토큰 미정의 | success/warning/error/info가 config에 없어 Tailwind 기본 사용 | **LOW** | Tailwind config |

**수정 방법:** Tailwind config에 DESIGN.md의 fontSize 스케일을 토큰으로 등록:
```js
fontSize: {
  'display': ['28px', { lineHeight: '1.2', letterSpacing: '-0.02em', fontWeight: '700' }],
  'heading': ['20px', { fontWeight: '700' }],
  'subheading': ['16px', { fontWeight: '600' }],
  'body': ['14px', { fontWeight: '400' }],
  'caption': ['12px', { fontWeight: '400' }],
  'micro': ['10px', { fontWeight: '400', letterSpacing: '0.1em' }],
}
```
그 후 `text-[22px]` → `text-heading`, `text-[28px]` → `text-display` 등으로 교체.

---

## 16. 모달 & 오버레이

| # | 항목 | 현재 상태 | 심각도 | 위치 |
|---|------|----------|--------|------|
| 16.1 | 모달 시맨틱 HTML | `<div>` 사용 — `role="dialog"` + `aria-modal="true"` 미적용 | **MEDIUM** | `contact_report_modal.html` |
| 16.2 | 모달 닫기 ESC 키 | 키보드 ESC 닫기 미구현 | **MEDIUM** | `contact_report_modal.html` |

---

## 우선순위별 수정 요약

### HIGH (즉시 수정)

| # | 문제 | 수정 방법 | 영향 범위 |
|---|------|----------|-----------|
| H1 | 업무 버튼 터치 타깃 20-22px | `p-2.5` 패딩 추가, min-w/h 44px | `_task_card.html` |
| H2 | `focus-visible` 링 미구현 | 전역 CSS 추가 | `base.html` |
| H3 | `aria-label` 전무 | 아이콘 버튼에 aria-label 속성 추가 | 전체 |
| H4 | gray-400 보조텍스트 대비 2.9:1 | gray-500으로 변경 | 전체 |
| H5 | "+ 추가" 버튼 36x20px | 최소 44px 높이 확보 | `section_tasks.html` |
| H6 | 상호작용 수정/삭제 아이콘 18px | `p-2.5` + `w-5 h-5`로 변경 | `interaction_timeline.html` |
| H7 | Tailwind fontSize 토큰 미정의 | DESIGN.md 스케일을 config에 등록 | `base.html` config |

### MEDIUM (1주 내 수정)

| # | 문제 | 수정 방법 | 영향 범위 |
|---|------|----------|-----------|
| M1 | 필터 칩 높이 28px | `py-2.5`로 높이 확보 | `contact_list.html` |
| M2 | 빈 상태 아래 회색 영역 | min-height 또는 flex-1 적용 | 미팅/매칭 |
| M3 | 아바타 36px | min-w/h 44px 적용 | 사이드바 |
| M4 | `safe-area-inset` 미적용 | 바텀 내비 패딩 추가 | `nav_bottom.html` |
| M5 | 필터 URL 반영 안 됨 | `hx-push-url` 추가 | `contact_list.html` |
| M6 | 업무 완료 시 피드백 없음 | 토스트 또는 애니메이션 추가 | `_task_card.html` |
| M7 | 페이지 전환 로딩 상태 없음 | 프로그레스 바 또는 스켈레톤 추가 | `base.html` |
| M8 | 관계 이모지 접근성 | 색각 이상자용 텍스트 보조 추가 | `contact_list_items.html` |
| M9 | 매칭 빈 상태 CTA 없음 | "연락처 추가하기" CTA 추가 | 매칭 페이지 |
| M10 | 모바일 폼 제출 버튼 내비 겹침 | 하단 여백 추가 | `contact_form.html` |
| M11 | 에러 메시지 표시 검증 | validation 에러 UX 확인 | `contact_form.html` |
| M12 | 로그인 이용약관 대비 부족 | gray-500으로 변경 | `login.html` |
| M13 | 모달 시맨틱/접근성 | `role="dialog"` + ESC 닫기 추가 | `contact_report_modal.html` |
| M14 | 미팅 FAB rounded-lg | FAB는 `rounded-full`이 표준 | `meeting_list_content.html:7` |

### LOW (개선 권장)

| # | 문제 | 수정 방법 | 영향 범위 |
|---|------|----------|-----------|
| L1 | Tailwind CDN 프로덕션 사용 | 빌드 시스템으로 전환 | `base.html` |
| L2 | 로그인 페이지 Tailwind config 중복 | base.html 확장하거나 공유 | `login.html` |
| L3 | 태블릿 고유 레이아웃 없음 | md 브레이크포인트 활용 | `base.html` |
| L4 | 데스크탑 콘텐츠 너비 제한 | 연락처 상세/설정에 max-w 적용 | 해당 페이지 |
| L5 | `prefers-reduced-motion` 미적용 | 미디어 쿼리 추가 | `base.html` |
| L6 | 빈 상태 아이콘/이모지 비일관 | 통일된 아이콘 스타일 적용 | 미팅/매칭 |
| L7 | gray-400/500 보조텍스트 혼용 | 용도별 통일 | 전체 |
| L8 | `autocomplete` 속성 미사용 | 폼 필드에 추가 | `contact_form.html` |

---

## 점수 요약

| 카테고리 | 등급 | 비고 |
|----------|------|------|
| Visual Hierarchy | **B** | 계층 구조 명확, 일부 정보밀도 부족 |
| Typography | **A** | Pretendard 통일, 스케일 준수 |
| Color & Contrast | **B** | Primary 일관, gray-400 대비 미달 |
| Spacing & Layout | **A** | 4px 시스템 일관 준수 |
| Interaction States | **C** | focus-visible 미구현, 피드백 부족 |
| Responsive | **B** | 기본 전환 OK, 태블릿/노치 미흡 |
| Accessibility | **C** | aria-label 전무, 대비 이슈 |
| Touch Targets | **D** | 다수 버튼 44px 미달 (task, interaction 등) |
| Content Quality | **A** | 한국어 자연스러움, 빈 상태 적절 |
| AI Slop | **A** | AI 생성 패턴 없음 |

**전체 Design Score: B-**
**AI Slop Score: A**

---

*Generated by /design-review on 2026-03-29*
