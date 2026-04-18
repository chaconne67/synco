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
    "focus:ring-2 focus:ring-ink3 focus:border-ink3"
)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            "client",
            "title",
            "deadline",
            "annual_salary",
            "fee_percent",
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
            "deadline": forms.DateInput(attrs={"class": INPUT_CSS, "type": "date"}),
            "annual_salary": forms.NumberInput(
                attrs={
                    "class": INPUT_CSS,
                    "placeholder": "예: 80000000",
                    "min": "0",
                    "step": "1000000",
                }
            ),
            "fee_percent": forms.NumberInput(
                attrs={
                    "class": INPUT_CSS,
                    "placeholder": "예: 20.00",
                    "min": "0",
                    "max": "100",
                    "step": "0.5",
                }
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
            "deadline": "마감 예정일",
            "annual_salary": "포지션 연봉 (원)",
            "fee_percent": "수수료율 (%)",
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

        # 신규 프로젝트는 deadline·연봉·수수료율 필수. 기존 프로젝트 편집은 optional
        # (누락 데이터는 대시보드에서 "데이터 누락 N건"으로 경고).
        # 주: BaseModel이 UUID PK를 생성 시점에 부여하므로 pk is None 체크 불가 → _state.adding 사용
        is_new = self.instance._state.adding
        self.fields["deadline"].required = is_new
        self.fields["annual_salary"].required = is_new
        self.fields["fee_percent"].required = is_new

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
# P09: Interview forms
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
                attrs={"class": "rounded border-gray-300 text-ink3 focus:ring-ink3"}
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


# ========================================
# Phase 3a: New forms (added below existing forms)
# ========================================

from projects.models import (
    Application,
    DropReason,
    ProjectResult,
)


class ApplicationCreateForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ["candidate", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            from candidates.models import Candidate

            self.fields["candidate"].queryset = Candidate.objects.filter(
                owned_by=organization
            )


class ApplicationDropForm(forms.Form):
    drop_reason = forms.ChoiceField(choices=DropReason.choices, label="드롭 사유")
    drop_note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="메모",
    )


class ProjectCloseForm(forms.Form):
    result = forms.ChoiceField(choices=ProjectResult.choices, label="결과")
    note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=True,
        label="사유·메모",
    )


class ActionItemCreateForm(forms.Form):
    action_type_id = forms.UUIDField()
    title = forms.CharField(max_length=300, required=False)
    channel = forms.CharField(max_length=20, required=False)
    scheduled_at = forms.DateTimeField(required=False)
    due_at = forms.DateTimeField(required=False)
    note = forms.CharField(widget=forms.Textarea, required=False)


class ActionItemCompleteForm(forms.Form):
    result = forms.CharField(widget=forms.Textarea, required=False)
    note = forms.CharField(widget=forms.Textarea, required=False)
    next_action_type_ids = forms.CharField(required=False)


class ActionItemSkipForm(forms.Form):
    note = forms.CharField(widget=forms.Textarea, required=False)


class ActionItemRescheduleForm(forms.Form):
    new_due_at = forms.DateTimeField(required=False)
    new_scheduled_at = forms.DateTimeField(required=False)


class ContactCompleteForm(forms.Form):
    RESPONSE_CHOICES = [
        ("positive", "긍정 (진행 의사 있음)"),
        ("negative", "부정 (거절)"),
        ("pending", "보류 (추후 결정)"),
    ]
    response = forms.ChoiceField(choices=RESPONSE_CHOICES, widget=forms.RadioSelect)
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


class PreMeetingScheduleForm(forms.Form):
    scheduled_at = forms.DateTimeField()
    channel = forms.ChoiceField(
        choices=[("in_person", "대면"), ("video", "화상"), ("phone", "전화")]
    )
    location = forms.CharField(required=False, max_length=300)


class PreMeetingRecordForm(forms.Form):
    summary = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))
    audio = forms.FileField(
        required=False, help_text="녹음 파일 (선택) — 추후 STT 지원 예정"
    )
