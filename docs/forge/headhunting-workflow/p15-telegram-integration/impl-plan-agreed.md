# P15 Telegram Integration — 확정 구현계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Telegram bot integration for notifications, approval actions via Inline Keyboard, multi-step contact recording, text-based task queries, and automated reminders.

**Architecture:** A new `projects/telegram/` package handles bot initialization, message formatting, keyboard building, webhook auth, and callback routing. Views in `projects/views_telegram.py` expose 4 endpoints under `/telegram/`. The notification service (`projects/services/notification.py`) sends messages via the bot and manages idempotency. All business mutations delegate to existing service functions (`approval.py`, `contact.py`) — Telegram handlers are thin wrappers. Text queries reuse P14's `intent_parser` and `entity_resolver` with graceful fallback if P14 is not yet implemented. A management command handles reminders via host cron.

**Tech Stack:** Django 5.2, python-telegram-bot>=21.0, Django cache framework (LocMemCache), HTMX, Tailwind CSS.

**Base:** This plan incorporates all changes from the initial implementation plan (`debate/impl-plan.md`) with 12 amendments from the implementation tempering process (`debate/impl-rulings.md`).

---

## Amendments from Implementation Tempering

The following changes MUST be applied when implementing each task. All reference the original `debate/impl-plan.md` task numbers.

### Amendment A1: Approval Notification Trigger (Task 7)

**Original:** No trigger wiring — approval Inline Keyboard messages are never sent.

**Required:** Modify `projects/views.py` `project_create` to create a Notification and send it after `ProjectApproval.objects.create()`:

```python
# After ProjectApproval.objects.create() in project_create view:
from accounts.models import Membership
from projects.services.notification import send_notification
from projects.telegram.keyboards import build_approval_keyboard
from projects.telegram.formatters import format_approval_request

# Find org owner(s)
owner_memberships = Membership.objects.filter(
    organization=org, role=Membership.Role.OWNER,
).select_related("user")

for m in owner_memberships:
    notif = Notification.objects.create(
        recipient=m.user,
        type=Notification.Type.APPROVAL_REQUEST,
        title=f"프로젝트 승인 요청: {project.title}",
        body=f"{request.user.get_full_name() or request.user.username} → {project.title}",
        callback_data={
            "action": "approval",
            "approval_id": str(approval.pk),
        },
    )
    text = format_approval_request(
        requester_name=request.user.get_full_name() or request.user.username,
        project_title=project.title,
        conflict_info=f"{top_collision['project'].title} ({top_collision['project'].get_status_display()})",
        message=request.POST.get("approval_message", ""),
    )
    short_id = str(notif.pk).replace("-", "")[:8]
    send_notification(notif, text=text, reply_markup=build_approval_keyboard(short_id))
```

### Amendment A2: Text Query Handler (Task 6)

**Original:** Text messages logged only — "future task" placeholder.

**Required:** Add text message handling in `_process_update()` and `handlers.py`:

```python
# In _process_update(), replace the text message logging block with:
def _handle_text_message(chat_id: str, text: str) -> None:
    """Handle free-text messages via intent parser."""
    try:
        binding = TelegramBinding.objects.get(chat_id=chat_id, is_active=True)
    except TelegramBinding.DoesNotExist:
        _safe_send(chat_id, "텔레그램 연동이 필요합니다. 웹 앱에서 연동을 진행해주세요.")
        return

    user = binding.user
    org = user.membership.organization

    # Check for awaiting_text_input state (Amendment A3)
    pending = Notification.objects.filter(
        recipient=user,
        callback_data__contains={"awaiting_text_input": True},
    ).order_by("-created_at").first()
    if pending:
        _handle_awaiting_text(pending, text, user)
        return

    # Try P14 intent parser (graceful fallback)
    try:
        from projects.services.voice.intent_parser import parse_intent
        from projects.services.voice.entity_resolver import resolve_candidate

        result = parse_intent(text, context={"user": user, "organization": org})
        # Handle based on intent...
        _handle_parsed_intent(chat_id, result, user, org)
    except ImportError:
        # P14 not yet implemented — graceful fallback
        _safe_send(chat_id, "텍스트 명령은 아직 준비 중입니다. 웹 앱을 이용해주세요.")
    except Exception:
        logger.exception("Error handling text message")
        _safe_send(chat_id, "요청 처리 중 오류가 발생했습니다.")
```

### Amendment A3: Message Action Completion (Task 6)

**Original:** "message" button returns prompt but has no follow-up path.

**Required:** Add awaiting_text_input state management:

```python
# In handle_approval_callback, for action == "message":
elif action == "message":
    notification.callback_data["awaiting_text_input"] = True
    notification.save(update_fields=["callback_data"])
    return {"ok": True, "result": "awaiting_message", "prompt": "메시지를 입력해주세요."}

# In _handle_awaiting_text():
def _handle_awaiting_text(notification: Notification, text: str, user: User) -> None:
    approval_id = notification.callback_data.get("approval_id")
    if approval_id:
        try:
            approval = ProjectApproval.objects.get(pk=approval_id)
            send_admin_message(approval, user, text)
            notification.callback_data["awaiting_text_input"] = False
            notification.save(update_fields=["callback_data"])
            _update_notification_message(notification, f"💬 메시지 전송 완료: {text[:50]}")
        except Exception:
            logger.exception("Error sending admin message")
```

### Amendment A4: Multi-step Notification Short ID Fix (Task 6)

**Original:** Keyboard uses parent notification's short_id instead of new notification's.

**Required:** In `handle_contact_callback`, create the new Notification FIRST, then build keyboard with new notification's pk:

```python
# Step 1→2 transition:
next_notif = Notification.objects.create(
    recipient=user,
    type=Notification.Type.AUTO_GENERATED,
    title="컨택 기록",
    body=text,
    callback_data=next_cb,
)
new_short_id = str(next_notif.pk).replace("-", "")[:8]
send_notification(next_notif, text=text, reply_markup=build_contact_result_keyboard(new_short_id))
```

### Amendment A5: Contact Creation Service Function (Task 5, 6)

**Original:** `Contact.objects.create()` called directly in handler.

**Required:** Add `create_contact()` to `projects/services/contact.py`:

```python
def create_contact(*, project, candidate, consultant, channel, result, notes=""):
    """Create a contact record with business rule validation.

    Shared by web views and Telegram handlers.
    """
    dup = check_duplicate(project, candidate)
    if dup["blocked"]:
        return {"ok": False, "error": dup["warnings"][0], "contact": None}

    contact = Contact.objects.create(
        project=project,
        candidate=candidate,
        consultant=consultant,
        channel=channel,
        result=result,
        contacted_at=timezone.now(),
        notes=notes,
    )

    # Release overlapping RESERVED locks
    Contact.objects.filter(
        project=project,
        candidate=candidate,
        result=Contact.Result.RESERVED,
        locked_until__gt=timezone.now(),
    ).update(locked_until=timezone.now())

    return {"ok": True, "error": None, "contact": contact, "warnings": dup["warnings"]}
```

Telegram handler calls `create_contact()` instead of `Contact.objects.create()`. Existing `contact_create` view should also be refactored to use this.

### Amendment A6: Safe Project Title Reference (Task 6)

**Original:** `approval.project.title` accessed after `reject_project()`/`merge_project()` deletes the project.

**Required:** Save title before calling service:

```python
if action == "approve":
    project_title = approval.project.title
    approve_project(approval, user)
    _update_notification_message(notification, f"✅ 승인 완료 — {project_title}")

elif action == "reject":
    project_title = approval.project.title
    reject_project(approval, user)
    _update_notification_message(notification, f"❌ 반려 완료 — {project_title}")

elif action == "join":
    project_title = approval.project.title
    merge_project(approval, user)
    _update_notification_message(notification, f"🔗 합류 완료 — {project_title}")
```

### Amendment A7: Template Base Path Fix (Task 7)

**Original:** `{% extends "base.html" %}` — does not exist.

**Required:** Use project convention:

```html
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}
```

### Amendment A8: Approval Callback Auth Fix (Task 7)

**Original:** `verify_telegram_user_access(chat_id, notification.callback_data.get("project"))` passes dict, not model.

**Required:** Look up the actual model first:

```python
# In _process_update, approval branch:
approval = ProjectApproval.objects.select_related("project").get(
    pk=notification.callback_data["approval_id"]
)
user, _ = verify_telegram_user_access(chat_id, approval.project)
handle_approval_callback(notification=notification, action=action, user=user)
```

### Amendment A9: Brute Force Defense Fix (Task 7)

**Original:** Wrong code attempts don't increment `attempts` counter.

**Required:** In `_handle_start_command()`, decouple code lookup from attempt tracking:

```python
def _handle_start_command(chat_id: str, code: str) -> None:
    # Find ANY active verification for this code (regardless of correctness)
    verification = TelegramVerification.objects.filter(
        code=code, consumed=False, expires_at__gt=timezone.now(),
    ).select_related("user").first()

    if not verification:
        _safe_send(chat_id, "인증 코드가 만료되었거나 존재하지 않습니다.")
        return

    # Increment attempts
    verification.attempts += 1
    verification.save(update_fields=["attempts"])

    if verification.is_blocked:
        _safe_send(chat_id, "인증 시도 횟수를 초과했습니다. 새 코드를 발급해주세요.")
        return

    # Success
    verification.consumed = True
    verification.save(update_fields=["consumed"])

    TelegramBinding.objects.update_or_create(
        user=verification.user,
        defaults={"chat_id": chat_id, "is_active": True, "verified_at": timezone.now()},
    )
    _safe_send(chat_id, "✅ synco 텔레그램 연동이 완료되었습니다!")
```

### Amendment A10: Code Collision Prevention (Task 7)

**Original:** `random.choices(string.digits, k=6)` with no collision check.

**Required:** Add collision check in bind view:

```python
# In telegram_bind POST:
for _ in range(3):
    code = "".join(random.choices(string.digits, k=6))
    # Check no active (unconsumed, unexpired) code with same value exists
    collision = TelegramVerification.objects.filter(
        code=code, consumed=False, expires_at__gt=timezone.now(),
    ).exists()
    if not collision:
        break
else:
    # Extremely unlikely - 3 consecutive collisions
    return render(request, template, {"error": "코드 생성에 실패했습니다. 다시 시도해주세요."})
```

### Amendment A11: Callback Query ID Dedup (Task 7)

**Original:** Only `update_id` dedup, no `callback_query_id` dedup.

**Required:** In `_process_update()`, add callback_query dedup:

```python
callback_query = data.get("callback_query")
if callback_query:
    cq_id = callback_query.get("id", "")
    if cq_id:
        cq_cache_key = f"tg_cq:{cq_id}"
        if cache.get(cq_cache_key):
            return
        cache.set(cq_cache_key, True, DEDUP_TTL)
    # ... rest of callback handling
```

### Amendment A12: Deployment Steps (Task 8)

**Original:** No deploy.sh modification, no .env.prod, no cron, no webhook registration.

**Required:** Add deployment task steps:

1. **deploy.sh modification:** Add after validate step:
   ```bash
   # Register Telegram webhook (after image validation)
   docker exec $(docker ps -qf name=synco_web) python manage.py setup_telegram_webhook || true
   ```

2. **.env.prod:** Document that the following keys must be added to `/home/docker/synco/.env.prod`:
   ```
   TELEGRAM_BOT_TOKEN=<bot token from @BotFather>
   SITE_URL=https://synco.kr
   TELEGRAM_WEBHOOK_SECRET=<random secret>
   ```

3. **Host crontab:** Add to `/home/work/synco/deploy.sh` or document manual step:
   ```bash
   # Add to crontab on 49.247.46.171:
   (crontab -l 2>/dev/null; echo "0 8 * * * docker exec \$(docker ps -qf name=synco_web) python manage.py send_reminders >> /home/docker/synco/runtime/logs/reminders.log 2>&1") | crontab -
   ```

---

## Task List (Original + Amendments Applied)

Tasks 1-9 from `debate/impl-plan.md` remain the base, with the following modifications:

| Task | Amendment | Change Summary |
|------|-----------|---------------|
| 1 | — | Dependencies + settings (unchanged) |
| 2 | — | Model migrations (unchanged) |
| 3 | — | Bot init + auth module (unchanged) |
| 4 | — | Keyboards + formatters (unchanged) |
| 5 | A5 | Notification service + `create_contact()` service function |
| 6 | A2, A3, A4, A6 | Handlers: text query handler, message action completion, short_id fix, safe title reference |
| 7 | A1, A7, A8, A9, A10, A11 | Views: approval trigger wiring, template fix, auth fix, brute force fix, code collision check, callback_query dedup |
| 8 | A12 | Management commands + deployment steps |
| 9 | — | Integration test + regression (unchanged) |

---

## Implementation Order

Execute tasks 1 through 9 in order. Each task's steps include the amendments listed above. The implementer MUST read both this document and `debate/impl-plan.md` together, applying the amendments in the table above.

Source: docs/forge/headhunting-workflow/p15-telegram-integration/debate/impl-plan.md
Amendments: docs/forge/headhunting-workflow/p15-telegram-integration/debate/impl-rulings.md

<!-- forge:p15-telegram-integration:구현담금질:complete:2026-04-10T14:00:00Z -->
