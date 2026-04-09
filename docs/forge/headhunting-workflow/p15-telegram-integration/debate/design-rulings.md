# Design Rulings — p15-telegram-integration

Status: COMPLETE
Last updated: 2026-04-10T12:00:00Z
Rounds: 1

## Resolved Items

### Issue D-R1-01: URL 설계가 현재 라우팅 구조와 불일치 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** `projects.urls`에 넣으면 `/projects/telegram/...`이 되므로 스펙의 `/telegram/...`과 불일치
- **Action:** `main/urls.py`에 `path("telegram/", include("projects.urls_telegram"))` 독립 include 추가. 산출물에서 `projects/urls.py` → `projects/urls_telegram.py`로 변경

### Issue D-R1-02: TelegramBinding에 verified_at 필드 없음 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 실제 모델에 `verified_at` 없음. "P01에서 정의 완료" 전제 거짓
- **Action:** P15 범위에 `verified_at` DateTimeField 마이그레이션 추가. 설계서 전제 수정

### Issue D-R1-03: 바인딩 인증 코드 저장소/상태 전이 미정의 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 코드 저장, TTL, 1회 소비, brute force 방어 전무
- **Action:** `TelegramVerification` 모델 추가 (accounts 앱): user FK, code CharField(6), expires_at, consumed BooleanField, attempts IntegerField(max 5)

### Issue D-R1-04: 웹훅 CSRF 처리 미명시 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Django CsrfViewMiddleware가 외부 POST 차단
- **Action:** webhook 뷰에 `@csrf_exempt` + Telegram secret token 검증으로 대체

### Issue D-R1-05: 웹훅 진위 검증 없음 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** webhook에 인증 없이 외부에서 임의 요청 가능
- **Action:** `set_webhook(secret_token=...)` + `X-Telegram-Bot-Api-Secret-Token` 헤더 검증 추가

### Issue D-R1-06: AppConfig.ready()에서 webhook 등록 부작용 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** startup 훅에서 외부 API 호출은 테스트/관리 커맨드에 부작용
- **Action:** `setup_telegram_webhook` management command로 분리. deploy.sh에서 실행

### Issue D-R1-07: 설정/의존성 스펙이 현재 프로젝트와 호환 불가 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** `env()`, `SITE_URL`, `python-telegram-bot` 패키지 모두 미존재
- **Action:** `os.environ.get()` 사용, `SITE_URL` 정의, `python-telegram-bot` 의존성 추가, `.env.example` 업데이트

### Issue D-R1-08: Telegram 핸들러가 기존 비즈니스 규칙 우회 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 핸들러가 서비스 계층을 우회하여 직접 ORM 호출 위험
- **Action:** handlers.py는 서비스 함수의 thin wrapper. 직접 ORM 호출 금지 규칙 명시

### Issue D-R1-09: 서버 측 권한 검증 누락 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** callback_data의 project_id/candidate_id에 대한 사용자 권한 미검증
- **Action:** 공통 인가 함수 `verify_telegram_user_access(chat_id, obj)` 정의. 모든 mutation 전 호출

### Issue D-R1-10: callback_data가 Telegram 64바이트 제한 초과 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 예시 JSON이 Telegram의 1-64 바이트 callback_data 제한 초과
- **Action:** callback_data 형식을 `"n:{short_id}:{action}"` (30바이트 미만)으로 변경. 상세 상태는 서버 측 Notification.callback_data에서 조회

### Issue D-R1-11: 다단계 상태 관리 설계 부적합 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Notification.callback_data 하나에 다단계 상태 → 동시 진행 시 충돌
- **Action:** 1 Notification = 1 step. 다단계 진행 시 각 step마다 새 Notification 생성, parent_notification_id 참조

### Issue D-R1-12: P14 intent_parser 재사용 가정이 현재 코드와 불일치 [CRITICAL]
- **Resolution:** PARTIAL
- **Summary:** P14가 아직 구현 전이므로 현재 코드에 없지만, P14 확정 구현계획서에 명확히 정의됨. P15는 P14 이후 구현
- **Action:** P14의 `parse_intent(text, context)` 함수와 사용 intent subset(status_query, todo_query, contact_record, navigate)을 설계서에 구체적으로 참조. P14 선행 의존성 명시

### Issue D-R1-13: 자유 텍스트 요청에 엔티티 식별/중복 해소 단계 없음 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 동명이인/동명 프로젝트 시 잘못된 레코드 조작
- **Action:** P14 entity_resolver 패턴 적용. 다건 매칭 시 Inline Keyboard로 선택. "parse → resolve → (ambiguous → select keyboard) → confirm" 파이프라인 명시

### Issue D-R1-14: 리마인더 기준이 모델에 매핑되지 않음 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** "서류 검토 대기 2일 이상" 등이 어느 모델/상태를 의미하는지 불명확
- **Action:** 각 리마인더 타입별 정확한 ORM 조건 명시

### Issue D-R1-15: 스케줄러 운영 방식이 Docker Swarm 배포와 미연결 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 실제 어디서 cron을 돌릴지 미정의
- **Action:** 호스트 cron으로 `docker exec` 실행. deploy.sh에 cron 설정 단계 추가

### Issue D-R1-16: 메시지 갱신 설계가 rebinding/unbind 미고려 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Notification에 전송 시점 chat_id 스냅샷 없음
- **Action:** Notification에 `telegram_chat_id` 필드 추가. 갱신 시 현재 binding과 비교, 불일치 시 스킵

### Issue D-R1-17: Telegram 재전송/idempotency 설계 없음 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** webhook/callback 중복 배달에 대한 방어 없음
- **Action:** `update_id` 기반 캐시 dedup (5분 TTL). `callback_query_id` 기반 dedup

### Issue D-R1-18: 테스트 기준이 happy path 위주 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 실패/보안/재시도 케이스 없음
- **Action:** 각 mutation path마다 인증 실패, 권한 실패, 중복 update, API 실패, stale binding, brute force 케이스 추가

## Disputed Items

(없음)
