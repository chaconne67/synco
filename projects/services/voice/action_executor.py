"""Voice action executor — preview + confirm for voice intents.

Two entry points:
    preview_action()  — dry-run, no DB mutations
    confirm_action()  — commits to DB

Dispatches to intent-specific handlers via _PREVIEW_HANDLERS / _CONFIRM_HANDLERS.
"""

from __future__ import annotations

import uuid as uuid_mod
from typing import Any

from django.db import models as db_models
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.models import Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import (
    Interview,
    Project,
    Submission,
)
from projects.services.dashboard import get_today_actions
from projects.services.voice.entity_resolver import resolve_submission_for_interview

# ---------------------------------------------------------------------------
# Mapping helpers — Korean UI labels to model constants
# ---------------------------------------------------------------------------

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
# 1. project_create (Amendment A1)
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

    return {
        "ok": True,
        "intent": "interview_schedule",
        "summary": f"{candidate.name}님의 {round_num}차 면접이 예약되었습니다.",
        "interview_id": str(interview.pk),
    }


# ---------------------------------------------------------------------------
# 6. status_query (read-only)
# ---------------------------------------------------------------------------


def _preview_status_query(
    *, entities: dict, project: Project, user: User, organization: Organization
) -> dict[str, Any]:
    from projects.models import Application

    application_count = Application.objects.filter(
        project=project,
        dropped_at__isnull=True,
        hired_at__isnull=True,
    ).count()
    submission_count = Submission.objects.filter(project=project).count()
    interview_count = Interview.objects.filter(
        submission__project=project,
    ).count()

    return {
        "ok": True,
        "intent": "status_query",
        "summary": (
            f"'{project.title}' 현황: "
            f"매칭 {application_count}건, 제출 {submission_count}건, 면접 {interview_count}건"
        ),
        "stats": {
            "applications": application_count,
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
    "project_create": _preview_project_create,
    "submission_create": _preview_submission_create,
    "interview_schedule": _preview_interview_schedule,
    "status_query": _preview_status_query,
    "todo_query": _preview_todo_query,
    "search_candidate": _preview_search,
    "navigate": _preview_navigate,
    "meeting_navigate": _preview_meeting_navigate,
}

_CONFIRM_HANDLERS: dict[str, Any] = {
    "project_create": _confirm_project_create,
    "submission_create": _confirm_submission_create,
    "interview_schedule": _confirm_interview_schedule,
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
