# 추출 스키마 재설계 계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이력서 추출 스키마를 4대 카테고리(인적사항, 학력, 경력, 능력)로 재구성. 각 카테고리에 핵심 필드 + etc[]를 두어 원본 데이터 손실 방지. 빠져 있는 기술 스택을 능력 카테고리에 추가.

**핵심 원칙:** 원본 이력서에 있는 정보는 반드시 어딘가에 저장되어야 한다. 핵심 필드에 안 맞으면 해당 카테고리의 etc[]에 넣는다. 4개 카테고리 어디에도 안 맞는 건 가장 가까운 카테고리의 etc[]에 넣는다.

**Architecture:** Candidate 모델에 `skills`, `personal_etc`, `education_etc`, `career_etc`, `skills_etc` JSONField 추가. 기존 테이블(Career, Education, Certification, LanguageSkill) 구조 유지.

**Tech Stack:** Django 5.2, Gemini 3.1 Flash Lite, PostgreSQL JSONField

**전제:** 개발 DB 초기화 완료 (Candidate/Resume/하위 레코드 전부 삭제). 재추출 시 legacy JSONField 잔존 데이터 문제 없음.

---

## 4대 카테고리 구조

```
1. 인적사항 (Personal) — 이 사람은 누구인가
   핵심: 이름, 영문명, 출생년도, 성별, 이메일, 전화번호, 주소, 병역
   etc[]: 가족사항, 자기소개, 기타 인적 정보

2. 학력 (Education) — 무엇을 배웠는가
   핵심: Education[] (학교, 학위, 전공, 학점, 기간, 해외 여부)
   etc[]: 교환학생, 연수, 교육, 세미나, 부전공, 수료 과정 등

3. 경력 (Career) — 어떤 일을 했는가
   핵심: Career[] (회사, 직책, 부서, 기간, 업무, 성과)
   etc[]: 프로젝트 상세, 해외파견, 봉사활동, 인턴 등

4. 능력 (Skills & Qualifications) — 무엇을 할 수 있는가
   핵심: skills[], Certification[], LanguageSkill[], core_competencies[]
   etc[]: 수상, 논문, 특허, 기타 능력 증빙
```

**"최상위 기타" 카테고리는 두지 않는다.** 4개 카테고리 중 가장 가까운 곳의 etc[]에 넣는다. 분류 불가능한 정보는 없다 — 사람에 관한 건 인적사항, 배운 건 학력, 한 일은 경력, 할 수 있는 건 능력.

---

## 모델 변경

### 추가할 필드 (Candidate 모델)

```python
skills = models.JSONField(
    default=list, blank=True,
    help_text='["Python", "Oracle", "SAP", ...]',
)
personal_etc = models.JSONField(
    default=list, blank=True,
    help_text='[{type, description}]',
)
education_etc = models.JSONField(
    default=list, blank=True,
    help_text='[{type, title, institution, date, description}]',
)
career_etc = models.JSONField(
    default=list, blank=True,
    help_text='[{type, name, company, role, start_date, end_date, technologies[], description}]',
)
skills_etc = models.JSONField(
    default=list, blank=True,
    help_text='[{type, title, description, date}]',
)
```

### 기존 필드 처리

DB 초기화 완료 상태이므로, 기존 개별 JSONField(awards, patents, projects 등)에는 데이터가 없음. 필드 자체는 유지하되, 새 추출에서는 etc[] 필드에 저장. 기존 JSONField는 향후 정리 시 삭제.

| 기존 필드 | 새 저장 위치 | 비고 |
|----------|------------|------|
| `military_service` | 유지 (인적사항 핵심) | 변경 없음 |
| `self_introduction` | `personal_etc` | 새 추출 시 etc[]로 |
| `family_info` | `personal_etc` | 새 추출 시 etc[]로 |
| `trainings` | `education_etc` | 새 추출 시 etc[]로 |
| `projects` | `career_etc` | 새 추출 시 etc[]로 |
| `overseas_experience` | `career_etc` | 새 추출 시 etc[]로 |
| `awards` | `skills_etc` | 새 추출 시 etc[]로 |
| `patents` | `skills_etc` | 새 추출 시 etc[]로 |
| `core_competencies` | 유지 (능력 핵심) | 변경 없음 |
| `summary` | 유지 | 변경 없음 |

**저장 정책:** 새 추출 시 legacy JSONField는 빈 값으로 저장. etc[] 필드에만 데이터 넣음. legacy + etc[] 합쳐서 보여주는 로직 불필요 (DB 초기화했으므로 legacy 데이터 없음).

---

## 추출 프롬프트 변경

### 추출 JSON 스키마 추가 필드

```json
{
  ...기존 필드 유지,
  "skills": ["string (기술·도구·시스템·방법론 등 고유명사 키워드)"],
  "personal_etc": [{"type": "string", "description": "string"}],
  "education_etc": [{"type": "string", "title": "string", "institution": "string", "date": "string", "description": "string"}],
  "career_etc": [{"type": "string", "name": "string", "company": "string", "role": "string", "start_date": "string", "end_date": "string", "technologies": ["string"], "description": "string"}],
  "skills_etc": [{"type": "string", "title": "string", "description": "string", "date": "string"}]
}
```

### 프롬프트 추가 지시

```
### skills vs core_competencies 구분

skills에는 이력서 전체에서 언급된 특정 기술·도구·시스템의 고유명사를 추출하세요.
이 데이터는 후보자 검색 시 기술 키워드 매칭에 사용됩니다.
구체적 명칭이 대상이고, 일반적 역량 서술("의사소통 능력", "리더십")은
core_competencies에 넣으세요.

구분 원칙: 그 단어로 검색했을 때 해당 기술을 가진 사람만 나와야 하면 skills,
다수의 사람에게 해당하는 일반적 역량이면 core_competencies.

직종에 따라 기술의 형태가 다릅니다:
- 소프트웨어 이름, 프로그래밍 언어, 데이터베이스
- 설비명, 측정 장비, 제조 시스템
- 인증 규격, 품질 방법론 (고유명사인 경우)
- 회계·법률·의료 등 도메인 전문 소프트웨어

### skills 표기 정규화

skills는 검색 키워드 매칭에 사용되므로 표기가 일관되어야 합니다.
- 영문 공식 명칭을 우선 사용하세요: "파이썬" → "Python", "오라클" → "Oracle"
- 공식 표기를 따르세요: "MSSQL" → "MS SQL Server", "C++" (O), "씨플플" (X)
- 원문이 한글이어도 해당 기술의 영문 공식명이 있으면 영문으로 통일하세요
- 약어가 널리 쓰이면 약어를 사용하세요: "SAP", "PMP", "ISO 9001"
- 한글만 존재하는 고유명사는 한글 그대로: "더존", "얼리슬로스"

### etc[] 필드 사용 원칙

이력서의 모든 정보는 4개 카테고리 중 하나에 반드시 속합니다:
- 인적사항: 이 사람이 누구인지에 관한 정보
- 학력: 무엇을 배웠는지에 관한 정보
- 경력: 어떤 일을 했는지에 관한 정보
- 능력: 무엇을 할 수 있는지에 관한 정보

각 카테고리에서 핵심 필드에 맞는 정보는 해당 필드에 넣으세요.
맞지 않지만 해당 카테고리에 속하는 정보는 해당 카테고리의 etc[]에 넣으세요.

원본에 있는 정보는 반드시 어딘가에 포함되어야 합니다.
누락보다 중복이 낫습니다. 확신이 없으면 포함하세요.

etc[] 항목에는 반드시 type을 넣어 무엇인지 식별할 수 있게 하세요.
예: {"type": "교환학생", "institution": "MIT", "date": "2019", "description": "6개월 교환학생"}
예: {"type": "프로젝트", "name": "ERP 전환", "company": "삼성전자", "role": "PM", "technologies": ["SAP"]}
예: {"type": "수상", "title": "우수사원상", "date": "2020", "description": "연간 최우수 성과"}
```

---

## integrity 파이프라인 전달 경로

Step 1 프롬프트만 바꾸면 부족함. 결과 조립부와 정규화 경로도 수정 필요.

### 수정 대상

1. **`candidates/services/integrity/pipeline.py` (line ~138)** — 결과 조립 dict에 새 필드 추가:
   ```python
   "skills": raw_data.get("skills", []),
   "personal_etc": raw_data.get("personal_etc", []),
   "education_etc": raw_data.get("education_etc", []),
   "career_etc": raw_data.get("career_etc", []),
   "skills_etc": raw_data.get("skills_etc", []),
   ```

2. **`candidates/services/integrity/step2_normalize.py` (line ~224)** — `normalize_skills()`에서 skills를 passthrough:
   ```python
   # skills는 고유명사 키워드 리스트이므로 정규화 불필요, 그대로 전달
   ```

3. **`data_extraction/services/extraction/integrity.py` (line ~783)** — 동일 수정

---

## 데이터 완성도 재계산

### 카테고리별 완성도 (`compute_field_confidences` 변경)

```
인적사항: 이름, 이메일, 연락처 → 3개 중 채워진 비율
학력:     학력 존재 여부 → 있으면 1.0, 없으면 0.0
경력:     경력 존재 여부 → 있으면 1.0, 없으면 0.0
능력:     기술 스택, 자격증 또는 어학 → 2개 중 채워진 비율
```

전체 완성도 = 카테고리별 평균

### 두 종류의 점수를 분리 반환

`compute_field_confidences()`는 두 dict를 반환:

```python
def compute_field_confidences(extracted, filename_parsed):
    # 1. 개별 필드 점수 (discrepancy.py 호환용, UI 미노출)
    field_scores = {
        "name": ...,
        "birth_year": ...,
        "email": ...,
        "phone": ...,
        "careers": ...,
        "educations": ...,
    }
    # 2. 카테고리 점수 (UI 표시용, 전체 완성도 계산용)
    category_scores = {
        "인적사항": ...,  # 이름, 이메일, 연락처 평균
        "학력": ...,
        "경력": ...,
        "능력": ...,     # 기술 스택, 자격증/어학 평균
    }
    return field_scores, category_scores
```

- `field_scores` → `candidate.field_confidences`에 저장 (discrepancy.py 호환)
- `category_scores` → UI 표시용. `compute_overall_confidence()`는 **category_scores만** 평균

### compute_overall_confidence 변경

```python
def compute_overall_confidence(category_scores, issues):
    # category_scores의 4개 값만 평균 (field_scores 혼합 안 함)
    values = list(category_scores.values())
    base = sum(values) / len(values)
    ...
```

이렇게 하면 전체 완성도 = 카테고리 평균이 보장되고, 기존 field_scores는 discrepancy에서 그대로 사용 가능.

### UI에서 카테고리 점수만 표시

상세 페이지 템플릿에서 `fc` 대신 `category_scores`를 순회:

```html
{% for cat_name, score in category_scores.items %}
  <!-- cat_name은 이미 한글 ("인적사항", "학력" 등) -->
{% endfor %}
```

`_cat_` prefix 불필요. 별도 라벨 매핑도 불필요. 키 자체가 한글.

### 0% 완성도 표시

`{% if live_score %}` → `{% if live_score is not None %}`로 변경. 0%여도 섹션 표시.

---

## 검색 반영

### 현재 검색 (search.py)

두 가지 검색 경로가 있음:
1. **LLM 필터 검색** (line 15, 33) — LLM이 자연어 질의에서 필터 조건을 추출. 현재 skill 전용 슬롯 없음.
2. **keyword 검색** (line 355, 357) — 이름, 회사, 직책 등 텍스트 필드 대상. skills 미포함.

### Task 7에서 두 경로 모두 수정

1. **keyword 검색에 skills 포함**: `raw_text` 또는 별도 검색 텍스트에 skills 키워드 추가
   ```python
   # skills 키워드를 검색 대상에 포함
   skill_text = " ".join(candidate.skills or [])
   ```

2. **LLM 필터 스키마에 skill_keywords 추가**: LLM이 "Python 쓸 줄 아는 사람" 질의에서 `skill_keywords: ["Python"]`을 추출할 수 있도록 필터 스키마 확장

---

## UI 영향 범위

### 상세 페이지 (실시간 계산)

`views.py`에서 `compute_field_confidences()` 실시간 호출 → `live_score` + `fc` → 카테고리별 표시. 새 카테고리 키 사용.

### 리뷰 목록/상세 (저장된 값)

`review_list_content.html` (line 41), `review_detail_content.html` (line 11)은 `candidate.confidence_score`를 직접 사용. 재추출 시 새 기준으로 저장되므로 코드 변경 불필요. 단, 리뷰 상세에서 필드별 신뢰도를 보여준다면 카테고리 라벨 매핑 필요.

### candidate_card.html

카드에서 신뢰도 관련 표시가 있다면 확인 필요.

---

## 상세 페이지 UI 재배치

```
검토 사항
요약

1. 인적사항
   기본 정보 (이름, 연락처, 주소, 성별, 생년)
   병역
   기타 ← personal_etc[]

2. 학력
   학력 목록 ← Education[]
   기타 ← education_etc[]

3. 경력
   경력 목록 ← Career[]
   기타 ← career_etc[]

4. 능력
   기술 스택 태그 ← skills[]
   자격증 목록 ← Certification[]
   어학 목록 ← LanguageSkill[]
   핵심 역량 태그 ← core_competencies[]
   기타 ← skills_etc[]

데이터 완성도 (카테고리별 + 전체)
```

---

## 작업 순서

### Task 1: 모델 + 마이그레이션

- [ ] `Candidate` 모델에 5개 JSONField 추가 (`skills`, `personal_etc`, `education_etc`, `career_etc`, `skills_etc`)
- [ ] `makemigrations` + `migrate`
- [ ] 테스트, 커밋

### Task 2: 추출 프롬프트 + 파이프라인 전달 경로 수정

- [ ] `candidates/services/llm_extraction.py` — JSON 스키마에 `skills`, 4개 `etc` 필드 추가
- [ ] `candidates/services/integrity/step1_extract.py` — Step 1 프롬프트에 skills 추출 지시 + etc[] 원칙 추가
- [ ] `candidates/services/integrity/pipeline.py` — 결과 조립 dict에 새 필드 전달 추가
- [ ] `candidates/services/integrity/step2_normalize.py` — `normalize_skills()`에서 skills passthrough 확인
- [ ] `data_extraction/services/extraction/prompts.py` — 동일 프롬프트 수정
- [ ] `data_extraction/services/extraction/integrity.py` — 동일 결과 조립 수정
- [ ] 1건 수동 추출로 skills + etc 추출 확인
- [ ] 커밋

### Task 3: 저장 로직 수정

- [ ] `candidates/services/integrity/save.py` — `_create_candidate`, `_update_candidate`에 새 필드 저장 추가
- [ ] `_create_candidate`의 legacy JSONField 저장 수정: awards, patents, projects, trainings, overseas_experience 등을 빈 값(`[]`, `{}`, `""`)으로 저장. 기존 코드가 이 필드들을 채우는 부분을 제거하거나 빈 값으로 대체
- [ ] `_update_candidate`의 legacy JSONField 저장 패턴 수정: `normalize_awards(...) or candidate.awards` → legacy 필드는 명시적으로 빈 값 저장 (`candidate.awards = []`). `or candidate.awards` 패턴 제거하여 stale 데이터 방지
- [ ] 저장 시 `confidence_score`를 새 카테고리 기준으로 계산하여 저장 (integrity 경로의 `_build_integrity_diagnosis()`가 만드는 점수를 덮어씀):
  ```python
  # save.py에서 저장 직전
  from candidates.services.validation import compute_field_confidences, compute_overall_confidence
  field_scores, category_scores = compute_field_confidences(extracted, {})
  score, status = compute_overall_confidence(category_scores, [])
  candidate.confidence_score = score
  candidate.field_confidences = field_scores
  ```
- [ ] `data_extraction/services/save.py` — 동일
- [ ] 테스트, 커밋

### Task 4: 데이터 완성도 재계산

- [ ] `candidates/services/validation.py` — `compute_field_confidences()`를 `(field_scores, category_scores)` tuple 반환으로 변경
- [ ] `candidates/services/validation.py` — `compute_overall_confidence()`를 category_scores dict 받도록 변경
- [ ] `candidates/services/validation.py` — `validate_extraction()` 내부 호출부 수정 (tuple unpack)
- [ ] `candidates/services/retry_pipeline.py` — `compute_field_confidences()` 호출부 수정 (tuple unpack). `_build_integrity_diagnosis` 경로에서도 category_scores 사용
- [ ] `data_extraction/services/validation.py` — 동일
- [ ] `data_extraction/services/pipeline.py` — 동일
- [ ] `candidates/views.py` — 호출부 수정. 템플릿에 `field_scores` (fc), `category_scores`, `live_score` 모두 전달. field_scores는 기존 배지/경고용, category_scores는 완성도 섹션용
- [ ] `candidate_detail_content.html`:
  - 완성도 섹션: `category_scores` 순회 (한글 키, 라벨 매핑 불필요)
  - 기존 배지/경고 (fc.birth_year, fc.phone 등): `field_scores`를 `fc`로 전달하여 유지
  - `{% if live_score %}` → `{% if live_score is not None %}` (0%도 표시)
- [ ] 테스트, 커밋

### Task 5: 상세 페이지 UI 재배치

- [ ] 4대 카테고리 섹션 순서로 재배치
- [ ] 능력 섹션에 기술 스택 태그 추가
- [ ] 각 카테고리의 etc[] 항목 표시
- [ ] 데이터 완성도를 카테고리별로 표시 (category_scores 순회)
- [ ] 리뷰 상세 페이지 — 저장된 confidence_score 정상 표시 확인
- [ ] candidate_card — 신뢰도 관련 표시 확인
- [ ] 브라우저 확인, 커밋

### Task 6: 전체 재추출

- [ ] `uv run python manage.py extract --drive "URL" --integrity --workers 10` 실행
- [ ] 전체 ~1,581건 추출 (예상 ~50분, ~$17)
- [ ] skills 필드 포함 확인
- [ ] etc[] 필드 포함 확인
- [ ] `candidate.confidence_score`가 카테고리 평균 기준으로 저장됨 확인
- [ ] 비용/시간 측정
- [ ] 커밋

### Task 7: 검색에 skills 반영

- [ ] `candidates/services/search.py` — `FILTER_SPEC_TEMPLATE`에 `skill_keywords` 슬롯 추가
- [ ] `candidates/services/search.py` — LLM에게 보여주는 스키마 문자열과 출력 예시에 `skill_keywords` 반영 (LLM이 이 필드를 생성하도록)
- [ ] `candidates/services/search.py` — `normalize_filter_spec()`에서 `skill_keywords` 처리
- [ ] `candidates/services/search.py` — queryset 빌더에 `skills__contains` 필터 추가
- [ ] `candidates/services/search.py` — keyword 검색 대상에 skills 포함 (Q 객체에 추가)
- [ ] 검색 LLM 프롬프트에 "skill_keywords는 영문 공식명으로 변환하여 반환" 규칙 추가. 사용자가 "파이썬"이라고 입력해도 LLM이 `skill_keywords: ["Python"]`으로 변환해서 반환하도록 지시 (저장 표기와 일치)
- [ ] 기술 키워드로 검색 시 해당 후보자 매칭 확인 (자연어 "파이썬 쓸 줄 아는 사람" → LLM이 skill_keywords: ["Python"] 생성 → 필터 적용)
- [ ] 테스트, 커밋

### Task 8: 통합 테스트

- [ ] legacy 추출 경로 (`candidates/services/retry_pipeline.py`) — field_scores/category_scores 정상 반환 테스트
- [ ] integrity 추출 경로 (`candidates/services/integrity/pipeline.py`) — skills, etc[] 전달 테스트
- [ ] data_extraction 추출 경로 (`data_extraction/services/pipeline.py`) — 동일
- [ ] 저장 경로 — confidence_score가 카테고리 평균으로 저장되는지 확인
- [ ] discrepancy — field_scores의 기존 키(birth_year, phone 등)로 정상 동작 확인
- [ ] 검색 기능 — skills 키워드 매칭 + LLM 필터 스키마 확인
- [ ] 상세 페이지 — 기존 배지/경고(fc.birth_year 등) 정상 표시 + 완성도 카테고리별 표시
- [ ] 리뷰 목록/상세 — confidence_score 정상 표시
- [ ] 전체 `uv run pytest -v` 통과
- [ ] 커밋

---

## 완료 기준

1. 추출 결과에 `skills[]`가 포함됨 (기술 스택 고유명사)
2. 추출 결과에 각 카테고리 `etc[]`가 포함됨 (핵심 필드에 안 맞는 데이터)
3. 원본 이력서의 정보가 누락 없이 어딘가에 저장됨
4. 상세 페이지가 4대 카테고리 순서로 재배치
5. 기술 스택 태그가 능력 섹션에 표시
6. 데이터 완성도가 카테고리별로 표시 (인적사항/학력/경력/능력)
7. `candidate.confidence_score`가 카테고리 평균으로 저장됨 (integrity 경로 포함)
8. 기존 `discrepancy.py`의 `field_confidences` 참조(birth_year, phone 등)가 정상 동작
9. 상세 페이지의 기존 배지/경고(fc.birth_year 등)가 정상 유지
10. 검색에서 기술 키워드로 후보자 매칭 가능 (keyword + LLM 필터 양쪽)
11. 리뷰 목록/상세에서 confidence_score 정상 표시
12. 전체 테스트 통과
13. 김병민 이력서에서 VC++, Oracle, MSSQL 등 기술 스택 추출됨
