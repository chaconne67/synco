import pytest
from contacts.models import Task


@pytest.mark.django_db
def test_task_has_status_field(user, contact):
    task = Task.objects.create(
        fc=user,
        contact=contact,
        title="팔로업 전화",
        status=Task.Status.PENDING,
    )
    assert task.status == "pending"


@pytest.mark.django_db
def test_task_has_description_field(user, contact):
    task = Task.objects.create(
        fc=user,
        contact=contact,
        title="팔로업 전화",
        description="원래 메모 내용이 여기에 들어갑니다",
    )
    assert task.description == "원래 메모 내용이 여기에 들어갑니다"


@pytest.mark.django_db
def test_task_status_choices(user, contact):
    for status_value in ["pending", "waiting", "done"]:
        task = Task.objects.create(
            fc=user,
            contact=contact,
            title=f"task_{status_value}",
            status=status_value,
        )
        assert task.status == status_value
