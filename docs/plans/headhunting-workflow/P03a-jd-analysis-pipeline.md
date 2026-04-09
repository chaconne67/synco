# P03a: JD 분석 파이프라인

> **Phase:** 3a (P03과 P05 사이)
> **선행조건:** P03 (project CRUD — JD 업로드 가능), P01 (models — Project.jd_analysis 필드)
> **산출물:** JD 파일 입력 → AI 분석 → requirements 자동 추출 → 서칭 필터 자동 생성

---

## 목표

프로젝트 등록 시 JD(Job Description) 파일을 업로드하거나 Google Drive에서 가져와
AI가 요구조건을 자동 추출하고, 후보자 서칭 필터로 변환한다.

---

## JD 입력 소스

| 소스 | 설명 | 구현 |
|------|------|------|
| **파일 업로드** | PDF, Word, HWP 직접 업로드 | 기존 data_extraction 텍스트 추출 활용 |
| **Google Drive** | 공유 폴더에서 파일 선택 | 기존 Drive API 연동 활용 |
| **텍스트 입력** | JD 내용 직접 붙여넣기 | textarea → jd_text 저장 |

---

## Project 모델 추가 필드

```python
# P01에서 정의한 Project 모델에 추가
jd_source = models.CharField(max_length=20, choices=[
    ("upload", "파일 업로드"),
    ("drive", "Google Drive"),
    ("text", "텍스트 입력"),
], blank=True)
jd_drive_file_id = models.CharField(max_length=255, blank=True)  # Drive 파일 ID
jd_raw_text = models.TextField(blank=True)        # 원문 텍스트 (추출/입력)
jd_analysis = models.JSONField(default=dict, blank=True)  # AI 전체 분석 결과
# requirements는 기존 필드 — AI가 추출한 구조화 조건 저장
```

---

## AI 분석 파이프라인

```
JD 입력 (파일/Drive/텍스트)
  │
  ├─ 1. 텍스트 추출
  │   파일 → data_extraction/services/text.py 활용 (PDF/Word/HWP 지원)
  │   Drive → Drive API로 파일 다운로드 → 텍스트 추출
  │   텍스트 → 그대로 사용
  │   → jd_raw_text에 저장
  │
  ├─ 2. AI 구조화 분석 (Gemini structured output)
  │   → jd_analysis JSON 생성
  │   → requirements JSON 생성 (서칭 필터용)
  │
  └─ 3. 후보자 자동 매칭
      requirements 기반으로 candidates 검색
      적합도 점수 산출 (높음/보통/낮음)
```

---

## AI 추출 결과: requirements JSON 스키마

```json
{
  "position": "품질기획팀장",
  "position_level": "과장~차장",
  "birth_year_from": 1982,
  "birth_year_to": 1986,
  "gender": "male",
  "min_experience_years": 12,
  "max_experience_years": 16,
  "education": {
    "preference": "이공계열",
    "fields": ["전자공학", "재료공학", "산업공학"]
  },
  "certifications": {
    "required": [],
    "preferred": ["품질경영기사", "6Sigma Black Belt"]
  },
  "keywords": ["QMS", "ISO", "IATF", "CTQ", "VE", "8D", "FMEA"],
  "industry": "제조업(전자/디바이스/부품)",
  "role_summary": "전사 품질 체계(QMS) 설계·표준화...",
  "responsibilities": ["품질 전략 로드맵 수립", "KPI 정의", "..."]
}
```

---

## URL 설계

| URL | View | 설명 |
|-----|------|------|
| `/projects/<uuid:pk>/analyze-jd/` | `analyze_jd` | JD 분석 트리거 (POST) |
| `/projects/<uuid:pk>/jd-results/` | `jd_results` | 분석 결과 표시 (HTMX partial) |
| `/projects/<uuid:pk>/drive-picker/` | `drive_picker` | Drive 파일 선택 UI |

---

## 서비스 구현

```python
# projects/services/jd_analysis.py

def analyze_jd(project: Project) -> dict:
    """JD 텍스트를 분석하여 requirements를 추출한다."""
    raw_text = project.jd_raw_text
    if not raw_text:
        raise ValueError("JD 텍스트 없음")

    # Gemini structured output으로 추출
    result = extract_jd_requirements(raw_text)

    project.jd_analysis = result["full_analysis"]
    project.requirements = result["requirements"]
    project.save(update_fields=["jd_analysis", "requirements"])
    return result

def extract_jd_requirements(text: str) -> dict:
    """Gemini API로 JD 텍스트에서 요구조건 추출."""
    # 기존 data_extraction의 Gemini 연동 패턴 활용
    # structured output 스키마 정의
    ...

def expand_keywords(keywords: list[str]) -> dict[str, list[str]]:
    """JD 키워드를 동의어/유사 표현으로 확장하여 검색 recall을 높인다.

    Gemini/Claude API로 한/영 양방향 확장, 약어/풀네임 매핑을 수행.
    Returns: {원본 키워드: [확장 키워드 리스트]}
    예: {"QMS": ["품질경영시스템", "quality management system", "ISO 9001"]}
    """
    ...

def match_candidates(requirements: dict) -> list:
    """requirements 기반으로 후보자를 검색하고 적합도 점수를 산출.

    적응형 매칭: 스코어는 후보자 고정 속성이 아닌 'JD x 후보자' 쌍의 맥락적 평가.
    expand_keywords로 확장된 키워드를 사용하여 검색 범위 확대.
    """
    # 기존 candidates/services/search.py 필터 로직 활용
    # 키워드 동의어 확장 → 검색 recall 향상
    expanded = expand_keywords(requirements.get("keywords", []))
    # 각 조건별 가중치 → 종합 적합도
    ...

def generate_gap_report(candidate, requirements: dict) -> dict:
    """후보자별 JD 요구사항 충족/미충족을 항목별로 분석한 리포트를 생성.

    Returns: {
        "score": 85,
        "items": [
            {"requirement": "경력 12~16년", "status": "met", "evidence": "careers 16년 확인"},
            {"requirement": "6Sigma BB", "status": "gap", "evidence": "certifications 미보유",
             "severity": "preferred"},
        ],
        "pitch": "품질기획 16년, QMS/ISO 전문가. 6Sigma만 보완 필요",
        "gap_summary": "우대사항 1건 미충족, 연령 범위 근접",
    }
    """
    ...
```

---

## UI 와이어프레임

### 프로젝트 등록 — JD 입력 확장

```
┌─ 새 의뢰 등록 ────────────────────────────────────┐
│                                                   │
│  고객사: [Rayence              ▾]                  │
│  포지션명: [품질기획팀장            ]                │
│                                                   │
│  JD 입력:                                         │
│  ┌─────────┬──────────────┬────────────┐         │
│  │ 📎 파일   │ 📁 Google Drive │ ✏️ 텍스트  │         │
│  └─────────┴──────────────┴────────────┘         │
│                                                   │
│  (파일 업로드 선택 시)                               │
│  📎 JD 파일: [rayence_jd.pdf        ] [업로드]     │
│                                                   │
│  (Drive 선택 시)                                   │
│  📁 [AI_HH > JD 폴더 브라우징...]                   │
│     rayence_품질기획_jd.docx  [선택]                │
│                                                   │
│  [JD 분석 →]                                      │
└───────────────────────────────────────────────────┘
```

### JD 분석 결과 확인

```
┌─ JD 분석 결과 ────────────────────────────────────┐
│                                                   │
│  ✅ 분석 완료                                      │
│                                                   │
│  ┌─ 추출된 요구조건 ─────────────────────────┐    │
│  │ 포지션: 품질기획팀장 (과장~차장)             │    │
│  │ 연령: 38~42세 (1982~1986)               │    │
│  │ 성별: 남                                 │    │
│  │ 경력: 12~16년                            │    │
│  │ 업종: 제조업 (전자/디바이스/부품)            │    │
│  │ 자격증: 품질경영기사(우대), 6Sigma BB       │    │
│  │ 전공: 이공계열 (전자/재료/산업공학)          │    │
│  │ 키워드: QMS, ISO, IATF, CTQ, FMEA       │    │
│  └─────────────────────────────────────────┘    │
│                                                   │
│  [✅ 이 조건으로 등록]  [✏️ 수정]  [🔄 재분석]       │
│                                                   │
│  등록 시 자동:                                     │
│  → 이 조건으로 후보자 자동 서칭                      │
│  → 공지 초안 자동 생성                              │
└───────────────────────────────────────────────────┘
```

---

## 적합도 매칭 시스템

> **핵심 원칙:** 적합도 스코어는 후보자의 고정 속성이 아니라 **"JD x 후보자" 쌍에 대한 맥락적 평가**이다.
> 같은 후보자도 JD가 달라지면 완전히 다른 스코어를 가진다. 이를 **적응형 매칭(Adaptive Matching)** 이라 한다.

### 5차원 가중치 스코어링

| 조건 | 가중치 | 판정 |
|------|--------|------|
| 경력 범위 일치 | 25% | 범위 내 = 만점, ±2년 = 감점, 그 외 = 0 |
| 업종·키워드 매칭 | 25% | 키워드 겹침 비율 |
| 자격증 보유 | 20% | required 충족 + preferred 보너스 |
| 학력 조건 | 15% | 전공 일치, 대학 티어 |
| 연령·성별 | 15% | 필수 조건 미충족 시 부적합 |

결과: **높음**(70%+) / **보통**(40~70%) / **낮음**(40%-)

### 키워드 동의어 확장 (검색 recall 향상)

JD 키워드를 후보자 DB에서 사용되는 다양한 표현으로 확장하여 검색 누락을 줄인다.
career-ops(구직자 도구)의 키워드 매칭 방법론을 역적용한 접근: 구직자가 이력서를 JD에 맞추는 것처럼, 헤드헌터는 JD를 이력서에 맞춰 검색어를 확장한다.

```
JD: "RAG pipelines"        → DB 검색: ["RAG", "retrieval augmented", "벡터 검색", "embedding"]
JD: "stakeholder management" → ["이해관계자 관리", "cross-functional", "부서 간 협업"]
JD: "QMS"                  → ["품질경영시스템", "quality management system", "ISO 9001"]
JD: "6Sigma Black Belt"    → ["6시그마", "6Sigma BB", "식스시그마 블랙벨트"]
```

- Gemini/Claude API로 동의어 확장 수행
- 한/영 양방향 확장, 약어/풀네임 매핑 포함
- 확장된 키워드는 기존 `업종·키워드 매칭` 가중치(25%)에 반영되어 recall을 높임

### Gap 분석 리포트 (후보자별 JD 커버율)

각 후보자에 대해 JD 요구사항 충족/미충족을 항목별로 분석한 리포트를 생성한다.
단순 점수가 아닌 **근거 기반 판정**을 제공하여 헤드헌터의 의사결정을 지원한다.

```
후보자 홍길동 — JD 적합도 85%
  ✅ 경력 16년 (요구: 12~16년) — careers 데이터로 확인
  ✅ 품질 관련 직무 경험 — duties에서 "품질기획", "QMS" 확인
  ❌ 6Sigma BB 미보유 — certifications에 없음 (Gap: 우대사항)
  ✅ 이공계 학사 — education에서 확인
  ⚠️ 연령 37세 (요구: 38~42세) — 범위 근접, 감점 적용
  → 추천 포인트: "품질기획 16년, QMS/ISO 전문가. 6Sigma만 보완 필요"
  → Gap 요약: 우대사항 1건 미충족, 연령 범위 근접
```

- 각 요구사항을 `✅ 충족` / `❌ 미충족` / `⚠️ 부분 충족`으로 분류
- 미충족 항목은 필수/우대 구분하여 심각도 표시
- 추천 포인트(pitch 문구)와 gap 요약을 자동 생성

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| 파일 업로드 | PDF, Word, HWP 각각 업로드 → 텍스트 추출 성공 |
| Drive 가져오기 | Drive 파일 선택 → 다운로드 → 텍스트 추출 |
| AI 분석 | 샘플 JD → requirements JSON 추출 정확도 |
| 필터 매핑 | 추출된 조건 → 서칭 탭 필터 자동 세팅 |
| 후보자 매칭 | 조건 기반 검색 → 적합도 점수 산출 |
| 키워드 확장 | JD 키워드 → 동의어 확장 → 검색 recall 향상 검증 |
| Gap 리포트 | 후보자별 요구사항 충족/미충족 항목 분류 정확도 |
| 적응형 매칭 | 동일 후보자, 다른 JD → 다른 스코어 산출 확인 |
| 대화형 연동 | 보이스로 "JD 올릴게" → 분석 → 확인 → 등록 |

---

## 산출물

- `projects/services/jd_analysis.py` — JD 분석 서비스 (`analyze_jd`, `extract_jd_requirements`)
- `projects/services/jd_prompts.py` — Gemini 프롬프트
- `projects/services/candidate_matching.py` — 적합도 매칭 (`match_candidates`, `expand_keywords`, `generate_gap_report`)
- `projects/views.py` — analyze_jd, jd_results, drive_picker 뷰
- `projects/templates/projects/partials/jd_*.html` — JD 관련 템플릿
- `projects/templates/projects/partials/gap_report.html` — 후보자별 Gap 분석 리포트 표시
- P03 프로젝트 등록 폼 확장 (JD 소스 선택 UI)
- P05 서칭 탭 연동 (requirements → 필터 자동 세팅)
- Gap 리포트 → 후보자 상세에서 JD별 적합도 근거 확인 UI
