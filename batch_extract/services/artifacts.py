from __future__ import annotations

from pathlib import Path


ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / ".batch_extract"


def ensure_job_dirs(job_id: str) -> Path:
    job_root = ARTIFACT_ROOT / job_id
    (job_root / "inputs").mkdir(parents=True, exist_ok=True)
    (job_root / "results").mkdir(parents=True, exist_ok=True)
    return job_root


def request_file_path(job_id: str) -> Path:
    return ensure_job_dirs(job_id) / "requests.jsonl"


def result_file_path(job_id: str) -> Path:
    return ensure_job_dirs(job_id) / "results" / "responses.jsonl"


def raw_text_path(job_id: str, request_key: str) -> Path:
    return ensure_job_dirs(job_id) / "inputs" / f"{request_key}.txt"
