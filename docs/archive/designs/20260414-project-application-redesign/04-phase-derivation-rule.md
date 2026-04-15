# 04. Phase 파생 규칙 — "가장 이른 미해결 단계"

Project Phase를 Application들의 집계로부터 자동 계산하는 규칙과, 이 규칙이 모든 현실 시나리오에서 올바르게 동작하는 이유.

---

## 1. 왜 "가장 멀리 간 후보자" 규칙이 틀렸나

처음 떠오르는 직관은 "Project phase = 가장 진보한 Application의 stage"다. 하지만 이건 틀렸다.

### 반례 (사장님이 지적한 시나리오)

> 삼성전자에서 구인 요청이 왔다. 후보자 10명을 막 서칭하고 있어. 아직 많이 못 찾았어. 그런데 운 좋게 일찍 찾은 한 명이 벌써 사전미팅까지 진행됐어. 프로젝트의 상태는 뭐인 거지?

"가장 멀리 간" 규칙 → phase = `PRE_MEETING`  
하지만 현실에서 이 프로젝트의 **주 업무는 여전히 서칭**이다. 1명의 outlier가 전체 상태를 왜곡한다.

**올바른 답**: phase = `SEARCHING`. 서칭이 아직 끝나지 않았으니까.

---

## 2. 올바른 규칙 — "가장 이른 미해결 단계"

```
Project.phase = 활성(non-terminal) Application 중 가장 이른 stage에 대응하는 phase
```

"활성"이란: stage가 `HIRED`도 `DROPPED`도 아닌 것. 아직 판단이 끝나지 않은 후보자.  
"가장 이른"이란: SEARCHING → PRE_MEETING → SUBMITTED → INTERVIEWING 순서에서 가장 앞 쪽.

### 알고리즘

```python
STAGE_TO_PHASE_ORDER = [
    ("sourced",             "searching"),
    ("screened",            "pre_meeting"),
    ("pre_meeting",         "pre_meeting"),
    ("recommended",         "submitted"),
    ("client_interviewing", "interviewing"),
]

def compute_project_phase(project):
    # 수동으로 종료된 프로젝트는 그대로
    if project.closed_at is not None:
        return "closed"

    active = project.applications.exclude(
        stage__in=["hired", "dropped"]
    ).values_list("stage", flat=True)
    active_set = set(active)

    # 가장 이른 단계부터 스캔
    for stage, phase in STAGE_TO_PHASE_ORDER:
        if stage in active_set:
            return phase

    # 활성 Application이 하나도 없음 → 자동 종료 판정
    if project.applications.filter(stage="hired").exists():
        # 입사자 있음 → 성공
        return "closed"  # close_reason=success는 signal에서 세팅
    # 활성자도 없고 입사자도 없음 → 실패 (전원 드롭)
    return "closed"  # close_reason=no_hire
```

**핵심 단순화**:
- 컨설턴트는 phase를 직접 건드리지 않음
- Application이 변할 때마다 signal/service가 이 함수를 호출해서 `Project.phase`를 업데이트
- Forward/backward 어떤 경우든 이 한 규칙이 모든 것을 처리

---

## 3. 시나리오 검증 — 이 규칙이 모든 케이스를 해결한다

### 시나리오 A — 정상 플로우 (삼성전자)

| 액션 | Application 상태 (활성) | Phase |
|---|---|---|
| 10명 추가 | 10 × SOURCED | `SEARCHING` |
| 5명 드롭, 5명 promote | 5 × SCREENED | `PRE_MEETING` |
| 2명 드롭, 3명 promote | 3 × RECOMMENDED | `SUBMITTED` |
| 클라이언트 피드백: 1 드롭, 2 promote | 2 × CLIENT_INTERVIEWING | `INTERVIEWING` |
| 1 드롭, 1 promote | 1 × HIRED (0 활성) | `CLOSED` (success) |

### 시나리오 B — 삼성전자에 운 좋게 일찍 간 한 명

| 액션 | Application 상태 | Phase |
|---|---|---|
| 10명 추가, 1명은 이미 promote 3번 | 9 SOURCED + 1 RECOMMENDED | **`SEARCHING`** ✅ |

`SOURCED`가 `RECOMMENDED`보다 이른 단계이므로 phase는 `SEARCHING`. 사장님 직관과 일치.

### 시나리오 C — 사전미팅에서 "다 마음에 안 듦, 재서칭"

| 액션 | Application 상태 | Phase |
|---|---|---|
| 현재 | 5 PRE_MEETING | `PRE_MEETING` |
| 5명 다 드롭 | 0 활성 | `CLOSED` (no_hire) 또는 빈 상태 |
| 새 후보자 8명 추가 | 8 SOURCED | **`SEARCHING`** ✅ |

프로젝트가 자동으로 다시 열리고 SEARCHING으로 이동한다.

중간의 "빈 상태"를 피하고 싶다면, 드롭과 추가를 같은 트랜잭션 안에서 처리하거나, 빈 상태에서도 `project.closed_at`이 null이면 phase를 `SEARCHING`으로 기본값 처리하면 된다.

### 시나리오 D — 클라이언트가 제출 후 "다른 후보자 더"

| 액션 | Application 상태 | Phase |
|---|---|---|
| 현재 | 3 RECOMMENDED | `SUBMITTED` |
| 새 후보자 5명 추가 (기존 3명 유지) | 5 SOURCED + 3 RECOMMENDED | **`SEARCHING`** ✅ |

`SOURCED`가 `RECOMMENDED`보다 이른 단계이므로 phase는 자동으로 SEARCHING으로 후퇴. 서칭 진행하면서 기존 3명도 살아있는 상태.

### 시나리오 E — 새 후보자 추가만으로 phase 자동 변경

사장님 말씀: "새 후보자를 추가시키는 것은 서칭 단계로 돌아가는 것."

| 액션 | Application 상태 | Phase |
|---|---|---|
| 현재 | 2 CLIENT_INTERVIEWING | `INTERVIEWING` |
| 새 후보자 1명 추가 | 1 SOURCED + 2 CLIENT_INTERVIEWING | **`SEARCHING`** ✅ |

면접 중인 2명은 그대로 유지하면서 phase만 뒤로 이동. 별도 로직 없이 규칙 하나로 해결.

### 시나리오 F — 페이지별 자동 완료

사장님 말씀: "모든 후보자에 대한 판단이 끝나면 그 페이지는 끝난 걸로."

| 액션 | Application 상태 | Phase |
|---|---|---|
| 10명 모두 SOURCED | 10 × SOURCED | `SEARCHING` |
| 5 드롭 + 5 promote | 0 SOURCED + 5 SCREENED | `PRE_MEETING` |

SEARCHING에 남은 pending이 0이 되면 자동으로 다음 단계로 넘어간다. 컨설턴트가 "이제 서칭 끝났어"라고 명시적으로 말할 필요 없음.

---

## 4. 특수 케이스와 엣지

### 4-1. 빈 프로젝트 (Application 0건)

이제 막 생성되고 아직 후보자를 아무도 추가하지 않은 프로젝트는 활성 Application이 없다. 이 경우:
- `Project.closed_at`이 null → phase = `SEARCHING` (기본값)

**규칙 보완**: 활성 Application이 없고 HIRED도 없으면, `closed_at`의 유무로 판단:
- `closed_at=null` → `SEARCHING` (아직 종료 안 된 프로젝트의 빈 상태)
- `closed_at=not null` → `CLOSED`

### 4-2. 전원 DROPPED 후 추가 작업 안 함

| 액션 | 상태 |
|---|---|
| 10 × DROPPED, 0 활성, 0 HIRED | `closed_at`이 null이면 `SEARCHING`으로 남음 |

이 경우 프로젝트가 사실상 실패지만 자동 종료되지는 않는다. 컨설턴트가 명시적으로 `Close Project` 액션을 취하거나, **시간 기반 auto-close rule**이 별도로 동작해야 한다.

### 4-3. 시간 기반 auto-close

정호열 탭의 stale 프로젝트 문제를 막으려면:
- 활성 Application이 0이고 최근 60일간 새 Application 추가 없음 → 자동 `closed_at` 설정, `close_reason=no_hire`
- 혹은 컨설턴트가 명시적으로 "프로젝트 닫기" 버튼 클릭 시 닫힘

이건 구현 단계에서 정책 결정 필요. 현재는 "자동 종료는 기본적으로 비활성, 컨설턴트 수동 종료를 기본으로 하되 옵션으로 auto-close rule 제공"으로 한다.

### 4-4. HIRED 성공 처리

한 Application이 HIRED가 되면:
- 그 즉시 `Project.closed_at = now()`, `close_reason = "success"`로 설정 (signal)
- 나머지 Application들은 그대로 둬도 되고, 자동으로 DROPPED 처리해도 됨 (정책 결정)

권장: **나머지 Application은 그대로 두고 "hired된 프로젝트의 비-dropped 상태"는 UI에서 중립적으로 표시**. 컨설턴트가 나중에 필요하면 정리할 수 있도록.

### 4-5. Phase DB 캐싱 vs property

성능 관점에서 phase를 Project 테이블에 캐시하는 게 좋다. 이유:
- 칸반 리스트 쿼리가 phase별 group_by 필요
- property로 하면 N+1 또는 복잡한 annotate 필요

**결정**: DB 컬럼으로 캐시. Application의 `post_save`/`post_delete` signal에서 `Project.phase`를 재계산해서 저장.

```python
@receiver([post_save, post_delete], sender=Application)
def update_project_phase(sender, instance, **kwargs):
    project = instance.project
    new_phase = compute_project_phase(project)
    if project.phase != new_phase:
        project.phase = new_phase
        project.save(update_fields=["phase"])
        # ProjectEvent로 히스토리 기록
```

---

## 5. 왜 Round 필드를 안 쓰는가

초기 논의에서는 "재서칭/재추천 반복"을 `round` 숫자 필드로 추적하자는 아이디어가 나왔다. 하지만 auto-derivation 규칙이 back-and-forth를 자연스럽게 처리하므로 Round는 불필요하다.

- Round 증가 시점을 정의하기 어려움 ("얼마나 뒤로 가야 새 라운드인가?")
- 같은 프로젝트 내에서 phase가 앞뒤로 움직이는 건 자연스러운 일
- 히스토리는 `ProjectEvent` 타임라인으로 정확히 기록됨 (숫자 하나보다 풍부)

대신 `ProjectEvent` 타임라인에 다음 이벤트들을 기록:
- `candidate_added`, `candidate_promoted`, `candidate_dropped`
- `phase_changed` (이전 phase → 새 phase, 계기가 된 Application ID)
- `project_reopened` (closed 후 다시 열린 경우)
- `client_feedback_received`
- 기타 중요 마일스톤

UI에서는 이 타임라인을 읽어서 "1차 서칭 → 사전미팅 → 재서칭 → ..." 같은 흐름을 표시할 수 있다.

---

## 6. 규칙 검증 테스트 케이스 (향후 구현 시)

구현할 때 다음 케이스를 모두 단위 테스트로 검증해야 한다:

1. 빈 프로젝트 → `SEARCHING`
2. SOURCED 1개 추가 → `SEARCHING`
3. SOURCED 1개 + PRE_MEETING 1개 → `PRE_MEETING` (아니, **SEARCHING**! SOURCED가 더 이름)
4. SCREENED 1개 + RECOMMENDED 1개 → `PRE_MEETING`
5. 전원 DROPPED + 추가 작업 없음 → `SEARCHING` (closed_at null 유지)
6. 전원 DROPPED + HIRED 1개 → `CLOSED` (success)
7. 전원 DROPPED + HIRED 없음 + closed_at 세팅 → `CLOSED` (no_hire)
8. INTERVIEWING 중 새 후보자 SOURCED 추가 → phase 자동 SEARCHING으로
9. SEARCHING에서 모든 SOURCED가 promote → PRE_MEETING으로 이동
10. 여러 후보자가 HIRED (이론적으로 가능) → CLOSED (success)
