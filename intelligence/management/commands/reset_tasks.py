from django.core.management.base import BaseCommand

from contacts.models import Interaction, Task


class Command(BaseCommand):
    help = (
        "Delete all AI-extracted tasks and reset task_checked flags for re-processing"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        ai_tasks = Task.objects.filter(source=Task.Source.AI_EXTRACTED)
        checked = Interaction.objects.filter(task_checked=True)

        task_count = ai_tasks.count()
        interaction_count = checked.count()

        if dry_run:
            self.stdout.write(f"Would delete {task_count} AI-extracted tasks")
            self.stdout.write(
                f"Would reset {interaction_count} interactions (task_checked → False)"
            )
            return

        ai_tasks.delete()
        checked.update(task_checked=False)

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {task_count} AI tasks, reset {interaction_count} interactions"
            )
        )
