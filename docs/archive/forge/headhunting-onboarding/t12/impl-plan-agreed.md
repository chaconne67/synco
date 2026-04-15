# t12: accounts/forms.py 생성

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 조직 정보 수정, 초대코드 생성, 알림 설정 변경에 필요한 폼 클래스를 생성한다.

**Design spec:** `docs/forge/headhunting-onboarding/t12/design-spec.md`

**depends_on:** t11

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `accounts/forms.py` | 생성 | `OrganizationForm`, `InviteCodeCreateForm`, `NotificationPreferenceForm` |

---

## Changes from Tempering

| Issue | Severity | Resolution |
|-------|----------|------------|
| R1-01: expires_at DateTimeField → DateField | MAJOR | Changed to `DateField` + `clean_expires_at()` with end-of-day conversion |
| R1-02: Missing future-date validation | MAJOR | Added past-date rejection in `clean_expires_at()` |
| R1-03: Hardcoded notification defaults | MAJOR | Removed fallback defaults from `to_preferences()` |
| R1-04: Role choices hardcoded | MAJOR | Derived from `InviteCode.Role` excluding OWNER |
| R1-05: CSS inconsistent with project | MINOR | Added `INPUT_CSS` constant using project pattern |

---

- [ ] **Step 1: Create accounts/forms.py with all forms**

```python
# accounts/forms.py
from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone

from .models import InviteCode, Organization

INPUT_CSS = (
    "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] "
    "focus:ring-2 focus:ring-primary focus:border-primary"
)

FILE_INPUT_CSS = (
    "block w-full text-sm text-gray-500 "
    "file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 "
    "file:text-sm file:font-medium file:bg-indigo-50 file:text-indigo-700 "
    "hover:file:bg-indigo-100"
)


class OrganizationForm(forms.ModelForm):
    """조직 정보 수정 폼 (owner용)."""

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
    """초대코드 생성 폼."""

    role = forms.ChoiceField(
        choices=[
            (r.value, r.label)
            for r in InviteCode.Role
            if r != InviteCode.Role.OWNER
        ],
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

    def clean_expires_at(self):
        """Validate future date and convert to end-of-day aware datetime."""
        import datetime as dt

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
```

- [ ] **Step 2: Commit**

```bash
git add accounts/forms.py
git commit -m "feat(accounts): add OrganizationForm, InviteCodeCreateForm, NotificationPreferenceForm"
```

<!-- forge:t12:impl-plan:complete:2026-04-12T21:45:00+09:00 -->
