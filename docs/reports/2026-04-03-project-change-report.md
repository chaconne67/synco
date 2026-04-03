# Synco 변경 작업 보고서

- 작성일: 2026-04-03
- 범위: 최근 점검 결과를 바탕으로 진행한 구조 정리, 기능 보정, 운영/배포 정비, 추출 파이프라인 개선 사항

## 1. 프로젝트 구조 정리

현재 실제 런타임 기준으로 사용하지 않는 앱과 잔존 코드를 정리했다.

- 비활성 앱 `contacts`, `meetings`, `intelligence` 삭제
- 관련 참조 제거 및 네비게이션/빌드 경로 정리
- 오래된 템플릿과 공용 fixture 제거
- 현재 활성 범위에 맞춰 `README`와 inspection 문서 재정비

주요 파일:

- `main/settings.py`
- `main/urls.py`
- `templates/common/nav_bottom.html`
- `tailwind.config.js`
- `README.md`
- `docs/inspection/2026-04-03-project-overview-inspection.md`

## 2. 후보자 검색 리팩터링

자연어 검색이 LLM이 만든 SQL을 직접 실행하던 구조에서, 구조화 필터와 Django ORM 기반 구조로 변경되었다.

- 세션에는 SQL이 아니라 필터 상태를 저장
- 검색 재적용도 ORM 기반으로 동작
- SQLite/PostgreSQL 전제 불일치 리스크를 줄임
- 관련 테스트 추가

주요 파일:

- `candidates/services/search.py`
- `candidates/views.py`
- `tests/test_search_service.py`
- `tests/test_search_views.py`

## 3. 총 경력 계산 로직 개선

총 경력은 더 이상 단순히 추출된 정수값만 우선하지 않고, 경력 구간을 합산한 시스템 계산값을 기본으로 사용한다.

- 겹치는 기간은 한 번만 계산
- 공백 기간은 자동 합산하지 않음
- 미래 종료일은 현재 기준으로 보정
- 계산 가능한 경력이 없을 때만 추출값 fallback
- 상세/검수 화면에서 계산 기준을 명시

추가로 개별 경력 항목마다 기간 표시를 넣었다.

- 예: `3년 6개월`, `1년 3개월`

주요 파일:

- `candidates/models.py`
- `candidates/templates/candidates/partials/candidate_detail_content.html`
- `candidates/templates/candidates/partials/review_detail_content.html`
- `tests/test_candidates_models.py`

## 4. 검토 사항(중요/주의/참고) 체계 정리

후보자 카드와 상세 화면에서 보이는 검토 문구를 규칙 기반으로 통합 정리했다.

- `DiscrepancyReport` 기반 경고와 경력 계산 fallback 안내를 하나의 notice 체계로 통합
- 리스트 카드에도 검토 배지와 대표 문구 표시
- 상세/검수 상세 상단에 `검토 사항` 섹션 추가
- 이상이 없는 후보자는 배지를 노출하지 않도록 정리

판정 기준도 여러 차례 현실 데이터에 맞게 조정했다.

- 같은 회사 내 부서 이동은 overlap `주의`에서 제외
- 같은 회사 내 유사 역할 중복은 `참고`로 낮춤
- 1개월 overlap은 무시
- 고등학교 시작 나이 15세는 정상으로 처리
- 학력 시작연도 누락은 기본적으로 문제로 보지 않음
- 총 경력 차이는 24~35개월 `주의`, 36개월 이상 `중요`
- 최신 경력 종료일 누락 등 추출 불완전성 신호가 있으면 한 단계 낮춤

주요 파일:

- `candidates/services/discrepancy.py`
- `candidates/models.py`
- `candidates/templates/candidates/partials/candidate_card.html`
- `candidates/templates/candidates/partials/_review_notice_section.html`
- `tests/test_discrepancy_service.py`
- `tests/test_search_views.py`

## 5. 검토 문구 표현 개선

검토 문구는 내부 구현 표현 대신 사람이 바로 이해할 수 있는 문장으로 바꿨다.

- `값`, `추출된 총 경력 값` 같은 표현 제거
- `이력서 작성 시점`, `그 시점 기준 총 경력 기간`, `현재 기준 총 경력 기간`으로 정리
- 날짜와 기간은 화면에서 볼드 처리

예시:

`이력서 작성 시점인 2021년 12월(추정) 기준 총 경력 기간은 10년이고 현재 기준 총 경력 기간은 14년 4개월입니다. 두 기간의 차이가 커서 확인이 필요합니다.`

주요 파일:

- `candidates/models.py`
- `candidates/templatetags/candidate_extras.py`
- `candidates/templates/candidates/partials/candidate_card.html`
- `candidates/templates/candidates/partials/_review_notice_section.html`

## 6. 경력 날짜 보정 로직 추가

원본 이력서에 종료일이 비어 있어도, 기간 정보가 있으면 총 경력 계산에 반영하도록 보정 로직을 추가했다.

예시:

- 원문: `2004/06/21 ~`, `(1년 7개월)`
- 보정 결과: `2004-06 ~ 2005-12`

적용 내용:

- `start_date + duration_text` 또는 원문 근거로 `end_date` 추정
- `기간 정보로 보정` 배지 표시
- `날짜와 기간 정보가 모두 부족한 경력`만 제외
- 경력 날짜 표시는 월 단위(`YYYY-MM`)로 정규화
- 타임라인 날짜/기간 줄바꿈 방지

주요 파일:

- `candidates/models.py`
- `candidates/templates/candidates/partials/candidate_detail_content.html`
- `candidates/templates/candidates/partials/review_detail_content.html`
- `tests/test_candidates_models.py`
- `tests/test_search_views.py`

## 7. 추출 스키마 확장

앞으로 새로 추출되는 resume는 날짜 보정 근거를 구조화 필드로 함께 저장한다.

새로 추가된 career 필드:

- `duration_text`
- `end_date_inferred`
- `date_evidence`
- `date_confidence`

적용 내용:

- LLM 추출 스키마와 프롬프트 확장
- import 시 `Career` 모델에 저장
- 검증 로직에서 `end_date_inferred`와 `date_confidence` 확인
- 총 경력 계산 우선순위:
  - 명시 종료일
  - 구조화된 `end_date_inferred`
  - `duration_text`/원문 기반 보정
  - 그래도 불가하면 제외

주요 파일:

- `candidates/services/llm_extraction.py`
- `candidates/services/gemini_extraction.py`
- `candidates/services/validation.py`
- `candidates/management/commands/import_resumes.py`
- `candidates/models.py`
- `candidates/migrations/0011_career_date_confidence_career_date_evidence_and_more.py`

## 8. 운영/배포 정비

운영 배포가 개발 환경과 과도하게 달라지지 않도록 배포 구성을 정리했다.

- 운영 이미지에서 dev 의존성과 개인용 도구 제거
- Dockerfile 멀티스테이지화
- `collectstatic` 실패 숨김 제거
- 운영에서 `DATABASE_URL` 누락 시 즉시 실패하도록 수정
- `SECURE_SSL_REDIRECT` 운영 기본값 정리
- 하드코딩 DB 비밀번호 제거
- `.env.example` 보강
- Google Drive 관련 secret 파일 git 추적 제외

주요 파일:

- `Dockerfile`
- `docker-compose.yml`
- `.env.example`
- `.gitignore`
- `.dockerignore`
- `main/settings.py`
- `candidates/services/drive_sync.py`

## 9. Python 및 런타임 환경 업데이트

- Python 실행 버전을 3.10 계열에서 3.13.6으로 상향
- 관련 문서와 Docker 기반 런타임도 함께 갱신

주요 파일:

- `.python-version`
- `pyproject.toml`
- `Dockerfile`
- `README.md`
- `CLAUDE.md`

## 10. 데이터/운영 정리 메모

- 테스트 확인용으로 수동 생성된 후보자 `문구확인`, `문구확인2`, `문구확인3` 삭제
- 김소련 케이스는 원본 이력서에 종료일은 없지만 기간 정보가 있어 보정 대상으로 처리
- 김세용, 김승일 등 실제 데이터 케이스를 기준으로 discrepancy 기준을 조정

## 11. 검증 결과

이번 변경 과정에서 주요 검증으로 다음을 수행했다.

- `uv run pytest -q`
- `uv run pytest -q tests/test_candidates_models.py tests/test_search_views.py tests/test_validation.py tests/test_llm_extraction.py`
- `uv run python manage.py migrate`
- `uv run python manage.py check --deploy`
- `docker build -t synco:deploy-check .`

최신 관련 테스트 결과:

- `69 passed`

## 12. 남은 후속 작업

이번 변경으로 새로 추출되는 데이터는 보정 근거를 구조적으로 저장할 수 있게 되었지만, 기존에 이미 저장된 후보자는 자동 반영되지 않는다.

권장 후속 작업:

- 기존 후보자 중 `end_date` 비어 있고 `is_current=False`인 경력 필터링
- raw text에 기간 흔적이 있는 후보자만 선별
- 해당 후보자에 한해 LLM backfill 실행
- `duration_text`, `end_date_inferred`, `date_evidence`, `date_confidence`만 선택적으로 보강

즉, 전체 재추출보다는 `보정 가능성이 높은 기존 데이터만 선별 재처리`하는 방향이 적절하다.
