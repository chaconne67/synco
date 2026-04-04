# data_extraction 성능·품질 개선 계획서

**일자:** 2026-04-04  
**목적:** 현재 `data_extraction` 앱의 실시간/배치 추출 경로를 기준으로, 처리량을 높이고 품질 drift를 줄이며 운영 가시성을 높이는 수정 사항을 정리한다.  
**범위:** `data_extraction/management/commands/extract.py`, `data_extraction/services/*`, 배치 경로, integrity 경로, 저장 직전/직후 품질 관리  

---

## 1. 참고한 리서치·점검 자료

- `docs/inspection/2026-04-02-extraction-pipeline-inspection.md`
- `docs/inspection/2026-04-03-data-extraction-e2e-reinspection.md`
- `docs/inspection/2026-04-03-data-extraction-db-save-reinspection.md`
- `docs/inspection/2026-04-04-overall-code-inspection.md`
- `docs/plans/2026-04-04-data-extraction-app-plan.md`
- `docs/superpowers/plans/2026-04-03-integrity-check-pipeline.md`

이 문서는 위 자료의 운영/품질 리스크를 현재 `data_extraction` 코드와 다시 대조해, 실제 효과가 큰 수정만 우선순위로 압축한 보완 계획이다.

---

## 2. 한줄 결론

지금 `data_extraction` 앱은 기능적으로는 동작하지만, **실시간 legacy / 실시간 integrity / batch ingest가 서로 다른 품질 기준으로 움직이고**, **Drive/Gemini 클라이언트와 batch 파일 처리가 불필요하게 비효율적이며**, **재실행·성능 측정·품질 회귀 탐지가 약한 상태**다.

가장 효과가 큰 순서는 아래와 같다.

1. 품질 판정 경로를 하나로 통일
2. Drive/Gemini 클라이언트 재사용으로 호출 오버헤드 절감
3. batch prepare/ingest를 스트리밍으로 바꿔 메모리와 DB 부하 감소
4. 체크포인트·재시도·실패 분류 추가
5. 관측성/벤치마크/골든셋 테스트 추가

---

## 3. 현재 코드 기준 핵심 관찰

### A. integrity 경로가 filename 교차검증을 거의 쓰지 못한다

- `data_extraction/services/pipeline.py`의 integrity 경로는 `compute_field_confidences(result, {})`를 호출한다.
- 즉, `filename_meta`를 이미 받고도 integrity 진단에는 비어 있는 dict를 넘긴다.
- 결과적으로 legacy 경로보다 integrity 경로가 이름/생년 파일명 교차검증을 덜 활용한다.

영향:

- 같은 후보자라도 경로에 따라 confidence 산정 기준이 달라진다.
- 운영자가 `--integrity`를 선택했을 때 품질이 더 좋아져야 하는데, 일부 기준은 오히려 약해진다.

### B. batch 경로는 realtime과 품질 규칙이 다르다

- `extract.py`의 realtime 경로는 `--integrity` 옵션을 지원한다.
- 반면 batch ingest는 `validate_extraction()` 기반의 legacy 판정만 수행하고, `integrity_flags`는 빈 배열로 저장한다.
- 즉 같은 원문도 realtime과 batch가 서로 다른 품질 체계를 사용한다.

영향:

- 배치 비용 절감은 되지만, 품질 기준이 달라져 회귀 비교가 어려워진다.
- 운영에서 “어느 경로가 더 신뢰할 수 있는가”가 불명확해진다.

### C. Drive 서비스와 Gemini 클라이언트를 너무 자주 새로 만든다

- `data_extraction/services/drive.py:get_drive_service()`는 호출할 때마다 credential 로드 + service build를 수행한다.
- realtime 처리에서는 각 그룹마다 `_process_group_inner()`가 새 Drive service를 만든다.
- batch prepare도 그룹 worker마다 새 Drive service를 만든다.
- Gemini도 `extraction/gemini.py`와 `extraction/integrity.py`에서 호출마다 client를 새로 만든다.

영향:

- 파일 수가 많아질수록 인증 파일 I/O와 client 생성 비용이 누적된다.
- 외부 API 자체보다 준비 오버헤드가 눈에 띄는 비율을 차지할 수 있다.

### D. batch prepare/ingest는 큰 작업에서 메모리와 DB round-trip이 많다

- `batch/prepare.py`는 모든 payload를 `collected` 리스트에 모은 뒤 한 번에 request file을 쓴다.
- `batch/ingest.py`는 result JSONL 전체를 `entries` 리스트로 먼저 읽는다.
- ingest worker는 `key_to_item`이 있어도 다시 `GeminiBatchItem.objects.get()`를 건별 호출한다.

영향:

- 요청 수가 커질수록 메모리 사용량이 불필요하게 증가한다.
- DB 조회/쓰기 횟수가 많아져 ingestion throughput이 떨어진다.

### E. realtime 경로는 재실행 시 다운로드·텍스트 추출을 매번 처음부터 한다

- realtime 처리의 임시 파일은 `TemporaryDirectory()` 안에서만 유지된다.
- batch는 `raw_text_path` 아티팩트를 남기지만 realtime은 그렇지 않다.

영향:

- 같은 Drive 파일을 다시 처리할 때도 다운로드와 텍스트 추출 비용을 다시 낸다.
- 부분 실패 후 재시작 시 시간이 오래 걸리고 원인 분석도 어렵다.

### F. 저장 직후 discrepancy scan이 항상 동기 실행된다

- `save_pipeline_result()`는 저장 직후 `scan_candidate_discrepancies()`를 실행하고 리포트를 합친다.
- 이 동작은 리뷰 품질에는 도움이 되지만, 대량 ingest에서는 CPU/DB 부하를 바로 키운다.

영향:

- batch ingest 속도가 저장 자체보다 후처리 스캔에 의해 제한될 수 있다.
- 대량 적재와 즉시 검수 가능성을 항상 같은 트랜잭션에 묶고 있다.

### G. 관측성과 회귀 탐지 도구가 부족하다

- 현재는 phase 시간 정도만 CLI에 출력한다.
- 토큰 절감률, LLM 응답 지연, 단계별 실패 원인, 경로별 품질 차이, prompt/schema 버전 정보가 체계적으로 남지 않는다.

영향:

- “왜 느려졌는지”, “왜 품질이 떨어졌는지”를 사후에 설명하기 어렵다.
- 리팩터링 이후 성능/품질 회귀를 빠르게 발견하기 어렵다.

---

## 4. 우선순위별 수정 제안

## P0. 품질 판정 경로 통일

**목표:** legacy / integrity / batch가 같은 품질 계약을 따르도록 만든다.

### 수정 내용

- `data_extraction/services/pipeline.py`에 공통 diagnosis builder를 만든다.
- integrity 경로에서도 `filename_meta`를 받아 파일명 교차검증을 반영한다.
- batch ingest가 legacy 검증만 쓰지 않도록 `--batch --integrity` 경로를 추가하거나, 최소한 batch의 prompt/schema/diagnosis 버전을 realtime과 명시적으로 분리한다.
- `ValidationDiagnosis.field_scores`와 `Candidate.field_confidences`의 의미를 경로와 무관하게 동일하게 맞춘다.

### 대상 파일

- `data_extraction/services/pipeline.py`
- `data_extraction/management/commands/extract.py`
- `data_extraction/services/batch/ingest.py`
- `data_extraction/services/validation.py`

### 기대 효과

- 같은 파일을 어떤 모드로 돌려도 confidence와 review 분류가 예측 가능해진다.
- integrity 모드가 실제로 더 풍부한 근거를 사용하도록 정렬된다.

### 완료 기준

- 동일 fixture에 대해 realtime legacy / realtime integrity / batch legacy / batch integrity 결과를 비교하는 테스트가 생긴다.
- 경로별 진단 차이가 “의도된 차이”만 남는다.

---

## P1. Drive / Gemini 클라이언트 재사용

**목표:** 외부 API 준비 비용을 줄여 처리량을 높인다.

### 수정 내용

- `drive.py`에 thread-local Drive service 캐시를 둔다.
- credentials 로드와 client secret JSON 파싱을 process-level memoization으로 바꾼다.
- `extraction/gemini.py`, `extraction/integrity.py`, `batch/api.py`에 thread-local Gemini client 캐시를 둔다.
- worker thread는 “스레드당 1회 생성, 여러 그룹 재사용” 패턴으로 바꾼다.

### 대상 파일

- `data_extraction/services/drive.py`
- `data_extraction/services/extraction/gemini.py`
- `data_extraction/services/extraction/integrity.py`
- `data_extraction/services/batch/api.py`
- `data_extraction/management/commands/extract.py`
- `data_extraction/services/batch/prepare.py`

### 기대 효과

- 대량 처리에서 인증/초기화 오버헤드 감소
- worker 수를 늘렸을 때 실제 처리량 향상
- API 호출 전 단계의 지연 감소

### 구현 메모

- `googleapiclient` service는 thread-safe가 아니므로 global singleton이 아니라 thread-local이 적합하다.
- Gemini client도 같은 원칙으로 관리한다.

---

## P2. batch prepare / ingest 스트리밍화

**목표:** 메모리 급증과 불필요한 DB round-trip을 줄인다.

### 수정 내용

- `prepare_drive_job()`에서 `collected` 리스트를 없애고, worker 결과를 받는 즉시 JSONL 파일에 append한다.
- `GeminiBatchItem` 생성은 payload마다 즉시 하거나, 일정 크기 단위 `bulk_create()`로 묶는다.
- batch prepare도 realtime처럼 “전체 파일 ID bulk 조회 1회” 방식으로 바꾼다.
- `ingest_job_results()`는 result file을 전체 메모리에 올리지 말고 line-by-line streaming 처리한다.
- ingest worker가 다시 `GeminiBatchItem.objects.get()`를 하지 않도록, 필요한 필드만 미리 로드하거나 batch update 전략을 쓴다.

### 대상 파일

- `data_extraction/services/batch/prepare.py`
- `data_extraction/services/batch/ingest.py`
- `data_extraction/management/commands/extract.py`

### 기대 효과

- 큰 job에서 메모리 안정성 향상
- ingest wall-clock 단축
- 실패 지점 파악이 쉬워지고 중간 결과 유실 위험 감소

### 완료 기준

- 1,500건 이상 기준으로 prepare/ingest 최대 메모리 사용량과 처리 시간을 기록하는 벤치마크가 추가된다.
- result JSONL이 크더라도 ingest가 O(lines) streaming으로 동작한다.

---

## P3. realtime 아티팩트 캐시 + 체크포인트

**목표:** 재실행 비용을 줄이고 중간 실패 복구를 쉽게 만든다.

### 수정 내용

- `.data_extraction/realtime/` 아래에 `drive_file_id + modified_time` 기준 raw text artifact를 저장한다.
- 전처리 결과와 파일 메타데이터를 같이 저장해 재실행 시 reuse 가능하게 한다.
- 그룹 처리 단계를 `downloaded`, `text_extracted`, `extracted`, `saved` 같은 checkpoint로 기록한다.
- `--resume` 또는 `--reuse-artifacts` 옵션을 추가해 같은 파일을 다시 돌릴 때 다운로드/텍스트 추출을 건너뛴다.

### 대상 파일

- `data_extraction/management/commands/extract.py`
- `data_extraction/services/text.py`
- `data_extraction/services/batch/artifacts.py`

### 기대 효과

- 부분 실패 후 재시작 시간 단축
- 텍스트 추출 병목 완화
- 품질 디버깅 시 “원문 텍스트 기준 재현”이 쉬워짐

### 추가 메모

- 배치가 이미 `raw_text_path`를 쓰고 있으므로, realtime에도 같은 artifact 설계를 재사용하는 편이 좋다.

---

## P4. 재시도 정책과 실패 분류 개선

**목표:** transient failure에 덜 취약하고, 운영자가 실패 원인을 빠르게 분류할 수 있게 만든다.

### 수정 내용

- group 처리 전체를 감싸는 bounded retry를 추가한다.
- 실패를 `drive_download`, `text_extraction`, `llm_timeout`, `llm_parse`, `validation_fail`, `db_save`처럼 단계별로 분류한다.
- Gemini 호출 retry에 backoff + jitter를 넣고, parse failure와 API failure를 구분 기록한다.
- batch full polling은 고정 30초 대신 adaptive polling으로 바꾼다.

### 대상 파일

- `data_extraction/management/commands/extract.py`
- `data_extraction/services/extraction/gemini.py`
- `data_extraction/services/extraction/integrity.py`
- `data_extraction/services/batch/api.py`

### 기대 효과

- 일시적 네트워크/API 오류에 대한 복원력 향상
- 장애 분석 속도 향상
- 전체 job 실패율 감소

### 완료 기준

- 실패 로그가 단계별 코드와 메시지를 남긴다.
- batch job metadata와 realtime summary에 실패 유형 집계가 포함된다.

---

## P5. 저장 후 후처리 비용 제어

**목표:** 대량 import 시 저장 속도와 검수 품질의 균형을 잡는다.

### 수정 내용

- `save_pipeline_result()`에 `scan_discrepancies` 플래그를 추가한다.
- realtime 기본값은 현재처럼 즉시 스캔 유지.
- batch ingest는 선택적으로 “저장 우선, discrepancy scan은 후속 job” 모드 지원.
- 대량 적재 후 별도 커맨드로 `scan_candidate_discrepancies`를 묶어 실행할 수 있게 한다.

### 대상 파일

- `data_extraction/services/save.py`
- `data_extraction/services/batch/ingest.py`
- `data_extraction/management/commands/extract.py`

### 기대 효과

- batch ingest 처리량 향상
- 대규모 backfill/재추출 작업에서 wall-clock 절감
- 운영 모드별 비용 제어 가능

### 주의

- review queue 즉시 가시성이 필요한 운영 시간대에는 realtime 우선 정책이 더 적합하다.

---

## P6. 전처리 품질 가드레일 추가

**목표:** 토큰 절감은 유지하되, 한글/영문 병기 이력서에서 정보 손실을 줄인다.

### 수정 내용

- `preprocess_resume_text()`의 near-duplicate 제거 기준을 대표 이력서 샘플로 재검증한다.
- 국문/영문 병기 섹션, 표/텍스트박스 중복, 경력기술서 상세 문장에 대한 골든셋 테스트를 만든다.
- line 삭제 이유를 옵션으로 기록할 수 있게 해 pruning 품질을 측정한다.
- noise rule은 하드코딩 문자열 삭제에서 “검색 가치가 낮은 일반 PC 스킬” 수준의 규칙 기반 필터로 정리한다.

### 대상 파일

- `data_extraction/services/text.py`
- `tests/test_de_text.py`
- 신규 fixture/benchmark 테스트

### 기대 효과

- 토큰 절감률은 유지하면서 경력/기술 누락 위험 감소
- 추출 품질 저하가 preprocessing 때문인지 LLM 때문인지 구분 가능

---

## P7. 관측성·버전 관리·회귀 탐지 강화

**목표:** 속도와 품질을 수치로 관리한다.

### 수정 내용

- phase별 소요 시간 외에 아래를 job metadata 또는 structured log로 남긴다.
  - 원문 길이 / 전처리 후 길이 / 절감률
  - 추정 입력 토큰 수
  - LLM 응답 시간
  - validation issue 개수
  - integrity flag 개수와 severity 분포
  - prompt/schema 버전
- `ValidationDiagnosis` 또는 batch item metadata에 prompt version, extraction path(legacy/integrity/batch)를 남긴다.
- 소규모 골든셋을 만들어 “속도 + 구조 품질 + 핵심 필드 recall”을 비교하는 canary 테스트를 추가한다.

### 대상 파일

- `data_extraction/management/commands/extract.py`
- `data_extraction/services/pipeline.py`
- `data_extraction/services/batch/prepare.py`
- `data_extraction/services/batch/ingest.py`
- `data_extraction/services/extraction/prompts.py`

### 기대 효과

- 모델/프롬프트/정규화 변경 후 회귀를 빠르게 발견
- 비용 최적화 근거 확보
- 운영 보고서 자동화 가능

---

## 5. 구현 순서 권장안

### 1단계: 품질 기준 정렬

- P0 수행
- batch/realtime parity 테스트 추가
- integrity 경로에 filename cross-check 반영

### 2단계: 가장 큰 성능 병목 제거

- P1 수행
- P2의 streaming prepare/ingest 반영
- 동일 데이터셋으로 before/after 시간 측정

### 3단계: 재실행·운영 안정성 보강

- P3 수행
- P4 수행
- 실패 유형 대시보드 또는 로그 집계 추가

### 4단계: 대량 적재 최적화

- P5 수행
- discrepancy 후처리 분리 여부를 운영 모드별로 결정

### 5단계: 회귀 방지 장치 구축

- P6 수행
- P7 수행

---

## 6. 기대 성과

### 성능

- Drive/Gemini client 준비 오버헤드 감소
- batch prepare/ingest 메모리 사용량 감소
- 대량 재추출 시 재실행 비용 감소
- discrepancy 동기 실행 비용을 운영 상황에 따라 분리 가능

### 품질

- 경로별 confidence drift 축소
- integrity/legacy/batch 결과 비교 가능성 향상
- 전처리로 인한 누락 가능성 감소
- 실패 원인과 품질 회귀의 원인 구분 가능

### 운영성

- 부분 실패 후 재개 가능
- 배치 작업의 원인 추적과 통계 분석 가능
- prompt/schema 변경을 더 안전하게 출시 가능

---

## 7. 완료 기준

1. realtime legacy / realtime integrity / batch ingest의 진단 규칙 차이가 문서화되고 테스트로 고정된다.
2. Drive service와 Gemini client가 스레드 단위로 재사용된다.
3. batch prepare/ingest가 전체 파일을 메모리에 올리지 않고 streaming으로 처리된다.
4. realtime 경로에 raw text artifact 재사용 또는 resume 기능이 생긴다.
5. 실패 로그가 단계별 코드로 분류된다.
6. discrepancy scan을 즉시/지연 모드로 선택할 수 있다.
7. 전처리 품질을 검증하는 골든셋 테스트가 추가된다.
8. job metadata 또는 로그에 성능·품질 지표가 남는다.

---

## 8. 개발자 전달 요약

지금 필요한 것은 새 기능을 더 붙이는 것이 아니라, `data_extraction` 앱을 **대량 처리에도 버티고, 경로가 달라도 같은 기준으로 판단하며, 실패와 회귀를 설명할 수 있는 파이프라인**으로 만드는 것이다.

가장 먼저 할 일은 세 가지다.

1. 품질 판정 경로 통일
2. 외부 클라이언트 재사용
3. batch streaming 처리

이 세 가지만 먼저 해도 속도, 비용, 운영 신뢰도가 모두 좋아진다.
