# Rulings — phase-1-models impl-plan

**Status**: COMPLETE
**Rounds**: 1
**Redteam**: Codex CLI (Django ORM expert) + Agent (Domain modeling expert)

---

## Resolved Items

### E1-1 [CRITICAL] App boot path broken — ACCEPTED
Phase 1 범위를 "모델 + 앱 부트 경로 최소 정리"로 확장. signals.py, admin.py, urls.py의 삭제 모델 참조를 같은 Phase에서 정리.

### E2-1 [CRITICAL] ActionType name collision — ACCEPTED
기존 `ActionType(TextChoices)` enum + `ActionStatus(TextChoices)` enum 제거를 T1.1에 명시. `AutoAction.action_type` 필드를 `CharField(max_length=30)` (choices 제거)로 임시 변경.

### E1-2 [MAJOR] User FK → settings.AUTH_USER_MODEL — ACCEPTED
T1.4의 모든 User FK를 `FK(settings.AUTH_USER_MODEL, ...)` 으로 명시.

### E1-3/E2-8 [MAJOR] Interview unique constraint — ACCEPTED
`(action_item, round)` constraint 제거. `Interview.clean()`에서 `action_item__application` 기준 중복 검증 구현.

### E1-4 [MAJOR] No action_type validation — PARTIAL (accepted)
T1.5/T1.6/T1.7에 유효 action_type 제약 주석 추가. 실제 검증은 Phase 2 scope.

### E1-5 [MAJOR] Project CheckConstraints — ACCEPTED
T1.1 Meta에 CheckConstraint 3개 추가: open→closed_at NULL, open→result 빈값, result!=''→closed.

### E1-6 [MAJOR] Seed reverse_func — PARTIAL (accepted)
본문 설명을 코드 예시와 일치하도록 수정: seed codes만 대상 삭제.

### E1-7 [MAJOR] Missing Meta cleanup — ACCEPTED
T1.5/T1.6/T1.7에 "삭제 필드 참조하는 Meta.ordering, constraints, __str__ 전수 점검" 스텝 추가.

### E2-3 [MAJOR] submit_to_pm suggests_next — PARTIAL (accepted)
T1.12에 "23개 전체 suggests_next 빠짐없이 정의" 지시 추가.

### E2-5 [MAJOR] STATE_FROM_ACTION_TYPE mapping — PARTIAL (accepted)
T1.3에 보호 타입 4개 + 주요 타입 매핑 스켈레톤 정의. 나머지는 "in_progress" fallback + Phase 2 TODO.

### E2-6 [MAJOR] Phase derivation documentation — PARTIAL (accepted)
T1.1 phase 필드에 파생 규칙 docstring 추가.

### E1-8 [MINOR] Missing index for current_state — ACCEPTED
T1.4 ActionItem Meta indexes에 `["application", "status", "-completed_at"]` 추가.

### E2-7 [MINOR] ActionOutputKind NONE notation — ACCEPTED
T1.2 enum을 `NONE = "", "없음"` 형태로 수정.

### E2-2 [MAJOR] Seed count confusion — REBUTTED
impl-plan은 "23개"로 정확히 기술. 세부 분류 수치는 plan에 없으며 FINAL-SPEC 표에서 확인. 리뷰 프롬프트의 컨텍스트 오류.

### E2-4 [MAJOR] DropReason insufficient — REBUTTED
FINAL-SPEC 9.4에서 "4개 enum, 과도한 분류 금지" 명시적 확정. 단일 진실 소스 원칙에 따라 plan이 spec을 충실히 반영.
