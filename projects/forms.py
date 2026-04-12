import os

from django import forms
from django.contrib.auth import get_user_model

from clients.models import Client

User = get_user_model()

from .models import (
    Contact,
    Interview,
    JDSource,
    NewsSource,
    Offer,
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


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ["candidate", "channel", "contacted_at", "result", "notes"]
        widgets = {
            "candidate": forms.Select(attrs={"class": INPUT_CSS}),
            "channel": forms.Select(attrs={"class": INPUT_CSS}),
            "contacted_at": forms.DateTimeInput(
                attrs={"class": INPUT_CSS, "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "result": forms.Select(attrs={"class": INPUT_CSS}),
            "notes": forms.Textarea(
                attrs={"class": INPUT_CSS, "rows": 3, "placeholder": "메모"}
            ),
        }
        labels = {
            "candidate": "후보자",
            "channel": "연락 방법",
            "contacted_at": "컨택 일시",
            "result": "결과",
            "notes": "메모",
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            from candidates.models import Candidate

            self.fields["candidate"].queryset = Candidate.objects.filter(
                owned_by=organization
            )
        # 예정(RESERVED) 결과는 폼에서 선택 불가 (reserve 전용 엔드포인트 사용)
        self.fields["result"].choices = [
            (value, label)
            for value, label in Contact.Result.choices
            if value != Contact.Result.RESERVED
        ]

    def clean(self):
        cleaned = super().clean()
        result = cleaned.get("result")
        channel = cleaned.get("channel")
        contacted_at = cleaned.get("contacted_at")

        # 실제 컨택 기록에는 채널과 일시 필수
        if result and result != Contact.Result.RESERVED:
            if not channel:
                self.add_error("channel", "연락 방법을 선택해주세요.")
            if not contacted_at:
                self.add_error("contacted_at", "컨택 일시를 입력해주세요.")

        return cleaned


# ---------------------------------------------------------------------------
# P07: Submission forms
# ---------------------------------------------------------------------------

ALLOWED_FILE_EXTENSIONS = [".pdf", ".doc", ".docx"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ["candidate", "template", "document_file", "notes"]
        widgets = {
            "candidate": forms.Select(attrs={"class": INPUT_CSS}),
            "template": forms.Select(attrs={"class": INPUT_CSS}),
            "document_file": forms.ClearableFileInput(attrs={"class": INPUT_CSS}),
            "notes": forms.Textarea(
                attrs={"class": INPUT_CSS, "rows": 3, "placeholder": "메모"}
            ),
        }
        labels = {
            "candidate": "후보자",
            "template": "양식",
            "document_file": "추천 서류",
            "notes": "메모",
        }

    def __init__(self, *args, organization=None, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization and project:
            from candidates.models import Candidate

            interested_candidate_ids = Contact.objects.filter(
                project=project,
                result=Contact.Result.INTERESTED,
            ).values_list("candidate_id", flat=True)

            # 이미 등록된 Submission의 후보자 제외 (수정 시에는 현재 후보자 포함)
            existing_submission_ids = Submission.objects.filter(
                project=project
            ).values_list("candidate_id", flat=True)
            if self.instance and self.instance.pk:
                existing_submission_ids = existing_submission_ids.exclude(
                    candidate_id=self.instance.candidate_id
                )

            self.fields["candidate"].queryset = Candidate.objects.filter(
                pk__in=interested_candidate_ids,
                owned_by=organization,
            ).exclude(pk__in=existing_submission_ids)
        elif organization:
            from candidates.models import Candidate

            self.fields["candidate"].queryset = Candidate.objects.filter(
                owned_by=organization
            )

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


class SubmissionFeedbackForm(forms.Form):
    """고객사 피드백 입력 폼."""

    result = forms.ChoiceField(
        choices=[
            (Submission.Status.PASSED, "통과"),
            (Submission.Status.REJECTED, "탈락"),
        ],
        widget=forms.Select(attrs={"class": INPUT_CSS}),
        label="결과",
    )
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


class InterviewForm(forms.ModelForm):
    class Meta:
        model = Interview
        fields = ["submission", "round", "scheduled_at", "type", "location", "notes"]
        widgets = {
            "submission": forms.Select(attrs={"class": INPUT_CSS}),
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
            "submission": "추천 건",
            "round": "차수",
            "scheduled_at": "면접 일시",
            "type": "유형",
            "location": "장소/링크",
            "notes": "메모",
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project:
            # 통과된 Submission만 선택 가능
            self.fields["submission"].queryset = Submission.objects.filter(
                project=project,
                status=Submission.Status.PASSED,
            ).select_related("candidate")

    def clean(self):
        cleaned = super().clean()
        submission = cleaned.get("submission")
        round_num = cleaned.get("round")

        if submission and round_num:
            # 중복 (submission, round) 검증 — 수정 시 자기 자신 제외
            qs = Interview.objects.filter(
                submission=submission,
                round=round_num,
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    "round",
                    f"{round_num}차 면접이 이미 등록되어 있습니다.",
                )

        return cleaned


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


class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = ["submission", "salary", "position_title", "start_date", "notes"]
        widgets = {
            "submission": forms.Select(attrs={"class": INPUT_CSS}),
            "salary": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "제안 연봉"}
            ),
            "position_title": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "제안 직책"}
            ),
            "start_date": forms.DateInput(
                attrs={"class": INPUT_CSS, "type": "date"},
                format="%Y-%m-%d",
            ),
            "notes": forms.Textarea(
                attrs={"class": INPUT_CSS, "rows": 3, "placeholder": "협상 메모"}
            ),
        }
        labels = {
            "submission": "추천 건",
            "salary": "제안 연봉",
            "position_title": "제안 직책",
            "start_date": "출근 예정일",
            "notes": "메모",
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project:
            from projects.services.lifecycle import is_submission_offer_eligible

            # 통과 Submission 중 최신 인터뷰 합격 + Offer 없는 것만
            passed_submissions = Submission.objects.filter(
                project=project,
                status=Submission.Status.PASSED,
            ).select_related("candidate")

            # 이미 Offer 있는 Submission 제외 (수정 시 자기 submission 포함)
            existing_offer_sub_ids = Offer.objects.filter(
                submission__project=project,
            ).values_list("submission_id", flat=True)
            if self.instance and self.instance.pk:
                existing_offer_sub_ids = existing_offer_sub_ids.exclude(
                    submission_id=self.instance.submission_id,
                )

            eligible_ids = [
                s.pk
                for s in passed_submissions.exclude(pk__in=existing_offer_sub_ids)
                if is_submission_offer_eligible(s)
            ]
            self.fields["submission"].queryset = Submission.objects.filter(
                pk__in=eligible_ids,
            ).select_related("candidate")


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
