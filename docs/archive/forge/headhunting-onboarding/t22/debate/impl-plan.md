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

- [ ] **Step 1: 예정 목록 "결과 기록" 버튼 확인**

현재 `tab_contacts.html` (라인 96-98)에 이미 "결과 기록" 버튼이 있다:
```html
          <button hx-get="{% url 'projects:contact_create' project.pk %}?candidate={{ contact.candidate.pk }}"
                  hx-target="#contact-form-area"
                  class="text-[13px] text-primary hover:text-primary-dark">결과 기록</button>
```

이 버튼의 라벨을 "컨택 등록"으로 변경하고, 더 눈에 띄는 스타일로 변경한다.

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
                  class="text-[13px] bg-primary text-white px-2.5 py-1 rounded-md hover:bg-primary-dark transition">컨택 등록</button>
```

- [ ] **Step 2: 수동 검증**

컨택 탭의 예정 목록에서 "컨택 등록" 버튼이 표시되고, 클릭 시 해당 후보자가 프리필된 컨택 폼이 열리는지 확인한다.

- [ ] **Step 3: 커밋**

```bash
git add projects/templates/projects/partials/tab_contacts.html
git commit -m "feat(projects): rename reserved contact button to '컨택 등록' with emphasized style"
```

<!-- forge:t22:구현계획:draft:2026-04-12 -->
