# impl-plan Rulings — t18

## Status: COMPLETE

## Resolved Items

### I1 [CRITICAL] Step 1 is a no-op (already implemented)
- **Round:** 1
- **Sources:** Codex (MINOR #4) + Gemini (CRITICAL #1) → escalated CRITICAL
- **Resolution:** ACCEPTED — Step 1 converted from code change to verification + regression test
- **Author response:** email_disconnect already redirects to settings_email at line 420

### I2 [CRITICAL] Step 2 targets wrong view, introduces duplicate logic
- **Round:** 1
- **Sources:** Codex (MAJOR #1, #2) + Gemini (CRITICAL #2) → escalated CRITICAL
- **Resolution:** ACCEPTED — Step 2 removed entirely. settings_email already handles HTMX POST
- **Author response:** Legacy email_settings stays as-is for backward compatibility

### I3 [CRITICAL] Verification plan too weak
- **Round:** 1
- **Sources:** Codex (MAJOR #3) + Gemini (MAJOR #3) → escalated CRITICAL
- **Resolution:** ACCEPTED — Add targeted tests before full suite run
- **Author response:** Zero existing tests for email_disconnect/email_settings paths

### I4 [MINOR] Duplicate save logic drift
- **Round:** 1
- **Sources:** Codex (MINOR #5)
- **Resolution:** ACCEPTED — Note discrepancy, defer consolidation to future task
- **Author response:** Beyond t18 scope, but tests should verify both paths
