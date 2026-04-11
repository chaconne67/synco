# Phase 2 설계: 뷰 보호 + 프로젝트 필터링 + 사이드바

> **원본:** `docs/plans/headhunting-onboarding/2026-04-11-ux-gap-rbac-onboarding-design.md` 1단계 중 Phase 2 해당 부분
> **선행:** Phase 1 완료 (InviteCode, Membership.status, 데코레이터, 온보딩 플로우)
> **범위:** _get_org 수정, 기존 뷰 권한 데코레이터 적용, 프로젝트 목록 consultant 필터링, 사이드바 역할별 메뉴

---

## 1.2 권한 매트릭스

| 기능 | owner | consultant | viewer |
|------|-------|-----------|--------|
| 고객사 CRUD | O | 읽기만 | 읽기만 |
| 프로젝트 생성 | O | X | X |
| 프로젝트 할당 (담당 지정) | O | X | X |
| 프로젝트 조회 | 전체 | 배정된 것만 | 배정된 것만 |
| 프로젝트 상태 변경 | O | 배정된 것만 | X |
| 후보자 서칭/컨택/추천 | O | 배정된 프로젝트 내 | X |
| 레퍼런스 관리 | O | X | X |
| 승인 큐 | O | 본인 요청만 | X |
| 대시보드 팀 현황 | O | X | X |
| 대시보드 내 업무 | O | O | O |
| 조직 관리 | O | X | X |
| 내 설정 | O | O | O |
| 뉴스피드 | O | O | 읽기만 |

---

## 1.3 사이드바 메뉴 (역할별 필터링)

**Owner:**
```
├─ 대시보드
├─ 후보자
├─ 프로젝트
├─ 고객사
├─ 레퍼런스
├─ 승인 요청 (N)
├─ 뉴스피드
├─ 조직 관리
└─ 설정
```

**Consultant:**
```
├─ 대시보드 (내 업무)
├─ 후보자
├─ 프로젝트 (배정된 것만)
├─ 고객사 (읽기 전용)
├─ 뉴스피드
└─ 설정
```

---

## 1.6 _get_org 헬퍼 수정

현재 `_get_org(request)`는 `get_object_or_404(Organization, memberships__user=request.user)`. status=pending인 Membership도 통과시킨다. active 필터를 추가해야 한다:

```python
def _get_org(request):
    return get_object_or_404(
        Organization,
        memberships__user=request.user,
        memberships__status='active'
    )
```

pending 상태에서 _get_org를 호출하는 view에 도달하면 404 → 승인 대기 화면으로 리다이렉트하는 미들웨어 또는 데코레이터로 처리.

---

## 1.7 접근 제어 구현 방식

```python
# 데코레이터
@login_required
@role_required('owner')
def client_create(request):
    ...

# 템플릿 분기
{% if membership.role == 'owner' %}
  <a href="...">새 고객사 등록</a>
{% endif %}

# 프로젝트 쿼리셋 필터링
if membership.role == 'owner':
    projects = Project.objects.filter(organization=org)
else:
    projects = Project.objects.filter(consultants=request.user)
```

---

## 적용 대상 뷰 정리

### clients/views.py

| 뷰 | 역할 제한 |
|----|----------|
| client_list | 모든 역할 (membership_required) |
| client_create | owner only |
| client_detail | 모든 역할 |
| client_update | owner only |
| client_delete | owner only |
| contract_create | owner only |
| contract_update | owner only |
| contract_delete | owner only |
| 레퍼런스 CRUD 전체 | owner only |

### projects/views.py

| 뷰 | 역할 제한 |
|----|----------|
| dashboard | membership_required |
| project_list | membership_required + consultant 필터링 |
| project_create | owner only |
| project_delete | owner only |
| approval_queue | owner only |
| approval_decide | owner only |
| 나머지 프로젝트 뷰 | membership_required |
