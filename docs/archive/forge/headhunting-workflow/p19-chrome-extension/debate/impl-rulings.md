# P19 Chrome Extension — Implementation Rulings

**Status:** COMPLETE
**Rounds:** 1
**Issues:** 16 (3 CRITICAL, 13 MAJOR)
**Accepted:** 14 | **Partial:** 2 | **Rebutted:** 0

---

## Accepted Items

### I-R1-01 [CRITICAL] ExtractionLog needs actor and details fields
Add migration: `actor = ForeignKey(User, SET_NULL, null=True, blank=True)`, `details = JSONField(default=dict, blank=True)`. Add `Action.EXTENSION_SAVE` to choices. Include in Step 0 migration.

### I-R1-02 [CRITICAL] Custom auth decorator for JSON 401
Replace `@login_required` with `extension_login_required` that returns `JsonResponse({"status": "error", "errors": ["Authentication required"]}, status=401)`.

### I-R1-03 [CRITICAL] Education year parsing
Add `parse_int_or_none(val)` helper: returns `int(val)` if numeric, `None` otherwise. Apply to `start_year`, `end_year` before `Education.objects.create()`.

### I-R1-04 [MAJOR] CSRF handling
Use `@csrf_exempt` on all extension views. Auth verified by custom decorator checking `request.user.is_authenticated` via session cookie. No CSRF_TRUSTED_ORIGINS change needed.

### I-R1-05 [MAJOR] SameSite cookie configuration
Production requires: `SESSION_COOKIE_SAMESITE = "None"`, `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SAMESITE = "None"`, `CSRF_COOKIE_SECURE = True`. Controlled via environment variable.

### I-R1-06 [MAJOR] consent_status default
Model field: `consent_status = models.CharField(max_length=20, default="not_requested", blank=True)`.

### I-R1-07 [MAJOR] Preserve new_careers_confirmed in validator
Add to `validate_profile_data()`: validate and preserve `new_careers_confirmed` with same structure limits as `careers`.

### I-R1-08 [MAJOR] Safe string conversion
Add `safe_str(val)`: returns `""` if `val is None` else `str(val)`. Use throughout validator instead of raw `str()`.

### I-R1-09 [MAJOR] Phone in secondary identifier check
Change check to: `if not any([company, position, email, ext_url, normalized_phone_valid])`.

### I-R1-10 [MAJOR] JSON and pagination error handling
Wrap `json.loads()` in try/except returning 400. Validate page: `page = max(1, int(request.GET.get("page", 1)))` with ValueError catch.

### I-R1-11 [MAJOR] external_profile_url in update allowed fields
Add to `allowed_fields` in `_handle_update`. Apply `normalize_url()`, handle `IntegrityError` from unique constraint.

### I-R1-14 [MAJOR] Client flow change for diff
check-duplicate returns exists/match info only. save-profile returns diff when duplicate found (409). Client shows diff on "update" click after save attempt.

### I-R1-15 [MAJOR] Education diff and update
`_build_diff()`: add education diff using `(institution.lower().strip(), degree.lower().strip())` key.
`_handle_update()`: add `new_educations_confirmed` handling.

### I-R1-16 [MAJOR] Nested array element validation
In serializer, validate each career/education item is `dict`. Skip non-dict items. Sanitize text fields inside serializer, not during DB writes.

---

## Partially Accepted Items

### I-R1-12 [MAJOR] Concurrent email/phone protection
**Accepted:** Add `select_for_update()` on identity check queryset within save transaction.
**Rejected:** Per-org unique constraints on email/phone (unsafe for blank values and existing data).

### I-R1-13 [MAJOR] Rate limit reliability
**Accepted:** Rate limit unreliable with LocMemCache.
**Resolution:** Replace `_check_rate_limit()` call with DB-backed counter: `ExtractionLog.objects.filter(action=Action.EXTENSION_SAVE, actor=user, created_at__date=today).count()` inside the save transaction. No cache backend change needed.

---

## Additional Minor Fixes (all accepted)

- URL normalization: all normalization on server side. Extension sends raw URL.
- Career company key: add `normalize_company()` helper (lowercase, strip, remove legal suffixes).
- Name+company matching: use `name__iexact` + `current_company__iexact`.
- LinkedIn SPA: add URL change watcher via `navigation` event / `popstate` / MutationObserver on URL.
- Test list: add failure path tests (invalid JSON, malformed arrays, long identifiers, education years, 401 auth).
- API status codes: add 405/413 to agreed contract.
- Service worker headers: merge headers properly `{ ...defaults.headers, ...(options.headers || {}) }`.
- Migration: add `default=""` for `external_profile_url` CharField.
