# accounts/forms.py
import datetime as dt

from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone

from accounts.models import Organization

INPUT_CSS = (
    "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] "
    "focus:ring-2 focus:ring-ink3 focus:border-ink3"
)

FILE_INPUT_CSS = (
    "block w-full text-sm text-gray-500 "
    "file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 "
    "file:text-sm file:font-medium file:bg-indigo-50 file:text-indigo-700 "
    "hover:file:bg-indigo-100"
)


# ---------------------------------------------------------------------------
# Legacy forms — kept only until views_org.py is deleted in T6.
# Do not add new consumers; these will be removed together with views_org.py.
# ---------------------------------------------------------------------------

class OrganizationForm(forms.ModelForm):
    """조직 정보 수정 폼 (owner용). LEGACY — T6에서 views_org.py와 함께 삭제."""

    class Meta:
        model = Organization
        fields = ["name", "logo"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": INPUT_CSS,
                    "placeholder": "조직명",
                }
            ),
            "logo": forms.ClearableFileInput(
                attrs={
                    "class": FILE_INPUT_CSS,
                }
            ),
        }


class InviteCodeCreateForm(forms.Form):
    """초대코드 생성 폼. LEGACY — T6에서 views_org.py와 함께 삭제."""

    role = forms.ChoiceField(
        choices=[],
        initial="consultant",
        widget=forms.Select(
            attrs={
                "class": INPUT_CSS,
            }
        ),
    )
    max_uses = forms.IntegerField(
        initial=1,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        widget=forms.NumberInput(
            attrs={
                "class": INPUT_CSS,
                "min": "1",
                "max": "100",
            }
        ),
    )
    expires_at = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": INPUT_CSS,
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import InviteCode
        self.fields["role"].choices = [
            (r.value, r.label) for r in InviteCode.Role if r != InviteCode.Role.OWNER
        ]

    def clean_expires_at(self):
        """Validate future date and convert to end-of-day aware datetime."""
        date_val = self.cleaned_data.get("expires_at")
        if date_val is None:
            return None
        today = timezone.localdate()
        if date_val < today:
            raise forms.ValidationError("만료일은 오늘 이후여야 합니다.")
        # Convert date to end-of-day aware datetime for model storage
        end_of_day = dt.datetime.combine(
            date_val,
            dt.time(23, 59, 59),
            tzinfo=timezone.get_current_timezone(),
        )
        return end_of_day


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
