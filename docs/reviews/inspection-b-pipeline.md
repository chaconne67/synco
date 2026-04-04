# 점검 B: 데이터 파이프라인 리뷰

점검일: 2026-04-04
점검자: Pipeline Inspection Agent

---

## Critical (데이터 손실/오류)

- [candidates/services/integrity/pipeline.py:91] **ThreadPoolExecutor 내부 Gemini 호출 시 close_old_connections() 미적용.** Step 2 career/education normalization이 `ThreadPoolExecutor(max_workers=2)`로 병렬 실행되는데, 각 스레드에서 `_call_gemini()`를 호출한다. Gemini 호출 자체는 DB를 사용하지 않으므로 현재 코드에서 직접적 DB 에러는 발생하지 않지만, 만약 normalization 함수 내부에 DB 접근이 추가되면 stale connection 문제가 발생한다. 동일 패턴이 `data_extraction/services/extraction/integrity.py:740`에도 존재. 현재 구조에서는 Warning 수준이나, inner function에 DB 접근을 넣으면 즉시 Critical이 된다.

- [data_extraction/services/extraction/integrity.py:156-180] **`compare_versions()`을 `data_extraction/services/pipeline.py:156`에서 호출할 때 import 경로가 `data_extraction.services.extraction.integrity`이지만, 실제 함수는 해당 파일에 존재한다.** 이는 정상 동작하나, `candidates/services/retry_pipeline.py:156`에서는 `candidates.services.integrity.step3_cross_version.compare_versions`를 import한다. 두 경로의 `compare_versions()`는 별도 구현이지만 동일한 로직이다 -- 코드 이중화이므로 불일치 위험이 있다.

---

## Warning (잠재적 문제)

### 1. 프롬프트/스키마 3중 복사 불일치 위험

- [candidates/services/llm_extraction.py:58-132] Legacy 스키마에는 `field_confidences`, `resume_reference_date_source`, `resume_reference_date_evidence`, `company_en`, `duration_text`, `end_date_inferred`, `date_evidence`, `date_confidence`, `inferred_capabilities`, `order` 등 다수의 career 필드가 정의되어 있다.
- [candidates/services/integrity/step1_extract.py:98-149] Integrity Step 1 스키마는 career에서 `company_en`, `end_date_inferred`, `date_evidence`, `date_confidence`, `inferred_capabilities`, `achievements`, `order`, `reason_left`, `salary`를 정의하지 않는다. 이들은 Step 2 normalization에서 생성되거나 아예 지원되지 않는다.
- [data_extraction/services/extraction/prompts.py:58-132, 244-295] `data_extraction` 버전은 `candidates/services/llm_extraction.py`의 완전 복사본이다. 향후 한쪽만 수정되면 불일치가 발생한다.

세 곳에서 스키마를 각각 관리하고 있어 필드 추가/제거 시 누락 위험이 높다.

### 2. Integrity pipeline에서 Step 1 → Step 2 과정에서 career 필드 손실

- [candidates/services/integrity/step2_normalize.py:66-92] Step 2 career normalization의 출력 스키마에 `reason_left`, `salary`, `duration_text`, `end_date_inferred`, `date_evidence`, `date_confidence`, `inferred_capabilities` 필드가 없다. Step 1에서 추출한 `duration_text`는 Step 2 입력으로 전달되지만, Step 2 출력에는 포함되지 않아 정규화 후 이 데이터가 소실된다. `_create_careers()`(save.py:498-519)에서 이 필드들을 DB에 저장하려 하지만, integrity pipeline 경로에서는 항상 빈 값이 된다.

### 3. Legacy pipeline과 Integrity pipeline의 career 필드 차이

- Legacy 경로: LLM이 `company_en`, `end_date_inferred`, `date_evidence`, `date_confidence`, `inferred_capabilities`, `achievements`, `reason_left`, `salary`, `order` 모두 반환
- Integrity 경로: Step 2 정규화가 `company_en`, `duties`, `achievements`, `order`만 반환. 나머지 필드는 빈 값으로 DB에 저장됨

이로 인해 같은 이력서라도 어떤 파이프라인으로 처리하느냐에 따라 Career 레코드의 데이터 풍부도가 달라진다.

### 4. data_extraction의 save.py에서 함수명 불일치

- [data_extraction/services/save.py:74,81] `save_text_only_resume()`, `save_failed_resume()` (public 함수)
- [candidates/services/integrity/save.py:257,269] `_save_text_only_resume()`, `_save_failed_resume()` (private 함수, 언더스코어 접두)
- [data_extraction/management/commands/extract.py:492-501] `extract.py`에서 `save_failed_resume`, `save_text_only_resume` 호출
- [candidates/management/commands/import_resumes.py:415-423] `import_resumes.py`에서 `_save_failed_resume`, `_save_text_only_resume` 호출

API 이름이 다르므로 호출부 혼용 시 ImportError 발생 가능.

### 5. Gemini client가 호출마다 새로 생성

- [candidates/services/integrity/step1_extract.py:152-157] `_get_client()`가 매 호출마다 새 `genai.Client`를 생성한다. 같은 패턴이 `data_extraction/services/extraction/integrity.py:46-51`과 `data_extraction/services/extraction/gemini.py:29-33`에도 있다. API key 기반이라 치명적이지는 않으나, 불필요한 객체 생성 오버헤드가 있다.

### 6. extraction_filters와 data_extraction/filters의 완전 이중화

- [candidates/services/extraction_filters.py] 전체 파일
- [data_extraction/services/filters.py] 전체 파일

두 파일이 동일한 코드의 복사본이다. 한쪽만 수정하면 다른 경로의 파이프라인에서 다른 정규화 결과가 나온다.

### 7. validation.py 2개 파일의 완전 이중화

- [candidates/services/validation.py] 전체 파일
- [data_extraction/services/validation.py] 전체 파일

완전한 복사본으로, `compute_field_confidences()` 반환 형식(tuple), `validate_extraction()` 등 동일 로직이 양쪽에 존재한다.

---

## Info (개선 제안)

### 1. 코드 이중화 전반적 해소 필요

`data_extraction` 앱은 `candidates` 앱의 파이프라인 코드를 거의 그대로 복사해서 사용한다. 공유 가능한 코드를 추출하여 하나의 모듈로 통합하는 것이 바람직하다:
- `extraction_filters.py` / `filters.py`
- `validation.py` (양쪽)
- `save.py` (양쪽)
- `integrity/pipeline.py` / `extraction/integrity.py`
- `retry_pipeline.py` / `pipeline.py`
- `llm_extraction.py` + `gemini_extraction.py` / `extraction/prompts.py` + `extraction/gemini.py`

### 2. Step 2 normalization에서 duties/achievements 외 필드도 출력하도록 스키마 확장

- [candidates/services/integrity/step2_normalize.py:66-92] Career 출력 스키마에 `reason_left` 등 추가 필드를 넣거나, Step 1 raw data에서 직접 가져오는 fallback 로직 추가 고려.

### 3. Migration 0017 부재

- Migration 체인이 0016 -> 0018 -> 0019로 연결된다. 0017은 존재하지 않지만 dependency 체인이 정상이므로 런타임 영향은 없다. 단, 번호 갭이 혼란을 줄 수 있다.

---

## Verified OK

### 새 필드 전달 경로 (skills, personal_etc, education_etc, career_etc, skills_etc)

- **Step 1 추출 프롬프트**: `candidates/services/integrity/step1_extract.py:144-148` -- 5개 필드 모두 STEP1_SCHEMA에 정의됨
- **data_extraction 프롬프트**: `data_extraction/services/extraction/prompts.py:119-123, 290-294` -- EXTRACTION_JSON_SCHEMA와 STEP1_SCHEMA 양쪽 모두에 5개 필드 정의됨
- **Legacy 프롬프트**: `candidates/services/llm_extraction.py:119-123` -- 5개 필드 모두 정의됨
- **Pipeline 조립**: `candidates/services/integrity/pipeline.py:157-161` -- 5개 필드 모두 raw_data에서 가져와 최종 결과에 포함
- **data_extraction pipeline 조립**: `data_extraction/services/extraction/integrity.py:806-810` -- 동일하게 5개 필드 포함
- **candidates/services/integrity/save.py _create_candidate()**: 470-474행 -- 5개 필드 모두 Candidate.objects.create()에 전달
- **candidates/services/integrity/save.py _update_candidate()**: 369-373행 -- 5개 필드 모두 candidate에 설정
- **data_extraction/services/save.py _create_candidate()**: 470-474행 -- 동일하게 전달
- **data_extraction/services/save.py _update_candidate()**: 369-373행 -- 동일하게 설정
- **Legacy 필드 비우기**: 양쪽 save.py에서 `awards=[]`, `patents=[]`, `projects=[]`, `trainings=[]`, `overseas_experience=[]` 비움 확인 (create/update 양쪽)
- **DB Model**: `candidates/models.py:292-312` -- 5개 JSONField 정의됨
- **Migration**: `candidates/migrations/0019_add_skills_and_etc_fields.py` -- 5개 필드 AddField 확인

### 완성도 계산 (compute_field_confidences)

- **반환 형식**: `candidates/services/validation.py:160-256` -- `tuple[dict, dict]` (field_scores, category_scores) 반환 확인
- **호출부**: `candidates/services/retry_pipeline.py:83` -- `field_scores, category_scores = compute_field_confidences(result, {})` tuple unpack 정상
- **data_extraction 호출부**: `data_extraction/services/pipeline.py:83` -- 동일하게 tuple unpack 정상
- **validate_extraction 내부**: `candidates/services/validation.py:304` -- tuple unpack 정상
- **data_extraction validate_extraction**: `data_extraction/services/validation.py:304` -- 동일 정상

### 저장 로직 (create/update 양쪽 save.py)

- **_create_candidate()**: 양쪽 save.py 모두 새 필드 5개 저장 + legacy 필드 5개 빈 배열로 초기화 확인
- **_update_candidate()**: 양쪽 save.py 모두 새 필드 5개 설정 + legacy 필드 5개 빈 배열로 초기화 확인
- **_rebuild_sub_records()**: 양쪽 save.py 모두 educations/careers/certifications/language_skills 삭제 후 재생성 확인

### 스레드 안전성

- **close_old_connections()**: `candidates/management/commands/import_resumes.py:316-322` -- _process_group()에서 try/finally로 적용 확인
- **close_old_connections()**: `data_extraction/management/commands/extract.py:394-400` -- 동일 패턴 확인
- **Drive 서비스 인스턴스 분리**: `import_resumes.py:335`, `extract.py:413` -- 각 worker에서 `service = get_drive_service()` 호출하여 별도 인스턴스 생성 확인

### 에러 처리

- **추출 실패 시 text_only 저장**: `candidates/services/integrity/save.py:73-76` -- extracted가 None이고 raw_text가 있으면 `_save_text_only_resume()` 호출 확인
- **빈 텍스트 시 failed 저장**: `candidates/services/integrity/save.py:77-81` -- raw_text가 비어있으면 `_save_failed_resume()` 호출 확인
- **CLI 에러 처리**: `import_resumes.py:346-349` -- text extraction 빈 결과 시 _save_failed_resume 호출 확인
- **CLI 에러 처리**: `import_resumes.py:362-369` -- extraction 실패 시 _save_text_only_resume 호출 확인

### 동일인 매칭

- **email 인덱스**: `candidates/models.py:335` -- `models.Index(fields=["email"], name="idx_candidate_email")` 확인
- **phone_normalized 인덱스**: `candidates/models.py:194` -- `models.CharField(max_length=20, blank=True, db_index=True)` 확인
- **phone_normalized 자동 계산**: `candidates/models.py:350-361` -- save() 오버라이드에서 `normalize_phone_for_matching()` 호출 확인
- **매칭 로직**: `candidates/services/candidate_identity.py:87-127` -- email -> phone 순서로 매칭, name 기반 매칭 없음 (정책 준수)
- **phone normalization**: `candidate_identity.py:68-79` -- 국제번호(82) 제거, 0 접두 처리 정상

### 프롬프트 일관성 (3개 소스 간 핵심 필드)

- 3개 프롬프트 소스 모두 `skills`, `personal_etc`, `education_etc`, `career_etc`, `skills_etc` 필드를 동일한 스키마 구조로 정의
- `skills vs core_competencies 구분` 지침이 3개 프롬프트 모두에 포함
- `etc[] 필드 사용 원칙`이 3개 프롬프트 모두에 포함

---

## 요약

| 등급 | 건수 | 핵심 |
|------|------|------|
| Critical | 2 | ThreadPoolExecutor 내 DB 안전성 잠재 문제, cross_version 코드 이중화 불일치 위험 |
| Warning | 7 | 스키마 3중 복사, Step2 career 필드 손실, 코드 이중화(6개 파일쌍) |
| Info | 3 | 코드 통합 제안, Step2 스키마 확장, migration 번호 갭 |
| Verified OK | 7 | 새 필드 전달, 완성도 계산, 저장 로직, 스레드 안전, 에러 처리, 동일인 매칭, 프롬프트 일관성 |

---

## Round 2 재점검

재점검일: 2026-04-04
재점검자: Pipeline Inspection Agent

### Critical #1 — ThreadPoolExecutor 내부 Step 2 normalization에서 close_old_connections 미적용

**판정: NOT_FIXED**

`candidates/services/integrity/pipeline.py:91` 및 `data_extraction/services/extraction/integrity.py:740`의 `ThreadPoolExecutor` 블록을 재확인한 결과, 변경 없음.

- `_normalize_careers()`와 `_normalize_educations()` 내부는 여전히 `close_old_connections()` 없이 실행됨
- 두 inner function이 호출하는 `_call_gemini()`는 Django DB를 전혀 사용하지 않음 (Gemini API HTTP 호출만 수행)
- 따라서 **현재 코드에서는 stale connection 문제가 실제로 발생하지 않음** — 이 사실은 최초 점검과 동일

수정은 이루어지지 않았으나, 현재 구현 범위 내에서 실제 장애 경로는 존재하지 않는다. 이후 inner function에 DB 접근이 추가될 경우 즉시 Critical이 된다. NOT_FIXED이지만 현재는 경보 수준 Warning 유지.

**확인 경로:**
- `candidates/services/integrity/pipeline.py:74-88` — `_normalize_careers()`, `_normalize_educations()` 정의
- `candidates/services/integrity/step1_extract.py:160-184` — `_call_gemini()`: DB 접근 없음
- `close_old_connections`는 `import_resumes.py:316-322`(outer ThreadPoolExecutor)에만 적용되어 있고, `pipeline.py`의 inner executor에는 없음

---

### Critical #2 — compare_versions() 함수 양쪽 별도 구현으로 불일치 위험

**판정: NOT_FIXED (현재 내용은 일치, 이중화 구조는 유지됨)**

두 구현을 전체 비교한 결과:

| 항목 | candidates 구현 | data_extraction 구현 |
|------|-----------------|----------------------|
| 파일 | `candidates/services/integrity/step3_cross_version.py:268` | `data_extraction/services/extraction/integrity.py:642` |
| `_normalize_company()` | 동일 | 동일 |
| `_parse_ym_to_months()` | 동일 | 동일 |
| `_career_duration_months()` | 동일 | 동일 |
| `_latest_career_end()` | 동일 | 동일 |
| `_match_careers()` | 동일 | 동일 |
| `_normalize_education()` | 동일 | 동일 |
| `_check_career_deleted()` | 동일 | 동일 |
| `_check_career_period_changed()` THRESHOLD | 3 | 3 |
| `_check_career_added_retroactively()` | 동일 | 동일 |
| `_check_education_changed()` | 동일 | 동일 |
| `compare_versions()` 조합 순서 | deleted→period_changed→added→education | 동일 |

**현재 시점에서 두 구현은 완전히 동일하다.** 그러나 이중화 구조는 그대로이며, 한쪽에만 버그를 수정하거나 상수(THRESHOLD 등)를 변경하면 즉시 불일치가 발생하는 구조적 위험은 해소되지 않았다.

`data_extraction/services/pipeline.py:156`과 `candidates/services/retry_pipeline.py:156`은 여전히 각각 다른 경로에서 `compare_versions`를 import하고 있어 향후 diverge 가능성이 있다.
