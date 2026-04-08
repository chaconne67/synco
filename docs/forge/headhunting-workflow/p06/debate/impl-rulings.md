# Implementation Rulings — p06

Status: COMPLETE
Last updated: 2026-04-08T18:20:00+09:00
Rounds: 1

## Resolved Items

### Issue 1: Contact.Result choices에 "reserved" 추가 시 migration 누락 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Result choices에 새 값 추가 시 migration이 필요하나 계획서에서 누락.
- **Action:** Step 1 "모델 변경 + Migration" 단계 추가. RESERVED choice 추가 + makemigrations + migrate 명시.

### Issue 2: "reserved" 값의 한/영 불일치 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 기존 Contact.Result 값이 모두 한글인데 "reserved" 영문 사용은 불일치.
- **Action:** `RESERVED = "예정", "예정"`으로 정의. 계획서 전체 `"reserved"` → `"예정"` 변경.

### Issue 3: 컨택 예정 등록 시 channel/contacted_at 필수 필드 충돌 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 예정 등록 시 channel/contacted_at 값이 없는데 모델이 필수로 요구.
- **Action:** channel에 blank=True 추가, contacted_at에 null=True/blank=True 추가. Migration 포함.

### Issue 4: 자동 해제 로직의 DELETE가 데이터 손실 위험 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 만료 예정 건을 .delete()하면 이력 추적 불가.
- **Action:** .delete() → .update(locked_until=None)으로 변경. UI에서 만료 예정 건 구분 표시.

### Issue 5: ContactForm의 candidate queryset 조직 격리 누락 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** ContactForm에서 후보자 드롭다운에 조직 격리 미적용.
- **Action:** ContactForm에 organization 파라미터 + candidate queryset 필터 추가.

### Issue 6: 중복 체크 "컨택 완료" 차단의 정의 모호 [MAJOR]
- **Resolution:** PARTIAL
- **Summary:** 미응답 후 재컨택은 실무상 당연하므로 전체 차단은 부적절.
- **Action:** result별 분기: 관심/거절 → 차단, 응답/미응답/보류 → 경고만 (재컨택 허용).

### Issue 7: 서칭 탭에 체크박스 미존재 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** P05 서칭 탭은 읽기 전용이라 체크박스가 없음. P06에서 추가 필요.
- **Action:** 서칭 탭에 체크박스 + "컨택 예정 등록" 버튼 추가. 산출물에 tab_search.html 수정 명시.

### Issue 8: contact_reserve의 UI 진입점 미명시 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 어디서 어떻게 reserve POST가 트리거되는지 불명확.
- **Action:** 서칭 탭 체크박스 → "컨택 예정 등록" 버튼 → POST (candidate_ids) 플로우 명시.

### Issue 9: "프로젝트 리드" 판정 로직의 불안정성 [MINOR]
- **Resolution:** REBUTTED
- **Summary:** M2M .first()의 비결정성은 맞지만, 과설계 방지를 위해 "담당 컨설턴트 중 한 명이면 해제 가능"으로 구현. through 모델 불필요.
- **Action:** 없음. 구현 시 assigned_consultants 소속 여부로 해제 권한 체크.

### Issue 10: 테스트 기준에 조직 격리 테스트 누락 [MINOR]
- **Resolution:** ACCEPTED
- **Summary:** P05 패턴과 동일하게 조직 격리 테스트 필요.
- **Action:** 테스트 기준에 조직 격리 항목 추가.

### Issue 11: 구현 순서/단계(Step) 미정의 [MINOR]
- **Resolution:** ACCEPTED
- **Summary:** AI 에이전트 실행을 위해 Step 분리 필요.
- **Action:** 7단계로 재구성: (1)모델 (2)서비스 (3)폼 (4)뷰 (5)컨택템플릿 (6)서칭연동 (7)테스트

## Disputed Items

(없음)
