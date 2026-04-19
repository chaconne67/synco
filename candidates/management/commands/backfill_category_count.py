from django.core.management.base import BaseCommand
from candidates.models import Category


class Command(BaseCommand):
    help = "Recompute Category.candidate_count for all categories."

    def handle(self, *args, **options):
        updated = 0
        for cat in Category.objects.all():
            real = cat.candidates.count()
            if cat.candidate_count != real:
                cat.candidate_count = real
                cat.save(update_fields=["candidate_count"])
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Updated {updated} categories."))
