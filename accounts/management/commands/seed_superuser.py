from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = (
        "Ensure SYNCO_SUPERUSER_EMAIL user exists with level=2 and is_superuser=True. "
        "If SYNCO_SUPERUSER_PASSWORD is set, also sets/updates the password."
    )

    def handle(self, *args, **options):
        email = getattr(settings, "SYNCO_SUPERUSER_EMAIL", None)
        if not email:
            raise CommandError("SYNCO_SUPERUSER_EMAIL is not configured.")

        password = getattr(settings, "SYNCO_SUPERUSER_PASSWORD", "") or ""

        user = User.objects.filter(email=email).first()
        created = user is None
        if created:
            user = User.objects.create(
                email=email,
                username=email,
                level=2,
                is_superuser=True,
                is_staff=True,
            )
            if password:
                user.set_password(password)
                user.save(update_fields=["password"])
        else:
            user.username = email
            user.level = 2
            user.is_superuser = True
            user.is_staff = True
            user.save(update_fields=["username", "level", "is_superuser", "is_staff"])
            if password:
                user.set_password(password)
                user.save(update_fields=["password"])

        password_note = "password set" if password else "password unchanged"
        self.stdout.write(
            self.style.SUCCESS(
                f"Superuser ensured: {user.email} "
                f"(level={user.level}, is_superuser={user.is_superuser}, {password_note})"
            )
        )
