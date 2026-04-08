from django import forms

from clients.models import Client

from .models import Project

INPUT_CSS = (
    "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] "
    "focus:ring-2 focus:ring-primary focus:border-primary"
)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["client", "title", "jd_text", "jd_file", "status"]
        widgets = {
            "client": forms.Select(attrs={"class": INPUT_CSS}),
            "title": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "프로젝트명"}
            ),
            "jd_text": forms.Textarea(
                attrs={
                    "class": INPUT_CSS,
                    "rows": 5,
                    "placeholder": "채용 공고 내용",
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
