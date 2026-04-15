# synco

AI 헤드헌팅 플랫폼. 이력서를 자동 파싱·구조화하고, 후보자를 검색·검수하는 채용 담당자용 서비스.

## 되돌리기 어려운 조작 — synco 로컬 가드

일반 원칙(원복성·영향 범위 기반 승인 요구)은 기본 시스템 프롬프트의 *Executing actions with care* 섹션에 있다. synco 특유의 적용 지점만 기록한다.

- **운영 DB 직접 조작**: 49.247.45.243의 운영 DB에 `INSERT`/`UPDATE`/`DELETE`/`ALTER`는 단 1건이라도 실행 전 사용자 승인.
- **`./deploy.sh`는 사용자 명시 지시에만**. 자발적 배포·컨테이너 재시작·이미지 교체 금지.
- **외부 상태 변경 API**: 고객사 이메일/서류 송부, 텔레그램 브로드캐스트, Drive 쓰기/삭제는 실행 전 승인. **읽기·추론 LLM 호출은 제외** — `common/llm.py`(Claude CLI) 와 `data_extraction`의 Gemini 배치는 일상 개발 호출이므로 승인 불필요.
- **코코넛 서버(49.247.38.186)**: 다른 팀의 운영 서버. 허용 범위는 아래 *Infrastructure* 섹션.

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

- **Backend:** Django 5.2 (Python 3.13+) + PostgreSQL (pgvector)
- **Frontend:** HTMX + Django Templates + Tailwind CSS (Pretendard font)
- **AI:**
  - **Claude CLI (subprocess)** — **모든 신규 LLM 호출의 기본값**. `common/llm.py`의 default provider(`claude_cli`), `common/claude.py`가 호스트의 `claude` 커맨드를 subprocess로 호출. Claude Code 구독 인증 재사용. Kimi/MiniMax 등 대체 provider는 `LLM_PROVIDER` 환경변수로 전환. 새 기능이 LLM이 필요하면 `common/llm.py` 경유.
  - **Gemini API** — `data_extraction` 앱의 이력서 배치 추출/정규화 전용. 이 앱 바깥에서 Gemini 직접 호출 금지. Gemini를 다른 용도로 쓰려면 먼저 사용자와 논의.
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

## 수정 후 검증 — synco 특유 포인트

UI/frontend 수정 시 브라우저로 실제 동작을 확인한 뒤 보고하는 일반 원칙은 기본 시스템 프롬프트에 있다. synco에서는 여기에 다음만 추가된다:

- **UI 수정 시 브라우저 검증은 `/browse` 스킬** 사용 (단순 화면 진입만으로는 부족 — 수정된 요소를 실제로 클릭·전송).
- **마이그레이션** 적용은 `uv run python manage.py migrate --plan` → 적용 → `showmigrations` 로 최종 상태 보고.
- **테스트가 없는 백엔드 수정**은 `uv run python manage.py shell` 재현 또는 `/browse` 중 하나로 관찰. 재현이 외부 상태 변경(이메일·텔레그램·Drive 쓰기 등)을 유발하면 재현 대신 "관찰 포인트 + 대안 관찰 방법"을 보고.

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
| **코코넛** | 49.247.38.186 | 다른 팀의 coconut 운영 서버 | synco 작업에서 **수정·재시작·kill 금지**, 읽기 전용 조사만 |

### SSH 접속

```bash
ssh -o IdentityFile=~/.ssh/id_ed25519 chaconne@49.247.45.243  # DB 서버
ssh -o IdentityFile=~/.ssh/id_ed25519 chaconne@49.247.38.186  # 코코넛 (읽기 조사 전용)
```

**코코넛 규칙:** synco 세션에서 코코넛 서버의 **상태(파일·프로세스·컨테이너·DB·네트워크 아웃바운드)** 를 변경하는 모든 조작은 금지. **운영 리소스 점유**(장기 실행 세션)도 다른 팀 작업에 혼선을 주므로 동일하게 금지. 읽기 전용·단기 조회만 허용.

- 허용 예: `ls`, `cat`, `docker ps`, `docker inspect`, 한 번에 끝나는 로그·파일 snapshot 조회 (`docker logs --tail 100`, `journalctl --since ...` 등 유한 출력)
- 금지 예: 파일 편집·생성·삭제, 컨테이너 재시작·stop·exec shell 진입, DB 쓰기 쿼리(SELECT 외), **장기 실행 또는 follow 모드**(`tail -f`, `docker logs -f`, `journalctl -f` 등 — 세션·파일 디스크립터를 잡아 다른 작업에 간섭), 외부로 데이터 전송, 패키지 설치
- 판정 불확실: 명령이 "상태를 바꾸거나 세션을 장기 점유하는지" 확신이 없으면 실행하지 않고 사용자에게 확인 (문서 상단 *실패 비용 우선순위* 섹션의 보수적 판정과 동일)

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

**왜 8000이 고정인가:** `./dev.sh`, `docker-compose.yml`, 각종 문서·링크가 8000에 하드코딩되어 있다. 회피 포트로 띄우면 빌드 산출물과 불일치가 생긴다.

**8000이 점유되어 있을 때:** `lsof -i :8000`으로 PID·USER·COMMAND를 확인한다.
- **종료 허용 조건**: 이 세션의 이전 Bash 도구 출력에 동일 PID가 명시적으로 기록되어 있고(즉 내가 `run_in_background` 등으로 띄워 PID를 안 경우), `ps -p <PID>`의 COMMAND가 그 기록과 일치. 이 두 가지가 모두 확인된 경우에만 종료하고 재실행.
- **그 외 모든 경우**(다른 터미널, 다른 세션, IDE 디버거 attach, 이번 세션 기록에 PID 없음, 판정 불확실) → **종료하지 않고** 사용자에게 점유 프로세스 정보를 보고 후 지시를 기다린다. "아마 내 프로세스일 것이다"는 판정이 아니다.

**8080은 평상시 띄우지 않는다.** 배포 전 로컬에서 릴리스 이미지 동작만 훑고 싶을 때만 사용한다. 일상 개발에는 불필요.

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

배포 실행은 `./deploy.sh`. 파이프라인 단계는 스크립트 본문 참조.

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

## Skill routing — synco 로컬 매핑

스킬 호출 일반 규칙(사용자가 `/skill-name`으로 부르거나 트리거와 명확히 일치할 때 호출)은 기본 시스템 프롬프트에 있다. synco에서는 아래 로컬 매핑과 예외만 추가된다.

**synco 로컬 거절 — 배포 파이프라인과 충돌하는 스킬**

`./deploy.sh`(Docker Swarm + rsync + rolling update)로 고정된 synco의 배포 파이프라인과 맞지 않는 스킬은 사용자가 직접 호출해도 거절하고 `./deploy.sh`로 안내.

- **거절 대상**: `ship`, `land-and-deploy`, `canary`, `setup-deploy` 및 "PR merge → GitHub release / canary / 원클릭 ship"을 전제로 하는 모든 스킬.
- **거절 대상 아님**: `document-release`(post-ship 문서), 단순 git 커밋·푸시.

**synco 맥락에서 자발 호출 가능한 스킬**

| 사용자 요청의 성격 | 스킬 | 적용 조건 | 반대 사례 |
|---|---|---|---|
| 아직 코드가 없는 새 아이디어 평가 | `office-hours` | 0→1 기획 논의 | 기존 페이지 UX 의사결정 |
| 버그·500·원인 불명 동작 | `investigate` | 에러·불일치·근본 원인 요구 | 단순 로그 확인 |
| 다회 루프 QA | `qa` | "기능 전체 검증해줘" 탐색 | 방금 고친 한 곳 확인 |
| 머지 전 diff 리뷰 | `review` | "PR 머지해도 될지 봐줘" | 함수 한 개 다시 읽기 |
| 디자인 시스템 기획 | `design-consultation` | 새 디자인 토큰 설계 | 기존 토큰 내 색 조정 |
| 라이브 사이트 시각적 폴리싱 | `design-review` | 배포 화면 정렬·간격·타이포 감사 | 목업 이식 |
| 아키텍처 검토 | `plan-eng-review` | 멀티 앱·모델 변경 사전 검토 | 단일 뷰 리팩터 |

표에 없는 스킬은 사용자가 이름으로 직접 호출할 때만 실행한다. 자발 호출은 이 표에 있는 7개로 제한.

---

# Behavioral guidelines — 시스템 프롬프트 보강

아래 지침은 기본 시스템 프롬프트에 직접 등장하지 않는 것만 남긴다. "과잉 추상화 금지", "dead code 즉시 삭제", "탐색적 질문엔 짧게 tradeoff 제시" 같은 일반 원칙은 시스템 프롬프트가 이미 처리한다.

## 배치 지시 override — 묻지 말고 완주

"전부 바꿔", "끝까지 진행", "알아서 해줘" 같은 배치 지시를 받으면 중간에 "계속할까요?"를 묻지 않고 끝까지 실행한다. 혼란이나 작은 결정은 **응답 본문에 `assumption: ...` 한 줄**로 드러내고 그대로 진행한다 (코드 주석이 아니라 대화 본문).

이 override는 **원복 가능한 도메인**(로컬 레포·dev 컨테이너 안)에만 적용된다. 운영 DB·배포·외부 상태 변경 호출 같은 "되돌리기 어려운 조작"은 위의 *되돌리기 어려운 조작 — synco 로컬 가드* 섹션의 보고·승인 규칙이 항상 우선한다.

## TDD 루프 선호

새 기능·버그 수정 시 가능하면 **테스트 먼저**:

- "유효성 검증 추가" → 잘못된 입력에 대한 테스트 작성 → 통과시킴
- "버그 고침" → 버그를 재현하는 테스트 작성 → 통과시킴
- "X 리팩터" → 리팩터 전·후 테스트가 통과하는지 확인

테스트 작성이 불가능·과잉인 작업(단순 UI 조정, 포맷 변경 등)은 건너뛴다.

## 프로젝트 강제 포맷터는 surgical 예외

`uv run ruff format`, `uv run ruff check --fix`는 pre-commit/CI가 강제하므로, 이들이 건드린 줄이 내가 의도하지 않은 주변 코드여도 surgical 위반이 아니다. 새 강제 도구(djlint 등)가 프로젝트에 추가되면 이 목록을 명시적으로 갱신. 목록이 낡아 보이면 실행 전 한 줄로 확인: "`<tool>`이 pre-commit에 추가된 것 같은데 목록에 없습니다. 반영하고 진행할까요?"

