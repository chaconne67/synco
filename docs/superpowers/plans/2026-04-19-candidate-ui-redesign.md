# Candidate UI Redesign (Phase D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** synco candidate 메인(list) / 상세(detail) 페이지 및 신규 후보자 추가 화면을 `assets/ui-sample/candidate-*.html` 목업 형태로 전환. 전역 레이아웃(사이드바·헤더)은 유지.

**Architecture:** 기존 Django + HTMX + Tailwind 스택 그대로. list/detail 템플릿 구조만 교체, 챗봇 FAB/모달은 list 페이지 하단 고정 검색바로 흡수. 신규 `candidate_create` 뷰·폼·템플릿 추가, Drive 업로드는 `data_extraction` 파이프라인에 queue. 음성 JS는 `chatbot.js`의 상태머신 로직을 참조해 `search_bar.js`로 새로 작성.

**Tech Stack:** Django 5.2, HTMX, Tailwind(Pretendard), Vanilla JS (MediaRecorder), pytest-django.

**Spec:** [docs/superpowers/specs/2026-04-19-candidate-ui-redesign-design.md](../specs/2026-04-19-candidate-ui-redesign-design.md)

---

## Scope Note

이 플랜은 단일 서브시스템(candidate UI)만 다루므로 분할 불필요. Phase C의 subagent-driven-development 패턴을 그대로 사용.

---

## File Structure

### 생성
- `candidates/templates/candidates/candidate_form.html` — Add Candidate 폼 페이지 (extends `common/base.html`)
- `candidates/templates/candidates/partials/candidate_card_v2.html` — 새 카드 파셜 (기존 `candidate_card.html` 대체)
- `candidates/templates/candidates/partials/search_bar_fixed.html` — 하단 고정 검색바 (idle/text/recording/processing 상태 DOM)
- `candidates/static/candidates/search_bar.js` — 하단 검색바 상태머신 + MediaRecorder + 전송 로직
- `candidates/templatetags/__init__.py` (없으면), `candidates/templatetags/candidate_ui.py` — `language_level_bars`, `review_notice_pill` 등 템플릿 헬퍼
- `candidates/services/candidate_create.py` — Candidate 생성 서비스 (identity matching + Resume 연결)
- `candidates/tests/test_candidate_create.py` — 생성 뷰 테스트
- `candidates/tests/test_ui_helpers.py` — `language_level_bars` 룰 테스트
- `candidates/tests/test_candidate_list_ui.py` — 리스트 렌더 스모크 테스트
- `candidates/tests/test_candidate_detail_ui.py` — 디테일 렌더 스모크 테스트

### 수정
- `tailwind.config.js` — `shadow-searchbar` 추가
- `templates/common/base.html` 또는 전역 CSS — `.eyebrow` / `.tnum` 유틸 추가 (기존 `extra_head` block 활용)
- `candidates/templates/candidates/search.html` — 헤더/칩/카드그리드/하단바 구조 교체
- `candidates/templates/candidates/partials/candidate_list.html` — `candidate_card_v2.html` 사용으로 교체
- `candidates/templates/candidates/partials/candidate_list_page.html` — 동일
- `candidates/templates/candidates/detail.html` — 컨테이너 padding/max-width 조정 (목업 기준)
- `candidates/templates/candidates/partials/candidate_detail_content.html` — 본문 구조 전면 교체
- `candidates/views.py` — `candidate_list`에 `category_counts` 추가, `candidate_create` view 신규
- `candidates/urls.py` — `/candidates/new/` 추가
- `candidates/models.py` — `Category.candidate_count` auto-update signal (없는 경우만 추가)

### 삭제
- `candidates/templates/candidates/partials/chatbot_fab.html`
- `candidates/templates/candidates/partials/chatbot_modal.html`
- `candidates/templates/candidates/partials/chat_messages.html`
- `candidates/static/candidates/chatbot.js`
- `candidates/templates/candidates/partials/search_status_bar.html` (검색 상태 텍스트는 header inline으로 흡수)

---

## Testing Strategy

- **TDD 대상**: `language_level_bars` 헬퍼, `candidate_create` 뷰 (identity matching / 중복감지 / 파일업로드), `Category.candidate_count` signal
- **Smoke 테스트**: list / detail / new 뷰가 200 반환하고 주요 텍스트(카드 이름, 섹션 헤더)를 포함하는지
- **수동 확인 (UI/JS)**: 카드 스타일, 하단 검색바 상태 전환, 음성 녹음·STT, 카테고리 칩 가로스크롤 — 브라우저에서 확인. 사용자는 `/dev.sh` 후 수정한 URL을 리포트

---

## Task 1: Tailwind 토큰·유틸 추가

목업의 `shadow-searchbar`, `.eyebrow`, `.tnum`을 실제 tailwind config / 글로벌 CSS에 추가. `.eyebrow` / `.tnum` 은 tailwind 유틸이 아닌 component class이므로 `static/css/` 또는 `base.html` `<style>`에 둔다.

**Files:**
- Modify: `tailwind.config.js:60-64`
- Modify: `templates/common/base.html` (`{% block extra_head %}` 전 `<style>` 섹션)

- [ ] **Step 1: `shadow-searchbar` 토큰 추가**

Edit `tailwind.config.js` — `boxShadow` 블록을 아래로 교체:

```javascript
      boxShadow: {
        'card': '0 1px 2px 0 rgba(15,23,42,0.04), 0 1px 3px 0 rgba(15,23,42,0.06)',
        'lift': '0 4px 6px -1px rgba(15,23,42,0.08), 0 2px 4px -2px rgba(15,23,42,0.04)',
        'fab':  '0 10px 15px -3px rgba(15,23,42,0.15), 0 4px 6px -2px rgba(15,23,42,0.08)',
        'searchbar': '0 10px 40px -10px rgba(15,23,42,0.18), 0 4px 12px -4px rgba(15,23,42,0.08)',
      },
```

- [ ] **Step 2: `.eyebrow` / `.tnum` 유틸 추가**

`templates/common/base.html`을 읽고 `<head>` 하단 또는 `extra_head` 직전 `<style>`에 아래 규칙을 추가 (이미 있는 `<style>` 블록이 있으면 그 안에 append):

```html
<style>
  .eyebrow { font-size: 10px; line-height: 1; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; color: #64748B; }
  .tnum { font-variant-numeric: tabular-nums; }
</style>
```

- [ ] **Step 3: 수동 확인**

`npm run build:css` 또는 `./dev.sh`로 tailwind watch 재빌드. 임시 템플릿에서 `<div class="shadow-searchbar eyebrow tnum">test</div>` 렌더가 깨지지 않는지 확인 (실제 테스트는 Task 4/5에서 자연스럽게).

- [ ] **Step 4: Commit**

```bash
git add tailwind.config.js templates/common/base.html
git commit -m "feat(ui): add shadow-searchbar token and eyebrow/tnum utilities"
```

---

## Task 2: `Category.candidate_count` auto-update signal

목업 칩이 `카테고리 · 524` 형식으로 count를 노출해야 함. 현재 `candidate_count` 필드는 존재하지만 자동 갱신 여부 확인 후 미구현이면 signal 추가.

**Files:**
- Modify: `candidates/models.py` (맨 아래 signal 섹션)
- Create: `candidates/tests/test_category_count.py`

- [ ] **Step 1: 현재 상태 확인**

```bash
grep -n "candidate_count" candidates/models.py candidates/signals.py 2>/dev/null
```
Expected: signal이나 `save` 오버라이드가 없으면 진행. 있으면 Task 전체 SKIP.

- [ ] **Step 2: 실패 테스트 작성**

Create `candidates/tests/test_category_count.py`:

```python
import pytest
from candidates.models import Candidate, Category


@pytest.mark.django_db
def test_candidate_count_auto_increments_on_category_add():
    cat = Category.objects.create(name="Tech")
    assert cat.candidate_count == 0

    c = Candidate.objects.create(name="홍길동")
    c.categories.add(cat)

    cat.refresh_from_db()
    assert cat.candidate_count == 1


@pytest.mark.django_db
def test_candidate_count_decrements_on_category_remove():
    cat = Category.objects.create(name="Tech")
    c = Candidate.objects.create(name="홍길동")
    c.categories.add(cat)
    c.categories.remove(cat)

    cat.refresh_from_db()
    assert cat.candidate_count == 0


@pytest.mark.django_db
def test_candidate_count_decrements_on_candidate_delete():
    cat = Category.objects.create(name="Tech")
    c = Candidate.objects.create(name="홍길동")
    c.categories.add(cat)
    c.delete()

    cat.refresh_from_db()
    assert cat.candidate_count == 0
```

- [ ] **Step 3: 테스트 실패 확인**

```bash
uv run pytest candidates/tests/test_category_count.py -v
```
Expected: FAIL (candidate_count가 0으로 남아있음).

- [ ] **Step 4: signal 구현**

`candidates/models.py` 맨 아래에 추가:

```python
from django.db.models.signals import m2m_changed, post_delete
from django.dispatch import receiver


@receiver(m2m_changed, sender=Candidate.categories.through)
def _sync_category_candidate_count(sender, instance, action, reverse, pk_set, **kwargs):
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    from django.db.models import Count

    if action == "post_clear":
        Category.objects.filter(candidates=instance).update(
            candidate_count=Count("candidates")
        )
        return

    cat_ids = pk_set or []
    for cat_id in cat_ids:
        Category.objects.filter(pk=cat_id).update(
            candidate_count=Count("candidates")
        )


@receiver(post_delete, sender=Candidate)
def _refresh_category_counts_on_candidate_delete(sender, instance, **kwargs):
    from django.db.models import Count

    Category.objects.filter(candidate_count__gt=0).annotate(
        real=Count("candidates")
    ).update(candidate_count=F("real")) if False else None
    # Simpler: recompute counts for affected categories
    for cat in Category.objects.filter(candidate_count__gt=0):
        cat.candidate_count = cat.candidates.count()
        cat.save(update_fields=["candidate_count"])
```

**주의**: `Count("candidates")` 서브쿼리 접근 방식은 DB에 따라 지원 안 될 수 있음. 실패하면 아래처럼 단순 재계산으로 교체:

```python
@receiver(m2m_changed, sender=Candidate.categories.through)
def _sync_category_candidate_count(sender, instance, action, pk_set, **kwargs):
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    affected = list(pk_set) if pk_set else list(Category.objects.values_list("pk", flat=True))
    for cat_id in affected:
        cat = Category.objects.filter(pk=cat_id).first()
        if cat:
            cat.candidate_count = cat.candidates.count()
            cat.save(update_fields=["candidate_count"])
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
uv run pytest candidates/tests/test_category_count.py -v
```
Expected: 3 passed.

- [ ] **Step 6: 기존 데이터 backfill 관리명령 (선택)**

Create `candidates/management/commands/backfill_category_count.py`:

```python
from django.core.management.base import BaseCommand
from candidates.models import Category


class Command(BaseCommand):
    help = "Recompute Category.candidate_count for all categories."

    def handle(self, *args, **options):
        updated = 0
        for cat in Category.objects.all():
            real = cat.candidates.count()
            if cat.candidate_count != real:
                cat.candidate_count = real
                cat.save(update_fields=["candidate_count"])
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Updated {updated} categories."))
```

- [ ] **Step 7: Commit**

```bash
git add candidates/models.py candidates/tests/test_category_count.py candidates/management/commands/backfill_category_count.py
git commit -m "feat(candidates): auto-sync Category.candidate_count via m2m signal"
```

---

## Task 3: Template helper — `language_level_bars` + `review_notice_pill`

spec §3.8 의 룰 기반 4-dot 매핑과 §2.2의 review-notice pill 헬퍼.

**Files:**
- Create: `candidates/templatetags/__init__.py` (빈 파일)
- Create: `candidates/templatetags/candidate_ui.py`
- Create: `candidates/tests/test_ui_helpers.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `candidates/tests/test_ui_helpers.py`:

```python
import pytest
from types import SimpleNamespace
from candidates.templatetags.candidate_ui import language_level_bars, review_notice_pill


def _lang(level="", test_name="", score=""):
    return SimpleNamespace(level=level, test_name=test_name, score=score)


def test_language_level_bars_native():
    assert language_level_bars(_lang(level="Native")) == 4
    assert language_level_bars(_lang(level="원어민")) == 4


def test_language_level_bars_business():
    assert language_level_bars(_lang(level="Business")) == 3
    assert language_level_bars(_lang(level="고급")) == 3


def test_language_level_bars_intermediate():
    assert language_level_bars(_lang(level="중급")) == 2
    assert language_level_bars(_lang(test_name="TOEIC", score="750")) == 2  # default


def test_language_level_bars_basic():
    assert language_level_bars(_lang(level="Basic")) == 1
    assert language_level_bars(_lang(level="초급")) == 1


def test_language_level_bars_empty_returns_default_2():
    assert language_level_bars(_lang()) == 2


def test_review_notice_pill_red_highest():
    c = SimpleNamespace(review_notice_red_count=2, review_notice_yellow_count=5, review_notice_blue_count=1)
    pill = review_notice_pill(c)
    assert pill["severity"] == "red"
    assert pill["count"] == 2
    assert "중요" in pill["label"]


def test_review_notice_pill_yellow_when_no_red():
    c = SimpleNamespace(review_notice_red_count=0, review_notice_yellow_count=3, review_notice_blue_count=1)
    pill = review_notice_pill(c)
    assert pill["severity"] == "yellow"
    assert pill["count"] == 3


def test_review_notice_pill_none_when_all_zero():
    c = SimpleNamespace(review_notice_red_count=0, review_notice_yellow_count=0, review_notice_blue_count=0)
    assert review_notice_pill(c) is None
```

- [ ] **Step 2: 실패 확인**

```bash
uv run pytest candidates/tests/test_ui_helpers.py -v
```
Expected: FAIL (module not found).

- [ ] **Step 3: 헬퍼 구현**

Create `candidates/templatetags/__init__.py` (빈 파일).

Create `candidates/templatetags/candidate_ui.py`:

```python
from django import template

register = template.Library()


_LEVEL_MAP_4 = {"native", "원어민", "모국어", "상", "a"}
_LEVEL_MAP_3 = {"business", "fluent", "advanced", "고급", "중상", "b"}
_LEVEL_MAP_2 = {"conversational", "intermediate", "중급", "중", "c"}
_LEVEL_MAP_1 = {"basic", "beginner", "초급", "하", "d"}


@register.simple_tag
def language_level_bars(lang) -> int:
    """Return 1-4 for UI dot bar."""
    level = (getattr(lang, "level", "") or "").strip().lower()
    test = (getattr(lang, "test_name", "") or "").strip().lower()
    score = (getattr(lang, "score", "") or "").strip().lower()
    blob = f"{level} {test} {score}"
    if any(k in blob for k in _LEVEL_MAP_4):
        return 4
    if any(k in blob for k in _LEVEL_MAP_3):
        return 3
    if any(k in blob for k in _LEVEL_MAP_2):
        return 2
    if any(k in blob for k in _LEVEL_MAP_1):
        return 1
    return 2  # default when info is missing


@register.simple_tag
def review_notice_pill(candidate):
    """Return pill dict {severity, count, label, classes} or None if no notices."""
    red = getattr(candidate, "review_notice_red_count", 0) or 0
    yellow = getattr(candidate, "review_notice_yellow_count", 0) or 0
    blue = getattr(candidate, "review_notice_blue_count", 0) or 0
    if red:
        return {
            "severity": "red",
            "count": red,
            "label": f"중요 {red}건",
            "classes": "text-rose-700 bg-rose-50 border-rose-100",
        }
    if yellow:
        return {
            "severity": "yellow",
            "count": yellow,
            "label": f"주의 {yellow}건",
            "classes": "text-amber-700 bg-amber-50 border-amber-100",
        }
    if blue:
        return {
            "severity": "blue",
            "count": blue,
            "label": f"참고 {blue}건",
            "classes": "text-slate-600 bg-slate-50 border-slate-100",
        }
    return None
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest candidates/tests/test_ui_helpers.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add candidates/templatetags/ candidates/tests/test_ui_helpers.py
git commit -m "feat(candidates): add candidate_ui templatetag helpers"
```

---

## Task 4: Candidate Card v2

목업의 카드 구조로 새 파셜 작성. skeleton avatar + 이름 + review-notice pill + 현 회사/직책 + 경력 배지 + 카테고리 + 스킬 + 요약 + 메타 한 줄.

**Files:**
- Create: `candidates/templates/candidates/partials/candidate_card_v2.html`
- Modify: `candidates/templates/candidates/partials/candidate_list.html`
- Modify: `candidates/templates/candidates/partials/candidate_list_page.html`

- [ ] **Step 1: 카드 파셜 작성**

Create `candidates/templates/candidates/partials/candidate_card_v2.html`:

```html
{% load candidate_ui %}
{% load candidate_extras %}
{% review_notice_pill candidate as notice %}

<div class="flex flex-col gap-1.5">
<a href="/candidates/{{ candidate.pk }}/"
   hx-get="/candidates/{{ candidate.pk }}/"
   hx-target="#main-content"
   hx-push-url="true"
   class="group block bg-white rounded-card border border-hair shadow-card hover:shadow-lift hover:-translate-y-0.5 transition-all duration-200 p-5">
  <div class="flex items-start gap-4">
    <!-- Skeleton avatar -->
    <div class="shrink-0 w-14 h-14 rounded-full bg-line flex items-center justify-center">
      <svg class="w-7 h-7 text-faint" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
              d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
      </svg>
    </div>
    <div class="min-w-0 flex-1">
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <h4 class="text-base font-bold text-ink truncate group-hover:text-ink3 transition-colors flex items-center gap-2">
            {{ candidate.name }}
            {% include "candidates/partials/_recommendation_badge.html" %}
          </h4>
          <p class="text-xs text-muted mt-1 truncate">
            {% if candidate.birth_year %}
              {{ current_year|default:2026|add:"-"|add:candidate.birth_year|stringformat:"d" }}세 · {{ candidate.birth_year }}년생
            {% endif %}
          </p>
        </div>
        {% if notice %}
        <span class="eyebrow shrink-0 border rounded-full px-2 py-0.5 {{ notice.classes }}">
          {{ notice.label }}
        </span>
        {% endif %}
      </div>
      <p class="text-sm text-ink2 mt-2 truncate">
        {% if candidate.current_company %}
          <span class="font-semibold">{{ candidate.current_company }}</span>{% if candidate.current_position %}<span class="mx-1 text-faint">·</span>{{ candidate.current_position }}{% endif %}
        {% elif candidate.current_position %}
          {{ candidate.current_position }}
        {% else %}
          <span class="text-faint">정보 없음</span>
        {% endif %}
      </p>

      <!-- Tags row -->
      <div class="flex items-center gap-1.5 mt-3 flex-wrap">
        {% if candidate.total_experience_display %}
        <span class="eyebrow text-ink3 bg-ink3/10 border border-ink3/20 px-2 py-1 rounded-full">
          {{ candidate.total_experience_display }}
        </span>
        {% endif %}
        {% if candidate.primary_category %}
        <span class="text-xs font-bold text-ink2 bg-line border border-hair px-2 py-1 rounded-lg">
          {{ candidate.primary_category.name_ko|default:candidate.primary_category.name }}
        </span>
        {% endif %}
        {% for skill in candidate.skills|slice:":3" %}
        <span class="text-xs font-medium text-muted bg-line border border-hair px-2 py-1 rounded-lg">
          {% if skill.name %}{{ skill.name }}{% else %}{{ skill }}{% endif %}
        </span>
        {% endfor %}
      </div>

      <!-- Summary -->
      {% if candidate.summary %}
      <p class="text-sm text-muted mt-3 leading-relaxed line-clamp-2">{{ candidate.summary }}</p>
      {% endif %}

      <!-- Meta footer -->
      <div class="flex items-center gap-2 mt-3 text-xs text-faint flex-wrap">
        {% if candidate.address %}<span>{{ candidate.address|truncatewords:1 }}</span>{% endif %}
        {% for edu in candidate.educations.all|slice:":1" %}<span>·</span><span>{{ edu.institution }}</span>{% endfor %}
        {% for career in candidate.careers.all|slice:":1" %}{% if not career.is_current %}<span>·</span><span>전 {{ career.company }}</span>{% endif %}{% endfor %}
      </div>
    </div>
  </div>
</a>

{% if target_project %}
<form method="post"
      action="{% url 'projects:project_add_candidate' target_project.pk %}"
      class="flex">
  {% csrf_token %}
  <input type="hidden" name="candidate_id" value="{{ candidate.pk }}">
  <button type="submit"
          class="inline-flex items-center px-3 h-8 rounded-lg border border-hair text-xs font-semibold text-muted bg-white hover:bg-ink3 hover:text-white hover:border-ink3 transition-colors">
    프로젝트에 추가
  </button>
</form>
{% endif %}
</div>
```

**주의**: 생년 계산 필터링은 Django 템플릿에서 안정적이지 않음. 실제로는 `candidate` 객체에 계산된 프로퍼티를 읽는 편이 낫다. 현재 모델에 없으면 모델에 `@property def age_display(self)` 추가 또는 view에서 annotate. 이번 Task 내에서는 모델에 헬퍼 프로퍼티 추가:

Edit `candidates/models.py` — `Candidate` 클래스 안 적절한 위치(`total_experience_display` 근처)에 추가:

```python
    @property
    def age_display(self) -> str:
        if not self.birth_year:
            return ""
        from datetime import date
        age = date.today().year - self.birth_year
        return f"{age}세 · {self.birth_year}년생"
```

그리고 카드 템플릿에서 `{{ candidate.birth_year }}` 표시 부분을 아래로 교체:

```html
          <p class="text-xs text-muted mt-1 truncate">{{ candidate.age_display }}</p>
```

- [ ] **Step 2: 리스트 파셜에서 새 카드로 교체**

Edit `candidates/templates/candidates/partials/candidate_list.html` — 기존 `candidate_card.html` include를 `candidate_card_v2.html`로 교체. 래퍼가 기존에 `grid grid-cols-1 md:grid-cols-2 gap-4` 같은 형식이면 유지, 아니면 아래로 설정:

```html
<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
  {% for candidate in candidates %}
    {% include "candidates/partials/candidate_card_v2.html" %}
  {% endfor %}
</div>
```

(기존 무한스크롤 센티넬 / "빈 상태" 블록은 그대로 유지)

Edit `candidates/templates/candidates/partials/candidate_list_page.html` — 동일하게 include 경로만 `candidate_card_v2.html`로 교체.

- [ ] **Step 3: 리스트 뷰 200 반환 스모크 테스트**

Create `candidates/tests/test_candidate_list_ui.py`:

```python
import pytest
from django.contrib.auth import get_user_model
from candidates.models import Candidate, Category


@pytest.fixture
def auth_client(client, db):
    User = get_user_model()
    u = User.objects.create_user(email="t@example.com", password="x")
    client.force_login(u)
    return client


@pytest.mark.django_db
def test_list_page_renders_card_v2(auth_client):
    Candidate.objects.create(name="김철수", current_company="네이버")
    resp = auth_client.get("/candidates/")
    assert resp.status_code == 200
    assert b"\xea\xb9\x80\xec\xb2\xa0\xec\x88\x98" in resp.content  # 김철수 UTF-8
    assert b"bg-white rounded-card" in resp.content or b"bg-white" in resp.content
```

**주의**: 프로젝트의 `User` 모델이 이메일 기반인지 확인. 안 그러면 `force_login`으로 fixture 조정. 기존 테스트의 로그인 헬퍼가 있으면 그거 사용.

```bash
uv run pytest candidates/tests/test_candidate_list_ui.py -v
```
Expected: PASS.

- [ ] **Step 4: 브라우저 수동 확인**

`./dev.sh` 실행 후 `http://localhost:8000/candidates/` 열어 카드 렌더링 확인. URL 리포트.

- [ ] **Step 5: Commit**

```bash
git add candidates/templates/candidates/partials/candidate_card_v2.html candidates/templates/candidates/partials/candidate_list.html candidates/templates/candidates/partials/candidate_list_page.html candidates/models.py candidates/tests/test_candidate_list_ui.py
git commit -m "feat(candidates): card v2 layout matching mockup"
```

---

## Task 5: List 페이지 헤더·카테고리 칩 개편

목업의 "Global Talent Pool / Candidates" 헤더 + "Add Candidate" 버튼 + count 있는 카테고리 칩.

**Files:**
- Modify: `candidates/views.py:305-446` (`candidate_list`)
- Modify: `candidates/templates/candidates/search.html`

- [ ] **Step 1: view에서 categories에 count 포함**

Edit `candidates/views.py:314` — `categories = Category.objects.all()`을 아래로 교체:

```python
    categories = Category.objects.order_by("-candidate_count", "name")
    total_candidates = Candidate.objects.count()
```

context에 `total_candidates` 추가 (render 호출부 딕셔너리에 키 추가).

- [ ] **Step 2: 헤더 + 칩 구조 교체**

Edit `candidates/templates/candidates/search.html` — `<!-- Page header -->` ~ `<!-- Category tabs card -->` 영역을 아래로 교체:

```html
    <!-- Page header -->
    <header class="mb-8 flex items-start justify-between gap-4 flex-wrap">
      <div>
        <span class="eyebrow text-ink3 block">Global Talent Pool</span>
        <h2 class="text-4xl font-black text-ink tracking-tight mt-2">Candidates</h2>
        <p class="text-sm text-muted mt-2">
          등록된 후보자 <strong class="text-ink font-bold tnum">{{ total_candidates }}명</strong>을 검색하고 검수하세요
        </p>
      </div>
      <a href="{% url 'candidates:candidate_create' %}"
         hx-get="{% url 'candidates:candidate_create' %}"
         hx-target="#main-content"
         hx-push-url="true"
         class="inline-flex items-center gap-2 rounded-xl bg-ink3 hover:bg-ink2 text-white text-xs font-bold uppercase tracking-widest px-5 py-3 shadow-lift hover:scale-[1.01] active:scale-[0.99] transition-all">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.4" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4"/></svg>
        Add Candidate
      </a>
    </header>

    <!-- Category chips (horizontal scroll) -->
    <div class="bg-white border border-hair rounded-card shadow-card p-1.5 mb-6 relative tab-scroll-container">
      <div class="tab-scroll-fade-left" id="tab-fade-left"></div>
      <div class="tab-scroll-fade-right visible" id="tab-fade-right"></div>
      <button class="tab-scroll-arrow tab-scroll-arrow-left" id="tab-arrow-left" onclick="document.getElementById('tab-scroller').scrollBy({left:-150,behavior:'smooth'})" aria-label="이전 카테고리">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.4" d="M15 19l-7-7 7-7"/></svg>
      </button>
      <button class="tab-scroll-arrow tab-scroll-arrow-right visible" id="tab-arrow-right" onclick="document.getElementById('tab-scroller').scrollBy({left:150,behavior:'smooth'})" aria-label="다음 카테고리">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.4" d="M9 5l7 7-7 7"/></svg>
      </button>
      <div id="tab-scroller" class="overflow-x-auto hide-scrollbar">
        <div class="flex gap-1 whitespace-nowrap">
          <a href="/candidates/{% if target_project %}?project={{ target_project.pk }}{% endif %}"
             hx-get="/candidates/{% if target_project %}?project={{ target_project.pk }}{% endif %}"
             hx-target="#main-content"
             hx-push-url="true"
             class="flex-shrink-0 inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-semibold transition
                    {% if not active_category %}bg-ink3 text-white shadow-sm{% else %}text-muted hover:bg-line{% endif %}">
            전체 <span class="tnum opacity-75">· {{ total_candidates }}</span>
          </a>
          {% for cat in categories %}
          <a href="/candidates/?category={{ cat.name }}{% if target_project %}&project={{ target_project.pk }}{% endif %}"
             hx-get="/candidates/?category={{ cat.name }}{% if target_project %}&project={{ target_project.pk }}{% endif %}"
             hx-target="#main-content"
             hx-push-url="true"
             class="flex-shrink-0 inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-semibold transition
                    {% if active_category == cat.name %}bg-ink3 text-white shadow-sm{% else %}text-muted hover:bg-line{% endif %}">
            {{ cat.name_ko|default:cat.name }} <span class="tnum opacity-75">· {{ cat.candidate_count }}</span>
          </a>
          {% endfor %}
        </div>
      </div>
    </div>
```

- [ ] **Step 3: 기존 `search_status_bar` include 제거**

Edit `candidates/templates/candidates/search.html` — `#search-status-bar` 블록 전체 삭제 (검색 상태 표시는 헤더 텍스트로 이미 충분). `#search-area` 와 `#candidate-list`는 유지.

- [ ] **Step 4: Add Candidate URL reverse-resolvable 확인**

현재 Task 7에서 `candidates:candidate_create` URL이 추가되지만 템플릿에서 먼저 참조되므로 render 오류 가능. 임시로 `{% url 'candidates:candidate_create' %}` 대신 `/candidates/new/` 하드코딩으로 두고, Task 7에서 url 이름 추가 후 교체.

실제 교체 내용: `{% url 'candidates:candidate_create' %}` → `/candidates/new/`

- [ ] **Step 5: 스모크 테스트 / 수동 확인**

```bash
uv run pytest candidates/tests/test_candidate_list_ui.py -v
```
기존 스모크 테스트 재통과. 실패하면 `target_project` / context 누락 여부 확인.

브라우저에서 `/candidates/` 재확인 — 헤더·칩 새 스타일 렌더.

- [ ] **Step 6: Commit**

```bash
git add candidates/views.py candidates/templates/candidates/search.html
git commit -m "feat(candidates): list page header + category chips with count"
```

---

## Task 6: 하단 고정 검색바 파셜 + JS

챗봇 FAB/모달을 대체하는 하단 고정 바. 상태머신(idle/text/recording/processing).

**Files:**
- Create: `candidates/templates/candidates/partials/search_bar_fixed.html`
- Create: `candidates/static/candidates/search_bar.js`
- Modify: `candidates/templates/candidates/search.html` (하단에 include + script)

- [ ] **Step 1: 파셜 작성**

Create `candidates/templates/candidates/partials/search_bar_fixed.html`:

```html
{# Fixed bottom search bar — voice-first with text fallback. #}
<div id="search-bar-wrapper"
     class="fixed bottom-0 left-0 right-0 lg:left-64 z-30 pointer-events-none px-4 pb-6 pt-8
            bg-gradient-to-t from-canvas via-canvas/90 to-transparent">
  <div class="pointer-events-auto mx-auto max-w-3xl bg-white border border-hair rounded-full shadow-searchbar flex items-center gap-2 px-4 py-2.5">

    <!-- Search icon (left) -->
    <svg class="w-5 h-5 text-faint shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
    </svg>

    <!-- Idle + Text input area -->
    <input id="sb-input"
           type="text"
           placeholder="후보자 이름, 회사, 직군 검색 — 또는 마이크로 말해보세요"
           class="flex-1 bg-transparent outline-none text-sm text-ink placeholder:text-faint font-medium"
           autocomplete="off">

    <!-- Recording waveform (hidden by default) -->
    <div id="sb-recording" class="hidden flex-1 items-center gap-1.5 px-2">
      <span class="w-2 h-2 bg-rose-500 rounded-full animate-pulse shrink-0"></span>
      <div class="flex-1 h-8 flex items-center gap-[2px]" id="sb-waveform">
        {% for i in "0123456789012345678901234" %}<div class="sb-bar"></div>{% endfor %}
      </div>
      <span id="sb-timer" class="text-xs font-mono text-rose-500 tnum shrink-0">00:00</span>
    </div>

    <!-- Processing spinner (hidden by default) -->
    <div id="sb-processing" class="hidden flex-1 items-center gap-2 px-2">
      <div class="w-4 h-4 border-2 border-line border-t-ink3 rounded-full animate-spin"></div>
      <span class="eyebrow text-muted">음성 인식 중…</span>
    </div>

    <!-- Action button (right) — swaps between mic / send / stop -->
    <button id="sb-mic-btn" type="button"
            class="w-10 h-10 rounded-full bg-ink3 hover:bg-ink2 text-white flex items-center justify-center shrink-0 transition-colors"
            aria-label="마이크로 검색">
      <i class="fa-solid fa-microphone"></i>
    </button>
    <button id="sb-send-btn" type="button"
            class="hidden w-10 h-10 rounded-full bg-ink3 hover:bg-ink2 text-white flex items-center justify-center shrink-0 transition-colors"
            aria-label="검색 전송">
      <i class="fa-solid fa-arrow-up"></i>
    </button>
    <button id="sb-stop-btn" type="button"
            class="hidden w-10 h-10 rounded-full bg-rose-500 hover:bg-rose-600 text-white flex items-center justify-center shrink-0 transition-colors animate-pulse"
            aria-label="녹음 정지">
      <i class="fa-solid fa-stop"></i>
    </button>
  </div>
</div>

<style>
  .sb-bar { flex: 1; min-width: 2px; max-width: 3px; height: 4px; background: #F43F5E; border-radius: 9999px; transition: height 0.06s ease-out; }
</style>

<script>
  window.SEARCH_URL = "{% url 'candidates:search_chat' %}";
  window.VOICE_URL = "{% url 'candidates:voice_transcribe' %}";
  window.CSRF_TOKEN = "{{ csrf_token }}";
</script>
<script src="{% static 'candidates/search_bar.js' %}" defer></script>
```

- [ ] **Step 2: JS 파일 작성 — `chatbot.js` 레퍼런스**

참조: `candidates/static/candidates/chatbot.js` 의 MediaRecorder, recording, STT 호출, 전송 로직.

Create `candidates/static/candidates/search_bar.js`:

```javascript
(function () {
  'use strict';

  const el = (id) => document.getElementById(id);
  const input = el('sb-input');
  const micBtn = el('sb-mic-btn');
  const sendBtn = el('sb-send-btn');
  const stopBtn = el('sb-stop-btn');
  const recWrap = el('sb-recording');
  const procWrap = el('sb-processing');
  const timerEl = el('sb-timer');
  const bars = document.querySelectorAll('.sb-bar');

  if (!input) return;

  let mediaRecorder = null;
  let audioChunks = [];
  let recordStart = 0;
  let timerId = null;
  let analyser = null;
  let animId = null;

  // -- State transitions --
  function setState(s) {
    // idle | text | recording | processing
    input.classList.toggle('hidden', s === 'recording' || s === 'processing');
    recWrap.classList.toggle('hidden', s !== 'recording');
    recWrap.classList.toggle('flex', s === 'recording');
    procWrap.classList.toggle('hidden', s !== 'processing');
    procWrap.classList.toggle('flex', s === 'processing');
    micBtn.classList.toggle('hidden', s !== 'idle');
    sendBtn.classList.toggle('hidden', s !== 'text');
    stopBtn.classList.toggle('hidden', s !== 'recording');
  }

  // Idle → Text when user types
  input.addEventListener('focus', () => { if (input.value.trim()) setState('text'); });
  input.addEventListener('input', () => setState(input.value.trim() ? 'text' : 'idle'));
  input.addEventListener('blur', () => { if (!input.value.trim()) setState('idle'); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); sendQuery(); }
    if (e.key === 'Escape') { input.value = ''; input.blur(); setState('idle'); }
  });

  sendBtn.addEventListener('click', sendQuery);
  micBtn.addEventListener('click', startRecording);
  stopBtn.addEventListener('click', stopRecording);

  // -- Send text query --
  async function sendQuery() {
    const q = input.value.trim();
    if (!q) return;
    const fd = new FormData();
    fd.append('message', q);
    fd.append('csrfmiddlewaretoken', window.CSRF_TOKEN);
    try {
      const resp = await fetch(window.SEARCH_URL, {
        method: 'POST',
        body: fd,
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!resp.ok) { console.error('search failed', resp.status); return; }
      const data = await resp.json();
      if (data.redirect_url) {
        // Reuse existing HTMX flow: fetch list and swap #candidate-list
        htmx.ajax('GET', data.redirect_url, { target: '#candidate-list', swap: 'innerHTML' });
      }
    } catch (err) { console.error(err); }
  }

  // -- Recording --
  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
      mediaRecorder = new MediaRecorder(stream, { mimeType: mime });
      audioChunks = [];
      mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
      mediaRecorder.onstop = onRecordingStopped;
      mediaRecorder.start();
      recordStart = Date.now();
      setState('recording');
      startTimer();
      startWaveform(stream);
      // Auto-stop at 60s
      setTimeout(() => { if (mediaRecorder && mediaRecorder.state === 'recording') stopRecording(); }, 60000);
    } catch (err) {
      console.error('mic denied', err);
      alert('마이크 권한이 필요합니다.');
    }
  }

  function stopRecording() {
    if (!mediaRecorder) return;
    const elapsed = Date.now() - recordStart;
    if (elapsed < 500) {
      // Too short
      mediaRecorder.stop();
      mediaRecorder.stream.getTracks().forEach(t => t.stop());
      cleanupRecording();
      setState('idle');
      return;
    }
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(t => t.stop());
    setState('processing');
  }

  function startTimer() {
    timerId = setInterval(() => {
      const sec = Math.floor((Date.now() - recordStart) / 1000);
      const mm = String(Math.floor(sec / 60)).padStart(2, '0');
      const ss = String(sec % 60).padStart(2, '0');
      timerEl.textContent = `${mm}:${ss}`;
    }, 200);
  }

  function startWaveform(stream) {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const src = ctx.createMediaStreamSource(stream);
      analyser = ctx.createAnalyser();
      analyser.fftSize = 64;
      src.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      function tick() {
        analyser.getByteFrequencyData(data);
        bars.forEach((b, i) => {
          const v = data[i % data.length] / 255;
          b.style.height = Math.max(4, v * 24) + 'px';
        });
        animId = requestAnimationFrame(tick);
      }
      tick();
    } catch (e) { /* ignore */ }
  }

  function cleanupRecording() {
    if (timerId) { clearInterval(timerId); timerId = null; }
    if (animId) { cancelAnimationFrame(animId); animId = null; }
    timerEl.textContent = '00:00';
  }

  async function onRecordingStopped() {
    cleanupRecording();
    const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
    const fd = new FormData();
    fd.append('audio', blob, 'recording.webm');
    fd.append('csrfmiddlewaretoken', window.CSRF_TOKEN);
    try {
      const resp = await fetch(window.VOICE_URL, {
        method: 'POST',
        body: fd,
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!resp.ok) {
        console.error('voice fail', resp.status);
        setState('idle');
        return;
      }
      const data = await resp.json();
      if (data.transcript) {
        input.value = data.transcript;
        setState('text');
        await sendQuery();
      } else {
        setState('idle');
      }
    } catch (err) {
      console.error(err);
      setState('idle');
    }
  }
})();
```

**주의**: `chatbot.js`의 실제 search_chat 응답 형식을 확인해 `data.redirect_url` 또는 `data.filters` 기반 리스트 swap으로 맞춘다. 실제 응답 형식은 `candidates/views.py` `search_chat` 함수에서 확인:

```bash
grep -n "JsonResponse\|redirect_url\|session_id" candidates/views.py | head -20
```
형식이 다르면 `sendQuery`의 응답 핸들링을 그에 맞게 수정.

- [ ] **Step 3: search.html에 include + FAB/모달 제거**

Edit `candidates/templates/candidates/search.html`:
- `{% include "candidates/partials/chatbot_fab.html" %}` 있으면 삭제 (base.html에 있을 수 있음 — 확인)
- `{% block content %}` 의 닫는 `</div>` 직전에 아래 추가:

```html
{% include "candidates/partials/search_bar_fixed.html" %}
```

- FAB/모달이 `base.html`에서 include되는지 확인:

```bash
grep -n "chatbot_fab\|chatbot_modal" templates/common/base.html candidates/templates/candidates/
```

발견되면 해당 include를 조건부(예: `{% if not hide_chatbot %}`)로 바꾸지 말고 그냥 삭제.

- [ ] **Step 4: 수동 브라우저 확인**

`./dev.sh` → `/candidates/` 하단 바 렌더, 입력 포커스 시 전송 버튼 교체, 마이크 클릭 → 녹음 → 정지 → STT 확인. URL 리포트.

- [ ] **Step 5: Commit**

```bash
git add candidates/templates/candidates/partials/search_bar_fixed.html candidates/static/candidates/search_bar.js candidates/templates/candidates/search.html
git commit -m "feat(candidates): fixed bottom search bar with voice+text state machine"
```

---

## Task 7: Add Candidate view + URL + 템플릿 (파일 업로드 제외)

spec §2.5 필수·선택 정보 폼. 이력서 업로드는 Task 8에서.

**Files:**
- Modify: `candidates/urls.py`
- Modify: `candidates/views.py`
- Create: `candidates/forms.py` 또는 modify (없으면 생성)
- Create: `candidates/templates/candidates/candidate_form.html`
- Create: `candidates/services/candidate_create.py`
- Create: `candidates/tests/test_candidate_create.py`

- [ ] **Step 1: URL 추가**

Edit `candidates/urls.py:15` — `candidate_detail` 바로 앞에 삽입:

```python
    path("new/", views.candidate_create, name="candidate_create"),
```

(`<uuid:pk>/` 보다 위에 와야 함 — "new"가 uuid로 안 해석되게)

- [ ] **Step 2: 테스트 작성 (실패)**

Create `candidates/tests/test_candidate_create.py`:

```python
import pytest
from django.contrib.auth import get_user_model
from candidates.models import Candidate


@pytest.fixture
def auth_client(client, db):
    User = get_user_model()
    u = User.objects.create_user(email="creator@example.com", password="x")
    client.force_login(u)
    return client


@pytest.mark.django_db
def test_new_page_renders(auth_client):
    resp = auth_client.get("/candidates/new/")
    assert resp.status_code == 200
    assert b"name=\"name\"" in resp.content


@pytest.mark.django_db
def test_create_requires_email_or_phone(auth_client):
    resp = auth_client.post("/candidates/new/", {"name": "홍길동"})
    assert resp.status_code in (400, 200)
    assert not Candidate.objects.filter(name="홍길동").exists()


@pytest.mark.django_db
def test_create_with_email_succeeds(auth_client):
    resp = auth_client.post("/candidates/new/", {
        "name": "홍길동",
        "email": "hong@ex.com",
        "current_company": "네이버",
    })
    assert resp.status_code in (302, 200)  # redirect or success page
    assert Candidate.objects.filter(name="홍길동", email="hong@ex.com").exists()


@pytest.mark.django_db
def test_duplicate_email_warns(auth_client):
    Candidate.objects.create(name="김기존", email="dup@ex.com")
    resp = auth_client.post("/candidates/new/", {
        "name": "김신규",
        "email": "dup@ex.com",
    })
    # Expect rendered warning page, not silent create
    assert resp.status_code == 200
    assert b"duplicate" in resp.content.lower() or "기존".encode("utf-8") in resp.content
```

```bash
uv run pytest candidates/tests/test_candidate_create.py -v
```
Expected: FAIL (view 없음).

- [ ] **Step 3: 서비스 작성**

Create `candidates/services/candidate_create.py`:

```python
from __future__ import annotations

from django.db import transaction

from candidates.models import Candidate


def find_duplicate(email: str | None, phone: str | None) -> Candidate | None:
    """Return existing candidate matching email or phone (exact), else None."""
    if email:
        hit = Candidate.objects.filter(email__iexact=email.strip()).first()
        if hit:
            return hit
    if phone:
        # Simple normalization: strip non-digits
        normalized = "".join(c for c in phone if c.isdigit())
        if normalized:
            hit = Candidate.objects.filter(phone__contains=normalized[-8:]).first()
            if hit:
                return hit
    return None


@transaction.atomic
def create_candidate(data: dict, user=None) -> Candidate:
    """Create a Candidate. Caller is responsible for duplicate check."""
    field_whitelist = {
        "name", "email", "phone", "current_company", "current_position",
        "birth_year", "primary_category", "source", "address",
    }
    kwargs = {k: v for k, v in data.items() if k in field_whitelist and v not in (None, "")}
    if "birth_year" in kwargs:
        try:
            kwargs["birth_year"] = int(kwargs["birth_year"])
        except (ValueError, TypeError):
            kwargs.pop("birth_year")
    candidate = Candidate.objects.create(**kwargs)
    return candidate
```

- [ ] **Step 4: view 작성**

Edit `candidates/views.py` — 임의 위치(`candidate_detail` 위)에 추가:

```python
@login_required
def candidate_create(request):
    """Render Add Candidate form (GET) or create (POST)."""
    from candidates.services.candidate_create import create_candidate, find_duplicate

    categories = Category.objects.order_by("name")

    if request.method == "POST":
        data = request.POST
        name = data.get("name", "").strip()
        email = data.get("email", "").strip() or None
        phone = data.get("phone", "").strip() or None

        errors = {}
        if not name:
            errors["name"] = "이름은 필수입니다."
        if not email and not phone:
            errors["contact"] = "이메일 또는 전화번호 중 하나 이상 입력해주세요."

        if errors:
            return render(
                request,
                "candidates/candidate_form.html",
                {"errors": errors, "form_data": data, "categories": categories},
                status=400,
            )

        # Duplicate check unless user confirmed override
        if not data.get("confirm_duplicate"):
            dup = find_duplicate(email, phone)
            if dup:
                return render(
                    request,
                    "candidates/candidate_form.html",
                    {
                        "duplicate": dup,
                        "form_data": data,
                        "categories": categories,
                    },
                )

        payload = {
            "name": name,
            "email": email or "",
            "phone": phone or "",
            "current_company": data.get("current_company") or "",
            "current_position": data.get("current_position") or "",
            "birth_year": data.get("birth_year") or None,
            "source": data.get("source") or "manual",
        }
        cat_id = data.get("primary_category")
        if cat_id:
            try:
                payload["primary_category"] = Category.objects.get(pk=cat_id)
            except (Category.DoesNotExist, ValueError):
                pass
        candidate = create_candidate(payload, user=request.user)

        from django.shortcuts import redirect
        return redirect("candidates:candidate_detail", pk=candidate.pk)

    return render(
        request,
        "candidates/candidate_form.html",
        {"categories": categories, "form_data": {}, "errors": {}},
    )
```

- [ ] **Step 5: 템플릿 작성**

Create `candidates/templates/candidates/candidate_form.html`:

```html
{% extends "common/base.html" %}
{% load static %}

{% block title %}후보자 추가 — synco{% endblock %}
{% block breadcrumb_current %}Add Candidate{% endblock %}
{% block page_title %}Add Candidate{% endblock %}

{% block content %}
<div class="px-10 py-10 max-w-3xl mx-auto">
  <header class="mb-8">
    <span class="eyebrow text-ink3 block">Global Talent Pool</span>
    <h2 class="text-3xl font-black text-ink tracking-tight mt-2">후보자 추가</h2>
    <p class="text-sm text-muted mt-2">이름과 연락처(이메일 또는 전화)는 필수입니다. 이력서를 업로드하면 자동 파싱 큐에 들어갑니다.</p>
  </header>

  {% if duplicate %}
  <div class="mb-6 bg-amber-50 border border-amber-200 rounded-card p-5">
    <p class="text-sm font-bold text-amber-900">동일인으로 의심되는 기존 후보자가 있습니다</p>
    <p class="text-sm text-amber-800 mt-2">
      <strong>{{ duplicate.name }}</strong>
      {% if duplicate.current_company %} · {{ duplicate.current_company }}{% endif %}
      ({{ duplicate.email|default:duplicate.phone }})
    </p>
    <div class="mt-3 flex gap-2">
      <a href="/candidates/{{ duplicate.pk }}/"
         class="inline-flex items-center px-3 py-1.5 rounded-lg bg-ink3 text-white text-xs font-bold uppercase tracking-widest">
        기존 후보자로 이동
      </a>
      <button type="submit" form="candidate-form" name="confirm_duplicate" value="1"
              class="inline-flex items-center px-3 py-1.5 rounded-lg border border-amber-400 text-amber-900 text-xs font-bold uppercase tracking-widest bg-white">
        그래도 별도 등록
      </button>
    </div>
  </div>
  {% endif %}

  <form id="candidate-form" method="post" enctype="multipart/form-data"
        class="bg-white border border-hair rounded-card shadow-card p-6 space-y-6">
    {% csrf_token %}

    {% if errors.contact %}
    <p class="text-sm text-rose-600">{{ errors.contact }}</p>
    {% endif %}

    <!-- Section 1: Required -->
    <div>
      <h3 class="eyebrow text-ink mb-3">필수 정보</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <label class="block">
          <span class="text-xs font-bold text-ink2">이름 *</span>
          <input name="name" value="{{ form_data.name|default:'' }}" required
                 class="mt-1 w-full border border-hair rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-ink3">
          {% if errors.name %}<p class="text-xs text-rose-600 mt-1">{{ errors.name }}</p>{% endif %}
        </label>
        <label class="block">
          <span class="text-xs font-bold text-ink2">이메일</span>
          <input name="email" type="email" value="{{ form_data.email|default:'' }}"
                 class="mt-1 w-full border border-hair rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-ink3">
        </label>
        <label class="block">
          <span class="text-xs font-bold text-ink2">전화번호</span>
          <input name="phone" value="{{ form_data.phone|default:'' }}"
                 class="mt-1 w-full border border-hair rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-ink3">
        </label>
      </div>
    </div>

    <!-- Section 2: Optional -->
    <div>
      <h3 class="eyebrow text-ink mb-3">선택 정보</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <label class="block">
          <span class="text-xs font-bold text-ink2">현 회사</span>
          <input name="current_company" value="{{ form_data.current_company|default:'' }}"
                 class="mt-1 w-full border border-hair rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-ink3">
        </label>
        <label class="block">
          <span class="text-xs font-bold text-ink2">현 직책</span>
          <input name="current_position" value="{{ form_data.current_position|default:'' }}"
                 class="mt-1 w-full border border-hair rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-ink3">
        </label>
        <label class="block">
          <span class="text-xs font-bold text-ink2">생년 (YYYY)</span>
          <input name="birth_year" type="number" min="1900" max="2020" value="{{ form_data.birth_year|default:'' }}"
                 class="mt-1 w-full border border-hair rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-ink3">
        </label>
        <label class="block">
          <span class="text-xs font-bold text-ink2">카테고리</span>
          <select name="primary_category"
                  class="mt-1 w-full border border-hair rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-ink3">
            <option value="">— 선택 —</option>
            {% for cat in categories %}
            <option value="{{ cat.pk }}" {% if form_data.primary_category == cat.pk|stringformat:'s' %}selected{% endif %}>{{ cat.name_ko|default:cat.name }}</option>
            {% endfor %}
          </select>
        </label>
        <label class="block">
          <span class="text-xs font-bold text-ink2">소스</span>
          <select name="source"
                  class="mt-1 w-full border border-hair rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-ink3">
            <option value="manual">수동 입력</option>
            <option value="referral">지인 추천</option>
            <option value="linkedin">LinkedIn</option>
            <option value="other">기타</option>
          </select>
        </label>
      </div>
    </div>

    <!-- Section 3: Resume (Task 8에서 활성화) -->
    <div>
      <h3 class="eyebrow text-ink mb-3">이력서 업로드 (선택)</h3>
      <input type="file" name="resume_file" accept=".pdf,.doc,.docx"
             class="block w-full text-sm text-muted file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border file:border-hair file:bg-line file:text-ink3 file:font-semibold hover:file:bg-hair">
      <p class="text-xs text-faint mt-1">pdf/doc/docx, 최대 10MB. 업로드 시 자동 파싱 큐에 들어갑니다.</p>
    </div>

    <div class="pt-4 border-t border-line flex justify-end gap-2">
      <a href="/candidates/" class="px-4 py-2 rounded-lg text-sm font-bold text-muted hover:text-ink">취소</a>
      <button type="submit"
              class="px-5 py-2 rounded-lg bg-ink3 hover:bg-ink2 text-white text-xs font-bold uppercase tracking-widest">
        후보자 등록
      </button>
    </div>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
uv run pytest candidates/tests/test_candidate_create.py -v
```
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add candidates/urls.py candidates/views.py candidates/services/candidate_create.py candidates/templates/candidates/candidate_form.html candidates/tests/test_candidate_create.py
git commit -m "feat(candidates): add candidate_create view with duplicate detection"
```

---

## Task 8: Add Candidate — 이력서 업로드 + Drive + data_extraction queue

Task 7 폼의 `resume_file` 필드를 실제로 처리. Drive `AI_HH > DB > 수동등록` 폴더에 업로드 후 Resume 레코드 생성, `data_extraction` 파이프라인에 큐잉.

**Files:**
- Modify: `candidates/services/candidate_create.py`
- Modify: `candidates/views.py` (`candidate_create`)
- Modify: `candidates/tests/test_candidate_create.py`

- [ ] **Step 1: 기존 Resume 업로드 · data_extraction 큐 방식 파악**

```bash
grep -rn "Resume.objects.create\|processing_status\|manual_upload\|drive_file_id" candidates/ data_extraction/ | head -30
```

존재하는 함수가 있으면 재사용. 없으면 서비스 함수 작성.

- [ ] **Step 2: Drive 업로드 헬퍼 존재 여부 확인**

```bash
grep -n "def upload" data_extraction/services/drive.py
```

`upload_file(service, parent_id, local_path, filename)` 가 없으면 추가. 있으면 시그니처 확인.

- [ ] **Step 3: 서비스 확장**

Edit `candidates/services/candidate_create.py` — 하단에 추가:

```python
import os
import tempfile

from candidates.models import Resume

MANUAL_UPLOAD_FOLDER_NAME = "수동등록"
DRIVE_PARENT_ID = "1k_VtpvJo8P8ynGTvVWS8DtYtK4gZDF_Y"


def attach_resume(candidate, uploaded_file) -> Resume | None:
    """Save uploaded resume to Drive (if configured) and create Resume record."""
    if not uploaded_file:
        return None
    # Size limit: 10MB
    if uploaded_file.size > 10 * 1024 * 1024:
        raise ValueError("파일 크기는 10MB 이하여야 합니다.")
    # Extension allowlist
    ext = os.path.splitext(uploaded_file.name)[1].lower().lstrip(".")
    if ext not in ("pdf", "doc", "docx"):
        raise ValueError("pdf/doc/docx만 업로드 가능합니다.")

    # Save locally first (to tmp) — Drive upload is optional / may fail
    tmp_path = None
    drive_file_id = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            from data_extraction.services.drive import (
                get_drive_service,
                find_category_folder,
            )
            svc = get_drive_service()
            folder_id = find_category_folder(svc, DRIVE_PARENT_ID, MANUAL_UPLOAD_FOLDER_NAME)
            if folder_id:
                # Upload via Drive API (adjust import if helper signature differs)
                from googleapiclient.http import MediaFileUpload
                media = MediaFileUpload(tmp_path, resumable=False)
                result = svc.files().create(
                    body={"name": uploaded_file.name, "parents": [folder_id]},
                    media_body=media,
                    fields="id",
                ).execute()
                drive_file_id = result.get("id")
        except Exception as e:
            # Drive failure should not block Resume creation
            import logging
            logging.getLogger(__name__).warning("Drive upload failed: %s", e)

        resume = Resume.objects.create(
            candidate=candidate,
            source="manual_upload",
            drive_file_id=drive_file_id or "",
            original_filename=uploaded_file.name,
            processing_status="pending",
        )
        candidate.current_resume = resume
        candidate.save(update_fields=["current_resume"])
        return resume
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
```

**주의**: `Resume` 모델의 실제 필드(`source`, `drive_file_id`, `original_filename`, `processing_status`)는 `candidates/models.py` 에서 확인 후 맞춤.

```bash
grep -n "class Resume\b" -A 40 candidates/models.py
```

- [ ] **Step 4: view에서 attach 호출**

Edit `candidates/views.py` — `candidate_create` 함수 내 `candidate = create_candidate(...)` 직후에 추가:

```python
        resume_file = request.FILES.get("resume_file")
        if resume_file:
            from candidates.services.candidate_create import attach_resume
            try:
                attach_resume(candidate, resume_file)
            except ValueError as e:
                # Rollback candidate? Keep candidate, report error inline
                from django.contrib import messages
                messages.error(request, str(e))
```

- [ ] **Step 5: 테스트 보강**

Edit `candidates/tests/test_candidate_create.py` — 아래 케이스 추가:

```python
import io
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.mark.django_db
def test_resume_upload_rejects_large_file(auth_client):
    big = SimpleUploadedFile("big.pdf", b"x" * (11 * 1024 * 1024), content_type="application/pdf")
    resp = auth_client.post("/candidates/new/", {
        "name": "홍길동",
        "email": "hong2@ex.com",
        "resume_file": big,
    })
    # Candidate may still be created (graceful), but no Resume
    from candidates.models import Candidate, Resume
    c = Candidate.objects.filter(email="hong2@ex.com").first()
    if c:
        assert not Resume.objects.filter(candidate=c).exists()


@pytest.mark.django_db
def test_resume_upload_rejects_bad_extension(auth_client):
    bad = SimpleUploadedFile("resume.exe", b"x", content_type="application/octet-stream")
    resp = auth_client.post("/candidates/new/", {
        "name": "홍길동",
        "email": "hong3@ex.com",
        "resume_file": bad,
    })
    from candidates.models import Resume
    assert not Resume.objects.filter(original_filename__endswith=".exe").exists()


@pytest.mark.django_db
def test_resume_upload_success_creates_pending_resume(auth_client, monkeypatch):
    # Bypass Drive call
    def fake_attach(candidate, uploaded):
        from candidates.models import Resume
        r = Resume.objects.create(
            candidate=candidate,
            source="manual_upload",
            original_filename=uploaded.name,
            processing_status="pending",
        )
        candidate.current_resume = r
        candidate.save(update_fields=["current_resume"])
        return r

    monkeypatch.setattr(
        "candidates.services.candidate_create.attach_resume", fake_attach
    )

    good = SimpleUploadedFile("cv.pdf", b"%PDF-1.4", content_type="application/pdf")
    auth_client.post("/candidates/new/", {
        "name": "홍업로드", "email": "upload@ex.com", "resume_file": good,
    })
    from candidates.models import Candidate
    c = Candidate.objects.get(email="upload@ex.com")
    assert c.current_resume is not None
    assert c.current_resume.processing_status == "pending"
```

```bash
uv run pytest candidates/tests/test_candidate_create.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add candidates/services/candidate_create.py candidates/views.py candidates/tests/test_candidate_create.py
git commit -m "feat(candidates): resume upload + Drive + processing queue integration"
```

---

## Task 9: Detail 페이지 Profile Header

avatar-xl + status pill(review-notice) + 이름 + eyebrow + 메타 pills(주소/Identity Verified/경력).

**Files:**
- Modify: `candidates/templates/candidates/partials/candidate_detail_content.html` (상단 헤더 영역)
- Modify: `candidates/templates/candidates/detail.html` (wrapper padding)

- [ ] **Step 1: 목업 헤더 영역 참조**

```bash
sed -n '1,120p' assets/ui-sample/candidate-detail.html
```
에서 profile header 섹션 확인 (avatar, CTA buttons, meta pills).

- [ ] **Step 2: 현재 `candidate_detail_content.html` 헤더 교체**

Edit `candidates/templates/candidates/partials/candidate_detail_content.html` — 파일 상단 ~ (대략 line 1-150) "Profile header" 내지 avatar/name 영역을 아래로 교체 (기존 review notice section include는 헤더 위로 보존):

```html
{% load candidate_ui %}
{% review_notice_pill candidate as notice %}

{# Back link #}
<div class="mb-6">
  <a href="/candidates/"
     hx-get="/candidates/"
     hx-target="#main-content"
     hx-push-url="true"
     class="text-xs font-bold text-muted hover:text-ink3 uppercase tracking-widest inline-flex items-center gap-1">
    ← Back to Talent Pool
  </a>
</div>

{# Review notice (if any) — preserve existing block #}
{% include "candidates/partials/_review_notice_section.html" %}

{# Profile header #}
<section class="bg-white border border-hair rounded-card shadow-card p-8 mb-6 flex flex-col lg:flex-row lg:items-center gap-6">
  <div class="relative shrink-0">
    <div class="w-32 h-32 rounded-2xl bg-line flex items-center justify-center">
      <svg class="w-16 h-16 text-faint" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
              d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
      </svg>
    </div>
    {% if notice %}
    <span class="absolute -bottom-2 left-1/2 -translate-x-1/2 eyebrow border rounded-full px-3 py-1 shadow-card {{ notice.classes }}">
      {{ notice.label }}
    </span>
    {% endif %}
  </div>

  <div class="flex-1 min-w-0">
    <span class="eyebrow text-ink3 block">Candidate Profile</span>
    <h1 class="text-4xl font-black text-ink tracking-tight mt-2 flex items-center gap-3">
      {{ candidate.name }}
      {% if candidate.age_display %}<span class="text-lg font-semibold text-muted">({{ candidate.age_display }})</span>{% endif %}
    </h1>
    <p class="text-base text-ink2 font-semibold mt-1">
      {% if candidate.current_position %}{{ candidate.current_position }}{% endif %}
      {% if candidate.current_company %}<span class="mx-1 text-faint">·</span>{{ candidate.current_company }}{% endif %}
    </p>

    <div class="flex items-center gap-2 mt-4 flex-wrap">
      {% if candidate.address %}
      <span class="eyebrow border border-hair bg-line rounded-full px-3 py-1 text-muted">{{ candidate.address }}</span>
      {% endif %}
      {% if candidate.validation_status == "confirmed" or candidate.validation_status == "auto_confirmed" %}
      <span class="eyebrow border border-emerald-100 bg-emerald-50 text-emerald-700 rounded-full px-3 py-1">
        ✓ Identity Verified
      </span>
      {% endif %}
      {% if candidate.computed_total_experience_display %}
      <span class="eyebrow border border-ink3/20 bg-ink3/10 text-ink3 rounded-full px-3 py-1">
        총 경력 {{ candidate.computed_total_experience_display }}
      </span>
      {% endif %}
    </div>
  </div>

  <div class="flex items-center gap-2 lg:self-start shrink-0">
    {% if primary_resume.drive_file_id %}
    <a href="https://drive.google.com/file/d/{{ primary_resume.drive_file_id }}/view" target="_blank"
       class="inline-flex items-center gap-2 border border-hair rounded-lg px-4 py-2 text-xs font-bold uppercase tracking-widest text-ink2 hover:bg-line transition">
      Export PDF
    </a>
    {% endif %}
    {% if candidate.email %}
    <a href="mailto:{{ candidate.email }}"
       class="inline-flex items-center gap-2 rounded-lg bg-ink3 hover:bg-ink2 text-white px-4 py-2 text-xs font-bold uppercase tracking-widest transition">
      Contact Candidate
    </a>
    {% endif %}
  </div>
</section>
```

**주의**: `computed_total_experience_display` 가 candidate 모델에 없으면 `total_experience_display` 사용. 확인:

```bash
grep -n "total_experience_display\|computed_total_experience" candidates/models.py
```

- [ ] **Step 3: wrapper 조정**

Edit `candidates/templates/candidates/detail.html:9` — `<div class="px-10 py-10 max-w-7xl">`를 `<div class="px-10 py-8 max-w-6xl mx-auto">` (목업 폭 맞춤)로 교체.

- [ ] **Step 4: 수동 확인**

`./dev.sh` → 아무 후보자 상세 페이지 열기. 헤더·avatar·pills 정상 렌더. URL 리포트.

- [ ] **Step 5: Commit**

```bash
git add candidates/templates/candidates/partials/candidate_detail_content.html candidates/templates/candidates/detail.html
git commit -m "feat(candidates): detail profile header v2"
```

---

## Task 10: Detail 좌측 컬럼 재구성

Summary / Work Experience timeline / Personal / Matched Projects / Comments.

**Files:**
- Modify: `candidates/templates/candidates/partials/candidate_detail_content.html`

- [ ] **Step 1: 좌/우 그리드 구조 래핑**

Edit `candidates/templates/candidates/partials/candidate_detail_content.html` — 프로필 헤더 직후부터 파일 끝까지를 아래 래퍼로 감싸도록 재구성:

```html
<div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
  <div class="lg:col-span-8 space-y-6">
    <!-- LEFT SECTIONS — Task 10에서 채움 -->
  </div>
  <aside class="lg:col-span-4 space-y-6">
    <!-- RIGHT SECTIONS — Task 11에서 채움 -->
  </aside>
</div>
```

- [ ] **Step 2: 좌측 섹션 1 — Summary**

LEFT 첫 섹션으로 추가:

```html
{% if candidate.summary %}
<section class="bg-white border border-hair rounded-card shadow-card p-6">
  <h3 class="eyebrow text-ink3 mb-3">Summary</h3>
  <p class="text-sm text-ink2 leading-relaxed">{{ candidate.summary }}</p>
</section>
{% endif %}
```

- [ ] **Step 3: 좌측 섹션 2 — Work Experience (timeline)**

```html
{% if careers %}
<section class="bg-white border border-hair rounded-card shadow-card p-6">
  <h3 class="eyebrow text-ink3 mb-4">Work Experience</h3>
  <div class="space-y-5 border-l-2 border-line pl-5 ml-2">
    {% for career in careers %}
    <div class="relative">
      <span class="absolute -left-[29px] top-1.5 w-3 h-3 rounded-full {% if career.is_current %}bg-ink3{% else %}bg-faint{% endif %} border-2 border-white"></span>
      <div class="flex items-start justify-between gap-2 flex-wrap">
        <div class="min-w-0">
          <h4 class="text-base font-bold text-ink">{{ career.position }}</h4>
          <p class="text-sm text-ink2 font-semibold">{{ career.company }}{% if career.department %} · {{ career.department }}{% endif %}</p>
          <p class="eyebrow text-muted mt-1">
            {{ career.start_date_display }} — {{ career.end_date_display }}{% if career.duration_display %} · {{ career.duration_display }}{% endif %}
          </p>
        </div>
        {% if career.is_current %}
        <span class="eyebrow bg-ink3/10 text-ink3 border border-ink3/20 rounded-full px-2 py-0.5">Present</span>
        {% else %}
        <span class="eyebrow text-faint border border-hair rounded-full px-2 py-0.5">Previous</span>
        {% endif %}
      </div>
      {% if career.duties %}
      <p class="text-sm text-muted mt-3 leading-relaxed">{{ career.duties|truncatewords:60 }}</p>
      {% endif %}
      {% if career.achievements %}
      <div class="mt-3 bg-line border-l-4 border-ink3 rounded-r-lg p-3">
        <p class="eyebrow text-ink3 mb-1">주요 성과</p>
        <p class="text-sm text-ink2 leading-relaxed">{{ career.achievements }}</p>
      </div>
      {% endif %}
    </div>
    {% endfor %}
  </div>
</section>
{% endif %}
```

- [ ] **Step 4: 좌측 섹션 3 — Personal**

```html
<section class="bg-white border border-hair rounded-card shadow-card p-6">
  <h3 class="eyebrow text-ink3 mb-4">Personal</h3>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3">
    {% if candidate.birth_year %}
    <div><span class="eyebrow text-muted">생년</span><p class="text-sm text-ink font-semibold">{{ candidate.birth_year }}</p></div>
    {% endif %}
    {% if candidate.gender %}
    <div><span class="eyebrow text-muted">성별</span><p class="text-sm text-ink font-semibold">{{ candidate.gender }}</p></div>
    {% endif %}
    {% if candidate.primary_category %}
    <div><span class="eyebrow text-muted">카테고리</span><p class="text-sm text-ink font-semibold">{{ candidate.primary_category.name_ko|default:candidate.primary_category.name }}</p></div>
    {% endif %}
    {% if candidate.email %}
    <div><span class="eyebrow text-muted">이메일</span><p class="text-sm text-ink font-semibold">{{ candidate.email }}</p></div>
    {% endif %}
    {% if candidate.current_salary %}
    <div><span class="eyebrow text-muted">현재 연봉</span><p class="text-sm text-ink font-semibold tnum">{{ candidate.current_salary }}</p></div>
    {% endif %}
    {% if candidate.desired_salary %}
    <div><span class="eyebrow text-muted">희망 연봉</span><p class="text-sm text-ink font-semibold tnum">{{ candidate.desired_salary }}</p></div>
    {% endif %}
  </div>
</section>
```

- [ ] **Step 5: 좌측 섹션 4 — Matched Projects**

```html
<section class="bg-white border border-hair rounded-card shadow-card p-6">
  <h3 class="eyebrow text-ink3 mb-4">Matched Projects</h3>
  {% if candidate_applications %}
  <div class="space-y-3">
    {% for app in candidate_applications %}
    <a href="/projects/{{ app.project.pk }}/"
       class="block border border-hair rounded-lg p-4 hover:bg-line transition">
      <div class="flex items-center justify-between">
        <div>
          <p class="text-sm font-bold text-ink">{{ app.project.client.name }} · {{ app.project.title }}</p>
          <p class="eyebrow text-muted mt-1">Stage · {{ app.get_current_state_display|default:app.current_state }}</p>
        </div>
      </div>
    </a>
    {% endfor %}
  </div>
  {% else %}
  <p class="text-sm text-muted">아직 매칭된 프로젝트가 없습니다.</p>
  {% endif %}
</section>
```

- [ ] **Step 6: 좌측 섹션 5 — Comments**

```html
{% include "candidates/partials/_comment_section.html" %}
```

(기존 comment section 스타일이 카드 감싸져있지 않으면 `<section class="bg-white border border-hair rounded-card shadow-card p-6">...</section>` 로 래핑)

- [ ] **Step 7: 기존 Overseas/Self intro/Awards/Patents 등 보존**

기존 템플릿 내부에 있던 조건부 섹션을 좌측 LEFT 맨 아래로 이전. 각 섹션을 위 카드 스타일(`bg-white border border-hair rounded-card shadow-card p-6`)에 맞춰 래핑 스타일만 통일.

- [ ] **Step 8: 수동 확인**

브라우저에서 후보자 상세 확인. URL 리포트.

- [ ] **Step 9: Commit**

```bash
git add candidates/templates/candidates/partials/candidate_detail_content.html
git commit -m "feat(candidates): detail left column — summary/work/personal/matched/comments"
```

---

## Task 11: Detail 우측 사이드바

Core Expertise / Education / Certifications / Languages(4-dot) / Activity Snapshot.

**Files:**
- Modify: `candidates/templates/candidates/partials/candidate_detail_content.html` (aside 블록)

- [ ] **Step 1: Core Expertise**

aside 첫 섹션:

```html
<section class="bg-white border border-hair rounded-card shadow-card p-6">
  <h3 class="eyebrow text-ink3 mb-3">Core Expertise</h3>
  <div class="flex flex-wrap gap-1.5">
    {% for item in candidate.core_competencies %}
    <span class="text-xs font-semibold bg-ink text-white px-2 py-1 rounded-lg">{% if item.name %}{{ item.name }}{% else %}{{ item }}{% endif %}</span>
    {% empty %}{% endfor %}
    {% for skill in candidate.skills %}
    <span class="text-xs font-medium text-ink2 bg-line border border-hair px-2 py-1 rounded-lg">{% if skill.name %}{{ skill.name }}{% else %}{{ skill }}{% endif %}</span>
    {% endfor %}
  </div>
</section>
```

- [ ] **Step 2: Education**

```html
{% if educations %}
<section class="bg-white border border-hair rounded-card shadow-card p-6">
  <h3 class="eyebrow text-ink3 mb-3">Education</h3>
  <div class="space-y-3">
    {% for edu in educations %}
    <div class="flex gap-3">
      <svg class="w-5 h-5 text-faint shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 3L1 9l11 6 9-4.91V17h2V9z"/></svg>
      <div class="min-w-0">
        <p class="text-sm font-bold text-ink truncate">{{ edu.institution }}</p>
        <p class="text-xs text-muted">{{ edu.degree|default:"" }}{% if edu.major %} · {{ edu.major }}{% endif %}</p>
        {% if edu.graduation_year %}<p class="eyebrow text-faint mt-0.5">Class of {{ edu.graduation_year }}</p>{% endif %}
      </div>
    </div>
    {% endfor %}
  </div>
</section>
{% endif %}
```

- [ ] **Step 3: Certifications**

```html
{% if certifications %}
<section class="bg-white border border-hair rounded-card shadow-card p-6">
  <h3 class="eyebrow text-ink3 mb-3">Certifications</h3>
  <div class="space-y-2">
    {% for cert in certifications %}
    <div class="border border-hair rounded-lg p-3">
      <p class="text-sm font-bold text-ink">{{ cert.name }}</p>
      {% if cert.issuing_org %}<p class="text-xs text-muted">{{ cert.issuing_org }}</p>{% endif %}
      {% if cert.acquisition_date %}<p class="eyebrow text-faint mt-1">{{ cert.acquisition_date|date:"Y-m" }}</p>{% endif %}
    </div>
    {% endfor %}
  </div>
</section>
{% endif %}
```

- [ ] **Step 4: Languages (4-dot)**

```html
{% load candidate_ui %}
{% if language_skills %}
<section class="bg-white border border-hair rounded-card shadow-card p-6">
  <h3 class="eyebrow text-ink3 mb-3">Languages</h3>
  <div class="space-y-3">
    {% for lang in language_skills %}
    {% language_level_bars lang as bars %}
    <div>
      <div class="flex items-center justify-between">
        <p class="text-sm font-bold text-ink">{{ lang.language }}</p>
        <p class="eyebrow text-muted">{{ lang.level|default:lang.test_name|default:"—" }}</p>
      </div>
      <div class="flex gap-1 mt-1.5">
        {% for i in "1234" %}
        <span class="w-1/4 h-1.5 rounded-full {% if forloop.counter <= bars %}bg-ink3{% else %}bg-line{% endif %}"></span>
        {% endfor %}
      </div>
    </div>
    {% endfor %}
  </div>
</section>
{% endif %}
```

- [ ] **Step 5: Activity Snapshot**

```html
<section class="bg-white border border-hair rounded-card shadow-card p-6">
  <h3 class="eyebrow text-ink3 mb-3">Activity Snapshot</h3>
  <dl class="space-y-2 text-sm">
    <div class="flex justify-between"><dt class="text-muted">Profile views</dt><dd class="text-faint">준비중</dd></div>
    <div class="flex justify-between"><dt class="text-muted">Last contacted</dt><dd class="text-faint">준비중</dd></div>
    <div class="flex justify-between"><dt class="text-muted">Added to pipeline</dt><dd class="text-ink font-semibold tnum">{{ candidate.created_at|date:"Y-m-d" }}</dd></div>
  </dl>
</section>
```

- [ ] **Step 6: Detail 렌더 스모크 테스트**

Create `candidates/tests/test_candidate_detail_ui.py`:

```python
import pytest
from django.contrib.auth import get_user_model
from candidates.models import Candidate, LanguageSkill


@pytest.fixture
def auth_client(client, db):
    User = get_user_model()
    u = User.objects.create_user(email="d@example.com", password="x")
    client.force_login(u)
    return client


@pytest.mark.django_db
def test_detail_renders_sections(auth_client):
    c = Candidate.objects.create(name="김상세", summary="테스트 요약")
    LanguageSkill.objects.create(candidate=c, language="영어", level="Business")
    resp = auth_client.get(f"/candidates/{c.pk}/")
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "Summary" in content
    assert "테스트 요약" in content
    assert "Languages" in content
    assert "Activity Snapshot" in content
    assert "준비중" in content
```

```bash
uv run pytest candidates/tests/test_candidate_detail_ui.py -v
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add candidates/templates/candidates/partials/candidate_detail_content.html candidates/tests/test_candidate_detail_ui.py
git commit -m "feat(candidates): detail right sidebar with 4-dot language bars"
```

---

## Task 12: Legacy 챗봇 자산 삭제

기존 FAB / 모달 / chatbot.js / search_status_bar 완전 제거.

**Files:**
- Delete: `candidates/templates/candidates/partials/chatbot_fab.html`
- Delete: `candidates/templates/candidates/partials/chatbot_modal.html`
- Delete: `candidates/templates/candidates/partials/chat_messages.html`
- Delete: `candidates/static/candidates/chatbot.js`
- Delete: `candidates/templates/candidates/partials/search_status_bar.html`

- [ ] **Step 1: 참조 누적 확인**

```bash
grep -rn "chatbot_fab\|chatbot_modal\|chat_messages\|chatbot\.js\|search_status_bar\|toggleChatbot" \
  candidates/templates/ templates/ candidates/static/ candidates/views.py
```
참조가 남아있으면 제거 또는 새 파셜로 교체.

- [ ] **Step 2: 파일 삭제**

```bash
git rm candidates/templates/candidates/partials/chatbot_fab.html
git rm candidates/templates/candidates/partials/chatbot_modal.html
git rm candidates/templates/candidates/partials/chat_messages.html
git rm candidates/static/candidates/chatbot.js
git rm candidates/templates/candidates/partials/search_status_bar.html
```

- [ ] **Step 3: 전체 테스트 실행**

```bash
uv run pytest candidates/ -v
```
Expected: all green. template 참조 누락 시 여기서 잡힘.

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor(candidates): remove legacy chatbot FAB/modal/JS (replaced by fixed search bar)"
```

---

## Task 13: 마무리 스윕 — lint / format / 전체 smoke

**Files:**
- 전체

- [ ] **Step 1: Lint / format**

```bash
uv run ruff check candidates/ data_extraction/
uv run ruff format candidates/ data_extraction/
```

변경사항 있으면 스테이징 후 commit.

- [ ] **Step 2: 전체 pytest**

```bash
uv run pytest -v
```
Expected: 전체 green.

- [ ] **Step 3: 수동 회귀 체크리스트 — 브라우저**

- [ ] `/candidates/` — 헤더, 칩, 카드 그리드, 하단 검색바 idle
- [ ] 카드 클릭 → 상세 페이지 전환
- [ ] 검색바 텍스트 입력 → 전송 버튼 → 검색 결과 로딩
- [ ] 검색바 마이크 → 녹음 → 정지 → STT → 자동 전송
- [ ] 카테고리 칩 클릭 → 필터링
- [ ] `/candidates/new/` — 폼 렌더, 필수 검증, 중복 경고, 등록 성공
- [ ] `/candidates/<pk>/` — profile header, 좌/우 섹션 모두 렌더
- [ ] Language 4-dot 바, Activity Snapshot "준비중" 확인
- [ ] 프로젝트 컨텍스트 `?project=<uuid>` — "프로젝트에 추가" 버튼 노출

- [ ] **Step 4: 최종 Commit**

ruff 변경 또는 추가 소소한 정리가 있을 때만:

```bash
git add -A
git commit -m "chore(candidates): lint/format after Phase D UI redesign"
```

- [ ] **Step 5: 완료 리포트**

사용자에게:
- 변경 요약 (carb v2, detail restructure, search bar, add candidate)
- 수정한 URL 경로 (`/candidates/`, `/candidates/<pk>/`, `/candidates/new/`)
- 수동 확인 요청 항목

---

## Self-Review

**1. Spec coverage**
- §1 스코프 (List/Detail/Add) — Task 3–11, Task 7–8
- §2.1 레이아웃 — Task 5
- §2.2 카드 구성 — Task 4
- §2.3 카테고리 칩 — Task 2, 5
- §2.4 하단 검색바 — Task 6
- §2.5 Add Candidate — Task 7, 8
- §2.6 Filters 제거 — Task 5 (버튼 자체 안 그림)
- §3.1–3.2 Profile Header — Task 9
- §3.3–3.7 좌측 섹션 — Task 10
- §3.8 사이드바 + 4-dot + Activity — Task 3, 11
- §3.9 보존 섹션 — Task 10 Step 7
- §4 스타일 토큰 — Task 1
- §5 URL 매핑 — Task 5, 7
- §6 데이터 / signal — Task 2
- §7 음성 JS — Task 6
- §8 테스트 — Task 2, 3, 4, 7, 8, 11
- §9 Phase C 잔여 — 플랜에는 포함 안 함 (spec에도 "선택적"). 작업 중 발견 시 개별 commit.
- §10 구현 순서 — 본 플랜과 동일
- §11 향후 고려 — 플랜 범위 밖 (즐겨찾기, Export PDF)

**2. Placeholder scan** — "TODO/TBD/fill in/similar to" 없음. 단, Task 8 Step 3의 Resume 모델 필드 확인과 Task 6 Step 2의 search_chat 응답 구조 확인은 "실행 시 확인"이라 spec 가이드 초과 작업이지만 필수.

**3. Type consistency** — `candidate_card_v2.html`에서 사용된 `age_display` 프로퍼티는 Task 4 Step 1에서 모델에 추가. `review_notice_pill` 반환 dict의 키(`severity/count/label/classes`)는 Task 3 정의와 Task 4·9 사용처 일치. `language_level_bars` 반환 타입(int 1–4)은 Task 3 정의와 Task 11의 `forloop.counter <= bars` 비교 일치.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-19-candidate-ui-redesign.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
