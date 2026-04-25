"""extract 실행 결과를 JSON 스냅샷으로 dump.

리얼타임/배치 비교 테스트용. 시간 기준으로 대상 후보자를 식별합니다.

Usage:
    uv run python manage.py extraction_snapshot \\
        --since "2026-04-25T15:00:00" \\
        --output snapshots/realtime.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from candidates.models import Candidate, Career, Education
from data_extraction.models import ResumeExtractionState


class Command(BaseCommand):
    help = "Dump candidates created/updated since a timestamp as a JSON snapshot."

    def add_arguments(self, parser):
        parser.add_argument(
            "--since",
            type=str,
            required=True,
            help="ISO timestamp (예: 2026-04-25T15:00:00). 이후 갱신된 ResumeExtractionState 대상.",
        )
        parser.add_argument(
            "--output",
            type=str,
            required=True,
            help="JSON 출력 경로",
        )
        parser.add_argument(
            "--label",
            type=str,
            default="",
            help="snapshot label (예: realtime, batch). 메타데이터에 기록",
        )

    def handle(self, *args, **options):
        since_str = options["since"]
        try:
            since_dt = datetime.fromisoformat(since_str)
        except ValueError as exc:
            raise CommandError(f"Invalid --since: {exc}")
        if timezone.is_naive(since_dt):
            since_dt = timezone.make_aware(since_dt)

        states = (
            ResumeExtractionState.objects.filter(updated_at__gte=since_dt)
            .select_related("resume__candidate")
            .order_by("updated_at")
        )

        records = []
        seen_candidate_ids: set[str] = set()
        for state in states:
            resume = state.resume
            if resume is None:
                continue
            candidate = getattr(resume, "candidate", None)
            if candidate is None:
                # text-only/failed placeholder는 candidate가 없을 수 있음
                records.append(self._failed_record(resume, state))
                continue
            cid = str(candidate.id)
            if cid in seen_candidate_ids:
                continue
            seen_candidate_ids.add(cid)
            records.append(self._candidate_record(candidate, resume, state))

        payload = {
            "label": options.get("label") or "",
            "since": since_dt.isoformat(),
            "captured_at": timezone.now().isoformat(),
            "record_count": len(records),
            "records": records,
        }

        out = Path(options["output"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Snapshot saved: {out} ({len(records)} records)"
            )
        )

    def _candidate_record(
        self, candidate: Candidate, resume, state: ResumeExtractionState
    ) -> dict:
        careers = list(
            Career.objects.filter(candidate=candidate)
            .order_by("order")
            .values(
                "company",
                "company_en",
                "position",
                "department",
                "start_date",
                "end_date",
                "duration_text",
                "is_current",
                "duties",
                "achievements",
                "reason_left",
                "salary",
                "order",
            )
        )
        educations = list(
            Education.objects.filter(candidate=candidate)
            .order_by("-end_year")
            .values(
                "institution",
                "degree",
                "major",
                "gpa",
                "start_year",
                "end_year",
                "is_abroad",
                "status",
            )
        )
        return {
            "drive_file_id": resume.drive_file_id,
            "file_name": resume.file_name,
            "candidate_id": str(candidate.id),
            "name": candidate.name,
            "name_en": candidate.name_en,
            "birth_year": candidate.birth_year,
            "email": candidate.email,
            "phone": candidate.phone,
            "validation_status": candidate.validation_status,
            "confidence_score": candidate.confidence_score,
            "field_confidences": candidate.field_confidences or {},
            "total_experience_years": candidate.total_experience_years,
            "current_company": candidate.current_company,
            "current_position": candidate.current_position,
            "summary": candidate.summary,
            "core_competencies": candidate.core_competencies or [],
            "skills_count": len(candidate.skills or []),
            "skills": candidate.skills or [],
            "careers": careers,
            "career_count": len(careers),
            "educations": educations,
            "education_count": len(educations),
            "raw_extracted_json": candidate.raw_extracted_json or {},
            "integrity_flags": (candidate.raw_extracted_json or {}).get(
                "integrity_flags", []
            ),
            "resume": {
                "version": resume.version,
                "is_primary": resume.is_primary,
                "processing_status": resume.processing_status,
                "drive_folder": resume.drive_folder,
            },
            "extraction_state": {
                "status": state.status,
                "provider": state.provider,
                "pipeline": state.pipeline,
                "attempt_count": state.attempt_count,
                "last_error": state.last_error,
                "quality_routing": (state.metadata or {}).get(
                    "quality_routing", {}
                ),
                "extraction_started_at": state.extraction_started_at,
                "extraction_completed_at": state.extraction_completed_at,
            },
        }

    def _failed_record(self, resume, state: ResumeExtractionState) -> dict:
        return {
            "drive_file_id": resume.drive_file_id,
            "file_name": resume.file_name,
            "candidate_id": None,
            "validation_status": "no_candidate",
            "resume": {
                "processing_status": resume.processing_status,
                "drive_folder": resume.drive_folder,
            },
            "extraction_state": {
                "status": state.status,
                "provider": state.provider,
                "pipeline": state.pipeline,
                "last_error": state.last_error,
                "quality_routing": (state.metadata or {}).get(
                    "quality_routing", {}
                ),
            },
        }
