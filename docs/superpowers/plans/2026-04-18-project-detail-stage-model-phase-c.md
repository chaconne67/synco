# 프로젝트 상세 페이지 단계 모델 Phase C 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 프로젝트 상세 페이지를 "프로젝트 레벨 작업 영역 A" + "후보자 카드 리스트 영역 B"로 재구성하고, 8단계 업무 프로세스를 새로운 분류 (서칭=프로젝트 레벨 / 7단계=후보자 카드)와 네이밍으로 전환하며, 각 후보자 단계별 전용 파티얼을 구축한다.

**Architecture:** 
- 단계를 프로젝트 레벨/후보자 레벨로 분리. 카드에는 7단계 진행바(서칭 제외)만 표시.
- 네이밍 변경: 이력서 수집 → 이력서 준비, 제출 준비 → 이력서 작성(제출용), 고객사 제출 → 이력서 제출.
- 각 카드 단계에 단계 전용 partial을 둬 "컨설턴트가 지금 할 일"을 명확하게 제시.
- 이력서 제출은 배치(영역 A)·개별(카드) 경로 공존. `Submission.batch_id` UUID로 같은 배치 묶음 표현.
- 별도 설계가 필요한 항목(녹음 STT·고객사별 템플릿·이메일 자동 수집·AI 포스팅 등)은 본 계획 범위 밖 — UI 플레이스홀더 + 문서 참조만 남긴다.

**Tech Stack:** Django 5.2, HTMX, Tailwind, PostgreSQL, uv, pytest-django.

**관련 문서:**
- 설계 문서: [docs/superpowers/specs/2026-04-18-project-detail-stage-model-design.md](../specs/2026-04-18-project-detail-stage-model-design.md)
- 이전 세션 핸드오프: [docs/session-handoff/2026-04-18-project-detail-L2.md](../../session-handoff/2026-04-18-project-detail-L2.md)

---

## 파일 구조 개요

### 새로 생성
```
projects/
├─ migrations/
│  └─ NNNN_submission_batch_and_stage_labels.py
├─ templates/projects/
│  ├─ project_detail.html                         (재작성)
│  └─ partials/
│     ├─ project_area_a.html                      (신규: 서칭 + 배치제출 래퍼)
│     ├─ area_a_searching.html                    (신규: 서칭 도구)
│     ├─ area_a_channel_placeholder.html          (신규: 외부 채널 "준비중")
│     ├─ area_a_submission_batch.html             (신규: 배치 제출 UI)
│     ├─ stage_contact.html                       (신규: 접촉 단계)
│     ├─ stage_resume.html                        (신규: 이력서 준비 — stage_resume_methods.html 리네임)
│     ├─ stage_pre_meeting.html                   (신규: 사전미팅 일정/진행/기록)
│     ├─ stage_prep_submission.html               (신규: 이력서 작성 제출용)
│     ├─ stage_client_submit.html                 (신규: 이력서 제출)
│     ├─ stage_interview.html                     (신규: 면접 + after-interview review)
│     └─ stage_hired.html                         (신규: 입사 확정)
└─ services/
   └─ searching.py                                (신규: DB 서칭 → Application 생성 서비스)

tests/projects/
├─ test_stage_labels.py                           (신규)
├─ test_card_stages.py                            (신규)
├─ test_searching_service.py                      (신규)
├─ test_submission_batch.py                       (신규)
└─ test_stage_partials.py                         (신규)
```

### 수정
```
projects/
├─ models.py                                       (STAGES_ORDER 라벨·Submission.batch_id)
├─ urls.py                                         (신규 엔드포인트 다수)
├─ views.py                                        (신규 뷰 + 기존 project_detail 조정)
├─ forms.py                                        (ContactCompleteForm, PreMeetingScheduleForm 등)
└─ templates/projects/partials/
   ├─ application_card.html                        (7단계 진행바 + stage partial include 스위칭)
   └─ stage_resume_methods.html                    (삭제 — stage_resume.html로 이동)

accounts/templates/accounts/partials/ — 영향 없음
candidates/
├─ views.py                                        (프로젝트 컨텍스트 모드)
└─ templates/candidates/partials/candidate_card.html (프로젝트에 추가 버튼)
```

### 제거/정리 (Task 17)
```
projects/views.py 의 project_tab_overview, project_tab_search, project_tab_submissions, project_tab_interviews 관련 레거시 뷰
projects/templates/projects/partials/tab_*.html 레거시 템플릿
```

---

## Task 1: STAGES_ORDER 라벨 네이밍 변경

**Files:**
- Modify: `projects/models.py` (STAGES_ORDER — 3개 라벨만)
- Create: `projects/management/commands/update_stage_labels.py`
- Test: `tests/test_stage_labels.py`

### Step 1.1: 테스트 작성 (실패 상태)

- [ ] **Create `tests/test_stage_labels.py`:**

```python
import pytest
from projects.models import STAGES_ORDER


def test_stages_order_renamed_labels():
    """3단계 네이밍 변경 — 이력서 관련 3개만 바뀐다."""
    labels = dict(STAGES_ORDER)
    assert labels["resume"] == "이력서 준비"
    assert labels["prep_submission"] == "이력서 작성(제출용)"
    assert labels["client_submit"] == "이력서 제출"


def test_unchanged_labels():
    """나머지 5개 단계 라벨은 유지."""
    labels = dict(STAGES_ORDER)
    assert labels["sourcing"] == "서칭"
    assert labels["contact"] == "접촉"
    assert labels["pre_meeting"] == "사전 미팅"
    assert labels["interview"] == "면접"
    assert labels["hired"] == "입사"
```

- [ ] **Run test to confirm failure:**

```bash
uv run pytest tests/test_stage_labels.py::test_stages_order_renamed_labels -v
```
Expected: FAIL — 현재 라벨은 "이력서 수집", "제출 준비", "고객사 제출"

### Step 1.2: models.py 라벨 교체

- [ ] **Edit `projects/models.py` STAGES_ORDER (around line 97):**

```python
STAGES_ORDER = [
    ("sourcing",        "서칭"),
    ("contact",         "접촉"),
    ("resume",          "이력서 준비"),
    ("pre_meeting",     "사전 미팅"),
    ("prep_submission", "이력서 작성(제출용)"),
    ("client_submit",   "이력서 제출"),
    ("interview",       "면접"),
    ("hired",           "입사"),
]
```

- [ ] **Run tests to verify pass:**

```bash
uv run pytest tests/test_stage_labels.py -v
```
Expected: PASS 2/2

### Step 1.3: ActionType 라벨 관리 명령어

- [ ] **Create `projects/management/commands/update_stage_labels.py`:**

```python
"""ActionType.label_ko 를 최신 네이밍 정책에 맞게 업데이트."""
from django.core.management.base import BaseCommand

from projects.models import ActionType


LABEL_UPDATES = {
    # 이력서 준비 단계
    "receive_resume":   "이력서 받기",
    "convert_resume":   "이력서 정리하기",
    # 이력서 작성(제출용) 단계
    "prepare_submission": "제출용 이력서 작성",
    "submit_to_pm":       "내부 검토 요청",
    # 이력서 제출 단계
    "submit_to_client":   "이력서 고객사 제출",
    "await_doc_review":   "서류 검토 대기",
    "receive_doc_feedback": "서류 피드백 수령",
}


class Command(BaseCommand):
    help = "ActionType.label_ko 를 Phase C 네이밍 정책대로 업데이트."

    def handle(self, *args, **options):
        updated = 0
        for code, label in LABEL_UPDATES.items():
            qs = ActionType.objects.filter(code=code)
            if not qs.exists():
                self.stdout.write(self.style.WARNING(f"skip: {code} not found"))
                continue
            qs.update(label_ko=label)
            updated += 1
            self.stdout.write(f"updated: {code} → {label}")
        self.stdout.write(self.style.SUCCESS(f"Done. {updated} rows updated."))
```

- [ ] **Run the command:**

```bash
uv run python manage.py update_stage_labels
```
Expected: 각 code 별 "updated: ..." 라인 + 최종 "Done. N rows updated."

### Step 1.4: 커밋

- [ ] **Commit:**

```bash
git add projects/models.py projects/management/commands/update_stage_labels.py tests/test_stage_labels.py
git commit -m "refactor(projects): rename resume/submission stage labels per Phase C spec"
```

---

## Task 2: CARD_STAGES_ORDER 상수 + 후보자 카드 7단계 property

**Files:**
- Modify: `projects/models.py` (CARD_STAGES_ORDER 추가, current_stage / stages_passed 는 그대로)
- Test: `tests/test_card_stages.py`

### Step 2.1: 테스트 작성

- [ ] **Create `tests/test_card_stages.py`:**

```python
import pytest
from projects.models import CARD_STAGES_ORDER, STAGES_ORDER


def test_card_stages_excludes_sourcing():
    card_ids = [s for s, _ in CARD_STAGES_ORDER]
    assert "sourcing" not in card_ids
    assert len(card_ids) == 7


def test_card_stages_order():
    expected = [
        "contact",
        "resume",
        "pre_meeting",
        "prep_submission",
        "client_submit",
        "interview",
        "hired",
    ]
    assert [s for s, _ in CARD_STAGES_ORDER] == expected


def test_card_stages_labels_match_project_stages():
    """라벨은 프로젝트 레벨 STAGES_ORDER와 동일 (중복 정의 방지)."""
    project_labels = dict(STAGES_ORDER)
    for stage_id, label in CARD_STAGES_ORDER:
        assert label == project_labels[stage_id]
```

- [ ] **Run: FAIL (CARD_STAGES_ORDER 없음)**

```bash
uv run pytest tests/test_card_stages.py -v
```

### Step 2.2: 모델에 CARD_STAGES_ORDER 추가

- [ ] **Edit `projects/models.py` (STAGES_ORDER 정의 바로 아래에 추가):**

```python
# 후보자 카드 진행바에 표시할 단계 (서칭은 프로젝트 레벨이라 제외)
CARD_STAGES_ORDER = [
    (sid, label) for sid, label in STAGES_ORDER if sid != "sourcing"
]
```

- [ ] **Run: PASS 3/3**

### Step 2.3: 커밋

- [ ] **Commit:**

```bash
git add projects/models.py tests/test_card_stages.py
git commit -m "feat(projects): add CARD_STAGES_ORDER for per-candidate 7-stage view"
```

---

## Task 3: Submission batch_id 필드 추가

**Files:**
- Modify: `projects/models.py` (Submission)
- Create: `projects/migrations/NNNN_submission_batch_id.py`
- Test: `tests/test_submission_batch.py`

### Step 3.1: 테스트 작성 (실패)

- [ ] **Create `tests/test_submission_batch.py`:**

```python
import uuid
import pytest
from projects.models import Submission


def test_submission_has_batch_id_field():
    field = Submission._meta.get_field("batch_id")
    assert field.null is True
    assert field.blank is True


@pytest.mark.django_db
def test_submissions_can_share_batch_id(submission_factory):
    """같은 batch_id로 여러 Submission 묶기 가능."""
    batch = uuid.uuid4()
    s1 = submission_factory(batch_id=batch)
    s2 = submission_factory(batch_id=batch)
    s3 = submission_factory(batch_id=None)  # 개별 제출
    
    batch_members = Submission.objects.filter(batch_id=batch)
    assert batch_members.count() == 2
    assert s3 not in batch_members
```

- [ ] **Check if `submission_factory` fixture exists, else add to `tests/conftest.py`:**

```bash
uv run pytest tests/test_submission_batch.py -v
```
Expected: ERROR — fixture missing 또는 field missing

- [ ] **If fixture missing, append to `tests/conftest.py`:**

```python
@pytest.fixture
def submission_factory(db, application_factory, action_type_factory):
    from projects.models import ActionItem, ActionItemStatus, Submission
    
    def _make(**kwargs):
        batch_id = kwargs.pop("batch_id", None)
        app = kwargs.pop("application", None) or application_factory()
        at = action_type_factory(code="submit_to_client")
        ai = ActionItem.objects.create(
            application=app,
            action_type=at,
            title="Test submit",
            status=ActionItemStatus.DONE,
        )
        return Submission.objects.create(
            action_item=ai,
            batch_id=batch_id,
        )
    return _make
```

### Step 3.2: 모델 필드 추가 + 마이그레이션

- [ ] **Edit `projects/models.py` Submission class — after `notes = ...` line:**

```python
    batch_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="같은 배치로 제출된 Submission들이 공유하는 UUID. None이면 개별 제출.",
    )
```

- [ ] **Generate migration:**

```bash
uv run python manage.py makemigrations projects --name submission_batch_id
```
Expected: `projects/migrations/NNNN_submission_batch_id.py` 생성

- [ ] **Apply migration:**

```bash
uv run python manage.py migrate projects
```

- [ ] **Run tests: PASS 2/2**

```bash
uv run pytest tests/test_submission_batch.py -v
```

### Step 3.3: 커밋

- [ ] **Commit:**

```bash
git add projects/models.py projects/migrations/*submission_batch_id*.py tests/test_submission_batch.py tests/conftest.py
git commit -m "feat(projects): add Submission.batch_id for grouping batch-submitted resumes"
```

---

## Task 4: project_detail.html 을 영역 A/B 구조로 재작성

**Files:**
- Modify: `projects/templates/projects/project_detail.html`
- Create: `projects/templates/projects/partials/project_area_a.html`
- Test: `tests/test_project_detail_layout.py`

### Step 4.1: 레이아웃 테스트 작성

- [ ] **Create `tests/test_project_detail_layout.py`:**

```python
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_project_detail_has_area_a_and_b(client, consultant_user, project_factory):
    project = project_factory(organization=consultant_user.org)
    client.force_login(consultant_user)
    resp = client.get(reverse("projects:project_detail", args=[project.pk]))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert 'id="project-area-a"' in content
    assert 'id="project-area-b"' in content
```

- [ ] **Check `consultant_user` / `project_factory` fixtures exist in `tests/conftest.py`. If not, grep for similar fixtures and reuse patterns.**

```bash
uv run pytest tests/test_project_detail_layout.py -v
```
Expected: FAIL — div id not present

### Step 4.2: area_a partial 생성

- [ ] **Create `projects/templates/projects/partials/project_area_a.html`:**

```django
{# 프로젝트 레벨 작업 영역 — 서칭 도구 + 배치 제출 관리 #}
<section id="project-area-a" class="space-y-6 mb-8">
  <div class="bg-surface rounded-card shadow-card p-6">
    <h2 class="text-lg font-semibold mb-4">서칭</h2>
    {% include "projects/partials/area_a_searching.html" %}
  </div>

  <div class="bg-surface rounded-card shadow-card p-6">
    <h2 class="text-lg font-semibold mb-4">이력서 배치 제출</h2>
    {% include "projects/partials/area_a_submission_batch.html" %}
  </div>
</section>
```

### Step 4.3: 빈 자리표시 파티얼 생성 (Task 5·6·7에서 채움)

- [ ] **Create `projects/templates/projects/partials/area_a_searching.html`:**

```django
<div class="text-sm text-muted">(서칭 도구 — Task 5에서 구현)</div>
```

- [ ] **Create `projects/templates/projects/partials/area_a_submission_batch.html`:**

```django
<div class="text-sm text-muted">(배치 제출 관리 — Task 7에서 구현)</div>
```

### Step 4.4: project_detail.html 재작성

- [ ] **Read current `projects/templates/projects/project_detail.html` first** (크기 큰 경우 기존 구조 보존하며 A/B wrapper 삽입)

```bash
wc -l projects/templates/projects/project_detail.html
```

- [ ] **Edit `projects/templates/projects/project_detail.html`** — 헤더 블록 유지, 기존 applications 리스트 영역을 다음으로 감싼다:

```django
{% extends "base.html" %}
{% block content %}
<main class="max-w-6xl mx-auto px-4 py-6">
  {# 기존 헤더 블록 보존 (제목, 메타, 더보기 드롭다운 등) #}
  {% include "projects/partials/project_header.html" with project=project %}

  {# 영역 A — 프로젝트 레벨 작업 #}
  {% include "projects/partials/project_area_a.html" %}

  {# 영역 B — 후보자 카드 리스트 #}
  <section id="project-area-b">
    <h2 class="text-lg font-semibold mb-4">후보자 목록</h2>
    {% include "projects/partials/project_applications_list.html" with applications=applications %}
  </section>
</main>
{% endblock %}
```

> **주의**: 현재 project_detail.html이 이미 다른 구조일 수 있으니 실제 파일을 Read 로 확인 후 헤더 블록만 추출해 `project_header.html` partial로 분리하고 본체만 위처럼 교체. partial 이름은 임의 — 기존과 겹치지 않는 선에서.

- [ ] **Run layout test: PASS**

```bash
uv run pytest tests/test_project_detail_layout.py -v
```

### Step 4.5: 수동 스모크 테스트

- [ ] **Start dev server:**

```bash
./dev.sh
```

- [ ] **Visit `/projects/<any-open-pk>/` — 영역 A 카드 2개 + 영역 B 후보자 리스트가 보여야 함.**

- [ ] **URL 보고**: 수정 후 경로 `/projects/<pk>/` 를 사용자에게 알려 브라우저 확인 요청.

### Step 4.6: 커밋

- [ ] **Commit:**

```bash
git add projects/templates/projects/project_detail.html projects/templates/projects/partials/project_area_a.html projects/templates/projects/partials/area_a_searching.html projects/templates/projects/partials/area_a_submission_batch.html tests/test_project_detail_layout.py
git commit -m "refactor(projects): restructure project_detail into area A (project-level) + area B (candidate cards)"
```

---

## Task 5: 영역 A — 서칭 도구 DB 검색 연결

**Files:**
- Create: `projects/services/searching.py`
- Modify: `projects/templates/projects/partials/area_a_searching.html`
- Modify: `candidates/views.py` (프로젝트 컨텍스트 모드 파라미터 받기)
- Modify: `candidates/templates/candidates/partials/candidate_card.html` (프로젝트에 추가 버튼)
- Modify: `projects/urls.py` (add_candidate_to_project 이미 존재 — project_add_candidate 재사용 검토)
- Test: `tests/test_searching_service.py`

### Step 5.1: 서칭 서비스 테스트

- [ ] **Create `tests/test_searching_service.py`:**

```python
import pytest

from projects.models import Application
from projects.services.searching import add_candidates_to_project


@pytest.mark.django_db
def test_add_candidates_creates_applications(project_factory, candidate_factory, user_factory):
    project = project_factory()
    c1 = candidate_factory()
    c2 = candidate_factory()
    creator = user_factory()
    
    apps = add_candidates_to_project(project, [c1.id, c2.id], created_by=creator)
    
    assert len(apps) == 2
    assert Application.objects.filter(project=project).count() == 2


@pytest.mark.django_db
def test_add_candidates_dedupes_existing(project_factory, candidate_factory, application_factory):
    project = project_factory()
    c1 = candidate_factory()
    application_factory(project=project, candidate=c1)  # 이미 존재
    
    apps = add_candidates_to_project(project, [c1.id])
    assert apps == []  # 중복이라 새로 만들지 않음
    assert Application.objects.filter(project=project, candidate=c1).count() == 1
```

- [ ] **Run: FAIL — service module missing**

### Step 5.2: 서칭 서비스 구현

- [ ] **Create `projects/services/searching.py`:**

```python
"""프로젝트 서칭 도구 — DB에서 후보자를 선택해 Application으로 등록."""
from __future__ import annotations

from candidates.models import Candidate
from projects.models import Application


def add_candidates_to_project(project, candidate_ids: list, created_by=None) -> list[Application]:
    """주어진 후보자 ID 목록을 프로젝트에 Application으로 추가. 이미 존재하면 건너뜀.
    
    Returns: 새로 생성된 Application 인스턴스 리스트.
    """
    existing_ids = set(
        Application.objects.filter(
            project=project, candidate_id__in=candidate_ids
        ).values_list("candidate_id", flat=True)
    )
    new_ids = [cid for cid in candidate_ids if cid not in existing_ids]
    if not new_ids:
        return []
    
    candidates = Candidate.objects.filter(id__in=new_ids)
    created = [
        Application.objects.create(
            project=project,
            candidate=c,
            created_by=created_by,
        )
        for c in candidates
    ]
    return created
```

- [ ] **Run tests: PASS 2/2**

### Step 5.3: 서칭 영역 UI

- [ ] **Replace `projects/templates/projects/partials/area_a_searching.html`:**

```django
<div class="flex flex-wrap gap-3">
  <a href="{% url 'candidates:candidate_list' %}?project={{ project.pk }}"
     class="btn-primary">
    DB에서 찾기
  </a>
  
  {# 외부 채널 — Task 6 #}
  {% include "projects/partials/area_a_channel_placeholder.html" with channel="잡코리아" %}
  {% include "projects/partials/area_a_channel_placeholder.html" with channel="사람인" %}
  {% include "projects/partials/area_a_channel_placeholder.html" with channel="LinkedIn" %}
  {% include "projects/partials/area_a_channel_placeholder.html" with channel="이메일" %}
</div>

<p class="text-sm text-muted mt-3">
  JD 기반으로 후보자를 발굴하세요. 드롭·추가와 관계없이 프로젝트 종료까지 언제든 다시 서칭할 수 있습니다.
</p>
```

### Step 5.4: candidates 페이지 프로젝트 컨텍스트 모드

- [ ] **Read `candidates/views.py` → candidate_list view to understand current structure.**

- [ ] **Modify `candidates/views.py` candidate_list:** — `request.GET.get("project")` 가 있으면 해당 프로젝트를 context 에 전달하고, 템플릿에서 "프로젝트에 추가" 버튼이 뜨도록.

(정확한 편집 위치는 현재 코드에 따라 결정. 예시 구조:)

```python
def candidate_list(request):
    project_id = request.GET.get("project")
    project = None
    if project_id:
        from projects.models import Project
        project = Project.objects.filter(
            pk=project_id, organization=request.user.org
        ).first()
    # ... existing filtering logic ...
    context["target_project"] = project
    return render(request, "candidates/candidate_list.html", context)
```

- [ ] **Modify `candidates/templates/candidates/partials/candidate_card.html`:** — 카드 하단에 프로젝트 모드일 때 "프로젝트에 추가" 버튼 추가.

```django
{% if target_project %}
<button
  hx-post="{% url 'projects:project_add_candidate' target_project.pk %}"
  hx-vals='{"candidate_id": "{{ candidate.pk }}"}'
  hx-swap="outerHTML"
  hx-target="this"
  class="btn-secondary btn-sm">
  프로젝트에 추가
</button>
{% endif %}
```

### Step 5.5: project_add_candidate 뷰가 이 호출을 받도록 점검

- [ ] **Read `projects/views.py` project_add_candidate.** 현재 AJAX body로 candidate_id 받는 패턴이면 그대로. 다르면 최소 수정.

### Step 5.6: 뷰 통합 테스트

- [ ] **Append to `tests/test_searching_service.py`:**

```python
@pytest.mark.django_db
def test_project_add_candidate_view(client, consultant_user, project_factory, candidate_factory):
    project = project_factory(organization=consultant_user.org)
    candidate = candidate_factory()
    client.force_login(consultant_user)
    
    resp = client.post(
        f"/projects/{project.pk}/add_candidate/",
        {"candidate_id": str(candidate.pk)},
    )
    assert resp.status_code in (200, 302)
    assert Application.objects.filter(project=project, candidate=candidate).exists()
```

- [ ] **Run: PASS**

### Step 5.7: 스모크 테스트

- [ ] 서버 재시작 후 `/projects/<pk>/` → "DB에서 찾기" 클릭 → candidates 페이지로 이동 + "프로젝트에 추가" 버튼 확인 → 한 명 추가 → 프로젝트 상세로 돌아가서 카드 추가 확인. URL 보고.

### Step 5.8: 커밋

- [ ] **Commit:**

```bash
git add projects/services/searching.py projects/templates/projects/partials/area_a_searching.html candidates/views.py candidates/templates/candidates/partials/candidate_card.html tests/test_searching_service.py
git commit -m "feat(projects): DB searching → candidate add flow in project detail area A"
```

---

## Task 6: 영역 A — 외부 채널 UI 플레이스홀더

**Files:**
- Create: `projects/templates/projects/partials/area_a_channel_placeholder.html`

### Step 6.1: 플레이스홀더 컴포넌트

- [ ] **Create `projects/templates/projects/partials/area_a_channel_placeholder.html`:**

```django
<button
  type="button"
  class="btn-secondary opacity-60 cursor-not-allowed"
  title="준비 중 — 별도 설계 문서 참조"
  disabled>
  {{ channel }} <span class="text-xs text-muted">(준비중)</span>
</button>
```

### Step 6.2: 커밋

- [ ] **Commit:**

```bash
git add projects/templates/projects/partials/area_a_channel_placeholder.html
git commit -m "feat(projects): add external channel placeholders (Jobkorea/Saramin/LinkedIn/Email)"
```

---

## Task 7: 영역 A — 이력서 배치 제출 관리

**Files:**
- Create: `projects/templates/projects/partials/area_a_submission_batch.html`
- Modify: `projects/views.py` (submission_batch_create 뷰 신규)
- Modify: `projects/urls.py`
- Test: `tests/test_submission_batch.py` (뷰 테스트 추가)

### Step 7.1: 뷰 테스트

- [ ] **Append to `tests/test_submission_batch.py`:**

```python
from django.urls import reverse
from projects.models import ActionItem, Submission


@pytest.mark.django_db
def test_submission_batch_create(client, consultant_user, project_factory, application_factory):
    project = project_factory(organization=consultant_user.org)
    a1 = application_factory(project=project)
    a2 = application_factory(project=project)
    client.force_login(consultant_user)
    
    resp = client.post(
        reverse("projects:submission_batch_create", args=[project.pk]),
        {"application_ids": [str(a1.pk), str(a2.pk)]},
    )
    assert resp.status_code in (200, 302)
    subs = Submission.objects.filter(action_item__application__project=project)
    assert subs.count() == 2
    batch_ids = {s.batch_id for s in subs}
    assert len(batch_ids) == 1  # 같은 batch_id 공유
    assert list(batch_ids)[0] is not None
```

- [ ] **Run: FAIL (view missing)**

### Step 7.2: 뷰 구현

- [ ] **Append to `projects/views.py`:**

```python
@login_required
@require_http_methods(["POST"])
def submission_batch_create(request, pk):
    """선택한 여러 Application 을 한 batch_id 로 묶어 Submission 생성."""
    import uuid
    from projects.models import ActionItem, ActionItemStatus, ActionType, Submission
    
    project = get_object_or_404(
        Project, pk=pk, organization=request.user.org
    )
    app_ids = request.POST.getlist("application_ids")
    if not app_ids:
        return HttpResponseBadRequest("application_ids required")
    
    applications = Application.objects.filter(
        pk__in=app_ids, project=project, dropped_at__isnull=True, hired_at__isnull=True,
    )
    submit_type = ActionType.objects.get(code="submit_to_client")
    batch_id = uuid.uuid4()
    
    for app in applications:
        ai = ActionItem.objects.create(
            application=app,
            action_type=submit_type,
            title="이력서 고객사 제출",
            status=ActionItemStatus.DONE,
            completed_at=timezone.now(),
            created_by=request.user,
        )
        Submission.objects.create(
            action_item=ai,
            consultant=request.user,
            batch_id=batch_id,
            submitted_at=timezone.now(),
        )
    
    return redirect("projects:project_detail", pk=project.pk)
```

- [ ] **Add URL to `projects/urls.py`:**

```python
    path(
        "<uuid:pk>/submissions/batch/",
        views.submission_batch_create,
        name="submission_batch_create",
    ),
```

- [ ] **Run tests: PASS**

### Step 7.3: UI 파티얼

- [ ] **Replace `projects/templates/projects/partials/area_a_submission_batch.html`:**

```django
{# 이력서 준비까지 통과했지만 아직 고객사 제출되지 않은 Application 목록 #}
{% if pending_for_submission %}
<form method="post" action="{% url 'projects:submission_batch_create' project.pk %}">
  {% csrf_token %}
  <ul class="space-y-2 mb-4">
    {% for app in pending_for_submission %}
      <li class="flex items-center gap-3">
        <input type="checkbox" name="application_ids" value="{{ app.pk }}"
               class="form-checkbox" id="batch-{{ app.pk }}">
        <label for="batch-{{ app.pk }}" class="flex-1">
          {{ app.candidate.name }} — {{ app.current_stage_label }}
        </label>
      </li>
    {% endfor %}
  </ul>
  <button type="submit" class="btn-primary">선택한 후보 묶어 제출</button>
</form>
{% else %}
  <div class="text-sm text-muted">제출 대기 중인 후보자가 없습니다.</div>
{% endif %}
```

### Step 7.4: project_detail 뷰에서 pending_for_submission context 공급

- [ ] **Edit `projects/views.py` project_detail view** — context 에 다음 추가:

```python
    pending_for_submission = [
        app for app in applications
        if app.current_stage == "client_submit"
    ]
    context["pending_for_submission"] = pending_for_submission
```

(`applications` 는 이미 prefetch 되어 current_stage 계산 가능한 상태여야 함. 필요 시 select_related/prefetch_related 추가.)

### Step 7.5: 커밋

- [ ] **Commit:**

```bash
git add projects/templates/projects/partials/area_a_submission_batch.html projects/views.py projects/urls.py tests/test_submission_batch.py
git commit -m "feat(projects): batch submission UI + view — creates Submissions sharing batch_id"
```

---

## Task 8: 후보자 카드 진행바 7단계로 변경

**Files:**
- Modify: `projects/templates/projects/partials/application_card.html`

### Step 8.1: 현재 카드 구조 파악

- [ ] **Read `projects/templates/projects/partials/application_card.html`** — 진행바가 STAGES_ORDER 를 돌고 있는지 확인.

### Step 8.2: CARD_STAGES_ORDER 사용하도록 수정

- [ ] **진행바 반복 부분에서 `STAGES_ORDER` → `CARD_STAGES_ORDER` 로 교체.** 템플릿에서 상수를 쓰려면 뷰에서 context 주입 필요 — 또는 커스텀 템플릿 태그. 가장 간단한 방법:

**projects/templatetags/projects_tags.py 에 simple_tag 추가 (없으면 신규 생성):**

```python
from django import template
from projects.models import CARD_STAGES_ORDER

register = template.Library()


@register.simple_tag
def card_stages():
    return CARD_STAGES_ORDER
```

- [ ] **Edit application_card.html:**

```django
{% load projects_tags %}
{% card_stages as stages %}
<div class="stage-progress">
  {% for stage_id, stage_label in stages %}
    {% if stage_id in application.stages_passed %}
      <div class="stage-passed">{{ stage_label }}</div>
    {% elif stage_id == application.current_stage %}
      <div class="stage-current">{{ stage_label }}</div>
    {% else %}
      <div class="stage-future">{{ stage_label }}</div>
    {% endif %}
  {% endfor %}
</div>
```

(정확한 CSS 클래스는 기존 파일 스타일에 맞춰 유지.)

### Step 8.3: 스모크 테스트

- [ ] `/projects/<pk>/` 방문 → 카드 진행바가 7단계 (접촉부터 입사까지) 로 표시되는지 확인. URL 보고.

### Step 8.4: 커밋

- [ ] **Commit:**

```bash
git add projects/templates/projects/partials/application_card.html projects/templatetags/projects_tags.py
git commit -m "refactor(projects): card progress bar uses 7-stage CARD_STAGES_ORDER (sourcing removed)"
```

---

## Task 9: 단계 partial 라우팅 — application_card 가 현재 단계 partial 을 include

**Files:**
- Modify: `projects/templates/projects/partials/application_card.html`

### Step 9.1: 스위치 include 구현

- [ ] **Edit application_card.html** — 진행바 아래 "현재 단계 작업 영역" 부분을 다음으로:

```django
<div class="stage-workspace mt-4">
  {% if application.current_stage == "contact" %}
    {% include "projects/partials/stage_contact.html" with application=application %}
  {% elif application.current_stage == "resume" %}
    {% include "projects/partials/stage_resume.html" with application=application %}
  {% elif application.current_stage == "pre_meeting" %}
    {% include "projects/partials/stage_pre_meeting.html" with application=application %}
  {% elif application.current_stage == "prep_submission" %}
    {% include "projects/partials/stage_prep_submission.html" with application=application %}
  {% elif application.current_stage == "client_submit" %}
    {% include "projects/partials/stage_client_submit.html" with application=application %}
  {% elif application.current_stage == "interview" %}
    {% include "projects/partials/stage_interview.html" with application=application %}
  {% elif application.current_stage == "hired" %}
    {% include "projects/partials/stage_hired.html" with application=application %}
  {% endif %}
</div>
```

### Step 9.2: 각 partial 빈 파일 생성 (Task 10~16 에서 채움)

- [ ] **Create 7 empty partials with placeholder content:**

```bash
for stage in contact resume pre_meeting prep_submission client_submit interview hired; do
  echo "<div class=\"text-sm text-muted\">($stage — 추후 구현)</div>" > \
    projects/templates/projects/partials/stage_${stage}.html
done
```

**주의**: `stage_resume.html` 은 기존 `stage_resume_methods.html` 의 내용을 복사/이동하는 게 낫다 (Phase B 기존 구현 보존).

- [ ] **Move content:**

```bash
cp projects/templates/projects/partials/stage_resume_methods.html \
   projects/templates/projects/partials/stage_resume.html
```

- [ ] Keep `stage_resume_methods.html` 이 `application_card.html` 외 다른 파일에서 참조되는지 grep 후, 없으면 다음 Task 에서 제거.

### Step 9.3: 커밋

- [ ] **Commit:**

```bash
git add projects/templates/projects/partials/application_card.html projects/templates/projects/partials/stage_*.html
git commit -m "feat(projects): per-stage partial dispatch from application card"
```

---

## Task 10: stage_contact.html — 접촉 단계 (완료 체크 + 응답 기록)

**Files:**
- Modify: `projects/templates/projects/partials/stage_contact.html`
- Modify: `projects/views.py` (stage_contact_complete 뷰)
- Modify: `projects/urls.py`
- Modify: `projects/forms.py` (ContactCompleteForm)

### Step 10.1: 뷰/폼 테스트

- [ ] **Create `tests/test_stage_contact.py`:**

```python
import pytest
from django.urls import reverse

from projects.models import ActionItem, ActionItemStatus


@pytest.mark.django_db
def test_contact_complete_creates_reach_out_done(
    client, consultant_user, application_factory, action_type_factory
):
    action_type_factory(code="reach_out")
    app = application_factory()
    client.force_login(consultant_user)
    
    resp = client.post(
        reverse("projects:stage_contact_complete", args=[app.pk]),
        {"response": "positive", "note": "수락함"},
    )
    assert resp.status_code in (200, 204, 302)
    ai = ActionItem.objects.get(application=app, action_type__code="reach_out")
    assert ai.status == ActionItemStatus.DONE
    assert "수락함" in ai.note
```

- [ ] **Run: FAIL — URL 없음.**

### Step 10.2: 폼 + 뷰

- [ ] **Append to `projects/forms.py`:**

```python
class ContactCompleteForm(forms.Form):
    RESPONSE_CHOICES = [
        ("positive", "긍정 (진행 의사 있음)"),
        ("negative", "부정 (거절)"),
        ("pending", "보류 (추후 결정)"),
    ]
    response = forms.ChoiceField(choices=RESPONSE_CHOICES, widget=forms.RadioSelect)
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
```

- [ ] **Append to `projects/views.py`:**

```python
@login_required
@require_http_methods(["POST"])
def stage_contact_complete(request, pk):
    from projects.forms import ContactCompleteForm
    from projects.models import ActionItem, ActionItemStatus, ActionType
    
    app = get_object_or_404(Application, pk=pk)
    form = ContactCompleteForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_text())
    
    response = form.cleaned_data["response"]
    note = form.cleaned_data["note"]
    
    if response == "negative":
        app.dropped_at = timezone.now()
        app.drop_reason = "candidate_declined"
        app.drop_note = note
        app.save(update_fields=["dropped_at", "drop_reason", "drop_note"])
    else:
        reach_out = ActionType.objects.get(code="reach_out")
        ActionItem.objects.create(
            application=app,
            action_type=reach_out,
            title="연락 — 의사 확인",
            status=ActionItemStatus.DONE,
            completed_at=timezone.now(),
            note=f"응답: {response}. {note}".strip(),
            created_by=request.user,
        )
    
    return redirect("projects:project_detail", pk=app.project.pk)
```

- [ ] **Add URL:**

```python
    path(
        "applications/<uuid:pk>/stage/contact/complete/",
        views.stage_contact_complete,
        name="stage_contact_complete",
    ),
```

- [ ] **Run tests: PASS**

### Step 10.3: Partial UI

- [ ] **Replace `projects/templates/projects/partials/stage_contact.html`:**

```django
<form method="post" action="{% url 'projects:stage_contact_complete' application.pk %}"
      class="space-y-3">
  {% csrf_token %}
  <p class="font-medium">후보자에게 JD 공유 + 진행 의사 확인</p>
  <div class="space-y-2">
    <label class="flex items-center gap-2">
      <input type="radio" name="response" value="positive" required>
      긍정 — 진행 의사 있음
    </label>
    <label class="flex items-center gap-2">
      <input type="radio" name="response" value="negative">
      부정 — 거절 (이 후보자 drop)
    </label>
    <label class="flex items-center gap-2">
      <input type="radio" name="response" value="pending">
      보류 — 추후 결정
    </label>
  </div>
  <textarea name="note" placeholder="응답 요지 (선택)" class="form-textarea w-full"
            rows="2"></textarea>
  <button type="submit" class="btn-primary">접촉 완료</button>
</form>
```

### Step 10.4: 스모크 + 커밋

- [ ] 접촉 단계 카드 확인. URL 보고. Commit:

```bash
git add projects/templates/projects/partials/stage_contact.html projects/views.py projects/urls.py projects/forms.py tests/test_stage_contact.py
git commit -m "feat(projects): contact stage partial — completion check + response record"
```

---

## Task 11: stage_resume.html — 이력서 준비 (기존 Phase B 재사용)

**Files:**
- Modify: `projects/templates/projects/partials/stage_resume.html` (이미 Task 9에서 복사됨)
- Delete: `projects/templates/projects/partials/stage_resume_methods.html` (불필요하면)

### Step 11.1: 참조 검색

- [ ] **Search for remaining references:**

```bash
```

사용하는 `stage_resume_methods.html` 검색 — Grep tool 사용.

- [ ] **If no references remain, delete:**

```bash
rm projects/templates/projects/partials/stage_resume_methods.html
```

- [ ] **If references remain, update them to `stage_resume.html`.**

### Step 11.2: stage_resume.html 내부 문구 라벨 업데이트

- [ ] 파일 내 "이력서 수집" 문자열이 있으면 "이력서 준비"로 변경.

### Step 11.3: 커밋

- [ ] **Commit:**

```bash
git add -A projects/templates/projects/partials/stage_resume*.html
git commit -m "refactor(projects): rename stage_resume_methods → stage_resume, update label to 이력서 준비"
```

---

## Task 12: stage_pre_meeting.html — 사전 미팅 (일정/진행/기록 3단계)

**Files:**
- Modify: `projects/templates/projects/partials/stage_pre_meeting.html`
- Modify: `projects/views.py` (3 views: schedule, hold, record)
- Modify: `projects/urls.py`
- Modify: `projects/forms.py`

### Step 12.1: 테스트

- [ ] **Create `tests/test_stage_pre_meeting.py`:**

```python
import pytest
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from projects.models import ActionItem


@pytest.mark.django_db
def test_pre_meeting_schedule(client, consultant_user, application_factory, action_type_factory):
    action_type_factory(code="schedule_pre_meet")
    app = application_factory()
    client.force_login(consultant_user)
    future = (timezone.now() + timedelta(days=3)).isoformat()
    
    resp = client.post(
        reverse("projects:stage_pre_meeting_schedule", args=[app.pk]),
        {"scheduled_at": future, "channel": "video"},
    )
    assert resp.status_code in (200, 302)
    ai = ActionItem.objects.get(application=app, action_type__code="schedule_pre_meet")
    assert ai.scheduled_at is not None


@pytest.mark.django_db
def test_pre_meeting_record_creates_meeting_record(
    client, consultant_user, application_factory, action_type_factory
):
    action_type_factory(code="pre_meeting")
    app = application_factory()
    client.force_login(consultant_user)
    
    resp = client.post(
        reverse("projects:stage_pre_meeting_record", args=[app.pk]),
        {"summary": "좋은 인상, 연봉 협의 필요"},
    )
    assert resp.status_code in (200, 302)
    ai = ActionItem.objects.get(application=app, action_type__code="pre_meeting")
    assert ai.status == "done"
    assert "좋은 인상" in ai.result
```

- [ ] **Run: FAIL**

### Step 12.2: 폼 추가

- [ ] **Append to `projects/forms.py`:**

```python
class PreMeetingScheduleForm(forms.Form):
    scheduled_at = forms.DateTimeField()
    channel = forms.ChoiceField(
        choices=[("in_person", "대면"), ("video", "화상"), ("phone", "전화")]
    )
    location = forms.CharField(required=False, max_length=300)


class PreMeetingRecordForm(forms.Form):
    summary = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))
    audio = forms.FileField(required=False, help_text="녹음 파일 (선택) — 추후 STT 지원 예정")
```

### Step 12.3: 뷰 3개

- [ ] **Append to `projects/views.py`:**

```python
@login_required
@require_http_methods(["POST"])
def stage_pre_meeting_schedule(request, pk):
    from projects.forms import PreMeetingScheduleForm
    from projects.models import ActionItem, ActionItemStatus, ActionType
    
    app = get_object_or_404(Application, pk=pk)
    form = PreMeetingScheduleForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_text())
    
    at = ActionType.objects.get(code="schedule_pre_meet")
    ActionItem.objects.create(
        application=app,
        action_type=at,
        title=f"사전 미팅 일정 ({form.cleaned_data['channel']})",
        status=ActionItemStatus.DONE,
        scheduled_at=form.cleaned_data["scheduled_at"],
        channel=form.cleaned_data["channel"],
        note=form.cleaned_data.get("location", ""),
        completed_at=timezone.now(),
        created_by=request.user,
    )
    return redirect("projects:project_detail", pk=app.project.pk)


@login_required
@require_http_methods(["POST"])
def stage_pre_meeting_record(request, pk):
    from projects.forms import PreMeetingRecordForm
    from projects.models import ActionItem, ActionItemStatus, ActionType, MeetingRecord
    
    app = get_object_or_404(Application, pk=pk)
    form = PreMeetingRecordForm(request.POST, request.FILES)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_text())
    
    at = ActionType.objects.get(code="pre_meeting")
    ai = ActionItem.objects.create(
        application=app,
        action_type=at,
        title="사전 미팅 진행",
        status=ActionItemStatus.DONE,
        result=form.cleaned_data["summary"],
        completed_at=timezone.now(),
        created_by=request.user,
    )
    audio = form.cleaned_data.get("audio")
    if audio:
        MeetingRecord.objects.create(
            action_item=ai,
            audio_file=audio,
            status=MeetingRecord.Status.UPLOADED,
            created_by=request.user,
        )
    return redirect("projects:project_detail", pk=app.project.pk)
```

- [ ] **Add URLs:**

```python
    path(
        "applications/<uuid:pk>/stage/pre_meeting/schedule/",
        views.stage_pre_meeting_schedule,
        name="stage_pre_meeting_schedule",
    ),
    path(
        "applications/<uuid:pk>/stage/pre_meeting/record/",
        views.stage_pre_meeting_record,
        name="stage_pre_meeting_record",
    ),
```

- [ ] **Run tests: PASS**

### Step 12.4: Partial UI (3단계 토글)

- [ ] **Replace `projects/templates/projects/partials/stage_pre_meeting.html`:**

```django
{% with scheduled=application.has_pre_meeting_scheduled %}
{% if not scheduled %}
  {# 단계 1: 일정 조율 #}
  <form method="post" action="{% url 'projects:stage_pre_meeting_schedule' application.pk %}"
        class="space-y-3">
    {% csrf_token %}
    <p class="font-medium">① 사전 미팅 일정 잡기</p>
    <input type="datetime-local" name="scheduled_at" required class="form-input">
    <select name="channel" class="form-select">
      <option value="in_person">대면</option>
      <option value="video">화상</option>
      <option value="phone">전화</option>
    </select>
    <input type="text" name="location" placeholder="장소/URL (선택)" class="form-input">
    <button type="submit" class="btn-primary">일정 확정</button>
  </form>
{% else %}
  {# 단계 3: 결과 기록 (단계 2 '미팅 진행'은 offline; 결과 입력으로 완료 처리) #}
  <form method="post" action="{% url 'projects:stage_pre_meeting_record' application.pk %}"
        enctype="multipart/form-data" class="space-y-3">
    {% csrf_token %}
    <p class="font-medium">② 미팅 결과 기록</p>
    <p class="text-sm text-muted">일정: {{ application.pre_meeting_scheduled_at }}</p>
    <textarea name="summary" rows="4" placeholder="미팅 요지·다음 액션 요약" 
              class="form-textarea w-full" required></textarea>
    <label class="block text-sm">
      녹음 파일 첨부 (선택)
      <input type="file" name="audio" accept="audio/*" class="form-input">
    </label>
    <button type="submit" class="btn-primary">미팅 완료</button>
  </form>
{% endif %}
{% endwith %}
```

### Step 12.5: Application property 추가 (가독성 보조)

- [ ] **Append to Application class in `projects/models.py`:**

```python
    @property
    def has_pre_meeting_scheduled(self) -> bool:
        return self.action_items.filter(
            action_type__code="schedule_pre_meet",
            status=ActionItemStatus.DONE,
        ).exists()

    @property
    def pre_meeting_scheduled_at(self):
        ai = self.action_items.filter(
            action_type__code="schedule_pre_meet",
            status=ActionItemStatus.DONE,
        ).order_by("-completed_at").first()
        return ai.scheduled_at if ai else None
```

### Step 12.6: 커밋

- [ ] **Commit:**

```bash
git add projects/templates/projects/partials/stage_pre_meeting.html projects/views.py projects/urls.py projects/forms.py projects/models.py tests/test_stage_pre_meeting.py
git commit -m "feat(projects): pre_meeting stage with scheduling + result recording (audio optional)"
```

---

## Task 13: stage_prep_submission.html — 이력서 작성(제출용)

**Files:**
- Modify: `projects/templates/projects/partials/stage_prep_submission.html`
- Modify: `projects/views.py` (stage_prep_submission_confirm)
- Modify: `projects/urls.py`

### Step 13.1: 테스트

- [ ] **Create `tests/test_stage_prep_submission.py`:**

```python
import pytest
from django.urls import reverse
from projects.models import ActionItem


@pytest.mark.django_db
def test_prep_submission_confirm_creates_submit_to_pm_done(
    client, consultant_user, application_factory, action_type_factory
):
    action_type_factory(code="submit_to_pm")
    app = application_factory()
    client.force_login(consultant_user)
    
    resp = client.post(
        reverse("projects:stage_prep_submission_confirm", args=[app.pk]),
    )
    assert resp.status_code in (200, 302)
    assert ActionItem.objects.filter(
        application=app, action_type__code="submit_to_pm", status="done"
    ).exists()
```

- [ ] **Run: FAIL**

### Step 13.2: 뷰

- [ ] **Append to `projects/views.py`:**

```python
@login_required
@require_http_methods(["POST"])
def stage_prep_submission_confirm(request, pk):
    from projects.models import ActionItem, ActionItemStatus, ActionType
    
    app = get_object_or_404(Application, pk=pk)
    at = ActionType.objects.get(code="submit_to_pm")
    ActionItem.objects.create(
        application=app,
        action_type=at,
        title="제출용 이력서 컨펌",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
        note="컨설턴트 컨펌 완료 (자동 생성 템플릿 미구현 — 수동 컨펌)",
        created_by=request.user,
    )
    return redirect("projects:project_detail", pk=app.project.pk)
```

- [ ] **Add URL:**

```python
    path(
        "applications/<uuid:pk>/stage/prep_submission/confirm/",
        views.stage_prep_submission_confirm,
        name="stage_prep_submission_confirm",
    ),
```

### Step 13.3: Partial UI

- [ ] **Replace `projects/templates/projects/partials/stage_prep_submission.html`:**

```django
<div class="space-y-3">
  <p class="font-medium">고객사 제출용 이력서 문서</p>
  <div class="bg-bg-muted p-4 rounded text-sm">
    <p class="mb-2">📄 자동 생성 기능은 별도 설계 중입니다.</p>
    <p class="text-muted">
      현재는 컨설턴트가 문서를 외부에서 준비한 뒤 아래 버튼으로 컨펌하세요. 
      이 단계는 <strong>건너뛸 수 없습니다</strong>.
    </p>
  </div>
  <form method="post" 
        action="{% url 'projects:stage_prep_submission_confirm' application.pk %}">
    {% csrf_token %}
    <button type="submit" class="btn-primary">✓ 문서 컨펌 완료</button>
  </form>
</div>
```

### Step 13.4: 커밋

- [ ] **Commit:**

```bash
git add projects/templates/projects/partials/stage_prep_submission.html projects/views.py projects/urls.py tests/test_stage_prep_submission.py
git commit -m "feat(projects): prep_submission stage with consultant confirm (auto-gen deferred)"
```

---

## Task 14: stage_client_submit.html — 이력서 제출 (개별)

**Files:**
- Modify: `projects/templates/projects/partials/stage_client_submit.html`
- Modify: `projects/views.py` (stage_client_submit_single)
- Modify: `projects/urls.py`

### Step 14.1: 테스트

- [ ] **Create `tests/test_stage_client_submit.py`:**

```python
import pytest
from django.urls import reverse
from projects.models import Submission


@pytest.mark.django_db
def test_client_submit_single_creates_submission_without_batch(
    client, consultant_user, application_factory, action_type_factory
):
    action_type_factory(code="submit_to_client")
    app = application_factory()
    client.force_login(consultant_user)
    
    resp = client.post(
        reverse("projects:stage_client_submit_single", args=[app.pk]),
    )
    assert resp.status_code in (200, 302)
    sub = Submission.objects.get(action_item__application=app)
    assert sub.batch_id is None
```

### Step 14.2: 뷰

- [ ] **Append to `projects/views.py`:**

```python
@login_required
@require_http_methods(["POST"])
def stage_client_submit_single(request, pk):
    from projects.models import ActionItem, ActionItemStatus, ActionType, Submission
    
    app = get_object_or_404(Application, pk=pk)
    at = ActionType.objects.get(code="submit_to_client")
    ai = ActionItem.objects.create(
        application=app,
        action_type=at,
        title="이력서 고객사 제출 (개별)",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
        created_by=request.user,
    )
    Submission.objects.create(
        action_item=ai,
        consultant=request.user,
        batch_id=None,
        submitted_at=timezone.now(),
    )
    return redirect("projects:project_detail", pk=app.project.pk)
```

- [ ] **Add URL:**

```python
    path(
        "applications/<uuid:pk>/stage/client_submit/single/",
        views.stage_client_submit_single,
        name="stage_client_submit_single",
    ),
```

### Step 14.3: Partial UI

- [ ] **Replace `projects/templates/projects/partials/stage_client_submit.html`:**

```django
<div class="space-y-3">
  <p class="font-medium">이력서 고객사 제출</p>
  <p class="text-sm text-muted">
    배치 제출은 위쪽 <strong>영역 A</strong> 에서 여러 명 묶어서 처리할 수 있습니다.
    이 후보자만 따로 제출하려면 아래 버튼을 누르세요. 이 단계는 건너뛸 수 없습니다.
  </p>
  <form method="post" 
        action="{% url 'projects:stage_client_submit_single' application.pk %}">
    {% csrf_token %}
    <button type="submit" class="btn-primary">이 후보만 단독 제출</button>
  </form>
</div>
```

### Step 14.4: 커밋

- [ ] **Commit:**

```bash
git add projects/templates/projects/partials/stage_client_submit.html projects/views.py projects/urls.py tests/test_stage_client_submit.py
git commit -m "feat(projects): client_submit stage — single-candidate submission path"
```

---

## Task 15: stage_interview.html — 면접 + After Interview Review

**Files:**
- Modify: `projects/templates/projects/partials/stage_interview.html`
- Modify: `projects/views.py` (stage_interview_review + stage_interview_complete)
- Modify: `projects/urls.py`

### Step 15.1: 테스트

- [ ] **Create `tests/test_stage_interview.py`:**

```python
import pytest
from django.urls import reverse
from projects.models import ActionItem


@pytest.mark.django_db
def test_interview_complete_without_review(
    client, consultant_user, application_factory, action_type_factory
):
    """Review 없이도 컨설턴트 버튼으로 완료 가능."""
    action_type_factory(code="interview_round")
    app = application_factory()
    client.force_login(consultant_user)
    
    resp = client.post(
        reverse("projects:stage_interview_complete", args=[app.pk]),
        {"result": "passed"},
    )
    assert resp.status_code in (200, 302)
    assert ActionItem.objects.filter(
        application=app, action_type__code="interview_round", status="done"
    ).exists()


@pytest.mark.django_db
def test_interview_review_with_text(
    client, consultant_user, application_factory, action_type_factory
):
    action_type_factory(code="interview_round")
    app = application_factory()
    client.force_login(consultant_user)
    
    resp = client.post(
        reverse("projects:stage_interview_complete", args=[app.pk]),
        {"result": "passed", "review": "질문 대응 무난, 연봉 협의 필요"},
    )
    assert resp.status_code in (200, 302)
    ai = ActionItem.objects.get(application=app, action_type__code="interview_round")
    assert "연봉 협의" in ai.result
```

### Step 15.2: 뷰

- [ ] **Append to `projects/views.py`:**

```python
@login_required
@require_http_methods(["POST"])
def stage_interview_complete(request, pk):
    from projects.models import ActionItem, ActionItemStatus, ActionType
    
    app = get_object_or_404(Application, pk=pk)
    result = request.POST.get("result", "passed")
    review = request.POST.get("review", "")
    
    if result == "failed":
        app.dropped_at = timezone.now()
        app.drop_reason = "client_rejected"
        app.drop_note = review
        app.save(update_fields=["dropped_at", "drop_reason", "drop_note"])
        return redirect("projects:project_detail", pk=app.project.pk)
    
    at = ActionType.objects.get(code="interview_round")
    ActionItem.objects.create(
        application=app,
        action_type=at,
        title="면접 결과 수령",
        status=ActionItemStatus.DONE,
        completed_at=timezone.now(),
        result=review,
        note=f"결과: {result}",
        created_by=request.user,
    )
    return redirect("projects:project_detail", pk=app.project.pk)
```

- [ ] **Add URL:**

```python
    path(
        "applications/<uuid:pk>/stage/interview/complete/",
        views.stage_interview_complete,
        name="stage_interview_complete",
    ),
```

### Step 15.3: Partial UI

- [ ] **Replace `projects/templates/projects/partials/stage_interview.html`:**

```django
<form method="post" action="{% url 'projects:stage_interview_complete' application.pk %}"
      class="space-y-3">
  {% csrf_token %}
  <p class="font-medium">면접 결과 입력</p>
  <select name="result" class="form-select" required>
    <option value="">선택…</option>
    <option value="passed">합격 (다음 단계로)</option>
    <option value="failed">탈락 (drop)</option>
    <option value="pending">보류 (라운드 재진행)</option>
  </select>
  <textarea name="review" rows="4" 
            placeholder="(선택) After Interview Review — 질문·응답·인상 요약"
            class="form-textarea w-full"></textarea>
  <p class="text-xs text-muted">
    녹음 → STT → 요약 자동화는 별도 설계 중입니다. 지금은 수기 입력만 지원합니다.
  </p>
  <button type="submit" class="btn-primary">면접 완료</button>
</form>
```

### Step 15.4: 커밋

- [ ] **Commit:**

```bash
git add projects/templates/projects/partials/stage_interview.html projects/views.py projects/urls.py tests/test_stage_interview.py
git commit -m "feat(projects): interview stage completion + optional after-interview review"
```

---

## Task 16: stage_hired.html — 입사 확정

**Files:**
- Modify: `projects/templates/projects/partials/stage_hired.html`

### Step 16.1: 기존 application_hire 뷰 재사용

- [ ] **Read `projects/views.py` application_hire view** — hired_at 세팅하고 프로젝트 종료 트리거 되는지 확인.

### Step 16.2: Partial UI

- [ ] **Replace `projects/templates/projects/partials/stage_hired.html`:**

```django
<div class="space-y-3">
  <p class="font-medium">🎉 입사 확정</p>
  {% if application.hired_at %}
    <p class="text-sm">입사 확정일: {{ application.hired_at|date:"Y-m-d" }}</p>
  {% else %}
    <form method="post" action="{% url 'projects:application_hire' application.pk %}"
          class="space-y-2">
      {% csrf_token %}
      <input type="date" name="hired_on" required class="form-input">
      <button type="submit" class="btn-primary">입사일 확정</button>
    </form>
  {% endif %}
</div>
```

### Step 16.3: 커밋

- [ ] **Commit:**

```bash
git add projects/templates/projects/partials/stage_hired.html
git commit -m "feat(projects): hired stage partial — reuses application_hire view"
```

---

## Task 17: 레거시 탭 뷰/템플릿 정리

**Files:**
- Modify: `projects/views.py` (project_tab_* 뷰 제거)
- Modify: `projects/urls.py` (tab URL 제거)
- Delete: `projects/templates/projects/partials/tab_*.html`

### Step 17.1: 참조 확인

- [ ] **Grep all tab_overview/tab_search/tab_submissions/tab_interviews references:**

```bash
```

(Grep tool 사용)

### Step 17.2: 안전하게 제거할 수 있는지 판단

- [ ] 외부 참조(브라우저 즐겨찾기 등)가 없고, 테스트도 없으면 제거. 있으면 redirect 스텁만 남기고 뷰 제거.

### Step 17.3: 제거 + 테스트

- [ ] **Remove tab views/urls/templates**:

```bash
rm projects/templates/projects/partials/tab_overview.html
rm projects/templates/projects/partials/tab_search.html
rm projects/templates/projects/partials/tab_submissions.html
rm projects/templates/projects/partials/tab_interviews.html
rm projects/templates/projects/partials/tab_interviews_with_form.html
rm projects/templates/projects/partials/detail_tab_bar.html
```

- [ ] **Edit `projects/urls.py`** — remove 4 tab URL paths.
- [ ] **Edit `projects/views.py`** — remove 4 tab view functions.

### Step 17.4: 전체 테스트

- [ ] **Run full test suite:**

```bash
uv run pytest -v
```
Expected: 기존 기능 깨짐 없음.

### Step 17.5: 커밋

- [ ] **Commit:**

```bash
git add -A
git commit -m "chore(projects): remove deprecated project_tab_* views and templates (replaced by area A/B layout)"
```

---

## Task 18: 통합 스모크 + 최종 점검

### Step 18.1: 전체 플로우 수동 테스트

- [ ] 다음 플로우를 브라우저에서 확인 후 URL 보고:
  1. 빈 프로젝트 → 영역 A의 "DB에서 찾기" → candidates 페이지에서 2명 추가
  2. 프로젝트 상세로 돌아와 2장 카드 확인 — 진행바 7단계, 접촉 단계 활성
  3. 1번 카드: 접촉 완료 (긍정) → 이력서 준비 단계로
  4. 2번 카드: 접촉 완료 (부정) → drop 확인
  5. 1번 카드: 이력서 준비 (기존 3방법 중 하나) → 사전미팅 단계로
  6. 1번 카드: 사전미팅 일정 → 결과 입력 → 이력서 작성 단계로
  7. 1번 카드: 컨펌 → 이력서 제출 단계로
  8. 1번 카드: 단독 제출 → 면접 단계로
  9. 영역 A 배치 제출 테스트 — 이력서 작성 단계 후보자 여러 명 선택
  10. 면접 결과 합격 → 입사 단계 → 입사일 확정 → 프로젝트 종료 확인

### Step 18.2: 전체 테스트 + 린트

- [ ] **Run all tests + lint:**

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
```

### Step 18.3: 최종 커밋 (문서 업데이트)

- [ ] **Update `docs/session-handoff/2026-04-18-project-detail-L2.md`** — Phase C 완료 표시.

- [ ] **Commit:**

```bash
git add docs/session-handoff/2026-04-18-project-detail-L2.md
git commit -m "docs(handoff): mark Phase C complete per design 2026-04-18-project-detail-stage-model"
```

---

## Self-Review Checklist (계획 완료 후 자체 점검)

### Spec coverage

- [x] Section 2 페이지 구조 (A/B) → Task 4
- [x] Section 3 단계 레벨 분류 (7-stage card) → Task 2, 8
- [x] Section 4 서칭 단계 상세 (DB + 외부 placeholder) → Task 5, 6
- [x] Section 5.1 접촉 → Task 10
- [x] Section 5.2 이력서 준비 → Task 11 (Phase B 재사용)
- [x] Section 5.3 사전 미팅 (일정·진행·기록) → Task 12
- [x] Section 5.4 이력서 작성 + 컨펌 → Task 13
- [x] Section 5.5 이력서 제출 (개별) → Task 14
- [x] Section 5.5 이력서 제출 (배치) → Task 7
- [x] Section 5.6 면접 + Review → Task 15
- [x] Section 5.7 입사 → Task 16
- [x] Section 7 네이밍 변경 → Task 1
- [x] Section 8 별도 설계 문서 대상 → 본 계획 범위 밖 (플레이스홀더만)
- [x] Submission.batch_id 필드 → Task 3
- [x] 레거시 탭 정리 → Task 17

### Placeholder / Ambiguity 점검

- 모든 Task 에 구체 파일 경로·코드·검증 명령 포함. TBD 없음.
- 템플릿 내부 CSS 클래스는 "기존 스타일에 맞춰 유지"로 주석 — 실제 구현 시 design-system.md 참조.

### Type / Signature 일관성

- `current_stage`, `stages_passed` — 기존 property 시그니처 유지.
- `CARD_STAGES_ORDER` — Task 2 정의 후 Task 8·9에서 동일 사용.
- `batch_id` — Task 3 정의 후 Task 7·14에서 동일 사용.
- ActionType code 참조 (`reach_out`, `submit_to_client`, `pre_meeting` 등) — 기존 DB 코드와 동일.

---

## 실행 방식 선택

이 계획을 완료하려면 다음 중 하나를 선택하세요:

**1. Subagent-Driven (권장)** — Task 별로 신선한 subagent 를 dispatch, 각 Task 후 리뷰.
**2. Inline Execution** — 현 세션에서 executing-plans 로 일괄 실행, 체크포인트에서 리뷰.
