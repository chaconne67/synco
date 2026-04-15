# 데이터 추출 전과정 점검 보고서

**일자:** 2026-04-03
**범위:** Google Drive 수집 -> 파일 그룹핑 -> 텍스트 추출 -> Gemini 구조화 추출 -> 검증/무결성 분석 -> DB 저장 -> 후처리(불일치 리포트, 임베딩)
**점검자:** Codex

---

## 1. 종합 판정

## 판정: CONDITIONAL GO

- **기본 경로(legacy, 기본값)**: `import_resumes` -> `text_extraction` -> `gemini_extraction` -> `validation` -> `save_pipeline_result` 흐름은 대체로 이어져 있다.
- **무결성 경로(`--integrity`)**: **NO GO**. 검증, 버전 비교, 저장 이후 리포트 노출이 현재 코드 기준으로 완전히 정합적이지 않다.

즉, 지금 레포의 “추출 전과정”은 하나가 아니라 두 개다.

1. 기본 운영 경로: 단일 Gemini 호출 + rule-based validation
2. 선택 경로: Step 1 -> 1.5 -> 2 -> 3 integrity pipeline

기본 경로는 실제로 동작 가능한 수준이지만, 신규 integrity 경로는 아직 운영 플로우에 연결되지 않은 부분이 여러 군데 남아 있다.

---

## 2. 이번 점검에서 확인한 실행 흐름

### A. 기본 임포트 경로

`candidates/management/commands/import_resumes.py`

1. Google Drive 연결 및 폴더 탐색
2. 파일 목록 조회
3. 파일명 기반 `(name, birth_year)` 그룹핑
4. primary 파일 다운로드
5. `.doc/.docx` 텍스트 추출 + 전처리
6. Gemini 구조화 추출
7. rule-based validation + 파일명 교차검증
8. `Candidate` / `Resume` / `Career` / `Education` / `ValidationDiagnosis` 저장
9. 규칙 기반 `DiscrepancyReport` 생성

### B. 선택 integrity 경로

`import_resumes --integrity`

1. Step 1: faithful extraction
2. Step 1.5: grouping
3. Step 2: normalization
4. Step 3: overlap / cross-version analysis
5. 동일한 `save_pipeline_result()`로 저장

설계상은 더 강력하지만, 실제 저장/검수 연결은 아직 미완성이다.

---

## 3. 확인한 강점

### A. Drive -> extraction -> save 기본 체인은 끊기지 않는다

- `drive_sync.py`는 read-only scope, refresh token, pagination, download retry를 갖추고 있다.
- `text_extraction.py`는 `.docx` 본문/테이블/텍스트박스를 읽고, `.doc`는 `antiword` 실패 시 LibreOffice로 fallback한다.
- `validation.py`는 이름, 출생연도, 경력 날짜 역전, 파일명 교차검증을 수행한다.
- `save_pipeline_result()`는 추출 결과를 후보자/이력서/검증 진단/리포트까지 한 트랜잭션 안에서 저장한다.

### B. 테스트 기반은 꽤 넓다

다음 추출 관련 테스트 묶음을 실행했다.

```bash
uv run pytest -q \
  tests/test_text_extraction.py \
  tests/test_drive_sync.py \
  tests/test_llm_extraction.py \
  tests/test_validation.py \
  tests/test_retry_pipeline.py \
  tests/test_import_pipeline.py \
  tests/test_integrity_step1.py \
  tests/test_integrity_step1_5.py \
  tests/test_integrity_step2.py \
  tests/test_integrity_step3.py \
  tests/test_integrity_validators.py \
  tests/test_integrity_pipeline.py \
  tests/test_integrity_cross_version.py \
  tests/test_discrepancy_service.py \
  tests/test_candidate_embedding.py
```

결과:

- **196 passed**
- **1 failed**

실패 테스트는 `tests/test_integrity_step1_5.py::TestGroupRawData::test_feedback_included_in_message` 1건이다.

---

## 4. 주요 발견 사항

### HIGH 1. 증분 임포트에서 “새 버전 갱신”이 아니라 중복 Candidate 생성으로 이어질 수 있다

근거:

- `group_by_person()`는 같은 사람 파일들 중 **최신 수정 파일을 primary**로 잡는다. `candidates/services/filename_parser.py:103-107`
- `import_resumes`는 **primary 파일 ID만** 기준으로 기존 그룹을 건너뛴다. `candidates/management/commands/import_resumes.py:204-210`
- 저장 단계는 기존 후보자를 찾지 않고 **항상 새 Candidate를 생성**한다. `candidates/services/integrity/save.py:85-119`, `candidates/services/integrity/save.py:225-251`

영향:

- 과거 이력서가 이미 DB에 있고, 같은 사람의 더 최신 이력서가 Drive에 추가되면:
  - 새 파일은 primary가 되므로 그룹이 다시 처리된다.
  - 하지만 기존 후보자를 업데이트하지 않고 새 후보자를 만든다.
  - 결과적으로 **같은 사람의 Candidate가 중복 생성**될 수 있다.

이건 현재 파이프라인의 가장 큰 정합성 리스크다.

### HIGH 2. `--integrity` 경로는 사실상 모든 성공 케이스를 `auto_confirmed`로 처리한다

근거:

- integrity 결과가 `None`만 아니면 diagnosis를 항상 `verdict="pass"`, `overall_score=0.9`로 만든다. `candidates/services/retry_pipeline.py:80-87`
- 저장 단계는 이 verdict/score를 그대로 사용해 `validation_status`를 계산한다. `candidates/services/integrity/save.py:66-74`

영향:

- integrity pipeline에서 `RED`/`YELLOW` 플래그가 나와도 후보자는 자동 확인 상태가 될 수 있다.
- 즉, “무결성 검사를 더 강하게 하려고 켠 옵션”이 오히려 **검수 대기 분류를 약화**시키는 구조다.

### HIGH 3. integrity 플래그 리포트가 저장되더라도, 바로 뒤의 규칙 기반 리포트에 가려질 수 있다

근거:

- `save_pipeline_result()`는 integrity flags가 있으면 `SELF_CONSISTENCY` 리포트를 먼저 만든다. `candidates/services/integrity/save.py:144-156`
- 바로 다음 줄에서 `scan_candidate_discrepancies()`도 다시 `SELF_CONSISTENCY` 리포트를 생성한다. `candidates/services/integrity/save.py:158-159`
- UI/도메인 접근자는 가장 최근 `SELF_CONSISTENCY` 리포트 하나만 사용한다. `candidates/models.py:753-763`

영향:

- integrity pipeline이 탐지한 플래그가 DB에는 저장돼도,
- 화면/검수 흐름에서는 뒤에 저장된 규칙 기반 리포트만 보이게 되어
- **핵심 integrity 결과가 실사용에서 묻힐 가능성**이 높다.

### MEDIUM 4. Step 2 검증은 현재 스키마 불일치로 사실상 비활성화돼 있다

근거:

- career normalization 출력은 `{"career": ..., "flags": [...]}` 구조다. `candidates/services/integrity/step2_normalize.py:52-75`, `candidates/services/integrity/step2_normalize.py:112-140`
- 그런데 `validate_step2()`는 `normalized["careers"]`, `normalized["integrity_flags"]`를 기대한다. `candidates/services/integrity/validators.py:141-199`
- pipeline은 이 validator를 그대로 호출한다. `candidates/services/integrity/pipeline.py:44-47`

영향:

- Step 2의 필수 필드/날짜 포맷/flag reasoning 검증이 실제로는 작동하지 않는다.
- 따라서 Step 2 “오류 시 feedback 재시도”도 거의 동작하지 않는 dead path에 가깝다.

추가로, 교육 정규화 결과는 normalization만 하고 validator를 아예 호출하지 않는다. `candidates/services/integrity/pipeline.py:141-146`

### MEDIUM 5. cross-version 비교는 설계돼 있지만 실제 import 경로에 연결돼 있지 않다

근거:

- `run_extraction_with_retry()`와 integrity pipeline은 `previous_data`를 받을 수 있게 설계돼 있다. `candidates/services/retry_pipeline.py:20-21`, `candidates/services/integrity/pipeline.py:162-168`
- 그러나 실제 import 호출부는 `previous_data`를 넘기지 않는다. `candidates/management/commands/import_resumes.py:303-310`
- 저장 시 non-primary resume는 `PENDING` 상태로만 기록된다. `candidates/services/integrity/save.py:107-119`

영향:

- Step 3의 핵심 설계 포인트 중 하나인 **버전 간 비교**는 현재 운영 import 경로에서 실행되지 않는다.
- 문서상 “전과정”에 포함된 cross-version 분석은 현재로서는 **잠재 기능**에 가깝다.

### MEDIUM 6. integrity 결과는 후보자 카드/검색에 쓰이는 핵심 필드를 비워 둘 수 있다

근거:

- integrity pipeline 최종 반환값에는 `current_company`, `current_position`, `core_competencies`, `summary`가 없다. `candidates/services/integrity/pipeline.py:171-186`
- 저장 함수는 이 키들이 있다고 가정하고 Candidate 필드에 기록한다. `candidates/services/integrity/save.py:233-240`

영향:

- `--integrity`로 임포트한 후보자는 경력/학력은 저장돼도,
- 목록 카드와 검색용 요약 필드가 비어 **UX와 검색 품질이 저하**될 수 있다.
- `field_confidences`도 빈 dict로 저장되어, 이후 discrepancy confidence gate에도 활용되지 못한다.

### LOW 7. 임포트 직후 임베딩은 자동 생성되지 않는다

근거:

- 임베딩 생성은 별도 커맨드 `generate_embeddings`로만 제공된다. `candidates/management/commands/generate_embeddings.py:1-47`
- import 경로 안에서는 `generate_candidate_embedding()` 호출이 없다.

영향:

- 새로 임포트한 후보자는 바로 semantic search 대상이 되지 않을 수 있다.
- 운영 관점에서는 “추출 완료”와 “검색 가능 상태” 사이에 수동 후처리 단계가 남는다.

### LOW 8. integrity 관련 테스트와 실제 코드 인터페이스 사이에 drift가 있다

근거:

- 실패한 테스트는 `_call_gemini(..., user_message=...)` 형태를 기대하지만, 실제 호출은 positional 인자다. `tests/test_integrity_step1_5.py:155-170`, `candidates/services/integrity/step1_5_grouping.py:139-142`
- 또 `validate_step1_5()` 테스트는 `grouping["groups"]` 구조를 쓰지만, 실제 grouping schema는 `career_groups` / `education_groups`다. `tests/test_integrity_validators.py`, `candidates/services/integrity/step1_5_grouping.py`
- 반면 `gemini_extraction.py` 자체를 직접 검증하는 테스트는 현재 보이지 않는다.

영향:

- integrity 경로는 테스트 수는 많지만, 일부는 최신 구현과 정확히 맞물리지 않는다.
- 이 상태에서는 “테스트가 많다”는 사실만으로 실제 안전성을 판단하기 어렵다.

---

## 5. 현재 기준 권장 우선순위

### 1순위

- Candidate 중복 생성/증분 버전 처리 전략 정리
- integrity 경로의 auto-confirmed 고정 로직 제거
- integrity 리포트와 rule-based 리포트의 저장/노출 방식 분리

### 2순위

- Step 2 validator 입력 스키마 정합성 복구
- cross-version `previous_data` 실제 연결
- integrity 최종 결과에 `current_company`, `summary`, `field_confidences` 등 운영 필드 보강

### 3순위

- import 후 임베딩 자동화 여부 결정
- integrity 테스트 drift 정리
- `gemini_extraction.py` 직접 단위 테스트 추가

---

## 6. 결론

현재 추출 전과정은 “기본 경로는 사용 가능, integrity 경로는 아직 실험 단계”로 보는 것이 가장 정확하다.

- **지금 바로 운영 점검 대상으로 볼 경로**: legacy 기본 경로
- **지금 바로 운영에 켜면 안 되는 경로**: `--integrity`

특히 이번 점검에서 가장 크게 확인된 문제는 “새 버전 이력서가 들어왔을 때 기존 후보자를 갱신하지 못하고 중복 후보자를 만들 수 있다”는 점이다. 이 문제는 추출 품질보다 상위의 데이터 정합성 이슈라서, 우선순위를 가장 높게 두는 것이 맞다.
