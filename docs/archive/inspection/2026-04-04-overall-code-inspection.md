# 전체 코드 점검 보고서

**일자:** 2026-04-04  
**브랜치:** `main`  
**점검 범위:** 최근 개발 반영분 전체 점검. 특히 `candidates` 중심 저장 경로, 검색/리뷰 화면, 운영 추적성, 설정/라우팅 정리 상태를 우선 검토했다.

---

## 1. 요약

현재 코드베이스는 큰 폭의 정리와 기능 반영이 함께 들어간 상태다.

- `contacts`, `meetings`, `intelligence` 앱이 제거되고, 서비스 범위가 `candidates` 중심으로 단순화되었다.
- 데이터 추출 저장 경로에는 `current_resume`, `compared_resume`, 동일인 식별, update path가 실제로 반영되었다.
- 검색은 SQL 생성 방식에서 structured filters + ORM 방식으로 전환되었다.
- 전체 테스트는 통과했다.

재실행 결과:

- `uv run pytest -q` → `282 passed`
- `uv run python manage.py check` → 문제 없음

다만 코드 완성도 관점에서 보면, 아래 5개 이슈는 아직 남아 있다.

---

## 2. 주요 점검 사항

### HIGH 1. cross-version 비교 기준과 저장 provenance 기준이 서로 다르다

근거:

- import 단계에서 integrity 비교 입력은 `_find_previous_data()`로 계산한다. [`import_resumes.py:302-315`](/home/work/synco/candidates/management/commands/import_resumes.py#L302)
- 이 함수는 email/phone이 없으면 이름 + 생년 기반 fallback을 쓴다. [`import_resumes.py:349-376`](/home/work/synco/candidates/management/commands/import_resumes.py#L349)
- 저장 단계에서는 별도로 `identify_candidate(extracted)`를 다시 호출해 `compared_resume`를 정한다. [`save.py:78-82`](/home/work/synco/candidates/services/integrity/save.py#L78)
- `identify_candidate()`는 email/phone만으로만 동일인을 판정한다. [`candidate_identity.py:29-65`](/home/work/synco/candidates/services/candidate_identity.py#L29)

문제:

- integrity flags는 A 후보자 데이터와 비교해서 생성됐는데,
- 저장된 `DiscrepancyReport.compared_resume`는 B 후보자 resume이거나 `None`일 수 있다.

영향:

- cross-version 리포트의 근거 사슬이 깨질 수 있다.
- 운영자가 “무엇과 비교해서 나온 경고인지” 신뢰하기 어려워진다.

권장 조치:

- import 단계에서 식별 결과를 한 번만 결정하고, 그 결과를 integrity pipeline과 save 단계가 함께 사용하도록 구조를 통일한다.
- `previous_data`, `matched_candidate`, `compared_resume`를 같은 source of truth에서 파생시켜야 한다.

### MEDIUM 2. update path의 Candidate overwrite 정책이 아직 명확히 정리되지 않았다

근거:

- `_update_candidate()`는 대부분 필드를 `new_value or old_value` 방식으로 갱신한다. [`save.py:274-335`](/home/work/synco/candidates/services/integrity/save.py#L274)

예:

- `candidate.email = extracted.get("email") or candidate.email`
- `candidate.current_company = extracted.get("current_company") or candidate.current_company`
- `candidate.awards = ... or candidate.awards`

문제:

- 최신 이력서에서 값이 비어 있거나 제거된 경우에도 과거 값이 계속 남는다.
- 현재 구현은 `current_resume`로 최신 대표 Resume를 가리키지만, `Candidate` 대표 프로필을 최신 문서 기준으로 완전 overwrite할지, 일부 필드만 누적 보존할지 정책이 코드에 명시적으로 정리돼 있지 않다.

영향:

- 후보자 상세와 검색 인덱스가 “최신 Resume 스냅샷”이라기보다 “과거 값이 일부 남아 있는 누적 상태”가 될 수 있다.
- 특히 연락처, 현재 회사, 프로젝트, 수상 내역처럼 최신 이력서에서 빠진 값을 어떻게 처리할지 팀 합의가 없으면 운영 해석이 흔들릴 수 있다.

권장 조치:

- 필드별 overwrite 정책표를 만든다.
- `Candidate` 대표 프로필을 “최신 Resume 스냅샷”으로 볼지, “운영용 누적 프로필”로 볼지 먼저 결정한다.
- 최신 Resume 기준 동기화를 목표로 한다면, 기본은 overwrite로 두고 누적 보존이 필요한 필드만 예외 merge하는 편이 안전하다.

### MEDIUM 3. `current_resume`와 `is_primary`가 병행되어 대표 Resume 기준이 이원화돼 있다

근거:

- 모델에는 `Candidate.current_resume`가 추가됐다. [`models.py:196-203`](/home/work/synco/candidates/models.py#L196)
- 저장 시에도 `candidate.current_resume = primary_resume`를 설정한다. [`save.py:120-121`](/home/work/synco/candidates/services/integrity/save.py#L120)
- 새 Resume 저장 시 매번 `is_primary=True`가 설정되지만, 이전 primary를 내리는 로직은 없다. [`save.py:107-118`](/home/work/synco/candidates/services/integrity/save.py#L107)
- 검수 상세와 후보자 상세는 여전히 `is_primary=True` resume를 조회한다. [`views.py:116`](/home/work/synco/candidates/views.py#L116), [`views.py:317`](/home/work/synco/candidates/views.py#L317)
- diagnosis도 `candidate` 기준 첫 건만 가져온다. [`views.py:325`](/home/work/synco/candidates/views.py#L325)
- `Resume` 기본 정렬은 `-is_primary`, `-version`이다. [`models.py:809-811`](/home/work/synco/candidates/models.py#L809)

문제:

- canonical pointer는 `current_resume`로 도입됐지만, 읽기 경로는 여전히 `is_primary`와 candidate-level diagnosis를 함께 사용한다.
- 그 결과 대표 Resume의 source of truth가 하나로 정리되지 않았고, `is_primary`는 시간이 갈수록 의미가 약해진다.

영향:

- 현재 정렬상 최신 primary가 먼저 잡힐 가능성은 높지만, 이는 우연히 맞아떨어지는 동작에 가깝다.
- 이후 backfill, 수동 수정, 다른 저장 경로가 추가되면 최신 대표 Resume와 화면 표시 기준이 어긋날 위험이 있다.

권장 조치:

- detail/review 화면은 `candidate.current_resume` 우선 조회로 바꾼다.
- `ValidationDiagnosis`도 `resume=candidate.current_resume` 기준으로 가져오도록 맞춘다.
- `is_primary`는 import 묶음 메타데이터로만 남기거나, 계속 유지할 거면 단일 primary invariant를 강제해야 한다.

### MEDIUM 4. 전화번호 정규화가 국제번호 케이스를 처리하지 못한다

근거:

- 현재 `_normalize_phone()`는 숫자만 남긴다. [`candidate_identity.py:24-26`](/home/work/synco/candidates/services/candidate_identity.py#L24)
- 비교는 이 정규화 결과를 그대로 사용한다. [`candidate_identity.py:53-63`](/home/work/synco/candidates/services/candidate_identity.py#L53)

문제:

- `010-1234-5678`과 `+82-10-1234-5678`은 실제 같은 번호인데 현재 구현에서는 다르게 본다.

영향:

- 동일인이어도 재수입 시 자동 매칭에 실패할 수 있다.
- 그 결과 Candidate 중복이 다시 생길 수 있다.

권장 조치:

- `82` 국가번호를 `0`으로 정규화하는 로직을 추가한다.
- 국제번호, 공백, 하이픈, 괄호 포함 케이스를 테스트로 고정한다.

### MEDIUM 5. 사람 검수 이력이 어떤 Resume 버전에 대한 판단인지 기록되지 않는다

근거:

- `ExtractionLog`는 이미 `resume` FK를 갖고 있다. [`models.py:1092-1103`](/home/work/synco/candidates/models.py#L1092)
- 하지만 `review_confirm()`과 `review_reject()`는 `candidate`만 기록하고 `resume`은 비워 둔다. [`views.py:148-156`](/home/work/synco/candidates/views.py#L148), [`views.py:169-177`](/home/work/synco/candidates/views.py#L169)

문제:

- 다중 Resume 후보자에서 “어느 버전을 사람이 승인/반려했는지” 알 수 없다.

영향:

- 운영 감사 추적성이 약하다.
- 같은 Candidate에 새 Resume가 들어온 뒤 이전 검수 이력을 해석하기 어려워진다.

권장 조치:

- confirm/reject 시 `candidate.current_resume`를 함께 로그에 저장한다.
- 검수 상태 변경도 candidate-level 상태와 resume-level 판단을 분리할지 검토할 필요가 있다.

---

## 3. 긍정적 확인 사항

이번 변경에서 분명히 좋아진 점도 있다.

### A. 저장 update path가 실제로 반영됐다

- 같은 email/phone이면 기존 Candidate를 재사용한다. [`save.py:80-98`](/home/work/synco/candidates/services/integrity/save.py#L80)
- 새 Resume는 버전 증가 형태로 누적된다. [`save.py:102-117`](/home/work/synco/candidates/services/integrity/save.py#L102)
- `compared_resume`도 저장된다. [`save.py:197-205`](/home/work/synco/candidates/services/integrity/save.py#L197)

### B. 검색 구조가 더 안전해졌다

- SQL 생성/실행 방식이 제거되고 structured filter + ORM 쿼리 방식으로 바뀌었다. [`search.py`](/home/work/synco/candidates/services/search.py)
- 이 전환은 SQL 안전성, 테스트 용이성, 유지보수성 측면에서 긍정적이다.

### C. 서비스 범위가 단순화됐다

- `accounts` 홈이 후보자 목록으로 바로 연결되고, 삭제된 앱 라우트도 정리됐다. [`accounts/views.py`](/home/work/synco/accounts/views.py), [`main/urls.py`](/home/work/synco/main/urls.py)
- 현재 내비게이션도 남은 구조와 일치한다. [`nav_sidebar.html`](/home/work/synco/templates/common/nav_sidebar.html), [`nav_bottom.html`](/home/work/synco/templates/common/nav_bottom.html)

---

## 4. 테스트 및 검증 결과

실행 결과:

- `uv run pytest -q` → `282 passed`
- `uv run pytest -q tests/test_import_pipeline.py tests/test_retry_pipeline.py tests/test_search_service.py tests/test_search_views.py tests/test_candidates_models.py` → `54 passed`
- `uv run pytest -q tests/test_save_update_path.py tests/test_candidate_identity.py` → `18 passed`
- `uv run python manage.py check` → `System check identified no issues`

해석:

- 현재 브랜치에는 즉시 드러나는 실패는 없다.
- 다만 위 5개 이슈는 테스트가 주로 “성공 경로”를 검증하기 때문에 통과 상태로 남아 있는 설계/운영 정합성 문제다.

---

## 5. 우선순위 제안

1. cross-version 비교 기준과 `compared_resume` 저장 기준을 단일화
2. `_update_candidate()`를 최신 Resume 기준 overwrite 정책으로 재정의
3. detail/review/diagnosis 조회를 `current_resume` 기준으로 전환
4. phone 국제번호 정규화 보강
5. confirm/reject 로그에 `resume` 연결

---

## 6. 최종 의견

현재 구현은 **기능적으로는 안정적이고 테스트도 잘 통과하는 상태**다.  
하지만 **운영 추적성과 최신 Resume 기준 대표 프로필 일관성**은 아직 마무리되지 않았다.

따라서 다음 단계는 새로운 기능 추가보다,

- 저장 기준 통일
- 읽기 경로 정렬
- 검수 이력 추적성 보강

에 집중하는 것이 맞다.
