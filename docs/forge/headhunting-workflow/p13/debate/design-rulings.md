# P13 Design Tempering — Rulings

**Status:** COMPLETE
**Rounds:** 2
**Issues:** 9 (8 accepted, 1 rebutted then accepted by red-team in R2)

---

## Accepted Items

### D-R1-01 [CRITICAL] 루트 진입점 설계가 잘못된 위치를 가리킴
**Ruling:** ACCEPTED
- `/` 매핑 변경은 `main/urls.py`에서 수행
- `/dashboard/` 명시적 URL은 `projects/urls.py`에 추가
- 산출물 목록을 `main/urls.py` + `projects/urls.py`로 분리

### D-R1-02 [CRITICAL] 로그인 후 대시보드 리다이렉트가 현재 인증 플로우 미반영
**Ruling:** ACCEPTED
- `accounts/views.py`의 `home()` 뷰 redirect 대상을 `"candidate_list"` → dashboard로 변경
- `settings.py`에 `LOGIN_REDIRECT_URL = "/"`도 설정 (방어적)
- 산출물에 `accounts/views.py` 수정 명시

### D-R1-03 [CRITICAL] 관리자 판별 기준이 현재 권한 모델과 충돌
**Ruling:** ACCEPTED
- 관리자 판별을 `request.user.membership.role == "owner"` 기준으로 통일
- `user.is_staff` 또는 별도 permission group 표현 삭제

### D-R1-04 [CRITICAL] 긴급도 규칙이 현재 스키마에 없는 필드를 전제
**Ruling:** PARTIAL → ACCEPTED
- Contact에 `next_contact_date = DateField(null=True, blank=True)` 1개 필드 추가
- 서류 검토 대기는 Submission.status="제출" + submitted_at 기준 계산 (기존 필드)
- 설계서에 "신규 필드 추가" 섹션 명시

### D-R1-05 [CRITICAL] 관리자 승인 섹션의 액션 버튼에 동작 경로 없음
**Ruling:** ACCEPTED
- 인라인 [승인] [합류] [반려] 버튼 제거
- "승인 큐 보기" 링크로 `/projects/approvals/`에 이동하도록 변경
- P11 승인 큐 구현 재사용

### D-R1-06 [CRITICAL] 사이드바 HTMX target이 잘못됨
**Ruling:** ACCEPTED
- `hx-target="main"` → `hx-target="#main-content"`로 수정
- 기존 전역 네비 패턴과 동일하게 적용

### D-R1-07 [MAJOR] 서비스 인터페이스가 조직 격리 요구를 누락
**Ruling:** ACCEPTED
- 모든 서비스 함수에 `org: Organization` 파라미터 추가
- `get_pending_approvals(org)` 포함

### D-R1-08 [MAJOR] 승인 뱃지용 context processor 설계 누락
**Ruling:** ACCEPTED
- P11 선행에서 생성될 context processor 재사용
- P13 선행조건으로 명시

## Rebutted Items (Red-team conceded in R2)

### D-R1-09 [MAJOR] ProjectApproval.project 삭제 정책 미반영
**Ruling:** REBUTTED → RED-TEAM ACCEPTED in R2
- P11 확정 구현계획서에서 SET_NULL 변경이 이미 결정됨
- P13은 P11 완료 후 구현되므로 중복 명시 불필요
- 단일 진실 소스 원칙 유지
