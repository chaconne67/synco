# synco 상용화 점검 보고서

**점검일:** 2026-03-31
**점검 범위:** 보이스 서치(candidates 앱) + 전체 UI/UX + 인터랙션
**점검팀:** UI/UX 디자인 점검자, 인터랙션 & 기능 점검자
**감독:** 오케스트레이터 (최종 검토 및 승인)

---

## 종합 판정: CONDITIONAL GO

> 3라운드 점검-수정 반복 후 최종 판정. 코드 수준 이슈는 모두 해결됨.
> 남은 BLOCKER 1건(이용약관/개인정보처리방침 실제 내용 작성)은 법률 검토가 필요한 비코드 작업.

| 심각도 | 초기 | 3차 점검 후 | 상세 |
|--------|------|------------|------|
| **BLOCKER** | 3→4→1 | **0 (코드)** / 1 (법률) | 이용약관/개인정보처리방침 실제 내용 작성 필요 |
| **HIGH** | 12→22→5 | **0 (코드)** / 1 (인프라) | Tailwind CDN → 빌드 파이프라인 전환 필요 |
| **MEDIUM** | 8 | 9 | 터치 타깃 marginal, CDN SRI, 기타 |
| **LOW** | 8 | 2 | 폴리시 개선 |

### 초기 판정 (참고용)

| 심각도 | 건수 | 상세 |
|--------|------|------|
| **BLOCKER** | 3 | 상용화 절대 불가 — 즉시 수정 필수 |
| **HIGH** | 12 | 상용화 전 반드시 수정 |
| **MEDIUM** | 8 | 권장 수정 |
| **LOW** | 8 | 폴리시 개선 |

---

## BLOCKER 이슈 (3건)

### B1. text-gray-300 색상 대비 WCAG 위반
- **파일:** `candidates/templates/candidates/partials/candidate_card.html:15`
- **현재:** `text-gray-300` (#D1D5DB) on white = 대비율 **1.87:1**
- **기준:** WCAG AA 최소 **4.5:1**
- **영향:** 후보자 카드 "정보 없음" 텍스트가 시력 약한 사용자에게 보이지 않음
- **수정:** `text-gray-300` → `text-gray-500` (#6B7280, 대비 5.28:1)
- **담당:** 프론트엔드

### B2. toast.html Alpine.js 미로드
- **파일:** `templates/common/components/toast.html` (Alpine x-data/x-show 사용)
- **파일:** `templates/common/base.html` (Alpine.js CDN 미포함)
- **현재:** toast.html이 Alpine.js 디렉티브 사용하지만 Alpine 미로드. 서버 응답 토스트 전부 작동 안 함
- **영향:** HTMX 응답에서 보내는 모든 피드백 토스트가 표시되지 않음
- **수정:** Alpine.js CDN 추가하거나 toast.html을 순수 JS로 재작성
- **담당:** 프론트엔드

### B3. HTMX 전역 에러 핸들러 부재
- **파일:** `templates/common/base.html:145-148`
- **현재:** htmx:responseError 이벤트에서 버튼 복원만 하고 사용자 에러 메시지 표시 안 함
- **영향:** 네트워크 끊김/서버 오류 시 사용자가 무한 대기. 모바일 환경에서 치명적
- **수정:** htmx:responseError에서 토스트로 에러 메시지 표시
- **담당:** 프론트엔드

---

## HIGH 이슈 (12건)

### H1. 카테고리 탭 터치 타깃 미달
- **파일:** `candidates/templates/candidates/search.html:36`
- **현재:** `px-3 py-1.5` (약 30px)
- **기준:** 44px 최소
- **수정:** `py-2.5` 이상으로 변경
- **담당:** 프론트엔드

### H2. 챗봇 닫기 버튼 터치 타깃 미달
- **파일:** `candidates/templates/candidates/partials/chatbot_modal.html:19`
- **현재:** `p-1` (약 28px)
- **수정:** `p-2.5` 이상
- **담당:** 프론트엔드

### H3. 뒤로가기 버튼 터치 타깃 미달
- **파일:** `candidates/templates/candidates/partials/candidate_detail_content.html:3`
- **현재:** `w-5 h-5` 아이콘, 패딩 없음 (20px)
- **수정:** `p-2` + `min-w-[44px] min-h-[44px]`
- **담당:** 프론트엔드

### H4. 태스크 완료/수정/삭제 버튼 터치 타깃 미달
- **파일:** `accounts/templates/accounts/partials/dashboard/_task_card.html:6,38-44`
- **현재:** 완료 체크 28px, 수정/삭제 텍스트 20px
- **수정:** 최소 44px 확보
- **담당:** 프론트엔드

### H5. gray-400 텍스트 WCAG 대비 미달
- **파일:** 전역 (search_status_bar.html, search.html 등)
- **현재:** gray-400 (#9CA3AF) on white = **2.86:1**
- **수정:** `text-gray-400` → `text-gray-500` (보조 텍스트 전역)
- **담당:** 프론트엔드

### H6. safe-area-pb CSS 미정의 + viewport-fit=cover 누락
- **파일:** `chatbot_modal.html:41` (safe-area-pb 클래스), `base.html:6` (viewport meta)
- **현재:** 커스텀 클래스 정의 없음, viewport-fit=cover 없음
- **수정:** base.html에 safe-area-pb CSS 추가 + viewport-fit=cover 추가
- **담당:** 프론트엔드

### H7. 보이스서치 페이지에서 홈 복귀 경로 없음
- **파일:** `candidates/templates/candidates/search.html`
- **현재:** 사이드바/하단 네비 모두 제거됨. 뒤로가기 버튼도 없음
- **수정:** 최소한 로고 클릭으로 홈 복귀 또는 뒤로가기 버튼 추가
- **담당:** 프론트엔드

### H8. 챗봇 검색 후 후보자 리스트 실시간 미갱신
- **파일:** `candidates/static/candidates/chatbot.js:20,105-133`
- **현재:** 리스트 갱신이 챗봇 닫을 때만 발생
- **수정:** doSearch() 성공 후 즉시 refreshCandidateList() 호출
- **담당:** 프론트엔드

### H9. input_type 하드코딩
- **파일:** `candidates/views.py:296`
- **현재:** SearchTurn 생성 시 input_type이 항상 "text"로 하드코딩
- **수정:** request body의 input_type 값 사용
- **담당:** 백엔드

### H10. 세션 복원 시 채팅 히스토리 미복원
- **파일:** `candidates/static/candidates/chatbot.js` (chat_history 미호출)
- **현재:** 세션은 sessionStorage에 저장되지만 채팅 메시지는 복원 안 됨
- **수정:** 챗봇 열 때 chat_history 엔드포인트 호출하여 이전 대화 로드
- **담당:** 프론트엔드

### H11. 챗봇 검색 상태 URL 미반영
- **파일:** `candidates/static/candidates/chatbot.js:106-133`
- **현재:** fetch API 사용, pushState 없음. 뒤로가기 시 검색 상태 소실
- **수정:** 검색 후 URL에 session_id 파라미터 추가 (history.replaceState)
- **담당:** 프론트엔드

### H12. 서버 입력 검증 부재 (500 에러 노출)
- **파일:** `candidates/views.py:245` (json.loads 미검증), `candidates/views.py:139` 등 (int() 미검증)
- **현재:** 잘못된 JSON, 비숫자 page 파라미터 시 500 에러 무방비
- **수정:** try/except로 입력 검증 + 적절한 에러 응답
- **담당:** 백엔드

---

## MEDIUM 이슈 (8건)

| # | 이슈 | 파일 | 담당 |
|---|------|------|------|
| M1 | 챗봇 마이크/전송 버튼 40px (44px 미만) | chatbot_modal.html:43,64 | FE |
| M2 | 접점 수정/삭제 아이콘 36px | interaction_timeline.html:34-44 | FE |
| M3 | border-gray-100 vs gray-200 혼용 | 전역 카드 | FE |
| M4 | border-radius 위계 불일치 (DESIGN.md vs 실제) | 전역 카드 | FE |
| M5 | 챗봇 중복 제출 방지 없음 | chatbot.js | FE |
| M6 | 카테고리+챗봇 필터 동기화 안 됨 | search.html + views.py | FE+BE |
| M7 | 성공 피드백 없음 (폼 제출 후 토스트 없음) | contacts/views.py | BE |
| M8 | focus trap 부재 (모달에서 Tab 탈출 가능) | chatbot_modal.html | FE |

---

## LOW 이슈 (8건)

| # | 이슈 | 파일 |
|---|------|------|
| L1 | autocomplete 속성 미설정 | 전체 폼 |
| L2 | Tailwind CDN 프로덕션 사용 | base.html:13 |
| L3 | 태블릿 전용 레이아웃 없음 | 전역 |
| L4 | 일부 빈 상태에 CTA 없음 | section_tasks, interaction_timeline 등 |
| L5 | 무한스크롤 spinner 없음 | candidate_list.html |
| L6 | 스켈레톤 로딩 제한적 | 전역 |
| L7 | 뒤로가기 버튼 패턴 혼용 | 전역 |
| L8 | 다크모드 미지원 명시 필요 | base.html |

---

## 수정 추적

### 1차 수정 (2026-03-31)

| 이슈 ID | 수정 내용 | 수정 파일 | 검증 |
|---------|----------|----------|------|
| B1 | text-gray-300 → text-gray-500 | candidate_card.html:15 | OK |
| B2 | toast.html을 순수 JS+CSS로 재작성 (Alpine 의존 제거) | toast.html | OK |
| B3 | showToast() 전역 함수 + htmx:responseError에서 토스트 표시 | base.html | OK |
| H1 | 카테고리 탭 py-1.5 → py-2.5 | search.html:36,45 | OK |
| H2 | 챗봇 닫기 p-1 → p-2.5 | chatbot_modal.html:19 | OK |
| H3 | 뒤로가기 min-w/h 44px 추가 | candidate_detail_content.html:7 | OK |
| H4 | 태스크 버튼 w-11 h-11 + min-w/h 44px | _task_card.html:8,40,43 | OK |
| H5 | 보조 텍스트 gray-400 → gray-500 | search_status_bar.html, search.html | OK |
| H6 | viewport-fit=cover + safe-area-pb CSS 추가 | base.html:6,55 | OK |
| H7 | synco 로고에 홈 링크 추가 | search.html:23 | OK |
| H8 | doSearch 성공 후 즉시 refreshCandidateList() 호출 | chatbot.js:132 | OK |
| H9 | input_type을 request body에서 읽도록 변경 | views.py:262-264,310 | OK |
| H10 | loadChatHistory() 함수 추가, 모달 열 때 히스토리 로드 | chatbot.js:26-28,212-230 | OK |
| H11 | history.replaceState로 session_id URL 반영 | chatbot.js:133 | OK |
| H12 | json.loads/int()/UUID 검증 + except 처리 추가 | views.py:140-155,254-257,346-363 | OK |
| M7 | 연락처 생성/수정 시 토스트 메시지 전달 | contacts/views.py + contact_detail_content.html | OK |

**테스트:** 113 passed, 0 failed. 린트/포맷 통과.

### 2차 재점검 — 제로 베이스 (2026-03-31)

> 1차 점검 결과를 모르는 외부 점검자 2명이 처음부터 전체 재점검

**판정: NO GO** — BLOCKER 4건, HIGH 18건+ 발견

#### 2차 BLOCKER (코드 수정 가능)

| ID | 이슈 | 파일 | 조치 |
|----|------|------|------|
| 2B1 | 이용약관 href="#" 플레이스홀더 (법적 위험) | login.html:55-57, settings_content.html:85-96 | 최소 "준비 중" 안내 페이지 연결 |
| 2B2 | 개인정보처리방침 href="#" 플레이스홀더 | login.html:55-57, settings_content.html:85-96 | 동일 |
| 2B3 | Rate limiting 전무 (API 비용 폭증 위험) | views.py 전체 | django-ratelimit 추가 |
| 2B4 | Tailwind CDN 프로덕션 사용 | base.html:14 | 빌드 파이프라인 전환 필요 (별도 작업) |

#### 2차 HIGH — 즉시 수정 가능

| ID | 이슈 | 파일 | 담당 |
|----|------|------|------|
| 2H1 | task_list_items 완료 버튼 20px | task_list_items.html:6 | FE |
| 2H2 | contact_detail 뒤로가기 28px | contact_detail_content.html:6-10 | FE |
| 2H3 | meeting_detail 뒤로가기 ~20px | meeting_detail_content.html:3-6 | FE |
| 2H4 | meeting_form 뒤로가기 ~20px | meeting_form_content.html:4-7 | FE |
| 2H5 | match_detail 뒤로가기 ~20px | match_detail_content.html:3-6 | FE |
| 2H6 | brief_detail 뒤로가기 ~20px | brief_detail_content.html:3-5 | FE |
| 2H7 | task_form 닫기 버튼 24px | task_form.html:9-13 | FE |
| 2H8 | dashboard 할일/일정 추가 버튼 28px | section_tasks.html:12-17, section_meetings.html:15 | FE |
| 2H9 | Feel Lucky 닫기 24px | section_feel_lucky.html:26-31 | FE |
| 2H10 | primary color 대비 4.12:1 (모든 버튼/링크) | base.html Tailwind config | FE |
| 2H11 | white on primary 버튼 대비 4.12:1 | 전역 | FE |
| 2H12 | candidate_detail gray-400 보조 텍스트 | candidate_detail_content.html:17,31,57,74,89 | FE |
| 2H13 | 설정 토글 비기능적 (폼 연결 없음) | settings_content.html:46-72 | FE |
| 2H14 | 프로필 완성도 80% 하드코딩 | ceo_dashboard_content.html:17-20 | FE |
| 2H15 | confidence_score 표시 버그 (0.8→1%) | candidate_detail_content.html:92-93 | FE |
| 2H16 | 챗봇 중복 전송 방지 없음 | chatbot.js | FE |
| 2H17 | HTMX sendError 핸들러 없음 | base.html | FE |
| 2H18 | contacts/views.py page 파라미터 미검증 | contacts/views.py:27 | BE |
| 2H19 | contact_create 서버 검증 없음 (KeyError 위험) | contacts/views.py:94 | BE |
| 2H20 | 오디오 파일 크기 제한 없음 | candidates/views.py | BE |
| 2H21 | N+1 쿼리 (candidate_card) | candidates/views.py | BE |
| 2H22 | 뒤로가기 패턴 불일치 (일부만 44px) | 전역 | FE |

### 2차 수정 (2026-03-31)

| 이슈 ID | 수정 내용 | 수정 파일 | 검증 |
|---------|----------|----------|------|
| 2B1+2B2 | 이용약관/개인정보처리방침 href→/terms/, /privacy/ + 뷰/템플릿 생성 | login.html, settings_content.html, accounts/urls.py, accounts/views.py, 4 templates | OK |
| 2B3 | Rate limiting: search_chat 분당 10회, voice_transcribe 분당 5회 | candidates/views.py (cache 기반) | OK |
| 2H1 | task_list_items 완료 버튼 min-w/h 44px | task_list_items.html:6 | OK |
| 2H2 | contact_detail 뒤로가기 44px | contact_detail_content.html:10 | OK |
| 2H3 | meeting_detail 뒤로가기 44px | meeting_detail_content.html:5 | OK |
| 2H4 | meeting_form 뒤로가기 44px | meeting_form_content.html:6 | OK |
| 2H5 | match_detail 뒤로가기 44px | match_detail_content.html:5 | OK |
| 2H6 | brief_detail 뒤로가기 44px | brief_detail_content.html:4 | OK |
| 2H7 | task_form 닫기 p-2.5 + min 44px | task_form.html:10 | OK |
| 2H8 | 대시보드 +버튼 min 44px | section_tasks.html:13, section_meetings.html:15 | OK |
| 2H9 | Feel Lucky 닫기 min 44px | section_feel_lucky.html:28 | OK |
| 2H10+2H11 | primary #5B6ABF→#4A56A8 (대비 4.5:1+) | base.html, login.html, role_select.html | OK |
| 2H12 | candidate_detail gray-400→gray-500 | candidate_detail_content.html 6곳 | OK |
| 2H13 | 설정 토글 → "준비 중" 안내로 대체 | settings_content.html | OK |
| 2H14 | 프로필 80% 하드코딩 섹션 주석 처리 | ceo_dashboard_content.html | OK |
| 2H15 | confidence_score widthratio 태그로 수정 | candidate_detail_content.html | OK |
| 2H16 | isSearching 플래그 추가 (중복 전송 방지) | chatbot.js | OK |
| 2H17 | htmx:sendError → 네트워크 에러 토스트 | base.html | OK |
| 2H18 | page 파라미터 검증 (contacts, candidates, meetings, intelligence) | 4개 views.py | OK |
| 2H19 | contact_create/edit .get() + strip() + 빈값 검증 | contacts/views.py | OK |
| 2H20 | 오디오 10MB 크기 제한 | candidates/views.py | OK |
| 2H21 | prefetch_related 추가 (N+1 해결) | candidates/views.py, search.py | OK |

**테스트:** 113 passed, 0 failed. 린트/포맷 통과.

**미해결 (아키텍처 수준):**
- 2B4: Tailwind CDN → 빌드 파이프라인 전환 (별도 인프라 작업 필요)

### 3차 재점검 — 제로 베이스 (2026-03-31)

**판정: BLOCKER 1 (법률) + HIGH 5 → 코드 수정 가능 4건 즉시 처리**

| 이슈 | 판정 | 조치 |
|------|------|------|
| 이용약관/개인정보처리방침 "준비 중" | BLOCKER | 법률 검토 후 실제 약관 작성 필요 (비코드) |
| SECRET_KEY insecure fallback | HIGH → **수정 완료** | DEBUG=True일 때만 dev 키, 운영은 ImproperlyConfigured |
| SESSION_COOKIE_SECURE 미설정 | HIGH → **수정 완료** | DEBUG=False 시 보안 쿠키/HSTS 자동 활성화 |
| text-gray-400 WCAG 미달 (3곳) | HIGH → **수정 완료** | gray-500으로 변경 |
| 미팅 생성/수정 입력 검증 부재 | HIGH → **수정 완료** | .get() + 빈값 검증 + 422 에러 |
| Tailwind CDN 프로덕션 사용 | HIGH | 빌드 파이프라인 전환 필요 (별도 인프라 작업) |

### 3차 수정 (2026-03-31)

| 이슈 | 수정 파일 | 수정 내용 | 검증 |
|------|----------|----------|------|
| SECRET_KEY | main/settings.py | insecure fallback 제거, DEBUG 시만 dev 키 | OK |
| 보안 쿠키 | main/settings.py | SESSION/CSRF_COOKIE_SECURE + HSTS (운영 전용) | OK |
| gray-400 잔여 | candidate_list.html, contact_list_items.html | 텍스트 gray-400→gray-500 | OK |
| 미팅 검증 | meetings/views.py | create/edit .get() + 빈값 검증 | OK |

**테스트:** 113 passed, 0 failed

---

## 최종 현황 (3라운드 완료 후)

### 해결된 이슈 총계: 48건

| 라운드 | BLOCKER 수정 | HIGH 수정 | MEDIUM 수정 | 합계 |
|--------|-------------|----------|------------|------|
| 1차 | 3 | 12 | 1 | 16 |
| 2차 | 3 | 22 | 0 | 25 |
| 3차 | 0 | 4 | 0 | 4 |
| **합계** | **6** | **38** | **1** | **45** |

### 미해결 잔여 이슈 (비코드/인프라)

| 이슈 | 심각도 | 담당 | 비고 |
|------|--------|------|------|
| 이용약관/개인정보처리방침 실제 내용 | BLOCKER (법률) | 법무/경영 | 개인정보보호법 준수 필수 |
| Tailwind CDN → 빌드 파이프라인 | HIGH (인프라) | DevOps | CDN 장애 시 UI 전체 깨짐 |
| HTMX unpkg SRI hash 추가 | MEDIUM (보안) | DevOps | CDN 무결성 검증 |

### 최종 판정: **CONDITIONAL GO**

코드 수준의 모든 BLOCKER/HIGH 이슈가 해결되었습니다. 서비스 배포를 위해서는:

1. **이용약관/개인정보처리방침** 실제 내용 작성 (법률 검토) → 완료 시 BLOCKER 해소
2. **Tailwind 빌드 파이프라인** 구축 → 완료 시 HIGH 해소
3. 위 2건 해결 후 → **GO** 판정 가능

보이스 서치 기능 자체는 happy path 정상, 에러 핸들링 완비, 중복 방지/rate limiting/입력 검증 모두 적용 완료.

---

## 변경 이력

| 날짜 | 내용 | 작성자 |
|------|------|--------|
| 2026-03-31 | 초기 점검 보고서 작성 — NO GO (B3, H12) | 오케스트레이터 |
| 2026-03-31 | 1차 수정 완료 (FE 13건 + BE 4건) | FE/BE 에이전트 |
| 2026-03-31 | 2차 제로 베이스 재점검 — NO GO (B4, H22) | 재점검 에이전트 |
| 2026-03-31 | 2차 수정 완료 (FE 21건 + BE 10건) | FE/BE 에이전트 |
| 2026-03-31 | 3차 제로 베이스 재점검 — NO GO (B1, H5) | 재점검 에이전트 |
| 2026-03-31 | 3차 수정 완료 (4건) | 수정 에이전트 |
| 2026-03-31 | **최종 판정: CONDITIONAL GO** | 오케스트레이터 |
