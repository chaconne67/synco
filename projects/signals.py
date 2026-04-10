# projects/signals.py
"""Event trigger signal handlers — create lightweight AutoAction records."""

from __future__ import annotations

from datetime import timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    ActionType,
    AutoAction,
    Contact,
    Interview,
    Project,
    ProjectStatus,
    Submission,
)


@receiver(post_save, sender=Project)
def on_project_created(sender, instance, created, **kwargs):
    """New project -> pending posting draft + candidate search actions."""
    if not created or instance.status != ProjectStatus.NEW:
        return
    _create_project_actions(instance)


def _create_project_actions(project):
    for action_type, title in [
        (ActionType.POSTING_DRAFT, f"{project.title} 공지 초안"),
        (ActionType.CANDIDATE_SEARCH, f"{project.title} 후보자 자동 서칭"),
    ]:
        # A3: Don't filter by status — any existing action blocks re-creation
        if AutoAction.objects.filter(
            project=project,
            action_type=action_type,
        ).exists():
            continue
        AutoAction.objects.create(
            project=project,
            trigger_event="project_created",
            action_type=action_type,
            title=title,
            data={"project_id": str(project.pk)},
        )


@receiver(post_save, sender=Contact)
def on_contact_result(sender, instance, **kwargs):
    """Contact with INTERESTED result -> pending submission draft action."""
    if instance.result != Contact.Result.INTERESTED:
        return
    candidate_id = str(instance.candidate_id)
    # A3: Don't filter by status
    if AutoAction.objects.filter(
        project=instance.project,
        action_type=ActionType.SUBMISSION_DRAFT,
        data__candidate_id=candidate_id,
    ).exists():
        return
    AutoAction.objects.create(
        project=instance.project,
        trigger_event="contact_interested",
        action_type=ActionType.SUBMISSION_DRAFT,
        title=f"{instance.candidate.name} 제출 서류 초안",
        data={"candidate_id": candidate_id},
    )


@receiver(post_save, sender=Submission)
def on_submission_submitted(sender, instance, **kwargs):
    """Submission status=SUBMITTED -> followup reminder with due_at +3 days."""
    if instance.status != Submission.Status.SUBMITTED:
        return
    submission_id = str(instance.pk)
    # A3: Don't filter by status
    if AutoAction.objects.filter(
        project=instance.project,
        action_type=ActionType.FOLLOWUP_REMINDER,
        data__submission_id=submission_id,
    ).exists():
        return
    due = timezone.now() + timedelta(days=3)
    AutoAction.objects.create(
        project=instance.project,
        trigger_event="submission_submitted",
        action_type=ActionType.FOLLOWUP_REMINDER,
        title=f"{instance.candidate.name} 팔로업 리마인더",
        data={"submission_id": submission_id},
        due_at=due,
    )


@receiver(post_save, sender=Interview)
def on_interview_passed(sender, instance, **kwargs):
    """Interview result=PASSED -> pending offer template action."""
    if instance.result != Interview.Result.PASSED:
        return
    submission_id = str(instance.submission_id)
    # A3: Don't filter by status
    if AutoAction.objects.filter(
        project=instance.submission.project,
        action_type=ActionType.OFFER_TEMPLATE,
        data__submission_id=submission_id,
    ).exists():
        return
    AutoAction.objects.create(
        project=instance.submission.project,
        trigger_event="interview_passed",
        action_type=ActionType.OFFER_TEMPLATE,
        title=f"{instance.submission.candidate.name} 오퍼 템플릿",
        data={"submission_id": submission_id},
    )
