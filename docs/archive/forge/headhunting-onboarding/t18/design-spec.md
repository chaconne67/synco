# t18: email_disconnect 리다이렉트 수정 + 최종 통합 테스트

> **Phase:** 2단계 — 통합 설정 + 조직 관리
> **선행 조건:** t13 (설정 탭 URL + 뷰), t14 (설정 탭 템플릿)

---

## 배경

설정 탭 통합 후, 기존 이메일 관련 뷰의 리다이렉트 경로를 새로운 설정 탭 URL로 업데이트해야 한다. 또한 전체 테스트 스위트를 실행하여 2단계 변경이 기존 기능을 깨뜨리지 않았는지 확인한다.

---

## 요구사항

### email_disconnect 리다이렉트 수정

- `email_disconnect` 뷰의 리다이렉트 대상을 `/accounts/settings/email/` (`settings_email`)로 변경

### email_settings HTMX 대응

- `email_settings` POST 처리 시 HTMX 요청이면 `settings_email.html` 파셜로 응답
- 일반 요청이면 기존 `email_settings.html` 전체 페이지로 응답 (하위 호환)

### 최종 통합 테스트

- 전체 테스트 스위트 실행: `uv run pytest -v --timeout=30`
- 기존 테스트 + 2단계 신규 테스트 모두 통과 확인

---

## 제약

- 기존 `email_settings.html` 전체 페이지 뷰는 유지 (직접 URL 접근 시 하위 호환)
- OAuth 콜백(`/accounts/email/callback/`) 완료 후 `/accounts/settings/email/`로 리다이렉트 (t13에서 처리)
