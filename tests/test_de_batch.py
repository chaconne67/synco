import json

import pytest

from data_extraction.models import GeminiBatchItem, GeminiBatchJob
from data_extraction.services.batch.ingest import ingest_job_results
from data_extraction.services.batch.ingest import _load_extracted_json
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
    """When batch ingest fails to parse JSON, a placeholder Candidate+Resume is created."""
    from candidates.models import Candidate, Resume

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
    """When batch response contains an error, a placeholder Candidate+Resume is created."""
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

    # Placeholder exists
    assert Resume.objects.filter(drive_file_id="drive_err_001").exists()
    resume = Resume.objects.get(drive_file_id="drive_err_001")
    assert resume.candidate is not None
    assert resume.processing_status == Resume.ProcessingStatus.FAILED
