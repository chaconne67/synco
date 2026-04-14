# Project/Application 재설계 — 프로젝트 상태 체계 재정의

**작성일**: 2026-04-14
**최종 확정일**: 2026-04-14
**최종 확정본**: 👉 **[FINAL-SPEC.md](FINAL-SPEC.md)** ← 구현 시 이 문서를 단일 진실 소스로 사용
**구현계획**: 👉 **[plans/](plans/)** ← Phase별 구현계획 (plan-forge-batch 대상)
**배경**: synco `ProjectStatus` 10-state enum이 실제 헤드헌팅 업무를 적절히 표현하지 못한다는 문제 제기에서 출발. 기준 자료는 Google Drive 공유문서함의 `Search Status.xlsx` (컨설턴트 6명, 313개 프로젝트, ~6,000건 후보자 이력).

> ⚠️ **중요**: 01~07 문서는 논의 과정의 히스토리입니다. 논의 후반부에 설계 방향이 크게 바뀌어, 2-phase + ActionItem 중심 모델로 재정의되었습니다. 구현은 반드시 [FINAL-SPEC.md](FINAL-SPEC.md)와 [plans/](plans/) 하위 Phase별 구현계획을 참조하십시오.

## 최종 확정 요지 (한 줄)

**synco는 상태 추적 도구가 아니라 할 일 관리 도구이다.** Project는 `searching / screening` 2-phase, Application은 순수 매칭 객체, 실제 업무는 **ActionItem**이라는 1급 개념(할 일 단위, 마감 + 결과 + 후속 체인)이 담당한다. 자세한 내용은 [FINAL-SPEC.md](FINAL-SPEC.md) 참조.

---

## 핵심 통찰 3가지

1. **상태는 Project가 아니라 Project-Candidate 관계(엣지)에 존재한다.**  
   한 프로젝트는 여러 후보자를 가지고, 한 후보자는 여러 프로젝트에 엮인다 (M:N). 각 엮임마다 고유한 상태가 있고, 이를 `Project.status` 단일 enum으로 끌어올리려 한 게 근본 오류.

2. **Project는 매크로 라이프사이클, Application은 마이크로 라이프사이클을 가진다.**  
   Project Phase는 "지금 이 프로젝트의 작업 포커스가 어디인가"를 나타내고, Application Stage는 "이 후보자가 이 프로젝트에서 어느 단계에 있는가"를 나타낸다. 둘은 디커플링되어야 한다.

3. **Project Phase는 "가장 이른 미해결 단계"로 자동 파생된다.**  
   컨설턴트는 Application만 관리하고, Project Phase는 시스템이 집계해서 계산한다. 이 한 규칙이 forward/backward 모든 시나리오를 자연스럽게 해결한다.

---

## 결정 사항 (확정)

| 항목 | 결정 | 비고 |
|---|---|---|
| Project Phase 개수 | **5개 + CLOSED** | SEARCHING → PRE_MEETING → SUBMITTED → INTERVIEWING → CLOSED |
| Application Stage 개수 | **6 활성 + DROPPED** | SOURCED → SCREENED → PRE_MEETING → RECOMMENDED → CLIENT_INTERVIEWING → HIRED + DROPPED |
| Project Phase 계산 | **자동 파생 (earliest pending)** | 컨설턴트는 직접 조작하지 않음 |
| Phase DB 캐싱 | **DB 컬럼으로 캐시** | Application 변경 시 signal로 재계산. 쿼리 성능용 |
| Round 필드 | **사용하지 않음** | 대신 `ProjectEvent` 타임라인으로 히스토리 추적 |
| CloseReason | **SUCCESS / NO_HIRE 2가지만** | 취소/보류/마감 모두 NO_HIRE로 흡수 |
| `Offer` 모델 | **제거** | 현실에서 의미 없음 (협상할 게 없음, 사장 몫) |
| `Project.status` 필드 | **제거** | `phase` + `closed_at` + `close_reason`으로 교체 |
| `PENDING_APPROVAL` | **제거 (상태에서)** | 이미 존재하는 `ProjectApproval` 모델로 분리됨 |
| `ON_HOLD` | **제거** | 헤드헌터 관점에서 의미 없음. 클라이언트 보류는 소프트 리젝션이므로 NO_HIRE |
| `NEW` | **제거** | 현실상 NEW ≡ SEARCHING |
| `NEGOTIATING` | **제거** | 데이터상 언급 6건, 의미 없음 |
| 기존 데이터 마이그레이션 | **필요 없음** | 로컬/운영 DB 모두 프로젝트 데이터 0건 (클린 슬레이트) |

---

## 문서 색인

이 디렉터리의 파일들을 순서대로 읽으면 재설계의 전체 맥락을 파악할 수 있습니다.

| # | 파일 | 내용 |
|---|---|---|
| 01 | [excel-analysis.md](01-excel-analysis.md) | 엑셀 분석 결과 — 컬럼 실제 사용, 컨설턴트별 스타일, Funnel 실측치 |
| 02 | [problem-with-current.md](02-problem-with-current.md) | 현재 synco 10-state enum의 문제점과 구조적 결함 |
| 03 | [two-layer-model.md](03-two-layer-model.md) | 2-레이어 모델 컨셉 (Project Phase × Application Stage) |
| 04 | [phase-derivation-rule.md](04-phase-derivation-rule.md) | "가장 이른 미해결 단계" 파생 규칙과 시나리오 검증 |
| 05 | [data-model.md](05-data-model.md) | 새 모델 정의 (Application, ProjectEvent, 수정된 Project) |
| 06 | [ui-design.md](06-ui-design.md) | 3-레벨 뷰 (칸반 / 프로젝트 상세 / 후보자 상세) UI 설계 |
| 07 | [implementation-plan.md](07-implementation-plan.md) | 단계별 구현 계획과 영향 범위 |

---

## 다음 세션 재개 가이드

다음 세션에서 이 작업을 이어받을 때:

1. **이 README와 [07-implementation-plan.md](07-implementation-plan.md)를 먼저 읽어** 전체 그림과 작업 단계를 파악한다.
2. **실제 코드 작업을 시작하기 전에** 설계 문서 내용이 여전히 유효한지 사장님과 확인 (논의가 길었으므로 약간의 정리가 필요할 수 있음).
3. 코드 작업은 범위가 크므로 `plan-forge` 또는 `impl-forge-batch` 스킬로 쪼개서 실행하는 것을 권장한다.
4. **로컬 DB 초기화**가 필요하다: `rm db.sqlite3 && uv run python manage.py migrate` (혹시 sqlite를 쓰고 있다면). Docker 개발 DB는 volume 제거 후 재생성.

---

## 관련 자료

- 기준 엑셀: `Search Status.xlsx` (Google Drive file_id `1hOTakXTuCj126JCuKAxqcEKToemtFcpJ`)
- 로컬 복사본: `/tmp/project_sheet.xlsx` (Drive API 다운로드)
- 1차 추출 CSV: `/tmp/project_status_extracted.csv` (313개 프로젝트 상태 추론 결과)
- 기존 모델: `projects/models.py:14-25` (`ProjectStatus` enum)
- OAuth 재인증 스크립트: `/tmp/google_reauth.py` (향후 시트 재다운로드용)
