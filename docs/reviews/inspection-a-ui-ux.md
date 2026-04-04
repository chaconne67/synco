# 점검 A: UI/UX 디자인 리뷰

점검일: 2026-04-04
점검 범위: 데이터 추출 관련 템플릿 (후보자 상세, 카드, 리뷰, 검색)

---

## Critical (사용성에 직접 영향)

### C-1. details/summary "기타 정보"에 hover/transition 없음 — 인터랙션 피드백 부족
- `candidate_detail_content.html:176` — `<summary class="text-[13px] text-gray-500 cursor-pointer">기타 정보</summary>` (personal_etc)
- `candidate_detail_content.html:249` — 동일 패턴 (education_etc)
- `candidate_detail_content.html:360` — `<summary class="text-[13px] text-gray-500 cursor-pointer">프로젝트 및 기타</summary>` (career_etc)
- `candidate_detail_content.html:497` — 동일 패턴 (skills_etc)

같은 파일의 다른 details/summary는 `hover:text-gray-600 transition select-none`을 포함하지만(line 134, 313, 602), etc 계열 4개 summary에는 `hover:text-gray-600 transition select-none`이 빠져 있다. 클릭 가능한 영역임에도 hover 시 시각적 피드백이 없어 사용자가 인터랙티브 요소임을 인지하기 어렵다.

### C-2. etc "기타 정보" summary의 클릭 영역이 너무 작음 (접근성)
- `candidate_detail_content.html:176`, `249`, `497`

이 3개 summary에는 `py-2` 패딩이 없다. 반면 같은 파일의 salary details summary(line 134), career reason_left summary(line 313), 데이터 완성도 상세 summary(line 602)에는 모두 `py-2`가 있다. 패딩 없는 summary는 터치 타겟이 약 18px로, WCAG 최소 44px 권장 기준에 크게 미달한다.

### C-3. 카테고리 점수에 raw float 표시 — 사용자가 해석 불가
- `candidate_detail_content.html:610`
```html
<span class="w-[32px] text-right font-medium ...">{{ score }}</span>
```
`category_scores` 값은 Python float (예: `0.6666666666666666`)로 반환된다. `{% widthratio %}` 필터가 바 너비에는 적용되었으나(line 608) 텍스트 레이블에는 적용되지 않아, "0.6666666666666666" 같은 값이 32px 폭 span에 그대로 표시된다. 소수점 잘림 없이 overflow 발생 가능.

### C-4. 리뷰 상세 페이지에서 새 필드 미노출
- `review_detail_content.html` — 리뷰 상세 페이지는 기본 정보, 경력, 학력, 자격증/어학, 원문 텍스트만 표시한다. views.py `review_detail()`에서 `salary_detail`, `military_service`, `awards`, `skills`, `personal_etc` 등 신규 필드 컨텍스트를 전달하지 않으며, 템플릿에서도 해당 섹션이 없다. 검토자가 이력서 전체 추출 결과를 볼 수 없으므로 정확한 검토가 불가능하다.

---

## Warning (디자인 일관성 위반)

### W-1. 카테고리 헤더(h2)와 섹션 헤더(h3)가 동일 스타일 — 시각적 계층 구분 부재
- `candidate_detail_content.html:54` — `<h2 class="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3 mt-6">인적사항</h2>`
- `candidate_detail_content.html:58` — `<h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">기본 정보</h3>`

4대 카테고리 헤더(h2)와 그 아래 섹션 헤더(h3)가 완전히 동일한 Tailwind 클래스를 사용한다. h2에 `mt-6`이 있어 간격으로만 구분되나, 폰트 크기/무게/색상이 동일하므로 카테고리 구분이 시각적으로 드러나지 않는다. h2에 `text-[13px] font-semibold text-gray-700` 같은 차별화 스타일이 필요하다.

### W-2. review_detail_content.html의 헤더 스타일이 candidate_detail_content.html과 불일치
- `review_detail_content.html:10` — `<h1 class="text-lg font-bold text-gray-900">`
- `candidate_detail_content.html:15` — `<h1 class="text-heading text-gray-900">`

리뷰 상세의 h1은 `text-lg font-bold`(18px, 700), 후보자 상세의 h1은 `text-heading`(24px, 700). 같은 후보자를 보는 두 페이지에서 이름 표시 크기가 다르다. `text-heading`이 프로젝트 표준이므로 리뷰 상세도 동일하게 맞춰야 한다.

### W-3. review_detail_content.html 섹션 헤더 vs candidate_detail_content.html 섹션 헤더 스타일 불일치
- `review_detail_content.html:35` — `<h2 class="text-subheading text-gray-900 mb-3">` (18px, semibold, gray-900)
- `candidate_detail_content.html:58` — `<h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">` (14px, medium, gray-500, uppercase)

같은 데이터를 보여주는 두 페이지에서 섹션 헤더가 완전히 다른 스타일이다. 하나는 크고 진한 글씨, 다른 하나는 작고 회색 대문자.

### W-4. skills[] 태그 색상이 core_competencies 태그와 비조화
- `candidate_detail_content.html:44` — core_competencies: `text-primary bg-primary-light px-2.5 py-1 rounded-full` (보라색 계열)
- `candidate_detail_content.html:393` — skills: `text-blue-700 bg-blue-50 border border-blue-200 px-2.5 py-1 rounded-full` (파란색 계열 + border)

core_competencies는 primary(보라) 색상에 border 없음. skills는 blue 색상에 border 있음. 기능적으로 유사한(역량/기술) 두 태그가 다른 색상 체계를 사용하며, skills만 border가 있어 시각적 무게가 다르다. 의도적 구분이라면 OK이나, 둘 다 "이 사람의 능력"이라는 맥락에서 혼란을 줄 수 있다.

### W-5. career_etc의 summary 텍스트가 다른 etc와 불일치
- `candidate_detail_content.html:176` — `기타 정보` (personal_etc)
- `candidate_detail_content.html:249` — `기타 정보` (education_etc)
- `candidate_detail_content.html:360` — `프로젝트 및 기타` (career_etc)
- `candidate_detail_content.html:497` — `기타 정보` (skills_etc)

personal_etc, education_etc, skills_etc는 "기타 정보"로 통일되어 있으나, career_etc만 "프로젝트 및 기타"로 다르다. 사용자 관점에서 어떤 카테고리의 기타 정보인지 구분이 안 되므로, "인적사항 기타", "학력 기타" 등으로 명확히 하거나, 혹은 모두 동일하게 "기타 정보"로 통일하는 것이 낫다.

### W-6. etc details가 카드 밖에 위치 — 레이아웃 불일치
- `candidate_detail_content.html:175` — `<details class="mt-3 mb-3">` (personal_etc, 카드 밖)
- `candidate_detail_content.html:248` — 동일 (education_etc)
- `candidate_detail_content.html:359` — 동일 (career_etc)
- `candidate_detail_content.html:496` — 동일 (skills_etc)

etc details는 `bg-white rounded-lg border` 카드 section 바깥에 위치한다. 같은 카테고리에 속하는 정보임에도 카드 안에 포함되지 않아 시각적으로 분리되어 보인다. 반면 salary의 details(line 133)는 카드 내부에 위치하고, family_info의 details(line 565)도 카드 내부에 위치한다.

### W-7. 데이터 완성도 바 차트 — 전체 바와 카테고리별 바의 높이 불일치
- `candidate_detail_content.html:597` — 전체 바: `h-2.5`
- `candidate_detail_content.html:608` — 카테고리 바: `h-1.5`

의도적인 계층 구분일 수 있으나, 같은 섹션 내에서 바 높이가 다르면 시각적 무게가 달라 카테고리별 점수가 덜 중요해 보인다.

### W-8. review_detail_content.html "자격증" 서브헤더에 영어 대문자 스타일 사용
- `review_detail_content.html:183` — `<h3 class="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">자격증</h3>`

한국어 "자격증"에 `uppercase`가 적용되어 있다. 한국어에는 대소문자 구분이 없어 기능적으로는 무해하지만, 의도와 맞지 않는 클래스 적용이다.

---

## Info (개선 제안)

### I-1. candidate_card.html에 review_notice 뱃지만 표시, 신규 필드(skills, etc) 미활용
- `candidate_card.html:43-57`

카드에서는 이름, 회사/직위, 카테고리, 학교, 경력사 회사만 표시한다. skills 태그나 총 경력 같은 핵심 정보가 없다. 단, 카드는 목록에서의 간략 표시이므로 의도적 생략일 수 있음.

### I-2. 자기소개 전체 보기 판단 기준이 문자 수와 단어 수 혼용
- `candidate_detail_content.html:552` — `truncatewords:120` (단어 수 기반 자르기)
- `candidate_detail_content.html:553` — `self_introduction|length > 500` (문자 수 기반 판단)

한국어는 단어 구분이 영어와 달라 `truncatewords`가 예상과 다르게 동작할 수 있다. 또한 120단어 truncate 후에도 500자 초과 여부로 "전체 보기"를 표시하므로, 짧은 소개(120단어 미만)에서도 500자 넘으면 "전체 보기"가 표시되지만 전체 내용과 동일한 텍스트가 중복 렌더링된다.

### I-3. 데이터 완성도 상세 summary의 hover 색상이 동일
- `candidate_detail_content.html:602` — `text-gray-500 cursor-pointer hover:text-gray-500`

hover 색상이 기본 색상과 동일(`text-gray-500` -> `hover:text-gray-500`)하여 hover 시 시각적 변화가 없다. `hover:text-gray-600`이어야 일관성이 맞다.

### I-4. review_detail_content.html 뒤로가기 버튼이 `javascript:void(0)` + `onclick="history.back()"` 사용
- `review_detail_content.html:3-4`

candidate_detail_content.html(line 6-8)은 동일 패턴이되 `min-w-[44px] min-h-[44px]`로 접근성 최소 터치 영역을 확보한 반면, review_detail_content.html은 `mr-3` 정도만 있고 최소 크기 지정이 없다. 터치 기기에서 뒤로가기 버튼이 너무 작을 수 있다.

### I-5. etc 섹션에서 데이터 없을 때 빈 details가 렌더링되지는 않지만, 템플릿 조건 검사 방식이 불완전할 수 있음
- `candidate_detail_content.html:174` — `{% if candidate.personal_etc %}`

JSONField의 default가 `list`이므로 빈 리스트 `[]`는 falsy여서 정상 동작한다. 그러나 만약 `None`이나 `[{}]`(빈 dict가 있는 리스트) 같은 값이 들어오면 빈 details가 렌더링될 수 있다. 방어 로직이 있으면 좋다.

### I-6. 검색 페이지 빈 상태 아이콘에 `aria-label` 누락
- `candidate_list.html:6` — 검색 결과 없을 때의 SVG 아이콘에 `aria-label`이 없다.
- `review_list_content.html:94` — 동일. 빈 상태 SVG에 접근성 레이블 없음.

스크린 리더 사용자를 위해 `aria-hidden="true"` 또는 `role="img" aria-label="..."` 추가 권장.

### I-7. candidate_card.html "정보 없음" span 색상 중복 적용
- `candidate_card.html:16` — `<span class="text-gray-500">정보 없음</span>`

부모 `<p>`가 이미 `text-gray-500`이므로 span의 `text-gray-500`은 중복이다. 기능상 문제는 없으나 불필요한 클래스.

### I-8. search.html에서 category 탭의 HTMX target이 `#main-content`
- `search.html:57-60`

카테고리 탭 클릭 시 `hx-target="#main-content"`로 전체 콘텐츠가 교체된다. 카테고리 전환 시 검색 영역만 교체하는 것이 사용자 경험상 더 부드러울 수 있으나, 현재 구조에서는 상태 바와 리스트가 분리되어 있어 전체 교체가 합리적일 수도 있다.

---

## Round 2 재점검

재점검일: 2026-04-04
재점검 범위: `candidate_detail_content.html`, `review_detail_content.html`, `views.py`

---

### C-1. etc summary hover/transition 누락 → **FIXED**

- 이전: `personal_etc`(line 176), `education_etc`(line 249), `career_etc`(line 360), `skills_etc`(line 497) 4개 summary에 `hover:text-gray-600 transition select-none` 누락.
- 현재: 4개 모두 `hover:text-gray-700 transition select-none` 추가 확인.
- 판정: **FIXED** (`hover:text-gray-600` 대신 `hover:text-gray-700`이 적용되었으나 hover 피드백 자체는 정상 제공됨. 색상 차이는 미미하여 허용 범위.)

---

### C-2. etc summary 클릭 영역 44px 미달 → **FIXED**

- 이전: `personal_etc`(line 176), `education_etc`(line 249), `skills_etc`(line 497) 3개에 `py-2` 누락.
- 현재: 4개 etc summary 모두 `py-2` 포함 확인.
- 판정: **FIXED**

---

### C-3. 카테고리 점수 raw float overflow → **FIXED**

- 이전: `<span ...>{{ score }}</span>` — Python float 값이 그대로 렌더링되어 32px 폭 span overflow.
- 현재: `{% widthratio score 1 100 %}%` 로 변경 (line 610). 텍스트 레이블에도 widthratio 필터 적용.
- 판정: **FIXED**

---

### C-4. 리뷰 상세 페이지 신규 필드 컨텍스트 미전달 → **NOT_FIXED**

- 이전: `views.py review_detail()`에서 `salary_detail`, `military_service`, `awards`, `skills`, `personal_etc` 등 신규 필드를 컨텍스트에 전달하지 않음.
- 현재: `review_detail()` 함수 (line 107~166)를 확인한 결과 여전히 `salary_detail`, `military_service`, `awards_data`, `projects_data`, `trainings_data`, `overseas_experience`, `family_info`, `self_introduction` 등을 컨텍스트에 전달하지 않음.
- `review_detail_content.html`도 기본정보/경력/학력/자격증·어학/원문텍스트/추출이력만 표시하며, 병역·연봉상세·수상·프로젝트·기타 섹션이 없음.
- 판정: **NOT_FIXED** — 검토자가 이력서 추출 결과 전체를 볼 수 없어 검토 품질에 직접 영향.

---

### W-4. skills 태그와 core_competencies 색상 불일치 → **FIXED**

- 이전: `skills` 태그 — `text-blue-700 bg-blue-50 border border-blue-200` (파란색 + border), `core_competencies` — `text-primary bg-primary-light` (보라색, border 없음).
- 현재: line 393 — `skills` 태그가 `text-primary bg-primary-light px-2.5 py-1 rounded-full`로 변경. `core_competencies`와 동일한 색상 체계, border 제거.
- 판정: **FIXED**

---

### W-5. etc summary 텍스트 불통일 → **PARTIALLY_FIXED**

- 이전: `personal_etc`/`education_etc`/`skills_etc`는 "기타 정보", `career_etc`만 "프로젝트 및 기타"로 불일치.
- 현재: 4개 etc summary 모두 "기타"로 통일됨.
- 미완: 어느 카테고리의 기타 정보인지 컨텍스트가 없음. 예: 인적사항 아래의 "기타"와 학력 아래의 "기타"가 동일한 텍스트라 구분이 어려움. "인적사항 기타", "학력 기타" 등으로 카테고리 명시가 여전히 필요함.
- 판정: **PARTIALLY_FIXED** (텍스트 통일은 달성, 카테고리 명시는 미해결)

---

### 신규 발견 이슈

#### N-1. 데이터 완성도 상세 summary hover 색상 여전히 동일 (I-3 미수정)
- `candidate_detail_content.html:602` — `hover:text-gray-500` (기본값과 동일). 이전 점검 I-3에서 지적했으나 여전히 수정되지 않음.
- 영향: hover 시 시각적 변화 없음.

#### N-2. review_detail_content.html 뒤로가기 버튼 최소 터치 영역 미확보 (I-4 미수정)
- `review_detail_content.html:3-4` — `<a ... class="text-gray-500 hover:text-gray-700 mr-3 cursor-pointer">`. `min-w-[44px] min-h-[44px]` 없음.
- `candidate_detail_content.html`의 동일 버튼(line 8)에는 `min-w-[44px] min-h-[44px]` 있음. 두 페이지 간 불일치 유지.
- 판정: **NOT_FIXED**

---

## Verified OK

- **한국어 텍스트**: 모든 UI 텍스트가 한국어로 작성됨. 레이블("인적사항", "학력", "경력", "능력", "기본 정보", "기타 정보" 등), 빈 상태 메시지("검토할 후보자가 없습니다", "검색 결과가 없습니다"), 버튼 텍스트("확인", "거부", "거부 확정", "취소") 모두 한국어. 기술적 레이블("AI 추출", "AI 생성", "AI 추론", "GPA")만 영문으로, 이는 도메인 용어로 적절함.
- **Tailwind 색상 시스템 사용 일관성**: 전체적으로 `gray-100/200/500/900`, `primary/primary-light/primary-dark`, `red/amber/green/blue` 계열을 일관되게 사용. 커스텀 hex 코드 없이 Tailwind 토큰만 사용.
- **반응형 레이아웃 — candidate_detail_content.html**: 기본 정보 섹션에 `md:grid md:grid-cols-2`(line 59) 사용, 모바일에서는 `space-y-2` 스택, 데스크톱에서는 2열 그리드. 경력 타임라인의 좌측 날짜 영역에 `whitespace-nowrap` 적용(line 273-276)으로 줄바꿈 방지.
- **반응형 레이아웃 — review_detail_content.html**: `grid grid-cols-1 lg:grid-cols-2`(line 28)로 데스크톱 2열, 모바일 1열 적절히 처리.
- **반응형 레이아웃 — search.html**: `max-w-4xl mx-auto` 컨테이너로 넓은 화면에서 적절히 제한. 카테고리 탭 스크롤에 `overflow-x-auto hide-scrollbar` + fade/arrow 처리 완비.
- **빈 상태 처리 — review_list_content.html**: 검토할 후보자 없을 때 아이콘 + 메시지 표시(line 92-99) 적절.
- **빈 상태 처리 — candidate_list.html**: 검색 결과 없을 때 아이콘 + 메시지 표시(line 4-12) 적절.
- **빈 상태 처리 — candidate_detail 각 섹션**: 모든 섹션이 `{% if ... %}` 가드로 감싸져 있어 데이터 없으면 섹션 자체가 렌더링되지 않음.
- **HTMX 패턴 일관성**: `hx-get` + `hx-target` + `hx-push-url="true"` 패턴이 search, review_list, candidate_card 등에서 일관되게 사용됨.
- **검토 사항 뱃지 — _review_notice_section.html**: severity별 색상 (red/amber/slate) 3단계가 일관되게 적용. 카드(candidate_card.html:46-53)와 상세(_review_notice_section.html)에서 동일한 뱃지 스타일 사용.
- **Tailwind config의 커스텀 토큰**: `text-heading`(24px/700), `text-subheading`(18px/600), `text-display`(32px/700), `text-micro`(12px/400) 정의됨. 프로젝트 전반에서 일관 사용.
- **details/summary 내 salary_detail 패턴**: 카드 내부에서 `border-t border-gray-100 pt-3` 구분선 + summary + 접히는 콘텐츠 패턴이 정상 적용(line 133-148).
- **신뢰도 배지 스타일 일관**: review_list_content.html(line 43-49)과 review_detail_content.html(line 13-19)에서 동일한 3단계 색상(green/yellow/red) 배지 사용.
- **candidate_card.html 반응형**: `truncate` 클래스로 긴 텍스트 오버플로우 방지, `flex-wrap`으로 태그 줄바꿈 처리, `shrink-0`으로 경력 배지 크기 보전.
- **가족 사항 민감 정보 처리**: details로 기본 숨김 + 잠금 아이콘 + 경고 메시지(line 574-576) — 적절한 UX 패턴.
