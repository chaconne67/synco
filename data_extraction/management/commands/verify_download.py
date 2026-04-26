"""Step B1 — 선정된 파일들을 순차 다운로드하고 메트릭 수집.

다운로드된 바이너리는 settings.RESUME_CACHE_ROOT 공용 캐시에 보관되어
운영 추출(extract.py·batch/prepare.py)과 동일한 경로를 공유합니다.
같은 file_id는 한 번만 Drive에서 받고, 재실행 시 캐시 hit (속도/대역폭 절약).

Usage:
    uv run python manage.py verify_download \\
        --input snapshots/test40_ids.json \\
        --output snapshots/step_b1_download.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand

from data_extraction.services.drive import download_to_cache, get_drive_service


class Command(BaseCommand):
    help = "Step B1: download selected files sequentially and report metrics."

    def add_arguments(self, parser):
        parser.add_argument("--input", type=str, required=True)
        parser.add_argument("--output", type=str, required=True)

    def handle(self, *args, **options):
        in_path = Path(options["input"])
        out_path = Path(options["output"])
        out_path.parent.mkdir(parents=True, exist_ok=True)

        spec = json.loads(in_path.read_text(encoding="utf-8"))
        files = spec.get("files", [])

        service = get_drive_service()

        results = []
        succeeded = 0
        failed = 0
        size_mismatch = 0
        total_bytes = 0
        total_seconds = 0.0
        cache_hits = 0

        self.stdout.write(f"Downloading {len(files)} files to RESUME_CACHE_ROOT")
        self.stdout.write("(cached files are reused — only new file_ids hit Drive)")
        self.stdout.write("")

        for idx, f in enumerate(files, start=1):
            t0 = time.time()
            error = ""
            actual_size = 0
            ok = False
            cached = False
            dest: Path | None = None
            try:
                from data_extraction.services.drive import get_resume_cache_path

                planned = get_resume_cache_path(f["file_id"], f["file_name"])
                cached = planned.exists() and planned.stat().st_size > 0

                dest = download_to_cache(service, f["file_id"], f["file_name"])
                actual_size = dest.stat().st_size
                ok = True
                succeeded += 1
                if cached:
                    cache_hits += 1
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                failed += 1
            elapsed = time.time() - t0
            total_seconds += elapsed

            expected = f.get("file_size", 0) or 0
            mismatch = ok and expected and actual_size != expected
            if mismatch:
                size_mismatch += 1
            if ok:
                total_bytes += actual_size

            tag = "HIT" if cached else ("OK " if ok else "FAIL")
            line = (
                f"  [{idx:>2}/{len(files)}] [{f['category']:<12}] "
                f"{tag} "
                f"{actual_size:>8d}B  {elapsed:>5.2f}s  "
                f"{f['file_name'][:50]}"
            )
            if mismatch:
                line += f"  ⚠ size mismatch (expected {expected})"
            if not ok:
                line += f"  ← {error}"
            self.stdout.write(line)

            results.append(
                {
                    "category": f["category"],
                    "file_id": f["file_id"],
                    "file_name": f["file_name"],
                    "mime_type": f["mime_type"],
                    "expected_size": expected,
                    "actual_size": actual_size,
                    "elapsed_seconds": round(elapsed, 3),
                    "saved_path": str(dest) if ok and dest else "",
                    "cache_hit": cached,
                    "ok": ok,
                    "size_mismatch": mismatch,
                    "error": error,
                }
            )

        avg_throughput_kbps = (
            (total_bytes / 1024) / total_seconds if total_seconds > 0 else 0
        )

        from django.conf import settings

        payload = {
            "input": str(in_path),
            "cache_root": str(settings.RESUME_CACHE_ROOT),
            "summary": {
                "count": len(files),
                "succeeded": succeeded,
                "failed": failed,
                "cache_hits": cache_hits,
                "size_mismatch": size_mismatch,
                "total_bytes": total_bytes,
                "total_seconds": round(total_seconds, 2),
                "avg_seconds_per_file": (
                    round(total_seconds / len(files), 3) if files else 0
                ),
                "avg_throughput_kbps": round(avg_throughput_kbps, 1),
            },
            "results": results,
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Summary ==="))
        for k, v in payload["summary"].items():
            self.stdout.write(f"  {k}: {v}")
        self.stdout.write("")
        self.stdout.write(f"Saved: {out_path}")
