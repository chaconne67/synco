# 점검 C: 코드 정합성 리뷰

점검일: 2026-04-04
점검 범위: candidates 앱, data_extraction 앱, 마이그레이션 체인, 서비스 레이어, 뷰, 템플릿, 검색, admin

---

## Critical (런타임 에러/데이터 오류)

### C1. `candidate_detail` 뷰의 `extracted_snapshot`에 skills/certifications/language_skills 누락

- **[candidates/views.py:330-342]** `compute_field_confidences()`에 전달하는 `extracted_snapshot`에 `skills`, `certifications`, `language_skills` 키가 빠져 있다. 이로 인해 `category_scores["능력"]`이 항상 0.0으로 계산된다. 실제 후보자에 자격증과 기술 스택이 있어도 능력 카테고리 점수가 0으로 표시된다.
- **영향**: UI에서 "능력" 카테고리 완성도가 항상 0%로 표시되며, `live_score` (전체 신뢰도)가 실제보다 낮게 계산된다.
- **수정 방향**: `extracted_snapshot`에 다음을 추가해야 한다:
  ```python
  "skills": candidate.skills or [],
  "certifications": [{"name": c.name} for c in certifications],
  "language_skills": [{"language": l.language} for l in language_skills],
  ```

### C2. 레거시 데이터 UI 공백: save 시 awards/patents/projects/trainings/overseas_experience 초기화 후 표시 불능

- **[data_extraction/services/save.py:376-380]** 및 **[candidates/services/integrity/save.py:376-380]** `_update_candidate()`에서 `awards=[]`, `patents=[]`, `projects=[]`, `trainings=[]`, `overseas_experience=[]`로 초기화한다.
- **[candidates/views.py:362-370]** 뷰는 여전히 `candidate.awards`, `candidate.projects` 등을 컨텍스트에 전달한다.
- **[candidates/templates/candidates/partials/candidate_detail_content.html:221-540]** 템플릿은 `trainings_data`, `projects_data`, `awards_data`, `patents_data`, `overseas_experience`를 표시하는 섹션을 보유하고 있다.
- **결과**: 새로 추출된 후보자의 경우, 수상/특허/프로젝트/교육/해외경험 데이터가 `*_etc` 필드에만 존재하고 레거시 필드는 빈 배열이므로, 해당 섹션이 빈 채로 표시되거나 안 보인다. `*_etc` 섹션(174-499행)은 별도로 표시되지만, 데이터 중복 표시 또는 누락 표시가 혼재할 수 있다.
- **영향**: 기존 후보자(레거시 데이터가 있는 경우)를 재추출하면 awards 등이 사라진다.

---

## Warning (잠재적 문제)

### W1. `candidates/services/extraction_filters.py`와 `data_extraction/services/filters.py` 완전 동일 복사본

- **[candidates/services/extraction_filters.py:1-177]** 와 **[data_extraction/services/filters.py:1-177]** 는 `diff` 결과 완전히 동일한 파일이다.
- 동일하게 `candidates/services/validation.py`와 `data_extraction/services/validation.py`도 완전 복사본이다.
- `candidates/services/text_extraction.py`와 `data_extraction/services/text.py`도 동일하다.
- `candidates/services/integrity/save.py`와 `data_extraction/services/save.py`는 거의 동일하되, 헬퍼 함수명 접두사(`_save_failed_resume` vs `save_failed_resume`)만 다르다.
- **위험**: 한쪽만 수정하고 다른쪽을 안 고치면 동작 차이가 발생한다. 현재는 동기화되어 있으나, 향후 변경 시 분기될 가능성 높음.

### W2. `_build_summary` private 함수를 외부 모듈에서 import

- **[candidates/services/integrity/save.py:25]** 및 **[data_extraction/services/save.py:25]** 에서 `candidates.services.discrepancy._build_summary`를 import한다. 파이썬 규약상 `_` 접두사는 내부 구현이며, 외부 모듈의 변경에 취약하다.

### W3. admin에 새 필드(skills, *_etc) 미반영

- **[candidates/admin.py:52-71]** `CandidateAdmin`의 `list_display`, `search_fields`에 `skills`, `personal_etc`, `education_etc`, `career_etc`, `skills_etc` 필드가 포함되지 않았다. JSONField는 직접 `search_fields`에 넣기 어렵지만, `readonly_fields`나 `fieldsets`로 admin 상세 페이지에서 볼 수 있게 하면 디버깅에 유용하다.

### W4. `skills__contains` 검색이 SQLite에서 작동하지 않을 수 있음

- **[candidates/services/search.py:370]** `qs = qs.filter(skills__contains=[kw])` — 이 JSONField `contains` lookup은 PostgreSQL에서는 정상 동작하나, `DEBUG=true`이고 `DATABASE_URL` 미설정 시 SQLite fallback에서는 동작하지 않는다.
- **[main/settings.py:103-109]** `DEBUG` 모드에서 `DATABASE_URL` 없으면 SQLite를 사용한다.
- **영향**: 개발자가 SQLite로 테스트할 때 skills 검색이 실패할 수 있다.

### W5. templatetags `_FIELD_LABELS`에 새 필드 라벨 누락

- **[candidates/templatetags/candidate_extras.py:16-28]** `_FIELD_LABELS` 딕셔너리에 `skills`, `certifications`, `language_skills` 등 새 필드의 한국어 라벨이 없다. `field_label_ko` 필터 사용 시 원본 키가 그대로 표시된다.

### W6. `candidates/services/retry_pipeline.py`와 `data_extraction/services/pipeline.py` 구조 중복

- **[candidates/services/retry_pipeline.py]** 와 **[data_extraction/services/pipeline.py]** 는 `run_extraction_with_retry()`, `_run_integrity_pipeline()`, `_run_legacy_pipeline()`, `apply_cross_version_comparison()`, `_build_integrity_diagnosis()` 함수가 거의 동일하다.
- 차이점: candidates 버전은 `candidates.services.integrity.pipeline`에서 import, data_extraction 버전은 `data_extraction.services.extraction.integrity`에서 import한다.
- **위험**: 로직 변경 시 양쪽 동기화 필요.

---

## Info (개선 제안)

### I1. 마이그레이션 0017 건너뜀

- 마이그레이션 체인: 0014 → 0015 → 0016 → 0018 → 0019. 0017이 없다.
- **[candidates/migrations/0018_rename_processing_status_values.py:21]** 0018은 `('candidates', '0016_backfill_candidate_phone_normalized')`에 의존하므로 체인은 정상 작동한다.
- 기능적 문제는 없으나, 번호가 비연속적이다 (0017이 삭제된 것으로 보임).

### I2. 테스트 커버리지 부족: skills 검색, *_etc 저장, 카테고리 완성도

- `tests/` 디렉토리에 다음에 대한 테스트가 없다:
  - `skills__contains` 기반 검색 동작 (`skill_keywords` 필터)
  - `*_etc` 필드의 저장/조회 라운드트립
  - `compute_field_confidences()`의 `category_scores["능력"]` 계산 (skills 포함 시)
  - `candidate_detail` 뷰의 `extracted_snapshot` + `live_score` 정확성

### I3. `data_extraction` 앱에 자체 모델 없음

- **[data_extraction/models.py]** 코멘트만 있고 모델 클래스가 없다. `data_extraction/migrations/0001_initial.py`도 빈 migration이다.
- 앱이 순수 서비스 레이어 역할만 하며, 모든 DB 모델은 `candidates` 앱에 있다. `INSTALLED_APPS`에 등록된 이유는 management commands와 서비스 모듈 구조를 위한 것으로 보인다.

### I4. `views.py`의 `from .models import ValidationDiagnosis` inline import

- **[candidates/views.py:348]** `candidate_detail` 함수 내부에서 `ValidationDiagnosis`를 inline import한다. 파일 상단의 import 블록(line 10-17)에 넣는 것이 일관적이다.

### I5. `compute_field_confidences`의 `total_experience_years` 미사용

- **[candidates/services/validation.py:160-256]** `compute_field_confidences()`는 `total_experience_years`를 입력으로 받지만 `field_scores`에 포함하지 않는다. 뷰(views.py:338)에서 `extracted_snapshot`에 넣고 있으나 활용되지 않는다.

---

## Verified OK

- **Import 정합성**: 모든 주요 모듈의 import 경로를 실제 Python import로 검증 완료. 순환 참조 없음. 모든 import 성공.
- **마이그레이션 체인**: 0015 → 0016 → 0018 → 0019 체인이 올바르게 연결됨. `makemigrations --check --dry-run` 통과. 0017 삭제 후 0018의 dependency가 0016으로 올바르게 수정됨.
- **함수 시그니처 일관성**: `compute_field_confidences()`의 `(field_scores, category_scores)` tuple 반환이 모든 호출부(views.py:343, retry_pipeline.py:83, data_extraction/pipeline.py:83)에서 올바르게 unpack됨.
- **`compute_overall_confidence()`**: 모든 호출부에서 `(score, status)` tuple 반환을 올바르게 처리.
- **settings 정합성**: `INSTALLED_APPS`에 `data_extraction`(line 56)과 `batch_extract`(line 57) 모두 등록됨.
- **`skills` JSONField 검색**: `skills__contains=[kw]` 구문이 PostgreSQL에서 올바르게 동작 (JSONField contains lookup). `FILTER_SPEC_TEMPLATE`에 `skill_keywords` 포함됨.
- **save 로직 동기화**: `candidates/services/integrity/save.py`와 `data_extraction/services/save.py` 양쪽 모두 새 필드(`skills`, `*_etc`) 저장 로직이 동일하게 구현됨.
- **integrity pipeline 결과 어셈블리**: `candidates/services/integrity/pipeline.py`(line 139-168)와 `data_extraction/services/extraction/integrity.py`(line 788-817) 모두 `skills`, `personal_etc`, `education_etc`, `career_etc`, `skills_etc`를 결과에 포함.
- **LLM 프롬프트**: `EXTRACTION_SYSTEM_PROMPT`에 skills vs core_competencies 구분 규칙, etc[] 사용 원칙이 명확히 기술됨.
- **Candidate.save() 오버라이드**: `phone_normalized` 자동 설정이 올바르게 작동. `update_fields`에 `phone` 포함 시 `phone_normalized`도 자동 추가.
- **전체 테스트 스위트**: 495개 테스트 전부 통과.

---

## Round 2 재점검

재점검일: 2026-04-04

### C1. `extracted_snapshot`에 skills/certifications/language_skills 누락 → **FIXED**

- **[candidates/views.py:368-370]** `candidate_detail`의 `extracted_snapshot`에 `skills`, `certifications`, `language_skills` 세 키 모두 추가됨. 수정 방향에서 제시한 코드와 동일하게 반영:
  ```python
  "skills": candidate.skills or [],
  "certifications": [{"name": c.name} for c in certifications],
  "language_skills": [{"language": l.language} for l in language_skills],
  ```
- **[candidates/views.py:138-140]** `review_detail`에도 동일하게 세 필드가 추가되어 두 뷰 모두 일관성 확보됨.
- `category_scores["능력"]`이 이제 certifications/language_skills/skills 데이터를 기반으로 정상 계산됨.

### C2. 레거시 JSONField 초기화 후 뷰/템플릿 참조 문제 → **PARTIALLY_FIXED**

- **[candidates/templates/candidates/partials/candidate_detail_content.html]** 템플릿이 `*_etc` 섹션(personal_etc, education_etc, career_etc, skills_etc)을 `candidate.X_etc`로 직접 참조하도록 수정됨. 새로 추출된 후보자의 기타 항목이 올바르게 표시됨.
- **[candidates/views.py:393-399]** `extra_context`는 여전히 레거시 `awards_data`, `trainings_data`, `projects_data`, `patents_data`, `overseas_experience`를 빈 배열(`candidate.awards or []` 등)로 전달한다. 신규 추출 후보자의 경우 이 필드들은 항상 `[]`이므로, 템플릿 내 해당 섹션(trainings, awards, projects, patents, overseas)이 표시되지 않는다.
- **잔존 문제**: 기존 레거시 데이터를 가진 후보자를 재추출하면 `awards`, `trainings`, `projects`, `patents`, `overseas_experience` 섹션이 공백으로 표시된다. 해당 데이터는 `career_etc` / `skills_etc` / `education_etc`로 이전되지만, 템플릿에서 레거시 섹션과 `*_etc` 섹션이 별도 UI 영역에 표시되므로 사용자 관점에서 데이터 이전 여부가 불명확하다.
- **수정 방향**: `extra_context`의 레거시 필드 전달을 제거하고, 해당 템플릿 섹션을 `*_etc` 기반으로 통합하거나 레거시 섹션 자체를 제거해야 함.

### W3. admin에 새 필드 미반영 → **FIXED**

- **[candidates/admin.py:64-70]** `CandidateAdmin.readonly_fields`에 `skills`, `personal_etc`, `education_etc`, `career_etc`, `skills_etc` 5개 필드가 추가됨. admin 상세 페이지에서 새 필드 확인 가능.

### W5. templatetags `_FIELD_LABELS` 새 필드 라벨 누락 → **NOT_FIXED**

- **[candidates/templatetags/candidate_extras.py:16-28]** `_FIELD_LABELS`에 `skills`, `certifications`, `language_skills` 라벨이 여전히 없다. 현재 딕셔너리는 기존 11개 필드만 포함. `field_label_ko` 필터 호출 시 `"skills"` → `"skills"` (원본 키)가 그대로 출력됨.
- **수정 방향**: 다음을 추가해야 함:
  ```python
  "skills": "기술 스택",
  "certifications": "자격증",
  "language_skills": "외국어",
  ```

### 신규 발견 이슈

#### N1. `candidate_detail`의 `extra_context`에 `*_etc` 컨텍스트 변수 미전달 (Warning)

- **[candidates/views.py:389-400]** `extra_context`에 `personal_etc`, `education_etc`, `career_etc`, `skills_etc`가 포함되지 않는다. 템플릿은 `candidate.personal_etc` 등 모델 속성으로 직접 접근하므로 현재는 동작하지만, 컨텍스트 변수 방식과 모델 직접 접근 방식이 혼재한다. `awards_data` 등은 컨텍스트 변수(`awards_data`)로, `*_etc`는 모델 속성(`candidate.career_etc`)으로 접근하는 불일치가 있다.
- **영향**: 즉각적인 버그는 없으나, 템플릿 수정 시 어느 방식이 맞는지 혼란을 줄 수 있다.

#### N2. `review_detail` 뷰에 `extra_context` 미전달 (Warning)

- **[candidates/views.py:151-165]** `review_detail`은 `awards_data`, `overseas_experience` 등 `extra_context`를 전달하지 않는다. `review_detail_content.html` 템플릿이 해당 변수를 참조할 경우 빈 값으로 렌더링된다.
- 현재 `review_detail_content.html` 템플릿 내용을 확인하지 않았으므로 실제 영향 범위는 추가 확인 필요.
