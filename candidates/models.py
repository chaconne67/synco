from django.db import models

from common.mixins import BaseModel


class Category(BaseModel):
    """직무 카테고리 (e.g. HR, Finance, Sales)."""

    name = models.CharField(max_length=100, unique=True)
    name_ko = models.CharField(max_length=100, blank=True)
    candidate_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "categories"
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return f"{self.name} ({self.name_ko})" if self.name_ko else self.name


class Candidate(BaseModel):
    """후보자 (헤드헌팅 대상)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "활동중"
        PLACED = "placed", "배치완료"
        INACTIVE = "inactive", "비활성"

    class Source(models.TextChoices):
        DRIVE_IMPORT = "drive_import", "드라이브 임포트"
        MANUAL = "manual", "직접 입력"
        REFERRAL = "referral", "추천"

    class ValidationStatus(models.TextChoices):
        AUTO_CONFIRMED = "auto_confirmed", "자동 확인"
        NEEDS_REVIEW = "needs_review", "검토 필요"
        CONFIRMED = "confirmed", "확인 완료"
        FAILED = "failed", "실패"

    # Basic info
    name = models.CharField(max_length=100)
    name_en = models.CharField(max_length=200, blank=True)
    birth_year = models.SmallIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=1, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=300, blank=True)

    # Categories
    categories = models.ManyToManyField(
        Category,
        blank=True,
        related_name="candidates",
    )
    primary_category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_candidates",
    )

    # Professional info
    total_experience_years = models.SmallIntegerField(null=True, blank=True)
    current_company = models.CharField(max_length=200, blank=True)
    current_position = models.CharField(max_length=200, blank=True)
    current_salary = models.IntegerField(null=True, blank=True, help_text="만원")
    desired_salary = models.IntegerField(null=True, blank=True, help_text="만원")
    core_competencies = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True)

    # Status
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    source = models.CharField(
        max_length=15,
        choices=Source.choices,
        default=Source.MANUAL,
    )

    # AI extraction metadata
    raw_text = models.TextField(blank=True)
    validation_status = models.CharField(
        max_length=20,
        choices=ValidationStatus.choices,
        default=ValidationStatus.NEEDS_REVIEW,
    )
    raw_extracted_json = models.JSONField(default=dict, blank=True)
    confidence_score = models.FloatField(null=True, blank=True)
    field_confidences = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "candidates"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["status"], name="idx_candidate_status"),
            models.Index(fields=["birth_year"], name="idx_candidate_birth_year"),
            models.Index(
                fields=["total_experience_years"],
                name="idx_candidate_exp_years",
            ),
            models.Index(
                fields=["validation_status"],
                name="idx_candidate_valid_status",
            ),
        ]

    def __str__(self):
        parts = [self.name]
        if self.current_company:
            parts.append(self.current_company)
        if self.current_position:
            parts.append(self.current_position)
        return " / ".join(parts)


class Resume(BaseModel):
    """이력서 파일 메타데이터 및 원문."""

    class ProcessingStatus(models.TextChoices):
        PENDING = "pending", "대기"
        DOWNLOADED = "downloaded", "다운로드 완료"
        EXTRACTED = "extracted", "텍스트 추출"
        PARSED = "parsed", "파싱 완료"
        FAILED = "failed", "실패"

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="resumes",
    )
    file_name = models.CharField(max_length=300)
    drive_file_id = models.CharField(max_length=100, unique=True)
    drive_folder = models.CharField(max_length=500, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    file_size = models.IntegerField(null=True, blank=True)
    raw_text = models.TextField(blank=True)
    is_primary = models.BooleanField(default=False)
    version = models.SmallIntegerField(default=1)
    processing_status = models.CharField(
        max_length=15,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
    )
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "resumes"
        ordering = ["-is_primary", "-version"]

    def __str__(self):
        return self.file_name


class Education(BaseModel):
    """학력."""

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="educations",
    )
    institution = models.CharField(max_length=100)
    degree = models.CharField(max_length=20, blank=True)
    major = models.CharField(max_length=100, blank=True)
    gpa = models.CharField(max_length=20, blank=True)
    start_year = models.IntegerField(null=True, blank=True)
    end_year = models.IntegerField(null=True, blank=True)
    is_abroad = models.BooleanField(default=False)

    class Meta:
        db_table = "educations"
        ordering = ["-end_year"]

    def __str__(self):
        return f"{self.institution} {self.degree} {self.major}".strip()


class Career(BaseModel):
    """경력."""

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="careers",
    )
    company = models.CharField(max_length=200)
    company_en = models.CharField(max_length=200, blank=True)
    position = models.CharField(max_length=200, blank=True)
    department = models.CharField(max_length=200, blank=True)
    start_date = models.CharField(max_length=20, blank=True)
    end_date = models.CharField(max_length=20, blank=True)
    is_current = models.BooleanField(default=False)
    duties = models.TextField(blank=True)
    achievements = models.TextField(blank=True)
    reason_left = models.CharField(max_length=300, blank=True)
    salary = models.IntegerField(null=True, blank=True, help_text="만원")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "careers"
        ordering = ["-is_current", "order"]
        indexes = [
            models.Index(fields=["company"], name="idx_career_company"),
        ]

    def __str__(self):
        return f"{self.company} - {self.position}"


class Certification(BaseModel):
    """자격증."""

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="certifications",
    )
    name = models.CharField(max_length=100)
    issuer = models.CharField(max_length=100, blank=True)
    acquired_date = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = "certifications"
        ordering = ["-acquired_date"]

    def __str__(self):
        return self.name


class LanguageSkill(BaseModel):
    """어학."""

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="language_skills",
    )
    language = models.CharField(max_length=30)
    test_name = models.CharField(max_length=50, blank=True)
    score = models.CharField(max_length=30, blank=True)
    level = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = "language_skills"

    def __str__(self):
        parts = [self.language]
        if self.test_name and self.score:
            parts.append(f"{self.test_name} {self.score}")
        elif self.level:
            parts.append(self.level)
        return " - ".join(parts)


class ExtractionLog(BaseModel):
    """AI 추출/사람 편집 이력."""

    class Action(models.TextChoices):
        AUTO_EXTRACT = "auto_extract", "자동 추출"
        HUMAN_EDIT = "human_edit", "사람 편집"
        HUMAN_CONFIRM = "human_confirm", "사람 확인"
        HUMAN_REJECT = "human_reject", "사람 거부"

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="extraction_logs",
    )
    resume = models.ForeignKey(
        Resume,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="extraction_logs",
    )
    action = models.CharField(
        max_length=20,
        choices=Action.choices,
    )
    field_name = models.CharField(max_length=50, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "extraction_logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()} - {self.field_name}"
