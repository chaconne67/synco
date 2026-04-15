# P15: Telegram Integration — 확정 설계서

> **Phase:** 15
> **선행조건:** P01 (TelegramBinding, Notification 기본 모델), P11 (승인 플로우), P13 (대시보드), **P14 (Voice Agent — intent_parser, entity_resolver)**
> **산출물:** 텔레그램 Bot 연동 + Inline Keyboard 업무 처리 + 텍스트 업무 요청 + 알림 발송

---

## 목표

텔레그램을 알림 및 간편 업무 채널로 연동한다. Inline Keyboard 기반 버튼 업무 처리,
텍스트 기반 업무 요청, 자동 알림 발송을 구현한다.

---

## URL 설계

> **[D-R1-01 반영]** `main/urls.py`에 독립 include 추가. `/telegram/` prefix는 projects 앱 하위가 아닌 루트 수준.

**main/urls.py 추가:**
```python
path("telegram/", include("projects.urls_telegram")),
```

**projects/urls_telegram.py:**

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/telegram/webhook/` | POST | `telegram_webhook` | Bot webhook endpoint (csrf_exempt) |
| `/telegram/bind/` | GET/POST | `telegram_bind` | 사용자-챗 연결 설정 UI |
| `/telegram/unbind/` | POST | `telegram_unbind` | 연결 해제 |
| `/telegram/test/` | POST | `telegram_test_send` | 테스트 메시지 발송 |

---

## 모델

### TelegramBinding (accounts 앱) — 수정 필요

> **[D-R1-02 반영]** `verified_at` 필드를 P15 마이그레이션에서 추가.

| 필드 | 타입 | 설명 | 상태 |
|------|------|------|------|
| `user` | OneToOne → User | 사용자 | 기존 |
| `chat_id` | CharField | 텔레그램 채팅 ID | 기존 |
| `is_active` | BooleanField | 활성 여부 | 기존 |
| `verified_at` | DateTimeField null | 인증 완료 시각 | **P15에서 추가** |

### TelegramVerification (accounts 앱) — 신규

> **[D-R1-03 반영]** 인증 코드 관리 전용 모델.

| 필드 | 타입 | 설명 |
|------|------|------|
| `user` | FK → User | 요청한 사용자 |
| `code` | CharField(6) | 6자리 인증 코드 |
| `expires_at` | DateTimeField | 만료 시각 (생성 후 5분) |
| `consumed` | BooleanField(default=False) | 사용 여부 |
| `attempts` | IntegerField(default=0) | 인증 시도 횟수 (최대 5) |

- 코드 생성 시 기존 미소비 코드 모두 무효화 (`consumed=True`)
- 5분 경과 또는 `consumed=True`이면 만료
- `attempts >= 5`이면 차단 → 새 코드 재발급 필요
- 코드는 DB 저장 (stateless 서버 호환, 테스트 용이)

### Notification (projects 앱) — 수정 필요

> **[D-R1-16 반영]** 전송 시점 chat_id 스냅샷 추가.

| 필드 | 타입 | 설명 | 상태 |
|------|------|------|------|
| `recipient` | FK → User | 수신자 | 기존 |
| `type` | CharField choices | approval_request / auto_generated / reminder / news | 기존 |
| `title` | CharField | 제목 | 기존 |
| `body` | TextField | 본문 | 기존 |
| `action_url` | URLField blank | 웹 앱 링크 | 기존 |
| `telegram_message_id` | CharField blank | 전송된 메시지 ID (갱신용) | 기존 |
| `telegram_chat_id` | CharField blank | 전송 시점의 chat_id 스냅샷 | **P15에서 추가** |
| `status` | CharField choices | pending / sent / read / acted | 기존 |
| `callback_data` | JSONField | 버튼 선택 시 처리 데이터 | 기존 |

---

## Bot 설정

> **[D-R1-07 반영]** 현재 프로젝트의 설정 방식(`os.environ.get` + `python-dotenv`)에 맞춤.

패키지: `python-telegram-bot` (async 지원, webhook 모드). **pyproject.toml에 의존성 추가 필요.**

```python
# main/settings.py 추가
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
SITE_URL = os.environ.get("SITE_URL", "https://synco.kr")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
```

**.env.example 추가 키:**
```
TELEGRAM_BOT_TOKEN=
SITE_URL=https://synco.kr
TELEGRAM_WEBHOOK_SECRET=
```

**배포 반영:**
- `.env.prod`에 `TELEGRAM_BOT_TOKEN`, `SITE_URL`, `TELEGRAM_WEBHOOK_SECRET` 추가
- `pyproject.toml`의 `dependencies`에 `python-telegram-bot>=21.0` 추가
- `uv.lock` 재생성 + 커밋

> **[D-R1-06 반영]** Bot 초기화는 `projects/telegram/bot.py`에서 수행하되, webhook 등록은 별도 management command.

```python
# projects/telegram/bot.py — Bot 인스턴스 생성 (webhook 등록은 하지 않음)
# projects/management/commands/setup_telegram_webhook.py — webhook URL 등록
```

**AppConfig.ready()에서 webhook 등록하지 않음.** 대신:
- 개발: `uv run python manage.py setup_telegram_webhook` 수동 실행
- 운영: `deploy.sh` 파이프라인의 validate 단계 이후 실행

---

## 보안: Webhook 인증

> **[D-R1-04, D-R1-05 반영]**

1. webhook 뷰에 `@csrf_exempt` 데코레이터 적용 (Django CSRF 우회)
2. 대체 인증: `set_webhook(secret_token=TELEGRAM_WEBHOOK_SECRET)` 설정
3. 모든 webhook 요청에서 `X-Telegram-Bot-Api-Secret-Token` 헤더 검증
4. 인증 실패 → 즉시 403 반환
5. 유효한 JSON 아닌 요청 → 400 반환

---

## 보안: 권한 검증

> **[D-R1-09 반영]**

모든 Telegram mutation 전에 다음 검증 체인을 거침:

```python
def verify_telegram_user_access(chat_id: str, obj) -> tuple[User, Organization]:
    """
    1. chat_id → TelegramBinding → user
    2. user → Membership → organization
    3. obj.organization == organization 확인
    4. 실패 시 PermissionDenied
    """
```

- callback에 포함된 `project_id`, `candidate_id` 등은 모두 서버에서 재검증
- stale button (바인딩 해제 후 남은 버튼) → 에러 메시지 반환

---

## 보안: Idempotency

> **[D-R1-17 반영]**

- **Webhook:** `update_id` 기반 중복 방어. Django cache framework (5분 TTL)에 최근 처리된 update_id 저장. 중복 요청 → 200 OK + 무처리
- **Callback query:** `callback_query_id` 기반 dedup. 동일 callback 재처리 방지
- Telegram은 webhook 응답이 없으면 재전송하므로, 모든 webhook 응답은 200 즉시 반환

---

## 사용자 바인딩 플로우

> **[D-R1-03 반영]** TelegramVerification 모델 기반 코드 인증 + brute force 방어.

```
1. 웹 앱 설정 페이지 → [텔레그램 연결] 클릭
2. TelegramVerification 생성: 6자리 코드 + 5분 TTL
   - 기존 미소비 코드 모두 무효화
   - 코드를 사용자에게 표시
3. 사용자가 텔레그램 Bot에 /start <코드> 전송
4. Bot이 chat_id + 코드 수신:
   a. TelegramVerification 조회 (code + consumed=False + expires_at > now)
   b. attempts += 1 (5회 초과 시 차단, 새 코드 재발급 안내)
   c. 코드 일치 → consumed=True
   d. TelegramBinding 생성/갱신 + verified_at 기록
   e. Bot이 "연결 완료" 메시지 전송
5. 웹 앱에 "연결 완료" 표시 (polling 또는 htmx)
```

---

## Inline Keyboard 업무 처리

> **[D-R1-10 반영]** callback_data는 64바이트 제한 준수.
> **[D-R1-08 반영]** 핸들러는 기존 서비스 함수의 thin wrapper.

### callback_data 형식

```
n:{notification_short_id}:{action}
```
예: `n:abc123:approve`, `n:abc123:reject`, `n:abc123:join` (30바이트 미만)

- `notification_short_id`: Notification UUID의 앞 8자리 (hex)
- `action`: 짧은 액션 식별자
- 상세 상태(project_id, candidate_id 등)는 서버 측 `Notification.callback_data` JSONField에서 조회

### 승인 요청

```
🤖 [synco] 프로젝트 등록 승인 요청

   전병권 → Rayence 품질기획팀장
   충돌: 김소연의 "Rayence 품질기획파트장" (서칭중)
   메시지: "인사팀 이부장으로부터 직접 의뢰 받았습니다"

   [✅ 승인]  [🔗 합류]  [💬 메시지]  [❌ 반려]
```

버튼 클릭 → callback_data 수신 → Notification 조회 → `verify_telegram_user_access` → **기존 `projects/services/approval.py` 함수 호출** → 메시지 갱신.

### 다단계 컨택 기록

> **[D-R1-11 반영]** 1 Notification = 1 step. 각 step마다 새 Notification 생성.

```
🤖 홍길동 컨택 결과를 기록합니다.

   연락 방법은?
   [📞 전화]  [💬 카톡]  [📧 이메일]

        ↓ (전화 선택)

   (새 Notification 생성 - step 2)
   결과는?
   [😊 관심있음]  [😐 미응답]
   [🤔 보류]     [❌ 거절]

        ↓ (관심있음 선택)

   (새 Notification 생성 - step 3)
🤖 컨택 기록 저장:
   홍길동 | 전화 | 관심 있음
   메모를 입력해주세요. (건너뛰려면 아래 버튼)
   [💾 저장 — 메모 없이]
```

서버 측 Notification.callback_data JSON 구조:
```python
{
    "action": "contact_record",
    "step": 2,
    "project_id": "uuid",
    "candidate_id": "uuid",
    "channel": "phone",
    "parent_notification_id": "uuid"  # 이전 step의 Notification
}
```

최종 저장 시 **기존 `projects/services/contact.py` 함수 호출** (직접 ORM 호출 금지).

---

## 텍스트 업무 요청

> **[D-R1-12 반영]** P14의 `parse_intent(text, context)` 함수 재사용. P14 선행 구현 필수.
> **[D-R1-13 반영]** entity_resolver 패턴 적용. 다건 매칭 시 Inline Keyboard 선택.

**P14에서 재사용하는 구체 모듈:**
- `projects/services/voice/intent_parser.py` — `parse_intent(text, context)` 함수
- `projects/services/voice/entity_resolver.py` — `resolve_candidate()`, `resolve_candidate_list()` 함수

**Telegram에서 사용하는 intent subset:**
- `status_query` — 프로젝트 상태 조회
- `todo_query` — 오늘의 액션 목록
- `contact_record` — 컨택 기록 (다단계 Inline Keyboard 시작)
- `navigate` — 웹 앱 링크 안내

**텍스트 처리 파이프라인:**
```
사용자 텍스트 → parse_intent() → entity_resolver()
    → resolved → 즉시 응답 또는 Inline Keyboard
    → ambiguous → 선택 Inline Keyboard 표시
    → not_found → 에러 메시지
```

| 입력 | 파이프라인 | 응답 |
|------|----------|------|
| "오늘 할 일 뭐야" | todo_query → 대시보드 데이터 조회 | 오늘의 액션 목록 텍스트 |
| "레이언스 건 현황" | status_query → resolve project → 상태 조회 | 프로젝트 상태 요약 |
| "홍길동 컨택 결과 입력" | contact_record → resolve candidate → 다단계 시작 | Inline Keyboard (채널 선택) |
| "이번 주 면접 일정" | todo_query (면접) → Interview 조회 | 면접 일정 목록 |

**다건 매칭 시:**
```
🤖 "홍길동"이(가) 여러 명 있습니다. 선택해주세요:

[1. 홍길동 - Rayence 품질기획팀장]
[2. 홍길동 - Samsung SDI 연구원]
```

---

## 알림 발송 시스템

### 알림 종류

| 타입 | 트리거 | 템플릿 |
|------|--------|--------|
| `approval_request` | 프로젝트 충돌 감지 | 승인 요청 + Inline Keyboard 버튼 |
| `auto_generated` | AI 초안/서칭 완료 | 완료 알림 + 웹 앱 링크 |
| `reminder` | 재컨택 예정/잠금 만료/팔로업 | 리마인더 + 액션 버튼 |
| `news` | 뉴스피드 매일 요약 | 뉴스 요약 + 링크 |

### 발송 서비스

`projects/services/notification.py`:

```python
def send_notification(notification: Notification) -> bool:
    """
    Notification → 텔레그램 메시지 발송.
    1. recipient → TelegramBinding 조회 (없으면 스킵, False 반환)
    2. is_active=False면 스킵
    3. 메시지 전송 성공 시:
       - notification.telegram_message_id = 전송된 message_id
       - notification.telegram_chat_id = 전송 시점의 chat_id (스냅샷)
       - notification.status = 'sent'
    4. API 실패 시: 로깅 + False 반환 (예외 전파하지 않음)
    """

def send_bulk_notifications(notifications: list[Notification]) -> int:
    """일괄 발송 (뉴스 등). 성공 건수 반환."""

def update_telegram_message(notification: Notification, new_text: str) -> bool:
    """
    기존 메시지 갱신 (승인 완료 등).
    1. notification.telegram_chat_id와 현재 TelegramBinding.chat_id 비교
    2. 불일치 (rebind됨) → 갱신 스킵, False 반환
    3. 일치 → editMessageText API 호출
    """
```

### 자동 리마인더 스케줄러

> **[D-R1-14, D-R1-15 반영]** 정확한 ORM 조건 + Docker Swarm 배포 연결.

management command: `projects/management/commands/send_reminders.py`

**리마인더 대상 (정확한 ORM 조건):**

| 리마인더 | ORM 조건 |
|---------|----------|
| 재컨택 예정 | `Contact.objects.filter(next_contact_date=date.today(), result=Contact.Result.RESERVED)` |
| 잠금 만료 임박 | `Contact.objects.filter(locked_until__date=date.today() + timedelta(days=1), result=Contact.Result.RESERVED)` |
| 서류 검토 대기 2일+ | `Submission.objects.filter(status=Submission.Status.SUBMITTED, submitted_at__lte=now - timedelta(days=2), client_feedback="")` |
| 면접 전날 알림 | `Interview.objects.filter(scheduled_at__date=date.today() + timedelta(days=1), result=Interview.Result.PENDING)` |

**스케줄링 주체:**
- 운영 서버(49.247.46.171) 호스트 crontab에 등록:
  ```cron
  0 8 * * * docker exec $(docker ps -qf name=synco_web) python manage.py send_reminders
  ```
- `deploy.sh`에 cron 설정 확인/등록 단계 추가

---

## 서비스 구조

| 파일 | 역할 |
|------|------|
| `projects/telegram/bot.py` | Bot Application 초기화 (webhook 등록은 하지 않음) |
| `projects/telegram/handlers.py` | callback_query + message handler (**서비스 함수 thin wrapper**) |
| `projects/telegram/keyboards.py` | Inline Keyboard 빌더 (64바이트 callback_data 준수) |
| `projects/telegram/formatters.py` | 메시지 포매팅 (Markdown) |
| `projects/telegram/auth.py` | webhook 인증 + `verify_telegram_user_access` |
| `projects/services/notification.py` | 알림 생성 + 발송 로직 |
| `projects/management/commands/send_reminders.py` | 자동 리마인더 |
| `projects/management/commands/setup_telegram_webhook.py` | webhook URL 등록 |

---

## 테스트 기준

> **[D-R1-18 반영]** happy path + 실패/보안/재시도 케이스 포함.

### Happy Path

| 항목 | 검증 방법 |
|------|----------|
| 바인딩 | 인증 코드 → Bot /start → TelegramVerification 소비 → TelegramBinding 생성 |
| 승인 버튼 | Inline Keyboard 승인 클릭 → `services/approval.py` 호출 → ProjectApproval 상태 변경 |
| 다단계 선택 | 채널 → 결과 → `services/contact.py` 호출 → Contact 생성 |
| 텍스트 요청 | "오늘 할 일" → intent_parser → 대시보드 데이터 → 텍스트 응답 |
| 알림 발송 | Notification 생성 → send_notification → telegram_message_id + telegram_chat_id 기록 |
| 메시지 갱신 | 승인 완료 시 update_telegram_message → 기존 메시지 업데이트 |
| 리마인더 | send_reminders → ORM 조건 매칭 → Notification 생성 + 발송 |
| 바인딩 해제 | unbind → is_active=False → 알림 발송 스킵 |
| 미바인딩 사용자 | TelegramBinding 없는 사용자 알림 → 스킵 |

### 실패/보안 케이스

| 항목 | 검증 방법 |
|------|----------|
| webhook 인증 실패 | secret token 불일치 → 403 반환 |
| 만료 인증 코드 | 5분 경과 코드 → 에러 메시지 |
| 재사용 인증 코드 | consumed=True 코드 → 에러 메시지 |
| brute force | attempts >= 5 → 차단 + 재발급 안내 |
| 권한 없는 승인 | 타 조직 사용자 → verify_telegram_user_access 실패 → 거부 메시지 |
| stale callback | 존재하지 않는 Notification → 에러 메시지 |
| Telegram API 실패 | send_notification → graceful degradation, False 반환 |
| 중복 update_id | 동일 update_id 재수신 → 200 OK + 무처리 |
| rebind 후 메시지 갱신 | chat_id 불일치 → 갱신 스킵 |
| entity ambiguity | 동명이인 → 선택 Inline Keyboard 표시 |

---

## 산출물

- `projects/telegram/__init__.py`
- `projects/telegram/bot.py` — Bot 초기화
- `projects/telegram/handlers.py` — 메시지/콜백 핸들러 (서비스 thin wrapper)
- `projects/telegram/keyboards.py` — Inline Keyboard 빌더
- `projects/telegram/formatters.py` — 메시지 포매팅
- `projects/telegram/auth.py` — webhook 인증 + 권한 검증
- `projects/services/notification.py` — 알림 발송 서비스
- `projects/views_telegram.py` — webhook, bind/unbind 뷰
- `projects/urls_telegram.py` — `/telegram/` 하위 URL
- `projects/management/commands/send_reminders.py` — 리마인더 커맨드
- `projects/management/commands/setup_telegram_webhook.py` — webhook 등록
- `accounts/models.py` — TelegramVerification 모델 추가, TelegramBinding.verified_at 추가
- `accounts/templates/accounts/telegram_bind.html` — 바인딩 설정 UI
- `main/urls.py` — `telegram/` include 추가
- `main/settings.py` — TELEGRAM_BOT_TOKEN, SITE_URL, TELEGRAM_WEBHOOK_SECRET
- `pyproject.toml` — python-telegram-bot 의존성 추가
- `.env.example` — 키 추가
- 마이그레이션 파일 (accounts, projects)
- 테스트 파일

<!-- forge:p15-telegram-integration:설계담금질:complete:2026-04-10T12:00:00Z -->
