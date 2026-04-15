# Archive — 과거 기록

이 폴더는 synco 기획 과정에서 쌓인 **역사적 자료**의 보관소이다. 삭제되지 않고 참조용으로 남아있으나, 현재 시점의 단일 진실 소스는 [../master/](../master/) 의 마스터 3종이다.

> **충돌 시 우선순위**: `docs/master/*.md` > `docs/design-system.md` + `docs/designs/` + `assets/ui-sample/` > `docs/archive/*`

## 폴더별 내용

| 폴더 | 원래 역할 | 현재 상태 | 대체 문서 |
|---|---|---|---|
| [plans/](plans/) | Phase 기획서 P01~P19, 사업계획서, 온보딩 플랜 | **마스터에 녹음됨** | `master/01-business-plan.md` (business-plan-synco.md 원본), `master/02-work-process.md` (P01~P13 녹음), `master/03-engineering-spec.md` (모델·URL) |
| [designs/](designs/) | 과거 UI 기획: 대시보드 인터랙션 플랜, Project/Application 재설계(FINAL-SPEC + 01~07 + plans/), 메인 대시보드 초안, 디자인 감사, RBAC 온보딩 플랜 | **마스터에 녹음됨** | `master/02-work-process.md` 6장·7.1절 (3층 모델, 대시보드 인터랙션), `master/03-engineering-spec.md` 5.4절 (모델 스펙) |
| [forge/](forge/) | plan-forge/impl-forge 담금질 및 구현 실행 추적 | 실행 히스토리로 보존 | 현재 코드 상태 = `master/03-engineering-spec.md` |
| [inspection/](inspection/) | 파이프라인·E2E·멀티에이전트 점검 보고서 (2026-03~04) | 과거 특정 시점 상태 기록 | 현재 상태는 `master/03-engineering-spec.md` 12장 |
| [reports/](reports/) | 2026-04-03 프로젝트 변경 리포트 | 시점 기록 | `master/03-engineering-spec.md` |
| [research/](research/) | AI 자동화 대상 산업, 한국 대학 랭킹 조사 | 마스터 데이터 시드로 반영됨 | `clients/management/commands/load_reference_data.py` |
| [reviews/](reviews/) | UI/UX·파이프라인·아키텍처·런타임 안전성 리뷰 | 과거 개선 히스토리 | `master/03-engineering-spec.md` |
| [superpowers/](superpowers/) | resume 파싱/voice 검색/integrity 파이프라인/TTS 스펙 | 특수 기능 초기 플랜 | 실제 구현 = `master/03-engineering-spec.md` |
| [presentations/](presentations/) | (비어있음) | — | — |

## plans/ 서브 구조 요약 (가장 큰 아카이브)

- [plans/business-plan-synco.md](plans/business-plan-synco.md) — **마스터 01의 원본.** 수정 시 마스터를 고치고 이 파일은 그대로 둔다.
- [plans/headhunting-workflow/](plans/headhunting-workflow/) — P01~P19 헤드헌팅 워크플로우 설계서
  - `README.md` — P 시리즈 지도
  - `design.md` — 72K 메가 설계서 (워크플로우 전체 상세)
  - `P01-models-and-app-foundation.md` ~ `P19-chrome-extension.md` — 각 단계 기획
- [plans/headhunting-onboarding/](plans/headhunting-onboarding/) — 온보딩/RBAC 플로우 설계
- [plans/archive/](plans/archive/) — **기존에 이미 아카이브된 것들** (data-extraction, resume-processing, tooling, 디자인 오피스아워 등)
- [plans/20260413-rbac-staff-ceo-login.md](plans/20260413-rbac-staff-ceo-login.md) — RBAC 최종 플랜

## forge/ 서브 구조 요약

| 서브 | 내용 |
|---|---|
| `forge/headhunting-workflow/` | P01~P19 담금질 과정 (debate 폴더 포함) |
| `forge/headhunting-onboarding/` | 온보딩 위상 담금질 |
| `forge/project-application-redesign/` | FINAL-SPEC 재설계 구현 추적 |
| `forge/forge-batch-remote-execution.md` | plan-forge-batch 자동화 설계 |

## 왜 여기 있는가

기획이 여러 차례 바뀌었고 그 과정에서 다음 세 가지 시대층이 공존하게 되었다:

1. **과거 (voice-first)** — 음성 채팅 중심 기획. 지금은 레거시로 격하됨
2. **중간 (plans/ 워크플로우)** — P01~P19 phase 기반 기획
3. **최신 (대시보드 + FINAL-SPEC)** — `assets/ui-sample/` 목업을 단일 진실 소스로 하는 대시보드-first 재정리

마스터 3종은 세 시대층을 모두 녹여 **최신 방향**으로 정렬된 내용만 담고 있다. 이 폴더의 파일들은 당시의 결정 맥락을 이해하고 싶을 때만 들여다본다.

## 주의

- 이 폴더의 파일에 **새 내용을 추가하지 않는다.** 새 기획/결정은 마스터 문서를 업데이트한다.
- 이 폴더의 파일을 **참조하는 링크를 마스터에서 만들지 않는다.** 마스터는 자립적이어야 한다.
- 필요하면 폴더 전체를 삭제해도 마스터 3종과 코드의 진실은 유지된다 (git 히스토리에 남음).
