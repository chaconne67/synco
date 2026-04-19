import json

from django.contrib.auth.decorators import login_required

from accounts.decorators import membership_required, role_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.helpers import _get_org

from .forms import ClientForm, ContractForm
from .models import Client, Contract, IndustryCategory
from .services.client_queries import (
    available_regions,
    category_counts,
    list_clients_with_stats,
)

CLOSED_STATUSES = ["closed_success", "closed_fail", "closed_cancel", "on_hold"]
PAGE_SIZE = 20
GRID_PAGE_SIZE = 9


def _parse_list_filters(request):
    """GET 파라미터에서 필터 kwargs 추출."""
    def _csv(key):
        v = request.GET.get(key, "").strip()
        return [x for x in v.split(",") if x] if v else None

    cat = request.GET.get("cat", "").strip()
    categories = [cat] if cat else None

    return {
        "categories": categories,
        "sizes": _csv("size"),
        "regions": _csv("region"),
        "offers_range": request.GET.get("offers") or None,
        "success_status": request.GET.get("success") or None,
    }


@login_required
@membership_required
def client_list(request):
    org = _get_org(request)
    filters = _parse_list_filters(request)
    qs = list_clients_with_stats(org, **filters)

    paginator = Paginator(qs, GRID_PAGE_SIZE)
    page_obj = paginator.get_page(1)

    return render(
        request,
        "clients/client_list.html",
        {
            "page_obj": page_obj,
            "total": qs.count(),
            "cat_counts": category_counts(org),
            "regions": available_regions(org),
            "filters": filters,
            "active_cat": request.GET.get("cat", ""),
            "industry_categories": [
                {"name": c.name, "label": c.label} for c in IndustryCategory
            ],
        },
    )


@login_required
@membership_required
def client_list_page(request):
    """Infinite scroll 페이지 응답 (카드 + 다음 sentinel)."""
    org = _get_org(request)
    filters = _parse_list_filters(request)
    qs = list_clients_with_stats(org, **filters)
    paginator = Paginator(qs, GRID_PAGE_SIZE)
    page_number = int(request.GET.get("page", "2"))
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "clients/partials/client_list_page.html",
        {"page_obj": page_obj, "filters": filters},
    )


@login_required
@role_required("owner")
def client_create(request):
    """Create a new client. GET=form, POST=save."""
    org = _get_org(request)

    cp_json_str = "[]"
    if request.method == "POST":
        form = ClientForm(request.POST)
        cp_json_str = request.POST.get("contact_persons_json", "[]")
        if form.is_valid():
            client = form.save(commit=False)
            client.organization = org
            # Parse contact_persons from hidden JSON input
            try:
                client.contact_persons = json.loads(cp_json_str)
            except (json.JSONDecodeError, TypeError):
                client.contact_persons = []
            client.save()
            return redirect("clients:client_detail", pk=client.pk)
    else:
        form = ClientForm()

    return render(
        request,
        "clients/client_form.html",
        {"form": form, "is_edit": False, "contact_persons_json": cp_json_str},
    )


@login_required
@membership_required
def client_detail(request, pk):
    """Client detail with contracts and active projects."""
    org = _get_org(request)
    client = get_object_or_404(Client, pk=pk, organization=org)
    contracts = client.contracts.all()
    active_projects = client.projects.exclude(status__in=CLOSED_STATUSES)

    contract_form = ContractForm()

    return render(
        request,
        "clients/client_detail.html",
        {
            "client": client,
            "contracts": contracts,
            "active_projects": active_projects,
            "contract_form": contract_form,
        },
    )


@login_required
@role_required("owner")
def client_update(request, pk):
    """Update an existing client."""
    org = _get_org(request)
    client = get_object_or_404(Client, pk=pk, organization=org)

    if request.method == "POST":
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            client = form.save(commit=False)
            cp_json = request.POST.get("contact_persons_json", "[]")
            try:
                client.contact_persons = json.loads(cp_json)
            except (json.JSONDecodeError, TypeError):
                pass  # keep existing contact_persons
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


@login_required
@role_required("owner")
def client_delete(request, pk):
    """Delete a client. Block if active projects exist."""
    if request.method != "POST":
        return HttpResponse(status=405)

    org = _get_org(request)
    client = get_object_or_404(Client, pk=pk, organization=org)
    active_projects = client.projects.exclude(status__in=CLOSED_STATUSES)

    if active_projects.exists():
        return render(
            request,
            "clients/client_detail.html",
            {
                "client": client,
                "contracts": client.contracts.all(),
                "active_projects": active_projects,
                "contract_form": ContractForm(),
                "error_message": "진행중인 프로젝트가 있어 삭제할 수 없습니다.",
            },
        )

    client.delete()
    return redirect("clients:client_list")


# --- Contract inline CRUD ---


@login_required
@role_required("owner")
def contract_create(request, pk):
    """Create a contract for a client (inline)."""
    org = _get_org(request)
    client = get_object_or_404(Client, pk=pk, organization=org)

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


@login_required
@role_required("owner")
def contract_update(request, pk, contract_pk):
    """Update a contract (inline)."""
    org = _get_org(request)
    client = get_object_or_404(Client, pk=pk, organization=org)
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


@login_required
@role_required("owner")
def contract_delete(request, pk, contract_pk):
    """Delete a contract (inline)."""
    if request.method != "POST":
        return HttpResponse(status=405)

    org = _get_org(request)
    client = get_object_or_404(Client, pk=pk, organization=org)
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
