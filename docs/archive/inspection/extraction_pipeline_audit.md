# 데이터 추출 파이프라인 필드 매핑 감사

**작성일:** 2026-04-05  
**갱신일:** 2026-04-05  
**발단:** 후보자 상세 페이지에서 정규 섹션과 `_etc` 기타 섹션에 동일 데이터가 중복 표시되거나, 일부 데이터가 전용 UI에 나타나지 않는 문제 발견

---

## 요약

현재 데이터 추출 파이프라인에는 세 종류의 구조 불일치가 공존한다.

1. **실제 필드 매핑 누락**
   - Step 1/Step 2 스키마가 DB 저장 스키마보다 좁아서 정보가 중간에 탈락한다.

2. **소비 경로 불일치**
   - 저장 로직은 `_etc`로 보내지만 뷰/템플릿은 레거시 JSONField를 계속 본다.

3. **프롬프트 의존 구조**
   - `_etc.type` 분류나 Step 2 필드 보존처럼, 프롬프트가 잘 따라주길 기대하는 부분이 많다.
   - 이 부분은 스키마 문구만 보강해도 “반드시 그렇게 실행된다”는 보장이 없다.

즉, 이번 이슈는 단순한 프롬프트 보강만으로 끝나는 문제가 아니라, **스키마 정의 + 후처리 + 저장 + 뷰 소비 + 호환성**을 함께 손봐야 하는 구조적 문제다.

또한 이 앱은 순수 스크립트 앱도, 순수 프롬프트 앱도 아니다.  
**언어모델의 시맨틱 판단**과 **스크립트의 구조 강제**가 함께 작동하는 hybrid 앱이므로,
"무엇을 모델에게 맡기고 무엇을 코드가 강제할지" 경계를 설계하는 것이 핵심이다.

---

## 파이프라인 구조

```text
이력서 텍스트
  ↓
Step 1: 충실 추출 (Gemini Flash)         ← STEP1_SCHEMA 기준
  ↓
Step 2: 정규화 (경력/학력 그룹)           ← CAREER_OUTPUT_SCHEMA / EDUCATION_OUTPUT_SCHEMA
  ↓
Step 3: 교차 검증 (기간 중복, 버전 비교)
  ↓
save.py → DB 모델 (Candidate, Career, Education, ...)
  ↓
views.py / template → 상세 화면 렌더링
```

---

## 앱의 목적과 성공 기준

이 앱의 목적은 단순 JSON 생성이 아니다. 다음 세 가지를 동시에 만족해야 한다.

1. **원문 사실 회수**
   - 이력서의 구조가 지저분하고 다국어/표/서술형이 섞여 있어도
     검색과 열람에 필요한 사실 데이터를 최대한 빠짐없이 회수해야 한다.

2. **검토 가능성 확보**
   - 모델이 애매한 판단을 하더라도, 사람이 나중에 근거를 추적하고 재판단할 수 있어야 한다.

3. **다운스트림 유용성**
   - 저장된 결과가 DB, 검색, 상세 UI, 검수 플로우에서 실제로 쓸 수 있어야 한다.

### 단계별 성공 기준

| 단계 | 성공 기준 |
|------|-----------|
| Step 1 | 원문 사실을 가능한 많이, 원문 보존적으로, 출처와 함께 추출했는가 |
| Step 2 | Step 1 데이터를 과도하게 잃지 않고 정규화했는가 |
| Final/save | DB와 UI에서 일관되게 소비 가능한 구조인가 |
| Review | 사람이 추적 가능한 근거와 불확실성 표시가 남는가 |

### 전체 품질 기준

이 파이프라인은 다음 기준으로 평가되어야 한다.

- **completeness**: 원문 정보가 빠지지 않았는가
- **provenance**: 어디서 왔는지 추적 가능한가
- **determinism**: downstream 코드가 안정적으로 소비 가능한가
- **recoverability**: 필요 시 Step 1 원본으로 되돌아가 재판단 가능한가
- **uncertainty visibility**: 사실과 추정이 구분되는가
- **downstream usefulness**: 검색/상세/검수에 실제로 도움이 되는가

---

## 하이브리드 앱 설계 원칙

이 앱은 script와 prompt가 혼합된 구조이므로, 설계 원칙을 명확히 두지 않으면
프롬프트가 과도한 책임을 떠안고, 결과가 흔들리기 쉽다.

### 1. 모델은 애매한 의미 판단을 담당

언어모델이 맡아야 할 영역:

- 섹션 경계 추론
- 다국어/표/서술형 텍스트에서 사실 추출
- 같은 회사/학교인지의 시맨틱 판단
- 충돌하는 기재 중 더 신뢰할 값을 고르는 판단
- 제한된 범위의 번역/요약
- 약한 수준의 불확실성 판단

### 2. 코드는 구조와 일관성을 강제

스크립트가 맡아야 할 영역:

- 스키마 shape 강제
- 날짜/전화번호/이메일 형식 정규화
- enum/type canonicalization
- Step 간 carry-forward
- 저장 구조와 UI용 구조 분리
- validator, score, retry 조건
- provenance 보존 규칙
- backward compatibility 처리

### 3. 단계별 계약을 명확히 분리

#### Step 1: 충실 추출

- 허용: 원문 사실 추출, 원문 보존, source/provenance 부착
- 금지: 의미 병합, 정렬, 추정값 생성, 후처리용 판단 강제

#### Step 2: 정규화

- 허용: 중복 병합, canonicalization, 제한적 추정, evidence/confidence 부여
- 금지: 원문에 없던 자유 창작, 근거 없는 보강

#### Final Assembly / Save

- 허용: UI 친화 shape 생성, `_etc` 분리, safe defaults
- 금지: 다시 의미 판단을 프롬프트에 위임하는 것

### 4. 프롬프트는 “잘 쓰는 것”보다 “헷갈리지 않게 쓰는 것”이 중요

좋은 프롬프트는 최소한 다음을 분명히 해야 한다.

- 이 단계의 역할
- 이번 단계의 목표
- 누락 비용과 노이즈 비용 중 무엇이 더 큰지
- 허용되는 변형과 금지되는 변형
- 불확실할 때의 기본 정책
- 추정 필드가 허용되는 조건
- 출력 형식 외의 텍스트 금지

### 5. 사실과 추정은 반드시 분리

hallucination을 줄이려면 다음 원칙이 필요하다.

- 원문에 없으면 `null` 또는 미기재
- 추정은 별도 필드에만 기록
- 추정에는 `evidence`, `confidence`를 동반
- 자유 서술 분류값은 코드에서 재정규화
- "그럴듯하게 채우는 것"보다 "보수적으로 남기는 것"을 우선

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `candidates/services/integrity/step1_extract.py` | Integrity Step 1 추출 프롬프트 + 스키마 |
| `candidates/services/integrity/step2_normalize.py` | Integrity Step 2 정규화 프롬프트 + 스키마 |
| `data_extraction/services/extraction/prompts.py` | `data_extraction` 통합 프롬프트 복제본 |
| `data_extraction/services/save.py` | 추출 결과 → DB 저장 |
| `candidates/views.py` | 후보자 상세/검토 화면 컨텍스트 구성 |
| `candidates/templates/.../candidate_detail_content.html` | 상세 화면 렌더링 |
| `candidates/models.py` | DB 모델 정의 |

---

## 1. Step 1에 반드시 있어야 하는 원문 필드 누락

Step 1은 "충실 추출" 단계이므로, 원문에 명시된 데이터는 모두 받아야 한다.

### Career

| 필드 | DB 모델 | 현재 Step 1 | 판단 |
|------|---------|-------------|------|
| `reason_left` | O | X | **추가 필요** |
| `achievements` | O | X | **추가 필요** |
| `salary` | O | X | **추가 필요** |
| `company_en` | O | X | **추가 필요** |

### Education / Language

| 필드 | DB 모델 | 현재 Step 1 | 판단 |
|------|---------|-------------|------|
| `gpa` | Education.gpa O | X | **추가 필요** |
| `level` | LanguageSkill.level O | X | **추가 필요** |

### Step 1에 넣으면 안 되는 필드

아래 필드는 원문 추출이 아니라 후속 처리 산물이므로 Step 1에 넣지 않는 것이 맞다.

| 필드 | 이유 |
|------|------|
| `inferred_capabilities` | 원문 기반이 아닌 AI 추론 |
| `order` | 정규화 후 정렬 결과 |
| `end_date_inferred` | 기간 계산/보정 결과 |
| `date_evidence` | 정규화/판단 근거 정리 결과 |
| `date_confidence` | 추정 신뢰도 |

### 영향

- Step 1에서 빠진 값은 AI가 `_etc` catch-all로 밀어 넣기 쉽다.
- 그 결과 정규 레코드와 `_etc`가 동시에 살아남아 중복 표시에 연결된다.

---

## 2. Step 2 출력 스키마가 Step 1/DB 사이를 끊고 있음

Step 2는 Step 1 원본을 정규화해 DB 저장용 구조로 넘기는 단계다.  
따라서 Step 2 출력은 최소한 DB 저장 코드가 기대하는 필드를 보존해야 한다.

### Career

| 필드 | DB 모델 | Step 1 | 현재 Step 2 | 판단 |
|------|---------|--------|-------------|------|
| `reason_left` | O | 추가 예정 | X | **추가 필요** |
| `salary` | O | 추가 예정 | X | **추가 필요** |
| `duration_text` | O | O | X | **추가 필요** |
| `end_date_inferred` | O | Step 2 산물 가능 | X | **추가 필요** |
| `date_evidence` | O | Step 2 산물 가능 | X | **추가 필요** |
| `date_confidence` | O | Step 2 산물 가능 | X | **추가 필요** |

### Education

| 필드 | DB 모델 | Step 1 | 현재 Step 2 | 판단 |
|------|---------|--------|-------------|------|
| `gpa` | O | 추가 예정 | X | **추가 필요** |
| `status` | DB 없음 | O | X | 모델 결정 전까지는 최소 보존 필요 |

### 주의

여기서 중요한 점은, **프롬프트에 필드를 추가하는 것만으로는 충분하지 않다**는 것이다.

현재 `validate_step2()`는 다음만 검증한다.

- `company` 존재
- `start_date` 존재
- 날짜 포맷
- flag reasoning 존재

즉 `reason_left`, `salary`, `duration_text`, `end_date_inferred`, `date_evidence`, `date_confidence`가 통째로 빠져도 오류로 잡히지 않는다.

**결론:** Step 2 보강은 프롬프트 수정뿐 아니라 validator 보강 또는 후처리 carry-forward가 함께 필요하다.

---

## 3. Education.status는 아직 모델 레벨 결정이 필요

현재 상태:

| 필드 | Step 1 | Step 2 | DB |
|------|--------|--------|----|
| `status` (`졸업/중퇴/수료`) | O | X | X |

이 값은 원문에 자주 명시되지만 현재 Education 모델에 저장 필드가 없다.

### 선택지

1. **Education 모델에 `status` 추가**
   - 가장 자연스러운 구조

2. **모델 추가는 미루고 원본 JSON에만 보존**
   - 최소한 `raw_extracted_json.step1`에는 남겨야 함

현재는 저장 모델이 없고 Step 2에서도 탈락하므로, 사실상 손실 또는 `_etc` 우회 저장 위험이 있다.

---

## 4. `_etc` 전략은 맞지만, `type` 자유서술에 기대면 깨질 수 있음

현재 방향성 자체는 `_etc` 통합이 더 낫다.

- 프로젝트/교육훈련/수상/특허/해외경험을 별도 추출 필드로 강제하면
  - 프롬프트 스키마가 비대해지고
  - AI가 경계 판단까지 떠안게 된다.
- 반대로 `_etc`에 `type` 태그를 두고 후단에서 분리하면 추출 단계 부담은 줄어든다.

### 하지만 현재 구현은 위험하다

지금 프롬프트는 `type`을 "한국어로 작성"하라고만 하고 있다.

실제 출력은 다음처럼 흔들릴 수 있다.

- `프로젝트`
- `주요 프로젝트`
- `수행 프로젝트`
- `교육`
- `교육훈련`
- `직무교육`
- `수상`
- `상훈`
- `해외경험`
- `해외 근무`

이 상태에서 뷰가 `type == "프로젝트"` 같은 식으로 분기하면 쉽게 누락된다.

### 결론

`B안 (_etc 유지 + 뷰에서 type별 분리)`이 맞지만, 다음이 전제되어야 한다.

1. **정규화 코드 필요**
   - `type` alias map 또는 canonicalization 함수

2. **뷰 분리 로직은 자유 텍스트에 직접 의존하면 안 됨**
   - 저장 전 정규화하거나, 뷰 직전 helper에서 정규화해야 함

3. **프롬프트만으로는 보장되지 않음**
   - `_etc.type`은 대표적인 프롬프트 의존 영역

---

## 5. 레거시 JSONField 소비 경로가 아직 살아 있음

현재 save.py는 다음 필드를 비워 둔다.

```python
awards=[], patents=[], projects=[], trainings=[], overseas_experience=[]
```

하지만 뷰/템플릿은 여전히 이 레거시 필드를 먼저 본다.

| 레거시 필드 | 실제 데이터 위치 | 현재 상태 |
|------------|------------------|----------|
| `projects` | `career_etc` | 항상 빈 배열 |
| `trainings` | `education_etc` | 항상 빈 배열 |
| `awards` | `skills_etc` | 항상 빈 배열 |
| `patents` | `skills_etc` | 항상 빈 배열 |
| `overseas_experience` | `career_etc` | 항상 빈 배열 |

### 결과

- `_etc`에는 데이터가 있는데 전용 UI 블록은 비어 있을 수 있다.
- 사용자는 “추출이 안 됐다”고 느끼지만, 실제로는 “소비 경로가 틀린” 상태다.

### 권장 방향

`A안`보다 `B안`이 적절하다.

- 레거시 필드를 되살려 저장하는 대신
- 뷰에서 `_etc`를 type별로 분리해 `projects_data`, `trainings_data`, `awards_data`, `patents_data`, `overseas_experience`를 구성하고
- 템플릿은 그 결과를 사용

단, 이 역시 `type` 정규화가 전제다.

---

## 6. 원문 추적은 DB 서브모델이 아니라 raw JSON 보존으로 해결하는 것이 실용적

기존 문서에서는 다음 필드를 "조용히 버려지는 필드"로 봤다.

| 필드 | 상태 |
|------|------|
| `total_experience_text` | 최종 저장 구조에서 손실 |
| `careers[].source_section` | Step 2 이후 손실 |
| `educations[].source_section` | 동상 |

여기서 핵심은 이 값들을 반드시 DB 컬럼으로 저장해야 한다는 뜻은 아니다.

### 더 실용적인 방향

`raw_extracted_json`에 단계별 결과를 함께 보존하면 충분하다.

```json
{
  "step1": {...},
  "step2": {...},
  "final": {...}
}
```

이렇게 하면:

- `source_section`은 감사 추적에 남고
- 최종 정규화 결과도 함께 보존되고
- 별도 DB 모델 확장은 피할 수 있다

### 단, 전환 리스크가 큼

현재 `raw_extracted_json` 소비자는 "평평한 최종 dict"를 가정한다.

- `salary_parser.normalize_salary(raw_extracted_json)`
- `backfill_candidate_details`
- 일부 테스트/관리 명령

따라서 구조를 바꾸면 이 소비자들을 동시에 업데이트해야 한다.

**결론:** 단계별 보존은 바람직하지만, 단독 변경은 위험하다. `raw_extracted_json["final"]` 표준화나 helper 함수 도입과 함께 전환해야 한다.

---

## 7. 스키마 중복은 유지보수 사고의 직접 원인

현재 동일 개념의 스키마가 여러 곳에 중복 정의되어 있다.

| 경로 | 위치 |
|------|------|
| Integrity Step 1 | `candidates/services/integrity/step1_extract.py` |
| Integrity Step 2 | `candidates/services/integrity/step2_normalize.py` |
| `data_extraction` 통합본 | `data_extraction/services/extraction/prompts.py` |
| 레거시 단일 추출 | `candidates/services/llm_extraction.py` |
| 구형 batch_extract | `batch_extract/services/request_builder.py` 경유 |

### 위험

- 한 곳만 수정하면 경로별 결과가 달라진다.
- 특히 P0 수정처럼 스키마를 건드릴 때, 중복 제거 없이 진행하면 **새로운 불일치**를 만드는 셈이 된다.

### 추가 위험: 구형 배치 경로

`batch_extract` 경로는 여전히 구형 프롬프트/응답 파서를 사용하며,  
`response_mime_type="application/json"`도 빠져 있어 구조 준수 안정성이 더 낮다.

---

## 8. 프롬프트와 코드의 역할을 분리해서 봐야 함

이번 감사에서 중요한 교훈은 다음과 같다.

### 프롬프트로 해결 가능한 것

- 모델이 어떤 필드를 반환해야 하는지 힌트 주기
- 원문 필드 범위 명시
- `_etc` 분류 원칙 설명

### 프롬프트만으로 해결되지 않는 것

- `_etc.type` 값의 표준화
- Step 2 출력 필드 누락 방지
- `raw_extracted_json` 구조 전환 후 호환성
- 경로별 스키마 일관성
- 뷰/템플릿 소비 경로 수정

즉, 아래 항목은 **프롬프트 의존이 아니라 코드 강제**가 필요하다.

1. `_etc.type` canonicalization
2. Step 2 validator/후처리 보강
3. `raw_extracted_json` accessor 정리
4. 스키마 단일화
5. 뷰에서 `_etc` 분리

---

## 9. 현재 앱에서 경계가 특히 중요한 지점

이번 감사 내용을 하이브리드 앱 관점에서 보면, 다음 지점들이 특히 중요하다.

### A. Step 1 스키마

- 모델이 무엇을 "사실 필드"로 인식할지를 결정한다.
- 여기서 빠진 필드는 `_etc`로 밀리거나 아예 누락될 수 있다.
- 따라서 Step 1 스키마는 "원문에 명시될 수 있는 값"을 빠짐없이 알려줘야 한다.

### B. Step 2 출력 스키마

- 모델이 정규화 과정에서 무엇을 "남겨야 하는지"를 결정한다.
- 여기서 빠진 필드는 save.py에 도달하기 전에 탈락한다.
- 따라서 Step 2는 DB 저장/화면 소비에서 필요한 필드를 계약 수준으로 명시해야 한다.

### C. `_etc.type`

- 모델의 자유서술에 맡기면 downstream 분기가 깨진다.
- 따라서 prompt에는 분류 원칙을 주되, 최종 canonical type은 코드가 강제해야 한다.

### D. `raw_extracted_json`

- 원문 추적과 재검토 가능성을 보장하는 핵심 저장소다.
- 따라서 최종값만 저장하지 말고 단계별 산출물을 보존하는 방향이 바람직하다.
- 단, 기존 소비자와의 호환성을 코드 레벨에서 관리해야 한다.

### E. validation / scoring

- 지금은 "필드가 아예 사라져도" 많이 놓친다.
- 따라서 validator는 단순 형식 검사뿐 아니라
  "이 단계에서 원래 남아 있어야 할 값이 비정상적으로 사라졌는가"까지 봐야 한다.

---

## 10. 원하는 결과를 더 높은 확률로 얻기 위한 실무 원칙

이 앱에서 프롬프트 품질을 높인다는 것은 문장을 멋지게 쓰는 것이 아니라,
입력과 출력 사이의 계약을 더 명확히 만드는 것이다.

### 입력단에서 모델에게 명확히 알려줘야 할 것

- 이 단계가 무엇을 하는 단계인지
- 출력이 다음 단계에서 어떻게 소비되는지
- 어떤 필드는 반드시 남겨야 하는지
- 어떤 판단은 하지 말아야 하는지
- 불확실할 때 어떤 보수적 선택을 해야 하는지

### 출력단에서 코드가 반드시 검사해야 할 것

- 구조가 유효한가
- 필수 필드가 남아 있는가
- 추정 필드가 근거 없이 채워지지 않았는가
- 자유서술 enum이 canonical type으로 정규화되는가
- UI/DB가 기대하는 shape과 일치하는가

### 재시도와 개선의 기준

모델 결과가 기대와 다를 때는 단순 재시도보다, 아래 질문으로 원인을 분해해야 한다.

1. 스키마에 필드가 없어서 못 낸 것인가
2. 프롬프트에서 역할/금지사항이 모호한가
3. validator가 놓치고 있는가
4. 후처리/저장에서 버리고 있는가
5. 뷰가 잘못 소비하고 있는가

이 분해가 되어야 프롬프트 수정이 효과적인지, 코드 수정이 필요한지 판단할 수 있다.

---

## 수정 우선순위

### P0 — 구조 먼저 고정

1. **스키마 단일화**
   - Step 1/Step 2/레거시/`data_extraction` 복제본을 한 소스로 통합
   - 이걸 먼저 해야 이후 수정이 한 곳에서만 일어남

2. **Step 1 스키마 보강**
   - `reason_left`
   - `achievements`
   - `salary`
   - `company_en`
   - `gpa`
   - `level`

3. **Step 2 출력 스키마 보강**
   - `reason_left`
   - `salary`
   - `duration_text`
   - `end_date_inferred`
   - `date_evidence`
   - `date_confidence`
   - 필요 시 `gpa`

4. **레거시 JSONField read-path 제거**
   - save.py는 `_etc` 유지
   - views.py에서 `_etc`를 type별로 분리
   - 템플릿은 분리된 결과 사용

### P1 — 프롬프트 의존도 낮추기

5. **`_etc.type` 정규화 코드 추가**
   - alias map / canonical type helper

6. **Step 2 validator 보강**
   - 추가된 필드가 불합리하게 탈락하지 않도록 검증

7. **`raw_extracted_json` 단계별 보존**
   - `step1`, `step2`, `final`
   - 단, 소비자 호환성 수정과 함께 적용

### P2 — 모델/레거시 정리

8. **Education.status 모델 반영 여부 결정**
9. **실제로 더 이상 쓰지 않는 레거시 JSONField 정리**
10. **구형 `batch_extract` 경로 정리 또는 제거**

---

## 권장 실행 순서

1. 스키마 단일화
2. Step 1 명시 필드 보강
3. Step 2 출력 보강
4. 뷰에서 `_etc` type 분리 + type canonicalization
5. `raw_extracted_json` 단계별 보존 + 기존 소비자 동시 수정
6. 마지막에 레거시 모델 필드 정리 여부 판단

이 순서는 다음 이유로 안전하다.

- 먼저 단일 소스를 만들어야 P0 수정이 다시 중복되지 않는다.
- `_etc` 소비 경로를 먼저 바로잡아야 사용자 체감 문제가 사라진다.
- `raw_extracted_json` 구조 변경은 호환성 영향이 커서 뒤로 미루는 편이 안전하다.

---

## 부록: 전체 필드 매핑 현황

### Career

| DB 필드 | Step 1 | Step 2 출력 | 레거시 | save.py | 비고 |
|---------|--------|-------------|--------|---------|------|
| company | O | O | O | O | 정상 |
| company_en | X | X | O | O | Step 1 추가 필요 |
| position | O | O | O | O | 정상 |
| department | O | O | O | O | 정상 |
| start_date | O | O | O | O | 정상 |
| end_date | O | O | O | O | 정상 |
| duration_text | O | X | O | O | Step 2 보존 필요 |
| end_date_inferred | X | X | O | O | Step 2 산물로 보존 필요 |
| date_evidence | X | X | O | O | Step 2 산물로 보존 필요 |
| date_confidence | X | X | O | O | Step 2 산물로 보존 필요 |
| is_current | O | O | O | O | 정상 |
| duties | O | O | O | O | 정상 |
| inferred_capabilities | X | X | O | O | Step 1 제외가 맞음 |
| achievements | X | O | O | O | Step 1 추가 필요 |
| reason_left | X | X | X | O | Step 1/2 추가 필요 |
| salary | X | X | X | O | Step 1/2 추가 필요 |
| order | X | O | O | O | Step 1 제외가 맞음 |

### Education

| DB 필드 | Step 1 | Step 2 출력 | 레거시 | save.py | 비고 |
|---------|--------|-------------|--------|---------|------|
| institution | O | O | O | O | 정상 |
| degree | O | O | O | O | 정상 |
| major | O | O | O | O | 정상 |
| gpa | X | X | O | O | Step 1/2 보강 필요 |
| start_year | O | O | O | O | 정상 |
| end_year | O | O | O | O | 정상 |
| is_abroad | O | O | O | O | 정상 |
| status | O | X | X | DB 없음 | 모델 결정 필요 |

### LanguageSkill

| DB 필드 | Step 1 | 레거시 | save.py | 비고 |
|---------|--------|--------|---------|------|
| language | O | O | O | 정상 |
| test_name | O | O | O | 정상 |
| score | O | O | O | 정상 |
| level | X | O | O | Step 1 보강 필요 |

### Certification

| DB 필드 | Step 1 | 레거시 | save.py |
|---------|--------|--------|---------|
| name | O | O | O |
| issuer | O | O | O |
| acquired_date | O | O | O |

(모든 필드 매핑 정상)
