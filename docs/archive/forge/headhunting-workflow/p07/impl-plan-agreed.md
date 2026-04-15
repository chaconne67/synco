# P07: Submission Basic CRUD — 확정 구현계획서

> **Phase:** 7
> **선행조건:** P05 (추천 탭 골격), P06 (컨택 탭 완성)
> **산출물:** 추천 탭 완성 — Submission CRUD + 양식 선택 + 파일 업로드/다운로드 + 상태 관리 + 고객사 피드백

---

## 범위 정의

### IN (P07)
- Submission 모델 필드 추가 (template, client_feedback_at, notes) + unique_together
- Submission CRUD (등록/수정/삭제) — 삭제 보호 포함
- 양식 선택 (4가지 SubmissionTemplate)
- 파일 업로드/다운로드 (Word/PDF, 최대 10MB)
- 상태 전환 (작성중 → 제출) + 고객사 피드백 (제출 → 통과/탈락)
- 프로젝트 status 자동 전환 (NEW/SEARCHING → RECOMMENDING)
- 추천 탭 완성 UI (상태별 그룹핑, HTMX 이벤트 기반 갱신)
- 컨택 탭에 "추천 서류 작성 →" 링크 추가 (관심 결과 건)
- 조직 격리 + 보안 테스트

### OUT (후속)
- 면접 생성 연결 (P09) — P07에서는 disabled placeholder만
- 추천 서류 내용 자동 생성 (AI)
- 활동 로그

---

## Step 1: 모델 변경 + Migration

### projects/models.py 수정

```python
class SubmissionTemplate(models.TextChoices):
    XD_KO = "xd_ko", "엑스다임 국문"
    XD_KO_EN = "xd_ko_en", "엑스다임 국영문"
    XD_EN = "xd_en", "엑스다임 영문"
    CUSTOM = "custom", "고객사 커스텀"


class Submission(BaseModel):
    """고객사 제출 서류."""

    class Status(models.TextChoices):
        DRAFTING = "작성중", "작성중"
        SUBMITTED = "제출", "제출"
        PASSED = "통과", "통과"
        REJECTED = "탈락", "탈락"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="submissions",
    )
    candidate = models.ForeignKey(
        "candidates.Candidate", on_delete=models.CASCADE, related_name="submissions",
    )
    consultant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="submissions",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFTING,
    )
    template = models.CharField(
        max_length=20, choices=SubmissionTemplate.choices, blank=True, default="",
    )
    document_file = models.FileField(upload_to="submissions/", blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    client_feedback = models.TextField(blank=True)
    client_feedback_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "candidate"],
                name="unique_submission_per_project_candidate",
            )
        ]

    def __str__(self) -> str:
        return f"{self.project} - {self.candidate} ({self.status})"
```

**핵심 결정:**
- `Status`는 기존 한국어 저장값 유지 (기존 코드/템플릿/테스트 호환)
- `template`는 `blank=True, default=""` (기존 데이터 호환)
- `unique_together` 대신 `UniqueConstraint` 사용 (Django 권장)
- `SubmissionTemplate`은 모델 클래스 외부에 별도 정의

### Migration

```bash
uv run python manage.py makemigrations projects --name p07_submission_template_feedback_notes
uv run python manage.py migrate
```

### 테스트

```python
def test_submission_new_fields_default():
    """기존 Submission 생성 코드가 새 필드 없이도 동작."""
    sub = Submission.objects.create(
        project=project, candidate=candidate, consultant=user,
    )
    assert sub.template == ""
    assert sub.client_feedback_at is None
    assert sub.notes == ""

def test_unique_constraint():
    """같은 프로젝트+후보자 중복 등록 차단."""
    Submission.objects.create(project=project, candidate=candidate, consultant=user)
    with pytest.raises(IntegrityError):
        Submission.objects.create(project=project, candidate=candidate, consultant=user)
```

---

## Step 2: URL 설계

### projects/urls.py 추가

```python
# P07: Submission 관리
path(
    "<uuid:pk>/submissions/new/",
    views.submission_create,
    name="submission_create",
),
path(
    "<uuid:pk>/submissions/<uuid:sub_pk>/edit/",
    views.submission_update,
    name="submission_update",
),
path(
    "<uuid:pk>/submissions/<uuid:sub_pk>/delete/",
    views.submission_delete,
    name="submission_delete",
),
path(
    "<uuid:pk>/submissions/<uuid:sub_pk>/submit/",
    views.submission_submit,
    name="submission_submit",
),
path(
    "<uuid:pk>/submissions/<uuid:sub_pk>/feedback/",
    views.submission_feedback,
    name="submission_feedback",
),
path(
    "<uuid:pk>/submissions/<uuid:sub_pk>/download/",
    views.submission_download,
    name="submission_download",
),
```

---

## Step 3: Form 구현

### projects/forms.py — SubmissionForm

```python
ALLOWED_FILE_EXTENSIONS = [".pdf", ".doc", ".docx"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ["candidate", "template", "document_file", "notes"]
        widgets = {
            "candidate": forms.Select(attrs={"class": INPUT_CSS}),
            "template": forms.Select(attrs={"class": INPUT_CSS}),
            "document_file": forms.ClearableFileInput(attrs={"class": INPUT_CSS}),
            "notes": forms.Textarea(
                attrs={"class": INPUT_CSS, "rows": 3, "placeholder": "메모"}
            ),
        }
        labels = {
            "candidate": "후보자",
            "template": "양식",
            "document_file": "추천 서류",
            "notes": "메모",
        }

    def __init__(self, *args, organization=None, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization and project:
            # 컨택 결과 "관심"인 후보자만 + 이미 Submission이 있는 후보자 제외
            from candidates.models import Candidate

            interested_candidate_ids = (
                Contact.objects.filter(
                    project=project,
                    result=Contact.Result.INTERESTED,
                )
                .values_list("candidate_id", flat=True)
            )

            # 이미 등록된 Submission의 후보자 제외 (수정 시에는 현재 후보자 포함)
            existing_submission_ids = (
                Submission.objects.filter(project=project)
                .values_list("candidate_id", flat=True)
            )
            if self.instance and self.instance.pk:
                existing_submission_ids = existing_submission_ids.exclude(
                    candidate_id=self.instance.candidate_id
                )

            self.fields["candidate"].queryset = Candidate.objects.filter(
                pk__in=interested_candidate_ids,
                owned_by=organization,
            ).exclude(pk__in=existing_submission_ids)
        elif organization:
            from candidates.models import Candidate
            self.fields["candidate"].queryset = Candidate.objects.filter(
                owned_by=organization
            )

    def clean_document_file(self):
        f = self.cleaned_data.get("document_file")
        if f:
            # 확장자 검증
            import os
            ext = os.path.splitext(f.name)[1].lower()
            if ext not in ALLOWED_FILE_EXTENSIONS:
                raise forms.ValidationError(
                    f"허용되지 않는 파일 형식입니다. ({', '.join(ALLOWED_FILE_EXTENSIONS)})"
                )
            # 용량 검증
            if f.size > MAX_FILE_SIZE:
                raise forms.ValidationError(
                    f"파일 크기가 10MB를 초과합니다. (현재: {f.size / 1024 / 1024:.1f}MB)"
                )
        return f
```

### projects/forms.py — SubmissionFeedbackForm

```python
class SubmissionFeedbackForm(forms.Form):
    """고객사 피드백 입력 폼."""
    result = forms.ChoiceField(
        choices=[
            (Submission.Status.PASSED, "통과"),
            (Submission.Status.REJECTED, "탈락"),
        ],
        widget=forms.Select(attrs={"class": INPUT_CSS}),
        label="결과",
    )
    feedback = forms.CharField(
        widget=forms.Textarea(
            attrs={"class": INPUT_CSS, "rows": 3, "placeholder": "피드백 내용"}
        ),
        label="피드백",
        required=False,
    )
```

---

## Step 4: Service Layer

### projects/services/submission.py

```python
"""Submission 상태 전환 + 프로젝트 status 연동."""

from django.utils import timezone

from projects.models import Project, ProjectStatus, Submission


class InvalidTransition(Exception):
    """허용되지 않는 상태 전환."""
    pass


# 허용되는 상태 전환
VALID_TRANSITIONS = {
    Submission.Status.DRAFTING: {Submission.Status.SUBMITTED},
    Submission.Status.SUBMITTED: {Submission.Status.PASSED, Submission.Status.REJECTED},
    # 통과/탈락은 종료 상태 — 추가 전환 불가
}


def submit_to_client(submission: Submission) -> Submission:
    """작성중 → 제출. submitted_at 기록."""
    if submission.status != Submission.Status.DRAFTING:
        raise InvalidTransition(
            f"'{submission.get_status_display()}' 상태에서는 제출할 수 없습니다."
        )
    submission.status = Submission.Status.SUBMITTED
    submission.submitted_at = timezone.now()
    submission.save(update_fields=["status", "submitted_at"])
    return submission


def apply_client_feedback(
    submission: Submission, result: str, feedback: str
) -> Submission:
    """제출 → 통과/탈락. 고객사 피드백 저장."""
    if submission.status != Submission.Status.SUBMITTED:
        raise InvalidTransition(
            f"'{submission.get_status_display()}' 상태에서는 피드백을 입력할 수 없습니다."
        )
    if result not in (Submission.Status.PASSED, Submission.Status.REJECTED):
        raise InvalidTransition(f"유효하지 않은 결과입니다: {result}")

    submission.status = result
    submission.client_feedback = feedback
    submission.client_feedback_at = timezone.now()
    submission.save(
        update_fields=["status", "client_feedback", "client_feedback_at"]
    )
    return submission


def maybe_advance_project_status(project: Project) -> bool:
    """
    첫 Submission 생성 시 프로젝트 status 자동 전환.
    NEW 또는 SEARCHING → RECOMMENDING.
    Returns True if status was changed.
    """
    if project.status not in (ProjectStatus.NEW, ProjectStatus.SEARCHING):
        return False

    project.status = ProjectStatus.RECOMMENDING
    project.save(update_fields=["status"])
    return True
```

---

## Step 5: View 구현

### projects/views.py — Submission CRUD

모든 뷰는 `@login_required` + `_get_org(request)` + `get_object_or_404(Project, pk=pk, organization=org)`.
Submission 접근 시: `get_object_or_404(Submission, pk=sub_pk, project=project)`.

```python
@login_required
def project_tab_submissions(request, pk):
    """추천 탭: 상태별 그룹핑 목록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submissions = (
        project.submissions
        .select_related("candidate", "consultant")
        .order_by("-created_at")
    )

    # 상태별 그룹핑
    drafting = [s for s in submissions if s.status == Submission.Status.DRAFTING]
    submitted = [s for s in submissions if s.status == Submission.Status.SUBMITTED]
    passed = [s for s in submissions if s.status == Submission.Status.PASSED]
    rejected = [s for s in submissions if s.status == Submission.Status.REJECTED]

    return render(
        request,
        "projects/partials/tab_submissions.html",
        {
            "project": project,
            "drafting": drafting,
            "submitted": submitted,
            "passed": passed,
            "rejected": rejected,
            "total_count": submissions.count(),
        },
    )


@login_required
def submission_create(request, pk):
    """추천 서류 등록."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)

    if request.method == "POST":
        form = SubmissionForm(
            request.POST, request.FILES, organization=org, project=project
        )
        if form.is_valid():
            submission = form.save(commit=False)
            submission.project = project
            submission.consultant = request.user
            submission.save()

            # 프로젝트 status 자동 전환
            from projects.services.submission import maybe_advance_project_status
            maybe_advance_project_status(project)

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "submissionChanged"},
            )
    else:
        form = SubmissionForm(organization=org, project=project)

    # 프리필: query param으로 candidate 전달 시
    candidate_id = request.GET.get("candidate")
    if candidate_id and request.method != "POST":
        form.initial["candidate"] = candidate_id

    return render(
        request,
        "projects/partials/submission_form.html",
        {
            "form": form,
            "project": project,
            "is_edit": False,
        },
    )


@login_required
def submission_update(request, pk, sub_pk):
    """추천 서류 수정. 작성중 상태에서만 가능."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submission = get_object_or_404(Submission, pk=sub_pk, project=project)

    if request.method == "POST":
        form = SubmissionForm(
            request.POST, request.FILES,
            instance=submission, organization=org, project=project,
        )
        if form.is_valid():
            form.save()
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "submissionChanged"},
            )
    else:
        form = SubmissionForm(
            instance=submission, organization=org, project=project,
        )

    return render(
        request,
        "projects/partials/submission_form.html",
        {
            "form": form,
            "project": project,
            "submission": submission,
            "is_edit": True,
        },
    )


@login_required
@require_http_methods(["POST"])
def submission_delete(request, pk, sub_pk):
    """추천 서류 삭제. 면접/오퍼 존재 시 차단."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submission = get_object_or_404(Submission, pk=sub_pk, project=project)

    # 삭제 보호: 면접 또는 오퍼 존재 시 차단
    if submission.interviews.exists() or hasattr(submission, "offer"):
        return HttpResponse(
            "면접 또는 오퍼 이력이 있어 삭제할 수 없습니다.",
            status=400,
        )

    submission.delete()
    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "submissionChanged"},
    )


@login_required
@require_http_methods(["POST"])
def submission_submit(request, pk, sub_pk):
    """고객사에 제출 (작성중 → 제출)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submission = get_object_or_404(Submission, pk=sub_pk, project=project)

    from projects.services.submission import InvalidTransition, submit_to_client

    try:
        submit_to_client(submission)
    except InvalidTransition as e:
        return HttpResponse(str(e), status=400)

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "submissionChanged"},
    )


@login_required
def submission_feedback(request, pk, sub_pk):
    """고객사 피드백 입력 (제출 → 통과/탈락)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submission = get_object_or_404(Submission, pk=sub_pk, project=project)

    if request.method == "POST":
        form = SubmissionFeedbackForm(request.POST)
        if form.is_valid():
            from projects.services.submission import (
                InvalidTransition,
                apply_client_feedback,
            )

            try:
                apply_client_feedback(
                    submission,
                    form.cleaned_data["result"],
                    form.cleaned_data["feedback"],
                )
            except InvalidTransition as e:
                return HttpResponse(str(e), status=400)

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "submissionChanged"},
            )
    else:
        form = SubmissionFeedbackForm()

    return render(
        request,
        "projects/partials/submission_feedback.html",
        {
            "form": form,
            "project": project,
            "submission": submission,
        },
    )


@login_required
def submission_download(request, pk, sub_pk):
    """첨부파일 다운로드. 파일 없으면 404."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submission = get_object_or_404(Submission, pk=sub_pk, project=project)

    if not submission.document_file:
        from django.http import Http404
        raise Http404("첨부파일이 없습니다.")

    from django.http import FileResponse
    import os

    response = FileResponse(
        submission.document_file.open("rb"),
        as_attachment=True,
        filename=os.path.basename(submission.document_file.name),
    )
    return response
```

---

## Step 6: Template 구현

### projects/templates/projects/partials/tab_submissions.html (완성)

```html
<div class="space-y-4"
     hx-trigger="submissionChanged from:body"
     hx-get="{% url 'projects:project_tab_submissions' project.pk %}"
     hx-target="#tab-content">

  <!-- 상단: 추천 등록 버튼 -->
  <div class="flex justify-between items-center">
    <h2 class="text-[15px] font-semibold text-gray-700">추천 이력 ({{ total_count }}건)</h2>
    <button hx-get="{% url 'projects:submission_create' project.pk %}"
            hx-target="#submission-form-area"
            class="text-[13px] bg-primary text-white px-3 py-1.5 rounded-lg hover:bg-primary-dark transition">
      + 추천 등록
    </button>
  </div>

  <!-- 폼 삽입 영역 -->
  <div id="submission-form-area"></div>

  <!-- 상태별 그룹 -->
  {% for group_label, group_list, group_color in status_groups %}
  {% if group_list %}
  <div class="bg-white rounded-lg border border-gray-100 p-5">
    <h3 class="text-[14px] font-medium text-{{ group_color }}-700 mb-3">
      {{ group_label }} ({{ group_list|length }}건)
    </h3>
    <table class="w-full text-[14px]">
      <!-- 후보자, 양식, 제출일, 담당, 작업 -->
      {% for submission in group_list %}
      <tr>
        <td>{{ submission.candidate.name }}</td>
        <td>{{ submission.get_template_display|default:"-" }}</td>
        <td>{% if submission.submitted_at %}{{ submission.submitted_at|date:"m/d" }}{% else %}{{ submission.created_at|date:"m/d" }}{% endif %}</td>
        <td>{% if submission.consultant %}{{ submission.consultant.get_full_name|default:submission.consultant.username }}{% else %}-{% endif %}</td>
        <td class="text-right">
          <!-- 상태별 액션 버튼 -->
          {% if submission.status == '작성중' %}
            <button hx-get="{% url 'projects:submission_update' project.pk submission.pk %}"
                    hx-target="#submission-form-area"
                    class="text-[13px] text-primary">수정</button>
            <button hx-post="{% url 'projects:submission_submit' project.pk submission.pk %}"
                    hx-confirm="고객사에 제출하시겠습니까?"
                    class="text-[13px] text-blue-600 ml-2">제출하기</button>
            <button hx-post="{% url 'projects:submission_delete' project.pk submission.pk %}"
                    hx-confirm="정말 삭제하시겠습니까?"
                    class="text-[13px] text-red-500 ml-2">삭제</button>
          {% elif submission.status == '제출' %}
            <button hx-get="{% url 'projects:submission_feedback' project.pk submission.pk %}"
                    hx-target="#submission-form-area"
                    class="text-[13px] text-purple-600">피드백 입력</button>
          {% elif submission.status == '통과' %}
            <span class="text-[13px] text-gray-400 cursor-not-allowed"
                  title="면접 등록은 추후 구현 예정입니다">면접 등록 (준비중)</span>
          {% endif %}

          <!-- 파일 다운로드 (HTMX 아닌 일반 링크) -->
          {% if submission.document_file %}
            <a href="{% url 'projects:submission_download' project.pk submission.pk %}"
               class="text-[13px] text-gray-600 hover:text-gray-800 ml-2">다운로드</a>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </table>
  </div>
  {% endif %}
  {% endfor %}

  {% if total_count == 0 %}
  <div class="bg-white rounded-lg border border-gray-100 p-5">
    <p class="text-[14px] text-gray-400">추천 이력이 없습니다.</p>
  </div>
  {% endif %}
</div>
```

**구현 참고:** 실제 구현 시 `status_groups`를 뷰에서 Python 리스트로 전달하거나, 템플릿에서 각 그룹을 개별 렌더링한다. 위 의사코드는 구조를 보여주기 위한 것.

### projects/templates/projects/partials/submission_form.html (등록/수정 폼)

```html
<div class="bg-white rounded-lg border border-gray-200 p-5 mb-4">
  <div class="flex justify-between items-center mb-4">
    <h3 class="text-[15px] font-semibold text-gray-700">
      {% if is_edit %}추천 서류 수정{% else %}추천 서류 등록{% endif %}
    </h3>
    <button onclick="this.closest('#submission-form-area').innerHTML=''"
            class="text-[13px] text-gray-500 hover:text-gray-700">닫기</button>
  </div>

  <form hx-post="{% if is_edit %}{% url 'projects:submission_update' project.pk submission.pk %}{% else %}{% url 'projects:submission_create' project.pk %}{% endif %}"
        hx-target="#submission-form-area"
        enctype="multipart/form-data"
        class="space-y-3">
    {% csrf_token %}
    <!-- candidate, template, document_file, notes 필드 렌더링 -->
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
              onclick="this.closest('#submission-form-area').innerHTML=''"
              class="text-[13px] text-gray-500 hover:text-gray-700 px-3 py-1.5">취소</button>
      <button type="submit"
              class="text-[13px] bg-primary text-white px-4 py-1.5 rounded-lg hover:bg-primary-dark transition">
        {% if is_edit %}수정{% else %}등록{% endif %}
      </button>
    </div>
  </form>
</div>
```

### projects/templates/projects/partials/submission_feedback.html (피드백 폼)

```html
<div class="bg-white rounded-lg border border-purple-100 p-5 mb-4">
  <div class="flex justify-between items-center mb-4">
    <h3 class="text-[15px] font-semibold text-purple-700">고객사 피드백 입력</h3>
    <button onclick="this.closest('#submission-form-area').innerHTML=''"
            class="text-[13px] text-gray-500 hover:text-gray-700">닫기</button>
  </div>

  <p class="text-[14px] text-gray-600 mb-3">
    {{ submission.candidate.name }} — {{ submission.get_template_display|default:"양식 미지정" }}
  </p>

  <form hx-post="{% url 'projects:submission_feedback' project.pk submission.pk %}"
        hx-target="#submission-form-area"
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
              onclick="this.closest('#submission-form-area').innerHTML=''"
              class="text-[13px] text-gray-500 hover:text-gray-700 px-3 py-1.5">취소</button>
      <button type="submit"
              class="text-[13px] bg-purple-600 text-white px-4 py-1.5 rounded-lg hover:bg-purple-700 transition">
        피드백 저장
      </button>
    </div>
  </form>
</div>
```

---

## Step 7: 컨택 탭 "추천 서류 작성 →" 링크 추가

### projects/templates/projects/partials/tab_contacts.html 수정

`관심` 결과인 행의 작업 컬럼에 추가:

```html
{% if contact.result == '관심' %}
  {% if contact.candidate.pk not in submitted_candidate_ids %}
    <a hx-get="{% url 'projects:submission_create' project.pk %}?candidate={{ contact.candidate.pk }}"
       hx-target="#tab-content"
       class="text-[13px] text-green-600 hover:text-green-800 mr-2">추천 서류 작성 →</a>
  {% else %}
    <span class="text-[13px] text-gray-400">추천 등록 완료</span>
  {% endif %}
{% endif %}
```

### projects/views.py — project_tab_contacts 수정

기존 뷰에 `submitted_candidate_ids` 추가:

```python
# 이미 Submission이 있는 후보자 ID
submitted_candidate_ids = set(
    project.submissions.values_list("candidate_id", flat=True)
)
```

context에 `"submitted_candidate_ids": submitted_candidate_ids` 추가.

---

## Step 8: 테스트

### tests/test_p07_submissions.py

```python
"""P07: Submission CRUD tests."""
import tempfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

# --- Login Required ---
class TestSubmissionLoginRequired:
    """7개 URL 모두 미로그인 시 redirect 검증."""
    def test_create_requires_login(self): ...
    def test_update_requires_login(self): ...
    def test_delete_requires_login(self): ...
    def test_submit_requires_login(self): ...
    def test_feedback_requires_login(self): ...
    def test_download_requires_login(self): ...
    def test_tab_requires_login(self): ...

# --- Organization Isolation ---
class TestSubmissionOrgIsolation:
    """타 조직 프로젝트의 Submission 접근 시 404."""
    def test_create_other_org_404(self): ...
    def test_update_other_org_404(self): ...
    def test_delete_other_org_404(self): ...
    def test_submit_other_org_404(self): ...
    def test_feedback_other_org_404(self): ...
    def test_download_other_org_404(self): ...

# --- CRUD ---
class TestSubmissionCRUD:
    def test_create_with_interested_candidate(self):
        """관심 후보자로 Submission 생성 → 목록에 표시."""

    def test_create_prefill_candidate(self):
        """?candidate= query param으로 후보자 미리 선택."""

    def test_create_non_interested_candidate_not_in_dropdown(self):
        """미응답/거절 후보자는 드롭다운에 미표시."""

    def test_create_duplicate_blocked(self):
        """같은 프로젝트+후보자 중복 등록 차단 (IntegrityError → form error)."""

    def test_update_submission(self):
        """Submission 수정 → 저장."""

    def test_delete_submission(self):
        """Submission 삭제 → 목록에서 제거."""

    def test_delete_blocked_with_interview(self):
        """면접 이력 존재 시 삭제 차단."""

    def test_delete_blocked_with_offer(self):
        """오퍼 존재 시 삭제 차단."""

# --- Template Selection ---
class TestTemplateSelection:
    def test_all_four_templates_selectable(self):
        """4가지 양식 모두 선택/저장 가능."""

# --- File Upload/Download ---
@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class TestFileUploadDownload:
    def test_upload_pdf(self):
        """PDF 업로드 → 다운로드 가능."""

    def test_upload_docx(self):
        """DOCX 업로드 → 다운로드 가능."""

    def test_upload_invalid_extension_rejected(self):
        """.exe 등 비허용 확장자 거부."""

    def test_upload_exceeds_10mb_rejected(self):
        """10MB 초과 파일 거부."""

    def test_download_no_file_404(self):
        """파일 없는 Submission 다운로드 시 404."""

# --- State Transitions ---
class TestStateTransitions:
    def test_submit_drafting_to_submitted(self):
        """작성중 → 제출 전환 + submitted_at 기록."""

    def test_submit_already_submitted_fails(self):
        """이미 제출된 건 재제출 불가."""

    def test_submit_passed_fails(self):
        """통과 상태에서 제출 불가."""

    def test_feedback_submitted_to_passed(self):
        """제출 → 통과 (피드백 입력)."""

    def test_feedback_submitted_to_rejected(self):
        """제출 → 탈락 (피드백 입력)."""

    def test_feedback_drafting_fails(self):
        """작성중 상태에서 피드백 불가."""

    def test_feedback_already_passed_fails(self):
        """통과 상태에서 피드백 재입력 불가."""

    def test_feedback_already_rejected_fails(self):
        """탈락 상태에서 피드백 재입력 불가."""

    def test_client_feedback_at_recorded(self):
        """피드백 입력 시 client_feedback_at 기록."""

# --- Project Status Auto-transition ---
class TestProjectStatusAutoTransition:
    def test_first_submission_new_to_recommending(self):
        """첫 Submission 생성 시 NEW → RECOMMENDING."""

    def test_first_submission_searching_to_recommending(self):
        """첫 Submission 생성 시 SEARCHING → RECOMMENDING."""

    def test_second_submission_no_change(self):
        """두 번째 Submission 생성 시 status 유지."""

    def test_already_recommending_no_change(self):
        """이미 RECOMMENDING 이상이면 변경 없음."""

# --- Contact Tab Link ---
class TestContactTabSubmissionLink:
    def test_interested_contact_shows_link(self):
        """관심 결과 건에 '추천 서류 작성 →' 링크 표시."""

    def test_non_interested_no_link(self):
        """미응답/거절 건에는 링크 미표시."""

    def test_already_submitted_shows_complete(self):
        """이미 Submission이 있으면 '추천 등록 완료' 표시."""

# --- HTMX Behavior ---
class TestHTMXBehavior:
    def test_create_returns_204_with_trigger(self):
        """생성 성공 시 204 + HX-Trigger: submissionChanged."""

    def test_tab_auto_refreshes_on_trigger(self):
        """submissionChanged 이벤트 시 탭 자동 새로고침 (hx-trigger 확인)."""
```

---

## 산출물

| 파일 | 변경 유형 |
|------|----------|
| `projects/models.py` | 수정 (SubmissionTemplate 추가, Submission 필드 추가, UniqueConstraint) |
| `projects/views.py` | 수정 (project_tab_submissions 완성 + 6개 CRUD 뷰 추가) |
| `projects/forms.py` | 수정 (SubmissionForm, SubmissionFeedbackForm 추가) |
| `projects/urls.py` | 수정 (6개 URL 추가) |
| `projects/services/submission.py` | 신규 (상태 전환, 프로젝트 status 연동) |
| `projects/templates/projects/partials/tab_submissions.html` | 리팩터 (상태별 그룹핑, HTMX 이벤트) |
| `projects/templates/projects/partials/submission_form.html` | 신규 |
| `projects/templates/projects/partials/submission_feedback.html` | 신규 |
| `projects/templates/projects/partials/tab_contacts.html` | 수정 (추천 서류 작성 링크 추가) |
| `projects/migrations/XXXX_p07_submission_template_feedback_notes.py` | 신규 |
| `tests/test_p07_submissions.py` | 신규 |

---

## HTMX 규약 (P07 추가)

| 컨텍스트 | target | trigger event | push-url |
|---------|--------|---------------|----------|
| 추천 탭 자동 새로고침 | `#tab-content` | `submissionChanged` | 없음 |
| 추천 폼 삽입 | `#submission-form-area` | — | 없음 |
| 피드백 폼 삽입 | `#submission-form-area` | — | 없음 |
| 파일 다운로드 | (HTMX 아님, 일반 `<a href>`) | — | 없음 |

<!-- forge:p07:구현담금질:complete:2026-04-08T19:15:00+09:00 -->
