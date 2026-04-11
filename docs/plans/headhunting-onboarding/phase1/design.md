# Phase 1 설계: 모델 + 데코레이터 + 온보딩 플로우

> **원본:** `docs/plans/headhunting-onboarding/2026-04-11-ux-gap-rbac-onboarding-design.md` 1단계 중 Phase 1 해당 부분
> **범위:** InviteCode 모델, Membership.status, 역할 체계, 온보딩 플로우, 데코레이터/context processor

---

## 배경

현재 synco는 P01~P19까지 헤드헌팅 핵심 기능이 구현되어 있으나, 다음 문제가 있다:

1. **온보딩 부재** — 카카오 로그인 후 Organization/Membership이 없어 대시보드 404
2. **역할 구분 없음** — owner/consultant 모두 동일 메뉴, 동일 권한으로 접근

### 배포 모델

하이브리드 SaaS. 단일 서버에 멀티테넌트(Organization 격리)로 운영하되, 고객사별 독립 사용이 기본. `db_share_enabled` 플래그로 조직 간 후보자 DB 공유를 선택적으로 활성화. UI 테마/로고는 조직별 커스터마이징 가능.

---

## 1.1 역할 체계

| 역할 | 대상 | 접근 방식 |
|------|------|----------|
| **superadmin** | 개발자 | Django admin만. 웹 UI 권한 체계에 포함하지 않음 |
| **owner** | 고객사 대표/사장 | 웹 UI 전체 + 조직 관리 메뉴 |
| **consultant** | 헤드헌터 컨설턴트 | 배정된 프로젝트 + 내 설정만 |
| **viewer** | 열람 전용 (필요 시) | 읽기만, 생성/수정 불가 |

---

## 1.4 온보딩 플로우

### 슈퍼관리자 사전 작업 (Django admin)

1. Organization 생성 (이름, plan, db_share_enabled)
2. owner용 초대코드 1개 생성 → 고객사 대표에게 전달

### 초대코드 모델

```
InviteCode
├─ code: 8자리 영숫자 (예: "SYNCO-A3K9")
├─ organization: FK(Organization)
├─ role: owner / consultant / viewer
├─ created_by: FK(User, nullable) — 슈퍼관리자 or owner
├─ max_uses: int (1회용 or N회용)
├─ used_count: int
├─ expires_at: datetime (nullable)
├─ is_active: bool
```

- 슈퍼관리자: owner/consultant/viewer 모든 역할의 코드 발급 가능
- owner: consultant 역할 코드만 발급 가능 ("직원 초대코드 생성" 버튼)

### 로그인 플로우

```
카카오 로그인
    │
    ├─ Membership 있음 + status=active → 대시보드
    │
    ├─ Membership 있음 + status=pending → 승인 대기 화면
    │   "가입 승인을 기다리고 있습니다."
    │   로그아웃 버튼만 표시
    │
    └─ Membership 없음 → 초대코드 입력 화면
         │
         ├─ 유효한 코드 입력
         │   ├─ role=owner → Membership(status=active) 즉시 생성, 대시보드로
         │   └─ role=consultant → Membership(status=pending) 생성
         │       → "가입 요청이 전달되었습니다. 승인을 기다려주세요."
         │       → owner에게 알림 (웹 + 텔레그램)
         │
         └─ 코드 없음 / 무효
             → "초대코드가 필요합니다. 관리자에게 문의하세요."
```

### Owner의 멤버 승인

조직 관리 > 멤버 탭에서:
- 승인 대기 목록 표시 (이름, 요청일, 승인/거절 버튼)
- 승인 → Membership.status = active, 사용자에게 알림
- 거절 → Membership 삭제, 사용자에게 알림

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

## 모델 변경 요약

### 신규 모델

```python
class InviteCode(BaseModel):
    code = CharField(max_length=20, unique=True)
    organization = FK(Organization)
    role = CharField(choices=['owner', 'consultant', 'viewer'])
    created_by = FK(User, nullable=True)
    max_uses = PositiveIntegerField(default=1)
    used_count = PositiveIntegerField(default=0)
    expires_at = DateTimeField(nullable=True)
    is_active = BooleanField(default=True)
```

### 기존 모델 변경

```python
# Membership: status 필드 추가
class Membership(BaseModel):
    ...
    status = CharField(
        choices=['active', 'pending'],
        default='active'
    )
```
