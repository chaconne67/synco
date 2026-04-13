"""개발 DB 3역할 시딩: 슈퍼유저·CEO·Consultant (이미 존재하면 upsert)."""

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Membership, Organization, User


SUPERUSER_NAME = "chaconne67"
SUPERUSER_EMAIL = "chaconne67@gmail.com"
SUPERUSER_PASSWORD = "bachbwv100$"

CEO_NAME = "ceo"
CEO_EMAIL = "ceo@synco.local"
CEO_PASSWORD = "ceo1234"

ORG_NAME = "테스트 헤드헌팅"
CONSULTANT_USERNAME = "kakao_4816981089"


class Command(BaseCommand):
    help = "Seed dev DB with superuser / CEO / consultant test accounts."

    @transaction.atomic
    def handle(self, *args, **options):
        # 1) Remove dead temp user
        deleted, _ = User.objects.filter(email="temp@example.com").delete()
        if deleted:
            self.stdout.write(f"removed temp@example.com ({deleted})")

        # 2) Superuser upsert
        su, created = User.objects.get_or_create(
            username=SUPERUSER_NAME,
            defaults={"email": SUPERUSER_EMAIL},
        )
        su.email = SUPERUSER_EMAIL
        su.is_superuser = True
        su.is_staff = True
        su.set_password(SUPERUSER_PASSWORD)
        su.save()
        self.stdout.write(f"{'created' if created else 'updated'} superuser: {SUPERUSER_NAME}")

        # 3) Test organization
        org, org_created = Organization.objects.get_or_create(name=ORG_NAME)
        self.stdout.write(f"{'created' if org_created else 'found'} org: {ORG_NAME}")

        # 4) CEO user upsert
        ceo, ceo_created = User.objects.get_or_create(
            username=CEO_NAME,
            defaults={"email": CEO_EMAIL},
        )
        ceo.email = CEO_EMAIL
        ceo.set_password(CEO_PASSWORD)
        ceo.save()
        self.stdout.write(f"{'created' if ceo_created else 'updated'} CEO user: {CEO_NAME}")

        Membership.objects.update_or_create(
            user=ceo,
            defaults={
                "organization": org,
                "role": Membership.Role.OWNER,
                "status": Membership.Status.ACTIVE,
            },
        )
        self.stdout.write("CEO membership: OWNER / active")

        # 5) Consultant — attach kakao_4816981089 if exists
        try:
            consultant = User.objects.get(username=CONSULTANT_USERNAME)
        except User.DoesNotExist:
            self.stdout.write(self.style.WARNING(f"{CONSULTANT_USERNAME} not found — skipping consultant membership"))
            self.stdout.write(self.style.SUCCESS("seed_dev_roles done"))
            return

        Membership.objects.update_or_create(
            user=consultant,
            defaults={
                "organization": org,
                "role": Membership.Role.CONSULTANT,
                "status": Membership.Status.ACTIVE,
            },
        )
        self.stdout.write("Consultant membership: CONSULTANT / active")
        self.stdout.write(self.style.SUCCESS("seed_dev_roles done"))
