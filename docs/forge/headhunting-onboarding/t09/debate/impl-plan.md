# Task 9: 빈 화면 CTA (역할별 분기)

**Goal:** 프로젝트 목록, 고객사 목록, 대시보드의 빈 화면에 역할별 CTA를 표시한다. owner에게는 생성 버튼을, consultant에게는 안내 메시지를 보여준다.

**Design spec:** `docs/forge/headhunting-onboarding/t09/design-spec.md`

**depends_on:** Task 1 (구현 완료), Task 2 (구현 완료), Task 7

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/templates/projects/partials/view_board.html` | 수정 | 프로젝트 빈 화면 역할별 CTA |
| `clients/templates/clients/client_list.html` | 수정 | 고객사 빈 화면 역할별 CTA |

---

- [ ] **Step 1: Update project list empty state**

In the project list template, find the empty state section and add role-based CTA:

```html
{% if not projects %}
<div class="flex flex-col items-center justify-center py-16 text-center">
  <svg class="w-12 h-12 text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
  </svg>
  {% if membership and membership.role == 'owner' %}
    <p class="text-gray-500 mb-4">프로젝트가 없습니다.</p>
    <a href="{% url 'projects:project_create' %}"
       class="px-4 py-2 bg-primary text-white rounded-lg text-sm">
      새 프로젝트 만들기
    </a>
  {% else %}
    <p class="text-gray-500">배정된 프로젝트가 없습니다.</p>
    <p class="text-gray-400 text-sm mt-1">관리자가 프로젝트를 배정하면 여기에 표시됩니다.</p>
  {% endif %}
</div>
{% endif %}
```

- [ ] **Step 2: Update client list empty state**

```html
{% if not clients %}
<div class="flex flex-col items-center justify-center py-16 text-center">
  {% if membership and membership.role == 'owner' %}
    <p class="text-gray-500 mb-4">등록된 고객사가 없습니다.</p>
    <a href="{% url 'clients:client_create' %}"
       class="px-4 py-2 bg-primary text-white rounded-lg text-sm">
      첫 고객사를 등록하세요
    </a>
  {% else %}
    <p class="text-gray-500">등록된 고객사가 없습니다.</p>
  {% endif %}
</div>
{% endif %}
```

- [ ] **Step 3: Update dashboard empty state**

In the dashboard template, add owner-specific CTA when no data:

```html
{% if not today_actions and not weekly_schedule %}
  {% if membership and membership.role == 'owner' %}
    <p class="text-gray-500 mb-4">아직 진행 중인 업무가 없습니다.</p>
    <a href="/clients/"
       hx-get="/clients/" hx-target="#main-content" hx-push-url="true"
       class="px-4 py-2 bg-primary text-white rounded-lg text-sm">
      고객사를 등록하고 첫 프로젝트를 시작하세요
    </a>
  {% else %}
    <p class="text-gray-500">배정된 프로젝트가 없습니다.</p>
    <p class="text-gray-400 text-sm mt-1">관리자가 프로젝트를 배정하면 여기에 표시됩니다.</p>
  {% endif %}
{% endif %}
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/templates/ clients/templates/
git commit -m "feat(ui): add role-based empty state CTAs for projects, clients, dashboard"
```
