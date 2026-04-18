import uuid

import pytest
from django.urls import reverse

from projects.models import Submission


def test_submission_has_batch_id_field():
    field = Submission._meta.get_field("batch_id")
    assert field.null is True
    assert field.blank is True


@pytest.mark.django_db
def test_submissions_can_share_batch_id(submission_factory):
    """같은 batch_id로 여러 Submission 묶기 가능."""
    batch = uuid.uuid4()
    _s1 = submission_factory(batch_id=batch)
    _s2 = submission_factory(batch_id=batch)
    s3 = submission_factory(batch_id=None)  # 개별 제출

    batch_members = Submission.objects.filter(batch_id=batch)
    assert batch_members.count() == 2
    assert s3 not in batch_members


@pytest.mark.django_db
def test_submission_batch_create(client, user, project, submission_factory):
    """프로젝트 배치 제출 뷰 — 선택한 Application 들을 하나의 batch_id 로 묶어 Submission 생성."""
    from projects.models import Application, Submission, ActionItem, ActionItemStatus
    from projects.models import ActionType
    from candidates.models import Candidate

    # 2 Application을 client_submit 단계로 세팅
    # (이전 모든 gate action이 완료됨)
    c1 = Candidate.objects.create(name="배치1")
    c2 = Candidate.objects.create(name="배치2")
    a1 = Application.objects.create(project=project, candidate=c1, created_by=user)
    a2 = Application.objects.create(project=project, candidate=c2, created_by=user)

    # Gate actions 생성: reach_out → receive_resume → pre_meeting → submit_to_pm
    gates = ["reach_out", "receive_resume", "pre_meeting", "submit_to_pm"]
    for app in [a1, a2]:
        for gate_code in gates:
            at = ActionType.objects.get(code=gate_code)
            ActionItem.objects.create(
                application=app,
                action_type=at,
                status=ActionItemStatus.DONE,
                created_by=user,
            )

    client.force_login(user)
    resp = client.post(
        reverse("projects:submission_batch_create", args=[project.pk]),
        {"application_ids": [str(a1.pk), str(a2.pk)]},
    )
    assert resp.status_code in (200, 302)

    subs = Submission.objects.filter(action_item__application__project=project)
    assert subs.count() == 2
    batch_ids = {s.batch_id for s in subs}
    assert len(batch_ids) == 1  # 같은 batch_id 공유
    assert list(batch_ids)[0] is not None


@pytest.mark.django_db
def test_submission_batch_rejects_empty(client, user, project):
    """application_ids 비어있으면 400."""
    client.force_login(user)
    resp = client.post(
        reverse("projects:submission_batch_create", args=[project.pk]),
        {},  # no application_ids
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_submission_batch_rejects_wrong_stage(client, user, project):
    """제출 준비 단계 이전의 Application 은 batch 에 끼워 넣어도 거절되어야 함."""
    from candidates.models import Candidate
    from projects.models import Application

    client.force_login(user)
    # New application — no action items yet → current_stage = "contact"
    c = Candidate.objects.create(name="너무이른후보")
    app = Application.objects.create(project=project, candidate=c, created_by=user)

    resp = client.post(
        reverse("projects:submission_batch_create", args=[project.pk]),
        {"application_ids": [str(app.pk)]},
    )
    # View must reject — "No applications ready for client submission"
    assert resp.status_code == 400
