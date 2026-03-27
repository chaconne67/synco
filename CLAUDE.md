# synco

AI CRM & 비즈니스 매칭 플랫폼. FC(보험설계사)가 CEO 인맥을 관리하고, AI 브리핑으로 영업 기회를 발견하는 서비스.

## Tech Stack

- **Backend:** FastAPI (Python 3.10+)
- **Frontend:** HTMX + Jinja2 + Tailwind CSS (Pretendard font)
- **DB:** PostgreSQL + SQLAlchemy 2.0 async + Alembic
- **Auth:** Kakao OAuth2 + JWT (cookie-based)
- **AI:** OpenAI GPT-4o + Whisper
- **Scheduler:** APScheduler (in-process, SQLAlchemyJobStore)
- **Push:** Web Push API (VAPID) + 카카오톡 알림톡 fallback
- **Deploy:** VPS + Nginx + Uvicorn (worker=1)

## Commands

```bash
# 개발 서버
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# DB 마이그레이션
alembic upgrade head
alembic revision --autogenerate -m "description"

# 테스트
pytest -v
pytest --cov=app

# 린트
ruff check app/
ruff format app/
```

## Project Structure

```
app/
├── api/           # Route handlers (auth, contacts, meetings, interactions, briefs, matches)
├── core/          # Config, database, security
├── models/        # SQLAlchemy models
├── schemas/       # Pydantic validation schemas
├── services/      # Business logic (AI, scheduler, push, kakao parser)
├── templates/     # Jinja2 templates
│   ├── layouts/   # base.html, app.html
│   ├── pages/     # Full page templates
│   └── components/# Reusable HTMX partials
└── static/        # CSS, JS, images, PWA files
```

## Conventions

### Language
- **UI 텍스트:** 한국어, 존대말 사용 (예: "등록되었습니다", "확인해주세요")
- **코드:** 영어 (변수명, 함수명, 주석)
- **커밋 메시지:** 영어

### Code Style
- Python: ruff (format + lint)
- 타입 힌트 사용 (Mapped[], Mapped[str | None])
- async/await 일관 사용
- Pydantic schema로 입력 검증 (시스템 경계에서)

### HTMX Patterns
- 네비게이션: `hx-get` + `hx-target="main"` + `hx-push-url="true"`
- Form 제출: `hx-post` + specific target
- 로딩: `hx-indicator` + skeleton/spinner
- 에러: `hx-on::after-request`에서 `event.detail.successful` 체크

### Auth
- JWT는 httponly secure cookie (`synco_token`)
- 미인증 시 일반 요청은 302 → `/auth/login`, HTMX 요청은 HX-Redirect 헤더
- CSRF 토큰 필수 (모든 POST)

### Database
- UUID primary keys (String(36))
- TimestampMixin (created_at, updated_at)
- 관계 접근 시 selectinload 사용 (N+1 방지)

### AI Integration
- 브리핑: on-demand + 24h 캐시
- 음성 메모: Web Speech API → Whisper fallback → GPT-4o 구조화
- 카톡 파싱: 백그라운드 처리
- 다이제스트: 스케줄러 배치 (월요일)

## Testing

```bash
pytest -v
```

- Framework: pytest + httpx AsyncClient
- DB: testcontainers (PostgreSQL)
- Fixtures: conftest.py에 db session, authenticated client, sample data
- 새 기능 구현 시 테스트 함께 작성

## Design System

DESIGN.md 참조. 핵심:
- Font: Pretendard
- Primary: #5B6ABF
- Border radius: Card 2xl, Button xl, Input lg
- Mobile-first, md/lg responsive
- Touch target 44px+, WCAG AA contrast
