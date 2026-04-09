# P14 Voice Agent — 확정 구현계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing Whisper voice search into a conversational voice agent that handles headhunting tasks via voice/text across all screens, plus meeting recording upload with LLM-powered insight extraction.

**Architecture:** Django views serve a `/voice/` URL namespace with 10 endpoints. A 7-service backend pipeline (transcriber, intent_parser, entity_resolver, action_executor, context_resolver, conversation, meeting_analyzer) processes voice input through STT -> intent parsing -> entity resolution -> preview -> confirm flow. Frontend is a floating button + modal on every page using MediaRecorder API and HTMX. Meeting recordings use async processing with status polling.

**Tech Stack:** Django 5.2, HTMX, Tailwind CSS, OpenAI Whisper (gpt-4o-transcribe), Gemini API (google-genai), MediaRecorder API, Django sessions.

**Base:** This plan incorporates all changes from the initial implementation plan (`debate/impl-plan.md`) with 12 amendments from the implementation tempering process (`debate/impl-rulings.md`).

---

## Amendments from Implementation Tempering

The following changes MUST be applied when implementing each task. All reference the original `debate/impl-plan.md` task numbers.

### Amendment A1: All 11 Intents in action_executor (Task 7)

**Original:** Only 7 intents had preview/confirm handlers (contact_record, contact_reserve, status_query, todo_query, navigate, meeting_navigate, search_candidate).

**Required:** Add preview/confirm handlers for ALL 11 intents:

```python
# Add to _PREVIEW_HANDLERS and _CONFIRM_HANDLERS:

def _preview_project_create(*, entities, project, user, organization):
    client_name = entities.get("client", "")
    title = entities.get("title", "")
    return {
        "ok": True,
        "intent": "project_create",
        "summary": f"프로젝트 등록: {client_name} - {title}",
        "details": {"client": client_name, "title": title},
    }

def _confirm_project_create(*, entities, project, user, organization):
    from clients.models import Client as ClientModel
    client_name = entities.get("client", "")
    title = entities.get("title", "")
    # Find or validate client
    client_obj = ClientModel.objects.filter(
        name__icontains=client_name, organization=organization
    ).first()
    if not client_obj:
        return {"ok": False, "intent": "project_create", "error": f"클라이언트 '{client_name}'을 찾을 수 없습니다."}
    new_project = Project.objects.create(
        client=client_obj,
        organization=organization,
        title=title,
        created_by=user,
    )
    return {
        "ok": True,
        "intent": "project_create",
        "summary": f"프로젝트 '{title}'이 등록되었습니다.",
        "record_id": str(new_project.pk),
    }

def _preview_submission_create(*, entities, project, user, organization):
    candidate = _get_candidate(entities["candidate_id"], organization)
    template = entities.get("template", "xd_ko")
    # Check preconditions
    has_interested = Contact.objects.filter(
        project=project, candidate=candidate, result=Contact.Result.INTERESTED
    ).exists()
    if not has_interested:
        return {"ok": False, "intent": "submission_create", "error": f"{candidate.name}님은 관심 컨택이 없어 추천할 수 없습니다."}
    has_existing = Submission.objects.filter(project=project, candidate=candidate).exists()
    if has_existing:
        return {"ok": False, "intent": "submission_create", "error": f"{candidate.name}님은 이미 추천 등록되어 있습니다."}
    return {
        "ok": True,
        "intent": "submission_create",
        "summary": f"{candidate.name}님 추천 서류 생성 (양식: {template})",
        "details": {"candidate": candidate.name, "template": template},
    }

def _confirm_submission_create(*, entities, project, user, organization):
    candidate = _get_candidate(entities["candidate_id"], organization)
    template = entities.get("template", "xd_ko")
    sub = Submission.objects.create(
        project=project,
        candidate=candidate,
        consultant=user,
        template=template,
    )
    return {
        "ok": True,
        "intent": "submission_create",
        "summary": f"{candidate.name}님 추천 서류가 생성되었습니다.",
        "record_id": str(sub.pk),
    }

def _preview_interview_schedule(*, entities, project, user, organization):
    from projects.services.voice.entity_resolver import resolve_submission_for_interview
    sub_result = resolve_submission_for_interview(
        candidate_id=entities.get("candidate_id"),
        project=project,
    )
    if sub_result["status"] != "resolved":
        return {"ok": False, "intent": "interview_schedule", "error": "적격 추천 건을 찾을 수 없습니다."}
    return {
        "ok": True,
        "intent": "interview_schedule",
        "summary": f"면접 일정 등록: {entities.get('scheduled_at', '')}, {entities.get('type', '')}",
        "details": entities,
    }

def _confirm_interview_schedule(*, entities, project, user, organization):
    from projects.services.voice.entity_resolver import resolve_submission_for_interview
    sub_result = resolve_submission_for_interview(
        candidate_id=entities.get("candidate_id"),
        project=project,
    )
    if sub_result["status"] != "resolved":
        return {"ok": False, "intent": "interview_schedule", "error": "적격 추천 건을 찾을 수 없습니다."}
    latest_round = Interview.objects.filter(submission_id=sub_result["submission_id"]).count() + 1
    interview = Interview.objects.create(
        submission_id=sub_result["submission_id"],
        round=latest_round,
        scheduled_at=parse_datetime(entities["scheduled_at"]),
        type=entities.get("type", Interview.Type.IN_PERSON),
        location=entities.get("location", ""),
    )
    maybe_advance_to_interviewing(project)
    return {
        "ok": True,
        "intent": "interview_schedule",
        "summary": f"면접 일정이 등록되었습니다. ({latest_round}차)",
        "record_id": str(interview.pk),
    }

def _preview_offer_create(*, entities, project, user, organization):
    from projects.services.voice.entity_resolver import resolve_submission_for_offer
    sub_result = resolve_submission_for_offer(
        candidate_id=entities.get("candidate_id"),
        project=project,
    )
    if sub_result["status"] != "resolved":
        return {"ok": False, "intent": "offer_create", "error": "오퍼 적격 추천 건을 찾을 수 없습니다."}
    return {
        "ok": True,
        "intent": "offer_create",
        "summary": f"오퍼 등록: 연봉 {entities.get('salary', '')}",
        "details": entities,
    }

def _confirm_offer_create(*, entities, project, user, organization):
    from projects.services.voice.entity_resolver import resolve_submission_for_offer
    sub_result = resolve_submission_for_offer(
        candidate_id=entities.get("candidate_id"),
        project=project,
    )
    if sub_result["status"] != "resolved":
        return {"ok": False, "intent": "offer_create", "error": "오퍼 적격 추천 건을 찾을 수 없습니다."}
    offer = Offer.objects.create(
        submission_id=sub_result["submission_id"],
        salary=entities.get("salary", ""),
        position_title=entities.get("position_title", ""),
    )
    maybe_advance_to_negotiating(project)
    return {
        "ok": True,
        "intent": "offer_create",
        "summary": "오퍼가 등록되었습니다.",
        "record_id": str(offer.pk),
    }
```

### Amendment A2: REQUIRED_ENTITIES Alignment (Task 4)

**Change in intent_parser.py:**

```python
REQUIRED_ENTITIES: dict[str, list[str]] = {
    "project_create": ["client", "title"],
    "contact_record": ["candidate_name", "channel", "contacted_at", "result"],  # contacted_at 추가
    "contact_reserve": ["candidate_names"],
    "submission_create": ["candidate_name", "template"],  # template 필수화
    "interview_schedule": ["candidate_name", "scheduled_at", "type"],
    "offer_create": ["candidate_name", "salary"],
    "search_candidate": ["keywords"],
    "navigate": ["target_page"],
}
```

### Amendment A3: List-based Candidate Resolution for contact_reserve (Task 5, 9)

**Add to entity_resolver.py:**

```python
def resolve_candidate_list(
    *,
    names: list[str],
    organization: Organization,
    project: Project | None = None,
) -> dict[str, Any]:
    """Resolve multiple candidate names to UUIDs.
    Returns: {"resolved_ids": [...], "ambiguous": [...], "not_found": [...]}
    """
    resolved_ids = []
    ambiguous = []
    not_found = []
    for name in names:
        result = resolve_candidate(name=name, organization=organization, project=project)
        if result.status == "resolved":
            resolved_ids.append(str(result.candidate_id))
        elif result.status == "ambiguous":
            ambiguous.append({"name": name, "candidates": result.candidates})
        else:
            not_found.append(name)
    return {"resolved_ids": resolved_ids, "ambiguous": ambiguous, "not_found": not_found}
```

**Change in views_voice.py voice_intent:** Handle `candidate_names` (list) in addition to singular `candidate_name`:

```python
if result.entities.get("candidate_names"):
    list_result = resolve_candidate_list(
        names=result.entities["candidate_names"],
        organization=org,
        project=project,
    )
    result.entities["candidate_ids"] = list_result["resolved_ids"]
    result.entities["_candidate_list_resolution"] = list_result
```

### Amendment A4: Multi-turn Continuation Logic (Task 6, 9, 12)

**Add reset endpoint to urls_voice.py:**

```python
path("reset/", views_voice.voice_reset, name="voice_reset"),
```

**Add to views_voice.py:**

```python
@login_required
@require_POST
def voice_reset(request):
    """POST /voice/reset/ — clear conversation state."""
    mgr = ConversationManager(request.session)
    mgr.reset()
    return JsonResponse({"ok": True})
```

**Add continuation logic to voice_intent view:**
When `pending_intent` exists, merge the new text as additional entity input rather than starting a new intent parse:

```python
mgr = ConversationManager(request.session)
conv = mgr.get_or_create()
if conv["pending_intent"] and conv["missing_fields"]:
    # This is a follow-up answer — merge into pending intent
    # Re-parse with context of what's missing
    result = parse_intent(
        text=text,
        context={**ctx, "pending_intent": conv["pending_intent"], "missing_fields": conv["missing_fields"]},
    )
    # Merge new entities into collected
    for k, v in result.entities.items():
        if v:
            conv["collected_entities"][k] = v
    # Recalculate missing
    required = REQUIRED_ENTITIES.get(conv["pending_intent"], [])
    still_missing = [f for f in required if not conv["collected_entities"].get(f)]
    conv["missing_fields"] = still_missing
    request.session.modified = True
    # ... return updated state
```

**Fix JS close handler:** Change `this._post("/voice/history/", ...)` to `this._post("/voice/reset/", {})`.

**Add server-side inactivity tracking in conversation.py:**

```python
import time

def get_or_create(self) -> dict[str, Any]:
    if SESSION_KEY in self._session:
        conv = self._session[SESSION_KEY]
        # Check 5-minute inactivity
        last_active = conv.get("last_active", 0)
        if time.time() - last_active > 300:
            del self._session[SESSION_KEY]
            return self.get_or_create()
    # ... create new
    conv["last_active"] = time.time()
    return conv

def touch(self):
    """Update last activity timestamp."""
    conv = self.get_or_create()
    conv["last_active"] = time.time()
    self._session.modified = True
```

### Amendment A5: Fix search_candidate (Task 7, 12)

**Replace _preview_search and _confirm_search:**

```python
def _preview_search(*, entities, project, user, organization):
    keywords = entities.get("keywords", "")
    # Use existing search infrastructure
    from candidates.models import Candidate
    results = Candidate.objects.filter(
        owned_by=organization,
    ).filter(
        models.Q(name__icontains=keywords) |
        models.Q(email__icontains=keywords)
    )[:10]
    return {
        "ok": True,
        "intent": "search_candidate",
        "summary": f"'{keywords}' 검색 결과: {results.count()}명",
        "candidates": [{"id": str(c.pk), "name": c.name} for c in results],
        "url": None,  # Results shown inline in modal
    }
```

### Amendment A6: Fix contact_record to Use Business Rules (Task 7)

**Replace _confirm_contact_record:**

```python
def _confirm_contact_record(*, entities, project, user, organization):
    candidate = _get_candidate(entities["candidate_id"], organization)
    channel = CHANNEL_MAP.get(entities.get("channel", ""), "")
    result_val = RESULT_MAP.get(entities.get("result", ""), "")
    contacted_at = parse_datetime(entities.get("contacted_at")) if entities.get("contacted_at") else timezone.now()

    # Check duplicate (same as existing view flow)
    dup_check = check_duplicate(project, candidate)
    if dup_check["blocked"]:
        return {"ok": False, "intent": "contact_record", "error": dup_check["warnings"][0]}

    contact = Contact.objects.create(
        project=project,
        candidate=candidate,
        consultant=user,
        channel=channel,
        result=result_val,
        contacted_at=contacted_at,
        notes=entities.get("notes", ""),
    )

    # Release overlapping RESERVED locks (same as existing view)
    Contact.objects.filter(
        project=project,
        candidate=candidate,
        result=Contact.Result.RESERVED,
        locked_until__gt=timezone.now(),
    ).update(locked_until=timezone.now())

    return {
        "ok": True,
        "intent": "contact_record",
        "summary": f"{candidate.name}님 컨택 기록이 저장되었습니다.",
        "record_id": str(contact.pk),
        "warnings": dup_check["warnings"],
    }
```

### Amendment A7: Intent-specific Submission Resolution (Task 5)

**Add to entity_resolver.py:**

```python
def resolve_submission_for_interview(
    *,
    candidate_id,
    project: Project,
) -> dict[str, Any]:
    """Resolve eligible submission for interview scheduling. PASSED status required."""
    eligible = Submission.objects.filter(
        project=project,
        candidate_id=candidate_id,
        status=Submission.Status.PASSED,
    ).order_by("-created_at")
    subs = list(eligible)
    if len(subs) == 0:
        return {"status": "not_found", "submission_id": None}
    if len(subs) == 1:
        return {"status": "resolved", "submission_id": subs[0].pk}
    return {"status": "ambiguous", "submission_id": None, "submissions": [{"id": str(s.pk)} for s in subs]}


def resolve_submission_for_offer(
    *,
    candidate_id,
    project: Project,
) -> dict[str, Any]:
    """Resolve eligible submission for offer creation.
    Must be PASSED, latest interview passed, no existing offer."""
    from projects.services.lifecycle import is_submission_offer_eligible

    eligible = Submission.objects.filter(
        project=project,
        candidate_id=candidate_id,
        status=Submission.Status.PASSED,
    ).order_by("-created_at")

    # Filter: no existing offer + latest interview passed
    valid = []
    for sub in eligible:
        has_offer = hasattr(sub, 'offer')
        try:
            _ = sub.offer
            has_offer = True
        except Offer.DoesNotExist:
            has_offer = False
        if not has_offer and is_submission_offer_eligible(sub):
            valid.append(sub)

    if len(valid) == 0:
        return {"status": "not_found", "submission_id": None}
    if len(valid) == 1:
        return {"status": "resolved", "submission_id": valid[0].pk}
    return {"status": "ambiguous", "submission_id": None, "submissions": [{"id": str(s.pk)} for s in valid]}
```

### Amendment A8: Meeting Upload Async Kickoff + Candidate Validation (Task 9)

**Change in views_voice.py voice_meeting_upload:**

```python
# After MeetingRecord creation, validate candidate ownership:
from candidates.models import Candidate
try:
    candidate_obj = Candidate.objects.get(pk=candidate_id, owned_by=org)
except Candidate.DoesNotExist:
    return JsonResponse({"error": "후보자를 찾을 수 없습니다."}, status=404)

# After record creation, start async processing:
import threading
from projects.services.voice.meeting_analyzer import analyze_meeting

def _run_analysis(record_id):
    try:
        analyze_meeting(record_id)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Async meeting analysis failed")

thread = threading.Thread(target=_run_analysis, args=(record.pk,), daemon=True)
thread.start()
```

### Amendment A9: 120-minute Duration Validation (Task 8)

**Add to meeting_analyzer.py validate_meeting_file:**

```python
import subprocess

MAX_DURATION_MINUTES = 120

def _get_audio_duration(file_path: str) -> float | None:
    """Get audio duration in seconds using ffprobe. Returns None if unavailable."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return None

def validate_meeting_file(f) -> list[str]:
    errors = []
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        errors.append(f"허용되지 않는 파일 형식입니다. ({', '.join(ALLOWED_EXTENSIONS)})")
    if f.size > MAX_FILE_SIZE:
        errors.append(f"파일 크기가 {MAX_FILE_SIZE // (1024*1024)}MB를 초과합니다.")
    # Duration check (best-effort, requires ffprobe)
    if hasattr(f, 'temporary_file_path'):
        duration = _get_audio_duration(f.temporary_file_path())
        if duration and duration > MAX_DURATION_MINUTES * 60:
            errors.append(f"녹음 길이가 {MAX_DURATION_MINUTES}분을 초과합니다.")
    return errors
```

### Amendment A10: Meeting Navigate UI Flow (Task 11, 12)

**meeting_navigate returns a panel switch command instead of a URL redirect:**

```python
def _preview_meeting_navigate(*, entities, project, user, organization):
    return {
        "ok": True,
        "intent": "meeting_navigate",
        "summary": "미팅 녹음 업로드 패널을 엽니다.",
        "action": "show_meeting_panel",  # JS interprets this to switch modal panel
    }
```

**JS handles `action: "show_meeting_panel"` by showing the upload form within the modal:**

```javascript
_executeImmediate: function (intentData) {
    var self = this;
    // ...
    .then(function (data) {
        if (data.action === "show_meeting_panel") {
            self._showMeetingPanel();
            return;
        }
        // ... existing URL redirect logic
    });
},

_showMeetingPanel: function () {
    // Load meeting upload form via HTMX or inline
    this.messages.innerHTML = '';
    // Fetch and render meeting upload form with project/candidate selects populated
    fetch("/voice/meeting-upload/", { method: "GET", headers: { "X-CSRFToken": this._getCsrf() } })
        .then(function(r) { return r.text(); })
        .then(function(html) {
            self.messages.innerHTML = html;
            // ... wire up form submit, polling, apply
        });
},
```

**Add GET handler to voice_meeting_upload** that returns the upload form HTML (partial template).

### Amendment A11: Field-specific Meeting Insights Apply (Task 8)

**Replace apply_meeting_insights in meeting_analyzer.py:**

```python
# Interest level -> Contact.result mapping
INTEREST_TO_RESULT = {
    "높음": Contact.Result.INTERESTED,
    "보통": Contact.Result.RESPONDED,
    "낮음": Contact.Result.ON_HOLD,
}

def apply_meeting_insights(*, record, selected_fields, user):
    analysis = record.edited_json if record.edited_json else record.analysis_json
    note_parts = [f"[미팅녹음분석 {record.pk}]"]

    for field in selected_fields:
        value = analysis.get(field, "")
        if not value:
            continue

        if field == "interest_level":
            # Update Contact.result
            result_val = INTEREST_TO_RESULT.get(value)
            if result_val:
                contact = Contact.objects.filter(
                    project=record.project, candidate=record.candidate,
                ).exclude(result=Contact.Result.RESERVED).order_by("-contacted_at").first()
                if contact:
                    contact.result = result_val
                    contact.save(update_fields=["result"])

        elif field == "action_items":
            # Create new RESERVED contact with next_contact_date
            from datetime import timedelta
            reserve_contact = Contact.objects.create(
                project=record.project,
                candidate=record.candidate,
                consultant=user,
                result=Contact.Result.RESERVED,
                locked_until=timezone.now() + timedelta(days=7),
                next_contact_date=(timezone.now() + timedelta(days=3)).date(),
                notes=f"[미팅녹음분석 {record.pk}] 액션 아이템: {value}",
            )

        elif field == "mood":
            # mood stays in analysis_json only, not applied to DB
            continue

        else:
            # All other fields -> Contact.notes append
            label = FIELD_LABELS.get(field, field)
            note_parts.append(f"- {label}: {value}")

    # Append notes if any non-mood, non-special fields
    if len(note_parts) > 1:
        notes_text = "\n".join(note_parts)
        existing_contact = Contact.objects.filter(
            project=record.project, candidate=record.candidate,
        ).exclude(result=Contact.Result.RESERVED).order_by("-contacted_at").first()
        if existing_contact:
            existing_contact.notes = (existing_contact.notes + "\n\n" + notes_text).strip()
            existing_contact.save(update_fields=["notes"])
        else:
            Contact.objects.create(
                project=record.project,
                candidate=record.candidate,
                consultant=user,
                channel=Contact.Channel.PHONE,
                result=Contact.Result.RESPONDED,
                contacted_at=timezone.now(),
                notes=notes_text,
            )

    record.status = MeetingRecord.Status.APPLIED
    record.applied_at = timezone.now()
    record.applied_by = user
    record.save(update_fields=["status", "applied_at", "applied_by"])
```

### Amendment A12: Expanded Test Coverage

**Add to tests/test_p14_voice_action_executor.py:**
- Tests for all 11 intents (project_create, submission_create, interview_schedule, offer_create, contact_reserve, status_query, todo_query, navigate, meeting_navigate, search_candidate)
- Test contact_record blocked duplicate
- Test contact_record clears RESERVED lock
- Test submission_create rejects non-INTERESTED candidate
- Test submission_create rejects duplicate submission
- Test interview_schedule rejects non-PASSED submission
- Test offer_create rejects non-eligible submission

**Add to tests/test_p14_voice_entity_resolver.py:**
- Test resolve_candidate_list with mixed results
- Test resolve_submission_for_interview
- Test resolve_submission_for_offer with eligibility rules

**Add to tests/test_p14_voice_views.py:**
- Test /voice/intent/ endpoint
- Test /voice/preview/ endpoint
- Test /voice/confirm/ with valid and reused tokens
- Test /voice/reset/ endpoint
- Test JSON + multipart CSRF handling
- Test multi-turn flow (pending intent -> follow-up)

**Add to tests/test_p14_voice_meeting.py:**
- Test validate_meeting_file with >120min duration (mock ffprobe)
- Test apply_meeting_insights interest_level -> Contact.result
- Test apply_meeting_insights action_items -> RESERVED Contact creation
- Test apply_meeting_insights mood -> not applied to DB
- Test candidate ownership validation in upload
- Test async processing kickoff

**Add to tests/test_p14_voice_conversation.py:**
- Test 5-minute inactivity auto-reset
- Test touch() updates last_active

---

## Task List (Original + Amendments Applied)

Tasks 1-13 from `debate/impl-plan.md` remain the base, with the following modifications:

| Task | Amendment | Change Summary |
|------|-----------|---------------|
| 1 | — | MeetingRecord model (unchanged) |
| 2 | — | Transcriber service (unchanged) |
| 3 | — | Context resolver (unchanged) |
| 4 | A2 | Intent parser: fix REQUIRED_ENTITIES (contacted_at required, template required) |
| 5 | A3, A7 | Entity resolver: add resolve_candidate_list, resolve_submission_for_interview, resolve_submission_for_offer |
| 6 | A4 | Conversation: add touch(), last_active, 5-min server-side reset |
| 7 | A1, A5, A6 | Action executor: add 4 missing intent handlers, fix search_candidate, fix contact_record business rules |
| 8 | A9, A11 | Meeting analyzer: add duration validation, fix field-specific DB apply mapping |
| 9 | A4, A8, A10 | Views + URLs: add /voice/reset/, fix meeting upload (candidate validation, async kickoff, GET handler for form), fix meeting_navigate |
| 10 | — | Management command (unchanged, but now also triggered from upload view) |
| 11 | A10 | Frontend templates: integrate meeting upload/status panels into modal |
| 12 | A4, A5, A10 | voice-agent.js: fix reset to POST /voice/reset/, add multi-turn continuation, add meeting panel UI |
| 13 | A12 | Tests: expand to cover all 11 intents, business rules, entity resolution variants, views, meeting field mapping |

---

## Implementation Order

Execute tasks in order 1 through 13. Each task's steps include the amendments listed above. The implementer MUST read both this document and `debate/impl-plan.md` together, applying the amendments in the table above.

Source: docs/forge/headhunting-workflow/p14-voice-agent/debate/impl-plan.md
Amendments: docs/forge/headhunting-workflow/p14-voice-agent/debate/impl-rulings.md

<!-- forge:p14-voice-agent:구현담금질:complete:2026-04-10T01:15:00Z -->
