from django import forms

from .models import Client, Contract

INPUT_CLS = "w-full rounded-lg border border-hair bg-surface px-4 py-2.5 text-sm focus:border-ink3 focus:ring-2 focus:ring-ink3/10 outline-none"
TEXTAREA_CLS = INPUT_CLS + " resize-none"


class ClientForm(forms.ModelForm):
    def clean_logo(self):
        from clients.services.client_create import validate_logo_file

        f = self.cleaned_data.get("logo")
        if f:
            try:
                validate_logo_file(f)
            except ValueError as e:
                raise forms.ValidationError(str(e)) from e
        return f

    class Meta:
        model = Client
        fields = [
            "name",
            "industry",
            "size",
            "region",
            "website",
            "logo",
            "description",
            "notes",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": INPUT_CLS, "placeholder": "고객사명"}
            ),
            "industry": forms.Select(attrs={"class": INPUT_CLS}),
            "size": forms.Select(attrs={"class": INPUT_CLS}),
            "region": forms.TextInput(
                attrs={"class": INPUT_CLS, "placeholder": "예: 서울, 경기"}
            ),
            "website": forms.URLInput(
                attrs={"class": INPUT_CLS, "placeholder": "https://"}
            ),
            "logo": forms.ClearableFileInput(
                attrs={"class": "text-sm", "accept": "image/*"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": TEXTAREA_CLS,
                    "rows": 2,
                    "placeholder": "카드 리스트에 노출되는 2줄 요약",
                }
            ),
            "notes": forms.Textarea(
                attrs={"class": TEXTAREA_CLS, "rows": 6, "placeholder": "메모"}
            ),
        }
        labels = {
            "name": "고객사명",
            "industry": "업종",
            "size": "기업 규모",
            "region": "지역",
            "website": "웹사이트",
            "logo": "로고",
            "description": "설명",
            "notes": "비고",
        }


class ContractForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = ["start_date", "end_date", "status", "terms"]
        widgets = {
            "start_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] focus:ring-2 focus:ring-ink3 focus:border-ink3",
                },
                format="%Y-%m-%d",
            ),
            "end_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] focus:ring-2 focus:ring-ink3 focus:border-ink3",
                },
                format="%Y-%m-%d",
            ),
            "status": forms.Select(
                attrs={
                    "class": "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] focus:ring-2 focus:ring-ink3 focus:border-ink3",
                }
            ),
            "terms": forms.Textarea(
                attrs={
                    "class": "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] focus:ring-2 focus:ring-ink3 focus:border-ink3",
                    "rows": 3,
                    "placeholder": "계약 조건",
                }
            ),
        }
        labels = {
            "start_date": "시작일",
            "end_date": "종료일",
            "status": "상태",
            "terms": "계약 조건",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["end_date"].required = False
