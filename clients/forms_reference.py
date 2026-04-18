"""Reference data management forms."""

from django import forms

from .models import CompanyProfile, PreferredCert, UniversityTier

_INPUT = "w-full border border-gray-300 rounded-lg px-3 py-2.5 text-[15px] focus:ring-2 focus:ring-ink3 focus:border-ink3"
_SELECT = _INPUT
_TEXTAREA = _INPUT


class UniversityTierForm(forms.ModelForm):
    class Meta:
        model = UniversityTier
        fields = ["name", "name_en", "country", "tier", "ranking", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "대학명"}),
            "name_en": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "University name (English)"}
            ),
            "country": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "KR", "maxlength": "10"}
            ),
            "tier": forms.Select(attrs={"class": _SELECT}),
            "ranking": forms.NumberInput(
                attrs={"class": _INPUT, "placeholder": "순위 (선택)", "min": "1"}
            ),
            "notes": forms.Textarea(
                attrs={"class": _TEXTAREA, "rows": 2, "placeholder": "비고"}
            ),
        }
        labels = {
            "name": "대학명",
            "name_en": "영문명",
            "country": "국가 코드",
            "tier": "티어",
            "ranking": "순위",
            "notes": "비고",
        }


class CompanyProfileForm(forms.ModelForm):
    class Meta:
        model = CompanyProfile
        fields = [
            "name",
            "name_en",
            "industry",
            "size_category",
            "revenue_range",
            "employee_count_range",
            "listed",
            "region",
            "notes",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "회사명"}),
            "name_en": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "Company name (English)"}
            ),
            "industry": forms.TextInput(attrs={"class": _INPUT, "placeholder": "업종"}),
            "size_category": forms.Select(attrs={"class": _SELECT}),
            "revenue_range": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "매출 규모"}
            ),
            "employee_count_range": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "직원 수 규모"}
            ),
            "listed": forms.Select(attrs={"class": _SELECT}),
            "region": forms.TextInput(attrs={"class": _INPUT, "placeholder": "소재지"}),
            "notes": forms.Textarea(
                attrs={"class": _TEXTAREA, "rows": 2, "placeholder": "비고"}
            ),
        }
        labels = {
            "name": "회사명",
            "name_en": "영문명",
            "industry": "업종",
            "size_category": "기업 규모",
            "revenue_range": "매출 규모",
            "employee_count_range": "직원 수",
            "listed": "상장 구분",
            "region": "소재지",
            "notes": "비고",
        }


class PreferredCertForm(forms.ModelForm):
    class Meta:
        model = PreferredCert
        fields = ["name", "full_name", "category", "level", "aliases", "notes"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "약칭 (예: KICPA)"}
            ),
            "full_name": forms.TextInput(
                attrs={"class": _INPUT, "placeholder": "정식 명칭 (예: 한국공인회계사)"}
            ),
            "category": forms.Select(attrs={"class": _SELECT}),
            "level": forms.Select(attrs={"class": _SELECT}),
            "aliases": forms.HiddenInput(),
            "notes": forms.Textarea(
                attrs={"class": _TEXTAREA, "rows": 2, "placeholder": "비고"}
            ),
        }
        labels = {
            "name": "약칭",
            "full_name": "정식 명칭",
            "category": "카테고리",
            "level": "난이도",
            "aliases": "별칭",
            "notes": "비고",
        }

    aliases_text = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": _INPUT,
                "placeholder": "별칭 (세미콜론 구분, 예: CPA;공인회계사)",
            }
        ),
        label="별칭",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.aliases:
            self.fields["aliases_text"].initial = ";".join(self.instance.aliases)

    def clean(self):
        cleaned = super().clean()
        aliases_text = cleaned.get("aliases_text", "")
        cleaned["aliases"] = (
            [a.strip() for a in aliases_text.split(";") if a.strip()]
            if aliases_text
            else []
        )
        return cleaned


class CSVImportForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV 파일",
        widget=forms.FileInput(
            attrs={
                "class": _INPUT,
                "accept": ".csv",
            }
        ),
    )
