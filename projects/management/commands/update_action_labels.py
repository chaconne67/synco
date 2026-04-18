"""사용자 친화 ActionType 라벨 일괄 업데이트.

헤드헌팅 업계 용어 → 일반 사용자가 바로 이해할 수 있는 한국어로 교체.

사용: uv run python manage.py update_action_labels
"""

from django.core.management.base import BaseCommand

from projects.models import ActionType


# code: (new label_ko, new description_stub)
UPDATES = {
    "search_db":            "DB에서 찾기",
    "search_external":      "외부에서 찾기",
    "reach_out":            "연락하기",
    "re_reach_out":         "다시 연락하기",
    "await_reply":          "답장 기다리기",
    "share_jd":             "JD 공유하기",
    "receive_resume":       "이력서 받기",
    "convert_resume":       "이력서 정리하기",
    "schedule_pre_meet":    "사전 미팅 일정 잡기",
    "pre_meeting":          "사전 미팅 진행하기",
    "prepare_submission":   "제출용 이력서 작성",
    "submit_to_pm":         "내부 검토 요청",
    "submit_to_client":     "고객사에 제출",
    "await_doc_review":     "서류 검토 기다리기",
    "receive_doc_feedback": "서류 피드백 받기",
    "schedule_interview":   "면접 일정 잡기",
    "interview_round":      "면접 진행",
    "await_interview_result": "면접 결과 기다리기",
    "confirm_hire":         "입사 확정",
    "await_onboarding":     "입사 기다리기",
    "follow_up":            "팔로업 연락",
    "escalate_to_boss":     "사장님께 보고",
    "note":                 "메모 남기기",
}


class Command(BaseCommand):
    help = "ActionType.label_ko 업데이트 + 단계 건너뛰기 placeholder ActionType seed"

    def handle(self, *args, **opts):
        updated = 0
        skipped = 0
        for code, new_label in UPDATES.items():
            try:
                at = ActionType.objects.get(code=code)
            except ActionType.DoesNotExist:
                self.stdout.write(f"  · {code}: not found, skipped")
                skipped += 1
                continue
            if at.label_ko == new_label:
                continue
            old = at.label_ko
            at.label_ko = new_label
            at.save(update_fields=["label_ko"])
            self.stdout.write(f"  ✓ {code}: {old} → {new_label}")
            updated += 1

        # stage_skipped placeholder — 8단계 건너뛰기 기록용
        stage_skipped, created = ActionType.objects.get_or_create(
            code="stage_skipped",
            defaults={
                "label_ko": "단계 건너뛰기",
                "description": "업무 단계를 생략하고 다음 단계로 이동 (이력서 기존 보유 등)",
                "sort_order": 999,
                "is_protected": True,
            },
        )
        if created:
            self.stdout.write("  ✓ stage_skipped ActionType 생성")
        elif stage_skipped.label_ko != "단계 건너뛰기":
            stage_skipped.label_ko = "단계 건너뛰기"
            stage_skipped.save(update_fields=["label_ko"])
            self.stdout.write("  ✓ stage_skipped 라벨 업데이트")

        self.stdout.write(self.style.SUCCESS(
            f"Updated {updated}, skipped {skipped}"
        ))
