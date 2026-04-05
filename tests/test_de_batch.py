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
            "candidates": [
                {"content": {"parts": [{"text": '{"name": "홍길동"}'}]}}
            ]
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
