# P15: Telegram Integration

> **Phase:** 15
> **선행조건:** P01 (TelegramBinding, Notification 모델), P11 (승인 플로우), P13 (대시보드)
> **산출물:** 텔레그램 Bot 연동 + Inline Keyboard 업무 처리 + 텍스트 업무 요청 + 알림 발송

---

## 목표

텔레그램을 알림 및 간편 업무 채널로 연동한다. Inline Keyboard 기반 버튼 업무 처리,
텍스트 기반 업무 요청, 자동 알림 발송을 구현한다.

---

## URL 설계

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/telegram/webhook/` | POST | `telegram_webhook` | Bot webhook endpoint |
| `/telegram/bind/` | GET/POST | `telegram_bind` | 사용자-챗 연결 설정 UI |
| `/telegram/unbind/` | POST | `telegram_unbind` | 연결 해제 |
| `/telegram/test/` | POST | `telegram_test_send` | 테스트 메시지 발송 |

---

## 모델 (P01에서 정의 완료)

### TelegramBinding (accounts 앱)

| 필드 | 타입 | 설명 |
|------|------|------|
| `user` | OneToOne → User | 사용자 |
| `chat_id` | CharField | 텔레그램 채팅 ID |
| `is_active` | BooleanField | 활성 여부 |
| `verified_at` | DateTimeField null | 인증 완료 시각 |

### Notification (projects 앱)

| 필드 | 타입 | 설명 |
|------|------|------|
| `recipient` | FK → User | 수신자 |
| `type` | CharField choices | approval_request / auto_generated / reminder / news |
| `title` | CharField | 제목 |
| `body` | TextField | 본문 |
| `action_url` | URLField blank | 웹 앱 링크 |
| `telegram_message_id` | CharField blank | 전송된 메시지 ID (갱신용) |
| `status` | CharField choices | pending / sent / read / acted |
| `callback_data` | JSONField | 버튼 선택 시 처리 데이터 |

---

## Bot 설정

패키지: `python-telegram-bot` (async 지원, webhook 모드).

```python
# settings.py
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_WEBHOOK_URL = f"{SITE_URL}/telegram/webhook/"
```

Bot 초기화: `projects/telegram/bot.py` — Application 인스턴스 + webhook 설정.
Django 시작 시 `AppConfig.ready()`에서 webhook 등록.

---

## 사용자 바인딩 플로우

```
1. 웹 앱 설정 페이지 → [텔레그램 연결] 클릭
2. 6자리 인증 코드 표시 (5분 유효)
3. 사용자가 텔레그램 Bot에 /start <코드> 전송
4. Bot이 chat_id 수신 → TelegramBinding 생성 + verified_at 기록
5. 웹 앱에 "연결 완료" 표시
```

---

## Inline Keyboard 업무 처리

### 승인 요청

```
🤖 [synco] 프로젝트 등록 승인 요청

   전병권 → Rayence 품질기획팀장
   충돌: 김소연의 "Rayence 품질기획파트장" (서칭중)
   메시지: "인사팀 이부장으로부터 직접 의뢰 받았습니다"

   [✅ 승인]  [🔗 합류]  [💬 메시지]  [❌ 반려]
```

버튼 클릭 → callback_data 수신 → `projects/telegram/handlers.py`에서 처리 → 메시지 갱신.

### 다단계 컨택 기록

```
🤖 홍길동 컨택 결과를 기록합니다.

   연락 방법은?
   [📞 전화]  [💬 카톡]  [📧 이메일]

        ↓ (전화 선택)

   결과는?
   [😊 관심있음]  [😐 미응답]
   [🤔 보류]     [❌ 거절]

        ↓ (관심있음 선택)

🤖 컨택 기록 저장:
   홍길동 | 전화 | 관심 있음
   메모를 입력해주세요. (건너뛰려면 아래 버튼)
   [💾 저장 — 메모 없이]
```

다단계 상태는 `Notification.callback_data`에 JSON으로 관리:
```python
{"action": "contact_record", "step": 2, "project_id": "uuid",
 "candidate_id": "uuid", "channel": "phone"}
```

---

## 텍스트 업무 요청

사용자가 자유 텍스트로 업무 요청 시 AI 의도 파싱 (P14 voice/intent_parser 재사용):

| 입력 | 응답 |
|------|------|
| "오늘 할 일 뭐야" | 오늘의 액션 목록 (대시보드 데이터) |
| "레이언스 건 현황" | 프로젝트 상태 요약 |
| "홍길동 컨택 결과 입력" | 다단계 Inline Keyboard 시작 |
| "이번 주 면접 일정" | 면접 일정 목록 |

---

## 알림 발송 시스템

### 알림 종류

| 타입 | 트리거 | 템플릿 |
|------|--------|--------|
| `approval_request` | 프로젝트 충돌 감지 | 승인 요청 + 버튼 |
| `auto_generated` | AI 초안/서칭 완료 | 완료 알림 + 웹 링크 |
| `reminder` | 재컨택 예정/잠금 만료/팔로업 | 리마인더 + 액션 버튼 |
| `news` | 뉴스피드 매일 요약 | 뉴스 요약 + 링크 |

### 발송 서비스

`projects/services/notification.py`:

```python
def send_notification(notification: Notification) -> bool:
    """Notification → 텔레그램 메시지 발송. TelegramBinding 확인."""

def send_bulk_notifications(notifications: list[Notification]) -> int:
    """일괄 발송 (뉴스 등)."""

def update_telegram_message(notification: Notification, new_text: str):
    """기존 메시지 갱신 (승인 완료 등)."""
```

### 자동 리마인더 스케줄러

management command + cron:

```bash
# 매일 오전 8시 — 리마인더 생성 + 발송
uv run python manage.py send_reminders
```

리마인더 대상:
- 오늘 재컨택 예정인 Contact
- 내일 만료되는 잠금 (locked_until)
- 서류 검토 대기 2일 이상
- 면접 전날 알림

---

## 서비스 구조

| 파일 | 역할 |
|------|------|
| `projects/telegram/bot.py` | Bot Application 초기화 + webhook |
| `projects/telegram/handlers.py` | callback_query + message handler |
| `projects/telegram/keyboards.py` | Inline Keyboard 빌더 |
| `projects/telegram/formatters.py` | 메시지 포매팅 (Markdown) |
| `projects/services/notification.py` | 알림 생성 + 발송 로직 |
| `projects/management/commands/send_reminders.py` | 자동 리마인더 |

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| 바인딩 | 인증 코드 → Bot /start → TelegramBinding 생성 |
| 승인 버튼 | Inline Keyboard 승인 클릭 → ProjectApproval 상태 변경 |
| 다단계 선택 | 채널 → 결과 → 저장 순서로 Contact 생성 |
| 텍스트 요청 | "오늘 할 일" → 액션 목록 응답 |
| 알림 발송 | Notification 생성 → 텔레그램 메시지 수신 |
| 메시지 갱신 | 승인 완료 시 기존 메시지 업데이트 |
| 리마인더 | send_reminders → 대상 건 Notification 생성 + 발송 |
| 바인딩 해제 | unbind → 알림 발송 중단 |
| 미바인딩 사용자 | TelegramBinding 없는 사용자 알림 → 스킵 |

---

## 산출물

- `projects/telegram/bot.py` — Bot 초기화 + webhook
- `projects/telegram/handlers.py` — 메시지/콜백 핸들러
- `projects/telegram/keyboards.py` — Inline Keyboard 빌더
- `projects/telegram/formatters.py` — 메시지 포매팅
- `projects/services/notification.py` — 알림 발송 서비스
- `projects/views.py` — webhook, bind/unbind 뷰
- `projects/urls.py` — `/telegram/` 하위 URL
- `projects/management/commands/send_reminders.py` — 리마인더 커맨드
- `accounts/templates/accounts/telegram_bind.html` — 바인딩 설정 UI
- 테스트 파일
