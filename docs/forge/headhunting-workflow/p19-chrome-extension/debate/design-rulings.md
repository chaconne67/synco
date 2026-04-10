# P19 Chrome Extension — Design Rulings

**Status:** COMPLETE
**Rounds:** 1
**Issues:** 30 (7 CRITICAL, 21 MAJOR, 2 MINOR)
**Accepted:** 24 | **Partial:** 6 | **Rebutted:** 0

---

## Accepted Items

### D-R1-01 [CRITICAL] Source field max_length overflow
Use `CHROME_EXT = "chrome_ext"` (10 chars) to fit within current `max_length=15`. No migration needed.

### D-R1-02 [CRITICAL] /api/ URL namespace doesn't exist
Place extension endpoints under `/candidates/extension/` using existing `candidates/urls.py`. Alternatively, define new `/api/` namespace in `main/urls.py` if future API expansion is planned.

### D-R1-03 [CRITICAL] API token auth system doesn't exist
Remove API token auth from spec. Use session-based auth only. Extension uses `credentials: "include"` with host_permissions.

### D-R1-04 [CRITICAL] Cross-origin session auth underspecified
Add to spec: Extension acquires CSRF token via `GET /candidates/extension/auth-status/` which returns CSRF token in response. POST views check CSRF via custom header (`X-CSRFToken`). Cookies require `SameSite=None; Secure` in production. `host_permissions` in manifest allows cookie sending.

### D-R1-05 [CRITICAL] Multi-tenancy organization scoping missing
All API views derive organization from `request.user.organization` (or membership). All queries filter by `owned_by`. All creates set `owned_by`. Client-provided org IDs ignored.

### D-R1-06 [CRITICAL] Duplicate merge contradicts identity policy
Auto-merge ONLY on: email match, phone match, or exact external_profile_url match (within same org). Name+company match returns "possible match" requiring user confirmation in overlay UI.

### D-R1-07 [CRITICAL] No persistence model for external profile URLs
Add `external_profile_url` field to Candidate model (CharField, max_length=500, blank=True, indexed). Add unique constraint: `(owned_by, external_profile_url)` where url is non-empty. Normalize URLs before storage (strip query params, trailing slashes).

### D-R1-08 [MAJOR] api app conflicts with app structure
All server code under `candidates/`: `views_extension.py`, `serializers_extension.py`, URL patterns in `candidates/urls.py`.

### D-R1-09 [MAJOR] New duplicate service vs existing identity service
Extend `candidate_identity.py` with `identify_candidate_from_extension(data, organization)`. Reuse existing email/phone matching, add external_profile_url matching. Single canonical identity decision path.

### D-R1-10 [MAJOR] Search lacks access control/pagination
All endpoints require `@login_required`. Org filtering. Search: pagination (20/page), min query length (2 chars), reuse `candidates/services/search.py`.

### D-R1-12 [MAJOR] Extension permission model missing
`manifest.json` specifies: `host_permissions: ["*://*.linkedin.com/*", "*://*.jobkorea.co.kr/*", "*://*.saramin.co.kr/*", "https://synco.example.com/*"]`. `permissions: ["storage", "activeTab"]`.

### D-R1-13 [MAJOR] No TOS compliance guardrails
Add: explicit user click per save (no auto-save), no background crawling/auto-navigation, per-user throttle (max 100 saves/day), visible confirmation overlay, audit log per save.

### D-R1-15 [MAJOR] Update pipeline can overwrite curated data
Updates are additive by default. New career/education records added. Existing fields NOT overwritten. Overlay shows diff of detected changes. User confirms individual field updates.

### D-R1-16 [MAJOR] Career/Education merge semantics undefined
Career identity key: `(company_normalized, start_date)`. Education identity key: `(institution_normalized, degree)`. Matching records: show diff, user confirms update. Non-matching: add as new. Idempotent: same URL + same data = no change.

### D-R1-17 [MAJOR] Duplicate-check leaks candidate existence
Org-scoped (only matches within user's org). Rate-limited. Returns minimal data: `{exists: bool, candidate_summary: {name, company, position} | null}`.

### D-R1-18 [MAJOR] No error handling contract
Standard JSON response: `{status: "success"|"error"|"duplicate_found", data: {...}, errors: [...]}`. HTTP codes: 200 (OK), 201 (created), 400 (validation), 401 (unauth), 403 (forbidden), 409 (duplicate, includes match details), 500 (server).

### D-R1-19 [MAJOR] Data validation too vague
Required: `name`. Max lengths: name=100, company=255, position=255, address=500, external_profile_url=500. HTML stripped from all text fields. Payload limit: 100KB. Array limits: careers=50, educations=20, skills=100. URL validation for external_profile_url.

### D-R1-21 [MAJOR] No page type distinction
Supported: LinkedIn full profile (`/in/*` URLs only). JobKorea/Saramin: search result cards (minimal) + detail pages (full). Min required for save: name + at least one of (company, position, email, external_profile_url). Content script only activates on supported URL patterns.

### D-R1-22 [MAJOR] No audit trail
Extension save creates audit record: `{user, organization, source_site, source_url, timestamp, operation_type (create|update|skip), candidate_id, fields_changed}`. Extend ExtractionLog with `Action.EXTENSION_SAVE = "extension_save"`.

### D-R1-23 [MAJOR] No idempotency/concurrency handling
`transaction.atomic()` for all save operations. Unique constraint on `(owned_by, external_profile_url)` prevents duplicates. `get_or_create` pattern for URL-based saves. Double-click protection via client-side debounce + server-side idempotency.

### D-R1-25 [MINOR] Django REST views ambiguous
Clarified: plain Django views returning `JsonResponse`. No DRF dependency.

### D-R1-28 [MAJOR] Server URL not specified
Extension options page with server URL input. Default: production URL (build-time constant). URL validated on save. Stored in `chrome.storage.sync`.

### D-R1-30 [MINOR] Tests acceptance-level only
Add: Django unit tests (auth, tenant filtering, duplicate decisions, validation errors, idempotency, merge). Parser fixture tests per site (saved HTML snapshots). Permission/cross-org tests.

---

## Partially Accepted Items

### D-R1-11 [MAJOR] Server-updated selectors
**Accepted:** Acknowledge need for selector management.
**Deferred to Phase 2:** Remote selector config endpoint. V1 bundles selectors in extension code, updated via extension version updates (matches industry practice: Loxo, Gem).
**Residual risk:** Low. Extension update cycle handles selector changes adequately for initial deployment.

### D-R1-14 [MAJOR] Privacy/consent handling
**Accepted:** Add `consent_status` field (default: `"not_requested"`) and source metadata (collector_user, source_url, collected_at) at candidate creation.
**Deferred:** Full GDPR/개인정보보호법 consent workflow (separate feature, handled in main app).

### D-R1-20 [MAJOR] LinkedIn DOM selectors brittle
**Accepted:** Add graceful degradation (partial results with quality indicator), user review before save, null handling for missing fields.
**Acknowledged:** DOM fragility is inherent to scraping; ongoing maintenance required. Selectors in spec are reference examples only.

### D-R1-24 [MAJOR] Popup counters
**Accepted:** "총 DB" requires server endpoint (org-scoped candidate count).
**Local:** "최근 저장" and "오늘 N명" use `chrome.storage.local` (no server round-trip).

### D-R1-26 [MAJOR → MINOR] Chrome Web Store deliverable
**Accepted:** Initial distribution: unlisted/private. Privacy policy required.
**Reclassified:** Deployment/distribution concern, not architecture. Severity downgraded.

### D-R1-29 [MAJOR] Observability for parser failures
**Accepted:** Parser returns `parse_quality` indicator (complete/partial/failed). Server logs failed saves with details. Extension shows user-friendly error.
**Deferred:** Full observability dashboard/alerting system.

---

## Merged Items

### D-R1-27 → D-R1-11
Remote selector config risk eliminated by deferring remote selectors to Phase 2. V1 has no remote code execution risk.
