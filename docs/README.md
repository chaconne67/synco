# synco 문서 — 내비게이션 인덱스

이 문서는 "뭘 찾고 싶은데 어디 봐야 하지?" 를 5초 안에 해결하기 위한 지도다. 실제 내용은 아래 링크된 문서에 있다. 이 파일에는 내용을 복사해 두지 않는다 (동기화 부담 방지).

---

## 1. 문서 전체 지도

| 문서 | 성격 | 핵심 내용 |
|---|---|---|
| [`/CLAUDE.md`](../CLAUDE.md) | Claude 작업 지침 + 인프라 요약 | 활성 앱, LLM 분담 정책, 서버/포트/SSH, 되돌리기 어려운 조작 가드 |
| [`/README.md`](../README.md) | 사용자 대면 Quick Start | 의존성 설치, 환경변수 목록, `dev.sh`/`deploy.sh`, Docker, 관리 커맨드 |
| [`master/01-business-plan.md`](master/01-business-plan.md) | 사업계획 | 시장·경쟁·수익 모델·GTM·방어 전략 |
| [`master/02-work-process.md`](master/02-work-process.md) | 업무 프로세스 | 용어·롤·온보딩·헤드헌팅 워크플로우·3층 상태 모델·ActionType 23종·화면별 흐름·시나리오·권한 매트릭스 |
| [`master/03-engineering-spec.md`](master/03-engineering-spec.md) | 개발 기획문서 | 스택·인프라·도메인 모델·Signal·URL 맵·뷰·파이프라인·서비스 함수·커맨드·배포·**현재 완성도**·로드맵 |
| [`design-system.md`](design-system.md) | 디자인 시스템 | Pretendard, 컬러 토큰, 컴포넌트 패턴 |
| [`../assets/ui-sample/*.html`](../assets/ui-sample/) | UI 목업 | 디자인 단일 진실 소스 |
| [`archive/`](archive/) | 과거 기록 | 삭제해도 무방. 역사적 맥락용 |

---

## 2. 용도별 빠른 찾기

### 🚀 프로젝트 써보기 / 돌려보기

| 찾는 것 | 문서 |
|---|---|
| 빠른 시작(의존성 설치, migrate, 개발 서버) | [`/README.md` §빠른 시작](../README.md#빠른-시작) |
| 개발 서버 명령 (`./dev.sh`) | [`/CLAUDE.md` §Commands](../CLAUDE.md#commands) |
| 테스트 / 린트 / 포맷 | [`/CLAUDE.md` §Commands](../CLAUDE.md#commands) · [`master/03` §13.1](master/03-engineering-spec.md#131-로컬-개발) |
| 관리 커맨드 (이력서 import, 임베딩 생성 등) | [`/README.md` §주요 명령](../README.md#주요-명령) · [`master/03` §12](master/03-engineering-spec.md#12-관리-커맨드) |
| 환경변수 전체 목록 | [`/README.md` §주요 환경변수](../README.md#주요-환경변수) |

### 🛠️ 기술 스택 / 아키텍처

| 찾는 것 | 문서 |
|---|---|
| 기술 스택 요약 | [`/CLAUDE.md` §Tech Stack](../CLAUDE.md#tech-stack) · [`master/03` §1](master/03-engineering-spec.md#1-기술-스택) |
| LLM 분담 (Claude CLI vs Gemini) | [`/CLAUDE.md` §Tech Stack](../CLAUDE.md#tech-stack) |
| 저장소 / 앱 구조 | [`master/03` §2](master/03-engineering-spec.md#2-저장소-구조) · [`master/03` §4](master/03-engineering-spec.md#4-django-앱-목록) |
| 도메인 모델 (accounts / candidates / clients / projects / data_extraction) | [`master/03` §5](master/03-engineering-spec.md#5-도메인-모델) |
| URL 맵 | [`master/03` §7](master/03-engineering-spec.md#7-url-맵) |
| 뷰 카탈로그 | [`master/03` §8](master/03-engineering-spec.md#8-뷰-카탈로그) |
| 템플릿 구조 | [`master/03` §9](master/03-engineering-spec.md#9-템플릿-구조) |
| 데이터 파이프라인 (이력서 추출·임베딩·매칭·알림 등) | [`master/03` §10](master/03-engineering-spec.md#10-데이터-파이프라인-구현-기준) · [`master/02` §13](master/02-work-process.md#13-데이터-파이프라인) |
| 서비스 레이어 함수 시그니처 | [`master/03` §11](master/03-engineering-spec.md#11-서비스-레이어-함수-참조-시그니처) |
| 자동 파생 / Signal 로직 (Phase·Hire·알림) | [`master/03` §6](master/03-engineering-spec.md#6-자동-파생과-시스템-규칙-signal-로직) · [`master/02` §9](master/02-work-process.md#9-자동-파생과-시스템-규칙) |
| 컨벤션 (HTMX, UUID, TimestampMixin 등) | [`/CLAUDE.md` §Conventions](../CLAUDE.md#conventions) · [`master/03` §16](master/03-engineering-spec.md#16-컨벤션-요약) |

### 🏗️ 인프라 / 배포

| 찾는 것 | 문서 |
|---|---|
| 서버 구성 (운영/DB/코코넛 IP와 역할) | [`/CLAUDE.md` §Infrastructure](../CLAUDE.md#infrastructure) · [`master/03` §3](master/03-engineering-spec.md#3-인프라-구성) |
| SSH 접속 | [`/CLAUDE.md` §SSH 접속](../CLAUDE.md#ssh-접속) · [`master/03` §SSH](master/03-engineering-spec.md#ssh) |
| DB 구성 (운영 / 개발 분리) | [`/CLAUDE.md` §DB 구성](../CLAUDE.md#db-구성) |
| 포트 정책 (8000 개발, 8080 스모크, 443/80 운영) | [`/CLAUDE.md` §포트 정책](../CLAUDE.md#포트-정책) · [`master/03` §포트 정책](master/03-engineering-spec.md#포트-정책) |
| 배포 실행 (`./deploy.sh`) | [`/README.md` §배포](../README.md#배포) · [`master/03` §13.3](master/03-engineering-spec.md#133-배포-deploysh) |
| 배포 자산 배치 (`/home/docker/synco/`) | [`master/03` §13.4](master/03-engineering-spec.md#134-배포-자산-배치) |
| 운영 미적용 migration 확인 | [`/CLAUDE.md` §DB Migration 운영 확인](../CLAUDE.md#db-migration-운영-확인) |
| 마이그레이션 규칙 | [`master/03` §13.2](master/03-engineering-spec.md#132-마이그레이션-규칙) |
| **되돌리기 어려운 조작 가드** | [`/CLAUDE.md` §되돌리기 어려운 조작](../CLAUDE.md#되돌리기-어려운-조작--synco-로컬-가드) |

### 📊 개발 현황 / 로드맵

| 찾는 것 | 문서 |
|---|---|
| 완성된 기능 / 부분 구현 / 미구현 | [`master/03` §14](master/03-engineering-spec.md#14-현재-완성도--잔재) |
| UI 재정리 진행 상황 | [`master/03` §14.4](master/03-engineering-spec.md#144-ui-재정리-진행-중) |
| Phase 의존성 로드맵 | [`master/03` §15](master/03-engineering-spec.md#15-phase-의존성-구현-로드맵) |
| 개발 완료 / 진행 중 / 예정 (비즈니스 관점) | [`master/01` §6](master/01-business-plan.md#6-기술-스택-및-현황) |
| 테스트 상태 (현재 `124 passed`) | [`/README.md` §현재 상태](../README.md#현재-상태) |

### 🧑‍💼 업무 / 제품 이해

| 찾는 것 | 문서 |
|---|---|
| 용어집 (Project/Application/ActionItem 등) | [`master/02` §2](master/02-work-process.md#2-용어집) |
| 사용자 롤 / 멀티테넌시 | [`master/02` §3](master/02-work-process.md#3-사용자-롤과-멀티테넌시) |
| 온보딩 여정 | [`master/02` §4](master/02-work-process.md#4-온보딩-여정--처음-가입부터-첫-프로젝트까지) |
| 헤드헌팅 전체 워크플로우 | [`master/02` §6](master/02-work-process.md#6-헤드헌팅-전체-워크플로우) |
| 3층 상태 모델 (Phase × Application × ActionItem) | [`master/02` §7](master/02-work-process.md#7-phase--application--actionitem--3층-모델) |
| ActionType 23종 | [`master/02` §8](master/02-work-process.md#8-actiontype--23종-시드) |
| 화면별 업무 흐름 | [`master/02` §11](master/02-work-process.md#11-화면별-업무-흐름) |
| 일일/주간 시나리오 | [`master/02` §16](master/02-work-process.md#16-일일주간-업무-시나리오) |
| 권한 매트릭스 | [`master/02` §17](master/02-work-process.md#17-권한-매트릭스) |

### 🎨 디자인

| 찾는 것 | 문서 |
|---|---|
| 컬러 토큰 / Pretendard / 컴포넌트 패턴 | [`design-system.md`](design-system.md) |
| UI 목업 (단일 진실 소스) | [`../assets/ui-sample/`](../assets/ui-sample/) |

---

## 3. 문서 작성 규칙

- 모든 문서는 `docs/` 아래에 둔다 (루트에 `.md` 신규 생성 금지. `README.md`/`CLAUDE.md` 제외)
- 마스터 문서는 `docs/master/` 에서만 관리
- 마스터 문서에서 `docs/archive/` 를 링크하지 않는다. 필요한 내용은 마스터 자체에 녹여넣는다
- 디자인 목업 변경 시 `design-system.md` 와 `master/02-work-process.md` 의 화면 설명을 함께 업데이트
- 새 기획/결정은 마스터를 직접 편집. archive에 새 파일 추가 금지
- **이 인덱스(`docs/README.md`)에는 내용을 복사하지 않는다.** 링크만 유지해 동기화 부담을 없앤다
