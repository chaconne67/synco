# Phase 2-3 설계 통합 요약 (t18~t25)

> 이 문서는 t18~t25의 design-spec.md 8개를 하나의 워크플로우로 통합 정리한 것이다.
> 각 할일의 상세 설계는 개별 `{slug}/design-spec.md` 참조.

---

## 전체 아키텍처

### Phase 2 잔여 (t18)

설정 탭 + 조직 관리 통합 후 마무리. email_disconnect 리다이렉트 경로를 새 설정 탭 URL로 갱신하고, 전체 테스트 스위트로 Phase 2 회귀 검증.

### Phase 3 (t19~t25): 워크플로우 연결

프로젝트 상세 페이지의 6개 탭(개요, 서칭, 컨택, 추천, 면접, 오퍼) 간 **자동 전환과 시각적 알림**을 구현하여 헤드헌팅 워크플로우의 연속성을 개선한다.

**핵심 인프라:** `tabChanged` 커스텀 이벤트 시스템 (t19)
- 서버 응답이 탭 콘텐츠를 교체할 때 탭바 활성 상태를 자동 갱신
- sessionStorage 기반 뱃지 신규 표시 (서버 부하 없음)
- 후속 태스크(t20~t24)가 이 이벤트를 발행하여 워크플로우 전환 구현

**워크플로우 전환 흐름:**

```
서칭 → [예정 등록] → 컨택 탭 예정 목록
                        │
                    [컨택 등록] (t22: 버튼 라벨/스타일 개선)
                        │
                    컨택 결과 기록
                        │
                   결과="관심"? ──Yes──→ 유도 배너 표시 (t21)
                        │                    │
                        │              [추천 서류 작성하기]
                        │                    │
                        ▼                    ▼
                   추천 등록 (t20) ←─────────┘
                        │
                   tabChanged → 추천 탭 자동 전환
                        │
                   면접 → 오퍼

개요 탭 퍼널 (t23): 각 단계 클릭 → 해당 탭 전환
  컨택(18) → 관심(7) → 추천(3) → 면접(1) → 오퍼(0)

뱃지 신규 표시 (t19 기반, t24 검증):
  탭 미확인 사이 새 항목 추가 → 뱃지에 파란 ring 표시
```

---

## 할일별 요약

### t18 — email_disconnect 리다이렉트 수정 + 최종 통합 테스트
- email_disconnect → `/accounts/settings/email/`로 리다이렉트 변경
- email_settings HTMX 대응 (파셜/전체 분기)
- Phase 2 전체 테스트 회귀 검증
- **복잡도:** small / **의존:** t14, t16, t17

### t19 — tabChanged 이벤트 시스템 + tab-navigation.js
- `tabChanged` 커스텀 이벤트 정의 + 탭바 활성 상태 자동 갱신
- `data-tab-bar`, `data-tab`, `data-badge-count`, `data-latest` 속성 추가
- `tab-navigation.js` 생성 (이벤트 핸들러 + sessionStorage 뱃지 로직)
- `project_detail()` 뷰에 `tab_latest` 컨텍스트 추가
- **복잡도:** medium / **의존:** t18 / **Phase 3 전체의 기반**

### t20 — submission_create() 성공 시 추천 탭 자동 전환
- 성공 시 추천 탭 파셜 200 반환 + `HX-Retarget: #tab-content`
- `tabChanged: {"activeTab": "submissions"}` 이벤트 발행
- 폼 검증 실패 시 기존 동작 유지 (HX-Retarget 없음)
- **복잡도:** medium / **의존:** t19

### t21 — contact_update() "관심" 결과 시 추천 유도 배너
- 결과=INTERESTED + Submission 미존재 시 유도 배너 렌더링
- 배너에 "추천 서류 작성하기" 버튼 → 추천 폼 로드 + tabChanged
- 일회성 (contact_update 응답에만 포함, 서버 상태 저장 안 함)
- **복잡도:** small / **의존:** t19

### t22 — 예정 목록에 "컨택 등록" 버튼 추가
- "결과 기록" → "컨택 등록" 라벨 변경 + 강조 버튼 스타일
- 기능 변경 없이 UI만 수정
- **복잡도:** small / **의존:** 없음 (독립)

### t23 — 퍼널 클릭 가능한 내비게이션
- 개요 탭 퍼널 각 단계 → `hx-get`으로 해당 탭 파셜 로드 + tabChanged
- "관심" 카운트 추가 (`_build_overview_context`)
- 컨택 탭 `?result=관심` 필터 지원
- **복잡도:** small / **의존:** t19

### t24 — 탭 뱃지 신규(new) 표시 검증
- t19 구현의 동작 검증 (구현 아닌 테스트만)
- data-tab, data-badge-count, data-latest 속성 렌더링 테스트
- **복잡도:** small / **의존:** t19

### t25 — 통합 테스트 + 엣지 케이스
- Phase 3 전체 워크플로우 통합 테스트
- 엣지: 폼 검증 실패, 중복 Submission, 배너 일회성, 퍼널 예정 제외
- Phase 1-2 회귀 확인
- **복잡도:** small / **의존:** t19~t24 전부

---

## 의존성 다이어그램

```
t18 (Phase 2 마무리)
  │
  ▼
t19 (tabChanged 이벤트 — Phase 3 기반)
  │
  ├──→ t20 (추천 자동 전환)
  ├──→ t21 (관심 유도 배너)
  ├──→ t23 (퍼널 내비)
  ├──→ t24 (뱃지 검증)
  │
  │    t22 (독립 — 컨택 등록 버튼)
  │
  └──→ t25 (t19~t24 전부 의존 — 통합 테스트)
```

## 공통 패턴 / 주의사항

1. **HTMX 탭 전환 패턴:** 성공 시 파셜 반환 + `HX-Retarget: #tab-content` + `HX-Reswap: innerHTML` + `HX-Trigger: tabChanged`. t20, t21, t23이 이 패턴을 공유한다.
2. **하위 호환:** 기존 이벤트(`submissionChanged`, `contactChanged`)는 항상 함께 발행. HTMX 아닌 일반 요청은 전체 페이지 렌더링 유지.
3. **테스트 파일 공유:** t20~t25의 테스트가 `tests/test_p20_workflow_transition.py`에 집중됨. 할일 간 테스트 충돌 주의 (각 할일이 같은 파일에 테스트 추가).
4. **클라이언트 전용:** Phase 3의 탭 전환/뱃지 로직은 JavaScript + sessionStorage. 서버 상태 변경 최소화.

---

## 변경 대상 파일 종합

| 파일 | 변경 할일 |
|------|----------|
| `projects/views.py` | t19, t20, t21, t23 |
| `projects/templates/projects/project_detail.html` | t19 |
| `projects/templates/projects/partials/detail_tab_bar.html` | t19 |
| `projects/templates/projects/partials/tab_overview.html` | t23 |
| `projects/templates/projects/partials/tab_contacts.html` | t22 |
| `projects/templates/projects/partials/contact_interest_banner.html` | t21 (신규) |
| `static/js/tab-navigation.js` | t19 (신규) |
| `accounts/views.py` | t18 |
| `tests/test_p20_workflow_transition.py` | t20, t21, t23, t24, t25 |
