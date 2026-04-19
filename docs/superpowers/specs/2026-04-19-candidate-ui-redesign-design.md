# Candidate UI 재설계 — Design Spec (Phase D)

- **작성일**: 2026-04-19
- **선행**: [Phase C 핸드오프](../../session-handoff/2026-04-19-phase-c-complete.md)
- **목업 원본**: [assets/ui-sample/candidate-list.html](../../../assets/ui-sample/candidate-list.html), [assets/ui-sample/candidate-detail.html](../../../assets/ui-sample/candidate-detail.html)
- **접근**: 목업 UI 그대로 이식. 데이터 갭은 기존 모델 매핑 or 신규 필드/폼으로 메움. 사이드바·헤더 등 전역 레이아웃은 손대지 않음.

---

## 1. 스코프

### 대상
1. **Candidate 메인(List)** — [candidates/templates/candidates/search.html](../../../candidates/templates/candidates/search.html)
2. **Candidate 상세(Detail)** — [candidates/templates/candidates/partials/candidate_detail_content.html](../../../candidates/templates/candidates/partials/candidate_detail_content.html)
3. **후보자 추가(Add)** — 신규 화면

### 영향 범위
- `common/base.html`, `common/nav_sidebar.html` — **건드리지 않음**
- 챗봇 관련: `chatbot_fab.html`, `chatbot_modal.html`, `chatbot.js` — List 하단 고정 바로 이식. **FAB은 제거**.
- Project 상세 "DB에서 찾기" 경로(`?project=<uuid>`): 기존대로 작동 유지
- 리뷰 큐(`review_list.html`, `review_detail.html`) — 변경 없음

### 비대상 (별도 스프린트)
- 사이드바·상단 헤더 리디자인
- Dashboard, Newsfeed, Reference 페이지 리디자인
- `CandidateEmbedding` 벡터검색·`DiscrepancyReport` 파이프라인 등 백엔드 로직

---

## 2. List 페이지 설계

### 2.1 레이아웃 (메인 콘텐츠 영역)

```
[Page header] Global Talent Pool / Candidates
  · 등록된 후보자 N명을 검색하고 검수하세요
  · 우측: [Add Candidate] 버튼 (Filters 버튼은 제거)

[Category chips row] horizontal-scroll
  · 전체 · 1,284 / 기술 · 524 / ...
  · 각 칩: Category.name_ko (fallback: name) + 카테고리별 count

[Candidate card grid] 2-col (lg 이상), 1-col (모바일)
  · 카드 8~20개씩 서버 사이드 페이징 + 무한 스크롤 (HTMX intersect)
```

하단 **고정 검색바**는 §2.4 별도.

### 2.2 카드 구성

각 카드의 데이터 소스:

| 목업 요소 | 데이터 |
|---|---|
| avatar (skeleton SVG) | 하드코딩 — 실제 사진 없음 |
| 이름 | `candidate.name` |
| 우측 뱃지 (중요/주의/참고) | `candidate.review_notice_red_count` / `yellow_count` / `blue_count`. 가장 높은 severity 하나만 노출 (RED > YELLOW > BLUE). 0건이면 뱃지 생략. |
| 나이 · 생년 | `birth_year` → "(Xseasons · YYYY년생)" (현재 연도 - birth_year). 없으면 생략 |
| 현 회사 · 직책 | `current_company` · `current_position` |
| 총 경력 "X년" | `total_experience_display` (기존 프로퍼티) — "15년 4개월" 중 "15년"만 표시 |
| 카테고리 태그 (진한색) | `primary_category.name_ko` 우선, fallback `name`. 없으면 생략 |
| 스킬 태그 (얕은색) | `skills` JSONField에서 앞 3~4개. 객체면 `{name}`, 문자열이면 그대로 |
| 2줄 요약 (line-clamp-2) | `summary` 필드 |
| 하단 메타 한 줄 | `address(앞 1~2토큰 "서울")` · 첫 `educations[0].institution` · 전 `careers[1].company` 조합. 빈 값은 건너뜀 |
| 우하단 액션 아이콘 | 이메일 (mailto:) · 별표(클릭 시 즐겨찾기) — **별표는 추후 구현**, 아이콘만 노출 |

카드 클릭 → `/candidates/<uuid>/` (HTMX push-url).

**프로젝트 컨텍스트 모드** (`?project=<uuid>`): 기존 로직대로 카드 하단에 "프로젝트에 추가" 버튼 노출 (목업 기본 상태 위에 덧붙임).

### 2.3 카테고리 칩

- 기존 `Category.candidate_count` 필드 사용
- "전체" 칩: 전체 `Candidate` count
- "N" 표시 서식: 목업대로 "기술 · 524" (name_ko + · + count)
- 액티브 칩: 짙은 배경
- 가로 스크롤: 기존 `search.html` 스크롤 동작 유지 (fade + arrow)

### 2.4 하단 고정 검색바 (챗봇 FAB 대체)

챗봇 FAB (`chatbot_fab.html`)를 제거하고 하단 중앙 고정 바로 이식. **기존 `chatbot.js`의 상태 전환 로직을 참조·재사용하되 DOM은 하단 고정 바 맞춤으로 새로 작성** (상태머신: idle → recording → processing → text).

**상태별 UI**:

1. **Idle (기본)**
   - 왼쪽: 검색 아이콘 + placeholder "후보자 이름, 회사, 직군 검색 — 또는 마이크로 말해보세요"
   - 텍스트 input (readonly-esque, click/focus 시 입력 모드 전환)
   - 오른쪽: 마이크 버튼 (ink 색 원형)

2. **Text Input (input 포커스)**
   - 마이크 버튼 → **전송 버튼** (arrow-up 아이콘)으로 교체
   - Enter 또는 전송 버튼 클릭 → `/candidates/search/` POST (기존 `search_chat` view 재사용)
   - Esc 또는 빈 값 blur → idle 복귀

3. **Recording (마이크 클릭)**
   - 입력창 위치에 **파형 애니메이션 바** + 녹음 타이머 (00:00)
   - 마이크 버튼 → **빨간 원형 정지 버튼** (`fa-circle-stop`)
   - 기존 `voice-recording` DOM 구조 그대로 가져와 fixed bar에 맞게 스타일 조정
   - 정지 클릭 → recording 중지 → processing 상태로 전환

4. **Processing (STT 중)**
   - 파형 영역 → 스피너 + "음성 인식 중..." 텍스트
   - STT 완료되면 텍스트 input에 결과 주입 후 자동 전송 (기존 `chatbot.js` 플로우)

**검색 결과 표시**:
- 기존 `search_chat` view가 HTMX로 `#candidate-list` 영역을 교체하는 흐름 유지
- 메시지 히스토리(AI 응답, "N명 찾음" 등)는 기존 `chat-messages` DOM 제거. 이번 재설계에서는 **검색 결과를 메인 카드 그리드에 바로 반영**. 대화 히스토리는 향후 필요 시 별도 섹션.

**챗봇 모달 제거 후 보존할 것**:
- `/candidates/voice/` endpoint — 그대로 사용
- `search_chat` view 서버 로직 — 그대로 사용
- `SearchSession`/`SearchTurn` 모델 — 그대로 기록
- `chat-messages` DOM과 좌측 AI 응답 말풍선 UI — **이번 spec에서는 제거**. 검색 결과는 카드 그리드로만 보여줌. (복귀 원하면 추후 추가)

### 2.5 Add Candidate 화면

**버튼 위치**: List page header 우측 상단.

**화면 구성** (신규 뷰 `candidate_create` — `/candidates/new/`):

**섹션 1 — 필수 정보**
- 이름 (required)
- 이메일 또는 전화 중 하나 이상 (둘 다 비면 submit 불가 — identity matching 정책)

**섹션 2 — 선택 정보**
- 현 회사
- 현 직책
- 생년 (YYYY)
- 카테고리 (`primary_category` Select box)
- 소스 (`source` Select: manual / referral / linkedin 등)

**섹션 3 — 이력서 업로드 (선택)**
- 파일 업로드 (pdf/docx/doc, 최대 10MB)
- 업로드하면 Drive `AI_HH > DB > 수동등록` 폴더에 저장 → `Resume` 레코드 생성 → `processing_status = pending`
- **파싱은 비동기**: `data_extraction` 파이프라인 큐잉. 사용자는 리뷰 큐 (`/candidates/review/`)에서 추후 확인

**제출 동작**:
- Candidate 생성 → `owned_by = request.user.organization`
- 이력서 첨부된 경우 `Resume` 생성 + `current_resume = resume` 연결
- 성공 시 `/candidates/<new_pk>/` redirect

**유효성·에러 처리**:
- identity matching: 동일 `email` 또는 `phone_normalized`가 같은 조직 내 이미 존재하면 **"기존 후보자 X와 동일인으로 의심됩니다. 해당 후보자로 이동하시겠습니까?"** 경고 후 confirmation
- 파일 크기/확장자 초과 시 서버 측 reject + 메시지

### 2.6 Filters 버튼

**제거**. 복잡한 필터 조합은 하단 검색바의 자연어 질의(텍스트 or 음성)로 처리.

---

## 3. Detail 페이지 설계

### 3.1 레이아웃

```
[Back link] ← Back to Pipeline

[Profile header]                                [CTA: Export PDF] [Contact Candidate]
  avatar-xl (skeleton) with Status pill
  │
  Candidate Profile eyebrow
  이름 [review-notice 뱃지]   (41세 · 1985년생)
  VP of Engineering · 카카오엔터프라이즈
  [주소 pill] [Identity Verified pill] [총 경력 15년 4개월 pill]

[12-col grid]
  LEFT (col-span-8)
    - Summary
    - Work Experience (timeline)
    - Personal (2-col grid)
    - Matched Projects
    - Comments

  RIGHT (col-span-4)
    - Core Expertise
    - Education
    - Certifications
    - Languages (4-dot bar)
    - Activity Snapshot
```

보존하는 기존 섹션 (목업에 없지만 현재 있음):
- Overseas Experience, Self Introduction, Family Info, Awards, Patents — 데이터가 있을 때만 노출하는 기존 로직 그대로 유지 (LEFT 또는 RIGHT 컬럼에 배치)
- Review Notice 카드, 이력서 원본 텍스트 섹션 (validation_status == needs_review/failed) — 그대로 유지

### 3.2 Profile Header

**avatar-xl** (132×132): skeleton SVG. 하단 중앙에 status pill.

**Status pill** (목업의 "Active" 자리): **review notice 최고 severity 뱃지로 교체**
- `review_notice_red_count > 0` → "중요 N건" (rose 배경)
- `yellow_count > 0` → "주의 N건" (amber 배경)
- `blue_count > 0` → "참고 N건" (slate 배경)
- 전부 0 → pill 자체 생략 (이전 Status 표시도 없애기)

**이름 옆 뱃지**: List 카드와 동일한 review-notice 뱃지 (최고 severity 하나).

**나이 표시**: `{{ current_year }} - birth_year` → "(41세 · 1985년생)". birth_year 없으면 생략.

**meta pills (3개)**:
1. 주소 pill — `candidate.address` 있을 때
2. Identity Verified — `validation_status in ("confirmed", "auto_confirmed")` 일 때
3. 총 경력 pill — `computed_total_experience_display` 사용 (상세: "15년 4개월")

**CTA 버튼**:
- Export PDF → 기존 `primary_resume.drive_file_id` 있으면 Drive 링크로 열기 (현재 동작 유지)
- Contact Candidate → `mailto:{{ candidate.email }}`

### 3.3 Summary

- `candidate.summary` 있을 때만 노출
- 없으면 섹션 자체 생략 (목업과 동일)

### 3.4 Work Experience (timeline)

- `careers` prefetch, `is_current` 내림차순, `order` 정렬
- 각 아이템:
  - position (H4)
  - company + `department`
  - `start_date_display` — `end_date_display` + ` · {duration_display}` eyebrow
  - `is_current` → "Present" 뱃지 (ink 색), 아니면 "Previous" (faint)
  - 본문: `duties` (truncatewords:60)
  - **주요 성과 박스** (목업의 하이라이트된 bullet 박스) — `achievements` 있을 때만
  - 기존 inferred_capabilities (AI 추정 역량) 박스 보존
  - 기존 salary / reason_left disclosure 보존

### 3.5 Personal

2-col grid (목업 기준):
- 생년 / 성별
- 카테고리 / 이메일
- 현재 연봉 / 희망 연봉 (목업 기준; 기존 전화/군역 등은 아래 collapse로)

기존 `salary_detail`, `military_service`, `personal_etc` disclosure/collapse 그대로 보존.

### 3.6 Matched Projects

`candidate_applications` (현재 view에서 이미 로딩) 사용.
- 각 카드:
  - `app.project.client.name · app.project.title`
  - eyebrow: "Stage N · {current_state}" + drop/hire 상태
- 빈 상태: "아직 매칭된 프로젝트가 없습니다."

### 3.7 Comments

기존 `_comment_section.html` + `_comment_list.html` 그대로 포함. 헤더 스타일만 목업에 맞춰 조정.

### 3.8 Right Sidebar

**Core Expertise**
- `core_competencies` (JSONField) 항목 → `skill-tag.is-core` (ink 배경)
- `skills` 항목 → 일반 `skill-tag` (회색 배경)

**Education**
- 기존 로직. 목업 스타일(graduation cap 아이콘 + 학위/학교/졸업년도 "Class of YYYY").
- 기존 `trainings_data` 하위 섹션 보존.

**Certifications**
- 기존 로직. 목업 스타일(border-line 박스).

**Languages** — 4-dot bar (룰 기반 매핑)

```python
def language_level_bars(lang: LanguageSkill) -> int:
    """Return 1-4 for UI dot bar."""
    level = (lang.level or "").strip().lower()
    test = (lang.test_name or "").strip().lower()
    score = (lang.score or "").strip().lower()

    level_map_4 = {"native", "원어민", "모국어", "상", "a"}
    level_map_3 = {"business", "fluent", "advanced", "고급", "중상", "b"}
    level_map_2 = {"conversational", "intermediate", "중급", "중", "c"}
    level_map_1 = {"basic", "beginner", "초급", "하", "d"}

    for key in level_map_4:
        if key in level or key in test or key in score: return 4
    for key in level_map_3:
        if key in level or key in test or key in score: return 3
    for key in level_map_2:
        if key in level or key in test or key in score: return 2
    for key in level_map_1:
        if key in level or key in test or key in score: return 1
    return 2  # default — 정보 부족 시 중간값
```

- 템플릿: 4개 span, `forloop.counter <= bars` 면 `.on` 클래스
- Level 라벨: `level or test_name or "—"`

**Activity Snapshot**
- 섹션 유지. Response rate는 완전 제거.
- 나머지는 "준비중" 표시:
  - Profile views: "준비중" (faint 색)
  - Last contacted: "준비중"
  - Added to pipeline: **실제로 표시** = `candidate.created_at|date:"Y-m-d"`

### 3.9 보존 섹션 (목업 외 추가)

조건부 노출로 유지 (데이터 있을 때만):
- Review notice section — 헤더 위에 경고 박스
- Resume parse error box — `primary_resume.error_message` 있을 때
- Overseas experience, Self introduction, Family info (collapse), Awards, Patents — 기존 로직 그대로 우측 또는 좌측에 배치. 목업 전체 스타일에 맞게 background/border만 손질.
- Raw resume text (validation_status needs_review/failed 케이스) — 바닥 collapse로 보존

---

## 4. 스타일 · 디자인 토큰

목업의 CDN Tailwind config를 재현. 핵심 커스텀은 [docs/design-system.md](../../design-system.md)와 동기화 필요:

- Colors: canvas/surface/ink/ink2/ink3/muted/faint/hair/line/success/warning/info/danger
- 새로 쓰는 커스텀 그림자: `shadow-card`, `shadow-lift`, `shadow-searchbar`
- `.eyebrow` utility class (font-size 10px, uppercase, letter-spacing 0.08em)
- `.tnum` utility class (tabular-nums)
- 카드: `rounded-card` (16px) + `shadow-card` + hover시 `top: -2px` 리프트
- 기존 `hide-scrollbar` utility 그대로 사용

설계 원칙:
- **Tailwind CDN 대신 실제 tailwind.config.js에 토큰 추가** — project 페이지 Phase A/B/C에서 이미 일부 토큰 정의됨. 차이점만 보완.
- 새로 추가할 토큰은 단일 커밋으로 분리 (디자인 시스템 확장)

---

## 5. URL · View · 템플릿 매핑

### 5.1 신규 URL

| URL | view | template |
|---|---|---|
| `/candidates/new/` | `candidate_create` | `candidates/candidate_form.html` |

### 5.2 변경되는 URL / view

| URL | 변경 |
|---|---|
| `/candidates/` | view는 거의 그대로. template만 `search.html` 구조 전면 교체 |
| `/candidates/<pk>/` | view 동일. template `detail.html` + `candidate_detail_content.html` 구조 교체 |
| `/candidates/search/` | 기존 `search_chat` 그대로 — 응답 target만 `#candidate-list` |
| `/candidates/voice/` | 기존 `voice_transcribe` 그대로 |

### 5.3 제거되는 템플릿 (dead code 확인 후)

- `partials/chatbot_fab.html` — 제거
- `partials/chatbot_modal.html` — 제거 (DOM은 하단 바에 통합)
- `partials/chat_messages.html` — 제거 (메시지 히스토리 안 씀)

### 5.4 신규 템플릿

- `candidates/candidate_form.html` — Add Candidate 화면
- `partials/search_bar_fixed.html` — 하단 고정 검색바 (List 하단에 include)
- `partials/candidate_card_v2.html` — 새 카드 스타일 (기존 `candidate_card.html` 대체)

---

## 6. 데이터 · 신규 필드

### 6.1 Candidate 모델

- **신규 필드 없음**. 기존 모델 프로퍼티만 사용.

### 6.2 Category

- 기존 `candidate_count` 필드 사용. 정합성 유지를 위해 update 트리거 확인 필요.
- (확인사항) Candidate-Category M2M 변경 시 `candidate_count` 자동 갱신되는지 signal/save 로직 점검. 없으면 signal 추가.

### 6.3 마이그레이션

- 모델 스키마 변경 없음 → **새 migration 없음** (데이터 backfill도 불필요)

### 6.4 Drive 폴더

- Add Candidate의 이력서 업로드용 폴더 "수동등록" 하위 폴더가 없으면 신규 생성. [Drive parent folder ID: 1k_VtpvJo8P8ynGTvVWS8DtYtK4gZDF_Y](memory:reference_drive_resume_folders)

---

## 7. 음성/STT 이식 상세

`chatbot.js`에서 필요한 함수·상태만 추출하여 새 파일 `candidates/static/candidates/search_bar.js`로 재구성:

**재사용할 함수**:
- `startRecording()`, `toggleRecording()`, `showTextInput()`, `hideTextInput()`, `sendMessage()`
- MediaRecorder mime-type 선택 로직 (`audio/webm;codecs=opus` 등)
- `/candidates/voice/` 호출 후 transcript → input 주입
- 5초/20초 Rate limit 처리 (기존 로직)

**삭제할 함수**:
- `toggleChatbot()`, overlay 제어
- `chat-messages` DOM 조작 (searchWithChip, appendMessage 등)

**상태 전환**:
- idle → text-input: input focus 이벤트
- idle → recording: 마이크 클릭
- recording → processing: 정지 클릭 → MediaRecorder.stop()
- processing → idle or text-input: STT 결과 세팅 후 자동 전송
- text-input → idle: Esc 또는 빈 값 blur

---

## 8. 테스트

기존 테스트 유지 + 다음 신규 케이스:

### 8.1 List 페이지
- 카드 렌더링: review_notice 0/red/yellow/blue 각 케이스 뱃지 노출 확인
- 카테고리 칩 count 일치 (`Category.candidate_count`와 queryset count)
- 하단 검색바 렌더링 (HTMX/JS 상태 전환은 수동 확인)
- 프로젝트 컨텍스트 모드(`?project=`) 유지

### 8.2 Detail 페이지
- Status pill — review notice 매핑 (red > yellow > blue > 생략) 분기 4개
- Languages 4-dot 매핑 — level "Native"/"Business"/"중급"/"Basic"/빈값 5 케이스
- Matched Projects 빈 상태 vs 있음
- 보존 섹션 (Overseas/Awards 등) 데이터 유무 분기

### 8.3 Add Candidate
- email/phone 둘 다 비어 submit → 400
- 동일 email/phone 중복 등록 경고
- 파일 업로드 시 Resume 레코드 생성 + `current_resume` 연결
- 파일 확장자·크기 초과 reject
- owned_by가 request org로 세팅되는지

---

## 9. Phase C에서 이어받은 Minor 이슈 (선택적으로 함께 정리)

Phase D 범위가 candidates 중심이라 직접 관련 없지만, 작업 중 발견되면 같이 수정할 후보:
- I4 (`stage_resume.html`의 `candidate.current_resume` N+1) → 이번 Detail view에서도 `select_related("current_resume")` 한 번 더 확인
- M2 (지역 import 중복) → 동일 패턴이 candidates view에 있으면 정리

강제는 아님. 별도 스프린트로 분리 가능.

---

## 10. 구현 순서 (예상)

구체 플랜은 writing-plans에서 확정. 큰 흐름:

1. **디자인 토큰 · 유틸 추가** — tailwind config 확장, `.eyebrow` / `.tnum` 등
2. **List 카드 v2 + 카테고리 칩 count** — 기존 `candidate_card.html` → `candidate_card_v2.html` 교체
3. **하단 고정 검색바** — 챗봇 모달 이식 + FAB 제거
4. **Add Candidate 화면** — form + view + upload 파이프라인
5. **Detail 헤더 + meta pills + Status 뱃지 교체**
6. **Detail 본문 재구성** — Summary/Work/Personal/Matched/Comments 재배치
7. **Detail 사이드바** — Core/Education/Certifications/Languages/Activity 재배치
8. **음성 JS 리팩터** — `search_bar.js` 신규, `chatbot.js` 제거
9. **테스트 보강** + 정리 스윕

각 단계는 Phase C 때와 동일하게 subagent-driven-development로 분할.

---

## 11. 미해결 · 향후 고려

- **별표 즐겨찾기** — 카드 하단 별 아이콘은 이번에 기능 없음. 향후 `CandidateBookmark` 모델 추가 시 활성화.
- **카테고리별 count 자동 갱신** — 아직 수동일 수 있음. Candidate save 시그널 or 배치 커맨드 중 하나로 정리 필요 (확인 후 결정).
- **Profile views / Last contacted / (Activity Snapshot)** — "준비중" 상태. 이후 analytics 기능 스프린트에서 구현.
- **Export PDF** — 현재는 Drive 원본 링크. 실제 PDF 내보내기(후보자 요약본 생성)는 별도 스프린트.
- **사이드바·헤더 리디자인** — Candidate/Project 완료 후 Dashboard 단계에서 같이 진행.
