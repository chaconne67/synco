# synco

AI CRM & 비즈니스 매칭 플랫폼. FC(보험설계사)가 CEO 인맥을 관리하고, AI 브리핑으로 영업 기회를 발견하는 서비스.

## Tech Stack

- **Backend:** Django 5.2 (Python 3.10+) + PostgreSQL
- **Frontend:** HTMX + Django Templates + Tailwind CSS (Pretendard font)
- **AI:** Claude API (프로토타입용)
- **Package Manager:** uv

## 현재 개발 상태 점검

`docs/04-product/status.md` 파일 확인

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

## 개발 체크리스트

코드 수정/기능 추가 완료 시 반드시 `CHECK_LIST.md`를 점검하고 모든 항목을 통과시킨 뒤 작업 완료로 간주할 것. 특히 **의존성 동일성**(pyproject.toml, Dockerfile, Docker 컨테이너 동작 확인)과 **UX 피드백**(로딩 상태, 에러 메시지)은 누락 빈도가 높으므로 주의.

## Conventions

- **UI 텍스트:** 한국어 존대말 ("등록되었습니다")
- **코드/커밋:** 영어
- **Python:** ruff (format + lint), 타입 힌트
- **HTMX 네비게이션:** `hx-get` + `hx-target="main"` + `hx-push-url="true"`
- **HTMX Form:** `hx-post` + specific target
- **DB:** UUID primary keys, TimestampMixin (created_at, updated_at)

## Design System

`docs/DESIGN.md` 참조.

---

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

Docker Swarm 기반 배포. Static 파일은 whitenoise로 Django가 직접 서빙.

```
/home/docker/
├── synco/
│   ├── Dockerfile           # 운영용 (gunicorn + migrate + collectstatic)
│   ├── .env.prod            # 운영 환경변수 (DB, SECRET_KEY 등)
│   └── src/                 # deploy 시 rsync로 복사되는 소스
├── nginx/
│   ├── Dockerfile           # Nginx 이미지
│   └── nginx.conf           # SSL + reverse proxy (synco.kr)
├── docker-stack-synco.yml   # Swarm 스택 정의 (nginx + synco_app)
└── deploy-synco.sh          # 원클릭 배포
```

**deploy-synco.sh 파이프라인:**

1. **check_migrations_** — `makemigrations --check --dry-run` (미생성 migration 차단)
2. **save_** — 소스 rsync 복사 (`/home/work/synco/` → `/home/docker/synco/src/`)
3. **backup_db_** — 운영 DB pg_dump 백업
4. **build_** — Django 이미지 빌드 (타임스탬프 태그, collectstatic 포함)
5. **deploy_** — 기존 스택 제거 → 새 태그로 `docker stack deploy`

**운영 배포 실행:**
```bash
sudo bash /home/docker/deploy-synco.sh
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

## DB Migration 안전 규칙

Django migration 파일이 개발/운영 DB 간 스키마 정합성의 단일 진실 소스.

### 원칙

1. **마이그레이션은 항상 되돌릴 수 있게 작성**
   - `RunPython`에는 반드시 `reverse_func` 포함
   - 컬럼 삭제 전 deprecated 기간 확보

2. **위험한 변경은 2단계로 분리**
   ```
   # 컬럼명 변경 시:
   # Step 1 배포: 새 컬럼 추가 + 양쪽에 데이터 쓰기
   # Step 2 배포: 이전 컬럼 제거
   ```

3. **배포 전 자동 백업**
   ```bash
   pg_dump > /mnt/backups/synco_$(date +%Y%m%d%H%M%S).sql
   ```

4. **배포 전 복사본에서 migration 선행 테스트**
   - 프로덕션 DB 복사 → 테스트 DB에서 migrate 실행 → 성공 시 본 배포

5. **문제 시 롤백**
   ```bash
   python manage.py migrate <app_name> <이전_번호>  # 특정 지점으로 되돌리기
   ```

---

## 개발/운영 정합성 관리

개발 DB(localhost)와 운영 DB(49.247.45.243)의 스키마가 어긋나는 것을 방지하기 위한 워크플로우.

### 핵심 규칙

- **migration 파일 = 단일 진실 소스.** 개발에서 `makemigrations` → git commit → 운영에서 `migrate`만 실행
- **운영 DB에서 절대 `makemigrations` 하지 않음.** 운영에서는 `migrate`만 실행
- **migration 파일은 반드시 git에 포함.** `.gitignore`에 `*/migrations/` 추가 금지

### 상태 확인 명령어

```bash
# 개발: 미적용 마이그레이션 확인
uv run python manage.py showmigrations | grep '\[ \]'

# 개발: 모델 변경 후 migration 파일 누락 감지
uv run python manage.py makemigrations --check --dry-run

# 운영: SSH로 미적용 마이그레이션 확인
ssh chaconne@49.247.46.171 \
  "docker exec \$(docker ps -qf name=synco_web) python manage.py showmigrations | grep '\[ \]'"
```

### 개발 워크플로우

```
1. 모델 변경 (models.py 수정)
2. makemigrations → migration 파일 생성 확인
3. migrate → 개발 DB 적용
4. 테스트 실행 (pytest)
5. migration 파일 포함하여 git commit
```

**주의:** `makemigrations`와 `migrate`를 하나의 작업 단위로 묶어서 실행. 모델만 변경하고 migration을 안 만들면 다음 개발자(또는 배포)에서 예상 못한 migration이 생김.

### 배포 전 체크리스트

```bash
# 1. 개발에 미생성 migration 없는지 확인
uv run python manage.py makemigrations --check --dry-run
# → "No changes detected" 가 나와야 정상

# 2. migration 파일이 git에 포함되었는지 확인
git status --short '*/migrations/*.py'
# → 새 migration 파일이 있으면 커밋 필요

# 3. 운영 DB 백업
ssh chaconne@49.247.45.243 \
  "pg_dump -U synco synco > /mnt/backups/synco_\$(date +%Y%m%d%H%M%S).sql"

# 4. 배포 (deploy-synco.sh가 migrate 자동 실행)
```

### 환경 간 차이 방지

| 항목 | 개발 | 운영 | 관리 방법 |
|------|------|------|-----------|
| DB 엔진 | PostgreSQL 16 (docker) | PostgreSQL 16 (docker) | 동일 버전 유지 |
| Python | 3.10 | 3.10 (Dockerfile 고정) | Dockerfile에서 버전 통일 |
| 의존성 | `uv.lock` | Dockerfile에서 설치 | `uv.lock` 커밋 필수 |
| 환경변수 | `.env` | 서버 `.env` | 키 목록은 `.env.example`로 관리 |
| Static | `runserver` 자동 서빙 | `collectstatic` + Nginx | 배포 스크립트에서 자동 처리 |

### 흔한 괴리 상황과 대응

**1. 개발에서 migration을 만들지 않고 배포한 경우**
```bash
# 운영에서 migrate 시 모델과 DB가 불일치 → 에러
# 대응: 개발에서 makemigrations → 커밋 → 재배포
```

**2. 여러 사람이 같은 앱에서 동시에 migration 생성**
```bash
# merge conflict 발생 가능
# 대응: merge 후 makemigrations --merge로 병합 migration 생성
uv run python manage.py makemigrations --merge
```

**3. 개발 DB를 초기화했지만 운영은 기존 데이터 유지**
```bash
# 개발에서 잘 되던 migration이 운영에서 데이터 충돌
# 대응: 배포 전 운영 DB 복사본에서 migration 테스트 (원칙 4)
```

**4. 운영에 직접 DB 스키마를 변경한 경우**
```bash
# migration 상태와 실제 스키마 불일치 → 이후 migrate 실패
# 대응: 절대 운영 DB를 직접 ALTER하지 않음. 반드시 migration으로만 변경
```
