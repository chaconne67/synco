import os

from django import forms

from clients.models import Client

from .models import Contact, JDSource, Project, Submission

INPUT_CSS = (
    "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] "
    "focus:ring-2 focus:ring-primary focus:border-primary"
)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["client", "title", "jd_source", "jd_text", "jd_file", "status"]
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
            "status": forms.Select(attrs={"class": INPUT_CSS}),
        }
        labels = {
            "client": "고객사",
            "title": "프로젝트명",
            "jd_source": "JD 입력 방식",
            "jd_text": "JD 내용",
            "jd_file": "JD 파일",
            "status": "상태",
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            self.fields["client"].queryset = Client.objects.filter(
                organization=organization
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
