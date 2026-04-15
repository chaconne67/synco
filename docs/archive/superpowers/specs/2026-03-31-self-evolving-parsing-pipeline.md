# Self-Evolving Parsing Pipeline Design Spec

**Date:** 2026-03-31
**Status:** Approved
**Priority:** Quality-first (cost secondary, time-aware)

---

## Problem

현재 파싱 파이프라인은 정적(static)이다. LLM 프롬프트가 고정되어 있고, 사람이 교정한 데이터가 다음 파싱에 반영되지 않는다. 같은 형식의 이력서를 넣으면 같은 실수를 반복한다.

김홍안 케이스 (신뢰도 0.55):
- 원인 1: 텍스트 추출기가 VML 텍스트박스를 무시하여 회사명+날짜 전부 누락
- 원인 2: LLM이 누락된 데이터에 대해 경고 없이 빈 값으로 저장
- 원인 3: 검증 시스템이 "왜" 신뢰도가 낮은지 원인을 분류하지 못함

## Solution

3단계 교차 검증 + 패턴 축적 자동 개선 루프.

### Architecture

```
이력서 파일
  ↓
[1단계] 텍스트 추출 (paragraphs + tables + textboxes + LibreOffice fallback)
  ↓
[2단계] Claude 파싱 (구조화 추출, few-shot 예시 동적 삽입)
  ↓
[3단계] Codex CLI 교차 검증 (원본 텍스트 vs 추출 결과)
  ↓
  ├── 통과 (score >= 0.85) → 저장
  └── 실패 → 원인 분류 (root_cause)
        ├── text_extraction → LibreOffice 재추출 → 2단계부터 재시도 (1회)
        ├── llm_parsing → 진단+few-shot 보강 → 2단계 재시도 (2회까지)
        └── ambiguous_source → 사람 리뷰 큐
  ↓
[4단계] 패턴 축적
  ├── 확실한 패턴 → 규칙 엔진 (extraction_rules.json)
  └── 애매한 패턴 → few-shot 예시 DB (ParseExample 모델)
```

### Stage 3: Codex CLI Cross-Validation

**Input to Codex:**
- 원본 텍스트 전문
- Claude 추출 JSON
- 파일명 메타데이터

**Codex Output Schema:**
```json
{
  "verdict": "pass | fail",
  "issues": [
    {
      "field": "careers[0].start_date",
      "type": "missing | incorrect | hallucinated",
      "evidence": "원본에 'Dec. 2016 – May 2025' 존재하나 추출 결과에 없음",
      "root_cause": "text_extraction | llm_parsing | ambiguous_source",
      "severity": "critical | warning",
      "suggested_value": "Dec. 2016"
    }
  ],
  "field_scores": {"name": 1.0, "careers": 0.3, "educations": 0.9, ...},
  "overall_score": 0.55
}
```

**Root Cause Classification:**
- `text_extraction`: 원본 텍스트에 해당 정보가 아예 없음 (추출기 문제)
- `llm_parsing`: 원본 텍스트에 정보가 있는데 LLM이 놓침 (프롬프트/모델 문제)
- `ambiguous_source`: 원본 자체가 모호하거나 정보 부족 (이력서 문제)

### Stage 4: Pattern Accumulation

**Rule Engine** (`candidates/services/extraction_rules.json`):
```json
[
  {
    "id": "vml_textbox_priority",
    "trigger": "docx 파일에 VML 텍스트박스 존재",
    "action": "텍스트박스 내용을 본문과 병합하여 추출",
    "stage": "text_extraction",
    "source_case": "김홍안 2026-03-31",
    "confidence": 1.0
  }
]
```
확실한 패턴을 코드/로직에 반영하는 구조화된 규칙 저장소.

**Few-shot Example DB** (`ParseExample` model):
- `category`: 이력서 카테고리 (Plant, HR, etc.)
- `resume_pattern`: 이력서 형식 설명 ("영문+국문 혼합, 텍스트박스 헤더")
- `input_excerpt`: 원본 텍스트 발췌 (토큰 절약을 위해 500자 이내)
- `correct_output`: 교정된 JSON 발췌
- `source_case`: 출처 (후보자명 + 날짜)

파싱 시 같은 카테고리의 예시를 최대 3개 프롬프트에 동적 삽입.

### Retry Strategy

| root_cause | 자동 재시도 | 방법 | 최대 횟수 |
|------------|-----------|------|----------|
| text_extraction | O | LibreOffice 변환 재추출 → 재파싱 | 1 |
| llm_parsing | O | Codex 진단 + few-shot을 프롬프트에 추가 → 재파싱 | 2 |
| ambiguous_source | X | 사람 리뷰 큐에 진단 결과와 함께 등록 | 0 |

전체 최대 재시도: 3회. 3회 후에도 검증 실패 시 사람 리뷰.

### Human Review Feedback Loop

사람이 교정 시:
1. 교정 전후 diff → `ExtractionLog`에 저장 (기존)
2. 교정 내용 분석 → 규칙 후보 또는 few-shot 예시 후보 자동 생성
3. 승인 시 규칙 엔진 또는 `ParseExample`에 추가

### Data Models

**ParseExample (신규):**
```python
class ParseExample(BaseModel):
    category = models.CharField(max_length=50)
    resume_pattern = models.CharField(max_length=200)
    input_excerpt = models.TextField()
    correct_output = models.JSONField()
    source_candidate = models.ForeignKey(Candidate, null=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)
```

**ValidationDiagnosis (신규):**
```python
class ValidationDiagnosis(BaseModel):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE)
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE)
    attempt_number = models.PositiveIntegerField(default=1)
    verdict = models.CharField(max_length=10)  # pass/fail
    overall_score = models.FloatField()
    issues = models.JSONField(default=list)
    field_scores = models.JSONField(default=dict)
    retry_action = models.CharField(max_length=30, blank=True)  # re_extract/re_parse/human_review
```

### Quality Metrics

파싱 완료 후 대시보드 또는 로그로 추적:
- 1차 통과율 (재시도 없이 통과한 비율)
- 재시도 후 통과율
- 카테고리별 평균 신뢰도
- 가장 빈번한 실패 패턴 Top 5
- few-shot 예시 적용 전후 신뢰도 변화

### Constraints

- Codex CLI 호출 시 타임아웃: 120초
- few-shot 예시는 카테고리당 최대 3개 (프롬프트 토큰 관리)
- 재시도 전체 3회 이내 (시간 제한 고려)
- 규칙 엔진은 JSON 파일 기반 (DB 불필요, 코드 리뷰 가능)
