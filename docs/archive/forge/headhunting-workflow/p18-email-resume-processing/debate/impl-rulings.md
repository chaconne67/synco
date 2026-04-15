# Implementation Rulings — p18-email-resume-processing

Status: COMPLETE
Last updated: 2026-04-10T16:00:00Z
Rounds: 1

## Resolved Items

### Issue I-R1-01: Identity matching not org-scoped [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** `identify_candidate()` queries globally without org filter, causing cross-tenant leakage.
- **Action:** Create org-aware wrapper `identify_candidate_for_org(extracted, organization)` that filters by `owned_by=organization`. Use this in the linker instead of the global function.

### Issue I-R1-02: New candidates created without owned_by [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** `_create_candidate()` doesn't set `owned_by`, making candidates invisible in org-scoped search.
- **Action:** After `save_pipeline_result()` creates a candidate, set `candidate.owned_by = upload.organization` and save. Add this to linker.py after candidate creation.

### Issue I-R1-03: Existing-candidate link bypasses resume version persistence [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Calling private `_update_candidate()` directly skips Resume, ExtractionLog, ValidationDiagnosis, DiscrepancyReport creation.
- **Action:** Use `save_pipeline_result()` for both new and existing candidates. Pass `comparison_context` for existing candidate matching. Remove direct `_update_candidate()` call from linker.

### Issue I-R1-04: Contact alone doesn't place candidate in search tab [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** `project_tab_search()` builds results from `match_candidates()` only.
- **Action:** Add "이력서 업로드" section to search tab that shows ResumeUpload records (extracted/linked/duplicate) for the project. This is separate from the JD matching results and provides a unified view of uploaded candidates.

### Issue I-R1-05: project=null email uploads have no management UI [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Email resumes without `[REF-{uuid}]` match become orphaned.
- **Action:** Add org-scoped endpoint `GET /resumes/unassigned/` showing ResumeUpload records with project=null for the user's organization. Add `POST /resumes/<pk>/assign/<project_pk>/` for project assignment. Add URL + view + template.

### Issue I-R1-06: Duplicate status transition ordering underspecified [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** The two-step `extracting→extracted→duplicate` must be explicit.
- **Action:** In `process_pending_upload()`: (1) transition to EXTRACTED after successful extraction, (2) then check for duplicates, (3) if match found transition from EXTRACTED to DUPLICATE. Document this sequence in code comments.

### Issue I-R1-07: Email dedup pre-insert check is race-prone [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** `.exists()` before insert is TOCTOU vulnerable.
- **Action:** Use `try: ResumeUpload.objects.create(...) except IntegrityError: continue` pattern. The DB unique constraint is the true dedup mechanism.

### Issue I-R1-08: Crypto uses SHA-256 but spec says HKDF [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Plan's SHA-256+base64 contradicts design spec's HKDF.
- **Action:** Use `HKDF(algorithm=hashes.SHA256(), length=32, salt=b"synco-gmail-credentials", info=b"fernet-key")` from `cryptography.hazmat.primitives.kdf.hkdf`. Stable salt and info parameters.

### Issue I-R1-09: Gmail error-handling not detailed in plan [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Design spec's error table not reflected in implementation steps.
- **Action:** Add explicit error handling in `GmailClient` methods:
  - 401: try refresh → on fail set `is_active=False`, create notification
  - 404 history: fallback to `messages.list(q='after:{epoch}')`
  - 429: exponential backoff, max 5 retries
  - 5xx: skip config, log, continue to next
  - Oversized attachment: skip + log
  - Network timeout: httpx 30s timeout, skip + log

### Issue I-R1-10: Test coverage misses project-specific failure modes [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Generic test list misses critical failure modes.
- **Action:** Add tests:
  - Cross-org identity collision: org A candidate with same email, org B upload → no match
  - owned_by assignment: new candidate after upload has owned_by set
  - Unassigned inbox: project=null uploads visible in org-scoped view
  - Search tab: linked candidate appears in upload section even without JD match
  - Duplicate transition: extracting→extracted→duplicate (not extracting→duplicate)
  - Concurrent dedup: IntegrityError caught and skipped gracefully

## Disputed Items

(None — all items resolved in Round 1)
