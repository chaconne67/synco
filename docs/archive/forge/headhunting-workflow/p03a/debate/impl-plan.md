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
    """JD 키워드를 동의어/유사 표현으로 확장하여 검색 recall을 높인다."""
    ...

def match_candidates(requirements: dict) -> list:
    """requirements 기반으로 후보자를 검색하고 적합도 점수를 산출."""
    ...

def generate_gap_report(candidate, requirements: dict) -> dict:
    """후보자별 JD 요구사항 충족/미충족을 항목별로 분석한 리포트를 생성."""
    ...
```

---

## UI 와이어프레임

### 프로젝트 등록 — JD 입력 확장
JD 입력 탭 UI (파일/Drive/텍스트 선택)

### JD 분석 결과 확인
추출된 요구조건 표시 + 확인/수정/재분석 버튼

---

## 적합도 매칭 시스템

5차원 가중치 스코어링:
| 조건 | 가중치 | 판정 |
|------|--------|------|
| 경력 범위 일치 | 25% | 범위 내 = 만점, ±2년 = 감점, 그 외 = 0 |
| 업종·키워드 매칭 | 25% | 키워드 겹침 비율 |
| 자격증 보유 | 20% | required 충족 + preferred 보너스 |
| 학력 조건 | 15% | 전공 일치, 대학 티어 |
| 연령·성별 | 15% | 필수 조건 미충족 시 부적합 |

결과: 높음(70%+) / 보통(40~70%) / 낮음(40%-)

키워드 동의어 확장 + Gap 분석 리포트 포함.

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

---

## 산출물

- `projects/services/jd_analysis.py` — JD 분석 서비스
- `projects/services/jd_prompts.py` — Gemini 프롬프트
- `projects/services/candidate_matching.py` — 적합도 매칭
- `projects/views.py` — analyze_jd, jd_results, drive_picker 뷰
- `projects/templates/projects/partials/jd_*.html` — JD 관련 템플릿
- `projects/templates/projects/partials/gap_report.html` — Gap 분석 리포트
- P03 프로젝트 등록 폼 확장 (JD 소스 선택 UI)
- migration 파일
- 테스트 파일
