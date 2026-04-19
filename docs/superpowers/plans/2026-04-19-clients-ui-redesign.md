# Clients UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `clients` 앱 전체(리스트/상세/신규/수정/삭제)를 목업 `assets/ui-sample/clients-list.html` 기준으로 재작성. 업종을 자유 텍스트에서 11종 choices로 정규화하고, website/logo/description 필드를 추가해 풍부한 카드 UI·필터·상세 페이지를 구성.

**Architecture:** Django 5 + HTMX + Tailwind. 집계는 서비스 계층(`clients/services/`)으로 분리해 `.annotate()` 한 번으로 카드·필터에 필요한 통계를 계산. 카드는 2개 클릭 영역(상단=외부 홈페이지, 하단=프로젝트 리스트). 리스트는 infinite scroll HTMX, 필터는 드롭다운 패널.

**Tech Stack:** Django 5.2, HTMX, Tailwind(Pretendard), PostgreSQL, pytest, Pillow(신규 추가), alpine.js 또는 vanilla JS.

**Spec:** `docs/superpowers/specs/2026-04-19-clients-ui-redesign-design.md`

---

## 작업 그룹

1. **Prep** (Task 1) — 의존성·세팅.
2. **Model & Migration** (Task 2–5) — choices, 신규 필드, 데이터 마이그레이션.
3. **Services** (Task 6–8) — 쿼리·집계·폼 헬퍼.
4. **Templatetags + CSS** (Task 9–10) — 로고·배지 유틸.
5. **List page** (Task 11–14) — grid, 카드, infinite scroll, 카테고리 칩, 필터 드롭다운.
6. **Detail page** (Task 15–17) — 프로필, 좌측(담당자/계약), 우측(프로젝트), 메모.
7. **Form + Delete** (Task 18–20) — 신규/수정 폼, 로고 업로드, 삭제 가드.
8. **Wrap-up** (Task 21) — 수동 QA 체크리스트·핸드오프.

---

## Task 1: 의존성 & 기본 세팅

**Files:**
- Modify: `pyproject.toml`
- Modify: `clients/apps.py` (확인만)
- Create: `clients/services/__init__.py`

- [ ] **Step 1: Pillow 의존성 추가**

```bash
uv add Pillow
```

확인: `pyproject.toml` 의 `dependencies` 에 `"pillow>=..."` 가 추가되고 `uv.lock` 업데이트.

- [ ] **Step 2: clients/services 디렉터리 준비**

```bash
mkdir -p clients/services
```

파일 내용:

```python
# clients/services/__init__.py
```

빈 파일. 모듈은 개별 파일로 분리.

- [ ] **Step 3: 커밋**

```bash
git add pyproject.toml uv.lock clients/services/__init__.py
git commit -m "chore(clients): add Pillow + services package scaffolding"
```

---

## Task 2: IndustryCategory choices 추가 (기존 industry 유지)

**Files:**
- Modify: `clients/models.py`
- Create: `tests/test_clients_models.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_clients_models.py`:

```python
import pytest

from clients.models import Client, IndustryCategory


@pytest.mark.django_db
def test_industry_category_has_11_choices():
    assert len(IndustryCategory.choices) == 11


@pytest.mark.django_db
def test_industry_category_values_include_expected():
    values = {c.value for c in IndustryCategory}
    assert "바이오/제약" in values
    assert "IT/SW" in values
    assert "기타" in values


@pytest.mark.django_db
def test_industry_category_enum_names_for_url_params():
    assert IndustryCategory["BIO_PHARMA"].value == "바이오/제약"
    assert IndustryCategory["IT_SW"].value == "IT/SW"
    assert IndustryCategory["ETC"].value == "기타"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/test_clients_models.py -v
```

Expected: `ImportError: cannot import name 'IndustryCategory'`.

- [ ] **Step 3: IndustryCategory 추가**

`clients/models.py` 상단 `class Client` 위에 추가:

```python
class IndustryCategory(models.TextChoices):
    BIO_PHARMA     = "바이오/제약",       "바이오 / 제약"
    HEALTHCARE     = "헬스케어/의료기기",  "헬스케어 / 의료기기"
    IT_SW          = "IT/SW",           "IT / SW"
    MATERIAL_PARTS = "소재/부품",        "소재 / 부품"
    FINANCE        = "금융/캐피탈",       "금융 / 캐피탈"
    CONSUMER       = "소비재/패션",       "소비재 / 패션"
    ENV_UTILITY    = "환경/유틸리티",     "환경 / 유틸리티"
    MOBILITY       = "모빌리티/제조",     "모빌리티 / 제조"
    MEDIA_ENTER    = "미디어/엔터",       "미디어 / 엔터"
    CONSTRUCTION   = "건설/부동산",       "건설 / 부동산"
    ETC            = "기타",             "기타"
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/test_clients_models.py -v
```

Expected: 3 passed.

- [ ] **Step 5: 커밋**

```bash
git add clients/models.py tests/test_clients_models.py
git commit -m "feat(clients): add IndustryCategory with 11 choices"
```

---

## Task 3: website/logo/description 필드 추가

**Files:**
- Modify: `clients/models.py`
- Create: `clients/migrations/XXXX_client_website_logo_description.py` (autogen)
- Modify: `tests/test_clients_models.py`

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_clients_models.py` 하단에 추가:

```python
from accounts.models import Organization


@pytest.fixture
def org(db):
    return Organization.objects.create(name="TestOrg")


@pytest.mark.django_db
def test_client_has_website_field(org):
    c = Client.objects.create(organization=org, name="X", website="https://example.com")
    c.refresh_from_db()
    assert c.website == "https://example.com"


@pytest.mark.django_db
def test_client_has_description_field(org):
    c = Client.objects.create(organization=org, name="X", description="desc")
    c.refresh_from_db()
    assert c.description == "desc"


@pytest.mark.django_db
def test_client_logo_upload_to_path(org):
    c = Client.objects.create(organization=org, name="X")
    field = c._meta.get_field("logo")
    assert field.upload_to == "clients/logos/"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/test_clients_models.py -v
```

Expected: 3 new failures.

- [ ] **Step 3: 필드 추가**

`clients/models.py::Client` 에 추가 (기존 필드 아래):

```python
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to="clients/logos/", blank=True, null=True)
    description = models.TextField(blank=True)
```

- [ ] **Step 4: 마이그레이션 생성**

```bash
uv run python manage.py makemigrations clients
```

생성된 파일 확인 — 3개 필드만 추가되는 단순 마이그레이션이어야 함.

- [ ] **Step 5: 마이그레이션 적용 + 테스트**

```bash
uv run python manage.py migrate clients
uv run pytest tests/test_clients_models.py -v
```

Expected: all passed.

- [ ] **Step 6: 커밋**

```bash
git add clients/models.py clients/migrations/ tests/test_clients_models.py
git commit -m "feat(clients): add website/logo/description fields"
```

---

## Task 4: industry 자유 텍스트 → IndustryCategory choices 교체 + 데이터 마이그레이션

**Files:**
- Modify: `clients/models.py`
- Create: `clients/migrations/XXXX_migrate_industry_to_category.py` (data migration)
- Create: `clients/migrations/YYYY_alter_industry_to_choices.py` (schema migration)

- [ ] **Step 1: 데이터 마이그레이션 생성**

```bash
uv run python manage.py makemigrations clients --empty --name migrate_industry_to_category
```

- [ ] **Step 2: 데이터 마이그레이션 내용 작성**

`clients/migrations/XXXX_migrate_industry_to_category.py`:

```python
from django.db import migrations


KEYWORD_MAP = [
    # (카테고리 value, 매칭 키워드 리스트)
    ("바이오/제약", ["바이오", "제약", "신약", "pharma", "bio"]),
    ("헬스케어/의료기기", ["헬스케어", "의료기기", "덴탈", "dental", "medical"]),
    ("IT/SW", ["it", "sw", "소프트웨어", "software", "saas", "플랫폼", "인터넷"]),
    ("소재/부품", ["소재", "부품", "반도체", "디스플레이", "화학"]),
    ("금융/캐피탈", ["금융", "캐피탈", "은행", "증권", "보험", "투자"]),
    ("소비재/패션", ["소비재", "패션", "식품", "리테일", "retail", "consumer"]),
    ("환경/유틸리티", ["환경", "에너지", "유틸리티", "energy", "utility"]),
    ("모빌리티/제조", ["모빌리티", "자동차", "mobility", "제조", "manufacturing"]),
    ("미디어/엔터", ["미디어", "엔터", "콘텐츠", "방송", "media"]),
    ("건설/부동산", ["건설", "부동산", "construction", "real estate"]),
]


def classify(industry_text: str) -> str:
    text = (industry_text or "").strip().lower()
    if not text:
        return "기타"
    for category, keywords in KEYWORD_MAP:
        for kw in keywords:
            if kw.lower() in text:
                return category
    return "기타"


def forwards(apps, schema_editor):
    Client = apps.get_model("clients", "Client")
    for client in Client.objects.all():
        client.industry = classify(client.industry)
        client.save(update_fields=["industry"])


def backwards(apps, schema_editor):
    # 비파괴적 복원 불가 — 역마이그레이션은 no-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "XXXX_client_website_logo_description"),  # ← Task 3 마이그레이션 번호로 교체
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
```

**중요:** `dependencies` 의 `XXXX_client_website_logo_description` 부분을 Task 3에서 실제로 생성된 마이그레이션 파일 이름으로 교체한다.

- [ ] **Step 3: 스키마 마이그레이션 생성**

`clients/models.py::Client.industry` 수정:

```python
    industry = models.CharField(
        max_length=30,
        choices=IndustryCategory.choices,
        default=IndustryCategory.ETC,
        blank=True,
    )
```

(기존: `industry = models.CharField(max_length=100, blank=True)`)

그리고:

```bash
uv run python manage.py makemigrations clients
```

생성된 파일은 `alter_client_industry` 같은 이름. 데이터 마이그레이션 **뒤**에 의존하도록 의존성 순서 자동 설정됨 — 확인.

- [ ] **Step 4: 통합 테스트 작성**

`tests/test_clients_models.py` 하단에 추가:

```python
@pytest.mark.django_db
def test_industry_default_is_etc(org):
    c = Client.objects.create(organization=org, name="X")
    assert c.industry == IndustryCategory.ETC.value


@pytest.mark.django_db
def test_industry_accepts_valid_category(org):
    c = Client.objects.create(
        organization=org, name="X", industry=IndustryCategory.BIO_PHARMA.value
    )
    c.refresh_from_db()
    assert c.industry == "바이오/제약"
```

- [ ] **Step 5: 마이그레이션 적용 + 테스트**

```bash
uv run python manage.py migrate clients
uv run pytest tests/test_clients_models.py -v
```

Expected: all passed.

- [ ] **Step 6: 커밋**

```bash
git add clients/models.py clients/migrations/ tests/test_clients_models.py
git commit -m "feat(clients): normalize industry to IndustryCategory choices

데이터 마이그레이션으로 기존 자유 텍스트를 11개 카테고리로 매핑. 매핑 불가는 '기타'."
```

---

## Task 5: 기존 ClientForm 업데이트 (모델 변경 대응)

**Files:**
- Modify: `clients/forms.py`

이 태스크는 기존 기능을 깨지 않기 위한 최소 변경. 디자인 재스타일은 Task 18에서.

- [ ] **Step 1: forms.py 에 신규 필드 포함**

`clients/forms.py::ClientForm.Meta.fields`:

```python
fields = ["name", "industry", "size", "region", "website", "logo", "description", "notes"]
```

widgets 에도 해당 필드 추가 — 임시 스타일(Task 18에서 재작성):

```python
"website": forms.URLInput(
    attrs={"class": "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px]"}
),
"logo": forms.ClearableFileInput(
    attrs={"class": "w-full text-sm"}
),
"description": forms.Textarea(
    attrs={"class": "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px]", "rows": 2}
),
```

labels 추가:

```python
"website": "웹사이트",
"logo": "로고",
"description": "설명",
```

- [ ] **Step 2: 기존 ClientForm 테스트가 깨지지 않는지 확인**

```bash
uv run pytest clients/ tests/ -v -k client
```

Expected: 기존 테스트 모두 통과. 만약 실패하면 fields 순서나 choice 변경 영향 — 수정.

- [ ] **Step 3: 커밋**

```bash
git add clients/forms.py
git commit -m "chore(clients): register website/logo/description in ClientForm"
```

---

## Task 6: client_queries 서비스 — 기본 어노테이션

**Files:**
- Create: `clients/services/client_queries.py`
- Create: `tests/test_clients_queries.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_clients_queries.py`:

```python
import pytest
from django.utils import timezone

from accounts.models import Organization
from clients.models import Client
from clients.services.client_queries import list_clients_with_stats
from projects.models import Project, Application


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org")


@pytest.mark.django_db
def test_list_clients_with_stats_zero_projects(org):
    Client.objects.create(organization=org, name="A")
    qs = list_clients_with_stats(org)
    client = qs.get(name="A")
    assert client.offers_count == 0
    assert client.success_count == 0
    assert client.placed_count == 0
    assert client.active_count == 0


@pytest.mark.django_db
def test_list_clients_with_stats_counts_projects(org):
    c = Client.objects.create(organization=org, name="A")
    Project.objects.create(
        client=c, organization=org, title="P1", status="open", result=""
    )
    Project.objects.create(
        client=c, organization=org, title="P2", status="closed", result="success"
    )
    qs = list_clients_with_stats(org)
    client = qs.get(pk=c.pk)
    assert client.offers_count == 2
    assert client.success_count == 1
    assert client.active_count == 1
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/test_clients_queries.py -v
```

Expected: `ModuleNotFoundError: clients.services.client_queries`.

- [ ] **Step 3: 서비스 구현**

`clients/services/client_queries.py`:

```python
from django.db.models import Count, Q

from clients.models import Client


def list_clients_with_stats(org, **filters):
    """Clients queryset annotated with offers/success/placed/active counts.

    Returns a queryset. Apply filters via keyword args (see Task 7).
    """
    qs = (
        Client.objects.filter(organization=org)
        .annotate(
            offers_count=Count("projects", distinct=True),
            success_count=Count(
                "projects",
                filter=Q(projects__result="success"),
                distinct=True,
            ),
            active_count=Count(
                "projects",
                filter=Q(projects__status="open"),
                distinct=True,
            ),
            placed_count=Count(
                "projects__applications",
                filter=Q(projects__applications__hired_at__isnull=False),
                distinct=True,
            ),
        )
        .order_by("-created_at")
    )
    return qs
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/test_clients_queries.py -v
```

Expected: 2 passed.

- [ ] **Step 5: 커밋**

```bash
git add clients/services/client_queries.py tests/test_clients_queries.py
git commit -m "feat(clients): list_clients_with_stats annotates offers/success/placed/active"
```

---

## Task 7: client_queries 서비스 — 필터 조합

**Files:**
- Modify: `clients/services/client_queries.py`
- Modify: `tests/test_clients_queries.py`

- [ ] **Step 1: 필터 테스트 추가**

`tests/test_clients_queries.py` 에 추가:

```python
from clients.models import IndustryCategory


@pytest.mark.django_db
def test_filter_by_category(org):
    Client.objects.create(organization=org, name="Bio", industry=IndustryCategory.BIO_PHARMA.value)
    Client.objects.create(organization=org, name="IT", industry=IndustryCategory.IT_SW.value)
    qs = list_clients_with_stats(org, categories=["BIO_PHARMA"])
    assert qs.count() == 1
    assert qs.first().name == "Bio"


@pytest.mark.django_db
def test_filter_by_size(org):
    Client.objects.create(organization=org, name="L", size="대기업")
    Client.objects.create(organization=org, name="S", size="중소")
    qs = list_clients_with_stats(org, sizes=["대기업"])
    assert qs.count() == 1
    assert qs.first().name == "L"


@pytest.mark.django_db
def test_filter_by_region(org):
    Client.objects.create(organization=org, name="A", region="서울")
    Client.objects.create(organization=org, name="B", region="경기")
    qs = list_clients_with_stats(org, regions=["서울"])
    assert qs.count() == 1


@pytest.mark.django_db
def test_filter_by_offers_range(org):
    c1 = Client.objects.create(organization=org, name="Zero")
    c2 = Client.objects.create(organization=org, name="Three")
    for i in range(3):
        Project.objects.create(client=c2, organization=org, title=f"P{i}", status="open")
    qs = list_clients_with_stats(org, offers_range="0")
    assert qs.count() == 1
    assert qs.first().name == "Zero"
    qs = list_clients_with_stats(org, offers_range="1-5")
    assert qs.count() == 1
    assert qs.first().name == "Three"


@pytest.mark.django_db
def test_filter_by_success_status_has(org):
    c1 = Client.objects.create(organization=org, name="HasSuccess")
    c2 = Client.objects.create(organization=org, name="NoOffers")
    Project.objects.create(client=c1, organization=org, title="P", status="closed", result="success")
    qs = list_clients_with_stats(org, success_status="has")
    assert qs.count() == 1
    assert qs.first().name == "HasSuccess"


@pytest.mark.django_db
def test_filter_by_success_status_none(org):
    c1 = Client.objects.create(organization=org, name="OffersNoSuccess")
    c2 = Client.objects.create(organization=org, name="HasSuccess")
    Project.objects.create(client=c1, organization=org, title="P", status="open", result="")
    Project.objects.create(client=c2, organization=org, title="Q", status="closed", result="success")
    qs = list_clients_with_stats(org, success_status="none")
    assert qs.count() == 1
    assert qs.first().name == "OffersNoSuccess"


@pytest.mark.django_db
def test_filter_by_success_status_no_offers(org):
    Client.objects.create(organization=org, name="NoOffers")
    c2 = Client.objects.create(organization=org, name="HasOffers")
    Project.objects.create(client=c2, organization=org, title="P", status="open")
    qs = list_clients_with_stats(org, success_status="no_offers")
    assert qs.count() == 1
    assert qs.first().name == "NoOffers"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/test_clients_queries.py -v
```

Expected: 7 new failures (unknown kwargs).

- [ ] **Step 3: 필터 구현**

`clients/services/client_queries.py` 에 업데이트:

```python
from django.db.models import Count, Q

from clients.models import Client, IndustryCategory


def _category_values(names):
    """Convert enum names (e.g. 'BIO_PHARMA') to DB values (e.g. '바이오/제약')."""
    values = []
    for name in names or []:
        try:
            values.append(IndustryCategory[name].value)
        except KeyError:
            continue
    return values


def list_clients_with_stats(
    org,
    *,
    categories=None,
    sizes=None,
    regions=None,
    offers_range=None,
    success_status=None,
):
    qs = (
        Client.objects.filter(organization=org)
        .annotate(
            offers_count=Count("projects", distinct=True),
            success_count=Count(
                "projects", filter=Q(projects__result="success"), distinct=True
            ),
            active_count=Count(
                "projects", filter=Q(projects__status="open"), distinct=True
            ),
            placed_count=Count(
                "projects__applications",
                filter=Q(projects__applications__hired_at__isnull=False),
                distinct=True,
            ),
        )
        .order_by("-created_at")
    )

    if categories:
        cat_values = _category_values(categories)
        if cat_values:
            qs = qs.filter(industry__in=cat_values)

    if sizes:
        qs = qs.filter(size__in=sizes)

    if regions:
        qs = qs.filter(region__in=regions)

    if offers_range:
        qs = _apply_offers_range(qs, offers_range)

    if success_status:
        qs = _apply_success_status(qs, success_status)

    return qs


def _apply_offers_range(qs, rng):
    if rng == "0":
        return qs.filter(offers_count=0)
    if rng == "1-5":
        return qs.filter(offers_count__gte=1, offers_count__lte=5)
    if rng == "6-10":
        return qs.filter(offers_count__gte=6, offers_count__lte=10)
    if rng == "10+":
        return qs.filter(offers_count__gt=10)
    return qs


def _apply_success_status(qs, status):
    if status == "has":
        return qs.filter(success_count__gt=0)
    if status == "none":
        return qs.filter(offers_count__gt=0, success_count=0)
    if status == "no_offers":
        return qs.filter(offers_count=0)
    return qs
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/test_clients_queries.py -v
```

Expected: 9 passed.

- [ ] **Step 5: 커밋**

```bash
git add clients/services/client_queries.py tests/test_clients_queries.py
git commit -m "feat(clients): add filter kwargs (category/size/region/offers_range/success_status)"
```

---

## Task 8: client_queries 보조 함수 + client_create 서비스

**Files:**
- Modify: `clients/services/client_queries.py`
- Create: `clients/services/client_create.py`
- Modify: `tests/test_clients_queries.py`
- Create: `tests/test_clients_create.py`

- [ ] **Step 1: category_counts / available_regions / client_stats / client_projects 테스트 추가**

`tests/test_clients_queries.py` 에 추가:

```python
from clients.services.client_queries import (
    available_regions,
    category_counts,
    client_projects,
    client_stats,
)


@pytest.mark.django_db
def test_category_counts(org):
    Client.objects.create(organization=org, name="A", industry="바이오/제약")
    Client.objects.create(organization=org, name="B", industry="바이오/제약")
    Client.objects.create(organization=org, name="C", industry="IT/SW")
    counts = category_counts(org)
    assert counts["BIO_PHARMA"] == 2
    assert counts["IT_SW"] == 1
    assert counts["FINANCE"] == 0


@pytest.mark.django_db
def test_available_regions(org):
    Client.objects.create(organization=org, name="A", region="서울")
    Client.objects.create(organization=org, name="B", region="서울")
    Client.objects.create(organization=org, name="C", region="경기")
    Client.objects.create(organization=org, name="D", region="")
    regions = available_regions(org)
    assert sorted(regions) == ["경기", "서울"]


@pytest.mark.django_db
def test_client_stats(org):
    c = Client.objects.create(organization=org, name="A")
    Project.objects.create(client=c, organization=org, title="P", status="open")
    Project.objects.create(client=c, organization=org, title="Q", status="closed", result="success")
    stats = client_stats(c)
    assert stats["offers"] == 2
    assert stats["success"] == 1
    assert stats["active"] == 1
    assert stats["placed"] == 0


@pytest.mark.django_db
def test_client_projects_status_filter(org):
    c = Client.objects.create(organization=org, name="A")
    Project.objects.create(client=c, organization=org, title="P1", status="open")
    Project.objects.create(client=c, organization=org, title="P2", status="closed", result="success")
    assert client_projects(c, status_filter="active").count() == 1
    assert client_projects(c, status_filter="closed").count() == 1
    assert client_projects(c, status_filter="all").count() == 2
```

- [ ] **Step 2: 서비스 함수 추가**

`clients/services/client_queries.py` 하단에 추가:

```python
def category_counts(org):
    """카테고리 enum name -> 건수. 0건도 포함."""
    counts = {c.name: 0 for c in IndustryCategory}
    qs = (
        Client.objects.filter(organization=org)
        .values("industry")
        .annotate(n=Count("id"))
    )
    value_to_name = {c.value: c.name for c in IndustryCategory}
    for row in qs:
        name = value_to_name.get(row["industry"])
        if name:
            counts[name] = row["n"]
    return counts


def available_regions(org):
    """조직 내 사용 중인 region 값 리스트(알파벳/가나다 순)."""
    return sorted(
        v
        for v in Client.objects.filter(organization=org)
        .values_list("region", flat=True)
        .distinct()
        if v
    )


def client_stats(client):
    """단일 고객사의 카드 통계 (리스트용과 동일 집계)."""
    one = list_clients_with_stats(client.organization).filter(pk=client.pk).first()
    if not one:
        return {"offers": 0, "success": 0, "active": 0, "placed": 0}
    return {
        "offers": one.offers_count,
        "success": one.success_count,
        "active": one.active_count,
        "placed": one.placed_count,
    }


def client_projects(client, *, status_filter="all"):
    qs = client.projects.all().order_by("-created_at")
    if status_filter == "active":
        return qs.filter(status="open")
    if status_filter == "closed":
        return qs.filter(status="closed")
    return qs
```

- [ ] **Step 3: client_create 서비스 테스트**

`tests/test_clients_create.py`:

```python
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import Organization
from clients.models import Client
from clients.services.client_create import (
    apply_logo_upload,
    normalize_contact_persons,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org")


def test_normalize_contact_persons_drops_empty_rows():
    raw = [
        {"name": "A", "position": "CEO", "phone": "", "email": ""},
        {"name": "", "position": "", "phone": "", "email": ""},
        {"name": "  ", "position": "x", "phone": "", "email": ""},
        {"name": "B", "position": "", "phone": "010", "email": ""},
    ]
    out = normalize_contact_persons(raw)
    assert len(out) == 2
    assert out[0]["name"] == "A"
    assert out[1]["name"] == "B"


def test_normalize_contact_persons_preserves_schema():
    raw = [{"name": "A", "position": "CEO", "phone": "010", "email": "a@x.com", "extra": "drop"}]
    out = normalize_contact_persons(raw)
    assert set(out[0].keys()) == {"name", "position", "phone", "email"}


@pytest.mark.django_db
def test_apply_logo_upload_saves_file(org):
    c = Client.objects.create(organization=org, name="A")
    f = SimpleUploadedFile("logo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, content_type="image/png")
    apply_logo_upload(c, f)
    c.refresh_from_db()
    assert c.logo.name.startswith("clients/logos/")


@pytest.mark.django_db
def test_apply_logo_upload_delete_flag(org):
    c = Client.objects.create(organization=org, name="A")
    f = SimpleUploadedFile("logo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, content_type="image/png")
    apply_logo_upload(c, f)
    apply_logo_upload(c, None, delete=True)
    c.refresh_from_db()
    assert not c.logo
```

- [ ] **Step 4: client_create 서비스 구현**

`clients/services/client_create.py`:

```python
from pathlib import Path

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".svg", ".webp"}
MAX_BYTES = 2 * 1024 * 1024


def normalize_contact_persons(raw):
    """빈 행(이름 공란)을 제거하고 스키마를 정규화."""
    out = []
    for row in raw or []:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        out.append({
            "name": name,
            "position": (row.get("position") or "").strip(),
            "phone": (row.get("phone") or "").strip(),
            "email": (row.get("email") or "").strip(),
        })
    return out


def apply_logo_upload(client, uploaded_file, *, delete=False):
    """새 로고 저장. delete=True 면 기존 파일 제거."""
    if delete:
        if client.logo:
            client.logo.delete(save=False)
        client.logo = None
        client.save(update_fields=["logo"])
        return

    if uploaded_file is None:
        return

    # 기존 파일이 있으면 먼저 삭제
    if client.logo:
        client.logo.delete(save=False)

    client.logo = uploaded_file
    client.save(update_fields=["logo"])


def validate_logo_file(uploaded_file):
    """form.clean_logo() 에서 호출. 문제 있으면 ValueError."""
    if uploaded_file is None:
        return
    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"허용되지 않는 파일 형식입니다 ({ext}).")
    if uploaded_file.size > MAX_BYTES:
        raise ValueError("2MB 이하 이미지만 업로드할 수 있습니다.")
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
uv run pytest tests/test_clients_queries.py tests/test_clients_create.py -v
```

Expected: all passed.

- [ ] **Step 6: 커밋**

```bash
git add clients/services/ tests/test_clients_queries.py tests/test_clients_create.py
git commit -m "feat(clients): client_queries helpers + client_create service (contacts/logo)"
```

---

## Task 9: Templatetags (로고·배지·initials)

**Files:**
- Create: `clients/templatetags/__init__.py` (없으면)
- Create: `clients/templatetags/clients_tags.py`
- Create: `tests/test_clients_templatetags.py`

- [ ] **Step 1: 디렉터리 확인·생성**

```bash
test -f clients/templatetags/__init__.py || (mkdir -p clients/templatetags && touch clients/templatetags/__init__.py)
```

- [ ] **Step 2: 실패 테스트 작성**

`tests/test_clients_templatetags.py`:

```python
import pytest

from accounts.models import Organization
from clients.models import Client
from clients.templatetags.clients_tags import (
    client_initials,
    logo_class,
    size_badge_class,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org")


def test_size_badge_class_mapping():
    assert size_badge_class("대기업") == "badge enterprise"
    assert size_badge_class("중견") == "badge midcap"
    assert size_badge_class("중소") == "badge sme"
    assert size_badge_class("외국계") == "badge foreign"
    assert size_badge_class("스타트업") == "badge startup"
    assert size_badge_class("") == ""
    assert size_badge_class(None) == ""


def test_client_initials_single_word():
    assert client_initials("SKBP") == "SK"


def test_client_initials_korean():
    assert client_initials("한독") == "한독"


def test_client_initials_long():
    assert client_initials("Vatech 그룹") == "VA"


@pytest.mark.django_db
def test_logo_class_deterministic(org):
    c1 = Client.objects.create(organization=org, name="A")
    c2 = Client.objects.create(organization=org, name="B")
    # same client always returns same class
    assert logo_class(c1) == logo_class(c1)
    # class is in valid range
    assert logo_class(c1) in {f"client-logo-{i}" for i in range(1, 9)}
```

- [ ] **Step 3: 테스트 실패 확인**

```bash
uv run pytest tests/test_clients_templatetags.py -v
```

Expected: ImportError.

- [ ] **Step 4: templatetag 구현**

`clients/templatetags/clients_tags.py`:

```python
from django import template

register = template.Library()

SIZE_BADGE_MAP = {
    "대기업": "badge enterprise",
    "중견": "badge midcap",
    "중소": "badge sme",
    "외국계": "badge foreign",
    "스타트업": "badge startup",
}


@register.filter
def size_badge_class(size):
    if not size:
        return ""
    return SIZE_BADGE_MAP.get(size, "")


@register.filter
def client_initials(name):
    if not name:
        return ""
    s = name.strip()
    # 공백 제거한 앞 2자를 대문자로
    first_two = "".join(s.split())[:2]
    return first_two.upper() if first_two.isascii() else first_two


@register.simple_tag
def logo_class(client):
    # pk(uuid) 의 첫 바이트를 8로 나눈 나머지로 1~8 선택
    raw = str(client.pk).replace("-", "")
    bucket = (int(raw[:2], 16) % 8) + 1
    return f"client-logo-{bucket}"
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
uv run pytest tests/test_clients_templatetags.py -v
```

Expected: 5 passed.

- [ ] **Step 6: 커밋**

```bash
git add clients/templatetags/ tests/test_clients_templatetags.py
git commit -m "feat(clients): templatetags for logo gradient / initials / size badge"
```

---

## Task 10: CSS — 그라디언트·배지·칩·통계 유틸

**Files:**
- Modify: `static/css/input.css`

- [ ] **Step 1: 유틸리티 추가**

`static/css/input.css` 의 `@layer components` 블록 안에 추가 (존재하는 `.eyebrow` / `.tag` 근처):

```css
/* Client card — category chips */
.cat-chip {
  @apply inline-flex items-center shrink-0 rounded-full text-xs font-semibold;
  padding: 9px 18px;
  color: #475569;
  background: transparent;
  border: 1.5px solid transparent;
  white-space: nowrap;
  transition: all .15s ease;
}
.cat-chip:hover { background: #F1F5F9; color: #0F172A; }
.cat-chip.is-active { background: #334155; color: #fff; }
.cat-chip[aria-disabled="true"] { opacity: 0.45; pointer-events: none; }

/* Client card — size badges */
.badge.enterprise { background: #F1F5F9; color: #334155; }
.badge.midcap     { background: #DBEAFE; color: #1E40AF; }
.badge.sme        { background: #FFEDD5; color: #9A3412; }
.badge.foreign    { background: #EDE9FE; color: #5B21B6; }
.badge.startup    { background: #DCFCE7; color: #166534; }

/* Client card — meta tags */
.meta-tag {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; border-radius: 6px;
  font-size: 11px; font-weight: 500;
  color: #475569; background: #F1F5F9;
}

/* Client card — stat block */
.stat {
  display: flex; flex-direction: column;
  padding: 10px 0;
}
.stat + .stat { border-left: 1px solid #F1F5F9; padding-left: 16px; }
.stat .num { font-size: 20px; font-weight: 800; line-height: 1; color: #0F172A; letter-spacing: -0.01em; }
.stat .num .unit { font-size: 11px; font-weight: 600; color: #94A3B8; margin-left: 2px; }
.stat .lbl { font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #94A3B8; margin-top: 6px; }

/* Client logo tile — 8 gradients */
.client-logo-tile {
  width: 56px; height: 56px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 800; font-size: 16px;
  flex-shrink: 0; letter-spacing: -0.02em;
  position: relative; overflow: hidden;
}
.client-logo-tile img {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  object-fit: contain;
  background: #ffffff;
  padding: 8px;
}
.client-logo-1 { background: linear-gradient(135deg, #60a5fa 0%, #1e3a8a 100%); }
.client-logo-2 { background: linear-gradient(135deg, #f87171 0%, #991b1b 100%); }
.client-logo-3 { background: linear-gradient(135deg, #93c5fd 0%, #1d4ed8 100%); }
.client-logo-4 { background: linear-gradient(135deg, #fcd34d 0%, #b45309 100%); }
.client-logo-5 { background: linear-gradient(135deg, #f9a8d4 0%, #9f1239 100%); }
.client-logo-6 { background: linear-gradient(135deg, #fdba74 0%, #c2410c 100%); }
.client-logo-7 { background: linear-gradient(135deg, #5eead4 0%, #115e59 100%); }
.client-logo-8 { background: linear-gradient(135deg, #86efac 0%, #15803d 100%); }

/* Horizontal scroll — hide scrollbar */
.hide-scrollbar::-webkit-scrollbar { display: none; }
.hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
```

- [ ] **Step 2: Tailwind 빌드 + 빠른 육안 확인**

```bash
npx tailwindcss -i static/css/input.css -o static/css/output.css
```

Expected: 에러 없이 빌드. 생성 CSS 에 `.client-logo-1` 등이 포함되는지 grep:

```bash
grep -c "client-logo-1" static/css/output.css
```

Expected: 1 이상.

- [ ] **Step 3: 커밋**

```bash
git add static/css/input.css static/css/output.css
git commit -m "feat(clients): css tokens for chips/badges/stats/logo gradients"
```

---

## Task 11: 리스트 페이지 — 기본 레이아웃 + 카드 partial

**Files:**
- Create: `clients/templates/clients/partials/client_card.html`
- Create: `clients/templates/clients/partials/client_list_page.html`
- Modify: `clients/templates/clients/client_list.html` (전면 재작성)
- Modify: `clients/views.py::client_list`
- Modify: `clients/urls.py`

- [ ] **Step 1: URL 추가**

`clients/urls.py` 의 `urlpatterns` 에 추가:

```python
path("page/", views.client_list_page, name="client_list_page"),
```

`client_list` 경로 바로 다음 줄.

- [ ] **Step 2: 뷰 재작성**

`clients/views.py` 상단 import 에 추가:

```python
from clients.services.client_queries import (
    available_regions,
    category_counts,
    list_clients_with_stats,
)
```

그리고 `client_list` / `client_list_page` 재작성:

```python
GRID_PAGE_SIZE = 9


def _parse_list_filters(request):
    """GET 파라미터에서 필터 kwargs 추출."""
    def _csv(key):
        v = request.GET.get(key, "").strip()
        return [x for x in v.split(",") if x] if v else None

    cat = request.GET.get("cat", "").strip()
    categories = [cat] if cat else None

    return {
        "categories": categories,
        "sizes": _csv("size"),
        "regions": _csv("region"),
        "offers_range": request.GET.get("offers") or None,
        "success_status": request.GET.get("success") or None,
    }


@login_required
@membership_required
def client_list(request):
    org = _get_org(request)
    filters = _parse_list_filters(request)
    qs = list_clients_with_stats(org, **filters)

    paginator = Paginator(qs, GRID_PAGE_SIZE)
    page_obj = paginator.get_page(1)

    return render(
        request,
        "clients/client_list.html",
        {
            "page_obj": page_obj,
            "total": qs.count(),
            "cat_counts": category_counts(org),
            "regions": available_regions(org),
            "filters": filters,
            "active_cat": request.GET.get("cat", ""),
        },
    )


@login_required
@membership_required
def client_list_page(request):
    """Infinite scroll 페이지 응답 (카드 + 다음 sentinel)."""
    org = _get_org(request)
    filters = _parse_list_filters(request)
    qs = list_clients_with_stats(org, **filters)
    paginator = Paginator(qs, GRID_PAGE_SIZE)
    page_number = int(request.GET.get("page", "2"))
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "clients/partials/client_list_page.html",
        {"page_obj": page_obj, "filters": filters},
    )
```

**기존 `q` 검색 파라미터 로직은 제거** — 전역 하단 검색바가 대체.

- [ ] **Step 3: 카드 partial 작성 (클릭 분할 포함)**

`clients/templates/clients/partials/client_card.html`:

```html
{% load clients_tags %}
<article class="col-span-4 bg-surface rounded-card shadow-card overflow-hidden relative">
  {# 케밥 메뉴 (owner only) — absolute top-right #}
  {% if membership and membership.role == "owner" %}
  <details class="absolute top-4 right-4 z-10" onclick="event.stopPropagation()">
    <summary class="list-none cursor-pointer w-8 h-8 rounded-full hover:bg-line flex items-center justify-center text-muted">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>
    </summary>
    <div class="absolute right-0 mt-1 w-32 bg-surface rounded-lg shadow-lift border border-hair py-1">
      <a href="{% url 'clients:client_update' client.pk %}"
         hx-get="{% url 'clients:client_update' client.pk %}" hx-target="#main-content" hx-push-url="true"
         class="block px-3 py-2 text-sm text-ink3 hover:bg-line">수정</a>
      <button type="button"
              hx-post="{% url 'clients:client_delete' client.pk %}"
              hx-confirm="이 고객사를 삭제하시겠어요?"
              hx-target="#main-content"
              class="w-full text-left px-3 py-2 text-sm text-danger hover:bg-line">삭제</button>
    </div>
  </details>
  {% endif %}

  {# 상단 영역: 회사 홈페이지 링크 (website 없으면 div) #}
  {% if client.website %}
  <a href="{{ client.website }}" target="_blank" rel="noopener" class="block p-6 pb-0 hover:bg-line/40 transition-colors">
  {% else %}
  <div class="p-6 pb-0">
  {% endif %}
    <div class="flex items-start gap-4">
      <div class="client-logo-tile {% logo_class client %}">
        {% if client.logo %}<img src="{{ client.logo.url }}" alt="{{ client.name }}" loading="lazy" />{% endif %}
        {{ client.name|client_initials }}
      </div>
      <div class="min-w-0 flex-1">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <h3 class="text-base font-bold tracking-tight">{{ client.name }}</h3>
              {% if client.size %}<span class="{{ client.size|size_badge_class }}">{{ client.get_size_display }}</span>{% endif %}
            </div>
            <p class="text-sm text-muted mt-1 truncate">
              <span class="font-semibold text-ink3">{{ client.get_industry_display }}</span>
              {% if client.region %}<span class="mx-1 text-faint">·</span>{{ client.region }}{% endif %}
            </p>
          </div>
          <div class="text-right shrink-0">
            <div class="text-2xl font-bold leading-none tnum">{{ client.active_count }}<span class="text-sm text-muted ml-0.5">건</span></div>
            <div class="eyebrow mt-1">Active</div>
          </div>
        </div>
      </div>
    </div>
  {% if client.website %}</a>{% else %}</div>{% endif %}

  {# 하단 영역: 프로젝트 리스트 (상세) 로 이동 #}
  <a hx-get="{% url 'clients:client_detail' client.pk %}" hx-target="#main-content" hx-push-url="true"
     href="{% url 'clients:client_detail' client.pk %}"
     class="block px-6 pb-6 mt-5 pt-5 border-t border-line hover:bg-line/40 transition-colors">
    {% if client.description %}
    <p class="text-sm text-ink3 leading-relaxed line-clamp-2">{{ client.description }}</p>
    {% else %}
    <p class="text-sm text-faint leading-relaxed italic">설명이 아직 등록되지 않았습니다</p>
    {% endif %}

    {% if client.offers_count %}
    <div class="grid grid-cols-3 gap-1 mt-4">
      <div class="stat"><div class="num">{{ client.offers_count }}</div><div class="lbl">Offers</div></div>
      <div class="stat"><div class="num">{{ client.success_count }}</div><div class="lbl">Success</div></div>
      <div class="stat"><div class="num">{{ client.placed_count }}<span class="unit">명</span></div><div class="lbl">Placed</div></div>
    </div>
    {% else %}
    <div class="mt-4 text-xs font-semibold text-faint uppercase tracking-widest">거래 이력 없음</div>
    {% endif %}

    <div class="flex items-center justify-between mt-5 pt-4 border-t border-line">
      <div class="flex items-center gap-2 flex-wrap">
        {% if client.contact_persons %}<span class="meta-tag">{{ client.contact_persons|length }}인 담당</span>{% endif %}
      </div>
      <div class="flex items-center gap-3 text-faint pointer-events-none opacity-60">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon stroke-linecap="round" stroke-linejoin="round" points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
      </div>
    </div>
  </a>
</article>
```

- [ ] **Step 4: 리스트 페이지 파편(Infinite scroll 응답용)**

`clients/templates/clients/partials/client_list_page.html`:

```html
{% load clients_tags %}
{% for client in page_obj %}
  {% include "clients/partials/client_card.html" %}
{% endfor %}

{% if page_obj.has_next %}
<div class="col-span-12 py-6 text-center"
     hx-get="{% url 'clients:client_list_page' %}?page={{ page_obj.next_page_number }}{% for k, v in request.GET.items %}{% if k != 'page' %}&{{ k }}={{ v }}{% endif %}{% endfor %}"
     hx-trigger="revealed"
     hx-swap="outerHTML">
  <div class="inline-flex items-center gap-2 text-xs font-semibold text-faint uppercase tracking-widest">더 불러오는 중…</div>
</div>
{% else %}
<div class="col-span-12 py-6 text-center text-xs font-semibold text-faint uppercase tracking-widest">모두 불러왔어요</div>
{% endif %}
```

- [ ] **Step 5: client_list.html 재작성 (헤더 + 칩 + grid 컨테이너)**

`clients/templates/clients/client_list.html` 전체 교체:

```html
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}
{% load clients_tags %}

{% block title %}Clients — synco{% endblock %}
{% block breadcrumb_current %}Clients{% endblock %}
{% block page_title %}Clients{% endblock %}

{% block content %}
<div class="px-8 py-8 space-y-6 pb-32">

  {# Page header #}
  <section class="flex items-end justify-between gap-4">
    <div>
      <div class="eyebrow">Active Corporate Relationships</div>
      <h2 class="text-3xl font-bold tracking-tight mt-1">Clients</h2>
      <p class="text-sm text-muted mt-1">
        등록된 고객사 <span class="font-semibold text-ink tnum">{{ total }}</span>곳의 거래 이력과 진행 현황을 관리하세요
      </p>
    </div>
    <div class="flex items-center gap-2">
      <button type="button" id="filter-toggle"
              class="inline-flex items-center gap-2 px-4 h-10 rounded-lg border border-hair bg-surface text-sm font-semibold text-ink3 hover:bg-line transition-colors">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon stroke-linecap="round" stroke-linejoin="round" points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
        Filters
      </button>
      {% if membership and membership.role == "owner" %}
      <a href="{% url 'clients:client_create' %}"
         hx-get="{% url 'clients:client_create' %}" hx-target="#main-content" hx-push-url="true"
         class="inline-flex items-center gap-2 px-4 h-10 rounded-lg bg-ink3 text-white text-sm font-semibold hover:bg-ink2 transition-colors">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><line stroke-linecap="round" stroke-linejoin="round" x1="12" y1="5" x2="12" y2="19"/><line stroke-linecap="round" stroke-linejoin="round" x1="5" y1="12" x2="19" y2="12"/></svg>
        Add Client
      </a>
      {% endif %}
    </div>
  </section>

  {# Filter dropdown panel (Task 14 에서 채움) #}
  <section id="filter-panel" class="hidden">
    {% include "clients/partials/client_filter_dropdown.html" %}
  </section>

  {# Category chips #}
  <section>
    <div class="overflow-x-auto hide-scrollbar -mx-1">
      <div class="flex gap-2 px-1">
        <button type="button"
                hx-get="{% url 'clients:client_list' %}" hx-target="#main-content" hx-push-url="true"
                class="cat-chip {% if not active_cat %}is-active{% endif %}">전체 · {{ total }}</button>
        {% for cat in industry_categories %}
        <button type="button"
                hx-get="{% url 'clients:client_list' %}?cat={{ cat.name }}" hx-target="#main-content" hx-push-url="true"
                class="cat-chip {% if active_cat == cat.name %}is-active{% endif %}"
                {% if cat_counts|get_item:cat.name == 0 %}aria-disabled="true"{% endif %}>
          {{ cat.label }} · {{ cat_counts|get_item:cat.name }}
        </button>
        {% endfor %}
      </div>
    </div>
  </section>

  {# Card grid + infinite scroll #}
  <section id="client-grid" class="grid grid-cols-12 gap-6">
    {% for client in page_obj %}
      {% include "clients/partials/client_card.html" %}
    {% empty %}
      <div class="col-span-12 bg-white rounded-card shadow-card p-12 text-center">
        {% if active_cat or filters.sizes or filters.regions or filters.offers_range or filters.success_status %}
          <p class="text-sm font-medium text-muted">조건에 해당하는 고객사가 없습니다</p>
        {% elif membership and membership.role == 'owner' %}
          <p class="text-sm font-medium text-muted mb-5">등록된 고객사가 없습니다</p>
          <a href="{% url 'clients:client_create' %}"
             hx-get="{% url 'clients:client_create' %}" hx-target="#main-content" hx-push-url="true"
             class="inline-flex items-center gap-2 px-4 h-10 rounded-lg bg-ink3 text-white text-sm font-semibold hover:bg-ink2">첫 고객사 등록</a>
        {% else %}
          <p class="text-sm font-medium text-muted">등록된 고객사가 없습니다</p>
        {% endif %}
      </div>
    {% endfor %}

    {% if page_obj.has_next %}
    <div class="col-span-12 py-6 text-center"
         hx-get="{% url 'clients:client_list_page' %}?page=2{% for k, v in request.GET.items %}&{{ k }}={{ v }}{% endfor %}"
         hx-trigger="revealed"
         hx-swap="outerHTML">
      <div class="inline-flex items-center gap-2 text-xs font-semibold text-faint uppercase tracking-widest">더 불러오는 중…</div>
    </div>
    {% endif %}
  </section>

</div>

<script>
  (function() {
    var toggle = document.getElementById('filter-toggle');
    var panel = document.getElementById('filter-panel');
    if (toggle && panel) {
      toggle.addEventListener('click', function() { panel.classList.toggle('hidden'); });
    }
  })();
</script>
{% endblock %}
```

이 템플릿은 `industry_categories` 와 `get_item` 필터를 참조 — 다음 step 에서 추가.

- [ ] **Step 6: industry_categories 컨텍스트 + get_item 필터 추가**

`clients/templatetags/clients_tags.py` 에 추가:

```python
@register.filter
def get_item(d, key):
    try:
        return d.get(key, 0)
    except AttributeError:
        return 0
```

`clients/views.py::client_list` 의 `render(...)` 컨텍스트에 추가:

```python
from clients.models import IndustryCategory
```

(아직 import 안 했다면 상단에 추가)

컨텍스트 딕셔너리에:

```python
"industry_categories": [
    {"name": c.name, "label": c.label} for c in IndustryCategory
],
```

- [ ] **Step 7: 런타임 스모크 테스트**

```bash
uv run python manage.py runserver 0.0.0.0:8000 &
sleep 2
curl -s http://localhost:8000/clients/ -o /tmp/clients.html -w "%{http_code}\n"
kill %1
```

Expected: `200` 또는 로그인 필요라면 `302`. 템플릿 렌더 에러 없음.

- [ ] **Step 8: 커밋**

```bash
git add clients/templates/ clients/views.py clients/urls.py clients/templatetags/clients_tags.py
git commit -m "feat(clients): list page redesign — grid cards, category chips, infinite scroll"
```

---

## Task 12: 리스트 페이지 뷰 테스트

**Files:**
- Create: `tests/test_clients_views_list.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_clients_views_list.py`:

```python
import pytest
from django.urls import reverse

from accounts.models import Organization, Membership, User
from clients.models import Client, IndustryCategory
from projects.models import Project


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org")


@pytest.fixture
def owner(org):
    u = User.objects.create_user(username="owner", password="x")
    Membership.objects.create(user=u, organization=org, role="owner")
    return u


@pytest.fixture
def owner_client(client, owner):
    client.force_login(owner)
    return client


@pytest.mark.django_db
def test_list_renders_header_and_empty_state(owner_client):
    resp = owner_client.get(reverse("clients:client_list"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Clients" in body
    assert "등록된 고객사" in body


@pytest.mark.django_db
def test_list_renders_cards(org, owner_client):
    Client.objects.create(organization=org, name="SKBP", industry=IndustryCategory.BIO_PHARMA.value)
    resp = owner_client.get(reverse("clients:client_list"))
    assert "SKBP" in resp.content.decode()


@pytest.mark.django_db
def test_list_category_filter(org, owner_client):
    Client.objects.create(organization=org, name="Bio", industry=IndustryCategory.BIO_PHARMA.value)
    Client.objects.create(organization=org, name="IT", industry=IndustryCategory.IT_SW.value)
    resp = owner_client.get(reverse("clients:client_list") + "?cat=BIO_PHARMA")
    body = resp.content.decode()
    assert "Bio" in body
    assert "IT" not in body


@pytest.mark.django_db
def test_list_size_filter(org, owner_client):
    Client.objects.create(organization=org, name="Big", size="대기업")
    Client.objects.create(organization=org, name="Small", size="중소")
    resp = owner_client.get(reverse("clients:client_list") + "?size=대기업")
    body = resp.content.decode()
    assert "Big" in body
    assert "Small" not in body


@pytest.mark.django_db
def test_list_page_endpoint_returns_next_cards(org, owner_client):
    # 10 건 생성, 페이지 2 (10번째만 나와야 함. 페이지 크기 9)
    for i in range(10):
        Client.objects.create(organization=org, name=f"C{i:02d}")
    resp = owner_client.get(reverse("clients:client_list_page") + "?page=2")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert body.count("client-logo-tile") == 1


@pytest.mark.django_db
def test_list_active_count_shown(org, owner_client):
    c = Client.objects.create(organization=org, name="A")
    Project.objects.create(client=c, organization=org, title="P", status="open")
    resp = owner_client.get(reverse("clients:client_list"))
    body = resp.content.decode()
    # 카드 우상단 Active 카운트
    assert "1" in body
    assert "Active" in body


@pytest.mark.django_db
def test_member_cannot_see_add_button(org, db, client):
    member = User.objects.create_user(username="m", password="x")
    Membership.objects.create(user=member, organization=org, role="member")
    client.force_login(member)
    resp = client.get(reverse("clients:client_list"))
    assert "Add Client" not in resp.content.decode()
```

- [ ] **Step 2: 테스트 통과 확인**

```bash
uv run pytest tests/test_clients_views_list.py -v
```

Expected: 7 passed.

- [ ] **Step 3: 커밋**

```bash
git add tests/test_clients_views_list.py
git commit -m "test(clients): list view coverage (header/cards/filters/infinite scroll)"
```

---

## Task 13: 필터 드롭다운 UI + 적용 로직

**Files:**
- Create: `clients/templates/clients/partials/client_filter_dropdown.html`

- [ ] **Step 1: 드롭다운 partial 작성**

`clients/templates/clients/partials/client_filter_dropdown.html`:

```html
<form method="get" action="{% url 'clients:client_list' %}"
      hx-get="{% url 'clients:client_list' %}" hx-target="#main-content" hx-push-url="true"
      class="bg-surface rounded-card shadow-lift p-6 space-y-5">
  {% if active_cat %}<input type="hidden" name="cat" value="{{ active_cat }}">{% endif %}

  <div>
    <div class="eyebrow mb-3">기업 규모</div>
    <div class="flex flex-wrap gap-2">
      {% for s in sizes %}
      <label class="cursor-pointer">
        <input type="checkbox" name="size" value="{{ s }}" class="hidden peer"
               {% if filters.sizes and s in filters.sizes %}checked{% endif %}>
        <span class="cat-chip peer-checked:is-active">{{ s }}</span>
      </label>
      {% endfor %}
    </div>
  </div>

  <div>
    <div class="eyebrow mb-3">지역</div>
    <div class="flex flex-wrap gap-2">
      {% for r in regions %}
      <label class="cursor-pointer">
        <input type="checkbox" name="region" value="{{ r }}" class="hidden peer"
               {% if filters.regions and r in filters.regions %}checked{% endif %}>
        <span class="cat-chip peer-checked:is-active">{{ r }}</span>
      </label>
      {% endfor %}
    </div>
  </div>

  <div>
    <div class="eyebrow mb-3">거래 건수</div>
    <div class="flex flex-wrap gap-2">
      {% for opt in offers_options %}
      <label class="cursor-pointer">
        <input type="radio" name="offers" value="{{ opt.value }}" class="hidden peer"
               {% if filters.offers_range == opt.value %}checked{% endif %}>
        <span class="cat-chip peer-checked:is-active">{{ opt.label }}</span>
      </label>
      {% endfor %}
    </div>
  </div>

  <div>
    <div class="eyebrow mb-3">성사 이력</div>
    <div class="flex flex-wrap gap-2">
      {% for opt in success_options %}
      <label class="cursor-pointer">
        <input type="radio" name="success" value="{{ opt.value }}" class="hidden peer"
               {% if filters.success_status == opt.value %}checked{% endif %}>
        <span class="cat-chip peer-checked:is-active">{{ opt.label }}</span>
      </label>
      {% endfor %}
    </div>
  </div>

  <div class="flex items-center justify-end gap-3 pt-4 border-t border-line">
    <a href="{% url 'clients:client_list' %}{% if active_cat %}?cat={{ active_cat }}{% endif %}"
       hx-get="{% url 'clients:client_list' %}{% if active_cat %}?cat={{ active_cat }}{% endif %}"
       hx-target="#main-content" hx-push-url="true"
       class="text-sm text-muted hover:text-ink3">초기화</a>
    <button type="submit" class="px-4 h-10 rounded-lg bg-ink3 text-white text-sm font-semibold hover:bg-ink2">적용하기</button>
  </div>
</form>
```

**참고:** `peer-checked:is-active` 패턴은 Tailwind peer modifier 로 동작. `.cat-chip.is-active` 스타일 이미 정의됨.

체크박스의 CSV 변환은 checkbox 가 다중 선택되면 `?size=대기업&size=중소` 형태로 전송됨 — `_parse_list_filters` 에서 `request.GET.getlist("size")` 로 바꿔야 함. 수정:

- [ ] **Step 2: _parse_list_filters 수정 (getlist 지원)**

`clients/views.py::_parse_list_filters`:

```python
def _parse_list_filters(request):
    cat = request.GET.get("cat", "").strip()
    categories = [cat] if cat else None

    sizes = request.GET.getlist("size") or None
    regions = request.GET.getlist("region") or None

    return {
        "categories": categories,
        "sizes": sizes,
        "regions": regions,
        "offers_range": request.GET.get("offers") or None,
        "success_status": request.GET.get("success") or None,
    }
```

- [ ] **Step 3: 필터 옵션을 뷰에서 컨텍스트로 제공**

`clients/views.py::client_list` 의 컨텍스트에 추가:

```python
from clients.models import Client as _ClientModel  # already imported

SIZE_CHOICES = [s.value for s in _ClientModel.Size]
OFFERS_OPTIONS = [
    {"value": "", "label": "전체"},
    {"value": "0", "label": "0건"},
    {"value": "1-5", "label": "1–5건"},
    {"value": "6-10", "label": "6–10건"},
    {"value": "10+", "label": "10건+"},
]
SUCCESS_OPTIONS = [
    {"value": "", "label": "전체"},
    {"value": "has", "label": "성사 있음"},
    {"value": "none", "label": "성사 없음"},
    {"value": "no_offers", "label": "거래 없음"},
]
```

(뷰 모듈 상단 상수로 추가)

컨텍스트 딕셔너리에:

```python
"sizes": SIZE_CHOICES,
"offers_options": OFFERS_OPTIONS,
"success_options": SUCCESS_OPTIONS,
```

- [ ] **Step 4: 필터 UI 스모크**

리스트 페이지에서 [Filters] 버튼 클릭 → 패널 펼침 → 규모/지역 선택 → [적용하기] → URL 에 `?size=...` 포함 + grid 필터링되는지 브라우저에서 확인. (수동 QA, 테스트 불필요)

- [ ] **Step 5: 뷰 테스트 업데이트**

`tests/test_clients_views_list.py` 의 `test_list_size_filter` 가 `?size=대기업` (싱글)로 되어있는데 getlist 전환 후에도 동작함 — 그대로 유지.

- [ ] **Step 6: 커밋**

```bash
git add clients/templates/clients/partials/client_filter_dropdown.html clients/views.py
git commit -m "feat(clients): filter dropdown panel (size/region/offers/success)"
```

---

## Task 14: 상세 페이지 — 프로필 카드 + 좌측(담당자/계약)

**Files:**
- Modify: `clients/templates/clients/client_detail.html` (전면 재작성)
- Create: `clients/templates/clients/partials/client_profile_header.html`
- Create: `clients/templates/clients/partials/client_contacts_card.html`
- Modify: `clients/templates/clients/partials/contract_section.html` (재스타일)
- Modify: `clients/views.py::client_detail`

- [ ] **Step 1: 뷰에 통계·프로젝트 쿼리 주입**

`clients/views.py::client_detail` 교체:

```python
from clients.services.client_queries import client_projects, client_stats


@login_required
@membership_required
def client_detail(request, pk):
    org = _get_org(request)
    client = get_object_or_404(Client, pk=pk, organization=org)
    stats = client_stats(client)
    projects = client_projects(client, status_filter="all")[:20]

    return render(
        request,
        "clients/client_detail.html",
        {
            "client": client,
            "contracts": client.contracts.all(),
            "projects": projects,
            "stats": stats,
            "contract_form": ContractForm(),
            "project_status_filter": "all",
        },
    )
```

- [ ] **Step 2: 프로필 헤더 partial**

`clients/templates/clients/partials/client_profile_header.html`:

```html
{% load clients_tags %}
<section class="bg-surface rounded-card shadow-card p-8 relative">
  {% if membership and membership.role == "owner" %}
  <details class="absolute top-6 right-6">
    <summary class="list-none cursor-pointer w-8 h-8 rounded-full hover:bg-line flex items-center justify-center text-muted">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>
    </summary>
    <div class="absolute right-0 mt-1 w-32 bg-surface rounded-lg shadow-lift border border-hair py-1 z-10">
      <a href="{% url 'clients:client_update' client.pk %}"
         hx-get="{% url 'clients:client_update' client.pk %}" hx-target="#main-content" hx-push-url="true"
         class="block px-3 py-2 text-sm text-ink3 hover:bg-line">수정</a>
      <button type="button"
              hx-post="{% url 'clients:client_delete' client.pk %}"
              hx-confirm="이 고객사를 삭제하시겠어요?"
              hx-target="#main-content"
              class="w-full text-left px-3 py-2 text-sm text-danger hover:bg-line">삭제</button>
    </div>
  </details>
  {% endif %}

  <div class="flex items-start gap-6">
    <div class="client-logo-tile {% logo_class client %}" style="width:80px;height:80px;font-size:20px;border-radius:16px;">
      {% if client.logo %}<img src="{{ client.logo.url }}" alt="" />{% endif %}
      {{ client.name|client_initials }}
    </div>
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2 flex-wrap">
        <h1 class="text-2xl font-bold tracking-tight">{{ client.name }}</h1>
        {% if client.size %}<span class="{{ client.size|size_badge_class }}">{{ client.get_size_display }}</span>{% endif %}
      </div>
      <p class="text-sm text-muted mt-1">
        <span class="font-semibold text-ink3">{{ client.get_industry_display }}</span>
        {% if client.region %}<span class="mx-1 text-faint">·</span>{{ client.region }}{% endif %}
      </p>
      {% if client.website %}
      <a href="{{ client.website }}" target="_blank" rel="noopener" class="inline-flex items-center gap-1.5 text-sm text-ink3 hover:underline mt-2">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle stroke-linecap="round" stroke-linejoin="round" cx="12" cy="12" r="10"/><line stroke-linecap="round" stroke-linejoin="round" x1="2" y1="12" x2="22" y2="12"/><path stroke-linecap="round" stroke-linejoin="round" d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
        {{ client.website|cut:"https://"|cut:"http://" }}
      </a>
      {% endif %}
      {% if client.description %}
      <p class="text-sm text-ink3 leading-relaxed mt-4 max-w-[720px]">{{ client.description }}</p>
      {% endif %}
    </div>
  </div>

  <div class="grid grid-cols-4 gap-4 mt-6 pt-6 border-t border-line">
    <div class="stat"><div class="num">{{ stats.offers }}</div><div class="lbl">Offers</div></div>
    <div class="stat"><div class="num">{{ stats.success }}</div><div class="lbl">Success</div></div>
    <div class="stat"><div class="num">{{ stats.placed }}<span class="unit">명</span></div><div class="lbl">Placed</div></div>
    <div class="stat"><div class="num">{{ stats.active }}</div><div class="lbl">Active</div></div>
  </div>
</section>
```

- [ ] **Step 3: 담당자 카드 partial**

`clients/templates/clients/partials/client_contacts_card.html`:

```html
<section class="bg-surface rounded-card shadow-card p-6">
  <div class="flex items-center justify-between mb-4">
    <div class="eyebrow">담당자</div>
    {% if membership and membership.role == "owner" and client.contact_persons %}
    <a href="{% url 'clients:client_update' client.pk %}#contacts"
       hx-get="{% url 'clients:client_update' client.pk %}" hx-target="#main-content" hx-push-url="true"
       class="text-xs font-semibold text-muted hover:text-ink3">편집</a>
    {% endif %}
  </div>

  {% if client.contact_persons %}
  <ul class="space-y-3">
    {% for cp in client.contact_persons %}
    <li class="flex items-start gap-3">
      <div class="w-7 h-7 rounded-full bg-ink2 text-white text-xs font-bold flex items-center justify-center shrink-0">
        {{ cp.name|slice:":1" }}
      </div>
      <div class="min-w-0 flex-1">
        <div class="text-sm font-semibold">{{ cp.name }}</div>
        {% if cp.position %}<div class="text-xs text-muted">{{ cp.position }}</div>{% endif %}
        <div class="mt-1 flex flex-col gap-0.5">
          {% if cp.email %}<a href="mailto:{{ cp.email }}" class="text-xs text-ink3 hover:underline">{{ cp.email }}</a>{% endif %}
          {% if cp.phone %}<a href="tel:{{ cp.phone }}" class="text-xs text-ink3 hover:underline tnum">{{ cp.phone }}</a>{% endif %}
        </div>
      </div>
    </li>
    {% endfor %}
  </ul>
  {% else %}
  <p class="text-sm text-faint italic">등록된 담당자 없음</p>
  {% if membership and membership.role == "owner" %}
  <a href="{% url 'clients:client_update' client.pk %}#contacts"
     hx-get="{% url 'clients:client_update' client.pk %}" hx-target="#main-content" hx-push-url="true"
     class="inline-block mt-3 text-xs font-semibold text-ink3 hover:text-ink2">+ 담당자 추가</a>
  {% endif %}
  {% endif %}
</section>
```

- [ ] **Step 4: contract_section.html 재스타일**

기존 파일을 디자인 시스템 토큰으로 수정. 구조 유지, 클래스만 교체:
- `bg-white` → `bg-surface`
- `rounded-xl` → `rounded-card`
- `border-slate-100` → `border-hair`
- 버튼 스타일을 Task 11의 Add Client 버튼과 동일한 `px-4 h-10 rounded-lg` 패턴으로.

(기존 내용이 보존되도록 diff 형태로 적용. 만약 파일이 크면 section 단위로.)

- [ ] **Step 5: client_detail.html 재작성**

```html
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}
{% load clients_tags %}

{% block title %}{{ client.name }} — Clients{% endblock %}
{% block breadcrumb_current %}{{ client.name }}{% endblock %}
{% block page_title %}{{ client.name }}{% endblock %}

{% block content %}
<div class="px-8 py-8 space-y-6 pb-32">

  <a href="{% url 'clients:client_list' %}"
     hx-get="{% url 'clients:client_list' %}" hx-target="#main-content" hx-push-url="true"
     class="inline-flex items-center gap-2 text-xs font-semibold text-muted hover:text-ink3">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/></svg>
    Back to Clients
  </a>

  {% include "clients/partials/client_profile_header.html" %}

  <div class="grid grid-cols-12 gap-6">
    <div class="col-span-4 space-y-6">
      {% include "clients/partials/client_contacts_card.html" %}
      {% include "clients/partials/contract_section.html" %}
    </div>
    <div class="col-span-8">
      {# 프로젝트 리스트 — Task 15 에서 주입 #}
      <div id="client-projects-panel">
        {% include "clients/partials/client_projects_panel.html" %}
      </div>
    </div>
  </div>

  {% if client.notes %}
  <section class="bg-surface rounded-card shadow-card p-6">
    <div class="flex items-center justify-between mb-3">
      <div class="eyebrow">메모</div>
      {% if membership and membership.role == "owner" %}
      <a href="{% url 'clients:client_update' client.pk %}#notes"
         hx-get="{% url 'clients:client_update' client.pk %}" hx-target="#main-content" hx-push-url="true"
         class="text-xs font-semibold text-muted hover:text-ink3">편집</a>
      {% endif %}
    </div>
    <p class="text-sm text-ink3 whitespace-pre-line">{{ client.notes }}</p>
  </section>
  {% endif %}

</div>
{% endblock %}
```

- [ ] **Step 6: 빌드 스모크**

```bash
uv run python manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 7: 커밋**

```bash
git add clients/templates/ clients/views.py
git commit -m "feat(clients): detail page — profile header + contacts + contract section"
```

---

## Task 15: 상세 — 프로젝트 리스트 패널 (세그먼티드 컨트롤 + HTMX 교체)

**Files:**
- Create: `clients/templates/clients/partials/client_projects_panel.html`
- Modify: `clients/views.py` (신규 `client_projects_panel` 뷰)
- Modify: `clients/urls.py`

- [ ] **Step 1: URL 추가**

`clients/urls.py`:

```python
path("<uuid:pk>/projects/", views.client_projects_panel, name="client_projects_panel"),
```

- [ ] **Step 2: 뷰 추가**

`clients/views.py`:

```python
@login_required
@membership_required
def client_projects_panel(request, pk):
    org = _get_org(request)
    client = get_object_or_404(Client, pk=pk, organization=org)
    status_filter = request.GET.get("status", "all")
    if status_filter not in {"active", "closed", "all"}:
        status_filter = "all"
    projects = client_projects(client, status_filter=status_filter)[:20]
    return render(
        request,
        "clients/partials/client_projects_panel.html",
        {
            "client": client,
            "projects": projects,
            "project_status_filter": status_filter,
            "stats": client_stats(client),
        },
    )
```

- [ ] **Step 3: partial 작성**

`clients/templates/clients/partials/client_projects_panel.html`:

```html
<section class="bg-surface rounded-card shadow-card p-6">
  <div class="flex items-end justify-between mb-5">
    <div>
      <div class="eyebrow">Engagements</div>
      <h3 class="text-lg font-semibold mt-1">프로젝트 <span class="text-muted tnum">{{ stats.offers }}</span></h3>
    </div>
    <div class="inline-flex rounded-lg border border-hair overflow-hidden text-xs font-semibold">
      <button type="button"
              hx-get="{% url 'clients:client_projects_panel' client.pk %}?status=active"
              hx-target="#client-projects-panel" hx-swap="innerHTML"
              class="px-3 h-8 {% if project_status_filter == 'active' %}bg-ink3 text-white{% else %}bg-surface text-muted hover:bg-line{% endif %}">
        진행중 {{ stats.active }}
      </button>
      <button type="button"
              hx-get="{% url 'clients:client_projects_panel' client.pk %}?status=closed"
              hx-target="#client-projects-panel" hx-swap="innerHTML"
              class="px-3 h-8 border-l border-hair {% if project_status_filter == 'closed' %}bg-ink3 text-white{% else %}bg-surface text-muted hover:bg-line{% endif %}">
        완료
      </button>
      <button type="button"
              hx-get="{% url 'clients:client_projects_panel' client.pk %}?status=all"
              hx-target="#client-projects-panel" hx-swap="innerHTML"
              class="px-3 h-8 border-l border-hair {% if project_status_filter == 'all' %}bg-ink3 text-white{% else %}bg-surface text-muted hover:bg-line{% endif %}">
        전체 {{ stats.offers }}
      </button>
    </div>
  </div>

  {% if projects %}
  <ul class="space-y-2">
    {% for p in projects %}
    <li>
      <a href="{% url 'projects:project_detail' p.pk %}"
         hx-get="{% url 'projects:project_detail' p.pk %}" hx-target="#main-content" hx-push-url="true"
         class="flex items-center justify-between gap-4 px-4 py-3 rounded-lg hover:bg-line transition-colors">
        <div class="min-w-0 flex-1">
          <div class="text-sm font-semibold truncate">{{ p.title }}</div>
          <div class="text-xs text-muted mt-0.5">
            {{ p.get_phase_display }}
            <span class="mx-1 text-faint">·</span>
            {{ p.created_at|date:"Y-m-d" }}
          </div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          {% if p.status == "closed" %}
            {% if p.result == "success" %}
            <span class="badge" style="background:#DCFCE7;color:#166534;">성사</span>
            {% else %}
            <span class="badge" style="background:#F1F5F9;color:#64748B;">종료</span>
            {% endif %}
          {% else %}
            <span class="badge" style="background:#DBEAFE;color:#1E40AF;">진행중</span>
          {% endif %}
        </div>
      </a>
    </li>
    {% endfor %}
  </ul>
  {% else %}
  <div class="py-10 text-center">
    <p class="text-sm text-muted">{% if project_status_filter == "active" %}진행 중인 프로젝트가 없습니다{% elif project_status_filter == "closed" %}완료된 프로젝트가 없습니다{% else %}등록된 프로젝트가 없습니다{% endif %}</p>
    {% if membership and membership.role == "owner" %}
    <a href="{% url 'projects:project_create' %}?client={{ client.pk }}"
       hx-get="{% url 'projects:project_create' %}?client={{ client.pk }}" hx-target="#main-content" hx-push-url="true"
       class="inline-flex items-center gap-2 mt-4 px-4 h-10 rounded-lg bg-ink3 text-white text-sm font-semibold hover:bg-ink2">
      + 새 프로젝트
    </a>
    {% endif %}
  </div>
  {% endif %}
</section>
```

**주의:** `projects:project_create` URL 이름이 정확한지 확인. 다르면 해당 앱의 `urls.py` 에서 조회해 사용.

- [ ] **Step 4: project_create URL 이름 확인**

```bash
grep -n "name=" projects/urls.py | grep -i create
```

이름이 다르면 partial 과 step 의 URL 이름을 교체.

- [ ] **Step 5: 테스트 추가**

`tests/test_clients_views_detail.py` (신규 파일):

```python
import pytest
from django.urls import reverse

from accounts.models import Organization, Membership, User
from clients.models import Client
from projects.models import Project


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org")


@pytest.fixture
def owner(org):
    u = User.objects.create_user(username="owner", password="x")
    Membership.objects.create(user=u, organization=org, role="owner")
    return u


@pytest.fixture
def logged_in(client, owner):
    client.force_login(owner)
    return client


@pytest.mark.django_db
def test_detail_renders_profile(org, logged_in):
    c = Client.objects.create(organization=org, name="SKBP", website="https://x.com", description="desc")
    resp = logged_in.get(reverse("clients:client_detail", args=[c.pk]))
    body = resp.content.decode()
    assert "SKBP" in body
    assert "desc" in body
    assert "x.com" in body


@pytest.mark.django_db
def test_detail_projects_panel_all(org, logged_in):
    c = Client.objects.create(organization=org, name="A")
    Project.objects.create(client=c, organization=org, title="P1", status="open")
    Project.objects.create(client=c, organization=org, title="P2", status="closed", result="success")
    resp = logged_in.get(reverse("clients:client_projects_panel", args=[c.pk]) + "?status=all")
    body = resp.content.decode()
    assert "P1" in body
    assert "P2" in body


@pytest.mark.django_db
def test_detail_projects_panel_active_only(org, logged_in):
    c = Client.objects.create(organization=org, name="A")
    Project.objects.create(client=c, organization=org, title="P1", status="open")
    Project.objects.create(client=c, organization=org, title="P2", status="closed", result="success")
    resp = logged_in.get(reverse("clients:client_projects_panel", args=[c.pk]) + "?status=active")
    body = resp.content.decode()
    assert "P1" in body
    assert "P2" not in body


@pytest.mark.django_db
def test_detail_empty_projects_shows_cta(org, logged_in):
    c = Client.objects.create(organization=org, name="A")
    resp = logged_in.get(reverse("clients:client_detail", args=[c.pk]))
    body = resp.content.decode()
    assert "등록된 프로젝트가 없습니다" in body
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
uv run pytest tests/test_clients_views_detail.py -v
```

Expected: 4 passed.

- [ ] **Step 7: 커밋**

```bash
git add clients/templates/ clients/views.py clients/urls.py tests/test_clients_views_detail.py
git commit -m "feat(clients): detail projects panel with segmented status control"
```

---

## Task 16: 상세 — 빈 담당자/계약 상태 정리

**Files:**
- (수정 없음 — Task 14 partial 의 빈 상태가 이미 구현됨)

이 태스크는 Task 14 가 이미 커버했는지 브라우저로 확인만 수행.

- [ ] **Step 1: 빈 고객사로 상세 진입 확인**

```bash
uv run python manage.py shell -c "
from accounts.models import Organization
from clients.models import Client
org = Organization.objects.first()
Client.objects.create(organization=org, name='Empty Test')
"
```

`/clients/` 에서 "Empty Test" 카드 클릭 → 담당자/계약/프로젝트 빈 상태 + owner 전용 CTA 가 렌더되는지.

- [ ] **Step 2: 정리 (테스트 데이터 제거)**

```bash
uv run python manage.py shell -c "
from clients.models import Client
Client.objects.filter(name='Empty Test').delete()
"
```

- [ ] **Step 3: 별도 커밋 불필요**

Task 14 커밋에 이미 포함됨.

---

## Task 17: 신규/수정 폼 — 기본 구조 재작성

**Files:**
- Modify: `clients/templates/clients/client_form.html` (전면 재작성)
- Modify: `clients/forms.py` (`clean_logo` 추가)

- [ ] **Step 1: form.clean_logo 추가**

`clients/forms.py::ClientForm` 에 method 추가:

```python
    def clean_logo(self):
        from clients.services.client_create import validate_logo_file
        f = self.cleaned_data.get("logo")
        if f:
            try:
                validate_logo_file(f)
            except ValueError as e:
                raise forms.ValidationError(str(e)) from e
        return f
```

- [ ] **Step 2: 폼 테스트 추가**

`tests/test_clients_views_form.py` (신규):

```python
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from accounts.models import Organization, Membership, User
from clients.models import Client


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org")


@pytest.fixture
def owner(org):
    u = User.objects.create_user(username="owner", password="x")
    Membership.objects.create(user=u, organization=org, role="owner")
    return u


@pytest.fixture
def logged_in(client, owner):
    client.force_login(owner)
    return client


@pytest.mark.django_db
def test_create_client_minimal(org, logged_in):
    resp = logged_in.post(
        reverse("clients:client_create"),
        data={"name": "New Co", "industry": "IT/SW", "contact_persons_json": "[]"},
    )
    assert resp.status_code in (302, 200)
    assert Client.objects.filter(organization=org, name="New Co").exists()


@pytest.mark.django_db
def test_update_client_website(org, logged_in):
    c = Client.objects.create(organization=org, name="A")
    resp = logged_in.post(
        reverse("clients:client_update", args=[c.pk]),
        data={"name": "A", "industry": "기타", "website": "https://example.com", "contact_persons_json": "[]"},
    )
    assert resp.status_code in (302, 200)
    c.refresh_from_db()
    assert c.website == "https://example.com"


@pytest.mark.django_db
def test_create_rejects_invalid_logo_ext(org, logged_in):
    bogus = SimpleUploadedFile("x.exe", b"MZ", content_type="application/x-msdownload")
    resp = logged_in.post(
        reverse("clients:client_create"),
        data={"name": "A", "industry": "기타", "contact_persons_json": "[]"},
        files={"logo": bogus},
    )
    # form re-renders with error
    body = resp.content.decode()
    assert "허용되지 않는" in body or resp.status_code == 200


@pytest.mark.django_db
def test_contact_persons_round_trip(org, logged_in):
    import json
    c = Client.objects.create(organization=org, name="A")
    cps = [{"name": "Kim", "position": "CEO", "phone": "010", "email": "k@x.com"}]
    resp = logged_in.post(
        reverse("clients:client_update", args=[c.pk]),
        data={
            "name": "A",
            "industry": "기타",
            "contact_persons_json": json.dumps(cps),
        },
    )
    c.refresh_from_db()
    assert c.contact_persons[0]["name"] == "Kim"
    assert c.contact_persons[0]["position"] == "CEO"
```

- [ ] **Step 3: client_form.html 재작성**

`clients/templates/clients/client_form.html` 전체 교체:

```html
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}

{% block title %}{% if is_edit %}고객사 수정{% else %}고객사 등록{% endif %} — synco{% endblock %}
{% block breadcrumb_current %}{% if is_edit %}Edit Client{% else %}New Client{% endif %}{% endblock %}
{% block page_title %}{% if is_edit %}고객사 수정{% else %}고객사 등록{% endif %}{% endblock %}

{% block content %}
<div class="px-8 py-8 max-w-[720px] mx-auto pb-32">

  <a href="{% if is_edit %}{% url 'clients:client_detail' client.pk %}{% else %}{% url 'clients:client_list' %}{% endif %}"
     hx-get="{% if is_edit %}{% url 'clients:client_detail' client.pk %}{% else %}{% url 'clients:client_list' %}{% endif %}"
     hx-target="#main-content" hx-push-url="true"
     class="inline-flex items-center gap-2 text-xs font-semibold text-muted hover:text-ink3 mb-6">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/></svg>
    {% if is_edit %}상세로 돌아가기{% else %}목록으로 돌아가기{% endif %}
  </a>

  <div class="eyebrow">{% if is_edit %}Edit Client{% else %}New Client{% endif %}</div>
  <h2 class="text-3xl font-bold tracking-tight mb-8">{% if is_edit %}고객사 수정{% else %}고객사 등록{% endif %}</h2>

  <form method="post" enctype="multipart/form-data" class="space-y-6">
    {% csrf_token %}

    <section class="bg-surface rounded-card shadow-card p-6">
      <div class="eyebrow mb-5">기본 정보</div>
      <div class="space-y-5">
        {% for field in form %}
          {% if field.name != "logo" %}
          <div>
            <label for="{{ field.id_for_label }}" class="block text-xs font-semibold text-ink3 mb-1.5">
              {{ field.label }}{% if field.field.required %} <span class="text-danger">*</span>{% endif %}
            </label>
            {{ field }}
            {% if field.errors %}<p class="text-xs text-danger mt-1">{{ field.errors.0 }}</p>{% endif %}
          </div>
          {% else %}
          <div id="logo-field">
            <label class="block text-xs font-semibold text-ink3 mb-1.5">{{ field.label }}</label>
            {% if client.logo %}
            <div class="flex items-center gap-3 mb-2">
              <img src="{{ client.logo.url }}" alt="" class="w-16 h-16 rounded-lg object-contain bg-white border border-hair p-1" />
              <label class="inline-flex items-center gap-2 text-xs text-danger">
                <input type="checkbox" name="logo-clear" value="on"> 기존 로고 삭제
              </label>
            </div>
            {% endif %}
            {{ field }}
            <p class="text-xs text-faint mt-1">JPG/PNG/SVG/WEBP · 2MB 이하</p>
            {% if field.errors %}<p class="text-xs text-danger mt-1">{{ field.errors.0 }}</p>{% endif %}
          </div>
          {% endif %}
        {% endfor %}
      </div>
    </section>

    <section id="contacts" class="bg-surface rounded-card shadow-card p-6">
      <div class="flex items-center justify-between mb-4">
        <div class="eyebrow">담당자</div>
        <button type="button" onclick="addContactPerson()"
                class="text-xs font-semibold text-ink3 hover:text-ink2 px-2 py-1 rounded hover:bg-line">
          + 추가
        </button>
      </div>
      <div id="contact-persons-container" class="space-y-3"></div>
      <input type="hidden" name="contact_persons_json" id="contact-persons-json" value="[]">
    </section>

    <section id="notes" class="bg-surface rounded-card shadow-card p-6">
      <div class="eyebrow mb-3">메모</div>
      {{ form.notes }}
    </section>

    <div class="sticky bottom-0 bg-canvas pt-4 flex items-center justify-between">
      {% if is_edit %}
      <button type="button"
              hx-post="{% url 'clients:client_delete' client.pk %}"
              hx-confirm="이 고객사를 삭제하시겠어요?"
              hx-target="#main-content"
              class="text-sm font-semibold text-danger hover:underline">삭제</button>
      {% else %}<span></span>{% endif %}
      <div class="flex items-center gap-3">
        <a href="{% if is_edit %}{% url 'clients:client_detail' client.pk %}{% else %}{% url 'clients:client_list' %}{% endif %}"
           hx-get="{% if is_edit %}{% url 'clients:client_detail' client.pk %}{% else %}{% url 'clients:client_list' %}{% endif %}"
           hx-target="#main-content" hx-push-url="true"
           class="text-sm text-muted hover:text-ink3">취소</a>
        <button type="submit"
                class="px-6 h-10 rounded-lg bg-ink3 text-white text-sm font-semibold hover:bg-ink2">
          {% if is_edit %}저장{% else %}등록{% endif %}
        </button>
      </div>
    </div>
  </form>
</div>

<script>
(function() {
  var container = document.getElementById('contact-persons-container');
  var jsonInput = document.getElementById('contact-persons-json');
  var initial = {{ contact_persons_json|safe }};
  initial.forEach(function(p) { addRow(p); });

  window.addContactPerson = function() {
    addRow({name: '', position: '', phone: '', email: ''});
  };

  function addRow(data) {
    var row = document.createElement('div');
    row.className = 'contact-person-row rounded-lg border border-hair p-3 space-y-2';
    row.innerHTML =
      '<div class="flex items-center justify-between">' +
        '<span class="text-xs font-semibold text-muted">담당자</span>' +
        '<button type="button" onclick="removeContactPerson(this)" class="text-xs text-danger hover:underline">삭제</button>' +
      '</div>' +
      '<div class="grid grid-cols-2 gap-2">' +
        '<input type="text" placeholder="이름" data-cp="name" value="' + esc(data.name || '') + '" class="rounded-lg border border-hair bg-surface px-3 py-2 text-sm focus:border-ink3 focus:ring-2 focus:ring-ink3/10 outline-none">' +
        '<input type="text" placeholder="직책" data-cp="position" value="' + esc(data.position || '') + '" class="rounded-lg border border-hair bg-surface px-3 py-2 text-sm focus:border-ink3 focus:ring-2 focus:ring-ink3/10 outline-none">' +
        '<input type="text" placeholder="전화" data-cp="phone" value="' + esc(data.phone || '') + '" class="rounded-lg border border-hair bg-surface px-3 py-2 text-sm focus:border-ink3 focus:ring-2 focus:ring-ink3/10 outline-none">' +
        '<input type="text" placeholder="이메일" data-cp="email" value="' + esc(data.email || '') + '" class="rounded-lg border border-hair bg-surface px-3 py-2 text-sm focus:border-ink3 focus:ring-2 focus:ring-ink3/10 outline-none">' +
      '</div>';
    container.appendChild(row);
    updateJson();
    row.querySelectorAll('input').forEach(function(i) { i.addEventListener('input', updateJson); });
  }

  window.removeContactPerson = function(btn) {
    btn.closest('.contact-person-row').remove();
    updateJson();
  };

  function updateJson() {
    var rows = container.querySelectorAll('.contact-person-row');
    var persons = [];
    rows.forEach(function(row) {
      var p = {};
      row.querySelectorAll('[data-cp]').forEach(function(i) { p[i.dataset.cp] = i.value; });
      if ((p.name || '').trim()) persons.push(p);
    });
    jsonInput.value = JSON.stringify(persons);
  }

  function esc(s) { var d = document.createElement('div'); d.appendChild(document.createTextNode(s)); return d.innerHTML; }

  document.querySelector('form').addEventListener('submit', updateJson);
})();
</script>
{% endblock %}
```

- [ ] **Step 4: 폼 widget 클래스 디자인 시스템으로 교체**

`clients/forms.py::ClientForm.Meta.widgets` 전체 교체:

```python
INPUT_CLS = "w-full rounded-lg border border-hair bg-surface px-4 py-2.5 text-sm focus:border-ink3 focus:ring-2 focus:ring-ink3/10 outline-none"
TEXTAREA_CLS = INPUT_CLS + " resize-none"

widgets = {
    "name": forms.TextInput(attrs={"class": INPUT_CLS, "placeholder": "고객사명"}),
    "industry": forms.Select(attrs={"class": INPUT_CLS}),
    "size": forms.Select(attrs={"class": INPUT_CLS}),
    "region": forms.TextInput(attrs={"class": INPUT_CLS, "placeholder": "예: 서울, 경기"}),
    "website": forms.URLInput(attrs={"class": INPUT_CLS, "placeholder": "https://"}),
    "logo": forms.ClearableFileInput(attrs={"class": "text-sm", "accept": "image/*"}),
    "description": forms.Textarea(attrs={"class": TEXTAREA_CLS, "rows": 2, "placeholder": "카드 리스트에 노출되는 2줄 요약"}),
    "notes": forms.Textarea(attrs={"class": TEXTAREA_CLS, "rows": 6, "placeholder": "메모"}),
}
```

- [ ] **Step 5: views.py 의 create/update 가 logo·파일 업로드 처리하도록 수정**

`clients/views.py::client_create`, `client_update` 의 `form = ClientForm(request.POST)` 호출을 `ClientForm(request.POST, request.FILES, ...)` 로 변경:

```python
# client_create
if request.method == "POST":
    form = ClientForm(request.POST, request.FILES)
    cp_json_str = request.POST.get("contact_persons_json", "[]")
    if form.is_valid():
        client = form.save(commit=False)
        client.organization = org
        try:
            client.contact_persons = json.loads(cp_json_str)
        except (json.JSONDecodeError, TypeError):
            client.contact_persons = []
        client.save()
        return redirect("clients:client_detail", pk=client.pk)

# client_update — 동일한 패턴
if request.method == "POST":
    form = ClientForm(request.POST, request.FILES, instance=client)
    # logo-clear 체크박스 처리
    if request.POST.get("logo-clear") == "on" and client.logo:
        from clients.services.client_create import apply_logo_upload
        apply_logo_upload(client, None, delete=True)
    if form.is_valid():
        client = form.save(commit=False)
        cp_json = request.POST.get("contact_persons_json", "[]")
        try:
            client.contact_persons = json.loads(cp_json)
        except (json.JSONDecodeError, TypeError):
            pass
        client.save()
        return redirect("clients:client_detail", pk=client.pk)
```

- [ ] **Step 6: normalize_contact_persons 를 view 에서 사용**

create/update 의 `client.contact_persons = json.loads(...)` 직후 `normalize_contact_persons` 적용:

```python
from clients.services.client_create import normalize_contact_persons
...
client.contact_persons = normalize_contact_persons(json.loads(cp_json_str))
```

- [ ] **Step 7: 테스트 통과 확인**

```bash
uv run pytest tests/test_clients_views_form.py -v
```

Expected: 4 passed.

- [ ] **Step 8: 커밋**

```bash
git add clients/forms.py clients/views.py clients/templates/clients/client_form.html tests/test_clients_views_form.py
git commit -m "feat(clients): create/edit form redesign with logo upload + contact persons"
```

---

## Task 18: 삭제 가드 (프로젝트 존재 시 차단)

**Files:**
- Modify: `clients/views.py::client_delete`
- Create: `tests/test_clients_views_delete.py`

기존 `client_delete` 은 `active_projects` (open 만) 기준으로 차단. 스펙은 **모든** 프로젝트(open/closed 모두) 존재 시 차단이므로 로직 강화.

- [ ] **Step 1: 테스트 작성**

`tests/test_clients_views_delete.py`:

```python
import pytest
from django.urls import reverse

from accounts.models import Organization, Membership, User
from clients.models import Client
from projects.models import Project


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org")


@pytest.fixture
def owner(org):
    u = User.objects.create_user(username="owner", password="x")
    Membership.objects.create(user=u, organization=org, role="owner")
    return u


@pytest.fixture
def logged_in(client, owner):
    client.force_login(owner)
    return client


@pytest.mark.django_db
def test_delete_blocks_when_any_projects_exist(org, logged_in):
    c = Client.objects.create(organization=org, name="A")
    Project.objects.create(client=c, organization=org, title="P", status="closed", result="success")
    resp = logged_in.post(reverse("clients:client_delete", args=[c.pk]))
    assert Client.objects.filter(pk=c.pk).exists()
    body = resp.content.decode()
    assert "삭제할 수 없습니다" in body


@pytest.mark.django_db
def test_delete_allows_when_no_projects(org, logged_in):
    c = Client.objects.create(organization=org, name="A")
    resp = logged_in.post(reverse("clients:client_delete", args=[c.pk]))
    assert resp.status_code in (302, 200)
    assert not Client.objects.filter(pk=c.pk).exists()
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/test_clients_views_delete.py -v
```

Expected: 첫 번째 테스트 실패 (기존 로직은 closed 프로젝트는 허용).

- [ ] **Step 3: client_delete 수정**

`clients/views.py::client_delete`:

```python
@login_required
@role_required("owner")
def client_delete(request, pk):
    if request.method != "POST":
        return HttpResponse(status=405)

    org = _get_org(request)
    client = get_object_or_404(Client, pk=pk, organization=org)

    if client.projects.exists():
        # 상세 페이지 재렌더 + 에러 메시지
        stats = client_stats(client)
        projects = client_projects(client, status_filter="all")[:20]
        return render(
            request,
            "clients/client_detail.html",
            {
                "client": client,
                "contracts": client.contracts.all(),
                "projects": projects,
                "stats": stats,
                "contract_form": ContractForm(),
                "project_status_filter": "all",
                "error_message": (
                    f"연결된 프로젝트 {client.projects.count()}건이 있어 삭제할 수 없습니다. "
                    "프로젝트를 먼저 정리하거나 조직 관리자에게 문의하세요."
                ),
            },
        )

    client.delete()
    return redirect("clients:client_list")
```

- [ ] **Step 4: 상세 템플릿에 error_message 표시**

`clients/templates/clients/client_detail.html` 의 상단 (Back 링크 아래) 에 추가:

```html
{% if error_message %}
<div class="bg-danger/10 border border-danger/20 rounded-card p-4 text-sm text-danger">{{ error_message }}</div>
{% endif %}
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
uv run pytest tests/test_clients_views_delete.py tests/test_clients_views_detail.py -v
```

Expected: all passed.

- [ ] **Step 6: 커밋**

```bash
git add clients/views.py clients/templates/clients/client_detail.html tests/test_clients_views_delete.py
git commit -m "feat(clients): delete guard — block when any projects exist"
```

---

## Task 19: 메모 카드 페이지 공통화 + 디자인 시스템 준수 전수 점검

**Files:**
- Modify: `clients/templates/clients/partials/contract_section.html` (디자인 토큰)

- [ ] **Step 1: contract_section.html 리뷰 + 재스타일**

`clients/templates/clients/partials/contract_section.html` 파일 전체를 읽고 다음 원칙으로 재스타일:
- `bg-white` → `bg-surface`
- `rounded-xl` → `rounded-card`
- `border-slate-*` → `border-hair`
- 버튼: `rounded-xl bg-ink3 text-white ... uppercase tracking-widest` → `px-4 h-10 rounded-lg bg-ink3 text-white text-sm font-semibold`
- `text-[11px]` / `text-[15px]` 같은 arbitrary 값 → 표준 토큰(`text-xs`/`text-sm`)

각 Contract 카드를 `rounded-card shadow-card p-5` 기반으로 정리. 기존 로직(inline edit form, delete form)은 유지.

- [ ] **Step 2: 기존 계약 CRUD 테스트가 통과하는지**

```bash
uv run pytest tests/ -v -k "contract"
```

Expected: 기존 테스트 통과. 셀렉터가 깨지면 templates 내 버튼 class 또는 `data-*` attribute 만 조정.

- [ ] **Step 3: 수동 브라우저 QA**

로컬에서 `uv run python manage.py runserver 0.0.0.0:8000` 실행 후 `/clients/<pk>/` 접속 → 계약 카드 UI 가 디자인 시스템과 이질감 없는지.

- [ ] **Step 4: 커밋**

```bash
git add clients/templates/clients/partials/contract_section.html
git commit -m "chore(clients): contract_section.html restyle to design system tokens"
```

---

## Task 20: 수동 QA 체크리스트 + 핸드오프 문서

**Files:**
- Create: `docs/session-handoff/2026-04-19-clients-redesign.md`

- [ ] **Step 1: 핸드오프 문서 작성**

`docs/session-handoff/2026-04-19-clients-redesign.md`:

```markdown
# Clients 메뉴 UI 리디자인 — 핸드오프

**상태:** 구현 완료. 브라우저 수동 QA + 운영 마이그레이션 적용 대기.

## 변경된 URL (수동 QA 대상)

- `/clients/` — 리스트(카테고리 칩, 필터 드롭다운, infinite scroll, 3-up 카드)
- `/clients/new/` — 신규 등록 폼 (로고 업로드, 담당자 JSON)
- `/clients/<pk>/` — 상세 (프로필 + 담당자/계약 좌측 + 프로젝트 패널 우측 + 메모)
- `/clients/<pk>/edit/` — 수정 폼
- `/clients/<pk>/projects/?status=active|closed|all` — 상세 프로젝트 패널 HTMX
- `/clients/page/?page=N&cat=...&size=...` — 리스트 infinite scroll HTMX

## 수동 회귀 체크리스트

- [ ] 리스트: 헤더 통계, 11개 카테고리 칩, 3-up 그리드, 카드 hover lift, 케밥 메뉴
- [ ] 카드 상단 클릭 → website new tab (website 없으면 비활성)
- [ ] 카드 하단 클릭 → 상세 페이지
- [ ] 카테고리 칩 필터 동작, 0건 칩 disabled
- [ ] Filters 드롭다운: 규모/지역/거래건수/성사이력 조합
- [ ] Infinite scroll: 9번째 이후 자동 로드, 마지막 "모두 불러왔어요"
- [ ] 신규 등록: 필수 검증, 로고 업로드 + 미리보기, 확장자/크기 검증, 담당자 추가/삭제
- [ ] 수정: 기존 로고 썸네일 + 삭제 체크박스, 담당자 JSON 왕복
- [ ] 상세: 프로필 4-up 통계, 담당자/계약 좌측, 프로젝트 세그먼티드 컨트롤
- [ ] 삭제: 프로젝트 있을 때 차단 배너, 없을 때 성공

## 운영 배포 순서

1. 미적용 마이그레이션 확인:
   ```
   ssh chaconne@49.247.46.171 \
     "docker exec \$(docker ps -qf name=synco_web) python manage.py showmigrations clients | grep '\[ \]'"
   ```
2. 승인 후 `./deploy.sh` — 마이그레이션 자동 실행.
3. 배포 후 `/clients/` 로그인 상태로 접근해 카드 그리드 표시·카테고리 카운트 정상인지.

## 알려진 제약 (백로그)

1. 카드 `📧` `⭐` 아이콘은 장식. 이메일/즐겨찾기 기능은 후속 phase.
2. 상세 프로젝트 리스트는 최근 20건 제한. "전체 보기" 는 별도 구현 필요.
3. 로고는 원본 업로드만. 썸네일/webp 변환·리사이즈 없음.
4. 데이터 마이그레이션 키워드 사전은 제한적. 매핑되지 않은 자유 텍스트는 모두 "기타" — 배포 후 운영자가 수동 재분류 필요할 수 있음.
5. `Project.client` on_delete=CASCADE 는 유지. 삭제 가드로 실질적으로 회피.

## 후속 과제

- `Project.client` on_delete=CASCADE → `PROTECT` 로 강화 (가드와 중복이지만 DB 레벨 방어)
- 로고 썸네일 자동 생성
- 카테고리 수동 재분류 관리 명령 (`manage.py reclassify_industries`)
```

- [ ] **Step 2: 전체 테스트 스모크**

```bash
uv run pytest tests/ -v -k "client" --no-header
```

Expected: 새로 추가된 테스트 모두 통과.

- [ ] **Step 3: ruff 통과**

```bash
uv run ruff check clients/
uv run ruff format clients/
```

Expected: no issues. 수정사항 있으면 재커밋.

- [ ] **Step 4: 커밋**

```bash
git add docs/session-handoff/2026-04-19-clients-redesign.md
git commit -m "docs(handoff): clients redesign manual QA checklist"
```

---

## Self-Review Notes

이 섹션은 계획 작성 중 검토한 항목. 구현자가 추가로 확인해야 할 포인트만 기록.

**스펙 커버리지:**
- §2 모델 변경 — Task 2/3/4 ✓
- §3 마이그레이션 — Task 4 (데이터) ✓
- §4 리스트 — Task 11/12 ✓
- §5 카드 — Task 11 ✓
- §6 필터 — Task 13 ✓
- §7 상세 — Task 14/15 ✓
- §8 폼/삭제 — Task 17/18 ✓
- §9 서비스 — Task 6/7/8 ✓
- §10 뷰/URL — Task 11/15 ✓
- §11 CSS/partial — Task 9/10/11/14/15 ✓
- §12 테스트 — Task 6/7/8/9/12/15/17/18 ✓

**잠재적 이슈:**
- Task 11 Step 2 에서 `request.GET.items()` 를 infinite scroll sentinel 에 순회 — 쿼리 파라미터가 URL에 정확히 포워딩되는지 수동 확인 필요.
- Task 13 의 Tailwind `peer-checked:is-active` 패턴은 `.cat-chip` 이 label 의 형제가 아닌 자식이므로 작동 확인 필요. 만약 안 되면 `x-data` alpine.js 로 수동 토글.
- Task 17 Step 5 에서 `logo-clear` 체크박스 처리 — `form.is_valid()` 호출 전에 `apply_logo_upload` 를 호출하면 form 에 instance 가 갱신된 상태가 전달됨. 순서는 유지.
- Task 15 `projects:project_create` URL 이름 존재 확인(Step 4).
- 데이터 마이그레이션의 `KEYWORD_MAP` 은 간이 키워드 매칭. 실제 운영 데이터에 대해 결과가 기대와 다르면 `python manage.py shell` 로 수동 재분류.

**Type/Signature 일관성:**
- `list_clients_with_stats` 의 kwargs 이름(`categories`, `sizes`, `regions`, `offers_range`, `success_status`) 이 Task 6~8, 11, 13 에서 모두 동일.
- `client_stats` 반환 딕셔너리 키(`offers`, `success`, `active`, `placed`) 가 Task 8, 14, 15 에서 동일.
- Templatetag 이름(`logo_class`, `client_initials`, `size_badge_class`, `get_item`) 이 Task 9, 11, 14 에서 동일.
