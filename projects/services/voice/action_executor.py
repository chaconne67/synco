"""Voice action executor — preview + confirm for all 11 voice intents.

Two entry points:
    preview_action()  — dry-run, no DB mutations
    confirm_action()  — commits to DB

Dispatches to intent-specific handlers via _PREVIEW_HANDLERS / _CONFIRM_HANDLERS.
"""

from __future__ import annotations

import uuid as uuid_mod
from datetime import date
from typing import Any

from django.db import models as db_models
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.models import Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import (
    Contact,
    Interview,
    Offer,
    Project,
    Submission,
)
from projects.services.contact import check_duplicate, reserve_candidates
from projects.services.dashboard import get_today_actions
from projects.services.lifecycle import (
    is_submission_offer_eligible,
    maybe_advance_to_interviewing,
    maybe_advance_to_negotiating,
)
from projects.services.voice.entity_resolver import (
    resolve_submission_for_interview,
    resolve_submission_for_offer,
)

# ---------------------------------------------------------------------------
# Mapping helpers — Korean UI labels to model constants
# ---------------------------------------------------------------------------

CHANNEL_MAP: dict[str, str] = {
    "전화": Contact.Channel.PHONE,
    "문자": Contact.Channel.SMS,
    "카톡": Contact.Channel.KAKAO,
    "이메일": Contact.Channel.EMAIL,
    "LinkedIn": Contact.Channel.LINKEDIN,
}

RESULT_MAP: dict[str, str] = {
    "응답": Contact.Result.RESPONDED,
    "미응답": Contact.Result.NO_RESPONSE,
    "거절": Contact.Result.REJECTED,
    "관심": Contact.Result.INTERESTED,
    "보류": Contact.Result.ON_HOLD,
    "예정": Contact.Result.RESERVED,
}

INTERVIEW_TYPE_MAP: dict[str, str] = {
    "대면": Interview.Type.IN_PERSON,
    "화상": Interview.Type.VIDEO,
    "전화": Interview.Type.PHONE,
}

NAVIGATE_MAP: dict[str, str] = {
    "projects": "projects:project_list",
    "candidates": "candidates:candidate_list",
    "dashboard": "dashboard",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_candidate(candidate_id: str, organization: Organization) -> Candidate:
    """Resolve candidate by UUID within the organization scope."""
    return Candidate.objects.get(pk=uuid_mod.UUID(candidate_id), owned_by=organization)


def _error(intent: str, message: str) -> dict[str, Any]:
    return {"ok": False, "intent": intent, "error": message}


# ---------------------------------------------------------------------------
# 1. contact_record
# ---------------------------------------------------------------------------


def _preview_contact_record(
    *, entities: dict, project: Project, user: User, organization: Organization
) -> dict[str, Any]:
    candidate = _get_candidate(entities["candidate_id"], organization)
    channel = entities.get("channel", "")
    result_val = entities.get("result", "")
    return {
        "ok": True,
        "intent": "contact_record",
        "summary": (
            f"{candidate.name}님에게 {channel} 컨택 ({result_val}) 기록을 저장합니다."
        ),
        "candidate_id": str(candidate.pk),
        "candidate_name": candidate.name,
    }


def _confirm_contact_record(
    *, entities: dict, project: Project, user: User, organization: Organization
) -> dict[str, Any]:
    candidate = _get_candidate(entities["candidate_id"], organization)
    channel = CHANNEL_MAP.get(entities.get("channel", ""), entities.get("channel", ""))
    result_val = RESULT_MAP.get(entities.get("result", ""), entities.get("result", ""))
    contacted_at_raw = entities.get("contacted_at")
    contacted_at = (
        parse_datetime(contacted_at_raw) if contacted_at_raw else timezone.now()
    )

    dup_check = check_duplicate(project, candidate)
    if dup_check["blocked"]:
        return _error("contact_record", dup_check["warnings"][0])

    contact = Contact.objects.create(
        project=project,
        candidate=candidate,
        consultant=user,
        channel=channel,
        result=result_val,
        contacted_at=contacted_at,
        notes=entities.get("notes", ""),
    )

    # Release overlapping RESERVED locks
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


# ---------------------------------------------------------------------------
# 2. contact_reserve
# ---------------------------------------------------------------------------


def _preview_contact_reserve(
    *, entities: dict, project: Project, user: User, organization: Organization
) -> dict[str, Any]:
    candidate_ids = entities.get("candidate_ids", [])
    names: list[str] = []
    for cid in candidate_ids:
        try:
            c = _get_candidate(cid, organization)
            names.append(c.name)
        except Candidate.DoesNotExist:
            names.append(f"(unknown: {cid})")
    return {
        "ok": True,
        "intent": "contact_reserve",
        "summary": f"{', '.join(names)}를 컨택 예정으로 등록합니다.",
        "candidate_names": names,
    }


def _confirm_contact_reserve(
    *, entities: dict, project: Project, user: User, organization: Organization
) -> dict[str, Any]:
    candidate_ids = entities.get("candidate_ids", [])
    result = reserve_candidates(project, candidate_ids, user)
    created_names = [c.candidate.name for c in result["created"]]
    return {
        "ok": True,
        "intent": "contact_reserve",
        "summary": f"컨택 예정 등록 완료: {', '.join(created_names) or '없음'}",
        "created": [str(c.pk) for c in result["created"]],
        "skipped": result["skipped"],
    }


# ---------------------------------------------------------------------------
# 3. project_create (Amendment A1)
# ---------------------------------------------------------------------------


def _preview_project_create(
    *, entities: dict, project: Project | None, user: User, organization: Organization
) -> dict[str, Any]:
    client_name = entities.get("client", "")
    title = entities.get("title", "")
    return {
        "ok": True,
        "intent": "project_create",
        "summary": f"'{client_name}' 고객사에 '{title}' 프로젝트를 생성합니다.",
        "client": client_name,
        "title": title,
    }


def _confirm_project_create(
    *, entities: dict, project: Project | None, user: User, organization: Organization
) -> dict[str, Any]:
    client_name = entities.get("client", "")
    title = entities.get("title", "")

    # Resolve client by name within organization
    client = Client.objects.filter(
        name__icontains=client_name.strip(),
        organization=organization,
    ).first()
    if not client:
        return _error("project_create", f"고객사 '{client_name}'를 찾을 수 없습니다.")

    new_project = Project.objects.create(
        client=client,
        organization=organization,
        title=title,
        created_by=user,
    )
    return {
        "ok": True,
        "intent": "project_create",
        "summary": f"'{title}' 프로젝트가 생성되었습니다.",
        "project_id": str(new_project.pk),
    }


# ---------------------------------------------------------------------------
# 4. submission_create (Amendment A1)
# ---------------------------------------------------------------------------


def _preview_submission_create(
    *, entities: dict, project: Project, user: User, organization: Organization
) -> dict[str, Any]:
    candidate = _get_candidate(entities["candidate_id"], organization)

    # Check preconditions: INTERESTED contact must exist
    interested = Contact.objects.filter(
        project=project,
        candidate=candidate,
        result=Contact.Result.INTERESTED,
    ).exists()
    if not interested:
        return _error(
            "submission_create",
            f"{candidate.name}님은 '관심' 컨택 이력이 없어 제출서류를 생성할 수 없습니다.",
        )

    # Check for duplicate submission
    existing = Submission.objects.filter(
        project=project,
        candidate=candidate,
    ).exists()
    if existing:
        return _error(
            "submission_create",
            f"{candidate.name}님의 제출서류가 이미 존재합니다.",
        )

    return {
        "ok": True,
        "intent": "submission_create",
        "summary": f"{candidate.name}님의 제출서류를 생성합니다.",
        "candidate_name": candidate.name,
    }


def _confirm_submission_create(
    *, entities: dict, project: Project, user: User, organization: Organization
) -> dict[str, Any]:
    candidate = _get_candidate(entities["candidate_id"], organization)

    interested = Contact.objects.filter(
        project=project,
        candidate=candidate,
        result=Contact.Result.INTERESTED,
    ).exists()
    if not interested:
        return _error(
            "submission_create",
            f"{candidate.name}님은 '관심' 컨택 이력이 없어 제출서류를 생성할 수 없습니다.",
        )

    existing = Submission.objects.filter(
        project=project,
        candidate=candidate,
    ).exists()
    if existing:
        return _error(
            "submission_create",
            f"{candidate.name}님의 제출서류가 이미 존재합니다.",
        )

    submission = Submission.objects.create(
        project=project,
        candidate=candidate,
        consultant=user,
        status=Submission.Status.DRAFTING,
        template=entities.get("template", ""),
    )
    return {
        "ok": True,
        "intent": "submission_create",
        "summary": f"{candidate.name}님의 제출서류가 생성되었습니다.",
        "submission_id": str(submission.pk),
    }


# ---------------------------------------------------------------------------
# 5. interview_schedule (Amendment A1)
# ---------------------------------------------------------------------------


def _preview_interview_schedule(
    *, entities: dict, project: Project, user: User, organization: Organization
) -> dict[str, Any]:
    candidate = _get_candidate(entities["candidate_id"], organization)

    resolution = resolve_submission_for_interview(
        candidate_id=candidate.pk,
        project=project,
    )
    if resolution["status"] != "resolved":
        return _error(
            "interview_schedule",
            f"{candidate.name}님에게 '통과' 상태의 제출서류가 없습니다.",
        )

    return {
        "ok": True,
        "intent": "interview_schedule",
        "summary": (f"{candidate.name}님의 면접을 예약합니다."),
        "submission_id": str(resolution["submission_id"]),
        "candidate_name": candidate.name,
    }


def _confirm_interview_schedule(
    *, entities: dict, project: Project, user: User, organization: Organization
) -> dict[str, Any]:
    candidate = _get_candidate(entities["candidate_id"], organization)

    resolution = resolve_submission_for_interview(
        candidate_id=candidate.pk,
        project=project,
    )
    if resolution["status"] != "resolved":
        return _error(
            "interview_schedule",
            f"{candidate.name}님에게 '통과' 상태의 제출서류가 없습니다.",
        )

    submission = Submission.objects.get(pk=resolution["submission_id"])

    # Determine round number
    existing_count = Interview.objects.filter(submission=submission).count()
    round_num = entities.get("round", existing_count + 1)

    scheduled_at_raw = entities.get("scheduled_at")
    scheduled_at = (
        parse_datetime(scheduled_at_raw) if scheduled_at_raw else timezone.now()
    )

    interview_type = INTERVIEW_TYPE_MAP.get(
        entities.get("type", ""), entities.get("type", Interview.Type.IN_PERSON)
    )

    interview = Interview.objects.create(
        submission=submission,
        round=round_num,
        scheduled_at=scheduled_at,
        type=interview_type,
        location=entities.get("location", ""),
        notes=entities.get("notes", ""),
    )

    maybe_advance_to_interviewing(project)

    return {
        "ok": True,
        "intent": "interview_schedule",
        "summary": f"{candidate.name}님의 {round_num}차 면접이 예약되었습니다.",
        "interview_id": str(interview.pk),
    }


# ---------------------------------------------------------------------------
# 6. offer_create (Amendment A1)
# ---------------------------------------------------------------------------


def _preview_offer_create(
    *, entities: dict, project: Project, user: User, organization: Organization
) -> dict[str, Any]:
    candidate = _get_candidate(entities["candidate_id"], organization)

    resolution = resolve_submission_for_offer(
        candidate_id=candidate.pk,
        project=project,
    )
    if resolution["status"] != "resolved":
        return _error(
            "offer_create",
            f"{candidate.name}님에게 오퍼 생성 가능한 제출서류가 없습니다.",
        )

    sub = Submission.objects.get(pk=resolution["submission_id"])
    if not is_submission_offer_eligible(sub):
        return _error(
            "offer_create",
            f"{candidate.name}님의 최종 면접 결과가 합격이 아닙니다.",
        )

    return {
        "ok": True,
        "intent": "offer_create",
        "summary": f"{candidate.name}님의 오퍼를 생성합니다.",
        "submission_id": str(sub.pk),
        "candidate_name": candidate.name,
    }


def _confirm_offer_create(
    *, entities: dict, project: Project, user: User, organization: Organization
) -> dict[str, Any]:
    candidate = _get_candidate(entities["candidate_id"], organization)

    resolution = resolve_submission_for_offer(
        candidate_id=candidate.pk,
        project=project,
    )
    if resolution["status"] != "resolved":
        return _error(
            "offer_create",
            f"{candidate.name}님에게 오퍼 생성 가능한 제출서류가 없습니다.",
        )

    sub = Submission.objects.get(pk=resolution["submission_id"])
    if not is_submission_offer_eligible(sub):
        return _error(
            "offer_create",
            f"{candidate.name}님의 최종 면접 결과가 합격이 아닙니다.",
        )

    start_date_raw = entities.get("start_date")
    start_date_val: date | None = None
    if start_date_raw:
        parsed_dt = parse_datetime(start_date_raw)
        if parsed_dt:
            start_date_val = parsed_dt.date()
        else:
            try:
                start_date_val = date.fromisoformat(start_date_raw)
            except (ValueError, TypeError):
                pass

    offer = Offer.objects.create(
        submission=sub,
        salary=entities.get("salary", ""),
        position_title=entities.get("position_title", ""),
        start_date=start_date_val,
        terms=entities.get("terms", {}),
        notes=entities.get("notes", ""),
    )

    maybe_advance_to_negotiating(project)

    return {
        "ok": True,
        "intent": "offer_create",
        "summary": f"{candidate.name}님의 오퍼가 생성되었습니다.",
        "offer_id": str(offer.pk),
    }


# ---------------------------------------------------------------------------
# 7. status_query (read-only)
# ---------------------------------------------------------------------------


def _preview_status_query(
    *, entities: dict, project: Project, user: User, organization: Organization
) -> dict[str, Any]:
    contact_count = (
        Contact.objects.filter(project=project)
        .exclude(
            result=Contact.Result.RESERVED,
        )
        .count()
    )
    submission_count = Submission.objects.filter(project=project).count()
    interview_count = Interview.objects.filter(
        submission__project=project,
    ).count()

    return {
        "ok": True,
        "intent": "status_query",
        "summary": (
            f"'{project.title}' 현황: "
            f"컨택 {contact_count}건, 제출 {submission_count}건, 면접 {interview_count}건"
        ),
        "stats": {
            "contacts": contact_count,
            "submissions": submission_count,
            "interviews": interview_count,
            "status": project.status,
        },
    }


# status_query is read-only — confirm behaves the same as preview
_confirm_status_query = _preview_status_query


# ---------------------------------------------------------------------------
# 8. todo_query (read-only)
# ---------------------------------------------------------------------------


def _preview_todo_query(
    *, entities: dict, project: Project | None, user: User, organization: Organization
) -> dict[str, Any]:
    actions = get_today_actions(user, organization)
    summary_items = [a.get("description", a.get("title", "")) for a in actions[:5]]
    return {
        "ok": True,
        "intent": "todo_query",
        "summary": (
            f"오늘의 할 일: {len(actions)}건"
            + (f" — {', '.join(summary_items)}" if summary_items else "")
        ),
        "actions": actions,
    }


_confirm_todo_query = _preview_todo_query


# ---------------------------------------------------------------------------
# 9. search_candidate (Amendment A5)
# ---------------------------------------------------------------------------


def _preview_search(
    *, entities: dict, project: Project | None, user: User, organization: Organization
) -> dict[str, Any]:
    keywords = entities.get("keywords", "")
    results = Candidate.objects.filter(
        owned_by=organization,
    ).filter(
        db_models.Q(name__icontains=keywords) | db_models.Q(email__icontains=keywords)
    )[:10]
    return {
        "ok": True,
        "intent": "search_candidate",
        "summary": f"'{keywords}' 검색 결과: {results.count()}명",
        "candidates": [{"id": str(c.pk), "name": c.name} for c in results],
        "url": None,
    }


_confirm_search = _preview_search


# ---------------------------------------------------------------------------
# 10. navigate
# ---------------------------------------------------------------------------


def _preview_navigate(
    *, entities: dict, project: Project | None, user: User, organization: Organization
) -> dict[str, Any]:
    target = entities.get("target_page", "")
    url_name = NAVIGATE_MAP.get(target)
    if not url_name:
        return {
            "ok": True,
            "intent": "navigate",
            "summary": f"'{target}' 페이지를 찾을 수 없습니다.",
            "url": None,
        }
    url = reverse(url_name)
    return {
        "ok": True,
        "intent": "navigate",
        "summary": f"'{target}' 페이지로 이동합니다.",
        "url": url,
    }


_confirm_navigate = _preview_navigate


# ---------------------------------------------------------------------------
# 11. meeting_navigate (Amendment A10)
# ---------------------------------------------------------------------------


def _preview_meeting_navigate(
    *, entities: dict, project: Project | None, user: User, organization: Organization
) -> dict[str, Any]:
    return {
        "ok": True,
        "intent": "meeting_navigate",
        "summary": "미팅 녹음 업로드 패널을 엽니다.",
        "action": "show_meeting_panel",
    }


_confirm_meeting_navigate = _preview_meeting_navigate


# ---------------------------------------------------------------------------
# Handler dispatch tables
# ---------------------------------------------------------------------------

_PREVIEW_HANDLERS: dict[str, Any] = {
    "contact_record": _preview_contact_record,
    "contact_reserve": _preview_contact_reserve,
    "project_create": _preview_project_create,
    "submission_create": _preview_submission_create,
    "interview_schedule": _preview_interview_schedule,
    "offer_create": _preview_offer_create,
    "status_query": _preview_status_query,
    "todo_query": _preview_todo_query,
    "search_candidate": _preview_search,
    "navigate": _preview_navigate,
    "meeting_navigate": _preview_meeting_navigate,
}

_CONFIRM_HANDLERS: dict[str, Any] = {
    "contact_record": _confirm_contact_record,
    "contact_reserve": _confirm_contact_reserve,
    "project_create": _confirm_project_create,
    "submission_create": _confirm_submission_create,
    "interview_schedule": _confirm_interview_schedule,
    "offer_create": _confirm_offer_create,
    "status_query": _confirm_status_query,
    "todo_query": _confirm_todo_query,
    "search_candidate": _confirm_search,
    "navigate": _confirm_navigate,
    "meeting_navigate": _confirm_meeting_navigate,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def preview_action(
    *,
    intent: str,
    entities: dict[str, Any],
    project: Project | None,
    user: User,
    organization: Organization,
) -> dict[str, Any]:
    """Dry-run preview — no DB changes."""
    handler = _PREVIEW_HANDLERS.get(intent)
    if not handler:
        return _error(intent, f"알 수 없는 인텐트입니다: {intent}")
    try:
        return handler(
            entities=entities,
            project=project,
            user=user,
            organization=organization,
        )
    except Candidate.DoesNotExist:
        return _error(intent, "후보자를 찾을 수 없습니다.")
    except Exception as exc:
        return _error(intent, str(exc))


def confirm_action(
    *,
    intent: str,
    entities: dict[str, Any],
    project: Project | None,
    user: User,
    organization: Organization,
) -> dict[str, Any]:
    """Execute and commit — mutates DB."""
    handler = _CONFIRM_HANDLERS.get(intent)
    if not handler:
        return _error(intent, f"알 수 없는 인텐트입니다: {intent}")
    try:
        return handler(
            entities=entities,
            project=project,
            user=user,
            organization=organization,
        )
    except Candidate.DoesNotExist:
        return _error(intent, "후보자를 찾을 수 없습니다.")
    except Exception as exc:
        return _error(intent, str(exc))
