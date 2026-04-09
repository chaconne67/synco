# synco

AI 헤드헌팅 플랫폼. 이력서를 자동 파싱·구조화하고, 후보자를 검색·검수하는 채용 담당자용 서비스.

## 개발 환경

- **Claude Code:** VSCode Extension으로 실행 (CLI 버전 아님)
- **에이전트 팀 운영 가능:** Agent 도구로 병렬 서브에이전트 디스패치 지원. 점검/수정/리뷰 등 독립 작업을 FE/BE/QA 에이전트로 분리 실행하고 오케스트레이터가 결과를 검토하는 팀 워크플로우 사용.

## Tech Stack

- **Backend:** Django 5.2 (Python 3.13+) + PostgreSQL
- **Frontend:** HTMX + Django Templates + Tailwind CSS (Pretendard font)
- **AI:** Gemini API (이력서 추출/정규화)
- **Package Manager:** uv

## 활성 앱

- **accounts** — 사용자 인증, 설정
- **candidates** — 후보자 관리, 이력서 파싱, 검색, 검수

## Commands

```bash
# 개발 서버 (Django + Tailwind watch 동시 실행)
./dev.sh

# DB 마이그레이션
uv run python manage.py makemigrations
uv run python manage.py migrate

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

## DB Migration 규칙

- **migration 파일 = 단일 진실 소스.** 개발에서 `makemigrations` → git commit → 운영에서 `migrate`만 실행
- **운영 DB에서 절대 `makemigrations` 하지 않음.** 운영 DB를 직접 ALTER하지 않음
- **migration 파일은 반드시 git에 포함.** `.gitignore`에 `*/migrations/` 추가 금지
- **`RunPython`에는 반드시 `reverse_func` 포함.** 위험한 변경은 2단계 분리 (새 컬럼 추가 → 이전 컬럼 제거)
- **`makemigrations`와 `migrate`는 하나의 작업 단위로 묶어서 실행**

```bash
# 미생성 migration 확인
uv run python manage.py makemigrations --check --dry-run

# 운영 미적용 migration 확인
ssh chaconne@49.247.46.171 \
  "docker exec \$(docker ps -qf name=synco_web) python manage.py showmigrations | grep '\[ \]'"
```

---

## 개발/운영 정합성

- **빌드 결과는 일관돼야 한다.** 개발과 배포는 같은 레포 소스와 같은 Dockerfile 기준
- **임시방편(인라인 스타일, 하드코딩) 금지.** 증상이 아닌 원인을 고칠 것
- **`uv.lock` 커밋 필수.** 의존성은 Dockerfile에서도 동일하게 설치
- **환경변수 키 목록은 `.env.example`로 관리**

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
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
