"""Generate embeddings for all candidates missing them.

Usage:
    uv run python manage.py generate_embeddings
    uv run python manage.py generate_embeddings --force
"""

from django.core.management.base import BaseCommand

from candidates.models import Candidate, CandidateEmbedding
from candidates.services.embedding import generate_candidate_embedding


class Command(BaseCommand):
    help = "Generate embeddings for candidates"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Regenerate all embeddings (ignore text_hash cache)",
        )

    def handle(self, *args, **options):
        force = options.get("force")

        if force:
            candidates = Candidate.objects.all()
        else:
            existing_ids = CandidateEmbedding.objects.values_list(
                "candidate_id", flat=True
            )
            candidates = Candidate.objects.exclude(id__in=existing_ids)

        total = candidates.count()
        self.stdout.write(f"Generating embeddings for {total} candidates...")

        ok, fail = 0, 0
        for c in candidates.iterator():
            result = generate_candidate_embedding(c)
            if result:
                ok += 1
            else:
                fail += 1
                self.stderr.write(f"  FAIL: {c.name}")

        self.stdout.write(self.style.SUCCESS(f"Done: {ok} OK, {fail} failed"))
