"""DB constraint tests: CheckConstraint + UniqueConstraint verification."""

import pytest
from django.db import IntegrityError
from django.utils import timezone

from projects.models import (
    Application,
    Project,
    ProjectResult,
    ProjectStatus,
)

pytestmark = pytest.mark.django_db


class TestUniqueApplicationPerProjectCandidate:
    def test_duplicate_raises_integrity_error(self, application, user):
        """Same project+candidate twice -> IntegrityError."""
        # First application already exists via fixture
        with pytest.raises(IntegrityError):
            Application.objects.create(
                project=application.project,
                candidate=application.candidate,
                created_by=user,
            )


class TestUniqueHiredPerProject:
    def test_second_hired_raises_integrity_error(self, application, second_application):
        """Two hired applications in same project -> IntegrityError."""
        now = timezone.now()
        application.hired_at = now
        application.save(update_fields=["hired_at"])

        second_application.hired_at = now
        with pytest.raises(IntegrityError):
            second_application.save(update_fields=["hired_at"])


class TestProjectCheckConstraints:
    def test_open_with_closed_at_raises(self, project):
        """open status + closed_at set -> constraint violation."""
        with pytest.raises(IntegrityError):
            Project.objects.filter(pk=project.pk).update(
                status=ProjectStatus.OPEN,
                closed_at=timezone.now(),
            )

    def test_open_with_result_raises(self, project):
        """open status + result set -> constraint violation."""
        with pytest.raises(IntegrityError):
            Project.objects.filter(pk=project.pk).update(
                status=ProjectStatus.OPEN,
                result=ProjectResult.SUCCESS,
            )

    def test_result_without_closed_raises(self, project):
        """result set + status=open -> constraint violation."""
        with pytest.raises(IntegrityError):
            Project.objects.filter(pk=project.pk).update(
                result=ProjectResult.FAIL,
                status=ProjectStatus.OPEN,
            )


@pytest.mark.django_db(transaction=True)
class TestHireTransaction:
    def test_hire_uses_select_for_update(self, application):
        """hire() with transaction=True to verify select_for_update path."""
        from projects.services.application_lifecycle import hire

        hire(application, None)
        application.refresh_from_db()
        assert application.hired_at is not None
        application.project.refresh_from_db()
        assert application.project.status == ProjectStatus.CLOSED
