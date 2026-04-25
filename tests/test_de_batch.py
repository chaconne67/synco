import json
from io import StringIO

import pytest
from django.core.management import call_command

from candidates.models import Resume
from data_extraction.models import GeminiBatchItem, GeminiBatchJob
from data_extraction.services.batch.integrity_chain import (
    ingest_integrity_job_results,
    prepare_next_integrity_job,
)
from data_extraction.services.batch.ingest import ingest_job_results
from data_extraction.services.batch.ingest import _load_extracted_json
from data_extraction.services.batch.prepare import prepare_drive_job
from data_extraction.services.batch.request_builder import (
    build_request_line,
    extract_text_response,
)


def test_build_request_line_contains_key_and_request():
    line = build_request_line(
        request_key="drive_001",
        resume_text="홍길동\n경력 10년",
        file_reference_date="2026-04-04",
    )
    parsed = json.loads(line)

    assert parsed["key"] == "drive_001"
    assert parsed["request"]["generation_config"]["max_output_tokens"] == 4000
    assert parsed["request"]["system_instruction"]["parts"][0]["text"]
    assert "홍길동" in parsed["request"]["contents"][0]["parts"][0]["text"]


def test_extract_text_response_reads_first_candidate_parts():
    parsed_line = {
        "key": "drive_001",
        "response": {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": '{"name": "홍길동"}'},
                        ]
                    }
                }
            ]
        },
    }

    assert extract_text_response(parsed_line) == '{"name": "홍길동"}'


def test_load_extracted_json_handles_markdown_block():
    response_text = '```json\n{"name": "홍길동"}\n```'

    assert _load_extracted_json(response_text) == {"name": "홍길동"}


def _patch_prepare_io(monkeypatch, tmp_path, files):
    monkeypatch.setattr(
        "data_extraction.services.batch.prepare.get_drive_service", lambda: object()
    )
    monkeypatch.setattr(
        "data_extraction.services.batch.prepare.discover_folders",
        lambda service, parent_id: [{"name": "HR", "id": "folder_1"}],
    )
    monkeypatch.setattr(
        "data_extraction.services.batch.prepare.list_files_in_folder",
        lambda service, folder_id: files,
    )
    monkeypatch.setattr(
        "data_extraction.services.batch.prepare.group_by_person",
        lambda normalized: [
            {"primary": file_info, "others": [], "parsed": {"name": file_info["file_name"]}}
            for file_info in normalized
        ],
    )
    monkeypatch.setattr(
        "data_extraction.services.batch.prepare.download_file",
        lambda service, file_id, dest_path: None,
    )
    monkeypatch.setattr(
        "data_extraction.services.batch.prepare.extract_text",
        lambda path: "홍길동 경력 10년",
    )
    monkeypatch.setattr(
        "data_extraction.services.batch.prepare.request_file_path",
        lambda job_id: tmp_path / f"{job_id}.jsonl",
    )
    monkeypatch.setattr(
        "data_extraction.services.batch.prepare.raw_text_path",
        lambda job_id, request_key: tmp_path / f"{job_id}-{request_key}.txt",
    )


@pytest.mark.django_db
def test_prepare_drive_job_applies_limit_after_existing_skip(tmp_path, monkeypatch):
    files = [
        {"id": "drive_001", "name": "existing.docx", "mimeType": "docx", "size": "1"},
        {"id": "drive_002", "name": "next.docx", "mimeType": "docx", "size": "1"},
        {"id": "drive_003", "name": "later.docx", "mimeType": "docx", "size": "1"},
    ]
    _patch_prepare_io(monkeypatch, tmp_path, files)
    Resume.objects.create(
        drive_file_id="drive_001",
        file_name="existing.docx",
        processing_status=Resume.ProcessingStatus.STRUCTURED,
    )
    job = GeminiBatchJob.objects.create(display_name="prepare-limit")

    prepare_drive_job(job=job, limit=1, workers=1)

    assert list(job.items.values_list("drive_file_id", flat=True)) == ["drive_002"]
    job.refresh_from_db()
    assert job.total_requests == 1
    assert job.metadata["skipped_existing"] == 1


@pytest.mark.django_db
def test_prepare_drive_job_skips_active_batch_items(tmp_path, monkeypatch):
    files = [
        {"id": "drive_001", "name": "already-prepared.docx", "mimeType": "docx"},
        {"id": "drive_002", "name": "new.docx", "mimeType": "docx"},
    ]
    _patch_prepare_io(monkeypatch, tmp_path, files)
    old_job = GeminiBatchJob.objects.create(display_name="old")
    GeminiBatchItem.objects.create(
        job=old_job,
        request_key="drive_001",
        drive_file_id="drive_001",
        file_name="already-prepared.docx",
        category_name="HR",
        status=GeminiBatchItem.Status.PREPARED,
    )
    job = GeminiBatchJob.objects.create(display_name="prepare-active-skip")

    prepare_drive_job(job=job, workers=1)

    assert list(job.items.values_list("drive_file_id", flat=True)) == ["drive_002"]
    job.refresh_from_db()
    assert job.metadata["skipped_active_batch"] == 1


@pytest.mark.django_db
def test_prepare_drive_job_failed_only_requeues_failed_resume(tmp_path, monkeypatch):
    files = [
        {"id": "drive_001", "name": "failed.docx", "mimeType": "docx"},
        {"id": "drive_002", "name": "new.docx", "mimeType": "docx"},
    ]
    _patch_prepare_io(monkeypatch, tmp_path, files)
    Resume.objects.create(
        drive_file_id="drive_001",
        file_name="failed.docx",
        processing_status=Resume.ProcessingStatus.FAILED,
    )
    job = GeminiBatchJob.objects.create(display_name="prepare-failed-only")

    prepare_drive_job(job=job, failed_only=True, workers=1)

    assert list(job.items.values_list("drive_file_id", flat=True)) == ["drive_001"]
    job.refresh_from_db()
    assert job.metadata["failed_only"] is True


@pytest.mark.django_db
def test_prepare_drive_job_birth_year_filter_skips_before_request(
    tmp_path, monkeypatch
):
    files = [
        {"id": "drive_001", "name": "old.docx", "mimeType": "docx"},
        {"id": "drive_002", "name": "young.docx", "mimeType": "docx"},
    ]
    _patch_prepare_io(monkeypatch, tmp_path, files)
    monkeypatch.setattr(
        "data_extraction.services.batch.prepare.extract_text",
        lambda path: (
            "생년월일: 1984.01.01"
            if "old.docx" in str(path)
            else "생년월일: 1986.01.01"
        ),
    )
    job = GeminiBatchJob.objects.create(display_name="prepare-birth-filter")

    prepare_drive_job(job=job, birth_year_filter=True, birth_year_value=1985, workers=1)

    assert list(job.items.values_list("drive_file_id", flat=True)) == ["drive_002"]
    job.refresh_from_db()
    assert job.total_requests == 1
    assert job.metadata["skipped_birth_year_filter"] == 1


@pytest.mark.django_db
def test_batch_prepare_command_does_not_return_model_to_stdout(monkeypatch):
    def fake_prepare_drive_job(*, job, **kwargs):
        job.status = GeminiBatchJob.Status.PREPARED
        job.request_file_path = "/tmp/requests.jsonl"
        job.total_requests = 0
        job.save()
        return job

    monkeypatch.setattr(
        "data_extraction.services.batch.prepare.prepare_drive_job",
        fake_prepare_drive_job,
    )

    out = StringIO()
    call_command(
        "extract",
        "--drive",
        "root",
        "--batch",
        "--step",
        "prepare",
        stdout=out,
    )

    assert "prepared" in out.getvalue()


@pytest.mark.django_db
def test_integrity_step1_ingest_stores_raw_data(tmp_path):
    job = GeminiBatchJob.objects.create(
        display_name="integrity-step1",
        status=GeminiBatchJob.Status.SUCCEEDED,
        result_file_path=str(tmp_path / "step1.jsonl"),
        metadata={"pipeline": "integrity", "stage": "step1"},
    )
    item = GeminiBatchItem.objects.create(
        job=job,
        request_key="drive_001",
        drive_file_id="drive_001",
        file_name="resume.docx",
        category_name="HR",
        raw_text_path=str(tmp_path / "raw.txt"),
        primary_file={"file_id": "drive_001", "file_name": "resume.docx"},
        metadata={"pipeline": "integrity", "stage": "step1"},
    )
    (tmp_path / "raw.txt").write_text("홍길동 경력", encoding="utf-8")
    result_line = {
        "key": "drive_001",
        "response": {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "name": "홍길동",
                                        "careers": [{"company": "A"}],
                                        "educations": [{"institution": "B"}],
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        ]
                    }
                }
            ]
        },
    }
    (tmp_path / "step1.jsonl").write_text(
        json.dumps(result_line, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    summary = ingest_integrity_job_results(job)

    assert summary == {"processed": 1, "ingested": 1, "failed": 0}
    item.refresh_from_db()
    assert item.status == GeminiBatchItem.Status.SUCCEEDED
    assert item.metadata["step1_raw_data"]["name"] == "홍길동"


@pytest.mark.django_db
def test_prepare_next_integrity_job_builds_step2_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "data_extraction.services.batch.integrity_chain.request_file_path",
        lambda job_id: tmp_path / f"{job_id}.jsonl",
    )
    parent = GeminiBatchJob.objects.create(
        display_name="integrity-step1",
        status=GeminiBatchJob.Status.INGESTED,
        metadata={"pipeline": "integrity", "stage": "step1"},
    )
    GeminiBatchItem.objects.create(
        job=parent,
        request_key="drive_001",
        drive_file_id="drive_001",
        file_name="resume.docx",
        category_name="HR",
        status=GeminiBatchItem.Status.SUCCEEDED,
        primary_file={"file_id": "drive_001", "file_name": "resume.docx"},
        metadata={
            "step1_raw_data": {
                "name": "홍길동",
                "careers": [{"company": "A"}],
                "educations": [{"institution": "B"}],
            }
        },
    )

    child = prepare_next_integrity_job(parent)

    assert child is not None
    assert child.metadata["stage"] == "step2"
    assert child.total_requests == 2
    assert set(child.items.values_list("request_key", flat=True)) == {
        "drive_001:career",
        "drive_001:education",
    }
    request_lines = (tmp_path / f"{child.id}.jsonl").read_text(encoding="utf-8")
    assert "경력 항목" in request_lines
    assert "학력 항목" in request_lines


@pytest.mark.django_db
def test_ingest_job_results_supports_parallel_workers(tmp_path, monkeypatch):
    job = GeminiBatchJob.objects.create(
        display_name="batch-job",
        status=GeminiBatchJob.Status.SUCCEEDED,
        result_file_path=str(tmp_path / "responses.jsonl"),
    )
    item = GeminiBatchItem.objects.create(
        job=job,
        request_key="drive_001",
        drive_file_id="drive_001",
        file_name="resume.doc",
        category_name="Accounting",
    )

    result_line = {
        "key": "drive_001",
        "response": {
            "candidates": [{"content": {"parts": [{"text": '{"name": "홍길동"}'}]}}]
        },
    }
    (tmp_path / "responses.jsonl").write_text(
        json.dumps(result_line, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    def fake_handle_result_payload(*, key_to_item, parsed):
        assert parsed["key"] == "drive_001"
        assert key_to_item["drive_001"].pk == item.pk
        return "ingested"

    monkeypatch.setattr(
        "data_extraction.services.batch.ingest._handle_result_payload",
        fake_handle_result_payload,
    )

    summary = ingest_job_results(job, workers=2)
    job.refresh_from_db()

    assert summary == {"processed": 1, "ingested": 1, "failed": 0}
    assert job.status == GeminiBatchJob.Status.INGESTED
    assert job.successful_requests == 1


@pytest.mark.django_db
def test_ingest_json_parse_failure_creates_placeholder(tmp_path, monkeypatch):
    """Unparseable LLM output with raw text creates a text-only review candidate."""
    from candidates.models import Resume

    # _handle_result_payload calls close_old_connections() which breaks test DB
    monkeypatch.setattr(
        "data_extraction.services.batch.ingest.close_old_connections", lambda: None
    )

    job = GeminiBatchJob.objects.create(
        display_name="batch-fail",
        status=GeminiBatchJob.Status.SUCCEEDED,
        result_file_path=str(tmp_path / "responses.jsonl"),
    )

    raw_text_file = tmp_path / "raw.txt"
    raw_text_file.write_text("original resume text", encoding="utf-8")

    item = GeminiBatchItem.objects.create(
        job=job,
        request_key="drive_fail_001",
        drive_file_id="drive_fail_001",
        file_name="broken.pdf",
        category_name="HR",
        status=GeminiBatchItem.Status.PREPARED,
        raw_text_path=str(raw_text_file),
        primary_file={
            "file_name": "broken.pdf",
            "file_id": "drive_fail_001",
            "mime_type": "application/pdf",
            "file_size": 500,
        },
        other_files=[],
        filename_meta={"name": "broken_name"},
    )

    # Completely unparseable response
    result_line = {
        "key": "drive_fail_001",
        "response": {
            "candidates": [
                {"content": {"parts": [{"text": "this is not json at all"}]}}
            ]
        },
    }
    (tmp_path / "responses.jsonl").write_text(
        json.dumps(result_line, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    summary = ingest_job_results(job, workers=1)

    assert summary["failed"] == 1
    item.refresh_from_db()
    assert item.status == GeminiBatchItem.Status.FAILED

    # Placeholder Candidate + Resume should exist
    assert Resume.objects.filter(drive_file_id="drive_fail_001").exists()
    resume = Resume.objects.get(drive_file_id="drive_fail_001")
    assert resume.candidate is not None
    assert resume.processing_status == Resume.ProcessingStatus.TEXT_ONLY
    assert resume.raw_text == "original resume text"


@pytest.mark.django_db
def test_ingest_error_response_creates_placeholder(tmp_path, monkeypatch):
    """Batch response errors are tracked without creating a Candidate."""
    from candidates.models import Candidate, Resume

    monkeypatch.setattr(
        "data_extraction.services.batch.ingest.close_old_connections", lambda: None
    )

    job = GeminiBatchJob.objects.create(
        display_name="batch-error",
        status=GeminiBatchJob.Status.SUCCEEDED,
        result_file_path=str(tmp_path / "responses.jsonl"),
    )

    item = GeminiBatchItem.objects.create(
        job=job,
        request_key="drive_err_001",
        drive_file_id="drive_err_001",
        file_name="error.pdf",
        category_name="Finance",
        status=GeminiBatchItem.Status.PREPARED,
        primary_file={
            "file_name": "error.pdf",
            "file_id": "drive_err_001",
            "mime_type": "application/pdf",
            "file_size": 300,
        },
        other_files=[],
        filename_meta={},
    )

    result_line = {
        "key": "drive_err_001",
        "error": {"code": 500, "message": "Internal server error"},
    }
    (tmp_path / "responses.jsonl").write_text(
        json.dumps(result_line, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    summary = ingest_job_results(job, workers=1)

    assert summary["failed"] == 1
    item.refresh_from_db()
    assert item.status == GeminiBatchItem.Status.FAILED

    assert Resume.objects.filter(drive_file_id="drive_err_001").exists()
    resume = Resume.objects.get(drive_file_id="drive_err_001")
    assert resume.candidate is None
    assert resume.processing_status == Resume.ProcessingStatus.FAILED
    assert Candidate.objects.count() == 0
