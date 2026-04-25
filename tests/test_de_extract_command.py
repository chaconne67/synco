import pytest

from candidates.models import Resume
from data_extraction.management.commands.extract import Command


@pytest.mark.django_db
def test_collect_work_items_applies_limit_after_existing_filter():
    """Limit should mean next N unprocessed groups, not first N listed files."""
    Resume.objects.create(file_name="processed.pdf", drive_file_id="processed")

    command = Command()
    command.force = False
    command.shuffle = False
    command.retry_failed = False
    command.failed_only = False

    work_items = command._collect_work_items(
        {
            "HR": [
                {
                    "name": "processed.pdf",
                    "id": "processed",
                    "mimeType": "application/pdf",
                    "size": "100",
                    "modifiedTime": "2026-04-01T00:00:00Z",
                },
                {
                    "name": "new-a.pdf",
                    "id": "new-a",
                    "mimeType": "application/pdf",
                    "size": "100",
                    "modifiedTime": "2026-04-01T00:00:00Z",
                },
                {
                    "name": "new-b.pdf",
                    "id": "new-b",
                    "mimeType": "application/pdf",
                    "size": "100",
                    "modifiedTime": "2026-04-01T00:00:00Z",
                },
            ]
        },
        limit=1,
    )

    assert work_items["skipped"] == 1
    assert len(work_items["new_groups"]) == 1
    assert work_items["new_groups"][0]["primary"]["file_id"] == "new-a"


@pytest.mark.django_db
def test_collect_work_items_retry_failed_includes_failed_existing_resume():
    Resume.objects.create(
        file_name="failed.doc",
        drive_file_id="failed",
        processing_status=Resume.ProcessingStatus.FAILED,
    )
    Resume.objects.create(
        file_name="done.docx",
        drive_file_id="done",
        processing_status=Resume.ProcessingStatus.STRUCTURED,
    )

    command = Command()
    command.force = False
    command.shuffle = False
    command.retry_failed = True
    command.failed_only = False

    work_items = command._collect_work_items(
        {
            "HR": [
                {
                    "name": "failed.doc",
                    "id": "failed",
                    "mimeType": "application/msword",
                    "size": "100",
                    "modifiedTime": "2026-04-01T00:00:00Z",
                },
                {
                    "name": "done.docx",
                    "id": "done",
                    "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "size": "100",
                    "modifiedTime": "2026-04-01T00:00:00Z",
                },
            ]
        },
        limit=0,
    )

    assert work_items["skipped"] == 1
    assert len(work_items["new_groups"]) == 1
    assert work_items["new_groups"][0]["primary"]["file_id"] == "failed"


@pytest.mark.django_db
def test_collect_work_items_failed_only_excludes_new_files():
    Resume.objects.create(
        file_name="failed.doc",
        drive_file_id="failed",
        processing_status=Resume.ProcessingStatus.FAILED,
    )

    command = Command()
    command.force = False
    command.shuffle = False
    command.retry_failed = False
    command.failed_only = True

    work_items = command._collect_work_items(
        {
            "HR": [
                {
                    "name": "failed.doc",
                    "id": "failed",
                    "mimeType": "application/msword",
                    "size": "100",
                    "modifiedTime": "2026-04-01T00:00:00Z",
                },
                {
                    "name": "new.doc",
                    "id": "new",
                    "mimeType": "application/msword",
                    "size": "100",
                    "modifiedTime": "2026-04-01T00:00:00Z",
                },
            ]
        },
        limit=0,
    )

    assert len(work_items["new_groups"]) == 1
    assert work_items["new_groups"][0]["primary"]["file_id"] == "failed"
