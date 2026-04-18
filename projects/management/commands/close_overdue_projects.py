"""마감일 경과한 OPEN 프로젝트를 자동으로 실패 종료 처리.

규칙:
- status=OPEN + deadline < today + hired Application 없음 → CLOSED + fail
- hired Application이 있는 프로젝트는 제외 (성공 signal이 우선)
- note에 자동 종료 기록 남김

사용:
    uv run python manage.py close_overdue_projects            # 실제 실행
    uv run python manage.py close_overdue_projects --dry-run  # 대상만 조회
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from projects.models import Project, ProjectStatus


class Command(BaseCommand):
    help = "마감일 경과한 OPEN 프로젝트를 실패로 자동 종료"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="실제 변경 없이 대상만 출력",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        today = timezone.now().date()
        now = timezone.now()

        candidates = (
            Project.objects.filter(
                status=ProjectStatus.OPEN,
                deadline__lt=today,
                applications__hired_at__isnull=True,
            )
            .exclude(applications__hired_at__isnull=False)
            .distinct()
            .select_related("organization", "client")
        )

        count = candidates.count()
        if count == 0:
            self.stdout.write("마감 경과 OPEN 프로젝트 없음.")
            return

        self.stdout.write(f"대상: {count}건")
        for p in candidates:
            self.stdout.write(
                f"  - [{p.organization.name}] {p.client.name} · {p.title} "
                f"(deadline={p.deadline}, pk={p.pk})"
            )

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("--dry-run: 변경 없음"))
            return

        # 실제 종료 처리 (signal 우회 — .update() 로 일괄)
        note_suffix = f"\n\n[AUTO-CLOSE {today.isoformat()}] 마감일 경과로 자동 종료 (실패)"
        for p in candidates:
            new_note = (p.note or "") + note_suffix
            Project.objects.filter(pk=p.pk).update(
                status=ProjectStatus.CLOSED,
                result="fail",
                closed_at=now,
                note=new_note,
            )
            # 활성 Application 모두 drop 처리
            p.applications.filter(
                dropped_at__isnull=True, hired_at__isnull=True
            ).update(
                dropped_at=now,
                drop_reason="other",
                drop_note="프로젝트 마감일 경과로 자동 종료",
            )

        self.stdout.write(self.style.SUCCESS(f"{count}건 종료 완료"))
