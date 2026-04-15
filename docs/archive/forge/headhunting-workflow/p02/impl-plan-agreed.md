# P02: Client Management — 확정 구현계획서

> **Phase:** 2
> **선행조건:** P01 (models and app foundation)
> **산출물:** Client CRUD 화면 + Contract 인라인 관리 + 사이드바/하단 네비 메뉴

---

## 목표

고객사(Client) CRUD 화면을 구현한다. HTMX 네비게이션 패턴을 적용하고
사이드바 + 하단 네비에 고객사 메뉴를 추가한다.

---

## URL 설계

| URL | View | Template | 설명 |
|-----|------|----------|------|
| `/clients/` | `client_list` | `clients/client_list.html` | 고객사 목록 |
| `/clients/new/` | `client_create` | `clients/client_form.html` | 등록 폼 |
| `/clients/<uuid:pk>/` | `client_detail` | `clients/client_detail.html` | 상세 |
| `/clients/<uuid:pk>/edit/` | `client_update` | `clients/client_form.html` | 수정 폼 |
| `/clients/<uuid:pk>/delete/` | `client_delete` | — | 삭제 (POST) |
| `/clients/<uuid:pk>/contracts/new/` | `contract_create` | inline partial | 계약 등록 |
| `/clients/<uuid:pk>/contracts/<uuid:contract_pk>/edit/` | `contract_update` | inline partial | 계약 수정 |
| `/clients/<uuid:pk>/contracts/<uuid:contract_pk>/delete/` | `contract_delete` | — | 계약 삭제 |

`clients/urls.py`에 정의, `main/urls.py`에 `path("clients/", include("clients.urls"))` 추가.

---

## View 구현

모든 view에 `@login_required` 데코레이터 적용.
모든 queryset에 Organization 필터링 적용.

```python
# clients/views.py
from django.contrib.auth.decorators import login_required

def _get_org(request):
    """현재 사용자의 Organization 반환. Membership 없으면 404."""
    return get_object_or_404(Organization, membership__user=request.user)

@login_required
def client_list(request):
    """고객사 목록. 검색(name, industry) + 페이지네이션."""
    org = _get_org(request)
    clients = Client.objects.filter(organization=org)
    # 검색 필터, 페이지네이션...

@login_required
def client_create(request):
    """고객사 등록. GET=폼, POST=저장 후 상세로 redirect."""
    org = _get_org(request)
    # POST: form.instance.organization = org

@login_required
def client_detail(request, pk):
    """고객사 상세. 계약 이력 + 진행중 프로젝트 포함."""
    org = _get_org(request)
    client = get_object_or_404(Client, pk=pk, organization=org)
    contracts = client.contracts.all()
    active_projects = client.projects.exclude(
        status__in=["closed_success", "closed_fail", "closed_cancel", "on_hold"]
    )

@login_required
def client_update(request, pk):
    """고객사 수정. GET=폼(기존값), POST=저장."""
    org = _get_org(request)
    client = get_object_or_404(Client, pk=pk, organization=org)

@login_required
def client_delete(request, pk):
    """삭제. 진행중 프로젝트 있으면 차단."""
    org = _get_org(request)
    client = get_object_or_404(Client, pk=pk, organization=org)
    active_projects = client.projects.exclude(
        status__in=["closed_success", "closed_fail", "closed_cancel", "on_hold"]
    )
    if active_projects.exists():
        # 삭제 차단, 에러 메시지 반환
        return ...
    client.delete()
```

---

## Template 렌더링 패턴

**동적 extends 패턴** 채택 (review_list.html 패턴):

```html
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}
```

이 패턴으로 HTMX 요청 시 partial, 직접 접근 시 full page를 단일 템플릿에서 처리.

### HTMX target

모든 HTMX 링크에서 `hx-target="#main-content"` 사용 (기존 코드베이스와 일치).

```
clients/templates/clients/
├── client_list.html          # 목록 (동적 extends)
├── client_detail.html        # 상세 (동적 extends)
└── client_form.html          # 등록/수정 공용 (동적 extends)
```

---

## 사이드바 + 하단 네비 변경

### nav_sidebar.html

```html
<!-- 기존 "후보자" 메뉴 위 또는 아래에 추가 -->
<a hx-get="/clients/" hx-target="#main-content" hx-push-url="true">
  🏢 고객사
</a>
```

P02 완료 시점 메뉴 순서: **후보자 > 고객사 > 설정**

### nav_bottom.html

```html
<a hx-get="/clients/" hx-target="#main-content" hx-push-url="true">
  🏢 고객사
</a>
```

---

## contact_persons 동적 폼

Client.contact_persons는 JSONField(list of dicts). 동적 추가/제거 UI 필요.

**구현 방식:** JavaScript로 DOM 조작 + hidden input에 JSON 직렬화.

```javascript
// static/js/contact-persons.js
// [+ 담당자 추가] 클릭 시 입력 행 DOM 추가
// 각 행: 이름, 직책, 전화, 이메일
// 폼 제출 시 모든 행을 JSON으로 직렬화하여 hidden input에 설정
```

View에서 `request.POST.get("contact_persons_json")`을 파싱하여 `client.contact_persons`에 저장.
ClientForm은 contact_persons 필드를 exclude하고 별도 처리.

---

## Contract 인라인 관리

고객사 상세 페이지에서 계약 이력을 표시하고 인라인 CRUD.

- 계약 목록: 상세 페이지 하단 섹션
- 등록/수정: HTMX 인라인 폼 (hx-target으로 계약 섹션만 교체)
- 삭제: POST 확인

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| CRUD 동작 | 등록 → 목록에 표시 → 상세 확인 → 수정 → 삭제 |
| Organization 격리 | 타 조직 고객사가 목록에 미표시 |
| @login_required | 비인증 접근 시 로그인 리다이렉트 |
| HTMX 네비게이션 | hx-get 요청 시 partial 반환, URL push 동작 |
| 검색 | 고객사명/업종 키워드 검색 결과 확인 |
| 사이드바/하단 | 고객사 메뉴 클릭 시 목록 화면 전환 |
| 상세 페이지 | 계약 이력 + 진행중 프로젝트(CLOSED/ON_HOLD 제외) 표시 |
| contact_persons | 복수 담당자 JSON 저장/조회 |
| 삭제 보호 | 진행중 프로젝트 있으면 삭제 차단 |
| Contract CRUD | 인라인 등록/수정/삭제 |

---

## 산출물

- `clients/views.py` — CRUD 뷰 5개 + Contract 뷰 3개
- `clients/urls.py` — URL 패턴
- `clients/forms.py` — ClientForm, ContractForm
- `clients/templates/clients/` — 목록/상세/폼 템플릿
- `main/urls.py` — clients include 추가
- `templates/common/nav_sidebar.html` — 고객사 메뉴 추가
- `templates/common/nav_bottom.html` — 고객사 메뉴 추가
- `static/js/contact-persons.js` — 담당자 동적 폼
- 테스트 파일

<!-- forge:p02:구현담금질:complete:2026-04-08T13:00:00+09:00 -->
