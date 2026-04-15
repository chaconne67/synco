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

- [ ] **Step 1: Create accounts/forms.py with all forms**

```python
# accounts/forms.py
from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator

from .models import InviteCode, NotificationPreference, Organization


class OrganizationForm(forms.ModelForm):
    """조직 정보 수정 폼 (owner용)."""

    class Meta:
        model = Organization
        fields = ["name", "logo"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "w-full px-3 py-2.5 text-[14px] border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent",
                    "placeholder": "조직명",
                }
            ),
            "logo": forms.ClearableFileInput(
                attrs={
                    "class": "block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100",
                }
            ),
        }


class InviteCodeCreateForm(forms.Form):
    """초대코드 생성 폼."""

    role = forms.ChoiceField(
        choices=[
            ("consultant", "Consultant"),
            ("viewer", "Viewer"),
        ],
        initial="consultant",
        widget=forms.Select(
            attrs={
                "class": "w-full px-3 py-2.5 text-[14px] border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent",
            }
        ),
    )
    max_uses = forms.IntegerField(
        initial=1,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        widget=forms.NumberInput(
            attrs={
                "class": "w-full px-3 py-2.5 text-[14px] border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent",
                "min": "1",
                "max": "100",
            }
        ),
    )
    expires_at = forms.DateTimeField(
        required=False,
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "w-full px-3 py-2.5 text-[14px] border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent",
            }
        ),
    )


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
                "web": self.cleaned_data.get("contact_result_web", True),
                "telegram": self.cleaned_data.get("contact_result_telegram", True),
            },
            "recommendation_feedback": {
                "web": self.cleaned_data.get("recommendation_feedback_web", True),
                "telegram": self.cleaned_data.get("recommendation_feedback_telegram", True),
            },
            "project_approval": {
                "web": self.cleaned_data.get("project_approval_web", True),
                "telegram": self.cleaned_data.get("project_approval_telegram", True),
            },
            "newsfeed_update": {
                "web": self.cleaned_data.get("newsfeed_update_web", True),
                "telegram": self.cleaned_data.get("newsfeed_update_telegram", False),
            },
        }
```

- [ ] **Step 2: Commit**

```bash
git add accounts/forms.py
git commit -m "feat(accounts): add OrganizationForm, InviteCodeCreateForm, NotificationPreferenceForm"
```
