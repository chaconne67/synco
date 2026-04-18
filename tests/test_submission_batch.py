import uuid

import pytest

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
