# 2단계: 통합 설정 + 조직 관리

> **작성일:** 2026-04-12
> **범위:** 분산된 설정 페이지 통합 + owner용 조직/멤버 관리 UI
> **선행 조건:** 1단계 (RBAC + 온보딩) 구현 완료

---

## 배경

1단계에서 역할 체계(owner/consultant/viewer)와 초대코드 기반 온보딩이 도입되었다.
그러나 다음 문제가 남아 있다:

1. **설정 분산** — 프로필(`/accounts/settings/`), Gmail(`/accounts/email/*`), 텔레그램(`/telegram/*`)이 각각 별도 URL에 흩어져 있어 사용자가 설정을 관리하려면 3곳을 돌아다녀야 한다.
2. **조직 관리 UI 없음** — owner가 멤버 초대/승인/역할변경/제거를 하려면 Django admin에 들어가야 한다. 초대코드 생성도 admin에서만 가능하다.

---

## 2.1 통합 설정 페이지

### 현재 구조 (분산)

| 기능 | URL | 앱 |
|------|-----|-----|
| 프로필 (이름, 소속, 전화번호) | `/accounts/settings/` | accounts |
| Gmail 연동 (OAuth, 필터) | `/accounts/email/connect/`, `/email/settings/` 등 | accounts |
| 텔레그램 연동 (코드 인증) | `/telegram/bind/`, `/unbind/`, `/test/` | projects |
| 알림 설정 | 미구현 ("준비 중" 표시) | - |

### 목표 구조 (통합)

`/accounts/settings/` 단일 URL 아래에 탭으로 통합한다.

```
/accounts/settings/           → 기본 탭(프로필)으로 리다이렉트
/accounts/settings/profile/   → 프로필 탭
/accounts/settings/email/     → Gmail 연동 탭
/accounts/settings/telegram/  → 텔레그램 연동 탭
/accounts/settings/notify/    → 알림 설정 탭
```

**탭 전환:** HTMX `hx-get` + `hx-target="#settings-content"` 방식.
프로젝트 상세 탭 전환 패턴과 동일하게 구현한다.

### 각 탭 상세

#### 프로필 탭 (`/accounts/settings/profile/`)

기존 `settings_content.html` 내용을 그대로 유지한다:
- 이름 (user.first_name)
- 소속 (user.company_name)
- 전화번호 (user.phone)
- 앱 정보 (버전, 이용약관, 개인정보처리방침)
- 로그아웃

변경점: "알림 설정" 항목 제거 → 별도 탭으로 이동.

#### Gmail 연동 탭 (`/accounts/settings/email/`)

기존 `email_settings_content.html`을 그대로 사용한다.
기능: OAuth 연결/해제, 필터 설정 (발신자, 라벨), 활성/비활성 토글.

변경점:
- 기존 `/accounts/email/settings/` URL은 유지하되, 설정 페이지 내 탭에서 접근하도록 진입점 통합.
- OAuth 콜백(`/accounts/email/callback/`)은 완료 후 `/accounts/settings/email/`로 리다이렉트.

#### 텔레그램 연동 탭 (`/accounts/settings/telegram/`)

기존 `telegram_bind.html`을 파셜로 분리하여 탭 내에서 렌더링한다.
기능: 6자리 코드 생성 → Bot에 `/start {code}` → 연동 완료, 테스트 메시지, 연동 해제.

변경점:
- 기존 `/telegram/bind/` URL은 유지 (내부 API).
- 설정 페이지 탭에서 HTMX로 호출하는 진입점 추가.

#### 알림 설정 탭 (`/accounts/settings/notify/`)

현재 "준비 중" 상태. 이 단계에서는 기본 구조만 만든다:

| 알림 유형 | 웹 | 텔레그램 |
|----------|-----|---------|
| 새 컨택 결과 | O/X | O/X |
| 추천 피드백 | O/X | O/X |
| 프로젝트 승인 요청 | O/X | O/X |
| 뉴스피드 업데이트 | O/X | O/X |

모델: `accounts.models.NotificationPreference` (OneToOne with User)
- `preferences`: JSONField — `{"contact_result": {"web": true, "telegram": true}, ...}`

> **Note:** 알림 발송 로직 자체는 이 단계에서 구현하지 않는다. UI와 모델만 준비한다.

### 사이드바 변경

"설정" 메뉴 클릭 시 `/accounts/settings/profile/`로 이동 (기존과 동일 진입점).

---

## 2.2 조직 관리 페이지

### 접근 권한

owner만 접근 가능. `@login_required` + `@membership_required` + `@role_required('owner')` 적용.
사이드바에 "조직 관리" 메뉴 추가 (owner에게만 표시 — 1단계 사이드바 필터링 활용).

### URL 구조

```
/org/                   → 조직 정보 탭으로 리다이렉트
/org/info/              → 조직 정보 탭
/org/members/           → 멤버 관리 탭
/org/invites/           → 초대코드 관리 탭
```

### 조직 정보 탭 (`/org/info/`)

조직 기본 정보를 조회/수정한다.

| 필드 | 타입 | 수정 가능 |
|------|------|----------|
| 조직명 | 텍스트 | O |
| 로고 | 파일 업로드 | O |
| 플랜 | 표시만 (BASIC/STANDARD/PREMIUM/PARTNER) | X (admin만 변경) |
| DB 공유 | 표시만 | X (admin만 변경) |

**폼 제출:** HTMX POST, 인라인 저장.

### 멤버 관리 탭 (`/org/members/`)

조직 소속 멤버 목록을 관리한다.

#### 멤버 목록

| 이름 | 역할 | 상태 | 가입일 | 액션 |
|------|------|------|--------|------|
| 김사장 | owner | 활성 | 2026-01-15 | - |
| 이컨설턴트 | consultant | 활성 | 2026-02-01 | 역할변경 / 제거 |
| 박대기 | consultant | 승인대기 | 2026-04-10 | 승인 / 거절 |

#### 액션 상세

**승인 대기 멤버:**
- 승인 → `Membership.status = 'active'`, 텔레그램/웹 알림 발송
- 거절 → `Membership.status = 'rejected'`, 알림 발송

**활성 멤버:**
- 역할 변경 → consultant ↔ viewer 전환 가능. owner 역할은 변경 불가.
- 제거 → Membership 삭제. 확인 다이얼로그 필수.
  제거된 사용자는 다음 로그인 시 초대코드 입력 화면으로 이동한다.

**제약:**
- owner는 자기 자신을 제거하거나 역할 변경할 수 없다.
- 조직에 owner가 1명뿐이면 해당 owner는 제거 불가.

### 초대코드 관리 탭 (`/org/invites/`)

owner가 초대코드를 생성/관리한다.

#### 초대코드 목록

| 코드 | 역할 | 사용/최대 | 만료일 | 상태 | 액션 |
|------|------|----------|--------|------|------|
| A3K9B7X2 | consultant | 2/10 | 2026-05-01 | 활성 | 비활성화 / 복사 |
| F7J2M8Q1 | consultant | 1/1 | - | 소진 | - |

#### 초대코드 생성 폼

| 필드 | 설명 | 기본값 |
|------|------|--------|
| 역할 | consultant / viewer (owner는 admin만 발급 가능) | consultant |
| 최대 사용 횟수 | 1~100 | 1 |
| 만료일 | 날짜 선택 (선택) | 없음 (무기한) |

생성 시 `InviteCode.created_by = request.user` 설정.

#### 코드 복사

"복사" 버튼 클릭 → 클립보드에 코드 복사. JavaScript `navigator.clipboard.writeText()` 사용.

---

## 2.3 앱별 변경 영향

### accounts 앱

- `models.py`: `NotificationPreference` 모델 추가
- `views.py`: 설정 탭 뷰 추가 (profile/email/telegram/notify), 조직 관리 뷰 추가
- `urls.py`: 설정 탭 URL + 조직 관리 URL 추가
- `forms.py`: `OrganizationForm`, `InviteCodeCreateForm`, `NotificationPreferenceForm` 추가
- `templates/`: 설정 탭 템플릿, 조직 관리 템플릿 추가

### projects 앱

- `views_telegram.py`: 텔레그램 설정 파셜 뷰 추가 (기존 bind 로직 재활용)
- `urls_telegram.py`: 설정 탭용 파셜 URL 추가

### templates/common

- `nav_sidebar.html`: "조직 관리" 메뉴 추가 (owner 조건부)
- `nav_bottom.html`: 모바일도 동일 반영

### main

- `urls.py`: `/org/` URL include 추가

---

<!-- forge:phase2:설계초안:draft:2026-04-12 -->
