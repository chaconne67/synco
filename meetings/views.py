from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from contacts.models import Contact

from .models import Meeting


MEETING_PAGE_SIZE = 20


@login_required
def meeting_list(request):
    meetings = Meeting.objects.filter(
        fc=request.user,
        status=Meeting.Status.SCHEDULED,
    ).select_related("contact")

    page = int(request.GET.get("page", 1))
    offset = (page - 1) * MEETING_PAGE_SIZE
    page_meetings = meetings[offset : offset + MEETING_PAGE_SIZE]
    has_more = meetings[
        offset + MEETING_PAGE_SIZE : offset + MEETING_PAGE_SIZE + 1
    ].exists()

    template = (
        "meetings/partials/meeting_list_content.html"
        if request.htmx
        else "meetings/meeting_list.html"
    )
    return render(
        request,
        template,
        {
            "meetings": page_meetings,
            "page": page,
            "has_more": has_more,
        },
    )


@login_required
def meeting_create(request):
    if request.method == "POST":
        contact = get_object_or_404(
            Contact, pk=request.POST["contact_id"], fc=request.user
        )
        meeting = Meeting.objects.create(
            fc=request.user,
            contact=contact,
            title=request.POST.get("title", f"{contact.name}님 미팅"),
            scheduled_at=request.POST["scheduled_at"],
            scheduled_end_at=request.POST["scheduled_end_at"],
            location=request.POST.get("location", ""),
        )
        if request.htmx:
            return HttpResponse(
                status=204,
                headers={"HX-Redirect": f"/meetings/{meeting.pk}/"},
            )
        return redirect("meetings:detail", pk=meeting.pk)

    contacts = Contact.objects.filter(fc=request.user)
    contact_id = request.GET.get("contact")
    selected_contact = None
    if contact_id:
        selected_contact = Contact.objects.filter(
            pk=contact_id, fc=request.user
        ).first()

    template = (
        "meetings/partials/meeting_form_content.html"
        if request.htmx
        else "meetings/meeting_form.html"
    )
    return render(
        request,
        template,
        {
            "contacts": contacts,
            "selected_contact": selected_contact,
        },
    )


@login_required
def meeting_detail(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk, fc=request.user)
    from contacts.models import Interaction

    meeting_memo = Interaction.objects.filter(meeting=meeting).first()

    template = (
        "meetings/partials/meeting_detail_content.html"
        if request.htmx
        else "meetings/meeting_detail.html"
    )
    return render(
        request,
        template,
        {
            "meeting": meeting,
            "meeting_memo": meeting_memo,
        },
    )


@login_required
def meeting_edit(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk, fc=request.user)

    if request.method == "POST":
        meeting.title = request.POST.get("title", meeting.title)
        meeting.scheduled_at = request.POST["scheduled_at"]
        meeting.scheduled_end_at = request.POST["scheduled_end_at"]
        meeting.location = request.POST.get("location", "")
        meeting.save()

        if request.htmx:
            return HttpResponse(
                status=204,
                headers={"HX-Redirect": f"/meetings/{meeting.pk}/"},
            )
        return redirect("meetings:detail", pk=meeting.pk)

    contacts = Contact.objects.filter(fc=request.user)
    template = (
        "meetings/partials/meeting_form_content.html"
        if request.htmx
        else "meetings/meeting_form.html"
    )
    return render(
        request,
        template,
        {
            "meeting": meeting,
            "contacts": contacts,
            "selected_contact": meeting.contact,
            "editing": True,
        },
    )


@login_required
def meeting_cancel(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk, fc=request.user)
    if request.method == "POST":
        meeting.status = Meeting.Status.CANCELLED
        meeting.save(update_fields=["status"])
        if request.htmx:
            return HttpResponse(
                status=204,
                headers={"HX-Redirect": "/meetings/"},
            )
    return redirect("meetings:list")


@login_required
def meeting_delete(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk, fc=request.user)
    if request.method == "POST":
        meeting.delete()
        if request.htmx:
            return HttpResponse(
                status=204,
                headers={"HX-Redirect": "/meetings/"},
            )
        return redirect("meetings:list")
    return redirect("meetings:detail", pk=pk)
