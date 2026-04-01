# 후보자 상세 페이지 — 디자인 점검 리스트

> 대상 파일: `candidates/templates/candidates/partials/candidate_detail_content.html`
> 기준 문서: `docs/candidate-detail-design-plan.md`
> 작성일: 2026-03-31

---

## 1. 레이아웃

### 1.1 섹션 배치 순서

- [ ] 헤더(이름 + 영문 이름) 가 최상단에 위치하는가 (파일 상단, `<h1>` 포함 영역)
- [ ] "경력 요약 + 핵심 역량" 신규 섹션이 헤더 바로 아래, 기본 정보 **위**에 배치되었는가 (디자인 계획서 섹션 B)
- [ ] "기본 정보" 섹션이 경력 요약 섹션 아래에 위치하는가
- [ ] "연봉 정보" 신규 섹션이 기본 정보 **아래**, 경력 **위**에 배치되었는가 (디자인 계획서 섹션 D)
- [ ] "경력" 섹션이 연봉 정보 아래에 위치하는가
- [ ] "학력" 섹션이 경력 아래에 위치하는가
- [ ] "자격증 · 어학" 섹션이 학력 아래에 위치하는가
- [ ] "파싱 신뢰도" 섹션이 최하단에 위치하는가
- [ ] 최종 섹션 순서가 `헤더 → 경력 요약 → 기본 정보 → 연봉 정보 → 경력 → 학력 → 자격증·어학 → 파싱 신뢰도` 인가

### 1.2 섹션 간격

- [ ] 모든 섹션 카드에 `mb-3` 클래스가 적용되어 일관적인 간격을 유지하는가
- [ ] 경력 요약 섹션과 기본 정보 섹션 사이 간격이 `mb-3`인가
- [ ] 연봉 정보 섹션과 경력 섹션 사이 간격이 `mb-3`인가

### 1.3 데스크톱 레이아웃

- [ ] 기본 정보 섹션 내부가 데스크톱(md 이상)에서 2열 그리드로 표시되는가 (CSS: `md:grid md:grid-cols-2 md:gap-x-6 md:gap-y-2 md:space-y-0`)
- [ ] 모바일에서는 기본 정보가 단일 컬럼(`space-y-2`)으로 유지되는가

---

## 2. 필드 표시

### 2.1 헤더 — name_en

- [ ] `name_en`이 이름(`<h1>`) 아래에 서브타이틀로 표시되는가 (CSS: `text-sm text-gray-400`)
- [ ] `name_en`이 이름 옆이 아닌 아래줄에 배치되는가 (예시 2 — 서브타이틀 방식 권장)

### 2.2 기본 정보 섹션 — gender, address, source

- [ ] `gender` 필드가 기본 정보 섹션에 텍스트로 표시되는가 (`<span class="text-gray-500">성별:</span>` + 값)
- [ ] `gender`가 `birth_year` 바로 아래(2번 순서)에 배치되는가
- [ ] `address` 필드가 기본 정보 섹션에 텍스트로 표시되는가 (`<span class="text-gray-500">주소:</span>` + 값)
- [ ] `address`가 `primary_category` 아래(4번 순서)에 배치되는가
- [ ] `source` 필드가 `get_source_display`로 한국어 라벨을 출력하는가
- [ ] `source`가 `total_experience_years` 아래(7번 순서), `email`/`phone` 위에 배치되는가
- [ ] 기본 정보 내 필드 순서: 생년 → 성별 → 카테고리 → 주소 → 현재(회사/직책) → 총 경력 → 출처 → 이메일 → 연락처

### 2.3 연봉 섹션 — current_salary, desired_salary

- [ ] `current_salary`가 연봉 정보 섹션에 표시되는가
- [ ] `current_salary` 값에 `intcomma` 필터가 적용되어 천 단위 콤마가 포함되는가 (예: `8,000`)
- [ ] `current_salary` 값 뒤에 "만원" 접미사가 붙는가
- [ ] `current_salary` 값에 `font-semibold text-gray-900` 스타일이 적용되는가
- [ ] `desired_salary`가 연봉 정보 섹션에 표시되는가
- [ ] `desired_salary` 값에 `intcomma` 필터가 적용되어 천 단위 콤마가 포함되는가
- [ ] `desired_salary` 값 뒤에 "만원" 접미사가 붙는가
- [ ] `desired_salary` 값에 `font-semibold text-primary` 스타일이 적용되어 시각적으로 구분되는가

### 2.4 경력 요약 섹션 — summary, core_competencies

- [ ] `summary`가 경력 요약 섹션 내 본문 텍스트로 표시되는가 (CSS: `text-[15px] text-gray-700 leading-relaxed`)
- [ ] 경력 요약 섹션에 별도 섹션 타이틀(`<h2>`)이 없는가 (디자인 계획서: 타이틀 생략)
- [ ] `core_competencies`가 태그/칩 형태로 표시되는가 (CSS: `text-[13px] font-medium text-primary bg-primary-light px-2.5 py-1 rounded-full`)
- [ ] 핵심 역량 태그들이 `flex flex-wrap gap-1.5`로 가로 줄바꿈 레이아웃인가
- [ ] 핵심 역량 태그가 `summary` 텍스트 아래에 배치되는가 (CSS: `mt-3`)
- [ ] `summary`만 있고 `core_competencies`가 비어있을 때 태그 영역이 숨겨지는가
- [ ] `core_competencies`만 있고 `summary`가 비어있을 때 텍스트 없이 태그만 표시되는가

### 2.5 경력 섹션 — achievements, salary, reason_left

- [ ] `achievements`가 경력 항목 내부에 하이라이트 박스로 표시되는가 (CSS: `bg-amber-50 border border-amber-100 rounded-md p-2.5`)
- [ ] `achievements` 박스에 "주요 성과" 라벨이 있는가 (CSS: `text-[13px] font-medium text-amber-700 mb-1`)
- [ ] `achievements` 텍스트에 `linebreaksbr` 필터가 적용되어 줄바꿈이 보존되는가
- [ ] `achievements`가 `duties` 아래에 배치되는가
- [ ] `salary`(경력 항목)가 소형 텍스트로 표시되는가 (CSS: `text-[13px] text-gray-500 mt-1.5`)
- [ ] `salary`(경력 항목) 값에 `intcomma` 필터 + "만원" 접미사가 적용되는가
- [ ] `salary`가 `achievements` 아래에 배치되는가
- [ ] `reason_left`가 `<details>`/`<summary>` 접이식으로 구현되었는가
- [ ] `reason_left`가 기본 상태에서 접혀있는가 (기본 숨김)
- [ ] 접이식 라벨이 "퇴사 사유 보기"인가
- [ ] 접이식 내부 텍스트에 좌측 테두리 스타일이 적용되는가 (CSS: `pl-3 border-l-2 border-gray-200`)
- [ ] `is_current`가 true인 경력 항목에서 `reason_left`가 미노출되는가 (조건: `not career.is_current`)
- [ ] `reason_left`가 `salary` 아래(최하단)에 배치되는가

### 2.6 학력 섹션 — gpa, is_abroad

- [ ] `gpa`가 학력 항목의 서브라인(두 번째 줄)에 표시되는가 (CSS: `text-[13px] text-gray-500 mt-0.5 ml-0.5`)
- [ ] `gpa` 값 앞에 "GPA" 접두사가 붙는가 (예: `GPA 4.2/4.5`)
- [ ] `is_abroad`가 true일 때 학교 이름 옆에 "해외" 텍스트 뱃지가 표시되는가
- [ ] 해외 뱃지 스타일이 `text-[11px] font-medium text-blue-700 bg-blue-50 border border-blue-200 px-1.5 py-0.5 rounded-full ml-1`인가
- [ ] `is_abroad`가 false일 때 해외 뱃지가 미노출되는가

### 2.7 자격증 · 어학 섹션 — level

- [ ] 어학 칩에 `level` 값이 가운데점(` · `)으로 구분되어 추가되는가 (예: `영어 TOEIC 950 · 비즈니스`)
- [ ] `test_name`/`score` 없이 `level`만 있을 때 `영어 · 비즈니스` 형태로 표시되는가
- [ ] `level`이 빈값일 때 ` · level` 부분이 미노출되는가

---

## 3. null/빈값 처리

### 3.1 개별 필드

- [ ] `name_en`이 빈 문자열일 때 서브타이틀 영역이 완전히 숨겨지는가
- [ ] `gender`가 빈값일 때 해당 행이 완전히 숨겨지는가
- [ ] `address`가 빈값일 때 해당 행이 완전히 숨겨지는가
- [ ] `current_salary`가 None일 때 해당 행이 완전히 숨겨지는가
- [ ] `desired_salary`가 None일 때 해당 행이 완전히 숨겨지는가
- [ ] `core_competencies`가 빈 배열(`[]`)일 때 태그 영역이 완전히 숨겨지는가
- [ ] `summary`가 빈 문자열일 때 요약 텍스트가 완전히 숨겨지는가
- [ ] `source`가 빈값일 때 해당 행이 완전히 숨겨지는가
- [ ] `achievements`가 빈 문자열일 때 성과 박스가 완전히 숨겨지는가
- [ ] `reason_left`가 빈 문자열일 때 접이식 영역이 완전히 숨겨지는가
- [ ] `salary`(경력 항목)가 None일 때 연봉 텍스트가 완전히 숨겨지는가
- [ ] `gpa`가 빈 문자열일 때 GPA 줄이 완전히 숨겨지는가
- [ ] `is_abroad`가 False일 때 해외 뱃지가 완전히 숨겨지는가
- [ ] `level`이 빈 문자열일 때 ` · level` 부분이 완전히 숨겨지는가

### 3.2 섹션 전체 숨김

- [ ] `current_salary`와 `desired_salary`가 모두 None일 때 "연봉 정보" 섹션 전체가 숨겨지는가 (조건: `{% if candidate.current_salary or candidate.desired_salary %}`)
- [ ] `summary`와 `core_competencies`가 모두 비어있을 때 "경력 요약 + 핵심 역량" 섹션 전체가 숨겨지는가 (조건: `{% if candidate.summary or candidate.core_competencies %}`)
- [ ] 빈값/null 필드에 "없음", "정보 없음" 등의 플레이스홀더 텍스트가 표시되지 않는가

---

## 4. 스타일 일관성

### 4.1 섹션 카드 스타일

- [ ] 경력 요약 섹션의 카드 스타일이 `bg-white rounded-lg border border-gray-200 p-4 mb-3`인가
- [ ] 연봉 정보 섹션의 카드 스타일이 `bg-white rounded-lg border border-gray-200 p-4 mb-3`인가
- [ ] 기존 섹션(기본 정보, 경력, 학력, 자격증·어학, 파싱 신뢰도)의 카드 스타일이 변경되지 않았는가

### 4.2 섹션 헤더 스타일

- [ ] 연봉 정보 섹션의 `<h2>` 스타일이 `text-sm font-medium text-gray-500 uppercase tracking-wider mb-3`인가
- [ ] 기존 섹션들의 `<h2>` 스타일이 변경되지 않았는가

### 4.3 라벨/텍스트 스타일

- [ ] 기본 정보 섹션 내 신규 필드(`gender`, `address`, `source`)의 라벨이 `text-gray-500` 인라인 `<span>`인가
- [ ] 기본 정보 섹션 내 신규 필드의 본문 텍스트 크기가 `text-[15px]`인가 (기존 필드와 동일)
- [ ] 연봉 섹션의 라벨이 `text-gray-500`인가
- [ ] 연봉 섹션의 본문 텍스트 크기가 `text-[15px]`인가
- [ ] 경력 요약 텍스트가 `text-[15px] text-gray-700 leading-relaxed`인가

### 4.4 칩/태그 스타일

- [ ] 핵심 역량 태그가 디자인 시스템의 칩 스타일(`bg-primary-light text-primary rounded-full`)을 사용하는가
- [ ] 해외 뱃지가 디자인 시스템의 뱃지 스타일(`bg-blue-50 text-blue-700 border-blue-200 rounded-full`)을 사용하는가
- [ ] 기존 자격증 칩(`bg-gray-100 text-gray-700 px-2 py-1 rounded`)이 변경되지 않았는가
- [ ] 기존 어학 칩(`bg-primary-light text-primary px-2 py-1 rounded`)이 변경되지 않았는가

### 4.5 컬러 시스템

- [ ] primary 컬러(`#5B6ABF`)가 일관되게 사용되는가 (핵심 역량 태그, 희망 연봉 강조)
- [ ] gray 스케일이 기존 패턴과 동일하게 사용되는가 (라벨: `gray-500`, 값: `gray-900`, 서브텍스트: `gray-400`)
- [ ] 성과 박스의 amber 컬러(`bg-amber-50`, `text-amber-700`, `border-amber-100`)가 일관되게 적용되는가

---

## 5. 모바일 대응

- [ ] 모바일(412px 기준)에서 경력 요약 섹션이 전체 너비, 단일 컬럼으로 표시되는가
- [ ] 모바일에서 핵심 역량 태그가 `flex-wrap`으로 자연스럽게 줄바꿈되는가
- [ ] 모바일에서 기본 정보가 단일 컬럼(`space-y-2`)으로 유지되는가 (2열 그리드가 아닌)
- [ ] 모바일에서 연봉 섹션이 단일 컬럼으로 표시되는가
- [ ] 모바일에서 `address` 텍스트가 넘치지 않고 자연스럽게 줄바꿈되는가
- [ ] 모바일에서 `achievements` 텍스트가 넘치지 않고 성과 박스 내에서 줄바꿈되는가
- [ ] 모바일에서 경력 타임라인(좌측 날짜 80px + 도트 + 우측 내용) 레이아웃이 깨지지 않는가
- [ ] 모바일에서 해외 뱃지가 인라인으로 유지되며 학교 이름 옆에 표시되는가 (줄바꿈 시 다음 줄로 이동 허용)
- [ ] 모바일에서 `<details>` 접이식이 정상적으로 열리고 닫히는가
- [ ] `name_en` 서브타이틀이 모바일에서 자연스럽게 표시되는가 (이름 아래줄)

---

## 6. 접근성

- [ ] 연봉 숫자에 `intcomma` 필터가 적용되어 가독성 있는 포맷(천 단위 콤마)인가
- [ ] 템플릿 상단에 `{% load humanize %}` 가 추가되었는가
- [ ] `django.contrib.humanize`가 `INSTALLED_APPS`에 포함되어 있는가 (`main/settings.py`)
- [ ] `<details>`/`<summary>` 요소가 키보드로 조작 가능한가 (Tab 키로 포커스, Enter/Space로 토글)
- [ ] `<details>` 기본 삼각형 마커가 적절히 스타일링되었는가

---

## 7. 데이터 의존성

- [ ] view에서 `candidate.core_competencies` (JSONField)를 별도 직렬화 없이 context로 전달하고 있는가
- [ ] 템플릿에서 `{% for comp in candidate.core_competencies %}` 반복이 정상 작동하는가
- [ ] view에서 `careers`, `educations`, `language_skills`, `certifications`이 기존대로 context에 포함되는가
- [ ] `candidate.get_source_display`가 source choices에 따라 올바른 한국어 라벨을 반환하는가
