"""Step B8 — Step1+2+3 결과를 통합해 save_pipeline_result로 DB에 저장.

force 정책: save_pipeline_result는 email/phone 매칭으로 기존 후보자에 합치고,
같은 drive_file_id Resume는 update_or_create로 덮음.

Usage:
    uv run python manage.py verify_save \\
        --step1-dir snapshots/step_b4_llm_step1 \\
        --step2-dir snapshots/step_b5_llm_step2 \\
        --download-input snapshots/step_b1_download.json \\
        --output snapshots/step_b8_save_summary.json
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Step B8: assemble Step1+2+3 results and save to DB."

    def add_arguments(self, parser):
        parser.add_argument("--step1-dir", type=str, required=True)
        parser.add_argument("--step2-dir", type=str, required=True)
        parser.add_argument("--download-input", type=str, required=True)
        parser.add_argument("--output", type=str, required=True)

    def handle(self, *args, **options):
        from candidates.models import Candidate, Career, Education, Resume
        from data_extraction.services.extraction.integrity import (
            _carry_forward_career_fields,
            _carry_forward_education_fields,
            _is_current_end_date_flag,
            _normalize_company,
            check_campus_match,
            check_career_education_overlap,
            check_education_gaps,
            check_period_overlaps,
            normalize_skills,
        )
        from data_extraction.services.extraction.validators import (
            validate_step2,
            validation_issues_to_flags,
        )
        from data_extraction.services.filters import apply_regex_field_filters
        from data_extraction.services.pipeline import (
            _build_integrity_diagnosis,
            apply_cross_version_comparison,
            attach_quality_routing,
        )
        from data_extraction.services.save import save_pipeline_result
        from data_extraction.services.validation import compute_field_confidences
        from candidates.models import Category
        from candidates.services.candidate_identity import (
            build_candidate_comparison_context,
        )

        step1_dir = Path(options["step1_dir"])
        step2_dir = Path(options["step2_dir"])

        # download metadata for primary_file shape
        download_data = json.loads(Path(options["download_input"]).read_text(encoding="utf-8"))
        primary_by_id = {}
        for r in download_data.get("results", []):
            if not r.get("ok"):
                continue
            primary_by_id[r["file_id"]] = {
                "file_name": r["file_name"],
                "file_id": r["file_id"],
                "mime_type": r["mime_type"],
                "file_size": r["actual_size"],
                "modified_time": "",
            }

        before = {
            "candidates": Candidate.objects.count(),
            "resumes": Resume.objects.count(),
            "careers": Career.objects.count(),
            "educations": Education.objects.count(),
        }
        self.stdout.write(f"Before save: {before}")
        self.stdout.write("")

        files = sorted(step1_dir.glob("*.json"))
        results = []
        succeeded = 0
        failed = 0
        new_count = 0
        update_count = 0

        for idx, s1_file in enumerate(files, start=1):
            fid = s1_file.stem
            s1 = json.loads(s1_file.read_text(encoding="utf-8"))
            s2_file = step2_dir / f"{fid}.json"
            if not s2_file.exists():
                self.stdout.write(self.style.WARNING(f"  [{idx}] Step2 missing: {fid}"))
                failed += 1
                continue
            s2 = json.loads(s2_file.read_text(encoding="utf-8"))

            target = s1.get("target") or s1
            primary_file = primary_by_id.get(fid)
            if not primary_file:
                self.stdout.write(self.style.WARNING(f"  [{idx}] primary_file missing: {fid}"))
                failed += 1
                continue

            raw_data = s1.get("result") or {}
            career_result = (s2.get("step2") or {}).get("career_result") or {}
            edu_result = (s2.get("step2") or {}).get("edu_result") or {}

            normalized_careers = (career_result.get("careers") or []) or (
                [career_result["career"]] if career_result.get("career") else []
            )
            normalized_educations = edu_result.get("educations") or []

            careers_raw = raw_data.get("careers") or []
            educations_raw = raw_data.get("educations") or []

            career_validation_issues = validate_step2(
                {
                    "careers": normalized_careers,
                    "flags": career_result.get("flags") or [],
                },
                raw_careers=careers_raw,
            )
            _carry_forward_career_fields(normalized_careers, careers_raw)
            _carry_forward_education_fields(normalized_educations, educations_raw)

            normalized_careers.sort(key=lambda c: c.get("start_date") or "", reverse=True)
            for i, c in enumerate(normalized_careers):
                c["order"] = i

            all_flags = [
                *(career_result.get("flags") or []),
                *(edu_result.get("flags") or []),
                *validation_issues_to_flags(
                    career_validation_issues,
                    stage="step2",
                    default_severity="RED",
                ),
            ]
            autocorrected = set()
            for c in normalized_careers:
                if c.get("end_date") and c.get("is_current"):
                    c["is_current"] = False
                    autocorrected.add(_normalize_company(c.get("company") or ""))
            if autocorrected:
                all_flags = [
                    f for f in all_flags
                    if not _is_current_end_date_flag(f, autocorrected)
                ]

            skills = normalize_skills(raw_data)
            all_flags.extend(check_period_overlaps(normalized_careers))
            all_flags.extend(
                check_career_education_overlap(normalized_careers, normalized_educations)
            )
            all_flags.extend(check_education_gaps(normalized_educations))
            all_flags.extend(check_campus_match(normalized_educations))

            extracted = apply_regex_field_filters({
                "name": raw_data.get("name"),
                "name_en": raw_data.get("name_en"),
                "birth_year": raw_data.get("birth_year"),
                "gender": raw_data.get("gender"),
                "email": raw_data.get("email"),
                "phone": raw_data.get("phone"),
                "address": raw_data.get("address"),
                "current_company": raw_data.get("current_company") or "",
                "current_position": raw_data.get("current_position") or "",
                "total_experience_years": raw_data.get("total_experience_years"),
                "resume_reference_date": raw_data.get("resume_reference_date"),
                "core_competencies": raw_data.get("core_competencies") or [],
                "summary": raw_data.get("summary") or "",
                "careers": normalized_careers,
                "educations": normalized_educations,
                "certifications": skills.get("certifications") or [],
                "language_skills": skills.get("language_skills") or [],
                "skills": raw_data.get("skills") or [],
                "personal_etc": raw_data.get("personal_etc") or [],
                "education_etc": raw_data.get("education_etc") or [],
                "career_etc": raw_data.get("career_etc") or [],
                "skills_etc": raw_data.get("skills_etc") or [],
                "integrity_flags": all_flags,
                "pipeline_meta": {
                    "step1_items": len(careers_raw) + len(educations_raw),
                    "retries": 0,
                    "step2_career_validation_issues": career_validation_issues,
                    "step1_careers_raw": careers_raw,
                    "step1_educations_raw": educations_raw,
                    "verify_pipeline": "test40",
                },
            })
            field_scores, _ = compute_field_confidences(extracted, {})
            extracted["field_confidences"] = field_scores

            raw_text = Path(target["text_path"]).read_text(encoding="utf-8")

            pipeline_result = {
                "extracted": extracted,
                "diagnosis": _build_integrity_diagnosis(all_flags, field_scores),
                "attempts": 1,
                "retry_action": (
                    "human_review"
                    if any(f.get("severity") == "RED" for f in all_flags)
                    else "none"
                ),
                "raw_text_used": raw_text,
                "integrity_flags": all_flags,
            }
            pipeline_result = attach_quality_routing(pipeline_result)

            comparison_context = build_candidate_comparison_context(extracted)
            if comparison_context and comparison_context.previous_data:
                pipeline_result = apply_cross_version_comparison(
                    pipeline_result,
                    comparison_context.previous_data,
                )
            existing_match = bool(comparison_context and comparison_context.candidate)

            category, _ = Category.objects.get_or_create(
                name=target["category"],
                defaults={"name_ko": ""},
            )
            try:
                candidate = save_pipeline_result(
                    pipeline_result=pipeline_result,
                    raw_text=raw_text,
                    category=category,
                    primary_file=primary_file,
                    other_files=[],
                    existing_ids=set(),
                    comparison_context=comparison_context,
                    filename_meta={"name": extracted.get("name")},
                )
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  [{idx}] save failed: {exc}"))
                failed += 1
                results.append({"file_id": fid, "ok": False, "error": str(exc)})
                continue

            if candidate is None:
                self.stdout.write(self.style.WARNING(f"  [{idx}] save returned None"))
                failed += 1
                continue

            succeeded += 1
            if existing_match:
                update_count += 1
            else:
                new_count += 1

            ds = pipeline_result["diagnosis"]
            self.stdout.write(
                f"  [{idx:>2}/{len(files)}] [{target['category']:<12}] "
                f"{'UPDATE' if existing_match else 'NEW   '} "
                f"verdict={ds.get('verdict'):<6} score={ds.get('overall_score'):.2f} "
                f"flags={len(all_flags)} careers={len(normalized_careers)} edus={len(normalized_educations)}  "
                f"→ {candidate.name} ({candidate.id})"
            )
            results.append({
                "file_id": fid,
                "candidate_id": str(candidate.id),
                "candidate_name": candidate.name,
                "is_update": existing_match,
                "diagnosis": ds,
                "flags_count": len(all_flags),
                "careers_count": len(normalized_careers),
                "educations_count": len(normalized_educations),
                "ok": True,
            })

        after = {
            "candidates": Candidate.objects.count(),
            "resumes": Resume.objects.count(),
            "careers": Career.objects.count(),
            "educations": Education.objects.count(),
        }
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Summary ==="))
        self.stdout.write(f"  files: {len(files)}")
        self.stdout.write(f"  succeeded: {succeeded}")
        self.stdout.write(f"  failed: {failed}")
        self.stdout.write(f"  new candidate: {new_count}")
        self.stdout.write(f"  update existing: {update_count}")
        self.stdout.write(f"  Before: {before}")
        self.stdout.write(f"  After:  {after}")
        delta = {k: after[k] - before[k] for k in before}
        self.stdout.write(f"  Delta:  {delta}")

        Path(options["output"]).parent.mkdir(parents=True, exist_ok=True)
        Path(options["output"]).write_text(
            json.dumps({
                "summary": {
                    "files": len(files),
                    "succeeded": succeeded,
                    "failed": failed,
                    "new": new_count,
                    "update": update_count,
                    "before": before,
                    "after": after,
                    "delta": delta,
                },
                "results": results,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.stdout.write("")
        self.stdout.write(f"Saved: {options['output']}")
