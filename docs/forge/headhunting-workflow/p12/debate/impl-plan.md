# P12: Reference Data Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build reference data management (universities, companies, certs) with admin UI, CSV import/export, and initial data loading.

**Architecture:** Extend the existing `clients` app with model schema changes, a dedicated `views_reference.py` and `urls_reference.py` mounted at `/reference/`. Tab-based UI with HTMX partial swapping for the three data types. CSV handler service for import/export. Gemini API-based company autofill.

**Tech Stack:** Django 5.2, PostgreSQL, HTMX, Tailwind CSS, Gemini API (`google-genai`), pytest

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `clients/models.py` | Model schema changes (3 reference models) | Modify |
| `clients/migrations/0002_p12_reference_models.py` | Auto-generated schema migration | Create (auto) |
| `clients/forms_reference.py` | CRUD forms + CSV import form for 3 models | Create |
| `clients/views_reference.py` | ~20 reference management views | Create |
| `clients/urls_reference.py` | `/reference/` URL routing | Create |
| `main/urls.py` | Add `/reference/` include | Modify |
| `clients/services/__init__.py` | Package init | Create |
| `clients/services/csv_handler.py` | CSV import/export logic | Create |
| `clients/services/company_autofill.py` | Gemini autofill service | Create |
| `clients/management/commands/load_reference_data.py` | Initial data loading command | Create |
| `clients/fixtures/universities.csv` | University seed data (~200) | Create |
| `clients/fixtures/companies.csv` | Company seed data (sample ~50 for dev) | Create |
| `clients/fixtures/certs.csv` | Cert seed data (sample ~50 for dev) | Create |
| `clients/templates/clients/reference_index.html` | Main layout with tabs | Create |
| `clients/templates/clients/partials/ref_universities.html` | University tab content | Create |
| `clients/templates/clients/partials/ref_companies.html` | Company tab content | Create |
| `clients/templates/clients/partials/ref_certs.html` | Cert tab content | Create |
| `clients/templates/clients/partials/ref_form_modal.html` | Shared CRUD form modal | Create |
| `clients/templates/clients/partials/ref_import_result.html` | CSV import result partial | Create |
| `templates/common/nav_sidebar.html` | Add reference menu item | Modify |
| `templates/common/nav_bottom.html` | Add reference nav for mobile | Modify |
| `tests/test_p12_reference.py` | All P12 tests | Create |

---

### Task 1: Model Schema Changes + Migration

**Files:**
- Modify: `clients/models.py`
- Create: `clients/migrations/0002_p12_reference_models.py` (auto-generated)
- Modify: `tests/test_p01_models.py` (update existing model tests to match new schema)

- [ ] **Step 1: Update UniversityTier model**

In `clients/models.py`, replace the `UniversityTier` class:

```python
class UniversityTier(BaseModel):
    """대학 랭킹 마스터 데이터."""

    class Tier(models.TextChoices):
        SKY = "SKY", "SKY"
        SSG = "SSG", "서성한"
        JKOS = "JKOS", "중경외시"
        KDH = "KDH", "건동홍"
        INSEOUL = "INSEOUL", "인서울 기타"
        SCIENCE_ELITE = "SCIENCE_ELITE", "이공계 명문"
        REGIONAL = "REGIONAL", "지방 거점 국립"
        OVERSEAS_TOP = "OVERSEAS_TOP", "해외 최상위"
        OVERSEAS_HIGH = "OVERSEAS_HIGH", "해외 상위"
        OVERSEAS_GOOD = "OVERSEAS_GOOD", "해외 우수"

    name = models.CharField(max_length=200)
    name_en = models.CharField(max_length=200, blank=True)
    country = models.CharField(max_length=10, default="KR")
    tier = models.CharField(max_length=20, choices=Tier.choices)
    ranking = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["tier", "ranking"]
        unique_together = [("name", "country")]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_tier_display()})"
```

- [ ] **Step 2: Update CompanyProfile model**

In `clients/models.py`, replace the `CompanyProfile` class:

```python
class CompanyProfile(BaseModel):
    """기업 분류 DB."""

    class SizeCategory(models.TextChoices):
        LARGE = "대기업", "대기업"
        MID = "중견", "중견"
        SMALL = "중소", "중소"
        FOREIGN = "외국계", "외국계"
        STARTUP = "스타트업", "스타트업"

    class Listed(models.TextChoices):
        KOSPI = "KOSPI", "KOSPI"
        KOSDAQ = "KOSDAQ", "KOSDAQ"
        UNLISTED = "비상장", "비상장"
        OVERSEAS = "해외상장", "해외상장"

    name = models.CharField(max_length=200, unique=True)
    name_en = models.CharField(max_length=200, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    size_category = models.CharField(
        max_length=50, choices=SizeCategory.choices, blank=True
    )
    revenue_range = models.CharField(max_length=50, blank=True)
    employee_count_range = models.CharField(max_length=50, blank=True)
    listed = models.CharField(max_length=20, choices=Listed.choices, blank=True)
    region = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
```

- [ ] **Step 3: Update PreferredCert model**

In `clients/models.py`, replace the `PreferredCert` class:

```python
class PreferredCert(BaseModel):
    """선호 자격증 마스터."""

    class Category(models.TextChoices):
        ACCOUNTING = "회계/재무", "회계/재무"
        LAW = "법률", "법률"
        TECH = "기술/엔지니어링", "기술/엔지니어링"
        IT = "IT", "IT"
        MEDICAL = "의료/제약", "의료/제약"
        TRADE = "무역/물류", "무역/물류"
        CONSTRUCTION = "건설/부동산", "건설/부동산"
        FOOD_ENV = "식품/환경", "식품/환경"
        LANGUAGE = "어학", "어학"
        SAFETY = "안전/품질", "안전/품질"
        OTHER = "기타", "기타"

    class Level(models.TextChoices):
        HIGH = "상", "상"
        MID = "중", "중"
        LOW = "하", "하"

    name = models.CharField(max_length=200, unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=30, choices=Category.choices)
    level = models.CharField(max_length=10, choices=Level.choices, blank=True)
    aliases = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_category_display()})"
```

- [ ] **Step 4: Generate and apply migration**

Run:
```bash
uv run python manage.py makemigrations clients --name p12_reference_models
uv run python manage.py migrate
```
Expected: Migration created and applied with no errors.

- [ ] **Step 5: Update existing model tests**

In `tests/test_p01_models.py`, update the `TestUniversityTier`, `TestCompanyProfile`, and `TestPreferredCert` classes to use new tier values and fields:

```python
class TestUniversityTier:
    @pytest.mark.django_db
    def test_create_university_tier(self):
        u = UniversityTier.objects.create(
            name="서울대학교",
            name_en="Seoul National University",
            tier="SKY",
            ranking=1,
        )
        assert u.name == "서울대학교"
        assert u.tier == "SKY"
        assert u.country == "KR"

    @pytest.mark.django_db
    def test_overseas_tier(self):
        u = UniversityTier.objects.create(name="MIT", tier="OVERSEAS_TOP", country="US")
        assert u.tier == "OVERSEAS_TOP"
        assert u.country == "US"


class TestCompanyProfile:
    @pytest.mark.django_db
    def test_create_company_profile(self):
        cp = CompanyProfile.objects.create(
            name="Google", industry="IT", size_category="대기업"
        )
        assert cp.name == "Google"
        assert str(cp) == "Google"


class TestPreferredCert:
    @pytest.mark.django_db
    def test_create_preferred_cert(self):
        pc = PreferredCert.objects.create(name="CPA", category="회계/재무")
        assert pc.name == "CPA"
        assert pc.category == "회계/재무"

    @pytest.mark.django_db
    def test_preferred_cert_unique_name(self):
        PreferredCert.objects.create(name="CPA", category="회계/재무")
        with pytest.raises(IntegrityError):
            PreferredCert.objects.create(name="CPA", category="IT")
```

- [ ] **Step 6: Run tests to verify migration + model changes**

Run: `uv run pytest tests/test_p01_models.py -v`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add clients/models.py clients/migrations/ tests/test_p01_models.py
git commit -m "feat(p12): update reference model schemas with new tiers, fields, and constraints"
```

---

### Task 2: Forms + CSV Import Form

**Files:**
- Create: `clients/forms_reference.py`

- [ ] **Step 1: Create reference forms file**

Create `clients/forms_reference.py`:

```python
"""Reference data management forms."""

from django import forms

from .models import CompanyProfile, PreferredCert, UniversityTier

_INPUT = "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] focus:ring-2 focus:ring-primary focus:border-primary"
_SELECT = _INPUT
_TEXTAREA = _INPUT


class UniversityTierForm(forms.ModelForm):
    class Meta:
        model = UniversityTier
        fields = ["name", "name_en", "country", "tier", "ranking", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "대학명"}),
            "name_en": forms.TextInput(attrs={"class": _INPUT, "placeholder": "University name (English)"}),
            "country": forms.TextInput(attrs={"class": _INPUT, "placeholder": "KR", "maxlength": "10"}),
            "tier": forms.Select(attrs={"class": _SELECT}),
            "ranking": forms.NumberInput(attrs={"class": _INPUT, "placeholder": "순위 (선택)", "min": "1"}),
            "notes": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 2, "placeholder": "비고"}),
        }
        labels = {
            "name": "대학명",
            "name_en": "영문명",
            "country": "국가 코드",
            "tier": "티어",
            "ranking": "순위",
            "notes": "비고",
        }


class CompanyProfileForm(forms.ModelForm):
    class Meta:
        model = CompanyProfile
        fields = [
            "name", "name_en", "industry", "size_category",
            "revenue_range", "employee_count_range", "listed", "region", "notes",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "회사명"}),
            "name_en": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Company name (English)"}),
            "industry": forms.TextInput(attrs={"class": _INPUT, "placeholder": "업종"}),
            "size_category": forms.Select(attrs={"class": _SELECT}),
            "revenue_range": forms.TextInput(attrs={"class": _INPUT, "placeholder": "매출 규모"}),
            "employee_count_range": forms.TextInput(attrs={"class": _INPUT, "placeholder": "직원 수 규모"}),
            "listed": forms.Select(attrs={"class": _SELECT}),
            "region": forms.TextInput(attrs={"class": _INPUT, "placeholder": "소재지"}),
            "notes": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 2, "placeholder": "비고"}),
        }
        labels = {
            "name": "회사명",
            "name_en": "영문명",
            "industry": "업종",
            "size_category": "기업 규모",
            "revenue_range": "매출 규모",
            "employee_count_range": "직원 수",
            "listed": "상장 구분",
            "region": "소재지",
            "notes": "비고",
        }


class PreferredCertForm(forms.ModelForm):
    class Meta:
        model = PreferredCert
        fields = ["name", "full_name", "category", "level", "aliases", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "약칭 (예: KICPA)"}),
            "full_name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "정식 명칭 (예: 한국공인회계사)"}),
            "category": forms.Select(attrs={"class": _SELECT}),
            "level": forms.Select(attrs={"class": _SELECT}),
            "aliases": forms.HiddenInput(),
            "notes": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 2, "placeholder": "비고"}),
        }
        labels = {
            "name": "약칭",
            "full_name": "정식 명칭",
            "category": "카테고리",
            "level": "난이도",
            "aliases": "별칭",
            "notes": "비고",
        }

    aliases_text = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": _INPUT,
            "placeholder": "별칭 (세미콜론 구분, 예: CPA;공인회계사)",
        }),
        label="별칭",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.aliases:
            self.fields["aliases_text"].initial = ";".join(self.instance.aliases)

    def clean(self):
        cleaned = super().clean()
        aliases_text = cleaned.get("aliases_text", "")
        cleaned["aliases"] = [a.strip() for a in aliases_text.split(";") if a.strip()] if aliases_text else []
        return cleaned


class CSVImportForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV 파일",
        widget=forms.FileInput(attrs={
            "class": _INPUT,
            "accept": ".csv",
        }),
    )
```

- [ ] **Step 2: Commit**

```bash
git add clients/forms_reference.py
git commit -m "feat(p12): add reference data CRUD forms and CSV import form"
```

---

### Task 3: CSV Handler Service

**Files:**
- Create: `clients/services/__init__.py`
- Create: `clients/services/csv_handler.py`
- Create: `tests/test_p12_reference.py` (CSV tests)

- [ ] **Step 1: Create services package**

Create `clients/services/__init__.py` (empty file).

- [ ] **Step 2: Write CSV handler tests**

Create the beginning of `tests/test_p12_reference.py`:

```python
"""P12: Reference Data Management tests."""

import io
import csv

import pytest
from django.test import Client as TestClient

from accounts.models import Membership, Organization, User
from clients.models import CompanyProfile, PreferredCert, UniversityTier
from clients.services.csv_handler import import_csv, export_csv


# --- Fixtures ---


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def staff_user(db, org):
    user = User.objects.create_user(username="staff", password="test1234", is_staff=True)
    Membership.objects.create(user=user, organization=org)
    return user


@pytest.fixture
def normal_user(db, org):
    user = User.objects.create_user(username="normal", password="test1234", is_staff=False)
    Membership.objects.create(user=user, organization=org)
    return user


@pytest.fixture
def staff_client(staff_user):
    c = TestClient()
    c.login(username="staff", password="test1234")
    return c


@pytest.fixture
def normal_client(normal_user):
    c = TestClient()
    c.login(username="normal", password="test1234")
    return c


# --- CSV Import Tests ---


class TestCSVImport:
    @pytest.mark.django_db
    def test_import_universities_csv(self):
        csv_content = "name,name_en,country,tier,ranking,notes\n서울대학교,Seoul National University,KR,SKY,1,\n"
        result = import_csv(UniversityTier, io.StringIO(csv_content))
        assert result["created"] == 1
        assert result["updated"] == 0
        assert result["errors"] == []
        assert UniversityTier.objects.count() == 1

    @pytest.mark.django_db
    def test_import_universities_upsert(self):
        UniversityTier.objects.create(name="서울대학교", country="KR", tier="SKY", ranking=1)
        csv_content = "name,name_en,country,tier,ranking,notes\n서울대학교,SNU,KR,SKY,1,Updated\n"
        result = import_csv(UniversityTier, io.StringIO(csv_content))
        assert result["created"] == 0
        assert result["updated"] == 1
        u = UniversityTier.objects.get(name="서울대학교", country="KR")
        assert u.name_en == "SNU"
        assert u.notes == "Updated"

    @pytest.mark.django_db
    def test_import_companies_csv(self):
        csv_content = "name,name_en,industry,size_category,revenue_range,employee_count_range,listed,region,notes\n삼성전자,Samsung Electronics,반도체,대기업,,,,서울,\n"
        result = import_csv(CompanyProfile, io.StringIO(csv_content))
        assert result["created"] == 1
        assert CompanyProfile.objects.get(name="삼성전자").industry == "반도체"

    @pytest.mark.django_db
    def test_import_certs_csv_with_aliases(self):
        csv_content = "name,full_name,category,level,aliases,notes\nKICPA,한국공인회계사,회계/재무,상,CPA;공인회계사,\n"
        result = import_csv(PreferredCert, io.StringIO(csv_content))
        assert result["created"] == 1
        cert = PreferredCert.objects.get(name="KICPA")
        assert cert.aliases == ["CPA", "공인회계사"]

    @pytest.mark.django_db
    def test_import_invalid_choice_rolls_back(self):
        csv_content = "name,name_en,country,tier,ranking,notes\n서울대학교,SNU,KR,INVALID,1,\n"
        result = import_csv(UniversityTier, io.StringIO(csv_content))
        assert len(result["errors"]) > 0
        assert UniversityTier.objects.count() == 0

    @pytest.mark.django_db
    def test_import_missing_header_fails(self):
        csv_content = "name,country\n서울대학교,KR\n"
        result = import_csv(UniversityTier, io.StringIO(csv_content))
        assert len(result["errors"]) > 0
        assert "header" in result["errors"][0].lower() or "필수" in result["errors"][0]


class TestCSVExport:
    @pytest.mark.django_db
    def test_export_universities(self):
        UniversityTier.objects.create(name="서울대학교", name_en="SNU", country="KR", tier="SKY", ranking=1)
        output = export_csv(UniversityTier, UniversityTier.objects.all())
        content = output.getvalue()
        assert "서울대학교" in content
        assert content.startswith("\ufeff")  # UTF-8 BOM

    @pytest.mark.django_db
    def test_export_certs_aliases_semicolon(self):
        PreferredCert.objects.create(
            name="KICPA", full_name="한국공인회계사", category="회계/재무",
            aliases=["CPA", "공인회계사"],
        )
        output = export_csv(PreferredCert, PreferredCert.objects.all())
        content = output.getvalue()
        assert "CPA;공인회계사" in content
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_p12_reference.py::TestCSVImport -v`
Expected: ImportError (csv_handler module doesn't exist yet)

- [ ] **Step 4: Implement CSV handler**

Create `clients/services/csv_handler.py`:

```python
"""CSV import/export for reference data models."""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING

from django.db import transaction

from clients.models import CompanyProfile, PreferredCert, UniversityTier

if TYPE_CHECKING:
    from django.db.models import Model, QuerySet


# --- Column definitions per model ---

COLUMNS: dict[type[Model], list[str]] = {
    UniversityTier: ["name", "name_en", "country", "tier", "ranking", "notes"],
    CompanyProfile: [
        "name", "name_en", "industry", "size_category",
        "revenue_range", "employee_count_range", "listed", "region", "notes",
    ],
    PreferredCert: ["name", "full_name", "category", "level", "aliases", "notes"],
}

# Upsert lookup keys per model
LOOKUP_KEYS: dict[type[Model], list[str]] = {
    UniversityTier: ["name", "country"],
    CompanyProfile: ["name"],
    PreferredCert: ["name"],
}

# Required columns (must be present in CSV header)
REQUIRED_COLUMNS: dict[type[Model], list[str]] = {
    UniversityTier: ["name", "country", "tier"],
    CompanyProfile: ["name"],
    PreferredCert: ["name", "category"],
}

# Fields with choices that need validation
_CHOICE_FIELDS: dict[type[Model], dict[str, set[str]]] = {
    UniversityTier: {
        "tier": {c.value for c in UniversityTier.Tier},
    },
    CompanyProfile: {
        "size_category": {c.value for c in CompanyProfile.SizeCategory} | {""},
        "listed": {c.value for c in CompanyProfile.Listed} | {""},
    },
    PreferredCert: {
        "category": {c.value for c in PreferredCert.Category},
        "level": {c.value for c in PreferredCert.Level} | {""},
    },
}


def import_csv(
    model: type[Model],
    file_obj: io.StringIO | io.TextIOWrapper,
) -> dict:
    """Import CSV data into a reference model.

    Returns dict with keys: created, updated, errors (list of str).
    On any error, entire transaction is rolled back.
    """
    errors: list[str] = []
    created = 0
    updated = 0

    try:
        reader = csv.DictReader(file_obj)
    except Exception as e:
        return {"created": 0, "updated": 0, "errors": [f"CSV 파싱 오류: {e}"]}

    if reader.fieldnames is None:
        return {"created": 0, "updated": 0, "errors": ["CSV 파일이 비어있습니다."]}

    # Header validation
    required = set(REQUIRED_COLUMNS.get(model, []))
    actual = set(reader.fieldnames)
    missing = required - actual
    if missing:
        return {
            "created": 0,
            "updated": 0,
            "errors": [f"필수 컬럼 누락: {', '.join(sorted(missing))}"],
        }

    columns = COLUMNS[model]
    choice_fields = _CHOICE_FIELDS.get(model, {})
    lookup_keys = LOOKUP_KEYS[model]

    try:
        with transaction.atomic():
            for row_num, row in enumerate(reader, start=2):  # row 2 = first data row
                # Only use columns defined for this model
                data = {}
                for col in columns:
                    val = row.get(col, "").strip()
                    # Handle aliases field: semicolon-separated → list
                    if col == "aliases":
                        data[col] = [a.strip() for a in val.split(";") if a.strip()] if val else []
                    # Handle ranking field: empty → None
                    elif col == "ranking":
                        data[col] = int(val) if val else None
                    else:
                        data[col] = val

                # Choice validation
                for field_name, valid_values in choice_fields.items():
                    val = data.get(field_name, "")
                    if val and val not in valid_values:
                        errors.append(
                            f"행 {row_num}: '{field_name}' 값 '{val}'이(가) 유효하지 않습니다."
                        )

                # Required field validation
                for req in REQUIRED_COLUMNS.get(model, []):
                    if not data.get(req):
                        errors.append(f"행 {row_num}: 필수 필드 '{req}'이(가) 비어있습니다.")

            if errors:
                raise _RollbackSignal()

            # Second pass: actual upsert (re-read from same data)
            file_obj.seek(0)
            reader2 = csv.DictReader(file_obj)
            for row in reader2:
                data = {}
                for col in columns:
                    val = row.get(col, "").strip()
                    if col == "aliases":
                        data[col] = [a.strip() for a in val.split(";") if a.strip()] if val else []
                    elif col == "ranking":
                        data[col] = int(val) if val else None
                    else:
                        data[col] = val

                lookup = {k: data[k] for k in lookup_keys}
                defaults = {k: v for k, v in data.items() if k not in lookup_keys}

                _, is_created = model.objects.update_or_create(
                    **lookup, defaults=defaults,
                )
                if is_created:
                    created += 1
                else:
                    updated += 1

    except _RollbackSignal:
        pass  # errors list already populated

    return {"created": created, "updated": updated, "errors": errors}


class _RollbackSignal(Exception):
    """Internal signal to trigger transaction rollback."""


def export_csv(model: type[Model], queryset: QuerySet) -> io.StringIO:
    """Export queryset to CSV StringIO with UTF-8 BOM.

    Returns StringIO with CSV content.
    """
    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM for Excel compatibility

    columns = COLUMNS[model]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()

    for obj in queryset:
        row = {}
        for col in columns:
            val = getattr(obj, col, "")
            if col == "aliases" and isinstance(val, list):
                row[col] = ";".join(val)
            elif val is None:
                row[col] = ""
            else:
                row[col] = str(val)
        writer.writerow(row)

    return output
```

- [ ] **Step 5: Run CSV tests**

Run: `uv run pytest tests/test_p12_reference.py::TestCSVImport tests/test_p12_reference.py::TestCSVExport -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add clients/services/__init__.py clients/services/csv_handler.py tests/test_p12_reference.py
git commit -m "feat(p12): add CSV import/export handler with validation and upsert"
```

---

### Task 4: Views + URLs + Templates (University Tab)

**Files:**
- Create: `clients/views_reference.py`
- Create: `clients/urls_reference.py`
- Modify: `main/urls.py`
- Create: `clients/templates/clients/reference_index.html`
- Create: `clients/templates/clients/partials/ref_universities.html`
- Create: `clients/templates/clients/partials/ref_form_modal.html`
- Create: `clients/templates/clients/partials/ref_import_result.html`

- [ ] **Step 1: Create views_reference.py with university views**

Create `clients/views_reference.py`:

```python
"""Reference data management views.

Permission model:
- Read (list, search, export): @login_required
- Write (create, update, delete, import): @staff_member_required
"""

from __future__ import annotations

import io

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from .forms_reference import (
    CompanyProfileForm,
    CSVImportForm,
    PreferredCertForm,
    UniversityTierForm,
)
from .models import CompanyProfile, PreferredCert, UniversityTier
from .services.csv_handler import COLUMNS, export_csv, import_csv

PAGE_SIZE = 30


# --- Index (redirects to university tab) ---


@login_required
def reference_index(request):
    """Reference management main page, defaults to universities tab."""
    return _render_reference_page(request, "universities")


# --- University views ---


@login_required
def reference_universities(request):
    """University ranking tab content."""
    qs = UniversityTier.objects.all()
    q = request.GET.get("q", "").strip()
    country = request.GET.get("country", "").strip()
    tier = request.GET.get("tier", "").strip()

    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(name_en__icontains=q))
    if country:
        qs = qs.filter(country=country)
    if tier:
        qs = qs.filter(tier=tier)

    paginator = Paginator(qs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    ctx = {
        "page_obj": page_obj,
        "q": q,
        "country": country,
        "tier": tier,
        "tier_choices": UniversityTier.Tier.choices,
        "countries": UniversityTier.objects.values_list("country", flat=True).distinct().order_by("country"),
        "active_tab": "universities",
        "is_staff": request.user.is_staff,
        "import_form": CSVImportForm(),
    }

    if request.headers.get("HX-Request"):
        return render(request, "clients/partials/ref_universities.html", ctx)
    return _render_reference_page(request, "universities", ctx)


@staff_member_required
def university_create(request):
    """Create a university. GET=form, POST=save."""
    if request.method == "POST":
        form = UniversityTierForm(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={"HX-Trigger": "universityChanged"})
    else:
        form = UniversityTierForm()
    return render(request, "clients/partials/ref_form_modal.html", {
        "form": form, "title": "대학 추가", "post_url": "/reference/universities/new/",
    })


@staff_member_required
def university_update(request, pk):
    """Update a university."""
    obj = get_object_or_404(UniversityTier, pk=pk)
    if request.method == "POST":
        form = UniversityTierForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={"HX-Trigger": "universityChanged"})
    else:
        form = UniversityTierForm(instance=obj)
    return render(request, "clients/partials/ref_form_modal.html", {
        "form": form, "title": "대학 수정", "post_url": f"/reference/universities/{pk}/edit/",
    })


@staff_member_required
def university_delete(request, pk):
    """Delete a university."""
    if request.method != "POST":
        return HttpResponse(status=405)
    obj = get_object_or_404(UniversityTier, pk=pk)
    obj.delete()
    return HttpResponse(status=204, headers={"HX-Trigger": "universityChanged"})


@staff_member_required
def university_import(request):
    """Import universities from CSV."""
    if request.method != "POST":
        return HttpResponse(status=405)
    form = CSVImportForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "clients/partials/ref_import_result.html", {
            "errors": ["파일을 선택해 주세요."],
        })
    csv_file = request.FILES["csv_file"]
    try:
        content = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return render(request, "clients/partials/ref_import_result.html", {
            "errors": ["UTF-8 인코딩이 아닙니다. UTF-8 파일을 사용해 주세요."],
        })
    result = import_csv(UniversityTier, io.StringIO(content))
    return render(request, "clients/partials/ref_import_result.html", result)


@login_required
def university_export(request):
    """Export universities to CSV."""
    qs = UniversityTier.objects.all()
    q = request.GET.get("q", "").strip()
    country = request.GET.get("country", "").strip()
    tier = request.GET.get("tier", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(name_en__icontains=q))
    if country:
        qs = qs.filter(country=country)
    if tier:
        qs = qs.filter(tier=tier)

    output = export_csv(UniversityTier, qs)
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="universities.csv"'
    return response


# --- Company views ---
# (placeholder — will be implemented in Task 5)


# --- Cert views ---
# (placeholder — will be implemented in Task 6)


# --- Helper ---


def _render_reference_page(request, active_tab, tab_ctx=None):
    """Render full reference page with tab content."""
    ctx = {"active_tab": active_tab}
    if tab_ctx:
        ctx.update(tab_ctx)
    else:
        # Default: load university data
        qs = UniversityTier.objects.all()
        paginator = Paginator(qs, PAGE_SIZE)
        ctx.update({
            "page_obj": paginator.get_page(1),
            "q": "",
            "country": "",
            "tier": "",
            "tier_choices": UniversityTier.Tier.choices,
            "countries": UniversityTier.objects.values_list("country", flat=True).distinct().order_by("country"),
            "is_staff": request.user.is_staff,
            "import_form": CSVImportForm(),
        })
    return render(request, "clients/reference_index.html", ctx)
```

- [ ] **Step 2: Create urls_reference.py**

Create `clients/urls_reference.py`:

```python
from django.urls import path

from . import views_reference as views

app_name = "reference"

urlpatterns = [
    path("", views.reference_index, name="index"),
    # Universities
    path("universities/", views.reference_universities, name="universities"),
    path("universities/new/", views.university_create, name="university_create"),
    path("universities/<uuid:pk>/edit/", views.university_update, name="university_update"),
    path("universities/<uuid:pk>/delete/", views.university_delete, name="university_delete"),
    path("universities/import/", views.university_import, name="university_import"),
    path("universities/export/", views.university_export, name="university_export"),
]
```

- [ ] **Step 3: Register URL in main/urls.py**

Add to `main/urls.py` after the `clients` include:

```python
path("reference/", include("clients.urls_reference")),
```

- [ ] **Step 4: Create reference_index.html**

Create `clients/templates/clients/reference_index.html`:

```html
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}

{% block title %}레퍼런스 관리 — synco{% endblock %}

{% block content %}
<div class="p-4 lg:p-8 space-y-6">
  <h1 class="text-heading font-bold">레퍼런스 관리</h1>

  <!-- Tabs -->
  <div class="flex gap-1 border-b border-gray-200">
    <button hx-get="/reference/universities/" hx-target="#ref-tab-content" hx-push-url="/reference/universities/"
            class="ref-tab px-4 py-2.5 text-[15px] font-medium rounded-t-lg border-b-2 -mb-px {% if active_tab == 'universities' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700{% endif %}"
            data-tab="universities">
      대학 랭킹
    </button>
    <button hx-get="/reference/companies/" hx-target="#ref-tab-content" hx-push-url="/reference/companies/"
            class="ref-tab px-4 py-2.5 text-[15px] font-medium rounded-t-lg border-b-2 -mb-px {% if active_tab == 'companies' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700{% endif %}"
            data-tab="companies">
      기업 DB
    </button>
    <button hx-get="/reference/certs/" hx-target="#ref-tab-content" hx-push-url="/reference/certs/"
            class="ref-tab px-4 py-2.5 text-[15px] font-medium rounded-t-lg border-b-2 -mb-px {% if active_tab == 'certs' %}border-primary text-primary{% else %}border-transparent text-gray-500 hover:text-gray-700{% endif %}"
            data-tab="certs">
      자격증
    </button>
  </div>

  <!-- Tab Content -->
  <div id="ref-tab-content">
    {% if active_tab == "universities" %}
      {% include "clients/partials/ref_universities.html" %}
    {% elif active_tab == "companies" %}
      {% include "clients/partials/ref_companies.html" %}
    {% elif active_tab == "certs" %}
      {% include "clients/partials/ref_certs.html" %}
    {% endif %}
  </div>
</div>

<script>
document.body.addEventListener('htmx:afterSwap', function(e) {
  if (e.detail.target.id === 'ref-tab-content') {
    var path = window.location.pathname;
    document.querySelectorAll('.ref-tab').forEach(function(tab) {
      var key = tab.dataset.tab;
      var active = path.includes('/' + key);
      tab.className = tab.className.replace(/border-primary text-primary|border-transparent text-gray-500 hover:text-gray-700/g, '');
      tab.classList.add(active ? 'border-primary' : 'border-transparent');
      tab.classList.add(active ? 'text-primary' : 'text-gray-500');
      if (!active) tab.classList.add('hover:text-gray-700');
    });
  }
});
</script>
{% endblock %}
```

- [ ] **Step 5: Create ref_universities.html partial**

Create `clients/templates/clients/partials/ref_universities.html`:

```html
<!-- Filters -->
<div class="flex flex-wrap gap-2 mb-4">
  <form hx-get="/reference/universities/" hx-target="#ref-tab-content" class="flex flex-wrap gap-2 w-full">
    <input type="text" name="q" value="{{ q }}" placeholder="대학명 검색"
           class="flex-1 min-w-[200px] border border-gray-300 rounded-lg px-3 py-2 text-[15px] focus:ring-2 focus:ring-primary focus:border-primary">
    <select name="country" class="border border-gray-300 rounded-lg px-3 py-2 text-[15px]">
      <option value="">전체 국가</option>
      {% for c in countries %}
      <option value="{{ c }}" {% if country == c %}selected{% endif %}>{{ c }}</option>
      {% endfor %}
    </select>
    <select name="tier" class="border border-gray-300 rounded-lg px-3 py-2 text-[15px]">
      <option value="">전체 티어</option>
      {% for val, label in tier_choices %}
      <option value="{{ val }}" {% if tier == val %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>
    <button type="submit" class="bg-gray-100 text-gray-700 font-medium py-2 px-4 rounded-lg text-[15px] hover:bg-gray-200">검색</button>
  </form>
</div>

<!-- Table -->
{% if page_obj.object_list %}
<div class="overflow-x-auto">
  <table class="w-full text-[15px]">
    <thead>
      <tr class="border-b border-gray-200 text-left text-gray-500 text-[13px]">
        <th class="pb-2 font-medium">대학명</th>
        <th class="pb-2 font-medium">영문명</th>
        <th class="pb-2 font-medium">국가</th>
        <th class="pb-2 font-medium">티어</th>
        <th class="pb-2 font-medium">순위</th>
        {% if is_staff %}<th class="pb-2 font-medium"></th>{% endif %}
      </tr>
    </thead>
    <tbody>
      {% for u in page_obj %}
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-2.5 font-medium text-gray-900">{{ u.name }}</td>
        <td class="py-2.5 text-gray-600">{{ u.name_en }}</td>
        <td class="py-2.5 text-gray-600">{{ u.country }}</td>
        <td class="py-2.5"><span class="inline-block bg-blue-50 text-blue-700 text-[13px] px-2 py-0.5 rounded">{{ u.get_tier_display }}</span></td>
        <td class="py-2.5 text-gray-600">{{ u.ranking|default:"-" }}</td>
        {% if is_staff %}
        <td class="py-2.5 text-right space-x-1">
          <button hx-get="/reference/universities/{{ u.pk }}/edit/" hx-target="#ref-form-area"
                  class="text-[13px] text-primary hover:underline">수정</button>
          <button hx-post="/reference/universities/{{ u.pk }}/delete/" hx-confirm="정말 삭제하시겠습니까?"
                  hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'
                  class="text-[13px] text-red-500 hover:underline">삭제</button>
        </td>
        {% endif %}
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<!-- Pagination -->
{% if page_obj.has_other_pages %}
<div class="flex justify-center gap-2 pt-4">
  {% if page_obj.has_previous %}
  <button hx-get="/reference/universities/?{% if q %}q={{ q }}&{% endif %}{% if country %}country={{ country }}&{% endif %}{% if tier %}tier={{ tier }}&{% endif %}page={{ page_obj.previous_page_number }}"
          hx-target="#ref-tab-content"
          class="px-3 py-2 rounded-lg text-[15px] text-gray-500 hover:bg-gray-100">이전</button>
  {% endif %}
  <span class="px-3 py-2 text-[15px] text-gray-500">{{ page_obj.number }} / {{ page_obj.paginator.num_pages }}</span>
  {% if page_obj.has_next %}
  <button hx-get="/reference/universities/?{% if q %}q={{ q }}&{% endif %}{% if country %}country={{ country }}&{% endif %}{% if tier %}tier={{ tier }}&{% endif %}page={{ page_obj.next_page_number }}"
          hx-target="#ref-tab-content"
          class="px-3 py-2 rounded-lg text-[15px] text-gray-500 hover:bg-gray-100">다음</button>
  {% endif %}
</div>
{% endif %}
{% else %}
<p class="text-center text-gray-500 py-8">{% if q %}검색 결과가 없습니다.{% else %}등록된 대학이 없습니다.{% endif %}</p>
{% endif %}

<!-- Actions -->
<div class="flex gap-2 pt-4">
  {% if is_staff %}
  <button hx-get="/reference/universities/new/" hx-target="#ref-form-area"
          class="bg-primary text-white font-semibold py-2 px-4 rounded-lg text-[15px] hover:bg-primary-dark transition">+ 추가</button>
  <form hx-post="/reference/universities/import/" hx-target="#ref-import-result" hx-encoding="multipart/form-data" class="flex gap-2">
    {% csrf_token %}
    {{ import_form.csv_file }}
    <button type="submit" class="bg-gray-100 text-gray-700 font-medium py-2 px-4 rounded-lg text-[15px] hover:bg-gray-200">CSV 가져오기</button>
  </form>
  {% endif %}
  <a href="/reference/universities/export/?{% if q %}q={{ q }}&{% endif %}{% if country %}country={{ country }}&{% endif %}{% if tier %}tier={{ tier }}{% endif %}"
     hx-boost="false"
     class="bg-gray-100 text-gray-700 font-medium py-2 px-4 rounded-lg text-[15px] hover:bg-gray-200">CSV 내보내기</a>
</div>

<!-- Form area (for modals) -->
<div id="ref-form-area"></div>
<div id="ref-import-result"></div>

<script>
document.body.addEventListener('universityChanged', function() {
  htmx.ajax('GET', '/reference/universities/', {target: '#ref-tab-content'});
});
</script>
```

- [ ] **Step 6: Create ref_form_modal.html**

Create `clients/templates/clients/partials/ref_form_modal.html`:

```html
<div class="fixed inset-0 bg-black/30 z-50 flex items-center justify-center" id="ref-modal-overlay"
     onclick="if(event.target===this)this.remove()">
  <div class="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 p-6 space-y-4">
    <h2 class="text-lg font-bold">{{ title }}</h2>
    <form hx-post="{{ post_url }}" hx-target="#ref-form-area" hx-swap="innerHTML" class="space-y-3">
      {% csrf_token %}
      {% for field in form %}
      {% if not field.is_hidden %}
      <div>
        <label class="block text-[13px] font-medium text-gray-700 mb-1">{{ field.label }}</label>
        {{ field }}
        {% if field.errors %}
        <p class="text-red-500 text-[13px] mt-0.5">{{ field.errors.0 }}</p>
        {% endif %}
      </div>
      {% else %}
      {{ field }}
      {% endif %}
      {% endfor %}
      <div class="flex justify-end gap-2 pt-2">
        <button type="button" onclick="document.getElementById('ref-modal-overlay').remove()"
                class="px-4 py-2 text-[15px] text-gray-500 hover:bg-gray-100 rounded-lg">취소</button>
        <button type="submit"
                class="bg-primary text-white font-semibold px-4 py-2 rounded-lg text-[15px] hover:bg-primary-dark">저장</button>
      </div>
    </form>
  </div>
</div>
```

- [ ] **Step 7: Create ref_import_result.html**

Create `clients/templates/clients/partials/ref_import_result.html`:

```html
<div class="mt-4 p-4 rounded-lg {% if errors %}bg-red-50 border border-red-200{% else %}bg-green-50 border border-green-200{% endif %}">
  {% if errors %}
  <h3 class="font-semibold text-red-700 text-[15px] mb-2">가져오기 실패</h3>
  <ul class="text-[13px] text-red-600 space-y-1">
    {% for err in errors %}
    <li>{{ err }}</li>
    {% endfor %}
  </ul>
  {% else %}
  <h3 class="font-semibold text-green-700 text-[15px] mb-1">가져오기 완료</h3>
  <p class="text-[13px] text-green-600">추가: {{ created }}건, 수정: {{ updated }}건</p>
  {% endif %}
</div>
```

- [ ] **Step 8: Write view tests for universities**

Add to `tests/test_p12_reference.py`:

```python
# --- View Tests: Universities ---


class TestReferenceAccess:
    @pytest.mark.django_db
    def test_anon_redirected(self):
        c = TestClient()
        resp = c.get("/reference/")
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    @pytest.mark.django_db
    def test_logged_in_can_read(self, normal_client):
        resp = normal_client.get("/reference/")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_non_staff_cannot_create(self, normal_client):
        resp = normal_client.get("/reference/universities/new/")
        assert resp.status_code == 302  # staff_member_required redirects

    @pytest.mark.django_db
    def test_staff_can_create(self, staff_client):
        resp = staff_client.get("/reference/universities/new/")
        assert resp.status_code == 200


class TestUniversityCRUD:
    @pytest.mark.django_db
    def test_create_university(self, staff_client):
        resp = staff_client.post("/reference/universities/new/", {
            "name": "서울대학교",
            "name_en": "Seoul National University",
            "country": "KR",
            "tier": "SKY",
            "ranking": "1",
            "notes": "",
        })
        assert resp.status_code == 204
        assert UniversityTier.objects.filter(name="서울대학교").exists()

    @pytest.mark.django_db
    def test_update_university(self, staff_client):
        u = UniversityTier.objects.create(name="서울대학교", country="KR", tier="SKY")
        resp = staff_client.post(f"/reference/universities/{u.pk}/edit/", {
            "name": "서울대학교",
            "name_en": "SNU",
            "country": "KR",
            "tier": "SKY",
            "ranking": "1",
            "notes": "Updated",
        })
        assert resp.status_code == 204
        u.refresh_from_db()
        assert u.name_en == "SNU"

    @pytest.mark.django_db
    def test_delete_university(self, staff_client):
        u = UniversityTier.objects.create(name="서울대학교", country="KR", tier="SKY")
        resp = staff_client.post(f"/reference/universities/{u.pk}/delete/")
        assert resp.status_code == 204
        assert not UniversityTier.objects.filter(pk=u.pk).exists()

    @pytest.mark.django_db
    def test_list_universities(self, normal_client):
        UniversityTier.objects.create(name="서울대학교", country="KR", tier="SKY")
        resp = normal_client.get("/reference/universities/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert "서울대학교" in resp.content.decode()

    @pytest.mark.django_db
    def test_search_universities(self, normal_client):
        UniversityTier.objects.create(name="서울대학교", country="KR", tier="SKY")
        UniversityTier.objects.create(name="MIT", country="US", tier="OVERSEAS_TOP")
        resp = normal_client.get("/reference/universities/?q=MIT", HTTP_HX_REQUEST="true")
        content = resp.content.decode()
        assert "MIT" in content
        assert "서울대학교" not in content

    @pytest.mark.django_db
    def test_filter_by_tier(self, normal_client):
        UniversityTier.objects.create(name="서울대학교", country="KR", tier="SKY")
        UniversityTier.objects.create(name="성균관대학교", country="KR", tier="SSG")
        resp = normal_client.get("/reference/universities/?tier=SKY", HTTP_HX_REQUEST="true")
        content = resp.content.decode()
        assert "서울대학교" in content
        assert "성균관대학교" not in content

    @pytest.mark.django_db
    def test_unique_constraint(self, staff_client):
        UniversityTier.objects.create(name="서울대학교", country="KR", tier="SKY")
        resp = staff_client.post("/reference/universities/new/", {
            "name": "서울대학교",
            "country": "KR",
            "tier": "SKY",
        })
        assert resp.status_code == 200  # form returned with errors
        assert UniversityTier.objects.filter(name="서울대학교").count() == 1


class TestUniversityCSVViews:
    @pytest.mark.django_db
    def test_export_csv(self, normal_client):
        UniversityTier.objects.create(name="서울대학교", country="KR", tier="SKY", ranking=1)
        resp = normal_client.get("/reference/universities/export/")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "text/csv; charset=utf-8-sig"
        assert "서울대학교" in resp.content.decode("utf-8-sig")

    @pytest.mark.django_db
    def test_import_csv(self, staff_client):
        csv_bytes = "name,name_en,country,tier,ranking,notes\n서울대학교,SNU,KR,SKY,1,\n".encode("utf-8-sig")
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("test.csv", csv_bytes, content_type="text/csv")
        resp = staff_client.post("/reference/universities/import/", {"csv_file": f})
        assert resp.status_code == 200
        assert UniversityTier.objects.filter(name="서울대학교").exists()
```

- [ ] **Step 9: Run tests**

Run: `uv run pytest tests/test_p12_reference.py -v`
Expected: All pass.

- [ ] **Step 10: Commit**

```bash
git add clients/views_reference.py clients/urls_reference.py main/urls.py \
       clients/templates/clients/reference_index.html \
       clients/templates/clients/partials/ref_universities.html \
       clients/templates/clients/partials/ref_form_modal.html \
       clients/templates/clients/partials/ref_import_result.html \
       tests/test_p12_reference.py
git commit -m "feat(p12): add university reference tab with CRUD, CSV import/export, and search"
```

---

### Task 5: Company Tab Views + Autofill Service

**Files:**
- Modify: `clients/views_reference.py` (add company views)
- Modify: `clients/urls_reference.py` (add company URLs)
- Create: `clients/services/company_autofill.py`
- Create: `clients/templates/clients/partials/ref_companies.html`
- Modify: `tests/test_p12_reference.py` (add company tests)

- [ ] **Step 1: Add company views to views_reference.py**

Add these views to `clients/views_reference.py`, replacing the company placeholder:

```python
# --- Company views ---


@login_required
def reference_companies(request):
    """Company DB tab content."""
    qs = CompanyProfile.objects.all()
    q = request.GET.get("q", "").strip()
    listed = request.GET.get("listed", "").strip()
    size = request.GET.get("size", "").strip()
    industry = request.GET.get("industry", "").strip()

    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(name_en__icontains=q))
    if listed:
        qs = qs.filter(listed=listed)
    if size:
        qs = qs.filter(size_category=size)
    if industry:
        qs = qs.filter(industry__icontains=industry)

    paginator = Paginator(qs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    ctx = {
        "page_obj": page_obj,
        "q": q,
        "listed_filter": listed,
        "size_filter": size,
        "industry_filter": industry,
        "listed_choices": CompanyProfile.Listed.choices,
        "size_choices": CompanyProfile.SizeCategory.choices,
        "active_tab": "companies",
        "is_staff": request.user.is_staff,
        "import_form": CSVImportForm(),
    }

    if request.headers.get("HX-Request"):
        return render(request, "clients/partials/ref_companies.html", ctx)
    return _render_reference_page(request, "companies", ctx)


@staff_member_required
def company_create(request):
    """Create a company."""
    if request.method == "POST":
        form = CompanyProfileForm(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={"HX-Trigger": "companyChanged"})
    else:
        form = CompanyProfileForm()
    return render(request, "clients/partials/ref_form_modal.html", {
        "form": form, "title": "기업 추가",
        "post_url": "/reference/companies/new/",
        "show_autofill": True,
    })


@staff_member_required
def company_update(request, pk):
    """Update a company."""
    obj = get_object_or_404(CompanyProfile, pk=pk)
    if request.method == "POST":
        form = CompanyProfileForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={"HX-Trigger": "companyChanged"})
    else:
        form = CompanyProfileForm(instance=obj)
    return render(request, "clients/partials/ref_form_modal.html", {
        "form": form, "title": "기업 수정",
        "post_url": f"/reference/companies/{pk}/edit/",
        "show_autofill": True,
    })


@staff_member_required
def company_delete(request, pk):
    """Delete a company."""
    if request.method != "POST":
        return HttpResponse(status=405)
    obj = get_object_or_404(CompanyProfile, pk=pk)
    obj.delete()
    return HttpResponse(status=204, headers={"HX-Trigger": "companyChanged"})


@staff_member_required
def company_autofill(request, pk):
    """Autofill company fields using Gemini web search."""
    import json
    from .services.company_autofill import autofill_company

    if request.method != "POST":
        return HttpResponse(status=405)
    obj = get_object_or_404(CompanyProfile, pk=pk)
    try:
        result = autofill_company(obj.name)
        return HttpResponse(
            json.dumps(result, ensure_ascii=False),
            content_type="application/json",
        )
    except Exception:
        return HttpResponse(
            json.dumps({"error": "자동채움에 실패했습니다. 직접 입력해 주세요."}, ensure_ascii=False),
            content_type="application/json",
            status=500,
        )


@staff_member_required
def company_import(request):
    """Import companies from CSV."""
    if request.method != "POST":
        return HttpResponse(status=405)
    form = CSVImportForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "clients/partials/ref_import_result.html", {"errors": ["파일을 선택해 주세요."]})
    csv_file = request.FILES["csv_file"]
    try:
        content = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return render(request, "clients/partials/ref_import_result.html", {"errors": ["UTF-8 인코딩이 아닙니다."]})
    result = import_csv(CompanyProfile, io.StringIO(content))
    return render(request, "clients/partials/ref_import_result.html", result)


@login_required
def company_export(request):
    """Export companies to CSV."""
    qs = CompanyProfile.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(name_en__icontains=q))
    listed = request.GET.get("listed", "").strip()
    if listed:
        qs = qs.filter(listed=listed)
    size = request.GET.get("size", "").strip()
    if size:
        qs = qs.filter(size_category=size)

    output = export_csv(CompanyProfile, qs)
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="companies.csv"'
    return response
```

- [ ] **Step 2: Add company URLs**

Add to `clients/urls_reference.py`:

```python
    # Companies
    path("companies/", views.reference_companies, name="companies"),
    path("companies/new/", views.company_create, name="company_create"),
    path("companies/<uuid:pk>/edit/", views.company_update, name="company_update"),
    path("companies/<uuid:pk>/delete/", views.company_delete, name="company_delete"),
    path("companies/<uuid:pk>/autofill/", views.company_autofill, name="company_autofill"),
    path("companies/import/", views.company_import, name="company_import"),
    path("companies/export/", views.company_export, name="company_export"),
```

- [ ] **Step 3: Create company autofill service**

Create `clients/services/company_autofill.py`:

```python
"""Company autofill via Gemini API + Google Search grounding.

Sends company name to Gemini to retrieve public company info
(industry, size, revenue, listing status, region).
"""

from __future__ import annotations

import json
import logging

from django.conf import settings
from google import genai
from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """다음 한국 기업의 정보를 조사해주세요: "{company_name}"

아래 JSON 형식으로만 응답하세요. 확인되지 않는 필드는 빈 문자열로 남기세요.
{{
  "industry": "업종 (예: 반도체, 금융, 건설)",
  "size_category": "대기업/중견/중소/외국계/스타트업 중 하나",
  "revenue_range": "연매출 규모 (예: 1조~5조)",
  "employee_count_range": "직원 수 규모 (예: 1000~5000명)",
  "listed": "KOSPI/KOSDAQ/비상장/해외상장 중 하나",
  "region": "본사 소재지 (예: 서울 강남구)"
}}"""

AUTOFILL_FIELDS = [
    "industry", "size_category", "revenue_range",
    "employee_count_range", "listed", "region",
]


def autofill_company(company_name: str) -> dict[str, str]:
    """Look up public company info via Gemini + Google Search.

    Args:
        company_name: Korean company name to look up.

    Returns:
        Dict with keys: industry, size_category, revenue_range,
        employee_count_range, listed, region. Empty string for unknown fields.

    Raises:
        RuntimeError: If Gemini API key is not configured.
        Exception: On API call failure (caller should handle).
    """
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in settings")

    client = genai.Client(api_key=api_key)
    google_search_tool = Tool(google_search=GoogleSearch())

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=_PROMPT_TEMPLATE.format(company_name=company_name),
        config=GenerateContentConfig(
            tools=[google_search_tool],
            temperature=0.1,
        ),
    )

    text = response.text.strip()
    # Extract JSON from response (may be wrapped in markdown code block)
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    data = json.loads(text)

    # Only return expected fields with string values
    result = {}
    for field in AUTOFILL_FIELDS:
        result[field] = str(data.get(field, "")).strip()
    return result
```

- [ ] **Step 4: Create ref_companies.html partial**

Create `clients/templates/clients/partials/ref_companies.html`:

```html
<!-- Filters -->
<div class="flex flex-wrap gap-2 mb-4">
  <form hx-get="/reference/companies/" hx-target="#ref-tab-content" class="flex flex-wrap gap-2 w-full">
    <input type="text" name="q" value="{{ q }}" placeholder="회사명 검색"
           class="flex-1 min-w-[200px] border border-gray-300 rounded-lg px-3 py-2 text-[15px] focus:ring-2 focus:ring-primary focus:border-primary">
    <select name="listed" class="border border-gray-300 rounded-lg px-3 py-2 text-[15px]">
      <option value="">전체 상장</option>
      {% for val, label in listed_choices %}
      <option value="{{ val }}" {% if listed_filter == val %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>
    <select name="size" class="border border-gray-300 rounded-lg px-3 py-2 text-[15px]">
      <option value="">전체 규모</option>
      {% for val, label in size_choices %}
      <option value="{{ val }}" {% if size_filter == val %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>
    <button type="submit" class="bg-gray-100 text-gray-700 font-medium py-2 px-4 rounded-lg text-[15px] hover:bg-gray-200">검색</button>
  </form>
</div>

<!-- Table -->
{% if page_obj.object_list %}
<div class="overflow-x-auto">
  <table class="w-full text-[15px]">
    <thead>
      <tr class="border-b border-gray-200 text-left text-gray-500 text-[13px]">
        <th class="pb-2 font-medium">회사명</th>
        <th class="pb-2 font-medium">업종</th>
        <th class="pb-2 font-medium">규모</th>
        <th class="pb-2 font-medium">상장</th>
        <th class="pb-2 font-medium">소재지</th>
        {% if is_staff %}<th class="pb-2 font-medium"></th>{% endif %}
      </tr>
    </thead>
    <tbody>
      {% for c in page_obj %}
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-2.5 font-medium text-gray-900">{{ c.name }}</td>
        <td class="py-2.5 text-gray-600">{{ c.industry|default:"-" }}</td>
        <td class="py-2.5 text-gray-600">{{ c.get_size_category_display|default:"-" }}</td>
        <td class="py-2.5 text-gray-600">{{ c.get_listed_display|default:"-" }}</td>
        <td class="py-2.5 text-gray-600">{{ c.region|default:"-" }}</td>
        {% if is_staff %}
        <td class="py-2.5 text-right space-x-1">
          <button hx-get="/reference/companies/{{ c.pk }}/edit/" hx-target="#ref-form-area"
                  class="text-[13px] text-primary hover:underline">수정</button>
          <button hx-post="/reference/companies/{{ c.pk }}/delete/" hx-confirm="정말 삭제하시겠습니까?"
                  hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'
                  class="text-[13px] text-red-500 hover:underline">삭제</button>
        </td>
        {% endif %}
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

{% if page_obj.has_other_pages %}
<div class="flex justify-center gap-2 pt-4">
  {% if page_obj.has_previous %}
  <button hx-get="/reference/companies/?{% if q %}q={{ q }}&{% endif %}{% if listed_filter %}listed={{ listed_filter }}&{% endif %}{% if size_filter %}size={{ size_filter }}&{% endif %}page={{ page_obj.previous_page_number }}"
          hx-target="#ref-tab-content"
          class="px-3 py-2 rounded-lg text-[15px] text-gray-500 hover:bg-gray-100">이전</button>
  {% endif %}
  <span class="px-3 py-2 text-[15px] text-gray-500">{{ page_obj.number }} / {{ page_obj.paginator.num_pages }}</span>
  {% if page_obj.has_next %}
  <button hx-get="/reference/companies/?{% if q %}q={{ q }}&{% endif %}{% if listed_filter %}listed={{ listed_filter }}&{% endif %}{% if size_filter %}size={{ size_filter }}&{% endif %}page={{ page_obj.next_page_number }}"
          hx-target="#ref-tab-content"
          class="px-3 py-2 rounded-lg text-[15px] text-gray-500 hover:bg-gray-100">다음</button>
  {% endif %}
</div>
{% endif %}
{% else %}
<p class="text-center text-gray-500 py-8">{% if q %}검색 결과가 없습니다.{% else %}등록된 기업이 없습니다.{% endif %}</p>
{% endif %}

<!-- Actions -->
<div class="flex gap-2 pt-4">
  {% if is_staff %}
  <button hx-get="/reference/companies/new/" hx-target="#ref-form-area"
          class="bg-primary text-white font-semibold py-2 px-4 rounded-lg text-[15px] hover:bg-primary-dark transition">+ 추가</button>
  <form hx-post="/reference/companies/import/" hx-target="#ref-import-result" hx-encoding="multipart/form-data" class="flex gap-2">
    {% csrf_token %}
    {{ import_form.csv_file }}
    <button type="submit" class="bg-gray-100 text-gray-700 font-medium py-2 px-4 rounded-lg text-[15px] hover:bg-gray-200">CSV 가져오기</button>
  </form>
  {% endif %}
  <a href="/reference/companies/export/?{% if q %}q={{ q }}&{% endif %}{% if listed_filter %}listed={{ listed_filter }}&{% endif %}{% if size_filter %}size={{ size_filter }}{% endif %}"
     hx-boost="false"
     class="bg-gray-100 text-gray-700 font-medium py-2 px-4 rounded-lg text-[15px] hover:bg-gray-200">CSV 내보내기</a>
</div>

<div id="ref-form-area"></div>
<div id="ref-import-result"></div>

<script>
document.body.addEventListener('companyChanged', function() {
  htmx.ajax('GET', '/reference/companies/', {target: '#ref-tab-content'});
});
</script>
```

- [ ] **Step 5: Add company view tests**

Add to `tests/test_p12_reference.py`:

```python
class TestCompanyCRUD:
    @pytest.mark.django_db
    def test_create_company(self, staff_client):
        resp = staff_client.post("/reference/companies/new/", {
            "name": "삼성전자",
            "name_en": "Samsung Electronics",
            "industry": "반도체",
            "size_category": "대기업",
            "listed": "KOSPI",
            "region": "서울",
            "revenue_range": "",
            "employee_count_range": "",
            "notes": "",
        })
        assert resp.status_code == 204
        assert CompanyProfile.objects.filter(name="삼성전자").exists()

    @pytest.mark.django_db
    def test_delete_company(self, staff_client):
        cp = CompanyProfile.objects.create(name="삼성전자", industry="반도체")
        resp = staff_client.post(f"/reference/companies/{cp.pk}/delete/")
        assert resp.status_code == 204
        assert not CompanyProfile.objects.filter(pk=cp.pk).exists()

    @pytest.mark.django_db
    def test_non_staff_cannot_create_company(self, normal_client):
        resp = normal_client.post("/reference/companies/new/", {"name": "Hack"})
        assert resp.status_code == 302  # staff redirect

    @pytest.mark.django_db
    def test_list_companies(self, normal_client):
        CompanyProfile.objects.create(name="삼성전자", industry="반도체")
        resp = normal_client.get("/reference/companies/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert "삼성전자" in resp.content.decode()
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_p12_reference.py -v -k "Company or company"`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add clients/views_reference.py clients/urls_reference.py \
       clients/services/company_autofill.py \
       clients/templates/clients/partials/ref_companies.html \
       tests/test_p12_reference.py
git commit -m "feat(p12): add company reference tab with CRUD, CSV, and Gemini autofill"
```

---

### Task 6: Cert Tab Views

**Files:**
- Modify: `clients/views_reference.py` (add cert views)
- Modify: `clients/urls_reference.py` (add cert URLs)
- Create: `clients/templates/clients/partials/ref_certs.html`
- Modify: `tests/test_p12_reference.py` (add cert tests)

- [ ] **Step 1: Add cert views to views_reference.py**

Add these views to `clients/views_reference.py`, replacing the cert placeholder:

```python
# --- Cert views ---


@login_required
def reference_certs(request):
    """Cert tab content."""
    qs = PreferredCert.objects.all()
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    level = request.GET.get("level", "").strip()

    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(full_name__icontains=q) | Q(aliases__icontains=q)
        )
    if category:
        qs = qs.filter(category=category)
    if level:
        qs = qs.filter(level=level)

    paginator = Paginator(qs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    ctx = {
        "page_obj": page_obj,
        "q": q,
        "category_filter": category,
        "level_filter": level,
        "category_choices": PreferredCert.Category.choices,
        "level_choices": PreferredCert.Level.choices,
        "active_tab": "certs",
        "is_staff": request.user.is_staff,
        "import_form": CSVImportForm(),
    }

    if request.headers.get("HX-Request"):
        return render(request, "clients/partials/ref_certs.html", ctx)
    return _render_reference_page(request, "certs", ctx)


@staff_member_required
def cert_create(request):
    """Create a cert."""
    if request.method == "POST":
        form = PreferredCertForm(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={"HX-Trigger": "certChanged"})
    else:
        form = PreferredCertForm()
    return render(request, "clients/partials/ref_form_modal.html", {
        "form": form, "title": "자격증 추가", "post_url": "/reference/certs/new/",
    })


@staff_member_required
def cert_update(request, pk):
    """Update a cert."""
    obj = get_object_or_404(PreferredCert, pk=pk)
    if request.method == "POST":
        form = PreferredCertForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={"HX-Trigger": "certChanged"})
    else:
        form = PreferredCertForm(instance=obj)
    return render(request, "clients/partials/ref_form_modal.html", {
        "form": form, "title": "자격증 수정", "post_url": f"/reference/certs/{pk}/edit/",
    })


@staff_member_required
def cert_delete(request, pk):
    """Delete a cert."""
    if request.method != "POST":
        return HttpResponse(status=405)
    obj = get_object_or_404(PreferredCert, pk=pk)
    obj.delete()
    return HttpResponse(status=204, headers={"HX-Trigger": "certChanged"})


@staff_member_required
def cert_import(request):
    """Import certs from CSV."""
    if request.method != "POST":
        return HttpResponse(status=405)
    form = CSVImportForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "clients/partials/ref_import_result.html", {"errors": ["파일을 선택해 주세요."]})
    csv_file = request.FILES["csv_file"]
    try:
        content = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return render(request, "clients/partials/ref_import_result.html", {"errors": ["UTF-8 인코딩이 아닙니다."]})
    result = import_csv(PreferredCert, io.StringIO(content))
    return render(request, "clients/partials/ref_import_result.html", result)


@login_required
def cert_export(request):
    """Export certs to CSV."""
    qs = PreferredCert.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(full_name__icontains=q) | Q(aliases__icontains=q))
    category = request.GET.get("category", "").strip()
    if category:
        qs = qs.filter(category=category)

    output = export_csv(PreferredCert, qs)
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="certs.csv"'
    return response
```

- [ ] **Step 2: Add cert URLs**

Add to `clients/urls_reference.py`:

```python
    # Certs
    path("certs/", views.reference_certs, name="certs"),
    path("certs/new/", views.cert_create, name="cert_create"),
    path("certs/<uuid:pk>/edit/", views.cert_update, name="cert_update"),
    path("certs/<uuid:pk>/delete/", views.cert_delete, name="cert_delete"),
    path("certs/import/", views.cert_import, name="cert_import"),
    path("certs/export/", views.cert_export, name="cert_export"),
```

- [ ] **Step 3: Create ref_certs.html partial**

Create `clients/templates/clients/partials/ref_certs.html`:

```html
<!-- Filters -->
<div class="flex flex-wrap gap-2 mb-4">
  <form hx-get="/reference/certs/" hx-target="#ref-tab-content" class="flex flex-wrap gap-2 w-full">
    <input type="text" name="q" value="{{ q }}" placeholder="자격증명 또는 별칭 검색"
           class="flex-1 min-w-[200px] border border-gray-300 rounded-lg px-3 py-2 text-[15px] focus:ring-2 focus:ring-primary focus:border-primary">
    <select name="category" class="border border-gray-300 rounded-lg px-3 py-2 text-[15px]">
      <option value="">전체 카테고리</option>
      {% for val, label in category_choices %}
      <option value="{{ val }}" {% if category_filter == val %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>
    <select name="level" class="border border-gray-300 rounded-lg px-3 py-2 text-[15px]">
      <option value="">전체 난이도</option>
      {% for val, label in level_choices %}
      <option value="{{ val }}" {% if level_filter == val %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>
    <button type="submit" class="bg-gray-100 text-gray-700 font-medium py-2 px-4 rounded-lg text-[15px] hover:bg-gray-200">검색</button>
  </form>
</div>

<!-- Table -->
{% if page_obj.object_list %}
<div class="overflow-x-auto">
  <table class="w-full text-[15px]">
    <thead>
      <tr class="border-b border-gray-200 text-left text-gray-500 text-[13px]">
        <th class="pb-2 font-medium">약칭</th>
        <th class="pb-2 font-medium">정식 명칭</th>
        <th class="pb-2 font-medium">카테고리</th>
        <th class="pb-2 font-medium">난이도</th>
        <th class="pb-2 font-medium">별칭</th>
        {% if is_staff %}<th class="pb-2 font-medium"></th>{% endif %}
      </tr>
    </thead>
    <tbody>
      {% for cert in page_obj %}
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-2.5 font-medium text-gray-900">{{ cert.name }}</td>
        <td class="py-2.5 text-gray-600">{{ cert.full_name|default:"-" }}</td>
        <td class="py-2.5"><span class="inline-block bg-purple-50 text-purple-700 text-[13px] px-2 py-0.5 rounded">{{ cert.get_category_display }}</span></td>
        <td class="py-2.5 text-gray-600">{{ cert.get_level_display|default:"-" }}</td>
        <td class="py-2.5 text-gray-500 text-[13px]">{{ cert.aliases|join:", "|default:"-" }}</td>
        {% if is_staff %}
        <td class="py-2.5 text-right space-x-1">
          <button hx-get="/reference/certs/{{ cert.pk }}/edit/" hx-target="#ref-form-area"
                  class="text-[13px] text-primary hover:underline">수정</button>
          <button hx-post="/reference/certs/{{ cert.pk }}/delete/" hx-confirm="정말 삭제하시겠습니까?"
                  hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'
                  class="text-[13px] text-red-500 hover:underline">삭제</button>
        </td>
        {% endif %}
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

{% if page_obj.has_other_pages %}
<div class="flex justify-center gap-2 pt-4">
  {% if page_obj.has_previous %}
  <button hx-get="/reference/certs/?{% if q %}q={{ q }}&{% endif %}{% if category_filter %}category={{ category_filter }}&{% endif %}{% if level_filter %}level={{ level_filter }}&{% endif %}page={{ page_obj.previous_page_number }}"
          hx-target="#ref-tab-content"
          class="px-3 py-2 rounded-lg text-[15px] text-gray-500 hover:bg-gray-100">이전</button>
  {% endif %}
  <span class="px-3 py-2 text-[15px] text-gray-500">{{ page_obj.number }} / {{ page_obj.paginator.num_pages }}</span>
  {% if page_obj.has_next %}
  <button hx-get="/reference/certs/?{% if q %}q={{ q }}&{% endif %}{% if category_filter %}category={{ category_filter }}&{% endif %}{% if level_filter %}level={{ level_filter }}&{% endif %}page={{ page_obj.next_page_number }}"
          hx-target="#ref-tab-content"
          class="px-3 py-2 rounded-lg text-[15px] text-gray-500 hover:bg-gray-100">다음</button>
  {% endif %}
</div>
{% endif %}
{% else %}
<p class="text-center text-gray-500 py-8">{% if q %}검색 결과가 없습니다.{% else %}등록된 자격증이 없습니다.{% endif %}</p>
{% endif %}

<!-- Actions -->
<div class="flex gap-2 pt-4">
  {% if is_staff %}
  <button hx-get="/reference/certs/new/" hx-target="#ref-form-area"
          class="bg-primary text-white font-semibold py-2 px-4 rounded-lg text-[15px] hover:bg-primary-dark transition">+ 추가</button>
  <form hx-post="/reference/certs/import/" hx-target="#ref-import-result" hx-encoding="multipart/form-data" class="flex gap-2">
    {% csrf_token %}
    {{ import_form.csv_file }}
    <button type="submit" class="bg-gray-100 text-gray-700 font-medium py-2 px-4 rounded-lg text-[15px] hover:bg-gray-200">CSV 가져오기</button>
  </form>
  {% endif %}
  <a href="/reference/certs/export/?{% if q %}q={{ q }}&{% endif %}{% if category_filter %}category={{ category_filter }}{% endif %}"
     hx-boost="false"
     class="bg-gray-100 text-gray-700 font-medium py-2 px-4 rounded-lg text-[15px] hover:bg-gray-200">CSV 내보내기</a>
</div>

<div id="ref-form-area"></div>
<div id="ref-import-result"></div>

<script>
document.body.addEventListener('certChanged', function() {
  htmx.ajax('GET', '/reference/certs/', {target: '#ref-tab-content'});
});
</script>
```

- [ ] **Step 4: Add cert view tests + aliases search test**

Add to `tests/test_p12_reference.py`:

```python
class TestCertCRUD:
    @pytest.mark.django_db
    def test_create_cert(self, staff_client):
        resp = staff_client.post("/reference/certs/new/", {
            "name": "KICPA",
            "full_name": "한국공인회계사",
            "category": "회계/재무",
            "level": "상",
            "aliases_text": "CPA;공인회계사",
            "notes": "",
        })
        assert resp.status_code == 204
        cert = PreferredCert.objects.get(name="KICPA")
        assert cert.aliases == ["CPA", "공인회계사"]

    @pytest.mark.django_db
    def test_delete_cert(self, staff_client):
        pc = PreferredCert.objects.create(name="KICPA", category="회계/재무")
        resp = staff_client.post(f"/reference/certs/{pc.pk}/delete/")
        assert resp.status_code == 204

    @pytest.mark.django_db
    def test_search_by_alias(self, normal_client):
        PreferredCert.objects.create(
            name="KICPA", full_name="한국공인회계사", category="회계/재무",
            aliases=["CPA", "공인회계사"],
        )
        resp = normal_client.get("/reference/certs/?q=CPA", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert "KICPA" in resp.content.decode()

    @pytest.mark.django_db
    def test_filter_by_category(self, normal_client):
        PreferredCert.objects.create(name="KICPA", category="회계/재무")
        PreferredCert.objects.create(name="CISA", category="IT")
        resp = normal_client.get("/reference/certs/?category=IT", HTTP_HX_REQUEST="true")
        content = resp.content.decode()
        assert "CISA" in content
        assert "KICPA" not in content
```

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/test_p12_reference.py -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add clients/views_reference.py clients/urls_reference.py \
       clients/templates/clients/partials/ref_certs.html \
       tests/test_p12_reference.py
git commit -m "feat(p12): add cert reference tab with CRUD, CSV, and alias search"
```

---

### Task 7: Sidebar + Navigation Updates

**Files:**
- Modify: `templates/common/nav_sidebar.html`
- Modify: `templates/common/nav_bottom.html`

- [ ] **Step 1: Add reference menu to sidebar**

In `templates/common/nav_sidebar.html`, add a reference link before the settings link:

```html
  <a href="/reference/"
     hx-get="/reference/" hx-target="#main-content" hx-push-url="true"
     data-nav="reference"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg>
    레퍼런스
  </a>
```

Update the `updateSidebar()` function to include the reference key:

```javascript
var active = (key === 'candidates' && (path === '/' || path.startsWith('/candidates'))) ||
             (key === 'projects' && path.startsWith('/projects')) ||
             (key === 'clients' && path.startsWith('/clients')) ||
             (key === 'reference' && path.startsWith('/reference')) ||
             (key === 'settings' && path.includes('/settings'));
```

- [ ] **Step 2: Add reference to mobile bottom nav**

In `templates/common/nav_bottom.html`, add a reference link in the nav. To keep 5 items fitting, replace or add before settings:

```html
    <a href="/reference/"
       hx-get="/reference/" hx-target="#main-content" hx-push-url="true"
       data-nav="reference"
       class="nav-tab flex flex-col items-center py-1 px-3 min-w-[64px] text-gray-500">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg>
      <span class="text-[12px] mt-0.5">레퍼런스</span>
    </a>
```

Update the `updateNav()` function similarly to add:
```javascript
(key === 'reference' && path.startsWith('/reference')) ||
```

- [ ] **Step 3: Add sidebar navigation test**

Add to `tests/test_p12_reference.py`:

```python
class TestSidebarNavigation:
    @pytest.mark.django_db
    def test_reference_page_full_render(self, normal_client):
        resp = normal_client.get("/reference/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "레퍼런스 관리" in content
        assert "<!DOCTYPE" in content  # full page

    @pytest.mark.django_db
    def test_reference_htmx_renders_partial(self, normal_client):
        resp = normal_client.get("/reference/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "<!DOCTYPE" not in content
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_p12_reference.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add templates/common/nav_sidebar.html templates/common/nav_bottom.html \
       tests/test_p12_reference.py
git commit -m "feat(p12): add reference management to sidebar and mobile nav"
```

---

### Task 8: Initial Data Loading Command + Seed Fixtures

**Files:**
- Create: `clients/management/__init__.py`
- Create: `clients/management/commands/__init__.py`
- Create: `clients/management/commands/load_reference_data.py`
- Create: `clients/fixtures/universities.csv`
- Create: `clients/fixtures/companies.csv`
- Create: `clients/fixtures/certs.csv`
- Modify: `tests/test_p12_reference.py`

- [ ] **Step 1: Create management command directory**

```bash
mkdir -p clients/management/commands
touch clients/management/__init__.py
touch clients/management/commands/__init__.py
```

- [ ] **Step 2: Create load_reference_data command**

Create `clients/management/commands/load_reference_data.py`:

```python
"""Load reference data from CSV fixtures.

Idempotent: re-running updates existing records and adds new ones.

Usage:
    uv run python manage.py load_reference_data
    uv run python manage.py load_reference_data --model universities
    uv run python manage.py load_reference_data --model companies
    uv run python manage.py load_reference_data --model certs
"""

from __future__ import annotations

import io
from pathlib import Path

from django.core.management.base import BaseCommand

from clients.models import CompanyProfile, PreferredCert, UniversityTier
from clients.services.csv_handler import import_csv

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"

MODEL_MAP = {
    "universities": (UniversityTier, "universities.csv"),
    "companies": (CompanyProfile, "companies.csv"),
    "certs": (PreferredCert, "certs.csv"),
}


class Command(BaseCommand):
    help = "Load reference data (universities, companies, certs) from CSV fixtures."

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            choices=list(MODEL_MAP.keys()),
            help="Load only the specified model. Default: all.",
        )

    def handle(self, *args, **options):
        targets = [options["model"]] if options["model"] else list(MODEL_MAP.keys())

        for key in targets:
            model, filename = MODEL_MAP[key]
            filepath = FIXTURES_DIR / filename
            if not filepath.exists():
                self.stderr.write(self.style.WARNING(f"  Skipped {key}: {filepath} not found"))
                continue

            content = filepath.read_text(encoding="utf-8-sig")
            result = import_csv(model, io.StringIO(content))

            if result["errors"]:
                self.stderr.write(self.style.ERROR(f"  {key}: errors"))
                for err in result["errors"]:
                    self.stderr.write(f"    {err}")
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  {key}: {result['created']} created, {result['updated']} updated"
                    )
                )
```

- [ ] **Step 3: Create sample fixture CSVs**

Create `clients/fixtures/universities.csv` with a representative sample (~20 rows):

```csv
name,name_en,country,tier,ranking,notes
서울대학교,Seoul National University,KR,SKY,1,
연세대학교,Yonsei University,KR,SKY,2,
고려대학교,Korea University,KR,SKY,3,
성균관대학교,Sungkyunkwan University,KR,SSG,1,
서강대학교,Sogang University,KR,SSG,2,
한양대학교,Hanyang University,KR,SSG,3,
중앙대학교,Chung-Ang University,KR,JKOS,1,
경희대학교,Kyung Hee University,KR,JKOS,2,
한국외국어대학교,Hankuk University of Foreign Studies,KR,JKOS,3,
시립대학교,University of Seoul,KR,JKOS,4,
건국대학교,Konkuk University,KR,KDH,1,
동국대학교,Dongguk University,KR,KDH,2,
홍익대학교,Hongik University,KR,KDH,3,
KAIST,KAIST,KR,SCIENCE_ELITE,1,
포항공과대학교,POSTECH,KR,SCIENCE_ELITE,2,
부산대학교,Pusan National University,KR,REGIONAL,1,
경북대학교,Kyungpook National University,KR,REGIONAL,2,
Harvard University,Harvard University,US,OVERSEAS_TOP,1,
MIT,MIT,US,OVERSEAS_TOP,2,
University of Oxford,University of Oxford,GB,OVERSEAS_TOP,3,
```

Create `clients/fixtures/companies.csv` with a sample (~20 rows):

```csv
name,name_en,industry,size_category,revenue_range,employee_count_range,listed,region,notes
삼성전자,Samsung Electronics,반도체/전자,대기업,300조+,100000+,KOSPI,경기 수원,
SK하이닉스,SK Hynix,반도체,대기업,50조~100조,30000~50000,KOSPI,경기 이천,
LG에너지솔루션,LG Energy Solution,2차전지,대기업,30조~50조,20000~30000,KOSPI,서울 영등포,
현대자동차,Hyundai Motor,자동차,대기업,100조+,70000~100000,KOSPI,서울 서초,
NAVER,NAVER,IT/플랫폼,대기업,5조~10조,5000~10000,KOSPI,경기 성남,
카카오,Kakao,IT/플랫폼,대기업,5조~10조,5000~10000,KOSPI,경기 성남,
포스코홀딩스,POSCO Holdings,철강,대기업,50조~100조,20000~30000,KOSPI,경북 포항,
KB금융지주,KB Financial Group,금융,대기업,50조~100조,20000~30000,KOSPI,서울 영등포,
신한금융지주,Shinhan Financial Group,금융,대기업,30조~50조,20000~30000,KOSPI,서울 중구,
셀트리온,Celltrion,바이오/제약,대기업,3조~5조,5000~10000,KOSPI,인천 연수,
쿠팡,Coupang,이커머스,대기업,30조~50조,50000~70000,해외상장,서울 송파,
크래프톤,Krafton,게임,대기업,1조~3조,1000~3000,KOSPI,서울 강남,
두산에너빌리티,Doosan Enerbility,에너지/플랜트,대기업,10조~30조,10000~20000,KOSPI,경남 창원,
한화에어로스페이스,Hanwha Aerospace,방산/항공,대기업,5조~10조,10000~20000,KOSPI,경남 창원,
에코프로비엠,Ecopro BM,2차전지소재,중견,3조~5조,1000~3000,KOSDAQ,경북 포항,
리노공업,LEENO Industrial,반도체장비,중견,5000억~1조,500~1000,KOSDAQ,부산,
토스뱅크,Toss Bank,금융/핀테크,스타트업,,,비상장,서울 강남,
야놀자,Yanolja,여행/IT,스타트업,,,비상장,서울 강남,
```

Create `clients/fixtures/certs.csv` with a sample (~20 rows):

```csv
name,full_name,category,level,aliases,notes
KICPA,한국공인회계사,회계/재무,상,CPA;공인회계사,
AICPA,미국공인회계사,회계/재무,상,US CPA,
CFA,국제재무분석사,회계/재무,상,Chartered Financial Analyst,
FRM,국제재무위험관리사,회계/재무,중,Financial Risk Manager,
변호사,변호사,법률,상,Lawyer;Attorney,
변리사,변리사,법률,상,Patent Attorney,
법무사,법무사,법률,중,,
기술사,기술사,기술/엔지니어링,상,Professional Engineer;PE,
기사,기사,기술/엔지니어링,중,Engineer,
정보처리기사,정보처리기사,IT,중,,
CISSP,국제공인정보시스템보안전문가,IT,상,Certified Information Systems Security Professional,
PMP,프로젝트관리전문가,IT,중,Project Management Professional,
AWS SAA,AWS 솔루션즈 아키텍트 어소시에이트,IT,중,AWS Solutions Architect,
의사,의사면허,의료/제약,상,Doctor;MD,
약사,약사면허,의료/제약,상,Pharmacist,
관세사,관세사,무역/물류,상,Customs Broker,
건축사,건축사,건설/부동산,상,Architect,
TOEIC,TOEIC,어학,하,토익,
TOEFL,TOEFL,어학,중,토플,
산업안전기사,산업안전기사,안전/품질,중,,
```

- [ ] **Step 4: Write command test**

Add to `tests/test_p12_reference.py`:

```python
from django.core.management import call_command


class TestLoadReferenceData:
    @pytest.mark.django_db
    def test_load_all(self):
        call_command("load_reference_data")
        assert UniversityTier.objects.count() > 0
        assert CompanyProfile.objects.count() > 0
        assert PreferredCert.objects.count() > 0

    @pytest.mark.django_db
    def test_idempotent(self):
        call_command("load_reference_data")
        count1 = UniversityTier.objects.count()
        call_command("load_reference_data")
        count2 = UniversityTier.objects.count()
        assert count1 == count2

    @pytest.mark.django_db
    def test_load_single_model(self):
        call_command("load_reference_data", model="universities")
        assert UniversityTier.objects.count() > 0
        assert CompanyProfile.objects.count() == 0
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_p12_reference.py::TestLoadReferenceData -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add clients/management/ clients/fixtures/ tests/test_p12_reference.py
git commit -m "feat(p12): add load_reference_data command with seed CSV fixtures"
```

---

### Task 9: Final Integration Test + Full Test Run

**Files:**
- Modify: `tests/test_p12_reference.py` (add HTMX tab switching test)

- [ ] **Step 1: Add integration tests**

Add to `tests/test_p12_reference.py`:

```python
class TestTabSwitching:
    @pytest.mark.django_db
    def test_tab_universities(self, normal_client):
        resp = normal_client.get("/reference/universities/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_tab_companies(self, normal_client):
        resp = normal_client.get("/reference/companies/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_tab_certs(self, normal_client):
        resp = normal_client.get("/reference/certs/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_index_redirects_to_universities(self, normal_client):
        resp = normal_client.get("/reference/")
        assert resp.status_code == 200
        assert "대학 랭킹" in resp.content.decode() or "대학명" in resp.content.decode()
```

- [ ] **Step 2: Run full P12 test suite**

Run: `uv run pytest tests/test_p12_reference.py -v`
Expected: All tests pass.

- [ ] **Step 3: Run entire project test suite**

Run: `uv run pytest -v`
Expected: All tests pass (including existing P01 tests with updated model expectations).

- [ ] **Step 4: Run lint**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: No lint or formatting issues.

- [ ] **Step 5: Final commit**

```bash
git add tests/test_p12_reference.py
git commit -m "feat(p12): add integration tests for tab switching and full coverage"
```
