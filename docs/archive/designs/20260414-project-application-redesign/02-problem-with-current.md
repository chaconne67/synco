# 02. 현재 synco `ProjectStatus`의 문제점

`projects/models.py:14-25`에 정의된 현재 10-state enum이 왜 현실을 제대로 표현하지 못하는지, 무엇을 고쳐야 하는지.

---

## 1. 현재 정의

```python
class ProjectStatus(models.TextChoices):
    NEW              = "new",              "신규"
    SEARCHING        = "searching",        "서칭중"
    RECOMMENDING     = "recommending",     "추천진행"
    INTERVIEWING     = "interviewing",     "면접진행"
    NEGOTIATING      = "negotiating",      "오퍼협상"
    CLOSED_SUCCESS   = "closed_success",   "클로즈(성공)"
    CLOSED_FAIL      = "closed_fail",      "클로즈(실패)"
    CLOSED_CANCEL    = "closed_cancel",    "클로즈(취소)"
    ON_HOLD          = "on_hold",          "보류"
    PENDING_APPROVAL = "pending_approval", "승인대기"
```

---

## 2. 상태별 현실 적합도

| 상태 | 현실 적합도 | 판정 | 근거 |
|---|---|---|---|
| `NEW` | 🟡 약함 | **제거** | 엑셀에 "NEW" 개념 없음. 프로젝트는 수주와 동시에 서칭이 시작됨. NEW ≡ SEARCHING의 첫 순간. 독립 상태로 둘 가치 없음 |
| `SEARCHING` | 🟢 강함 | **유지** | 전체 프로젝트의 70% 이상이 실질적으로 이 상태. 필수 |
| `RECOMMENDING` | 🟡 모호 | **리팩터** | "추천진행"이라는 워딩이 모호. 실제로는 "PM 내부검토 + 클라이언트 서류심사 대기"를 포함. 사장님 피드백: **이 단계는 현실에서 굳이 분류할 필요 없음** |
| `INTERVIEWING` | 🟢 강함 | **유지** | 1/2/3차 컬럼과 매칭되는 명확한 단계 |
| `NEGOTIATING` | 🔴 거의 안 쓰임 | **제거** | 전체 데이터 중 신호 6건. 현실에서 오퍼 협상은 out-of-band (사장 레벨). 독립 상태로 둘 가치 없음 |
| `CLOSED_SUCCESS` | 🟢 강함 | **유지** | 42건의 명시적 성공 신호 |
| `CLOSED_FAIL` | 🟢 강함 | **유지** | 일반적인 드롭 종료 |
| `CLOSED_CANCEL` | 🟡 중복 | **제거 (NO_HIRE로 흡수)** | 사장님 피드백: 클라이언트가 취소하든 보류하든 실패로 통합. 재의뢰는 새 프로젝트 |
| `ON_HOLD` | 🔴 개념 오류 | **제거** | 사장님 피드백: "헤드헌터 입장에서 보류할 이유가 없음. 클라이언트의 '잠깐 보류할게요'는 소프트 리젝션 = 실패." 독립 상태가 아니라 실패의 변종 |
| `PENDING_APPROVAL` | ❌ 비즈니스 상태 아님 | **제거** | synco 내부 권한 충돌 워크플로. `ProjectApproval` 모델이 별도로 있으므로 Project.status에 섞을 필요 없음 |

**10개 → 0개 잔류.** 모든 상태가 제거되거나 재정의된다.

---

## 3. 구조적 결함 4가지

enum 값 하나하나의 문제는 지엽적이고, 더 깊은 구조적 결함이 4개 있다.

### 결함 1 — 상태가 잘못된 엔티티에 붙어있다

한 프로젝트 `Vatech | 정보보안팀장`에는 후보자 18명이 엮여있고 **각자 다른 단계**에 있다:
- `to PM 대기` (3명)
- `to Client 대기` (2명)
- `1차 합격, 2차 준비중` (1명)
- `본인포기` (5명)
- `탈락` (7명)

이 프로젝트의 "상태"를 단 하나의 enum 값으로 어떻게 표현할 것인가? "가장 진보한 후보자 기준"? → 1명의 outlier가 프로젝트 전체 상태를 왜곡한다.  
"대다수 기준"? → 의미가 모호하고 매번 바뀐다.  
**정답: Project에는 단일 상태가 본질적으로 존재하지 않는다. 상태는 (Project, Candidate) 엣지에 존재한다.**

### 결함 2 — 병렬 단계를 표현 못 한다

현재 모델은 **순차 상태 머신**을 가정한다. SEARCHING → RECOMMENDING → INTERVIEWING → NEGOTIATING → CLOSED 순으로 이동.

현실은 **병렬**이다:
- 후보자 A는 아직 서칭 중
- 후보자 B는 사전미팅 끝나고 이력서 제출
- 후보자 C는 클라이언트 면접 중
- 후보자 D는 이미 드롭

이들은 **동시에** 한 프로젝트 안에 존재한다. 단일 enum으로 이 병렬성을 표현할 수 없다.

### 결함 3 — Stale 상태를 처리할 방법이 없다

엑셀에서 정호열 탭의 94개 프로젝트 중 92개가 "서칭중"처럼 보이지만, 사실 대부분 수개월~수년간 활동 없는 **포기된 프로젝트**다. 아무도 명시적으로 CLOSED 표시하지 않아서 영원히 "서칭중"에 머물러있다.

현재 synco 모델은 이를 자동으로 감지·정리할 수단이 없다. enum 값이 stale해지고, 칸반이 쓰레기로 가득 찬다. **시간 기반 auto-close 규칙이 필수**지만 10-state enum만으로는 이를 걸어두기 어렵다.

### 결함 4 — 비즈니스 상태와 행정 상태가 뒤섞여있다

`PENDING_APPROVAL`은 비즈니스 라이프사이클이 아니라 synco 내부의 **권한 충돌 해결 워크플로**다. 이걸 `ProjectStatus` enum에 포함시키면:
- 칸반에서 "승인대기" 컬럼이 생김 (말이 안 됨)
- 필터에 "승인대기"가 노출됨 (의미 불분명)
- 비즈니스 상태 통계가 왜곡됨

이건 별도 필드 (`is_pending_approval: bool` 또는 기존 `ProjectApproval` 모델 링크) 로 분리되어야 한다.

---

## 4. 잘못된 위치에 있는 상태들이 이미 존재한다는 단서

아이러니하게도 synco 모델은 이미 **상태를 올바른 위치에 저장할 수 있는 구조**를 가지고 있다:

```
Project ─┬─ Contact       (project ↔ candidate, result: 응답/미응답/거절/관심/보류/예정)
         ├─ Submission    (project ↔ candidate UNIQUE, status: 작성중/제출/통과/탈락)
         ├─ Interview     (submission ↔ round, result: 대기/합격/보류/탈락)
         └─ Offer         (submission 1:1, status: 협상중/수락/거절)
```

즉 Contact/Submission/Interview/Offer 각각이 **(Project, Candidate) 엣지의 하위 이벤트**로 이미 존재한다. 이들이 파이프라인 상태를 분산 저장하고 있음에도 불구하고 **그 위에 `Project.status`라는 요약 레이어를 또 얹어서** 중복과 혼선을 만들고 있다.

**재설계의 핵심**: 이 분산된 상태를 `Application`이라는 단일 엔티티로 통합하고, 기존 Contact/Submission/Interview는 그 Application에 매달린 이벤트/아티팩트로 재배치한다. Offer는 제거. Project.status는 제거하고 auto-derive되는 `phase`로 대체.

---

## 5. 요약 — 무엇을 잃고 무엇을 얻는가

### 제거
- `ProjectStatus` enum 10개 상태 전체
- `Project.status` 필드
- `Offer` 모델 (현실에서 의미 없음)
- `Project.status = PENDING_APPROVAL` 관행 (ProjectApproval 모델로 이미 분리 가능)

### 추가
- `Application` 모델 — (Project, Candidate) 엣지의 상태·이력
- `Application.stage` enum — 6 활성 + DROPPED
- `DropReason` enum — 김현정 태그 체계 기반 드롭 사유 분류
- `ProjectEvent` 모델 — 프로젝트 히스토리 타임라인 (Round 대체)
- `Project.phase` enum — 자동 파생되는 5-phase + CLOSED
- `Project.closed_at`, `Project.close_reason` — 종료 표기

### 수정
- `Submission`, `Contact`, `Interview`, `MeetingRecord` — Application에 매달린 이벤트로 의미 재정의 (스키마 변경 최소, 관계만 재배치)

---

## 6. 왜 지금 고쳐야 하는가

1. **데이터가 아직 없다** (로컬 0건, 운영 DB에 projects 앱 자체가 배포 안 됨). 마이그레이션 부담 0.
2. **프론트/백엔드 모두 리팩터 범위가 크지만 반대로 지금이 가장 쉽다.** 프로덕션 사용자 없고, 기존 UI를 버려도 되는 시점.
3. **엑셀 데이터가 현실 검증 자료로 존재한다.** 재설계안이 현실과 맞는지 곧바로 확인 가능.
4. **v2 UI 재설계와 맞물려 있다.** 칸반/대시보드/후보자 상세 화면을 어차피 재작성해야 한다면, 모델도 같이 정비하는 게 효율적.
