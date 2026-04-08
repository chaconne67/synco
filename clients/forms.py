from django import forms

from .models import Client, Contract


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["name", "industry", "size", "region", "notes"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] focus:ring-2 focus:ring-primary focus:border-primary",
                    "placeholder": "고객사명",
                }
            ),
            "industry": forms.TextInput(
                attrs={
                    "class": "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] focus:ring-2 focus:ring-primary focus:border-primary",
                    "placeholder": "예: IT, 금융, 제조",
                }
            ),
            "size": forms.Select(
                attrs={
                    "class": "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] focus:ring-2 focus:ring-primary focus:border-primary",
                }
            ),
            "region": forms.TextInput(
                attrs={
                    "class": "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] focus:ring-2 focus:ring-primary focus:border-primary",
                    "placeholder": "예: 서울, 경기",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] focus:ring-2 focus:ring-primary focus:border-primary",
                    "rows": 3,
                    "placeholder": "비고",
                }
            ),
        }
        labels = {
            "name": "고객사명",
            "industry": "업종",
            "size": "기업 규모",
            "region": "지역",
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
                    "class": "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] focus:ring-2 focus:ring-primary focus:border-primary",
                },
                format="%Y-%m-%d",
            ),
            "end_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] focus:ring-2 focus:ring-primary focus:border-primary",
                },
                format="%Y-%m-%d",
            ),
            "status": forms.Select(
                attrs={
                    "class": "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] focus:ring-2 focus:ring-primary focus:border-primary",
                }
            ),
            "terms": forms.Textarea(
                attrs={
                    "class": "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] focus:ring-2 focus:ring-primary focus:border-primary",
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
