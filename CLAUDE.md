# synco

AI CRM & 비즈니스 매칭 플랫폼. FC(보험설계사)가 CEO 인맥을 관리하고, AI 브리핑으로 영업 기회를 발견하는 서비스.

## Tech Stack

- **Backend:** Django 5.2 (Python 3.10+) + PostgreSQL
- **Frontend:** HTMX + Django Templates + Tailwind CSS (Pretendard font)
- **AI:** Claude API (프로토타입용)
- **Package Manager:** uv

## Commands

```bash
# 개발 서버
uv run python manage.py runserver 0.0.0.0:8000

# DB 마이그레이션
uv run python manage.py makemigrations
uv run python manage.py migrate

# 테스트
uv run pytest -v

# 린트
uv run ruff check .
uv run ruff format .
```

## Conventions

- **UI 텍스트:** 한국어 존대말 ("등록되었습니다")
- **코드/커밋:** 영어
- **Python:** ruff (format + lint), 타입 힌트
- **HTMX 네비게이션:** `hx-get` + `hx-target="main"` + `hx-push-url="true"`
- **HTMX Form:** `hx-post` + specific target
- **DB:** UUID primary keys, TimestampMixin (created_at, updated_at)

## Research

웹 검색이 필요할 때는 `docs/research-config.md`의 Fallback Chain과 에이전트 통제 규칙을 따른다.

## Design System

`docs/DESIGN.md` 참조.
