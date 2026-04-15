# P09: Interview & Offer

> **Phase:** 9
> **선행조건:** P07 (Submission CRUD — "면접 등록 →" 링크), P05 (면접/오퍼 탭 골격)
> **산출물:** 면접 탭 + 오퍼 탭 완성, 프로젝트 status 자동 전환

---

## 목표

프로젝트 상세의 면접 탭과 오퍼 탭을 완성한다. Interview/Offer CRUD와
프로젝트 라이프사이클 상태 자동 전환을 구현한다.

---

## URL 설계

### 면접

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/projects/<pk>/tab/interviews/` | GET | `project_tab_interviews` | 면접 탭 (목록) |
| `/projects/<pk>/interviews/new/` | GET/POST | `interview_create` | 면접 등록 |
| `/projects/<pk>/interviews/<int_pk>/edit/` | GET/POST | `interview_update` | 면접 수정 |
| `/projects/<pk>/interviews/<int_pk>/delete/` | POST | `interview_delete` | 면접 삭제 |
| `/projects/<pk>/interviews/<int_pk>/result/` | GET/POST | `interview_result` | 면접 결과 입력 |

### 오퍼

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/projects/<pk>/tab/offers/` | GET | `project_tab_offers` | 오퍼 탭 (목록) |
| `/projects/<pk>/offers/new/` | GET/POST | `offer_create` | 오퍼 등록 |
| `/projects/<pk>/offers/<off_pk>/edit/` | GET/POST | `offer_update` | 오퍼 수정 |
| `/projects/<pk>/offers/<off_pk>/delete/` | POST | `offer_delete` | 오퍼 삭제 |
| `/projects/<pk>/offers/<off_pk>/accept/` | POST | `offer_accept` | 오퍼 수락 |
| `/projects/<pk>/offers/<off_pk>/reject/` | POST | `offer_reject` | 오퍼 거절 |

---

## 모델

### Interview (projects 앱 — 기존 모델에 필드 추가/수정 필요 시)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | UUID | PK |
| `submission` | FK → Submission | 대상 추천 건 (통과 상태) |
| `round` | PositiveSmallIntegerField | 면접 차수 (1, 2, 3...) |
| `scheduled_at` | DateTimeField | 면접 일시 |
| `type` | CharField choices | 면접 유형 |
| `location` | CharField blank | 면접 장소 / 화상 링크 |
| `result` | CharField choices null | 면접 결과 |
| `feedback` | TextField blank | 면접관/고객사 피드백 |
| `notes` | TextField blank | 컨설턴트 메모 |

```python
class InterviewType(models.TextChoices):
    IN_PERSON = "in_person", "대면"
    VIDEO = "video", "화상"
    PHONE = "phone", "전화"

class InterviewResult(models.TextChoices):
    PASSED = "passed", "합격"
    ON_HOLD = "on_hold", "보류"
    FAILED = "failed", "탈락"
```

**unique_together:** `(submission, round)` — 같은 추천 건에 같은 차수 중복 방지.

### Offer (projects 앱)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | UUID | PK |
| `submission` | OneToOne → Submission | 대상 추천 건 |
| `salary` | CharField | 제안 연봉 |
| `position_title` | CharField | 제안 직책 |
| `start_date` | DateField null | 출근 예정일 |
| `status` | CharField choices | 오퍼 상태 |
| `terms` | JSONField default=dict | 추가 조건 |
| `notes` | TextField blank | 협상 메모 |
| `decided_at` | DateTimeField null | 수락/거절 일시 |

```python
class OfferStatus(models.TextChoices):
    NEGOTIATING = "negotiating", "협상중"
    ACCEPTED = "accepted", "수락"
    REJECTED = "rejected", "거절"
```

---

## 면접 탭 UI

후보자별 그룹핑, 차수 순 정렬.
"면접 등록": Submission 선택 → 차수 자동계산 (이전+1), 일시/유형(대면/화상/전화)/장소/링크/메모.
P07의 "면접 등록 →" 클릭 시: Submission이 미리 선택된 상태로 진입.

---

## 오퍼 탭 UI

후보자별 오퍼 카드: 제안 연봉, 직책, 출근일, 상태, 추가 조건(terms JSON).
[수락] / [거절] / [수정] 버튼.
등록 폼: 추천 건 선택 (면접 합격 Submission만), 제안 연봉, 직책, 출근 예정일, 추가 조건.

---

## 프로젝트 status 자동 전환

| 트리거 | 전환 | 조건 |
|--------|------|------|
| 첫 Interview 생성 | → `interviewing` (면접진행) | 현재 status가 `recommending` 이하 |
| 첫 Offer 생성 | → `negotiating` (오퍼협상) | 현재 status가 `interviewing` 이하 |
| Offer status → `accepted` | → `closed_success` (클로즈-성공) | — |
| 모든 Offer → `rejected` + 면접 없음 | → `closed_fail` (클로즈-실패) | 진행 중 건 없을 때만 |

**구현:** `projects/services/lifecycle.py` — `update_project_status(project)` 함수.
**역방향 전환 방지:** status는 라이프사이클 순서상 전진만 가능. 수동 취소/보류는 어느 단계에서든 가능.

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| Interview CRUD | 등록 → 목록 표시 → 수정 → 삭제 |
| 차수 자동 계산 | 이전 차수 + 1 제안 확인 |
| 면접 결과 입력 | 합격/보류/탈락 결과 저장 |
| Offer CRUD | 등록 → 목록 표시 → 수정 → 삭제 |
| 오퍼 수락/거절 | 수락 → accepted, 거절 → rejected |
| status 자동전환: 면접 | Interview 생성 → Project status = interviewing |
| status 자동전환: 오퍼 | Offer 생성 → Project status = negotiating |
| status 자동전환: 클로즈 | Offer accepted → Project status = closed_success |
| 역방향 전환 방지 | interviewing 상태에서 recommending으로 돌아가지 않음 |
| Submission 연결 | passed Submission만 면접 등록 가능 |
| 삭제 보호 | Offer 존재 시 Interview 삭제 차단 등 |

---

## 산출물

- `projects/models.py` — Interview, Offer 모델 필드 추가/수정
- `projects/views.py` — Interview/Offer CRUD 뷰 11개
- `projects/forms.py` — InterviewForm, InterviewResultForm, OfferForm
- `projects/urls.py` — Interview/Offer 관련 URL 추가
- `projects/services/lifecycle.py` — 프로젝트 status 자동 전환 로직
- `projects/templates/projects/partials/tab_interviews.html` — 면접 탭 완성
- `projects/templates/projects/partials/tab_offers.html` — 오퍼 탭 완성
- `projects/templates/projects/partials/interview_form.html` — 면접 등록/수정 폼
- `projects/templates/projects/partials/interview_result_form.html` — 면접 결과 입력 폼
- `projects/templates/projects/partials/offer_form.html` — 오퍼 등록/수정 폼
- P07 추천 탭 "면접 등록 →" 링크 활성화
- migration 파일
- 테스트 파일
