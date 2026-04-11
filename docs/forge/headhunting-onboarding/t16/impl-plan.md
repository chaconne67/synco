# t16: 조직 관리 템플릿 구현

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 조직 관리 페이지의 베이스 템플릿, 탭 바, 각 탭(정보/멤버/초대코드) 파셜 템플릿을 구현한다.

**Design spec:** `docs/forge/headhunting-onboarding/t16/design-spec.md`

**depends_on:** t15

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `accounts/templates/accounts/org_base.html` | 생성 | 조직 관리 베이스 (탭 바 + `#org-content`) |
| `accounts/templates/accounts/partials/org_tab_bar.html` | 생성 | 조직 관리 탭 바 (정보/멤버/초대코드) |
| `accounts/templates/accounts/partials/org_info.html` | 생성 | 조직 정보 탭 파셜 |
| `accounts/templates/accounts/partials/org_members.html` | 생성 | 멤버 관리 탭 파셜 |
| `accounts/templates/accounts/partials/org_invites.html` | 생성 | 초대코드 관리 탭 파셜 |

---

- [ ] **Step 1: Create org_base.html**

```html
{# accounts/templates/accounts/org_base.html #}
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}

{% block title %}synco - 조직 관리{% endblock %}

{% block content %}
<div class="p-4 lg:p-8 space-y-6">
  <!-- Page Header -->
  <div>
    <h1 class="text-heading font-bold">조직 관리</h1>
  </div>

  <!-- Tab Bar -->
  {% include "accounts/partials/org_tab_bar.html" %}

  <!-- Tab Content -->
  <div id="org-content">
    {% if tab_template %}
      {% include tab_template %}
    {% else %}
      {% include "accounts/partials/org_info.html" %}
    {% endif %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Create org_tab_bar.html**

```html
{# accounts/templates/accounts/partials/org_tab_bar.html #}
<div class="border-b border-gray-200 flex gap-0 overflow-x-auto -mx-4 lg:-mx-8 px-4 lg:px-8">
  {% with active=active_tab|default:"info" %}

  <button hx-get="{% url 'org_info' %}"
          hx-target="#org-content"
          hx-push-url="true"
          class="px-4 py-2.5 text-[14px] font-medium whitespace-nowrap border-b-2 transition
            {% if active == 'info' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300{% endif %}">
    조직 정보
  </button>

  <button hx-get="{% url 'org_members' %}"
          hx-target="#org-content"
          hx-push-url="true"
          class="px-4 py-2.5 text-[14px] font-medium whitespace-nowrap border-b-2 transition
            {% if active == 'members' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300{% endif %}">
    멤버 관리
  </button>

  <button hx-get="{% url 'org_invites' %}"
          hx-target="#org-content"
          hx-push-url="true"
          class="px-4 py-2.5 text-[14px] font-medium whitespace-nowrap border-b-2 transition
            {% if active == 'invites' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300{% endif %}">
    초대코드
  </button>

  {% endwith %}
</div>
```

- [ ] **Step 3: Create org_info.html**

```html
{# accounts/templates/accounts/partials/org_info.html #}
{% load static %}

<section class="bg-white rounded-lg border border-gray-100 p-5">
  <h2 class="text-[15px] font-semibold text-gray-500 mb-4">조직 정보</h2>

  <form method="post"
        enctype="multipart/form-data"
        hx-post="{% url 'org_info' %}"
        hx-target="#org-content"
        hx-push-url="false">
    {% csrf_token %}

    <div class="space-y-4">
      <!-- Organization name -->
      <div>
        <label for="id_name" class="block text-[14px] font-medium text-gray-700 mb-1.5">조직명</label>
        {{ form.name }}
      </div>

      <!-- Logo -->
      <div>
        <label for="id_logo" class="block text-[14px] font-medium text-gray-700 mb-1.5">로고</label>
        {% if org.logo %}
        <div class="mb-2">
          <img src="{{ org.logo.url }}" alt="조직 로고" class="w-16 h-16 rounded-lg object-cover border border-gray-200">
        </div>
        {% endif %}
        {{ form.logo }}
      </div>

      <!-- Plan (read-only) -->
      <div class="flex items-center justify-between">
        <span class="text-[14px] text-gray-500">플랜</span>
        <span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700">
          {{ org.get_plan_display }}
        </span>
      </div>

      <!-- DB share (read-only) -->
      <div class="flex items-center justify-between">
        <span class="text-[14px] text-gray-500">DB 공유</span>
        <span class="text-[14px] font-medium {% if org.db_share_enabled %}text-green-600{% else %}text-gray-400{% endif %}">
          {% if org.db_share_enabled %}사용 중{% else %}미사용{% endif %}
        </span>
      </div>
    </div>

    <div class="mt-6">
      <button type="submit"
              class="w-full py-2.5 text-[14px] font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition">
        저장
      </button>
    </div>
  </form>
</section>
```

- [ ] **Step 4: Create org_members.html**

```html
{# accounts/templates/accounts/partials/org_members.html #}
{% load static %}

{% if message %}
<div class="mb-4 p-3 bg-green-50 text-green-700 rounded-lg text-sm">{{ message }}</div>
{% endif %}

<section class="bg-white rounded-lg border border-gray-100">
  <div class="p-5 border-b border-gray-100">
    <h2 class="text-[15px] font-semibold text-gray-500">멤버 목록</h2>
  </div>

  <div class="divide-y divide-gray-50">
    {% for member in members %}
    <div class="p-4 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 bg-gray-100 rounded-full flex items-center justify-center text-[14px] font-medium text-gray-600">
          {{ member.user.first_name|default:member.user.username|truncatechars:2 }}
        </div>
        <div>
          <p class="text-[14px] font-medium text-gray-900">
            {{ member.user.first_name|default:member.user.username }}
          </p>
          <div class="flex items-center gap-2 mt-0.5">
            <span class="text-[12px] px-1.5 py-0.5 rounded
              {% if member.role == 'owner' %}bg-purple-50 text-purple-700
              {% elif member.role == 'consultant' %}bg-blue-50 text-blue-700
              {% else %}bg-gray-100 text-gray-600{% endif %}">
              {{ member.get_role_display }}
            </span>
            <span class="text-[12px] px-1.5 py-0.5 rounded
              {% if member.status == 'active' %}bg-green-50 text-green-700
              {% elif member.status == 'pending' %}bg-amber-50 text-amber-700
              {% else %}bg-red-50 text-red-700{% endif %}">
              {% if member.status == 'active' %}활성
              {% elif member.status == 'pending' %}승인대기
              {% else %}거절{% endif %}
            </span>
            <span class="text-[11px] text-gray-400">{{ member.created_at|date:"Y-m-d" }}</span>
          </div>
        </div>
      </div>

      <div class="flex items-center gap-2">
        {% if member.status == 'pending' %}
          <!-- Approve/Reject buttons -->
          <form method="post"
                hx-post="{% url 'org_member_approve' member.pk %}"
                hx-target="#org-content">
            {% csrf_token %}
            <button type="submit"
                    class="px-3 py-1.5 text-[12px] font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 transition">
              승인
            </button>
          </form>
          <form method="post"
                hx-post="{% url 'org_member_reject' member.pk %}"
                hx-target="#org-content">
            {% csrf_token %}
            <button type="submit"
                    class="px-3 py-1.5 text-[12px] font-medium text-red-600 border border-red-200 rounded-lg hover:bg-red-50 transition">
              거절
            </button>
          </form>

        {% elif member.status == 'active' and member.role != 'owner' %}
          <!-- Role change dropdown -->
          <form method="post"
                hx-post="{% url 'org_member_role' member.pk %}"
                hx-target="#org-content">
            {% csrf_token %}
            <select name="role"
                    onchange="this.form.requestSubmit()"
                    class="text-[12px] px-2 py-1.5 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value="consultant" {% if member.role == 'consultant' %}selected{% endif %}>Consultant</option>
              <option value="viewer" {% if member.role == 'viewer' %}selected{% endif %}>Viewer</option>
            </select>
          </form>
          <!-- Remove button -->
          <form method="post"
                hx-post="{% url 'org_member_remove' member.pk %}"
                hx-target="#org-content"
                hx-confirm="정말로 {{ member.user.first_name|default:member.user.username }}님을 조직에서 제거하시겠습니까?">
            {% csrf_token %}
            <button type="submit"
                    class="px-3 py-1.5 text-[12px] font-medium text-red-500 border border-red-200 rounded-lg hover:bg-red-50 transition">
              제거
            </button>
          </form>
        {% endif %}
      </div>
    </div>
    {% empty %}
    <div class="p-8 text-center text-[14px] text-gray-400">
      멤버가 없습니다.
    </div>
    {% endfor %}
  </div>
</section>
```

- [ ] **Step 5: Create org_invites.html**

```html
{# accounts/templates/accounts/partials/org_invites.html #}
{% load static %}

{% if message %}
<div class="mb-4 p-3 bg-green-50 text-green-700 rounded-lg text-sm">{{ message }}</div>
{% endif %}

<!-- Create invite code form -->
<section class="bg-white rounded-lg border border-gray-100 p-5 mb-4">
  <h2 class="text-[15px] font-semibold text-gray-500 mb-4">새 초대코드 생성</h2>

  <form method="post"
        hx-post="{% url 'org_invite_create' %}"
        hx-target="#org-content">
    {% csrf_token %}

    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <div>
        <label for="id_role" class="block text-[13px] font-medium text-gray-600 mb-1">역할</label>
        {{ form.role }}
      </div>
      <div>
        <label for="id_max_uses" class="block text-[13px] font-medium text-gray-600 mb-1">최대 사용 횟수</label>
        {{ form.max_uses }}
      </div>
      <div>
        <label for="id_expires_at" class="block text-[13px] font-medium text-gray-600 mb-1">만료일 (선택)</label>
        {{ form.expires_at }}
      </div>
    </div>

    <div class="mt-4">
      <button type="submit"
              class="w-full sm:w-auto px-6 py-2.5 text-[14px] font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition">
        초대코드 생성
      </button>
    </div>
  </form>
</section>

<!-- Invite code list -->
<section class="bg-white rounded-lg border border-gray-100">
  <div class="p-5 border-b border-gray-100">
    <h2 class="text-[15px] font-semibold text-gray-500">초대코드 목록</h2>
  </div>

  <!-- Desktop table -->
  <div class="hidden sm:block overflow-x-auto">
    <table class="w-full">
      <thead>
        <tr class="text-left text-[12px] font-medium text-gray-500 border-b border-gray-100">
          <th class="px-5 py-3">코드</th>
          <th class="px-5 py-3">역할</th>
          <th class="px-5 py-3">사용/최대</th>
          <th class="px-5 py-3">만료일</th>
          <th class="px-5 py-3">상태</th>
          <th class="px-5 py-3">액션</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-50">
        {% for code in codes %}
        <tr>
          <td class="px-5 py-3 font-mono text-[14px] font-medium text-gray-900">{{ code.code }}</td>
          <td class="px-5 py-3 text-[13px] text-gray-600">{{ code.get_role_display }}</td>
          <td class="px-5 py-3 text-[13px] text-gray-600">{{ code.used_count }}/{{ code.max_uses }}</td>
          <td class="px-5 py-3 text-[13px] text-gray-600">
            {% if code.expires_at %}{{ code.expires_at|date:"Y-m-d" }}{% else %}-{% endif %}
          </td>
          <td class="px-5 py-3">
            {% if code.is_valid %}
              <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-green-50 text-green-700">
                <span class="w-1.5 h-1.5 rounded-full bg-green-500"></span>활성
              </span>
            {% elif not code.is_active %}
              <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-gray-100 text-gray-500">비활성</span>
            {% else %}
              <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700">소진/만료</span>
            {% endif %}
          </td>
          <td class="px-5 py-3">
            <div class="flex items-center gap-2">
              {% if code.is_active and code.is_valid %}
                <button onclick="navigator.clipboard.writeText('{{ code.code }}'); window.showToast('코드가 복사되었습니다')"
                        class="px-2.5 py-1 text-[12px] font-medium text-indigo-600 border border-indigo-200 rounded-lg hover:bg-indigo-50 transition">
                  복사
                </button>
                <form method="post"
                      hx-post="{% url 'org_invite_deactivate' code.pk %}"
                      hx-target="#org-content">
                  {% csrf_token %}
                  <button type="submit"
                          class="px-2.5 py-1 text-[12px] font-medium text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50 transition">
                    비활성화
                  </button>
                </form>
              {% endif %}
            </div>
          </td>
        </tr>
        {% empty %}
        <tr>
          <td colspan="6" class="px-5 py-8 text-center text-[14px] text-gray-400">
            생성된 초대코드가 없습니다.
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <!-- Mobile card list -->
  <div class="sm:hidden divide-y divide-gray-50">
    {% for code in codes %}
    <div class="p-4 space-y-2">
      <div class="flex items-center justify-between">
        <span class="font-mono text-[14px] font-medium text-gray-900">{{ code.code }}</span>
        {% if code.is_valid %}
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-green-50 text-green-700">활성</span>
        {% elif not code.is_active %}
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-gray-100 text-gray-500">비활성</span>
        {% else %}
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700">소진/만료</span>
        {% endif %}
      </div>
      <div class="text-[12px] text-gray-500">
        {{ code.get_role_display }} | {{ code.used_count }}/{{ code.max_uses }}
        {% if code.expires_at %} | {{ code.expires_at|date:"Y-m-d" }}{% endif %}
      </div>
      {% if code.is_active and code.is_valid %}
      <div class="flex gap-2 pt-1">
        <button onclick="navigator.clipboard.writeText('{{ code.code }}'); window.showToast('코드가 복사되었습니다')"
                class="px-3 py-1.5 text-[12px] font-medium text-indigo-600 border border-indigo-200 rounded-lg hover:bg-indigo-50 transition">
          복사
        </button>
        <form method="post"
              hx-post="{% url 'org_invite_deactivate' code.pk %}"
              hx-target="#org-content">
          {% csrf_token %}
          <button type="submit"
                  class="px-3 py-1.5 text-[12px] font-medium text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50 transition">
            비활성화
          </button>
        </form>
      </div>
      {% endif %}
    </div>
    {% empty %}
    <div class="p-8 text-center text-[14px] text-gray-400">
      생성된 초대코드가 없습니다.
    </div>
    {% endfor %}
  </div>
</section>
```

- [ ] **Step 6: Verify all org templates render**

Run: `uv run pytest tests/accounts/test_org_management.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add accounts/templates/accounts/org_base.html accounts/templates/accounts/partials/org_*.html
git commit -m "feat(accounts): add org management templates — info, members, invites tabs"
```
