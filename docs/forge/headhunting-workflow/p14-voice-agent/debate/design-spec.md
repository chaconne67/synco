# P14 Voice Agent - 설계서 초안

## 핵심 결정 요약

- **목표:** 기존 Whisper 보이스 검색을 대화형 에이전트로 확장. 모든 주요 화면에 마이크 버튼 배치, 음성/텍스트로 주요 업무 처리. 미팅 녹음 업로드 → STT + LLM 인사이트 추출 기능 추가.
- **URL 설계:** `/voice/` 하위 9개 엔드포인트 (transcribe, intent, execute, confirm, context, history, meeting-upload, meeting-analyze, meeting-apply)
- **파이프라인:** MediaRecorder → Whisper STT → Gemini Intent Parsing (11개 intent 타입) → Action Execution → 사용자 확인 → DB 저장
- **미팅 녹음 인사이트:** 음성 파일 업로드 → Whisper STT → (선택적 화자분리 pyannote) → LLM 구조화 분석 (8개 항목) → 헤드헌터 확인 → 선택 항목 DB 반영
- **서비스 구조:** `projects/services/voice/` 하위 6개 서비스 파일 (transcriber, intent_parser, action_executor, context_resolver, conversation, meeting_analyzer)
- **프론트엔드:** voice-agent.js + voice_modal.html + voice_button.html. MediaRecorder API → WebM/Opus → FormData POST
- **컨텍스트 인식:** `data-voice-context` HTML 속성으로 현재 화면 정보 전달
- **세션 관리:** Django 세션에 대화 상태 저장. 모달 닫기 또는 5분 비활성 시 초기화
- **v1 접근:** 화자 분리 없이 전체 텍스트만 사용 가능

## Intent 정의

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

## 컨텍스트 인식

| 현재 화면 | 기본 컨텍스트 | 예시 |
|-----------|-------------|------|
| 대시보드 | 전체 | "레이언스 건 현황" → status_query |
| 프로젝트 상세 | 해당 프로젝트 | "홍길동 전화했는데 관심 있대" → contact_record |
| 서칭 탭 | 해당 프로젝트 + 검색 | "15년 이상 품질 경험" → search_candidate |
| 컨택 탭 | 해당 프로젝트 + 컨택 | "김영희 재컨택해야 해" → contact_reserve |
| 후보자 DB | 검색 | "삼성전자 출신 개발자" → search_candidate |

## URL 설계

```
/voice/transcribe/          POST  음성→텍스트 변환
/voice/intent/              POST  텍스트→의도 파싱
/voice/execute/             POST  의도→액션 실행
/voice/confirm/             POST  사용자 확인 후 DB 저장
/voice/context/             GET   현재 컨텍스트 조회
/voice/history/             GET   대화 히스토리 조회
/voice/meeting-upload/      POST  미팅 녹음 파일 업로드
/voice/meeting-analyze/     POST  업로드된 녹음 분석
/voice/meeting-apply/       POST  분석 결과 선택 항목 DB 반영
```

## 서비스/파일 구조

| 파일 | 역할 |
|------|------|
| `projects/services/voice/transcriber.py` | Whisper 딕테이션 래퍼 (기존 서비스 호출) |
| `projects/services/voice/intent_parser.py` | Gemini API 의도 파싱 + 엔티티 추출 |
| `projects/services/voice/action_executor.py` | Intent별 실제 액션 실행 (CRUD 호출) |
| `projects/services/voice/context_resolver.py` | 화면 컨텍스트 → 파싱 힌트 변환 |
| `projects/services/voice/conversation.py` | 멀티턴 대화 관리 (세션 기반) |
| `projects/services/voice/meeting_analyzer.py` | 미팅 녹음 분석 파이프라인 (STT + LLM 인사이트 추출) |

## 프론트엔드 구현

| 파일 | 역할 |
|------|------|
| `static/js/voice-agent.js` | MediaRecorder, 대화 UI 제어 |
| `projects/templates/projects/partials/voice_modal.html` | 대화 모달 |
| `projects/templates/projects/partials/voice_button.html` | 플로팅 버튼 (base 템플릿 include) |

녹음: MediaRecorder API → WebM/Opus → FormData POST → `/voice/transcribe/`.
대화 UI: HTMX swap으로 메시지 추가. 세션 ID로 멀티턴 관리.

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

## 미팅 녹음 인사이트 파이프라인

1. 음성 파일 업로드 (`/voice/meeting-upload/`)
2. Whisper STT → 전체 텍스트 추출
3. (선택적) pyannote 화자분리 — v1에서는 화자 분리 없이 전체 텍스트만 사용
4. LLM 구조화 분석 (8개 항목):
   - 후보자 관심도/의향
   - 현재 연봉/희망 연봉
   - 이직 가능 시기
   - 주요 경력 하이라이트
   - 우려 사항/질문
   - 다음 단계 액션 아이템
   - 전반적 미팅 분위기
   - 특이사항/메모
5. 헤드헌터 확인 UI (분석 결과 편집 가능)
6. 선택 항목 DB 반영 (`/voice/meeting-apply/`)

Source: docs/plans/headhunting-workflow/P14-voice-agent.md
