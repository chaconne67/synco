"""컨택 중복 체크 + 잠금 관리 서비스."""

from datetime import timedelta

from django.db import models as db_models
from django.utils import timezone

from projects.models import Contact

LOCK_DURATION_DAYS = 7

# 차단 결과: 이미 명확한 의사 표시가 있는 경우
BLOCKING_RESULTS = {Contact.Result.INTERESTED, Contact.Result.REJECTED}

# 경고 결과: 재컨택 허용
WARNING_RESULTS = {
    Contact.Result.RESPONDED,
    Contact.Result.NO_RESPONSE,
    Contact.Result.ON_HOLD,
}


def check_duplicate(project, candidate):
    """
    중복 컨택 체크.

    Returns:
        {
            "blocked": bool,       # True이면 저장 불가
            "warnings": list[str], # 경고 메시지 목록
            "other_projects": list[Contact],  # 다른 프로젝트의 컨택 이력
        }
    """
    result = {
        "blocked": False,
        "warnings": [],
        "other_projects": [],
    }

    # 같은 프로젝트 내 동일 후보자 컨택 이력 (예정 제외)
    same_project_contacts = (
        Contact.objects.filter(
            project=project,
            candidate=candidate,
        )
        .exclude(result=Contact.Result.RESERVED)
        .select_related("consultant")
    )

    for contact in same_project_contacts:
        consultant_name = ""
        if contact.consultant:
            consultant_name = (
                contact.consultant.get_full_name() or contact.consultant.username
            )

        if contact.result in BLOCKING_RESULTS:
            result["blocked"] = True
            contacted_date = (
                contact.contacted_at.strftime("%m/%d") if contact.contacted_at else "-"
            )
            result["warnings"].append(
                f"이미 '{contact.get_result_display()}' 결과로 컨택된 후보자입니다. "
                f"(담당: {consultant_name}, {contacted_date})"
            )
        elif contact.result in WARNING_RESULTS:
            contacted_date = (
                contact.contacted_at.strftime("%m/%d") if contact.contacted_at else "-"
            )
            result["warnings"].append(
                f"이전 컨택 이력이 있습니다: {contact.get_result_display()} "
                f"(담당: {consultant_name}, {contacted_date})"
            )

    # 같은 프로젝트 내 예정(잠금) 체크
    reserved = (
        Contact.objects.filter(
            project=project,
            candidate=candidate,
            result=Contact.Result.RESERVED,
            locked_until__gt=timezone.now(),
        )
        .select_related("consultant")
        .first()
    )

    if reserved:
        consultant_name = ""
        if reserved.consultant:
            consultant_name = (
                reserved.consultant.get_full_name() or reserved.consultant.username
            )
        result["warnings"].append(
            f"{consultant_name}이(가) 컨택 예정 등록 "
            f"(잠금 만료: {reserved.locked_until:%m/%d})"
        )

    # 다른 프로젝트의 컨택 이력
    other_contacts = (
        Contact.objects.filter(candidate=candidate)
        .exclude(project=project)
        .exclude(result=Contact.Result.RESERVED)
        .select_related("project", "consultant")
        .order_by("-contacted_at")[:5]
    )
    result["other_projects"] = list(other_contacts)

    return result


def reserve_candidates(project, candidate_ids, consultant):
    """
    후보자들을 컨택 예정 등록(잠금).

    Returns:
        {"created": list[Contact], "skipped": list[str]}
    """
    created = []
    skipped = []
    now = timezone.now()
    lock_until = now + timedelta(days=LOCK_DURATION_DAYS)

    for cid in candidate_ids:
        # 이미 잠금 또는 컨택 완료(차단 결과) 존재 시 skip
        existing = (
            Contact.objects.filter(
                project=project,
                candidate_id=cid,
            )
            .filter(
                db_models.Q(result=Contact.Result.RESERVED, locked_until__gt=now)
                | db_models.Q(result__in=list(BLOCKING_RESULTS))
            )
            .exists()
        )

        if existing:
            from candidates.models import Candidate

            try:
                name = Candidate.objects.get(pk=cid).name
            except Candidate.DoesNotExist:
                name = str(cid)
            skipped.append(name)
            continue

        contact = Contact.objects.create(
            project=project,
            candidate_id=cid,
            consultant=consultant,
            result=Contact.Result.RESERVED,
            locked_until=lock_until,
            channel="",
            contacted_at=None,
        )
        created.append(contact)

    return {"created": created, "skipped": skipped}


def release_expired_reservations():
    """만료된 예정 건의 잠금 해제 (locked_until 리셋)."""
    return Contact.objects.filter(
        result=Contact.Result.RESERVED,
        locked_until__lt=timezone.now(),
    ).update(locked_until=None)
