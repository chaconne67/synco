# 데이터 추출 전과정 재점검 보고서

**일자:** 2026-04-03
**범위:** Google Drive 수집 -> 파일 그룹핑 -> 텍스트 추출 -> Gemini 추출 -> integrity/validation -> DB 저장 -> 후처리
**점검자:** Codex
**기준 문서:** `docs/inspection/2026-04-03-data-extraction-e2e-inspection.md` 재검토

---

## 1. 재점검 결론

## 판정: CONDITIONAL GO

- **기본 경로(legacy)**: 사용 가능
- **integrity 경로(`--integrity`)**: 이전보다 나아졌지만 아직 운영 투입 전 추가 정리가 필요

이번 재점검에서 확인된 가장 큰 변화는 두 가지다.

1. 추출 관련 테스트 묶음이 현재 **전부 통과**한다.
2. active integrity pipeline이 이전 점검 때와 달리 **Step 1 -> Step 2 -> Step 3** 구조로 단순화되었다.

즉, 이전 보고서의 일부 지적은 해소되었지만, 데이터 정합성과 검수 분류 쪽 핵심 리스크는 아직 남아 있다.

---

## 2. 이번에 확인한 개선점

### A. 추출 관련 테스트가 현재 전부 통과한다

실행:

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

- **198 passed**

이전 재점검 직전 실패하던 `test_feedback_included_in_message`도 현재는 통과한다.

### B. integrity pipeline의 실제 실행 경로가 단순화되었다

현재 active pipeline:

- Step 1: `extract_raw_data()`
- Step 2: career/education normalization 병렬 수행
- Step 3: overlap / cross-version analysis

근거: `candidates/services/integrity/pipeline.py:27-158`

이전처럼 Step 1.5 grouping이 메인 경로에 필수로 끼어 있지는 않다. 따라서 이전 보고서의 “Step 1.5 결과가 실제 pipeline과 불일치한다”는 지적은 active path 기준으로는 우선순위가 내려갔다.

### C. Step 2 career output 스키마는 이전보다 정합적이다

현재 career normalization 출력 스키마는 `careers` 배열 기준이다.

근거: `candidates/services/integrity/step2_normalize.py:56-82`

이전 점검 때의 `"career"` 단건 출력 전제는 현재 코드 기준으로는 주 이슈가 아니다.

---

## 3. 여전히 남아 있는 핵심 리스크

### HIGH 1. 새 버전 이력서가 들어와도 기존 후보자를 갱신하지 않고 새 Candidate를 만들 수 있다

근거:

- 사람 그룹 primary는 최신 modified_time 파일이다. `candidates/services/filename_parser.py:103-107`
- `import_resumes`는 primary file id만 기준으로 기존 그룹을 건너뛴다. `candidates/management/commands/import_resumes.py:204-210`
- 저장은 기존 후보자 조회 없이 항상 새 Candidate를 생성한다. `candidates/services/integrity/save.py:85-119`

영향:

- 같은 사람의 새 이력서 버전이 들어오면 기존 후보자 업데이트 대신 새 후보자가 생길 수 있다.
- 이 문제는 여전히 데이터 정합성 측면에서 가장 크다.

### HIGH 2. integrity 경로는 여전히 성공 시 사실상 `pass / 0.9 / auto_confirmed`로 수렴한다

근거:

- integrity 결과가 `None`이 아니면 diagnosis를 고정값으로 만든다. `candidates/services/retry_pipeline.py:80-91`
- 저장 시 이 diagnosis로 validation status를 계산한다. `candidates/services/integrity/save.py:64-80`

영향:

- integrity flags가 많아도 후보자가 자동 확인 상태가 될 수 있다.
- 검수 파이프라인에서 가장 중요한 “사람이 다시 봐야 하는 후보” 분류가 약해진다.

### HIGH 3. integrity 리포트와 rule-based 리포트가 같은 타입으로 연속 저장된다

근거:

- integrity flags가 있으면 `SELF_CONSISTENCY` 리포트를 저장한다. `candidates/services/integrity/save.py:144-156`
- 직후에 `scan_candidate_discrepancies()`도 다시 `SELF_CONSISTENCY` 리포트를 만든다. `candidates/services/integrity/save.py:158-159`
- 조회는 가장 최근 `SELF_CONSISTENCY` 하나만 쓴다. `candidates/models.py:753-764`

영향:

- integrity 결과가 DB에 있어도 뒤의 rule-based 리포트에 가려질 수 있다.
- 화면에서 무엇이 보이는지 일관되지 않을 수 있다.

### MEDIUM 4. cross-version 비교는 아직 import 경로에 실제 연결되지 않았다

근거:

- pipeline과 retry layer는 `previous_data`를 받을 수 있다. `candidates/services/integrity/pipeline.py:27-30`, `candidates/services/retry_pipeline.py:13-21`
- 실제 import 호출부는 `previous_data`를 넘기지 않는다. `candidates/management/commands/import_resumes.py:302-310`

영향:

- Step 3의 cross-version 설계는 존재하지만, 실제 임포트에서는 아직 발동하지 않는다.

### MEDIUM 5. integrity import 결과는 후보자 카드/검색용 필드를 빈 값으로 저장할 가능성이 높다

근거:

- integrity pipeline 최종 반환값에는 `current_company`, `current_position`, `summary`, `core_competencies`가 없다. `candidates/services/integrity/pipeline.py:137-157`
- 저장 함수는 이 키를 그대로 Candidate 필드에 반영한다. `candidates/services/integrity/save.py:86-92`, `candidates/services/integrity/save.py:194-251`

영향:

- `--integrity`로 들어온 후보자는 경력/학력은 저장돼도 목록 카드와 검색용 요약 필드가 약해질 수 있다.
- `field_confidences`도 현재 빈 dict다. `candidates/services/integrity/pipeline.py:152-156`

### MEDIUM 6. validator / 보조 코드 일부는 active path와 여전히 drift가 있다

근거:

- `validate_step1_5()`는 아직 `grouping["groups"]`를 기대하지만 실제 grouping schema는 `career_groups` / `education_groups`다. `candidates/services/integrity/validators.py:103-133`, `candidates/services/integrity/step1_5_grouping.py:38-55`
- 현재 active integrity pipeline은 Step 1.5를 호출하지 않는다. `candidates/services/integrity/pipeline.py:49-158`

영향:

- 즉시 운영 장애는 아니지만, 관련 코드/테스트/설계가 완전히 정리된 상태는 아니다.
- 다음 리팩터링 때 혼선을 만들 가능성이 있다.

### LOW 7. 임포트 직후 임베딩 생성은 여전히 자동화되지 않았다

근거:

- 임베딩 생성은 별도 커맨드에서만 수행된다. `candidates/management/commands/generate_embeddings.py:24-47`
- import 경로에서는 연결이 없다.

영향:

- 추출 완료 직후 semantic search 반영까지 추가 실행 단계가 필요하다.

---

## 4. 이전 보고서 대비 상태 변화

### 해소된 항목

- integrity 관련 테스트 drift 1건 해소
- extraction-related 테스트 전부 통과
- active integrity pipeline에서 Step 1.5 의존 제거
- career normalization 출력 스키마 일부 정합성 개선

### 아직 남은 항목

- Candidate 중복 생성 가능성
- integrity 경로의 검수 분류 약화
- integrity / rule-based 리포트 충돌
- cross-version 미연결
- integrity 결과의 요약 필드 부족

---

## 5. 최종 의견

수정 반영으로 테스트 상태와 integrity 경로 구조는 분명 좋아졌다. 다만 지금 단계에서 “데이터 추출 전과정이 완전히 정리됐다”고 보기는 어렵다.

현재 우선순위는 여전히 아래 순서가 맞다.

1. 기존 후보자 갱신 전략과 중복 생성 방지
2. integrity 결과를 validation status에 반영하는 기준 재설계
3. integrity 리포트와 rule-based 리포트의 저장/조회 정책 분리
4. cross-version 입력 연결

실무 기준으로는 legacy 경로는 계속 점검 대상이 될 수 있지만, `--integrity`는 아직 운영 기본값으로 돌리기보다 실험/검증 단계로 유지하는 편이 안전하다.
