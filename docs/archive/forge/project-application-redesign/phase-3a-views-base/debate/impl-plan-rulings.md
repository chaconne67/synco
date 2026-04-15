# Rulings — impl-plan (phase-3a-views-base)

**Status:** COMPLETE
**Rounds:** 1
**Total Issues:** 10 (6 CRITICAL, 4 MAJOR)
**Resolved:** 10 (all ACCEPTED)
**Disputed:** 0

---

## Resolved Items

### R1-01 [CRITICAL] `@membership_required` + `_get_org()` + 서비스 시그니처
- **Red-team:** 모든 신규 뷰가 `@login_required`만 사용, `@membership_required` 누락. `request.user.organization` 속성 불존재. dashboard 서비스 `(user, org)` 시그니처 불일치.
- **Author:** ACCEPTED. 모든 뷰에 `@membership_required` + `org = _get_org(request)` 적용. 서비스 호출에 `org` 인자 추가.

### R1-02 [CRITICAL] Dashboard URL 라우팅
- **Red-team:** Dashboard routes를 `projects/urls.py`에 추가하면 `/projects/dashboard/`가 됨. 실제 `/dashboard/`는 `main/urls.py` 관할.
- **Author:** ACCEPTED. Dashboard 관련 뷰와 URL은 `main/urls.py`에서 관리. `projects/urls.py`에는 추가하지 않음.

### R1-03 [CRITICAL] `project_close` DB CHECK constraint
- **Red-team:** `closed_at` 저장 시 `status`를 함께 `CLOSED`로 설정하지 않으면 CHECK constraint 위반.
- **Author:** ACCEPTED. `project.status = ProjectStatus.CLOSED`를 명시적으로 설정한 후 `update_fields`에 `status` 포함.

### R1-04 [CRITICAL↑] `forms.py` 파괴 + IDOR
- **Red-team:** 전면 재작성이 기존 뷰의 폼 import 파괴. org-scoped queryset 누락으로 IDOR 취약점.
- **Author:** ACCEPTED. 기존 폼 보존 (추가만, 삭제는 Phase 3b). 새 폼에 `organization` 인자 및 org-scoped queryset 유지.

### R1-05 [CRITICAL↑] `project_create` 충돌/승인 삭제
- **Red-team:** 충돌 감지 + 승인 워크플로 삭제. FINAL-SPEC이 `ProjectApproval`을 "변경 없는 테이블"로 명시.
- **Author:** ACCEPTED. 기존 충돌 감지 + 승인 워크플로 유지. `project_check_collision` URL 보존.

### R1-06 [CRITICAL] 칸반 역할 기반 스코핑
- **Red-team:** `get_project_kanban_cards(org)`가 조직 전체 프로젝트 반환. consultant는 배정된 프로젝트만 봐야 함.
- **Author:** ACCEPTED. 뷰에서 기존 `project_list`와 동일한 owner/consultant 분기 적용.

### R1-07 [MAJOR] URL name 호환성
- **Red-team:** `project_update`→`project_edit` 등 이름 변경이 기존 템플릿/테스트 파괴.
- **Author:** ACCEPTED. 기존 URL name 유지 (`project_update` 그대로). 새 URL은 추가만. 기존 라우트 삭제는 Phase 3b 이후.

### R1-08 [MAJOR] `project_reopen` phase 재계산
- **Red-team:** reopen 후 phase가 stale. signal은 ActionItem/Application 변경 시에만 작동.
- **Author:** ACCEPTED. reopen 시 명시적으로 `compute_project_phase()` 호출.

### R1-09 [MAJOR] `project_close` pending ActionItem 정리
- **Red-team:** 수동 종료 시 pending ActionItem이 dashboard에 잔류.
- **Author:** ACCEPTED. dashboard 서비스 쿼리에 `application__project__closed_at__isnull=True` 필터 추가 (Phase 3a 범위 내).

### R1-10 [MAJOR] close/reopen/edit 권한 모델
- **Red-team:** 권한 규칙 미정의. 조직 내 아무 사용자가 종료/재오픈 가능.
- **Author:** ACCEPTED. 최소 규칙 명문화: create/edit/close/reopen은 owner + assigned consultant. delete는 owner only (기존 유지).
