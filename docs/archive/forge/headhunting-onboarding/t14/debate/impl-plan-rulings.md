# impl-plan Rulings — t14: 설정 탭 템플릿 구현

**Status:** COMPLETE (Round 1)
**Document:** docs/forge/headhunting-onboarding/t14/debate/impl-plan.md

---

## Resolved Items

### R1-01 [CRITICAL] — ACCEPTED
HTMX main navigation entry does not render tab bar. Tab views return only partial for HTMX, but sidebar entry targets `#main-content` and needs the full tab shell. Plan must add HX-Target header detection logic.

### R1-02 [CRITICAL] — ACCEPTED
Email tab POST goes to legacy `email_settings` endpoint returning wrong template. Template must POST to `settings_email` instead. View-side POST handling must be added as a required companion change.

### R1-03 [CRITICAL] — ACCEPTED
Telegram test/unbind return full page template instead of tab partial. Template must use partial-aware endpoints or note that partial variants are required for test/unbind.

### R1-04 [CRITICAL] — ACCEPTED
Test plan ignores t13 R1-04. Must add content verification tests (tab bar presence, active tab content, HTMX partial correctness).

### R1-05 [MINOR] — ACCEPTED
Style tokens inconsistent (text-[14px], focus:ring-indigo-500 vs project conventions). Note preferred tokens in plan.

### R1-06 [MINOR] — ACCEPTED
terms/privacy links hardcoded. Use {% url %} template tags.

### R1-07 [MINOR] — REBUTTED
HTMX redirect for /accounts/settings/ not handled. Outside t14 scope (view logic, not template). HTMX follows 302 redirects transparently — user won't see full page reload.

---

## Disputed Items

None — all items resolved in Round 1.
