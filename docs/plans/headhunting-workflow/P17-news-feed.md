# P17: News Feed

> **Phase:** 17
> **선행조건:** P01 (모델 기반), P03 (프로젝트 — 관련도 매칭 대상), P15 (텔레그램 — 뉴스 발송)
> **산출물:** 뉴스 수집 파이프라인 + 관련도 매칭 + 뉴스피드 UI + 텔레그램 뉴스 요약

---

## 목표

채용/인사/업계 뉴스를 자동 수집하고, 진행 중 프로젝트와의 관련도를 매칭하여
뉴스피드 화면에 표시한다. 텔레그램으로 매일 뉴스 요약을 발송한다.

---

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

---

## 모델 (projects 앱)

### NewsSource

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | UUID | PK |
| `name` | CharField | 소스명 (예: "한경 채용뉴스") |
| `url` | URLField | RSS 피드 URL |
| `type` | CharField choices | news / youtube / blog |
| `category` | CharField choices | 분류 카테고리 |
| `is_active` | BooleanField | 활성 여부 |
| `last_fetched_at` | DateTimeField null | 마지막 수집 시각 |
| `created_at` / `updated_at` | DateTimeField | 타임스탬프 |

```python
class NewsCategory(models.TextChoices):
    HIRING = "hiring", "채용"
    HR = "hr", "인사"
    INDUSTRY = "industry", "업계동향"
    ECONOMY = "economy", "경제/실업"
```

### NewsArticle

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | UUID | PK |
| `source` | FK → NewsSource | 출처 |
| `title` | CharField | 기사 제목 |
| `summary` | TextField | AI 요약 (2~3문장) |
| `url` | URLField unique | 원문 링크 |
| `published_at` | DateTimeField | 게재일 |
| `tags` | JSONField default=list | 태그 (회사명, 키워드 등) |
| `category` | CharField | 분류 (소스에서 상속 또는 AI 분류) |
| `relevance_projects` | JSONField default=list | 관련 프로젝트 ID 목록 |
| `relevance_score` | FloatField default=0 | 최대 관련도 점수 |
| `is_pinned` | BooleanField default=False | 내 프로젝트 관련 상단 고정 |
| `created_at` | DateTimeField | 수집 시각 |

---

## 뉴스 수집 파이프라인

management command + cron으로 매일 자동 실행:

```bash
# 매일 오전 7시 — 뉴스 수집 + AI 요약 + 관련도 매칭
uv run python manage.py fetch_news
```

### 수집 단계

```
1. 활성 NewsSource 순회
   │
2. RSS 피드 파싱 (feedparser)
   │  → 이미 수집된 URL은 스킵 (unique 제약)
   │
3. 신규 기사 저장 (title, url, published_at)
   │
4. AI 요약 생성 (Gemini API, 배치 처리)
   │  → 원문에서 2~3문장 요약 + 태그 추출
   │
5. 관련도 매칭
   │  → 진행 중 프로젝트의 client.name, industry, requirements 키워드와 비교
   │  → 매칭 점수 0.0~1.0, 0.5 이상이면 relevance_projects에 추가
   │
6. 텔레그램 뉴스 요약 발송 (P15 연동)
```

### AI 요약 프롬프트

```
기사를 2~3문장으로 요약하고, 관련 회사명/키워드를 태그로 추출하세요.
분류: 채용/인사/업계동향/경제 중 선택.
```

---

## 관련도 매칭 로직

`projects/services/news/matcher.py`:

```python
def match_relevance(article: NewsArticle, projects: QuerySet) -> list[dict]:
    """기사와 프로젝트 간 관련도 매칭."""
```

매칭 기준:
1. **회사명 직접 매칭** — 기사 태그에 프로젝트 고객사명 포함 → 0.9
2. **업종 매칭** — 같은 업종 키워드 → 0.6
3. **키워드 매칭** — JD/requirements와 기사 태그 교집합 → 0.5~0.8

---

## 뉴스피드 UI

```
┌─ 뉴스피드 ──────────── [전체] [채용] [인사] [업계동향] ──┐
│                                                         │
│  📌 내 프로젝트 관련 ──────────────────────────────────  │
│  │ 삼성전자, 하반기 경력직 대규모 채용 예고                │
│  │ 매일경제 | 2시간 전 | 🏷️ 삼성SDI 해외영업 관련         │
│  │ AI 요약: 삼성전자가 하반기 경력직 1,200명 채용을        │
│  │ 예고했다. 반도체, 디스플레이 부문 중심...               │
│  │                                                      │
│  │ CJ그룹 임원인사 단행 — 마케팅 부문 대폭 교체           │
│  │ 한국경제 | 5시간 전 | 🏷️ CJ 마케팅 관련                │
│                                                         │
│  📰 최신 뉴스 ─────────────────────────────────────────  │
│  │ 외국계 기업 한국 철수 러시... 인력시장 영향              │
│  │ 조선비즈 | 어제 | 🏷️ 채용                              │
│  │                                                      │
│  │ IT 인재 전쟁, 연봉 30% 인상도 부족                     │
│  │ 블로터 | 어제 | 🏷️ 채용, IT                            │
│                                                         │
│  [더 보기]                                               │
└──────────────────────────────────────────────────────────┘
```

HTMX 필터: `hx-get="/news/filter/?category=hiring"` → `hx-target="#news-list"`.

---

## 소스 관리 UI

소스명, 유형(RSS/블로그), 분류, 최근 수집일, 활성 상태를 테이블로 표시. CRUD + 활성/비활성 토글.

---

## 텔레그램 뉴스 발송

매일 아침 뉴스 수집 완료 후 바인딩된 사용자에게 요약 발송.
내 프로젝트 관련 뉴스 상단 + 주요 뉴스 하단 + 웹 앱 링크.

---

## 사이드바 메뉴

```
│  📰  뉴스피드              │
```

`hx-get="/news/"` + `hx-target="main"` + `hx-push-url="true"`.
새 관련 뉴스 존재 시 점 표시기(dot indicator).

---

## 서비스 구조

| 파일 | 역할 |
|------|------|
| `projects/services/news/fetcher.py` | RSS 파싱 + 기사 저장 |
| `projects/services/news/summarizer.py` | Gemini API 요약 + 태그 추출 |
| `projects/services/news/matcher.py` | 프로젝트 관련도 매칭 |
| `projects/management/commands/fetch_news.py` | 뉴스 수집 커맨드 |

외부 의존: `feedparser` (RSS 파싱), Gemini API (요약).

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| RSS 수집 | fetch_news → NewsArticle 생성 확인 |
| 중복 방지 | 같은 URL 재수집 시 스킵 |
| AI 요약 | 기사 → summary + tags 생성 |
| 관련도 매칭 | 고객사명 포함 기사 → relevance_score > 0 |
| 상단 고정 | 내 프로젝트 관련 기사 상단 표시 |
| 필터 | 카테고리별 필터 동작 |
| 소스 CRUD | 추가 → 수정 → 비활성화 → 삭제 |
| 텔레그램 | 뉴스 요약 메시지 발송 |
| 사이드바 | 뉴스피드 메뉴 접근 + 새 뉴스 표시기 |

---

## 산출물

- `projects/models.py` — NewsSource, NewsArticle 모델
- `projects/views.py` — 뉴스피드 + 소스 관리 뷰
- `projects/urls.py` — `/news/` 하위 URL
- `projects/forms.py` — NewsSourceForm
- `projects/services/news/fetcher.py` — RSS 수집
- `projects/services/news/summarizer.py` — AI 요약
- `projects/services/news/matcher.py` — 관련도 매칭
- `projects/management/commands/fetch_news.py` — 수집 커맨드
- `projects/templates/projects/news_feed.html` — 뉴스피드 메인
- `projects/templates/projects/partials/news_list.html` — 기사 목록 (HTMX)
- `projects/templates/projects/news_sources.html` — 소스 관리
- 사이드바 템플릿 수정 (뉴스피드 메뉴 추가)
- 테스트 파일
