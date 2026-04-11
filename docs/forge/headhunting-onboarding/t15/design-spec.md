# t15: 조직 관리 뷰 + URL + 테스트

> **Phase:** 2단계 — 통합 설정 + 조직 관리
> **선행 조건:** t12 (forms.py), 1단계 RBAC (t01-t10)

---

## 배경

현재 owner가 멤버 초대/승인/역할변경/제거를 하려면 Django admin에 들어가야 한다. 초대코드 생성도 admin에서만 가능하다. owner용 조직 관리 UI를 구축하여 이 문제를 해결한다.

---

## 요구사항

### 접근 권한

owner만 접근 가능. `@login_required` + `@role_required('owner')` 적용.

### URL 구조

```
/org/                              -> 조직 정보 탭으로 리다이렉트
/org/info/                         -> 조직 정보 탭
/org/members/                      -> 멤버 관리 탭
/org/members/<pk>/approve/         -> 멤버 승인 (POST)
/org/members/<pk>/reject/          -> 멤버 거절 (POST)
/org/members/<pk>/role/            -> 역할 변경 (POST)
/org/members/<pk>/remove/          -> 멤버 제거 (POST)
/org/invites/                      -> 초대코드 관리 탭
/org/invites/create/               -> 초대코드 생성 (POST)
/org/invites/<pk>/deactivate/      -> 초대코드 비활성화 (POST)
```

### 조직 정보 탭 (`/org/info/`)

조직 기본 정보 조회/수정:

| 필드 | 수정 가능 |
|------|----------|
| 조직명 | O |
| 로고 | O |
| 플랜 (BASIC/STANDARD/PREMIUM/PARTNER) | X (admin만) |
| DB 공유 | X (admin만) |

HTMX POST로 인라인 저장.

### 멤버 관리 탭 (`/org/members/`)

멤버 목록 + 액션:

**승인 대기 멤버:**
- 승인 -> `Membership.status = 'active'`
- 거절 -> `Membership.status = 'rejected'`

**활성 멤버:**
- 역할 변경: consultant <-> viewer 전환 가능. owner 역할은 변경 불가.
- 제거: Membership 삭제. 제거된 사용자는 다음 로그인 시 초대코드 입력 화면으로 이동.

**제약:**
- owner는 자기 자신을 제거하거나 역할 변경할 수 없다.
- 조직에 owner가 1명뿐이면 해당 owner는 제거 불가.

### 초대코드 관리 탭 (`/org/invites/`)

초대코드 생성/관리:
- 생성 폼: 역할, 최대 사용 횟수, 만료일
- 목록: 코드, 역할, 사용/최대, 만료일, 상태, 액션(비활성화/복사)
- 생성 시 `InviteCode.created_by = request.user` 설정

---

## 제약

- `main/urls.py`에 `/org/` URL include 추가 필요
- `accounts/urls_org.py` 신규 생성
- `accounts/views_org.py` 신규 생성
- `accounts/helpers.py`의 `_get_org` 함수와 `accounts/decorators.py`의 `role_required` 데코레이터 활용
