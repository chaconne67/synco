# t12: accounts/forms.py 생성

> **Phase:** 2단계 — 통합 설정 + 조직 관리
> **선행 조건:** t11 (NotificationPreference 모델)

---

## 배경

2단계에서 통합 설정 페이지와 조직 관리 UI를 구축하려면, 다음 폼 클래스가 필요하다:

1. **OrganizationForm** — owner가 조직 정보(이름, 로고)를 수정하는 폼
2. **InviteCodeCreateForm** — owner가 초대코드를 생성하는 폼
3. **NotificationPreferenceForm** — 사용자가 알림 설정을 변경하는 폼

현재 `accounts/forms.py`가 없으므로 새로 생성한다.

---

## 요구사항

### OrganizationForm

- ModelForm 기반, `Organization` 모델 사용
- 수정 가능 필드: `name`, `logo`
- Tailwind CSS 스타일 위젯 적용

### InviteCodeCreateForm

- 일반 Form (ModelForm이 아님)
- 필드:
  - `role`: consultant / viewer 선택 (기본값: consultant)
  - `max_uses`: 1~100 정수 (기본값: 1)
  - `expires_at`: 날짜 선택 (선택 사항, 무기한 가능)

### NotificationPreferenceForm

- 일반 Form
- JSONField를 개별 체크박스로 분리하여 표현
- 알림 유형 4가지 x 채널 2가지 = 8개 BooleanField
- `load_from_preferences(dict)`: JSON -> form initial values 변환
- `to_preferences()`: form cleaned_data -> JSON dict 변환

---

## 제약

- owner만 admin에서 owner 역할 발급 가능. InviteCodeCreateForm의 role 선택지에는 owner를 포함하지 않는다.
- 위젯 클래스는 프로젝트의 기존 Tailwind 스타일(`text-[14px]`, `rounded-lg`, `focus:ring-2` 등)과 일관되게 적용한다.
