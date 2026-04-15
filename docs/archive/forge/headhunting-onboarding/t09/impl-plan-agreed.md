# Task 9: 빈 화면 CTA (역할별 분기) — Agreed Implementation Plan

**Goal:** 프로젝트 목록, 고객사 목록, 대시보드, 프로젝트 컨택/추천 탭의 빈 화면에 역할별 CTA를 표시한다. owner에게는 생성 버튼을, consultant에게는 안내 메시지를 보여준다.

**Design spec:** `docs/forge/headhunting-onboarding/t09/design-spec.md`

**depends_on:** Task 1 (구현 완료), Task 2 (구현 완료), Task 7

**Rulings:** `docs/forge/headhunting-onboarding/t09/debate/impl-rulings.md`

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/templates/projects/project_list.html` | 수정 | 헤더 `+ 등록` 버튼 owner-only |
| `projects/templates/projects/partials/view_list.html` | 수정 | 프로젝트 리스트 뷰 빈 화면 역할별 CTA |
| `projects/templates/projects/partials/view_table.html` | 수정 | 프로젝트 테이블 뷰 빈 화면 역할별 CTA |
| `clients/templates/clients/client_list.html` | 수정 | 헤더 버튼 owner-only + 빈 화면 역할별 CTA |
| `projects/templates/projects/partials/dash_actions.html` | 수정 | 대시보드 오늘의 액션 빈 화면 역할별 문구 |
| `projects/templates/projects/partials/dash_schedule.html` | 수정 | 대시보드 이번 주 빈 화면 역할별 문구 |
| `projects/templates/projects/partials/tab_contacts.html` | 수정 | 컨택 탭 빈 화면 문구 업데이트 (역할 무관) |
| `projects/templates/projects/partials/tab_submissions.html` | 수정 | 추천 탭 빈 화면 문구 업데이트 (역할 무관) |

---

- [ ] **Step 1: Gate header buttons in project_list.html**

In `projects/templates/projects/project_list.html`, wrap the header `+ 등록` button in owner role check.

**현재 코드** (lines 9-15):
```html
<a href="{% url 'projects:project_create' %}"
   hx-get="{% url 'projects:project_create' %}" hx-target="#main-content" hx-push-url="true"
   class="bg-primary text-white font-semibold py-2 px-4 rounded-lg text-[15px] hover:bg-primary-dark transition">
  + 등록
</a>
```

**변경 후:**
```html
{% if membership and membership.role == 'owner' %}
<a href="{% url 'projects:project_create' %}"
   hx-get="{% url 'projects:project_create' %}" hx-target="#main-content" hx-push-url="true"
   class="bg-primary text-white font-semibold py-2 px-4 rounded-lg text-[15px] hover:bg-primary-dark transition">
  + 등록
</a>
{% endif %}
```

---

- [ ] **Step 2: Update project list view empty state (view_list.html)**

In `projects/templates/projects/partials/view_list.html`, replace the empty state block (lines 83-100) with role-based CTA.

**현재 코드** (lines 83-100):
```html
{% with has_any=urgency_groups.0.projects|length|add:urgency_groups.1.projects|length|add:urgency_groups.2.projects|length %}
{% if not has_any %}
<div class="flex flex-col items-center justify-center py-12 px-4 text-center">
  <p class="text-gray-500 text-[15px] mb-4">
    {% if scope == "mine" %}
    담당 프로젝트가 없습니다.
    {% else %}
    등록된 프로젝트가 없습니다.
    {% endif %}
  </p>
  <a href="{% url 'projects:project_create' %}"
     hx-get="{% url 'projects:project_create' %}" hx-target="#main-content" hx-push-url="true"
     class="bg-primary text-white font-semibold py-2.5 px-5 rounded-lg text-[15px] hover:bg-primary-dark transition">
    프로젝트 등록
  </a>
</div>
{% endif %}
{% endwith %}
```

**변경 후:**
```html
{% with has_any=urgency_groups.0.projects|length|add:urgency_groups.1.projects|length|add:urgency_groups.2.projects|length %}
{% if not has_any %}
<div class="flex flex-col items-center justify-center py-12 px-4 text-center">
  {% if membership and membership.role == 'owner' %}
  <p class="text-gray-500 text-[15px] mb-4">
    {% if scope == "mine" %}
    담당 프로젝트가 없습니다.
    {% else %}
    등록된 프로젝트가 없습니다.
    {% endif %}
  </p>
  <a href="{% url 'projects:project_create' %}"
     hx-get="{% url 'projects:project_create' %}" hx-target="#main-content" hx-push-url="true"
     class="bg-primary text-white font-semibold py-2.5 px-5 rounded-lg text-[15px] hover:bg-primary-dark transition">
    새 프로젝트 만들기
  </a>
  {% else %}
  <p class="text-gray-500 text-[15px]">배정된 프로젝트가 없습니다.</p>
  <p class="text-gray-400 text-[13px] mt-1">관리자가 프로젝트를 배정하면 여기에 표시됩니다.</p>
  {% endif %}
</div>
{% endif %}
{% endwith %}
```

---

- [ ] **Step 3: Update project table view empty state (view_table.html)**

In `projects/templates/projects/partials/view_table.html`, replace the empty state block (lines 101-116) with role-based CTA.

**현재 코드** (lines 101-116):
```html
{% else %}
<div class="flex flex-col items-center justify-center py-12 px-4 text-center">
  <p class="text-gray-500 text-[15px] mb-4">
    {% if scope == "mine" %}
    담당 프로젝트가 없습니다.
    {% else %}
    등록된 프로젝트가 없습니다.
    {% endif %}
  </p>
  <a href="{% url 'projects:project_create' %}"
     hx-get="{% url 'projects:project_create' %}" hx-target="#main-content" hx-push-url="true"
     class="bg-primary text-white font-semibold py-2.5 px-5 rounded-lg text-[15px] hover:bg-primary-dark transition">
    프로젝트 등록
  </a>
</div>
{% endif %}
```

**변경 후:**
```html
{% else %}
<div class="flex flex-col items-center justify-center py-12 px-4 text-center">
  {% if membership and membership.role == 'owner' %}
  <p class="text-gray-500 text-[15px] mb-4">
    {% if scope == "mine" %}
    담당 프로젝트가 없습니다.
    {% else %}
    등록된 프로젝트가 없습니다.
    {% endif %}
  </p>
  <a href="{% url 'projects:project_create' %}"
     hx-get="{% url 'projects:project_create' %}" hx-target="#main-content" hx-push-url="true"
     class="bg-primary text-white font-semibold py-2.5 px-5 rounded-lg text-[15px] hover:bg-primary-dark transition">
    새 프로젝트 만들기
  </a>
  {% else %}
  <p class="text-gray-500 text-[15px]">배정된 프로젝트가 없습니다.</p>
  <p class="text-gray-400 text-[13px] mt-1">관리자가 프로젝트를 배정하면 여기에 표시됩니다.</p>
  {% endif %}
</div>
{% endif %}
```

---

- [ ] **Step 4: Gate header button and update client list empty state**

In `clients/templates/clients/client_list.html`:

**(a)** Wrap header `+ 등록` button (lines 9-15) in owner check:
```html
{% if membership and membership.role == 'owner' %}
<a href="{% url 'clients:client_create' %}"
   hx-get="{% url 'clients:client_create' %}" hx-target="#main-content" hx-push-url="true"
   class="bg-primary text-white font-semibold py-2 px-4 rounded-lg text-[15px] hover:bg-primary-dark transition">
  + 등록
</a>
{% endif %}
```

**(b)** Update empty state (lines 88-104). Preserve the existing `q` search distinction. Only modify the `{% if not q %}` branch to add role-based CTA:

**현재 코드:**
```html
{% else %}
<div class="flex flex-col items-center justify-center py-12 px-4 text-center">
  <p class="text-gray-500 text-[15px] mb-4">
    {% if q %}
    '{{ q }}'에 해당하는 고객사가 없습니다.
    {% else %}
    등록된 고객사가 없습니다.
    {% endif %}
  </p>
  {% if not q %}
  <a href="{% url 'clients:client_create' %}"
     hx-get="{% url 'clients:client_create' %}" hx-target="#main-content" hx-push-url="true"
     class="bg-primary text-white font-semibold py-2.5 px-5 rounded-lg text-[15px] hover:bg-primary-dark transition">
    고객사 등록
  </a>
  {% endif %}
</div>
{% endif %}
```

**변경 후:**
```html
{% else %}
<div class="flex flex-col items-center justify-center py-12 px-4 text-center">
  {% if q %}
  <p class="text-gray-500 text-[15px]">'{{ q }}'에 해당하는 고객사가 없습니다.</p>
  {% elif membership and membership.role == 'owner' %}
  <p class="text-gray-500 text-[15px] mb-4">등록된 고객사가 없습니다.</p>
  <a href="{% url 'clients:client_create' %}"
     hx-get="{% url 'clients:client_create' %}" hx-target="#main-content" hx-push-url="true"
     class="bg-primary text-white font-semibold py-2.5 px-5 rounded-lg text-[15px] hover:bg-primary-dark transition">
    첫 고객사를 등록하세요
  </a>
  {% else %}
  <p class="text-gray-500 text-[15px]">등록된 고객사가 없습니다.</p>
  {% endif %}
</div>
{% endif %}
```

---

- [ ] **Step 5: Update dashboard per-partial empty states**

**(a)** In `projects/templates/projects/partials/dash_actions.html`, update the `{% else %}` block (line 21):

**현재 코드:**
```html
{% else %}
<p class="text-[14px] text-gray-400 text-center py-4">오늘 긴급한 액션이 없습니다.</p>
{% endif %}
```

**변경 후:**
```html
{% else %}
<p class="text-[14px] text-gray-400 text-center py-4">
  {% if is_owner %}오늘 긴급한 액션이 없습니다.{% else %}배정된 업무가 없습니다.{% endif %}
</p>
{% endif %}
```

**(b)** In `projects/templates/projects/partials/dash_schedule.html`, update the `{% else %}` block (line 17):

**현재 코드:**
```html
{% else %}
<p class="text-[14px] text-gray-400 text-center py-4">이번 주 일정이 없습니다.</p>
{% endif %}
```

**변경 후:**
```html
{% else %}
<p class="text-[14px] text-gray-400 text-center py-4">
  {% if is_owner %}이번 주 일정이 없습니다.{% else %}배정된 일정이 없습니다.{% endif %}
</p>
{% endif %}
```

**Note:** `is_owner` is already available in dashboard context (`projects/views.py:2450`). `dash_actions.html`는 `dashboard_actions` 뷰에서도 렌더되므로, 해당 뷰에도 `is_owner` 전달이 필요할 수 있다. 확인 필요 — `dashboard_actions` 뷰(`views.py:2464`)는 현재 `is_owner`를 전달하지 않는다. 추가 필요.

---

- [ ] **Step 6: Update contact tab empty state (role-independent)**

In `projects/templates/projects/partials/tab_contacts.html`, update the empty message (line 74-76):

**현재 코드:**
```html
{% else %}
<p class="text-[14px] text-gray-400">컨택 이력이 없습니다.</p>
{% endif %}
```

**변경 후:**
```html
{% else %}
<p class="text-[14px] text-gray-400">후보자를 서칭하고 컨택을 시작하세요.</p>
<button hx-get="{% url 'projects:project_tab_search' project.pk %}"
        hx-target="#tab-content"
        class="text-[13px] text-primary hover:text-primary-dark mt-2 inline-block">
  서칭 탭으로 이동 &rarr;
</button>
{% endif %}
```

---

- [ ] **Step 7: Update submission tab empty state (role-independent)**

In `projects/templates/projects/partials/tab_submissions.html`, update the empty message (lines 192-196):

**현재 코드:**
```html
{% if total_count == 0 %}
<div class="bg-white rounded-lg border border-gray-100 p-5">
  <p class="text-[14px] text-gray-400">추천 이력이 없습니다.</p>
</div>
{% endif %}
```

**변경 후:**
```html
{% if total_count == 0 %}
<div class="bg-white rounded-lg border border-gray-100 p-5">
  <p class="text-[14px] text-gray-400">컨택에서 관심 후보자가 생기면 추천서류를 작성할 수 있습니다.</p>
</div>
{% endif %}
```

---

- [ ] **Step 8: Pass is_owner to dashboard_actions partial view**

In `projects/views.py`, update the `dashboard_actions` view (line 2464) to pass `is_owner`:

**현재 코드:**
```python
def dashboard_actions(request):
    """오늘의 액션 HTMX partial (새로고침용)."""
    org = _get_org(request)
    from projects.services.dashboard import get_today_actions
    today_actions = get_today_actions(request.user, org)
    return render(
        request,
        "projects/partials/dash_actions.html",
        {"today_actions": today_actions},
    )
```

**변경 후:**
```python
def dashboard_actions(request):
    """오늘의 액션 HTMX partial (새로고침용)."""
    org = _get_org(request)
    from projects.services.dashboard import get_today_actions
    today_actions = get_today_actions(request.user, org)
    is_owner = False
    try:
        is_owner = request.user.membership.role == "owner"
    except Exception:
        pass
    return render(
        request,
        "projects/partials/dash_actions.html",
        {"today_actions": today_actions, "is_owner": is_owner},
    )
```

---

- [ ] **Step 9: Run test suite**

Run: `uv run pytest -v`
Expected: All existing tests PASS.

---

- [ ] **Step 10: Commit**

```bash
git add projects/templates/ clients/templates/ projects/views.py
git commit -m "feat(ui): add role-based empty state CTAs for projects, clients, dashboard, tabs"
```

<!-- forge:t09:구현담금질:complete:2026-04-12T20:30:00+09:00 -->
