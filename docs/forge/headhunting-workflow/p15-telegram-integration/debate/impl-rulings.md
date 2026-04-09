# Implementation Rulings — p15-telegram-integration

Status: COMPLETE
Last updated: 2026-04-10T14:00:00Z
Rounds: 1

## Resolved Items

### Issue I-R1-01: 승인 요청 Telegram 알림 트리거 연결 누락 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** `projects/views.py`의 `project_create`에서 `ProjectApproval.objects.create()` 후 owner에게 Telegram 승인 알림을 발송하는 단계가 계획에 없음
- **Action:** Task 7에 `projects/views.py` 수정 단계 추가: `ProjectApproval` 생성 후 owner 대상 `Notification` 생성 + `send_notification()` 호출 + 승인 Inline Keyboard 포함

### Issue I-R1-02: 텍스트 업무 요청 기능 미구현 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 설계서에 P15 범위로 정의된 텍스트 업무 요청이 "future task"로 미뤄져 있음
- **Action:** Task 6에 텍스트 메시지 핸들러 추가: `parse_intent()` 호출 → `entity_resolver()` → 응답 생성. P14 모듈 미존재 시 graceful fallback(미지원 안내 메시지). 해당 테스트 추가

### Issue I-R1-03: 승인 `message` 액션 미완결 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** "메시지" 버튼 후 텍스트 입력 → `send_admin_message()` 호출 경로 없음
- **Action:** handlers.py에 "awaiting_message" 상태 관리 추가. Notification.callback_data에 `awaiting_text_input: true` 플래그 → 다음 텍스트 메시지를 해당 approval에 연결 → `send_admin_message()` 호출

### Issue I-R1-04: 다단계 컨택에서 새 Notification의 short_id가 아닌 부모 short_id 사용 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** `_send_next_step()`으로 새 Notification을 만들지만, 키보드는 이전 notification.pk로 생성
- **Action:** handlers.py 수정: `_send_next_step()`의 반환값(새 Notification)의 pk로 키보드 생성하도록 순서 변경

### Issue I-R1-05: 컨택 저장이 직접 ORM 호출 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 설계서는 "직접 ORM 호출 금지" 명시. 현재 `contact.py`에 생성 전용 서비스 함수 없음
- **Action:** `projects/services/contact.py`에 `create_contact()` 서비스 함수 추가 (check_duplicate + create + release reserved locks). Telegram 핸들러와 기존 `contact_create` 뷰 양쪽에서 호출

### Issue I-R1-06: reject/join 후 삭제된 project.title 참조 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** `reject_project()`, `merge_project()`가 project를 삭제하므로 이후 `approval.project.title` 접근 시 예외
- **Action:** 핸들러에서 서비스 호출 전 `project_title = approval.project.title`을 지역 변수로 저장

### Issue I-R1-07: 템플릿이 존재하지 않는 base.html 상속 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 실제 프로젝트는 `common/base.html` 사용. `{% extends "base.html" %}`는 TemplateDoesNotExist 발생
- **Action:** 기존 패턴대로 `{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}` 사용

### Issue I-R1-08: 승인 콜백 권한 검증 우회 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** `verify_telegram_user_access()`에 callback_data dict를 넘기면 organization 속성이 없어 검증 스킵됨
- **Action:** `_process_update()`에서 approval 분기: `approval_id` → `ProjectApproval` 조회 → `approval.project`를 `verify_telegram_user_access()`에 전달

### Issue I-R1-09: brute force 방어 로직 불완전 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 틀린 코드 입력 시 attempts가 증가하지 않아 무한 시도 가능
- **Action:** `_handle_start_command()` 수정: 코드 매칭과 무관하게 해당 user의 최신 활성 verification을 찾아 attempts를 증가시키는 로직. 또는 chat_id 기반 rate limiting

### Issue I-R1-10: 인증 코드 충돌 위험 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 6자리 숫자 코드(100만 조합)에서 동시 발급 시 충돌하면 잘못된 계정 바인딩
- **Action:** 코드 생성 시 활성 미소비 코드 충돌 검사 + 재시도. `while` 루프로 미충돌 코드 생성 (최대 3회). 실패 시 에러

### Issue I-R1-11: callback_query_id dedup 누락 + 동기 처리 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 설계서의 `callback_query_id` dedup이 구현에 없음. 동기 처리로 응답 지연
- **Action:** `callback_query.id` 기반 cache dedup 추가. 동기 처리는 현재 규모에서 수용 가능하나, dedup은 필수 추가

### Issue I-R1-12: 배포 반영 단계 누락 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** deploy.sh 수정, .env.prod 키, cron 등록, webhook 등록 절차가 계획에 없음
- **Action:** Task 8에 배포 반영 단계 추가: deploy.sh의 validate 후 `setup_telegram_webhook` 호출, host crontab에 `send_reminders` 등록, .env.prod에 키 추가 절차 명시

## Disputed Items

(없음)
