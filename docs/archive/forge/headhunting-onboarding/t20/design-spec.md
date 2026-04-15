# t20: submission_create() 성공 시 추천 탭 자동 전환

> **Phase:** 3 — 워크플로우 연결
> **선행 조건:** t19 (tabChanged 이벤트 시스템)

---

## 배경

현재 추천 서류를 등록하면 `submission_create()` 뷰가 `204 + HX-Trigger: submissionChanged`를 반환한다. 이로 인해 사용자는 추천 등록 후에도 컨택 탭에 남아 있으며, 추천 탭에서 등록 결과를 확인하려면 수동으로 탭을 전환해야 한다.

```
현재 UX:
  컨택 탭에서 추천 폼 작성 → 등록 → 204 반환
  → 사용자는 여전히 컨택 탭에 있음
  → 수동으로 [추천] 탭 클릭해야 결과 확인
```

## 요구사항

### 추천 서류 등록 후 추천 탭으로 자동 전환

`submission_create()` 뷰를 수정하여:

- 성공 시 `project_tab_submissions` 파셜을 렌더링하여 200으로 반환한다.
- 응답 헤더에 `HX-Retarget: #tab-content`와 `HX-Reswap: innerHTML`을 추가하여 탭 콘텐츠 영역 전체를 교체한다.
- `HX-Trigger`에 `tabChanged: {"activeTab": "submissions"}`를 포함하여 탭바 활성 상태를 갱신한다.
- 기존 `submissionChanged` 이벤트도 함께 발행하여 하위 호환성을 유지한다.

```
변경 후 UX:
  컨택 탭에서 추천 폼 작성 → 등록 → 추천 탭 파셜 반환
  → 탭 콘텐츠가 추천 탭으로 자동 교체
  → 탭바 활성 상태도 "추천"으로 갱신
```

### 폼 유효성 검사 실패 시 기존 동작 유지

- 유효성 검사 실패 시에는 기존처럼 `hx-target="#submission-form-area"`에 폼을 다시 렌더링한다.
- `HX-Retarget` 헤더 없이 반환하므로, HTMX는 form의 `hx-target` 속성을 따른다.
- `submission_form.html`의 `hx-target` 변경은 불필요하다 (HTMX는 `HX-Retarget` 응답 헤더가 있으면 `hx-target` 속성보다 우선).

## 제약사항

- t19에서 생성한 `tabChanged` 이벤트 시스템에 의존한다.
- Submission 레코드가 실제로 생성되어야 한다 (기능 변경이 아닌 UX 개선).

---

## 앱별 변경 영향

| 앱/파일 | 변경 |
|---------|------|
| `projects/views.py` | 수정 — `submission_create()` 성공 시 추천 탭 파셜 반환 + HX-Retarget + tabChanged |
| `tests/test_p20_workflow_transition.py` | 생성 — 자동 전환, HX-Retarget, tabChanged 헤더, Submission 생성 확인 테스트 |

<!-- forge:t20:설계:draft:2026-04-12 -->
