# impl-plan Rulings — t15

Status: COMPLETE

---

## Resolved Items

### R1-01: 템플릿 파일 누락 [CRITICAL] — REBUTTED
템플릿은 t16의 명시적 범위. t15는 뷰 + URL + 테스트만 담당. t16 design-spec이 이를 확인.

### R1-02: HTMX 렌더링 규약 불일치 [MAJOR] — ACCEPTED
기존 settings 뷰의 _is_tab_switch() 패턴을 따르도록 수정. org용 탭 스위치 함수 추가.

### R1-04: 초대코드 생성 실패 시 성공 메시지 [CRITICAL] — ACCEPTED
message를 is_valid() 블록 내부로 이동. invalid이면 bound form + 에러 반환.

### R1-05: Cross-org 보안 테스트 누락 [MAJOR] — ACCEPTED
cross-org approve/role/remove/deactivate 차단 테스트 추가.

### R1-06: Owner 역할 변경 제한 과도 [MAJOR] — REBUTTED
설계 명세에 "owner 역할은 변경 불가"로 명시. 현재 구현이 설계와 정합.

### R1-07: 멤버 정렬 순서 불일치 [MINOR] — ACCEPTED
Case/When으로 명시적 pending=0, active=1, rejected=2 정렬.

### R1-08: 조직 정보 수정 성공 메시지 부재 [MINOR] — ACCEPTED
org_info에 성공 메시지 추가.

### R1-09: URL 네임스페이스 미지정 [MINOR] — REBUTTED
프로젝트 전체가 글로벌 네임 사용. 네임스페이스 도입은 전체 리팩터링 범위.

### R1-03: HTMX 테스트 누락 [CRITICAL] — PARTIAL (RESOLVED)
HTMX 분기 로직(_is_org_tab_switch)은 t15 뷰에 추가. HTMX 렌더링 테스트(partial 응답 내용 검증)는 t16에서 템플릿과 함께 검증. t15 테스트에서는 비즈니스 로직(approve/reject 등 POST 동작) 검증에 집중.

## Disputed Items

(없음)
