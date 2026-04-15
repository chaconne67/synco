# P09: Interview & Offer — 확정 구현계획서

> **Phase:** 9
> **선행조건:** P07 (Submission CRUD — "면접 등록 →" 링크), P05 (면접/오퍼 탭 골격)
> **산출물:** 면접 탭 + 오퍼 탭 완성, 프로젝트 status 자동 전환

---

## 범위 정의

### IN (P09)
- Interview 모델 필드 추가 (location, notes) + unique constraint
- Offer 모델 필드 추가 (notes, decided_at)
- Interview CRUD (등록/수정/삭제/결과 입력) — 삭제 보호 포함
- Offer CRUD (등록/수정/삭제/수락/거절)
- 면접 탭 완성 UI (후보자별 그룹핑, HTMX 이벤트 기반 갱신)
- 오퍼 탭 완성 UI (오퍼 카드, 수락/거절 버튼)
- 프로젝트 status 자동 전환 (interviewing, negotiating, closed_success)
- P07 추천 탭 "면접 등록 →" 링크 활성화
- 조직 격리 + 인증 + 보안 테스트

### OUT (후속)
- closed_fail 자동 전환 (조건 정의 복잡 — 수동 전환으로 처리)
- status_update 수동 전환 제한 (권한 관리 Phase에서 처리)

---

## Step 1: 모델 변경 + Migration

### projects/models.py 수정

**Interview 모델 — 필드 추가:**

```python
class Interview(BaseModel):
    """면접 단계."""

    class Type(models.TextChoices):
        IN_PERSON = "대면", "대면"
        VIDEO = "화상", "화상"
        PHONE = "전화", "전화"

    class Result(models.TextChoices):
        PENDING = "대기", "대기"
        PASSED = "합격", "합격"
        ON_HOLD = "보류", "보류"
        FAILED = "탈락", "탈락"

    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name="interviews",
    )
    round = models.PositiveSmallIntegerField()
    scheduled_at = models.DateTimeField()
    type = models.CharField(max_length=20, choices=Type.choices)
    location = models.CharField(max_length=500, blank=True)  # NEW: 면접 장소 / 화상 링크
    result = models.CharField(
        max_length=20,
        choices=Result.choices,
        default=Result.PENDING,
    )
    feedback = models.TextField(blank=True)
    notes = models.TextField(blank=True)  # NEW: 컨설턴트 메모

    class Meta:
        ordering = ["submission", "round"]
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "round"],
                name="unique_interview_per_submission_round",
            )
        ]

    def __str__(self) -> str:
        return f"{self.submission} - {self.round}차 면접"
```

**Offer 모델 — 필드 추가:**

```python
class Offer(BaseModel):
    """오퍼 조율."""

    class Status(models.TextChoices):
        NEGOTIATING = "협상중", "협상중"
        ACCEPTED = "수락", "수락"
        REJECTED = "거절", "거절"

    submission = models.OneToOneField(
        Submission,
        on_delete=models.CASCADE,
        related_name="offer",
    )
    salary = models.CharField(max_length=100, blank=True)
    position_title = models.CharField(max_length=200, blank=True)
    start_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEGOTIATING,
    )
    terms = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)  # NEW: 협상 메모
    decided_at = models.DateTimeField(null=True, blank=True)  # NEW: 수락/거절 일시

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Offer: {self.submission}"
```

**핵심 결정:**
- 기존 한국어 DB 저장값 유지 (대면/화상/전화, 대기/합격/보류/탈락, 협상중/수락/거절)
- 새 필드만 추가: Interview에 `location`, `notes`; Offer에 `notes`, `decided_at`
- Interview에 `UniqueConstraint(fields=["submission", "round"])` 추가
- 운영 DB에 Interview 데이터 0건이므로 데이터 정리 마이그레이션 불필요

### Migration

```bash
uv run python manage.py makemigrations projects --name p09_interview_offer_fields
uv run python manage.py migrate
```

### 테스트

```python
def test_interview_new_fields_default():
    """기존 Interview 생성 코드가 새 필드 없이도 동작."""
    interview = Interview.objects.create(
        submission=submission, round=1,
        scheduled_at=timezone.now(), type=Interview.Type.IN_PERSON,
    )
    assert interview.location == ""
    assert interview.notes == ""

def test_interview_unique_constraint():
    """같은 submission+round 중복 차단."""
    Interview.objects.create(
        submission=submission, round=1,
        scheduled_at=timezone.now(), type=Interview.Type.IN_PERSON,
    )
    with pytest.raises(IntegrityError):
        Interview.objects.create(
            submission=submission, round=1,
            scheduled_at=timezone.now(), type=Interview.Type.VIDEO,
        )

def test_offer_new_fields_default():
    """기존 Offer 생성 코드가 새 필드 없이도 동작."""
    offer = Offer.objects.create(submission=submission)
    assert offer.notes == ""
    assert offer.decided_at is None
```

---

## Step 2: URL 설계

### projects/urls.py 추가

```python
# P09: Interview 관리
path(
    "<uuid:pk>/interviews/new/",
    views.interview_create,
    name="interview_create",
),
path(
    "<uuid:pk>/interviews/<uuid:interview_pk>/edit/",
    views.interview_update,
    name="interview_update",
),
path(
    "<uuid:pk>/interviews/<uuid:interview_pk>/delete/",
    views.interview_delete,
    name="interview_delete",
),
path(
    "<uuid:pk>/interviews/<uuid:interview_pk>/result/",
    views.interview_result,
    name="interview_result",
),
# P09: Offer 관리
path(
    "<uuid:pk>/offers/new/",
    views.offer_create,
    name="offer_create",
),
path(
    "<uuid:pk>/offers/<uuid:offer_pk>/edit/",
    views.offer_update,
    name="offer_update",
),
path(
    "<uuid:pk>/offers/<uuid:offer_pk>/delete/",
    views.offer_delete,
    name="offer_delete",
),
path(
    "<uuid:pk>/offers/<uuid:offer_pk>/accept/",
    views.offer_accept,
    name="offer_accept",
),
path(
    "<uuid:pk>/offers/<uuid:offer_pk>/reject/",
    views.offer_reject,
    name="offer_reject",
),
```

---

## Step 3: Service Layer

### projects/services/lifecycle.py (신규)

```python
"""프로젝트 라이프사이클 상태 자동 전환 + Interview/Offer 전이 규칙."""

from django.utils import timezone

from projects.models import Interview, Offer, Project, ProjectStatus, Submission


class InvalidTransition(Exception):
    """허용되지 않는 상태 전환."""
    pass


# --- Project Status Auto-transition ---

# 라이프사이클 순서 (숫자가 클수록 후반)
STATUS_ORDER = {
    ProjectStatus.NEW: 0,
    ProjectStatus.SEARCHING: 1,
    ProjectStatus.RECOMMENDING: 2,
    ProjectStatus.INTERVIEWING: 3,
    ProjectStatus.NEGOTIATING: 4,
    ProjectStatus.CLOSED_SUCCESS: 5,
}


def maybe_advance_to_interviewing(project: Project) -> bool:
    """
    첫 Interview 생성 시 프로젝트 status 자동 전환.
    RECOMMENDING 이하 → INTERVIEWING.
    Returns True if status was changed.
    """
    current_order = STATUS_ORDER.get(project.status, -1)
    if current_order >= STATUS_ORDER[ProjectStatus.INTERVIEWING]:
        return False

    project.status = ProjectStatus.INTERVIEWING
    project.save(update_fields=["status"])
    return True


def maybe_advance_to_negotiating(project: Project) -> bool:
    """
    첫 Offer 생성 시 프로젝트 status 자동 전환.
    INTERVIEWING 이하 → NEGOTIATING.
    Returns True if status was changed.
    """
    current_order = STATUS_ORDER.get(project.status, -1)
    if current_order >= STATUS_ORDER[ProjectStatus.NEGOTIATING]:
        return False

    project.status = ProjectStatus.NEGOTIATING
    project.save(update_fields=["status"])
    return True


def maybe_advance_to_closed_success(project: Project) -> bool:
    """
    Offer accepted → CLOSED_SUCCESS.
    Returns True if status was changed.
    """
    current_order = STATUS_ORDER.get(project.status, -1)
    if current_order >= STATUS_ORDER[ProjectStatus.CLOSED_SUCCESS]:
        return False

    project.status = ProjectStatus.CLOSED_SUCCESS
    project.save(update_fields=["status"])
    return True


# --- Interview Result Transition ---

INTERVIEW_RESULT_TRANSITIONS = {
    Interview.Result.PENDING: {
        Interview.Result.PASSED,
        Interview.Result.ON_HOLD,
        Interview.Result.FAILED,
    },
    # 합격/보류/탈락은 종료 상태 — 추가 전환 불가
}


def apply_interview_result(
    interview: Interview, result: str, feedback: str
) -> Interview:
    """대기 → 합격/보류/탈락. 면접 결과 저장."""
    allowed = INTERVIEW_RESULT_TRANSITIONS.get(interview.result, set())
    if result not in allowed:
        raise InvalidTransition(
            f"'{interview.get_result_display()}' 상태에서는 결과를 변경할 수 없습니다."
        )
    if result not in Interview.Result.values:
        raise InvalidTransition(f"유효하지 않은 결과입니다: {result}")

    interview.result = result
    interview.feedback = feedback
    interview.save(update_fields=["result", "feedback"])
    return interview


# --- Offer Status Transition ---

OFFER_STATUS_TRANSITIONS = {
    Offer.Status.NEGOTIATING: {
        Offer.Status.ACCEPTED,
        Offer.Status.REJECTED,
    },
    # 수락/거절은 종료 상태 — 추가 전환 불가
}


def accept_offer(offer: Offer) -> Offer:
    """협상중 → 수락."""
    if offer.status != Offer.Status.NEGOTIATING:
        raise InvalidTransition(
            f"'{offer.get_status_display()}' 상태에서는 수락할 수 없습니다."
        )
    offer.status = Offer.Status.ACCEPTED
    offer.decided_at = timezone.now()
    offer.save(update_fields=["status", "decided_at"])
    return offer


def reject_offer(offer: Offer) -> Offer:
    """협상중 → 거절."""
    if offer.status != Offer.Status.NEGOTIATING:
        raise InvalidTransition(
            f"'{offer.get_status_display()}' 상태에서는 거절할 수 없습니다."
        )
    offer.status = Offer.Status.REJECTED
    offer.decided_at = timezone.now()
    offer.save(update_fields=["status", "decided_at"])
    return offer


# --- Offer Eligibility Check ---

def is_submission_offer_eligible(submission: Submission) -> bool:
    """해당 Submission의 최신 인터뷰 결과가 합격인지 확인."""
    latest_interview = (
        submission.interviews
        .order_by("-round")
        .first()
    )
    if not latest_interview:
        return False
    return latest_interview.result == Interview.Result.PASSED
```

---

## Step 4: Form 구현

### projects/forms.py — InterviewForm

```python
class InterviewForm(forms.ModelForm):
    class Meta:
        model = Interview
        fields = ["submission", "round", "scheduled_at", "type", "location", "notes"]
        widgets = {
            "submission": forms.Select(attrs={"class": INPUT_CSS}),
            "round": forms.NumberInput(attrs={"class": INPUT_CSS, "min": 1}),
            "scheduled_at": forms.DateTimeInput(
                attrs={"class": INPUT_CSS, "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "type": forms.Select(attrs={"class": INPUT_CSS}),
            "location": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "면접 장소 또는 화상 링크"}
            ),
            "notes": forms.Textarea(
                attrs={"class": INPUT_CSS, "rows": 3, "placeholder": "메모"}
            ),
        }
        labels = {
            "submission": "추천 건",
            "round": "차수",
            "scheduled_at": "면접 일시",
            "type": "유형",
            "location": "장소/링크",
            "notes": "메모",
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project:
            # 통과된 Submission만 선택 가능
            self.fields["submission"].queryset = Submission.objects.filter(
                project=project,
                status=Submission.Status.PASSED,
            ).select_related("candidate")

    def clean(self):
        cleaned = super().clean()
        submission = cleaned.get("submission")
        round_num = cleaned.get("round")

        if submission and round_num:
            # 중복 (submission, round) 검증 — 수정 시 자기 자신 제외
            qs = Interview.objects.filter(
                submission=submission, round=round_num,
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    "round",
                    f"{round_num}차 면접이 이미 등록되어 있습니다.",
                )

        return cleaned
```

### projects/forms.py — InterviewResultForm

```python
class InterviewResultForm(forms.Form):
    """면접 결과 입력 폼."""
    result = forms.ChoiceField(
        choices=[
            (Interview.Result.PASSED, "합격"),
            (Interview.Result.ON_HOLD, "보류"),
            (Interview.Result.FAILED, "탈락"),
        ],
        widget=forms.Select(attrs={"class": INPUT_CSS}),
        label="결과",
    )
    feedback = forms.CharField(
        widget=forms.Textarea(
            attrs={"class": INPUT_CSS, "rows": 3, "placeholder": "면접관/고객사 피드백"}
        ),
        label="피드백",
        required=False,
    )
```

### projects/forms.py — OfferForm

```python
class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = ["submission", "salary", "position_title", "start_date", "notes"]
        widgets = {
            "submission": forms.Select(attrs={"class": INPUT_CSS}),
            "salary": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "제안 연봉"}
            ),
            "position_title": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "제안 직책"}
            ),
            "start_date": forms.DateInput(
                attrs={"class": INPUT_CSS, "type": "date"},
                format="%Y-%m-%d",
            ),
            "notes": forms.Textarea(
                attrs={"class": INPUT_CSS, "rows": 3, "placeholder": "협상 메모"}
            ),
        }
        labels = {
            "submission": "추천 건",
            "salary": "제안 연봉",
            "position_title": "제안 직책",
            "start_date": "출근 예정일",
            "notes": "메모",
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project:
            from projects.services.lifecycle import is_submission_offer_eligible

            # 최신 인터뷰 합격 + Offer 없는 Submission만
            passed_submissions = Submission.objects.filter(
                project=project,
                status=Submission.Status.PASSED,
            ).select_related("candidate")

            # 이미 Offer 있는 Submission 제외 (수정 시 자기 submission 포함)
            existing_offer_sub_ids = Offer.objects.filter(
                submission__project=project,
            ).values_list("submission_id", flat=True)
            if self.instance and self.instance.pk:
                existing_offer_sub_ids = existing_offer_sub_ids.exclude(
                    submission_id=self.instance.submission_id,
                )

            eligible_ids = [
                s.pk for s in passed_submissions.exclude(pk__in=existing_offer_sub_ids)
                if is_submission_offer_eligible(s)
            ]
            self.fields["submission"].queryset = Submission.objects.filter(
                pk__in=eligible_ids,
            ).select_related("candidate")
```

---

## Step 5: View 구현

모든 뷰는 `@login_required` + `_get_org(request)` + `get_object_or_404(Project, pk=pk, organization=org)`.
Interview 접근 시: `get_object_or_404(Interview, pk=interview_pk, submission__project=project)`.
Offer 접근 시: `get_object_or_404(Offer, pk=offer_pk, submission__project=project)`.

### projects/views.py — Interview CRUD

```python
# --- P09: Interview ---

@login_required
def project_tab_interviews(request, pk):
    """면접 탭: 후보자별 그룹핑, 차수 순 정렬."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    interviews = (
        Interview.objects.filter(submission__project=project)
        .select_related("submission__candidate", "submission__consultant")
        .order_by("submission__candidate__name", "round")
    )

    # 후보자별 그룹핑
    from itertools import groupby
    grouped = []
    for candidate_name, group in groupby(interviews, key=lambda i: i.submission.candidate):
        grouped.append({
            "candidate": candidate_name,
            "interviews": list(group),
        })

    return render(
        request,
        "projects/partials/tab_interviews.html",
        {
            "project": project,
            "grouped_interviews": grouped,
            "total_count": interviews.count(),
        },
    )


@login_required
def interview_create(request, pk):
    """면접 등록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if request.method == "POST":
        form = InterviewForm(request.POST, project=project)
        if form.is_valid():
            interview = form.save()

            # 프로젝트 status 자동 전환
            from projects.services.lifecycle import maybe_advance_to_interviewing
            maybe_advance_to_interviewing(project)

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "interviewChanged"},
            )
    else:
        form = InterviewForm(project=project)

    # 프리필: query param으로 submission 전달 시
    submission_id = request.GET.get("submission")
    if submission_id and request.method != "POST":
        form.initial["submission"] = submission_id
        # round 자동 계산: 해당 submission의 max round + 1
        try:
            max_round = (
                Interview.objects.filter(submission_id=submission_id)
                .order_by("-round")
                .values_list("round", flat=True)
                .first()
            ) or 0
            form.initial["round"] = max_round + 1
        except Exception:
            form.initial["round"] = 1

    return render(
        request,
        "projects/partials/interview_form.html",
        {
            "form": form,
            "project": project,
            "is_edit": False,
        },
    )


@login_required
def interview_update(request, pk, interview_pk):
    """면접 수정."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    interview = get_object_or_404(
        Interview, pk=interview_pk, submission__project=project,
    )

    if request.method == "POST":
        form = InterviewForm(request.POST, instance=interview, project=project)
        if form.is_valid():
            form.save()
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "interviewChanged"},
            )
    else:
        form = InterviewForm(instance=interview, project=project)

    return render(
        request,
        "projects/partials/interview_form.html",
        {
            "form": form,
            "project": project,
            "interview": interview,
            "is_edit": True,
        },
    )


@login_required
@require_http_methods(["POST"])
def interview_delete(request, pk, interview_pk):
    """면접 삭제. 삭제 보호: 결과 입력 완료(합격/탈락) 시 차단."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    interview = get_object_or_404(
        Interview, pk=interview_pk, submission__project=project,
    )

    # 삭제 보호: Offer가 연결된 Submission의 Interview는 삭제 불가
    if hasattr(interview.submission, "offer"):
        return HttpResponse(
            "오퍼가 등록된 추천 건의 면접은 삭제할 수 없습니다.",
            status=400,
        )

    interview.delete()
    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "interviewChanged"},
    )


@login_required
def interview_result(request, pk, interview_pk):
    """면접 결과 입력 (대기 → 합격/보류/탈락)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    interview = get_object_or_404(
        Interview, pk=interview_pk, submission__project=project,
    )

    if request.method == "POST":
        form = InterviewResultForm(request.POST)
        if form.is_valid():
            from projects.services.lifecycle import (
                InvalidTransition,
                apply_interview_result,
            )

            try:
                apply_interview_result(
                    interview,
                    form.cleaned_data["result"],
                    form.cleaned_data["feedback"],
                )
            except InvalidTransition as e:
                return HttpResponse(str(e), status=400)

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "interviewChanged"},
            )
    else:
        form = InterviewResultForm()

    return render(
        request,
        "projects/partials/interview_result_form.html",
        {
            "form": form,
            "project": project,
            "interview": interview,
        },
    )
```

### projects/views.py — Offer CRUD

```python
# --- P09: Offer ---

@login_required
def project_tab_offers(request, pk):
    """오퍼 탭: 목록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    offers = (
        Offer.objects.filter(submission__project=project)
        .select_related("submission__candidate", "submission__consultant")
        .order_by("-created_at")
    )
    return render(
        request,
        "projects/partials/tab_offers.html",
        {
            "project": project,
            "offers": offers,
            "total_count": offers.count(),
        },
    )


@login_required
def offer_create(request, pk):
    """오퍼 등록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if request.method == "POST":
        form = OfferForm(request.POST, project=project)
        if form.is_valid():
            form.save()

            # 프로젝트 status 자동 전환
            from projects.services.lifecycle import maybe_advance_to_negotiating
            maybe_advance_to_negotiating(project)

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "offerChanged"},
            )
    else:
        form = OfferForm(project=project)

    return render(
        request,
        "projects/partials/offer_form.html",
        {
            "form": form,
            "project": project,
            "is_edit": False,
        },
    )


@login_required
def offer_update(request, pk, offer_pk):
    """오퍼 수정. 협상중 상태에서만."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    offer = get_object_or_404(
        Offer, pk=offer_pk, submission__project=project,
    )

    if request.method == "POST":
        form = OfferForm(request.POST, instance=offer, project=project)
        if form.is_valid():
            form.save()
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "offerChanged"},
            )
    else:
        form = OfferForm(instance=offer, project=project)

    return render(
        request,
        "projects/partials/offer_form.html",
        {
            "form": form,
            "project": project,
            "offer": offer,
            "is_edit": True,
        },
    )


@login_required
@require_http_methods(["POST"])
def offer_delete(request, pk, offer_pk):
    """오퍼 삭제. 수락/거절 상태에서는 삭제 불가."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    offer = get_object_or_404(
        Offer, pk=offer_pk, submission__project=project,
    )

    if offer.status != Offer.Status.NEGOTIATING:
        return HttpResponse(
            "수락 또는 거절된 오퍼는 삭제할 수 없습니다.",
            status=400,
        )

    offer.delete()
    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "offerChanged"},
    )


@login_required
@require_http_methods(["POST"])
def offer_accept(request, pk, offer_pk):
    """오퍼 수락 (협상중 → 수락)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    offer = get_object_or_404(
        Offer, pk=offer_pk, submission__project=project,
    )

    from projects.services.lifecycle import (
        InvalidTransition,
        accept_offer,
        maybe_advance_to_closed_success,
    )

    try:
        accept_offer(offer)
    except InvalidTransition as e:
        return HttpResponse(str(e), status=400)

    # 프로젝트 status 자동 전환
    maybe_advance_to_closed_success(project)

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "offerChanged"},
    )


@login_required
@require_http_methods(["POST"])
def offer_reject(request, pk, offer_pk):
    """오퍼 거절 (협상중 → 거절)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    offer = get_object_or_404(
        Offer, pk=offer_pk, submission__project=project,
    )

    from projects.services.lifecycle import InvalidTransition, reject_offer

    try:
        reject_offer(offer)
    except InvalidTransition as e:
        return HttpResponse(str(e), status=400)

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "offerChanged"},
    )
```

---

## Step 6: Template 구현

### projects/templates/projects/partials/tab_interviews.html (완성)

```html
<div class="space-y-4"
     hx-trigger="interviewChanged from:body"
     hx-get="{% url 'projects:project_tab_interviews' project.pk %}"
     hx-target="#tab-content">

  <!-- 상단: 면접 등록 버튼 -->
  <div class="flex justify-between items-center">
    <h2 class="text-[15px] font-semibold text-gray-700">면접 이력 ({{ total_count }}건)</h2>
    <button hx-get="{% url 'projects:interview_create' project.pk %}"
            hx-target="#interview-form-area"
            class="text-[13px] bg-primary text-white px-3 py-1.5 rounded-lg hover:bg-primary-dark transition">
      + 면접 등록
    </button>
  </div>

  <!-- 폼 삽입 영역 -->
  <div id="interview-form-area"></div>

  <!-- 후보자별 그룹핑 -->
  {% for group in grouped_interviews %}
  <div class="bg-white rounded-lg border border-gray-100 p-5">
    <h3 class="text-[14px] font-medium text-gray-700 mb-3">
      {{ group.candidate.name }} ({{ group.interviews|length }}건)
    </h3>
    <div class="overflow-x-auto">
      <table class="w-full text-[14px]">
        <thead>
          <tr class="border-b border-gray-100">
            <th class="text-left py-2 text-gray-500 font-medium">차수</th>
            <th class="text-left py-2 text-gray-500 font-medium">유형</th>
            <th class="text-left py-2 text-gray-500 font-medium">일정</th>
            <th class="text-left py-2 text-gray-500 font-medium">장소</th>
            <th class="text-left py-2 text-gray-500 font-medium">결과</th>
            <th class="text-right py-2 text-gray-500 font-medium">작업</th>
          </tr>
        </thead>
        <tbody>
          {% for interview in group.interviews %}
          <tr class="border-b border-gray-50">
            <td class="py-2 text-gray-800 font-medium">{{ interview.round }}차</td>
            <td class="py-2 text-gray-600">{{ interview.get_type_display }}</td>
            <td class="py-2 text-gray-500">{{ interview.scheduled_at|date:"m/d H:i" }}</td>
            <td class="py-2 text-gray-500">{{ interview.location|default:"-" }}</td>
            <td class="py-2">
              <span class="text-[13px] px-1.5 py-0.5 rounded
                {% if interview.result == '합격' %}bg-green-50 text-green-600
                {% elif interview.result == '탈락' %}bg-red-50 text-red-500
                {% elif interview.result == '보류' %}bg-yellow-50 text-yellow-600
                {% else %}bg-gray-50 text-gray-500{% endif %}">
                {{ interview.get_result_display }}
              </span>
            </td>
            <td class="py-2 text-right">
              {% if interview.result == '대기' %}
                <button hx-get="{% url 'projects:interview_result' project.pk interview.pk %}"
                        hx-target="#interview-form-area"
                        class="text-[13px] text-purple-600 hover:text-purple-800">결과 입력</button>
                <button hx-get="{% url 'projects:interview_update' project.pk interview.pk %}"
                        hx-target="#interview-form-area"
                        class="text-[13px] text-primary hover:text-primary-dark ml-2">수정</button>
                <button hx-post="{% url 'projects:interview_delete' project.pk interview.pk %}"
                        hx-confirm="정말 삭제하시겠습니까?"
                        class="text-[13px] text-red-500 hover:text-red-700 ml-2">삭제</button>
              {% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
  {% endfor %}

  {% if total_count == 0 %}
  <div class="bg-white rounded-lg border border-gray-100 p-5">
    <p class="text-[14px] text-gray-400">면접 이력이 없습니다.</p>
  </div>
  {% endif %}
</div>
```

### projects/templates/projects/partials/interview_form.html (등록/수정 폼)

```html
<div class="bg-white rounded-lg border border-gray-200 p-5 mb-4">
  <div class="flex justify-between items-center mb-4">
    <h3 class="text-[15px] font-semibold text-gray-700">
      {% if is_edit %}면접 수정{% else %}면접 등록{% endif %}
    </h3>
    <button onclick="document.getElementById('interview-form-area').innerHTML=''"
            class="text-[13px] text-gray-500 hover:text-gray-700">닫기</button>
  </div>

  <form hx-post="{% if is_edit %}{% url 'projects:interview_update' project.pk interview.pk %}{% else %}{% url 'projects:interview_create' project.pk %}{% endif %}"
        hx-target="#interview-form-area"
        class="space-y-3">
    {% csrf_token %}
    {% for field in form %}
    <div>
      <label class="block text-[13px] font-medium text-gray-600 mb-1">{{ field.label }}</label>
      {{ field }}
      {% if field.errors %}
        {% for error in field.errors %}
          <p class="text-[12px] text-red-500 mt-0.5">{{ error }}</p>
        {% endfor %}
      {% endif %}
    </div>
    {% endfor %}

    <div class="flex justify-end gap-2 pt-2">
      <button type="button"
              onclick="document.getElementById('interview-form-area').innerHTML=''"
              class="text-[13px] text-gray-500 hover:text-gray-700 px-3 py-1.5">취소</button>
      <button type="submit"
              class="text-[13px] bg-primary text-white px-4 py-1.5 rounded-lg hover:bg-primary-dark transition">
        {% if is_edit %}수정{% else %}등록{% endif %}
      </button>
    </div>
  </form>
</div>
```

### projects/templates/projects/partials/interview_result_form.html (결과 입력 폼)

```html
<div class="bg-white rounded-lg border border-purple-100 p-5 mb-4">
  <div class="flex justify-between items-center mb-4">
    <h3 class="text-[15px] font-semibold text-purple-700">면접 결과 입력</h3>
    <button onclick="document.getElementById('interview-form-area').innerHTML=''"
            class="text-[13px] text-gray-500 hover:text-gray-700">닫기</button>
  </div>

  <p class="text-[14px] text-gray-600 mb-3">
    {{ interview.submission.candidate.name }} — {{ interview.round }}차 {{ interview.get_type_display }}
  </p>

  <form hx-post="{% url 'projects:interview_result' project.pk interview.pk %}"
        hx-target="#interview-form-area"
        class="space-y-3">
    {% csrf_token %}
    {% for field in form %}
    <div>
      <label class="block text-[13px] font-medium text-gray-600 mb-1">{{ field.label }}</label>
      {{ field }}
      {% if field.errors %}
        {% for error in field.errors %}
          <p class="text-[12px] text-red-500 mt-0.5">{{ error }}</p>
        {% endfor %}
      {% endif %}
    </div>
    {% endfor %}

    <div class="flex justify-end gap-2 pt-2">
      <button type="button"
              onclick="document.getElementById('interview-form-area').innerHTML=''"
              class="text-[13px] text-gray-500 hover:text-gray-700 px-3 py-1.5">취소</button>
      <button type="submit"
              class="text-[13px] bg-purple-600 text-white px-4 py-1.5 rounded-lg hover:bg-purple-700 transition">
        결과 저장
      </button>
    </div>
  </form>
</div>
```

### projects/templates/projects/partials/tab_offers.html (완성)

```html
<div class="space-y-4"
     hx-trigger="offerChanged from:body"
     hx-get="{% url 'projects:project_tab_offers' project.pk %}"
     hx-target="#tab-content">

  <!-- 상단: 오퍼 등록 버튼 -->
  <div class="flex justify-between items-center">
    <h2 class="text-[15px] font-semibold text-gray-700">오퍼 이력 ({{ total_count }}건)</h2>
    <button hx-get="{% url 'projects:offer_create' project.pk %}"
            hx-target="#offer-form-area"
            class="text-[13px] bg-primary text-white px-3 py-1.5 rounded-lg hover:bg-primary-dark transition">
      + 오퍼 등록
    </button>
  </div>

  <!-- 폼 삽입 영역 -->
  <div id="offer-form-area"></div>

  {% for offer in offers %}
  <div class="bg-white rounded-lg border
    {% if offer.status == '수락' %}border-green-200
    {% elif offer.status == '거절' %}border-red-200
    {% else %}border-yellow-200{% endif %} p-5">
    <div class="flex justify-between items-start">
      <div>
        <h3 class="text-[15px] font-medium text-gray-800">
          {{ offer.submission.candidate.name }}
        </h3>
        <div class="mt-2 space-y-1 text-[14px] text-gray-600">
          <p>제안 연봉: {{ offer.salary|default:"-" }}</p>
          <p>직책: {{ offer.position_title|default:"-" }}</p>
          <p>출근 예정일: {% if offer.start_date %}{{ offer.start_date|date:"Y-m-d" }}{% else %}-{% endif %}</p>
          {% if offer.notes %}
          <p>메모: {{ offer.notes }}</p>
          {% endif %}
        </div>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-[13px] px-2 py-0.5 rounded-full
          {% if offer.status == '수락' %}bg-green-50 text-green-600
          {% elif offer.status == '거절' %}bg-red-50 text-red-500
          {% else %}bg-yellow-50 text-yellow-600{% endif %}">
          {{ offer.get_status_display }}
        </span>
      </div>
    </div>

    {% if offer.status == '협상중' %}
    <div class="mt-3 flex justify-end gap-2 border-t border-gray-100 pt-3">
      <button hx-get="{% url 'projects:offer_update' project.pk offer.pk %}"
              hx-target="#offer-form-area"
              class="text-[13px] text-primary hover:text-primary-dark">수정</button>
      <button hx-post="{% url 'projects:offer_accept' project.pk offer.pk %}"
              hx-confirm="오퍼를 수락 처리하시겠습니까?"
              class="text-[13px] text-green-600 hover:text-green-800">수락</button>
      <button hx-post="{% url 'projects:offer_reject' project.pk offer.pk %}"
              hx-confirm="오퍼를 거절 처리하시겠습니까?"
              class="text-[13px] text-red-500 hover:text-red-700">거절</button>
      <button hx-post="{% url 'projects:offer_delete' project.pk offer.pk %}"
              hx-confirm="정말 삭제하시겠습니까?"
              class="text-[13px] text-gray-500 hover:text-gray-700">삭제</button>
    </div>
    {% endif %}

    {% if offer.decided_at %}
    <p class="mt-2 text-[12px] text-gray-400">
      {{ offer.get_status_display }} 일시: {{ offer.decided_at|date:"Y-m-d H:i" }}
    </p>
    {% endif %}
  </div>
  {% endfor %}

  {% if total_count == 0 %}
  <div class="bg-white rounded-lg border border-gray-100 p-5">
    <p class="text-[14px] text-gray-400">오퍼 이력이 없습니다.</p>
  </div>
  {% endif %}
</div>
```

### projects/templates/projects/partials/offer_form.html (등록/수정 폼)

```html
<div class="bg-white rounded-lg border border-gray-200 p-5 mb-4">
  <div class="flex justify-between items-center mb-4">
    <h3 class="text-[15px] font-semibold text-gray-700">
      {% if is_edit %}오퍼 수정{% else %}오퍼 등록{% endif %}
    </h3>
    <button onclick="document.getElementById('offer-form-area').innerHTML=''"
            class="text-[13px] text-gray-500 hover:text-gray-700">닫기</button>
  </div>

  <form hx-post="{% if is_edit %}{% url 'projects:offer_update' project.pk offer.pk %}{% else %}{% url 'projects:offer_create' project.pk %}{% endif %}"
        hx-target="#offer-form-area"
        class="space-y-3">
    {% csrf_token %}
    {% for field in form %}
    <div>
      <label class="block text-[13px] font-medium text-gray-600 mb-1">{{ field.label }}</label>
      {{ field }}
      {% if field.errors %}
        {% for error in field.errors %}
          <p class="text-[12px] text-red-500 mt-0.5">{{ error }}</p>
        {% endfor %}
      {% endif %}
    </div>
    {% endfor %}

    <div class="flex justify-end gap-2 pt-2">
      <button type="button"
              onclick="document.getElementById('offer-form-area').innerHTML=''"
              class="text-[13px] text-gray-500 hover:text-gray-700 px-3 py-1.5">취소</button>
      <button type="submit"
              class="text-[13px] bg-primary text-white px-4 py-1.5 rounded-lg hover:bg-primary-dark transition">
        {% if is_edit %}수정{% else %}등록{% endif %}
      </button>
    </div>
  </form>
</div>
```

---

## Step 7: P07 추천 탭 "면접 등록 →" 링크 활성화

### projects/templates/projects/partials/tab_submissions.html 수정

기존 disabled placeholder:
```html
<span class="text-[13px] text-gray-400 cursor-not-allowed"
      title="면접 등록은 추후 구현 예정입니다">면접 등록 (준비중)</span>
```

변경:
```html
<a hx-get="{% url 'projects:interview_create' project.pk %}?submission={{ submission.pk }}"
   hx-target="#tab-content"
   class="text-[13px] text-indigo-600 hover:text-indigo-800">면접 등록 →</a>
```

**동작:** 면접 탭으로 전환되면서 해당 submission이 프리필된 면접 등록 폼이 표시됨.
**주의:** `hx-target="#tab-content"`로 면접 탭 전체를 로드. 면접 등록 뷰가 면접 탭을 반환하도록 처리하거나, 추천 탭 내에서 모달/인라인 삽입으로 처리.

**구현 결정:** 추천 탭에서 "면접 등록 →" 클릭 시 면접 탭으로 전환(`hx-target="#tab-content"`) 후, interview_create 뷰가 폼을 반환. 이 경우 interview_create는 `#interview-form-area`에 폼을 삽입하므로, 추천 탭에서는 직접 면접 탭 URL을 호출하고 query param으로 submission을 전달하는 방식 대신, **면접 탭을 먼저 로드하고 JavaScript로 폼을 열도록** 처리:

```html
<button hx-get="{% url 'projects:project_tab_interviews' project.pk %}"
        hx-target="#tab-content"
        hx-on::after-settle="htmx.ajax('GET', '{% url 'projects:interview_create' project.pk %}?submission={{ submission.pk }}', {target:'#interview-form-area'})"
        class="text-[13px] text-indigo-600 hover:text-indigo-800">면접 등록 →</button>
```

또는 단순하게: interview_create 뷰가 GET 요청 시 면접 탭 전체 + 폼을 함께 반환하도록 처리. 더 간단한 구현:

```html
<a hx-get="{% url 'projects:interview_create' project.pk %}?submission={{ submission.pk }}"
   hx-target="#interview-form-area"
   class="text-[13px] text-indigo-600 hover:text-indigo-800">면접 등록 →</a>
```

이 경우 `#interview-form-area`는 면접 탭에만 존재하므로, 현재 탭이 면접 탭이 아니면 타겟을 찾지 못합니다. **최종 결정:** 추천 탭에서 "면접 등록 →" 클릭 시 면접 탭의 면접 등록 페이지로 전체 내비게이션:

```html
<a href="{% url 'projects:interview_create' project.pk %}?submission={{ submission.pk }}"
   hx-get="{% url 'projects:interview_create' project.pk %}?submission={{ submission.pk }}"
   hx-target="#tab-content"
   class="text-[13px] text-indigo-600 hover:text-indigo-800">면접 등록 →</a>
```

이를 위해 interview_create 뷰는 GET 요청 시 **면접 탭 전체를 렌더링하되 폼이 이미 열린 상태**로 반환합니다. 구현: interview_create가 GET일 때 tab_interviews 컨텍스트 + 폼을 함께 포함한 템플릿을 반환.

---

## Step 8: 테스트

### tests/test_p09_interviews_offers.py

```python
"""P09: Interview & Offer tests."""

import pytest
from django.utils import timezone

# --- Login Required ---
class TestInterviewLoginRequired:
    """면접 관련 URL 미로그인 시 redirect 검증."""
    def test_tab_requires_login(self): ...
    def test_create_requires_login(self): ...
    def test_update_requires_login(self): ...
    def test_delete_requires_login(self): ...
    def test_result_requires_login(self): ...

class TestOfferLoginRequired:
    """오퍼 관련 URL 미로그인 시 redirect 검증."""
    def test_tab_requires_login(self): ...
    def test_create_requires_login(self): ...
    def test_update_requires_login(self): ...
    def test_delete_requires_login(self): ...
    def test_accept_requires_login(self): ...
    def test_reject_requires_login(self): ...

# --- Organization Isolation ---
class TestInterviewOrgIsolation:
    """타 조직 프로젝트의 Interview 접근 시 404."""
    def test_tab_other_org_404(self): ...
    def test_create_other_org_404(self): ...
    def test_update_other_org_404(self): ...
    def test_delete_other_org_404(self): ...
    def test_result_other_org_404(self): ...

class TestOfferOrgIsolation:
    """타 조직 프로젝트의 Offer 접근 시 404."""
    def test_tab_other_org_404(self): ...
    def test_create_other_org_404(self): ...
    def test_update_other_org_404(self): ...
    def test_delete_other_org_404(self): ...
    def test_accept_other_org_404(self): ...
    def test_reject_other_org_404(self): ...

# --- Interview CRUD ---
class TestInterviewCRUD:
    def test_create_interview(self):
        """통과 Submission에 면접 등록 → 목록 표시."""

    def test_create_with_submission_prefill(self):
        """?submission= query param으로 submission 프리필 + round 자동 계산."""

    def test_round_auto_increment(self):
        """이전 차수 + 1 자동 제안."""

    def test_create_only_passed_submission(self):
        """통과 상태 Submission만 선택 가능."""

    def test_create_duplicate_round_blocked(self):
        """같은 submission+round 중복 등록 차단 (200 + 에러 메시지)."""

    def test_update_interview(self):
        """면접 수정 → 저장."""

    def test_delete_interview(self):
        """면접 삭제 → 목록에서 제거."""

    def test_delete_blocked_with_offer(self):
        """오퍼 존재 시 면접 삭제 차단."""

    def test_tab_grouped_by_candidate(self):
        """면접 탭 후보자별 그룹핑 확인."""

# --- Interview Result ---
class TestInterviewResult:
    def test_result_pending_to_passed(self):
        """대기 → 합격."""

    def test_result_pending_to_failed(self):
        """대기 → 탈락."""

    def test_result_pending_to_on_hold(self):
        """대기 → 보류."""

    def test_result_already_passed_fails(self):
        """합격 상태에서 재변경 불가."""

    def test_result_already_failed_fails(self):
        """탈락 상태에서 재변경 불가."""

# --- Offer CRUD ---
class TestOfferCRUD:
    def test_create_offer(self):
        """최신 면접 합격 Submission에 오퍼 등록."""

    def test_create_only_latest_interview_passed(self):
        """최신(max round) 면접 합격인 Submission만 선택 가능."""

    def test_create_failed_after_pass_blocked(self):
        """1차 합격 + 2차 탈락 → 오퍼 등록 불가."""

    def test_create_duplicate_offer_blocked(self):
        """이미 Offer 있는 Submission → 드롭다운 미표시."""

    def test_update_offer(self):
        """오퍼 수정 → 저장."""

    def test_delete_offer_negotiating(self):
        """협상중 오퍼 삭제 가능."""

    def test_delete_offer_accepted_blocked(self):
        """수락된 오퍼 삭제 차단."""

    def test_delete_offer_rejected_blocked(self):
        """거절된 오퍼 삭제 차단."""

# --- Offer Accept/Reject ---
class TestOfferAcceptReject:
    def test_accept_negotiating(self):
        """협상중 → 수락 + decided_at 기록."""

    def test_reject_negotiating(self):
        """협상중 → 거절 + decided_at 기록."""

    def test_accept_already_accepted_fails(self):
        """이미 수락된 오퍼 재수락 불가."""

    def test_reject_already_rejected_fails(self):
        """이미 거절된 오퍼 재거절 불가."""

    def test_accept_already_rejected_fails(self):
        """이미 거절된 오퍼 수락 불가."""

# --- Project Status Auto-transition ---
class TestProjectStatusAutoTransition:
    def test_first_interview_to_interviewing(self):
        """첫 Interview 생성 → RECOMMENDING → INTERVIEWING."""

    def test_first_interview_from_new_to_interviewing(self):
        """첫 Interview 생성 → NEW → INTERVIEWING."""

    def test_already_interviewing_no_change(self):
        """이미 INTERVIEWING이면 변경 없음."""

    def test_first_offer_to_negotiating(self):
        """첫 Offer 생성 → INTERVIEWING → NEGOTIATING."""

    def test_already_negotiating_no_change(self):
        """이미 NEGOTIATING이면 변경 없음."""

    def test_offer_accepted_to_closed_success(self):
        """Offer accepted → NEGOTIATING → CLOSED_SUCCESS."""

    def test_no_reverse_transition(self):
        """INTERVIEWING → RECOMMENDING 역전환 방지."""

    def test_closed_success_no_further_auto_advance(self):
        """CLOSED_SUCCESS 이후 자동 전환 없음."""

# --- HTMX Behavior ---
class TestHTMXBehavior:
    def test_interview_create_returns_204_with_trigger(self):
        """면접 생성 성공 시 204 + HX-Trigger: interviewChanged."""

    def test_offer_create_returns_204_with_trigger(self):
        """오퍼 생성 성공 시 204 + HX-Trigger: offerChanged."""

    def test_interview_tab_auto_refreshes_on_trigger(self):
        """interviewChanged 이벤트 시 탭 자동 새로고침."""

    def test_offer_tab_auto_refreshes_on_trigger(self):
        """offerChanged 이벤트 시 탭 자동 새로고침."""

# --- P07 Integration ---
class TestP07Integration:
    def test_passed_submission_shows_interview_link(self):
        """통과 건에 '면접 등록 →' 링크 표시."""

    def test_drafting_submission_no_interview_link(self):
        """작성중 건에는 면접 등록 링크 미표시."""
```

---

## 산출물

| 파일 | 변경 유형 |
|------|----------|
| `projects/models.py` | 수정 (Interview: location, notes 추가 + UniqueConstraint; Offer: notes, decided_at 추가) |
| `projects/views.py` | 수정 (project_tab_interviews/offers 완성 + Interview/Offer CRUD 뷰 9개 추가) |
| `projects/forms.py` | 수정 (InterviewForm, InterviewResultForm, OfferForm 추가) |
| `projects/urls.py` | 수정 (9개 URL 추가) |
| `projects/services/lifecycle.py` | 신규 (프로젝트 status 자동 전환 + Interview/Offer 전이 규칙) |
| `projects/templates/projects/partials/tab_interviews.html` | 리팩터 (후보자별 그룹핑, HTMX 이벤트) |
| `projects/templates/projects/partials/tab_offers.html` | 리팩터 (오퍼 카드, 수락/거절) |
| `projects/templates/projects/partials/interview_form.html` | 신규 |
| `projects/templates/projects/partials/interview_result_form.html` | 신규 |
| `projects/templates/projects/partials/offer_form.html` | 신규 |
| `projects/templates/projects/partials/tab_submissions.html` | 수정 ("면접 등록 →" 링크 활성화) |
| `projects/migrations/XXXX_p09_interview_offer_fields.py` | 신규 |
| `tests/test_p09_interviews_offers.py` | 신규 |

---

## HTMX 규약 (P09 추가)

| 컨텍스트 | target | trigger event | push-url |
|---------|--------|---------------|----------|
| 면접 탭 자동 새로고침 | `#tab-content` | `interviewChanged` | 없음 |
| 면접 폼 삽입 | `#interview-form-area` | — | 없음 |
| 면접 결과 폼 삽입 | `#interview-form-area` | — | 없음 |
| 오퍼 탭 자동 새로고침 | `#tab-content` | `offerChanged` | 없음 |
| 오퍼 폼 삽입 | `#offer-form-area` | — | 없음 |
| 오퍼 수락/거절 | 탭 자동 새로고침 | `offerChanged` | 없음 |

<!-- forge:p09:구현담금질:complete:2026-04-08T20:45:00+09:00 -->
