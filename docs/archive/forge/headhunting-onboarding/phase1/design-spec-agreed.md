# UX Gap Analysis: 역할 기반 접근 제어 + 온보딩 + 워크플로우 보강

> **작성일:** 2026-04-11
> **범위:** 전체 사용자 여정 점검 — 로그인부터 일상 업무까지
> **구현 순서:** 1단계 역할/온보딩 → 2단계 설정/관리 → 3단계 워크플로우 연결

---

## 배경

현재 synco는 P01~P19까지 헤드헌팅 핵심 기능이 구현되어 있으나, 다음 문제가 있다:

1. **온보딩 부재** — 카카오 로그인 후 Organization/Membership이 없어 대시보드 404
2. **역할 구분 없음** — owner/consultant 모두 동일 메뉴, 동일 권한으로 접근
3. **워크플로우 단절** — 컨택→추천 전환 시 수동 탭 이동 필요
4. **설정 분산** — 프로필/Gmail/텔레그램이 각각 별도 URL에 흩어짐
5. **조직 관리 UI 없음** — 멤버/초대/조직정보 관리 화면이 없음

### 배포 모델

하이브리드 SaaS. 단일 서버에 멀티테넌트(Organization 격리)로 운영하되, 고객사별 독립 사용이 기본. `db_share_enabled` 플래그로 조직 간 후보자 DB 공유를 선택적으로 활성화. UI 테마/로고는 조직별 커스터마이징 가능.

---

## 1단계: 역할 기반 접근 제어 + 온보딩

### 1.1 역할 체계

| 역할 | 대상 | 접근 방식 |
|------|------|----------|
| **superadmin** | 개발자 | Django admin만. 웹 UI 권한 체계에 포함하지 않음 |
| **owner** | 고객사 대표/사장 | 웹 UI 전체 + 조직 관리 메뉴 |
| **consultant** | 헤드헌터 컨설턴트 | 배정된 프로젝트 + 내 설정만 |
| **viewer** | 열람 전용 (필요 시) | 읽기만, 생성/수정 불가 |

### 1.2 권한 매트릭스

| 기능 | owner | consultant | viewer |
|------|-------|-----------|--------|
| 고객사 CRUD | O | 읽기만 | 읽기만 |
| 프로젝트 생성 | O | X | X |
| 프로젝트 할당 (담당 지정) | O | X | X |
| 프로젝트 조회 | 전체 | 배정된 것만 | 배정된 것만 |
| 프로젝트 상태 변경 | O | 배정된 것만 | X |
| 후보자 서칭/컨택/추천 | O | 배정된 프로젝트 내 | X |
| 레퍼런스 관리 | O | X | X |
| 프로젝트 승인 큐 | O | 본인 요청만 | X |
| 대시보드 팀 현황 | O | X | X |
| 대시보드 내 업무 | O | O | O |
| 조직 관리 | O | X | X |
| 내 설정 | O | O | O |
| 뉴스피드 | O | O | 읽기만 |

### 1.3 사이드바 메뉴 (역할별 필터링)

**Owner:**
```
├─ 대시보드
├─ 후보자
├─ 프로젝트
├─ 고객사
├─ 레퍼런스
├─ 프로젝트 승인 (N)    ← 기존 ProjectApproval (이름 변경)
├─ 뉴스피드
├─ 조직 관리            ← 신규 (멤버 승인 포함)
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

> **Note:** 모바일 하단 네비게이션의 역할별 필터링은 Phase 2에서 처리한다. Phase 1에서는 view 단 접근 제어 데코레이터로 보안을 보장한다.

### 1.4 온보딩 플로우

#### 슈퍼관리자 사전 작업 (Django admin)

1. Organization 생성 (이름, plan, db_share_enabled)
2. owner용 초대코드 1개 생성 → 고객사 대표에게 전달

#### 초대코드 모델

```
InviteCode
├─ code: 8자리 랜덤 영숫자 (고정 prefix 없음. 예: "A3K9B7X2")
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

#### Membership.status 필드 추가

```
Membership.status
├─ type: CharField(max_length=20, choices=Status.choices)
├─ choices: active / pending / rejected
├─ default: 'active'
├─ migration: RunPython으로 기존 rows를 status='active'로 설정
│   reverse: status 필드 제거 (RemoveField)
```

#### 로그인 플로우

```
카카오 로그인
    │
    ├─ Membership 있음 + status=active → 대시보드
    │
    ├─ Membership 있음 + status=pending → 승인 대기 화면
    │   "가입 승인을 기다리고 있습니다."
    │   로그아웃 버튼만 표시
    │
    ├─ Membership 있음 + status=rejected → 거절 안내 화면
    │   "가입 요청이 거절되었습니다. 관리자에게 문의하세요."
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

#### Owner의 멤버 승인

조직 관리 페이지에서:
- 승인 대기 목록 표시 (이름, 요청일, 승인/거절 버튼)
- 승인 → Membership.status = active, 사용자에게 알림
- 거절 → Membership.status = rejected, 사용자에게 알림
- owner가 이후 재초대하려면: 해당 Membership 삭제 후 새 초대코드 발급

### 1.5 역할별 빈 화면 CTA

| 화면 | Owner | Consultant |
|------|-------|-----------|
| 대시보드 | "고객사를 등록하고 첫 프로젝트를 시작하세요" + 고객사 등록 버튼 | "배정된 프로젝트가 없습니다. 관리자가 프로젝트를 배정하면 여기에 표시됩니다." |
| 프로젝트 목록 | "새 프로젝트 만들기" 버튼 | "배정된 프로젝트가 없습니다." |
| 고객사 목록 | "첫 고객사를 등록하세요" + 등록 버튼 | "등록된 고객사가 없습니다." |
| 프로젝트 > 컨택 탭 | "후보자를 서칭하고 컨택을 시작하세요" + 서칭 탭 이동 | 동일 |
| 프로젝트 > 추천 탭 | "컨택에서 관심 후보자가 생기면 추천서류를 작성할 수 있습니다." | 동일 |

### 1.6 _get_org 헬퍼 통합 및 수정

현재 `_get_org(request)`는 `projects/views.py`와 `clients/views.py`에 동일 함수가 중복 정의되어 있다. 이를 `accounts/helpers.py`로 추출하여 단일 소스로 통합한다.

```python
# accounts/helpers.py
def _get_org(request):
    return get_object_or_404(
        Organization,
        memberships__user=request.user,
        memberships__status='active'
    )
```

`projects/views.py`와 `clients/views.py`에서 `from accounts.helpers import _get_org`로 임포트한다.

pending 상태 사용자가 _get_org를 호출하는 view에 도달하면 404 → `membership_required` 데코레이터에서 사전 차단하므로 이 경우는 발생하지 않는다.

### 1.7 접근 제어 구현 방식

```python
# accounts/decorators.py

@membership_required
# Membership 없음 → /accounts/invite/ 리다이렉트
# Membership.status=pending → /accounts/pending/ 리다이렉트
# Membership.status=rejected → /accounts/rejected/ 리다이렉트
# Membership.status=active → 통과

@role_required('owner')
# membership.role != 'owner' → 403 또는 리다이렉트
```

데코레이터를 적용하지 않은 view (login, logout, invite_code, pending_approval, rejected, terms, privacy)는 자연히 접근 제어에서 제외된다.

```python
# View 예시
@login_required
@membership_required
@role_required('owner')
def client_create(request):
    ...

# 템플릿 분기
{% if membership.role == 'owner' %}
  <a href="...">새 고객사 등록</a>
{% endif %}

# 프로젝트 쿼리셋 필터링 (accounts/context_processors.py에서 membership 주입)
if membership.role == 'owner':
    projects = Project.objects.filter(organization=org)
else:
    projects = Project.objects.filter(assigned_consultants=request.user)
```

### 1.8 context_processors

```python
# accounts/context_processors.py
def membership(request):
    """모든 템플릿에 membership 정보 주입."""
    if not request.user.is_authenticated:
        return {}
    try:
        m = request.user.membership
        if m.status == 'active':
            return {'membership': m}
    except Membership.DoesNotExist:
        pass
    return {}
```

`main/settings.py`의 `context_processors` 목록에 `accounts.context_processors.membership` 추가.

---

<!-- forge:phase1:설계담금질:complete:2026-04-12T01:30:00+09:00 -->
