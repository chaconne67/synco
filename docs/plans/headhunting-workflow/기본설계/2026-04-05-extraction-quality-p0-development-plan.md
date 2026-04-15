# 데이터 추출 품질 P0 개발 착수 계획서

> **For agentic workers:** Execute in order. Do not expand scope without updating this plan. Use checkbox (`- [ ]`) tracking.

**일자:** 2026-04-05  
**목적:** `data_extraction` 앱의 P0 품질 개선 3개를 바로 구현 가능한 수준으로 고정한다.  
**참조 문서:**  
- `docs/plans/2026-04-05-extraction-quality-p0-plan.md`
- `docs/plans/2026-04-04-data-extraction-quality-improvement-recommendations.md`
- `docs/plans/2026-04-04-data-extraction-app-plan.md`

---

## 1. 한줄 결론

지금 단계에서는 `Task 11` 정리를 먼저 하지 않는다.  
대신 `data_extraction`을 주 경로로 고정하고, P0 3개를 아래 순서로 구현한다.

1. Structured Output
2. 텍스트 품질 게이트
3. Critical Field Gate

`candidates/services/` 구 경로는 Task 11 전까지 **동결**한다.  
즉, 신규 개선은 `data_extraction`에만 넣고, 구 경로는 버그 수정 외 변경하지 않는다.

---

## 2. 범위와 원칙

### 포함 범위

- `data_extraction/services/extraction/gemini.py`
- `data_extraction/services/extraction/integrity.py`
- `data_extraction/services/batch/request_builder.py`
- `data_extraction/services/batch/ingest.py`
- `data_extraction/services/text.py`
- `data_extraction/services/pipeline.py`
- `data_extraction/management/commands/extract.py`
- `data_extraction/services/validation.py`
- 필요 시 신규 `data_extraction/services/decision.py`
- 관련 `tests/test_de_*.py`

### 제외 범위

- `Task 11` 삭제 작업
- `candidates/services/` 구조 정리
- `batch_extract/` 제거
- MIME 확장, observability, prompt slim화, evidence 확장

### 구현 원칙

- [ ] 신규 개선은 `data_extraction`에만 반영
- [ ] `candidates/services/` 추출 경로는 수정하지 않음
- [ ] 하위 호환 fallback은 batch ingest처럼 필요한 곳에만 최소한으로 유지
- [ ] 각 단계는 테스트 통과 후 다음 단계로 진행
- [ ] 한 단계 안에 구조 리팩터링과 기능 변경을 같이 몰아넣지 않음

---

## 3. 선행 결정

구현 시작 전에 아래를 확정된 정책으로 본다.

- [ ] 주 경로는 `extract` + `data_extraction/services/*`
- [ ] 구 경로 `import_resumes` + `candidates/services/*` 는 동결
- [ ] Task 11은 P0 안정화 이후 별도 브랜치에서 진행
- [ ] P0 단계에서는 `data_extraction`만 테스트 통과를 우선 보장
- [ ] 전체 회귀 테스트는 각 단계 종료 시점에 수행

이 결정은 `2026-04-04-data-extraction-app-plan.md`의 공존 기간(Task 1~10) 원칙과 맞춘다.

---

## 4. 구현 순서

## Phase 0. 착수 준비

### 목표

P0 작업 전에 수정 대상과 테스트 기준을 고정한다.

### 작업

- [ ] 작업 브랜치 생성
- [ ] 현재 P0 대상 파일 diff 없는지 확인
- [ ] `tests/test_de_pipeline.py`, `tests/test_de_batch.py`, `tests/test_de_validation.py` 현재 통과 여부 확인
- [ ] 필요 시 신규 테스트 파일 생성:
  - `tests/test_de_text_quality.py`
  - `tests/test_de_decision.py`

### 완료 기준

- [ ] P0 대상 테스트 묶음이 준비됨
- [ ] 현재 baseline 테스트 결과를 기록함

---

## 5. Phase 1: Structured Output

### 목표

Gemini 응답을 fenced block 기반 자유 텍스트가 아니라 `application/json` 구조 응답으로 받는다.

### 대상 파일

- `data_extraction/services/extraction/gemini.py`
- `data_extraction/services/extraction/integrity.py`
- `data_extraction/services/batch/request_builder.py`
- `data_extraction/services/batch/ingest.py`

### 세부 작업

- [ ] `gemini.py`
  - `GenerateContentConfig`에 `response_mime_type="application/json"` 추가
  - fenced block 제거 로직 삭제
  - `json.loads(response.text)` 직접 사용

- [ ] `integrity.py`
  - `_call_gemini()`에 `response_mime_type="application/json"` 추가
  - fenced block 제거 로직 삭제
  - step1 / career normalization / education normalization 모두 공통 helper 경유 유지

- [ ] `batch/request_builder.py`
  - `generation_config.response_mime_type = "application/json"` 추가
  - 요청 payload가 realtime과 같은 응답 계약을 갖도록 정렬

- [ ] `batch/ingest.py`
  - `_load_extracted_json()`를 structured output 우선으로 단순화
  - 단, 기존 batch 결과 파일 호환용 fenced fallback은 유지

### 테스트

- [ ] `tests/test_de_batch.py`에 request payload assertion 추가
- [ ] structured output direct JSON 파싱 테스트 추가
- [ ] fenced fallback 호환 테스트 유지 또는 추가
- [ ] `uv run pytest tests/test_de_batch.py tests/test_de_pipeline.py -v`

### 수동 검증

- [ ] realtime 1건 추출 확인
- [ ] integrity 1건 추출 확인
- [ ] batch prepare 결과 JSONL 1건 확인

### 완료 기준

- [ ] `data_extraction` 경로에서 fenced parsing이 필수 전제가 아님
- [ ] JSON 파싱 실패가 structured output 미지원이 아닌 이상 재현되지 않음

### 구현 참조

→ [extraction-quality-p0-plan.md Task 1](2026-04-05-extraction-quality-p0-plan.md) — 변경 전/후 코드, fallback 로직, 파일:라인 상세

### 커밋 단위

- [ ] `feat(data_extraction): adopt Gemini structured output for realtime and batch`

---

## 6. Phase 2: 텍스트 품질 게이트

### 목표

짧거나 깨진 텍스트가 LLM 호출까지 가지 않도록 선제 차단한다.

### 대상 파일

- `data_extraction/services/text.py`
- `data_extraction/services/pipeline.py`
- `data_extraction/management/commands/extract.py`
- `data_extraction/services/batch/prepare.py`

### 세부 작업

- [ ] `text.py`
  - `classify_text_quality()` 추가
  - 반환값은 아래 중 하나로 고정:
    - `ok`
    - `too_short`
    - `garbled_text`
    - `unsupported_format`

- [ ] `pipeline.py`
  - LLM 호출 전에 텍스트 품질 검사
  - `ok`가 아니면 `extracted=None`과 명시적 diagnosis 반환

- [ ] `extract.py`
  - realtime 경로에서 품질 불량 문서 저장 정책 적용
  - `too_short`, `garbled_text`는 `FAILED` 또는 `TEXT_ONLY` 저장 기준을 코드로 고정

- [ ] `batch/prepare.py`
  - request file에 넣기 전에 품질 검사
  - 품질 불량이면:
    - `GeminiBatchItem.status=FAILED`
    - `error_message` 저장
    - `prepare_failures`에 기록
    - request file에는 미포함

### 테스트

- [ ] 신규 `tests/test_de_text_quality.py`
  - empty / too_short / garbled_text / ok 케이스
- [ ] `tests/test_de_pipeline.py`
  - 품질 불량 시 LLM 호출 없이 fail 반환
- [ ] `tests/test_de_batch.py`
  - batch prepare skip/fail 기록 테스트

### 수동 검증

- [ ] 짧은 fixture 입력 시 realtime에서 저장만 되고 LLM 미호출 확인
- [ ] batch prepare에서 불량 텍스트가 JSONL에 안 들어가는지 확인

### 완료 기준

- [ ] 품질 불량 텍스트는 realtime/batch 모두 LLM 호출 전 차단
- [ ] failure reason이 최소한 `error_message` 또는 diagnosis에 남음

### 구현 참조

→ [extraction-quality-p0-plan.md Task 2](2026-04-05-extraction-quality-p0-plan.md) — classify_text_quality() 코드, pipeline/extract 게이트 코드, 테스트 케이스

### 커밋 단위

- [ ] `feat(data_extraction): add text quality gate before extraction`

---

## 7. Phase 3: Critical Field Gate

### 목표

핵심 필드 누락/이상 시 평균 점수와 무관하게 자동 통과를 막는다.

### 대상 파일

- `data_extraction/services/validation.py`
- `data_extraction/services/pipeline.py`
- `data_extraction/services/batch/ingest.py`
- `data_extraction/services/save.py`
- 필요 시 신규 `data_extraction/services/decision.py`

### 선행 메모

현재 코드는 경로별 판정이 갈라져 있다.

- legacy realtime: `validate_extraction()` 후 verdict 재계산
- batch ingest: 동일하게 verdict 재계산
- integrity: 별도 diagnosis 생성
- save: diagnosis에서 `validation_status` 재파생

따라서 이 단계의 핵심은 rule 추가보다 **판정 기준 단일화**다.

### 세부 작업

- [ ] 공통 판정 helper 추가 여부 결정
  - 선택 A: `validate_extraction()`이 최종 verdict/status까지 책임
  - 선택 B: `decision.py` 신규 추가 후 모든 경로가 공통 helper 사용

- [ ] `validation.py`
  - `field_scores`를 바탕으로 critical gate 적용
  - 최소 규칙:
    - `name == 0.0` -> `failed`
    - `email == 0.0` and `phone == 0.0` -> `auto_confirmed` 금지
    - 경력 날짜 역전 또는 낮은 `date_confidence` -> `needs_review`

- [ ] `pipeline.py`
  - legacy 경로의 verdict 재계산 제거 또는 공통 helper로 치환
  - integrity 경로도 동일한 최종 status 체계를 따르도록 정렬

- [ ] `batch/ingest.py`
  - batch verdict 재계산 제거 또는 공통 helper로 치환

- [ ] `save.py`
  - `validation_status`를 별도 로직으로 다시 덮어쓰지 않도록 정리

### 테스트

- [ ] `tests/test_de_validation.py`
  - 이름 누락 -> failed
  - 이메일/전화 모두 없음 -> needs_review
  - 정상 케이스 -> auto_confirmed

- [ ] `tests/test_de_pipeline.py`
  - legacy 경로 critical gate 반영
  - integrity 경로 critical gate 반영

- [ ] `tests/test_de_batch.py`
  - batch ingest critical gate 반영

### 수동 검증

- [ ] 이름 없는 샘플 1건 확인
- [ ] 연락처 없는 샘플 1건 확인
- [ ] integrity 경로와 batch 경로의 판정 차이 확인

### 완료 기준

- [ ] 같은 fixture에 대해 legacy / integrity / batch의 최종 status가 공통 기준으로 해석됨
- [ ] save 단계에서 status가 임의로 바뀌지 않음

### 구현 참조

→ [extraction-quality-p0-plan.md Task 3](2026-04-05-extraction-quality-p0-plan.md) — compute_overall_confidence 시그니처 변경, field_scores 전달 코드, views.py 수정, 테스트 케이스

### 커밋 단위

- [ ] `feat(data_extraction): add critical field gates and unify extraction decisions`

---

## 8. Phase 4: 마무리 검증

### 목표

P0 3개가 같이 들어갔을 때 회귀 없이 동작하는지 확인한다.

### 작업

- [ ] `uv run pytest tests/test_de_*.py -v`
- [ ] `uv run pytest -v`
- [ ] realtime 2건 수동 검증
- [ ] integrity 2건 수동 검증
- [ ] batch prepare/ingest 2건 수동 검증

### 확인 항목

- [ ] JSON 파싱 실패 0건
- [ ] 품질 불량 텍스트 차단 확인
- [ ] 이름 누락 시 failed 확인
- [ ] 연락처 누락 시 auto_confirmed 차단 확인

### 커밋 단위

- [ ] `test(data_extraction): verify P0 extraction quality improvements end-to-end`

---

## 9. 작업 분할 기준

하나의 큰 PR로 밀지 않고 최소 아래 3개 PR 또는 커밋 단위로 나눈다.

1. Structured Output
2. Text Quality Gate
3. Critical Field Gate + Decision Unification

이유:

- 원인 분리가 쉽다
- 실패 시 rollback이 간단하다
- 테스트 범위를 단계별로 고정할 수 있다

---

## 10. 테스트 매트릭스

### 자동 테스트

- [ ] `tests/test_de_batch.py`
- [ ] `tests/test_de_pipeline.py`
- [ ] `tests/test_de_validation.py`
- [ ] `tests/test_de_text_quality.py`
- [ ] 필요 시 `tests/test_de_save.py`

### 수동 테스트

- [ ] 정상 이력서
- [ ] 짧은 텍스트
- [ ] 깨진 텍스트
- [ ] 이름 누락
- [ ] 연락처 누락
- [ ] integrity red/yellow flag 포함 문서

### 회귀 확인 포인트

- [ ] batch JSONL 포맷 유지
- [ ] save path에서 `ValidationDiagnosis` 생성 유지
- [ ] `DiscrepancyReport` 생성 유지
- [ ] `build_candidate_comparison_context()` 기반 candidate 재사용 유지

---

## 11. 롤백 기준

아래 중 하나라도 발생하면 해당 Phase만 되돌리고 다음 단계로 진행하지 않는다.

- [ ] realtime 추출이 structured output 전환 후 연속 실패
- [ ] batch JSONL이 Gemini Batch API에서 거부됨
- [ ] 텍스트 품질 게이트가 정상 문서를 과도하게 차단
- [ ] critical gate 적용 후 `auto_confirmed` 비율이 비정상적으로 급락
- [ ] save 단계에서 validation status 불일치 발생

롤백 원칙:

- [ ] 가장 최근 Phase 커밋만 되돌림
- [ ] 이전 Phase는 유지
- [ ] 원인 수정 후 같은 Phase부터 재진행

---

## 12. 완료 기준

아래를 모두 만족하면 이 계획은 완료다.

- [ ] `data_extraction` 경로가 structured output 기반으로 동작
- [ ] 품질 불량 텍스트가 LLM 이전에 차단
- [ ] critical field gate가 legacy / integrity / batch에 공통 반영
- [ ] save 단계와 최종 status 계산이 충돌하지 않음
- [ ] `tests/test_de_*.py` 전체 통과
- [ ] 전체 테스트 통과
- [ ] Task 11 전까지 구 경로 미수정 원칙 유지

---

## 13. 다음 단계

P0 완료 후 다음 순서로 이어간다.

1. batch / realtime / integrity 관측성 강화
2. MIME 확장과 extract strategy 분기
3. prompt slim화
4. Task 11 정리
