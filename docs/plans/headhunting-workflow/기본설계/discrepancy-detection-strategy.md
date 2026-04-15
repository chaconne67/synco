# 이력서 Discrepancy 탐지 전략

## 1. 목표

동일 후보자의 복수 이력서 간, 또는 단일 이력서 내부에서 발생하는 시간 모순, 경력 불일치, 학력/자격 정보 변화 등을 탐지해 사람이 빠르게 검토할 수 있게 만드는 기능.

핵심 원칙은 다음과 같다.

- 추출 품질 문제와 실제 이력 불일치를 분리해서 다룬다.
- 머지된 후보자 프로필이 아니라, 가능한 한 원본 resume 단위 증거를 기준으로 판단한다.
- Rule-based 1차 스캔을 우선하고, LLM은 의심 건 요약에만 제한적으로 사용한다.

---

## 2. 현재 코드베이스 기준 현실 제약

현재 구현 상태에서 바로 전제로 삼을 수 있는 사실:

- `Candidate`에는 이미 머지된 대표 프로필이 저장된다.
- `Resume`는 후보자별 버전을 저장하지만, primary 외 `others`는 대부분 구조화 추출 결과가 없다.
- `ValidationDiagnosis`는 추출 품질 검증용이며, 무결성(discrepancy) 진단 저장소가 아니다.
- 총 경력은 이제 `Career` 구간 합산 기반의 시스템 계산값과, 이력서 추출값(`total_experience_years`)을 비교할 수 있다.

즉, 지금 즉시 구현 가능한 범위는 **Layer 2: 단일 후보자 내부 일관성 검사**다.
Cross-version 비교는 resume별 structured snapshot 저장이 먼저 필요하다.

---

## 3. 탐지 계층

### Layer 1: 내부 일관성 (지금 바로 가능)

후보자 하나의 현재 프로필 안에서 논리적 모순을 탐지한다.

비교 대상:

- 경력 기간 간 겹침
- 경력 시작/종료 역전
- 미래 날짜
- 총 경력 추출값과 실제 경력 합산값 차이
- 학력-나이 충돌
- 학력 구멍, 날짜 불완전성

탐지 신호:

- 두 경력의 기간이 겹침 → `OVERLAP`
- 시작일 > 종료일 → `DATE_ORDER`
- 현재 기준 미래 경력 날짜 존재 → `FUTURE_DATE`
- 추출 총 경력과 합산 총 경력 차이 12개월 이상 → `EXPERIENCE_MISMATCH`
- birth_year 기준 비정상 학력 시작 → `AGE_MISMATCH`
- 학력 날짜 불완전 → `INCOMPLETE_DATES`

주의:

- 경력 공백(`GAP`)은 기본적으로 경고가 아니라 참고 정보다.
- 공백은 육아, 유학, 취업 준비, 프리랜스 미기재 등 정상 사유가 많으므로 단독으로 위조 의심 신호로 승격하지 않는다.

### Layer 2: 버전 간 비교 (선행 작업 필요)

동일 후보자의 여러 resume 버전 사이에서 과거 사실이 사라졌거나 바뀌었는지 본다.

비교 대상:

- 학력 목록 삭제/변경
- 경력 목록 삭제/변경
- 자격증 삭제/변경
- 신상 정보의 비정상 변경

탐지 신호:

- 이전 버전에 있던 항목이 이후 버전에서 사라짐 → `DELETION`
- 동일 항목의 기간이 크게 바뀜 → `DATE_CHANGE`
- 동일 항목의 핵심 내용이 크게 바뀜 → `CONTENT_CHANGE`

중요:

- 이 단계는 **머지 전**에 해야 한다.
- 비교 입력은 `Candidate`가 아니라 **resume별 structured snapshot**이어야 한다.

### Layer 3: LLM 보조 해석 (선별 적용)

Rule-based 결과 중 YELLOW 이상만 LLM에 보내 맥락적 설명 가능성을 받는다.

용도:

- 위조 판정 자동화가 아니라, 검토자에게 “확인 포인트”를 요약 제공
- 겸직, 회사명 변경, 편입, 조직개편, 프리랜스 가능성 등 설명 후보 제시

LLM 출력 예시:

- 위조 가능성: high / medium / low
- 가능한 정상 설명
- 추가 확인 필요 서류 또는 질문

---

## 4. 추출 품질과 무결성 진단의 분리

현재 `ValidationDiagnosis`는 extraction validation 전용이다.

이 모델이 다루는 것:

- 필드 confidence
- 파싱 실패/경고
- hallucination 여부
- retry 필요 여부

Discrepancy는 별도 저장 구조를 둔다.

권장 모델:

```python
class DiscrepancyReport(BaseModel):
    candidate = models.ForeignKey("Candidate", on_delete=models.CASCADE)
    source_resume = models.ForeignKey("Resume", null=True, blank=True, on_delete=models.SET_NULL)
    compared_resume = models.ForeignKey("Resume", null=True, blank=True, on_delete=models.SET_NULL)
    report_type = models.CharField(max_length=20)  # self_consistency / cross_version
    integrity_score = models.FloatField()
    summary = models.TextField(blank=True)
    alerts = models.JSONField(default=list)
    llm_assessment = models.TextField(blank=True)
    scan_version = models.CharField(max_length=20, default="v1")
```

이렇게 분리해야 다음이 가능하다.

- 추출 문제와 무결성 문제를 따로 해석
- resume pair별 비교 결과 보존
- 재스캔 시 버전 추적

---

## 5. Rule-based 1차 스캔 설계

### 5.1 입력 기준

- `Candidate`
- `Career`
- `Education`
- `Certification`
- `ValidationDiagnosis`

보조 규칙:

- confidence가 낮은 필드에서 나온 신호는 severity를 낮추거나 보류한다.
- 날짜 파싱 실패는 곧바로 위조 의심이 아니라 `INCOMPLETE_DATES`로 처리한다.

### 5.2 스캐너 예시

```python
def scan_candidate(candidate) -> list[Alert]:
    alerts = []

    alerts += check_career_overlaps(candidate.careers.all())
    alerts += check_career_date_order(candidate.careers.all())
    alerts += check_future_dates(candidate.careers.all())
    alerts += check_experience_total(candidate)
    alerts += check_education_age(candidate.birth_year, candidate.educations.all())
    alerts += check_education_completeness(candidate.educations.all())

    return downgrade_low_confidence_alerts(
        alerts=alerts,
        field_scores=candidate.field_confidences or {},
    )
```

### 5.3 총 경력 정합성 기준

총 경력 비교는 다음 두 값을 사용한다.

- 시스템 계산값: `Career` 유효 구간을 병합한 실제 근무 기간 합
- 추출값: `Candidate.total_experience_years`

판정 기준:

- 차이 12개월 미만: 통과
- 차이 12~23개월: `YELLOW`
- 차이 24개월 이상: `RED`

예외:

- 계산 가능한 경력이 너무 적거나 날짜가 많이 불완전하면 `BLUE`
- 미래 날짜 보정이 들어간 경우 `FUTURE_DATE`를 별도 생성

### 5.4 공백 기간 규칙

`GAP`은 기본적으로 참고 정보다.

권장 규칙:

- 12개월 이상 공백 존재 → `BLUE`
- 병역, 학업, 해외체류, 훈련 데이터와 겹치면 suppress
- 다른 경고(`DELETION`, `DATE_CHANGE`, `EXPERIENCE_MISMATCH`)와 같이 나타날 때만 우선순위 상승 검토

---

## 6. Cross-version 비교를 위한 선행 작업

현재는 `others` resume가 구조화 추출되지 않은 경우가 많으므로, 아래 작업이 먼저 필요하다.

### 6.1 resume별 structured snapshot 저장

각 `Resume`에 대해 머지 전 정규화 결과를 저장해야 한다.

권장 방식:

```python
class ResumeSnapshot(BaseModel):
    resume = models.OneToOneField("Resume", on_delete=models.CASCADE, related_name="snapshot")
    extracted_json = models.JSONField(default=dict)
    normalized_json = models.JSONField(default=dict)
    field_scores = models.JSONField(default=dict)
    extraction_model = models.CharField(max_length=50, blank=True)
```

### 6.2 실행 순서

1. pending other resumes의 텍스트 추출
2. resume별 structured extraction
3. snapshot 저장
4. snapshot 간 diff 생성
5. 그 다음에만 candidate merge

이 순서를 지켜야 머지로 인해 원본 증거가 사라지지 않는다.

---

## 7. Alert 포맷

```json
{
  "type": "EXPERIENCE_MISMATCH",
  "severity": "YELLOW",
  "field": "total_experience_years",
  "layer": "self_consistency",
  "detail": "이력서 표기 8년과 경력 합산 6년 3개월 차이",
  "evidence": {
    "extracted": "8년",
    "computed": "6년 3개월"
  },
  "confidence_gate": {
    "field_confidence": 0.82,
    "downgraded": true
  }
}
```

severity 기준:

- `RED`: 강한 불일치, 사람이 즉시 확인 필요
- `YELLOW`: 설명 가능성 있지만 확인 필요
- `BLUE`: 참고 정보

---

## 8. UI 표시 원칙

후보자 상세 페이지에는 extraction confidence와 integrity를 분리해서 보여준다.

예시:

```text
[추출 신뢰도]
- 84%

[무결성 리포트]
- 점수: 78%
- RED 0건
- YELLOW 2건: 총 경력 불일치, 경력 기간 겹침
- BLUE 1건: 1년 이상 공백
```

현재 화면에 바로 넣기 좋은 최소 범위:

- 총 경력 불일치
- 미래 날짜 보정 여부
- 경력 날짜 불완전 제외 여부

---

## 9. 단계별 구현 계획

### Phase 1: Self-consistency 스캐너

현재 DB만으로 가능한 범위부터 구현.

- `check_career_overlaps`
- `check_career_date_order`
- `check_future_dates`
- `check_experience_total`
- `check_education_age`
- `check_education_completeness`
- `DiscrepancyReport` 저장
- 상세 페이지 표시

### Phase 2: other resume 구조화

- pending other resume 텍스트 추출
- resume별 structured extraction
- `ResumeSnapshot` 저장

### Phase 3: Cross-version diff

- snapshot pair 비교
- `DELETION`, `DATE_CHANGE`, `CONTENT_CHANGE` 생성
- resume pair별 `DiscrepancyReport` 저장

### Phase 4: LLM 보조 해석

- YELLOW 이상만 LLM에 전달
- 요약 문장과 추가 확인 포인트 생성

### Phase 5: Batch scan + 운영화

- management command
- 후보자별 최신 report 재계산
- admin/review UI 노출

---

## 10. 지금 당장 할 일

우선순위는 아래 순서가 현실적이다.

1. `DiscrepancyReport` 모델 추가
2. Self-consistency rule scanner 구현
3. 현재 상세 페이지의 총 경력 mismatch를 report로 승격
4. other resume extraction/snapshot 저장 설계
5. 그 이후 cross-version 비교 착수

지금 단계에서 “위조 탐지”를 바로 약속하기보다, 먼저 **내부 일관성 검사 + 근거 저장 + 검토 UX**를 완성하는 것이 가장 안전하다.
