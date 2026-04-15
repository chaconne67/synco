# P17 News Feed - 확정 설계서

## 핵심 결정 요약

- **모델:** NewsSource, NewsArticle, NewsArticleRelevance를 projects 앱에 추가. 모두 BaseModel 상속
- **뉴스 수집 파이프라인:** management command `fetch_news` → RSS 파싱(feedparser) → AI 요약(Gemini, machine enum 출력) → 관련도 매칭 → 텔레그램 발송. 매일 cron 실행 (flock, Asia/Seoul)
- **관련도 매칭:** 기사 태그 vs 프로젝트(고객사명 0.9, 업종 0.6, 키워�� 0.5~0.8). `NewsArticleRelevance` join model로 정규화 저장. score 0.5 이상이면 연결
- **UI:** 뉴스피드 메인(/news/) + HTMX 카테고리 필터(전체/채용/인사/업계동향/경제) + 소스 관리 CRUD
- **텔레그램 연동:** 매일 아침 뉴스 요약 발송 (P15 바인딩된 사용자 대상, org+project 기반 선별, 일별 dedupe)
- **사이드바:** 뉴스피드 메뉴 추가 + 새 관련 뉴스 dot indicator (last_news_seen_at 기반)
- **DB 설계:** UUID PK, BaseModel 상속 (TimestampMixin 포함). NewsArticle.url에 unique 제약
- **인증:** 모든 뷰 `@login_required`. 소스 관리 CRUD는 staff/admin 권한 필요
- **조직 격리:** NewsSource에 organization FK. 뷰는 현재 사용자 조직으로 필터링

## URL 설계

**라우팅:** `projects/urls_news.py` 생성, `main/urls.py`에 `path("news/", include("projects.urls_news"))` 등록.

| URL | Method | View | 설명 | 인증 |
|-----|--------|------|------|------|
| `/news/` | GET | `news_feed` | 뉴스피드 메인 | @login_required |
| `/news/filter/` | GET | `news_filter` | 필터 적용 (HTMX partial) | @login_required |
| `/news/sources/` | GET | `news_sources` | 소스 관리 목록 | @login_required + staff |
| `/news/sources/new/` | GET/POST | `news_source_create` | 소스 추가 | @login_required + staff |
| `/news/sources/<pk>/edit/` | GET/POST | `news_source_update` | 소스 수정 | @login_required + staff |
| `/news/sources/<pk>/delete/` | POST | `news_source_delete` | 소스 삭제 | @login_required + staff |
| `/news/sources/<pk>/toggle/` | POST | `news_source_toggle` | 소스 활성/비활성 | @login_required + staff |

## 모델 설계

```python
from common.mixins import BaseModel


class NewsSourceType(models.TextChoices):
    RSS = "rss", "RSS/뉴스"
    YOUTUBE = "youtube", "YouTube"  # MVP 이후 지원
    BLOG = "blog", "블로그"  # MVP 이후 지원


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
    url = models.URLField()  # http/https only, validated in form/model clean
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
        on_delete=models.CASCADE,
        related_name="articles",
    )
    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True)
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
        return f"{self.article.title} → {self.project.title} ({self.score:.2f})"
```

## 서비스 구조

| 파일 | 역할 |
|------|------|
| `projects/services/news/fetcher.py` | RSS 파싱 + 기사 저장 (get_or_create, RSS type만 처리) |
| `projects/services/news/summarizer.py` | Gemini API 요약 + 태그/카테고리 추출 (machine enum 출력 강제) |
| `projects/services/news/matcher.py` | 프로젝트 관련도 매칭 (NewsArticleRelevance 생성) |
| `projects/management/commands/fetch_news.py` | 뉴스 수집 커맨드 (전체 파이프라인 오케스트레이션) |

### 파이프라인 처리 흐름

```
fetch_news command:
  1. NewsSource.objects.filter(is_active=True, type="rss", organization=org)
  2. For each source:
     a. fetcher.fetch_articles(source) → get_or_create articles (summary_status=pending)
     b. source.last_fetched_at = now()
  3. For articles with summary_status=pending:
     a. summarizer.summarize(article) → summary, tags, category
     b. transaction.atomic:
        article.summary = summary
        article.tags = tags
        article.category = category
        article.summary_status = completed
        article.save()
     c. On Gemini failure: article.summary_status = failed, log error
  4. For summarized articles:
     a. matcher.match(article) → create NewsArticleRelevance rows (score >= 0.5)
  5. transaction.on_commit:
     a. Build per-org digest
     b. Select recipients (TelegramBinding + active project relevance)
     c. Create Notification per recipient (dedupe: date + recipient + type="news")
     d. send_bulk_notifications() with throttle
```

### URL 유효성 검사

- `NewsSource.url`: http/https scheme만 허용 (form clean에서 검증)
- Fetcher: requests timeout=30s, max redirects=5, max content=5MB

### Gemini 요약 출력 규격

```
Summarizer prompt must enforce machine enum output:
  category: one of "hiring" | "hr" | "industry" | "economy"
  tags: list of Korean keyword strings
  summary: 2-3 sentence Korean summary
```

## 뉴스피드 UI

### 메인 (/news/)
- **상단:** 내 프로젝트 관련 뉴스 (NewsArticleRelevance로 현재 사용자의 assigned_projects 기준 조회)
- **하단:** 최신 뉴스 (조직 내 전체)
- **카테고리 필터:** 전체 / 채용 / 인사 / 업계동향 / 경제 (HTMX partial `/news/filter/`)

### 사이드바 dot indicator
- `last_news_seen_at` 필드 추가 (User 모델 또는 별도 모델)
- 뉴스피드 페이지 방문 시 갱신
- Context processor에서 최신 관련 뉴스 vs last_news_seen_at 비교하여 dot 표시

## 의존성

- `feedparser` — RSS 파싱 (`uv add feedparser`)

## Cron 실행 설정

```bash
# /etc/cron.d/synco-fetch-news (Asia/Seoul timezone)
SHELL=/bin/bash
CRON_TZ=Asia/Seoul
0 7 * * * chaconne flock -n /tmp/synco_fetch_news.lock uv run python manage.py fetch_news >> /home/docker/synco/runtime/logs/fetch_news.log 2>&1
```

## 산출물 목록

projects/models.py, projects/views_news.py, projects/urls_news.py, projects/forms.py,
projects/services/news/__init__.py, projects/services/news/fetcher.py,
projects/services/news/summarizer.py, projects/services/news/matcher.py,
projects/management/commands/fetch_news.py,
projects/templates/projects/news_feed.html, projects/templates/projects/partials/news_list.html,
projects/templates/projects/news_sources.html, projects/templates/projects/news_source_form.html,
templates/common/nav_sidebar.html (사이드바 수정), main/urls.py (뉴스 URL 등록),
tests/

Source: docs/plans/headhunting-workflow/P17-news-feed.md

<!-- forge:p17-news-feed:설계담금질:complete:2026-04-10T12:45:00+09:00 -->
