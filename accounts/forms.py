# accounts/forms.py

import io

from django import forms
from django.core.files.base import ContentFile
from PIL import Image, ImageOps

from .models import User


# ---------------------------------------------------------------------------
# Active forms
# ---------------------------------------------------------------------------

MAX_AVATAR_UPLOAD_SIZE = 5 * 1024 * 1024
AVATAR_SIZE = 512
AVATAR_JPEG_QUALITY = 85


class AvatarImageField(forms.ImageField):
    def to_python(self, data):
        if data and getattr(data, "size", 0) > MAX_AVATAR_UPLOAD_SIZE:
            raise forms.ValidationError("프로필 이미지는 5MB 이하만 업로드할 수 있습니다.")
        return super().to_python(data)


class ProfileForm(forms.ModelForm):
    """Profile settings form."""

    avatar = AvatarImageField(required=False)

    class Meta:
        model = User
        fields = ["avatar", "last_name", "first_name", "company_name", "phone"]

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if not avatar:
            return avatar
        if getattr(avatar, "size", 0) > MAX_AVATAR_UPLOAD_SIZE:
            raise forms.ValidationError("프로필 이미지는 5MB 이하만 업로드할 수 있습니다.")
        return avatar

    def save(self, commit=True):
        user = super().save(commit=False)
        avatar = self.cleaned_data.get("avatar")
        if avatar and hasattr(avatar, "file"):
            user.avatar.save(
                "avatar.jpg",
                _optimize_avatar(avatar),
                save=False,
            )
        if commit:
            user.save()
        return user


def _optimize_avatar(avatar) -> ContentFile:
    image = Image.open(avatar)
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")
    image.thumbnail((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (AVATAR_SIZE, AVATAR_SIZE), (248, 250, 252))
    left = (AVATAR_SIZE - image.width) // 2
    top = (AVATAR_SIZE - image.height) // 2
    canvas.paste(image, (left, top))

    output = io.BytesIO()
    canvas.save(output, format="JPEG", quality=AVATAR_JPEG_QUALITY, optimize=True)
    return ContentFile(output.getvalue())


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
