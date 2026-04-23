# synco

AI 기반 후보자 검색과 이력서 추출 파이프라인을 중심으로 한 Django 프로젝트입니다.

현재 코드베이스의 활성 범위는 `accounts`와 `candidates` 앱이며, 사용자 로그인, 후보자 목록/상세/검수 UI, 자연어/음성 검색, Google Drive 이력서 import, Gemini 기반 구조화 추출, 임베딩 생성까지 포함합니다.

## 현재 상태

- 활성 앱: `accounts`, `candidates`
- 제거됨: `contacts`, `meetings`, `intelligence`
- 테스트 상태: `uv run pytest -q --create-db` 기준 `124 passed`

## 주요 기능

- 아이디·이메일 + 비밀번호 로그인
- 후보자 목록/상세/검수 화면
- HTMX 기반 자연어 검색 UI
- Whisper 기반 음성 검색 입력
- Google Drive 이력서 수집
- Gemini 기반 이력서 구조화 추출
- 규칙 기반 검증 및 검수 상태 관리
- 후보자 임베딩 생성

## 기술 스택

- Python 3.13
- Django 5
- HTMX
- Tailwind CSS
- `uv` 기반 Python 환경 관리
- PostgreSQL/pgvector 또는 SQLite
- Gemini, OpenAI Whisper, Claude CLI/OpenAI-compatible LLM

## 빠른 시작

### 1. 준비물

- Python 3.13+
- `uv`
- Node.js / npm
- 선택: PostgreSQL + pgvector

### 2. 의존성 설치

```bash
uv sync --extra dev
npm install
```

### 3. 환경변수 설정

```bash
cp .env.example .env
```

기본적으로 `DATABASE_URL`이 없으면 SQLite(`db.sqlite3`)를 사용합니다.
단, 이 fallback은 `DEBUG=true` 개발 환경에서만 허용되며 운영에서는 `DATABASE_URL`이 필수입니다.

### 4. DB 마이그레이션

```bash
uv run python manage.py migrate
```

### 5. 개발 서버 실행

Tailwind watcher와 Django 서버를 함께 띄우려면:

```bash
./dev.sh
```

직접 따로 실행하려면:

```bash
npx tailwindcss -i ./static/css/input.css -o ./static/css/output.css --watch
uv run python manage.py runserver 0.0.0.0:8000
```

## 테스트

반드시 `uv` 환경에서 실행하세요.

```bash
uv run pytest -q
```

`pytest -q`를 시스템 파이썬으로 바로 실행하면 Django/pytest-django 미설정 상태로 실패할 수 있습니다.

## 주요 환경변수

### 공통

- `DEBUG`
- `SECRET_KEY`
- `DATABASE_URL`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `SECURE_SSL_REDIRECT`

### Gemini

- `GEMINI_API_KEY`

용도:

- 이력서 구조화 추출
- 임베딩 생성

### OpenAI

- `OPENAI_API_KEY`

용도:

- 음성 전사 (`gpt-4o-transcribe`)

### 범용 LLM

- `LLM_PROVIDER`
- `LLM_API_KEY`
- `LLM_MODEL`

기본값은 `claude_cli`이며, 이 경우 로컬에 `claude` CLI 인증이 되어 있어야 합니다.
배포 스크립트는 `~/.claude`, `~/.claude.json`을 `/home/docker/synco` 아래로 동기화해 동일한 provider 구성을 유지합니다.

## 주요 명령

### 이력서 import

```bash
uv run python manage.py import_resumes --folder Accounting
uv run python manage.py import_resumes --all
uv run python manage.py import_resumes --all --dry-run
```

### 후보자 임베딩 생성

```bash
uv run python manage.py generate_embeddings
```

### 기존 후보자 상세 필드 백필

```bash
uv run python manage.py backfill_candidate_details
```

## Google Drive 연동

이력서 import는 Google Drive OAuth 정보를 사용합니다.

기본 경로는 환경변수로 설정할 수 있으며, 예시 기본값은 아래와 같습니다.

- `.secrets/client_secret.json`
- `.secrets/google_token.json`

관련 환경변수:

- `GOOGLE_CLIENT_SECRET_PATH`
- `GOOGLE_TOKEN_PATH`

이 파일들은 민감 정보이므로 저장소에 커밋하지 않도록 주의해야 합니다.
현재 `.gitignore`에는 `.secrets/`와 기존 `assets/...` 경로 모두 제외 규칙을 추가해 둔 상태입니다.

## 디렉토리 개요

```text
accounts/      사용자 로그인·설정
candidates/    후보자 모델, 검색 UI, 추출 파이프라인, 관리 명령
common/        공통 LLM/임베딩 유틸
main/          Django settings, URL, WSGI/ASGI
templates/     공통 템플릿
static/        Tailwind 입력/출력 및 정적 파일
docs/          계획, 리서치, inspection 문서
tests/         pytest 테스트
```

## 현재 아키텍처 메모

- 실제 런타임 기준 핵심 도메인은 `candidates`입니다.
- 자연어 검색은 현재 LLM이 생성한 구조화 필터를 ORM으로 적용하는 구조입니다.
- 검색 계층은 더 이상 DB 방언에 직접 의존하지 않지만, 필터 해석 품질은 LLM 응답에 영향을 받습니다.
- 확장 전에는 검색 안전성, DB 정합성, secret 관리 정리가 권장됩니다.

자세한 점검 내용:

- [전체 프로젝트 점검 보고서](docs/inspection/2026-04-03-project-overview-inspection.md)
- [데이터 추출 파이프라인 점검 보고서](docs/inspection/2026-04-02-extraction-pipeline-inspection.md)
- [상용화 점검 보고서](docs/inspection/2026-03-31-production-readiness-inspection.md)

## Docker

PostgreSQL 컨테이너와 배포 검증용 웹 컨테이너 구성이 포함되어 있습니다.

DB만 띄우려면:

```bash
docker compose up db
```

웹 컨테이너까지 포함하려면 먼저 `.env`에 `POSTGRES_PASSWORD`, `SECRET_KEY`, `DATABASE_URL` 등을 채운 뒤:

```bash
docker compose run --rm web python manage.py migrate
docker compose --profile deploy up --build
```

주의:

- 현재 `web` 서비스는 `gunicorn`으로 실행됩니다.
- `web`은 소스 디렉터리를 마운트하지 않는 불변 이미지 기준으로 실행됩니다.
- `docker-compose.yml`에는 더 이상 실 비밀번호를 넣지 않습니다. `.env`로만 주입하세요.

## 배포

개발 서버의 현재 상태를 그대로 운영 배포 워크스페이스(`/home/docker`)에 동기화하고, 이미지 빌드, DB 마이그레이션, Swarm 업데이트까지 한 번에 실행하려면:

```bash
./deploy.sh
```

동작 순서:

- 현재 레포를 `/home/docker/synco/src`로 rsync
- 배포용 nginx/stack 템플릿 동기화
- `.secrets`, `~/.claude`, `~/.claude.json` 런타임 파일 동기화
- DB 백업
- 앱/nginx 이미지 빌드
- 릴리스 이미지로 `check --deploy`, `migrate`
- `docker stack deploy`로 Synco 스택 갱신

검증만 하려면:

```bash
./deploy.sh --dry-run
```

## 참고

- 스타일 빌드는 Tailwind CLI를 사용합니다.
- 정적 파일 결과물은 `static/css/output.css`에 생성됩니다.
- 루트의 `main.py`는 앱 진입점이 아니라 예시 파일 수준이므로, 실제 실행은 `manage.py` 기준으로 보면 됩니다.
