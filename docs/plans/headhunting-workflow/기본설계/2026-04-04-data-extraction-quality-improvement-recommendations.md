# data_extraction 품질 및 성능 개선 권고안

**일자:** 2026-04-05  
**대상:** `data_extraction` 앱  
**목적:** 현재 코드 상태를 다시 반영해, 이미 반영된 개선과 아직 남은 개선을 구분하고 우선순위를 재정렬한다.  
**전제:** 종이 문서는 없고, 주요 입력은 한글 이력서이며, 현재 비용 구조는 낮다. 따라서 이번 권고안은 `토큰 절감 자체`보다 `정확도`, `정합성`, `운영 안정성`, `검수 효율` 개선을 우선한다.

---

## 1. 현재 상태 요약

현재 `data_extraction` 앱은 초기 버전과 비교해 꽤 많이 정리되어 있다.

- 추출 진입점은 `data_extraction/services/pipeline.py`
- 기본 추출은 `data_extraction/services/extraction/gemini.py`
- 무결성 경로는 `data_extraction/services/extraction/integrity.py`
- 규칙 검증은 `data_extraction/services/validation.py`
- 저장은 `data_extraction/services/save.py`
- 배치 준비/요청/적재는 `data_extraction/services/batch/*.py`

이전 점검 대비 이미 좋아진 점이 분명하다.

- `skills`, `personal_etc`, `education_etc`, `career_etc`, `skills_etc`가 프롬프트/저장 경로에 반영되어 있다.
- validation은 단순 필드 평균이 아니라 `인적사항/학력/경력/능력` 카테고리 점수 기반으로 계산된다.
- 저장 단계에서 `resume_reference_date_evidence`, `date_evidence`, `date_confidence`, integrity alerts merge가 반영되어 있다.
- 저장 단계는 기존 후보자 재사용을 위한 `build_candidate_comparison_context()`를 사용한다.

즉, 이 문서는 더 이상 “무에서 설계” 문서가 아니라, `현재 구현을 기준으로 남은 품질 개선 과제`를 정리하는 문서다.

---

## 2. 현재 코드에서 이미 반영된 개선

## A. 스키마 확장과 저장 정책 정리가 이미 진행됨

아래 항목은 이미 구현되어 있다.

- `skills`, `*_etc` 필드가 프롬프트에 포함됨: `data_extraction/services/extraction/prompts.py`
- `skills`와 `*_etc`가 저장됨: `data_extraction/services/save.py`
- legacy JSON 필드 일부는 비우고 새 `*_etc`로 이관하는 정책이 적용됨: `data_extraction/services/save.py`

의미:

- “원본 이력서에 있는 정보를 어디엔가 보존해야 한다”는 방향은 이미 코드에 반영되었다.
- 따라서 이제 남은 일은 스키마 추가가 아니라 `이 필드들의 추출 품질과 검수 기준을 높이는 것`이다.

## B. validation이 카테고리 점수 기반으로 바뀜

`data_extraction/services/validation.py`는 현재 다음 구조를 가진다.

- 개별 field score 계산
- `인적사항/학력/경력/능력` 카테고리 점수 계산
- 카테고리 평균 + issue penalty로 `validation_status` 산출

이전 문서에서 “카테고리 점수 기반으로 바꾸자”라고 적어둔 내용은 이미 상당 부분 반영되었다.

다만 아직 부족한 점은 남아 있다.

- `critical field gate`가 없다.
- `rule_code`가 없다.
- `needs_review`로 가는 이유를 구조적으로 분석하기 어렵다.

즉, 현 상태는 “단순 존재 점수”보다 좋아졌지만, 아직 `핵심 필드 우선 라우팅` 수준까지는 아니다.

## C. 근거 데이터 저장이 부분적으로 반영됨

현재 저장 경로에는 이미 다음이 있다.

- `resume_reference_date_source`
- `resume_reference_date_evidence`
- 경력별 `date_evidence`
- 경력별 `date_confidence`
- integrity alert의 `evidence`, `reasoning`

이전 문서의 “근거 데이터 저장 강화”는 일부 완료된 상태다.  
남은 과제는 `핵심 필드 전반`으로 확장하는 것이다.

## D. integrity 리포트와 rule-based 리포트는 단일 리포트로 병합됨

`data_extraction/services/save.py`는 integrity alerts와 rule-based discrepancy alerts를 합쳐 단일 `DiscrepancyReport`를 만든다.

이건 이전 점검에서 지적됐던 “integrity 결과가 뒤 리포트에 묻히는 문제”를 줄이는 방향의 개선이다.

---

## 3. 현재 코드 기준 핵심 한계

## A. 입력 포맷 커버리지는 여전히 좁다

현재 상태:

- `data_extraction/services/drive.py`는 실제 수집을 `.doc` / `.docx` MIME에 한정한다.
- `data_extraction/services/text.py`도 실제 텍스트 추출은 `.doc`, `.docx`만 지원한다.
- 반면 `data_extraction/services/filename.py`는 `.pdf`, `.hwp` 확장자까지 알고 있다.

즉, 파일명 파서와 실제 추출 파이프라인의 커버리지가 어긋나 있다.

영향:

- PDF/HWP 파일은 그룹핑/파일명 파싱 관점에서는 고려되지만, 실제 본문 추출 경로에는 올라오지 못한다.
- “지원하는 것처럼 보이지만 실제로는 수집되지 않는 포맷”이 존재한다.

이 항목은 현재도 높은 우선순위다.

## B. Gemini 출력은 아직 자유 JSON 파싱 방식이다

현재 `data_extraction/services/extraction/gemini.py`와 `data_extraction/services/extraction/integrity.py`는 모두:

- 일반 텍스트 응답 수신
- fenced code block 제거
- `json.loads()` 수동 파싱

방식을 쓴다.

배치 경로도 동일하다.

- 요청 생성: `data_extraction/services/batch/request_builder.py`
- 결과 파싱: `data_extraction/services/batch/ingest.py`

의미:

- structured output이 아직 도입되지 않았다.
- JSON 파싱 실패, fence 포함, key 누락 같은 문제는 여전히 남아 있다.

이 항목은 지금도 `P0`다.

## C. 짧거나 깨진 텍스트를 막는 품질 게이트가 아직 없다

현재 `data_extraction/services/batch/prepare.py`는 `raw_text.strip()`만 확인한다.

즉:

- 문자 수가 거의 없는 문서
- 깨진 텍스트
- 의미 없는 헤더만 남은 문서

도 빈 문자열만 아니면 LLM에 들어갈 수 있다.

실제 배치 샘플에도 극단적으로 짧은 텍스트가 섞여 있었다.

이 문제는 비용보다 품질 리스크가 더 크다.

## D. validation이 좋아졌지만 아직 `critical field gate`는 없다

현재 validation은 카테고리 점수 기반이지만, 아래처럼 강제 게이트는 없다.

- 이름 미존재면 무조건 review
- 이메일/전화 중 하나라도 형식 이상이면 auto_confirmed 금지
- 현재 회사/직위/경력 날짜 불확실 시 무조건 review

현재 방식은 평균 기반이라, 핵심 필드 하나가 약해도 다른 점수가 보완할 수 있다.

실무 운영에서는 이게 위험하다.

## E. 비용/토큰/실패 유형 관측성이 아직 부족하다

현재 `GeminiBatchItem.metadata`에 토큰 사용량이 자동 저장되지 않는다.

아직 없는 것:

- `prompt_token_count`
- `candidate_token_count`
- `total_token_count`
- `response_chars`
- `raw_text_chars`
- `error_type`

따라서 다음 질문에 답하기 어렵다.

- 어떤 폴더가 비싼가
- 어떤 템플릿이 실패가 많은가
- 어떤 문서군이 review를 많이 유발하는가

## F. 프롬프트가 길고 반복적이다

현재 `data_extraction/services/extraction/prompts.py`는 다음이 모두 포함된 긴 형태다.

- 장문의 규칙
- 긴 JSON 스키마
- skills 규칙
- etc 규칙
- 번역 규칙

이 방식은 설명력은 좋지만 다음 비용이 있다.

- 입력 토큰 증가
- 긴 문서에서 context 여유 감소
- batch payload 크기 증가

다만 현재 비용 구조가 낮기 때문에, 이건 “비용 절감”보다 `출력 안정성` 관점에서 다뤄야 한다.

## G. 현재 실제 LLM 호출 수는 경로별로 다르다

이 항목은 비용 문서화에 중요하다.

### 기본/배치 경로

- 추출: 1회
- 검증: 코드 기반

즉, 현재 `data_extraction` 기본 batch 경로는 `문서당 1회 LLM`이다.

### integrity 경로

보통 아래 호출이 발생한다.

1. Step 1 faithful extraction
2. Step 1 warning 시 재추출 가능
3. career normalization
4. career normalization retry 가능
5. education normalization

즉, integrity 경로는 문서당 `3~5회`까지 갈 수 있다.

따라서 비용 문서화는 반드시 경로별로 분리해야 한다.

---

## 4. 비용 관련 현재 기준 정리

남아 있는 batch request 샘플 기준 실측치는 다음과 같다.

- 기본 추출 1회 기준:
  - 평균 입력 약 `3,281 tokens / 문서`
  - 평균 출력 약 `1,344 tokens / 문서`
  - 20만건 약 `$284`

여기서 `추출 + 품질용 LLM 검증` 2회 구조를 가정하면:

- 동일 규모 2회: 20만건 약 `$567`
- 좀 더 현실적인 `검증 프롬프트는 작고 출력도 짧다` 가정: 20만건 약 `$420~$460`

즉, 현재 문서에 비용을 적을 때는 아래처럼 써야 정확하다.

- `기본 batch 경로`: 약 `$300 전후`
- `추출 + LLM 검증 2회`: 약 `$420~$570`
- `integrity 3~5회`: 그보다 더 높음

이 문서의 남은 개선안은 이 비용 구조를 전제로 판단해야 한다.

---

## 5. 현재 기준 우선순위

## P0. Gemini Structured Output 도입

**상태:** 아직 미구현  
**이유:** 현재 가장 직접적으로 JSON 품질을 올릴 수 있는 항목

### 수정 대상

- `data_extraction/services/extraction/gemini.py`
- `data_extraction/services/extraction/integrity.py`
- `data_extraction/services/batch/request_builder.py`
- `data_extraction/services/batch/ingest.py`

### 권장 방향

- `response_mime_type="application/json"`
- `response_json_schema=...`

를 사용해 추출과 정규화 응답을 스키마 강제형으로 바꾼다.

### 기대 효과

- JSON 파싱 실패 감소
- fenced code block 후처리 제거 가능
- batch/realtime 경로 정합성 향상

## P0. 텍스트 품질 게이트 도입

**상태:** 아직 미구현  
**이유:** 짧은 텍스트와 깨진 텍스트가 LLM으로 넘어가는 것을 막아야 함

### 수정 대상

- `data_extraction/services/text.py`
- `data_extraction/services/batch/prepare.py`
- `data_extraction/services/pipeline.py`
- `data_extraction/management/commands/extract.py`
- `data_extraction/services/save.py`

### 권장 방향

`extract_text()` 이후 아래 분류를 추가한다.

- `ok`
- `too_short`
- `garbled_text`
- `unsupported_format`

경로별 라우팅은 분리해서 설계해야 한다.

- realtime 경로:
  - `too_short`, `garbled_text`는 `TEXT_ONLY` 또는 `FAILED` Resume로 저장하고 LLM 호출을 생략
- batch prepare 경로:
  - 아직 Resume를 만들지 않으므로 즉시 `TEXT_ONLY/FAILED` Resume를 만들지 말고
  - `GeminiBatchItem.status=FAILED`
  - `GeminiBatchItem.error_message`
  - `GeminiBatchJob.metadata["prepare_failures"]`
  - 필요 시 `GeminiBatchItem.metadata["error_type"]`
  로 남긴다

즉, batch prepare에서는 `Resume.processing_status`가 아니라 `batch item 수준 실패`로 기록하는 쪽이 더 자연스럽다.

## P0. critical field gate 추가

**상태:** 부분 반영, 아직 미완성  
**이유:** 카테고리 평균만으로는 핵심 필드 위험을 충분히 막지 못함

### 수정 대상

- `data_extraction/services/validation.py`
- `data_extraction/services/pipeline.py`
- `data_extraction/services/save.py`
- `data_extraction/services/batch/ingest.py`
- 필요 시 공통 판정 헬퍼 신규 추가

예:

- `data_extraction/services/decision.py`
- `build_diagnosis_from_validation()`
- `build_validation_status_from_diagnosis()`

### 권장 방향

아래 필드는 평균 점수와 별도로 게이트한다.

- `name`
- `email`
- `phone`
- `current_company`
- `current_position`
- `careers`

예시:

- `name == 0.0` 이면 무조건 `failed`
- `email < 1.0` 또는 `phone < 1.0`이면 자동 통과 금지
- 경력 날짜 역전/낮은 `date_confidence`가 있으면 `needs_review`

가장 중요한 점은 `판정 기준을 한 곳으로 모으는 것`이다.

현재는 경로별로 판정이 갈라져 있다.

- legacy realtime 경로는 `validate_extraction()` 후 다시 `confidence_score >= 0.85`로 verdict를 만든다
- batch ingest도 같은 방식으로 verdict를 다시 계산한다
- integrity 경로는 `validate_extraction()` 대신 별도 diagnosis를 만든다
- save 단계는 다시 `diagnosis`로부터 `validation_status`를 파생한다

따라서 critical field gate를 넣을 때는 아래 중 하나가 필요하다.

1. `validate_extraction()`이 최종 `verdict`, `validation_status`, `rule_codes`까지 반환하고, legacy/batch가 이를 그대로 사용하도록 통일
2. integrity/legacy/batch가 모두 공통 `decision builder`를 호출하도록 통일

문서대로 구현할 때도 `validation.py`, `pipeline.py`, `save.py`만 수정해서는 부족하다.  
반드시 `batch/ingest.py`와 integrity diagnosis 생성 경로도 함께 바꿔야 한다.

## P1. batch 관측성 강화

**상태:** 아직 미구현  
**이유:** 비용/실패 분석을 위해 반드시 필요

### 수정 대상

- `batch_extract/models.py`
- `data_extraction/services/batch/ingest.py`
- `data_extraction/services/batch/prepare.py`
- `data_extraction/management/commands/extract.py`
- `data_extraction/services/save.py`

### 권장 방향

`GeminiBatchItem.metadata`에 저장:

- `prompt_token_count`
- `candidate_token_count`
- `total_token_count`
- `response_chars`
- `raw_text_chars`
- `error_type`

또한 `ValidationDiagnosis.issues`와 별도로 machine-friendly한 `rule_code`를 도입하는 것이 좋다.

이 항목은 ingest만으로 끝나지 않는다. 관측 지점을 경로별로 나눠야 한다.

- batch prepare 실패:
  - `GeminiBatchItem.metadata.error_type`
  - `GeminiBatchJob.metadata.prepare_failures`
- batch ingest 실패:
  - `GeminiBatchItem.metadata.prompt_token_count`
  - `GeminiBatchItem.metadata.candidate_token_count`
  - `GeminiBatchItem.metadata.total_token_count`
  - `GeminiBatchItem.metadata.error_type`
- realtime / integrity:
  - `ValidationDiagnosis.issues`
  - `ValidationDiagnosis.retry_action`
  - 필요 시 `ValidationDiagnosis` 또는 별도 로그 구조에 `error_type`, `rule_codes`, `raw_text_chars` 추가

목표는 “배치 결과만 잘 보이는 것”이 아니라 `prepare / ingest / realtime / integrity` 전체에서 실패와 review 원인을 비교 가능하게 만드는 것이다.

## P1. Drive MIME 확장과 다운로드 전략 분리

**상태:** 아직 미구현  
**이유:** filename 파서와 실제 추출 커버리지를 맞춰야 함

### 수정 대상

- `data_extraction/services/drive.py`
- `data_extraction/services/text.py`
- `data_extraction/services/batch/prepare.py`
- `data_extraction/management/commands/extract.py`

### 권장 방향

- 수집 MIME 확장은 범위를 명확히 정해야 한다.
- 최소 범위: PDF, Google Docs
- 선택 범위: HWP
- `mime_type -> extract strategy` 분기
- 장기적으로 Google Drive changes API 기반 증분 동기화

현재는 `filename.py`가 `.pdf`, `.hwp`를 알고 있어도 실제 수집/본문 추출은 따라가지 못한다.

여기서 HWP는 문서에서 명시적으로 선택해야 한다.

- `HWP를 지원 범위에 포함할 경우`
  - filename parser만이 아니라 Drive 수집, 텍스트 추출, 테스트까지 같이 확장
- `HWP를 당장 제외할 경우`
  - 문서에 “filename parser의 확장자 인식일 뿐, 실제 추출 지원 범위는 아님”이라고 명시
  - 필요하면 `filename.py`의 `_EXTENSIONS`와 실제 지원 범위를 정리

즉, 현재 문서에는 `PDF, Google Docs, HWP 중 어디까지 1차 범위로 볼지`를 명확히 써야 한다.  
현 시점 권고는 `PDF와 Google Docs를 P1 최소 범위`, `HWP는 별도 결정 항목`으로 두는 것이다.

## P1. 프롬프트 슬림화

**상태:** 아직 미구현  
**이유:** 이미 스키마가 커졌고 설명도 많아졌기 때문에 유지보수와 안정성 관점에서 필요

### 수정 대상

- `data_extraction/services/extraction/prompts.py`
- `data_extraction/services/extraction/gemini.py`
- `data_extraction/services/batch/request_builder.py`

### 권장 방향

- 긴 JSON 스키마와 장문 규칙을 매 호출 본문에 직접 넣는 방식을 줄인다.
- structured output 도입 후에는 prompt를 `원칙 중심`으로 줄인다.

## P2. 템플릿/문서 유형 classifier 추가

**상태:** 아직 미구현  
**이유:** 표 중심 문서, 국영문 혼합 문서, 짧은 문서의 실패 패턴을 줄이기 위해 유효

### 수정 대상

- `data_extraction/services/pipeline.py`
- `data_extraction/services/extraction/prompts.py`
- `data_extraction/services/batch/request_builder.py`

### 권장 방향

LLM classifier가 아니라 lightweight rule classifier부터 시작한다.

- `mixed_ko_en`
- `table_heavy`
- `sparse_short`
- `career_heavy`

유형별로 prompt, max tokens, validation strictness를 다르게 적용한다.

## P2. 근거 데이터 저장 확장

**상태:** 일부 반영, 아직 미완성  
**이유:** 현재는 날짜 계열 중심이며 핵심 필드 전반의 증거 저장은 부족함

### 수정 대상

- `data_extraction/services/extraction/prompts.py`
- `data_extraction/services/save.py`
- 필요 시 모델/JSON 구조

### 권장 방향

핵심 필드에 대해 아래 구조를 추가 저장한다.

```json
{
  "field": "current_company",
  "value": "삼성전자",
  "evidence": "2022.03 ~ 현재 / 삼성전자 / 반도체사업부",
  "source_section": "경력사항"
}
```

---

## 6. 지금 단계에서 하지 않아도 되는 것

## A. 전문 파서 전면 교체

현재 비용 구조상 전면 교체는 우선순위가 아니다.

- 기본 batch 경로는 이미 저비용
- 지금 더 급한 건 JSON 안정성, 입력 품질 게이트, 관측성

전문 파서는 특정 폴더/직군 PoC로만 제한하는 것이 맞다.

## B. OCR 중심 투자

종이 문서가 없으므로 OCR은 현재 우선순위가 낮다.

더 급한 건:

- MIME 커버리지
- structured output
- validation gate
- batch observability

---

## 7. 성공 지표

현재 코드 상태를 기준으로 보면 아래 지표가 핵심이다.

- JSON 파싱 실패율
- 짧은/깨진 텍스트 차단율
- `auto_confirmed` 비율
- `needs_review` 비율
- 핵심 필드 오류율
- 문서당 평균 입력 토큰
- 문서당 평균 출력 토큰
- 문서 유형별 실패율
- 폴더별 실패율
- batch item별 `error_type` 분포

권장 대시보드 축:

- `folder`
- `mime_type`
- `validation_status`
- `error_type`
- `model_name`
- `schema_version`
- `integrity_mode`

---

## 8. 최종 권고

현재 `data_extraction`은 “기초 구조를 세우는 단계”는 이미 지나갔다.  
지금은 `출력 형식 강제`, `핵심 필드 우선 검수`, `입력 품질 게이트`, `비용/실패 관측성`을 붙여서 운영 품질을 끌어올릴 단계다.

가장 먼저 할 일은 다음 네 가지다.

1. Gemini structured output 도입
2. 텍스트 품질 게이트 추가
3. critical field gate 추가
4. batch 토큰/실패 유형 메타데이터 저장

이 네 가지가 들어가면, 지금 이미 구현된 `skills/ETC 확장`, `카테고리 점수 validation`, `integrity merge`, `후보자 재사용 저장`의 가치가 훨씬 더 커진다.

---

## 9. 구현 체크리스트

아래 체크리스트는 `바로 구현 이슈로 쪼갤 수 있는 단위` 기준으로 정리했다.  
권장 순서는 `공통 판정 기준 정리 -> structured output -> 텍스트 품질 게이트 -> 관측성 -> MIME 확장`이다.

## Phase 0. 공통 준비

- [ ] 현재 경로별 판정/실패/저장 흐름을 짧은 설계 메모로 고정한다.
  - 대상: `data_extraction/services/pipeline.py`, `data_extraction/services/batch/ingest.py`, `data_extraction/services/save.py`, `data_extraction/services/extraction/integrity.py`
  - 완료 기준: legacy / batch / integrity 각각의 `입력 -> 추출 -> 판정 -> 저장` 흐름이 1페이지 이내로 정리되어 구현 중 기준 문서로 쓸 수 있다.

- [ ] 테스트 골격을 먼저 만든다.
  - 대상: `tests/test_de_pipeline.py`, `tests/test_de_batch.py`, 신규 `tests/test_de_text_quality.py`, 신규 `tests/test_de_decision.py`
  - 완료 기준: 이후 작업에서 회귀를 잡을 최소 테스트 파일이 준비되어 있다.

## Phase 1. 공통 판정 헬퍼 도입

- [ ] 경로 공통 판정 헬퍼를 추가한다.
  - 대상: 신규 `data_extraction/services/decision.py`
  - 작업:
    - `build_diagnosis_from_validation()`
    - `build_validation_status_from_diagnosis()`
    - 필요 시 `apply_critical_field_gates()`
  - 완료 기준: legacy / batch / integrity / save가 같은 verdict, same score interpretation, same validation_status를 공유한다.

- [ ] legacy 경로가 공통 판정 헬퍼를 사용하도록 바꾼다.
  - 대상: `data_extraction/services/pipeline.py`
  - 완료 기준: `confidence_score >= 0.85` 직접 비교로 verdict를 만드는 코드가 제거된다.

- [ ] batch ingest가 공통 판정 헬퍼를 사용하도록 바꾼다.
  - 대상: `data_extraction/services/batch/ingest.py`
  - 완료 기준: batch ingest도 legacy와 같은 verdict / retry_action / validation_status를 사용한다.

- [ ] save 단계의 validation_status 파생을 공통 기준으로 통일한다.
  - 대상: `data_extraction/services/save.py`
  - 완료 기준: save 단계가 자체 규칙으로 status를 다시 덮어쓰지 않는다.

- [ ] integrity 경로의 diagnosis 생성도 공통 기준과 맞춘다.
  - 대상: `data_extraction/services/pipeline.py`, `data_extraction/services/extraction/integrity.py`, `data_extraction/services/decision.py`
  - 완료 기준: integrity flags 기반 점수/상태와 공통 validation status 체계가 충돌하지 않는다.

## Phase 2. Gemini Structured Output 도입

- [ ] legacy extraction을 structured output으로 전환한다.
  - 대상: `data_extraction/services/extraction/gemini.py`
  - 작업:
    - `response_mime_type="application/json"`
    - `response_json_schema=...`
    - fence 제거, 수동 `json.loads()` 제거
  - 완료 기준: `response.text` 후처리 없이 dict 응답을 안정적으로 얻는다.

- [ ] integrity Step 1과 Step 2 정규화 호출을 structured output으로 전환한다.
  - 대상: `data_extraction/services/extraction/integrity.py`
  - 완료 기준: step1 / career normalization / education normalization이 모두 스키마 강제형 응답을 사용한다.

- [ ] batch request payload를 structured output 형식으로 바꾼다.
  - 대상: `data_extraction/services/batch/request_builder.py`
  - 완료 기준: batch request line에 schema 강제 설정이 포함된다.

- [ ] batch ingest 파서를 structured output 기준으로 단순화한다.
  - 대상: `data_extraction/services/batch/ingest.py`
  - 완료 기준: markdown fence 제거 전제 코드가 없어지거나 optional fallback 수준으로 축소된다.

- [ ] structured output 회귀 테스트를 추가한다.
  - 대상: `tests/test_de_batch.py`, 신규 또는 기존 extraction 관련 테스트
  - 완료 기준:
    - legacy 성공 케이스
    - integrity 성공 케이스
    - batch 응답 성공 케이스
    - schema mismatch / empty candidate 실패 케이스
    가 자동 테스트로 커버된다.

## Phase 3. 텍스트 품질 게이트 도입

- [ ] 텍스트 품질 판별 함수를 추가한다.
  - 대상: `data_extraction/services/text.py`
  - 작업:
    - `classify_text_quality()` 또는 동등 함수 추가
    - 반환값 예: `ok`, `too_short`, `garbled_text`, `unsupported_format`
  - 완료 기준: 길이 부족, 문자 깨짐, 비지원 포맷을 함수 레벨에서 구분할 수 있다.

- [ ] realtime 경로에서 품질 게이트를 적용한다.
  - 대상: `data_extraction/management/commands/extract.py`, `data_extraction/services/save.py`
  - 완료 기준: `too_short`, `garbled_text`, `unsupported_format` 문서는 LLM 호출 전에 중단되고 `Resume`에 적절한 상태와 메시지가 남는다.

- [ ] batch prepare 경로에서 품질 게이트를 적용한다.
  - 대상: `data_extraction/services/batch/prepare.py`
  - 완료 기준: 품질 불량 문서는 request file에 포함되지 않고 `GeminiBatchItem.status=FAILED`와 `prepare_failures`에 이유가 남는다.

- [ ] pipeline 레벨에서 텍스트 품질 결과를 받을 수 있게 정리한다.
  - 대상: `data_extraction/services/pipeline.py`
  - 완료 기준: 추후 다른 호출자도 같은 품질 판정 결과를 재사용할 수 있다.

- [ ] 텍스트 품질 테스트를 추가한다.
  - 대상: 신규 `tests/test_de_text_quality.py`
  - 완료 기준:
    - too_short 분기
    - garbled_text 분기
    - unsupported_format 분기
    - 정상 문서 분기
    가 테스트된다.

## Phase 4. critical field gate 추가

- [ ] critical field 규칙을 정의하고 코드화한다.
  - 대상: `data_extraction/services/validation.py`, `data_extraction/services/decision.py`
  - 작업:
    - `name == 0.0 -> failed`
    - `email < 1.0` 또는 `phone < 1.0 -> auto_confirmed 금지`
    - 경력 날짜 역전 / 낮은 `date_confidence` -> needs_review
  - 완료 기준: 평균 점수와 별도로 강제 게이트가 동작한다.

- [ ] machine-friendly `rule_code`를 도입한다.
  - 대상: `data_extraction/services/validation.py`, `data_extraction/services/save.py`, 필요 시 `candidates/models.py`
  - 완료 기준: `issues`에 사람이 읽는 message만이 아니라 코드형 분류값도 포함된다.

- [ ] validation 결과와 diagnosis 결과의 필드 구조를 통일한다.
  - 대상: `data_extraction/services/validation.py`, `data_extraction/services/decision.py`
  - 완료 기준: legacy / batch / integrity가 같은 필드명으로 issue, rule_code, retry_action을 다룬다.

- [ ] critical field gate 테스트를 추가한다.
  - 대상: 신규 `tests/test_de_decision.py`, `tests/test_de_pipeline.py`, `tests/test_de_batch.py`
  - 완료 기준:
    - 이름 누락
    - 연락처 형식 오류
    - 경력 날짜 역전
    - 낮은 date_confidence
    케이스의 최종 status가 고정된다.

## Phase 5. batch / realtime / integrity 관측성 강화

- [ ] batch item metadata 저장 필드를 확정한다.
  - 대상: `batch_extract/models.py`
  - 완료 기준: migration 추가 없이 JSONField만 활용할지, 명시 필드 추가가 필요한지 결정되어 있다.

- [ ] batch prepare 메타데이터를 강화한다.
  - 대상: `data_extraction/services/batch/prepare.py`
  - 작업:
    - `raw_text_chars`
    - `error_type`
    - 필요 시 `text_quality`
  - 완료 기준: prepare 단계 실패와 skip 이유를 item/job 단위로 집계할 수 있다.

- [ ] batch ingest 메타데이터를 저장한다.
  - 대상: `data_extraction/services/batch/ingest.py`
  - 작업:
    - `prompt_token_count`
    - `candidate_token_count`
    - `total_token_count`
    - `response_chars`
    - `error_type`
  - 완료 기준: result file만 보고 재계산하지 않아도 item metadata에서 토큰/실패 유형을 조회할 수 있다.

- [ ] realtime / integrity 경로의 실패 원인도 같은 축으로 남긴다.
  - 대상: `data_extraction/management/commands/extract.py`, `data_extraction/services/save.py`, 필요 시 `candidates/models.py`
  - 완료 기준: batch와 별개가 아니라 `error_type`, `rule_codes`, `raw_text_chars`를 비교 가능한 형태로 남길 수 있다.

- [ ] 관측성 테스트와 샘플 조회 쿼리를 준비한다.
  - 대상: `tests/test_de_batch.py`, 필요 시 운영용 메모 문서
  - 완료 기준: prepare 실패, ingest 실패, review 유발 rule_code를 확인하는 예시가 남아 있다.

## Phase 6. Drive MIME 확장과 추출 전략 분기

- [ ] 1차 지원 범위를 확정한다.
  - 대상: 이 문서 또는 별도 구현 메모
  - 완료 기준: `PDF`, `Google Docs`, `HWP` 중 무엇이 1차 범위인지 명시되어 있다.

- [ ] Drive 수집 쿼리를 지원 범위에 맞게 확장한다.
  - 대상: `data_extraction/services/drive.py`
  - 완료 기준: 지원 범위로 정한 MIME이 실제 목록 수집에 포함된다.

- [ ] `mime_type -> extract strategy` 분기를 추가한다.
  - 대상: `data_extraction/services/text.py`, `data_extraction/services/batch/prepare.py`, `data_extraction/management/commands/extract.py`
  - 완료 기준: MIME별로 적절한 텍스트 추출기 또는 unsupported 분기가 명시된다.

- [ ] HWP 정책을 코드와 문서에 같이 반영한다.
  - 대상: `data_extraction/services/filename.py`, 관련 테스트, 이 문서
  - 완료 기준: HWP를 지원하지 않으면 parser 확장자 인식과 실제 지원 범위의 차이가 문서/코드에서 혼동되지 않는다.

- [ ] MIME 확장 테스트를 추가한다.
  - 대상: filename / drive / text 관련 테스트
  - 완료 기준: 지원 MIME 수집, 비지원 포맷 차단, strategy 분기가 자동 테스트된다.

## Phase 7. 프롬프트 슬림화

- [ ] structured output 전환 후 중복 스키마 설명을 제거한다.
  - 대상: `data_extraction/services/extraction/prompts.py`
  - 완료 기준: prompt가 규칙 중심으로 축소되고, 스키마 정의는 structured output 설정에 의존한다.

- [ ] legacy / batch 프롬프트 버전을 기록한다.
  - 대상: `data_extraction/services/extraction/gemini.py`, `data_extraction/services/batch/request_builder.py`, 관측성 저장 경로
  - 완료 기준: 어떤 prompt 버전으로 추출했는지 추적 가능하다.

- [ ] 프롬프트 길이 감소 효과를 확인한다.
  - 대상: batch metadata 또는 수동 측정
  - 완료 기준: 문서당 입력 토큰 평균 변화가 기록된다.

## Phase 8. 문서 유형 classifier

- [ ] lightweight rule classifier를 추가한다.
  - 대상: `data_extraction/services/pipeline.py` 또는 신규 helper
  - 완료 기준: `mixed_ko_en`, `table_heavy`, `sparse_short`, `career_heavy` 같은 타입을 rule-based로 분류할 수 있다.

- [ ] 문서 유형별 prompt / validation 설정 연결을 추가한다.
  - 대상: `data_extraction/services/extraction/prompts.py`, `data_extraction/services/batch/request_builder.py`, `data_extraction/services/decision.py`
  - 완료 기준: 특정 문서군에서 strictness나 max tokens를 다르게 줄 수 있다.

- [ ] classifier 메타데이터를 저장한다.
  - 대상: batch metadata, 필요 시 `ValidationDiagnosis`
  - 완료 기준: 유형별 실패율과 review 비율을 대시보드에서 볼 수 있다.

## Phase 9. 근거 데이터 저장 확장

- [ ] 핵심 필드 evidence 스키마를 확정한다.
  - 대상: `data_extraction/services/extraction/prompts.py`, `data_extraction/services/save.py`
  - 완료 기준: `field`, `value`, `evidence`, `source_section` 구조가 정해진다.

- [ ] 추출 결과에 evidence를 포함시킨다.
  - 대상: `data_extraction/services/extraction/gemini.py`, `data_extraction/services/extraction/integrity.py`, structured output schema
  - 완료 기준: 핵심 필드 몇 개에 대해 근거 문자열을 받을 수 있다.

- [ ] 저장 정책을 정한다.
  - 대상: `data_extraction/services/save.py`, 필요 시 모델/JSON 구조
  - 완료 기준: evidence가 raw JSON에만 남을지, 별도 필드/JSON으로 정규화할지 결정된다.

## Phase 10. 검증 및 운영 적용

- [ ] 우선순위 높은 경로에 대한 통합 테스트를 추가한다.
  - 대상: batch prepare, batch ingest, realtime command, save path 관련 테스트
  - 완료 기준: P0 작업 4개가 end-to-end 회귀 테스트로 묶인다.

- [ ] 샘플 문서 세트로 수동 검증한다.
  - 대상: 실제 이력서 샘플 또는 익명화 fixture
  - 완료 기준:
    - JSON 파싱 실패율
    - too_short / garbled 차단율
    - auto_confirmed / needs_review 비율
    - 핵심 필드 오류율
    을 변경 전후로 비교할 수 있다.

- [ ] 배포 후 관측 지표를 확인한다.
  - 대상: batch job metadata, `ValidationDiagnosis`, `DiscrepancyReport`
  - 완료 기준: 문서 7장의 성공 지표를 최소 1회 이상 실제 데이터로 확인한다.
