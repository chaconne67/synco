from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = "Ensure SYNCO_SUPERUSER_EMAIL user exists with level=2 and is_superuser=True."

    def handle(self, *args, **options):
        email = getattr(settings, "SYNCO_SUPERUSER_EMAIL", None)
        if not email:
            raise CommandError("SYNCO_SUPERUSER_EMAIL is not configured.")

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email.split("@")[0],
                "level": 2,
                "is_superuser": True,
                "is_staff": True,
            },
        )
        if not created:
            user.level = 2
            user.is_superuser = True
            user.is_staff = True
            user.save(update_fields=["level", "is_superuser", "is_staff"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Superuser ensured: {user.email} "
                f"(level={user.level}, is_superuser={user.is_superuser})"
            )
        )
