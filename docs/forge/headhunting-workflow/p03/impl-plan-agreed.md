# P03: Project Basic CRUD — 확정 구현계획서

> **Phase:** 3
> **선행조건:** P01 (models), P02 (client management)
> **산출물:** Project CRUD + 필터/정렬 리스트 + 사이드바 메뉴

---

## 목표

프로젝트(Project) 기본 CRUD와 필터/정렬이 가능한 리스트 뷰를 구현한다.
P02에서 확립된 패턴(org 필터링, 동적 extends, @login_required 등)을 동일하게 적용한다.

---

## URL 설계

| URL | View | Template | 설명 |
|-----|------|----------|------|
| `/projects/` | `project_list` | `projects/project_list.html` | 프로젝트 목록 |
| `/projects/new/` | `project_create` | `projects/project_form.html` | 등록 폼 |
| `/projects/<uuid:pk>/` | `project_detail` | `projects/project_detail.html` | 상세 |
| `/projects/<uuid:pk>/edit/` | `project_update` | `projects/project_form.html` | 수정 폼 |
| `/projects/<uuid:pk>/delete/` | `project_delete` | — | 삭제 (POST) |

`projects/urls.py` 생성 (`app_name = "projects"`).
`main/urls.py`에 `path("projects/", include("projects.urls"))` 추가.

---

## View 구현

모든 view에 `@login_required` 적용.
모든 queryset에 Organization 필터링 (`_get_org(request)` P02 패턴 재사용).

```python
@login_required
def project_list(request):
    """프로젝트 목록. scope/client/status 필터 + 정렬 + 페이지네이션."""
    org = _get_org(request)
    projects = Project.objects.filter(organization=org)
    
    # scope 필터 (기본: mine)
    scope = request.GET.get("scope", "mine")
    if scope == "mine":
        projects = projects.filter(
            Q(assigned_consultants=request.user) | Q(created_by=request.user)
        ).distinct()
    
    # client, status 필터
    # 정렬: created_at 기반 (days_desc = created_at asc, days_asc = created_at desc)

@login_required
def project_create(request):
    """등록. 고객사 선택 + JD 텍스트/파일 입력."""
    org = _get_org(request)
    # POST: form = ProjectForm(request.POST, request.FILES)
    # form.instance.organization = org
    # form.instance.created_by = request.user
    # save 후: project.assigned_consultants.add(request.user)
    # Client 드롭다운: Client.objects.filter(organization=org) 로 제한

@login_required
def project_detail(request, pk):
    """상세. 기본 개요 (P05에서 탭 확장)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

@login_required
def project_update(request, pk):
    """수정."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    # form = ProjectForm(request.POST, request.FILES, instance=project)

@login_required
def project_delete(request, pk):
    """삭제. Contact/Submission 등 관련 데이터 존재 시 차단."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    # 관련 데이터 체크: contacts, submissions 존재 시 삭제 차단
```

---

## 필터 파라미터

| 파라미터 | 값 | 기본값 |
|---------|-----|-------|
| `scope` | `mine` / `all` | `mine` |
| `client` | Client UUID | — |
| `status` | ProjectStatus value | — |
| `sort` | `days_desc` / `days_asc` / `created` | `days_desc` |

- `scope=mine`: `Q(assigned_consultants=user) | Q(created_by=user)`
- 정렬은 created_at 기반으로 단순화 (DurationField annotation 불필요)

---

## 파일 업로드

Project.jd_file은 FileField. 폼에서 처리:
- Template: `<form enctype="multipart/form-data">`
- View: `ProjectForm(request.POST, request.FILES)`
- posting_text 필드는 폼에서 exclude (P10에서 구현)

---

## Template 구조

P02 패턴 따름 — top-level 파일, 동적 extends:

```
projects/templates/projects/
├── project_list.html     # 목록 (동적 extends)
├── project_detail.html   # 상세 (동적 extends)
└── project_form.html     # 등록/수정 공용 (동적 extends)
```

모든 HTMX: `hx-target="#main-content"` + `hx-push-url="true"`

---

## 경과일 표시

```python
@property
def days_elapsed(self) -> int:
    return (timezone.now().date() - self.created_at.date()).days
```

템플릿에서 `{{ project.days_elapsed }}` 표시. 정렬은 DB 레벨에서 `created_at` 기준.

---

## 사이드바 + 하단 네비 변경

P02 완료 후 메뉴 순서: 후보자 > **프로젝트** > 고객사 > 설정

nav_sidebar.html, nav_bottom.html 모두 수정:
```html
<a hx-get="/projects/" hx-target="#main-content" hx-push-url="true">
  📋 프로젝트
</a>
```

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| CRUD 동작 | pytest-django client fixture로 HTTP 요청/응답 테스트 |
| Organization 격리 | 타 조직 프로젝트 미표시 |
| @login_required | 비인증 시 로그인 리다이렉트 |
| scope=mine | 본인 담당/생성 건만 표시 |
| scope=all | 같은 org의 모든 프로젝트 표시 |
| 필터 | client, status 필터 동작 |
| 정렬 | days_desc/days_asc 정렬 |
| created_by 자동 설정 | 등록 시 request.user 할당 |
| assigned_consultants 자동 추가 | 등록 시 creator 추가 |
| JD 파일 업로드 | 파일 업로드 → 저장 확인 |
| 삭제 보호 | 관련 데이터 있으면 차단 |
| 경과일 표시 | days_elapsed 정확성 |

---

## 산출물

- `projects/views.py` — CRUD 뷰 5개
- `projects/urls.py` — URL 패턴
- `projects/forms.py` — ProjectForm
- `projects/templates/projects/` — 목록/상세/폼 템플릿
- `main/urls.py` — projects include 추가
- `templates/common/nav_sidebar.html` — 프로젝트 메뉴 추가
- `templates/common/nav_bottom.html` — 프로젝트 메뉴 추가
- 테스트 파일

<!-- forge:p03:구현담금질:complete:2026-04-08T14:00:00+09:00 -->
