import json

from accounts.decorators import level_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ClientForm, ContractForm
from .models import Client, Contract, IndustryCategory
from .services.client_create import apply_logo_upload, normalize_contact_persons
from .services.client_queries import (
    available_regions,
    category_counts,
    client_projects,
    client_stats,
    list_clients_with_stats,
)

PAGE_SIZE = 20
GRID_PAGE_SIZE = 9

SIZE_CHOICES = [s.value for s in Client.Size]
OFFERS_OPTIONS = [
    {"value": "", "label": "전체"},
    {"value": "0", "label": "0건"},
    {"value": "1-5", "label": "1–5건"},
    {"value": "6-10", "label": "6–10건"},
    {"value": "10+", "label": "10건+"},
]
SUCCESS_OPTIONS = [
    {"value": "", "label": "전체"},
    {"value": "has", "label": "성사 있음"},
    {"value": "none", "label": "성사 없음"},
    {"value": "no_offers", "label": "거래 없음"},
]


def _parse_list_filters(request):
    """GET 파라미터에서 필터 kwargs 추출."""
    cat = request.GET.get("cat", "").strip()
    categories = [cat] if cat else None

    sizes = request.GET.getlist("size") or None
    regions = request.GET.getlist("region") or None

    return {
        "categories": categories,
        "sizes": sizes,
        "regions": regions,
        "offers_range": request.GET.get("offers") or None,
        "success_status": request.GET.get("success") or None,
    }


@level_required(1)
def client_list(request):
    filters = _parse_list_filters(request)
    qs = list_clients_with_stats(**filters)

    paginator = Paginator(qs, GRID_PAGE_SIZE)
    page_obj = paginator.get_page(1)

    return render(
        request,
        "clients/client_list.html",
        {
            "page_obj": page_obj,
            "total": qs.count(),
            "cat_counts": category_counts(),
            "regions": available_regions(),
            "filters": filters,
            "active_cat": request.GET.get("cat", ""),
            "industry_categories": [
                {"name": c.name, "label": c.label} for c in IndustryCategory
            ],
            "sizes": SIZE_CHOICES,
            "offers_options": OFFERS_OPTIONS,
            "success_options": SUCCESS_OPTIONS,
        },
    )


@level_required(1)
def client_list_page(request):
    """Infinite scroll 페이지 응답 (카드 + 다음 sentinel)."""
    filters = _parse_list_filters(request)
    qs = list_clients_with_stats(**filters)
    paginator = Paginator(qs, GRID_PAGE_SIZE)
    page_number = int(request.GET.get("page", "2"))
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "clients/partials/client_list_page.html",
        {"page_obj": page_obj, "filters": filters},
    )


@level_required(2)
def client_create(request):
    """Create a new client. GET=form, POST=save."""
    cp_json_str = "[]"
    if request.method == "POST":
        form = ClientForm(request.POST, request.FILES)
        cp_json_str = request.POST.get("contact_persons_json", "[]")
        if form.is_valid():
            client = form.save(commit=False)
            try:
                raw = json.loads(cp_json_str)
            except (json.JSONDecodeError, TypeError):
                raw = []
            client.contact_persons = normalize_contact_persons(raw)
            client.save()
            return redirect("clients:client_detail", pk=client.pk)
    else:
        form = ClientForm()

    return render(
        request,
        "clients/client_form.html",
        {"form": form, "is_edit": False, "contact_persons_json": cp_json_str},
    )


@level_required(1)
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    stats = client_stats(client)
    projects = client_projects(client, status_filter="all")[:20]

    return render(
        request,
        "clients/client_detail.html",
        {
            "client": client,
            "contracts": client.contracts.all(),
            "projects": projects,
            "stats": stats,
            "contract_form": ContractForm(),
            "project_status_filter": "all",
        },
    )


@level_required(1)
def client_projects_panel(request, pk):
    client = get_object_or_404(Client, pk=pk)
    status_filter = request.GET.get("status", "all")
    if status_filter not in {"active", "closed", "all"}:
        status_filter = "all"
    projects = client_projects(client, status_filter=status_filter)[:20]
    return render(
        request,
        "clients/partials/client_projects_panel.html",
        {
            "client": client,
            "projects": projects,
            "project_status_filter": status_filter,
            "stats": client_stats(client),
        },
    )


@level_required(2)
def client_update(request, pk):
    """Update an existing client."""
    client = get_object_or_404(Client, pk=pk)

    if request.method == "POST":
        form = ClientForm(request.POST, request.FILES, instance=client)
        if (
            request.POST.get("logo-clear") == "on"
            and client.logo
            and not request.FILES.get("logo")
        ):
            apply_logo_upload(client, None, delete=True)
        if form.is_valid():
            client = form.save(commit=False)
            cp_json = request.POST.get("contact_persons_json", "[]")
            try:
                raw = json.loads(cp_json)
            except (json.JSONDecodeError, TypeError):
                raw = []
            client.contact_persons = normalize_contact_persons(raw)
            client.save()
            return redirect("clients:client_detail", pk=client.pk)
    else:
        form = ClientForm(instance=client)

    return render(
        request,
        "clients/client_form.html",
        {
            "form": form,
            "client": client,
            "is_edit": True,
            "contact_persons_json": json.dumps(client.contact_persons or []),
        },
    )


@level_required(2)
def client_delete(request, pk):
    """Delete a client. Block if any projects exist (open or closed)."""
    if request.method != "POST":
        return HttpResponse(status=405)

    client = get_object_or_404(Client, pk=pk)

    if client.projects.exists():
        return render(
            request,
            "clients/client_detail.html",
            {
                "client": client,
                "contracts": client.contracts.all(),
                "projects": client_projects(client, status_filter="all")[:20],
                "stats": client_stats(client),
                "contract_form": ContractForm(),
                "project_status_filter": "all",
                "error_message": (
                    f"연결된 프로젝트 {client.projects.count()}건이 있어 삭제할 수 없습니다. "
                    "프로젝트를 먼저 정리하거나 조직 관리자에게 문의하세요."
                ),
            },
        )

    client.delete()
    return redirect("clients:client_list")


# --- Contract inline CRUD ---


@level_required(2)
def contract_create(request, pk):
    """Create a contract for a client (inline)."""
    client = get_object_or_404(Client, pk=pk)

    if request.method == "POST":
        form = ContractForm(request.POST)
        if form.is_valid():
            contract = form.save(commit=False)
            contract.client = client
            contract.save()

            # Return the updated contract section
            contracts = client.contracts.all()
            return render(
                request,
                "clients/partials/contract_section.html",
                {
                    "client": client,
                    "contracts": contracts,
                    "contract_form": ContractForm(),
                },
            )
    else:
        form = ContractForm()

    return render(
        request,
        "clients/partials/contract_section.html",
        {
            "client": client,
            "contracts": client.contracts.all(),
            "contract_form": form,
            "show_form": True,
        },
    )


@level_required(2)
def contract_update(request, pk, contract_pk):
    """Update a contract (inline)."""
    client = get_object_or_404(Client, pk=pk)
    contract = get_object_or_404(Contract, pk=contract_pk, client=client)

    if request.method == "POST":
        form = ContractForm(request.POST, instance=contract)
        if form.is_valid():
            form.save()
            contracts = client.contracts.all()
            return render(
                request,
                "clients/partials/contract_section.html",
                {
                    "client": client,
                    "contracts": contracts,
                    "contract_form": ContractForm(),
                },
            )
    else:
        form = ContractForm(instance=contract)

    return render(
        request,
        "clients/partials/contract_section.html",
        {
            "client": client,
            "contracts": client.contracts.all(),
            "contract_form": ContractForm(),
            "edit_contract": contract,
            "edit_form": form,
        },
    )


@level_required(2)
def contract_delete(request, pk, contract_pk):
    """Delete a contract (inline)."""
    if request.method != "POST":
        return HttpResponse(status=405)

    client = get_object_or_404(Client, pk=pk)
    contract = get_object_or_404(Contract, pk=contract_pk, client=client)
    contract.delete()

    contracts = client.contracts.all()
    return render(
        request,
        "clients/partials/contract_section.html",
        {
            "client": client,
            "contracts": contracts,
            "contract_form": ContractForm(),
        },
    )
