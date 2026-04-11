# t18: email_disconnect 리다이렉트 수정 + 최종 통합 테스트

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이메일 관련 뷰의 리다이렉트를 새 설정 탭 URL로 업데이트하고, 전체 테스트 스위트로 2단계 통합을 검증한다.

**Design spec:** `docs/forge/headhunting-onboarding/t18/design-spec.md`

**depends_on:** t13, t14

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `accounts/views.py` | 수정 | email_disconnect 리다이렉트, email_settings HTMX 대응 |

---

- [ ] **Step 1: Update email_disconnect redirect**

In `accounts/views.py`, change `email_disconnect` return:

```python
    return redirect(reverse("settings_email"))
```

- [ ] **Step 2: Update email_settings POST to return settings tab partial**

In `accounts/views.py`, update `email_settings` to redirect to the tab when accessed from settings:

```python
@login_required
def email_settings(request):
    """Gmail monitoring settings page."""
    from .models import EmailMonitorConfig

    config = EmailMonitorConfig.objects.filter(user=request.user).first()

    if request.method == "POST" and config:
        config.filter_labels = request.POST.getlist("filter_labels")
        config.filter_from = [
            e.strip()
            for e in request.POST.get("filter_from", "").split(",")
            if e.strip()
        ]
        config.is_active = request.POST.get("is_active") == "on"
        config.save(
            update_fields=[
                "filter_labels",
                "filter_from",
                "is_active",
                "updated_at",
            ]
        )
        # If HTMX request, return the settings tab partial
        if getattr(request, "htmx", None):
            return render(request, "accounts/partials/settings_email.html", {
                "config": config,
                "active_tab": "email",
            })

    return render(request, "accounts/email_settings.html", {"config": config})
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v --timeout=30`
Expected: All tests PASS (old + new)

- [ ] **Step 4: Commit**

```bash
git add accounts/views.py
git commit -m "fix(accounts): update email redirect to settings tab, HTMX partial response for email settings"
```
