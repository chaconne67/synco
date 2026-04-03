from django.core.management.base import BaseCommand, CommandError

from candidates.models import Candidate
from candidates.services.discrepancy import scan_candidate_discrepancies


class Command(BaseCommand):
    help = "Run self-consistency discrepancy scan for candidates"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--all", action="store_true", help="Scan all candidates")
        group.add_argument("--candidate-id", type=str, help="Scan a single candidate UUID")
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limit candidate count when using --all (0=unlimited)",
        )

    def handle(self, *args, **options):
        candidate_id = options.get("candidate_id")
        limit = options.get("limit") or 0

        qs = Candidate.objects.prefetch_related("careers", "educations").order_by(
            "-updated_at"
        )
        if candidate_id:
            qs = qs.filter(pk=candidate_id)
            if not qs.exists():
                raise CommandError(f"Candidate not found: {candidate_id}")

        if limit:
            qs = qs[:limit]

        scanned = 0
        actionable = 0

        for candidate in qs:
            report = scan_candidate_discrepancies(candidate)
            scanned += 1
            if report.has_actionable_alerts:
                actionable += 1
            self.stdout.write(
                f"- {candidate.name}: score={report.integrity_score} alerts={report.total_alert_count}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Scanned {scanned} candidates. Actionable reports: {actionable}"
            )
        )
