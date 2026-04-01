# 후보자 상세 페이지 — 누락 필드 추가 디자인 계획서

> 작성일: 2026-03-31
> 대상 파일: `candidates/templates/candidates/partials/candidate_detail_content.html`

---

## 1. 현재 페이지 구조 분석

현재 상세 페이지는 5개 섹션으로 구성되어 있습니다.

| # | 섹션 | 표시 정보 | 비고 |
|---|------|-----------|------|
| 1 | **헤더** | 뒤로가기 + `name` | 단순 타이틀 |
| 2 | **기본 정보** | `birth_year`, `primary_category`, `current_company`/`current_position`, `total_experience_years`, `email`, `phone` | 카드 형태, `{% if %}` 조건부 노출 |
| 3 | **경력** | 타임라인 형태 — `start_date`, `end_date`, `company`, `is_current`, `position`, `department`, `duties` | 좌측 연도 + 도트 타임라인 + 우측 내용 |
| 4 | **학력** | `institution`, `degree`, `major`, `end_year` | 한 줄 인라인 텍스트 |
| 5 | **자격증 / 어학** | 자격증(`name`, `acquired_date`) + 어학(`language`, `test_name`, `score`) | 칩/태그 형태, 단일 섹션에 합침 |
| 6 | **파싱 신뢰도** | `confidence_score` | 프로그레스 바 |

### 현재 미표시 필드 (DB에는 존재)

- Candidate: `name_en`, `gender`, `address`, `current_salary`, `desired_salary`, `core_competencies`, `summary`, `source`
- Career: `achievements`, `reason_left`, `salary`
- Education: `gpa`, `is_abroad`
- LanguageSkill: `level`

---

## 2. 추가 필드 배치 계획

### 2.1 전체 페이지 구조 (변경 후)

```
┌─────────────────────────────────────────────┐
│  ← 뒤로가기    홍길동                         │  헤더 (기존)
│                Hong Gil-dong                │  ← name_en 추가
├─────────────────────────────────────────────┤
│  ▌경력 요약                                   │  ★ 신규 섹션
│  "15년차 HR 전문가. 삼성전자, LG에서..."        │
│  [핵심역량] [조직관리] [채용전략] [HRIS]        │  ← core_competencies
├─────────────────────────────────────────────┤
│  ▌기본 정보                                   │  기존 섹션 확장
│  생년: 1985      성별: 남성                    │  ← gender 추가
│  카테고리: HR     주소: 서울시 강남구            │  ← address 추가
│  현재: 삼성전자 인사팀장                        │
│  총 경력: 15년   출처: 드라이브 임포트           │  ← source 추가
│  이메일: ...     연락처: ...                    │
├─────────────────────────────────────────────┤
│  ▌연봉 정보                                   │  ★ 신규 섹션
│  현재 연봉: 8,000만원                          │
│  희망 연봉: 10,000만원                         │
├─────────────────────────────────────────────┤
│  ▌경력                                        │  기존 섹션 확장
│  2020 — 현재   삼성전자 [현직]                  │
│               인사팀장 · 인사부                  │
│               직무: ...                        │
│               ✦ 성과: 채용 프로세스 40% 단축     │  ← achievements
│               💰 연봉: 8,000만원                │  ← salary
│               ▸ 퇴사 사유 (접이식)              │  ← reason_left
│  ─────────────────────────────────────────── │
│  2015 — 2020   LG전자                         │
│               ...                             │
├─────────────────────────────────────────────┤
│  ▌학력                                        │  기존 섹션 확장
│  서울대학교 · 석사 · 경영학 2015                │
│     GPA 4.2/4.5                               │  ← gpa
│  🌏 UCLA · 학사 · HRM 2010                    │  ← is_abroad 뱃지
├─────────────────────────────────────────────┤
│  ▌자격증 · 어학                                │  기존 섹션 확장
│  [SHRM-CP (2018)] [PHR (2016)]               │
│  [영어 TOEIC 950 비즈니스] [일본어 JLPT N2 중급]│  ← level 추가
├─────────────────────────────────────────────┤
│  ▌파싱 신뢰도                                  │  기존 유지
│  ████████░░ 80%                               │
└─────────────────────────────────────────────┘
```

### 2.2 섹션별 상세 배치

#### A. 헤더 영역 — `name_en` 추가

- **위치:** `<h1>` 태그 바로 아래, 이름 오른쪽 또는 아래줄
- **형태:** 이름 옆에 소괄호로 표시하거나 서브타이틀로 표시
- **예시 1 (인라인):** `홍길동 (Hong Gil-dong)` — 이름이 짧을 때 적합
- **예시 2 (서브타이틀):** 이름 아래 `text-sm text-gray-500`으로 영문 이름 배치
- **권장:** 예시 2 (서브타이틀) — 모바일에서 줄바꿈이 자연스럽고, 헤더가 깔끔함

```
홍길동
Hong Gil-dong        ← text-sm text-gray-400
```

#### B. 경력 요약 + 핵심 역량 — 신규 섹션 (기본 정보 위)

- **위치:** 기본 정보 섹션 **위**에 배치 (페이지 최상단, 헤더 바로 아래)
- **이유:** 후보자를 한눈에 파악하는 "엘리베이터 피치" 역할. 상세 정보보다 먼저 노출
- **구성:**
  1. `summary` — 경력 요약 텍스트 (본문)
  2. `core_competencies` — 핵심 역량 태그 (요약 아래)

```html
<!-- 경력 요약 & 핵심 역량 -->
<section class="bg-white rounded-lg border border-gray-200 p-4 mb-3">
  <!-- summary -->
  <p class="text-[15px] text-gray-700 leading-relaxed">
    {{ candidate.summary }}
  </p>
  <!-- core_competencies 태그 -->
  <div class="flex flex-wrap gap-1.5 mt-3">
    {% for comp in candidate.core_competencies %}
    <span class="text-[13px] font-medium text-primary bg-primary-light
                 px-2.5 py-1 rounded-full">
      {{ comp }}
    </span>
    {% endfor %}
  </div>
</section>
```

- **섹션 타이틀:** 생략 (요약 자체가 직관적이므로). 단, `summary`와 `core_competencies` 모두 비어있으면 섹션 전체 미노출
- **summary만 있을 때:** 태그 영역 숨김
- **core_competencies만 있을 때:** 텍스트 없이 태그만 표시

#### C. 기본 정보 섹션 — 기존 확장

현재 6개 필드에 3개 추가: `gender`, `address`, `source`

**배치 순서 (변경 후):**

| 순서 | 필드 | 라벨 | 비고 |
|------|------|------|------|
| 1 | `birth_year` | 생년 | 기존 |
| 2 | `gender` | 성별 | **신규** |
| 3 | `primary_category` | 카테고리 | 기존 |
| 4 | `address` | 주소 | **신규** |
| 5 | `current_company` + `current_position` | 현재 | 기존 |
| 6 | `total_experience_years` | 총 경력 | 기존 |
| 7 | `source` | 출처 | **신규** |
| 8 | `email` | 이메일 | 기존 |
| 9 | `phone` | 연락처 | 기존 |

**필드별 표현:**

- **`gender`**: 텍스트로 표시. `남성`, `여성` 등 모델에 저장된 값 그대로 출력
  ```html
  {% if candidate.gender %}
  <p><span class="text-gray-500">성별:</span> {{ candidate.gender }}</p>
  {% endif %}
  ```

- **`address`**: 텍스트로 표시. 길어질 수 있으므로 줄바꿈 허용
  ```html
  {% if candidate.address %}
  <p><span class="text-gray-500">주소:</span> {{ candidate.address }}</p>
  {% endif %}
  ```

- **`source`**: `get_source_display`로 한국어 라벨 출력
  ```html
  {% if candidate.source %}
  <p><span class="text-gray-500">출처:</span> {{ candidate.get_source_display }}</p>
  {% endif %}
  ```

#### D. 연봉 정보 — 신규 섹션 (기본 정보와 경력 사이)

- **위치:** 기본 정보 아래, 경력 위
- **이유:** 연봉은 민감 정보이므로 기본 정보와 분리하여 독립 섹션으로 구분. 시각적으로 "여기에 민감 정보가 있다"는 인식 부여
- **구성:**

| 필드 | 라벨 | 포맷 | 예시 |
|------|------|------|------|
| `current_salary` | 현재 연봉 | 천 단위 콤마 + "만원" | 8,000만원 |
| `desired_salary` | 희망 연봉 | 천 단위 콤마 + "만원" | 10,000만원 |

```html
{% if candidate.current_salary or candidate.desired_salary %}
<section class="bg-white rounded-lg border border-gray-200 p-4 mb-3">
  <h2 class="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">
    연봉 정보
  </h2>
  <div class="space-y-2 text-[15px]">
    {% if candidate.current_salary %}
    <p>
      <span class="text-gray-500">현재 연봉:</span>
      <span class="font-semibold text-gray-900">
        {{ candidate.current_salary|intcomma }}만원
      </span>
    </p>
    {% endif %}
    {% if candidate.desired_salary %}
    <p>
      <span class="text-gray-500">희망 연봉:</span>
      <span class="font-semibold text-primary">
        {{ candidate.desired_salary|intcomma }}만원
      </span>
    </p>
    {% endif %}
  </div>
</section>
{% endif %}
```

- 희망 연봉은 `text-primary`(synco indigo)로 강조하여 현재/희망을 시각적으로 구분
- `intcomma` 필터 사용 (Django `django.contrib.humanize` 필요, 또는 커스텀 필터)

#### E. 경력 섹션 — 각 항목에 3개 필드 추가

기존 타임라인 레이아웃 유지. 각 경력 항목의 "내용 (우측)" 영역에 추가.

**추가 필드 배치 (duties 아래):**

| 순서 | 필드 | 표현 방식 |
|------|------|-----------|
| 기존 | `duties` | 텍스트 (truncatewords) |
| 1 | `achievements` | 성과 리스트 (줄바꿈 구분) |
| 2 | `salary` | 연봉 텍스트 (콤마 + 만원) |
| 3 | `reason_left` | 접이식(아코디언) 텍스트 |

**achievements — 성과:**
- 텍스트 앞에 작은 아이콘(별표 또는 체크)을 붙여 시각적으로 구분
- `duties`와 다른 스타일로 "성과"임을 직관적으로 인식
- 여러 줄일 수 있으므로 `linebreaksbr` 필터 적용

```html
{% if career.achievements %}
<div class="mt-2 bg-amber-50 border border-amber-100 rounded-md p-2.5">
  <p class="text-[13px] font-medium text-amber-700 mb-1">주요 성과</p>
  <p class="text-sm text-gray-700 leading-relaxed">
    {{ career.achievements|linebreaksbr }}
  </p>
</div>
{% endif %}
```

**salary — 해당 직장 연봉:**
- 경력 항목 내 한 줄 텍스트
- `duties` 또는 `achievements` 아래 배치

```html
{% if career.salary %}
<p class="text-[13px] text-gray-500 mt-1.5">
  연봉 {{ career.salary|intcomma }}만원
</p>
{% endif %}
```

**reason_left — 퇴사 사유:**
- 민감할 수 있으므로 기본 숨김, 클릭 시 노출 (접이식)
- 현직(`is_current`)인 경우 미노출
- `<details>` + `<summary>` HTML 요소 사용 (JS 불필요)

```html
{% if career.reason_left and not career.is_current %}
<details class="mt-2">
  <summary class="text-[13px] text-gray-400 cursor-pointer
                   hover:text-gray-600 transition select-none">
    퇴사 사유 보기
  </summary>
  <p class="text-sm text-gray-600 mt-1 pl-3 border-l-2 border-gray-200">
    {{ career.reason_left }}
  </p>
</details>
{% endif %}
```

#### F. 학력 섹션 — 각 항목에 2개 필드 추가

현재 한 줄 인라인 구조를 유지하되, 추가 정보를 아래줄에 배치.

**is_abroad — 해외 학력 뱃지:**
- 학교 이름 옆에 인라인 뱃지로 표시
- 이모지 대신 텍스트 뱃지 사용 (접근성 + 일관성)

```html
{% if edu.is_abroad %}
<span class="text-[11px] font-medium text-blue-700 bg-blue-50
             border border-blue-200 px-1.5 py-0.5 rounded-full ml-1">
  해외
</span>
{% endif %}
```

**gpa — 학점:**
- 학력 항목의 서브라인(두 번째 줄)에 표시
- 존재할 때만 노출

```html
{% if edu.gpa %}
<p class="text-[13px] text-gray-500 mt-0.5 ml-0.5">
  GPA {{ edu.gpa }}
</p>
{% endif %}
```

**학력 항목 전체 구조 (변경 후):**

```html
{% for edu in educations %}
<div class="{% if not forloop.last %}mb-2{% endif %}">
  <div class="text-[15px]">
    <span class="font-medium text-gray-900">{{ edu.institution }}</span>
    {% if edu.is_abroad %}
    <span class="text-[11px] font-medium text-blue-700 bg-blue-50
                 border border-blue-200 px-1.5 py-0.5 rounded-full ml-1">
      해외
    </span>
    {% endif %}
    {% if edu.degree %}
    <span class="text-gray-500"> · {{ edu.degree }}</span>
    {% endif %}
    {% if edu.major %}
    <span class="text-gray-500"> · {{ edu.major }}</span>
    {% endif %}
    {% if edu.end_year %}
    <span class="text-[15px] text-gray-500 ml-1">{{ edu.end_year }}</span>
    {% endif %}
  </div>
  {% if edu.gpa %}
  <p class="text-[13px] text-gray-500 mt-0.5 ml-0.5">GPA {{ edu.gpa }}</p>
  {% endif %}
</div>
{% endfor %}
```

#### G. 자격증 / 어학 섹션 — 어학 항목에 `level` 추가

현재 어학은 칩 형태로 `language`, `test_name`, `score`를 한 줄에 표시.
`level`을 추가하여 어학 수준을 보여줍니다.

**표시 규칙:**
- `test_name`/`score`가 있으면: `영어 TOEIC 950 · 비즈니스`
- `test_name`/`score` 없이 `level`만 있으면: `영어 · 비즈니스`
- 모두 없으면: `영어` (기존과 동일)

```html
{% for lang in language_skills %}
<span class="text-[15px] bg-primary-light text-primary px-2 py-1 rounded">
  {{ lang.language }}
  {% if lang.test_name %} {{ lang.test_name }}{% endif %}
  {% if lang.score %} {{ lang.score }}{% endif %}
  {% if lang.level %} · {{ lang.level }}{% endif %}
</span>
{% endfor %}
```

`level` 값은 가운데점(` · `)으로 구분하여 기존 점수 정보와 시각적으로 분리합니다.

---

## 3. UI 컴포넌트 설계 상세

### 3.1 연봉 포맷

- **단위:** 만원 (DB 저장 단위와 동일)
- **포맷:** 천 단위 콤마 구분 + "만원" 접미사
- **예시:** `8,000만원`, `12,500만원`
- **구현:** Django `intcomma` 필터 (`django.contrib.humanize`)
- **참고:** `humanize` 앱이 `INSTALLED_APPS`에 포함되어 있는지 확인 필요. 미포함 시 커스텀 템플릿 필터로 대체

### 3.2 핵심 역량 (core_competencies)

- **데이터:** JSON 배열 (예: `["조직관리", "채용전략", "HRIS", "글로벌HR"]`)
- **표현:** 칩/태그 형태, 가로 줄바꿈 (`flex-wrap`)
- **스타일:** `bg-primary-light text-primary rounded-full` — 디자인 시스템의 뱃지/칩 스타일 준수
- **최대 표시 수:** 제한 없음 (보통 3-8개 수준). 10개 초과 시 추후 "더보기" 검토

### 3.3 경력 요약 (summary)

- **위치:** 페이지 최상단 (헤더 바로 아래, 기본 정보 위)
- **스타일:** 일반 본문 텍스트. 카드 내부에 별도 제목 없이 배치
- **최대 길이:** 제한 없음 (DB는 TextField). 화면에서는 자연 줄바꿈
- **긴 요약 처리:** 4줄 이상일 경우 `line-clamp-4` + "더보기" 링크 고려 (v1에서는 전문 노출)

### 3.4 해외 학력 뱃지 (is_abroad)

- **형태:** 인라인 텍스트 뱃지 ("해외")
- **스타일:** `text-[11px] font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded-full`
- **위치:** 학교 이름 바로 오른쪽
- **이모지 미사용 이유:** 이모지는 OS/브라우저별 렌더링 차이가 크고, 디자인 시스템에서 이모지를 구조적 요소로 사용하지 않음

### 3.5 성별 (gender)

- **표현:** 텍스트 ("남성", "여성" 등) — 모델에 저장된 값 그대로
- **아이콘 미사용 이유:** 성별 아이콘은 문화적 민감성이 높고, 비이진 성별 표현이 어려움
- **위치:** 기본 정보 섹션, 생년 바로 아래

### 3.6 퇴사 사유 (reason_left)

- **형태:** 접이식 (`<details>` / `<summary>`)
- **기본 상태:** 접힌 상태 (숨김)
- **이유:** 부정적 내용이 포함될 수 있어 기본 노출 시 페이지 인상이 나빠질 수 있음
- **현직 경력:** `is_current`가 true이면 미노출
- **접이식 라벨:** "퇴사 사유 보기"

### 3.7 성과 (achievements)

- **형태:** 경력 항목 내부, 하이라이트 박스
- **스타일:** `bg-amber-50 border-amber-100` — 성과를 시각적으로 강조
- **텍스트 처리:** `linebreaksbr` 필터로 줄바꿈 보존
- **위치:** `duties` 아래, `salary`/`reason_left` 위

### 3.8 출처 (source)

- **표현:** `get_source_display`로 한국어 라벨 ("드라이브 임포트", "직접 입력", "추천")
- **위치:** 기본 정보 섹션 하단 (이메일/연락처 위)
- **스타일:** 다른 기본 정보 필드와 동일한 `<p>` + `<span class="text-gray-500">` 패턴

---

## 4. 데이터 없을 때 처리 규칙

모든 추가 필드는 **값이 없으면 해당 항목을 완전히 숨깁니다** (`{% if %}` 조건부 렌더링). 빈 라벨이나 "없음" 텍스트를 표시하지 않습니다.

| 필드 | null/빈값 판단 기준 | 처리 |
|------|---------------------|------|
| `name_en` | 빈 문자열 (`""`) | 서브타이틀 영역 미노출 |
| `gender` | 빈 문자열 | 해당 행 미노출 |
| `address` | 빈 문자열 | 해당 행 미노출 |
| `current_salary` | `None` | 해당 행 미노출 |
| `desired_salary` | `None` | 해당 행 미노출 |
| `current_salary` + `desired_salary` 모두 없음 | 둘 다 `None` | **연봉 정보 섹션 전체 미노출** |
| `core_competencies` | 빈 배열 (`[]`) | 태그 영역 미노출 |
| `summary` | 빈 문자열 | 요약 텍스트 미노출 |
| `summary` + `core_competencies` 모두 없음 | 둘 다 비어있음 | **경력 요약 섹션 전체 미노출** |
| `source` | 빈 문자열 | 해당 행 미노출 (기본값 `manual`이므로 보통 존재) |
| `achievements` | 빈 문자열 | 성과 박스 미노출 |
| `reason_left` | 빈 문자열 | 접이식 영역 미노출 |
| `salary` (Career) | `None` | 연봉 텍스트 미노출 |
| `gpa` | 빈 문자열 | GPA 줄 미노출 |
| `is_abroad` | `False` | 해외 뱃지 미노출 |
| `level` | 빈 문자열 | ` · level` 부분 미노출 (나머지는 기존대로) |

**원칙:** 데이터가 풍부한 후보자는 풍부하게, 데이터가 적은 후보자는 깔끔하게 보이도록. "정보 없음" 같은 플레이스홀더는 사용하지 않습니다.

---

## 5. 민감 정보 표시 규칙

### 5.1 현재 시스템 상태

현재 후보자 상세 페이지는 **로그인한 사용자만 접근** 가능합니다 (Django `@login_required`). 별도의 권한 레벨(열람 권한 vs 편집 권한) 구분은 없습니다.

### 5.2 민감 정보 분류

| 필드 | 민감도 | 처리 방침 |
|------|--------|-----------|
| `phone`, `email` | 중 | **현행 유지** — 마스킹 없이 노출 (인가된 사용자 전용) |
| `current_salary`, `desired_salary` | 고 | **별도 섹션으로 분리** — 시각적 구분으로 인지 부여 |
| `salary` (Career) | 고 | **경력 항목 내 소형 텍스트** — 과도한 강조 방지 |
| `reason_left` | 중 | **접이식 기본 숨김** — 의도적 클릭으로만 노출 |
| `address` | 중 | 마스킹 없이 노출 |

### 5.3 마스킹 적용 여부

**v1에서는 마스킹을 적용하지 않습니다.** 이유:

1. 현재 사용자는 단일 조직(헤드헌팅 회사) 내부 인원으로 한정
2. 후보자 정보 열람이 핵심 업무이므로, 마스킹은 업무 효율을 저해
3. 추후 다중 조직 / 외부 공유 기능 추가 시 역할 기반 마스킹 도입 검토

**향후 고려사항:**
- 권한 레벨 도입 시: `can_view_salary` 퍼미션으로 연봉 섹션 조건부 노출
- 외부 공유 링크: 연봉/연락처 자동 마스킹 (`010-****-5678`)

---

## 6. 반응형 레이아웃 고려

### 6.1 현재 반응형 구조

- 페이지 컨테이너: `max-w-4xl mx-auto px-4 py-4`
- 모든 섹션이 단일 컬럼 (`space-y`, 세로 스택)
- 경력 타임라인: 좌측 날짜(80px) + 도트 + 우측 내용 (3열 flex)

### 6.2 추가 필드의 반응형 처리

| 컴포넌트 | 모바일 (< 768px) | 데스크톱 (>= 768px) |
|----------|-------------------|---------------------|
| **경력 요약 섹션** | 전체 너비, 단일 컬럼 | 동일 (텍스트 + 태그는 단일 컬럼이 적합) |
| **핵심 역량 태그** | `flex-wrap`으로 자연 줄바꿈 | 동일 |
| **기본 정보** | 단일 컬럼 (현행 유지) | 2열 그리드 고려 가능 (`md:grid md:grid-cols-2`) |
| **연봉 정보** | 단일 컬럼 | 2열 인라인 (`md:flex md:gap-8`) |
| **경력 타임라인** | 3열 flex (현행 유지) | 동일 |
| **성과 박스** | 전체 너비 | 동일 |
| **퇴사 사유** | 전체 너비 접이식 | 동일 |
| **학력 GPA** | 아래줄 표시 | 동일 |
| **해외 뱃지** | 인라인 (줄바꿈 시 다음 줄로) | 인라인 유지 |

### 6.3 기본 정보 섹션 2열 그리드 (데스크톱)

기본 정보 필드가 9개로 늘어나므로, 데스크톱에서는 2열 그리드가 정보 밀도를 높입니다.

```
모바일:                          데스크톱 (md 이상):
┌─────────────────┐             ┌─────────────┬─────────────┐
│ 생년: 1985      │             │ 생년: 1985  │ 성별: 남성   │
│ 성별: 남성       │             │ 카테고리: HR│ 주소: 서울...│
│ 카테고리: HR     │             │ 현재: 삼성..│ 총 경력: 15년│
│ 주소: 서울...    │             │ 출처: 드라.. │ 이메일: ...  │
│ 현재: 삼성전자...│             │ 연락처: ... │              │
│ 총 경력: 15년    │             └─────────────┴─────────────┘
│ 출처: 드라이브...│
│ 이메일: ...      │
│ 연락처: ...      │
└─────────────────┘
```

**구현:**
```html
<div class="space-y-2 text-[15px] md:grid md:grid-cols-2 md:gap-x-6 md:gap-y-2 md:space-y-0">
  <!-- 필드들 -->
</div>
```

### 6.4 연봉 섹션 가로 배치 (데스크톱)

```
모바일:                          데스크톱:
┌─────────────────┐             ┌──────────────────────────────┐
│ 현재 연봉:       │             │ 현재 연봉: 8,000만원          │
│   8,000만원      │             │ 희망 연봉: 10,000만원         │
│ 희망 연봉:       │             └──────────────────────────────┘
│   10,000만원     │
└─────────────────┘
```

---

## 7. 최종 섹션 순서 (변경 후)

| # | 섹션 | 상태 | 노출 조건 |
|---|------|------|-----------|
| 1 | 헤더 (이름 + 영문 이름) | 기존 확장 | 항상 |
| 2 | 경력 요약 + 핵심 역량 | **신규** | `summary` 또는 `core_competencies` 중 하나 이상 존재 |
| 3 | 기본 정보 | 기존 확장 | 항상 |
| 4 | 연봉 정보 | **신규** | `current_salary` 또는 `desired_salary` 중 하나 이상 존재 |
| 5 | 경력 | 기존 확장 | `careers` 존재 |
| 6 | 학력 | 기존 확장 | `educations` 존재 |
| 7 | 자격증 · 어학 | 기존 확장 | `certifications` 또는 `language_skills` 존재 |
| 8 | 파싱 신뢰도 | 기존 유지 | `confidence_score` 존재 |

---

## 8. 구현 시 체크리스트

- [ ] `django.contrib.humanize`가 `INSTALLED_APPS`에 포함되어 있는지 확인 (연봉 `intcomma` 필터 사용)
- [ ] 템플릿 상단에 `{% load humanize %}` 추가
- [ ] view에서 이미 `careers`, `educations`, `language_skills`를 context로 전달하고 있으므로 추가 쿼리 불필요
- [ ] `candidate.core_competencies`는 JSONField이므로 템플릿에서 직접 `{% for comp in candidate.core_competencies %}` 반복 가능
- [ ] `<details>`/`<summary>` 태그의 기본 삼각형 마커 스타일링 — Tailwind의 `marker:` 또는 CSS로 커스터마이징
- [ ] 접근성: 추가된 모든 인터랙티브 요소(`<details>`)가 키보드로 조작 가능한지 확인
- [ ] 기존 페이지 스타일과의 일관성: 섹션 헤더(`text-sm font-medium text-gray-500 uppercase tracking-wider`), 카드(`bg-white rounded-lg border border-gray-200 p-4 mb-3`), 본문(`text-[15px]`) 동일하게 유지

---

## 9. 참고: 기존 디자인 패턴 요약

구현 시 반드시 따라야 할 기존 패턴입니다.

| 요소 | 패턴 |
|------|------|
| 섹션 카드 | `bg-white rounded-lg border border-gray-200 p-4 mb-3` |
| 섹션 헤더 | `text-sm font-medium text-gray-500 uppercase tracking-wider mb-3` |
| 본문 텍스트 | `text-[15px]` |
| 라벨 텍스트 | `text-gray-500` (인라인 `<span>`) |
| 값 텍스트 | 기본 `text-gray-900` 또는 강조 시 `font-semibold` |
| 칩/태그 | `bg-gray-100 text-gray-700 px-2 py-1 rounded` (일반) 또는 `bg-primary-light text-primary px-2 py-1 rounded` (강조) |
| 조건부 노출 | `{% if field %}...{% endif %}` — 빈값이면 완전 숨김 |
| 폰트 | Pretendard (시스템 지정) |
| 컬러 | primary `#5B6ABF`, gray 스케일 |
| 터치 타겟 | 최소 44px |
