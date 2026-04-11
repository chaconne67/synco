# Task 3: 카카오 로그인 플로우 수정 + 온보딩 화면

> **출처:** `docs/forge/headhunting-onboarding/phase1/design-spec-agreed.md`
> **선행 조건:** Task 1 (InviteCode 모델, Membership.status) -- 구현 완료, Task 2 (데코레이터, context processor, _get_org 통합) -- 구현 완료

---

## 배경

현재 synco는 카카오 로그인 후 Organization/Membership이 없으면 대시보드 404가 발생한다. 초대코드 기반 온보딩 플로우를 구현하여, Membership이 없는 사용자를 초대코드 입력 화면으로 안내하고, 역할에 따라 즉시 활성화(owner) 또는 승인 대기(consultant)로 분기해야 한다.

---

## 요구사항

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

### 화면 목록

1. **초대코드 입력 화면** (`/accounts/invite/`) -- 코드 입력 폼, 오류 메시지 표시, 로그아웃 링크
2. **승인 대기 화면** (`/accounts/pending/`) -- 대기 안내 메시지, 로그아웃 버튼만
3. **거절 안내 화면** (`/accounts/rejected/`) -- 거절 안내 메시지, 로그아웃 버튼만

### 루트 URL 리다이렉션

`/` 접근 시 Membership 상태에 따라 적절한 화면으로 리다이렉트한다.

---

## 제약사항

- Task 1에서 추가한 InviteCode 모델과 Membership.status 필드를 사용한다.
- Task 2에서 생성한 `membership_required` 데코레이터 패턴과 일관성을 유지한다.
- 온보딩 화면(invite, pending, rejected)에는 접근 제어 데코레이터를 적용하지 않는다.
- 모든 온보딩 화면은 `@login_required`만 적용한다.
