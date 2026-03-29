import pytest
import numpy as np
from unittest.mock import patch

from intelligence.services.task_detect import detect_task
from intelligence.services._references import TASK_REFS


def test_task_refs_has_waiting():
    assert "waiting" in TASK_REFS


@pytest.mark.django_db
def test_detect_task_creates_with_llm_title(user, contact):
    from contacts.models import Interaction

    interaction = Interaction.objects.create(
        fc=user,
        contact=contact,
        type="memo",
        summary="다음주에 다시 전화해서 견적서 보내기로 했다",
    )

    fake_embedding = [0.1] * 3072
    fake_refs = {
        "task": np.array([0.1] * 3072),
        "followup": np.array([0.05] * 3072),
        "promise": np.array([0.05] * 3072),
        "waiting": np.array([0.0] * 3072),
        "not_task": np.array([0.0] * 3072),
    }

    llm_result = {"title": "견적서 발송 팔로업", "due_date": "2026-04-07"}

    with patch(
        "intelligence.services.task_detect.get_task_vectors", return_value=fake_refs
    ):
        with patch(
            "intelligence.services.task_detect.call_llm_json", return_value=llm_result
        ):
            task = detect_task(interaction, embedding=fake_embedding)

    assert task is not None
    assert task.title == "견적서 발송 팔로업"
    assert task.description == interaction.summary
    assert task.status == "pending"
    assert str(task.due_date) == "2026-04-07"


@pytest.mark.django_db
def test_detect_task_waiting_status(user, contact):
    from contacts.models import Interaction

    interaction = Interaction.objects.create(
        fc=user,
        contact=contact,
        type="memo",
        summary="좋은 내용이지만 지금은 상황이 안 되고 나중에 연락하겠다",
    )

    fake_embedding = [0.1] * 3072
    fake_refs = {
        "task": np.array([0.0] * 3072),
        "followup": np.array([0.0] * 3072),
        "promise": np.array([0.0] * 3072),
        "waiting": np.array([0.1] * 3072),
        "not_task": np.array([0.0] * 3072),
    }

    llm_result = {"title": "재연락 대기", "due_date": None}

    with patch(
        "intelligence.services.task_detect.get_task_vectors", return_value=fake_refs
    ):
        with patch(
            "intelligence.services.task_detect.call_llm_json", return_value=llm_result
        ):
            task = detect_task(interaction, embedding=fake_embedding)

    assert task is not None
    assert task.status == "waiting"
    assert task.due_date is None


@pytest.mark.django_db
def test_detect_task_not_task_returns_none(user, contact):
    from contacts.models import Interaction

    interaction = Interaction.objects.create(
        fc=user,
        contact=contact,
        type="memo",
        summary="일반적인 안부 통화",
    )

    fake_embedding = [0.1] * 3072
    fake_refs = {
        "task": np.array([0.0] * 3072),
        "followup": np.array([0.0] * 3072),
        "promise": np.array([0.0] * 3072),
        "waiting": np.array([0.0] * 3072),
        "not_task": np.array([0.1] * 3072),
    }

    with patch(
        "intelligence.services.task_detect.get_task_vectors", return_value=fake_refs
    ):
        task = detect_task(interaction, embedding=fake_embedding)

    assert task is None
    interaction.refresh_from_db()
    assert interaction.task_checked is True
