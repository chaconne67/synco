import os

from django import forms
from django.contrib.auth import get_user_model

from clients.models import Client

User = get_user_model()

from .models import (
    Interview,
    JDSource,
    NewsSource,
    PostingSite,
    Project,
    Submission,
)

INPUT_CSS = (
    "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] "
    "focus:ring-2 focus:ring-primary focus:border-primary"
)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            "client",
            "title",
            "jd_source",
            "jd_text",
            "jd_file",
            "assigned_consultants",
        ]
        widgets = {
            "client": forms.Select(attrs={"class": INPUT_CSS}),
            "title": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "프로젝트명"}
            ),
            "jd_source": forms.Select(attrs={"class": INPUT_CSS}),
            "jd_text": forms.Textarea(
                attrs={
                    "class": INPUT_CSS,
                    "rows": 5,
                    "placeholder": "채용 공고 내용을 입력하세요",
                }
            ),
            "jd_file": forms.ClearableFileInput(
                attrs={
                    "class": INPUT_CSS,
                }
            ),
        }
        labels = {
            "client": "고객사",
            "title": "프로젝트명",
            "jd_source": "JD 입력 방식",
            "jd_text": "JD 내용",
            "jd_file": "JD 파일",
        }

    assigned_consultants = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="담당 컨설턴트",
    )

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            self.fields["client"].queryset = Client.objects.filter(
                organization=organization
            )
            self.fields["assigned_consultants"].queryset = User.objects.filter(
                membership__organization=organization,
                membership__status="active",
            )
        self.fields["jd_text"].required = False
        self.fields["jd_file"].required = False
        self.fields["jd_source"].required = False

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get("jd_source")

        if source == JDSource.TEXT and not cleaned.get("jd_text"):
            self.add_error(
                "jd_text",
                "텍스트 입력 방식을 선택한 경우 JD 내용을 입력해야 합니다.",
            )
        elif source == JDSource.UPLOAD and not cleaned.get("jd_file"):
            if not (self.instance and self.instance.jd_file):
                self.add_error(
                    "jd_file",
                    "파일 업로드 방식을 선택한 경우 파일을 첨부해야 합니다.",
                )

        return cleaned


# ContactForm removed — Contact model deleted in Phase 1.
# Phase 3 will replace with ActionItem-based forms.
class ContactForm(forms.Form):
    """Stub — Contact model deleted. Phase 3 will replace."""

    pass


# ---------------------------------------------------------------------------
# P07: Submission forms
# ---------------------------------------------------------------------------

ALLOWED_FILE_EXTENSIONS = [".pdf", ".doc", ".docx"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


# SubmissionForm — Phase 3 will rewrite to use ActionItem-based flow.
class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ["template", "document_file", "notes"]
        widgets = {
            "template": forms.Select(attrs={"class": INPUT_CSS}),
            "document_file": forms.ClearableFileInput(attrs={"class": INPUT_CSS}),
            "notes": forms.Textarea(
                attrs={"class": INPUT_CSS, "rows": 3, "placeholder": "메모"}
            ),
        }
        labels = {
            "template": "양식",
            "document_file": "추천 서류",
            "notes": "메모",
        }

    def clean_document_file(self):
        f = self.cleaned_data.get("document_file")
        if f:
            ext = os.path.splitext(f.name)[1].lower()
            if ext not in ALLOWED_FILE_EXTENSIONS:
                raise forms.ValidationError(
                    f"허용되지 않는 파일 형식입니다. ({', '.join(ALLOWED_FILE_EXTENSIONS)})"
                )
            if f.size > MAX_FILE_SIZE:
                raise forms.ValidationError(
                    f"파일 크기가 10MB를 초과합니다. (현재: {f.size / 1024 / 1024:.1f}MB)"
                )
        return f


# SubmissionFeedbackForm — Submission.Status removed. Phase 3 will redesign.
class SubmissionFeedbackForm(forms.Form):
    """고객사 피드백 입력 폼. Phase 3 will redesign."""

    feedback = forms.CharField(
        widget=forms.Textarea(
            attrs={"class": INPUT_CSS, "rows": 3, "placeholder": "피드백 내용"}
        ),
        label="피드백",
        required=False,
    )


# ---------------------------------------------------------------------------
# P09: Interview / Offer forms
# ---------------------------------------------------------------------------


# InterviewForm — Phase 3 will rewrite to use ActionItem-based flow.
class InterviewForm(forms.ModelForm):
    class Meta:
        model = Interview
        fields = ["round", "scheduled_at", "type", "location", "notes"]
        widgets = {
            "round": forms.NumberInput(attrs={"class": INPUT_CSS, "min": 1}),
            "scheduled_at": forms.DateTimeInput(
                attrs={"class": INPUT_CSS, "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "type": forms.Select(attrs={"class": INPUT_CSS}),
            "location": forms.TextInput(
                attrs={
                    "class": INPUT_CSS,
                    "placeholder": "면접 장소 또는 화상 링크",
                }
            ),
            "notes": forms.Textarea(
                attrs={"class": INPUT_CSS, "rows": 3, "placeholder": "메모"}
            ),
        }
        labels = {
            "round": "차수",
            "scheduled_at": "면접 일시",
            "type": "유형",
            "location": "장소/링크",
            "notes": "메모",
        }


class InterviewResultForm(forms.Form):
    """면접 결과 입력 폼."""

    result = forms.ChoiceField(
        choices=[
            (Interview.Result.PASSED, "합격"),
            (Interview.Result.ON_HOLD, "보류"),
            (Interview.Result.FAILED, "탈락"),
        ],
        widget=forms.Select(attrs={"class": INPUT_CSS}),
        label="결과",
    )
    feedback = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": INPUT_CSS,
                "rows": 3,
                "placeholder": "면접관/고객사 피드백",
            }
        ),
        label="피드백",
        required=False,
    )


# OfferForm removed — Offer model deleted in Phase 1.
# Phase 3 will replace with ActionItem-based hiring workflow.
class OfferForm(forms.Form):
    """Stub — Offer model deleted. Phase 3 will replace."""

    pass


# ---------------------------------------------------------------------------
# P10: Posting forms
# ---------------------------------------------------------------------------


class PostingEditForm(forms.Form):
    """공지 텍스트 편집 폼."""

    posting_text = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": INPUT_CSS,
                "rows": 15,
                "placeholder": "공지 내용을 입력하세요",
            }
        ),
        label="공지 내용",
    )


class PostingSiteForm(forms.ModelForm):
    class Meta:
        model = PostingSite
        fields = ["site", "posted_at", "is_active", "applicant_count", "url", "notes"]
        widgets = {
            "site": forms.Select(attrs={"class": INPUT_CSS}),
            "posted_at": forms.DateInput(
                attrs={"class": INPUT_CSS, "type": "date"},
                format="%Y-%m-%d",
            ),
            "is_active": forms.CheckboxInput(
                attrs={
                    "class": "rounded border-gray-300 text-primary focus:ring-primary"
                }
            ),
            "applicant_count": forms.NumberInput(attrs={"class": INPUT_CSS, "min": 0}),
            "url": forms.URLInput(
                attrs={"class": INPUT_CSS, "placeholder": "포스팅 URL (선택)"}
            ),
            "notes": forms.Textarea(
                attrs={"class": INPUT_CSS, "rows": 2, "placeholder": "메모"}
            ),
        }
        labels = {
            "site": "사이트",
            "posted_at": "게시일",
            "is_active": "활성",
            "applicant_count": "지원자 수",
            "url": "URL",
            "notes": "메모",
        }


# ---------------------------------------------------------------------------
# P11: Approval forms
# ---------------------------------------------------------------------------

DECISION_CHOICES = [
    ("승인", "승인"),
    ("합류", "합류"),
    ("메시지", "메시지"),
    ("반려", "반려"),
]


class ApprovalDecisionForm(forms.Form):
    """관리자 승인 판단 폼."""

    decision = forms.ChoiceField(
        choices=DECISION_CHOICES,
        widget=forms.Select(attrs={"class": INPUT_CSS}),
        label="판단",
    )
    response_text = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": INPUT_CSS,
                "rows": 3,
                "placeholder": "메시지 또는 반려 사유",
            }
        ),
        label="메시지",
        required=False,
    )
    merge_target = forms.UUIDField(required=False)


# ---------------------------------------------------------------------------
# P17: News Source form
# ---------------------------------------------------------------------------


class NewsSourceForm(forms.ModelForm):
    class Meta:
        model = NewsSource
        fields = ["name", "url", "type", "category"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "소스 이름"}
            ),
            "url": forms.URLInput(
                attrs={
                    "class": INPUT_CSS,
                    "placeholder": "https://example.com/feed.xml",
                }
            ),
            "type": forms.Select(attrs={"class": INPUT_CSS}),
            "category": forms.Select(attrs={"class": INPUT_CSS}),
        }
        labels = {
            "name": "소스 이름",
            "url": "피드 URL",
            "type": "유형",
            "category": "카테고리",
        }

    def clean_url(self):
        url = self.cleaned_data.get("url", "")
        if url and not url.startswith(("http://", "https://")):
            raise forms.ValidationError("http:// 또는 https:// URL만 허용됩니다.")
        return url
