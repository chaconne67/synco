---
date: 2026-04-12
status: draft-v2
topic: taste-to-ship (tts)
type: workflow design spec
---

# taste-to-ship (tts) — End-to-End AI Build Workflow

> **v2 변경사항:** Stage 1e (Environment Readiness) 추가, `07-infrastructure.md` 설계 문서 추가 (8→9종), Stage 4.5 (Pre-Implementation Preflight) 추가, 새 프로젝트 부트스트랩 지원, 좀비/stale 자원 검사 강제화.


> *Choose your taste, I'll do the rest.*

SaaS 웹 애플리케이션을 **아이디어에서 배포까지** 하나의 워크플로우로 연결하는 메타-오케스트레이터. **기존 프로젝트에 기능 확장**하는 경우와 **빈 디렉토리에서 새 프로젝트를 부트스트랩**하는 경우 모두 동일한 워크플로우로 처리한다 (Stage 1e가 프로젝트 상태를 자동 감지하여 분기). 사용자의 인간 개입을 **Stage 1 통합 인터뷰 한 자리 + 배포 직전 1-click 확인**으로 한정하고, 그 사이 전 과정을 **세션 체이닝 기반 자동 실행**으로 처리한다.

## Motivation

### 해결하려는 3가지 문제

1. **설계 공백으로 인한 경로 의존성**
   현재 워크플로우(office-hours → brainstorming → 구현 계획서 초안 → 태스크 분할 → plan-forge-batch)의 "구현 계획서 초안" 단계에서 UI/UX 품질, 데이터 모델, 인증·권한, 기능 간 연계 등이 충분히 검토되지 않는다. 이 공백은 구현 이후에 드러나 수정 비용이 폭발한다. 특히 **디자인 결정**은 모든 화면에 퍼지고 나면 리팩토링이 거의 불가능하므로, 결정 시점이 "사후 리뷰"에서 **"구현 이전 승인"**으로 앞당겨져야 한다.

2. **장시간 작업에서의 컨텍스트 오염**
   아이디어에서 배포까지 전 과정을 한 세션에서 돌리면 컨텍스트가 포화되어 hallucination, 무한 루프, 엉뚱한 방향 탐색 같은 증상이 누적된다. `plan-forge-batch`가 구현 단계에서 해결한 "세션 경계로 컨텍스트 격리" 원리를 **워크플로우 전체 레벨에서 재적용**해야 한다.

3. **사용자 개입의 산발성**
   현재는 중간중간 사용자에게 질문이 튀어나와 맥락 전환 비용이 크다. 사용자는 "중간에 한참 알아서 진행해놓고 어떻게 하냐고 물어보면 뭘 물어보는지 몰라서 또 물어보고 왔다 갔다" 하는 상황을 겪는다. **모든 인간 개입을 앞단 한 자리에 모아야** 한다.

### 핵심 통찰

**사용자의 taste가 확정되면 — 제품 개념, 디자인 방향, 아키텍처 초안, 승인된 목업 — 나머지는 확산(diffusion) 과정으로 자동화 가능하다.** 노이즈에서 형상이 드러나는 diffusion 모델처럼, taste가 seed/prompt가 되어 점진적으로 구체화된 최종 제품으로 수렴한다.

---

## Goals

- **G1.** 아이디어 → 배포를 단일 워크플로우 스킬로 연결
- **G2.** 사용자 인간 개입을 Stage 1 통합 인터뷰 + 배포 1-click으로 한정
- **G3.** 경로 의존성이 있는 결정(디자인 룩앤필, 브랜드 톤, 모듈 경계)을 **사용자 승인 후에만** 진행
- **G4.** 전 과정을 세션 체이닝으로 분할하여 컨텍스트 오염 방지
- **G5.** `plan-forge-batch`의 엔진 로직을 재사용 가능한 라이브러리로 추출
- **G6.** 동적 세션 분할 계획으로 프로젝트 규모에 적응
- **G7.** 기존 `plan-forge-batch`는 유지하고 새 스킬을 병존시켜 점진적 전환
- **G8.** **기존 프로젝트 확장**과 **새 프로젝트 부트스트랩**을 동일 워크플로우에서 모두 지원. Stage 1e가 프로젝트 상태를 자동 감지하여 분기
- **G9.** 구현 시작 전에 **환경 준비 상태를 완전 검증**(기술 스택·DB·외부 서비스·좀비 프로세스·stale lock)하여, 자동 실행 단계에서 환경 문제로 중단되지 않도록 보장

## Non-Goals

- **NG1.** 완전 무인 실행 (사용자 개입 0건). Stage 1 인터뷰와 배포 확인은 사람이 반드시 한다.
- **NG2.** 예술적 디자인 자동 생성. 디자인은 **기능적 UX 품질**을 목표로 하며, 사용자 승인 없이 브랜드 정체성을 결정하지 않는다.
- **NG3.** 기존 `plan-forge-batch` 스킬의 즉시 폐기. 새 스킬과 병존하며 검증 후 삭제 여부를 결정한다.
- **NG4.** 다른 언어/프레임워크 지원. 현재 타겟은 Django + HTMX + Postgres 스택의 SaaS 웹 앱이다. 다른 스택은 추후 확장.
- **NG5.** 분산 실행. 로컬 단일 머신 기반으로 작동한다.
- **NG6.** 좀비 프로세스의 **무조건 자동 kill**. 파괴적 동작 전에 사용자 확인을 요구한다 (`/careful` 정신).

---

## Core Principles

| 원칙 | 적용 |
|---|---|
| **Path-dependency prevention** | 경로 의존성 있는 결정은 Stage 1에서 사용자 승인 후 확정 |
| **Context isolation via session chaining** | 모든 자동 실행 단위는 별도 세션. 상태는 파일시스템으로 전달 |
| **Human front-loading** | 인간 개입은 워크플로우 앞단에 뭉쳐서 한 번에 끝 |
| **Dynamic session planning** | Intake 이후 session-plan을 자동 생성하고 단계 사이에 재평가 |
| **Fault isolation via module boundaries** | 태스크는 architecture 문서의 모듈 경계를 절대 넘지 않음 |
| **Forge everything** | 설계 문서, 태스크 문서, 구현 계획 모두 adversarial review(담금질) 통과 |
| **Engine/content separation** | batch 엔진(세션 체이닝, 진행 추적)과 콘텐츠(담금질·구현·점검)를 분리 |
| **Environment verified before autonomy** | Stage 1 종료 전에 환경이 완전히 준비되어 있어야 함. 좀비·누수·미설정 존재 시 진행 금지 |
| **New or existing, same flow** | 프로젝트 상태(빈 디렉토리 vs 기존 레포)를 자동 감지. 동일 워크플로우가 부트스트랩 또는 확장으로 분기 |
| **Destructive ops require consent** | 좀비 kill, lock 파일 제거, 컨테이너 삭제 등 파괴적 동작은 사용자 확인 후 실행 |

---

## User Involvement Boundary

### 인간 접촉 포인트 (2개만)

| 포인트 | 성격 | 소요 시간 | 이유 |
|---|---|---|---|
| **Stage 1: Intake** (필수) | 인터랙티브 인터뷰, 1 sitting | 수십 분 ~ 1시간 | 제품 개념·디자인 룩앤필·아키텍처 제약은 머릿속에만 있음. 질문으로만 꺼낼 수 있음 |
| **Gate: Pre-Deploy** (필수) | 1-click y/n | 초 단위 | 배포는 blast radius 큼. 자동 금지 |

### 자동화 대상 (중간 개입 없음)

- 설계 문서 초안 작성
- 설계 담금질
- 태스크 분할
- 태스크 담금질
- Pre-implementation preflight
- 구현 + 구현 점검
- 배포 실행

**원칙:** Stage 1 종료 시점에 생성된 `intake/` 번들(및 new mode의 경우 skeleton 프로젝트)이 사용자 taste의 최종본이다. 이후 단계는 이 번들을 seed로 받아 실행한다. 중간에 사용자에게 추가 질문을 하지 않는다.

### Stage 1 내부 인터랙션 포인트 (한 sitting 안)

Stage 1 sitting 동안 사용자는 다음 지점에서 응답한다. 모두 "한 자리"에서 연속으로 진행된다:

| 시점 | 종류 | 내용 |
|---|---|---|
| 1a | 인터뷰 | office-hours 질문 시퀀스 |
| 1b | 선택 | 브랜드 톤, 색 방향, 참고 사이트 |
| 1c | **승인** | 목업 variant 선택 (대시보드·리스트·상세·컴포넌트) |
| 1d | 확인 | 모듈 목록·의존성·기술 스택 |
| 1e-1 | 대화 | 외부 서비스·DB 구성·배포 타겟 |
| 1e-3 | **승인** | 좀비·stale 자원 발견 시 kill 승인 |
| 1e-4 (new) | 확인 | skeleton 부트스트랩 결과 (첫 커밋 전 둘러보기) |
| 1e-4 (unclear) | 선택 | new/existing/abort |

---

## Pipeline Overview

```
[HUMAN, 1 sitting]
Stage 1: Intake ─────────────────────────────────────────┐
  1a. Product Brief       (/office-hours)                │
  1b. Design Direction    (design-consultation)          │
  1c. Visual Approval     (ui-mockup upgraded) ⭐        │ Session chain
  1d. Architecture Sketch (brainstorming)                │ (each sub-stage
  1e. Environment Readiness ⭐                           │  = 1 session)
      - Existing mode: verify stack / DB / services      │
      - New mode:      bootstrap skeleton project        │
      - 1e-1 Infrastructure intake (interactive)         │
      - 1e-2 Static env check (auto)                     │
      - 1e-3 Zombie & lock check (auto + user consent)   │
      - 1e-4 Bootstrap or verify (mode-dependent)        │
                                                          │
  → intake/ bundle (committed to git) ────────────────────┘
  ═════════════════ 이후 100% 자동 ═════════════════

[AUTO]
Stage 1.5: Session Planning
  - Read intake bundle + infrastructure-checklist.md
  - Re-run zombie check (light) for drift detection
  → session-plan.json

Stage 2: Design Package (9 docs)
  2a. Draft generation (00~07, 99)
  2b. design-forge-batch (개별 + 쌍 담금질)
  2c. Re-plan (session-plan 갱신)

Stage 3: Task Split
  99-agreed.md + 01-architecture.md → t01..tN + plan.md

Stage 4: Task Forging
  task-forge-batch (태스크별 담금질)

Stage 4.5: Pre-Implementation Preflight
  - 각 태스크가 필요한 리소스가 실제로 준비되어 있는지 확인
  - 태스크 수준의 정확한 환경 검증
  - 문제 발견 시 해당 태스크 skip + 리포트

Stage 5: Implementation
  impl-forge-batch (구현 + 점검)

[HUMAN, 1-click]
Gate: Pre-Deploy 확인

[AUTO]
Stage 6: Deploy
  ./deploy.sh
```

---

## Stage 1: Intake (Human, 1 Sitting)

통합 인터뷰를 통해 **사용자 taste의 최종본**을 생성한다. 내부적으로는 sub-stage마다 별도 세션으로 체이닝되지만, 사용자 경험상 연속된 인터뷰다.

### 1a. Product Brief

- **실행 스킬:** `/office-hours`
- **입력:** 사용자 아이디어 (구두)
- **출력:** `docs/intake/{project}/product-brief.md`
- **내용:**
  - 제품 개요, 문제 정의, 타겟 사용자
  - 가치 제안 (왜 이 제품인가)
  - 핵심 유스케이스 3~5개
  - 성공 지표
  - 경쟁/차별화 포인트

### 1b. Design Direction

- **실행 스킬:** `design-consultation` (gstack)
- **입력:** product-brief.md + 사용자 선호 질의
- **출력:** `docs/intake/{project}/design-direction.md`
- **내용:**
  - 브랜드 톤 (professional, playful, minimal, technical 등)
  - 색감 방향 (primary, accent, 중립 팔레트)
  - 타이포그래피 (Pretendard 기본, 대안 제안)
  - 참고 사이트 3~5개
  - 피하고 싶은 시각적 요소

### 1c. Visual Approval ⭐

**가장 중요한 sub-stage.** 경로 의존성을 앞단에서 끊는 단계.

- **실행 스킬:** `ui-mockup` (업그레이드판, Gemini Nano Banana Pro 기반)
- **입력:** product-brief.md + design-direction.md
- **출력:**
  - `docs/intake/{project}/approved-mockups/dashboard.png`
  - `docs/intake/{project}/approved-mockups/list.png`
  - `docs/intake/{project}/approved-mockups/detail.png`
  - `docs/intake/{project}/approved-mockups/component-library.png` (버튼·카드·네비)
  - `docs/intake/{project}/design-approved.md` (승인 근거, 피드백 정리)
- **프로세스:**
  1. 핵심 화면 3~5개 식별 (product-brief의 유스케이스 기반)
  2. 각 화면 variant 3~5개 병렬 생성 (Gemini Nano Banana Pro)
  3. 비교 보드 표시
  4. **사용자가 직접 선택** (일괄, 변형 승인 가능)
  5. 컴포넌트 라이브러리 샘플 생성 (버튼, 입력, 카드, 네비)
  6. 사용자가 최종 승인

**이 단계 없이 Stage 2로 진행 금지.** 디자인 미승인 상태로 워크플로우가 자동으로 넘어가면 안 된다.

### 1d. Architecture Sketch

- **실행 스킬:** `superpowers:brainstorming` (인터랙티브)
- **입력:** product-brief.md + (선택) 기존 시스템 제약
- **출력:** `docs/intake/{project}/architecture-sketch.md`
- **내용:**
  - 모듈 목록 초안 (이름, 책임 범위)
  - 모듈 간 의존성 방향 (DAG)
  - 기술 스택 확인 (기본: Django 5.2 + HTMX + Postgres)
  - 외부 통합 목록 (결제, 메일, 인증 등)
  - 기존 시스템과의 연계 제약 (기존 프로젝트 모드에서만)

### 1e. Environment Readiness ⭐

**가장 중요한 마지막 sub-stage.** 사용자가 자리에 있는 **마지막 기회**. 이 지점을 지나면 자동 실행이 시작되어 개입할 수 없다.

**핵심 역할:** 프로젝트 상태(빈 디렉토리 vs 기존 레포)를 자동 감지하여 **existing mode**(검증) 또는 **new mode**(부트스트랩)로 분기한다. 두 모드 모두 "Stage 2 이후 자동 실행이 환경 문제로 실패하지 않을 것"을 보장하는 것이 목표다.

**모드 감지:**

```bash
if [ -d .git ] && [ -f manage.py ]; then
  MODE="existing"
elif [ -z "$(ls -A . 2>/dev/null)" ]; then
  MODE="new"
else
  MODE="unclear"   # 사용자에게 확인 요청
fi
```

#### 1e-1. Infrastructure Intake (인터랙티브)

- **실행 스킬:** 신규 대화형 로직 (tts orchestrator 내부)
- **입력:** product-brief.md + architecture-sketch.md + 모드
- **출력:** `docs/intake/{project}/infrastructure-plan.md`
- **대화 내용:**
  - 외부 서비스 목록 확정 (결제·메일·OAuth·AI API 등)
  - 각 서비스의 credential 취득 계획 (이미 있음 / 지금 발급 / 나중에)
  - DB 구성:
    - existing: 현 DB 유지 vs 새 DB 프로비저닝
    - new: 로컬 Postgres 컨테이너 / 운영 DB 연결 선택
  - 배포 타겟 (기존 synco 인프라 vs 새 VM vs 로컬만)
  - 도메인·SSL 계획
  - 운영 모니터링·로깅 전략

#### 1e-2. Static Environment Check (자동)

모드와 무관하게 실행되는 기본 환경 검증. 모든 체크는 **read-only** — 파괴적 동작 없음.

| 검사 항목 | 방식 | 통과 조건 |
|---|---|---|
| Python 버전 | `python --version` | ≥ 3.13 |
| uv | `uv --version` | 존재 |
| Git | `git --version`, `git status --porcelain` | 존재 |
| Docker 데몬 | `docker info` | 동작 중 |
| Docker Compose | `docker compose version` | v2 이상 |
| Red-team CLI | `which codex`, `which gemini` | 최소 1개 존재 (없으면 Agent 폴백 경고) |
| API 키 | `echo $OPENAI_API_KEY`, `$GEMINI_API_KEY` | 최소 1개 존재 |
| Disk space | `df -h .` | 프로젝트 경로에 1GB+ 여유 |
| **Existing 전용:** Django 설치 | `uv run python -c "import django; print(django.VERSION)"` | ≥ 5.2 |
| **Existing 전용:** Migration 상태 | `uv run python manage.py makemigrations --check --dry-run` | 미생성 migration 없음 |
| **Existing 전용:** DB 접속 | `docker compose ps` + `pg_isready` | 로컬 DB 또는 운영 DB 접속 가능 |
| **Existing 전용:** `.env` 키 대조 | `.env.example` ∩ `.env` | 필수 키 모두 존재 |

#### 1e-3. Zombie & Lock Check ⭐ (자동 + 사용자 확인)

**경로 의존성 못지않게 실무에서 자주 실패하는 지점.** 이전 실행이 남긴 잔재를 식별하고 제거한다.

| 검사 대상 | 확인 방법 | 조치 원칙 |
|---|---|---|
| **포트 점유** (8000, 5432, 8080) | `lsof -i:$PORT` 또는 `ss -tlnp` | 점유 프로세스 식별 → 사용자에게 리포트 → 확인 후 kill. **다른 포트로 회피 금지** (CLAUDE.md 포트 정책) |
| **Orphan Django runserver** | `pgrep -af "manage.py runserver"` + ppid 체크 | 부모 죽은 것만 식별 → 사용자 확인 후 kill |
| **Orphan claude CLI 세션** (이전 tts 잔재) | `pgrep -af "claude -p"` + ppid 체크 | 부모 죽은 것 식별 → 사용자 확인 후 kill |
| **Stale lock 파일** | `.claude/*.lock`, `*.pid`, `/tmp/*.pid` | 파일 내 PID 검증 → 소유자 죽었으면 **자동 제거** (안전), 살아있으면 경고 |
| **Orphan Docker 컨테이너** | `docker ps -a --filter "status=exited"` + 이름/레이블 | 이전 테스트/배포 잔재 식별 → 사용자 확인 후 `docker rm` |
| **Stale Docker 자원** | `docker system df`, 미사용 volume/network | 미사용 자원 리포트 → 정리 제안 (강제 아님) |
| **DB 연결 누수** | `psql -c "SELECT pid, state, state_change FROM pg_stat_activity WHERE state='idle in transaction' AND state_change < NOW() - INTERVAL '10 minutes'"` | 오래된 idle-in-tx 식별 → 사용자 확인 후 `pg_terminate_backend` |
| **파일 시스템 lock** | `fuser` / `lsof`로 `.git/index.lock`, `uv.lock` 등 감지 | 보유 프로세스 식별, 죽은 경우 경고 (자동 삭제 위험) |

**조치 원칙:**

| 상황 | 동작 |
|---|---|
| 소유자 PID가 이미 죽은 stale lock 파일 | **자동 제거** (안전) |
| 살아있는 프로세스가 보유한 포트/리소스 | **식별 + 리포트**, 사용자 확인 후 kill |
| 정체 불명 프로세스 (사용자도 모르겠다 답) | **유지**, "수동 점검 필요" 경고 후 Stage 1e 진행 거부 |

**게이트 동작:** 1e-3을 통과해야만 1e-4로 진행 가능. 좀비를 걷어내지 않고 자동 실행 단계로 넘어가면 Stage 5 구현 중간에 "연결 경쟁" 실패가 발생한다.

#### 1e-4. Mode-Dependent Action

##### Existing mode — 검증 완료

- 위 1e-2, 1e-3이 모두 통과 → 준비 완료
- `docs/intake/{project}/environment-check.md` 에 스냅샷 기록

##### New mode — Skeleton Bootstrap

신규 프로젝트의 경우, intake의 architecture-sketch + infrastructure-plan을 바탕으로 **최소 뼈대**를 실제로 생성한다. **모듈(Django app)은 만들지 않는다** — 모듈 생성은 Stage 5 구현 시 태스크로 처리. 1e-4가 만드는 것은 "Stage 2가 문서를 쓸 공간"이다.

**생성 목록:**

1. **Git 초기화:** `git init`, 초기 `.gitignore` (Python + Django + IDE + Docker 표준)
2. **uv 초기화:** `uv init` → `pyproject.toml`, `uv.lock`
3. **Python 의존성 설치:** Django 5.2, psycopg, HTMX 템플릿 로더, pytest-django, ruff 기본 세트
4. **Django 프로젝트 생성:** `django-admin startproject config .` (config는 settings 루트)
5. **Settings 템플릿 적용:**
   - `DATABASES` → Postgres (로컬 docker-compose 접속)
   - `INSTALLED_APPS` → 기본 + `django.contrib.postgres`
   - `TIME_ZONE = 'Asia/Seoul'`, `LANGUAGE_CODE = 'ko-kr'`
   - `AUTH_USER_MODEL` placeholder (Stage 5에서 교체 가능)
   - Templates backend + static files
6. **Docker Compose (개발):** `docker-compose.yml` with Postgres 16 service
7. **`.env.example`:** 필수 키 전체 목록 (DB, SECRET_KEY, API keys, ...)
8. **`.env`:** example 복사본 (사용자가 실제 값 채움)
9. **`dev.sh`:** 개발 서버 실행 스크립트 (Django + Tailwind watch 병행)
10. **`pytest` 설정:** `pyproject.toml` [tool.pytest.ini_options]
11. **`ruff` 설정:** format + lint 기본값
12. **Tailwind + Pretendard 설정:** `package.json`, `tailwind.config.js`, 기본 CSS
13. **`CLAUDE.md` 템플릿:** 프로젝트 메모리 초기본 (synco의 CLAUDE.md 구조 참고)
14. **`deploy.sh` 템플릿:** synco의 deploy.sh 구조 복사, 주석으로 "배포 타겟 확정 후 수정" 표시
15. **`README.md`:** 제품명 + 한 줄 설명 + 개발 시작 가이드
16. **초기 migration:** `uv run python manage.py migrate` (Django 기본 테이블 생성)
17. **첫 커밋:** `git add . && git commit -m "chore: initial skeleton from tts"`

**검증:**
- `uv run python manage.py check --deploy` 경고 허용 (Stage 5에서 교정)
- `uv run python manage.py runserver --noreload` 으로 1초 부팅 테스트
- `pytest --collect-only` 로 테스트 수집 가능 확인

##### Unclear mode — 사용자에게 확인

디렉토리에 파일은 있는데 `manage.py`가 없거나, git은 있는데 Django가 아닌 경우. 사용자에게:
- (a) 새 프로젝트로 취급 (현 파일을 건드리지 않고 skeleton 생성 거부)
- (b) 기존 프로젝트로 취급 (Django 수동 설정 전제)
- (c) 중단

### Intake 번들 최종 구조

```
docs/intake/{YYYYMMDD}-{project}/
├── product-brief.md
├── design-direction.md
├── design-approved.md
├── approved-mockups/
│   ├── dashboard.png
│   ├── list.png
│   ├── detail.png
│   └── component-library.png
├── architecture-sketch.md
├── infrastructure-plan.md      ⭐ 1e-1 산출물
├── environment-check.md        ⭐ 1e-2/1e-3 스냅샷
├── zombie-cleanup-log.md       ⭐ 1e-3 조치 이력
└── mode.txt                    ⭐ "existing" | "new" | "unclear→resolved-as-X"
```

새 프로젝트의 경우, 위 intake 번들과 **별도로** 프로젝트 루트에 skeleton 파일들(`manage.py`, `pyproject.toml`, `docker-compose.yml` 등)이 생성된다.

모든 파일은 git commit된다. 이 커밋이 **"이후 자동 실행"의 트리거**다.

---

## Stage 1.5: Session Planning (Auto)

### 목적

Intake 번들을 입력으로 받아, 이후 stage들이 어떻게 세션 단위로 쪼개질지 **동적으로 계획**한다. 정적 분할로는 프로젝트 규모에 적응할 수 없다. 동시에 **환경 drift**(Stage 1e 이후 좀비 재발생 등)를 가볍게 재검증한다.

### 입력

- Intake 번들 전체 (product-brief, architecture-sketch, infrastructure-plan, environment-check, approved-mockups)

### 처리

1. **설계 문서 수 결정** — 기본 9종, 프로젝트 규모에 따라 일부 통합 가능 (소규모에서 `06-workflow-map`을 `00-overview`에 통합 등)
2. **태스크 수 N 추정** — `architecture-sketch.md`의 모듈 개수 + 복잡도 기반
3. **각 논리 단위의 복잡도 분류** — 소/중/대
4. **세션 분할 결정:**
   - 소: 1 unit = 1 session
   - 중: 1 unit = 1 session (watchdog 감시)
   - 대: 1 unit = 2~3 sessions (의도적 분할)
5. **의존성 그래프 생성**
6. **Light drift check** — Stage 1e 종료 후 환경이 바뀌었을 수 있음:
   - 핵심 포트(8000, 5432) 재점검
   - Docker 데몬 살아있음
   - Git HEAD가 intake commit 뒤에 있음 (오염 없음)
   - 문제 발견 시 `session-plan.json`에 `blockers` 기록, 자동 진행 중단 후 사용자 재호출 대기

### 출력

`docs/forge/{project}/session-plan.json`

```json
{
  "schema_version": "1.0",
  "project": "{project}",
  "created_at": "2026-04-12T...",
  "stages": [
    {
      "id": "2.1",
      "type": "design-draft",
      "sessions": [
        {"unit": "00-overview", "complexity": "소", "estimated_minutes": 5},
        {"unit": "01-architecture", "complexity": "중", "estimated_minutes": 10},
        {"unit": "02-design-system", "complexity": "중", "estimated_minutes": 10},
        {"unit": "03-ux-flows", "complexity": "중", "estimated_minutes": 10},
        {"unit": "04-data-model", "complexity": "중", "estimated_minutes": 10},
        {"unit": "05-auth-rbac", "complexity": "중", "estimated_minutes": 10},
        {"unit": "06-workflow-map", "complexity": "소", "estimated_minutes": 5},
        {"unit": "99-implementation-plan", "complexity": "대", "estimated_minutes": 20}
      ]
    },
    {
      "id": "2.2",
      "type": "design-forge",
      "sessions": [
        {"unit": "00-overview", "complexity": "소"},
        {"unit": "01-architecture", "complexity": "대"},
        ...
      ]
    },
    {
      "id": "3",
      "type": "task-split",
      "sessions": [{"unit": "split", "complexity": "중"}]
    },
    {
      "id": "4",
      "type": "task-forge",
      "sessions": [],
      "deferred": true,
      "deferred_reason": "태스크 수 N은 Stage 3 종료 후 확정. 재평가 시 채워짐."
    },
    {
      "id": "5",
      "type": "impl",
      "sessions": [],
      "deferred": true,
      "deferred_reason": "태스크 수 N은 Stage 3 종료 후 확정. 재평가 시 채워짐."
    }
  ],
  "deps": {
    "2.2": ["2.1"],
    "3": ["2.2"],
    "4": ["3"],
    "5": ["4"]
  }
}
```

### 재평가 지점 (Re-planning)

세션 계획은 **단계 간에 갱신**된다:

| 재평가 지점 | 무엇을 갱신하는가 |
|---|---|
| Stage 2 종료 후 | 실제 설계 복잡도 → Stage 3 태스크 수 예측 |
| Stage 3 종료 후 | 실제 태스크 수 N 확정 → Stage 4, 5 세션 수 확정 |
| Stage 4 종료 후 | 담금질 결과 복잡도 → Stage 5 세션 분할 조정 |

재평가 로직은 `session-planner` 스킬이 각 단계 종료 시 자동 호출된다.

### 폭주 방지 (Watchdog)

`_forge-batch-engine`의 watchdog이 각 세션의 journal mtime과 CPU를 감시하여:
- hang 감지 시 kill + respawn
- 지속 시간이 임계치 초과 시 "세션 너무 큼" 경고를 `session-plan.json`에 기록
- 다음 재평가 때 해당 unit을 더 잘게 분할

---

## Stage 2: Design Package (Auto)

### 역할 재정의

Stage 2는 **디자인 결정을 하는 곳이 아니다.** Intake에서 이미 승인된 인풋을 **형식화(formalize)**하는 곳이다.

### 9-Doc Design Package

```
docs/designs/{YYYYMMDD}-{project}/
├── 00-overview.md            제품 개요, 목표, 성공 지표, 유스케이스
├── 01-architecture.md        ⭐ 모듈 경계, 인터페이스, 의존성, fault isolation
├── 02-design-system.md       디자인 시스템 (색·폰트·컴포넌트)
├── 03-ux-flows.md            화면·플로우 (intake의 승인된 목업 기반)
├── 04-data-model.md          엔티티·관계·인덱스·마이그레이션
├── 05-auth-rbac.md           인증, 역할/권한 매트릭스, 테넌시 모델
├── 06-workflow-map.md        사용자 여정, 기능 연계, 상태 전이
├── 07-infrastructure.md      ⭐ 런타임·DB·외부서비스·env vars·배포·CI/CD
└── 99-implementation-plan.md 구현 계획 (태스크는 01의 모듈 경계 준수)
```

### Intake ↔ Design Package 맵핑

| 설계 문서 | Intake 인풋 |
|---|---|
| `00-overview.md` | `product-brief.md` 재구성 |
| `01-architecture.md` | `architecture-sketch.md` 정식 확장 |
| `02-design-system.md` | `design-direction.md` + `approved-mockups/` 시스템화 |
| `03-ux-flows.md` | `approved-mockups/` + `product-brief.md` 플로우 확장 |
| `04-data-model.md` | `architecture-sketch.md` + `product-brief.md` 엔티티 도출 |
| `05-auth-rbac.md` | `product-brief.md` (사용자 역할) + `architecture-sketch.md` |
| `06-workflow-map.md` | `product-brief.md` + `architecture-sketch.md` |
| `07-infrastructure.md` | `infrastructure-plan.md` + `environment-check.md` 형식화 |
| `99-implementation-plan.md` | 위 모두 종합 |

### Stage 2a: Draft Generation

- 각 문서를 **1 session = 1 doc** 원칙으로 작성
- 8 sessions (또는 session-plan에 따라 조정)
- 각 세션은 `superpowers:brainstorming`의 **autonomous 변형** 또는 단순 문서 생성 프롬프트로 실행
- 출력: `{doc}.md` (draft)

### Stage 2b: Design Forging

- 각 draft 문서를 `design-forge-batch`가 담금질
- **담금질 구성 (기본):**
  - **1단계 — 개별 담금질:** 각 문서를 독립 세션에서 담금질 (관점별 깊이 확보). 9개 세션.
  - **2단계 — 쌍(pair) 담금질:** 강한 의존 관계가 있는 문서 쌍을 함께 담금질하여 문서 간 모순 탐지. 모든 조합이 아니라 O(N) 수준으로 제한:
    - `03-data-model` ↔ `05-auth-rbac` (엔티티·권한 일관성)
    - `01-architecture` ↔ `06-workflow-map` (모듈 경계·플로우 일관성)
    - `02-design-system` ↔ `03-ux-flows` (디자인·화면 일관성)
    - `99-implementation-plan` ↔ `01-architecture` (구현·모듈 경계 일관성)
    - `07-infrastructure` ↔ `04-data-model` (DB 설정·스키마 일관성)
    - `07-infrastructure` ↔ `05-auth-rbac` (외부 OAuth·인증 방식 일관성)
    - `07-infrastructure` ↔ `99-implementation-plan` (인프라 준비·구현 순서 일관성)
- 출력: `{doc}-agreed.md` + 센티널 마커
- 통합 검증(9종 모두 한 세션 로드)은 **하지 않는다** — 컨텍스트 부담이 크고 쌍 담금질로 대체 가능

### 01-architecture.md가 뼈대

**가장 중요한 문서.** 반드시 다음을 명시:

- 모듈 목록과 책임 범위 (한 줄 설명 + 상세)
- 모듈 간 의존성 방향 (단방향 DAG, 순환 금지)
- 모듈 간 인터페이스 (API shape, 이벤트, 데이터 구조)
- 각 모듈의 blast radius (버그 발생 시 영향 범위)
- **태스크 분할 규칙:** 한 태스크는 한 모듈 내부 작업만. 모듈 경계를 넘지 않음.

---

## Stage 3: Task Split (Auto)

### 입력

- `99-implementation-plan-agreed.md`
- `01-architecture-agreed.md`

### 처리

- 구현 계획을 **모듈 경계를 따라 분할**
- 한 태스크 = 한 모듈 내부의 일관된 작업 단위
- 태스크 간 의존성 추출
- 각 태스크에 대해:
  - `t{NN}.md` (태스크 상세 — 목적, 변경 대상 파일, 접근 방법, 완료 조건)
  - 모듈 소속 명시
  - 의존 태스크 명시

### 출력

```
docs/forge/{project}/
├── plan.md              # 전체 워크플로우 안내도 (모듈 목록 + 태스크 매핑)
├── t01.md
├── t02.md
├── ...
└── tN.md
```

### 핵심 제약

**태스크 분할 시 `01-architecture-agreed.md`의 모듈 경계를 절대 위반하지 않는다.** 이 제약이 fault isolation을 보장한다. 분할 결과는 Stage 3 종료 시 `session-planner`가 재평가하여 Stage 4, 5의 세션 수를 확정한다.

---

## Stage 4: Task Forging (Auto)

### 처리

- 각 태스크 문서(`t{NN}.md`)에 대해 `task-forge-batch` 실행
- `context` = Intake 번들 + 설계 패키지 9종 agreed
- 각 태스크가 별도 세션에서 담금질
- 출력: `t{NN}-agreed.md` + 센티널 마커

### 왜 UPFRONT 담금질인가

- 설계 패키지가 충실하므로 태스크 간 drift 위험 낮음
- 모든 태스크 계획이 구현 전에 확정되어 Stage 5는 순수 실행
- Stage 5 도중 담금질 실패로 인한 중단 없음
- 재실행 편의성: 구현만 다시 돌릴 수 있음

### 재평가

Stage 4 종료 후, 담금질에서 드러난 복잡도 변화를 반영하여 Stage 5의 세션 분할을 갱신.

---

## Stage 4.5: Pre-Implementation Preflight (Auto)

태스크 수준의 **정확한** 환경 검증. Stage 1e-3은 워크플로우 시작 시 개략적 검증이고, Stage 4.5는 "바로 지금 이 태스크를 시작하기 전에 필요한 것이 다 준비되어 있는가"를 확인한다.

### 처리

각 태스크 `t{NN}-agreed.md`에 대해:

1. **필요 리소스 추출** — 태스크 문서에서 다음을 자동 추출:
   - 접근하는 외부 서비스 (예: Stripe API, SendGrid)
   - 필요한 env vars (예: `STRIPE_SECRET_KEY`)
   - 필요한 DB 테이블/마이그레이션 (선행 태스크로부터)
   - 필요한 파이썬 패키지

2. **리소스 준비 확인:**
   - env vars: `.env`에 존재 + 값이 placeholder 아님
   - 외부 서비스: (선택) ping 또는 auth check
   - DB 상태: 선행 태스크 migration이 적용되었는가
   - 패키지: `uv.lock`에 등록되어 있는가

3. **Stage 1e-3 재실행 (light):**
   - 포트 점유 재확인 (중간에 뭔가 생겼을 수 있음)
   - 좀비 재스캔

4. **판정:**
   - 모두 OK → 태스크를 Stage 5 큐에 등록
   - 리소스 missing → 해당 태스크 **skip**, 나머지 태스크 진행 + 리포트
   - 환경 전체 문제 (DB 죽음 등) → 전체 Stage 5 **abort** + 사용자 알림

### 출력

`docs/forge/{project}/preflight-report.md` — 태스크별 준비 상태 스냅샷 + skip된 태스크 목록 + 사후 조치 가이드

---

## Stage 5: Implementation (Auto)

### 처리

- `impl-forge-batch`가 Stage 4.5를 통과한 각 태스크에 대해:
  - 1 session: 구현 (subagent-driven-development 패턴)
  - 1 session: 구현 점검 (impl-check)
- 의존성 순서 준수
- 실패 전파 원칙 (상위 실패 → 하위 skip)
- 각 태스크 완료 시 git commit

### `impl-forge-batch` vs 기존 `plan-forge-batch`

`impl-forge-batch`는 기존 `plan-forge-batch`의 **복사본**이다. 차이:

- 담금질 단계 제거 (태스크는 이미 `*-agreed.md` 상태로 들어옴)
- 구현 + 점검만 수행
- 엔진은 `_forge-batch-engine`을 공유

기존 `plan-forge-batch`는 유지되어 담금질-포함 배치가 필요한 다른 워크플로우에서 사용 가능. 충분히 검증된 후 삭제 여부 결정.

---

## Gate: Pre-Deploy Confirm (Human)

- 1-click y/n
- 타임아웃: 24시간 (기본). 초과 시 워크플로우 일시정지, 사용자 재개 대기
- 승인 시 Stage 6 진행
- 거부 시 워크플로우 종료, 사용자에게 "언제든 재개 가능" 안내

---

## Stage 6: Deploy (Auto)

- `./deploy.sh` 실행 (1 session)
- 파이프라인: check_migrations → test → save → backup_db → build → validate → deploy
- 실패 시 abort, 사용자에게 보고

---

## Skill Architecture

### Layer Diagram

```
┌───────────────────────────────────────────────────────┐
│ taste-to-ship (tts)  ⭐                               │  ← Orchestrator
│ · Stage 1~6 체이닝 + Gate 관리                        │
│ · trigger aliases: taste-to-ship, tts, /tts           │
└───────────────┬───────────────────────────────────────┘
                │ invokes
   ┌────────────┼──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
   ↓            ↓          ↓          ↓          ↓          ↓          ↓          ↓
┌────────┐ ┌──────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│office- │ │design-   │ │ui-mockup│ │brain-   │ │env-     │ │session- │ │design-  │ │task-    │
│hours   │ │consultation│ │(upgr.)  │ │storming │ │readiness│ │planner  │ │forge-   │ │forge-   │
│        │ │          │ │         │ │         │ │(Stage 1e)│ │         │ │batch    │ │batch    │
└────────┘ └──────────┘ └─────────┘ └─────────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
  Stage 1a   Stage 1b    Stage 1c    Stage 1d      Stage 1e    Stage 1.5   Stage 2b    Stage 4
                                                      │           │           │           │
                                           ┌──────────┴──────┐    │           │           │
                                           ↓                 ↓    ↓           ↓           ↓
                                     ┌──────────┐  ┌─────────────────────────────────────┐
                                     │task-     │  │ _forge-batch-engine  ⭐              │  ← Shared lib
                                     │preflight │  │ · session-chaining                  │
                                     │          │  │ · progress-tracking                 │
                                     └────┬─────┘  │ · watchdog                          │
                                       Stage 4.5   │ · sentinel marker                   │
                                          │        │ · dependency analysis               │
                                          ↓        └──────────────────┬──────────────────┘
                                     ┌─────────┐                       │
                                     │impl-    │                       │
                                     │forge-   │ ←─────────────────────┘
                                     │batch    │
                                     └────┬────┘
                                       Stage 5
                                          │
                                          ↓
                                    ┌──────────┐
                                    │plan-forge│  ← 기존 유지
                                    └──────────┘
```

### 새 스킬 목록

| 스킬 | 역할 | 기반 |
|---|---|---|
| `taste-to-ship` (tts) | 최상위 워크플로우 오케스트레이터 | 신규 작성 |
| `_forge-batch-engine` | 세션 체이닝·진행 추적·watchdog 공유 라이브러리 | 기존 `plan-forge-batch`에서 추출 |
| `env-readiness` | Stage 1e 로직: static check + zombie check + bootstrap(new) or verify(existing) | 신규 작성 |
| `session-planner` | Intake → session-plan.json 변환 + 재평가 + light drift check | 신규 작성 |
| `design-forge-batch` | 설계 문서 담금질만 (구현·점검 제거). 대상: 설계 패키지 9종 | `plan-forge-batch` 복사 → 구현·점검 제거 |
| `task-forge-batch` | 태스크 담금질만 (구현·점검 제거). 대상: t01~tN, UPFRONT 모드 | `plan-forge-batch` 복사 → 구현·점검 제거 |
| `task-preflight` | Stage 4.5 로직: 태스크별 리소스/환경 확인 | 신규 작성 |
| `impl-forge-batch` | 구현 + 점검만 (담금질 제거). 입력: 이미 agreed된 태스크 | `plan-forge-batch` 복사 → 담금질 제거 |

### 업그레이드 대상

| 스킬 | 변경 |
|---|---|
| `ui-mockup` | Gemini Nano Banana Pro 모델 도입 + design-shotgun의 핵심 기능 포팅 (병렬 생성, evolve, serve HTTP 피드백, iterate) |

### 기존 유지

| 스킬 | 상태 |
|---|---|
| `plan-forge` | 유지 (각 batch 스킬이 내부적으로 dispatch) |
| `plan-forge-batch` | 유지 (병존, 나중에 삭제 검토) |
| `office-hours` | 유지 (Stage 1a에서 사용) |
| `design-consultation` | 유지 (Stage 1b에서 사용) |
| `superpowers:brainstorming` | 유지 (Stage 1d에서 사용) |

### 트리거 키워드

`taste-to-ship` 스킬의 `description` 필드에 다음을 모두 포함:

- `taste-to-ship` (정식)
- `tts` (발음 가능한 alias, 원래 text-to-speech 약자지만 여기서는 taste-to-ship)
- `/tts` (slash command 형식)
- `풀 워크플로우 시작` (한국어 자연어)
- `아이디어부터 배포까지` (한국어 자연어)

---

## State Management

### 진실 소스 우선순위

| 우선순위 | 파일 | 용도 |
|---|---|---|
| 1 | 센티널 마커 (agreed 문서 끝 줄) | 완료 판정 |
| 2 | `*-agreed.md` | 합의된 최종본 |
| 3 | `*-rulings.md` | 담금질 판결 (사람이 읽는 서사) |
| 4 | `debate-log.json` | 라운드별 토론 기록 |
| 5 | `forge-progress.json` | 배치 진행 요약 (캐시) |
| 6 | `session-plan.json` | 세션 분할 계획 (캐시) |
| 7 | `workflow-progress.json` | 워크플로우 전체 진행 상태 (캐시) |
| 8 | `environment-check.md`, `preflight-report.md` | 환경 검사 스냅샷 |
| 9 | `zombie-cleanup-log.md` | 파괴적 동작 이력 (감사 추적) |

**git 커밋이 진실 소스의 최후 방어선:** 모든 Stage 종료 시 git commit. 캐시 파일과 git 상태가 충돌하면 git HEAD를 신뢰.

캐시와 진실 소스가 불일치하면 진실 소스를 신뢰.

### 디렉토리 레이아웃

```
docs/
├── intake/{YYYYMMDD}-{project}/        ← Stage 1 산출물
│   ├── product-brief.md
│   ├── design-direction.md
│   ├── design-approved.md
│   ├── approved-mockups/
│   ├── architecture-sketch.md
│   ├── infrastructure-plan.md
│   ├── environment-check.md
│   ├── zombie-cleanup-log.md
│   └── mode.txt
├── designs/{YYYYMMDD}-{project}/       ← Stage 2 산출물 (9 docs)
│   ├── 00-overview.md ~ 07-infrastructure.md
│   ├── 99-implementation-plan.md
│   └── debate/ (담금질 로그)
└── forge/{project}/                    ← Stage 3~5 산출물
    ├── plan.md
    ├── session-plan.json
    ├── workflow-progress.json
    ├── forge-progress.json
    ├── preflight-report.md             ← Stage 4.5 산출물
    ├── logs/
    │   └── journal.log
    ├── t01.md, t01-agreed.md, debate/
    ├── t02.md, t02-agreed.md, debate/
    └── ...
```

**New mode 추가 산출물 (프로젝트 루트):**

```
.                                        ← Stage 1e-4 (new mode) 부트스트랩 결과
├── .git/
├── .gitignore
├── .env.example, .env
├── pyproject.toml, uv.lock
├── manage.py
├── config/                              ← Django settings 루트
├── docker-compose.yml
├── dev.sh
├── deploy.sh (template)
├── CLAUDE.md (template)
├── README.md
├── package.json, tailwind.config.js (if Tailwind)
└── docs/ (intake/designs/forge 들어갈 공간)
```

### Git Commit 정책

- 각 Stage 종료 시 git commit (자동)
- 커밋 메시지 규칙: `tts({stage}/{unit}): {status}`
- 예: `tts(1a/product-brief): approved`, `tts(2.2/04-data-model): forged`, `tts(5/t03): implemented`
- 메모리의 "git commit은 전체가 기본" 원칙 준수

---

## Failure Handling

### 실패 전파 원칙

`plan-forge-batch`와 동일:
- 상위 Stage 실패 → 하위 Stage skip
- 같은 Stage 내 의존성 있는 unit 실패 → 후속 unit skip
- 독립 unit은 실패와 무관하게 계속

### Resume 지점

| 실패 지점 | Resume 방법 |
|---|---|
| Stage 1 sub-stage 중단 | 다음 실행 시 해당 sub-stage부터 재개 (intake 커밋 기준) |
| Stage 1e 환경 검증 실패 | 사용자가 환경 수정 후 재실행. 체크리스트의 미통과 항목부터 재검사 |
| Stage 1e-4 bootstrap 중 실패 (new mode) | 부분 생성 상태 롤백 (`git clean -fdx` 조건부) 후 재시도 |
| Stage 1.5 drift 감지 | 자동 중단. 사용자에게 환경 재정리 요청 후 재실행 |
| Stage 2 draft 중 실패 | 실패한 문서만 재생성 |
| Stage 2 forge 중 실패 | `*-agreed.md` 미존재 문서만 재담금질 |
| Stage 3 split 실패 | 전체 재실행 (빠름) |
| Stage 4 forge 중 실패 | 실패한 태스크만 재담금질 |
| Stage 4.5 preflight에서 태스크 리소스 부족 | 해당 태스크 skip, 나머지 진행. preflight-report.md로 사후 조치 가이드 |
| Stage 5 구현 중 실패 | 실패한 태스크부터 재개 (이전 태스크는 git commit으로 고정) |
| Gate 거부 | 워크플로우 일시정지, 사용자 명령으로 재개 |
| Stage 6 deploy 실패 | `./deploy.sh` 단계별 실패 지점 리포트, 수동 복구 후 재실행 |

### Watchdog 개입

- hang 세션 감지: journal mtime 고정 + CPU 낮음 → kill + respawn (최대 3회)
- 재시도 초과 시: 해당 unit을 "blocked"로 기록, 사용자 개입 요청

---

## Migration Path

### Phase 1: 엔진 추출

1. `_forge-batch-engine/` 디렉토리 생성
2. 기존 `plan-forge-batch/`에서 세션 체이닝·watchdog·progress-tracking 코드 추출
3. 기존 `plan-forge-batch`는 건드리지 않음 (라이브러리를 import하지도 않음, 독립 유지)

### Phase 2: 배치 스킬 3종 생성

4. `design-forge-batch/` 생성 (plan-forge-batch 복사 + 구현·점검 제거)
5. `task-forge-batch/` 생성 (plan-forge-batch 복사 + 구현·점검 제거 + UPFRONT 모드)
6. `impl-forge-batch/` 생성 (plan-forge-batch 복사 + 담금질 제거)
7. 각 스킬은 `_forge-batch-engine`을 import

### Phase 3: 보조 스킬

8. `env-readiness/` 생성 (Stage 1e 로직: static check + zombie check + bootstrap/verify)
9. `task-preflight/` 생성 (Stage 4.5 로직)
10. `session-planner/` 생성 (Stage 1.5 로직 + 재평가 + light drift check)
11. `ui-mockup` 업그레이드 (Gemini Nano Banana Pro + design-shotgun 기능 포팅: parallel generation, evolve, serve HTTP feedback, iterate)

### Phase 4: 오케스트레이터

12. `taste-to-ship/` (tts) 생성
13. Stage 1~6 체이닝 구현 (Stage 1e 모드 감지 분기 포함)
14. Gate 관리 구현
15. 트리거 키워드 등록 (`taste-to-ship`, `tts`, `/tts`, `풀 워크플로우 시작`, `아이디어부터 배포까지`)
16. New mode skeleton 템플릿 작성 (synco의 구조를 참고한 Django + HTMX + Postgres + Tailwind 템플릿)

### Phase 5: 검증 (2가지 경로)

17. **Existing 프로젝트 검증** — synco 레포에 작은 기능 추가를 tts로 진행 (e.g., "후보자 북마크 기능")
18. **New 프로젝트 검증** — 빈 디렉토리에서 tts 실행하여 bootstrap + 최소 기능 구현까지 완주 (e.g., "간단한 TODO SaaS")
19. 각 Stage 개별 테스트
20. 실패/resume 시나리오 테스트 (중간에 좀비 발생, 세션 hang, 배치 도중 중단 등)
21. Zombie check 시나리오 테스트 (의도적으로 orphan 생성 후 tts 실행)

### Phase 6: 전환 결정

22. 실제 프로젝트 2~3건 taste-to-ship으로 진행 (existing 2건, new 1건)
23. 안정성 확인
24. 기존 `plan-forge-batch` 삭제 여부 판단 (유지할 수도 있음)

---

## Open Questions

- **Q1.** Stage 2a draft 생성 시 `superpowers:brainstorming`을 그대로 쓸 수 없음 (인터랙티브). autonomous 변형을 만들 것인가, 아니면 단순 문서 생성 프롬프트로 대체할 것인가? → 구현 계획 단계에서 결정.
- **Q2.** 쌍 담금질에서 다루지 않는 조합(예: `04-data-model` ↔ `06-workflow-map`)은 개별 담금질에만 의존하는데, 모순이 있을 경우 어떻게 감지할 것인가? → 현재는 "개별 담금질이 충분히 foot print 넓어야 함"으로 가정. 실사용에서 문제가 발견되면 쌍 조합을 추가.
- **Q3.** Gate 24시간 타임아웃이 적절한가? 주말 고려하면 72시간? → 사용자 설정 가능하게.
- **Q4.** Session planner의 복잡도 추정이 부정확할 때 fallback? → 재평가 지점에서 자동 보정. 그래도 실패 시 사용자에게 "프로젝트 규모가 예상과 다름, 수동 조정 요청" 알림.
- **Q5.** Multi-project 동시 실행 지원? → 현 버전에서는 non-goal. 단일 프로젝트 직렬 실행만.
- **Q6.** `workflow-progress.json` 스키마는 아직 정의되지 않음. → 구현 계획 단계에서 `forge-progress.json`과의 관계와 함께 확정.
- **Q7.** New mode skeleton 템플릿의 관리 방식: 하드코딩 vs 별도 템플릿 레포 vs `cookiecutter` 같은 도구 활용? → 구현 계획 단계에서 결정. 초기에는 synco 구조를 참고한 하드코딩 템플릿으로 시작할 예정.
- **Q8.** Stage 4.5 태스크 리소스 추출이 부정확할 때(예: 태스크 문서가 외부 서비스 언급을 명시하지 않음)? → LLM 기반 추출 + 누락 위험 있음 → 태스크 담금질 시 "필요 리소스" 섹션을 필수화하여 해결.
- **Q9.** New mode에서 기본 Django app 이름·구조 관례는? → `config/`(settings 루트) + `apps/{module}` 패턴. architecture-sketch의 모듈 이름을 그대로 Django app 이름으로 사용.
- **Q10.** Zombie check가 false positive를 낼 경우(사용자 정상 작업 중인 프로세스를 zombie로 오판)? → 절대 자동 kill하지 않음. 항상 사용자 확인 후 조치. 사용자가 "아니, 그건 살려둬"라고 답하면 워크플로우 중단하고 사용자에게 환경 정리 후 재시작 요청.

---

## Appendix: Design Package 문서 상세 스펙

각 문서의 필수 섹션 정의. 담금질 레드팀은 이 섹션들이 모두 채워졌는지 체크한다.

### 00-overview.md

- 제품 이름과 한 줄 정의
- 타겟 사용자 (페르소나)
- 해결하는 문제
- 가치 제안
- 핵심 유스케이스 (3~5)
- 성공 지표 (측정 가능)
- 범위 밖 (Non-goals)

### 01-architecture.md ⭐

- 모듈 목록 (이름 + 1줄 책임)
- 모듈 상세 (각 모듈당: 책임, 주요 엔티티, 의존 모듈, blast radius)
- 의존성 DAG (다이어그램 또는 인접 리스트)
- 모듈 간 인터페이스 (API, 이벤트, 공유 데이터)
- 기술 스택
- **태스크 분할 규칙** (이 섹션은 명시적으로 필수)

### 02-design-system.md

- 브랜드 톤 (intake의 design-direction 재서술)
- 색 팔레트 (primary, accent, neutral, semantic)
- 타이포그래피 (폰트, 크기 스케일, 행간)
- 컴포넌트 라이브러리 (버튼·입력·카드·네비게이션·테이블·모달 등 — intake 승인된 것 기반)
- Spacing scale
- 반응형 breakpoint
- 다크모드 (선택)

### 03-ux-flows.md

- 화면 목록 (intake 승인된 목업 기반)
- 각 화면: 목적, 주요 요소, 인터랙션, 엣지 케이스 (zero state, loading, error, long text)
- 화면 간 플로우 (state diagram or flowchart)
- 주요 사용자 여정 (3~5)

### 04-data-model.md

- 엔티티 목록 + 속성
- 엔티티 관계 (ERD)
- 인덱스 전략
- 제약 (unique, check, FK)
- 마이그레이션 고려사항 (데이터 마이그레이션 vs 스키마 변경 분리)
- 테넌시 모델 (있다면)

### 05-auth-rbac.md

- 인증 방식 (OAuth, magic link, email/password)
- 세션 관리
- 역할 목록 + 권한 매트릭스
- Row-level security 정책 (있다면)
- 테넌시 격리 (있다면)
- 로그인/로그아웃/가입/비밀번호 리셋 플로우

### 06-workflow-map.md

- 핵심 워크플로우 (상태 전이 + 트리거)
- 기능 간 연계 (A → B → C)
- 이벤트/알림 흐름
- 백그라운드 작업 (스케줄, 큐)

### 07-infrastructure.md ⭐

- **Runtime environment**
  - Python 버전 (≥ 3.13)
  - Django 버전 (≥ 5.2)
  - 패키지 매니저 (uv)
  - Node/Tailwind (있다면)
- **Database**
  - 개발 DB 구성 (로컬 Docker Postgres)
  - 운영 DB 구성 (49.247.45.243 or 별도)
  - 접속 문자열 패턴 (환경변수로 주입)
  - 백업·복원 전략
  - 마이그레이션 운영 원칙 (운영 DB 직접 수정 금지)
- **External services**
  - 각 서비스: 역할, credential 취득 방법, 필요한 env vars, fallback 전략
  - 예: `Stripe (결제) — 대시보드에서 키 발급, STRIPE_SECRET_KEY/STRIPE_PUBLISHABLE_KEY, 실패 시 결제 disabled UI`
- **Environment variables (complete list)**
  - 이름, 설명, 필수/선택, 예시값, 적용 환경 (dev/prod/test)
  - 민감도 등급 (secret/config)
- **Secrets management**
  - `.env.prod`, `.secrets/` 위치
  - Git ignore 여부
  - 운영 배포 시 동기화 방법
- **Docker**
  - 개발: `docker-compose.yml` 서비스 (DB, 기타)
  - 운영: `docker-stack-synco.yml` 또는 해당 프로젝트 stack
  - 이미지 빌드 전략
- **Deployment**
  - 배포 대상 서버 (IP, SSH, 접속 방법)
  - 배포 파이프라인 (deploy.sh 단계)
  - 도메인·SSL
  - 롤백 전략
- **CI/CD**
  - 현재 단계: 로컬 deploy.sh 기준
  - 향후 GitHub Actions 등 확장 시 계획
- **Red-team tools**
  - 담금질에 사용할 도구 (codex CLI, gemini CLI, codex API, gemini API, agent)
  - 각 도구의 필요 조건 (바이너리, API 키)
- **Prerequisites checklist (pre-flight)**
  - Stage 1e가 만든 체크리스트의 정식 버전
  - 각 항목: 이름, 확인 방법, 통과 조건, 실패 시 조치
- **Observability**
  - 로깅 전략 (django logging, 구조화 로그)
  - 에러 리포팅 (있다면 Sentry 등)
  - 메트릭/모니터링 (있다면)
- **Zombie & cleanup policy**
  - Stage 1e-3의 검사 항목 목록
  - 각 항목별 자동/수동 조치 원칙

### 99-implementation-plan.md

- 구현 순서 (의존성 기반)
- 모듈별 구현 계획 (각 모듈당: 작업 단위, 파일, 테스트 전략)
- 마일스톤 (optional)
- 초기 데이터 시드 (있다면)
- 배포 준비 (env vars, secrets, 마이그레이션)

---

## 끝.

*이 스펙이 확정되면 `superpowers:writing-plans`로 넘어가 Phase 1~6의 구현 계획을 상세화한다.*
