# 03. 2-레이어 모델 — Project Phase × Application Stage

**핵심 개념**: Project와 Application은 서로 다른 라이프사이클을 가지며, 이 두 축은 디커플링되어야 한다.

---

## 1. 왜 2-레이어인가

Project와 Candidate는 **many-to-many** 관계다:
- 한 Project에 여러 Candidate가 엮인다
- 한 Candidate는 여러 Project에 엮인다
- 각 (Project, Candidate) 엣지가 고유한 상태를 가진다

Project 자체의 라이프사이클도 존재하지만, 그것은 Candidate들의 상태를 **집계한 매크로 상태**다. 이 둘을 혼동하면 안 된다.

```
┌─────────────────────────────────────────────────────────────┐
│  Project Phase (매크로) — 이 프로젝트가 지금 어느 단계인가  │
│                                                               │
│   SEARCHING → PRE_MEETING → SUBMITTED → INTERVIEWING         │
│                                                → CLOSED     │
│      ↑ 파생 (auto-derived from applications)                │
│                                                               │
│  ┌───┴─────────────────────────────────────────────────┐    │
│  │ Application Stage (마이크로) — 이 후보자는 어디에   │    │
│  │                                                       │    │
│  │ SOURCED → SCREENED → PRE_MEETING → RECOMMENDED       │    │
│  │         → CLIENT_INTERVIEWING → HIRED / DROPPED      │    │
│  └───────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Project Phase — 5단계 + 종료

사장님이 설명하신 프로젝트 업무 플로우 그대로:

| # | Phase | 코드 | 의미 | 산출물 (게이트) |
|---|---|---|---|---|
| 1 | **서칭** | `SEARCHING` | 클라이언트 의뢰 직후. 후보자 발굴 단계 (프로젝트가 가장 오래 머무는 곳) | **1차 후보자 리스트** — 사전미팅할 후보 명단 |
| 2 | **사전미팅** | `PRE_MEETING` | 컨설턴트 핵심 업무 — 대면/화상 미팅으로 이력·인성·외모·말투 정성 평가 | **미팅 기록** (녹음/녹취/정리) + **최종 추천 리스트** |
| 3 | **제출/검토** | `SUBMITTED` | 최종 후보 이력서를 클라이언트에 전달, 서류 심사 대기 | **클라이언트 피드백** — 어떤 후보자를 면접할지 선별 |
| 4 | **면접** | `INTERVIEWING` | 클라이언트 면접 진행 중 (1차/2차/최종) | **면접 결과** — 입사 결정 또는 전원 탈락 |
| 5 | **종료** | `CLOSED` | `close_reason`으로 SUCCESS / NO_HIRE 구분 | — |

```python
class ProjectPhase(models.TextChoices):
    SEARCHING    = "searching",    "서칭"
    PRE_MEETING  = "pre_meeting",  "사전미팅"
    SUBMITTED    = "submitted",    "제출/검토"
    INTERVIEWING = "interviewing", "면접"
    CLOSED       = "closed",       "종료"


class CloseReason(models.TextChoices):
    SUCCESS = "success", "성공 (입사)"
    NO_HIRE = "no_hire", "실패 (입사자 없음)"
```

**종료 사유는 두 가지만**. 취소/보류/마감 모두 `NO_HIRE`로 흡수. 재의뢰는 새 프로젝트로 생성.

---

## 3. Application Stage — 6단계 + 드롭

각 (Project, Candidate) 엣지가 따라가는 마이크로 라이프사이클.

| # | Stage | 코드 | 의미 | 다음으로 전진 조건 |
|---|---|---|---|---|
| 1 | **발굴** | `SOURCED` | 컨설턴트가 이 후보자를 프로젝트 대상으로 등록 | 이력서 검토 완료 |
| 2 | **검토** | `SCREENED` | 이력서·커리어로 1차 판단 통과. 사전미팅 대상 후보 | 사전미팅 완료 |
| 3 | **사전미팅** | `PRE_MEETING` | 컨설턴트가 직접 만나서 정성 평가 완료 | 클라이언트 제출 결정 |
| 4 | **추천** | `RECOMMENDED` | 클라이언트에 이력서 제출됨, 피드백 대기 | 면접 대상자로 선정 |
| 5 | **면접** | `CLIENT_INTERVIEWING` | 클라이언트 면접 진행 중 (회차 정보는 Interview 서브모델) | 입사 확정 |
| 6 | **입사** | `HIRED` | 합격 + 실제 입사 | — (종료) |
| — | **드롭** | `DROPPED` | 어느 단계에서든 탈락·철회·포기. `drop_reason` 필수 | — (종료) |

```python
class ApplicationStage(models.TextChoices):
    SOURCED             = "sourced",             "발굴"
    SCREENED            = "screened",            "검토"
    PRE_MEETING         = "pre_meeting",         "사전미팅"
    RECOMMENDED         = "recommended",         "추천"
    CLIENT_INTERVIEWING = "client_interviewing", "면접"
    HIRED               = "hired",               "입사"
    DROPPED             = "dropped",             "드롭"
```

---

## 4. DropReason — 김현정 태그 체계 기반

엑셀에서 이미 가장 체계적으로 사용되고 있는 김현정의 드롭 사유 분류를 그대로 채택.

```python
class DropReason(models.TextChoices):
    # 후보자 측 사유
    CAND_NOT_INTERESTED = "cand_not_interested", "후보자_이직의사없음"
    CAND_WITHDREW       = "cand_withdrew",       "후보자_철회포기"
    CAND_NO_REPLY       = "cand_no_reply",       "후보자_연락두절"
    CAND_LOCATION       = "cand_location",       "후보자_근무지조건"
    CAND_SALARY         = "cand_salary",         "후보자_처우조건"
    CAND_GOT_OTHER_JOB  = "cand_got_other_job",  "후보자_타사입사"
    CAND_DECLINED_OFFER = "cand_declined_offer", "후보자_입사포기"

    # 컨설턴트 판정
    UNFIT_CAREER    = "unfit_career",    "부적합_경력"
    UNFIT_INDUSTRY  = "unfit_industry",  "부적합_산업"
    UNFIT_EDUCATION = "unfit_education", "부적합_학력"
    UNFIT_JOB_FIT   = "unfit_job_fit",   "부적합_직무"
    UNFIT_OTHER     = "unfit_other",     "부적합_기타"

    # 클라이언트 측
    CLIENT_REJECT_DOC       = "client_reject_doc",       "클라이언트_서류탈락"
    CLIENT_REJECT_INTERVIEW = "client_reject_interview", "클라이언트_면접탈락"
    CLIENT_CLOSED_POSITION  = "client_closed_position",  "클라이언트_포지션마감"
    CLIENT_CANCELLED        = "client_cancelled",        "클라이언트_진행취소"

    # 중복/행정
    DUPLICATE_OTHER_FIRM = "duplicate_other_firm", "타서치펌_중복지원"
```

필요시 이후 `other_reason_text` 자유 텍스트 필드를 추가해서 "기타" 사유를 구체화할 수 있다.

---

## 5. 두 레이어의 상호작용

### 원칙 — 컨설턴트는 Application만 관리, Phase는 시스템이 파생

- 컨설턴트의 모든 행동은 **Application 단위**로 일어난다:
  - 새 후보자 추가 (= Application 생성, stage=SOURCED)
  - 다음 단계로 promote (= Application.stage 전진)
  - 드롭 (= Application.stage = DROPPED + drop_reason)

- **Project.phase는 Application 집계의 부산물**로 자동 계산된다. 컨설턴트가 직접 조작하지 않는다.

이 분리가 다음을 보장한다:
1. Phase stale 상태가 발생하지 않음 (Application 상태가 항상 최신이므로)
2. Phase가 컨설턴트 책임이 아니므로 휴먼 에러 없음
3. Phase 전진·후퇴가 논리적으로 항상 일관됨

### Phase 계산 규칙 (요약)

```python
project.phase = "가장 이른 pending stage가 있는 phase" OR CLOSED
```

구체적 매핑:

| Application에 남아있는 가장 이른 active stage | → Project Phase |
|---|---|
| `SOURCED` | `SEARCHING` |
| `SCREENED` 또는 `PRE_MEETING` | `PRE_MEETING` |
| `RECOMMENDED` | `SUBMITTED` |
| `CLIENT_INTERVIEWING` | `INTERVIEWING` |
| 활성 application 없음, HIRED 존재 | `CLOSED` (success) |
| 활성 application 없음, HIRED 없음 | `CLOSED` (no_hire) 또는 빈 상태 |

이 규칙의 상세 시나리오 검증은 [04-phase-derivation-rule.md](04-phase-derivation-rule.md) 참조.

---

## 6. 왜 이 모델이 현실과 맞는가

### ✅ 병렬 단계 자연 표현
한 프로젝트 안에 후보자 10명이 서로 다른 stage에 분포해도 문제없음. Project phase는 "가장 이른 pending"에서 단일값으로 추출되고, 나머지는 전부 Application 수준에서 자연스럽게 존재.

### ✅ 백-앤-포스 자연 지원
클라이언트가 "다른 후보자 더 찾아주세요"라고 해서 새 후보자를 추가하면, 새 Application이 SOURCED로 생성되고 **phase가 자동으로 SEARCHING으로 후퇴**한다. 별도 코드 없음.

### ✅ 후보자 관점의 M:N 관계
한 Candidate가 여러 Project에 동시에 지원할 수 있고, 각각은 독립적인 Application으로 추적된다. 후보자 상세 페이지에서 `candidate.applications.all()`로 한눈에 확인 가능.

### ✅ 드롭 사유 분석 가능
모든 드롭이 `drop_reason`을 강제로 가지므로, "우리 프로젝트들이 가장 많이 실패하는 이유", "특정 클라이언트의 서류 탈락률", "컨설턴트별 후보자 거절 패턴" 등의 분석이 자동 가능.

### ✅ 사전 미팅을 1급 단계로 승격
엑셀에는 존재하지 않던 PRE_MEETING 단계가 명시적으로 모델링된다. 이는 컨설턴트 핵심 업무의 **가치 가시화**이자 synco가 엑셀보다 나은 지점.

---

## 7. Phase와 Stage의 개념적 차이 (재강조)

| | Project Phase | Application Stage |
|---|---|---|
| **대상** | 프로젝트 1건 | (프로젝트, 후보자) 엣지 1건 |
| **개수** | 5 + CLOSED | 6 + DROPPED |
| **관리자** | 시스템 (auto-derived) | 컨설턴트 (manual) |
| **의미** | "프로젝트의 현재 작업 포커스" | "이 후보자의 진척도" |
| **저장 위치** | `Project.phase` (cached) | `Application.stage` |
| **히스토리** | `ProjectEvent` 타임라인 | `Application.*_at` 타임스탬프 + ProjectEvent |
| **변경 빈도** | Application 변경 시 재계산 | 컨설턴트 액션마다 |

**"Project phase를 직접 이동시키는 기능은 UI에 없어야 한다."** 이건 반드시 지켜야 할 원칙이다. 컨설턴트가 phase를 직접 만지면 2-레이어 모델의 일관성이 깨진다.
