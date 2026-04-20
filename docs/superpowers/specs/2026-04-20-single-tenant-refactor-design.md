# Single-Tenant 리팩터 — 멀티테넌시 제거 + RBAC 단순화

**작성일:** 2026-04-20
**상태:** Phase 2a 배포 중단. 본 리팩터 선행 후 Phase 2a 코드 재연결.

## 목표

synco 를 **회사별 완전 독립 배포** (single-tenant) 구조로 전환하고 권한 시스템을 **Level 0/1/2 + is_superuser** 로 단순화한다. `Organization` / `Membership` 모델과 초대 워크플로를 제거하여 "처음이 꼬여있어서 전체가 다 불편하다" 는 구조적 문제를 걷어낸다.

## 배경

현재 구조의 문제:

- `Organization` 모델 + `Membership` 조인 테이블 + 모든 엔티티의 `organization` FK 3층이 코드 전반에 박혀 있음
- `Membership.role` (owner/consultant/viewer) + `Membership.status` (active/pending/rejected) + 초대 코드 발송·수락 플로우가 존재하지만 실제 사용 시나리오가 얇음
- 대시보드 스코프 규칙 (owner=조직 전체 / consultant=본인 담당) 이 기존 테스트 (`tests/test_views_dashboard.py::test_only_assigned_actions_visible`) 와 의도적으로 충돌하며 Phase 2a 배포가 막힘
- 멀티테넌시의 복잡성 대비 실제 "한 서버에 여러 회사가 섞여 들어가는" 유즈케이스가 없음

## 범위

### 포함

1. `Organization`, `Membership`, 초대 관련 모델·뷰·템플릿·마이그레이션 전부 제거
2. 모든 엔티티에서 `organization` FK 필드 제거
3. `User` 모델에 `level` 필드(Int, 0/1/2) 추가 + 구 Membership 부속 필드 (Gmail/Telegram/알림) 이관
4. 카카오 OAuth 단일 로그인
5. 신규 유저 승인 플로우 (Level 0 대기 페이지 → 사장·슈퍼유저가 레벨 승격)
6. `@level_required(n)` 데코레이터 도입, `@membership_required` 제거
7. 쿼리 스코프 헬퍼 (`scope_work_qs(qs, user)`) 도입 — 업무성 엔티티 표준 필터
8. `django-hijack` 통합 — 슈퍼유저가 `/admin` 에서 "이 유저로 로그인"
9. 마이그레이션 파일 전부 삭제 후 재생성 (fresh `0001_initial.py`)
10. ActionType 등 필수 마스터 데이터 시드 스크립트
11. `deploy/docker-stack-synco.yml` 은 single-tenant 형태 유지, 미래 확장용 `--company` 인자 스텁만 추가
12. 기존 Phase 2a 대시보드 코드를 새 권한 모델로 갈아끼움

### 제외

1. **한 서버 위에 여러 회사 병렬 배포** — 이번엔 1회사 1스택. 두 번째 회사가 생기는 시점에 복제
2. **이메일/휴대폰 번호 로그인** — 카카오 OAuth 만
3. **Phase 2b 대시보드 카드 (Revenue, Recent Activity)** — 별도 후속 프로젝트

## 아키텍처

### 회사별 완전 독립 배포

```
┌─ A회사 (synco-a.example.com) ─┐   ┌─ B회사 (synco-b.example.com) ─┐
│  동일 Django 이미지          │   │  동일 Django 이미지          │
│  ├─ User + 업무/정보 모델    │   │  ├─ User + 업무/정보 모델    │
│  └─ 단일 DB (A 전용)         │   │  └─ 단일 DB (B 전용)         │
│  Docker Swarm 스택 A         │   │  Docker Swarm 스택 B         │
└──────────────────────────────┘   └──────────────────────────────┘
```

코드는 회사를 모른다. `request.user` 가 누구인지만 안다. 격리의 책임은 인프라 레이어 (분리된 스택/DB/도메인) 가 완전히 진다.

## 권한 모델

### 두 개 축

| 축 | 필드 | 값 | 의미 |
|---|---|---|---|
| 비즈니스 권한 | `User.level` (IntegerField) | 0 / 1 / 2 | 승인 상태 + 비즈니스 역할 |
| 시스템 권한 | `User.is_superuser` (bool) | True / False | Django `/admin` 접근 (개발자) |

### 레벨 의미

**Level 0 — 승인 대기** (신규 유저 기본값)
- 카카오 로그인은 통과했지만 앱 기능 전부 잠김
- 승인 대기 페이지만 보임: "요청이 접수되었습니다. 승인 후 이용 가능합니다."
- "메인화면으로 가기" 버튼은 비활성
- 어떤 URL 을 직접 입력해도 대기 페이지로 리다이렉트

**Level 1 — 직원 (컨설턴트)**
- 정보성 데이터 (Candidate / Client / 참고 마스터) 전체 조회
- 업무성 데이터 (Project / Application / ActionItem / Interview / Submission) 본인 assigned 만
- 대시보드는 본인 업무 기준 집계

**Level 2 — 사장**
- Level 1 의 모든 권한 + 조직 전체 업무 데이터 조회
- 유저 승인 권한 (Level 0 → 1/2 승격) — 앱 UI 내부 "팀 관리" 페이지에서 수행
- Client / ActionType / 참고 마스터 편집 — 앱 UI 내부 폼에서 수행
- Team 메뉴, 대시보드 조직 전체 집계
- **`/admin` 페이지는 진입 불가** (`is_staff=False`)

### Superuser 축 (별도)

- `is_superuser=True` 는 **개발자 전용**. 항상 `is_staff=True` 와 세트 → `/admin` 접근 가능
- 데이터 스코프는 Level 2 와 동일 (전체)
- 마이그레이션·모델 구조 수정 같은 기술 조작 담당
- 사장이 수행하는 모든 승인·편집을 `/admin` 에서도 직접 할 수 있음 (같은 일을 두 경로로 가능)
- **chaconne67@gmail.com** 은 초기 시드에서 `level=2, is_superuser=True, is_staff=True` 로 자동 생성
- 필요시 특정 사장에게도 `is_superuser=True` 를 부여할 수 있음 — 이 경우 그 사장은 `/admin` 도 열림

### `is_staff` 플래그의 역할

Django 의 `is_staff` 는 `/admin` 접근 게이트로 쓰며, `is_superuser` 와 **완전히 동기화**한다. 사장(Level 2) 도 `is_staff=False`. 사장이 관리 작업 (유저 승인, Client 편집 등) 을 수행하려면 `/admin` 이 아니라 앱 UI 안의 전용 페이지를 사용한다.

### 권한 체크 순서

1. **로그인 확인** (`@login_required`): 미로그인 시 카카오 로그인 페이지로
2. **승인 확인** (`@level_required(1)`): `level == 0` 이면 승인 대기 페이지로 강제 리다이렉트
3. **역할 확인** (`@level_required(2)`): 사장 전용 페이지 진입 시
4. **쿼리 스코프** (`scope_work_qs(qs, user)`): 업무성 엔티티 목록 조회 시 `level >= 2 or is_superuser` 이면 전체, 아니면 `assigned_consultants=user` 필터

### 데코레이터 표준

```
@login_required          # 모든 로그인 유저
@level_required(1)       # 승인된 유저만 (Level 1 이상 또는 superuser)
@level_required(2)       # 사장 이상 (Level 2 또는 superuser)
@superuser_required      # 개발자 전용 (is_superuser)
```

커스텀 `@membership_required` 는 제거.

## 데이터 스코프 매트릭스

| 분류 | 모델 | Level 0 | Level 1 (직원) | Level 2 (사장) / Superuser |
|---|---|---|---|---|
| 정보 — 후보자 | Candidate | 차단 | 전체 조회·검색·편집 | 전체 + 삭제 |
| 정보 — 후보자 부속 | ResumeDocument, Education, Experience, Certification | 차단 | Candidate 경유 접근 | 전체 |
| 정보 — 고객사 | Client | 차단 | 전체 조회 | 전체 + 편집·삭제 |
| 정보 — 계약 | Contract | 차단 | 전체 조회 | 편집·삭제 |
| 정보 — 참고 마스터 | University, Company, Certification(master) | 차단 | 전체 조회 | 편집 (`/admin`) |
| 정보 — 워크플로 마스터 | ActionType | 차단 | 드롭다운 조회 | 편집 (`/admin`) |
| 업무 — 프로젝트 | Project | 차단 | `assigned_consultants=self` | 전체 |
| 업무 — 지원 | Application | 차단 | 본인 담당 프로젝트 체인 | 전체 |
| 업무 — 할 일 | ActionItem | 차단 | `assigned_to=self` | 전체 |
| 업무 — 면접 | Interview | 차단 | 본인 담당 프로젝트 체인 | 전체 |
| 업무 — 제출 | Submission | 차단 | 본인 담당 프로젝트 체인 | 전체 |
| 업무 — 승인 | Approval | 차단 | 본인 관련만 | 전체 |
| 업무 — 뉴스피드 | NewsfeedPost | 차단 | 전체 조회 (읽기 전용) | 전체 + 리소스 관리 |
| 개인 — 본인 계정 | User (self row) | 차단 | 본인 row 프로필·알림 편집 | 전체 유저 관리 (/admin 은 Superuser) |

## 모델 변경 내역

### 제거

- `Organization` 모델 (accounts/models.py)
- `Membership` 모델 (accounts/models.py)
- `Invitation` / `accounts/invitations.*` 전체
- 모든 엔티티의 `organization` FK 필드
- `@membership_required` 데코레이터
- `request.org`, `request.membership` 컨텍스트 속성
- 서비스 함수 시그니처에서 `org` / `organization` 파라미터

### 추가

- `User.level` — IntegerField, choices=[(0,'대기'),(1,'직원'),(2,'사장')], default=0
- `User.gmail_token` 등 구 Membership 부속 필드 (정확한 목록은 구현 단계에서 현 Membership 필드를 스캔해 결정)
- `accounts/decorators.py::level_required(n)`
- `accounts/decorators.py::superuser_required`
- `accounts/services/scope.py::scope_work_qs(qs, user)` — 업무성 QS 표준 스코프 필터

### 유지

- `Project.assigned_consultants` (M2M → User) — 업무 스코프 핵심 키
- `ActionItem.assigned_to` (FK → User) — 개인 할당 핵심 키
- `*.created_by` 감사 필드
- UUID primary keys, TimestampMixin

## 로그인·승인 플로우

### 카카오 OAuth 통일

- `/login` 에 "카카오로 계속하기" 버튼 하나
- 유저명/비밀번호 로그인 폼 제거
- 일반 회원가입 뷰 제거

### 신규 유저 라이프사이클

1. 카카오 로그인 성공 → User 자동 생성 (`level=0`, `is_superuser=False`)
2. 최초 접속: 승인 대기 페이지 노출
   - 메시지: "승인 요청이 관리자에게 전달되었습니다. 확인해 주세요."
   - "메인화면으로 가기" 버튼 — **비활성**
3. 슈퍼유저/사장이 `/admin` 에서 `User.level` 을 1 또는 2 로 변경
4. 유저 재접속 → 동일 대기 페이지가 나오지만 "메인화면으로 가기" 버튼이 활성화됨
5. 버튼 클릭 → 대시보드로 이동

### 슈퍼유저 초기 시드

- 최초 배포 시 `manage.py migrate` 후 `manage.py seed_superuser` (신규 커맨드) 가 `.env` 의 `SYNCO_SUPERUSER_EMAIL=chaconne67@gmail.com` 기반으로 `level=2, is_superuser=True` User 한 명 생성
- 이후 신규 유저는 모두 이 슈퍼유저가 수동 승인

### 개발 테스트 UX — django-hijack

- `/admin` 유저 목록에서 "이 유저로 로그인" 버튼
- 슈퍼유저가 Level 1/2 테스트 계정을 admin 에서 수동 생성 (카카오 가입 없이 이메일+레벨만 지정)
- 버튼 클릭 → 그 유저 세션으로 전환 → 앱 UI 에서 해당 레벨 화면 직접 확인
- 상단에 "@target 으로 hijack 중 / 원래 계정으로 돌아가기" 배너

## 마이그레이션 전략

운영 DB 가 더미 데이터만 있으므로 **fresh start**:

1. 각 앱 (`accounts`, `clients`, `candidates`, `projects`, `data_extraction`) 의 `migrations/*.py` 를 모두 삭제 (단 `__init__.py` 유지)
2. 코드에서 `Organization`, `Membership` 정의·import·사용처 전부 제거
3. 모든 모델에서 `organization` FK 필드 삭제
4. `User` 에 `level` + 부속 필드 이관
5. `python manage.py makemigrations` — 각 앱당 새 `0001_initial.py` 하나씩 생성
6. 개발 DB: `docker compose down -v && docker compose up -d` → 볼륨째 초기화 → `migrate` → `seed_superuser`
7. 운영 DB (49.247.45.243): `docker exec` 로 `TRUNCATE` 전 테이블 또는 DB drop/create → `migrate` → `seed_superuser`
8. ActionType 같은 필수 마스터는 `0002_seed_actiontypes.py` 데이터 마이그레이션

**결과:** 각 앱 마이그레이션 history 가 `0001_initial.py` + 필요시 데이터 시드 파일 한두 개로 평탄화. 누적된 레거시 마이그레이션 청산.

## 배포 전략

### Phase 1 (이번 리팩터 범위)

- 현재 단일 Docker Swarm 스택을 그대로 유지. 단 코드만 single-tenant 로 전환.
- `deploy.sh` 는 `--company` 인자를 받는 **스텁만** 추가 (나중에 두 번째 회사가 생길 때 실구현)
- 운영 서버 (49.247.46.171) 의 스택 이름·DB 이름은 현행 유지

### Phase 2 (차후, 범위 외)

- 두 번째 회사가 들어오는 시점에 `deploy.sh --company=b` 구현
- 스택 템플릿화: `synco-${COMPANY_SLUG}`, DB 볼륨 분리, Nginx vhost 추가
- `.env.${COMPANY_SLUG}` 파일 분리
- DNS 설정

## Phase 2a 재연결

Phase 2a 대시보드 코드 (projects/services/dashboard.py) 는 현재 `Membership.role` 을 기준으로 owner/consultant 분기한다. 본 리팩터가 끝난 뒤:

- `scope_owner = membership.role == "owner"` → `scope_owner = user.level >= 2 or user.is_superuser`
- `get_dashboard_context(org, user, membership)` → `get_dashboard_context(user)` 로 시그니처 단순화
- `@membership_required` → `@level_required(1)`
- 뷰: `request.user.membership.organization` → `request.user` 만 넘김
- 테스트 (`tests/test_dashboard_phase2a.py`) 는 Membership fixture 제거, User + level 기반으로 재구성
- `tests/test_views_dashboard.py::test_only_assigned_actions_visible` 는 컨설턴트 (Level 1) 유저로 전환되어 자연스럽게 통과

대시보드 자체 로직은 유지되고 권한 레이어만 갈아끼운다.

## 테스트 전략

**conftest.py 재작성:**

- 기존 `org`, `owner`, `user`, `Membership` fixture 전면 개편
- 새 fixture:
  - `dev_user` — level=2, is_superuser=True
  - `boss_user` — level=2, is_superuser=False
  - `staff_user` — level=1, is_superuser=False
  - `pending_user` — level=0
- `logged_in_client(user)` — force_login
- 기존 `other_org_user` 는 제거 (다른 조직 개념 자체가 사라짐)

**신규 테스트 케이스:**

- Level 0 유저 → 어떤 URL 접근해도 승인 대기 페이지
- Level 1 유저 → 본인 assigned 프로젝트만 목록에 노출
- Level 2 유저 → 조직 전체 프로젝트 목록
- `/admin` 진입 → Level 2 만으론 403, is_superuser 만 허용
- Candidate 검색 → Level 1 도 전체 조회 가능
- Client 편집 → Level 1 은 403, Level 2 이상은 허용
- 카카오 로그인 콜백 → 신규 유저 자동 생성 + level=0
- django-hijack → 슈퍼유저가 Level 1 유저로 로그인 후 세션 전환 확인

**정리 대상:**

모든 기존 테스트에서 다음 패턴 제거:
- `Organization.objects.create(...)`
- `Membership.objects.create(user=, organization=, role=, status=)`
- `request.org`, `request.membership`
- 서비스 호출 시 `org=` 인자

## 태스크 분할 (writing-plans 에서 상세화 예정)

1. **T1** — User 모델 확장 (level 필드 + 부속 필드 이관). 단 Membership/Organization 은 아직 둠. 새 테스트 fixture 준비.
2. **T2** — `level_required` / `superuser_required` 데코레이터 + `scope_work_qs` 헬퍼 구현. 단위 테스트.
3. **T3** — 카카오 로그인 단일화. 기타 로그인 경로 제거. 승인 대기 페이지 구현.
4. **T4** — django-hijack 통합.
5. **T5** — 모든 뷰·서비스에서 `organization` 파라미터 제거, 데코레이터 교체, 쿼리 스코프 교체. 앱 단위로 나눔 (accounts → clients → candidates → projects → data_extraction).
6. **T6** — Organization / Membership / Invitation 모델 및 관련 코드 제거.
7. **T7** — 모든 엔티티 `organization` FK 필드 제거. 마이그레이션 wipe → `makemigrations` 재생성.
8. **T8** — ActionType 등 마스터 데이터 시드 마이그레이션.
9. **T9** — 기존 테스트 스위트 전면 개편 (Organization/Membership fixture 제거, Level 기반 재작성).
10. **T10** — Phase 2a 대시보드 코드 (`projects/services/dashboard.py`, `tests/test_dashboard_phase2a.py`) 를 새 권한 모델로 교체.
11. **T11** — `deploy.sh` `--company` 스텁 추가 + 운영 DB 초기화 절차 문서화.
12. **T12** — 운영 서버 배포 및 seed_superuser 실행.

각 Task 는 writing-plans 단계에서 TDD 스텝·커밋 단위로 상세화.

## 오픈 이슈

- **구 Membership 필드 목록 확정** — Gmail 연결 토큰·텔레그램 chat_id·알림 설정 등 구체 필드명은 T1 착수 시 현재 `Membership` 모델을 스캔해 확정.
- **신규 유저 승인 알림** — 유저가 레벨 0 으로 들어오면 슈퍼유저에게 자동 알림 보낼지 여부는 이번 범위 외. 슈퍼유저가 `/admin` 대기 유저 목록을 수동 확인하는 것으로 시작. 필요해지면 별도 프로젝트.
- **Phase 2b 대시보드 카드** (Revenue, Recent Activity) 는 본 리팩터 이후 설계 재개.
- **운영 DB 초기화 타이밍** — T7 이후 운영 서버 재배포 시점에 한꺼번에. 서비스 중단 공지는 chaconne67 개발자 1인 사용 중이라 생략 가능.
