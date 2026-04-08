# Design Rulings — p11

Status: COMPLETE
Last updated: 2026-04-08T23:15:00+09:00
Rounds: 2

## Resolved Items

### Issue 1: /admin/approvals/ URL 충돌 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** `/admin/`은 Django admin이 점유. 승인 큐 URL을 앱 경로로 이동.
- **Action:** `/admin/approvals/` -> `/projects/approvals/`, `/admin/approvals/<appr_pk>/decide/` -> `/projects/approvals/<appr_pk>/decide/`

### Issue 2: 관리자 역할 미정의 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Membership.Role 기반 역할 매핑 추가.
- **Action:** OWNER = 승인 큐 열람 + 판단 권한, CONSULTANT = 프로젝트 등록 + 승인 요청, VIEWER = 열람만

### Issue 3: TextChoices 저장값 불일치 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 기존 모델의 한국어 저장값 유지.
- **Action:** ConflictType/ApprovalStatus의 영어 저장값을 기존 코드(`"대기"`, `"승인"`, `"합류"`, `"반려"`)로 대체. `conflict_type`도 한국어 저장값 사용.

### Issue 4: 승인 요청 생성 시점 모순 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** `project_create` POST에서 원자적으로 Project + ProjectApproval 생성. 별도 엔드포인트 삭제.
- **Action:** `/projects/<pk>/approval/request/` URL 삭제. `project_create` 뷰에서 충돌 감지 시 `transaction.atomic()` 내에서 Project(pending_approval) + ProjectApproval 동시 생성.

### Issue 5: position_title 필드 부재 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 기존 `Project.title`을 충돌 비교 대상으로 사용.
- **Action:** 설계서 전체에서 `position_title`을 `title`로 수정.

### Issue 6: HTMX 트리거 시점 오류 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 고객사와 제목 양쪽 변경 시, 두 값이 모두 존재할 때만 충돌 체크 실행.
- **Action:** JS에서 client+title 둘 다 비어있지 않을 때만 hx-post 트리거. client 변경 + title blur 양쪽에서 발화.

### Issue 7: medium 규칙이 과도한 차단 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** `medium`은 비차단 참고 경고로 변경, `high`만 승인 차단.
- **Action:** 유사도 >= 0.7 (high)만 `pending_approval` 트리거. < 0.7 (medium)은 정보 패널만 표시, 즉시 등록 가능.

### Issue 8: 다중 충돌 후보 / 합류 대상 선택 [CRITICAL]
- **Resolution:** PARTIAL
- **Summary:** 별도 중간 모델 불필요하나, 관리자가 합류 대상을 선택할 수 있어야 함.
- **Action:** (1) detect_collisions()가 유사 프로젝트 리스트(최대 5건) 반환, (2) conflict_project는 최고 유사도 1건(디폴트 합류 대상), (3) 승인 큐에서 합류 시 같은 고객사 진행 중 프로젝트 드롭다운 표시, (4) approval_decide 뷰에 merge_target 파라미터 추가.

### Issue 9: 승인 대기 상태 우회 가능 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** status 필드를 폼에서 제거하고, PATCH API에서 pending_approval 전환 거부.
- **Action:** ProjectForm에서 `status` 필드 제거. `status_update` PATCH 뷰에서 pending_approval 상태 프로젝트의 직접 상태 변경 거부. pending_approval -> new 전환은 승인 서비스만.

### Issue 10: 승인 대기 중 후속 업무 미차단 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** `pending_approval` 프로젝트에서 모든 하위 작업(컨택/제출/면접/오퍼) 생성 차단.
- **Action:** contact_create, submission_create, interview_create, offer_create 뷰에 `if project.status == ProjectStatus.PENDING_APPROVAL` 가드 추가.

### Issue 11: 합류 시 프로젝트 삭제 위험 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Issue 10 차단으로 하위 데이터 없음 보장 + 방어적 검사.
- **Action:** 합류 서비스에서 하위 데이터 존재 시 InvalidTransition 예외. pending_approval 상태 + 하위 데이터 0건일 때만 삭제 허용.

### Issue 12: 취소/메시지/반려 결과 미정의 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 각 액션의 정확한 결과 정의.
- **Action:** 취소: ProjectApproval 삭제 + Project 삭제. 메시지: admin_response 저장 + Notification 생성, status 대기 유지. 반려: ProjectApproval.status=반려 + Project 삭제 + Notification(반려 사유 포함).

### Issue 13: 활성 승인요청 중복 가능 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 경로 단일화로 중복 경로 제거 + 서비스 레벨 검사.
- **Action:** project_create 원자적 생성으로 통일(Issue 4). 서비스에서 기존 대기 건 존재 시 중복 생성 방지.

### Issue 14: 승인 상태 전이 규칙 미정의 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 기존 패턴(InvalidTransition)을 따르는 전이 규칙 추가.
- **Action:** `APPROVAL_TRANSITIONS = {"대기": {"승인", "합류", "반려"}}`. Terminal 상태 재처리 불가. `transaction.atomic()` + `select_for_update()`.

### Issue 15: 조직 격리 체인 누락 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** ProjectApproval 조회/생성에 organization 격리 적용.
- **Action:** 승인 큐: `ProjectApproval.objects.filter(project__organization=org, status="대기")`. conflict_project 검색도 `organization=org` 필터.

### Issue 16: admin.py 산출물 누락 [MINOR]
- **Resolution:** ACCEPTED
- **Summary:** 산출물에 admin.py 추가.
- **Action:** ProjectApprovalAdmin에 conflict_score, conflict_type 표시 추가.

## Disputed Items

(없음)
