# P06: Contact Management — 확정 구현계획서

> **Phase:** 6 / 6
> **선행조건:** P05 (프로젝트 상세 탭 구조 — 컨택 탭 골격 존재)
> **산출물:** 컨택 탭 완성 + 컨택 예정 잠금 + 중복 방지 시스템 + 서칭 탭 연동

---

## 범위 정의

### IN (P06)
- Contact 모델 확장 (RESERVED choice, 필드 nullable 변경)
- 컨택 기록 CRUD (등록/수정/삭제)
- 컨택 예정 등록 (잠금 메커니즘) — 서칭 탭에서 진입
- 잠금 자동 해제 (만료 시 locked_until 리셋)
- 중복 방지 (result별 차단/경고 분기)
- 컨택 탭 완성 UI (완료 목록 + 예정 목록)
- 서칭 탭 연동 (체크박스 + 상태 표시 + 컨택 예정 등록 버튼)
- 조직 격리 적용

### OUT (후속)
- Submission 생성 연결 ("추천 서류 작성" 버튼은 비활성 placeholder)
- management command로 자동 해제 cron 등록
- 전용 활동 로그 모델

---

## Step 1: 모델 변경 + Migration

### projects/models.py 수정

```python
class Contact(BaseModel):
    """컨택 이력."""

    class Channel(models.TextChoices):
        PHONE = "전화", "전화"
        SMS = "문자", "문자"
        KAKAO = "카톡", "카톡"
        EMAIL = "이메일", "이메일"
        LINKEDIN = "LinkedIn", "LinkedIn"

    class Result(models.TextChoices):
        RESPONDED = "응답", "응답"
        NO_RESPONSE = "미응답", "미응답"
        REJECTED = "거절", "거절"
        INTERESTED = "관심", "관심"
        ON_HOLD = "보류", "보류"
        RESERVED = "예정", "예정"  # P06: 컨택 예정(잠금)

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="contacts",
    )
    candidate = models.ForeignKey(
        "candidates.Candidate", on_delete=models.CASCADE, related_name="project_contacts",
    )
    consultant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="contacts",
    )
    channel = models.CharField(max_length=20, choices=Channel.choices, blank=True)  # P06: blank 허용 (예정 등록 시)
    contacted_at = models.DateTimeField(null=True, blank=True)  # P06: nullable (예정 등록 시)
    result = models.CharField(max_length=20, choices=Result.choices)
    notes = models.TextField(blank=True)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-contacted_at"]

    def __str__(self) -> str:
        return f"{self.project} - {self.candidate} ({self.channel})"

    @property
    def is_reserved(self) -> bool:
        """예정 상태이고 잠금이 유효한지."""
        from django.utils import timezone
        return (
            self.result == self.Result.RESERVED
            and self.locked_until is not None
            and self.locked_until > timezone.now()
        )

    @property
    def is_expired_reservation(self) -> bool:
        """만료된 예정인지."""
        from django.utils import timezone
        return (
            self.result == self.Result.RESERVED
            and (self.locked_until is None or self.locked_until <= timezone.now())
        )
```

### Migration

```bash
uv run python manage.py makemigrations projects --name p06_contact_reserved_nullable
uv run python manage.py migrate
```

### 테스트

```python
def test_contact_result_reserved_choice():
    """Contact.Result에 RESERVED choice 존재."""
    assert "예정" in Contact.Result.values

def test_contact_channel_blank_allowed():
    """channel이 blank 허용."""
    contact = Contact(
        project=project, candidate=candidate, consultant=user,
        channel="", result=Contact.Result.RESERVED,
    )
    contact.full_clean()  # should not raise

def test_contact_contacted_at_nullable():
    """contacted_at이 null 허용."""
    contact = Contact(
        project=project, candidate=candidate, consultant=user,
        result=Contact.Result.RESERVED,
        contacted_at=None,
    )
    contact.full_clean()  # should not raise
```

---

## Step 2: 서비스 레이어

### projects/services/contact.py (신규)

```python
"""컨택 중복 체크 + 잠금 관리 서비스."""
from datetime import timedelta

from django.utils import timezone

from projects.models import Contact


LOCK_DURATION_DAYS = 7

# 차단 결과: 이미 명확한 의사 표시가 있는 경우
BLOCKING_RESULTS = {Contact.Result.INTERESTED, Contact.Result.REJECTED}

# 경고 결과: 재컨택 허용
WARNING_RESULTS = {
    Contact.Result.RESPONDED,
    Contact.Result.NO_RESPONSE,
    Contact.Result.ON_HOLD,
}


def check_duplicate(project, candidate):
    """
    중복 컨택 체크. 반환값:
    {
        "blocked": bool,       # True이면 저장 불가
        "warnings": list[str], # 경고 메시지 목록
        "other_projects": list[Contact],  # 다른 프로젝트의 컨택 이력
    }
    """
    result = {
        "blocked": False,
        "warnings": [],
        "other_projects": [],
    }

    # 같은 프로젝트 내 동일 후보자 컨택 이력
    same_project_contacts = Contact.objects.filter(
        project=project,
        candidate=candidate,
    ).exclude(result=Contact.Result.RESERVED).select_related("consultant")

    for contact in same_project_contacts:
        if contact.result in BLOCKING_RESULTS:
            result["blocked"] = True
            result["warnings"].append(
                f"이미 '{contact.get_result_display()}' 결과로 컨택된 후보자입니다. "
                f"(담당: {contact.consultant}, {contact.contacted_at:%m/%d})"
            )
        elif contact.result in WARNING_RESULTS:
            result["warnings"].append(
                f"이전 컨택 이력이 있습니다: {contact.get_result_display()} "
                f"(담당: {contact.consultant}, {contact.contacted_at:%m/%d})"
            )

    # 같은 프로젝트 내 예정(잠금) 체크
    reserved = Contact.objects.filter(
        project=project,
        candidate=candidate,
        result=Contact.Result.RESERVED,
        locked_until__gt=timezone.now(),
    ).select_related("consultant").first()

    if reserved:
        result["warnings"].append(
            f"{reserved.consultant}이(가) 컨택 예정 등록 "
            f"(잠금 만료: {reserved.locked_until:%m/%d})"
        )

    # 다른 프로젝트의 컨택 이력
    other_contacts = (
        Contact.objects.filter(candidate=candidate)
        .exclude(project=project)
        .exclude(result=Contact.Result.RESERVED)
        .select_related("project", "consultant")
        .order_by("-contacted_at")[:5]
    )
    result["other_projects"] = list(other_contacts)

    return result


def reserve_candidates(project, candidate_ids, consultant):
    """
    후보자들을 컨택 예정 등록(잠금).
    반환: {"created": list, "skipped": list[str]}
    """
    created = []
    skipped = []
    now = timezone.now()
    lock_until = now + timedelta(days=LOCK_DURATION_DAYS)

    for cid in candidate_ids:
        # 이미 잠금 또는 컨택 완료(차단 결과) 존재 시 skip
        existing = Contact.objects.filter(
            project=project,
            candidate_id=cid,
        ).filter(
            # 유효한 예정 또는 차단 결과
            models.Q(result=Contact.Result.RESERVED, locked_until__gt=now)
            | models.Q(result__in=list(BLOCKING_RESULTS))
        ).exists()

        if existing:
            from candidates.models import Candidate
            try:
                name = Candidate.objects.get(pk=cid).name
            except Candidate.DoesNotExist:
                name = str(cid)
            skipped.append(name)
            continue

        contact = Contact.objects.create(
            project=project,
            candidate_id=cid,
            consultant=consultant,
            result=Contact.Result.RESERVED,
            locked_until=lock_until,
            channel="",
            contacted_at=None,
        )
        created.append(contact)

    return {"created": created, "skipped": skipped}


def release_expired_reservations():
    """만료된 예정 건의 잠금 해제 (locked_until 리셋)."""
    return Contact.objects.filter(
        result=Contact.Result.RESERVED,
        locked_until__lt=timezone.now(),
    ).update(locked_until=None)
```

### 테스트

```python
class TestCheckDuplicate:
    def test_blocking_result_blocks(self):
        """관심/거절 결과 후보자는 차단."""
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            channel="전화", contacted_at=now, result="관심",
        )
        result = check_duplicate(project, candidate)
        assert result["blocked"] is True

    def test_warning_result_allows(self):
        """응답/미응답/보류 결과 후보자는 경고만."""
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            channel="전화", contacted_at=now, result="미응답",
        )
        result = check_duplicate(project, candidate)
        assert result["blocked"] is False
        assert len(result["warnings"]) == 1

    def test_reserved_shows_warning(self):
        """예정 등록된 후보자는 경고."""
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            result="예정", locked_until=now + timedelta(days=7),
        )
        result = check_duplicate(project, candidate)
        assert result["blocked"] is False
        assert any("컨택 예정" in w for w in result["warnings"])

    def test_other_project_contacts(self):
        """다른 프로젝트 컨택 이력 표시."""
        Contact.objects.create(
            project=other_project, candidate=candidate, consultant=user,
            channel="이메일", contacted_at=now, result="응답",
        )
        result = check_duplicate(project, candidate)
        assert len(result["other_projects"]) == 1


class TestReserveCandidates:
    def test_creates_reservation(self):
        """정상 예정 등록."""
        result = reserve_candidates(project, [candidate.pk], user)
        assert len(result["created"]) == 1
        contact = result["created"][0]
        assert contact.result == "예정"
        assert contact.locked_until is not None

    def test_skips_already_reserved(self):
        """이미 잠긴 후보자는 skip."""
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            result="예정", locked_until=now + timedelta(days=7),
        )
        result = reserve_candidates(project, [candidate.pk], user)
        assert len(result["skipped"]) == 1

    def test_skips_blocking_result(self):
        """차단 결과 후보자는 skip."""
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            channel="전화", contacted_at=now, result="관심",
        )
        result = reserve_candidates(project, [candidate.pk], user)
        assert len(result["skipped"]) == 1


class TestReleaseExpired:
    def test_releases_expired(self):
        """만료된 예정 건의 locked_until 리셋."""
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            result="예정", locked_until=now - timedelta(days=1),
        )
        count = release_expired_reservations()
        assert count == 1
        contact = Contact.objects.get(project=project, candidate=candidate)
        assert contact.locked_until is None

    def test_keeps_valid_reservations(self):
        """유효한 예정 건은 유지."""
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            result="예정", locked_until=now + timedelta(days=3),
        )
        count = release_expired_reservations()
        assert count == 0
```

---

## Step 3: ContactForm

### projects/forms.py 추가

```python
from .models import Contact

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
```

### 테스트

```python
class TestContactForm:
    def test_valid_form(self):
        """정상 폼 제출."""
        form = ContactForm(data={
            "candidate": candidate.pk,
            "channel": "전화",
            "contacted_at": "2026-04-08T10:00",
            "result": "응답",
            "notes": "통화 완료",
        }, organization=org)
        assert form.is_valid()

    def test_reserved_not_in_choices(self):
        """예정 결과는 폼 선택지에 없음."""
        form = ContactForm(organization=org)
        result_values = [v for v, _ in form.fields["result"].choices]
        assert "예정" not in result_values

    def test_candidate_org_isolation(self):
        """타 조직 후보자가 드롭다운에 없음."""
        form = ContactForm(organization=org)
        qs = form.fields["candidate"].queryset
        assert candidate_other_org not in qs

    def test_channel_required_for_actual_contact(self):
        """실제 컨택 시 채널 필수."""
        form = ContactForm(data={
            "candidate": candidate.pk,
            "channel": "",
            "contacted_at": "2026-04-08T10:00",
            "result": "응답",
        }, organization=org)
        assert not form.is_valid()
        assert "channel" in form.errors
```

---

## Step 4: View 구현

### projects/views.py 추가

```python
from django.db import models as db_models

from .forms import ContactForm
from .models import Contact


@login_required
def project_tab_contacts(request, pk):
    """컨택 탭: 완료 목록 + 예정 목록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    # 만료 예정 건 잠금 해제
    from projects.services.contact import release_expired_reservations
    release_expired_reservations()

    # 실제 컨택 완료 목록 (예정 제외)
    completed_contacts = (
        project.contacts
        .exclude(result=Contact.Result.RESERVED)
        .select_related("candidate", "consultant")
        .order_by("-contacted_at")
    )

    # 컨택 예정(잠금) 목록 — 유효한 것만
    from django.utils import timezone
    reserved_contacts = (
        project.contacts
        .filter(result=Contact.Result.RESERVED, locked_until__gt=timezone.now())
        .select_related("candidate", "consultant")
        .order_by("-created_at")
    )

    # 만료된 예정 목록
    expired_contacts = (
        project.contacts
        .filter(result=Contact.Result.RESERVED)
        .filter(db_models.Q(locked_until__isnull=True) | db_models.Q(locked_until__lte=timezone.now()))
        .select_related("candidate", "consultant")
        .order_by("-created_at")
    )

    return render(
        request,
        "projects/partials/tab_contacts.html",
        {
            "project": project,
            "completed_contacts": completed_contacts,
            "reserved_contacts": reserved_contacts,
            "expired_contacts": expired_contacts,
            "can_release": request.user in project.assigned_consultants.all(),
        },
    )


@login_required
def contact_create(request, pk):
    """컨택 기록 등록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if request.method == "POST":
        form = ContactForm(request.POST, organization=org)
        if form.is_valid():
            # 중복 체크
            from projects.services.contact import check_duplicate
            dup = check_duplicate(project, form.cleaned_data["candidate"])
            if dup["blocked"]:
                return render(request, "projects/partials/contact_form.html", {
                    "form": form,
                    "project": project,
                    "is_edit": False,
                    "duplicate_warnings": dup["warnings"],
                    "blocked": True,
                })

            contact = form.save(commit=False)
            contact.project = project
            contact.consultant = request.user
            contact.save()

            # 같은 후보자의 예정 건이 있으면 해제 (결과 기록 시 잠금 자동 해제)
            Contact.objects.filter(
                project=project,
                candidate=contact.candidate,
                result=Contact.Result.RESERVED,
            ).exclude(pk=contact.pk).update(
                locked_until=None,
            )

            # 컨택 탭 새로고침
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "contactChanged"},
            )
    else:
        form = ContactForm(organization=org)

    # 프리필: query param으로 candidate 전달 시
    candidate_id = request.GET.get("candidate")
    if candidate_id and not request.method == "POST":
        form.initial["candidate"] = candidate_id
        # 중복 체크 결과도 미리 표시
        from projects.services.contact import check_duplicate
        from candidates.models import Candidate
        try:
            candidate_obj = Candidate.objects.get(pk=candidate_id, owned_by=org)
            dup = check_duplicate(project, candidate_obj)
        except Candidate.DoesNotExist:
            dup = None
    else:
        dup = None

    return render(request, "projects/partials/contact_form.html", {
        "form": form,
        "project": project,
        "is_edit": False,
        "duplicate_warnings": dup["warnings"] if dup else [],
        "other_project_contacts": dup["other_projects"] if dup else [],
        "blocked": dup["blocked"] if dup else False,
    })


@login_required
def contact_update(request, pk, contact_pk):
    """컨택 기록 수정."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    contact = get_object_or_404(Contact, pk=contact_pk, project=project)

    if request.method == "POST":
        form = ContactForm(request.POST, instance=contact, organization=org)
        if form.is_valid():
            form.save()
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "contactChanged"},
            )
    else:
        form = ContactForm(instance=contact, organization=org)

    return render(request, "projects/partials/contact_form.html", {
        "form": form,
        "project": project,
        "contact": contact,
        "is_edit": True,
    })


@login_required
@require_http_methods(["POST"])
def contact_delete(request, pk, contact_pk):
    """컨택 기록 삭제."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    contact = get_object_or_404(Contact, pk=contact_pk, project=project)
    contact.delete()
    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "contactChanged"},
    )


@login_required
@require_http_methods(["POST"])
def contact_reserve(request, pk):
    """컨택 예정 등록 (잠금). 서칭 탭에서 체크박스 선택 후 호출."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    candidate_ids = request.POST.getlist("candidate_ids")
    if not candidate_ids:
        return HttpResponse("후보자를 선택해주세요.", status=400)

    from projects.services.contact import reserve_candidates
    result = reserve_candidates(project, candidate_ids, request.user)

    # 서칭 탭 새로고침을 위한 HX-Trigger
    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "contactChanged"},
    )


@login_required
@require_http_methods(["POST"])
def contact_release_lock(request, pk, contact_pk):
    """잠금 해제. 담당 컨설턴트만 가능."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    contact = get_object_or_404(
        Contact, pk=contact_pk, project=project, result=Contact.Result.RESERVED,
    )

    # 권한 체크: 담당 컨설턴트이거나 잠금 본인
    if (
        request.user not in project.assigned_consultants.all()
        and request.user != contact.consultant
    ):
        return HttpResponse("잠금 해제 권한이 없습니다.", status=403)

    contact.locked_until = None
    contact.save(update_fields=["locked_until"])

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "contactChanged"},
    )


@login_required
def contact_check_duplicate(request, pk):
    """중복 체크 (HTMX partial). 후보자 드롭다운 변경 시 호출."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    candidate_id = request.GET.get("candidate")
    if not candidate_id:
        return HttpResponse("")

    from candidates.models import Candidate
    from projects.services.contact import check_duplicate

    try:
        candidate = Candidate.objects.get(pk=candidate_id, owned_by=org)
    except Candidate.DoesNotExist:
        return HttpResponse("")

    dup = check_duplicate(project, candidate)

    return render(request, "projects/partials/duplicate_check_result.html", {
        "duplicate": dup,
        "project": project,
    })
```

### 테스트

```python
class TestContactCRUD:
    def test_create_contact(self):
        """컨택 등록 성공."""
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/new/",
            {"candidate": candidate.pk, "channel": "전화",
             "contacted_at": "2026-04-08T10:00", "result": "응답"},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        assert Contact.objects.filter(project=project, candidate=candidate).exists()

    def test_create_blocked_by_duplicate(self):
        """관심 결과 존재 시 등록 차단."""
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            channel="전화", contacted_at=now, result="관심",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/new/",
            {"candidate": candidate.pk, "channel": "이메일",
             "contacted_at": "2026-04-09T10:00", "result": "응답"},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200  # re-render form with error
        assert "이미" in resp.content.decode()

    def test_update_contact(self):
        """컨택 수정 성공."""
        contact = Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            channel="전화", contacted_at=now, result="미응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {"candidate": candidate.pk, "channel": "전화",
             "contacted_at": "2026-04-08T10:00", "result": "응답",
             "notes": "통화 완료"},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        contact.refresh_from_db()
        assert contact.result == "응답"

    def test_delete_contact(self):
        """컨택 삭제 성공."""
        contact = Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            channel="전화", contacted_at=now, result="미응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/delete/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        assert not Contact.objects.filter(pk=contact.pk).exists()

    def test_tab_contacts_separates_completed_and_reserved(self):
        """컨택 탭이 완료와 예정을 분리."""
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            channel="전화", contacted_at=now, result="응답",
        )
        Contact.objects.create(
            project=project, candidate=candidate2, consultant=user,
            result="예정", locked_until=now + timedelta(days=7),
        )
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/contacts/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        content = resp.content.decode()
        assert candidate.name in content
        assert candidate2.name in content


class TestContactReserve:
    def test_reserve_creates_locked_contact(self):
        """컨택 예정 등록 시 잠금 설정."""
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/reserve/",
            {"candidate_ids": [str(candidate.pk)]},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        contact = Contact.objects.get(project=project, candidate=candidate)
        assert contact.result == "예정"
        assert contact.locked_until > now

    def test_reserve_skips_already_reserved(self):
        """이미 잠긴 후보자는 skip."""
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            result="예정", locked_until=now + timedelta(days=7),
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/reserve/",
            {"candidate_ids": [str(candidate.pk)]},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        assert Contact.objects.filter(
            project=project, candidate=candidate, result="예정",
        ).count() == 1  # 추가 생성 안 됨


class TestContactReleaseLock:
    def test_release_by_consultant(self):
        """담당 컨설턴트가 잠금 해제."""
        contact = Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            result="예정", locked_until=now + timedelta(days=7),
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/release/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        contact.refresh_from_db()
        assert contact.locked_until is None

    def test_release_denied_for_non_consultant(self):
        """비담당자는 잠금 해제 불가."""
        contact = Contact.objects.create(
            project=project, candidate=candidate, consultant=user,
            result="예정", locked_until=now + timedelta(days=7),
        )
        resp = auth_client2.post(  # auth_client2는 다른 사용자 (같은 org이지만 비담당)
            f"/projects/{project.pk}/contacts/{contact.pk}/release/",
            HTTP_HX_REQUEST="true",
        )
        # 다른 org 사용자면 404, 같은 org이지만 비담당이면 403
        assert resp.status_code in (403, 404)


class TestContactOrgIsolation:
    def test_create_other_org_404(self):
        """타 조직 프로젝트에 컨택 등록 시 404."""
        resp = auth_client.get(f"/projects/{project_other_org.pk}/contacts/new/")
        assert resp.status_code == 404

    def test_reserve_other_org_404(self):
        """타 조직 프로젝트에 예정 등록 시 404."""
        resp = auth_client.post(
            f"/projects/{project_other_org.pk}/contacts/reserve/",
            {"candidate_ids": [str(candidate.pk)]},
        )
        assert resp.status_code == 404

    def test_delete_other_org_404(self):
        """타 조직 프로젝트의 컨택 삭제 시 404."""
        resp = auth_client.post(
            f"/projects/{project_other_org.pk}/contacts/{contact_other_org.pk}/delete/",
        )
        assert resp.status_code == 404
```

---

## Step 5: URL 설계

### projects/urls.py 추가

```python
urlpatterns = [
    # 기존 URL 유지...

    # P06: 컨택 관리
    path(
        "<uuid:pk>/contacts/new/",
        views.contact_create,
        name="contact_create",
    ),
    path(
        "<uuid:pk>/contacts/<uuid:contact_pk>/edit/",
        views.contact_update,
        name="contact_update",
    ),
    path(
        "<uuid:pk>/contacts/<uuid:contact_pk>/delete/",
        views.contact_delete,
        name="contact_delete",
    ),
    path(
        "<uuid:pk>/contacts/reserve/",
        views.contact_reserve,
        name="contact_reserve",
    ),
    path(
        "<uuid:pk>/contacts/<uuid:contact_pk>/release/",
        views.contact_release_lock,
        name="contact_release_lock",
    ),
    path(
        "<uuid:pk>/contacts/check-duplicate/",
        views.contact_check_duplicate,
        name="contact_check_duplicate",
    ),
]
```

---

## Step 6: Template 구현

### projects/templates/projects/partials/tab_contacts.html (수정)

```html
<div class="space-y-4" hx-trigger="contactChanged from:body" hx-get="{% url 'projects:project_tab_contacts' project.pk %}" hx-target="#tab-content">

  <!-- 상단: 컨택 등록 버튼 -->
  <div class="flex justify-between items-center">
    <h2 class="text-[15px] font-semibold text-gray-700">컨택 이력</h2>
    <button hx-get="{% url 'projects:contact_create' project.pk %}"
            hx-target="#contact-form-area"
            class="text-[13px] bg-primary text-white px-3 py-1.5 rounded-lg hover:bg-primary-dark transition">
      + 컨택 등록
    </button>
  </div>

  <!-- 폼 삽입 영역 -->
  <div id="contact-form-area"></div>

  <!-- 실제 컨택 완료 목록 -->
  <div class="bg-white rounded-lg border border-gray-100 p-5">
    <h3 class="text-[14px] font-medium text-gray-600 mb-3">컨택 완료 ({{ completed_contacts|length }}건)</h3>

    {% if completed_contacts %}
    <div class="overflow-x-auto">
      <table class="w-full text-[14px]">
        <thead>
          <tr class="border-b border-gray-100">
            <th class="text-left py-2 text-gray-500 font-medium">후보자</th>
            <th class="text-left py-2 text-gray-500 font-medium">채널</th>
            <th class="text-left py-2 text-gray-500 font-medium">결과</th>
            <th class="text-left py-2 text-gray-500 font-medium">컨택일</th>
            <th class="text-left py-2 text-gray-500 font-medium">담당</th>
            <th class="text-right py-2 text-gray-500 font-medium">작업</th>
          </tr>
        </thead>
        <tbody>
          {% for contact in completed_contacts %}
          <tr class="border-b border-gray-50">
            <td class="py-2 text-gray-800 font-medium">{{ contact.candidate.name }}</td>
            <td class="py-2 text-gray-600">{{ contact.get_channel_display }}</td>
            <td class="py-2">
              <span class="text-[13px] px-1.5 py-0.5 rounded
                {% if contact.result == '관심' %}bg-green-50 text-green-600
                {% elif contact.result == '미응답' %}bg-gray-50 text-gray-500
                {% elif contact.result == '거절' %}bg-red-50 text-red-500
                {% elif contact.result == '응답' %}bg-blue-50 text-blue-600
                {% else %}bg-yellow-50 text-yellow-600{% endif %}">
                {{ contact.get_result_display }}
              </span>
            </td>
            <td class="py-2 text-gray-500">{{ contact.contacted_at|date:"m/d H:i" }}</td>
            <td class="py-2 text-gray-500">
              {% if contact.consultant %}{{ contact.consultant.get_full_name|default:contact.consultant.username }}{% else %}-{% endif %}
            </td>
            <td class="py-2 text-right">
              <button hx-get="{% url 'projects:contact_update' project.pk contact.pk %}"
                      hx-target="#contact-form-area"
                      class="text-[13px] text-primary hover:text-primary-dark mr-2">수정</button>
              <button hx-post="{% url 'projects:contact_delete' project.pk contact.pk %}"
                      hx-confirm="정말 삭제하시겠습니까?"
                      class="text-[13px] text-red-500 hover:text-red-700">삭제</button>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <p class="text-[14px] text-gray-400">컨택 이력이 없습니다.</p>
    {% endif %}
  </div>

  <!-- 컨택 예정(잠금) 목록 -->
  {% if reserved_contacts %}
  <div class="bg-white rounded-lg border border-amber-100 p-5">
    <h3 class="text-[14px] font-medium text-amber-700 mb-3">컨택 예정 ({{ reserved_contacts|length }}건)</h3>
    <div class="space-y-2">
      {% for contact in reserved_contacts %}
      <div class="flex items-center justify-between py-2 {% if not forloop.last %}border-b border-gray-50{% endif %}">
        <div>
          <span class="text-[14px] font-medium text-gray-800">{{ contact.candidate.name }}</span>
          <span class="text-[13px] text-gray-500 ml-2">
            담당: {% if contact.consultant %}{{ contact.consultant.get_full_name|default:contact.consultant.username }}{% else %}-{% endif %}
          </span>
          <span class="text-[12px] text-amber-600 ml-2">
            잠금 만료: {{ contact.locked_until|date:"m/d H:i" }}
          </span>
        </div>
        <div class="flex items-center gap-2">
          <button hx-get="{% url 'projects:contact_create' project.pk %}?candidate={{ contact.candidate.pk }}"
                  hx-target="#contact-form-area"
                  class="text-[13px] text-primary hover:text-primary-dark">결과 기록</button>
          {% if can_release %}
          <button hx-post="{% url 'projects:contact_release_lock' project.pk contact.pk %}"
                  hx-confirm="잠금을 해제하시겠습니까?"
                  class="text-[13px] text-red-500 hover:text-red-700">잠금 해제</button>
          {% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

</div>
```

### projects/templates/projects/partials/contact_form.html (신규)

```html
<div class="bg-white rounded-lg border border-gray-200 p-5 mb-4">
  <h3 class="text-[15px] font-semibold text-gray-700 mb-4">
    {% if is_edit %}컨택 수정{% else %}컨택 등록{% endif %}
  </h3>

  {% if blocked %}
  <div class="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
    <p class="text-[14px] text-red-600 font-medium">등록이 차단되었습니다.</p>
    {% for warning in duplicate_warnings %}
    <p class="text-[13px] text-red-500 mt-1">{{ warning }}</p>
    {% endfor %}
  </div>
  {% elif duplicate_warnings %}
  <div class="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4">
    {% for warning in duplicate_warnings %}
    <p class="text-[13px] text-amber-700">{{ warning }}</p>
    {% endfor %}
  </div>
  {% endif %}

  {% if other_project_contacts %}
  <div class="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4">
    <p class="text-[13px] text-blue-700 font-medium mb-1">다른 프로젝트 컨택 이력:</p>
    {% for c in other_project_contacts %}
    <p class="text-[12px] text-blue-600">
      {{ c.project.title }} — {{ c.get_result_display }} ({{ c.contacted_at|date:"m/d" }})
    </p>
    {% endfor %}
  </div>
  {% endif %}

  <form {% if is_edit %}
          hx-post="{% url 'projects:contact_update' project.pk contact.pk %}"
        {% else %}
          hx-post="{% url 'projects:contact_create' project.pk %}"
        {% endif %}
        hx-target="#contact-form-area"
        class="space-y-4">
    {% csrf_token %}

    <div>
      <label class="block text-[14px] text-gray-600 mb-1">{{ form.candidate.label }}</label>
      {{ form.candidate }}
      {% if form.candidate.errors %}
      <p class="text-[13px] text-red-500 mt-1">{{ form.candidate.errors.0 }}</p>
      {% endif %}
      <!-- 중복 체크 결과 표시 영역 -->
      <div id="duplicate-check-result"
           hx-get="{% url 'projects:contact_check_duplicate' project.pk %}"
           hx-trigger="change from:previous select"
           hx-include="previous select"
           hx-params="candidate"
           hx-swap="innerHTML"></div>
    </div>

    <div class="grid grid-cols-2 gap-4">
      <div>
        <label class="block text-[14px] text-gray-600 mb-1">{{ form.channel.label }}</label>
        {{ form.channel }}
        {% if form.channel.errors %}
        <p class="text-[13px] text-red-500 mt-1">{{ form.channel.errors.0 }}</p>
        {% endif %}
      </div>
      <div>
        <label class="block text-[14px] text-gray-600 mb-1">{{ form.contacted_at.label }}</label>
        {{ form.contacted_at }}
        {% if form.contacted_at.errors %}
        <p class="text-[13px] text-red-500 mt-1">{{ form.contacted_at.errors.0 }}</p>
        {% endif %}
      </div>
    </div>

    <div>
      <label class="block text-[14px] text-gray-600 mb-1">{{ form.result.label }}</label>
      {{ form.result }}
      {% if form.result.errors %}
      <p class="text-[13px] text-red-500 mt-1">{{ form.result.errors.0 }}</p>
      {% endif %}
    </div>

    <div>
      <label class="block text-[14px] text-gray-600 mb-1">{{ form.notes.label }}</label>
      {{ form.notes }}
    </div>

    <div class="flex justify-end gap-2">
      <button type="button"
              hx-get="{% url 'projects:project_tab_contacts' project.pk %}"
              hx-target="#tab-content"
              class="text-[14px] text-gray-500 px-4 py-2 hover:text-gray-700">
        취소
      </button>
      <button type="submit"
              {% if blocked %}disabled{% endif %}
              class="text-[14px] bg-primary text-white px-4 py-2 rounded-lg hover:bg-primary-dark transition
                {% if blocked %}opacity-50 cursor-not-allowed{% endif %}">
        {% if is_edit %}수정{% else %}등록{% endif %}
      </button>
    </div>
  </form>
</div>
```

### projects/templates/projects/partials/duplicate_check_result.html (신규)

```html
{% if duplicate.blocked %}
<div class="bg-red-50 rounded p-2 mt-1">
  {% for warning in duplicate.warnings %}
  <p class="text-[12px] text-red-600">{{ warning }}</p>
  {% endfor %}
</div>
{% elif duplicate.warnings %}
<div class="bg-amber-50 rounded p-2 mt-1">
  {% for warning in duplicate.warnings %}
  <p class="text-[12px] text-amber-700">{{ warning }}</p>
  {% endfor %}
</div>
{% endif %}

{% if duplicate.other_projects %}
<div class="bg-blue-50 rounded p-2 mt-1">
  <p class="text-[12px] text-blue-700 font-medium">다른 프로젝트 이력:</p>
  {% for c in duplicate.other_projects %}
  <p class="text-[12px] text-blue-600">{{ c.project.title }} — {{ c.get_result_display }}</p>
  {% endfor %}
</div>
{% endif %}
```

---

## Step 7: 서칭 탭 연동

### projects/views.py — project_tab_search 수정

```python
@login_required
def project_tab_search(request, pk):
    """서칭: 매칭 결과 + 컨택 상태 표시 + 예정 등록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    # 만료 예정 건 해제
    from projects.services.contact import release_expired_reservations
    release_expired_reservations()

    results = []
    if project.requirements:
        from projects.services.candidate_matching import match_candidates
        results = match_candidates(
            project.requirements, organization=org, limit=50
        )

        # 컨택 상태 매핑
        from django.utils import timezone
        now = timezone.now()

        # 이 프로젝트의 컨택 이력
        project_contacts = {
            c.candidate_id: c
            for c in project.contacts.select_related("consultant").all()
        }

        # 다른 프로젝트의 컨택 이력 (같은 org)
        candidate_ids = [item["candidate"].pk for item in results]
        other_contacts = (
            Contact.objects.filter(candidate_id__in=candidate_ids)
            .exclude(project=project)
            .exclude(result=Contact.Result.RESERVED)
            .select_related("project", "consultant")
        )
        other_contacts_map = {}
        for c in other_contacts:
            other_contacts_map.setdefault(c.candidate_id, []).append(c)

        for item in results:
            cid = item["candidate"].pk
            contact = project_contacts.get(cid)

            if contact:
                if contact.result == Contact.Result.RESERVED:
                    if contact.locked_until and contact.locked_until > now:
                        item["contact_status"] = "reserved"
                        item["reserved_by"] = contact.consultant
                        item["locked_until"] = contact.locked_until
                        # 다른 컨설턴트의 잠금 시 비활성화
                        item["disabled"] = contact.consultant != request.user
                    else:
                        item["contact_status"] = "expired"
                        item["disabled"] = False
                else:
                    item["contact_status"] = "contacted"
                    item["contact_result"] = contact.get_result_display()
                    item["disabled"] = True
            else:
                item["contact_status"] = None
                item["disabled"] = False

            item["other_project_contacts"] = other_contacts_map.get(cid, [])

    return render(
        request,
        "projects/partials/tab_search.html",
        {
            "project": project,
            "results": results,
            "has_requirements": bool(project.requirements),
        },
    )
```

### projects/templates/projects/partials/tab_search.html (수정)

```html
<div class="space-y-4" hx-trigger="contactChanged from:body" hx-get="{% url 'projects:project_tab_search' project.pk %}" hx-target="#tab-content">

  {% if not has_requirements %}
  <div class="bg-white rounded-lg border border-gray-100 p-8 text-center">
    <svg class="w-12 h-12 text-gray-300 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
    </svg>
    <p class="text-[15px] text-gray-500 mb-1">JD 분석이 먼저 필요합니다.</p>
    <p class="text-[14px] text-gray-400">개요 탭에서 JD 분석을 실행해주세요.</p>
  </div>

  {% elif not results %}
  <div class="bg-white rounded-lg border border-gray-100 p-8 text-center">
    <svg class="w-12 h-12 text-gray-300 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/>
    </svg>
    <p class="text-[15px] text-gray-500">매칭되는 후보자가 없습니다.</p>
  </div>

  {% else %}
  <form hx-post="{% url 'projects:contact_reserve' project.pk %}"
        hx-target="#tab-content"
        class="bg-white rounded-lg border border-gray-100 p-5">
    {% csrf_token %}

    <div class="flex items-center justify-between mb-4">
      <h2 class="text-[15px] font-semibold text-gray-700">매칭 후보자 ({{ results|length }}명)</h2>
      <button type="submit"
              class="text-[13px] bg-amber-500 text-white px-3 py-1.5 rounded-lg hover:bg-amber-600 transition">
        컨택 예정 등록
      </button>
    </div>

    <div class="space-y-2">
      {% for item in results %}
      <div class="flex items-center justify-between py-2 {% if not forloop.last %}border-b border-gray-50{% endif %}">
        <div class="flex items-center gap-3">
          <!-- 체크박스 -->
          <input type="checkbox" name="candidate_ids" value="{{ item.candidate.pk }}"
                 {% if item.disabled %}disabled{% endif %}
                 class="rounded border-gray-300 text-primary focus:ring-primary
                   {% if item.disabled %}opacity-50 cursor-not-allowed{% endif %}">
          <div>
            <span class="text-[14px] font-medium text-gray-800
              {% if item.disabled %}text-gray-400{% endif %}">
              {{ item.candidate.name }}
            </span>
            <span class="text-[13px] text-gray-500 ml-2">
              {% if item.candidate.current_company %}{{ item.candidate.current_company }}{% endif %}
              {% if item.candidate.current_position %} · {{ item.candidate.current_position }}{% endif %}
            </span>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <!-- 컨택 상태 표시 -->
          {% if item.contact_status == "contacted" %}
          <span class="text-[11px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500"
                title="{{ item.contact_result }}">컨택됨</span>
          {% elif item.contact_status == "reserved" %}
          <span class="text-[11px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-600"
                title="잠금 만료: {{ item.locked_until|date:'m/d H:i' }}">
            컨택 예정 ({{ item.reserved_by.get_full_name|default:item.reserved_by.username }})
          </span>
          {% endif %}

          {% if item.other_project_contacts %}
          <span class="text-[11px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-500"
                title="{% for c in item.other_project_contacts %}{{ c.project.title }}: {{ c.get_result_display }}&#10;{% endfor %}">
            타 프로젝트 이력
          </span>
          {% endif %}

          <!-- 매칭 점수 -->
          <span class="text-[13px] font-medium
            {% if item.level == '높음' %}text-green-600
            {% elif item.level == '보통' %}text-yellow-600
            {% else %}text-red-500{% endif %}">
            {{ item.level }} ({{ item.score|floatformat:0 }}%)
          </span>
        </div>
      </div>
      {% endfor %}
    </div>
  </form>
  {% endif %}

</div>
```

---

## Step 8: 테스트

### tests/test_p06_contacts.py

P05 테스트 패턴을 따른다. fixtures: org, org2, user_with_org, user_with_org2, auth_client, auth_client2, client_obj, project, candidate.

```python
"""P06: Contact management tests."""

import pytest
from datetime import timedelta

from django.test import Client as TestClient
from django.utils import timezone

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import Contact, Project
from projects.services.contact import (
    check_duplicate,
    release_expired_reservations,
    reserve_candidates,
)


# --- Fixtures (P05 패턴 동일) ---

@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")

@pytest.fixture
def org2(db):
    return Organization.objects.create(name="Other Firm")

@pytest.fixture
def user_with_org(db, org):
    user = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=user, organization=org)
    return user

@pytest.fixture
def user_with_org2(db, org2):
    user = User.objects.create_user(username="tester2", password="test1234")
    Membership.objects.create(user=user, organization=org2)
    return user

@pytest.fixture
def user2_with_org(db, org):
    """같은 org의 두번째 사용자 (비담당자 테스트용)."""
    user = User.objects.create_user(username="tester3", password="test1234")
    Membership.objects.create(user=user, organization=org)
    return user

@pytest.fixture
def auth_client(user_with_org):
    c = TestClient()
    c.login(username="tester", password="test1234")
    return c

@pytest.fixture
def auth_client2(user_with_org2):
    c = TestClient()
    c.login(username="tester2", password="test1234")
    return c

@pytest.fixture
def auth_client3(user2_with_org):
    """같은 org의 비담당자 클라이언트."""
    c = TestClient()
    c.login(username="tester3", password="test1234")
    return c

@pytest.fixture
def client_obj(org):
    return Client.objects.create(name="Acme Corp", industry="IT", organization=org)

@pytest.fixture
def client_obj2(org2):
    return Client.objects.create(name="Other Corp", industry="Finance", organization=org2)

@pytest.fixture
def project(client_obj, org, user_with_org):
    p = Project.objects.create(
        client=client_obj, organization=org, title="Test Project",
        created_by=user_with_org,
    )
    p.assigned_consultants.add(user_with_org)
    return p

@pytest.fixture
def project2(client_obj, org, user_with_org):
    """같은 org의 다른 프로젝트."""
    return Project.objects.create(
        client=client_obj, organization=org, title="Other Project",
        created_by=user_with_org,
    )

@pytest.fixture
def project_other_org(client_obj2, org2, user_with_org2):
    return Project.objects.create(
        client=client_obj2, organization=org2, title="Other Org Project",
        created_by=user_with_org2,
    )

@pytest.fixture
def candidate(org):
    return Candidate.objects.create(name="홍길동", owned_by=org)

@pytest.fixture
def candidate2(org):
    return Candidate.objects.create(name="김철수", owned_by=org)

@pytest.fixture
def candidate_other_org(org2):
    return Candidate.objects.create(name="이영희", owned_by=org2)


# --- Service Tests ---

class TestCheckDuplicate:
    def test_blocking_interested(self, project, candidate, user_with_org):
        now = timezone.now()
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user_with_org,
            channel="전화", contacted_at=now, result="관심",
        )
        result = check_duplicate(project, candidate)
        assert result["blocked"] is True

    def test_blocking_rejected(self, project, candidate, user_with_org):
        now = timezone.now()
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user_with_org,
            channel="전화", contacted_at=now, result="거절",
        )
        result = check_duplicate(project, candidate)
        assert result["blocked"] is True

    def test_warning_no_response(self, project, candidate, user_with_org):
        now = timezone.now()
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user_with_org,
            channel="전화", contacted_at=now, result="미응답",
        )
        result = check_duplicate(project, candidate)
        assert result["blocked"] is False
        assert len(result["warnings"]) == 1

    def test_no_duplicate(self, project, candidate):
        result = check_duplicate(project, candidate)
        assert result["blocked"] is False
        assert len(result["warnings"]) == 0

    def test_other_project_shown(self, project, project2, candidate, user_with_org):
        now = timezone.now()
        Contact.objects.create(
            project=project2, candidate=candidate, consultant=user_with_org,
            channel="이메일", contacted_at=now, result="응답",
        )
        result = check_duplicate(project, candidate)
        assert len(result["other_projects"]) == 1


class TestReserveCandidates:
    def test_create(self, project, candidate, user_with_org):
        result = reserve_candidates(project, [candidate.pk], user_with_org)
        assert len(result["created"]) == 1
        assert result["created"][0].result == "예정"
        assert result["created"][0].locked_until is not None

    def test_skip_existing(self, project, candidate, user_with_org):
        now = timezone.now()
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user_with_org,
            result="예정", locked_until=now + timedelta(days=7),
        )
        result = reserve_candidates(project, [candidate.pk], user_with_org)
        assert len(result["skipped"]) == 1


class TestReleaseExpired:
    def test_release(self, project, candidate, user_with_org):
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user_with_org,
            result="예정", locked_until=timezone.now() - timedelta(days=1),
        )
        count = release_expired_reservations()
        assert count == 1

    def test_keep_valid(self, project, candidate, user_with_org):
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user_with_org,
            result="예정", locked_until=timezone.now() + timedelta(days=3),
        )
        count = release_expired_reservations()
        assert count == 0


# --- View Tests ---

class TestContactCreateView:
    def test_get_form(self, auth_client, project):
        resp = auth_client.get(f"/projects/{project.pk}/contacts/new/")
        assert resp.status_code == 200

    def test_post_success(self, auth_client, project, candidate):
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/new/",
            {"candidate": candidate.pk, "channel": "전화",
             "contacted_at": "2026-04-08T10:00", "result": "응답"},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        assert Contact.objects.filter(project=project).count() == 1

    def test_blocked_duplicate(self, auth_client, project, candidate, user_with_org):
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user_with_org,
            channel="전화", contacted_at=timezone.now(), result="관심",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/new/",
            {"candidate": candidate.pk, "channel": "이메일",
             "contacted_at": "2026-04-09T10:00", "result": "응답"},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200  # form re-rendered


class TestContactUpdateView:
    def test_update(self, auth_client, project, candidate, user_with_org):
        contact = Contact.objects.create(
            project=project, candidate=candidate, consultant=user_with_org,
            channel="전화", contacted_at=timezone.now(), result="미응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {"candidate": candidate.pk, "channel": "전화",
             "contacted_at": "2026-04-08T10:00", "result": "응답"},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        contact.refresh_from_db()
        assert contact.result == "응답"


class TestContactDeleteView:
    def test_delete(self, auth_client, project, candidate, user_with_org):
        contact = Contact.objects.create(
            project=project, candidate=candidate, consultant=user_with_org,
            channel="전화", contacted_at=timezone.now(), result="미응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/delete/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        assert not Contact.objects.filter(pk=contact.pk).exists()


class TestContactReserveView:
    def test_reserve(self, auth_client, project, candidate):
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/reserve/",
            {"candidate_ids": [str(candidate.pk)]},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        assert Contact.objects.filter(
            project=project, candidate=candidate, result="예정",
        ).exists()


class TestContactReleaseLockView:
    def test_release_by_assigned(self, auth_client, project, candidate, user_with_org):
        contact = Contact.objects.create(
            project=project, candidate=candidate, consultant=user_with_org,
            result="예정", locked_until=timezone.now() + timedelta(days=7),
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/release/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 204
        contact.refresh_from_db()
        assert contact.locked_until is None

    def test_release_denied(self, auth_client3, project, candidate, user_with_org):
        """같은 org이지만 비담당자는 해제 불가."""
        contact = Contact.objects.create(
            project=project, candidate=candidate, consultant=user_with_org,
            result="예정", locked_until=timezone.now() + timedelta(days=7),
        )
        resp = auth_client3.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/release/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 403


class TestContactOrgIsolation:
    def test_create_other_org_404(self, auth_client, project_other_org):
        resp = auth_client.get(f"/projects/{project_other_org.pk}/contacts/new/")
        assert resp.status_code == 404

    def test_reserve_other_org_404(self, auth_client, project_other_org, candidate):
        resp = auth_client.post(
            f"/projects/{project_other_org.pk}/contacts/reserve/",
            {"candidate_ids": [str(candidate.pk)]},
        )
        assert resp.status_code == 404

    def test_tab_contacts_other_org_404(self, auth_client, project_other_org):
        resp = auth_client.get(f"/projects/{project_other_org.pk}/tab/contacts/")
        assert resp.status_code == 404


class TestContactTabContent:
    def test_separates_completed_and_reserved(
        self, auth_client, project, candidate, candidate2, user_with_org
    ):
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user_with_org,
            channel="전화", contacted_at=timezone.now(), result="응답",
        )
        Contact.objects.create(
            project=project, candidate=candidate2, consultant=user_with_org,
            result="예정", locked_until=timezone.now() + timedelta(days=7),
        )
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/contacts/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        content = resp.content.decode()
        assert candidate.name in content
        assert candidate2.name in content


class TestSearchTabContactStatus:
    def test_contacted_candidate_shown(
        self, auth_client, project, candidate, user_with_org
    ):
        """서칭 탭에서 컨택된 후보자 상태 표시."""
        Contact.objects.create(
            project=project, candidate=candidate, consultant=user_with_org,
            channel="전화", contacted_at=timezone.now(), result="관심",
        )
        project.requirements = {"position": "개발자"}
        project.save()
        resp = auth_client.get(
            f"/projects/{project.pk}/tab/search/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
```

---

## 산출물

| 파일 | 변경 유형 |
|------|----------|
| `projects/models.py` | 수정 (Contact.Result RESERVED 추가, channel blank, contacted_at nullable) |
| `projects/migrations/0003_p06_contact_reserved_nullable.py` | 신규 (migration) |
| `projects/services/contact.py` | 신규 (check_duplicate, reserve_candidates, release_expired) |
| `projects/forms.py` | 수정 (ContactForm 추가) |
| `projects/views.py` | 수정 (project_tab_contacts 확장 + 6개 신규 뷰) |
| `projects/urls.py` | 수정 (6개 컨택 URL 추가) |
| `projects/templates/projects/partials/tab_contacts.html` | 수정 (완료+예정 분리, 버튼) |
| `projects/templates/projects/partials/contact_form.html` | 신규 |
| `projects/templates/projects/partials/duplicate_check_result.html` | 신규 |
| `projects/templates/projects/partials/tab_search.html` | 수정 (체크박스+상태+예정등록) |
| `tests/test_p06_contacts.py` | 신규 |

---

## HTMX 규약 정리

| 컨텍스트 | target | trigger |
|---------|--------|---------|
| 전체 내비 (목록, 수정) | `#main-content` | `hx-push-url="true"` |
| 탭 전환 | `#tab-content` | 없음 |
| 폼 표시 | `#contact-form-area` | 없음 |
| 컨택 변경 후 탭 새로고침 | `#tab-content` | `HX-Trigger: contactChanged` |
| 중복 체크 인라인 | `#duplicate-check-result` | candidate select change |

<!-- forge:p06:구현담금질:complete:2026-04-08T18:30:00+09:00 -->
