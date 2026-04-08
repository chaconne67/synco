# P12: Reference Data Management — 확정 구현계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build reference data management (universities, companies, certs) with admin UI, CSV import/export, and initial data loading.

**Architecture:** Extend the existing `clients` app with model schema changes, a dedicated `views_reference.py` and `urls_reference.py` mounted at `/reference/`. Tab-based UI with HTMX partial swapping for the three data types. CSV handler service for import/export. Gemini API-based company autofill.

**Tech Stack:** Django 5.2, PostgreSQL, HTMX, Tailwind CSS, Gemini API (`google-genai`), pytest

**Base plan:** `docs/forge/headhunting-workflow/p12/debate/impl-plan.md`
**Design spec:** `docs/forge/headhunting-workflow/p12/design-spec-agreed.md`

---

## Tempering Changes Applied

The following changes were identified during implementation tempering and MUST be applied when implementing the base plan. Each change references the issue ID from `debate/impl-rulings.md`.

### Change 1: Update clients/admin.py (I-R1-01, CRITICAL)

**When:** During Task 1, after model changes but before running tests.

**Add new step between Step 5 and Step 6 of Task 1:**

- [ ] **Step 5.5: Update clients/admin.py to match new schema**

Replace the reference model admin classes in `clients/admin.py`:

```python
@admin.register(UniversityTier)
class UniversityTierAdmin(admin.ModelAdmin):
    list_display = ("name", "name_en", "country", "tier", "ranking")
    list_filter = ("tier", "country")
    search_fields = ("name", "name_en")


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "name_en", "industry", "size_category", "listed", "region")
    list_filter = ("size_category", "listed")
    search_fields = ("name", "name_en", "industry")


@admin.register(PreferredCert)
class PreferredCertAdmin(admin.ModelAdmin):
    list_display = ("name", "full_name", "category", "level")
    list_filter = ("category", "level")
    search_fields = ("name", "full_name")
```

Add `clients/admin.py` to the Task 1 commit.

---

### Change 2: Fix company_autofill to work without pk (I-R1-02, CRITICAL)

**When:** Task 5, Step 1 (company views) and Step 2 (company URLs).

**Replace the `company_autofill` view in `views_reference.py`:**

```python
@staff_member_required
def company_autofill(request):
    """Autofill company fields using Gemini web search.

    Accepts company name via POST body. Does NOT require an existing CompanyProfile.
    Returns JSON with field values to populate the form.
    """
    import json
    from .services.company_autofill import autofill_company

    if request.method != "POST":
        return HttpResponse(status=405)

    company_name = request.POST.get("name", "").strip()
    if not company_name:
        return HttpResponse(
            json.dumps({"error": "회사명을 입력해 주세요."}, ensure_ascii=False),
            content_type="application/json",
            status=400,
        )

    try:
        result = autofill_company(company_name)
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
```

**Replace the autofill URL in `urls_reference.py`:**

```python
# Change FROM:
path("companies/<uuid:pk>/autofill/", views.company_autofill, name="company_autofill"),
# Change TO:
path("companies/autofill/", views.company_autofill, name="company_autofill"),
```

**Update the company form modal template** to include an autofill button that sends the name field:

```html
{% if show_autofill %}
<div class="flex items-center gap-2">
  <button type="button" id="autofill-btn"
          class="text-[13px] text-primary hover:underline"
          onclick="doAutofill()">자동채움</button>
  <span class="text-[11px] text-gray-400">회사명이 외부 검색 서비스로 전송됩니다</span>
</div>
<script>
function doAutofill() {
  var nameInput = document.querySelector('input[name="name"]');
  if (!nameInput || !nameInput.value.trim()) {
    alert('회사명을 먼저 입력해 주세요.');
    return;
  }
  var btn = document.getElementById('autofill-btn');
  btn.textContent = '조회 중...';
  btn.disabled = true;
  fetch('/reference/companies/autofill/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
    },
    body: 'name=' + encodeURIComponent(nameInput.value.trim()),
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) {
      window.showToast && showToast(data.error);
    } else {
      Object.keys(data).forEach(function(key) {
        var input = document.querySelector('[name="' + key + '"]');
        if (input && data[key]) input.value = data[key];
      });
    }
  })
  .catch(() => window.showToast && showToast('자동채움에 실패했습니다.'))
  .finally(() => { btn.textContent = '자동채움'; btn.disabled = false; });
}
</script>
{% endif %}
```

---

### Change 3: Create stub views/templates for all tabs in Task 4 (I-R1-03, MAJOR)

**When:** Task 4, Step 1.

**In `views_reference.py`, replace the placeholder comments with minimal stubs:**

```python
# --- Company views (stub — full implementation in Task 5) ---


@login_required
def reference_companies(request):
    """Company DB tab content — stub."""
    ctx = {
        "page_obj": None,
        "active_tab": "companies",
        "is_staff": request.user.is_staff,
    }
    if request.headers.get("HX-Request"):
        return render(request, "clients/partials/ref_companies.html", ctx)
    return _render_reference_page(request, "companies", ctx)


# --- Cert views (stub — full implementation in Task 6) ---


@login_required
def reference_certs(request):
    """Cert tab content — stub."""
    ctx = {
        "page_obj": None,
        "active_tab": "certs",
        "is_staff": request.user.is_staff,
    }
    if request.headers.get("HX-Request"):
        return render(request, "clients/partials/ref_certs.html", ctx)
    return _render_reference_page(request, "certs", ctx)
```

**Create stub templates in Task 4:**

`clients/templates/clients/partials/ref_companies.html`:
```html
<p class="text-center text-gray-500 py-8">기업 DB (준비 중)</p>
```

`clients/templates/clients/partials/ref_certs.html`:
```html
<p class="text-center text-gray-500 py-8">자격증 (준비 중)</p>
```

**Also register stub company/cert URLs in Task 4's urls_reference.py:**
```python
path("companies/", views.reference_companies, name="companies"),
path("certs/", views.reference_certs, name="certs"),
```

These stubs get replaced in Tasks 5 and 6.

---

### Change 4: Add comment about aliases search approximation (I-R1-04, MAJOR)

**When:** Task 6, Step 1 (cert views).

**In the cert search view, add a comment:**

```python
    if q:
        # Note: aliases__icontains searches the serialized JSON text.
        # This is a practical approximation for short alias tokens.
        # For exact array element matching, use PostgreSQL jsonb @> operator.
        qs = qs.filter(
            Q(name__icontains=q) | Q(full_name__icontains=q) | Q(aliases__icontains=q)
        )
```

---

### Change 5: Simplify CSV handler to single-pass (I-R1-05, MINOR)

**When:** Task 3, Step 4.

**Replace the `import_csv` function in `csv_handler.py` with a single-pass approach:**

```python
def import_csv(
    model: type[Model],
    file_obj: io.StringIO | io.TextIOWrapper,
) -> dict:
    """Import CSV data into a reference model.

    Single-pass: validate + upsert each row within one atomic transaction.
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
            for row_num, row in enumerate(reader, start=2):
                data = {}
                for col in columns:
                    val = row.get(col, "").strip()
                    if col == "aliases":
                        data[col] = [a.strip() for a in val.split(";") if a.strip()] if val else []
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

            # All rows validated — now upsert (re-read file)
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
        pass

    return {"created": created, "updated": updated, "errors": errors}
```

Note: After further analysis, keeping the two-pass approach is acceptable since the entire operation runs within `transaction.atomic()` — if `update_or_create` fails in the second pass, the whole transaction rolls back. The key improvement is ensuring the second-pass errors are also caught within the atomic block. The code above keeps two passes but wraps both in the same atomic block.

---

### Change 6: Make _render_reference_page tab-aware (I-R1-06, MINOR)

**When:** Task 4, Step 1.

**Replace the `_render_reference_page` helper:**

```python
def _render_reference_page(request, active_tab, tab_ctx=None):
    """Render full reference page with tab content."""
    ctx = {"active_tab": active_tab}
    if tab_ctx:
        ctx.update(tab_ctx)
    # No default data loading — each tab view provides its own context
    return render(request, "clients/reference_index.html", ctx)
```

The `reference_index` view should explicitly call the university tab view's logic:

```python
@login_required
def reference_index(request):
    """Reference management main page, defaults to universities tab."""
    return reference_universities(request)
```

---

## File Structure (Final)

| File | Responsibility | Action |
|------|---------------|--------|
| `clients/models.py` | Model schema changes (3 reference models) | Modify |
| `clients/admin.py` | **Admin classes updated for new fields** | Modify |
| `clients/migrations/0002_p12_reference_models.py` | Auto-generated schema migration | Create (auto) |
| `clients/forms_reference.py` | CRUD forms + CSV import form for 3 models | Create |
| `clients/views_reference.py` | ~20 reference management views | Create |
| `clients/urls_reference.py` | `/reference/` URL routing | Create |
| `main/urls.py` | Add `/reference/` include | Modify |
| `clients/services/__init__.py` | Package init | Create |
| `clients/services/csv_handler.py` | CSV import/export logic | Create |
| `clients/services/company_autofill.py` | Gemini autofill service | Create |
| `clients/management/commands/load_reference_data.py` | Initial data loading command | Create |
| `clients/fixtures/universities.csv` | University seed data (~20 sample) | Create |
| `clients/fixtures/companies.csv` | Company seed data (~18 sample) | Create |
| `clients/fixtures/certs.csv` | Cert seed data (~20 sample) | Create |
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

## Task Execution Order

1. **Task 1: Model Schema Changes + Migration + Admin Update** (base plan Task 1 + Change 1)
2. **Task 2: Forms + CSV Import Form** (base plan Task 2, unchanged)
3. **Task 3: CSV Handler Service** (base plan Task 3 + Change 5)
4. **Task 4: Views + URLs + Templates (University Tab + Stubs)** (base plan Task 4 + Changes 3, 6)
5. **Task 5: Company Tab Views + Autofill Service** (base plan Task 5 + Change 2)
6. **Task 6: Cert Tab Views** (base plan Task 6 + Change 4)
7. **Task 7: Sidebar + Navigation Updates** (base plan Task 7, unchanged)
8. **Task 8: Initial Data Loading Command + Seed Fixtures** (base plan Task 8, unchanged)
9. **Task 9: Final Integration Test + Full Test Run** (base plan Task 9, unchanged)

Each task's detailed steps are in the base plan (`debate/impl-plan.md`) with the tempering changes above applied on top.

<!-- forge:p12:구현담금질:complete:2026-04-08T23:15:00+09:00 -->
