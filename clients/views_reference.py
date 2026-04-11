"""Reference data management views.

Permission model:
- Read (list, search, export): @login_required
- Write (create, update, delete, import): @staff_member_required
"""

from __future__ import annotations

import io

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required

from accounts.decorators import membership_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from .forms_reference import (
    CompanyProfileForm,
    CSVImportForm,
    PreferredCertForm,
    UniversityTierForm,
)
from .models import CompanyProfile, PreferredCert, UniversityTier
from .services.csv_handler import export_csv, import_csv

PAGE_SIZE = 30


# --- Index (defaults to university tab) ---


@login_required
@membership_required
def reference_index(request):
    """Reference management main page, defaults to universities tab."""
    return reference_universities(request)


# --- University views ---


@login_required
@membership_required
def reference_universities(request):
    """University ranking tab content."""
    qs = UniversityTier.objects.all()
    q = request.GET.get("q", "").strip()
    country = request.GET.get("country", "").strip()
    tier = request.GET.get("tier", "").strip()

    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(name_en__icontains=q))
    if country:
        qs = qs.filter(country=country)
    if tier:
        qs = qs.filter(tier=tier)

    paginator = Paginator(qs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    ctx = {
        "page_obj": page_obj,
        "q": q,
        "country": country,
        "tier": tier,
        "tier_choices": UniversityTier.Tier.choices,
        "countries": UniversityTier.objects.values_list("country", flat=True)
        .distinct()
        .order_by("country"),
        "active_tab": "universities",
        "is_staff": request.user.is_staff,
        "import_form": CSVImportForm(),
    }

    if request.headers.get("HX-Request"):
        return render(request, "clients/partials/ref_universities.html", ctx)
    return _render_reference_page(request, "universities", ctx)


@staff_member_required
def university_create(request):
    """Create a university. GET=form, POST=save."""
    if request.method == "POST":
        form = UniversityTierForm(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={"HX-Trigger": "universityChanged"})
    else:
        form = UniversityTierForm()
    return render(
        request,
        "clients/partials/ref_form_modal.html",
        {
            "form": form,
            "title": "대학 추가",
            "post_url": "/reference/universities/new/",
        },
    )


@staff_member_required
def university_update(request, pk):
    """Update a university."""
    obj = get_object_or_404(UniversityTier, pk=pk)
    if request.method == "POST":
        form = UniversityTierForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={"HX-Trigger": "universityChanged"})
    else:
        form = UniversityTierForm(instance=obj)
    return render(
        request,
        "clients/partials/ref_form_modal.html",
        {
            "form": form,
            "title": "대학 수정",
            "post_url": f"/reference/universities/{pk}/edit/",
        },
    )


@staff_member_required
def university_delete(request, pk):
    """Delete a university."""
    if request.method != "POST":
        return HttpResponse(status=405)
    obj = get_object_or_404(UniversityTier, pk=pk)
    obj.delete()
    return HttpResponse(status=204, headers={"HX-Trigger": "universityChanged"})


@staff_member_required
def university_import(request):
    """Import universities from CSV."""
    if request.method != "POST":
        return HttpResponse(status=405)
    form = CSVImportForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(
            request,
            "clients/partials/ref_import_result.html",
            {"errors": ["파일을 선택해 주세요."]},
        )
    csv_file = request.FILES["csv_file"]
    try:
        content = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return render(
            request,
            "clients/partials/ref_import_result.html",
            {"errors": ["UTF-8 인코딩이 아닙니다. UTF-8 파일을 사용해 주세요."]},
        )
    result = import_csv(UniversityTier, io.StringIO(content))
    return render(request, "clients/partials/ref_import_result.html", result)


@login_required
@membership_required
def university_export(request):
    """Export universities to CSV."""
    qs = UniversityTier.objects.all()
    q = request.GET.get("q", "").strip()
    country = request.GET.get("country", "").strip()
    tier = request.GET.get("tier", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(name_en__icontains=q))
    if country:
        qs = qs.filter(country=country)
    if tier:
        qs = qs.filter(tier=tier)

    output = export_csv(UniversityTier, qs)
    response = HttpResponse(
        output.getvalue(), content_type="text/csv; charset=utf-8-sig"
    )
    response["Content-Disposition"] = 'attachment; filename="universities.csv"'
    return response


# --- Company views ---


@login_required
@membership_required
def reference_companies(request):
    """Company DB tab content."""
    qs = CompanyProfile.objects.all()
    q = request.GET.get("q", "").strip()
    listed = request.GET.get("listed", "").strip()
    size = request.GET.get("size", "").strip()
    industry = request.GET.get("industry", "").strip()

    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(name_en__icontains=q))
    if listed:
        qs = qs.filter(listed=listed)
    if size:
        qs = qs.filter(size_category=size)
    if industry:
        qs = qs.filter(industry__icontains=industry)

    paginator = Paginator(qs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    ctx = {
        "page_obj": page_obj,
        "q": q,
        "listed_filter": listed,
        "size_filter": size,
        "industry_filter": industry,
        "listed_choices": CompanyProfile.Listed.choices,
        "size_choices": CompanyProfile.SizeCategory.choices,
        "active_tab": "companies",
        "is_staff": request.user.is_staff,
        "import_form": CSVImportForm(),
    }

    if request.headers.get("HX-Request"):
        return render(request, "clients/partials/ref_companies.html", ctx)
    return _render_reference_page(request, "companies", ctx)


@staff_member_required
def company_create(request):
    """Create a company."""
    if request.method == "POST":
        form = CompanyProfileForm(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={"HX-Trigger": "companyChanged"})
    else:
        form = CompanyProfileForm()
    return render(
        request,
        "clients/partials/ref_form_modal.html",
        {
            "form": form,
            "title": "기업 추가",
            "post_url": "/reference/companies/new/",
            "show_autofill": True,
        },
    )


@staff_member_required
def company_update(request, pk):
    """Update a company."""
    obj = get_object_or_404(CompanyProfile, pk=pk)
    if request.method == "POST":
        form = CompanyProfileForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={"HX-Trigger": "companyChanged"})
    else:
        form = CompanyProfileForm(instance=obj)
    return render(
        request,
        "clients/partials/ref_form_modal.html",
        {
            "form": form,
            "title": "기업 수정",
            "post_url": f"/reference/companies/{pk}/edit/",
            "show_autofill": True,
        },
    )


@staff_member_required
def company_delete(request, pk):
    """Delete a company."""
    if request.method != "POST":
        return HttpResponse(status=405)
    obj = get_object_or_404(CompanyProfile, pk=pk)
    obj.delete()
    return HttpResponse(status=204, headers={"HX-Trigger": "companyChanged"})


@staff_member_required
def company_autofill(request):
    """Autofill company fields using Gemini web search.

    Accepts company name via POST body. Does NOT require an existing CompanyProfile.
    Returns JSON with field values to populate the form.
    """
    import json

    from .services.company_autofill import autofill_company

    if request.method != "POST":
        return HttpResponse(status=405)

    company_name = request.POST.get("name", "").strip()
    if not company_name:
        return HttpResponse(
            json.dumps({"error": "회사명을 입력해 주세요."}, ensure_ascii=False),
            content_type="application/json",
            status=400,
        )

    try:
        result = autofill_company(company_name)
        return HttpResponse(
            json.dumps(result, ensure_ascii=False),
            content_type="application/json",
        )
    except Exception:
        return HttpResponse(
            json.dumps(
                {"error": "자동채움에 실패했습니다. 직접 입력해 주세요."},
                ensure_ascii=False,
            ),
            content_type="application/json",
            status=500,
        )


@staff_member_required
def company_import(request):
    """Import companies from CSV."""
    if request.method != "POST":
        return HttpResponse(status=405)
    form = CSVImportForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(
            request,
            "clients/partials/ref_import_result.html",
            {"errors": ["파일을 선택해 주세요."]},
        )
    csv_file = request.FILES["csv_file"]
    try:
        content = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return render(
            request,
            "clients/partials/ref_import_result.html",
            {"errors": ["UTF-8 인코딩이 아닙니다."]},
        )
    result = import_csv(CompanyProfile, io.StringIO(content))
    return render(request, "clients/partials/ref_import_result.html", result)


@login_required
@membership_required
def company_export(request):
    """Export companies to CSV."""
    qs = CompanyProfile.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(name_en__icontains=q))
    listed = request.GET.get("listed", "").strip()
    if listed:
        qs = qs.filter(listed=listed)
    size = request.GET.get("size", "").strip()
    if size:
        qs = qs.filter(size_category=size)

    output = export_csv(CompanyProfile, qs)
    response = HttpResponse(
        output.getvalue(), content_type="text/csv; charset=utf-8-sig"
    )
    response["Content-Disposition"] = 'attachment; filename="companies.csv"'
    return response


# --- Cert views ---


@login_required
@membership_required
def reference_certs(request):
    """Cert tab content."""
    qs = PreferredCert.objects.all()
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    level = request.GET.get("level", "").strip()

    if q:
        # Note: aliases__icontains searches the serialized JSON text.
        # This is a practical approximation for short alias tokens.
        # For exact array element matching, use PostgreSQL jsonb @> operator.
        qs = qs.filter(
            Q(name__icontains=q) | Q(full_name__icontains=q) | Q(aliases__icontains=q)
        )
    if category:
        qs = qs.filter(category=category)
    if level:
        qs = qs.filter(level=level)

    paginator = Paginator(qs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    ctx = {
        "page_obj": page_obj,
        "q": q,
        "category_filter": category,
        "level_filter": level,
        "category_choices": PreferredCert.Category.choices,
        "level_choices": PreferredCert.Level.choices,
        "active_tab": "certs",
        "is_staff": request.user.is_staff,
        "import_form": CSVImportForm(),
    }

    if request.headers.get("HX-Request"):
        return render(request, "clients/partials/ref_certs.html", ctx)
    return _render_reference_page(request, "certs", ctx)


@staff_member_required
def cert_create(request):
    """Create a cert."""
    if request.method == "POST":
        form = PreferredCertForm(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={"HX-Trigger": "certChanged"})
    else:
        form = PreferredCertForm()
    return render(
        request,
        "clients/partials/ref_form_modal.html",
        {"form": form, "title": "자격증 추가", "post_url": "/reference/certs/new/"},
    )


@staff_member_required
def cert_update(request, pk):
    """Update a cert."""
    obj = get_object_or_404(PreferredCert, pk=pk)
    if request.method == "POST":
        form = PreferredCertForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={"HX-Trigger": "certChanged"})
    else:
        form = PreferredCertForm(instance=obj)
    return render(
        request,
        "clients/partials/ref_form_modal.html",
        {
            "form": form,
            "title": "자격증 수정",
            "post_url": f"/reference/certs/{pk}/edit/",
        },
    )


@staff_member_required
def cert_delete(request, pk):
    """Delete a cert."""
    if request.method != "POST":
        return HttpResponse(status=405)
    obj = get_object_or_404(PreferredCert, pk=pk)
    obj.delete()
    return HttpResponse(status=204, headers={"HX-Trigger": "certChanged"})


@staff_member_required
def cert_import(request):
    """Import certs from CSV."""
    if request.method != "POST":
        return HttpResponse(status=405)
    form = CSVImportForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(
            request,
            "clients/partials/ref_import_result.html",
            {"errors": ["파일을 선택해 주세요."]},
        )
    csv_file = request.FILES["csv_file"]
    try:
        content = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return render(
            request,
            "clients/partials/ref_import_result.html",
            {"errors": ["UTF-8 인코딩이 아닙니다."]},
        )
    result = import_csv(PreferredCert, io.StringIO(content))
    return render(request, "clients/partials/ref_import_result.html", result)


@login_required
@membership_required
def cert_export(request):
    """Export certs to CSV."""
    qs = PreferredCert.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(full_name__icontains=q) | Q(aliases__icontains=q)
        )
    category = request.GET.get("category", "").strip()
    if category:
        qs = qs.filter(category=category)

    output = export_csv(PreferredCert, qs)
    response = HttpResponse(
        output.getvalue(), content_type="text/csv; charset=utf-8-sig"
    )
    response["Content-Disposition"] = 'attachment; filename="certs.csv"'
    return response


# --- Helper ---


def _render_reference_page(request, active_tab, tab_ctx=None):
    """Render full reference page with tab content."""
    ctx = {"active_tab": active_tab}
    if tab_ctx:
        ctx.update(tab_ctx)
    # No default data loading — each tab view provides its own context
    return render(request, "clients/reference_index.html", ctx)
