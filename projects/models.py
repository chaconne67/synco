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


class ProjectApproval(BaseModel):
    """충돌 감지 승인 요청."""

    class Status(models.TextChoices):
        PENDING = "대기", "대기"
        APPROVED = "승인", "승인"
        JOINED = "합류", "합류"
        REJECTED = "반려", "반려"

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
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
