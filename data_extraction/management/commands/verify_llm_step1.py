"""Step B4 — 단일 후보자 텍스트로 Step 1 LLM 호출 검증.

토큰/시간 측정 + 결과 JSON 검증 + source_section 라벨링 확인.

Usage:
    uv run python manage.py verify_llm_step1 \\
        --input snapshots/step_b3_quality.json \\
        --file-id <drive_file_id> \\
        --output snapshots/step_b4_llm_step1_<label>.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Step B4: invoke LLM Step 1 on a single resume and report metrics."

    def add_arguments(self, parser):
        parser.add_argument("--input", type=str, required=True)
        parser.add_argument(
            "--file-id",
            type=str,
            required=True,
            help="snapshots/step_b3_quality.json 안의 drive_file_id",
        )
        parser.add_argument("--output", type=str, required=True)

    def handle(self, *args, **options):
        from data_extraction.services.extraction import telemetry
        from data_extraction.services.extraction.integrity import extract_raw_data

        in_path = Path(options["input"])
        spec = json.loads(in_path.read_text(encoding="utf-8"))
        target = next(
            (r for r in spec.get("results", []) if r["file_id"] == options["file_id"]),
            None,
        )
        if target is None:
            raise CommandError(
                f"file_id {options['file_id']} not in {in_path}"
            )

        text = Path(target["text_path"]).read_text(encoding="utf-8")
        self.stdout.write(
            f"Target: {target['category']} / {target['file_name']}"
        )
        self.stdout.write(
            f"  text_path: {target['text_path']}"
        )
        self.stdout.write(
            f"  preprocessed length: {target['preprocessed_length']:,}자"
        )
        self.stdout.write("")
        self.stdout.write("Calling Step 1 (Gemini 3.1 Flash Lite)...")
        self.stdout.write("")

        telemetry.reset()
        t0 = time.time()
        try:
            extracted = extract_raw_data(text, file_name=target["file_name"])
        except Exception as exc:
            elapsed = time.time() - t0
            tokens = telemetry.snapshot()
            self.stdout.write(self.style.ERROR(f"Extraction raised: {exc}"))
            payload = {
                "target": target,
                "elapsed_seconds": round(elapsed, 2),
                "token_usage": tokens,
                "result": None,
                "error": f"{type(exc).__name__}: {exc}",
            }
            self._save(options["output"], payload)
            return
        elapsed = time.time() - t0
        tokens = telemetry.snapshot()

        if extracted is None:
            self.stdout.write(self.style.ERROR("Extraction returned None (3 retries failed)"))
            payload = {
                "target": target,
                "elapsed_seconds": round(elapsed, 2),
                "token_usage": tokens,
                "result": None,
                "error": "extract_raw_data returned None",
            }
            self._save(options["output"], payload)
            return

        # ---- Print structured summary ----
        self.stdout.write(
            self.style.SUCCESS(
                f"Extraction done in {elapsed:.1f}s, "
                f"{tokens['calls']} calls, "
                f"in={tokens['input_tokens']:,}, out={tokens['output_tokens']:,}"
            )
        )
        self.stdout.write("")

        self.stdout.write("=== Top-level fields ===")
        for k in (
            "name", "name_en", "birth_year", "gender", "email", "phone",
            "current_company", "current_position", "total_experience_years",
            "total_experience_text", "resume_reference_date",
        ):
            self.stdout.write(f"  {k}: {extracted.get(k)!r}")

        careers = extracted.get("careers") or []
        educations = extracted.get("educations") or []
        certs = extracted.get("certifications") or []
        skills = extracted.get("skills") or []

        self.stdout.write("")
        self.stdout.write(f"=== careers: {len(careers)}건 ===")
        for i, c in enumerate(careers):
            self.stdout.write(
                f"  [{i}] {c.get('company')!r} / {c.get('position')!r} "
                f"/ {c.get('start_date')!r}~{c.get('end_date')!r} "
                f"/ source_section={c.get('source_section')!r}"
            )

        self.stdout.write("")
        self.stdout.write(f"=== educations: {len(educations)}건 ===")
        for i, e in enumerate(educations):
            self.stdout.write(
                f"  [{i}] {e.get('institution')!r} / {e.get('degree')!r} "
                f"/ {e.get('major')!r} / {e.get('start_year')}-{e.get('end_year')} "
                f"/ status={e.get('status')!r}"
            )

        self.stdout.write("")
        self.stdout.write(f"=== certifications: {len(certs)}건 ===")
        for c in certs[:10]:
            self.stdout.write(f"  - {c.get('name')!r} ({c.get('issuer')!r}, {c.get('acquired_date')!r})")

        self.stdout.write("")
        self.stdout.write(f"=== skills: {len(skills)}건 ===")
        for s in skills[:15]:
            self.stdout.write(f"  - {s.get('name')!r} {('— ' + s.get('description')) if s.get('description') else ''}")

        # source_section diversity
        ss_set = sorted({c.get("source_section") or "" for c in careers if c.get("source_section")})
        self.stdout.write("")
        self.stdout.write(f"=== source_section 분포 ({len(ss_set)}종) ===")
        for ss in ss_set:
            cnt = sum(1 for c in careers if c.get("source_section") == ss)
            self.stdout.write(f"  - {ss!r}: {cnt}건")

        payload = {
            "target": target,
            "elapsed_seconds": round(elapsed, 2),
            "token_usage": tokens,
            "result": extracted,
        }
        self._save(options["output"], payload)

    def _save(self, output_path: str, payload: dict):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.stdout.write("")
        self.stdout.write(f"Saved: {out}")
