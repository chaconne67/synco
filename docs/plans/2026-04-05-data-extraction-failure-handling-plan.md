# data_extraction 실패 내성 및 후보자 생성 보장 계획서

> **For agentic workers:** implement only after this plan is reviewed. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 파일 추출, 텍스트 추출, LLM 추출, JSON 파싱, 검증 중 어떤 단계에서 실패하더라도 파일이 존재하면 반드시 후보자 목록에 나타나게 하고, DB에 최소 `Candidate`/`Resume` 객체를 남기며, 사용자가 실패 사유와 원본 링크를 통해 직접 확인할 수 있게 만든다.

**Primary Outcome:**
- 파일이 있으면 드롭되지 않는다.
- 실패해도 `Candidate`와 `Resume`는 생성된다.
- 실패 이유가 화면에 노출된다.
- 원본 Drive 링크가 항상 연결된다.
- LLM JSON 보정은 파싱 실패를 줄이되 정상 데이터를 과도하게 왜곡하지 않는다.

**Scope:**
- `data_extraction/management/commands/extract.py`
- `data_extraction/services/pipeline.py`
- `data_extraction/services/save.py`
- `data_extraction/services/batch/prepare.py`
- `data_extraction/services/batch/ingest.py`
- `data_extraction/services/extraction/gemini.py`
- `data_extraction/services/extraction/sanitizers.py`
- `data_extraction/services/text.py`
- `candidates/views.py`
- `candidates/templates/candidates/partials/*.html`
- 관련 테스트

---

## 현재 점검 기준

### 반드시 만족해야 하는 정책

1. **후보자 생성 보장**
- 파일만 존재하면 extraction 성공 여부와 무관하게 후보자 목록에 보여야 한다.
- 최소 단위로 `Candidate`, `Resume`는 반드시 생성되어야 한다.

2. **실패 정보 보장**
- 데이터 추출 실패 시 실패 사유가 저장되어야 한다.
- 사용자가 상세 화면에서 실패 사유를 볼 수 있어야 한다.
- 원본 이력서 링크가 연결되어 사용자가 직접 검토할 수 있어야 한다.

3. **파싱 보정 안정성**
- LLM이 JSON을 완벽히 반환하지 못해도 복구 가능한 범위는 복구해야 한다.
- 다만 보정 로직이 정상 응답을 재해석하거나 왜곡하지 않도록 보수적으로 설계해야 한다.

---

## 현재 코드 기준 위험 지점

## 현재 이미 구현된 부분

### 1. 상세 페이지 하단 원문 텍스트 노출

- 후보자 상세 화면 템플릿 [candidate_detail_content.html](/home/work/synco/candidates/templates/candidates/partials/candidate_detail_content.html) 에는 이미 하단 `원본 텍스트` 섹션이 있다.
- 조건:
  - `candidate.validation_status == "needs_review"` 또는 `"failed"`
  - `primary_resume.raw_text` 존재
- 이 경우 하단 collapsible 섹션에서 원문 텍스트를 그대로 보여준다.
- 따라서 현재 구현은 “기타 영역에 노출”이라기보다 “상세 페이지 마지막 별도 원본 텍스트 섹션에 노출”에 가깝다.

### 2. review 상세 화면 원문 텍스트 노출

- 검토 상세 화면 템플릿 [review_detail_content.html](/home/work/synco/candidates/templates/candidates/partials/review_detail_content.html) 에도 `원문 텍스트` 영역이 이미 있다.
- 우선순위:
  - `candidate.raw_text`
  - 없으면 `primary_resume.raw_text`

### 3. 현재 남은 핵심 확인 포인트

- 원문 텍스트를 보여주는 UI는 이미 존재하지만, 실패 케이스에서 그 화면에 진입할 수 있도록 `Candidate` 자체가 항상 생성되는지는 별도 보강이 필요하다.
- 즉 “노출 영역”은 일부 이미 구현되어 있으나, “실패 시에도 반드시 후보자 레코드가 생겨서 그 화면까지 도달 가능한지”는 아직 보장되지 않는다.

### 1. 실패 시 레코드가 누락되는 경로

- `extract.py` 실시간 경로에서 텍스트 품질 부족이나 추출 실패 시 `Resume`만 남고 `Candidate`는 생성되지 않는 분기가 존재할 수 있다.
- `save_pipeline_result()`는 `extracted`가 비어 있으면 `None`을 반환하므로, 호출자에 따라 후보자 생성이 생략된다.
- `batch/prepare.py`에서 텍스트 추출 실패가 나면 `GeminiBatchItem`만 실패 처리되고 후보자/이력서가 생성되지 않는다.
- `batch/ingest.py`에서 JSON 파싱 실패 또는 저장 실패 시에도 batch item 실패로 끝나고 사용자 관점의 후보자 목록에는 나타나지 않을 수 있다.

### 2. 실패 이유의 사용자 노출 부족

- `Resume.error_message`는 저장되지만 candidate 상세/검토 화면에서 명시적으로 노출되지 않는 경로가 있다.
- 원본 Drive 링크는 일부 화면에만 보이며, 실패 상태 강조와 함께 제공되지 않는다.

### 3. JSON 파싱 경로 불일치

- 실시간 경로와 integrity 경로와 batch ingest 경로가 서로 다른 JSON 파싱 방식을 사용한다.
- `sanitizers.parse_llm_json()`가 존재하지만 모든 경로에 일관되게 적용되지 않는다.

### 4. 전처리 과보정 위험

- `preprocess_resume_text()`의 중복 제거/노이즈 제거가 이력서 원문을 지나치게 정리해 중요한 문맥을 삭제할 가능성이 있다.
- 특히 짧은 기술 스택, 표 기반 이력, 반복 섹션, 자기소개 내 경력 단서가 손실될 수 있는지 확인이 필요하다.

---

## 목표 동작 정의

### 실패 단계별 기대 동작

| 실패 단계 | 기대 저장 결과 | 사용자에게 보여줄 내용 |
|---|---|---|
| 파일 다운로드 실패 | `Candidate` + `Resume(FAILED)` | 다운로드 실패 사유, 원본 링크 |
| 텍스트 추출 실패 | `Candidate` + `Resume(FAILED or TEXT_ONLY)` | 텍스트 추출 실패 사유, 원본 링크 |
| 텍스트 품질 부족 | `Candidate` + `Resume(TEXT_ONLY)` | 품질 부족 사유, 원문 텍스트, 원본 링크 |
| LLM 호출 실패 | `Candidate` + `Resume(TEXT_ONLY)` | AI 추출 실패 사유, 원문 텍스트, 원본 링크 |
| LLM JSON 파싱 실패 | `Candidate` + `Resume(TEXT_ONLY)` | JSON 파싱 실패 사유, 원문 텍스트, 원본 링크 |
| 검증 실패 | `Candidate` + `Resume(STRUCTURED)` | 검토 필요 사유, 원본 링크 |

### placeholder 후보자 정책

- 이름 추출이 실패하면 파일명 파싱 결과의 이름을 우선 사용한다.
- 파일명에서도 이름을 얻지 못하면 파일명 기반 fallback 이름을 사용한다.
- placeholder 후보자도 `validation_status=needs_review`로 생성한다.
- placeholder 후보자도 카테고리와 현재 resume를 연결한다.
- 실패 resume에도 `drive_file_id`, `error_message`, `processing_status`, `raw_text`를 가능한 범위까지 저장한다.

---

## 구현 전략

## Task 1: 실패 저장 정책을 공통 함수로 정리

**목표:** 실패를 “레코드 누락”이 아니라 “검토 가능한 placeholder 생성”으로 통일한다.

**수정 파일:**
- `data_extraction/services/save.py`

- [ ] `save_pipeline_result()` 실패 분기 정책 문서화
- [ ] 실패 시 공통으로 호출할 저장 함수 설계
- [ ] 공통 함수에서 `Candidate`, `Resume`, `ValidationDiagnosis`, `ExtractionLog` 생성 여부 결정
- [ ] `Resume.processing_status`를 실패 유형별로 일관되게 매핑
- [ ] 동일 파일 재처리 시 `update_or_create`와 신규 생성 정책 정리

**설계 메모:**
- placeholder 생성 함수는 실시간/배치가 모두 호출 가능해야 한다.
- 실패해도 `current_resume`가 비어 있지 않게 유지해야 한다.
- 정상 structured 저장 경로와 placeholder 저장 경로를 분리하되, 호출 인터페이스는 최대한 통일한다.

## Task 2: 실시간 extract 경로에 실패 저장 정책 연결

**목표:** `extract.py`에서 어떤 예외가 나도 파일이 드롭되지 않게 한다.

**수정 파일:**
- `data_extraction/management/commands/extract.py`

- [ ] 다운로드 실패 시 placeholder 저장
- [ ] 텍스트 추출 실패 시 placeholder 저장
- [ ] 텍스트 품질 부족 시 placeholder 저장
- [ ] `run_extraction_with_retry()` 결과가 비어 있을 때 placeholder 저장
- [ ] 예외 처리 시 raw_text가 있으면 함께 저장
- [ ] 다중 파일 그룹(`others`)도 최소한 resume 레코드로 연결할지 정책 확정

## Task 3: batch prepare/ingest 경로에 동일 정책 적용

**목표:** batch mode에서도 실패 파일이 후보자 목록에서 사라지지 않게 한다.

**수정 파일:**
- `data_extraction/services/batch/prepare.py`
- `data_extraction/services/batch/ingest.py`

- [ ] prepare 단계 텍스트 추출 실패 시 placeholder 저장 여부 반영
- [ ] batch item 실패와 user-facing candidate 저장을 분리해서 관리
- [ ] ingest 단계 JSON 파싱 실패 시 placeholder 저장
- [ ] ingest 단계 `save_pipeline_result()` 실패 시 placeholder 저장
- [ ] batch item의 `error_message`와 `Resume.error_message`가 같은 원인으로 연결되도록 정리

## Task 4: 실패 정보와 원본 링크를 UI에 노출

**목표:** 사용자가 실패를 “보이지 않는 내부 오류”가 아니라 “확인 가능한 상태”로 보게 한다.

**수정 파일:**
- `candidates/views.py`
- `candidates/templates/candidates/partials/candidate_detail_content.html`
- `candidates/templates/candidates/partials/review_detail_content.html`
- 필요 시 `candidate_card.html`

- [ ] 상세 화면에 processing status 노출
- [ ] 상세 화면에 실패 사유(`Resume.error_message`) 노출
- [ ] 상세 화면에 원본 Drive 링크 유지 또는 강화
- [ ] 기존 하단 `원본 텍스트` 섹션이 실패 후보자에서도 실제로 도달 가능하도록 생성 경로 보장
- [ ] 원문 텍스트를 기존 별도 섹션으로 유지할지, 마지막 `기타` 블록에 통합할지 결정
- [ ] review 화면에도 동일 정보 노출
- [ ] placeholder 후보자일 때 안내 문구 표시
- [ ] 후보자 카드 목록에 실패/검토 필요 상태 뱃지 추가 여부 검토

**표시 우선순위:**
- `current_resume.error_message`
- 최신 `ValidationDiagnosis.issues`
- 원문 텍스트
- 원본 링크

## Task 5: LLM JSON 파싱 로직 통일

**목표:** 실시간/무결성/배치가 같은 파싱 정책을 쓰게 만든다.

**수정 파일:**
- `data_extraction/services/extraction/gemini.py`
- `data_extraction/services/batch/ingest.py`
- `data_extraction/services/extraction/sanitizers.py`

- [ ] `parse_llm_json()`를 공통 진입점으로 확정
- [ ] `gemini.py`에 공통 parser 적용
- [ ] `batch/ingest.py`의 `_load_extracted_json()`를 공통 parser 기반으로 정리
- [ ] integrity 경로와 실시간 경로의 파싱 동작 차이 제거

## Task 6: 과보정 위험 검토 및 제한

**목표:** 실패 복구는 강화하되 정상 데이터 변형은 줄인다.

**수정 파일:**
- `data_extraction/services/extraction/sanitizers.py`
- `data_extraction/services/text.py`

- [ ] `parse_llm_json()` 규칙별 위험도 검토
- [ ] 허용 가능한 복구와 금지할 복구를 구분
- [ ] truncated JSON 강제 닫기 로직의 오탐 가능성 점검
- [ ] trailing comma, fenced block 제거, single-element list 해제는 유지 가능 여부 검토
- [ ] `preprocess_resume_text()`의 near-duplicate 제거가 이력서 정보 손실을 유발하는지 검토
- [ ] noise 필터가 실제 skills/경력 문장을 잘못 지우는지 샘플 기준 점검

### 보정 원칙

- **허용:** BOM 제거, fenced block 제거, control char 제거, single-item list unwrap
- **조건부 허용:** trailing comma 수정, raw_decode로 첫 JSON 객체 추출
- **보수적으로 재검토:** truncated JSON 자동 닫기, 과도한 near-duplicate 제거, 광범위 noise 제거

---

## 테스트 계획

## Task 7: 실패 저장 관련 테스트 추가

**대상 테스트 파일:**
- `tests/test_de_save.py`
- `tests/test_de_pipeline.py`
- `tests/test_de_batch.py`
- 필요 시 `tests/test_search_views.py`

- [ ] extraction 실패 시에도 `Candidate` 생성 테스트
- [ ] extraction 실패 시에도 `Resume` 생성 테스트
- [ ] 실패 사유가 `Resume.error_message`에 저장되는지 테스트
- [ ] placeholder 후보자에 `current_resume`가 연결되는지 테스트
- [ ] batch prepare 실패 시 placeholder 생성 테스트
- [ ] batch ingest JSON 파싱 실패 시 placeholder 생성 테스트
- [ ] 상세 화면에 실패 사유와 원본 링크가 보이는지 테스트

## Task 8: JSON 보정 테스트 추가

**대상 테스트 파일:**
- `tests/test_de_batch.py`
- 신규 필요 시 `tests/test_de_sanitizers.py`

- [ ] fenced JSON 파싱 테스트
- [ ] trailing comma 복구 테스트
- [ ] single-element list unwrap 테스트
- [ ] extra trailing text 처리 테스트
- [ ] 잘린 JSON 복구 허용 범위 테스트
- [ ] 정상 JSON이 보정 과정에서 바뀌지 않는 테스트
- [ ] 과보정이 우려되는 응답은 `None`으로 실패 처리되는 테스트

---

## 구현 순서

1. 실패 저장 정책 문서 기준 확정
2. 공통 placeholder 저장 함수 설계 및 테스트 추가
3. realtime 경로 연결
4. batch 경로 연결
5. UI 실패 정보 노출
6. JSON parser 공통화
7. 과보정 축소
8. 회귀 테스트

---

## 완료 기준

- [ ] 파일이 있으면 후보자 목록에서 사라지지 않는다.
- [ ] 실패 파일도 DB에 `Candidate`와 `Resume`가 남는다.
- [ ] 사용자가 실패 이유와 원본 링크를 상세/검토 화면에서 볼 수 있다.
- [ ] 실시간과 배치가 동일한 JSON 파싱 정책을 사용한다.
- [ ] 파싱 보정이 정상 응답을 불필요하게 왜곡하지 않는다.
- [ ] 관련 테스트가 모두 통과한다.

---

## 보류/결정 필요 사항

1. placeholder 후보자의 이름이 파일명 fallback일 때, 목록에서 별도 뱃지를 붙일지
2. 다운로드 자체가 실패한 경우에도 빈 raw_text resume를 만들지
3. 동일 drive file 재처리 시 기존 placeholder 후보자를 업데이트할지, 새 version resume를 만들지
4. batch prepare 단계 실패를 즉시 후보자 생성으로 처리할지, ingest 단계까지 기다릴지

---

## 비목표

- 이번 계획은 추출 품질 자체를 높이는 프롬프트 개선이 목적이 아니다.
- candidate identity 매칭 로직 전면 개편은 포함하지 않는다.
- UI 전체 리디자인은 포함하지 않는다.
