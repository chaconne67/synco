# t13: 설정 탭 URL + 뷰 통합

> **Phase:** 2단계 — 통합 설정 + 조직 관리
> **선행 조건:** t11 (NotificationPreference 모델), t12 (forms.py)

---

## 배경

현재 설정 관련 페이지가 3곳에 분산되어 있다:

| 기능 | URL | 앱 |
|------|-----|-----|
| 프로필 (이름, 소속, 전화번호) | `/accounts/settings/` | accounts |
| Gmail 연동 (OAuth, 필터) | `/accounts/email/connect/`, `/email/settings/` 등 | accounts |
| 텔레그램 연동 (코드 인증) | `/telegram/bind/`, `/unbind/`, `/test/` | projects |

사용자가 설정을 관리하려면 3곳을 돌아다녀야 한다. 이를 단일 URL 아래 탭으로 통합한다.

---

## 요구사항

### URL 구조

```
/accounts/settings/           -> 기본 탭(프로필)으로 리다이렉트
/accounts/settings/profile/   -> 프로필 탭
/accounts/settings/email/     -> Gmail 연동 탭
/accounts/settings/telegram/  -> 텔레그램 연동 탭
/accounts/settings/notify/    -> 알림 설정 탭
```

### 탭 전환 방식

HTMX `hx-get` + `hx-target="#settings-content"` 방식.
프로젝트 상세 탭 전환 패턴(`detail_tab_bar.html`)과 동일하게 구현한다.

- HTMX 요청 시: 파셜 템플릿만 반환
- 일반 요청 시: 전체 페이지(settings.html + 해당 탭 파셜) 반환

### 각 탭 뷰 동작

**프로필 탭** (`settings_profile`):
- 기존 `settings_content.html` 렌더링

**이메일 탭** (`settings_email`):
- `EmailMonitorConfig` 조회 후 이메일 설정 파셜 렌더링

**텔레그램 탭** (`settings_telegram`):
- `TelegramBinding` 조회 후 텔레그램 설정 파셜 렌더링
- `projects/views_telegram.py`에 `telegram_bind_partial` 뷰 추가 (기존 bind 로직 재활용)

**알림 설정 탭** (`settings_notify`):
- GET: `NotificationPreference` 조회/생성 후 폼 렌더링
- POST: 폼 검증 후 preferences 저장

### 기존 URL 호환

- 기존 `/accounts/email/*` URL은 그대로 유지 (OAuth 플로우)
- OAuth 콜백 완료 후 `/accounts/settings/email/`로 리다이렉트

---

## 제약

- `@login_required` 데코레이터 필수 (모든 설정 탭)
- `settings_page` 기존 뷰는 `settings_profile`로 리다이렉트하도록 변경
