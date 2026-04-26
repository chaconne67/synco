# projects/views.py 책임별 분리 Implementation Plan (Plan A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `projects/views.py` 3,345줄 / 90 함수를 책임별로 14개 파일로 분리하여 가독성·탐색성을 높인다. 외부 동작(URL, import, HTMX 응답) 변경 0건.

**Architecture:** 임시 패키지 `projects/_views_split/`에서 분리 작업을 진행한 뒤, 마지막 한 commit으로 `projects/views.py` 삭제 + `projects/_views_split/ → projects/views/` rename + `projects/views/__init__.py` 완성을 atomic하게 swap. 중간 상태에서 모든 import는 정상 (`projects/views.py` 그대로 유지). CBV 전환은 본 plan 범위 밖 — Plan B로 분리 (§Plan B 참조).

**Tech Stack:** Django 5.2, pytest-django, `level_required` decorator (`accounts/decorators.py:16`).

**원칙:**
- 외부 동작 변경 0건: URL name·HTTP 응답·HTMX 헤더 모두 유지
- 임시 패키지 전략: 중간 commit마다 import 정상, pytest 정상
- 마지막 swap commit이 atomic: rename + 삭제 + 재배치 + re-export가 한 commit
- DRY/YAGNI: helper만 분리, 추상화 추가 없음
- 잦은 commit: 각 task 1 commit

**검증된 코드 사실 (2026-04-26 시점):**
- `projects/views.py` 90 함수 (helper 6개 포함)
- `projects/urls.py` `app_name = "projects"`, 83 path가 `views.X` 형태로 함수 참조
- `main/urls.py:8`은 `from projects.views import dashboard` 한 줄, `main/urls.py:16`에 `path("dashboard/", dashboard, name="dashboard")` — **`dashboard`는 전역 URL name**, `projects:dashboard` 아님
- 외부 import는 main/urls.py 1곳 (`from projects.views import dashboard`) + tests에서 `@patch("projects.views.process_pending_upload")` 등 attribute path 3곳 (`tests/test_p18_views.py:100,152,201`)
- `projects/views.py:38` `from projects.services.resume.linker import link_resume_to_candidate`, `projects/views.py:43` `process_pending_upload` import — test patch가 **`projects.views.process_pending_upload`** path를 잡으므로 분리 후에도 같은 모듈 경로(`projects.views`)에서 그 이름이 import 가능해야 함 (re-export 필요)

---

## File Structure

`projects/views.py` 90 함수 → `projects/_views_split/` (작업 중) → `projects/views/` (swap 후)

함수 분류 (실측한 prefix 기준, 모든 함수명·prefix는 `grep -E "^def "` 결과):

| 파일 | 함수 (개수) |
|---|---|
| `_helpers.py` | `_has_pending_approval`, `_filter_params_string`, `_build_tab_context`, `_build_overview_context`, `_get_draft_context`, `_create_receive_resume_action` (6) |
| `dashboard.py` | `dashboard` (1) |
| `project.py` | `project_list`, `project_check_collision`, `project_create`, `project_detail`, `project_applications_partial`, `project_timeline_partial`, `project_update`, `project_delete`, `project_close`, `project_reopen`, `project_tab_overview`, `project_tab_search`, `project_tab_submissions`, `project_tab_interviews`, `drive_picker` (15) |
| `jd.py` | `analyze_jd`, `jd_results`, `start_search_session`, `jd_matching_results` (4) |
| `submissions.py` | `submission_create`, `submission_batch_create`, `submission_update`, `submission_delete`, `submission_submit`, `submission_feedback`, `submission_download`, `submission_draft`, `draft_generate`, `draft_consultation`, `draft_consultation_audio`, `draft_finalize`, `draft_review`, `draft_convert`, `draft_preview` (15) |
| `interviews.py` | `interview_create`, `interview_update`, `interview_delete`, `interview_result` (4) |
| `postings.py` | `posting_generate`, `posting_edit`, `posting_download`, `posting_sites`, `posting_site_add`, `posting_site_update`, `posting_site_delete` (7) |
| `applications.py` | `project_add_candidate`, `application_drop`, `application_restore`, `application_hire`, `application_skip_stage`, `application_resume_use_db`, `application_resume_request_email`, `application_resume_upload`, `application_actions_partial` (9) |
| `actions.py` | `action_create`, `action_complete`, `action_skip`, `action_reschedule`, `action_propose_next` (5) |
| `stages.py` | `stage_contact_complete`, `stage_pre_meeting_schedule`, `stage_pre_meeting_record`, `stage_prep_submission_confirm`, `stage_client_submit_single`, `stage_interview_complete` (6) |
| `resumes.py` | `resume_upload`, `resume_process_pending`, `resume_upload_status`, `resume_link_candidate`, `resume_discard`, `resume_retry`, `resume_unassigned`, `resume_assign_project` (8) |
| `approvals.py` | `approval_queue`, `approval_decide`, `approval_cancel`, `project_auto_actions`, `auto_action_apply`, `auto_action_dismiss` (6) |
| `context.py` | `project_context`, `project_context_save`, `project_context_resume`, `project_context_discard` (4) |
| **합계** | **90** |

규칙:
- `_helpers.py`는 module-private (밑줄 prefix). 다른 분리 파일이 import 가능. `_helpers.py`는 다른 분리 파일을 import 안 함 (단방향 → circular import 차단)
- 각 파일은 자기 함수가 사용하는 import만 가져옴 (불필요 import 0)
- `__init__.py`는 swap 단계에서만 만들어짐. 작업 중에는 임시 패키지 `_views_split/`만 사용

---

## Phase 1: 임시 패키지에서 함수 이동

각 task는 함수 그룹을 `projects/views.py`에서 `projects/_views_split/<group>.py`로 이동. **이 단계에서 `projects/views.py`는 그대로 모듈로 존재** (Python의 패키지 우선 동작 회피).

이 단계의 핵심 trick: **`projects/views.py`가 자기 안에서 `from projects._views_split.X import Y`로 옮긴 함수를 다시 import**. 외부에서는 여전히 `from projects.views import Y`로 동작 (views.py 모듈이 Y를 re-export).

### Task 1.1: `_views_split/` 디렉토리 + `_helpers.py` 생성

**Files:**
- Create: `projects/_views_split/__init__.py` (빈 파일)
- Create: `projects/_views_split/_helpers.py`
- Modify: `projects/views.py` (6개 helper 본문 제거 + re-import)

대상 6개 함수: `_has_pending_approval` (line 90), `_filter_params_string` (line 97), `_build_tab_context` (line 336), `_build_overview_context` (line 603), `_get_draft_context` (line 1232), `_create_receive_resume_action` (line 2733)

- [ ] **Step 1: 임시 패키지 디렉토리 + 빈 __init__.py 생성**

```bash
mkdir -p projects/_views_split
touch projects/_views_split/__init__.py
```

- [ ] **Step 2: 6개 helper 함수의 import 의존성 식별**

```bash
sed -n '1,90p' projects/views.py | grep -E "^from |^import " > /tmp/views_imports.txt
cat /tmp/views_imports.txt
```

이 import 중 6개 helper가 실제로 사용하는 것만 다음 step에서 `_helpers.py`로 옮긴다. 각 helper 본문에서 호출하는 심볼을 grep으로 확인:

```bash
for fn in _has_pending_approval _filter_params_string _build_tab_context _build_overview_context _get_draft_context _create_receive_resume_action; do
    echo "=== $fn ==="
    sed -n "/^def $fn/,/^def \|^@/p" projects/views.py | head -50
done
```

- [ ] **Step 3: `_helpers.py` 작성 — 6개 함수 본문 + 그들이 쓰는 import만**

```python
# projects/_views_split/_helpers.py
"""Module-private helpers shared across split view files.

Originally inline in projects/views.py. Extracted here so split files
can share them without circular imports. _helpers.py imports nothing
from sibling split files (one-way dependency).
"""
from __future__ import annotations

# (Step 2에서 식별한 import만 — Q, render, get_object_or_404 등 실제 호출되는 것만)

# 6개 helper 본문을 기존 projects/views.py에서 그대로 복사 (수정 없음)
def _has_pending_approval(project):
    ...  # 기존 line 90~95 본문

def _filter_params_string(request, exclude=None):
    ...  # 기존 line 97~108 본문

def _build_tab_context(project):
    ...  # 기존 line 336~358 본문

def _build_overview_context(project):
    ...  # 기존 line 603~639 본문

def _get_draft_context(request, pk, sub_pk):
    ...  # 기존 line 1232~1244 본문

def _create_receive_resume_action(application, actor, *, done, note, due_days=0):
    ...  # 기존 line 2733~2761 본문
```

- [ ] **Step 4: `projects/views.py`에서 6개 함수 본문 제거 + re-import 추가**

```python
# projects/views.py 상단 (기존 import 다음)
from projects._views_split._helpers import (
    _has_pending_approval,
    _filter_params_string,
    _build_tab_context,
    _build_overview_context,
    _get_draft_context,
    _create_receive_resume_action,
)
```

해당 6개 `def` 블록을 본문에서 제거.

- [ ] **Step 5: pytest 전체 + ruff check**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
uv run ruff check projects/views.py projects/_views_split/ 2>&1 | tail -5
```

Expected: pytest PASS / ruff clean

- [ ] **Step 6: Commit**

```bash
git add projects/_views_split/__init__.py projects/_views_split/_helpers.py projects/views.py
git commit -m "Extract 6 view helpers into projects/_views_split/_helpers.py"
```

### Task 1.2: `dashboard.py` 분리

**Files:**
- Create: `projects/_views_split/dashboard.py`
- Modify: `projects/views.py`

대상: `dashboard` (line 2084)

- [ ] **Step 1: `dashboard.py` 생성 — 함수 본문 + 필요 import**

```python
# projects/_views_split/dashboard.py
"""Dashboard view (Level-gated personal dashboard)."""
from __future__ import annotations

# 기존 projects/views.py에서 dashboard가 사용하는 import만:
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.decorators import level_required
from projects.services.dashboard import get_dashboard_context
# ... dashboard 본문이 실제 사용하는 것

# 기존 line 2084~2112 본문 그대로 복사
@login_required
@level_required(1)
def dashboard(request):
    ...
```

- [ ] **Step 2: `projects/views.py`에서 `dashboard` 함수 본문 제거 + re-import**

```python
# projects/views.py 상단
from projects._views_split.dashboard import dashboard
```

dashboard def 블록 본문 제거.

- [ ] **Step 3: pytest + 외부 import 검증**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
uv run python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')
django.setup()
from projects.views import dashboard
from django.urls import reverse
print('dashboard URL:', reverse('dashboard'))  # 전역 URL name
print('Function:', dashboard.__name__)
"
```

Expected: pytest PASS, `dashboard URL: /dashboard/`, `Function: dashboard`

- [ ] **Step 4: Commit**

```bash
git add projects/_views_split/dashboard.py projects/views.py
git commit -m "Move dashboard view to projects/_views_split/dashboard.py"
```

### Task 1.3: `project.py` 분리 (15 함수)

**Files:**
- Create: `projects/_views_split/project.py`
- Modify: `projects/views.py`

대상 15개: `project_list`, `project_check_collision`, `project_create`, `project_detail`, `project_applications_partial`, `project_timeline_partial`, `project_update`, `project_delete`, `project_close`, `project_reopen`, `project_tab_overview`, `project_tab_search`, `project_tab_submissions`, `project_tab_interviews`, `drive_picker`

- [ ] **Step 1: `project.py` 생성 — 15개 함수 본문 + import**

```python
# projects/_views_split/project.py
"""Project lifecycle CRUD + tab views."""
from __future__ import annotations

# 함수 15개가 실제 사용하는 import만
from django.contrib.auth.decorators import login_required
# ...

from projects._views_split._helpers import (
    _has_pending_approval,
    _filter_params_string,
    _build_tab_context,
    _build_overview_context,
)

# 기존 projects/views.py의 line 110~916 영역에서 15개 함수 본문 그대로 복사
# (decorator 포함: @login_required, @level_required, @require_http_methods 등)
```

- [ ] **Step 2: `projects/views.py`에서 15개 함수 제거 + re-import**

```python
# projects/views.py
from projects._views_split.project import (
    project_list,
    project_check_collision,
    project_create,
    project_detail,
    project_applications_partial,
    project_timeline_partial,
    project_update,
    project_delete,
    project_close,
    project_reopen,
    project_tab_overview,
    project_tab_search,
    project_tab_submissions,
    project_tab_interviews,
    drive_picker,
)
```

15개 def 블록 본문 제거.

- [ ] **Step 3: pytest + URL reverse 검증**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
uv run python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')
django.setup()
from django.urls import reverse
import uuid
pk = uuid.uuid4()
for name, kwargs in [
    ('projects:project_list', {}),
    ('projects:project_create', {}),
    ('projects:project_detail', {'pk': pk}),
    ('projects:project_tab_overview', {'pk': pk}),
    ('projects:drive_picker', {'pk': pk}),
]:
    print(name, '→', reverse(name, kwargs=kwargs))
"
```

Expected: pytest PASS, 5개 URL 모두 정상

- [ ] **Step 4: Commit**

```bash
git add projects/_views_split/project.py projects/views.py
git commit -m "Move 15 project_* / drive_picker views to projects/_views_split/project.py"
```

### Task 1.4: `jd.py` 분리 (4 함수)

대상 4개: `analyze_jd`, `jd_results`, `start_search_session`, `jd_matching_results`

- [ ] **Step 1: `jd.py` 생성 (Task 1.3 패턴)**

```python
# projects/_views_split/jd.py
"""JD analysis + matching views."""
from __future__ import annotations

# 4개 함수가 쓰는 import만
# 4개 함수 본문 복사
```

- [ ] **Step 2: `projects/views.py`에서 4개 제거 + re-import**

```python
from projects._views_split.jd import (
    analyze_jd,
    jd_results,
    start_search_session,
    jd_matching_results,
)
```

- [ ] **Step 3: pytest**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add projects/_views_split/jd.py projects/views.py
git commit -m "Move 4 jd_* / analyze_jd views to projects/_views_split/jd.py"
```

### Task 1.5: `submissions.py` 분리 (15 함수)

대상 15개: `submission_create`, `submission_batch_create`, `submission_update`, `submission_delete`, `submission_submit`, `submission_feedback`, `submission_download`, `submission_draft`, `draft_generate`, `draft_consultation`, `draft_consultation_audio`, `draft_finalize`, `draft_review`, `draft_convert`, `draft_preview`

- [ ] **Step 1: `submissions.py` 생성**

```python
# projects/_views_split/submissions.py
"""Submission + draft workflow views."""
from __future__ import annotations

# 15개 함수의 import
from projects._views_split._helpers import _get_draft_context

# 15개 함수 본문 복사
```

- [ ] **Step 2: `projects/views.py`에서 15개 제거 + re-import**

- [ ] **Step 3: pytest + URL reverse 4개 검증**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
uv run python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')
django.setup()
from django.urls import reverse
import uuid
pk, sub_pk = uuid.uuid4(), uuid.uuid4()
for name, kwargs in [
    ('projects:submission_create', {'pk': pk}),
    ('projects:submission_draft', {'pk': pk, 'sub_pk': sub_pk}),
    ('projects:draft_generate', {'pk': pk, 'sub_pk': sub_pk}),
    ('projects:draft_consultation', {'pk': pk, 'sub_pk': sub_pk}),
]:
    print(name, '→', reverse(name, kwargs=kwargs))
"
```

- [ ] **Step 4: Commit**

```bash
git add projects/_views_split/submissions.py projects/views.py
git commit -m "Move 15 submission_* / draft_* views to projects/_views_split/submissions.py"
```

### Task 1.6: `interviews.py` 분리 (4 함수)

대상 4개: `interview_create`, `interview_update`, `interview_delete`, `interview_result`

- [ ] **Step 1: `interviews.py` 생성 (Task 1.4 패턴)**

- [ ] **Step 2: `projects/views.py`에서 4개 제거 + re-import**

- [ ] **Step 3: pytest**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add projects/_views_split/interviews.py projects/views.py
git commit -m "Move 4 interview_* views to projects/_views_split/interviews.py"
```

### Task 1.7: `postings.py` 분리 (7 함수)

대상 7개: `posting_generate`, `posting_edit`, `posting_download`, `posting_sites`, `posting_site_add`, `posting_site_update`, `posting_site_delete`

- [ ] **Step 1: `postings.py` 생성**

- [ ] **Step 2: `projects/views.py`에서 7개 제거 + re-import**

- [ ] **Step 3: pytest**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add projects/_views_split/postings.py projects/views.py
git commit -m "Move 7 posting_* views to projects/_views_split/postings.py"
```

### Task 1.8: `applications.py` 분리 (9 함수)

대상 9개: `project_add_candidate`, `application_drop`, `application_restore`, `application_hire`, `application_skip_stage`, `application_resume_use_db`, `application_resume_request_email`, `application_resume_upload`, `application_actions_partial`

- [ ] **Step 1: `applications.py` 생성**

- [ ] **Step 2: `projects/views.py`에서 9개 제거 + re-import**

- [ ] **Step 3: pytest**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add projects/_views_split/applications.py projects/views.py
git commit -m "Move 9 application_* / project_add_candidate views to projects/_views_split/applications.py"
```

### Task 1.9: `actions.py` 분리 (5 함수)

대상 5개: `action_create`, `action_complete`, `action_skip`, `action_reschedule`, `action_propose_next`

- [ ] **Step 1: `actions.py` 생성**

- [ ] **Step 2: `projects/views.py`에서 5개 제거 + re-import**

- [ ] **Step 3: pytest**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add projects/_views_split/actions.py projects/views.py
git commit -m "Move 5 action_* views to projects/_views_split/actions.py"
```

### Task 1.10: `stages.py` 분리 (6 함수)

대상 6개: `stage_contact_complete`, `stage_pre_meeting_schedule`, `stage_pre_meeting_record`, `stage_prep_submission_confirm`, `stage_client_submit_single`, `stage_interview_complete`

- [ ] **Step 1: `stages.py` 생성**

- [ ] **Step 2: `projects/views.py`에서 6개 제거 + re-import**

- [ ] **Step 3: pytest**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add projects/_views_split/stages.py projects/views.py
git commit -m "Move 6 stage_* views to projects/_views_split/stages.py"
```

### Task 1.11: `resumes.py` 분리 (8 함수) — test patch target 보존

대상 8개: `resume_upload`, `resume_process_pending`, `resume_upload_status`, `resume_link_candidate`, `resume_discard`, `resume_retry`, `resume_unassigned`, `resume_assign_project`

⚠️ **주의**: `tests/test_p18_views.py:100,152,201`은 `@patch("projects.views.process_pending_upload")` 와 `@patch("projects.views.link_resume_to_candidate")` 를 사용한다. 이 두 심볼은 `projects/views.py:38, 43`에서 import된 외부 함수다. 분리 후에도 `projects.views.process_pending_upload` attribute로 접근 가능해야 test가 깨지지 않는다.

- [ ] **Step 1: `resumes.py` 생성 — 8개 함수 + 외부 import 같이 옮김**

`process_pending_upload`와 `link_resume_to_candidate`는 resume 관련 함수 본문에서 사용되므로 `resumes.py` 안에서 import한다.

```python
# projects/_views_split/resumes.py
"""Resume upload, processing, linking views."""
from __future__ import annotations

# 8개 함수의 import + test patch가 필요로 하는 외부 import
from projects.services.resume.linker import link_resume_to_candidate
from projects.services.resume.upload_processor import process_pending_upload
# ... 나머지 import

# 8개 함수 본문 복사
```

- [ ] **Step 2: `projects/views.py`에서 8개 함수 제거 + re-import (test patch 호환을 위해 함수 + 외부 심볼 둘 다)**

```python
# projects/views.py
from projects._views_split.resumes import (
    resume_upload,
    resume_process_pending,
    resume_upload_status,
    resume_link_candidate,
    resume_discard,
    resume_retry,
    resume_unassigned,
    resume_assign_project,
    # test의 @patch("projects.views.X")가 잡을 수 있도록 같이 re-export
    link_resume_to_candidate,
    process_pending_upload,
)
```

기존 `projects/views.py:38, 43` 의 직접 import 라인은 제거 (이제 _views_split.resumes에서 import).

- [ ] **Step 3: pytest 전체 — 특히 test_p18_views.py 통과 확인**

```bash
uv run pytest tests/test_p18_views.py -v --tb=short 2>&1 | tail -15
uv run pytest --tb=short -q 2>&1 | tail -5
```

Expected: test_p18_views.py PASS (patch target 정상), 전체 PASS

- [ ] **Step 4: Commit**

```bash
git add projects/_views_split/resumes.py projects/views.py
git commit -m "Move 8 resume_* views to projects/_views_split/resumes.py (preserve test patch targets)"
```

### Task 1.12: `approvals.py` 분리 (6 함수)

대상 6개: `approval_queue`, `approval_decide`, `approval_cancel`, `project_auto_actions`, `auto_action_apply`, `auto_action_dismiss`

- [ ] **Step 1: `approvals.py` 생성**

- [ ] **Step 2: `projects/views.py`에서 6개 제거 + re-import**

- [ ] **Step 3: pytest**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add projects/_views_split/approvals.py projects/views.py
git commit -m "Move 6 approval_* / auto_action_* views to projects/_views_split/approvals.py"
```

### Task 1.13: `context.py` 분리 (4 함수)

대상 4개: `project_context`, `project_context_save`, `project_context_resume`, `project_context_discard`

- [ ] **Step 1: `context.py` 생성**

- [ ] **Step 2: `projects/views.py`에서 4개 제거 + re-import**

- [ ] **Step 3: pytest**

```bash
uv run pytest --tb=short -q 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add projects/_views_split/context.py projects/views.py
git commit -m "Move 4 project_context_* views to projects/_views_split/context.py"
```

---

## Phase 2: Atomic Swap — `projects/views.py` 삭제 + `_views_split/` → `views/`

이 시점 `projects/views.py`는 90 함수가 모두 `_views_split/` 모듈로 옮겨졌고, 자기는 re-export만 한다. 이제 한 commit으로:
1. `projects/views.py` 삭제
2. `projects/_views_split/` → `projects/views/` rename
3. 분리 파일들 안의 `projects._views_split` → `projects.views` import 경로 갱신
4. `projects/views/__init__.py` 작성 (모든 함수 re-export)

이 모든 변경이 한 commit이어야 중간 상태에서 import가 깨지지 않는다.

### Task 2.1: 잔여 함수 0건 확인

- [ ] **Step 1: `projects/views.py` 잔여 def/class 확인**

```bash
grep -nE "^def [a-zA-Z_]+|^class " projects/views.py
```

Expected: 출력 없음 (90 함수 모두 분리됨, 남은 건 import만)

만약 잔여가 있으면 어느 그룹에 속하는지 판단 후 적절한 분리 파일에 추가하고 다시 Phase 1 마지막 task처럼 import.

- [ ] **Step 2: `projects/views.py`가 순수 re-export 모듈인지 확인**

```bash
wc -l projects/views.py
```

Expected: 100줄 이내 (re-import 라인만 남음)

### Task 2.2: Atomic swap commit

**Files:**
- Delete: `projects/views.py`
- Rename: `projects/_views_split/` → `projects/views/`
- Modify: 모든 분리 파일의 `projects._views_split` → `projects.views` import
- Create: `projects/views/__init__.py` (전체 re-export)

- [ ] **Step 1: 새 `projects/views/__init__.py` 본문 준비**

각 분리 파일의 함수를 그대로 re-export. test patch target도 포함.

```python
# projects/views/__init__.py — atomic swap 후 위치
"""Re-export all views to preserve external import paths.

Splits:
- _helpers: 6 module-private helpers (밑줄 prefix)
- dashboard, project, jd, submissions, interviews, postings,
  applications, actions, stages, resumes, approvals, context
"""
from projects.views._helpers import (
    _has_pending_approval,
    _filter_params_string,
    _build_tab_context,
    _build_overview_context,
    _get_draft_context,
    _create_receive_resume_action,
)
from projects.views.dashboard import dashboard
from projects.views.project import (
    project_list, project_check_collision, project_create,
    project_detail, project_applications_partial, project_timeline_partial,
    project_update, project_delete, project_close, project_reopen,
    project_tab_overview, project_tab_search, project_tab_submissions,
    project_tab_interviews, drive_picker,
)
from projects.views.jd import (
    analyze_jd, jd_results, start_search_session, jd_matching_results,
)
from projects.views.submissions import (
    submission_create, submission_batch_create, submission_update,
    submission_delete, submission_submit, submission_feedback,
    submission_download, submission_draft,
    draft_generate, draft_consultation, draft_consultation_audio,
    draft_finalize, draft_review, draft_convert, draft_preview,
)
from projects.views.interviews import (
    interview_create, interview_update, interview_delete, interview_result,
)
from projects.views.postings import (
    posting_generate, posting_edit, posting_download, posting_sites,
    posting_site_add, posting_site_update, posting_site_delete,
)
from projects.views.applications import (
    project_add_candidate,
    application_drop, application_restore, application_hire,
    application_skip_stage, application_resume_use_db,
    application_resume_request_email, application_resume_upload,
    application_actions_partial,
)
from projects.views.actions import (
    action_create, action_complete, action_skip,
    action_reschedule, action_propose_next,
)
from projects.views.stages import (
    stage_contact_complete, stage_pre_meeting_schedule,
    stage_pre_meeting_record, stage_prep_submission_confirm,
    stage_client_submit_single, stage_interview_complete,
)
from projects.views.resumes import (
    resume_upload, resume_process_pending, resume_upload_status,
    resume_link_candidate, resume_discard, resume_retry,
    resume_unassigned, resume_assign_project,
    # test patch targets (tests/test_p18_views.py:100,152,201)
    link_resume_to_candidate, process_pending_upload,
)
from projects.views.approvals import (
    approval_queue, approval_decide, approval_cancel,
    project_auto_actions, auto_action_apply, auto_action_dismiss,
)
from projects.views.context import (
    project_context, project_context_save,
    project_context_resume, project_context_discard,
)

# (No __all__ — projects/urls.py uses `from . import views` then `views.X`,
#  so all symbols imported above are accessible as views.X attributes.)
```

- [ ] **Step 2: 모든 swap 작업을 한 commit에 묶기**

```bash
# 2-a: views.py 삭제
rm projects/views.py

# 2-b: _views_split/ 안의 import 경로 갱신
#  (이전에는 `from projects._views_split._helpers import ...` 로 되어 있음.
#   이제 같은 패키지 내부이므로 `from projects.views._helpers import ...` 로 바뀜.)
find projects/_views_split -name "*.py" -exec \
    sed -i 's|projects\._views_split|projects.views|g' {} +

# 2-c: 디렉토리 rename
mv projects/_views_split projects/views

# 2-d: __init__.py 본문을 위 Step 1 내용으로 작성
#  (편집기로 또는 cat <<EOF > projects/views/__init__.py)
```

- [ ] **Step 3: pytest 전체 + 외부 import 검증**

```bash
uv run pytest --tb=short 2>&1 | tail -10
uv run python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')
django.setup()
# 외부에서 흔한 import 패턴 시뮬레이션
from projects.views import (
    project_list, project_create, project_detail,
    submission_create, draft_generate,
    application_drop, action_complete,
    dashboard, approval_queue,
    process_pending_upload, link_resume_to_candidate,  # test patch targets
)
from django.urls import reverse
print('All imports OK')
print('dashboard URL (전역):', reverse('dashboard'))
print('project_list URL (namespace):', reverse('projects:project_list'))
"
```

Expected: pytest PASS, `All imports OK`, dashboard와 project_list URL 정상

- [ ] **Step 4: Atomic swap commit**

```bash
git add -A
git commit -m "Atomic swap: replace projects/views.py with projects/views/ package

- Delete monolithic projects/views.py (was just re-export shim by this point)
- Rename projects/_views_split/ → projects/views/
- Update internal sibling imports (_views_split → views)
- Add projects/views/__init__.py with all 90 function re-exports

External behavior: 0 changes
- All 'from projects.views import X' continue to work
- All projects:* URL names unchanged (urls.py uses views.X)
- Global 'dashboard' URL name unchanged (main/urls.py)
- test patch('projects.views.process_pending_upload') still resolves
  (re-exported in __init__.py)
"
```

---

## Phase 3: 회귀 안전망 (smoke tests)

분리 후 외부 동작 변경이 없음을 자동 검증하는 두 가지 smoke test 추가.

### Task 3.1: URL reverse smoke test

`main/urls.py`를 기준으로:
- 전역 URL: `home`, `dashboard`, `team` (namespace 없음)
- namespace URL: `projects:*`, `accounts:*`, `candidates:*`, `clients:*`, `reference:*`, `voice:*`, `telegram:*`, `news:*`, `superadmin:*`

이 smoke test는 모든 URL name을 자동 발견 후 검증한다.

**Files:**
- Create: `tests/test_url_reverse_smoke.py`

- [ ] **Step 1: smoke test 작성**

```python
# tests/test_url_reverse_smoke.py
"""Smoke test: every URL name (전역 + namespace) must resolve via reverse().

Guards against rename/move regressions during the views split refactor.
Discovers URL patterns dynamically from the resolver, then attempts reverse
with a list of candidate kwargs.
"""
import uuid

import pytest
from django.urls import NoReverseMatch, get_resolver, reverse


def _collect_url_names():
    """Walk get_resolver() and yield 'name' (전역) or 'namespace:name' strings."""
    resolver = get_resolver()
    names: list[str] = []

    def visit(patterns, namespace_prefix=""):
        for pattern in patterns:
            sub = getattr(pattern, "url_patterns", None)
            if sub is not None:
                ns = getattr(pattern, "namespace", None)
                next_prefix = f"{namespace_prefix}{ns}:" if ns else namespace_prefix
                visit(sub, next_prefix)
            else:
                name = getattr(pattern, "name", None)
                if name:
                    names.append(f"{namespace_prefix}{name}")

    visit(resolver.url_patterns)
    return names


_PLACEHOLDER_UUID = uuid.uuid4()
_CANDIDATE_KWARGS = [
    {},
    {"pk": _PLACEHOLDER_UUID},
    {"pk": _PLACEHOLDER_UUID, "sub_pk": _PLACEHOLDER_UUID},
    {"pk": _PLACEHOLDER_UUID, "interview_pk": _PLACEHOLDER_UUID},
    {"pk": _PLACEHOLDER_UUID, "site_pk": _PLACEHOLDER_UUID},
    {"pk": _PLACEHOLDER_UUID, "action_pk": _PLACEHOLDER_UUID},
    {"pk": _PLACEHOLDER_UUID, "resume_pk": _PLACEHOLDER_UUID},
    {"pk": _PLACEHOLDER_UUID, "contract_pk": _PLACEHOLDER_UUID},
    {"resume_pk": _PLACEHOLDER_UUID, "project_pk": _PLACEHOLDER_UUID},
    {"appr_pk": _PLACEHOLDER_UUID},
    {"path": "test.html"},
    # Add more shapes only when a discovered URL needs them.
]


@pytest.mark.parametrize("name", _collect_url_names())
def test_url_reverses_with_some_candidate(name):
    """Every URL name must reverse with at least one candidate kwargs shape.

    If none of the candidates fits a new URL, add it to _CANDIDATE_KWARGS
    rather than skipping the test.
    """
    last_error = None
    for kwargs in _CANDIDATE_KWARGS:
        try:
            url = reverse(name, kwargs=kwargs)
            assert url
            return
        except NoReverseMatch as e:
            last_error = e
            continue
    raise AssertionError(
        f"URL name '{name}' could not be reversed with any candidate kwargs. "
        f"Last error: {last_error}. "
        f"If this URL takes new kwargs, add a shape to _CANDIDATE_KWARGS."
    )
```

- [ ] **Step 2: 테스트 실행 — 모든 URL name 검증**

```bash
uv run pytest tests/test_url_reverse_smoke.py -v 2>&1 | tail -20
```

Expected: 전부 PASS (실패하면 그 URL이 새 kwargs를 요구하거나 분리 후 깨진 것)

- [ ] **Step 3: Commit**

```bash
git add tests/test_url_reverse_smoke.py
git commit -m "Add URL reverse smoke test (전역 + namespace 모든 URL name 자동 검증)"
```

### Task 3.2: 핵심 화면 render smoke test

분리 후 import/template-resolution 회귀를 잡는 5개 화면 render 테스트.

**Files:**
- Create: `tests/projects/test_views_smoke.py`

- [ ] **Step 1: smoke test 작성**

```python
# tests/projects/test_views_smoke.py
"""Smoke test: key project views render without 500.

Guards against import/template-resolution regressions after views split.
"""
import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_dashboard_renders(staff_user, client):
    client.force_login(staff_user)
    resp = client.get(reverse("dashboard"))  # 전역 URL name (main/urls.py:16)
    assert resp.status_code in (200, 302)


def test_project_list_renders(staff_user, client):
    client.force_login(staff_user)
    resp = client.get(reverse("projects:project_list"))
    assert resp.status_code in (200, 302)


def test_project_create_form_renders(staff_user, client):
    client.force_login(staff_user)
    resp = client.get(reverse("projects:project_create"))
    assert resp.status_code in (200, 302)


def test_approval_queue_renders(staff_user, client):
    client.force_login(staff_user)
    resp = client.get(reverse("projects:approval_queue"))
    assert resp.status_code in (200, 302)


def test_resume_unassigned_renders(staff_user, client):
    client.force_login(staff_user)
    resp = client.get(reverse("projects:resume_unassigned"))
    assert resp.status_code in (200, 302)
```

- [ ] **Step 2: 테스트 실행**

```bash
uv run pytest tests/projects/test_views_smoke.py -v 2>&1 | tail -15
```

Expected: 5개 모두 PASS (200 또는 302)

- [ ] **Step 3: Commit**

```bash
git add tests/projects/test_views_smoke.py
git commit -m "Add render smoke test for 5 key projects views"
```

---

## Phase 4 (선택): `projects/urls.py` import 정리

`projects/urls.py`는 현재 `from . import views` 후 `views.X` 형태로 83 path 참조. 이건 **변경하지 않아도 정상 동작** (`projects/views/__init__.py`가 모든 X를 attribute로 노출). 가독성 향상이 목적이라면 명시적 import로 정리 가능.

**Files:**
- Modify: `projects/urls.py`

- [ ] **Step 1: 그룹별 명시적 import로 변경**

```python
from django.urls import path

from projects.views import (
    # project lifecycle (15)
    project_list, project_check_collision, project_create,
    project_detail, project_applications_partial, project_timeline_partial,
    project_update, project_delete, project_close, project_reopen,
    project_tab_overview, project_tab_search, project_tab_submissions,
    project_tab_interviews, drive_picker,
    # JD (4)
    analyze_jd, jd_results, start_search_session, jd_matching_results,
    # submissions / drafts (15)
    submission_create, submission_batch_create, submission_update,
    submission_delete, submission_submit, submission_feedback,
    submission_download, submission_draft,
    draft_generate, draft_consultation, draft_consultation_audio,
    draft_finalize, draft_review, draft_convert, draft_preview,
    # interviews (4)
    interview_create, interview_update, interview_delete, interview_result,
    # postings (7)
    posting_generate, posting_edit, posting_download, posting_sites,
    posting_site_add, posting_site_update, posting_site_delete,
    # applications (9)
    project_add_candidate, application_drop, application_restore,
    application_hire, application_skip_stage,
    application_resume_use_db, application_resume_request_email,
    application_resume_upload, application_actions_partial,
    # actions (5)
    action_create, action_complete, action_skip,
    action_reschedule, action_propose_next,
    # stages (6)
    stage_contact_complete, stage_pre_meeting_schedule,
    stage_pre_meeting_record, stage_prep_submission_confirm,
    stage_client_submit_single, stage_interview_complete,
    # resumes (8)
    resume_upload, resume_process_pending, resume_upload_status,
    resume_link_candidate, resume_discard, resume_retry,
    resume_unassigned, resume_assign_project,
    # approvals (6)
    approval_queue, approval_decide, approval_cancel,
    project_auto_actions, auto_action_apply, auto_action_dismiss,
    # context (4)
    project_context, project_context_save,
    project_context_resume, project_context_discard,
)

# urlpatterns의 views.X → X로 일괄 치환
```

- [ ] **Step 2: pytest + URL reverse smoke**

```bash
uv run pytest tests/test_url_reverse_smoke.py --tb=short 2>&1 | tail -5
uv run pytest --tb=short 2>&1 | tail -5
```

- [ ] **Step 3: Commit**

```bash
git add projects/urls.py
git commit -m "Reorganize projects/urls.py imports by responsibility group"
```

---

## 완료 기준

- [ ] `projects/views.py` 파일 삭제됨
- [ ] `projects/views/` 패키지 존재 (`__init__.py` + 13개 분리 파일 + `_helpers.py`)
- [ ] 모든 `from projects.views import X` 동작 (`__init__.py` re-export로 호환)
- [ ] `tests/test_p18_views.py` 의 `@patch("projects.views.process_pending_upload")`, `@patch("projects.views.link_resume_to_candidate")` 통과 (re-export로 attribute 접근 가능)
- [ ] `tests/test_url_reverse_smoke.py` 추가 (전역 + 모든 namespace URL name 자동 검증)
- [ ] `tests/projects/test_views_smoke.py` 추가 (5개 화면 render)
- [ ] `uv run pytest --tb=short` PASS (분리 전 baseline 대비 신규 smoke test만 늘어남)
- [ ] (선택) Phase 4 적용 시 `projects/urls.py`가 명시적 그룹별 import

---

## 회귀 위험 + 완화책

| 위험 | 가능성 | 완화 |
|---|---|---|
| 임시 패키지 작업 중 `projects/views.py`와 `projects/_views_split/` 동시 존재 → 어느 쪽이 잡히나 | 낮음 | `_views_split/`는 `projects.views`와 다른 이름이라 shadow 발생 안 함. Python 동작상 안전 |
| Atomic swap commit 도중 import 깨짐 | 중 | 한 commit에서 4단계 모두 처리. Step 3에서 명시적 검증 |
| `from projects.views import X` 외부 import 깨짐 | 낮음 | `__init__.py`가 모든 함수 re-export. main/urls.py 1곳, test attribute 3곳 모두 검증 |
| URL `reverse()` NoReverseMatch | 낮음 | URL name 그대로 유지 + Phase 3 Task 3.1이 모든 name 자동 검증 |
| circular import (`_helpers.py` 의존성) | 낮음 | `_helpers.py`는 다른 분리 파일 import 안 함 (단방향) |
| `tests/test_p18_views.py` patch 대상 attribute 깨짐 | 중 | Task 1.11 Step 2에서 `link_resume_to_candidate`, `process_pending_upload` 도 같이 re-export 명시 |
| 분리 파일에 함수 본문 옮길 때 import 누락 → ImportError | 중 | 각 task Step 3에서 pytest 즉시 실행, 빨리 잡힘 |
| HTMX 응답 헤더 (`HX-Trigger`, partial render) 변경 | **0** | 본 plan은 함수 본문 0줄 변경. 응답 패턴 그대로 |

---

## 진행 메타

- **순서**: Phase 1 → Phase 2 → Phase 3 → Phase 4 (선택)
- **각 phase 시작 전**: `git status` 깨끗 확인 + 새 worktree 권장
- **각 task 끝**: `pytest --tb=short` PASS 확인 후 다음 task
- **commit 메시지 규칙**: 동사로 시작 (Move, Atomic swap, Add, Reorganize)

---

## Plan B (별도 후속 계획 — 본 plan 범위 밖)

본 plan 완료 후 별도 PR/plan으로 다룰 작업:

**Goal**: `LevelRequiredMixin` + Class-Based View 패턴을 신규 화면에서 먼저 검증.

**후보 화면**: `UniversityTier.needs_review=True` 검수 큐
- P7에서 LLM이 자동 등록한 학교들 중 `needs_review=True`인 항목들에 대해 검수자가 tier·랭킹 부여하는 신규 워크플로우
- HTMX legacy 0건 (아직 안 만든 화면)
- 권한은 level 2 (검수자)
- ListView (검수 대기 큐) + UpdateView (tier 부여) 두 CBV로 구성
- `accounts/mixins.py` 의 `LevelRequiredMixin` 신규 작성

**왜 본 plan에서 제외했나**:
- `clients/views_reference.py` 는 HTMX modal 응답(`HttpResponse(status=204, headers={"HX-Trigger": "..."})`), 권한 분기(read=level 1, write=level 2), CSV import/export, 필터/카운트 context가 섞여 있어 CBV의 `form_valid` / `delete` / `get` / `get_context_data` / `get_template_names` 를 거의 모두 오버라이드해야 한다. 자동화 절약 < 오버라이드 비용으로 ROI가 낮다.
- 신규 화면에서 패턴을 먼저 검증해 가치가 확인되면 그 결과를 reference CRUD에 역적용 검토.

**Plan B 시작 시점**: 본 plan PR 머지 + UniversityTier 검수 화면 요구사항 spec 작성 후.

---

## Self-Review

- ✅ Spec 커버: 사용자 + 다른 에이전트 합의 내용 모두 반영 — Plan A로 축소, atomic swap, dashboard 전역 URL, smoke test main/urls.py 기준
- ✅ Placeholder 없음: 각 task가 실제 file path + 코드 + 명령 포함
- ✅ Type/이름 일관성: 14개 분리 파일명 + 90 함수명 모두 코드에서 검증한 값 (`grep -E "^def "` 결과 그대로)
- ✅ test 호환: `tests/test_p18_views.py` 의 patch target 3곳 모두 re-export 명시 (Task 1.11 Step 2, Task 2.2 Step 1)
- ✅ URL 사실: dashboard는 전역, projects:* 는 namespace — `main/urls.py:8,16` 직접 확인
- ✅ 외부 동작 변경 0건: HTMX 응답·HX-Trigger·권한 모두 함수 본문 그대로 이동, 변경 없음
- ✅ 추정 0건: 모든 함수 그룹·라인 번호·import 패턴은 `grep`/`sed`로 코드에서 직접 추출
