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
| 승인 큐 | O | 본인 요청만 | X |
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

### 1.4 온보딩 플로우

#### 슈퍼관리자 사전 작업 (Django admin)

1. Organization 생성 (이름, plan, db_share_enabled)
2. owner용 초대코드 1개 생성 → 고객사 대표에게 전달

#### 초대코드 모델

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

조직 관리 > 멤버 탭에서:
- 승인 대기 목록 표시 (이름, 요청일, 승인/거절 버튼)
- 승인 → Membership.status = active, 사용자에게 알림
- 거절 → Membership 삭제, 사용자에게 알림

### 1.5 역할별 빈 화면 CTA

| 화면 | Owner | Consultant |
|------|-------|-----------|
| 대시보드 | "고객사를 등록하고 첫 프로젝트를 시작하세요" + 고객사 등록 버튼 | "배정된 프로젝트가 없습니다. 관리자가 프로젝트를 배정하면 여기에 표시됩니다." |
| 프로젝트 목록 | "새 프로젝트 만들기" 버튼 | "배정된 프로젝트가 없습니다." |
| 고객사 목록 | "첫 고객사를 등록하세요" + 등록 버튼 | "등록된 고객사가 없습니다." |
| 프로젝트 > 컨택 탭 | "후보자를 서칭하고 컨택을 시작하세요" + 서칭 탭 이동 | 동일 |
| 프로젝트 > 추천 탭 | "컨택에서 관심 후보자가 생기면 추천서류를 작성할 수 있습니다." | 동일 |

### 1.6 _get_org 헬퍼 수정

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

### 1.7 접근 제어 구현 방식

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

## 2단계: 설정 및 조직 관리

### 2.1 사용자 설정 (모든 역할 공통)

프로젝트 상세의 HTMX 탭 패턴 재활용. 3탭 구조.

**프로필 탭:**
- 이름 (편집 가능)
- 전화번호 (편집 가능)
- 회사명 (읽기 전용 — Organization.name)

**연동 탭:**
- 카카오 (연결됨 — 읽기 전용)
- Gmail [연결하기] / [연결됨 | 해제]
- 텔레그램 [연결하기] / [연결됨 | 해제]

**알림 탭:**
- 웹 알림: on/off
- 텔레그램 알림: on/off (텔레그램 미연동 시 비활성)
- 알림 종류별 세부 설정 (확장 가능 구조)
  - 승인 요청/결과
  - 프로젝트 배정
  - 리컨택 알림
  - 면접 일정 알림

### 2.2 조직 관리 (owner만)

별도 사이드바 메뉴. 탭 구조로 확장 가능.

**기본정보 탭:**
- 조직명 (편집)
- 로고 (업로드)
- 테마 색상 (향후 확장)

**멤버 탭:**
- 직원 초대코드 생성 버튼
- 활성 초대코드 목록 (링크 복사, 비활성화)
- 승인 대기 (승인/거절)
- 멤버 목록 (역할, 상태, 연동현황)

**향후 확장 예정 탭:**
- 업무 현황 — 컨설턴트별 진행 프로젝트, 컨택/추천 수
- 성과 리포트 — 기간별 KPI, 전환율
- 조직 설정 — DB 공유, plan 정보 (읽기 전용)

### 2.3 현재와의 변경점

| 현재 | 변경 |
|------|------|
| 설정 페이지 단일, 프로필 표시만 | 3탭 구조, 프로필 편집 가능 |
| Gmail 설정 별도 URL | 연동 탭으로 통합 |
| 텔레그램 바인딩 별도 URL | 연동 탭으로 통합 |
| 알림 "준비 중" placeholder | 실제 on/off 설정 |
| 조직 관리 UI 없음 | 별도 메뉴로 신규 생성 |
| Membership에 status 필드 없음 | status(active/pending/rejected) 추가 |

---

## 3단계: 워크플로우 연결 보강

### 3.1 컨택 "관심" → 추천서류 CTA

컨택 결과를 "관심"으로 저장한 직후, 응답에 다음 액션 안내를 포함:

```
┌──────────────────────────────────────────┐
│ ✓ 컨택 결과가 저장되었습니다.               │
│                                          │
│ 홍길동(ABC전자 과장)님이 관심을 보였습니다.   │
│ [추천서류 작성하기 →]  [닫기]               │
└──────────────────────────────────────────┘
```

- "추천서류 작성하기" → Submission 생성 페이지 (후보자+프로젝트 자동 선택)
- "닫기" → 컨택 목록으로 복귀
- "관심" 이외의 결과에서는 CTA 없음

### 3.2 대시보드 액션 → 프로젝트 상세 드릴다운

대시보드 "오늘의 액션" 클릭 시 해당 프로젝트의 관련 탭으로 직접 이동:

- 리컨택 예정 → 프로젝트/컨택 탭
- 서류 미피드백 → 프로젝트/추천 탭
- 면접 일정 → 프로젝트/면접 탭

### 3.3 프로젝트 생성 시 담당자 지정

프로젝트 생성/수정 폼에 담당 컨설턴트 선택 필드 추가:

- 복수 선택 가능 (기존 `consultants` M2M 필드 활용)
- owner만 이 필드가 보임
- 미지정 시 owner 본인이 기본 담당
- 생성 후에도 프로젝트 수정에서 담당자 변경/추가 가능

---

## 대시보드 역할별 분화

### Owner 대시보드

```
├─ 승인 대기 알림 (멤버 승인 N건, 프로젝트 승인 N건)
├─ 전체 파이프라인 요약 (프로젝트 상태별 개수)
├─ 팀 현황 테이블 (컨설턴트별 진행 프로젝트/컨택/추천/면접 수)
├─ 최근 활동 로그 (전 조직원)
└─ 금주 일정 (전체 면접/리컨택)
```

### Consultant 대시보드

```
├─ 오늘의 액션 (내 프로젝트 긴급도별)
├─ 내 파이프라인 요약 (내 프로젝트만)
├─ 최근 활동 로그 (내 것만)
└─ 금주 일정 (내 면접/리컨택만)
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

# Organization: 테마 관련 필드 (향후 확장용, 2단계)
# 현재 plan, db_share_enabled, logo는 이미 존재
```

---

## 구현 순서

| 단계 | 범위 | 선행 |
|------|------|------|
| 1-1 | InviteCode 모델 + Membership.status 추가, 마이그레이션 | 없음 |
| 1-2 | 카카오 로그인 플로우 수정 (초대코드 입력 화면, 승인 대기 화면) | 1-1 |
| 1-3 | role_required 데코레이터, 기존 view 전체에 권한 체크 추가 | 1-1 |
| 1-4 | 사이드바 역할별 메뉴 필터링 | 1-3 |
| 1-5 | 프로젝트 목록 consultant 필터링 (배정된 것만) | 1-3 |
| 1-6 | 빈 화면 CTA (역할별 분기) | 1-4 |
| 2-1 | 사용자 설정 3탭 (프로필 편집, 연동 통합, 알림) | 1-3 |
| 2-2 | 조직 관리 (기본정보, 멤버/초대코드/승인) | 1-1 |
| 3-1 | 컨택 "관심" → 추천서류 CTA | 1-3 |
| 3-2 | 대시보드 드릴다운 링크 | 없음 |
| 3-3 | 프로젝트 폼에 담당 컨설턴트 필드 | 1-3 |
| 3-4 | 대시보드 역할별 분화 | 1-3, 1-5 |
