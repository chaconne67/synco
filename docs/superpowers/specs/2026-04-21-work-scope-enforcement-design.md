# 업무 스코프 일관 적용 (Work Scope Enforcement) — 설계

**작성일:** 2026-04-21
**브랜치:** `refactor/single-tenant`
**선행:** 단일테넌트 리팩터 T1~T11 완료 (`docs/superpowers/specs/2026-04-20-single-tenant-refactor-design.md`)

## 배경

T1~T11 에서 `User.level` + `is_superuser` 2축 권한 모델을 도입하고 `accounts/services/scope.py::scope_work_qs` 헬퍼를 만들었다. 원칙은 다음 두 가지:

- **업무 데이터** (Project / Application / ActionItem / Interview / Submission): Level 1(직원) 은 본인 assigned 만, Level 2+(사장) · superuser(개발자) 는 전체
- **정보 데이터** (Candidate / Client / 마스터): Level 1 이상 전체 조회

감사 결과 원칙과 실제 코드가 어긋난다.

1. **[A] 업무 스코프 미적용.** `scope_work_qs` 는 레포 전체에서 `projects/views.py:2431` **한 곳만** 사용 중. 업무 뷰 100여 곳은 `@level_required(1)` 게이트만 걸려 있어 Level 1 유저가 URL 의 `pk` 만 알면 동료의 프로젝트·지원서·액션·인터뷰·Submission 을 그대로 조회 가능.
2. **[B] 삭제된 FK 참조.** T6 에서 지운 `organization` 필드를 아직 참조하는 코드 2곳 (`projects/management/commands/close_overdue_projects.py:45`, `clients/services/client_queries.py:26`). 호출 시 런타임 에러.
3. **[C] 데드 파라미터·응답.** `organization=None` 파라미터가 `projects/services/voice/*.py`, `projects/services/candidate_matching.py` 에 10+ 곳. `candidates/views_extension.py:74` 는 응답에 `"organization": None` 을 계속 내보내고 테스트가 이를 검증.

## 목표

A · B · C 를 한 플랜에서 해결. 단일테넌트 리팩터로 시작한 권한 재편을 마감.

## 설계

### 새 헬퍼: `get_scoped_object_or_404`

기존 `scope_work_qs(qs, user)` 는 쿼리셋 필터용이라 뷰 대부분이 쓰는 `get_object_or_404(Model, pk=...)` 패턴과 안 맞는다. 신규 헬퍼를 하나 추가:

```
accounts/services/scope.py

def get_scoped_object_or_404(model, user, **lookup):
    """Fetch a work-model instance subject to the user's scope.

    Level 2+/superuser: behaves like get_object_or_404.
    Level 1: raises Http404 if the user is not assigned to the object.
    Level 0: always Http404.
    """
```

모델별 "assigned" 판정은 각 모델의 전용 predicate 를 `scope.py` 안에 상수 맵으로 정의:

| 모델 | assigned 판정 (Level 1 경우) |
|---|---|
| `Project` | `assigned_consultants` 에 `user` 포함 |
| `Application` | `project__assigned_consultants` 에 `user` 포함 |
| `ActionItem` | `assigned_to == user` **OR** `application__project__assigned_consultants` 에 `user` 포함 |
| `Interview` | `action_item__application__project__assigned_consultants` 에 `user` 포함 |
| `Submission` | `application__project__assigned_consultants` 에 `user` 포함 |

Action·Interview 는 "본인 담당 액션 + 본인 컨설턴트로 있는 프로젝트의 다른 액션" 둘 다 볼 수 있음 (팀 업무 가시성 유지).

맵 구조 예:

```python
_WORK_SCOPE_RULES = {
    Project:     lambda user: Q(assigned_consultants=user),
    Application: lambda user: Q(project__assigned_consultants=user),
    ActionItem:  lambda user: Q(assigned_to=user) | Q(application__project__assigned_consultants=user),
    Interview:   lambda user: Q(action_item__application__project__assigned_consultants=user),
    Submission:  lambda user: Q(application__project__assigned_consultants=user),
}
```

권한 없는 객체 접근 시 **404** — 존재 여부 자체를 숨김 (Django 관용).

### 기존 `scope_work_qs` 처리

시그니처는 `(qs, user)` 2개 인자로 단순화. 모델에 따른 판정은 내부에서 `qs.model` 을 키로 맵을 조회:

```python
def scope_work_qs(qs, user):
    model = qs.model
    if user.is_superuser or user.level >= 2:
        return qs
    if user.level < 1:
        return qs.none()
    rule = _WORK_SCOPE_RULES.get(model)
    if rule is None:
        raise ValueError(f"No scope rule for {model.__name__}")
    return qs.filter(rule(user)).distinct()
```

기존 `assigned_field="assigned_consultants"` 키워드 인자는 삭제 (Project 전용 하드코딩이라 Application·Interview 에 못 쓰고 있었음).

### Dashboard 통합

`projects/services/dashboard.py` 는 현재 `scope_owner: bool` 을 5개 헬퍼에 인자로 전달. 이를 `scope_work_qs` 로 교체:

- `_scope_projects(user, scope_owner)` → `_scope_projects(user)` : 내부에서 `scope_work_qs(Project.objects.all(), user)` 호출
- `_monthly_success`, `_project_status_counts`, `_weekly_schedule`, `_monthly_calendar` 는 `scope_owner` 인자 제거
- `_team_performance()` 는 기존처럼 scope 우회 (설계 의도)
- `get_dashboard_context()` 반환값의 `_scope_owner` 플래그는 필요하면 `user.level >= 2 or is_superuser` 를 재계산해 유지 (템플릿 조건 분기가 있을 수 있음)

코드 주석 `"T10 will rewire internal queries via scope_work_qs"` 가 해결된다.

### 뷰 수정 패턴

업무 모델 pk 로 단일 객체 조회하는 모든 뷰:

```python
# Before
project = get_object_or_404(Project, pk=pk)

# After
project = get_scoped_object_or_404(Project, request.user, pk=pk)
```

리스트 조회는 기존 `scope_work_qs` 를 붙인다:

```python
# Before
applications = Application.objects.filter(project=project)

# After
applications = scope_work_qs(Application.objects.filter(project=project), request.user)
```

단, **상위 객체(project)** 가 이미 scoped 로 통과됐다면 그 하위 Application 리스트에는 추가 scope 불필요 (프로젝트 접근 권한이 곧 그 프로젝트의 application 전체 접근 권한).

### 대상 파일

**업무 뷰 (A 수정):**
- `projects/views.py` — 약 40곳 패턴 치환
- `projects/views_news.py` — 해당 없음 (news 는 정보성)
- `projects/views_voice.py` — Project/Application 조회부
- `projects/views_telegram.py` — Project/Application 조회부
- `projects/services/dashboard.py` — 위 "Dashboard 통합" 섹션

**B 버그:**
- `projects/management/commands/close_overdue_projects.py:45` — `.select_related("organization", "client")` → `.select_related("client")`
- `clients/services/client_queries.py` — `org=None` 파라미터 제거, `organization=org` 필터 제거 (호출처도 같이 수정)

**C 데드 청소:**
- `projects/services/voice/action_executor.py` — `organization=None` 파라미터 전수 제거
- `projects/services/voice/context_resolver.py`, `entity_resolver.py` — 동일
- `projects/services/candidate_matching.py` — 동일
- `candidates/views_extension.py:74` — `"organization": None` 응답 필드 제거
- `tests/test_extension_api.py` — organization 관련 assertion 삭제
- `conftest.py`, `tests/conftest.py`, `main/urls.py` — stale 주석 청소

### 테스트 전략

#### 단위 테스트

- `tests/accounts/test_scope_work_qs.py` 확장: 5개 모델(Project/Application/ActionItem/Interview/Submission) × 3개 Level (0/1/2) × superuser 매트릭스
- `tests/accounts/test_scoped_object.py` 신규: `get_scoped_object_or_404` — 권한 있으면 반환, 없으면 Http404

#### 통합 테스트

- `tests/test_work_scope_404.py` 신규: 주요 업무 뷰별로 "staff_a 의 프로젝트에 staff_b 가 접근 → 404" 샘플 최소 5건
  - `GET /projects/{other}/` → 404
  - `GET /projects/{other}/applications/` (partial) → 404
  - Action 편집, Interview 편집, Submission 리스트 각각 최소 1건씩

뷰 100여 곳을 전수 테스트하진 않고 각 리소스 타입당 대표 엔드포인트만 커버. 치환이 기계적 패턴이라 한두 곳이 되면 나머지도 된다는 가정.

#### 회귀

전체 테스트 973개 pass 유지.

### 성능

`Q(assigned_to=user) | Q(application__project__assigned_consultants=user)` 같은 OR+join 쿼리가 늘어난다. 현재 규모(Project/Application 수 천 단위)에선 문제없고, 확장 시 인덱스 조정은 별 이슈로.

`get_scoped_object_or_404` 는 DB 쿼리 1회 추가 — `get_object_or_404` 와 동일 수준.

## 비고 · 결정 사항

- **404 통일**: 권한 없는 리소스는 "존재하지 않음" 으로. 403 은 쓰지 않음 (Level 0 은 `level_required` 단에서 이미 pending page 로 리다이렉트).
- **정보성 모델** (Candidate/Client/마스터) 은 건드리지 않음. `@level_required(1)` 게이트만으로 전체 조회 허용이 설계 원칙.
- **ActionItem scope 규칙**에 `assigned_to == user` 를 포함해 "본인 TODO" 를 빠짐없이 보이게 함.
- **`scope_work_qs` 의 `assigned_field` 인자 삭제**는 호출처 1곳(`projects/views.py:2431`) 뿐이라 안전.

## 작업 범위 (구현 플랜으로 넘길 항목)

1. `accounts/services/scope.py` 확장 + 단위 테스트
2. `projects/services/dashboard.py` 를 `scope_work_qs` 로 통합
3. `projects/views.py` 업무 뷰 패턴 치환
4. `projects/views_voice.py` / `views_telegram.py` 동일 치환
5. cross-user 404 통합 테스트
6. B 버그 수정 (`close_overdue_projects.py`, `client_queries.py`)
7. C 데드 청소 (voice/matching/extension + stale 주석)
8. 전체 회귀 테스트 + 린트
