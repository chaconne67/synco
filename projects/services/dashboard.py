"""대시보드 데이터 집계 서비스.

Phase 2b: Rewritten with Application/ActionItem-based queries.
"""

from __future__ import annotations

import datetime
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import User
from projects.models import (
    ActionItem,
    ActionItemStatus,
    Interview,
    Project,
    ProjectPhase,
    ProjectResult,
    ProjectStatus,
)


def get_today_actions(user: User):
    """해당 사용자의 오늘 할 일 (scheduled_at 오늘 또는 due_at 오늘, overdue 제외)."""
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    return (
        ActionItem.objects.filter(
            assigned_to=user,
            status=ActionItemStatus.PENDING,
        )
        .filter(
            Q(scheduled_at__gte=today_start, scheduled_at__lt=today_end)
            | Q(due_at__gte=max(now, today_start), due_at__lt=today_end)
        )
        .select_related("application__project", "application__candidate", "action_type")
    )


def _sweep_overdue_projects():
    """마감 경과 OPEN 프로젝트를 자동으로 실패 종료.

    정책: deadline < today + hired Application 없음 → status=CLOSED, result=fail.
    관리 커맨드와 동일 로직, 칸반 조회 시 lazy 실행.
    """
    today = timezone.now().date()
    now = timezone.now()

    overdue = Project.objects.filter(
        status=ProjectStatus.OPEN,
        deadline__lt=today,
    ).exclude(applications__hired_at__isnull=False)
    note_suffix = f"\n\n[AUTO-CLOSE {today.isoformat()}] 마감일 경과로 자동 종료 (실패)"
    from projects.models import Application

    for p in overdue:
        Project.objects.filter(pk=p.pk).update(
            status=ProjectStatus.CLOSED,
            result="fail",
            closed_at=now,
            note=(p.note or "") + note_suffix,
        )
        Application.objects.filter(
            project=p, dropped_at__isnull=True, hired_at__isnull=True
        ).update(
            dropped_at=now,
            drop_reason="other",
            drop_note="프로젝트 마감일 경과로 자동 종료",
        )


def get_project_kanban_cards(
    org=None,
    *,
    consultant_id=None,
    client_id=None,
    search=None,
    sort_searching="asc",
    sort_screening="asc",
    sort_closed="desc",
):
    """2-phase 칸반에 필요한 카드 데이터.

    필터:
    - consultant_id: 담당자 UUID (assigned_consultants 중)
    - client_id: 고객사 UUID
    - search: title 또는 client.name ilike

    Note: org parameter is deprecated (single-tenant). Kept for call-site compatibility.
    """
    # 칸반 렌더 직전에 마감 경과 프로젝트 자동 종료 (Stale auto-close)
    _sweep_overdue_projects()

    now = timezone.now()
    qs = (
        Project.objects.all()
        .annotate(
            active_count=Count(
                "applications",
                filter=Q(
                    applications__dropped_at__isnull=True,
                    applications__hired_at__isnull=True,
                ),
            ),
        )
        .select_related("client")
        .prefetch_related("assigned_consultants")
    )
    if consultant_id:
        qs = qs.filter(assigned_consultants__id=consultant_id)
    if client_id:
        qs = qs.filter(client_id=client_id)
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(client__name__icontains=search))
    projects = qs.distinct()

    cards = {
        ProjectPhase.SEARCHING: [],
        ProjectPhase.SCREENING: [],
        "closed": [],
    }

    for project in projects:
        pending_actions = ActionItem.objects.filter(
            application__project=project,
            status=ActionItemStatus.PENDING,
        )
        overdue_count = pending_actions.filter(due_at__lt=now).count()
        pending_count = pending_actions.count()

        # closed + success 프로젝트는 입사자 이름 표시용으로 hired Application 조회
        hired_candidate = None
        if project.status == ProjectStatus.CLOSED and project.result == "success":
            hired_app = (
                project.applications.filter(hired_at__isnull=False)
                .select_related("candidate")
                .first()
            )
            if hired_app:
                hired_candidate = hired_app.candidate

        card = {
            "project": project,
            "active_count": project.active_count,
            "pending_actions_count": pending_count,
            "overdue_count": overdue_count,
            "deadline": project.deadline,
            "days_until_deadline": (
                (project.deadline - now.date()).days if project.deadline else None
            ),
            "hired_candidate": hired_candidate,
        }

        if project.status == ProjectStatus.CLOSED:
            cards["closed"].append(card)
        else:
            cards[project.phase].append(card)

    # 정렬 정책 (컬럼별 독립):
    # - OPEN 컬럼: created_at 기준. 기본 asc(오래된 것 상단).
    # - CLOSED 컬럼: closed_at 기준. 기본 desc(최근 종료건 먼저).
    cards[ProjectPhase.SEARCHING].sort(
        key=lambda c: c["project"].created_at,
        reverse=(sort_searching == "desc"),
    )
    cards[ProjectPhase.SCREENING].sort(
        key=lambda c: c["project"].created_at,
        reverse=(sort_screening == "desc"),
    )
    cards["closed"].sort(
        key=lambda c: c["project"].closed_at or c["project"].updated_at,
        reverse=(sort_closed == "desc"),
    )

    return cards


def _monthly_success(user):
    """S1-1 Monthly Success: 이번 달 성공·진행중·성공률."""
    now_local = timezone.localtime()
    month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    qs = _scope_projects(user)

    closed_this_month = qs.filter(
        status=ProjectStatus.CLOSED,
        closed_at__gte=month_start,
    )
    success = closed_this_month.filter(result=ProjectResult.SUCCESS).count()
    fail = closed_this_month.filter(result=ProjectResult.FAIL).count()
    active = qs.filter(status=ProjectStatus.OPEN).count()
    total = success + fail
    return {
        "success_count": success,
        "active_count": active,
        "success_rate": round(success / total * 100) if total else None,
    }


def _estimated_revenue(user):
    """S1-2 Estimated Revenue: 올해 등록 + (진행중 OR 확정) 프로젝트의 예상 수수료 합계 (원).

    확정 = CLOSED + result=SUCCESS.
    annual_salary·fee_percent 둘 중 하나라도 비어있으면 그 프로젝트는 제외.
    """
    now_local = timezone.localtime()
    year_start = now_local.replace(
        month=1, day=1, hour=0, minute=0, second=0, microsecond=0
    )
    qs = _scope_projects(user).filter(
        created_at__gte=year_start,
        annual_salary__isnull=False,
        fee_percent__isnull=False,
    ).filter(
        Q(status=ProjectStatus.OPEN)
        | Q(status=ProjectStatus.CLOSED, result=ProjectResult.SUCCESS)
    )
    total = sum(p.expected_fee or 0 for p in qs)
    return {"total": total}


def _recent_activity(user, limit: int = 6):
    """S2-2 Recent Activity: 사용자 스코프 기준 최근 이벤트, 시간 desc.

    집계 이벤트:
    - Application.hired_at  → 후보자 배치 확정 (success)
    - Submission.submitted_at → 서류 고객사 송부 (document)
    - Application.created_at → 새 후보자 추가 (plus)
    - Project.closed_at + result=SUCCESS → 프로젝트 성공 종료 (success)
    """
    from accounts.services.scope import scope_work_qs
    from projects.models import Application, Submission

    events = []

    projects_qs = scope_work_qs(Project.objects.all(), user)
    for p in projects_qs.filter(
        status=ProjectStatus.CLOSED,
        result=ProjectResult.SUCCESS,
        closed_at__isnull=False,
    ).select_related("client").order_by("-closed_at")[:limit]:
        events.append({
            "kind": "success",
            "title": "프로젝트가 성공으로 종료되었습니다",
            "subtitle": f"{p.client.name} · {p.title}",
            "ts": p.closed_at,
        })

    apps_qs = scope_work_qs(Application.objects.all(), user)
    for a in apps_qs.filter(hired_at__isnull=False).select_related(
        "project", "project__client", "candidate"
    ).order_by("-hired_at")[:limit]:
        events.append({
            "kind": "success",
            "title": "후보자 배치가 확정되었습니다",
            "subtitle": f"{a.project.client.name} · {a.project.title}",
            "ts": a.hired_at,
        })

    subs_qs = scope_work_qs(Submission.objects.all(), user)
    for s in subs_qs.filter(submitted_at__isnull=False).select_related(
        "action_item__application__project__client"
    ).order_by("-submitted_at")[:limit]:
        project = s.action_item.application.project
        events.append({
            "kind": "document",
            "title": "서류가 고객사에 송부되었습니다",
            "subtitle": f"{project.client.name} · {project.title}",
            "ts": s.submitted_at,
        })

    for a in apps_qs.select_related(
        "project__client"
    ).order_by("-created_at")[:limit]:
        events.append({
            "kind": "plus",
            "title": "새 후보자가 추가되었습니다",
            "subtitle": f"{a.project.client.name} · {a.project.title}",
            "ts": a.created_at,
        })

    events.sort(key=lambda e: e["ts"], reverse=True)
    return events[:limit]


def _project_status_counts(user):
    """S1-3 Project Status: searching/screening/closed 누적 개수."""
    qs = _scope_projects(user)
    return {
        "searching": qs.filter(
            status=ProjectStatus.OPEN, phase=ProjectPhase.SEARCHING
        ).count(),
        "screening": qs.filter(
            status=ProjectStatus.OPEN, phase=ProjectPhase.SCREENING
        ).count(),
        "closed": qs.filter(status=ProjectStatus.CLOSED).count(),
    }


def _display_name(user) -> str:
    """한글 이름 표시. last+first → get_full_name → username."""
    parts = (user.last_name or "").strip() + (user.first_name or "").strip()
    if parts:
        return parts
    full = (user.get_full_name() or "").strip()
    if full:
        return full
    return user.username


def _progress_color(rate):
    """S2-1 progress bar 색상 클래스. rate=None → default."""
    if rate is None:
        return ""
    if rate >= 80:
        return "success"
    if rate >= 60:
        return ""
    return "info"


def _team_performance():
    """S2-1 Team Performance: active staff/boss users, 누적 성공률 desc.

    level >= 1 (STAFF/BOSS) 전체. 표본 없는 멤버(rate=None)는 맨 아래.
    """
    from accounts.models import User as _User

    users = _User.objects.filter(level__gte=1, is_active=True)
    rows = []
    for user in users:
        assigned = user.assigned_projects.all()
        active_count = assigned.filter(status=ProjectStatus.OPEN).count()
        closed = assigned.filter(status=ProjectStatus.CLOSED)
        closed_total = closed.count()
        success_count = closed.filter(result=ProjectResult.SUCCESS).count()
        rate = round(success_count / closed_total * 100) if closed_total else None

        role_label = "CEO" if (user.is_superuser or user.level >= 2) else "MANAGER"

        rows.append(
            {
                "username": user.username,
                "display_name": _display_name(user),
                "role_label": role_label,
                "active_count": active_count,
                "success_rate": rate,
                "progress_color": _progress_color(rate),
            }
        )

    # sort: rate desc NULLS LAST
    rows.sort(key=lambda r: (r["success_rate"] is None, -(r["success_rate"] or 0)))
    return rows


# action_type codes treated as 고객사-related → warning label color in weekly schedule
_CLIENT_FACING_CODES = {"submit_to_client", "pre_meeting"}


def _week_range():
    now = timezone.localtime()
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    next_monday = monday + timedelta(days=7)
    return monday, next_monday


def _weekly_schedule(user, limit: int = 5):
    """S3 Weekly Schedule: 이번 주 Interview + ActionItem 합집합, 시간 asc."""
    from accounts.services.scope import scope_work_qs

    monday, next_monday = _week_range()

    interviews = scope_work_qs(
        Interview.objects.filter(
            scheduled_at__gte=monday,
            scheduled_at__lt=next_monday,
        ),
        user,
    ).select_related(
        "action_item__application__candidate",
        "action_item__application__project__client",
    )
    actions = scope_work_qs(
        ActionItem.objects.filter(
            scheduled_at__gte=monday,
            scheduled_at__lt=next_monday,
        ).exclude(action_type__code="interview_round"),
        user,
    ).select_related(
        "action_type",
        "application__project__client",
    )

    events = []

    for iv in interviews:
        candidate = iv.action_item.application.candidate
        events.append(
            {
                "scheduled_at": iv.scheduled_at,
                "label_color": "info",
                "title": f"{iv.round}차 면접",
                "subtitle": f"후보자: {candidate.name} · {iv.location or '-'}",
            }
        )

    for ai in actions:
        code = ai.action_type.code
        color = "warning" if code in _CLIENT_FACING_CODES else "ink3"
        proj = ai.application.project
        client = proj.client
        events.append(
            {
                "scheduled_at": ai.scheduled_at,
                "label_color": color,
                "title": ai.title,
                "subtitle": f"{proj.title} · {client.name}",
            }
        )

    events.sort(key=lambda e: e["scheduled_at"])
    return events[:limit]


def _month_grid_start(year: int, month: int):
    """이번 달 1일이 속한 주의 일요일(KST 자정)을 반환."""
    first_day = timezone.make_aware(datetime.datetime(year, month, 1))
    # weekday(): Monday=0 … Sunday=6. 일요일 시작 달력이므로:
    # isoweekday(): Monday=1 … Sunday=7. Sunday offset = isoweekday() % 7
    sunday_offset = first_day.isoweekday() % 7
    return first_day - timedelta(days=sunday_offset)


def _monthly_calendar(user) -> list[dict]:
    """S3 Monthly Calendar: 6주×7일=42셀, 이번 달 기준.

    각 셀: {"date": int, "is_today": bool, "is_outside": bool, "event_label": str|None}
    """
    from accounts.services.scope import scope_work_qs

    now = timezone.localtime()
    today = now.date()
    year, month = today.year, today.month

    # 다음 달 첫날
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    month_end = datetime.date(next_year, next_month, 1)

    grid_start = _month_grid_start(year, month)

    # 42-day grid 범위 (aware) — outside-month 셀도 이벤트 표시
    grid_end = grid_start + timedelta(days=42)

    # Interview 쿼리
    interviews_qs = scope_work_qs(
        Interview.objects.filter(
            scheduled_at__gte=grid_start,
            scheduled_at__lt=grid_end,
        ),
        user,
    )

    # date → interview 건수
    interview_counts: dict[datetime.date, int] = {}
    for iv in interviews_qs:
        d = timezone.localtime(iv.scheduled_at).date()
        interview_counts[d] = interview_counts.get(d, 0) + 1

    # ActionItem 쿼리 (interview_round 제외)
    actions_qs = scope_work_qs(
        ActionItem.objects.filter(
            scheduled_at__gte=grid_start,
            scheduled_at__lt=grid_end,
        ).exclude(action_type__code="interview_round"),
        user,
    )

    # date → action 건수
    action_counts: dict[datetime.date, int] = {}
    for ai in actions_qs:
        d = timezone.localtime(ai.scheduled_at).date()
        action_counts[d] = action_counts.get(d, 0) + 1

    cells = []
    for i in range(42):
        cell_date = (grid_start + timedelta(days=i)).date()
        is_outside = cell_date < datetime.date(year, month, 1) or cell_date >= month_end
        n_iv = interview_counts.get(cell_date, 0)
        n_ai = action_counts.get(cell_date, 0)
        if n_iv > 0:
            event_label = "인터뷰" if n_iv == 1 else f"인터뷰 {n_iv}"
        elif n_ai > 0:
            event_label = "일정" if n_ai == 1 else f"일정 {n_ai}"
        else:
            event_label = None
        cells.append(
            {
                "date": cell_date.day,
                "is_today": cell_date == today,
                "is_outside": is_outside,
                "event_label": event_label,
            }
        )
    return cells


def get_dashboard_context(user: User) -> dict:
    """대시보드 카드 전체 컨텍스트.

    Phase 2a: S1-1 Monthly Success, S1-3 Project Status,
              S2-1 Team Performance, S3 Weekly/Monthly Calendar.
    Phase 2b 카드(S1-2 Revenue, S2-2 Recent Activity)는 하드코딩 유지.
    """
    return {
        "monthly_success": _monthly_success(user),
        "estimated_revenue": _estimated_revenue(user),
        "project_status": _project_status_counts(user),
        "team_performance": _team_performance(),
        "recent_activity": _recent_activity(user),
        "weekly_schedule": _weekly_schedule(user),
        "monthly_calendar": _monthly_calendar(user),
        "_scope_owner": user.is_superuser or user.level >= 2,
    }


def _scope_projects(user):
    """업무 스코프 쿼리셋. scope_work_qs 를 그대로 사용."""
    from accounts.services.scope import scope_work_qs

    return scope_work_qs(Project.objects.all(), user)
