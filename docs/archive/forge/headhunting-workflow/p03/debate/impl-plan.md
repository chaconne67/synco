# P03: Project Basic CRUD

> **Phase:** 3 / 6
> **선행조건:** P01 (models), P02 (client management — 고객사 선택 필요)
> **산출물:** Project CRUD + 리스트 뷰 + 사이드바 메뉴

---

## 목표

프로젝트(Project) 기본 CRUD와 필터/정렬이 가능한 리스트 뷰를 구현한다.
등록 시 고객사 선택 + JD 입력을 지원하고, 사이드바에 프로젝트 메뉴를 추가한다.

---

## URL 설계

| URL | View | Template | 설명 |
|-----|------|----------|------|
| `/projects/` | `project_list` | `projects/project_list.html` | 프로젝트 목록 |
| `/projects/new/` | `project_create` | `projects/partials/project_form.html` | 등록 폼 |
| `/projects/<uuid:pk>/` | `project_detail` | `projects/project_detail.html` | 상세 (P05에서 탭 확장) |
| `/projects/<uuid:pk>/edit/` | `project_update` | `projects/partials/project_form.html` | 수정 폼 |
| `/projects/<uuid:pk>/delete/` | `project_delete` | — | 삭제 (POST) |

---

## View 구현

```python
# projects/views.py
def project_list(request):
    """프로젝트 목록. 필터 + 정렬 + 페이지네이션."""

def project_create(request):
    """등록. 고객사 선택 + JD 텍스트/파일 입력."""

def project_detail(request, pk):
    """상세. 기본 개요 표시 (P05에서 탭 구조로 확장)."""

def project_update(request, pk):
    """수정."""

def project_delete(request, pk):
    """삭제."""
```

### 필터 파라미터

| 파라미터 | 값 | 기본값 |
|---------|-----|-------|
| `scope` | `mine` / `all` | `mine` |
| `client` | Client UUID | — |
| `status` | ProjectStatus value | — |
| `sort` | `days_asc` / `days_desc` / `created` | `days_desc` |

필터는 GET 파라미터로 전달, HTMX로 목록 영역만 교체.

---

## Project Status

```python
class ProjectStatus(models.TextChoices):
    NEW = "new", "신규"
    SEARCHING = "searching", "서칭중"
    RECOMMENDING = "recommending", "추천진행"
    INTERVIEWING = "interviewing", "면접진행"
    NEGOTIATING = "negotiating", "오퍼협상"
    CLOSED_SUCCESS = "closed_success", "클로즈(성공)"
    CLOSED_FAIL = "closed_fail", "클로즈(실패)"
    CLOSED_CANCEL = "closed_cancel", "클로즈(취소)"
    ON_HOLD = "on_hold", "보류"
    PENDING_APPROVAL = "pending_approval", "승인대기"
```

---

## Template 구조

```
projects/templates/projects/
├── project_list.html              # 목록 full page
├── project_detail.html            # 상세 full page
└── partials/
    ├── project_list_content.html  # 목록 내용 (필터+테이블)
    ├── project_detail_content.html # 상세 내용
    └── project_form.html          # 등록/수정 공용 폼
```

---

## UI 와이어프레임

### 프로젝트 목록 (기본 리스트)

```
┌─ 프로젝트 ──────────────────────── [+ 새 의뢰] ─┐
│                                                 │
│  필터: [내 담당▾] [고객사▾] [상태▾]               │
│  정렬: [경과일순▾]                               │
│                                                 │
│  ┌────────┬──────────┬──────┬────┬──────┐      │
│  │고객사   │포지션     │상태   │담당 │경과일 │      │
│  ├────────┼──────────┼──────┼────┼──────┤      │
│  │Rayence │품질기획팀장│서칭중  │전병권│ 12   │      │
│  │삼성SDI  │해외영업   │면접진행│김소연│ 25   │      │
│  │SK하이닉 │공정엔지니어│오퍼협상│전병권│ 41   │      │
│  │LG전자   │경영기획   │신규   │전병권│  2   │      │
│  └────────┴──────────┴──────┴────┴──────┘      │
│                                                 │
│  ← 1 2 3 →                                     │
└─────────────────────────────────────────────────┘
```

### 프로젝트 등록 폼

```
┌─ 새 의뢰 등록 ────────────────────────────────────┐
│                                                   │
│  고객사: [Rayence              ▾]  [+ 신규 등록]   │
│  포지션명: [품질기획팀장            ]               │
│                                                   │
│  JD 입력:                                         │
│  ○ 텍스트 직접 입력   ● 파일 업로드                  │
│                                                   │
│  JD 파일: [파일 선택: rayence_jd.pdf]              │
│                                                   │
│  요구조건 (선택):                                   │
│  경력:  [15 ]년 이상                               │
│  학력:  [인서울 이상 ▾]                             │
│  성별:  [무관 ▾]                                   │
│  필수자격: [품질경영기사         ]                   │
│                                                   │
│  [등록]  [취소]                                    │
└───────────────────────────────────────────────────┘
```

- 고객사 드롭다운: 기존 Client 목록에서 검색·선택
- JD 입력: 텍스트와 파일 중 택1 (또는 둘 다)
- 요구조건: requirements JSONField에 저장

---

## 사이드바 변경

```html
<a hx-get="/projects/" hx-target="main" hx-push-url="true">
  📋 프로젝트
</a>
```

최종 메뉴 순서: 대시보드 > **프로젝트** > 고객사 > 후보자 DB

---

## 경과일 계산

```python
@property
def days_elapsed(self) -> int:
    """프로젝트 생성일로부터 경과 일수."""
    return (timezone.now().date() - self.created_at.date()).days
```

리스트에서 경과일 기준 정렬 시 DB 레벨 annotation 사용:
```python
Project.objects.annotate(
    days=ExpressionWrapper(
        Now() - F("created_at"), output_field=DurationField()
    )
).order_by("-days")
```

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| CRUD 동작 | 등록 → 목록 표시 → 상세 → 수정 → 삭제 |
| 필터 | scope=mine 시 본인 담당만, client 필터, status 필터 |
| 정렬 | 경과일 오름차순/내림차순 |
| JD 입력 | 텍스트 입력 + 파일 업로드 각각 동작 |
| 고객사 연결 | 등록 시 선택한 고객사가 상세에 표시 |
| status choices | 10개 상태 모두 설정/표시 가능 |

---

## 산출물

- `projects/views.py` — CRUD 뷰 5개
- `projects/urls.py` — URL 패턴
- `projects/forms.py` — ProjectForm
- `projects/templates/projects/` — 목록/상세/폼 템플릿
- 사이드바 템플릿 수정
- 테스트 파일
