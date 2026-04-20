# accounts/forms.py

from django import forms


# ---------------------------------------------------------------------------
# Active forms
# ---------------------------------------------------------------------------


class NotificationPreferenceForm(forms.Form):
    """알림 설정 폼. JSONField를 개별 체크박스로 분리."""

    # 새 컨택 결과
    contact_result_web = forms.BooleanField(required=False)
    contact_result_telegram = forms.BooleanField(required=False)
    # 추천 피드백
    recommendation_feedback_web = forms.BooleanField(required=False)
    recommendation_feedback_telegram = forms.BooleanField(required=False)
    # 프로젝트 승인 요청
    project_approval_web = forms.BooleanField(required=False)
    project_approval_telegram = forms.BooleanField(required=False)
    # 뉴스피드 업데이트
    newsfeed_update_web = forms.BooleanField(required=False)
    newsfeed_update_telegram = forms.BooleanField(required=False)

    def load_from_preferences(self, preferences: dict):
        """JSONField dict -> form initial values."""
        for key, channels in preferences.items():
            for channel, enabled in channels.items():
                field_name = f"{key}_{channel}"
                if field_name in self.fields:
                    self.initial[field_name] = enabled

    def to_preferences(self) -> dict:
        """Form cleaned_data -> JSONField dict."""
        return {
            "contact_result": {
                "web": self.cleaned_data["contact_result_web"],
                "telegram": self.cleaned_data["contact_result_telegram"],
            },
            "recommendation_feedback": {
                "web": self.cleaned_data["recommendation_feedback_web"],
                "telegram": self.cleaned_data["recommendation_feedback_telegram"],
            },
            "project_approval": {
                "web": self.cleaned_data["project_approval_web"],
                "telegram": self.cleaned_data["project_approval_telegram"],
            },
            "newsfeed_update": {
                "web": self.cleaned_data["newsfeed_update_web"],
                "telegram": self.cleaned_data["newsfeed_update_telegram"],
            },
        }
