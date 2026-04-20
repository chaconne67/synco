"""ActionType.label_ko 를 최신 네이밍 정책에 맞게 업데이트."""

from django.core.management.base import BaseCommand

from projects.models import ActionType


LABEL_UPDATES = {
    # 이력서 준비 단계
    "receive_resume": "이력서 받기",
    "convert_resume": "이력서 정리하기",
    # 이력서 작성(제출용) 단계
    "prepare_submission": "제출용 이력서 작성",
    "submit_to_pm": "내부 검토 요청",
    # 이력서 제출 단계
    "submit_to_client": "이력서 고객사 제출",
    "await_doc_review": "서류 검토 대기",
    "receive_doc_feedback": "서류 피드백 수령",
}


class Command(BaseCommand):
    help = "ActionType.label_ko 를 Phase C 네이밍 정책대로 업데이트."

    def handle(self, *args, **options):
        updated = 0
        for code, label in LABEL_UPDATES.items():
            qs = ActionType.objects.filter(code=code)
            if not qs.exists():
                self.stdout.write(self.style.WARNING(f"skip: {code} not found"))
                continue
            qs.update(label_ko=label)
            updated += 1
            self.stdout.write(f"updated: {code} → {label}")
        self.stdout.write(self.style.SUCCESS(f"Done. {updated} rows updated."))
