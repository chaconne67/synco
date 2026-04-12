# impl-plan Rulings — t21

## Status: COMPLETE

## Round 1

### Resolved Items

**R1-01: contactChanged 이벤트로 인한 배너 즉시 덮어쓰기 [CRITICAL]**
- Action: ACCEPTED
- Resolution: 배너를 `#contact-form-area`에 단독 삽입하는 대신, 컨택 탭 전체를 리렌더링하여 배너를 포함시키는 방식으로 전환. `HX-Retarget="#tab-content"` 사용.

**R1-02: 상태 "변경" 검사 누락 [CRITICAL]**
- Action: ACCEPTED
- Resolution: `form.save()` 전에 `old_result`를 보존하고, `old_result != INTERESTED and contact.result == INTERESTED` 전이 조건으로 변경.

**R1-03: 배너 CTA 클릭 시 tabChanged 이벤트 미발행 [MAJOR]**
- Action: ACCEPTED
- Resolution: CTA 버튼에 tabChanged 발행 메커니즘 추가 (hx-on::after-request 또는 응답 헤더).

**R1-04: 테스트가 HTMX 핵심 헤더를 검증하지 않음 [MAJOR]**
- Action: ACCEPTED
- Resolution: HX-Retarget, HX-Reswap, HX-Trigger 헤더 검증 + "이미 관심이던 건 수정 시 배너 미표시" 테스트 추가.

**R1-05: 배너가 CTA 클릭 후에도 화면에 잔류 [MAJOR]**
- Action: REBUTTED
- Evidence: `#contact-form-area`는 `tab_contacts.html` line 14에서 `#tab-content` 안에 위치. CTA의 `hx-target="#tab-content"`가 전체를 교체하므로 배너도 자동 제거.

### Disputed Items
(없음 — 모든 항목 해결됨)
