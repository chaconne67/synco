# 이력서 위조 감지 & 헤드헌터 코멘트 시스템

---

## 왜 만드는가 (목적)

헤드헌팅 업무에서 **이력서 위조/과장은 실무적으로 빈번하게 발생하는 문제**다. 학부를 숨기고 대학원만 기재하거나, 짧은 경력을 삭제하거나, 여러 회사 경력을 하나로 통합하거나, 이력서를 낼 때마다 생년이 달라지는 경우가 실제로 존재한다. 이런 후보자를 고객사에 추천하면 **신뢰 손상과 비즈니스 리스크**로 직결된다.

현재 synco는 이력서를 자동 파싱하고 기간 중복 같은 기본 무결성 검사를 수행하지만, **실무에서 가장 많이 발생하는 위조 패턴을 감지하지 못하고**, 헤드헌터가 인터뷰를 통해 확인한 결과를 **시스템에 기록할 수단이 없다**. 위조 의심 사항은 구두로만 전달되거나, 파일명에 "추천불가"를 붙이는 식으로 관리되고 있다.

## 무엇을 원하는가 (목표)

1. **자동으로 잡을 수 있는 위조 패턴은 시스템이 먼저 감지한다.** 헤드헌터가 이력서를 열었을 때, 학부 누락·입학년도 누락·캠퍼스 의심·생년 불일치·경력 삭제/통합 등의 경고가 이미 표시되어 있어야 한다. 사람이 일일이 눈으로 찾는 수고를 줄인다.

2. **헤드헌터가 인터뷰 후 판정과 사유를 체계적으로 기록한다.** "추천/비추천/보류" 판정과 구조화된 사유 코드(학부 미기재, 경력 삭제 의심 등) + 자유텍스트 코멘트를 후보자 단위로 남길 수 있다. 이 기록은 DB에 저장되어 검색·필터링·이력 추적이 가능하다.

3. **비추천/보류 후보자를 즉시 필터링할 수 있다.** 목록에서 추천 상태별로 필터링하여, 비추천 후보자가 고객사에 추천되는 사고를 방지한다.

## 어떤 결과가 나와야 하는가 (성공 기준)

- 이력서 추출 완료 시, 위조 의심 알림이 기존 RED/YELLOW/BLUE 체계로 자동 표시됨
- 멀티캠퍼스 대학(고려대 안암/세종, 연세대 신촌/원주 등)에 대해 캠퍼스 미기재 또는 지방캠퍼스 학과 자동 감지됨
- 상세페이지에서 추천/비추천/보류 판정 + 사유 선택 + 자유텍스트(음성 입력 지원) 코멘트를 저장할 수 있음
- 코멘트 이력이 시간순으로 표시되어, 누가 언제 어떤 판정을 내렸는지 추적 가능함
- 목록에서 추천 상태별 필터링이 동작함

---

## 배경

엑스다임 내부 헤드헌터가 이력서를 접수받아 검수할 때, 다음과 같은 위조/누락 패턴이 빈번하게 발생한다:

- **학력:** 학부 미기재(대학원만), 입학년도 누락(편입 은폐), 캠퍼스 미기재(지방캠퍼스 은폐)
- **경력:** 짧은 재직 경력 삭제, 여러 회사를 하나로 통합, 업무 내용 불일치
- **생년:** 이력서 버전마다 출생연도가 다름 (나이 줄이기 시도)

현재 synco에는 무결성 파이프라인(`integrity.py`)과 RED/YELLOW/BLUE 알림 체계가 있으나, 위 패턴에 대한 **전용 감지 규칙이 없고**, 헤드헌터가 인터뷰 후 **판정/코멘트를 기록할 수단도 없다**.

---

## 범위

### 포함

1. 자동 감지 규칙 6종 추가 (기존 파이프라인 확장)
2. 멀티캠퍼스 대학 매핑 데이터 구축 (정적 JSON)
3. 후보자 추천 판정 (`recommendation_status`) 필드
4. 헤드헌터 코멘트 모델 (`CandidateComment`)
5. 상세페이지 코멘트 UI (판정 + 사유 선택 + 자유텍스트 + 음성 입력)
6. 목록 페이지 추천 상태 필터

### 제외

- 대학 DB 실시간 조회 (정적 매핑으로 대체)
- 업무 내용 위조 감지 (면접으로만 파악 가능)
- 파일명 "추천불가" 자동 인식 (데이터 확인 불가)
- 비정규 학력(숭실전산원 등) 자동 판별

---

## 1. 자동 감지 규칙

기존 `data_extraction/services/extraction/integrity.py`의 `check_*` 패턴을 따른다. 모든 규칙은 동일한 알림 형식(`type`, `severity`, `field`, `detail`, `reasoning`)을 반환하고, `run_integrity_pipeline()`의 Step 3에서 호출된다.

### 1.1 학력 검증 — `check_education_gaps(educations)`

| 감지 항목 | 조건 | severity |
|-----------|------|----------|
| 학부 누락 | 대학원(석사/박사) 학력이 있으나 학부(학사) 학력 없음 | YELLOW |
| 입학년도 누락 | `end_year`만 있고 `start_year` 없음 | YELLOW |

**입력:** `normalized_educations` 리스트
**판단 기준:**
- degree 필드에서 "석사", "박사", "MBA", "master", "doctor", "ph.d" 등 대학원 키워드 매칭
- 같은 후보자에 "학사", "bachelor" 등 학부 학력이 하나도 없으면 YELLOW

### 1.2 캠퍼스 매칭 — `check_campus_match(educations)`

멀티캠퍼스 대학 매핑 데이터(`multi_campus_universities.json`)를 참조하여 감지.

| 감지 항목 | 조건 | severity |
|-----------|------|----------|
| 캠퍼스 미기재 | 멀티캠퍼스 대학인데 캠퍼스 정보 없음 | YELLOW |
| 지방캠퍼스 학과 매칭 | 학과가 지방캠퍼스에만 존재하는 것으로 확인됨 | RED |

**판단 로직:**
1. `institution`에서 대학명 추출 (별칭 매칭 포함: "고대" → "고려대학교")
2. 매핑 테이블에 해당 대학이 있으면 → 캠퍼스 키워드 탐색 ("세종", "원주", "ERICA", "수원" 등)
3. 캠퍼스 키워드가 없으면 → YELLOW "캠퍼스 확인 필요 (고려대학교: 안암/세종)"
4. `major`가 `campus_only_departments`에 매칭되면 → RED "해당 학과는 세종캠퍼스에만 존재"

### 1.3 생년 불일치 — `check_birth_year_consistency(current_birth_year, previous_birth_year)`

버전 간 비교 규칙. `birth_year`는 `compare_versions()`의 careers/educations dict에 포함되지 않으므로, `run_integrity_pipeline()` Step 3에서 직접 호출. `raw_data.get("birth_year")`와 `previous_data`의 birth_year를 비교한다. `previous_data` dict에 `birth_year` 키를 추가로 전달받도록 파이프라인 호출부를 수정.

| 감지 항목 | 조건 | severity |
|-----------|------|----------|
| 생년 불일치 | 이전 버전과 현재 버전의 `birth_year`가 다름 | RED |

**detail 예시:** "출생연도가 이전 이력서(1974년)와 현재(1975년)에서 다름. 호적 기준 확인 필요"

### 1.4 경력 통합 의심 — `check_career_consolidation(current_careers, previous_careers)`

버전 간 비교 규칙. `compare_versions()` 내부에서 호출 (careers 데이터로 판단 가능).

| 감지 항목 | 조건 | severity |
|-----------|------|----------|
| 경력 통합 | 이전 버전 2개 이상 경력의 합산 기간과 현재 1개 경력의 기간이 유사 | RED |

**판단 로직:**
1. 이전 버전에서 삭제된(unmatched) 경력들을 수집
2. 현재 버전에서 새로 추가된/기간이 늘어난 경력을 수집
3. 삭제된 경력들의 기간 합산 ≈ 늘어난 경력의 기간 증분 (±3개월 허용) → RED

### 1.5 경력 삭제 보강 — 기존 `_check_career_deleted` 수정

| 감지 항목 | 조건 | severity 변경 |
|-----------|------|---------------|
| 반복 삭제 | 삭제된 경력이 2건 이상 | YELLOW → RED |

기존 `_check_career_deleted()`가 반환하는 플래그에서, 삭제 건수가 2건 이상이면 전체를 RED로 승격.

### 파이프라인 통합 위치

`run_integrity_pipeline()` 내 Step 3 영역 (line 917~933):

```python
# 3a: Career period overlaps (기존)
# 3b: Career-education overlaps (기존)
# 3c: Cross-version comparison (기존 — birth_year, consolidation 추가)

# 3d: Education gaps (신규)
edu_gap_flags = check_education_gaps(normalized_educations)
all_flags.extend(edu_gap_flags)

# 3e: Campus match (신규)
campus_flags = check_campus_match(normalized_educations)
all_flags.extend(campus_flags)
```

경력 통합은 `compare_versions()` 내부에서 호출. 생년 불일치는 Step 3에서 별도 호출:

```python
# 3f: Birth year consistency (신규, pipeline level)
if previous_data and previous_data.get("birth_year"):
    birth_flags = check_birth_year_consistency(
        raw_data.get("birth_year"), previous_data["birth_year"]
    )
    all_flags.extend(birth_flags)
```

---

## 2. 멀티캠퍼스 대학 매핑 데이터

### 파일 위치

`data_extraction/data/multi_campus_universities.json`

### 데이터 구조

```json
{
  "고려대학교": {
    "main_campus": "안암(서울)",
    "tier": "SKY",
    "campuses": {
      "안암(서울)": {"in_seoul": true},
      "세종": {"in_seoul": false, "tier_override": "지방거점"}
    },
    "campus_only_departments": {
      "세종": ["약학과", "간호학과", "공공정책학부", "문화스포츠학부", "자유전공학부(세종)"],
      "안암(서울)": ["의학과", "법학전문대학원"]
    },
    "campus_keywords": {
      "안암(서울)": ["안암", "서울"],
      "세종": ["세종", "조치원"]
    },
    "aliases": ["고대", "고려대", "Korea Univ", "Korea University"]
  }
}
```

### 대상 대학 목록

기존 `korean-university-rankings.md`의 분류와 연동:

| 대학 | 캠퍼스 | 비고 |
|------|--------|------|
| 고려대학교 | 안암(서울) / 세종 | SKY vs 지방거점 |
| 연세대학교 | 신촌(서울) / 원주(미래) | SKY vs 지방 |
| 성균관대학교 | 인문사회(서울) / 자연과학(수원) | 서성한, 인서울 vs 경기 |
| 한양대학교 | 서울 / ERICA(안산) | 서성한 vs 별도 |
| 건국대학교 | 서울 / 글로컬(충주) | 인서울 vs 지방 |
| 동국대학교 | 서울 / 경주 | 인서울 vs 지방 |
| 홍익대학교 | 서울 / 세종 | 인서울 vs 지방 |
| 단국대학교 | 죽전(경기) / 천안 | 수도권 vs 지방 |
| 경희대학교 | 서울 / 국제(수원) | 인서울 vs 경기 |

### 데이터 수집 방법

웹 검색으로 각 대학의 캠퍼스별 학과 목록을 수집하여 JSON 파일 작성. 이후 수동 업데이트.

---

## 3. 후보자 추천 판정

### Candidate 모델 변경

```python
class RecommendationStatus(models.TextChoices):
    PENDING = "pending", "미결정"
    RECOMMENDED = "recommended", "추천"
    NOT_RECOMMENDED = "not_recommended", "비추천"
    ON_HOLD = "on_hold", "보류"

# Candidate 모델에 추가
recommendation_status = models.CharField(
    max_length=20,
    choices=RecommendationStatus.choices,
    default=RecommendationStatus.PENDING,
    db_index=True,
)
```

- 기존 `validation_status`(자동 검증)와 독립적으로 운영
- `validation_status`: 시스템이 자동으로 판정 (추출 성공/실패/검토 필요)
- `recommendation_status`: 헤드헌터가 인터뷰 후 수동 판정 (추천/비추천/보류)

---

## 4. 코멘트 모델

### CandidateComment

```python
class CandidateComment(BaseModel):
    """후보자 검수 코멘트. 판정 변경 이력 포함."""

    class InputMethod(models.TextChoices):
        TEXT = "text", "텍스트"
        VOICE = "voice", "음성"

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="candidate_comments",
    )

    # 판정 스냅샷 (이 코멘트 시점의 판정)
    recommendation_status = models.CharField(
        max_length=20,
        choices=Candidate.RecommendationStatus.choices,
    )

    # 사유 코드 (복수 선택)
    reason_codes = models.JSONField(
        default=list,
        blank=True,
        help_text='["edu_undergrad_missing", "career_deleted", ...]',
    )

    # 자유 텍스트
    content = models.TextField(blank=True)

    # 입력 방식
    input_method = models.CharField(
        max_length=10,
        choices=InputMethod.choices,
        default=InputMethod.TEXT,
    )

    class Meta:
        db_table = "candidate_comments"
        ordering = ["-created_at"]
```

### 사유 코드 정의

코드에서 상수로 관리 (DB에 별도 테이블 불필요):

```python
REASON_CODES = {
    # 학력
    "edu_undergrad_missing": "학부 미기재 (대학원만 기재)",
    "edu_campus_suspicious": "캠퍼스 미기재 또는 의심",
    "edu_admission_year_missing": "입학년도 미기재 (편입 의심)",
    "edu_non_degree_program": "비정규 과정 (전산원 등)",
    # 경력
    "career_deleted": "경력 삭제 의심",
    "career_consolidated": "경력 통합 의심",
    "career_content_mismatch": "업무 내용 불일치 (면접 확인)",
    "career_gap_suspicious": "경력 공백 의심",
    # 신상
    "birth_year_mismatch": "출생연도 불일치",
    # 기타
    "other": "기타",
}
```

향후 사유 코드 추가/변경 시 이 dict만 수정하면 UI에 자동 반영.

### 코멘트 저장 시 동작

1. `CandidateComment` 생성
2. `Candidate.recommendation_status`를 코멘트의 `recommendation_status`로 업데이트
3. 하나의 트랜잭션으로 처리

---

## 5. UI 설계

### 5.1 상세페이지 코멘트 섹션

`candidates/templates/candidates/partials/review_detail_content.html` 하단, 기존 컨텐츠 아래에 추가.

**구성:**

```
┌─────────────────────────────────────────────┐
│ 검수 판정                                    │
│                                             │
│ [● 추천] [○ 비추천] [○ 보류]    ← 라디오     │
│                                             │
│ 사유 선택:                                   │
│ [x] 학부 미기재        [ ] 경력 삭제 의심      │
│ [ ] 캠퍼스 의심         [ ] 경력 통합 의심      │
│ [ ] 입학년도 미기재     [ ] 업무 내용 불일치     │
│ [ ] 비정규 과정         [ ] 출생연도 불일치      │
│ [ ] 기타                                     │
│                                             │
│ 코멘트:                                      │
│ ┌─────────────────────────────── [🎤]─┐     │
│ │                                      │     │
│ └──────────────────────────────────────┘     │
│                                             │
│                          [저장]              │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ 코멘트 이력                                  │
│                                             │
│ 2026-04-05 14:30  홍길동                     │
│ 비추천 · 학부 미기재, 경력 삭제 의심            │
│ "인터뷰 결과 학부는 지방대 졸업 후 편입 확인.   │
│  2018~2019 경력 누락 인정함."                 │
│                                             │
│ 2026-04-03 10:15  김영희                     │
│ 보류 · 캠퍼스 의심                            │
│ "고려대 세종캠퍼스 여부 확인 필요"              │
└─────────────────────────────────────────────┘
```

### 5.2 음성 입력

Web Speech API (`SpeechRecognition`)를 사용한 브라우저 네이티브 음성 인식:

```javascript
const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
recognition.lang = 'ko-KR';
recognition.continuous = true;
```

- 마이크 버튼 클릭 → 음성 인식 시작 → textarea에 실시간 반영
- 저장 시 `input_method = "voice"` 기록
- 브라우저 미지원 시 마이크 버튼 숨김

### 5.3 목록 페이지 필터

기존 리뷰 목록(`review_list.html`)에 `recommendation_status` 필터 추가:

```
[전체] [미결정] [추천] [비추천] [보류]
```

기존 `validation_status` 필터와 나란히 배치. 두 필터는 AND 조건으로 동작.

### 5.4 상세페이지 헤더 배지

후보자 이름 옆에 추천 상태 배지 표시:

- 추천: 녹색 배지
- 비추천: 빨간색 배지
- 보류: 노란색 배지
- 미결정: 표시 없음

---

## 6. API 엔드포인트

### POST `/candidates/<uuid:pk>/comments/`

코멘트 생성 + 판정 업데이트.

**Request (HTMX form):**
```
recommendation_status=not_recommended
reason_codes=edu_undergrad_missing,career_deleted
content=인터뷰 결과 학부는 지방대...
input_method=voice
```

**Response:** 코멘트 이력 partial HTML (HTMX swap)

### GET `/candidates/<uuid:pk>/comments/`

코멘트 이력 조회. 상세페이지 로드 시 포함.

---

## 7. 마이그레이션 계획

1. `Candidate` 모델에 `recommendation_status` 필드 추가 (default="pending")
2. `CandidateComment` 모델 생성
3. `makemigrations` → `migrate`
4. 기존 후보자는 모두 `pending` 상태로 시작

---

## 8. 파일 변경 목록

| 파일 | 변경 내용 |
|------|-----------|
| `candidates/models.py` | `RecommendationStatus`, `recommendation_status` 필드, `CandidateComment` 모델 |
| `data_extraction/services/extraction/integrity.py` | `check_education_gaps()`, `check_campus_match()`, `check_birth_year_consistency()`, `check_career_consolidation()`, `_check_career_deleted()` 보강 |
| `data_extraction/data/multi_campus_universities.json` | 멀티캠퍼스 대학 매핑 데이터 (신규) |
| `candidates/views.py` | 코멘트 생성/조회 뷰 |
| `candidates/urls.py` | 코멘트 URL 패턴 |
| `candidates/templates/candidates/partials/review_detail_content.html` | 코멘트 섹션 UI |
| `candidates/templates/candidates/partials/_comment_section.html` | 코멘트 폼 + 이력 partial (신규) |
| `candidates/templates/candidates/partials/_comment_list.html` | 코멘트 이력 partial (신규) |
| `candidates/templates/candidates/review_list_content.html` | 추천 상태 필터 |
| `static/js/voice-input.js` | 음성 입력 JS (신규) |
| `tests/test_fraud_detection.py` | 자동 감지 규칙 테스트 (신규) |
| `tests/test_candidate_comments.py` | 코멘트 CRUD 테스트 (신규) |
