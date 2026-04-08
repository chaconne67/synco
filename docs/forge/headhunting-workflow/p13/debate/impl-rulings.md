# P13 Impl Tempering — Rulings

**Status:** COMPLETE
**Rounds:** 1
**Issues:** 6 (5 accepted, 1 partial)

---

## Accepted Items

### I-R1-01 [MAJOR] get_weekly_schedule()가 compute_project_urgency() 단일 결과에 의존
**Ruling:** ACCEPTED
- `collect_all_actions(project)` 함수를 `urgency.py`에 추가 (모든 우선순위 액션 반환)
- `get_today_actions()`와 `get_weekly_schedule()`은 collect_all_actions() 호출 후 level 필터
- `compute_project_urgency()`는 기존 유지 (대표 긴급도용)

### I-R1-02 [MAJOR] 팀 KPI 이중 카운트 + viewer 포함
**Ruling:** ACCEPTED
- Membership 필터: `role__in=["owner", "consultant"]` (viewer 제외)
- 개인별 집계: `Contact.consultant=user`, `Submission.consultant=user` 기준
- 팀 KPI: org 전체의 distinct 레코드 기준

### I-R1-03 [MAJOR] 라우팅 계획 내부 모순
**Ruling:** ACCEPTED
- `/`, `/dashboard/`, `/dashboard/actions/`, `/dashboard/team/` 전부 `main/urls.py`에서 정의
- `projects/urls.py` 수정 불필요
- Task 4의 라우팅 관련 내용 삭제, Task 6으로 통합

### I-R1-04 [MINOR] 루트 URL이 redirect로 처리
**Ruling:** ACCEPTED
- `path("", dashboard, name="dashboard")`를 `path("", include("accounts.urls"))` 앞에 배치
- accounts `home()` 뷰는 보조 경로로 유지

### I-R1-05 [MINOR] Task 5(humanize) 불필요
**Ruling:** ACCEPTED
- Task 5 삭제. `django.contrib.humanize`는 settings.py:51에 이미 존재.

### I-R1-06 [MINOR] 최근 활동에 AI 초안 이벤트 미반영
**Ruling:** PARTIAL → docstring 수정만 적용
- docstring을 "Aggregates recent contacts, project creations, and submissions"로 수정
- SubmissionDraft 활동은 향후 활동 로그 모델 도입 시 추가
