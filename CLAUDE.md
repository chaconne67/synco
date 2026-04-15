# synco

AI 헤드헌팅 플랫폼. 이력서를 자동 파싱·구조화하고, 후보자를 검색·검수하는 채용 담당자용 서비스.

## 되돌리기 어려운 조작 — synco 로컬 가드

일반 원칙(원복성·영향 범위 기반 승인 요구)은 기본 시스템 프롬프트의 *Executing actions with care* 섹션에 있다. synco 특유의 적용 지점만 기록한다.

- **운영 DB 직접 조작**: 49.247.45.243의 운영 DB에 `INSERT`/`UPDATE`/`DELETE`/`ALTER`는 단 1건이라도 실행 전 사용자 승인.
- **`./deploy.sh`는 사용자 명시 지시에만**. 자발적 배포·컨테이너 재시작·이미지 교체 금지.
- **외부 상태 변경 API**: 고객사 이메일/서류 송부, 텔레그램 브로드캐스트, Drive 쓰기/삭제는 실행 전 승인. **읽기·추론 LLM 호출은 제외** — `common/llm.py`(Claude CLI) 와 `data_extraction`의 Gemini 배치는 일상 개발 호출이므로 승인 불필요.
- **코코넛 서버(49.247.38.186)**: 다른 팀 운영 서버. read-only만 허용.

## 활성 앱

| 앱 | 책임 |
|---|---|
| `accounts` | 로그인(Kakao OAuth), 조직·멤버십·초대코드, Gmail·텔레그램 연결, 알림 설정 |
| `candidates` | 후보자·이력서·학력/경력/자격증, 검수, 벡터 검색, 위조 탐지 |
| `clients` | 고객사·계약, 참고 마스터(대학·기업·자격증) |
| `projects` | 프로젝트·Application·ActionItem·Submission·면접·승인·뉴스피드·대시보드 |
| `data_extraction` | Drive 이력서 Gemini Batch 추출 파이프라인 |
| `common` | BaseModel(UUID·Timestamp), `llm.py`/`claude.py` LLM 호출 헬퍼 |

전체 도메인 모델과 URL 맵은 `docs/master/03-engineering-spec.md` 참조.

## Tech Stack

Django 5.2 + HTMX + Tailwind(Pretendard) + PostgreSQL(pgvector), 패키지 관리 `uv`. 기본 스택 상세는 `pyproject.toml`·`package.json`·`base.html` 참조.

**LLM 분담 — AI 사용 정책 (코드 읽어도 바로 안 드러나는 부분)**:
- **Claude CLI subprocess** (`common/llm.py` default provider, `common/claude.py`): 모든 신규 LLM 호출의 기본. 호스트 `claude` 커맨드 subprocess로 Claude Code 구독 인증 재사용. Kimi/MiniMax 등 대체 provider는 `LLM_PROVIDER` 환경변수로 전환.
- **Gemini API**: `data_extraction` 앱의 이력서 배치 추출·정규화 전용. 이 앱 바깥 직접 호출 금지. 다른 용도로 쓰려면 먼저 사용자와 논의.

## Commands

```bash
./dev.sh                    # Django + Tailwind watch
uv run pytest -v            # 테스트
uv run ruff check .         # 린트
uv run ruff format .        # 포맷
```

## 수정 후 검증 — synco 특유 포인트

UI/frontend 수정 시 브라우저로 실제 동작을 확인한 뒤 보고하는 일반 원칙은 기본 시스템 프롬프트에 있다. synco에서는 여기에 다음만 추가된다:

- **UI 수정 시 브라우저 검증은 `/browse` 스킬** 사용 (단순 화면 진입만으로는 부족 — 수정된 요소를 실제로 클릭·전송).
- **마이그레이션** 적용은 `uv run python manage.py migrate --plan` → 적용 → `showmigrations` 로 최종 상태 보고.
- **테스트가 없는 백엔드 수정**은 `uv run python manage.py shell` 재현 또는 `/browse` 중 하나로 관찰. 재현이 외부 상태 변경(이메일·텔레그램·Drive 쓰기 등)을 유발하면 재현 대신 "관찰 포인트 + 대안 관찰 방법"을 보고.

## Conventions

- **UI 텍스트:** 한국어 존대말 ("등록되었습니다")
- **코드/커밋:** 영어
- **Python:** ruff (format + lint)
- **HTMX 네비게이션:** `hx-get` + `hx-target="main"` + `hx-push-url="true"`
- **HTMX Form:** `hx-post` + specific target
- **DB:** UUID primary keys, TimestampMixin (created_at, updated_at)

## Infrastructure

### 서버 구성

| 서버 | IP | 역할 | 비고 |
|------|-----|------|------|
| **운영/개발** | 49.247.46.171 | synco 앱 배포 + 개발 | Docker Swarm + Nginx |
| **DB** | 49.247.45.243 | PostgreSQL 상시 운용 | /mnt 100GB 디스크 (73GB 여유) |
| **코코넛** | 49.247.38.186 | 다른 팀의 coconut 운영 서버 | synco 작업에서 **수정·재시작·kill 금지**, 읽기 전용 조사만 |

### SSH 접속

```bash
ssh -o IdentityFile=~/.ssh/id_ed25519 chaconne@49.247.45.243  # DB 서버
ssh -o IdentityFile=~/.ssh/id_ed25519 chaconne@49.247.38.186  # 코코넛 (read-only)
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
| **8000** | 개발 서버 (`runserver`) — **고정** | 호스트 직접 실행 |
| **8080** | 배포 이미지 로컬 스모크 (릴리스 전 수동 점검) | `docker compose --profile deploy` |
| **443/80** | 운영 (nginx → gunicorn) | Docker Swarm |

8000은 `dev.sh`·`docker-compose.yml`·문서 링크에 하드코딩돼 있어 회피 불가. 점유되어 있으면 `lsof -i :8000`으로 확인하고, **이번 세션의 이전 Bash 출력에 동일 PID가 기록된 내 프로세스가 아니면** 종료하지 않고 사용자에게 보고. "아마 내 것"은 판정이 아니다.

8080은 배포 이미지 로컬 스모크 전용. 일상 개발에는 띄우지 않음.

### 배포 방식

Docker Swarm 기반. 레포의 `./deploy.sh`, `deploy/docker-stack-synco.yml`, `deploy/nginx/`가 단일 진실 소스. 운영 서버에는 `/home/docker/synco/` 에 `.env.prod`·`.secrets/`·`.claude/`·`runtime/logs/`·`src/`(rsync 대상) 가 배치돼 있음. 배포 실행은 `./deploy.sh`, 파이프라인 단계는 스크립트 본문 참조.

### 개발 환경

```bash
# DB만 docker로 실행 (web 컨테이너는 profiles: deploy로 제외됨)
docker compose up -d

# Django는 호스트에서 직접 실행 (포트 8000 고정)
uv run python manage.py runserver 0.0.0.0:8000
```

- `docker compose up -d`로 DB만 뜸. web 컨테이너는 `profiles: ["deploy"]`로 개발 시 자동 시작 안 됨
- LLM 호출(`common/llm.py`)이 호스트의 `claude` CLI를 subprocess로 부르기 때문에 Django를 컨테이너가 아닌 호스트에서 실행해야 인증·권한이 그대로 재사용된다
- 개발 DB는 로컬 컨테이너, 운영 DB와 분리

---

## DB Migration 운영 확인

운영 미적용 migration 확인:

```bash
ssh chaconne@49.247.46.171 \
  "docker exec \$(docker ps -qf name=synco_web) python manage.py showmigrations | grep '\[ \]'"
```

## Skill routing — 배포 스킬 거절

`ship`, `land-and-deploy`, `canary`, `setup-deploy` 및 다른 배포 파이프라인(PR merge → release / canary rollout / 원클릭 ship)을 가정하는 스킬은 사용자가 직접 호출해도 거절하고 `./deploy.sh`로 안내. synco 배포는 `./deploy.sh` 고정.


