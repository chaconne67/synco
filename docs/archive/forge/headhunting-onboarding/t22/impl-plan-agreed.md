# t22: 예정 목록에 "컨택 등록" 버튼 추가

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 컨택 탭 예정 목록의 "결과 기록" 버튼을 "컨택 등록"으로 변경하고 스타일을 강조 버튼으로 바꿔 워크플로우 전환을 명시적으로 안내한다.

**Design spec:** `docs/forge/headhunting-onboarding/t22/design-spec.md`

**depends_on:** 없음

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/templates/projects/partials/tab_contacts.html` | 수정 | 예정 목록 버튼 라벨 "결과 기록" → "컨택 등록", 스타일 강조 |

---

## Tempering Decisions

| ID | 결정 | 변경 내용 |
|----|------|----------|
| R1-01 | ACCEPTED | 스타일을 상단 버튼과 동일 규격(px-3 py-1.5 rounded-lg)으로 통일 |
| R1-02 | PARTIAL | Step 2 검증에 레이아웃 확인 항목 추가 (긴 이름, 좁은 viewport) |
| R1-03 | REBUTTED | "+" prefix와 위치 맥락으로 충분히 차별화됨 |
| R1-04 | REBUTTED | 주 행동 vs 파괴적 행동의 의도적 위계 차이 |
| R1-05 | ACCEPTED | 라인 번호를 105-107로 수정 |

---

- [ ] **Step 1: 예정 목록 "결과 기록" 버튼 변경**

현재 `tab_contacts.html` (라인 105-107)에 이미 "결과 기록" 버튼이 있다:
```html
          <button hx-get="{% url 'projects:contact_create' project.pk %}?candidate={{ contact.candidate.pk }}"
                  hx-target="#contact-form-area"
                  class="text-[13px] text-primary hover:text-primary-dark">결과 기록</button>
```

이 버튼의 라벨을 "컨택 등록"으로 변경하고, 상단 버튼과 동일한 규격의 강조 스타일로 변경한다.

현재:
```html
          <button hx-get="{% url 'projects:contact_create' project.pk %}?candidate={{ contact.candidate.pk }}"
                  hx-target="#contact-form-area"
                  class="text-[13px] text-primary hover:text-primary-dark">결과 기록</button>
```

변경:
```html
          <button hx-get="{% url 'projects:contact_create' project.pk %}?candidate={{ contact.candidate.pk }}"
                  hx-target="#contact-form-area"
                  class="text-[13px] bg-primary text-white px-3 py-1.5 rounded-lg hover:bg-primary-dark transition">컨택 등록</button>
```

> **Note:** 스타일은 상단 "+ 컨택 등록" 버튼과 동일한 규격(px-3 py-1.5 rounded-lg)을 사용한다 (R1-01 반영).

- [ ] **Step 2: 수동 검증**

컨택 탭의 예정 목록에서 다음을 확인한다:
1. "컨택 등록" 버튼이 표시되고, 클릭 시 해당 후보자가 프리필된 컨택 폼이 열리는지 확인
2. 긴 후보자명(10자 이상)이 있는 행에서 레이아웃이 깨지지 않는지 확인
3. 좁은 viewport(모바일 폭)에서 버튼이 밀리거나 겹치지 않는지 확인
4. "잠금 해제" 버튼이 함께 표시되는 행에서 두 버튼이 정상적으로 나란히 표시되는지 확인

> **Note:** 레이아웃 검증 항목(2-4)은 R1-02 반영. 레이아웃 문제가 발견되면 별도 할일로 처리.

- [ ] **Step 3: 커밋**

```bash
git add projects/templates/projects/partials/tab_contacts.html
git commit -m "feat(projects): rename reserved contact button to '컨택 등록' with emphasized style"
```

<!-- forge:t22:impl-plan:complete:2026-04-13T01:20:00+09:00 -->
