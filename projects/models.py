from django.conf import settings
from django.db import models
from django.utils import timezone

from common.mixins import BaseModel


class JDSource(models.TextChoices):
    UPLOAD = "upload", "파일 업로드"
    DRIVE = "drive", "Google Drive"
    TEXT = "text", "텍스트 입력"


class ProjectStatus(models.TextChoices):
    NEW = "new", "신규"
    SEARCHING = "searching", "서칭중"
    RECOMMENDING = "recommending", "추천진행"
    INTERVIEWING = "interviewing", "면접진행"
    NEGOTIATING = "negotiating", "오퍼협상"
    CLOSED_SUCCESS = "closed_success", "클로즈(성공)"
    CLOSED_FAIL = "closed_fail", "클로즈(실패)"
    CLOSED_CANCEL = "closed_cancel", "클로즈(취소)"
    ON_HOLD = "on_hold", "보류"
    PENDING_APPROVAL = "pending_approval", "승인대기"


class Project(BaseModel):
    """의뢰 건 (헤드헌팅 프로젝트)."""

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="projects",
    )
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="projects",
    )
    title = models.CharField(max_length=300)
    jd_text = models.TextField(blank=True)
    jd_file = models.FileField(upload_to="projects/jd/", blank=True)
    jd_source = models.CharField(max_length=20, choices=JDSource.choices, blank=True)
    jd_drive_file_id = models.CharField(max_length=255, blank=True)
    jd_raw_text = models.TextField(blank=True)
    jd_analysis = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=30,
        choices=ProjectStatus.choices,
        default=ProjectStatus.NEW,
    )
    assigned_consultants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="assigned_projects",
    )
    requirements = models.JSONField(default=dict, blank=True)
    posting_text = models.TextField(blank=True)
    posting_file_name = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_projects",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def days_elapsed(self) -> int:
        return (timezone.now().date() - self.created_at.date()).days


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
        Project,
        on_delete=models.CASCADE,
        related_name="contacts",
    )
    candidate = models.ForeignKey(
        "candidates.Candidate",
        on_delete=models.CASCADE,
        related_name="project_contacts",
    )
    consultant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="contacts",
    )
    channel = models.CharField(
        max_length=20, choices=Channel.choices, blank=True
    )  # P06: blank for reserved
    contacted_at = models.DateTimeField(
        null=True, blank=True
    )  # P06: nullable for reserved
    result = models.CharField(max_length=20, choices=Result.choices)
    notes = models.TextField(blank=True)
    locked_until = models.DateTimeField(null=True, blank=True)
    next_contact_date = models.DateField(null=True, blank=True)  # 재컨택 예정일

    class Meta:
        ordering = ["-contacted_at"]

    def __str__(self) -> str:
        return f"{self.project} - {self.candidate} ({self.channel})"

    @property
    def is_reserved(self) -> bool:
        """예정 상태이고 잠금이 유효한지."""
        return (
            self.result == self.Result.RESERVED
            and self.locked_until is not None
            and self.locked_until > timezone.now()
        )

    @property
    def is_expired_reservation(self) -> bool:
        """만료된 예정인지."""
        return self.result == self.Result.RESERVED and (
            self.locked_until is None or self.locked_until <= timezone.now()
        )


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
        Project,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    candidate = models.ForeignKey(
        "candidates.Candidate",
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    consultant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="submissions",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFTING,
    )
    template = models.CharField(
        max_length=20,
        choices=SubmissionTemplate.choices,
        blank=True,
        default="",
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
    consultation_audio = models.FileField(upload_to="drafts/audio/", blank=True)
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
    output_file = models.FileField(upload_to="drafts/output/", blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Draft: {self.submission} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # masking_config 기본값 보장
        if not self.masking_config:
            self.masking_config = DEFAULT_MASKING_CONFIG.copy()
        super().save(*args, **kwargs)


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
    location = models.CharField(max_length=500, blank=True)
    result = models.CharField(
        max_length=20,
        choices=Result.choices,
        default=Result.PENDING,
    )
    feedback = models.TextField(blank=True)
    notes = models.TextField(blank=True)

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
    notes = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Offer: {self.submission}"


class ConflictType(models.TextChoices):
    HIGH = "높은중복", "높은 중복 가능성"
    MEDIUM = "참고정보", "참고 정보"


class ProjectApproval(BaseModel):
    """충돌 감지 승인 요청."""

    class Status(models.TextChoices):
        PENDING = "대기", "대기"
        APPROVED = "승인", "승인"
        JOINED = "합류", "합류"
        REJECTED = "반려", "반려"

    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approvals",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="approval_requests",
    )
    conflict_project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conflict_approvals",
    )
    conflict_score = models.FloatField(default=0.0)
    conflict_type = models.CharField(
        max_length=20,
        choices=ConflictType.choices,
        blank=True,
        default="",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    message = models.TextField(blank=True)
    admin_response = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_decisions",
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Approval: {self.project} ({self.status})"


class ProjectContext(BaseModel):
    """업무 연속성 컨텍스트."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="contexts",
    )
    consultant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_contexts",
    )
    last_step = models.CharField(max_length=100, blank=True)
    pending_action = models.CharField(max_length=100, blank=True)
    draft_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "consultant"],
                name="unique_context_per_project_consultant",
            )
        ]

    def __str__(self) -> str:
        return f"Context: {self.project} - {self.consultant}"


class Notification(BaseModel):
    """알림 시스템."""

    class Type(models.TextChoices):
        APPROVAL_REQUEST = "approval_request", "승인 요청"
        AUTO_GENERATED = "auto_generated", "자동 생성"
        REMINDER = "reminder", "리마인더"
        NEWS = "news", "뉴스"

    class Status(models.TextChoices):
        PENDING = "pending", "대기"
        SENT = "sent", "전송됨"
        READ = "read", "읽음"
        ACTED = "acted", "처리됨"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(max_length=30, choices=Type.choices)
    title = models.CharField(max_length=300)
    body = models.TextField()
    action_url = models.URLField(blank=True)
    telegram_message_id = models.CharField(max_length=100, blank=True)
    telegram_chat_id = models.CharField(max_length=100, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    callback_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class PostingSiteChoice(models.TextChoices):
    JOBKOREA = "jobkorea", "잡코리아"
    SARAMIN = "saramin", "사람인"
    INCRUIT = "incruit", "인크루트"
    LINKEDIN = "linkedin", "LinkedIn"
    WANTED = "wanted", "원티드"
    CATCH = "catch", "캐치"
    OTHER = "other", "기타"


class PostingSite(BaseModel):
    """포스팅 사이트별 게시 현황."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="posting_sites",
    )
    site = models.CharField(
        max_length=20,
        choices=PostingSiteChoice.choices,
    )
    posted_at = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    applicant_count = models.PositiveIntegerField(default=0)
    url = models.URLField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "site"],
                name="unique_posting_site_per_project",
            )
        ]

    def __str__(self) -> str:
        return f"{self.project} - {self.get_site_display()}"


class MeetingRecord(BaseModel):
    """미팅 녹음 분석 레코드."""

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "업로드됨"
        TRANSCRIBING = "transcribing", "전사 중"
        ANALYZING = "analyzing", "분석 중"
        READY = "ready", "분석 완료"
        APPLIED = "applied", "반영 완료"
        FAILED = "failed", "실패"

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="meeting_records",
    )
    candidate = models.ForeignKey(
        "candidates.Candidate",
        on_delete=models.CASCADE,
        related_name="meeting_records",
    )
    audio_file = models.FileField(upload_to="meetings/audio/")
    transcript = models.TextField(blank=True)
    analysis_json = models.JSONField(default=dict, blank=True)
    edited_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADED,
    )
    error_message = models.TextField(blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applied_meeting_records",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_meeting_records",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Meeting: {self.candidate} ({self.status})"


class ActionType(models.TextChoices):
    POSTING_DRAFT = "posting_draft", "공지 초안"
    CANDIDATE_SEARCH = "candidate_search", "후보자 자동 서칭"
    SUBMISSION_DRAFT = "submission_draft", "제출 서류 초안"
    OFFER_TEMPLATE = "offer_template", "오퍼 템플릿"
    FOLLOWUP_REMINDER = "followup_reminder", "팔로업 리마인더"
    RECONTACT_REMINDER = "recontact_reminder", "재컨택 리마인더"


class ActionStatus(models.TextChoices):
    PENDING = "pending", "대기"
    APPLIED = "applied", "적용됨"
    DISMISSED = "dismissed", "무시됨"


class AutoAction(BaseModel):
    """이벤트 기반 자동 생성물."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="auto_actions",
    )
    trigger_event = models.CharField(max_length=100)
    action_type = models.CharField(max_length=30, choices=ActionType.choices)
    title = models.CharField(max_length=300)
    data = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ActionStatus.choices,
        default=ActionStatus.PENDING,
    )
    due_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_auto_actions",
    )
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applied_auto_actions",
    )
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dismissed_auto_actions",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"AutoAction: {self.title} ({self.status})"


class NewsSourceType(models.TextChoices):
    RSS = "rss", "RSS/뉴스"
    YOUTUBE = "youtube", "YouTube"
    BLOG = "blog", "블로그"


class NewsCategory(models.TextChoices):
    HIRING = "hiring", "채용"
    HR = "hr", "인사"
    INDUSTRY = "industry", "업계동향"
    ECONOMY = "economy", "경제/실업"


class SummaryStatus(models.TextChoices):
    PENDING = "pending", "대기"
    COMPLETED = "completed", "완료"
    FAILED = "failed", "실패"


class NewsSource(BaseModel):
    """뉴스 소스 (RSS 피드)."""

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="news_sources",
    )
    name = models.CharField(max_length=200)
    url = models.URLField()
    type = models.CharField(
        max_length=20,
        choices=NewsSourceType.choices,
        default=NewsSourceType.RSS,
    )
    category = models.CharField(
        max_length=20,
        choices=NewsCategory.choices,
    )
    is_active = models.BooleanField(default=True)
    last_fetched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class NewsArticle(BaseModel):
    """뉴스 기사."""

    source = models.ForeignKey(
        NewsSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
    )
    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True)
    raw_content = models.TextField(blank=True)
    url = models.URLField(unique=True)
    published_at = models.DateTimeField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)
    category = models.CharField(
        max_length=20,
        choices=NewsCategory.choices,
        blank=True,
    )
    summary_status = models.CharField(
        max_length=20,
        choices=SummaryStatus.choices,
        default=SummaryStatus.PENDING,
    )

    class Meta:
        ordering = ["-published_at"]

    def __str__(self) -> str:
        return self.title


class NewsArticleRelevance(BaseModel):
    """기사-프로젝트 관련도 (정규화 조인 모델)."""

    article = models.ForeignKey(
        NewsArticle,
        on_delete=models.CASCADE,
        related_name="relevances",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="news_relevances",
    )
    score = models.FloatField()
    matched_terms = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-score"]
        constraints = [
            models.UniqueConstraint(
                fields=["article", "project"],
                name="unique_article_project_relevance",
            )
        ]

    def __str__(self) -> str:
        return f"{self.article.title} -> {self.project.title} ({self.score:.2f})"


class ResumeUpload(BaseModel):
    """이력서 업로드 및 추출 추적."""

    class FileType(models.TextChoices):
        PDF = "pdf", "PDF"
        DOCX = "docx", "Word (DOCX)"
        DOC = "doc", "Word (DOC)"

    class Source(models.TextChoices):
        MANUAL = "manual", "수동 업로드"
        EMAIL = "email", "이메일"

    class Status(models.TextChoices):
        PENDING = "pending", "대기"
        EXTRACTING = "extracting", "추출중"
        EXTRACTED = "extracted", "추출완료"
        LINKED = "linked", "후보자 연결됨"
        DUPLICATE = "duplicate", "중복"
        FAILED = "failed", "실패"
        DISCARDED = "discarded", "폐기"

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="resume_uploads",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resume_uploads",
    )
    file = models.FileField(upload_to="resumes/uploads/")
    file_name = models.CharField(max_length=500)
    file_type = models.CharField(max_length=10, choices=FileType.choices)
    source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.MANUAL
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    candidate = models.ForeignKey(
        "candidates.Candidate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resume_uploads",
    )
    extraction_result = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    last_attempted_at = models.DateTimeField(null=True, blank=True)

    # Email source fields
    email_subject = models.CharField(max_length=500, blank=True)
    email_from = models.EmailField(blank=True)
    email_message_id = models.CharField(max_length=255, blank=True)
    email_attachment_id = models.CharField(max_length=255, blank=True)

    # Upload batch tracking
    upload_batch = models.UUIDField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resume_uploads",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "email_message_id", "email_attachment_id"],
                condition=models.Q(source="email"),
                name="unique_email_attachment_per_org",
            ),
        ]

    def __str__(self) -> str:
        return f"ResumeUpload: {self.file_name} ({self.get_status_display()})"
