# P17 News Feed - 설계서 초안

## 핵심 결정 요약

- **모델:** NewsSource (RSS 소스 관리) + NewsArticle (기사 저장/요약/관련도)을 projects 앱에 추가
- **뉴스 수집 파이프라인:** management command `fetch_news` → RSS 파싱(feedparser) → AI 요약(Gemini) → 관련도 매칭 → 텔레그램 발송. 매일 cron 실행
- **관련도 매칭:** 기사 태그 vs 프로젝트(고객사명 0.9, 업종 0.6, 키워드 0.5~0.8). relevance_score 0.5 이상이면 관련 프로젝트에 연결
- **UI:** 뉴스피드 메인(/news/) + HTMX 카테고리 필터 + 소스 관리 CRUD
- **텔레그램 연동:** 매일 아침 뉴스 요약 발송 (P15 바인딩된 사용자 대상)
- **사이드바:** 뉴스피드 메뉴 추가 + 새 관련 뉴스 dot indicator
- **DB 설계:** UUID PK, TimestampMixin 사용. NewsArticle.url에 unique 제약

## URL 설계

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/news/` | GET | `news_feed` | 뉴스피드 메인 |
| `/news/filter/` | GET | `news_filter` | 필터 적용 (HTMX partial) |
| `/news/sources/` | GET | `news_sources` | 소스 관리 목록 |
| `/news/sources/new/` | GET/POST | `news_source_create` | 소스 추가 |
| `/news/sources/<pk>/edit/` | GET/POST | `news_source_update` | 소스 수정 |
| `/news/sources/<pk>/delete/` | POST | `news_source_delete` | 소스 삭제 |
| `/news/sources/<pk>/toggle/` | POST | `news_source_toggle` | 소스 활성/비활성 |

## 모델 설계

NewsSource: name, url, type(news/youtube/blog), category(hiring/hr/industry/economy), is_active, last_fetched_at
NewsArticle: source(FK), title, summary, url(unique), published_at, tags(JSON), category, relevance_projects(JSON), relevance_score, is_pinned

```python
class NewsCategory(models.TextChoices):
    HIRING = "hiring", "채용"
    HR = "hr", "인사"
    INDUSTRY = "industry", "업계동향"
    ECONOMY = "economy", "경제/실업"
```

## 서비스 구조

| 파일 | 역할 |
|------|------|
| `projects/services/news/fetcher.py` | RSS 파싱 + 기사 저장 |
| `projects/services/news/summarizer.py` | Gemini API 요약 + 태그 추출 |
| `projects/services/news/matcher.py` | 프로젝트 관련도 매칭 |
| `projects/management/commands/fetch_news.py` | 뉴스 수집 커맨드 |

## 뉴스피드 UI 와이어프레임

내 프로젝트 관련 뉴스 상단 고정(📌) + 최신 뉴스 하단. 카테고리 필터(전체/채용/인사/업계동향). HTMX partial로 필터 적용.

## 산출물 목록

projects/models.py, projects/views.py, projects/urls.py, projects/forms.py,
projects/services/news/fetcher.py, projects/services/news/summarizer.py, projects/services/news/matcher.py,
projects/management/commands/fetch_news.py,
projects/templates/projects/news_feed.html, projects/templates/projects/partials/news_list.html,
projects/templates/projects/news_sources.html, 사이드바 템플릿 수정, 테스트 파일

Source: docs/plans/headhunting-workflow/P17-news-feed.md
