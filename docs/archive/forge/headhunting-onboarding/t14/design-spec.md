# t14: 설정 탭 템플릿 구현

> **Phase:** 2단계 — 통합 설정 + 조직 관리
> **선행 조건:** t13 (설정 탭 URL + 뷰 통합)

---

## 배경

t13에서 설정 탭의 URL과 뷰를 구성했다. 이 태스크에서는 실제 렌더링할 템플릿을 구현한다.

기존 `settings.html`을 탭 바 + 콘텐츠 컨테이너 구조로 변경하고, 각 탭에 해당하는 파셜 템플릿을 생성한다.

---

## 요구사항

### settings.html 구조 변경

기존 단일 페이지를 다음 구조로 변경:

```
settings.html
  ├── settings_tab_bar.html  (프로필 | 이메일 | 텔레그램 | 알림)
  └── #settings-content
       └── (각 탭 파셜)
```

### 탭 바 (`settings_tab_bar.html`)

- 4개 탭 버튼: 프로필, 이메일, 텔레그램, 알림
- `hx-get` + `hx-target="#settings-content"` + `hx-push-url="true"`
- 활성 탭: `border-primary text-primary` 스타일
- 비활성 탭: `border-transparent text-gray-500` 스타일

### 프로필 탭 (`settings_content.html`)

기존 내용 유지, "알림 설정" 항목 제거 (별도 탭으로 이동):
- 내 정보 섹션 (이름, 소속, 전화번호)
- 앱 정보 섹션 (버전, 이용약관, 개인정보처리방침)
- 로그아웃

### 이메일 탭 (`settings_email.html`)

기존 `email_settings_content.html` 내용을 재활용하되 페이지 헤더/뒤로가기 버튼 제거:
- 연결 상태 (활성/비활성)
- 필터 설정 폼 (발신자 필터, 모니터링 토글)
- 연결 해제 버튼
- 미연결 시: 연결 안내 + 연결 버튼

### 텔레그램 탭 (`settings_telegram.html`)

기존 `telegram_bind.html` 내용을 파셜로 분리:
- 연동됨: 연동 상태, 테스트 메시지 버튼, 연동 해제 버튼
- 미연동: 연결 안내 + 6자리 코드 생성 버튼
- 코드 생성 시: 코드 표시 + 만료 시간 안내

### 알림 설정 탭 (`settings_notify.html`)

알림 유형별 웹/텔레그램 체크박스 그리드:

| 알림 유형 | 웹 | 텔레그램 |
|----------|-----|---------|
| 새 컨택 결과 | O/X | O/X |
| 추천 피드백 | O/X | O/X |
| 프로젝트 승인 요청 | O/X | O/X |
| 뉴스피드 업데이트 | O/X | O/X |

저장 버튼은 HTMX POST로 `#settings-content`에 결과 반영.

---

## 제약

- HTMX 요청과 일반 요청 모두 지원 (`request.htmx` 분기)
- 기존 Tailwind 스타일과 일관성 유지
- 사이드바 "설정" 메뉴 클릭 시 `/accounts/settings/profile/`로 이동 (기존과 동일 진입점)
