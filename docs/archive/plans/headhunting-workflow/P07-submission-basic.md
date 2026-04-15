# P07: Submission Basic CRUD

> **Phase:** 7
> **선행조건:** P05 (추천 탭 골격), P06 (컨택 탭 — "추천 서류 작성 →" 링크)
> **산출물:** 추천 탭 완성 — Submission CRUD + 양식 선택 + 파일 업로드/다운로드 + 상태 관리 + 고객사 피드백

---

## 목표

프로젝트 상세의 추천 탭을 완성한다. 고객사에 제출할 추천 서류(Submission)의
등록/수정/삭제, 양식 선택, 파일 업로드/다운로드, 상태 전환, 고객사 피드백 입력을 구현한다.

---

## URL 설계

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/projects/<pk>/tab/submissions/` | GET | `project_tab_submissions` | 추천 탭 (목록) |
| `/projects/<pk>/submissions/new/` | GET/POST | `submission_create` | 추천 서류 등록 |
| `/projects/<pk>/submissions/<sub_pk>/edit/` | GET/POST | `submission_update` | 추천 서류 수정 |
| `/projects/<pk>/submissions/<sub_pk>/delete/` | POST | `submission_delete` | 추천 서류 삭제 |
| `/projects/<pk>/submissions/<sub_pk>/submit/` | POST | `submission_submit` | 고객사에 제출 (상태 전환) |
| `/projects/<pk>/submissions/<sub_pk>/feedback/` | GET/POST | `submission_feedback` | 고객사 피드백 입력 |
| `/projects/<pk>/submissions/<sub_pk>/download/` | GET | `submission_download` | 첨부파일 다운로드 |

---

## 모델 변경

### Submission (projects 앱 — 기존 설계 그대로)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | UUID | PK |
| `project` | FK → Project | 소속 프로젝트 |
| `candidate` | FK → Candidate | 추천 후보자 |
| `consultant` | FK → User | 작성 컨설턴트 |
| `template` | CharField choices | 양식 (엑스다임 국문/국영문/영문/고객사 커스텀) |
| `status` | CharField choices | 작성중/제출/통과/탈락 |
| `document_file` | FileField | 업로드된 제출 서류 |
| `submitted_at` | DateTimeField null | 제출 일시 |
| `client_feedback` | TextField blank | 고객사 피드백 |
| `client_feedback_at` | DateTimeField null | 피드백 수신 일시 |
| `notes` | TextField blank | 컨설턴트 메모 |
| `created_at` | DateTimeField auto | |
| `updated_at` | DateTimeField auto | |

**choices:**
```python
class SubmissionTemplate(models.TextChoices):
    XD_KO = "xd_ko", "엑스다임 국문"
    XD_KO_EN = "xd_ko_en", "엑스다임 국영문"
    XD_EN = "xd_en", "엑스다임 영문"
    CUSTOM = "custom", "고객사 커스텀"

class SubmissionStatus(models.TextChoices):
    DRAFT = "draft", "작성중"
    SUBMITTED = "submitted", "제출"
    PASSED = "passed", "통과"
    REJECTED = "rejected", "탈락"
```

**unique_together:** `(project, candidate)` — 같은 프로젝트에 같은 후보자 중복 추천 방지.

---

## 등록 폼

```
┌─ 추천 서류 등록 ─────────────────────────────────────┐
│                                                      │
│  후보자: [홍길동 - 메디톡스 품질부장    ▾]              │
│          (컨택 결과 "관심"인 후보자만 표시)             │
│                                                      │
│  양식:   ○ 엑스다임 국문                               │
│          ● 엑스다임 국영문                             │
│          ○ 엑스다임 영문                               │
│          ○ 고객사 커스텀                               │
│                                                      │
│  서류 파일:                                           │
│  [파일 선택] (Word/PDF, 최대 10MB)                    │
│                                                      │
│  메모:                                               │
│  [____________________________]                      │
│  [____________________________]                      │
│                                                      │
│  [저장 (작성중)]  [취소]                               │
└──────────────────────────────────────────────────────┘
```

- 후보자 드롭다운: 해당 프로젝트에서 컨택 결과가 "관심(interested)"인 후보자 목록
- P06의 컨택 탭 "추천 서류 작성 →" 클릭 시: 후보자가 미리 선택된 상태로 진입

---

## 추천 탭 목록 UI

```
┌─ 추천 서류 (3건) ────────────────── [+ 새 추천] ─────┐
│                                                      │
│  ┌─ 작성중 ──────────────────────────────────────┐   │
│  │  홍길동  |  엑스다임 국영문  |  최종수정: 04/06   │   │
│  │  [편집]  [파일 다운로드]  [제출하기 →]           │   │
│  └────────────────────────────────────────────────┘   │
│                                                      │
│  ┌─ 제출됨 ──────────────────────────────────────┐   │
│  │  이순신  |  엑스다임 국문  |  제출일: 03/25      │   │
│  │  고객사: 서류 검토중                            │   │
│  │  [고객사 피드백 입력]  [파일 다운로드]           │   │
│  └────────────────────────────────────────────────┘   │
│                                                      │
│  ┌─ 통과 ✓ ─────────────────────────────────────┐   │
│  │  김영희  |  엑스다임 국영문  |  제출일: 03/20    │   │
│  │  고객사: "경력이 인상적입니다. 면접 진행하겠습니다"│   │
│  │  [파일 다운로드]  [면접 등록 →]                  │   │
│  └────────────────────────────────────────────────┘   │
│                                                      │
│  ┌─ 탈락 ✗ ─────────────────────────────────────┐   │
│  │  박철수  |  고객사 커스텀  |  제출일: 03/18      │   │
│  │  고객사: "경력 연차가 부족합니다"                 │   │
│  └────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

- 상태별 그룹핑: 작성중 → 제출됨 → 통과 → 탈락
- "제출하기 →": 상태를 `draft` → `submitted`로 전환 + `submitted_at` 기록
- "면접 등록 →": 통과 건에서 Interview 생성으로 연결 (P09에서 구현)
- "고객사 피드백 입력": 인라인 폼 또는 모달

---

## 고객사 피드백 입력

```
┌─ 고객사 피드백 ─ 이순신 ──────────────────────────────┐
│                                                      │
│  결과: ○ 통과  ○ 탈락                                 │
│                                                      │
│  피드백 내용:                                         │
│  [____________________________]                      │
│  [____________________________]                      │
│                                                      │
│  [저장]  [취소]                                       │
└──────────────────────────────────────────────────────┘
```

- "통과" 선택 시 `status = passed`, "탈락" 선택 시 `status = rejected`
- `client_feedback` + `client_feedback_at` 저장

---

## 상태 전환 규칙

| 현재 상태 | 가능한 전환 | 트리거 |
|----------|------------|--------|
| 작성중 | → 제출 | "제출하기" 클릭 |
| 제출 | → 통과 / 탈락 | 고객사 피드백 입력 |
| 통과 | (종료 — 면접으로 연결) | — |
| 탈락 | (종료) | — |

**프로젝트 status 연동:** 첫 Submission 생성 시 프로젝트 status가 `searching` 이하이면 `recommending`으로 자동 전환.

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| Submission CRUD | 등록 → 목록 표시 → 수정 → 삭제 |
| 양식 선택 | 4가지 양식 모두 선택/저장 가능 |
| 파일 업로드 | Word/PDF 업로드 → 다운로드 가능 |
| 상태 전환 | 작성중 → 제출 → 통과/탈락 순서 강제 |
| 고객사 피드백 | 피드백 입력 → status 자동 변경 |
| 중복 방지 | 같은 프로젝트+후보자 중복 등록 차단 |
| 프로젝트 status 연동 | 첫 Submission 생성 시 프로젝트 status 자동 전환 |
| 컨택 탭 연결 | "추천 서류 작성 →" 클릭 시 후보자 미리 선택 |

---

## 산출물

- `projects/models.py` — Submission 모델 추가
- `projects/views.py` — Submission CRUD 뷰 + 제출 + 피드백
- `projects/forms.py` — SubmissionForm, SubmissionFeedbackForm
- `projects/urls.py` — Submission 관련 URL 추가
- `projects/services/submission.py` — 상태 전환 로직, 프로젝트 status 연동
- `projects/templates/projects/partials/tab_submissions.html` — 추천 탭 완성
- `projects/templates/projects/partials/submission_form.html` — 등록/수정 폼
- `projects/templates/projects/partials/submission_feedback.html` — 피드백 폼
- P06 컨택 탭 "추천 서류 작성 →" 링크 활성화
- 테스트 파일
