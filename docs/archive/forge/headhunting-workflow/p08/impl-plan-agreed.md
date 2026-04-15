# P08: AI Document Pipeline — 확정 구현계획서

> **Phase:** 8
> **선행조건:** P07 (Submission CRUD — 추천 서류 기본 구조 존재)
> **산출물:** SubmissionDraft 기반 AI 문서 생성 파이프라인 전체 (초안 → 상담 → 최종 → 변환)

---

## 범위 정의

### IN (P08)
- SubmissionDraft 모델 + migration
- AI 초안 생성 (Gemini API) + 자동 보정
- 상담 내용 입력 (직접 입력 + 녹음 파일 Whisper 딕테이션)
- AI 최종 정리 (초안 + 상담 병합)
- 컨설턴트 검토/수정
- Word 변환 (python-docx) + 마스킹
- 상태 전이 서비스 (P07 패턴)
- 추천 탭 UI 수정 (초안 작업 진입점)
- 테스트 (P07 수준)

### OUT (후속)
- PDF 변환 (의존성 추가 필요, 별도 단계)
- 영문 번역 AI (output_language=en 지원은 모델만, 실제 번역은 후속)
- 파이프라인 자동화 (generate → finalize 연속 실행)

---

## Step 1: 모델 변경 + Migration

### projects/models.py 수정

```python
class DraftStatus(models.TextChoices):
    PENDING = "pending", "대기"
    DRAFT_GENERATED = "draft_generated", "초안 생성됨"
    CONSULTATION_ADDED = "consultation_added", "상담 입력됨"
    FINALIZED = "finalized", "AI 정리 완료"
    REVIEWED = "reviewed", "검토 완료"
    CONVERTED = "converted", "변환 완료"


class OutputLanguage(models.TextChoices):
    KO = "ko", "국문"
    EN = "en", "영문"
    KO_EN = "ko_en", "국영문"


class OutputFormat(models.TextChoices):
    WORD = "word", "Word"
    PDF = "pdf", "PDF"


DEFAULT_MASKING_CONFIG = {
    "salary": True,
    "birth_detail": True,
    "contact": True,
    "current_company": False,
}


class SubmissionDraft(BaseModel):
    """AI 문서 생성 파이프라인 초안."""

    submission = models.OneToOneField(
        Submission,
        on_delete=models.CASCADE,
        related_name="draft",
    )
    # template은 Submission.template을 참조 — 중복 저장하지 않음
    status = models.CharField(
        max_length=30,
        choices=DraftStatus.choices,
        default=DraftStatus.PENDING,
    )

    # 1단계: AI 초안
    auto_draft_json = models.JSONField(default=dict, blank=True)
    auto_corrections = models.JSONField(default=list, blank=True)

    # 2단계: 상담
    consultation_input = models.TextField(blank=True)
    consultation_audio = models.FileField(
        upload_to="drafts/audio/", blank=True
    )
    consultation_transcript = models.TextField(blank=True)
    consultation_summary = models.JSONField(default=dict, blank=True)

    # 3단계: AI 최종 정리
    final_content_json = models.JSONField(default=dict, blank=True)

    # 4단계: 변환 설정
    masking_config = models.JSONField(default=dict, blank=True)
    output_format = models.CharField(
        max_length=10,
        choices=OutputFormat.choices,
        default=OutputFormat.WORD,
    )
    output_language = models.CharField(
        max_length=10,
        choices=OutputLanguage.choices,
        default=OutputLanguage.KO,
    )
    output_file = models.FileField(
        upload_to="drafts/output/", blank=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Draft: {self.submission} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # masking_config 기본값 보장
        if not self.masking_config:
            self.masking_config = DEFAULT_MASKING_CONFIG.copy()
        super().save(*args, **kwargs)
```

**핵심 결정:**
- `template` 필드 없음 — `self.submission.template`로 참조 (source of truth 단일화)
- `output_language` 기본값은 KO, 변환 시 선택 가능
- `masking_config`는 `save()` 오버라이드로 기본값 보장
- `consultation_audio`는 `blank=True` (null이 아닌 빈 문자열)
- `output_file`도 `blank=True` (변환 전에는 비어있음)

### Migration

```bash
uv run python manage.py makemigrations projects --name p08_submission_draft
uv run python manage.py migrate
```

### 테스트

```python
def test_draft_creation_defaults():
    """SubmissionDraft 생성 시 기본값 확인."""
    draft = SubmissionDraft.objects.create(submission=submission)
    assert draft.status == DraftStatus.PENDING
    assert draft.masking_config == DEFAULT_MASKING_CONFIG
    assert draft.output_format == OutputFormat.WORD
    assert draft.output_language == OutputLanguage.KO
    assert draft.auto_draft_json == {}
    assert draft.auto_corrections == []

def test_draft_onetoone_constraint():
    """같은 Submission에 두 번째 draft 생성 차단."""
    SubmissionDraft.objects.create(submission=submission)
    with pytest.raises(IntegrityError):
        SubmissionDraft.objects.create(submission=submission)

def test_draft_cascade_delete():
    """Submission 삭제 시 draft도 함께 삭제."""
    SubmissionDraft.objects.create(submission=submission)
    submission.delete()
    assert SubmissionDraft.objects.count() == 0
```

---

## Step 2: 상태 전이 서비스

### projects/services/draft_pipeline.py

```python
"""SubmissionDraft 상태 전이 서비스."""

from projects.models import DraftStatus, SubmissionDraft


class InvalidDraftTransition(Exception):
    """허용되지 않는 draft 상태 전환."""
    pass


# 허용되는 상태 전이 맵
VALID_TRANSITIONS = {
    DraftStatus.PENDING: {DraftStatus.DRAFT_GENERATED},
    DraftStatus.DRAFT_GENERATED: {
        DraftStatus.CONSULTATION_ADDED,
        DraftStatus.FINALIZED,  # 상담 건너뛰기 허용
    },
    DraftStatus.CONSULTATION_ADDED: {DraftStatus.FINALIZED},
    DraftStatus.FINALIZED: {DraftStatus.REVIEWED},
    DraftStatus.REVIEWED: {
        DraftStatus.CONVERTED,
        DraftStatus.FINALIZED,  # 회귀: 재정리
    },
    DraftStatus.CONVERTED: {
        DraftStatus.REVIEWED,  # 회귀: 재검토
    },
}


def transition_draft(draft: SubmissionDraft, new_status: str) -> SubmissionDraft:
    """Draft 상태를 전환한다. 허용되지 않은 전이는 예외 발생."""
    allowed = VALID_TRANSITIONS.get(draft.status, set())
    if new_status not in allowed:
        raise InvalidDraftTransition(
            f"'{draft.get_status_display()}'에서 "
            f"'{DraftStatus(new_status).label}'(으)로 전환할 수 없습니다."
        )
    draft.status = new_status
    draft.save(update_fields=["status", "updated_at"])
    return draft
```

### 테스트

```python
def test_valid_transitions():
    """허용된 전이는 성공."""
    draft = SubmissionDraft.objects.create(submission=submission)
    assert draft.status == DraftStatus.PENDING
    transition_draft(draft, DraftStatus.DRAFT_GENERATED)
    assert draft.status == DraftStatus.DRAFT_GENERATED

def test_invalid_transition():
    """허용되지 않은 전이는 예외 발생."""
    draft = SubmissionDraft.objects.create(submission=submission)
    with pytest.raises(InvalidDraftTransition):
        transition_draft(draft, DraftStatus.FINALIZED)  # pending → finalized 불가

def test_skip_consultation():
    """상담 건너뛰기: draft_generated → finalized 가능."""
    draft = SubmissionDraft.objects.create(
        submission=submission, status=DraftStatus.DRAFT_GENERATED
    )
    transition_draft(draft, DraftStatus.FINALIZED)
    assert draft.status == DraftStatus.FINALIZED

def test_regression_reviewed_to_finalized():
    """회귀 전이: reviewed → finalized (재정리)."""
    draft = SubmissionDraft.objects.create(
        submission=submission, status=DraftStatus.REVIEWED
    )
    transition_draft(draft, DraftStatus.FINALIZED)
    assert draft.status == DraftStatus.FINALIZED
```

---

## Step 3: URL 설계

### projects/urls.py 추가

```python
# P08: Draft 파이프라인
path(
    "<uuid:pk>/submissions/<uuid:sub_pk>/draft/",
    views.submission_draft,
    name="submission_draft",
),
path(
    "<uuid:pk>/submissions/<uuid:sub_pk>/draft/generate/",
    views.draft_generate,
    name="draft_generate",
),
path(
    "<uuid:pk>/submissions/<uuid:sub_pk>/draft/consultation/",
    views.draft_consultation,
    name="draft_consultation",
),
path(
    "<uuid:pk>/submissions/<uuid:sub_pk>/draft/consultation/audio/",
    views.draft_consultation_audio,
    name="draft_consultation_audio",
),
path(
    "<uuid:pk>/submissions/<uuid:sub_pk>/draft/finalize/",
    views.draft_finalize,
    name="draft_finalize",
),
path(
    "<uuid:pk>/submissions/<uuid:sub_pk>/draft/review/",
    views.draft_review,
    name="draft_review",
),
path(
    "<uuid:pk>/submissions/<uuid:sub_pk>/draft/convert/",
    views.draft_convert,
    name="draft_convert",
),
path(
    "<uuid:pk>/submissions/<uuid:sub_pk>/draft/preview/",
    views.draft_preview,
    name="draft_preview",
),
```

---

## Step 4: View 구현

### 공통 헬퍼

```python
def _get_draft_context(request, pk, sub_pk):
    """Draft 뷰 공통: org 검증 + project + submission + draft(get_or_create)."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submission = get_object_or_404(Submission, pk=sub_pk, project=project)
    draft, _created = SubmissionDraft.objects.get_or_create(
        submission=submission,
        defaults={"masking_config": DEFAULT_MASKING_CONFIG.copy()},
    )
    return org, project, submission, draft
```

### submission_draft (GET) — 메인 화면

```python
@login_required
def submission_draft(request, pk, sub_pk):
    """초안 작업 메인 화면. 현재 상태에 따라 적절한 단계 표시."""
    org, project, submission, draft = _get_draft_context(request, pk, sub_pk)
    return render(
        request,
        "projects/submission_draft.html",
        {
            "project": project,
            "submission": submission,
            "draft": draft,
            "candidate": submission.candidate,
        },
    )
```

### draft_generate (POST) — AI 초안 생성

```python
@login_required
@require_http_methods(["POST"])
def draft_generate(request, pk, sub_pk):
    """AI 초안 생성. Gemini API 호출."""
    org, project, submission, draft = _get_draft_context(request, pk, sub_pk)

    if draft.status not in (DraftStatus.PENDING, DraftStatus.DRAFT_GENERATED):
        return HttpResponse("이미 초안 생성이 완료되었습니다.", status=400)

    from projects.services.draft_generator import generate_draft
    try:
        generate_draft(draft)
    except Exception as e:
        return render(
            request,
            "projects/partials/draft_error.html",
            {"error": str(e), "draft": draft},
        )

    return render(
        request,
        "projects/partials/draft_step_generated.html",
        {"draft": draft, "project": project, "submission": submission},
    )
```

### draft_consultation (GET/POST) — 상담 내용 입력

```python
@login_required
def draft_consultation(request, pk, sub_pk):
    """상담 내용 직접 입력."""
    org, project, submission, draft = _get_draft_context(request, pk, sub_pk)

    if request.method == "POST":
        draft.consultation_input = request.POST.get("consultation_input", "")
        draft.save(update_fields=["consultation_input", "updated_at"])

        # AI 상담 정리
        from projects.services.draft_consultation import summarize_consultation
        try:
            summarize_consultation(draft)
        except Exception:
            pass  # 정리 실패해도 입력은 저장됨

        from projects.services.draft_pipeline import transition_draft
        if draft.status == DraftStatus.DRAFT_GENERATED:
            transition_draft(draft, DraftStatus.CONSULTATION_ADDED)

        return render(
            request,
            "projects/partials/draft_step_consultation.html",
            {"draft": draft, "project": project, "submission": submission},
        )

    return render(
        request,
        "projects/partials/draft_step_consultation.html",
        {"draft": draft, "project": project, "submission": submission},
    )
```

### draft_consultation_audio (POST) — 녹음 업로드 + 딕테이션

```python
ALLOWED_AUDIO_EXTENSIONS = {".webm", ".mp4", ".m4a", ".ogg", ".wav", ".mp3"}
MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25MB (Whisper API limit)


@login_required
@require_http_methods(["POST"])
def draft_consultation_audio(request, pk, sub_pk):
    """녹음 파일 업로드 + Whisper 딕테이션."""
    org, project, submission, draft = _get_draft_context(request, pk, sub_pk)

    audio_file = request.FILES.get("audio_file")
    if not audio_file:
        return HttpResponse("오디오 파일이 필요합니다.", status=400)

    # 파일 검증
    import os
    ext = os.path.splitext(audio_file.name)[1].lower()
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        return HttpResponse(
            f"지원하지 않는 오디오 형식입니다. ({', '.join(ALLOWED_AUDIO_EXTENSIONS)})",
            status=400,
        )
    if audio_file.size > MAX_AUDIO_SIZE:
        return HttpResponse("오디오 파일은 25MB 이하만 가능합니다.", status=400)
    if audio_file.size == 0:
        return HttpResponse("빈 오디오 파일입니다.", status=400)

    # 저장 + 딕테이션
    draft.consultation_audio = audio_file
    draft.save(update_fields=["consultation_audio", "updated_at"])

    from candidates.services.whisper import transcribe_audio
    try:
        transcript = transcribe_audio(audio_file)
        draft.consultation_transcript = transcript
        draft.save(update_fields=["consultation_transcript", "updated_at"])
    except RuntimeError as e:
        return render(
            request,
            "projects/partials/draft_error.html",
            {"error": str(e), "draft": draft},
        )

    # AI 상담 정리 (transcript 포함)
    from projects.services.draft_consultation import summarize_consultation
    try:
        summarize_consultation(draft)
    except Exception:
        pass  # 정리 실패해도 transcript는 저장됨

    from projects.services.draft_pipeline import transition_draft
    if draft.status == DraftStatus.DRAFT_GENERATED:
        transition_draft(draft, DraftStatus.CONSULTATION_ADDED)

    return render(
        request,
        "projects/partials/draft_step_consultation.html",
        {"draft": draft, "project": project, "submission": submission},
    )
```

### draft_finalize (POST) — AI 최종 정리

```python
@login_required
@require_http_methods(["POST"])
def draft_finalize(request, pk, sub_pk):
    """AI 최종 정리: 초안 + 상담 병합."""
    org, project, submission, draft = _get_draft_context(request, pk, sub_pk)

    allowed_statuses = {
        DraftStatus.DRAFT_GENERATED,
        DraftStatus.CONSULTATION_ADDED,
        DraftStatus.REVIEWED,  # 회귀: 재정리
    }
    if draft.status not in allowed_statuses:
        return HttpResponse("현재 상태에서는 AI 정리를 실행할 수 없습니다.", status=400)

    from projects.services.draft_finalizer import finalize_draft
    try:
        finalize_draft(draft)
    except Exception as e:
        return render(
            request,
            "projects/partials/draft_error.html",
            {"error": str(e), "draft": draft},
        )

    from projects.services.draft_pipeline import transition_draft
    transition_draft(draft, DraftStatus.FINALIZED)

    return render(
        request,
        "projects/partials/draft_step_review.html",
        {"draft": draft, "project": project, "submission": submission},
    )
```

### draft_review (GET/POST) — 컨설턴트 검토/수정

```python
@login_required
def draft_review(request, pk, sub_pk):
    """컨설턴트가 final_content_json을 직접 수정."""
    org, project, submission, draft = _get_draft_context(request, pk, sub_pk)

    if request.method == "POST":
        import json
        try:
            updated_content = json.loads(request.POST.get("final_content", "{}"))
        except json.JSONDecodeError:
            return HttpResponse("유효하지 않은 데이터 형식입니다.", status=400)

        draft.final_content_json = updated_content
        draft.save(update_fields=["final_content_json", "updated_at"])

        from projects.services.draft_pipeline import transition_draft
        if draft.status == DraftStatus.FINALIZED:
            transition_draft(draft, DraftStatus.REVIEWED)

        return render(
            request,
            "projects/partials/draft_step_review.html",
            {"draft": draft, "project": project, "submission": submission},
        )

    return render(
        request,
        "projects/partials/draft_step_review.html",
        {"draft": draft, "project": project, "submission": submission},
    )
```

### draft_convert (POST) — 제출용 Word 변환

```python
@login_required
@require_http_methods(["POST"])
def draft_convert(request, pk, sub_pk):
    """제출용 Word 파일 변환 + 마스킹."""
    org, project, submission, draft = _get_draft_context(request, pk, sub_pk)

    allowed_statuses = {DraftStatus.REVIEWED, DraftStatus.CONVERTED}
    if draft.status not in allowed_statuses:
        return HttpResponse("검토 완료 후 변환할 수 있습니다.", status=400)

    # 마스킹/언어 설정 업데이트
    import json
    masking_str = request.POST.get("masking_config", "")
    if masking_str:
        try:
            draft.masking_config = json.loads(masking_str)
        except json.JSONDecodeError:
            pass
    output_language = request.POST.get("output_language", draft.output_language)
    if output_language in dict(OutputLanguage.choices):
        draft.output_language = output_language
    draft.save(update_fields=["masking_config", "output_language", "updated_at"])

    from projects.services.draft_converter import convert_to_word
    try:
        convert_to_word(draft)
    except Exception as e:
        return render(
            request,
            "projects/partials/draft_error.html",
            {"error": str(e), "draft": draft},
        )

    # output_file → Submission.document_file 복사
    if draft.output_file:
        submission.document_file = draft.output_file
        submission.save(update_fields=["document_file", "updated_at"])

    from projects.services.draft_pipeline import transition_draft
    if draft.status != DraftStatus.CONVERTED:
        transition_draft(draft, DraftStatus.CONVERTED)

    return render(
        request,
        "projects/partials/draft_step_converted.html",
        {"draft": draft, "project": project, "submission": submission},
    )
```

### draft_preview (GET) — 미리보기

```python
@login_required
def draft_preview(request, pk, sub_pk):
    """현재 단계의 데이터를 미리보기."""
    org, project, submission, draft = _get_draft_context(request, pk, sub_pk)

    # final_content_json이 있으면 최종, 없으면 auto_draft_json
    preview_data = draft.final_content_json or draft.auto_draft_json

    return render(
        request,
        "projects/partials/draft_preview.html",
        {
            "draft": draft,
            "project": project,
            "submission": submission,
            "preview_data": preview_data,
        },
    )
```

---

## Step 5: AI 초안 생성 서비스

### projects/services/draft_generator.py

```python
"""AI 초안 생성 + 자동 보정 (Gemini API)."""

import logging

from django.conf import settings
from google import genai

from data_extraction.services.extraction.sanitizers import parse_llm_json

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"


def _get_gemini_client() -> genai.Client:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in settings")
    return genai.Client(api_key=api_key)


def _collect_candidate_data(candidate) -> dict:
    """Candidate 인스턴스에서 초안 생성에 필요한 모든 데이터를 수집."""
    data = {
        # 기본 정보
        "name": candidate.name,
        "name_en": candidate.name_en,
        "birth_year": candidate.birth_year,
        "gender": candidate.gender,
        "email": candidate.email,
        "phone": candidate.phone,
        "address": candidate.address,
        "current_company": candidate.current_company,
        "current_position": candidate.current_position,
        "total_experience_years": candidate.total_experience_years,
        "summary": candidate.summary,
        "self_introduction": candidate.self_introduction,
        # 연봉
        "current_salary": candidate.current_salary,
        "desired_salary": candidate.desired_salary,
        "salary_detail": candidate.salary_detail,
        # JSON 필드
        "core_competencies": candidate.core_competencies,
        "military_service": candidate.military_service,
        "family_info": candidate.family_info,
        "overseas_experience": candidate.overseas_experience,
        "awards": candidate.awards,
        "patents": candidate.patents,
        "projects": candidate.projects,
        "trainings": candidate.trainings,
        "skills": candidate.skills,
        "personal_etc": candidate.personal_etc,
        "education_etc": candidate.education_etc,
        "career_etc": candidate.career_etc,
        "skills_etc": candidate.skills_etc,
        # 관련 모델
        "careers": list(
            candidate.careers.values(
                "company", "company_en", "position", "department",
                "start_date", "end_date", "duration_text",
            )
        ),
        "educations": list(
            candidate.educations.values(
                "institution", "degree", "major", "gpa",
                "start_year", "end_year", "is_abroad",
            )
        ),
        "certifications": list(
            candidate.certifications.values(
                "name", "issuer", "acquired_date",
            )
        ),
        "language_skills": list(
            candidate.language_skills.values(
                "language", "test_name", "score", "level",
            )
        ),
    }
    return data


DRAFT_SYSTEM_PROMPT = """당신은 헤드헌팅 회사의 추천 서류 작성 전문가입니다.
후보자 데이터를 받아 고객사 제출용 추천 서류 초안을 작성합니다.

## 규칙
1. 모든 텍스트는 한국어로 작성합니다.
2. 경력 기간은 "YYYY.MM ~ YYYY.MM (N년 M개월)" 형식으로 통일합니다.
3. 회사 소개가 없는 경우 회사명으로 간략한 소개를 작성합니다.
4. 자격증 명칭은 공식 명칭으로 매칭합니다.
5. 오탈자를 교정합니다.
6. 영문명이 없으면 한국어 이름의 영문 표기를 생성합니다.

## 출력 형식
JSON으로 응답합니다. 구조:
{
  "personal_info": {
    "name": "", "name_en": "", "birth_year": null,
    "gender": "", "email": "", "phone": "", "address": ""
  },
  "summary": "전문 요약 (3-5문장)",
  "core_competencies": ["역량1", "역량2", ...],
  "careers": [
    {
      "company": "", "company_en": "", "company_intro": "",
      "position": "", "department": "",
      "period": "", "duration": "",
      "responsibilities": ["업무1", ...]
    }
  ],
  "educations": [
    {"institution": "", "degree": "", "major": "", "period": ""}
  ],
  "certifications": [
    {"name": "", "issuer": "", "date": ""}
  ],
  "language_skills": [
    {"language": "", "test": "", "score": "", "level": ""}
  ],
  "skills": ["기술1", "기술2", ...],
  "military": {"status": "", "branch": "", "period": ""},
  "additional": {
    "awards": [...],
    "patents": [...],
    "overseas": [...],
    "training": [...],
    "self_introduction": ""
  },
  "corrections": [
    {"field": "", "original": "", "corrected": "", "reason": ""}
  ]
}
"""


def _build_draft_prompt(candidate_data: dict) -> str:
    """Gemini에 전달할 프롬프트 구성."""
    import json
    return f"""아래 후보자 데이터를 엑스다임 추천 서류 양식에 맞게 구조화하세요.
자동 보정(오탈자, 서식 통일, 영문명 생성, 회사 소개 작성, 자격증 명칭 매칭)을 수행하고,
보정 내역을 corrections 배열에 기록하세요.

후보자 데이터:
{json.dumps(candidate_data, ensure_ascii=False, indent=2)}
"""


def generate_draft(draft) -> None:
    """AI 초안 생성. draft 객체에 결과를 저장한다."""
    candidate = draft.submission.candidate

    candidate_data = _collect_candidate_data(candidate)
    client = _get_gemini_client()
    prompt = _build_draft_prompt(candidate_data)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=DRAFT_SYSTEM_PROMPT,
            max_output_tokens=8000,
            temperature=0.3,
            response_mime_type="application/json",
        ),
    )

    result = parse_llm_json(response.text)
    if not isinstance(result, dict):
        raise RuntimeError("AI 초안 생성에 실패했습니다. 잘못된 응답 형식.")

    # corrections 분리 저장
    corrections = result.pop("corrections", [])

    draft.auto_draft_json = result
    draft.auto_corrections = corrections if isinstance(corrections, list) else []
    draft.status = "draft_generated"
    draft.save(update_fields=[
        "auto_draft_json", "auto_corrections", "status", "updated_at",
    ])
```

---

## Step 6: 상담 내용 처리 서비스

### projects/services/draft_consultation.py

```python
"""상담 내용 처리 (직접 입력 정리, AI 정리)."""

import logging

from django.conf import settings
from google import genai

from data_extraction.services.extraction.sanitizers import parse_llm_json

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

CONSULTATION_SYSTEM_PROMPT = """당신은 헤드헌팅 상담 내용을 정리하는 전문가입니다.
컨설턴트가 후보자와 상담한 내용을 구조화합니다.

## 출력 형식
JSON으로 응답합니다:
{
  "motivation": "이직 동기",
  "salary_expectation": "희망 연봉 관련 내용",
  "availability": "입사 가능 시기",
  "strengths": ["강점1", ...],
  "concerns": ["우려 사항1", ...],
  "additional_info": "기타 특이사항",
  "key_points": ["핵심 포인트1", ...]
}
"""


def summarize_consultation(draft) -> None:
    """상담 내용(직접 입력 + transcript)을 AI로 정리."""
    # 입력 소스 병합
    parts = []
    if draft.consultation_input:
        parts.append(f"[직접 입력]\n{draft.consultation_input}")
    if draft.consultation_transcript:
        parts.append(f"[녹음 내용]\n{draft.consultation_transcript}")

    if not parts:
        return  # 입력 없으면 정리할 것 없음

    combined = "\n\n".join(parts)

    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=f"아래 상담 내용을 정리해주세요:\n\n{combined}",
        config=genai.types.GenerateContentConfig(
            system_instruction=CONSULTATION_SYSTEM_PROMPT,
            max_output_tokens=4000,
            temperature=0.3,
            response_mime_type="application/json",
        ),
    )

    result = parse_llm_json(response.text)
    if isinstance(result, dict):
        draft.consultation_summary = result
        draft.save(update_fields=["consultation_summary", "updated_at"])
```

---

## Step 7: AI 최종 정리 서비스

### projects/services/draft_finalizer.py

```python
"""AI 최종 정리 (초안 + 상담 병합)."""

import json
import logging

from django.conf import settings
from google import genai

from data_extraction.services.extraction.sanitizers import parse_llm_json

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

FINALIZE_SYSTEM_PROMPT = """당신은 헤드헌팅 추천 서류 최종 정리 전문가입니다.
AI 초안과 상담 내용을 병합하여 최종 추천 서류 데이터를 완성합니다.

## 규칙
1. 초안의 구조를 유지하되, 상담 내용을 반영하여 보완합니다.
2. 이직 동기, 강점, 희망 연봉 등 상담에서 얻은 정보를 적절한 섹션에 추가합니다.
3. 상담 내용과 초안이 충돌하면 상담 내용을 우선합니다 (최신 정보).
4. 출력은 초안과 동일한 JSON 구조입니다 (corrections 제외).
"""


def finalize_draft(draft) -> None:
    """초안 + 상담 병합 → final_content_json 저장."""
    if not draft.auto_draft_json:
        raise RuntimeError("초안이 생성되지 않았습니다.")

    prompt_parts = [
        f"## AI 초안\n{json.dumps(draft.auto_draft_json, ensure_ascii=False, indent=2)}"
    ]

    if draft.consultation_summary:
        prompt_parts.append(
            f"## 상담 정리\n{json.dumps(draft.consultation_summary, ensure_ascii=False, indent=2)}"
        )
    if draft.consultation_input:
        prompt_parts.append(f"## 상담 원문 (참고용)\n{draft.consultation_input}")

    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents="아래 초안과 상담 내용을 병합하여 최종 추천 서류 데이터를 완성하세요.\n\n"
                 + "\n\n".join(prompt_parts),
        config=genai.types.GenerateContentConfig(
            system_instruction=FINALIZE_SYSTEM_PROMPT,
            max_output_tokens=8000,
            temperature=0.3,
            response_mime_type="application/json",
        ),
    )

    result = parse_llm_json(response.text)
    if not isinstance(result, dict):
        raise RuntimeError("AI 최종 정리에 실패했습니다.")

    draft.final_content_json = result
    draft.save(update_fields=["final_content_json", "updated_at"])
```

---

## Step 8: Word 변환 + 마스킹 서비스

### projects/services/draft_converter.py

```python
"""Word 변환 + 마스킹 처리 (python-docx)."""

import io
import logging

from django.core.files.base import ContentFile
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

from projects.models import DEFAULT_MASKING_CONFIG

logger = logging.getLogger(__name__)

# 마스킹 대상 필드 매핑
MASKING_FIELDS = {
    "salary": ["current_salary", "desired_salary", "salary_detail", "salary_expectation"],
    "birth_detail": ["birth_year"],
    "contact": ["email", "phone", "address"],
    "current_company": ["current_company"],
}


def _apply_masking(data: dict, masking_config: dict) -> dict:
    """마스킹 설정에 따라 데이터에서 민감 필드를 제거."""
    import copy
    masked = copy.deepcopy(data)

    for mask_key, should_mask in masking_config.items():
        if not should_mask:
            continue
        fields = MASKING_FIELDS.get(mask_key, [])
        for field in fields:
            # top-level
            if field in masked:
                masked[field] = "[마스킹]"
            # personal_info nested
            if "personal_info" in masked and field in masked["personal_info"]:
                masked["personal_info"][field] = "[마스킹]"
            # additional nested
            if "additional" in masked and field in masked.get("additional", {}):
                masked["additional"][field] = "[마스킹]"

    return masked


def _add_section(doc: Document, title: str, content: str | list | dict) -> None:
    """Word 문서에 섹션 추가."""
    doc.add_heading(title, level=2)

    if isinstance(content, str):
        doc.add_paragraph(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                for k, v in item.items():
                    if v and v != "[마스킹]":
                        doc.add_paragraph(f"{k}: {v}", style="List Bullet")
            else:
                doc.add_paragraph(str(item), style="List Bullet")
    elif isinstance(content, dict):
        for k, v in content.items():
            if v and v != "[마스킹]":
                doc.add_paragraph(f"{k}: {v}")


def _build_document(data: dict) -> Document:
    """final_content_json에서 Word 문서 생성."""
    doc = Document()

    # 스타일 설정
    style = doc.styles["Normal"]
    font = style.font
    font.name = "맑은 고딕"
    font.size = Pt(10)

    # 제목
    personal = data.get("personal_info", {})
    name = personal.get("name", "")
    name_en = personal.get("name_en", "")
    title = f"추천 서류 — {name}"
    if name_en:
        title += f" ({name_en})"
    heading = doc.add_heading(title, level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 인적사항
    if personal:
        _add_section(doc, "인적사항", personal)

    # 요약
    if data.get("summary"):
        _add_section(doc, "전문 요약", data["summary"])

    # 핵심 역량
    if data.get("core_competencies"):
        _add_section(doc, "핵심 역량", data["core_competencies"])

    # 경력
    if data.get("careers"):
        doc.add_heading("경력사항", level=2)
        for career in data["careers"]:
            company = career.get("company", "")
            position = career.get("position", "")
            period = career.get("period", "")
            doc.add_heading(f"{company} — {position} ({period})", level=3)
            if career.get("company_intro"):
                doc.add_paragraph(career["company_intro"])
            if career.get("responsibilities"):
                for resp in career["responsibilities"]:
                    doc.add_paragraph(resp, style="List Bullet")

    # 학력
    if data.get("educations"):
        _add_section(doc, "학력", data["educations"])

    # 자격증
    if data.get("certifications"):
        _add_section(doc, "자격증/면허", data["certifications"])

    # 어학
    if data.get("language_skills"):
        _add_section(doc, "어학능력", data["language_skills"])

    # 기술
    if data.get("skills"):
        _add_section(doc, "보유 기술", data["skills"])

    # 병역
    if data.get("military"):
        military = data["military"]
        if any(v for v in military.values()):
            _add_section(doc, "병역", military)

    # 기타
    if data.get("additional"):
        additional = data["additional"]
        for key, label in [
            ("awards", "수상경력"),
            ("patents", "특허"),
            ("overseas", "해외경험"),
            ("training", "교육이수"),
        ]:
            if additional.get(key):
                _add_section(doc, label, additional[key])
        if additional.get("self_introduction"):
            _add_section(doc, "자기소개", additional["self_introduction"])

    return doc


def convert_to_word(draft) -> None:
    """Draft의 final_content_json을 Word 파일로 변환."""
    data = draft.final_content_json
    if not data:
        raise RuntimeError("최종 정리 데이터가 없습니다.")

    # 마스킹 적용
    masked_data = _apply_masking(data, draft.masking_config or DEFAULT_MASKING_CONFIG)

    # Word 문서 생성
    doc = _build_document(masked_data)

    # 파일로 저장
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    candidate_name = draft.submission.candidate.name
    filename = f"추천서류_{candidate_name}.docx"
    draft.output_file.save(filename, ContentFile(buffer.read()), save=True)
```

---

## Step 9: 템플릿 구현

### projects/templates/projects/submission_draft.html (full page)

```html
{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}

{% block content %}
<div class="max-w-5xl mx-auto px-4 py-6">
  {# 헤더 #}
  <div class="flex items-center justify-between mb-6">
    <div>
      <h1 class="text-xl font-bold text-gray-900">
        추천 서류 초안 작업
      </h1>
      <p class="text-sm text-gray-500 mt-1">
        {{ submission.candidate.name }} — {{ project.title }}
      </p>
    </div>
    <a href="{% url 'projects:project_detail' project.pk %}"
       hx-get="{% url 'projects:project_tab_submissions' project.pk %}"
       hx-target="#tab-content"
       class="text-sm text-gray-500 hover:text-gray-700">
      ← 추천 목록으로
    </a>
  </div>

  {# 진행 단계 표시 #}
  {% include "projects/partials/draft_progress.html" %}

  {# 현재 단계 콘텐츠 #}
  <div id="draft-content">
    {% include "projects/partials/draft_current_step.html" %}
  </div>
</div>
{% endblock %}
```

### 단계별 partial 목록

| 파일 | 용도 | 포함 단계 |
|------|------|----------|
| `partials/draft_progress.html` | 진행 단계 바 | 전체 |
| `partials/draft_current_step.html` | 현재 단계 분기 | 전체 |
| `partials/draft_step_pending.html` | 대기 → 초안 생성 버튼 | PENDING |
| `partials/draft_step_generated.html` | 초안 결과 + 보정 내역 + 다음 단계 | DRAFT_GENERATED |
| `partials/draft_step_consultation.html` | 상담 입력 폼 + 녹음 업로드 | CONSULTATION |
| `partials/draft_step_review.html` | 최종 정리 결과 + 편집 | FINALIZED/REVIEWED |
| `partials/draft_step_convert.html` | 변환 옵션 (마스킹, 언어) + 변환 버튼 | REVIEWED |
| `partials/draft_step_converted.html` | 변환 완료 + 다운로드 링크 | CONVERTED |
| `partials/draft_preview.html` | 미리보기 | 모든 단계 |
| `partials/draft_error.html` | 에러 메시지 | 에러 시 |

### tab_submissions.html 수정

기존 Submission 카드에 "초안 작업" 버튼 추가:

```html
{# 기존 수정/삭제 버튼 옆에 추가 #}
<a href="{% url 'projects:submission_draft' project.pk submission.pk %}"
   hx-get="{% url 'projects:submission_draft' project.pk submission.pk %}"
   hx-target="#main-content"
   hx-push-url="true"
   class="text-sm text-primary hover:text-primary/80">
  초안 작업
</a>
```

---

## Step 10: 기존 코드 수정

### projects/services/submission.py 수정

`submit_to_client()` 호출 전 document_file 존재 검증:

```python
def submit_to_client(submission: Submission) -> Submission:
    """작성중 → 제출. submitted_at 기록."""
    if submission.status != Submission.Status.DRAFTING:
        raise InvalidTransition(
            f"'{submission.get_status_display()}' 상태에서는 제출할 수 없습니다."
        )
    if not submission.document_file:
        raise InvalidTransition("제출할 서류 파일이 없습니다.")
    submission.status = Submission.Status.SUBMITTED
    submission.submitted_at = timezone.now()
    submission.save(update_fields=["status", "submitted_at"])
    return submission
```

### projects/views.py — submission_delete 수정

converted draft 경고 추가 (CASCADE 삭제는 유지):

```python
@login_required
@require_http_methods(["POST"])
def submission_delete(request, pk, sub_pk):
    """추천 서류 삭제. 면접/오퍼 존재 시 차단."""
    org = _get_org(request)
    project = get_object_or_404(Project, pk=pk, organization=org)
    submission = get_object_or_404(Submission, pk=sub_pk, project=project)

    # 삭제 보호: 면접 또는 오퍼 존재 시 차단
    has_interviews = submission.interviews.exists()
    has_offer = False
    try:
        submission.offer
        has_offer = True
    except Offer.DoesNotExist:
        has_offer = False

    if has_interviews or has_offer:
        # ... 기존 차단 로직 유지
        pass

    # draft는 CASCADE로 함께 삭제 (별도 차단 없음)
    submission.delete()
    return HttpResponse(status=204, headers={"HX-Trigger": "submissionChanged"})
```

---

## Step 11: 테스트

### tests/test_p08_draft_pipeline.py

```python
"""P08: AI Document Pipeline tests."""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as TestClient
from django.urls import reverse

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import (
    DraftStatus,
    Project,
    ProjectStatus,
    Submission,
    SubmissionDraft,
    SubmissionTemplate,
)
from projects.services.draft_pipeline import (
    InvalidDraftTransition,
    transition_draft,
)
```

### 테스트 항목

| # | 테스트 | 카테고리 |
|---|--------|---------|
| 1 | `test_draft_creation_defaults` | 모델 |
| 2 | `test_draft_onetoone_constraint` | 모델 |
| 3 | `test_draft_cascade_delete` | 모델 |
| 4 | `test_valid_transitions` | 상태 전이 |
| 5 | `test_invalid_transition` | 상태 전이 |
| 6 | `test_skip_consultation` | 상태 전이 |
| 7 | `test_regression_reviewed_to_finalized` | 상태 전이 |
| 8 | `test_draft_view_login_required` | 보안 |
| 9 | `test_draft_view_org_isolation` | 보안 |
| 10 | `test_submission_draft_get_or_create` | 뷰 |
| 11 | `test_draft_generate_success` | AI (mock) |
| 12 | `test_draft_generate_gemini_failure` | AI 에러 |
| 13 | `test_draft_generate_invalid_response` | AI 에러 |
| 14 | `test_consultation_text_input` | 상담 |
| 15 | `test_consultation_audio_upload` | 상담 |
| 16 | `test_consultation_audio_invalid_format` | 검증 |
| 17 | `test_consultation_audio_too_large` | 검증 |
| 18 | `test_consultation_audio_empty` | 검증 |
| 19 | `test_whisper_hallucination_filtered` | Whisper |
| 20 | `test_finalize_success` | AI (mock) |
| 21 | `test_finalize_without_draft` | 에러 |
| 22 | `test_finalize_invalid_status` | 상태 |
| 23 | `test_review_update_content` | 뷰 |
| 24 | `test_review_invalid_json` | 검증 |
| 25 | `test_convert_to_word` | 변환 |
| 26 | `test_convert_masking_applied` | 마스킹 |
| 27 | `test_convert_copies_to_submission` | 연동 |
| 28 | `test_convert_before_review_blocked` | 상태 |
| 29 | `test_submit_without_document_blocked` | 제출 검증 |
| 30 | `test_htmx_responses` | HTMX |

### 핵심 테스트 코드

```python
# 보안: login_required
def test_draft_view_login_required(client):
    """비로그인 시 draft 뷰 접근 차단."""
    url = reverse("projects:submission_draft", args=[project.pk, submission.pk])
    response = client.get(url)
    assert response.status_code == 302  # redirect to login

# 보안: org isolation
def test_draft_view_org_isolation(auth_client2, project, submission):
    """다른 조직의 submission draft 접근 차단."""
    url = reverse("projects:submission_draft", args=[project.pk, submission.pk])
    response = auth_client2.get(url)
    assert response.status_code == 404

# AI 에러: Gemini 실패
@patch("projects.services.draft_generator._get_gemini_client")
def test_draft_generate_gemini_failure(mock_client, auth_client, project, submission):
    """Gemini API 실패 시 에러 화면 렌더."""
    mock_client.return_value.models.generate_content.side_effect = Exception("API Error")
    url = reverse("projects:draft_generate", args=[project.pk, submission.pk])
    response = auth_client.post(url)
    assert response.status_code == 200
    assert "에러" in response.content.decode() or "error" in response.content.decode().lower()

# 오디오 검증
def test_consultation_audio_invalid_format(auth_client, project, submission):
    """지원하지 않는 오디오 형식 거부."""
    audio = SimpleUploadedFile("test.txt", b"not audio", content_type="text/plain")
    url = reverse("projects:draft_consultation_audio", args=[project.pk, submission.pk])
    response = auth_client.post(url, {"audio_file": audio})
    assert response.status_code == 400

# 변환 + 마스킹
@patch("projects.services.draft_converter.Document")
def test_convert_masking_applied(mock_doc, auth_client, project, submission):
    """마스킹 설정이 Word 변환에 적용되는지 확인."""
    draft = SubmissionDraft.objects.create(
        submission=submission,
        status=DraftStatus.REVIEWED,
        final_content_json={
            "personal_info": {"name": "홍길동", "email": "test@test.com", "phone": "010-1234"},
            "summary": "테스트",
        },
        masking_config={"contact": True, "salary": False, "birth_detail": False, "current_company": False},
    )
    url = reverse("projects:draft_convert", args=[project.pk, submission.pk])
    response = auth_client.post(url)
    # draft.output_file이 생성되었는지 확인
    draft.refresh_from_db()
    assert draft.output_file

# 제출 검증
def test_submit_without_document_blocked(submission):
    """document_file 없이 제출 시 차단."""
    from projects.services.submission import InvalidTransition, submit_to_client
    submission.document_file = ""
    submission.save()
    with pytest.raises(InvalidTransition, match="서류 파일"):
        submit_to_client(submission)
```

---

## 산출물 목록

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `projects/models.py` | 수정 | DraftStatus, OutputLanguage, OutputFormat, SubmissionDraft 모델 추가 |
| `projects/urls.py` | 수정 | Draft 관련 URL 8개 추가 |
| `projects/views.py` | 수정 | Draft 관련 뷰 8개 + 공통 헬퍼 추가 |
| `projects/forms.py` | 수정 | (필요 시) Draft 관련 폼 |
| `projects/services/draft_pipeline.py` | 신규 | 상태 전이 서비스 |
| `projects/services/draft_generator.py` | 신규 | AI 초안 생성 + 보정 (Gemini) |
| `projects/services/draft_consultation.py` | 신규 | 상담 내용 처리 (Whisper + AI 정리) |
| `projects/services/draft_finalizer.py` | 신규 | AI 최종 정리 |
| `projects/services/draft_converter.py` | 신규 | Word 변환 + 마스킹 |
| `projects/services/submission.py` | 수정 | submit_to_client에 document_file 검증 추가 |
| `projects/templates/projects/submission_draft.html` | 신규 | Draft 메인 full-page |
| `projects/templates/projects/partials/draft_*.html` | 신규 | 각 단계 partial 10개 |
| `projects/templates/projects/partials/tab_submissions.html` | 수정 | "초안 작업" 버튼 추가 |
| `projects/migrations/0xxx_p08_submission_draft.py` | 신규 | SubmissionDraft migration |
| `tests/test_p08_draft_pipeline.py` | 신규 | 30개 테스트 |

---

## 실행 순서

1. **Step 1:** 모델 + migration (SubmissionDraft)
2. **Step 2:** 상태 전이 서비스 (draft_pipeline.py) + 테스트
3. **Step 3:** URL 등록
4. **Step 4:** View 구현 (8개 뷰 + 헬퍼)
5. **Step 5:** AI 초안 생성 서비스 (draft_generator.py)
6. **Step 6:** 상담 내용 처리 서비스 (draft_consultation.py)
7. **Step 7:** AI 최종 정리 서비스 (draft_finalizer.py)
8. **Step 8:** Word 변환 서비스 (draft_converter.py)
9. **Step 9:** 템플릿 구현 (full page + partial 10개)
10. **Step 10:** 기존 코드 수정 (submission.py, tab_submissions.html)
11. **Step 11:** 전체 테스트

<!-- forge:p08:구현담금질:complete:2026-04-08T12:00:00+09:00 -->
