# impl-plan Rulings — t13

**Status:** COMPLETE
**Rounds:** 1

---

## Resolved Items

### R1-01: Onboarding URLs deleted from urlpatterns [CRITICAL] — ACCEPTED
Step 3's urlpatterns replacement drops invite/pending/rejected routes. Fix: changed to append-only, preserving all existing routes.

### R1-02: Missing templates cause TemplateDoesNotExist [CRITICAL] — PARTIAL
Templates deferred to t14 by design. Added Step 4 to create stub templates so views render and tests pass.

### R1-03: Root URL `home` duplicated in accounts/urls.py [CRITICAL] — ACCEPTED
Removed `path("", views.home, name="home")` from Step 3. Root stays in main/urls.py.

### R1-04: Tests too weak — only check status code [CRITICAL] — PARTIAL
Added `assertTemplateUsed` checks and HTMX partial verification. Full content assertions deferred to t14.

### R1-05: telegram_bind_partial disconnected from UI flow [MAJOR] — REBUTTED
Endpoint is infrastructure for t14 templates. Must exist before templates can reference it.

### R1-06: NotificationPreference/Form dependency not in File Map [CRITICAL] — REBUTTED
Both exist from t11 (model, commit 42cb509) and t12 (form, commit 9b2a7e1). File Map correctly lists only files modified by t13.

### R1-07: Dangling email_settings URL [MINOR] — REBUTTED
email_settings handles POST for config updates; settings_email is the tab container GET view. Different purposes.

### R1-08: Cross-app import circular reference risk [MAJOR] — REBUTTED
EmailMonitorConfig and TelegramBinding are in accounts/models.py, not projects. No cross-app import.
