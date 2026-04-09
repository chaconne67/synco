# P14: Voice Agent

> **Phase:** 14
> **선행조건:** P13 (대시보드), P03 (프로젝트 CRUD), P06 (컨택), P07 (추천 서류)
> **산출물:** 대화형 보이스 에이전트 + 모든 주요 화면 마이크 버튼 + 의도 파싱 파이프라인 + 미팅 녹음 인사이트 분석

---

## 목표

기존 synco의 Whisper 보이스 검색을 대화형 에이전트로 확장한다. 모든 주요 화면에
마이크 버튼을 배치하고, 음성/텍스트 입력으로 프로젝트 등록, 컨택 기록, 면접 등록 등
주요 업무를 대화 방식으로 처리한다. 또한 후보자 사전 미팅 녹음을 업로드하면
Whisper STT + LLM 분석을 통해 구조화된 인사이트를 추출하고, 후보자 DB에
자동 반영하는 미팅 녹음 인사이트 기능을 제공한다.

---

## URL 설계

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/voice/transcribe/` | POST | `voice_transcribe` | 음성 → Whisper 딕테이션 |
| `/voice/intent/` | POST | `voice_parse_intent` | 텍스트 → 의도 파싱 |
| `/voice/execute/` | POST | `voice_execute_action` | 파싱된 액션 실행 |
| `/voice/confirm/` | POST | `voice_confirm` | 사용자 확인 후 최종 저장 |
| `/voice/context/` | GET | `voice_get_context` | 현재 화면 컨텍스트 조회 |
| `/voice/history/` | GET | `voice_history` | 대화 히스토리 (세션 내) |
| `/voice/meeting-upload/` | POST | `meeting_upload` | 미팅 녹음 파일 업로드 |
| `/voice/meeting-analyze/<uuid:pk>/` | GET | `meeting_analyze` | 분석 결과 조회 |
| `/voice/meeting-apply/<uuid:pk>/` | POST | `meeting_apply` | 인사이트 DB 반영 |

---

## 파이프라인 아키텍처

```
🎙️ 음성 녹음 (브라우저 MediaRecorder API)
  │
  ▼
Whisper API 딕테이션 (기존 candidates/services/whisper.py 재사용)
  │
  ▼
AI 의도 파싱 (Gemini API)
  ├─ intent: project_create | contact_record | interview_schedule | ...
  ├─ entities: {client, position, candidate, channel, result, ...}
  └─ missing_fields: [부족한 필수 정보]
  │
  ▼
  ├─ 정보 충분 → 요약 표시 → 사용자 확인 → 저장 → 다음 액션 제안
  └─ 정보 부족 → 에이전트가 질문 → 사용자 답변 → 재파싱 → 반복
```

---

## 미팅 녹음 인사이트

헤드헌터가 후보자와 사전 미팅(전화/대면)을 녹음한 파일을 업로드하면,
자동으로 텍스트 변환 및 LLM 분석을 수행하여 구조화된 인사이트를 추출한다.

### 파이프라인

```
📁 음성 파일 업로드 (mp3/wav/m4a, 최대 60분)
  │
  ▼
Whisper STT 텍스트 변환 (기존 candidates/services/whisper.py 재사용)
  │
  ▼
화자 분리 (pyannote.audio) — 헤드헌터 vs 후보자 발화 구분
  │  └─ v1: 화자 분리 없이 전체 텍스트만 사용 가능
  ▼
LLM 구조화 분석 (Gemini/Claude)
  │
  ▼
인사이트 리포트 표시 → 헤드헌터 확인/수정 → 선택 항목 DB 반영
```

### LLM이 추출하는 인사이트 항목

| 항목 | 설명 | DB 반영 대상 |
|------|------|-------------|
| 핵심 요약 | 미팅 내용 3-5문장 요약 | CandidateComment 또는 meeting_notes |
| 이직 동기 | 후보자가 밝힌 이직 사유, 불만족 요인 | 메모 (컨택 기록 notes) |
| 희망 조건 | 연봉, 직급, 근무형태, 위치 | desired_salary, 메모 |
| 강점 자기평가 | 후보자가 언급한 강점/성과 | core_competencies 보완 |
| 커뮤니케이션 스타일 | 논리적/감성적, 구체적/추상적 | 메모 (참고용) |
| 관심 포지션/산업 | 언급된 관심 분야 | 메모 |
| 레드플래그 | 잦은 이직 설명 불일치 등 | 메모 (주의사항) |
| 후속 조치 | 약속사항, 추가 확인 필요 | 팔로업 메모 |

### UI 흐름

후보자 상세 페이지 또는 컨택 탭에서:
1. "미팅 녹음 업로드" 버튼
2. 음성 파일 업로드 (mp3/wav/m4a, 최대 60분)
3. 처리 중 표시 (STT + 분석에 1-3분 소요)
4. 인사이트 리포트 표시 — 각 항목에 "DB 반영" 체크박스
5. 헤드헌터가 확인/수정 후 "반영" 클릭
6. 선택된 항목이 후보자 DB에 저장

### 기술 스택

- STT: Whisper (기존 candidates/services/whisper.py)
- 화자 분리: pyannote.audio (신규) 또는 간단히 전체 텍스트만 사용 (v1)
- LLM: Gemini (기존 인프라) 또는 Claude
- 비용: 건당 약 $0.02~0.23 (30분 기준)

---

## 의도(Intent) 정의

| Intent | 설명 | 필수 엔티티 |
|--------|------|------------|
| `project_create` | 프로젝트 등록 | client, position |
| `contact_record` | 컨택 결과 기록 | candidate, channel, result |
| `contact_reserve` | 컨택 예정 등록 | candidate(s) |
| `submission_create` | 추천 서류 생성 | candidate |
| `interview_schedule` | 면접 일정 등록 | candidate, datetime, type |
| `offer_create` | 오퍼 등록 | candidate, salary |
| `status_query` | 현황 조회 | project(optional) |
| `todo_query` | 오늘 할 일 | — |
| `search_candidate` | 후보자 검색 | keywords |
| `navigate` | 화면 이동 | target_page |
| `meeting_upload` | 미팅 녹음 업로드 및 분석 | candidate, audio_file |

---

## 컨텍스트 인식

현재 보고 있는 화면에 따라 의도 파싱의 기본 스코프를 결정:

| 현재 화면 | 기본 컨텍스트 | 예시 |
|-----------|-------------|------|
| 대시보드 | 전체 | "레이언스 건 현황" → status_query |
| 프로젝트 상세 | 해당 프로젝트 | "홍길동 전화했는데 관심 있대" → contact_record |
| 서칭 탭 | 해당 프로젝트 + 검색 | "15년 이상 품질 경험" → search_candidate |
| 컨택 탭 | 해당 프로젝트 + 컨택 | "김영희 재컨택해야 해" → contact_reserve |
| 후보자 DB | 검색 | "삼성전자 출신 개발자" → search_candidate |

컨텍스트는 프론트엔드에서 `data-voice-context` 속성으로 전달:
```html
<main data-voice-context='{"page":"project_detail","project_id":"uuid","tab":"contacts"}'>
```

---

## 서비스 구조

| 파일 | 역할 |
|------|------|
| `projects/services/voice/transcriber.py` | Whisper 딕테이션 래퍼 (기존 서비스 호출) |
| `projects/services/voice/intent_parser.py` | Gemini API 의도 파싱 + 엔티티 추출 |
| `projects/services/voice/action_executor.py` | Intent별 실제 액션 실행 (CRUD 호출) |
| `projects/services/voice/context_resolver.py` | 화면 컨텍스트 → 파싱 힌트 변환 |
| `projects/services/voice/conversation.py` | 멀티턴 대화 관리 (세션 기반) |
| `projects/services/voice/meeting_analyzer.py` | 미팅 녹음 분석 파이프라인 (STT + LLM 인사이트 추출) |

---

## 대화 흐름 예시

```
🎙️  "프로젝트 등록할거야"
🤖  고객사는 어느 회사인가요?
🎙️  "레이언스"
🤖  Rayence (의료기기, 코스닥, 경기 화성) 맞나요? 포지션을 알려주세요.
🎙️  "품질기획팀장"
🤖  이렇게 등록할까요?
    고객사: Rayence | 포지션: 품질기획팀장
    [확인]  [수정]  [취소]
🎙️  "등록해줘"
🤖  등록 완료. 후보자 서칭을 시작할까요?
```

---

## UI: 마이크 버튼

모든 주요 화면 우하단에 플로팅 마이크 버튼 배치:

```
                                          ┌─────┐
                                          │ 🎙️  │  ← 플로팅 버튼
                                          └─────┘
```

클릭 시 → 모달 오버레이:

```
┌─ 보이스 에이전트 ──────────────────────────────────────┐
│                                                        │
│  🤖 Rayence 품질기획 프로젝트를 보고 계시네요.           │
│     무엇을 도와드릴까요?                                │
│                                                        │
│  👤 홍길동한테 전화했는데 관심 있대                       │
│                                                        │
│  🤖 컨택 기록:                                         │
│     홍길동 | 전화 | 관심 있음                            │
│     메모를 추가하시겠어요?                               │
│                                                        │
│  ┌────────────────────────────────────────────────┐   │
│  │                                 [🎙️] [전송]     │   │
│  └────────────────────────────────────────────────┘   │
│                                                        │
│  [닫기]                                                │
└────────────────────────────────────────────────────────┘
```

- 음성 입력: 🎙️ 길게 누르면 녹음, 놓으면 전송
- 텍스트 입력: 입력창에 직접 타이핑 가능 (텍스트도 같은 intent parser로 처리)

---

## 프론트엔드 구현

| 파일 | 역할 |
|------|------|
| `static/js/voice-agent.js` | MediaRecorder, 대화 UI 제어 |
| `projects/templates/projects/partials/voice_modal.html` | 대화 모달 |
| `projects/templates/projects/partials/voice_button.html` | 플로팅 버튼 (base 템플릿 include) |

녹음: `MediaRecorder API` → WebM/Opus → FormData POST → `/voice/transcribe/`.
대화 UI: HTMX swap으로 메시지 추가. 세션 ID로 멀티턴 관리.

---

## 세션 관리

Django 세션에 대화 상태 저장:
```python
request.session["voice_conversation"] = {
    "id": "uuid",
    "turns": [...],
    "pending_intent": "contact_record",
    "collected_entities": {"candidate": "uuid", "channel": "phone"},
    "missing_fields": ["result"],
}
```
모달 닫기 또는 5분 비활성 시 세션 초기화.

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| 딕테이션 | 음성 파일 → 텍스트 변환 확인 |
| 의도 파싱 | "프로젝트 등록할거야" → intent=project_create |
| 엔티티 추출 | "레이언스 품질기획" → client=Rayence, position=품질기획 |
| 부족 정보 질문 | 필수 필드 미입력 시 에이전트 질문 |
| 컨텍스트 인식 | 프로젝트 상세에서 "전화했어" → 해당 프로젝트 기준 |
| 확인 후 저장 | 요약 확인 → 실제 DB 저장 |
| 다음 액션 제안 | 저장 후 후속 단계 안내 |
| 텍스트 입력 | 키보드 입력도 동일하게 동작 |
| 마이크 버튼 | 대시보드/프로젝트/후보자 등 모든 화면에 표시 |
| 미팅 녹음 업로드 | 음성 파일 업로드 → STT 변환 성공 |
| 미팅 인사이트 추출 | LLM이 녹음 텍스트에서 8개 항목 구조화 추출 |
| 인사이트 DB 반영 | 헤드헌터 확인 후 선택 항목이 후보자 DB에 저장 |
| 화자 분리 | 헤드헌터/후보자 발화 구분 (v1에서는 선택적) |

---

## 산출물

- `projects/views.py` — voice_* 뷰 6개
- `projects/urls.py` — `/voice/` 하위 URL
- `projects/services/voice/intent_parser.py` — AI 의도 파싱
- `projects/services/voice/action_executor.py` — 액션 실행
- `projects/services/voice/context_resolver.py` — 컨텍스트 해석
- `projects/services/voice/conversation.py` — 멀티턴 대화 관리
- `static/js/voice-agent.js` — 프론트엔드 녹음 + 대화 UI
- `projects/templates/projects/partials/voice_modal.html` — 대화 모달
- `projects/templates/projects/partials/voice_button.html` — 플로팅 버튼
- `projects/services/voice/meeting_analyzer.py` — 미팅 녹음 분석 파이프라인
- base 템플릿 수정 (플로팅 버튼 include)
- 테스트 파일
