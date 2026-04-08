from django import forms

from clients.models import Client

from .models import JDSource, Project

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
