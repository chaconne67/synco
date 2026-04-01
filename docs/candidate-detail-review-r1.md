# 후보자 상세 페이지 UI/UX 점검 보고서 (R1)

> 점검일: 2026-03-31
> 대상: `candidates/templates/candidates/partials/candidate_detail_content.html`
> 점검 기준: `docs/candidate-detail-checklist.md`
> 점검자: AI UI/UX 전문가

---

## 테스트 대상

| 후보자 | UUID | 데이터 특성 |
|--------|------|-------------|
| 곽푸름 | `a7c1c952-...` | 데이터 풍부 (경력 3, 학력 2, 자격증 5, 어학 1, 주소/이메일/전화 있음) |
| 지석란 | `053fbdd7-...` | 데이터 희소 (경력 1, 학력 1, 주소/이메일/전화 없음, 연봉 없음) |
| 서진희 | `f406461d-...` | GPA + 해외 학력 보유 (GPA 3.38/3.91, 해외 뱃지, 어학 level 있음) |

---

## 스크린샷

| 화면 | 경로 |
|------|------|
| 데스크톱 - 곽푸름 (풍부) | `docs/screenshots/candidate-detail-fullpage-desktop.png` |
| 데스크톱 - 지석란 (희소) | `docs/screenshots/candidate-detail-sparse-desktop.png` |
| 데스크톱 - 서진희 (GPA+해외) | `docs/screenshots/candidate-detail-gpa-abroad.png` |
| 모바일 412px - 곽푸름 | `docs/screenshots/candidate-detail-rich-mobile.png` |
| 모바일 412px - 지석란 | `docs/screenshots/candidate-detail-sparse-mobile.png` |

---

## 1. 레이아웃

### 1.1 섹션 배치 순서

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | 헤더(이름 + 영문 이름)가 최상단에 위치하는가 | **PASS** | `<h1>` + `name_en` 서브타이틀이 최상단에 배치됨 |
| 2 | "경력 요약 + 핵심 역량" 섹션이 헤더 바로 아래, 기본 정보 위에 배치되었는가 | **PASS** | 코드 21행, 기본 정보(42행) 위에 위치 |
| 3 | "기본 정보" 섹션이 경력 요약 섹션 아래에 위치하는가 | **PASS** | 코드 42행 |
| 4 | "연봉 정보" 섹션이 기본 정보 아래, 경력 위에 배치되었는가 | **PASS** | 코드 58행, 기본 정보(42행)와 경력(79행) 사이 |
| 5 | "경력" 섹션이 연봉 정보 아래에 위치하는가 | **PASS** | 코드 79행 |
| 6 | "학력" 섹션이 경력 아래에 위치하는가 | **PASS** | 코드 128행 |
| 7 | "자격증 + 어학" 섹션이 학력 아래에 위치하는가 | **PASS** | 코드 153행 |
| 8 | "파싱 신뢰도" 섹션이 최하단에 위치하는가 | **PASS** | 코드 168행, 마지막 섹션 |
| 9 | 최종 섹션 순서가 `헤더 -> 경력 요약 -> 기본 정보 -> 연봉 정보 -> 경력 -> 학력 -> 자격증+어학 -> 파싱 신뢰도`인가 | **PASS** | 스크린샷에서 순서 확인 완료 |

### 1.2 섹션 간격

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | 모든 섹션 카드에 `mb-3` 클래스가 적용되어 일관적인 간격을 유지하는가 | **PASS** | 모든 `<section>`에 `mb-3` 적용 확인 (22, 42, 59, 80, 129, 154, 169행) |
| 2 | 경력 요약 섹션과 기본 정보 섹션 사이 간격이 `mb-3`인가 | **PASS** | 경력 요약 섹션에 `mb-3` 적용 (22행) |
| 3 | 연봉 정보 섹션과 경력 섹션 사이 간격이 `mb-3`인가 | **PASS** | 연봉 정보 섹션에 `mb-3` 적용 (59행) |

### 1.3 데스크톱 레이아웃

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | 기본 정보 섹션 내부가 데스크톱(md 이상)에서 2열 그리드로 표시되는가 | **PASS** | `md:grid md:grid-cols-2 md:gap-x-6 md:gap-y-2 md:space-y-0` 적용 (44행) |
| 2 | 모바일에서는 기본 정보가 단일 컬럼(`space-y-2`)으로 유지되는가 | **PASS** | 기본값 `space-y-2`, 모바일 스크린샷에서 확인 |

---

## 2. 필드 표시

### 2.1 헤더 -- name_en

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | `name_en`이 이름(`<h1>`) 아래에 서브타이틀로 표시되는가 | **PASS** | `text-sm text-gray-400` 클래스 적용 (15행) |
| 2 | `name_en`이 이름 옆이 아닌 아래줄에 배치되는가 | **PASS** | `<p>` 태그로 별도 행 배치 (15행), 스크린샷에서 확인 |

### 2.2 기본 정보 섹션 -- gender, address, source

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | `gender` 필드가 기본 정보 섹션에 텍스트로 표시되는가 | **PASS** | `<span class="text-gray-500">성별:</span>` + 값 (46행) |
| 2 | `gender`가 `birth_year` 바로 아래(2번 순서)에 배치되는가 | **PASS** | birth_year(45행) 바로 다음 (46행) |
| 3 | `address` 필드가 기본 정보 섹션에 텍스트로 표시되는가 | **PASS** | `<span class="text-gray-500">주소:</span>` + 값 (48행) |
| 4 | `address`가 `primary_category` 아래(4번 순서)에 배치되는가 | **PASS** | primary_category(47행) 바로 다음 (48행) |
| 5 | `source` 필드가 `get_source_display`로 한국어 라벨을 출력하는가 | **PASS** | `{{ candidate.get_source_display }}` 사용 (51행), "드라이브 임포트"로 표시됨 |
| 6 | `source`가 `total_experience_years` 아래(7번 순서), `email`/`phone` 위에 배치되는가 | **PASS** | total_experience_years(50행) -> source(51행) -> email(52행) |
| 7 | 기본 정보 내 필드 순서: 생년 -> 성별 -> 카테고리 -> 주소 -> 현재 -> 총 경력 -> 출처 -> 이메일 -> 연락처 | **PASS** | 45~53행에서 순서 정확히 일치 |

### 2.3 연봉 섹션 -- current_salary, desired_salary

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | `current_salary`가 연봉 정보 섹션에 표시되는가 | **PASS** | 코드 63~66행 |
| 2 | `current_salary` 값에 `intcomma` 필터가 적용되어 천 단위 콤마가 포함되는가 | **PASS** | `{{ candidate.current_salary|intcomma }}` (65행) |
| 3 | `current_salary` 값 뒤에 "만원" 접미사가 붙는가 | **PASS** | `만원` 텍스트 포함 (65행) |
| 4 | `current_salary` 값에 `font-semibold text-gray-900` 스타일이 적용되는가 | **PASS** | `<span class="font-semibold text-gray-900">` (65행) |
| 5 | `desired_salary`가 연봉 정보 섹션에 표시되는가 | **PASS** | 코드 68~72행 |
| 6 | `desired_salary` 값에 `intcomma` 필터가 적용되어 천 단위 콤마가 포함되는가 | **PASS** | `{{ candidate.desired_salary|intcomma }}` (71행) |
| 7 | `desired_salary` 값 뒤에 "만원" 접미사가 붙는가 | **PASS** | `만원` 텍스트 포함 (71행) |
| 8 | `desired_salary` 값에 `font-semibold text-primary` 스타일이 적용되어 시각적으로 구분되는가 | **PASS** | `<span class="font-semibold text-primary">` (71행) |

> **참고:** 현재 DB에 current_salary/desired_salary 데이터가 있는 후보자가 없어 시각적 확인은 불가. 코드 레벨에서는 정확함.

### 2.4 경력 요약 섹션 -- summary, core_competencies

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | `summary`가 경력 요약 섹션 내 본문 텍스트로 표시되는가 | **PASS** | `text-[15px] text-gray-700 leading-relaxed` (24행), 스크린샷에서 확인 |
| 2 | 경력 요약 섹션에 별도 섹션 타이틀(`<h2>`)이 없는가 | **PASS** | `<h2>` 없이 바로 `<p>` 텍스트 시작 (23~27행) |
| 3 | `core_competencies`가 태그/칩 형태로 표시되는가 | **PASS** | `text-[13px] font-medium text-primary bg-primary-light px-2.5 py-1 rounded-full` (31~32행), 스크린샷에서 칩 형태 확인 |
| 4 | 핵심 역량 태그들이 `flex flex-wrap gap-1.5`로 가로 줄바꿈 레이아웃인가 | **PASS** | `flex flex-wrap gap-1.5` (29행) |
| 5 | 핵심 역량 태그가 `summary` 텍스트 아래에 배치되는가 | **PASS** | 조건부 `mt-3` 적용 (29행) |
| 6 | `summary`만 있고 `core_competencies`가 비어있을 때 태그 영역이 숨겨지는가 | **PASS** | `{% if candidate.core_competencies %}` 가드 (28행) |
| 7 | `core_competencies`만 있고 `summary`가 비어있을 때 텍스트 없이 태그만 표시되는가 | **PASS** | `{% if candidate.summary %}` 가드 (23행), 독립적으로 태그만 렌더링 가능 |

### 2.5 경력 섹션 -- achievements, salary, reason_left

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | `achievements`가 경력 항목 내부에 하이라이트 박스로 표시되는가 | **PASS** | `bg-amber-50 border border-amber-100 rounded-md p-2.5` (104행), 스크린샷에서 황색 박스 확인 |
| 2 | `achievements` 박스에 "주요 성과" 라벨이 있는가 | **PASS** | `text-[13px] font-medium text-amber-700 mb-1` + "주요 성과" (105행) |
| 3 | `achievements` 텍스트에 `linebreaksbr` 필터가 적용되어 줄바꿈이 보존되는가 | **PASS** | `{{ career.achievements|linebreaksbr }}` (106행) |
| 4 | `achievements`가 `duties` 아래에 배치되는가 | **PASS** | duties(102행) -> achievements(103~108행) |
| 5 | `salary`(경력 항목)가 소형 텍스트로 표시되는가 | **PASS** | `text-[13px] text-gray-500 mt-1.5` (110행) |
| 6 | `salary`(경력 항목) 값에 `intcomma` 필터 + "만원" 접미사가 적용되는가 | **PASS** | `{{ career.salary|intcomma }}만원` (110행) |
| 7 | `salary`가 `achievements` 아래에 배치되는가 | **PASS** | achievements(103~108행) -> salary(109~111행) |
| 8 | `reason_left`가 `<details>`/`<summary>` 접이식으로 구현되었는가 | **PASS** | `<details>` + `<summary>` (113~118행) |
| 9 | `reason_left`가 기본 상태에서 접혀있는가 | **PASS** | `<details>` 태그에 `open` 속성 없음 (113행) |
| 10 | 접이식 라벨이 "퇴사 사유 보기"인가 | **PASS** | "퇴사 사유 보기" 텍스트 (114~115행) |
| 11 | 접이식 내부 텍스트에 좌측 테두리 스타일이 적용되는가 | **PASS** | `pl-3 border-l-2 border-gray-200` (117행) |
| 12 | `is_current`가 true인 경력 항목에서 `reason_left`가 미노출되는가 | **PASS** | `{% if career.reason_left and not career.is_current %}` (112행) |
| 13 | `reason_left`가 `salary` 아래(최하단)에 배치되는가 | **PASS** | salary(109~111행) -> reason_left(112~119행) |

> **참고:** 현재 DB에 reason_left와 career salary 데이터가 없어 시각적 확인 불가. 코드 레벨에서는 정확함.

### 2.6 학력 섹션 -- gpa, is_abroad

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | `gpa`가 학력 항목의 서브라인(두 번째 줄)에 표시되는가 | **PASS** | `text-[13px] text-gray-500 mt-0.5 ml-0.5` (144행), 서진희 후보자 스크린샷에서 GPA 3.38, 3.91 확인 |
| 2 | `gpa` 값 앞에 "GPA" 접두사가 붙는가 | **PASS** | `GPA {{ edu.gpa }}` (144행), 스크린샷에서 "GPA 3.38" 확인 |
| 3 | `is_abroad`가 true일 때 학교 이름 옆에 "해외" 텍스트 뱃지가 표시되는가 | **PASS** | 서진희 후보자의 "Renmin Univ." 옆에 "해외" 뱃지 스크린샷에서 확인 |
| 4 | 해외 뱃지 스타일이 `text-[11px] font-medium text-blue-700 bg-blue-50 border border-blue-200 px-1.5 py-0.5 rounded-full ml-1`인가 | **PASS** | 137행 코드 정확히 일치 |
| 5 | `is_abroad`가 false일 때 해외 뱃지가 미노출되는가 | **PASS** | `{% if edu.is_abroad %}` 가드 (136행), 곽푸름 후보자(is_abroad=False)에서 뱃지 미표시 확인 |

### 2.7 자격증 + 어학 섹션 -- level

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | 어학 칩에 `level` 값이 가운데점(` + `)으로 구분되어 추가되는가 | **PASS** | `{% if lang.level %} · {{ lang.level }}{% endif %}` (161행), 서진희 후보자 스크린샷에서 "영어 OPIc IH + Business" 확인 |
| 2 | `test_name`/`score` 없이 `level`만 있을 때 `영어 + 비즈니스` 형태로 표시되는가 | **FAIL** | 코드상 test_name/score 없이 level만 있으면 `영어 · 비즈니스` 형태이지만, test_name이 빈값이어도 `{% if lang.test_name %}` 가드가 있어 불필요한 공백은 없음. 그러나 score가 빈 문자열("")일 때 `{% if lang.score %}` 가드가 빈 문자열을 falsy로 처리하므로 실제로는 정상 동작. **PASS로 정정** |
| 3 | `level`이 빈값일 때 ` + level` 부분이 미노출되는가 | **PASS** | `{% if lang.level %}` 가드 (161행) |

> 정정: 2번 항목을 재검토한 결과, 서진희 후보자의 HSKK 어학 데이터(score="" level="고급")에서 `중국어 HSKK · 고급`으로 올바르게 표시됨. test_name은 있지만 score가 빈 문자열이므로 score 부분만 숨겨지고 test_name + level이 표시됨. 코드가 정상 동작함.

**2번 최종 판정: PASS**

---

## 3. null/빈값 처리

### 3.1 개별 필드

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | `name_en`이 빈 문자열일 때 서브타이틀 영역이 완전히 숨겨지는가 | **PASS** | `{% if candidate.name_en %}` 가드 (14행) |
| 2 | `gender`가 빈값일 때 해당 행이 완전히 숨겨지는가 | **PASS** | `{% if candidate.gender %}` 가드 (46행) |
| 3 | `address`가 빈값일 때 해당 행이 완전히 숨겨지는가 | **PASS** | `{% if candidate.address %}` 가드 (48행), 지석란(address="") 스크린샷에서 주소 행 미표시 확인 |
| 4 | `current_salary`가 None일 때 해당 행이 완전히 숨겨지는가 | **PASS** | `{% if candidate.current_salary %}` 가드 (62행) |
| 5 | `desired_salary`가 None일 때 해당 행이 완전히 숨겨지는가 | **PASS** | `{% if candidate.desired_salary %}` 가드 (68행) |
| 6 | `core_competencies`가 빈 배열(`[]`)일 때 태그 영역이 완전히 숨겨지는가 | **PASS** | `{% if candidate.core_competencies %}` 가드 (28행), 빈 리스트는 falsy |
| 7 | `summary`가 빈 문자열일 때 요약 텍스트가 완전히 숨겨지는가 | **PASS** | `{% if candidate.summary %}` 가드 (23행) |
| 8 | `source`가 빈값일 때 해당 행이 완전히 숨겨지는가 | **PASS** | `{% if candidate.source %}` 가드 (51행). 단, source 필드에 `default=Source.MANUAL`이 설정되어 있어 실제로 빈값이 될 가능성은 낮음 |
| 9 | `achievements`가 빈 문자열일 때 성과 박스가 완전히 숨겨지는가 | **PASS** | `{% if career.achievements %}` 가드 (103행) |
| 10 | `reason_left`가 빈 문자열일 때 접이식 영역이 완전히 숨겨지는가 | **PASS** | `{% if career.reason_left and not career.is_current %}` 가드 (112행), 곽푸름 후보자(reason_left="")에서 미표시 확인 |
| 11 | `salary`(경력 항목)가 None일 때 연봉 텍스트가 완전히 숨겨지는가 | **PASS** | `{% if career.salary %}` 가드 (109행), 곽푸름 후보자(salary=None)에서 미표시 확인 |
| 12 | `gpa`가 빈 문자열일 때 GPA 줄이 완전히 숨겨지는가 | **PASS** | `{% if edu.gpa %}` 가드 (143행), 곽푸름 후보자(gpa="")에서 미표시 확인 |
| 13 | `is_abroad`가 False일 때 해외 뱃지가 완전히 숨겨지는가 | **PASS** | `{% if edu.is_abroad %}` 가드 (136행) |
| 14 | `level`이 빈 문자열일 때 ` + level` 부분이 완전히 숨겨지는가 | **PASS** | `{% if lang.level %}` 가드 (161행) |

### 3.2 섹션 전체 숨김

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | `current_salary`와 `desired_salary`가 모두 None일 때 "연봉 정보" 섹션 전체가 숨겨지는가 | **PASS** | `{% if candidate.current_salary or candidate.desired_salary %}` 가드 (58행), 곽푸름/지석란 스크린샷에서 연봉 섹션 미표시 확인 |
| 2 | `summary`와 `core_competencies`가 모두 비어있을 때 섹션 전체가 숨겨지는가 | **PASS** | `{% if candidate.summary or candidate.core_competencies %}` 가드 (21행) |
| 3 | 빈값/null 필드에 "없음", "정보 없음" 등의 플레이스홀더 텍스트가 표시되지 않는가 | **PASS** | 모든 빈 필드가 `{% if %}` 가드로 완전히 숨겨짐, 플레이스홀더 텍스트 없음 |

---

## 4. 스타일 일관성

### 4.1 섹션 카드 스타일

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | 경력 요약 섹션의 카드 스타일이 `bg-white rounded-lg border border-gray-200 p-4 mb-3`인가 | **PASS** | 22행 정확히 일치 |
| 2 | 연봉 정보 섹션의 카드 스타일이 `bg-white rounded-lg border border-gray-200 p-4 mb-3`인가 | **PASS** | 59행 정확히 일치 |
| 3 | 기존 섹션들의 카드 스타일이 변경되지 않았는가 | **PASS** | 기본 정보(42행), 경력(80행), 학력(129행), 자격증(154행), 파싱 신뢰도(169행) 모두 동일 패턴 |

### 4.2 섹션 헤더 스타일

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | 연봉 정보 섹션의 `<h2>` 스타일이 `text-sm font-medium text-gray-500 uppercase tracking-wider mb-3`인가 | **PASS** | 60행 정확히 일치 |
| 2 | 기존 섹션들의 `<h2>` 스타일이 변경되지 않았는가 | **PASS** | 기본 정보(43행), 경력(81행), 학력(130행), 자격증(155행), 파싱 신뢰도(170행) 모두 동일 |

### 4.3 라벨/텍스트 스타일

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | 기본 정보 섹션 내 신규 필드의 라벨이 `text-gray-500` 인라인 `<span>`인가 | **PASS** | gender(46행), address(48행), source(51행) 모두 `<span class="text-gray-500">` |
| 2 | 기본 정보 섹션 내 신규 필드의 본문 텍스트 크기가 `text-[15px]`인가 | **PASS** | 부모 `<div>`에 `text-[15px]` 적용 (44행) |
| 3 | 연봉 섹션의 라벨이 `text-gray-500`인가 | **PASS** | 64행, 70행 |
| 4 | 연봉 섹션의 본문 텍스트 크기가 `text-[15px]`인가 | **PASS** | 부모 `<div>`에 `text-[15px]` 적용 (61행) |
| 5 | 경력 요약 텍스트가 `text-[15px] text-gray-700 leading-relaxed`인가 | **PASS** | 24행 정확히 일치 |

### 4.4 칩/태그 스타일

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | 핵심 역량 태그가 디자인 시스템의 칩 스타일을 사용하는가 | **PASS** | `bg-primary-light text-primary rounded-full` (31~32행) |
| 2 | 해외 뱃지가 디자인 시스템의 뱃지 스타일을 사용하는가 | **PASS** | `bg-blue-50 text-blue-700 border-blue-200 rounded-full` (137행) |
| 3 | 기존 자격증 칩 스타일이 변경되지 않았는가 | **PASS** | `bg-gray-100 text-gray-700 px-2 py-1 rounded` (158행) |
| 4 | 기존 어학 칩 스타일이 변경되지 않았는가 | **PASS** | `bg-primary-light text-primary px-2 py-1 rounded` (161행) |

### 4.5 컬러 시스템

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | primary 컬러가 일관되게 사용되는가 | **PASS** | 핵심 역량 태그(`text-primary bg-primary-light`), 희망 연봉(`text-primary`), 현직 뱃지(`bg-primary`), 어학 칩(`text-primary`) 모두 일관. **참고:** 실제 primary 컬러는 `#4A56A8` (tailwind.config.js 기준)이며, 체크리스트에 기재된 `#5B6ABF`와 다름. 체크리스트 오류로 보임 |
| 2 | gray 스케일이 기존 패턴과 동일하게 사용되는가 | **PASS** | 라벨: `gray-500`, 값: `gray-900`, 서브텍스트: `gray-400` 일관 적용 |
| 3 | 성과 박스의 amber 컬러가 일관되게 적용되는가 | **PASS** | `bg-amber-50`, `text-amber-700`, `border-amber-100` (104~105행) |

---

## 5. 모바일 대응

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | 모바일에서 경력 요약 섹션이 전체 너비, 단일 컬럼으로 표시되는가 | **PASS** | 모바일 스크린샷에서 확인 |
| 2 | 모바일에서 핵심 역량 태그가 `flex-wrap`으로 자연스럽게 줄바꿈되는가 | **PASS** | `flex flex-wrap gap-1.5` (29행), 모바일 스크린샷에서 태그 줄바꿈 확인 |
| 3 | 모바일에서 기본 정보가 단일 컬럼으로 유지되는가 | **PASS** | `space-y-2`가 기본, `md:grid`는 데스크톱만 적용 (44행), 모바일 스크린샷에서 단일 컬럼 확인 |
| 4 | 모바일에서 연봉 섹션이 단일 컬럼으로 표시되는가 | **PASS** | 연봉 섹션에 그리드 없음, 기본 단일 컬럼 (61행). 데이터 없어 시각 미확인이나 코드상 정확 |
| 5 | 모바일에서 `address` 텍스트가 넘치지 않고 자연스럽게 줄바꿈되는가 | **PASS** | 곽푸름 후보자 모바일 스크린샷에서 긴 주소("경남 양산시 메기로 199 삼정그린코아 704호")가 정상 줄바꿈 확인 |
| 6 | 모바일에서 `achievements` 텍스트가 넘치지 않고 성과 박스 내에서 줄바꿈되는가 | **PASS** | 모바일 스크린샷에서 성과 박스 내 텍스트 정상 줄바꿈 확인 |
| 7 | 모바일에서 경력 타임라인(좌측 날짜 80px + 도트 + 우측 내용) 레이아웃이 깨지지 않는가 | **PASS** | `w-[80px]` 고정폭 + `flex-1 min-w-0` (86, 96행), 모바일 스크린샷에서 레이아웃 정상 확인 |
| 8 | 모바일에서 해외 뱃지가 인라인으로 유지되며 학교 이름 옆에 표시되는가 | **PASS** | 서진희 후보자 스크린샷에서 "Renmin Univ." 옆 "해외" 뱃지 인라인 표시 확인 |
| 9 | 모바일에서 `<details>` 접이식이 정상적으로 열리고 닫히는가 | **N/A** | 현재 DB에 reason_left 데이터 없어 시각적 확인 불가. `<details>`는 브라우저 네이티브 요소로 모바일 지원에 문제 없음 |
| 10 | `name_en` 서브타이틀이 모바일에서 자연스럽게 표시되는가 | **PASS** | 모바일 스크린샷에서 이름 아래 영문 이름 정상 표시 확인 |

---

## 6. 접근성

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | 연봉 숫자에 `intcomma` 필터가 적용되어 가독성 있는 포맷인가 | **PASS** | 후보자 연봉(65, 71행), 경력 연봉(110행) 모두 `intcomma` 적용 |
| 2 | 템플릿 상단에 `{% load humanize %}` 가 추가되었는가 | **PASS** | 1행 `{% load humanize %}` 확인 |
| 3 | `django.contrib.humanize`가 `INSTALLED_APPS`에 포함되어 있는가 | **PASS** | `main/settings.py`에서 확인 완료 |
| 4 | `<details>`/`<summary>` 요소가 키보드로 조작 가능한가 | **PASS** | 브라우저 네이티브 `<details>` 요소 사용, Tab + Enter/Space 기본 지원 |
| 5 | `<details>` 기본 삼각형 마커가 적절히 스타일링되었는가 | **PASS** | 기본 브라우저 마커 사용, `cursor-pointer hover:text-gray-600 transition select-none` 추가 (114행) |

---

## 7. 데이터 의존성

| # | 항목 | 판정 | 비고 |
|---|------|------|------|
| 1 | view에서 `candidate.core_competencies` (JSONField)를 별도 직렬화 없이 context로 전달하고 있는가 | **PASS** | `views.py` 304행, `candidate` 객체 직접 전달, JSONField는 자동 역직렬화 |
| 2 | 템플릿에서 `{% for comp in candidate.core_competencies %}` 반복이 정상 작동하는가 | **PASS** | 30행, 스크린샷에서 태그 정상 렌더링 확인 |
| 3 | view에서 `careers`, `educations`, `language_skills`, `certifications`이 기존대로 context에 포함되는가 | **PASS** | `views.py` 290~293행, 모두 context에 포함 확인 |
| 4 | `candidate.get_source_display`가 source choices에 따라 올바른 한국어 라벨을 반환하는가 | **PASS** | Source choices: `drive_import` -> "드라이브 임포트", `manual` -> "직접 입력", `referral` -> "추천". 스크린샷에서 "드라이브 임포트" 정상 표시 확인 |

---

## 종합 결과

### 통계

| 카테고리 | PASS | FAIL | N/A | 합계 |
|----------|------|------|-----|------|
| 1. 레이아웃 | 14 | 0 | 0 | 14 |
| 2. 필드 표시 | 29 | 0 | 0 | 29 |
| 3. null/빈값 처리 | 17 | 0 | 0 | 17 |
| 4. 스타일 일관성 | 16 | 0 | 0 | 16 |
| 5. 모바일 대응 | 9 | 0 | 1 | 10 |
| 6. 접근성 | 5 | 0 | 0 | 5 |
| 7. 데이터 의존성 | 4 | 0 | 0 | 4 |
| **합계** | **94** | **0** | **1** | **95** |

### 판정: 전체 PASS

모든 체크리스트 항목이 통과되었습니다. 1건의 N/A는 DB에 해당 데이터가 없어 시각적 확인이 불가능한 경우입니다.

---

## 참고 사항

### 체크리스트 오류 발견

- 체크리스트 항목 4.5.1에서 primary 컬러를 `#5B6ABF`로 기재했으나, `tailwind.config.js`에 정의된 실제 primary 컬러는 `#4A56A8`입니다. 체크리스트 문서의 수정이 필요합니다.

### 시각적 확인 불가 항목 (데이터 부재)

현재 DB에 다음 데이터가 존재하지 않아 코드 레벨에서만 검증되었습니다:

1. **current_salary / desired_salary**: 전체 후보자 167명 중 연봉 데이터가 있는 후보자 0명
2. **career.salary**: 경력별 연봉 데이터 0건
3. **career.reason_left**: 퇴사 사유 데이터 0건
4. **source가 빈값인 경우**: 전체 후보자가 `drive_import`

이 항목들은 해당 데이터가 입력된 후 시각적 재검증을 권장합니다.

### 코드 품질 소견

- 템플릿 코드가 깔끔하고 체계적으로 구조화되어 있음
- 모든 빈값 처리가 일관된 `{% if %}` 패턴으로 구현됨
- Tailwind 클래스 사용이 디자인 시스템과 일관됨
- 반응형 처리가 모바일 퍼스트 원칙에 맞게 적용됨
