# synco

AI 헤드헌팅 플랫폼. 이력서를 자동 파싱·구조화하고, 후보자를 검색·검수하는 채용 담당자용 서비스.

## Tech Stack

- **Backend:** Django 5.2 (Python 3.13+) + PostgreSQL
- **Frontend:** HTMX + Django Templates + Tailwind CSS (Pretendard font)
- **AI:** Gemini API (이력서 추출/정규화)
- **Package Manager:** uv

## Commands

```bash
# 개발 서버 (Django + Tailwind watch 동시 실행)
./dev.sh

# 테스트
uv run pytest -v

# 린트
uv run ruff check .
uv run ruff format .
```

## 수정 후 검증 필수

사용자가 수정을 지시했을 경우 반드시 **실제로 테스트를 실행하여 결과를 확인한 후** 사용자에게 보고한다. 특히 UI/UX 수정의 경우 **브라우저 도구(`/browse`)를 활용하여 실제로 클릭, 네비게이션, 스크롤 등을 수행하고 스크린샷을 캡처하여** 수정 내용이 의도대로 반영되었는지 시각적으로 확인한 후 보고한다. 코드 변경만으로 "완료"라고 보고하지 않는다.

## Conventions

- **UI 텍스트:** 한국어 존대말 ("등록되었습니다")
- **코드/커밋:** 영어
- **Python:** ruff (format + lint), 타입 힌트
- **HTMX 네비게이션:** `hx-get` + `hx-target="main"` + `hx-push-url="true"`
- **HTMX Form:** `hx-post` + specific target
- **DB:** UUID primary keys, TimestampMixin (created_at, updated_at)

## Infrastructure

### 서버 구성

| 서버 | IP | 역할 | 비고 |
|------|-----|------|------|
| **운영/개발** | 49.247.46.171 | synco 앱 배포 + 개발 | Docker Swarm + Nginx |
| **DB** | 49.247.45.243 | PostgreSQL 상시 운용 | /mnt 100GB 디스크 (73GB 여유) |
| **코코넛** | 49.247.38.186 | coconut 전용 | **절대 건드리지 않음** |

### SSH 접속

```bash
ssh -o IdentityFile=~/.ssh/id_ed25519 chaconne@49.247.45.243  # DB 서버
ssh -o IdentityFile=~/.ssh/id_ed25519 chaconne@49.247.38.186  # 코코넛 (참조만)
```

### DB 구성

- **운영 DB:** PostgreSQL 16 컨테이너 @ 49.247.45.243
  - 데이터 경로: `/mnt/synco-pgdata/`
  - 포트: 5432, `restart: always` 상시 운용
  - 접속: `postgresql://synco:<password>@49.247.45.243:5432/synco`
- **개발 DB:** Docker 로컬 PostgreSQL @ 49.247.46.171
  - 개발 전용, 자유롭게 실험 가능
  - 접속: `postgresql://synco:synco@localhost:5432/synco`

### 포트 정책

| 포트 | 용도 | 환경 |
|------|------|------|
| **8000** | 개발 서버 (`runserver`) | 호스트 직접 실행 |
| **8080** | Docker web 컨테이너 (배포 테스트용) | `docker compose --profile deploy` |
| **443/80** | 운영 (nginx → gunicorn) | Docker Swarm |

- **개발과 운영 포트는 절대 겹치지 않게 한다**
- 도커 컨테이너는 배포에만 사용. 개발은 호스트에서 직접 실행
- 8000이 점유되어 있으면 다른 포트로 회피하지 말고 점유 프로세스를 확인/제거

### 배포 방식

Docker Swarm 기반 배포. 배포 자산의 기준은 레포의 `deploy.sh`, `deploy/docker-stack-synco.yml`, `deploy/nginx/` 이다.

```
/home/work/synco/
├── deploy.sh                # 원클릭 배포 진입점
└── deploy/
    ├── docker-stack-synco.yml
    └── nginx/
        ├── Dockerfile
        └── nginx.conf

/home/docker/
├── synco/
│   ├── .env.prod            # 운영 환경변수 (DB, SECRET_KEY 등)
│   ├── .secrets/            # Google OAuth 등 런타임 secret
│   ├── .claude/             # Claude CLI auth sync 대상
│   ├── .claude.json
│   ├── runtime/logs/
│   └── src/                 # deploy 시 rsync로 복사되는 현재 소스
├── nginx/
│   ├── Dockerfile
│   └── nginx.conf
└── docker-stack-synco.yml
```

**deploy.sh 파이프라인:**

1. **check_migrations_** — `makemigrations --check --dry-run` (미생성 migration 차단)
2. **test_** — `uv run pytest -q --create-db` (기본값)
3. **save_** — 현재 소스/배포 템플릿/런타임 secret을 `/home/docker`로 동기화
4. **backup_db_** — 운영 DB pg_dump 백업
5. **build_** — 앱/nginx 이미지 빌드
6. **validate_** — 릴리스 이미지로 `check --deploy`, `migrate`
7. **deploy_** — `docker stack deploy`로 Swarm rolling update

**운영 배포 실행:**
```bash
./deploy.sh
```

### 개발 환경

```bash
# DB만 docker로 실행 (web 컨테이너는 profiles: deploy로 제외됨)
docker compose up -d

# Django는 호스트에서 직접 실행 (포트 8000 고정)
uv run python manage.py runserver 0.0.0.0:8000
```

- `docker compose up -d`로 DB만 뜸. web 컨테이너는 `profiles: ["deploy"]`로 개발 시 자동 시작 안 됨
- **포트 8000은 개발 서버 전용.** 8000이 점유되어 있으면 다른 포트로 회피하지 말고 점유 프로세스를 확인/제거
- AI 기능(엑셀 임포트 등)은 호스트의 `claude` CLI를 사용하므로 Django를 호스트에서 직접 실행
- 개발 DB는 로컬 컨테이너, 운영 DB와 분리

---

## DB Migration 운영 확인

운영 미적용 migration 확인:

```bash
ssh chaconne@49.247.46.171 \
  "docker exec \$(docker ps -qf name=synco_web) python manage.py showmigrations | grep '\[ \]'"
```

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review

---

# Behavioral guidelines

기본 시스템 프롬프트와 중복되지 않는 보강 지침. 각 섹션은 LLM이 명시적 지시 없이는 자주 실패하는 패턴을 겨냥한다.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 3. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

