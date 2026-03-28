# synco 프로젝트 현황 문서

> 최종 업데이트: 2026-03-27
> 151 tests passing (PostgreSQL)

---

## 1. 프로젝트 개요

보험설계사(FC)가 CEO 인맥을 관리하고, AI 브리핑으로 영업 기회를 발견하는 CRM 플랫폼.

---

## 2. 기술 스택

| 영역 | 기술 | 비고 |
|------|------|------|
| Backend | FastAPI (Python 3.11) | async/await 전체 적용 |
| Frontend | HTMX + Jinja2 + Tailwind CSS | SPA 없이 서버 렌더링 |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 async | JSONB, Alembic 마이그레이션 |
| Auth | Kakao OAuth2 + JWT (httponly cookie) | CSRF 미들웨어 포함 |
| AI | Claude CLI (`claude --print --model haiku`) | 구독 인증, API 키 불필요 |
| Push | Web Push API (pywebpush + VAPID) | 설정 페이지에서 구독/해제 |
| Scheduler | APScheduler (in-process) | 10분 간격 리마인더 + 푸시 발송 |
| Deploy | Docker Swarm (app) + Docker Compose (DB) | Nginx reverse proxy |
| Test | pytest + pytest-asyncio + httpx | PostgreSQL `synco_test` DB |

---

## 3. 프로젝트 구조

```
app/
├── api/                 # 라우트 핸들러
│   ├── auth.py          # 카카오 로그인, 역할 선택, 로그아웃
│   ├── contacts.py      # 연락처 CRUD
│   ├── meetings.py      # 미팅 일정 CRUD + 메모 제출
│   ├── interactions.py  # 접점 기록 CRUD
│   ├── briefs.py        # AI 브리핑
│   ├── matches.py       # 비즈니스 매칭 + 상태 관리
│   ├── onboarding.py    # 3단계 온보딩
│   ├── import_contacts.py  # CSV/Excel 임포트
│   ├── voice_memo.py    # 음성 메모 구조화
│   └── push.py          # Web Push 구독/해제/VAPID키
├── core/
│   ├── config.py        # Pydantic Settings (.env)
│   ├── database.py      # SQLAlchemy async engine
│   ├── security.py      # JWT + AuthRedirect
│   └── csrf.py          # CSRF 미들웨어
├── models/              # SQLAlchemy 모델 (7개 테이블)
│   ├── user.py          # users
│   ├── contact.py       # contacts
│   ├── meeting.py       # meetings
│   ├── interaction.py   # interactions
│   ├── brief.py         # briefs
│   └── match.py         # matches
├── schemas/             # Pydantic 입력 검증
│   ├── contact.py       # ContactCreate/Update/Search
│   ├── meeting.py       # MeetingCreate/Update
│   └── interaction.py   # InteractionCreate
├── services/            # 비즈니스 로직
│   ├── ai_briefing.py   # Claude CLI 브리핑 생성
│   ├── matching.py      # 매칭 스코어링 + AI 시너지
│   ├── voice_memo.py    # 음성 메모 구조화
│   ├── scheduler.py     # APScheduler 리마인더 + 푸시 발송
│   ├── push.py          # Web Push 발송 (pywebpush)
│   └── contact_import.py # CSV/Excel 파싱 + 중복 체크
├── templates/
│   ├── layouts/         # base.html, app.html
│   ├── pages/           # 17개 전체 페이지
│   └── components/      # 12개 HTMX 파셜
└── static/
    ├── manifest.json    # PWA 매니페스트
    ├── sw.js            # Service Worker
    └── images/          # PWA 아이콘 (icon-192.png, icon-512.png)
```

---

## 4. 기능 현황

### 완성된 기능

| 기능 | 라우트 | 설명 |
|------|--------|------|
| 카카오 로그인 | `/auth/*` | OAuth2 → JWT 쿠키, 역할 선택, 로그아웃 |
| 온보딩 | `/onboarding/*` | 3단계 (GA 정보 → 첫 연락처 → 완료) |
| 연락처 CRUD | `/contacts/*` | 생성/조회/수정/삭제, 검색(이름/업종), 전화번호 정규화 |
| 미팅 일정 | `/meetings/*` | 생성/조회/완료/취소/삭제, 연락처 연동 |
| 미팅 메모 제출 | `/meetings/{id}/memo` | 완료 후 메모 입력 → Interaction 자동 생성, 건너뛰기 가능 |
| 접점 기록 | `/interactions/*` | 생성/삭제, 유형(통화/미팅/메모/카톡), 감정 분석 |
| AI 브리핑 | `/briefs/*` | Claude CLI로 생성, 24시간 캐시, 강제 재생성 |
| 비즈니스 매칭 | `/matches/*` | 업종/지역/규모 스코어링 + AI 시너지 설명 |
| 매칭 상태 관리 | `PATCH /matches/{id}/status` | 수락/거절/확인 상태 변경, HTMX 인라인 업데이트 |
| CSV/Excel 임포트 | `/import/*` | 한글 컬럼 자동 매핑(30종+), 인코딩 감지, 중복 제거 |
| 음성 메모 | `/voice-memo/*` | Web Speech API(브라우저) → Claude CLI 구조화 → 접점 저장 |
| 대시보드 | `/dashboard` | 오늘 일정, 최신 AI 브리핑, 미연락 CEO(30일+), 최근 접점 |
| 설정 | `/settings` | 프로필, 알림 on/off 토글, 임포트 바로가기, 로그아웃 |
| Web Push 알림 | `/push/*` | 구독/해제 API, VAPID 키 제공, 설정 페이지 토글 |
| 미팅 리마인더 | 백그라운드 | APScheduler 10분 간격, 1시간 전 Web Push 발송 |
| PWA | `/static/manifest.json` | 매니페스트 + 아이콘 + Service Worker |

### 스텁 (미사용)

| 기능 | 현재 상태 | 비고 |
|------|-----------|------|
| 음성 전사 (Whisper) | `transcribe_audio()` 빈 함수 | 현재는 브라우저 Web Speech API로 대체, 서버 전사 불필요 |

### 미구현

| 기능 | 설명 |
|------|------|
| CEO 등록/온보딩 | `role='ceo'` 선택 가능하지만 CEO 전용 화면 없음 |
| CEO-연락처 연동 | `ceo_user_id` FK 있지만 연결 로직 없음 |
| 카카오 알림톡 | 웹푸시 외 추가 채널, 사업자 등록 + 카카오 비즈니스 채널 필요 |
| 주간 다이제스트 | 월요일 배치 (주간 접점/미팅/미연락 CEO 요약), 미구현 |
| API 비용 추적 | TODOS.md MEDIUM 우선순위, 미구현 |

---

## 5. 데이터베이스 스키마

```
users ─────────┐
  id (PK)      │
  kakao_id (UQ)│
  name         │
  role         │     contacts ──────────┐
  push_sub     │       id (PK)         │
  onboarding_  │       fc_id (FK→users) │
  completed    │       name, phone,     │
               │       company_name,    │
               │       industry, region │
               │                        │
               │     meetings ──────────┤
               │       contact_id (FK)  │
               │       title, status    │
               │       scheduled_at     │
               │       reminder_sent    │
               │       memo_submitted   │
               │                        │
               │     interactions ──────┤
               │       contact_id (FK)  │
               │       meeting_id (FK)  │
               │       type, summary    │
               │       sentiment        │
               │                        │
               │     briefs ────────────┤
               │       contact_id (FK)  │
               │       company_analysis │
               │       insights (JSONB) │
               │       generated_at     │
               │                        │
               └─── matches ────────────┘
                      contact_a_id (FK)
                      contact_b_id (FK)
                      score, status
                      synergy_description
```

Alembic 마이그레이션 2개:
1. `722606141b25` — 전체 테이블 생성
2. `a1b2c3d4e5f6` — `onboarding_completed` 추가, briefs에 timestamp 추가

---

## 6. 테스트 현황

**151 tests, PostgreSQL `synco_test` DB 직접 사용**

| 파일 | 테스트 수 | 커버리지 |
|------|-----------|----------|
| test_auth.py | 7 | 로그인 리다이렉트, HTMX, 만료 토큰, 역할 선택 |
| test_contacts.py | 12 | CRUD 전체, 검색, 권한 격리 |
| test_meetings.py | 11 | CRUD, 완료/취소, HTMX |
| test_meeting_memo.py | 7 | 메모 제출, 빈 메모 건너뛰기, Interaction 생성, HTMX |
| test_interactions.py | 5 | 생성, 삭제, 필터링 |
| test_briefs.py | 13 | 생성(mock), 캐시, 강제 재생성, 파싱 유닛 |
| test_matching.py | 30 | 스코어링 유닛, 매칭 생성, API 엔드포인트 |
| test_match_status.py | 7 | 수락/거절/확인 상태 변경, 권한 격리, 잘못된 상태값 |
| test_import.py | 14 | 컬럼 매핑, CSV 파싱, 중복 제거 |
| test_voice_memo.py | 13 | 구조화, JSON 파싱, CLI 실패 폴백 |
| test_push.py | 8 | 구독/해제, VAPID 키, 발송 서비스 유닛 |
| test_scheduler.py | 8 | 리마인더 로직 + 푸시 발송, 스케줄러 시작/중지 |
| test_schemas.py | 19 | 전화번호 정규화, 입력 검증 |

---

## 7. 배포 구조

```
서버 (VPS)
│
├── PostgreSQL (상시 가동, 독립)
│   docker compose -f docker-compose.db.yml up -d
│   └── synco_db_data (Docker volume, 영속)
│
├── synco-app (서비스, 코드 변경 시 재빌드)
│   docker build -t synco-app .
│   docker stack deploy -c docker-stack.yml synco
│   └── Moa_net (외부 네트워크, Nginx 연결)
│
└── Nginx (리버스 프록시, HTTPS)
    └── synco.kr → localhost:8000
```

### 배포 순서

```bash
# 1. DB (최초 1회, 이후 상시 가동)
docker compose -f docker-compose.db.yml up -d

# 2. 마이그레이션 (스키마 변경 시)
alembic upgrade head

# 3. 서비스 빌드 + 배포
docker build -t synco-app .
docker stack deploy -c docker-stack.yml synco

# 4. 확인
docker service ls
docker service logs synco_app
```

### 개발 모드

```bash
# DB는 같은 Docker 컨테이너 사용
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 테스트
pytest -v
```

---

## 8. 환경 변수 (.env)

| 변수 | 필수 | 설명 |
|------|------|------|
| SECRET_KEY | O | JWT 서명 키 |
| DATABASE_URL | O | `postgresql+asyncpg://synco:synco@localhost:5432/synco` |
| KAKAO_CLIENT_ID | O | 카카오 앱 REST API 키 |
| KAKAO_CLIENT_SECRET | O | 카카오 앱 시크릿 |
| KAKAO_REDIRECT_URI | O | `https://synco.kr/auth/kakao/callback` |
| DEBUG | - | `true`이면 SQL 로그 출력 |
| VAPID_PRIVATE_KEY | - | Web Push VAPID 개인키 (푸시 알림 발송용) |
| VAPID_PUBLIC_KEY | - | Web Push VAPID 공개키 (브라우저 구독용) |

AI는 `claude` CLI 명령어가 PATH에 있으면 동작. 별도 API 키 불필요.

---

## 9. 알려진 이슈

1. **CSRF + 일반 폼** — HTMX가 아닌 순수 HTML form POST는 CSRF 헤더 누락으로 403 발생 가능
2. **매칭 O(n^2)** — 연락처 수가 많아지면 성능 저하 (현재 prototype 수준에서는 문제 없음)
3. **`pytest-cov` 미설치** — `pytest --cov=app` 명령 실행 불가
4. **VAPID 키 미설정** — `.env`에 VAPID 키가 비어 있으면 푸시 알림이 발송되지 않음 (구독은 가능)
