# Design Rulings — p18-email-resume-processing

Status: COMPLETE
Last updated: 2026-04-10T15:00:00Z
Rounds: 1

## Resolved Items

### Issue D-R1-01: ResumeUpload missing organization scope [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Independent uploads (project=null) need explicit org FK for tenant isolation.
- **Action:** Add `organization = FK → Organization` to ResumeUpload, derive from project or user at creation.

### Issue D-R1-02: Models don't specify BaseModel inheritance [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Both new models must inherit BaseModel for UUID PK + timestamps.
- **Action:** Declare `class ResumeUpload(BaseModel)` and `class EmailMonitorConfig(BaseModel)`.

### Issue D-R1-03: Synchronous extraction in POST with polling contradiction [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** POST must not run extraction synchronously. No Celery means deferred processing.
- **Action:** POST creates ResumeUpload(status=pending), returns immediately. Processing via: (a) a "process pending" view that the upload JS triggers after POST returns, or (b) management command. Polling monitors status.

### Issue D-R1-04: File format support contradicts existing pipeline [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Spec incorrectly references pdfplumber and claims DOCX is new.
- **Action:** Reference existing `data_extraction/services/text.py` extract_text() which handles PDF (PyMuPDF), DOCX (python-docx), DOC (antiword/LibreOffice). Only HWP is new.

### Issue D-R1-05: HWP dependencies not in pyproject.toml [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** HWP support requires new dependency not yet installed.
- **Action:** Defer HWP to a follow-up. Phase 1 supports PDF/DOCX/DOC only. If HWP is added later, `uv add olefile` and register in pyproject.toml first.

### Issue D-R1-06: Gmail credential encryption unspecified [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** OAuth tokens must not be stored as plaintext JSON.
- **Action:** Use `cryptography.fernet.Fernet` with SECRET_KEY-derived key. Encrypt on save, decrypt on read. Add `cryptography` to pyproject.toml if not present.

### Issue D-R1-07: OAuth refresh token handling incomplete [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Without offline access and refresh logic, Gmail monitoring fails after token expiry.
- **Action:** Specify `access_type='offline'`, `prompt='consent'`, token refresh in gmail_client.py, reconnect flow when refresh fails.

### Issue D-R1-08: Gmail dedup insufficient for multi-attachment [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Single email can have multiple resume attachments.
- **Action:** Add `email_attachment_id` CharField. Unique constraint on `(organization, email_message_id, email_attachment_id)`.

### Issue D-R1-09: Candidate linking not atomic [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Concurrent uploads can create duplicate candidates.
- **Action:** Use `transaction.atomic()` + `select_for_update()` in linker.py, following existing `save_pipeline_result` pattern.

### Issue D-R1-10: Identity matching lacks normalization details [MAJOR]
- **Resolution:** REBUTTED
- **Summary:** Existing `candidates/services/candidate_identity.py` provides `build_candidate_comparison_context()` with full normalization. Spec reuses existing pipeline which includes this. Will add explicit reference for clarity.

### Issue D-R1-11: Project matching by keyword unsafe for multi-tenant [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Keyword matching must be scoped and confirmed.
- **Action:** Scope matching to user's organization. Use project UUID in `[REF-{uuid}]`. Keyword matching requires manual confirmation, never auto-link.

### Issue D-R1-12: File validation missing [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** No size/MIME/extension validation defined.
- **Action:** Max file size 20MB. Allowed types: PDF, DOCX, DOC. Validate MIME + extension consistency. Parser timeout 60s.

### Issue D-R1-13: Gmail attachment download lacks size/error handling [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** API errors and oversized files can break cron.
- **Action:** Per-attachment 20MB cap, retry with backoff, skip with logging, never abort entire run.

### Issue D-R1-14: history_id expiration handling underspecified [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Expired history IDs cause permanent polling failure.
- **Action:** Fallback to `messages.list(q='after:{epoch}')` when history.list returns 404/error. Update history_id from latest successful response.

### Issue D-R1-15: EmailMonitorConfig not scoped to organization [MAJOR]
- **Resolution:** REBUTTED
- **Summary:** User belongs to exactly one Organization via Membership OneToOne. Organization derivable via `user.membership.organization`. Redundant org FK would violate DRY.

### Issue D-R1-16: extraction_result JSONField for relational data [MAJOR]
- **Resolution:** REBUTTED
- **Summary:** `extraction_result` stores opaque pipeline output snapshot (same as existing `Candidate.raw_extracted_json`). Relational decisions (candidate, project) use FK fields. No join model needed.

### Issue D-R1-17: No spec for adding candidate to project searching list [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Candidate creation alone doesn't place them in project workflow.
- **Action:** After linking, create Contact record with `result=Result.INTERESTED` (or new value) to place candidate in project's searching tab.

### Issue D-R1-18: URL authorization and tenant scoping absent [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Views need explicit authorization checks.
- **Action:** Every view filters by organization via project.organization, checks user membership, and verifies resume_pk belongs to the project.

### Issue D-R1-19: State transitions not constrained [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Unconstrained transitions risk invalid state changes.
- **Action:** Define allowed transitions: pending→extracting, extracting→extracted/failed, extracted→linked/discarded/duplicate, failed→pending (retry). Enforce in service layer under transaction.atomic().

### Issue D-R1-20: Polling endpoint underspecified [MINOR]
- **Resolution:** ACCEPTED
- **Summary:** Status endpoint needs proper scoping.
- **Action:** Scope to current user's uploads for this project. Support `upload_batch` query param for tracking multi-file upload sessions.

### Issue D-R1-21: Failure/retry behavior not designed [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** No retry mechanism, limits, or error storage.
- **Action:** Add `error_message` TextField, `retry_count` IntegerField (max=3), `last_attempted_at` DateTimeField. New URL: `/projects/<pk>/resumes/<resume_pk>/retry/` (POST).

### Issue D-R1-22: Spec doesn't reference run_extraction_with_retry [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Must explicitly use existing integrity pipeline.
- **Action:** Call `run_extraction_with_retry(raw_text, file_path, ...)` with `use_integrity_pipeline=True` from uploader.py.

### Issue D-R1-23: Telegram notification as hard dependency [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Notification failure must not break core processing.
- **Action:** Notification is best-effort, non-blocking. Check TelegramBinding exists, wrap send in try/except, log failures.

### Issue D-R1-24: file_type choices missing DOC [MINOR]
- **Resolution:** ACCEPTED
- **Summary:** Existing text.py supports .doc, spec should too.
- **Action:** Add `doc` to file_type choices. Update allowed extensions list.

### Issue D-R1-25: FK on_delete behavior unspecified [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Important audit records should survive parent deletion.
- **Action:** `project` → SET_NULL, `candidate` → SET_NULL, `created_by` → SET_NULL. All nullable.

### Issue D-R1-26: Gmail cron concurrency not addressed [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Overlapping cron runs can duplicate processing.
- **Action:** `select_for_update(skip_locked=True)` on EmailMonitorConfig at start of each cron iteration. Skip locked configs.

### Issue D-R1-27: OAuth URLs are global not tenant-aware [MINOR]
- **Resolution:** REBUTTED
- **Summary:** OAuth is per-user OneToOne; organization implicit via session auth. Matches existing URL patterns (`/projects/<pk>/` without org prefix).

### Issue D-R1-28: Retention/privacy policy for uploaded files [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Sensitive data needs clear lifecycle rules.
- **Action:** Discard = delete physical file + status=discarded. Disconnect = revoke tokens + stop monitoring, preserve already-imported. Failed uploads auto-cleanup after 30 days via management command.

## Disputed Items

(None — all items resolved in Round 1)
