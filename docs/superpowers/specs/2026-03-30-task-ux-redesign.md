# Task UX Redesign

**Date:** 2026-03-30
**Status:** Approved

## Problem

Dashboard "오늘의 업무" section is broken at every level:

1. **Task title = raw memo text** — `사업자번호 | 이름 | 전화 | 메모원문`이 title에 통째로 들어감
2. **No detail view** — 카드 클릭해도 아무 반응 없음
3. **No meaningful classification** — due_date 전부 NULL, "오늘의 업무" 분류 기준 없음
4. **Tasks duplicate Interactions** — 동일 텍스트가 Interaction과 Task에 중복 저장
5. **Completion checkbox unrecognizable** — 빈 동그라미가 무슨 의미인지 알 수 없음

Root cause: `task_detect.py` line 43 — `title=interaction.summary[:80]` (원문 80자 잘라넣기).
임베딩 기반 task/not_task 판별은 동작하지만, 판별 후 **액션 요약과 날짜 추출**이 없음.

## Data Analysis

- 176 Interactions, 23 AI-extracted Tasks (13% extraction rate)
- Task 23건 전부 source=ai_extracted, due_date=NULL
- 18건 미완료, 5건 완료
- 메모 포맷이 비일관적 — 파이썬 파싱 불가, AI 필요
- 메모 내용 패턴:
  - 명시적 다음 스텝: "다음주 통화", "10/14 2시" → 팔로업 일정
  - 보류/거절: "지금은 상황이 아님", "필요하면 연락하겠다" → 할 일 아님, 대기
  - 재방문 요청: "서류만 주고 가라" → 자료 전달
  - 가족 상의: "와이프와 상의", "자녀들 중 누가" → 결과 확인 팔로업
- 18건 중 실제 pending 액션 5-6건, 나머지는 waiting 상태

## Design

### Pipeline

```
Interaction 생성 (임포트 or 수동)
    ↓
임베딩 모델 (전체 Interaction에 대해, 저렴)
    ↓
cosine similarity → task / waiting / not_task 분류
    ↓ (task 또는 waiting 판정인 경우만)
LLM (Claude API) → { title: "액션 요약", due_date: "YYYY-MM-DD" or null }
    ↓
Task 생성 (title=요약, description=원문, status, due_date)
```

임베딩은 전체에 돌리고, LLM은 task 판정 건(~13%)에만 호출. 비용 효율적.

### Model Changes

**Task model:**

```python
class Task(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "할 일"
        WAITING = "waiting", "대기"
        DONE = "done", "완료"

    class Source(models.TextChoices):
        MANUAL = "manual", "직접 입력"
        AI_EXTRACTED = "ai_extracted", "AI 추출"

    fc = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tasks")
    contact = models.ForeignKey("Contact", on_delete=models.CASCADE, null=True, blank=True, related_name="tasks")
    title = models.CharField(max_length=200)           # LLM 생성 액션 요약
    description = models.TextField(blank=True)          # 메모 원문 (NEW)
    due_date = models.DateField(null=True, blank=True)  # LLM 추출 날짜
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)  # NEW (replaces is_completed)
    source = models.CharField(max_length=15, choices=Source.choices, default=Source.MANUAL)
```

- `is_completed` 제거 → `status=done`으로 대체
- `description` 추가 — 메모 원문 보존
- `status` 추가 — pending/waiting/done 3상태

Migration: `is_completed=True` → `status=done`, `is_completed=False` → `status=pending`.

### Reference Vectors

`_references.py` TASK_REFS에 `waiting` 카테고리 추가:

```python
TASK_REFS = {
    "task": "견적서를 보내기로 약속했고 다음주까지 회신해야 한다",
    "followup": "다시 연락하기로 했고 자료를 준비해서 전달해야 한다",
    "promise": "보험 상품 비교표를 만들어서 보내주기로 했다",
    "waiting": "좋은 내용이지만 지금은 상황이 안 되고 나중에 연락하겠다고 했다",
    "not_task": "일반적인 안부를 나누었고 특별한 약속은 없었다",
}
```

Detection logic:
- `max(task, followup, promise) - not_task > MARGIN` → pending task
- `waiting - not_task > MARGIN` and waiting > task scores → waiting task
- Otherwise → no task

### LLM Title Extraction

Task 판정 건에만 Claude API 호출:

```
System: 보험설계사(FC)의 고객 접점 메모에서 FC가 해야 할 다음 액션을 추출합니다.
User:
메모: {interaction.summary}
고객: {contact.name} / {contact.company_name}

다음 JSON을 반환하세요:
{
  "title": "FC가 해야 할 다음 액션 한 줄 요약 (20자 이내)",
  "due_date": "YYYY-MM-DD 또는 null (메모에 날짜 힌트가 있을 때만)"
}
```

title 예시:
- "다음주 통화 후 스케줄 조정" → `"김동훈 대표 팔로업 전화"`
- "가족들과 상의해보겠다" → `"코드 취득 결과 확인"`
- "서류만 주고 가라" → `"자료 전달"`

### Dashboard UI

섹션 제목: "오늘의 업무" → **"할 일"**

분류 (status=pending만 표시):
```
밀린 업무 (due_date < today)     ← 빨간 경고 배너, 상단
오늘 (due_date = today)          ← 메인
이번 주 (due_date ≤ 일요일)      ← 그 아래
날짜 미지정 (due_date is null)   ← 하단
```

`status=waiting`은 대시보드에서 숨김. 연락처 상세에서만 "대기 중" 뱃지와 함께 표시.

### Task Card UI

**접힌 상태 (기본):**
```
[☐] 진현태 대표 팔로업 전화              4/1   ✏️ 🗑️
    진현태 · (주)영창정공
```

- 체크박스: rounded-lg, hover 시 체크마크 미리보기
- title: 액션 요약 (LLM 생성, 20자 이내)
- 하위 텍스트: 연락처 이름 · 회사명
- 우측: due_date + 수정/삭제 아이콘

**펼친 상태 (카드 클릭 시 인라인 확장):**
```
[☐] 진현태 대표 팔로업 전화              4/1   ✏️ 🗑️
    진현태 · (주)영창정공
    ─────────────────────────────
    지금은 무엇을 할 상황이 아니다.
    정리할때이다...

    [연락처 보기]  [완료 처리]
```

- 구분선 아래 description (메모 원문)
- "연락처 보기" → 해당 Contact detail 페이지 이동
- "완료 처리" → 체크 애니메이션 + 카드 페이드아웃

확장/축소: 카드 본문 영역 클릭 시 토글. 체크/수정/삭제 버튼 클릭은 확장 트리거 안 함.

### Data Cleanup

기존 AI 추출 Task 전부 삭제 (Interaction에 동일 데이터 보존됨).
삭제 후 `task_checked=False`로 리셋 → 파이프라인이 새 로직으로 재처리.

```python
# management command: reset_tasks
Task.objects.filter(source="ai_extracted").delete()
Interaction.objects.filter(task_checked=True).update(task_checked=False)
```

### Scope

변경 파일:
- `contacts/models.py` — Task 모델 변경 (description, status 추가, is_completed 제거)
- `intelligence/services/_references.py` — waiting 참조 벡터 추가
- `intelligence/services/task_detect.py` — waiting 분류 + LLM title 추출 호출
- `common/claude.py` (or new) — LLM 호출 유틸
- `accounts/views.py` — 대시보드 쿼리 변경 (날짜 기반 분류)
- `accounts/templates/accounts/partials/dashboard/section_tasks.html` — 섹션 제목 + 분류 UI
- `accounts/templates/accounts/partials/dashboard/_task_card.html` — 인라인 확장 UI
- `contacts/views.py` — task_complete/edit/delete 뷰 (status 기반)
- migration 파일 — is_completed → status 변환
- management command — 기존 데이터 정리 + 재처리
