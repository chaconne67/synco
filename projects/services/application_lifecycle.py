from django.db import IntegrityError, transaction
from django.utils import timezone

from projects.models import (
    ActionItem,
    ActionItemStatus,
    Application,
    DropReason,
    Project,
    ProjectResult,
    ProjectStatus,
)
from projects.services.phase import compute_project_phase


def create_application(
    project: Project,
    candidate,
    actor,
    *,
    notes: str = "",
) -> Application:
    """Create Application with guards. Single entry point for web + voice."""
    if project.closed_at is not None:
        raise ValueError("cannot add candidate to a closed project")

    try:
        with transaction.atomic():
            application = Application.objects.create(
                project=project,
                candidate=candidate,
                notes=notes,
                created_by=actor,
            )
    except IntegrityError:
        raise ValueError("이미 매칭된 후보자입니다.")
    return application


def drop(application: Application, reason: str, actor, note: str = "") -> Application:
    """Drop an application. Auto-cancels pending actions."""
    # transition guards [I-07]
    if application.dropped_at is not None:
        raise ValueError("already dropped")
    if application.hired_at is not None:
        raise ValueError("cannot drop a hired application")
    if reason not in DropReason.values:
        raise ValueError(f"invalid drop_reason: {reason}")

    # atomic [I-05]
    with transaction.atomic():
        application.dropped_at = timezone.now()
        application.drop_reason = reason
        application.drop_note = note
        application.save(
            update_fields=["dropped_at", "drop_reason", "drop_note", "updated_at"]
        )
        ActionItem.objects.filter(
            application=application,
            status=ActionItemStatus.PENDING,
        ).update(status=ActionItemStatus.CANCELLED)
    return application


def restore(application: Application, actor) -> Application:
    """Undo drop. Cannot restore hired or in closed project."""
    # transition guards [I-07]
    if application.dropped_at is None:
        raise ValueError("application is not dropped")
    if application.hired_at is not None:
        raise ValueError("cannot restore a hired application")
    if application.project.closed_at is not None:
        raise ValueError("cannot restore application in a closed project")

    application.dropped_at = None
    application.drop_reason = ""
    application.drop_note = ""
    application.save(
        update_fields=["dropped_at", "drop_reason", "drop_note", "updated_at"]
    )
    return application


def hire(application: Application, actor) -> Application:
    """Confirm hire. Owns full HIRED processing: project close + losers drop. [I-01, I-02]"""
    # transition guards [I-07]
    if application.dropped_at is not None:
        raise ValueError("cannot hire a dropped application")
    if application.hired_at is not None:
        raise ValueError("already hired")

    with transaction.atomic():
        # lock project + check for existing hired [I-02]
        project = Project.objects.select_for_update().get(pk=application.project_id)

        if project.closed_at is not None:
            raise ValueError("cannot hire in a closed project")

        existing_hired = (
            Application.objects.select_for_update()
            .filter(
                project=project,
                hired_at__isnull=False,
            )
            .exists()
        )
        if existing_hired:
            raise ValueError("another application is already hired in this project")

        now = timezone.now()

        # 1. confirm hire
        application.hired_at = now
        application.save(update_fields=["hired_at", "updated_at"])

        # 2. auto-close project
        auto_note = f"[자동] {application.candidate} 입사 확정으로 종료"
        project.closed_at = now
        project.status = ProjectStatus.CLOSED
        project.result = ProjectResult.SUCCESS
        project.note = (
            (project.note + "\n" + auto_note).strip() if project.note else auto_note
        )
        project.save(
            update_fields=["closed_at", "status", "result", "note", "updated_at"]
        )

        # 3. drop all other active applications — bulk [I-01, I-06]
        others = Application.objects.filter(
            project=project,
            dropped_at__isnull=True,
            hired_at__isnull=True,
        ).exclude(id=application.id)

        drop_note = f"입사자({application.candidate}) 확정으로 포지션 마감"
        others.update(
            dropped_at=now,
            drop_reason=DropReason.OTHER,
            drop_note=drop_note,
            updated_at=now,
        )

        # 4. cancel losers' pending actions [I-01]
        ActionItem.objects.filter(
            application__project=project,
            application__dropped_at=now,  # just-dropped applications
            status=ActionItemStatus.PENDING,
        ).update(status=ActionItemStatus.CANCELLED)

        # 5. explicit phase recompute [I-06]
        new_phase = compute_project_phase(project)
        if project.phase != new_phase:
            Project.objects.filter(pk=project.pk).update(phase=new_phase)

    return application
