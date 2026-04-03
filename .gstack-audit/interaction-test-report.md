# HTMX Interaction Test Report

**Date:** 2026-03-29
**App URL:** http://localhost:8000
**Viewports tested:** Desktop (1280x720), Mobile (375x812)

---

## FAILURES SUMMARY

### FAIL-1: Industry filter chips return no results (broken filter logic)

- **File:** `contacts/views.py:25`
- **Line:** `contacts = contacts.filter(industry=industry)`
- **Problem:** Filter chips send generic category names (e.g., "제조업", "IT/소프트웨어") but the database stores specific KSIC industry names (e.g., "응용 소프트웨어 개발 및 공급업", "유아용 의복 제조업"). The exact match `filter(industry=industry)` never matches any records, so every filter chip shows zero results with "아직 등록된 연락처가 없습니다" empty state.
- **Fix:** Change exact match to contains match: `contacts = contacts.filter(industry__icontains=industry)` -- or better, define a mapping from chip category to industry keywords and use Q objects to match multiple patterns per category.

### FAIL-2: "총 N건" count not updated after filter chip click

- **File:** `contacts/templates/contacts/contact_list.html:110`
- **Line:** `<p class="text-sm text-gray-500 mb-3">총 {{ total_count }}건</p>`
- **Problem:** The total count element is outside `#contact-list`, so when a filter chip's HTMX response replaces only `#contact-list`, the count stays at the unfiltered total (e.g., "총 177건" while showing 0 filtered results). Also, the filter chip active state (blue highlight on "전체") is not updated since the chips are also outside `#contact-list`.
- **Fix:** Either (a) wrap the count + chips + list in a single target container and swap that, or (b) use `hx-swap-oob` to update the count and chip states from the HTMX partial response.

---

## DETAILED TEST RESULTS

### 1. Dashboard (http://localhost:8000/)

| # | Element | Action | Expected | Actual | Result |
|---|---------|--------|----------|--------|--------|
| 1.1 | Task complete button (POST) | Click checkmark | Task card removed from list | Card removed, task count reduced from 5 to 4 | **PASS** |
| 1.2 | Task delete button (POST) | Click trash + confirm dialog | Confirm dialog shown, then card removed | Dialog "이 업무를 삭제하시겠습니까?" shown, card removed after accept | **PASS** |
| 1.3 | Task edit button (GET) | Click pencil icon | Edit form appears inline at card position | Form with textbox, date, save/cancel replaces card | **PASS** |
| 1.4 | Task edit save (POST) | Click "저장" on edit form | Task updated and form replaced with task list | Task list re-rendered with updated data | **PASS** |
| 1.5 | Task edit cancel | Click "취소" | Edit form dismissed, original card restored | Card restored correctly | **PASS** |
| 1.6 | "+ 추가" button (GET) | Click | New task form appears in #task-form-slot | Form with placeholder "업무 내용을 입력하세요", date input, save button appeared | **PASS** |
| 1.7 | "N건 더 보기" button (GET) | Click | All remaining tasks loaded | Went from 5 to 22 tasks, button removed | **PASS** |
| 1.8 | "브리핑 전문 보기" link | Click | Navigate to brief detail page | Navigated to /intelligence/briefs/{uuid}/ via HTMX into #main-content with URL push | **PASS** |
| 1.9 | Contact link in "주의 필요" section | Click "김석기" | Navigate to contact detail | Navigated to /contacts/{uuid}/ with full contact detail loaded | **PASS** |

### 2. Contacts List (http://localhost:8000/contacts/)

| # | Element | Action | Expected | Actual | Result |
|---|---------|--------|----------|--------|--------|
| 2.1 | Search input (GET, keyup delay:300ms) | Type "김석기" | Contacts filtered to matching results | Filtered to 1 result showing 김석기 in #contact-list | **PASS** |
| 2.2 | Filter chip "제조" (GET) | Click | Contacts filtered by manufacturing industry | Empty results -- exact match "제조업" finds no contacts (DB has "유아용 의복 제조업" etc.) | **FAIL** |
| 2.3 | Filter chip "IT" (GET) | Click | Contacts filtered by IT industry | Empty results -- same root cause as 2.2 | **FAIL** |
| 2.4 | "총 N건" after filter | Observe after filter click | Count should update to match filtered results | Count stays at "총 177건" even with 0 filtered results | **FAIL** |
| 2.5 | Contact card click | Click "박수영" | Navigate to contact detail | Navigated to /contacts/{uuid}/ with 박수영 detail loaded | **PASS** |
| 2.6 | "일괄 등록" button | Click | Navigate to import page | Navigated to /contacts/import/ with upload UI | **PASS** |
| 2.7 | "추가" button | Click | Navigate to new contact form | Navigated to /contacts/new/ with empty form | **PASS** |
| 2.8 | Infinite scroll trigger (revealed) | Scroll to bottom | Load next page of contacts | Went from 20 to 40 contacts (page 2 loaded) | **PASS** |

### 3. Contact Detail

| # | Element | Action | Expected | Actual | Result |
|---|---------|--------|----------|--------|--------|
| 3.1 | "메모" button (GET) | Click | Interaction form appears inline | Form with type tabs (통화/미팅/메시지/메모), textarea, sentiment, save/cancel appeared | **PASS** |
| 3.2 | "미팅" button (GET) | Click | Navigate to meeting form with contact pre-filled | Navigated to /meetings/new/?contact={uuid} with 김석기 pre-selected | **PASS** |
| 3.3 | "AI 브리핑 생성하기" button (POST) | Click | Brief generated and card shown in #ai-brief-slot | Brief card appeared with analysis status and "자세히 >" link | **PASS** |
| 3.4 | "편집" link | Click | Navigate to contact edit form | Navigated to /contacts/{uuid}/edit/ with pre-filled form | **PASS** |
| 3.5 | Back arrow | Click | Navigate back to contacts list | Navigated to /contacts/ | **PASS** |
| 3.6 | Interaction edit button (GET) | Click pencil on interaction | Edit form appears inline | Form with type dropdown, content textarea, save/cancel replaced interaction card | **PASS** |
| 3.7 | Interaction delete button (POST) | Click trash + confirm | Interaction removed after confirm | Dialog "이 접점 기록을 삭제하시겠습니까?" shown, interaction removed | **PASS** |

### 4. Contact Form (http://localhost:8000/contacts/new/)

| # | Element | Action | Expected | Actual | Result |
|---|---------|--------|----------|--------|--------|
| 4.1 | Submit form (POST) | Fill name + click "등록하기" | Contact created and redirect to detail | Created contact and redirected to /contacts/{new-uuid}/ | **PASS** |
| 4.2 | Back arrow | Click | Navigate back to contacts list | Navigated to /contacts/ | **PASS** |

### 5. Meetings (http://localhost:8000/meetings/)

| # | Element | Action | Expected | Actual | Result |
|---|---------|--------|----------|--------|--------|
| 5.1 | "+" FAB | Click | Navigate to meeting form | Navigated to /meetings/new/ with form | **PASS** |
| 5.2 | "미팅 등록하기" empty state CTA | Click | Navigate to meeting form | Navigated to /meetings/new/ | **PASS** |

### 6. Matching (http://localhost:8000/intelligence/matches/)

| # | Element | Action | Expected | Actual | Result |
|---|---------|--------|----------|--------|--------|
| 6.1 | "연락처 추가하기" CTA | Click | Navigate to contacts | Navigated to /contacts/ | **PASS** |

### 7. Settings (http://localhost:8000/accounts/settings/)

| # | Element | Action | Expected | Actual | Result |
|---|---------|--------|----------|--------|--------|
| 7.1 | Toggle switches (checkboxes) | Click | Toggle state (visual only OK for prototype) | Toggles work visually but have no server interaction (no hx-post, no name attr) | **PASS** (visual only, acceptable for prototype) |

### 8. Import (http://localhost:8000/contacts/import/)

| # | Element | Action | Expected | Actual | Result |
|---|---------|--------|----------|--------|--------|
| 8.1 | File upload area | Click | Opens file picker | Upload area is wrapped in `<label>` with hidden `<input type="file">` -- click triggers file input | **PASS** |
| 8.2 | "AI 분류 시작" button | Observe without file | Button should be disabled | Button correctly disabled with gray styling | **PASS** |

---

## MOBILE VIEWPORT TESTS (375x812)

| Page | Horizontal Overflow | Layout | Result |
|------|---------------------|--------|--------|
| Dashboard | No (scrollWidth=375) | Content fits, bottom nav visible | **PASS** |
| Contacts list | No (scrollWidth=375) | Filter chips horizontally scrollable, cards fit | **PASS** |
| Contact detail | No (scrollWidth=375) | All sections stack nicely, bottom nav visible | **PASS** |
| Settings | No (scrollWidth=375) | Profile/notification/app info cards fit | **PASS** |
| Import | No (scrollWidth=375) | Upload area and button fit | **PASS** |
| Meetings | No (scrollWidth=375) | Empty state centered, FAB visible | **PASS** |

---

## SUMMARY

| Category | Pass | Fail | Total |
|----------|------|------|-------|
| Dashboard interactions | 9 | 0 | 9 |
| Contacts list interactions | 5 | 3 | 8 |
| Contact detail interactions | 7 | 0 | 7 |
| Contact form | 2 | 0 | 2 |
| Meetings | 2 | 0 | 2 |
| Matching | 1 | 0 | 1 |
| Settings | 1 | 0 | 1 |
| Import | 2 | 0 | 2 |
| Mobile viewport | 6 | 0 | 6 |
| **TOTAL** | **35** | **3** | **38** |

**Pass rate: 92% (35/38)**

All 3 failures stem from the same root cause: the industry filter system. The filter chips send generic category names but the database stores specific KSIC industry names, causing zero-match on every filter. The count and chip highlight state are also not updated because they live outside the HTMX swap target.

### Console Errors

No JavaScript errors detected. Only Tailwind CDN warnings (expected for development).
