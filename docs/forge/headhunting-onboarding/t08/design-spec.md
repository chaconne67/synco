# Task 8: 프로젝트 생성 시 담당 컨설턴트 지정

> **출처:** `docs/forge/headhunting-onboarding/phase1/design-spec-agreed.md`
> **선행 조건:** Task 1, 2 (구현 완료), Task 5 (기존 view에 권한 데코레이터 적용), Task 6 (프로젝트 목록 consultant 필터링)

---

## 배경

RBAC 도입으로 consultant는 배정된 프로젝트만 볼 수 있게 되었다(Task 6). 프로젝트 생성 시 owner가 담당 컨설턴트를 지정할 수 있어야 한다. 지정하지 않으면 프로젝트 생성자(owner)가 기본 담당자로 설정된다.

---

## 요구사항

### 프로젝트 생성 폼

- `assigned_consultants` 필드 추가 (ModelMultipleChoiceField, CheckboxSelectMultiple)
- 선택지는 같은 조직의 active 멤버만 표시
- 선택하지 않으면 프로젝트 생성자가 기본 담당자로 지정

### 권한

- 프로젝트 생성은 owner만 가능 (Task 5에서 `@role_required("owner")` 적용 전제)

### 프로젝트 수정 폼

- 프로젝트 수정 시에도 담당 컨설턴트 변경 가능 (동일 로직)

---

## 제약사항

- `assigned_consultants` M2M 필드는 기존 Project 모델에 이미 존재한다.
- 폼 초기화 시 `org` 파라미터를 받아 조직별 멤버 필터링을 수행한다.
- 프로젝트 생성자가 consultant를 지정하지 않을 경우, 기본값으로 생성자를 할당한다.
