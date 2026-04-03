# 데이터 추출 저장 정책 재점검 및 운영 전환 개발 계획

**일자:** 2026-04-03  
**목적:** 수정된 코드를 다시 검토한 뒤, 남아 있는 저장 정책 이슈를 정리하고 운영 전환까지 포함한 개발 계획을 수립한다.  
**범위:** `import_resumes`, legacy/integrity 공통 저장 경로, 동일인 판정, `Candidate`/`Resume` 역할, 검증/리포트 저장, 화면 호환성, 백필/중복 정리, 배포/롤백 계획

---

## 1. 결론

현재 시스템은 **추출 파이프라인 자체는 충분히 올라와 있지만, 저장 정책은 아직 “운영 완성형”이 아니다.**

이번 점검 기준 최종 판단은 다음과 같다.

- extraction, validation, discrepancy 생성은 실사용 가능한 수준이다.
- 하지만 import 이후 persistence는 아직 “사람 단위 관리”보다 “입력 건 단위 생성”에 더 가깝다.
- 따라서 다음 개발 우선순위는 모델을 크게 갈아엎는 것이 아니라,
  **`Candidate = 사람`, `Resume = 버전` 정책으로 저장 경로를 고정하고 운영 전환을 안전하게 수행하는 것**이다.

권장 목표 상태:

- `Candidate`: 현재 대표 프로필
- `Resume`: 버전별 원문/파일 기록
- `ValidationDiagnosis`: 특정 Resume 기준 진단
- `DiscrepancyReport`: 특정 Resume 기준 리포트
- 동일인 판정 성공 시 새 Resume를 추가하고 기존 Candidate를 업데이트

---

## 2. 다시 확인한 현재 코드 상태

### 2.1 import 경로는 legacy/integrity 모두 같은 저장 함수로 수렴한다

- [`import_resumes.py:308`](/home/work/synco/candidates/management/commands/import_resumes.py#L308) 에서 `run_extraction_with_retry()`를 호출한다.
- [`import_resumes.py:335`](/home/work/synco/candidates/management/commands/import_resumes.py#L335) 에서 결과를 항상 `save_pipeline_result()`로 저장한다.

의미:

- 저장 정책 개선은 integrity 전용 이슈가 아니다.
- `save_pipeline_result()`를 바꾸면 legacy / integrity import 모두 영향을 받는다.

### 2.2 이전 버전 비교 입력은 실제로 연결되어 있다

- [`import_resumes.py:302`](/home/work/synco/candidates/management/commands/import_resumes.py#L302) 에서 integrity 모드일 때 `_find_previous_data()`를 호출한다.
- [`import_resumes.py:315`](/home/work/synco/candidates/management/commands/import_resumes.py#L315) 에서 `previous_data`를 전달한다.
- [`retry_pipeline.py:60`](/home/work/synco/candidates/services/retry_pipeline.py#L60) 에서 integrity pipeline이 이를 사용한다.

의미:

- cross-version 비교 자체는 이미 동작 중이다.
- 문제는 비교 대상 식별과 저장 provenance다.

### 2.3 저장 시 생성되는 주요 레코드는 이미 충분하다

- [`save.py:95`](/home/work/synco/candidates/services/integrity/save.py#L95) 에서 `Resume` 생성
- [`save.py:122`](/home/work/synco/candidates/services/integrity/save.py#L122) 에서 `ExtractionLog` 생성
- [`save.py:132`](/home/work/synco/candidates/services/integrity/save.py#L132) 에서 `ValidationDiagnosis` 생성
- [`save.py:182`](/home/work/synco/candidates/services/integrity/save.py#L182) 에서 `DiscrepancyReport` 생성

의미:

- 추가로 필요한 것은 레코드 종류가 아니라, 레코드 간 참조와 update semantics다.

### 2.4 버전/비교 필드를 위한 모델 기반은 이미 있다

- [`models.py:767`](/home/work/synco/candidates/models.py#L767) `Resume`
- [`models.py:1087`](/home/work/synco/candidates/models.py#L1087) `ExtractionLog.resume`
- [`models.py:1196`](/home/work/synco/candidates/models.py#L1196) `DiscrepancyReport.source_resume`
- [`models.py:1203`](/home/work/synco/candidates/models.py#L1203) `DiscrepancyReport.compared_resume`
- [`models.py:1300`](/home/work/synco/candidates/models.py#L1300) `ValidationDiagnosis.resume`

의미:

- 데이터 모델을 새로 만들지 않아도 운영 전환 1차 작업은 가능하다.

### 2.5 저장 경로 관련 재실행 테스트

이번 점검에서 아래 테스트를 다시 실행했다.

- `tests/test_import_pipeline.py`
- `tests/test_retry_pipeline.py`
- `tests/test_integrity_pipeline.py`
- `tests/test_integrity_cross_version.py`

결과:

- `40 passed`

해석:

- 현재 동작이 깨진 것은 아니다.
- 하지만 테스트가 “운영 전환 시 꼭 필요한 경계 조건”을 충분히 막고 있지는 않다.

---

## 3. 남아 있는 핵심 문제

### 3.1 동일인 판정 로직이 update 대상 식별용으로는 약하다

현재 `_find_previous_data()`는 [`import_resumes.py:349`](/home/work/synco/candidates/management/commands/import_resumes.py#L349) 이후
이름을 먼저 보고, 있으면 birth year를 추가 필터로 거는 수준이다.

문제:

- 동명이인 오매칭 가능
- 이름 표기/생년 누락 시 동일인 누락 가능
- 현재 함수는 “비교용 후보 추정”에는 쓸 수 있지만 “업데이트 대상 확정”에는 부족

### 3.2 저장 함수는 여전히 새 Candidate 생성 중심이다

- [`save.py:86`](/home/work/synco/candidates/services/integrity/save.py#L86) 이후 트랜잭션에서
  [`save.py:87`](/home/work/synco/candidates/services/integrity/save.py#L87) `_create_candidate()`를 항상 호출한다.

문제:

- 동일인이어도 기존 Candidate를 갱신하지 않는다.
- 결과적으로 Resume version 누적이 아니라 Candidate 중복 누적이 되기 쉽다.

### 3.3 대표 Resume 개념이 코드에 명시적으로 없다

현재 화면은 대표 Resume를 다음처럼 찾는다.

- [`views.py:116`](/home/work/synco/candidates/views.py#L116) `review_detail`: `candidate.resumes.filter(is_primary=True).first()`
- [`views.py:317`](/home/work/synco/candidates/views.py#L317) `candidate_detail`: 동일

문제:

- `is_primary`는 현재 import 묶음의 대표 파일 의미에 가깝다.
- “현재 Candidate 프로필의 기준 Resume”라는 의미와는 다를 수 있다.
- update path가 생기면 `is_primary`만으로는 운영 의미가 모호해진다.

### 3.4 diagnosis / review 화면도 Resume 기준으로 완전히 정렬되어 있지 않다

- [`views.py:325`](/home/work/synco/candidates/views.py#L325) 에서 `ValidationDiagnosis.objects.filter(candidate=candidate).first()`를 쓴다.

문제:

- 현재는 “가장 최근 diagnosis”를 우연히 잡는 구조다.
- 향후 Resume가 여러 개 쌓이면 “현재 대표 Resume의 diagnosis”를 명시적으로 선택해야 한다.

### 3.5 review/search 화면은 SELF_CONSISTENCY 리포트만 본다

- [`views.py:58`](/home/work/synco/candidates/views.py#L58)
- [`search.py:291`](/home/work/synco/candidates/services/search.py#L291)
- [`models.py:676`](/home/work/synco/candidates/models.py#L676)
- [`models.py:753`](/home/work/synco/candidates/models.py#L753)

문제:

- 현재 UI는 `SELF_CONSISTENCY`만 prefetch/집계한다.
- 향후 `CROSS_VERSION` 리포트를 분리 생성하면 화면에 바로 반영되지 않는다.

즉, cross-version을 더 정교하게 저장하려면
**데이터 저장 변경과 화면 호환 전략을 같이 설계해야 한다.**

### 3.6 compared_resume 필드는 준비돼 있지만 실제 저장되지 않는다

- [`models.py:1203`](/home/work/synco/candidates/models.py#L1203) 에 필드가 있으나,
- [`save.py:182`](/home/work/synco/candidates/services/integrity/save.py#L182) 저장 시 값이 비어 있다.

문제:

- 운영자가 “무엇과 비교해서 나온 경고인지” 복원하기 어렵다.

### 3.7 관리자 도구도 버전 운영 기준으로는 아직 부족하다

- [`admin.py:25`](/home/work/synco/candidates/admin.py#L25) Resume inline은 `is_primary`만 노출
- [`admin.py:76`](/home/work/synco/candidates/admin.py#L76) Resume admin도 `version`, `is_primary`만 중심

문제:

- current resume
- compared resume
- 동일인 후보
- 중복 정리 상태

같은 운영 핵심 정보가 보이지 않는다.

---

## 4. 목표 설계

### 4.1 단기 목표 설계

단기적으로 가장 현실적인 구조는 다음과 같다.

- `Candidate`: 사람 단위 대표 프로필
- `Resume`: 같은 사람에게 들어온 이력서 버전
- `Candidate.current_resume`: 현재 프로필의 기준 Resume
- `ValidationDiagnosis.resume`: 해당 Resume에 대한 진단
- `DiscrepancyReport.source_resume`: 현재 분석한 Resume
- `DiscrepancyReport.compared_resume`: 비교한 이전 Resume

핵심 원칙:

1. 새 이력서 유입 시 항상 새 Resume 생성
2. 동일인 판정 성공 시 기존 Candidate 재사용
3. 채택된 Resume 기준으로 Candidate 갱신
4. 진단과 리포트는 Resume 기준으로 저장
5. 화면은 Candidate를 보여주되, 근거는 current_resume / compared_resume로 추적

### 4.2 중장기 설계

중장기적으로는 `CandidateIdentity` 분리가 가장 깔끔하다.
하지만 현재 단계에서는 아래 이유로 보류해도 된다.

- 현재 모델만으로도 1차 운영 안정화 가능
- 지금 중요한 것은 identity entity 신설보다 update persistence와 운영 가시성 확보

따라서 본 계획은 **현 모델 유지 + 저장 정책 정비 + 운영 전환**에 집중한다.

---

## 5. 개발 계획

### P0. 저장 정책 명세 고정

**목표**

- 팀 내 합의 문장 자체를 코드와 문서에 고정한다.

**정책**

- `Candidate = 사람`
- `Resume = 버전`
- import 성공 시 항상 Resume 생성
- 동일인 판정 성공 시 Candidate 업데이트
- 동일인 판정 불충분 시 새 Candidate 생성

**작업**

- [`save.py`](/home/work/synco/candidates/services/integrity/save.py) docstring 갱신
- [`import_resumes.py`](/home/work/synco/candidates/management/commands/import_resumes.py) 주석/함수명 정리
- 테스트 이름을 정책 중심으로 재작성

**완료 기준**

- 개발자 누구라도 저장 정책을 다르게 해석할 여지가 없다.

### P1. 동일인 식별 서비스 분리

**목표**

- `_find_previous_data()`를 “비교용 dict 조회”에서 “식별 서비스”로 승격한다.

**권장 새 함수**

- `identify_candidate(extracted_or_parsed) -> MatchResult`

**권장 반환값**

- `matched_candidate`
- `compared_resume`
- `match_reason`
- `confidence`

**권장 판정 순서**

1. email exact match
2. phone normalized match
3. name + career overlap
4. name + education overlap
5. name + birth_year
6. name only -> 자동 병합 금지

**작업 위치**

- 신규 service: `candidates/services/candidate_identity.py`
- 호출부: [`import_resumes.py`](/home/work/synco/candidates/management/commands/import_resumes.py)

**구현 메모**

- filename parser 정보는 보조 신호로만 사용
- 자동 병합은 보수적으로
- `previous_data`는 `matched_candidate/current_resume`에서 파생

### P2. save path에 update branch 추가

**목표**

- 동일인인 경우 기존 Candidate 아래로 Resume를 누적한다.

**권장 시그니처**

- `save_pipeline_result(..., matched_candidate=None, compared_resume=None, match_reason="")`

**동작**

- `matched_candidate is None`: 새 Candidate 생성
- `matched_candidate exists`: 기존 Candidate 재사용
- 항상 새 Resume 생성
- Candidate 기본 필드, detail fields, 하위 정규화 레코드 갱신
- `current_resume`를 방금 채택된 Resume로 변경

**작업 위치**

- [`save.py`](/home/work/synco/candidates/services/integrity/save.py)

**구현 방식 권장**

- update 시 `Career`, `Education`, `Certification`, `LanguageSkill`는
  “current_resume 기준 스냅샷”으로 보고 재구성
- 수동 수정 보존 요구가 생기면 그때 provenance/override 모델을 분리

### P3. Candidate에 current_resume 추가

**목표**

- 현재 대표 프로필의 기준 문서를 명시한다.

**스키마**

- `Candidate.current_resume = FK(Resume, null=True, blank=True, on_delete=SET_NULL)`

**영향 코드**

- [`models.py`](/home/work/synco/candidates/models.py)
- [`views.py:116`](/home/work/synco/candidates/views.py#L116), [`views.py:317`](/home/work/synco/candidates/views.py#L317)
- [`admin.py`](/home/work/synco/candidates/admin.py)

**호환 전략**

- 1차: `current_resume` 우선, 없으면 `is_primary=True` fallback
- 2차: backfill 완료 후 `is_primary` 의존 제거

### P4. compared_resume 저장

**목표**

- cross-version 근거를 DB에 남긴다.

**작업**

- 식별 서비스가 선택한 이전 Resume를 `save_pipeline_result()`로 전달
- `DiscrepancyReport.objects.create(... compared_resume=...)` 반영

**참고**

- 현재 UI가 `SELF_CONSISTENCY`만 읽기 때문에,
  1차 전환에서는 기존 report_type을 유지한 채 `compared_resume`만 채우는 방식이 안전하다.

### P5. version / primary semantics 재정의

**목표**

- version 증가 규칙과 `is_primary` 의미를 분리한다.

**권장 규칙**

- `version`: Candidate 아래 누적 증가
- `is_primary`: import 묶음 내 대표 파일 여부 또는 deprecated
- `current_resume`: 현재 프로필 기준 Resume

**이유**

- 현재 [`save.py:103`](/home/work/synco/candidates/services/integrity/save.py#L103), [`save.py:118`](/home/work/synco/candidates/services/integrity/save.py#L118) 의
  `version=1`, `idx+2`는 새 Candidate 생성 전제다.
- update 구조에서는 기존 누적 버전 기준으로 계산해야 한다.

### P6. validation / review 흐름 Resume 기준화

**목표**

- 검수 상태와 로그가 현재 대표 Resume와 정렬되게 만든다.

**작업**

- 상세 화면의 primary resume 조회를 `candidate.current_resume` 우선으로 변경
- [`views.py:325`](/home/work/synco/candidates/views.py#L325) diagnosis 조회를 current resume 기준으로 변경
- `review_confirm`, `review_reject` 시 `ExtractionLog.resume`에 current resume 연결

**효과**

- 운영자가 “무엇을 승인/반려했는지” 추적 가능
- 다중 Resume 후보자에서도 검수 이력이 덜 혼동됨

### P7. 리포트 타입 전환 전략 결정

이 부분은 운영 호환성과 직접 연결된다.

**권장 1차안**

- 현행처럼 `SELF_CONSISTENCY` 단일 리포트를 유지
- 단, `compared_resume`를 함께 저장해 cross-version provenance 확보

장점:

- [`views.py:58`](/home/work/synco/candidates/views.py#L58), [`search.py:291`](/home/work/synco/candidates/services/search.py#L291), [`models.py:676`](/home/work/synco/candidates/models.py#L676)
  등 기존 화면 로직을 거의 안 건드려도 됨

**권장 2차안**

- `SELF_CONSISTENCY`와 `CROSS_VERSION` 리포트 분리 생성
- review/search/detail 화면이 두 리포트를 함께 집계하도록 변경

이번 전환의 1차 범위에서는 **1차안이 더 안전하다.**

### P8. 관리자/운영 도구 보강

**목표**

- 중복 정리와 전환 이후 운영이 가능하도록 admin/command를 보강한다.

**필수 보강**

- Candidate admin에 `current_resume` 표시
- Resume admin에 `candidate`, `version`, `is_primary`, `processing_status`, `created_at` 강화
- DiscrepancyReport admin에 `source_resume`, `compared_resume` 노출

**권장 추가 도구**

- `find_duplicate_candidates` management command
- `merge_candidates` management command 또는 admin action

---

## 6. 운영 전환 계획

### 6.1 전환 원칙

- 기존 화면을 깨지 않으면서 점진적으로 전환
- 스키마 추가 → 호환 코드 → 백필 → 저장 경로 전환 → 중복 정리 → 최종 정리 순서 유지
- 한 번에 semantics를 바꾸지 말고 fallback 기간을 둔다

### 6.2 단계별 전환

#### 1단계. 스키마 추가

추가 권장:

- `Candidate.current_resume`

보류 가능:

- identity 분리 엔티티

이 단계에서는 기존 동작을 바꾸지 않는다.

#### 2단계. 읽기 경로 호환화

변경:

- review/detail/search에서 current resume 우선 조회
- 없으면 기존 `is_primary` fallback

대상:

- [`views.py:116`](/home/work/synco/candidates/views.py#L116)
- [`views.py:317`](/home/work/synco/candidates/views.py#L317)
- [`views.py:325`](/home/work/synco/candidates/views.py#L325)
- admin 표시

목표:

- 스키마만 추가된 상태에서도 운영 화면이 깨지지 않게 함

#### 3단계. 백필

필수 백필:

- 기존 Candidate의 `current_resume` 채우기

권장 백필 규칙:

1. `is_primary=True` Resume가 있으면 그 Resume를 current resume로 지정
2. 없으면 version 최고값 Resume
3. 그것도 없으면 생성일 최신 Resume
4. Resume가 아예 없으면 null 유지 후 점검 대상 목록화

추가 백필 가능:

- current_resume 기준으로 validation summary 재정렬 점검

권장 구현:

- 신규 command: `backfill_current_resume`
- `--dry-run` 지원
- 변경 건수 / null 건수 / 다중 primary 건수 출력

#### 4단계. 저장 경로 전환

변경:

- `identify_candidate()` 도입
- `save_pipeline_result()` update branch 활성화
- `compared_resume` 저장

권장 배포 방식:

- feature flag 또는 command option으로 단계적 활성화
  예: `--update-existing-candidate`

이유:

- 운영 환경에서 바로 전체 폴더에 적용하기보다 일부 카테고리로 검증 가능

#### 5단계. 중복 후보자 탐지 및 정리

전환 후에도 기존 중복 Candidate는 남아 있을 수 있다.

필수 작업:

- 이름/생년/email/phone/경력 중복 기반 후보 리스트 생성
- 수동 병합 대상과 자동 병합 가능 대상을 분리

권장 산출물:

- `duplicate_candidates_report.csv`
- `high_confidence_duplicate_groups.json`

자동 병합은 보수적으로:

- email/phone 일치 수준만 자동 후보
- name only는 절대 자동 병합 금지

#### 6단계. 화면/운영 기준 전환 완료

완료 조건:

- detail/review/search가 current resume 기준으로 동작
- current_resume 백필 완료
- compared_resume 저장 확인
- 중복 정리 1차 완료

이후:

- `is_primary`를 UI 대표성 판단 근거에서 제거
- 필요하면 report type 분리 2차 착수

---

## 7. 백필 및 데이터 정리 계획

### 7.1 백필 대상

1. `Candidate.current_resume`
2. 필요 시 `Resume.version` 정렬/재부여 검증
3. `compared_resume`는 과거 데이터는 대부분 복원 불가하므로 신규 데이터부터 보장

### 7.2 중복 정리 원칙

- 기존 Candidate 두 개를 합칠 때 “남길 Candidate”를 먼저 고른다.
- 보통 `current_resume`가 더 최신이고, 데이터가 더 풍부한 쪽을 survivor로 선정한다.
- 다른 쪽의 Resume, ExtractionLog, Diagnosis, DiscrepancyReport를 survivor로 재연결한다.
- 하위 Career/Education 등은 survivor의 current resume 기준으로 재구성한다.

### 7.3 merge 도구에 필요한 기능

`merge_candidates <source_id> <target_id> --dry-run`

해야 할 일:

- source resumes를 target으로 이동
- logs/diagnoses/reports candidate FK 이동
- source/current resume 충돌 해결
- target profile 재계산
- source candidate 비활성화 또는 삭제

주의:

- 자동 실행 전 dry-run 필수
- 합병 이력 로그 남기기

---

## 8. 테스트 계획

### 8.1 필수 신규 테스트

1. 동일인 strong match 시 기존 Candidate 재사용
2. name-only 동명이인 비병합
3. 새 Resume 저장 시 version 증가
4. update 후 current_resume 갱신
5. review/detail 화면이 current_resume 우선 사용
6. diagnosis 조회가 current_resume 기준
7. `DiscrepancyReport.compared_resume` 저장
8. 기존 화면이 fallback(`is_primary`)으로도 동작
9. merge/backfill command dry-run 결과 검증

### 8.2 권장 테스트 파일

- 기존 확장: [`tests/test_import_pipeline.py`](/home/work/synco/tests/test_import_pipeline.py)
- 신규: `tests/test_candidate_identity.py`
- 신규: `tests/test_integrity_save_update.py`
- 신규: `tests/test_resume_backfill.py`
- 신규: `tests/test_candidate_merge.py`
- 기존 보강: detail/review view tests

---

## 9. 릴리즈 체크리스트

배포 전:

- 마이그레이션 생성 및 검토
- 읽기 경로 fallback 동작 확인
- 백필 dry-run 결과 검토
- duplicate report 샘플 점검
- 일부 카테고리 canary 실행 계획 수립

배포 중:

- 스키마 배포
- 읽기 경로 배포
- 백필 실행
- canary import 실행
- 중복 증가 여부 모니터링

배포 후:

- Candidate 증가 수 vs Resume 증가 수 비교
- `current_resume is null` 건수 모니터링
- 동일 이름 중복 Candidate 증가율 확인
- validation status 분포 점검
- review 화면 샘플 확인

---

## 10. 롤백 계획

문제가 생기면 아래 순서로 대응한다.

1. update path feature flag off
2. import를 기존 “새 Candidate 생성” 모드로 임시 복귀
3. 읽기 경로는 `current_resume` fallback 유지
4. 백필된 `current_resume`는 남겨도 무방
5. merge 실행분은 별도 로그 기준으로 수동 복구

즉, **스키마 추가와 읽기 호환화는 롤백 비용이 낮고, 실제 위험 구간은 update path 활성화와 merge 실행**이다.

---

## 11. 권장 실행 순서

1. `current_resume` 필드 추가
2. detail/review/admin 읽기 경로를 current_resume 우선 + is_primary fallback으로 변경
3. `backfill_current_resume` 커맨드 작성 및 dry-run
4. `identify_candidate()` 서비스 작성
5. `save_pipeline_result()` update branch 추가
6. `compared_resume` 저장
7. 저장 정책 테스트 추가
8. canary category로 import 검증
9. duplicate report 생성
10. merge 도구 작성 및 수동 정리
11. 안정화 후 `is_primary` 의존 축소

---

## 12. 개발자 전달 요약

지금 필요한 것은 extraction을 더 고도화하는 작업이 아니다.
남은 본질은 저장 정합성과 운영 전환이다.

핵심 액션은 세 가지다.

1. 동일인 식별을 import 저장의 첫 단계로 만든다.
2. Candidate는 재사용하고 Resume는 누적한다.
3. current resume / compared resume를 중심으로 운영 추적성을 확보한다.

한 줄 요약:

**다음 단계의 목표는 “더 잘 뽑는 것”이 아니라 “같은 사람을 같은 사람으로 저장하고 운영에서 설명 가능하게 만드는 것”이다.**
