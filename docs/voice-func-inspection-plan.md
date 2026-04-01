# 보이스 서치 기능 파이프라인 점검 계획서

> 작성일: 2026-03-31
> 대상: synco 프로젝트 — 후보자 보이스 검색 파이프라인

---

## 1. 현재 구현 상태 분석

### 1.1 파이프라인 전체 구조도

```
[사용자 마이크]
    │
    ▼
[MediaRecorder JS] ─── audio/webm blob 생성
    │
    ▼
[POST /candidates/voice/] ─── FormData(audio blob)
    │
    ▼
[Django voice_transcribe 뷰] ─── 파일 크기 검증(10MB), Rate limit(5회/분)
    │
    ▼
[candidates/services/whisper.py] ─── OpenAI Whisper API (whisper-1 모델, language="ko")
    │
    ▼
[JSON 응답 {text: "..."}] ─── 프론트엔드로 전사 텍스트 반환
    │
    ▼
[POST /candidates/search/] ─── JSON(message, session_id, input_type)
    │
    ▼
[candidates/services/search.py::parse_search_query] ─── LLM(call_llm_json)으로 자연어→필터 JSON 변환
    │
    ▼
[candidates/services/search.py::hybrid_search] ─── 구조화 필터 + Gemini 임베딩 시맨틱 검색
    │
    ▼
[JSON 응답] ─── {session_id, ai_message, result_count, filters, action}
    │
    ▼
[chatbot.js] ─── 채팅 UI 업데이트 + 후보자 리스트 새로고침(HTMX ajax)
```

### 1.2 각 단계별 구현 상태

#### 1단계: 음성 녹음 (프론트엔드)

| 항목 | 값 |
|------|-----|
| **파일** | `candidates/static/candidates/chatbot.js` |
| **함수** | `startRecording()`, `stopRecording()`, `handleRecordingComplete()` |
| **구현 완성도** | 90% |

**구현 내용:**
- `navigator.mediaDevices.getUserMedia({ audio: true })` 로 마이크 접근
- `MediaRecorder` API로 녹음, `ondataavailable`로 청크 수집
- 녹음 종료 시 `new Blob(audioChunks, { type: "audio/webm" })` 생성
- `FormData`에 `audio` 필드로 blob 첨부, `voice.webm` 파일명 지정
- `fetch("/candidates/voice/", { method: "POST" })` 로 서버 전송
- 마이크 상태 UI 3단계: idle → recording → processing

**미흡한 부분:**
- `MediaRecorder` 생성 시 `mimeType` 미지정 — 브라우저 기본값 사용. Safari/iOS에서 `audio/webm` 미지원 시 문제 가능
- `MediaRecorder.isTypeSupported()` 검사 없음
- 녹음 최대 시간 제한 없음 (무한 녹음 가능 → 10MB 초과 가능)
- 오디오 수준(레벨) 시각적 피드백 없음 (녹음 중인지 사용자가 확인 어려움)
- 녹음 중 네트워크 에러/권한 해제 시 처리 미흡

#### 2단계: 음성→텍스트 변환 (Whisper STT)

| 항목 | 값 |
|------|-----|
| **파일** | `candidates/services/whisper.py` |
| **함수** | `transcribe_audio(audio_file)` |
| **구현 완성도** | 85% |

**구현 내용:**
- OpenAI SDK 사용 (`openai.OpenAI(api_key=settings.OPENAI_API_KEY)`)
- `client.audio.transcriptions.create(model="whisper-1", file=audio_file, language="ko")`
- 싱글톤 클라이언트 패턴 (`_client` 전역 변수)
- `RuntimeError` 래핑하여 상위 뷰로 전파

**미흡한 부분:**
- **모델이 `whisper-1` (구버전)** — 2025년 3월 출시된 `gpt-4o-mini-transcribe`가 더 낮은 WER, 더 적은 hallucination 제공
- Django `InMemoryUploadedFile`의 `.name` 속성이 Whisper API 호환되는지 검증 필요 (파일 확장자가 올바르게 전달되는지)
- 타임아웃 설정 없음 — 네트워크 지연 시 무한 대기 가능
- 빈 오디오(무음) 입력 처리 없음 — Whisper가 빈 텍스트 또는 hallucination 반환 가능
- 재시도(retry) 로직 없음

#### 3단계: 텍스트→검색 필터 변환 (LLM 파싱)

| 항목 | 값 |
|------|-----|
| **파일** | `candidates/services/search.py` |
| **함수** | `parse_search_query(user_text, current_filters)` |
| **구현 완성도** | 90% |

**구현 내용:**
- `common/llm.py::call_llm_json()`으로 LLM 호출 (기본 provider: `claude_cli` 서브프로세스)
- 시스템 프롬프트에 카테고리 목록, 필터 스키마, 출력 규칙 정의
- `action` 분류: new / narrow / broaden
- 실패 시 `_fallback_result()` — 시맨틱 검색만으로 폴백
- 현재 필터 컨텍스트를 프롬프트에 포함하여 멀티턴 지원

**미흡한 부분:**
- `claude_cli` provider가 서브프로세스 실행이라 느림 (timeout 120초 설정됨)
- `broaden` action 처리 로직이 `new`와 동일 (`else` 분기) — 의도적인지 확인 필요
- LLM이 잘못된 JSON 반환 시 `_extract_json`에서 파싱 실패 → 폴백 동작은 정상
- 프롬프트에 음성 검색 특유의 구어체/불완전 문장 처리 가이드 없음

#### 4단계: 하이브리드 검색 실행

| 항목 | 값 |
|------|-----|
| **파일** | `candidates/services/search.py` |
| **함수** | `hybrid_search()`, `execute_structured_search()` |
| **구현 완성도** | 95% |

**구현 내용:**
- 구조화 필터: category, min/max_experience_years, companies_include, education_keyword, position_keyword
- 시맨틱 검색: Gemini embedding (3072-dim) + pgvector `CosineDistance`
- 하이브리드: 구조화 필터 결과 중 시맨틱 순위 정렬 + 미매칭 임베딩 후보 추가
- limit 기본값 50

**미흡한 부분:**
- 임베딩이 없는 후보자는 시맨틱 검색에서 누락됨 (빈 결과 가능)
- `candidate_ids` 집합이 클 때 `IN` 쿼리 성능 고려 필요

#### 5단계: 결과 렌더링

| 항목 | 값 |
|------|-----|
| **파일** | `candidates/static/candidates/chatbot.js` |
| **함수** | `doSearch()`, `appendAIMessage()`, `refreshCandidateList()`, `updateStatusBar()` |
| **구현 완성도** | 90% |

**구현 내용:**
- AI 응답 메시지를 채팅 UI에 추가
- `htmx.ajax("GET", "/candidates/?session_id=...")` 로 후보자 리스트 새로고침
- 검색 상태 바 업데이트 (쿼리 텍스트 + 결과 수)
- `history.replaceState` 로 URL 업데이트 (세션 유지)
- 채팅 히스토리 로드 (`loadChatHistory`)

**미흡한 부분:**
- AI 응답에 마크다운/HTML이 포함될 경우 `escapeHtml`로 인해 그대로 텍스트로 표시됨
- 결과 0건일 때 특별한 UI 안내 없음 (AI 메시지에만 의존)

#### 6단계: 세션/턴 관리

| 항목 | 값 |
|------|-----|
| **파일** | `candidates/models.py`, `candidates/views.py` |
| **모델** | `SearchSession`, `SearchTurn` |
| **구현 완성도** | 95% |

**구현 내용:**
- `SearchSession`: user FK, is_active, current_filters (JSONField)
- `SearchTurn`: session FK, turn_number, input_type (voice/text), user_text, ai_response, filters_applied, result_count
- 새 세션 생성 시 기존 active 세션 비활성화
- `sessionStorage`에 session_id 저장 (브라우저 탭 단위)
- 채팅 히스토리 HTML partial 렌더링 (`chat_history` 뷰)

**미흡한 부분:**
- 세션 만료/정리 로직 없음 (오래된 세션 누적)
- `sessionStorage` 사용으로 새 탭마다 세션 초기화됨 (의도적일 수 있으나 사용성 검토 필요)

### 1.3 미구현 / 불완전 구현 식별

| 구분 | 항목 | 심각도 | 설명 |
|------|------|--------|------|
| **미구현** | Safari/iOS MediaRecorder 호환 | 높음 | mimeType 미지정으로 iOS Safari에서 동작 불가 가능성 |
| **미구현** | 녹음 시간 제한 | 중간 | 무한 녹음 → 10MB 초과 → 서버 거부, 사용자 혼란 |
| **미구현** | Whisper 타임아웃 | 중간 | OpenAI API 호출 시 타임아웃 미설정 |
| **미구현** | 빈 오디오/무음 처리 | 중간 | Whisper hallucination 또는 빈 텍스트 반환 처리 없음 |
| **불완전** | `whisper-1` 모델 사용 | 낮음 | 최신 `gpt-4o-mini-transcribe` 대비 정확도/hallucination 열위 |
| **불완전** | 구어체 검색어 처리 | 낮음 | 음성 입력 특유의 불완전 문장 처리 프롬프트 미보강 |
| **미구현** | 오디오 레벨 시각 피드백 | 낮음 | 녹음 중 사용자가 마이크 입력 확인 불가 |
| **미구현** | 오래된 세션 정리 | 낮음 | 세션 테이블 무한 증가 가능 |

---

## 2. 유사 서비스 기술 리서치 결과

### 2.1 Voice-First 검색 아키텍처 패턴

**Chained STT/LLM Pipeline (우리 방식과 동일):**
- 음성 → STT → LLM → 검색 결과 의 순차 파이프라인
- 장점: 각 컴포넌트를 독립적으로 교체 가능 (STT 제공자, LLM 모델 등)
- 단점: 순차 실행으로 총 레이턴시 = STT + LLM + 검색 시간 합산
- 참조: [LiveKit Voice Agent Architecture](https://livekit.com/blog/voice-agent-architecture-stt-llm-tts-pipelines-explained)

**Speech-to-Speech (실시간) 방식:**
- 단일 멀티모달 AI 모델이 음성 입력에서 직접 응답 생성
- 우리 사용 사례에는 과도 (검색 결과를 반환해야 하므로 텍스트 중간 단계 필요)
- 참조: [Softcery: Real-Time vs Turn-Based](https://softcery.com/lab/ai-voice-agents-real-time-vs-turn-based-tts-stt-architecture)

### 2.2 WebSocket vs REST 비교

| 기준 | REST (현재 구현) | WebSocket |
|------|------------------|-----------|
| **구현 복잡도** | 낮음 | 높음 (Django Channels 필요) |
| **레이턴시** | 녹음 완료 후 일괄 전송 | 실시간 스트리밍 가능 |
| **브라우저 호환** | 매우 높음 | 높음 |
| **적합 사례** | Turn-based 대화 (우리 케이스) | 실시간 연속 대화 |
| **권장** | **현재 유지 적합** | 실시간 연속 음성 필요 시 검토 |

결론: synco의 turn-based 검색 대화에는 현재 REST 방식이 적합. WebSocket은 오버엔지니어링.

참조: [Building Real-Time Voice AI with WebSockets](https://theten.ai/blog/building-real-time-voice-ai-with-websockets), [Deepgram: Designing Voice AI Workflows](https://deepgram.com/learn/designing-voice-ai-workflows-using-stt-nlp-tts)

### 2.3 Whisper API 베스트 프랙티스

**오디오 포맷:**
- 지원 포맷: MP3, MP4, MPEG, MPGA, M4A, WAV, WEBM
- 최적: MP3 64-128kbps (파일 크기 대비 품질 최적)
- WebM(현재 구현)은 지원되나, Safari에서 생성 불가 가능

**파일 크기 제한:**
- API 제한: 25MB (우리 뷰에서 10MB로 제한 — 보수적이고 적절)
- MP3 64kbps 기준 약 50분 분량이 25MB

**정확도 향상:**
- `language` 파라미터 명시 (구현됨: `"ko"`)
- 긴 파일은 청크 분할 + 이전 전사 텍스트를 prompt로 전달
- `whisper-1` → `gpt-4o-mini-transcribe` 업그레이드 시 WER 대폭 개선, hallucination 90% 감소

**알려진 이슈:**
- Safari/iOS의 MediaRecorder가 audio/mp4 생성 → Whisper에서 간헐적 거부
- 무음 오디오 입력 시 Whisper가 텍스트를 조작(hallucination)하는 경향

참조: [OpenAI Speech to Text Guide](https://developers.openai.com/api/docs/guides/speech-to-text), [Whisper API Limits 2026](https://www.transcribetube.com/blog/openai-whisper-api-limits), [GitHub: Optimal Audio Settings for Whisper](https://gist.github.com/danielrosehill/06fb17e7462980f99efa9fdab2335a14)

### 2.4 모바일 브라우저 호환성 이슈

| 브라우저 | MediaRecorder | 기본 mimeType | Whisper 호환 |
|----------|---------------|---------------|-------------|
| Chrome (Android/Desktop) | O | audio/webm;codecs=opus | O |
| Firefox | O | audio/ogg;codecs=opus | O (ogg 지원) |
| Safari (iOS/macOS) | O (14.5+) | audio/mp4 | 불안정 (간헐적 거부) |
| Samsung Internet | O | audio/webm | O |

핵심 문제: 현재 코드가 `{ type: "audio/webm" }` 하드코딩 → Safari에서 실제로는 mp4 데이터인데 webm으로 래핑 → Whisper 에러 가능

참조: [OpenAI Community: MediaRecorder with Whisper on mobile](https://community.openai.com/t/mediarecorder-api-w-whisper-not-working-on-mobile-browsers/866019), [LobeChat Issue #8091](https://github.com/lobehub/lobe-chat/issues/8091)

### 2.5 Voice Search UX 베스트 프랙티스

- 음성 인식 시작 시 청각/시각적 피드백 (우리: 마이크 아이콘 색상 변경 — 최소 수준 구현됨)
- 처리 중 "Searching..." 같은 상태 표시 (우리: "생각 중..." 애니메이션 — 구현됨)
- 오인식 시 대안 제시 또는 명확화 요청 (미구현)
- 텍스트 입력 대안 항시 제공 (구현됨)
- 마이크 권한 거부 시 안내 메시지 (구현됨: "마이크 권한을 허용해주세요")

참조: [Voice User Interface Design Best Practices](https://designlab.com/blog/voice-user-interface-design-best-practices), [Voice Search Optimization UX 2025](https://designindc.com/blog/how-to-optimize-your-website-for-voice-search-in-2025/)

---

## 3. 점검 항목 목록

### 3.1 음성 녹음 & 전송 (JS → Django)

| # | 점검 대상 | 현재 상태 | 기대 상태 | 점검 방법 |
|---|----------|----------|----------|----------|
| 3.1.1 | `chatbot.js:startRecording()` — mimeType 명시 | `new MediaRecorder(stream)` — mimeType 미지정 | `MediaRecorder.isTypeSupported()` 로 동적 선택 | 코드 리딩 |
| 3.1.2 | `chatbot.js:handleRecordingComplete()` — blob type | `{ type: "audio/webm" }` 하드코딩 | 실제 MediaRecorder의 mimeType 사용 | 코드 리딩 + Safari 실기기 테스트 |
| 3.1.3 | 녹음 최대 시간 제한 | 제한 없음 | 60초 또는 적절한 상한 설정 | 코드 리딩 |
| 3.1.4 | blob 크기 프론트 검증 | 없음 | 10MB 초과 시 사전 경고 | 코드 리딩 |
| 3.1.5 | CSRF 토큰 전송 | `getCSRF()` — 쿠키에서 추출 | 정상 동작 확인 (CSRF_COOKIE_HTTPONLY=False 설정됨) | API 호출 테스트 |
| 3.1.6 | 마이크 권한 거부 처리 | `.catch()` → toast 메시지 | 정상 동작 확인 | 브라우저 테스트 |
| 3.1.7 | 녹음 중 UI 피드백 | 마이크 아이콘 색상 변경 (빨간색) | 오디오 레벨 시각 피드백 추가 권장 | 코드 리딩 + 실사용 테스트 |

### 3.2 Whisper STT 호출 (오디오 → 텍스트)

| # | 점검 대상 | 현재 상태 | 기대 상태 | 점검 방법 |
|---|----------|----------|----------|----------|
| 3.2.1 | `whisper.py:transcribe_audio()` — 모델 버전 | `whisper-1` | `gpt-4o-mini-transcribe` 검토 | 코드 리딩 |
| 3.2.2 | `whisper.py:transcribe_audio()` — 타임아웃 | 없음 | OpenAI client에 timeout 파라미터 설정 | 코드 리딩 |
| 3.2.3 | `views.py:voice_transcribe()` — 파일 크기 검증 | `audio.size > 10 * 1024 * 1024` | 적절 (API 제한 25MB 대비 보수적) | 코드 리딩 |
| 3.2.4 | `views.py:voice_transcribe()` — Rate limit | 5회/분 | 적절 (음성 검색 빈도 고려) | 코드 리딩 |
| 3.2.5 | Django `InMemoryUploadedFile` → Whisper API 전달 | `request.FILES.get("audio")` 직접 전달 | `.name` 속성에 올바른 확장자 포함 확인 | API 호출 테스트 |
| 3.2.6 | 빈 오디오/무음 처리 | 없음 | 전사 텍스트 빈 문자열 검사 후 사용자 안내 | 코드 리딩 + 무음 파일 테스트 |
| 3.2.7 | Whisper hallucination 방어 | 없음 | 반복 패턴 감지 또는 신뢰도 검사 검토 | 리서치 기반 분석 |
| 3.2.8 | `OPENAI_API_KEY` 설정 | `settings.py`에 환경변수로 정의 | `.env`에 실제 키 설정 확인 | 설정 점검 |

### 3.3 LLM 검색 연동 (텍스트 → 검색 쿼리 → 결과)

| # | 점검 대상 | 현재 상태 | 기대 상태 | 점검 방법 |
|---|----------|----------|----------|----------|
| 3.3.1 | `search.py:parse_search_query()` — 구어체 처리 | 시스템 프롬프트에 구어체 가이드 없음 | 음성 입력 특유의 불완전 문장, "~요" 체, 축약어 처리 가이드 추가 | 코드 리딩 + 테스트 문장 입력 |
| 3.3.2 | `search.py:parse_search_query()` — 폴백 동작 | `_fallback_result()` — 시맨틱 검색만 수행 | 폴백 시에도 사용 가능한 결과 반환 확인 | API 호출 테스트 |
| 3.3.3 | `llm.py:call_llm_json()` — JSON 파싱 | `_extract_json()` — ```json 블록 처리 | 다양한 LLM 출력 형식 대응 확인 | 단위 테스트 |
| 3.3.4 | `views.py:search_chat()` — `broaden` action | `else: filters = new_filters` (new와 동일) | 의도적인지 확인, 기존 필터에서 조건 제거 동작 필요 | 코드 리딩 |
| 3.3.5 | `search.py:hybrid_search()` — 임베딩 없는 후보자 | 시맨틱 검색에서 누락 | 구조화 필터 결과에 포함되므로 unranked로 반환됨 — 정상 | 코드 리딩 |
| 3.3.6 | `common/llm.py` — `claude_cli` provider 레이턴시 | 서브프로세스 실행, timeout 120초 | 평균 응답 시간 측정 필요 | 실제 API 호출 + 시간 측정 |

### 3.4 결과 렌더링 (백엔드 → 프론트엔드)

| # | 점검 대상 | 현재 상태 | 기대 상태 | 점검 방법 |
|---|----------|----------|----------|----------|
| 3.4.1 | `chatbot.js:appendAIMessage()` — HTML 이스케이프 | `escapeHtml(text)` 적용 | XSS 방지됨, 단 서식(볼드 등) 표시 불가 | 코드 리딩 |
| 3.4.2 | `chatbot.js:refreshCandidateList()` — HTMX 새로고침 | `htmx.ajax("GET", url, {target: "#candidate-list"})` | 결과 리스트 정상 갱신 확인 | 실사용 테스트 |
| 3.4.3 | `chatbot.js:updateStatusBar()` — 상태 바 | `innerHTML` 직접 삽입 | XSS 검사 필요 (`escapeHtml` 적용됨 — 정상) | 코드 리딩 |
| 3.4.4 | "생각 중..." 인디케이터 | `appendThinking()` / `removeThinking()` | 정상 표시/제거 확인 | 실사용 테스트 |
| 3.4.5 | 결과 0건 시 UI | AI 메시지에만 의존 | 빈 상태 안내 UI 추가 권장 | 실사용 테스트 |

### 3.5 세션/턴 관리 (멀티턴 대화)

| # | 점검 대상 | 현재 상태 | 기대 상태 | 점검 방법 |
|---|----------|----------|----------|----------|
| 3.5.1 | `views.py:search_chat()` — 세션 생성/조회 | UUID 검증 + user 매칭 + is_active 필터 | 정상 동작 확인 | API 호출 테스트 |
| 3.5.2 | `SearchTurn` 저장 — input_type 구분 | `input_type=input_type` (voice/text) | 음성/텍스트 입력 올바르게 기록되는지 확인 | DB 조회 테스트 |
| 3.5.3 | 멀티턴 필터 누적 | `narrow` action: `{**session.current_filters, **new_filters}` | 필터 누적이 정상 동작하는지 확인 | 시나리오 테스트 |
| 3.5.4 | 세션 정리 | 미구현 | 오래된 세션 자동 삭제 또는 보관 정책 필요 | 코드 리딩 |
| 3.5.5 | `chat_history` 뷰 | session_id로 턴 조회 + HTML partial 렌더링 | 히스토리 정상 로드 확인 | API 호출 테스트 |

### 3.6 에러 핸들링

| # | 점검 대상 | 현재 상태 | 기대 상태 | 점검 방법 |
|---|----------|----------|----------|----------|
| 3.6.1 | 마이크 권한 거부 | toast "마이크 권한을 허용해주세요" | 구현됨 — 정상 | 브라우저 테스트 |
| 3.6.2 | 네트워크 오류 (음성 전송) | `.catch()` → toast "음성 인식에 실패했습니다" | 구현됨 — 정상 | 네트워크 차단 테스트 |
| 3.6.3 | 네트워크 오류 (검색) | `.catch()` → AI 메시지 "검색 중 오류가 발생했습니다" | 구현됨 — 정상 | 네트워크 차단 테스트 |
| 3.6.4 | Whisper API 실패 | `RuntimeError` → JSON `{"error": "..."}` 500 응답 | 구현됨 — 정상 | 잘못된 오디오 파일 전송 테스트 |
| 3.6.5 | LLM 파싱 실패 | `_fallback_result()` 폴백 | 구현됨 — 정상 | LLM 응답 모킹 테스트 |
| 3.6.6 | Rate limit 초과 | 429 응답 + "요청이 너무 많습니다" 메시지 | 구현됨 — 프론트에서 적절히 표시되는지 확인 | 연속 요청 테스트 |
| 3.6.7 | `OPENAI_API_KEY` 미설정 | OpenAI 클라이언트 생성 시 에러 | 서버 시작 시 사전 검증 권장 | 설정 제거 후 테스트 |
| 3.6.8 | 오디오 파일 없음 | 400 응답 "오디오 파일이 없습니다" | 구현됨 — 정상 | curl 테스트 |
| 3.6.9 | 파일 크기 초과 | 400 응답 "10MB 이하로 녹음해주세요" | 구현됨 — 정상 | 대용량 파일 테스트 |

### 3.7 성능

| # | 점검 대상 | 현재 상태 | 기대 상태 | 점검 방법 |
|---|----------|----------|----------|----------|
| 3.7.1 | 전체 파이프라인 레이턴시 | 미측정 | 목표: 5초 이내 (STT + LLM + 검색) | 실제 음성 입력 시간 측정 |
| 3.7.2 | Whisper STT 레이턴시 | 미측정 | 목표: 2초 이내 (짧은 문장 기준) | API 호출 시간 측정 |
| 3.7.3 | LLM 파싱 레이턴시 | 미측정 (claude_cli 서브프로세스) | 목표: 3초 이내 | API 호출 시간 측정 |
| 3.7.4 | 오디오 파일 크기 | WebM 기본 설정 | 10초 녹음 = 약 50-100KB (WebM opus) | 실제 녹음 파일 크기 측정 |
| 3.7.5 | 동시 요청 처리 | Django runserver (단일 프로세스) | 개발 환경에서는 충분, 운영은 gunicorn worker 수 확인 | 부하 테스트 |

---

## 4. 실전 테스트 계획

### 4.1 edge-tts 테스트 음성 파일 생성 스크립트

#### 설치

```bash
pip install edge-tts
# 또는 uv 환경에서:
uv pip install edge-tts
```

#### 사용 가능한 한국어 음성 확인

```bash
edge-tts --list-voices | grep ko-KR
```

주요 한국어 음성:
- `ko-KR-SunHiNeural` (여성)
- `ko-KR-InJoonNeural` (남성)
- `ko-KR-HyunsuNeural` (남성)

#### 테스트 음성 파일 일괄 생성 스크립트

```python
#!/usr/bin/env python3
"""edge-tts로 보이스 서치 테스트용 한국어 음성 파일을 생성합니다."""

import asyncio
import os

import edge_tts

OUTPUT_DIR = "tests/voice_fixtures"

# 테스트 시나리오: (파일명, 텍스트, 설명)
TEST_SCENARIOS = [
    # 정상 케이스
    ("normal_01_basic.mp3",
     "보험 영업 경력 10년 이상인 분 찾아주세요",
     "기본 검색 - 경력 필터"),
    ("normal_02_company.mp3",
     "삼성전자에서 근무한 HR 담당자 있나요",
     "회사명 + 카테고리 검색"),
    ("normal_03_education.mp3",
     "서울대학교 출신 연구개발 인력 보여줘",
     "학력 + 카테고리 검색"),
    ("normal_04_position.mp3",
     "현재 과장급 이상 재직 중인 영업 담당자",
     "직급 + 카테고리 검색"),
    ("normal_05_multi_filter.mp3",
     "경력 5년에서 15년 사이 마케팅 분야 삼성이나 LG 경험자",
     "복합 필터 검색"),

    # 구어체/자연어 케이스
    ("colloquial_01_casual.mp3",
     "음 그 있잖아요 엔지니어 쪽으로 경험 좀 있는 사람 없을까요",
     "구어체 - 불완전 문장"),
    ("colloquial_02_filler.mp3",
     "어 그러니까 좀 경력이 한 20년 정도 되는 시니어급 찾고 있거든요",
     "구어체 - 필러 단어 포함"),
    ("colloquial_03_dialect.mp3",
     "IT 쪽으로 일하시는 분 중에 연봉 좀 높으신 분 있나요",
     "존대말 검색"),

    # 전문 용어 케이스
    ("jargon_01_insurance.mp3",
     "MDRT 달성 경력이 있는 보험설계사 찾아주세요",
     "보험 전문용어"),
    ("jargon_02_tech.mp3",
     "풀스택 개발자 경력 시니어 레벨 AWS 경험자",
     "IT 전문용어"),
    ("jargon_03_finance.mp3",
     "CFA 자격증 보유한 애널리스트 또는 펀드매니저",
     "금융 전문용어"),

    # 멀티턴 시나리오
    ("multi_01_first.mp3",
     "영업 분야 경력자 보여주세요",
     "멀티턴 1차 - 넓은 검색"),
    ("multi_02_narrow.mp3",
     "그 중에서 경력 10년 이상만요",
     "멀티턴 2차 - 좁히기"),
    ("multi_03_narrow_more.mp3",
     "삼성전자 경험자만 필터링해줘",
     "멀티턴 3차 - 추가 좁히기"),

    # 엣지 케이스
    ("edge_01_short.mp3",
     "HR",
     "초단문 - 카테고리명만"),
    ("edge_02_long.mp3",
     "현재 대기업에서 근무하고 있으면서 경력이 최소 15년 이상이고 학력은 석사 이상이며 "
     "해외 근무 경험이 있고 영어 능통자이면서 마케팅 또는 세일즈 분야에 전문성이 있는 "
     "임원급 후보자를 찾고 싶습니다",
     "장문 - 다수 조건 나열"),
    ("edge_03_ambiguous.mp3",
     "좋은 사람 추천해주세요",
     "모호한 요청"),
    ("edge_04_no_match.mp3",
     "화성에서 일한 경험이 있는 우주비행사",
     "매칭 불가 검색어"),
]

VOICES = ["ko-KR-SunHiNeural", "ko-KR-InJoonNeural"]


async def generate_test_files():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for i, (filename, text, desc) in enumerate(TEST_SCENARIOS):
        voice = VOICES[i % len(VOICES)]  # 남/여 번갈아 사용
        filepath = os.path.join(OUTPUT_DIR, filename)

        print(f"[{i+1}/{len(TEST_SCENARIOS)}] {desc}")
        print(f"  Voice: {voice}")
        print(f"  Text: {text}")
        print(f"  File: {filepath}")

        communicate = edge_tts.Communicate(text=text, voice=voice)
        await communicate.save(filepath)

        # WebM 변환 (Whisper 테스트용) — ffmpeg 필요
        webm_path = filepath.replace(".mp3", ".webm")
        os.system(
            f'ffmpeg -y -i "{filepath}" -c:a libopus -b:a 32k "{webm_path}" '
            f"-loglevel error 2>/dev/null"
        )
        if os.path.exists(webm_path):
            print(f"  WebM: {webm_path}")

        print()

    print(f"완료! {len(TEST_SCENARIOS)}개 테스트 파일 생성: {OUTPUT_DIR}/")


if __name__ == "__main__":
    asyncio.run(generate_test_files())
```

#### CLI로 단일 파일 생성

```bash
# MP3 생성
edge-tts --voice ko-KR-SunHiNeural \
  --text "보험 영업 경력 10년 이상인 분 찾아주세요" \
  --write-media tests/voice_fixtures/test_basic.mp3

# WebM 변환 (MediaRecorder 출력 형식과 동일)
ffmpeg -i tests/voice_fixtures/test_basic.mp3 \
  -c:a libopus -b:a 32k \
  tests/voice_fixtures/test_basic.webm
```

### 4.2 테스트 시나리오 목록

#### 카테고리 A: 정상 케이스

| # | 입력 문장 | 기대 필터 | 기대 결과 |
|---|----------|----------|----------|
| A1 | "보험 영업 경력 10년 이상인 분 찾아주세요" | `{category: "Sales", min_experience_years: 10}` | Sales 카테고리 + 경력 10년 이상 필터 적용 |
| A2 | "삼성전자에서 근무한 HR 담당자 있나요" | `{category: "HR", companies_include: ["삼성전자"]}` | 삼성전자 경력 + HR 카테고리 필터 |
| A3 | "서울대학교 출신 연구개발 인력 보여줘" | `{category: "R&D", education_keyword: "서울대"}` | 서울대 학력 + R&D 카테고리 필터 |
| A4 | "경력 5년에서 15년 사이 마케팅 분야" | `{category: "Marketing", min_experience_years: 5, max_experience_years: 15}` | 복합 필터 적용 |

#### 카테고리 B: 구어체/음성 특유 입력

| # | 입력 문장 | 점검 포인트 |
|---|----------|------------|
| B1 | "음 그 있잖아요 엔지니어 쪽으로..." | 필러 단어 무시하고 핵심 의도 추출 |
| B2 | "어 그러니까 좀 경력이 한 20년..." | "한 20년" → `min_experience_years: 20` 근사 변환 |
| B3 | "좋은 사람 추천해주세요" | 모호한 요청에 대한 적절한 안내 메시지 |

#### 카테고리 C: 멀티턴 대화

| 턴 | 입력 | 기대 action | 기대 필터 변화 |
|----|------|------------|---------------|
| 1 | "영업 분야 경력자 보여주세요" | `new` | `{category: "Sales"}` |
| 2 | "그 중에서 경력 10년 이상만요" | `narrow` | `{category: "Sales", min_experience_years: 10}` |
| 3 | "삼성전자 경험자만 필터링해줘" | `narrow` | `+ companies_include: ["삼성전자"]` |

#### 카테고리 D: 에러 및 엣지 케이스

| # | 테스트 | 기대 동작 |
|---|--------|----------|
| D1 | 무음 오디오 파일 전송 | 빈 텍스트 또는 에러 메시지 반환 |
| D2 | 10MB 초과 파일 전송 | 400 에러 "10MB 이하로 녹음해주세요" |
| D3 | 오디오 없이 POST | 400 에러 "오디오 파일이 없습니다" |
| D4 | 잘못된 파일 형식 (예: .txt) | Whisper API 에러 → 500 "음성 인식 중 오류" |
| D5 | 6회 연속 음성 요청 (1분 내) | 429 "요청이 너무 많습니다" |
| D6 | 잘못된 session_id | 새 세션 생성됨 |

### 4.3 API 호출 테스트 스크립트

#### 사전 준비: 테스트 사용자 세션 쿠키 획득

```bash
# 1. 로그인하여 세션 쿠키 획득 (개발 서버 기준)
# 브라우저에서 로그인 후 개발자 도구에서 sessionid 쿠키 복사
# 또는 curl로 로그인:
SESSION_COOKIE="sessionid=<your-session-id>"
CSRF_TOKEN="csrftoken=<your-csrf-token>"
BASE_URL="http://localhost:8000"
```

#### 테스트 1: 음성 파일 업로드 → Whisper 전사

```bash
# 정상 케이스: WebM 파일 전사
curl -v -X POST "${BASE_URL}/candidates/voice/" \
  -H "Cookie: ${SESSION_COOKIE}; ${CSRF_TOKEN}" \
  -H "X-CSRFToken: <csrf-token-value>" \
  -F "audio=@tests/voice_fixtures/normal_01_basic.webm;type=audio/webm" \
  2>&1

# 기대 응답:
# {"text": "보험 영업 경력 10년 이상인 분 찾아주세요"}

# MP3 파일도 테스트 (edge-tts 원본)
curl -v -X POST "${BASE_URL}/candidates/voice/" \
  -H "Cookie: ${SESSION_COOKIE}; ${CSRF_TOKEN}" \
  -H "X-CSRFToken: <csrf-token-value>" \
  -F "audio=@tests/voice_fixtures/normal_01_basic.mp3;type=audio/mpeg" \
  2>&1

# 에러 케이스: 파일 없이 요청
curl -v -X POST "${BASE_URL}/candidates/voice/" \
  -H "Cookie: ${SESSION_COOKIE}; ${CSRF_TOKEN}" \
  -H "X-CSRFToken: <csrf-token-value>" \
  2>&1
# 기대: 400 {"error": "오디오 파일이 없습니다."}
```

#### 테스트 2: 텍스트 검색 (음성 전사 텍스트 입력 시뮬레이션)

```bash
# 새 세션 검색
curl -v -X POST "${BASE_URL}/candidates/search/" \
  -H "Cookie: ${SESSION_COOKIE}; ${CSRF_TOKEN}" \
  -H "X-CSRFToken: <csrf-token-value>" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "보험 영업 경력 10년 이상인 분 찾아주세요",
    "session_id": null,
    "input_type": "voice"
  }' 2>&1

# 기대 응답 형식:
# {
#   "session_id": "<uuid>",
#   "ai_message": "...",
#   "result_count": N,
#   "filters": {...},
#   "action": "new"
# }
```

#### 테스트 3: 멀티턴 대화

```bash
# 1턴: 넓은 검색
RESPONSE=$(curl -s -X POST "${BASE_URL}/candidates/search/" \
  -H "Cookie: ${SESSION_COOKIE}; ${CSRF_TOKEN}" \
  -H "X-CSRFToken: <csrf-token-value>" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "영업 분야 경력자 보여주세요",
    "session_id": null,
    "input_type": "voice"
  }')
echo "1턴 응답: ${RESPONSE}"
SESSION_ID=$(echo $RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")

# 2턴: 좁히기
curl -s -X POST "${BASE_URL}/candidates/search/" \
  -H "Cookie: ${SESSION_COOKIE}; ${CSRF_TOKEN}" \
  -H "X-CSRFToken: <csrf-token-value>" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"그 중에서 경력 10년 이상만요\",
    \"session_id\": \"${SESSION_ID}\",
    \"input_type\": \"voice\"
  }"
# 기대: action="narrow", filters에 min_experience_years 추가
```

#### 테스트 4: 전체 파이프라인 (pytest)

```python
# tests/test_voice_pipeline.py
"""Voice search pipeline integration tests.

사전 조건:
- OPENAI_API_KEY 환경변수 설정
- 테스트 음성 파일: tests/voice_fixtures/ (edge-tts로 생성)
- DB에 후보자 데이터 존재
"""

import json
import os
from pathlib import Path

import pytest
from django.test import Client

FIXTURES_DIR = Path(__file__).parent / "voice_fixtures"


@pytest.fixture
def auth_client(db, django_user_model):
    """로그인된 테스트 클라이언트."""
    user = django_user_model.objects.create_user(
        username="testuser", password="testpass123"
    )
    client = Client()
    client.login(username="testuser", password="testpass123")
    return client


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
class TestVoicePipeline:
    """Whisper API를 실제 호출하는 통합 테스트."""

    def test_voice_transcribe_webm(self, auth_client):
        """WebM 파일 전사 테스트."""
        audio_path = FIXTURES_DIR / "normal_01_basic.webm"
        if not audio_path.exists():
            pytest.skip("Test fixture not found")

        with open(audio_path, "rb") as f:
            response = auth_client.post(
                "/candidates/voice/",
                {"audio": f},
                format="multipart",
            )

        assert response.status_code == 200
        data = response.json()
        assert "text" in data
        assert len(data["text"]) > 0
        # 한국어 전사 결과에 핵심 키워드 포함 여부 (느슨한 검증)
        assert any(kw in data["text"] for kw in ["보험", "영업", "경력", "10년"])

    def test_voice_transcribe_no_file(self, auth_client):
        """오디오 파일 없이 요청 시 400 에러."""
        response = auth_client.post("/candidates/voice/")
        assert response.status_code == 400
        assert response.json()["error"] == "오디오 파일이 없습니다."

    def test_search_with_voice_text(self, auth_client):
        """전사된 텍스트로 검색 테스트."""
        response = auth_client.post(
            "/candidates/search/",
            json.dumps({
                "message": "보험 영업 경력 10년 이상인 분 찾아주세요",
                "session_id": None,
                "input_type": "voice",
            }),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "ai_message" in data
        assert "result_count" in data
        assert data["result_count"] >= 0

    def test_multi_turn_voice_search(self, auth_client):
        """멀티턴 검색 세션 테스트."""
        # 1턴
        r1 = auth_client.post(
            "/candidates/search/",
            json.dumps({
                "message": "영업 분야 경력자 보여주세요",
                "session_id": None,
                "input_type": "voice",
            }),
            content_type="application/json",
        )
        d1 = r1.json()
        session_id = d1["session_id"]
        count_1 = d1["result_count"]

        # 2턴: 좁히기
        r2 = auth_client.post(
            "/candidates/search/",
            json.dumps({
                "message": "그 중에서 경력 10년 이상만요",
                "session_id": session_id,
                "input_type": "voice",
            }),
            content_type="application/json",
        )
        d2 = r2.json()
        assert d2["session_id"] == session_id
        # 좁히기이므로 결과 수가 같거나 줄어야 함 (DB 데이터에 따라 다름)
        assert d2["result_count"] >= 0


class TestVoiceEdgeCases:
    """Whisper API 호출 없이 테스트 가능한 엣지 케이스."""

    def test_voice_no_auth(self, client):
        """비로그인 시 리다이렉트."""
        response = client.post("/candidates/voice/")
        assert response.status_code == 302  # login redirect

    def test_voice_get_method(self, auth_client):
        """GET 메서드 거부."""
        response = auth_client.get("/candidates/voice/")
        assert response.status_code == 405

    def test_search_empty_message(self, auth_client):
        """빈 메시지 검색."""
        response = auth_client.post(
            "/candidates/search/",
            json.dumps({"message": "", "session_id": None}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_search_invalid_json(self, auth_client):
        """잘못된 JSON 요청."""
        response = auth_client.post(
            "/candidates/search/",
            "not-json",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_search_invalid_session_id(self, auth_client):
        """잘못된 session_id 형식."""
        response = auth_client.post(
            "/candidates/search/",
            json.dumps({
                "message": "테스트",
                "session_id": "not-a-uuid",
            }),
            content_type="application/json",
        )
        # 새 세션이 생성되어야 함
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
```

### 4.4 검증 기준

#### 기능 검증 기준

| 항목 | Pass 기준 |
|------|----------|
| Whisper 전사 정확도 | 핵심 키워드가 전사 결과에 포함 (완벽한 일치 불필요) |
| LLM 필터 변환 | 기대하는 필터 키가 결과 JSON에 포함 |
| 검색 결과 | result_count >= 0 (에러 없이 완료) |
| 멀티턴 | 동일 session_id로 필터가 누적/변경됨 |
| 에러 처리 | 모든 에러 케이스에서 적절한 HTTP 상태 코드 + 한국어 메시지 반환 |

#### 성능 검증 기준

| 항목 | 목표 | 측정 방법 |
|------|------|----------|
| Whisper STT | < 3초 (10초 이하 음성) | `time curl ...` |
| LLM 필터 파싱 | < 5초 | 응답 시간 - STT 시간 |
| 검색 실행 | < 1초 | 별도 측정 또는 로깅 |
| 전체 파이프라인 (음성→결과) | < 8초 | 사용자 체감 시간 |

#### 호환성 검증 기준

| 브라우저 | 테스트 항목 | 기대 동작 |
|----------|-----------|----------|
| Chrome (Desktop) | 마이크 녹음 + 전사 | 정상 동작 |
| Chrome (Android) | 마이크 녹음 + 전사 | 정상 동작 |
| Safari (macOS) | 마이크 녹음 + 전사 | mimeType 이슈 확인 필요 |
| Safari (iOS) | 마이크 녹음 + 전사 | mimeType 이슈 확인 필요 |
| Firefox | 마이크 녹음 + 전사 | ogg 포맷으로 동작 확인 |

---

## 5. 참조 기술 가이드

### 5.1 Whisper API 최적 설정

**현재 (whisper-1):**
```python
client.audio.transcriptions.create(
    model="whisper-1",
    file=audio_file,
    language="ko",
)
```

**권장 업그레이드 (gpt-4o-mini-transcribe):**
```python
client.audio.transcriptions.create(
    model="gpt-4o-mini-transcribe",
    file=audio_file,
    language="ko",
)
```

변경 사항:
- WER(Word Error Rate) 대폭 개선
- Hallucination 90% 감소 (whisper-v2 대비)
- API 인터페이스 동일 — 모델명만 변경하면 됨
- 참조: [OpenAI: Introducing Next-Generation Audio Models](https://openai.com/index/introducing-our-next-generation-audio-models/), [GPT-4o mini Transcribe Model](https://platform.openai.com/docs/models/gpt-4o-mini-transcribe)

### 5.2 크로스 브라우저 MediaRecorder 설정

```javascript
// 권장 패턴: 동적 mimeType 선택
function getSupportedMimeType() {
  var types = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ];
  for (var i = 0; i < types.length; i++) {
    if (MediaRecorder.isTypeSupported(types[i])) {
      return types[i];
    }
  }
  return "";  // 브라우저 기본값 사용
}

// 사용
var mimeType = getSupportedMimeType();
var options = mimeType ? { mimeType: mimeType } : {};
mediaRecorder = new MediaRecorder(stream, options);

// blob 생성 시에도 실제 mimeType 사용
var blob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
```

참조: [MDN: MediaRecorder mimeType](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/mimeType), [OpenAI Community: MediaRecorder Whisper Mobile](https://community.openai.com/t/mediarecorder-api-w-whisper-not-working-on-mobile-browsers/866019)

### 5.3 녹음 시간 제한 패턴

```javascript
var MAX_RECORDING_MS = 60000;  // 60초
var recordingTimer = null;

function startRecording() {
  // ... MediaRecorder 설정 ...
  mediaRecorder.start();
  recordingTimer = setTimeout(function() {
    if (isRecording) {
      stopRecording();
      showToast("녹음 시간이 초과되어 자동으로 중지되었습니다.");
    }
  }, MAX_RECORDING_MS);
}

function stopRecording() {
  if (recordingTimer) {
    clearTimeout(recordingTimer);
    recordingTimer = null;
  }
  // ... 기존 stop 로직 ...
}
```

### 5.4 빈 오디오/무음 감지

```python
# whisper.py에서 전사 후 검증
def transcribe_audio(audio_file) -> str:
    # ... 기존 Whisper 호출 ...
    text = transcript.text.strip()

    if not text:
        raise RuntimeError("음성이 감지되지 않았습니다. 다시 말씀해주세요.")

    # Whisper hallucination 패턴 감지 (반복 텍스트)
    if len(set(text.split())) <= 2 and len(text) > 20:
        raise RuntimeError("음성이 제대로 인식되지 않았습니다. 다시 시도해주세요.")

    return text
```

### 5.5 Django InMemoryUploadedFile → Whisper API 전달 시 주의점

Django의 `request.FILES`에서 받은 파일 객체는 `InMemoryUploadedFile` 또는 `TemporaryUploadedFile`이다. OpenAI SDK는 file-like 객체의 `.name` 속성에서 확장자를 추출하여 포맷을 판단한다.

```python
# 현재 코드에서 잠재적 이슈:
# audio = request.FILES.get("audio")
# 이때 audio.name은 JS에서 전달한 "voice.webm"

# 확인 필요: audio.name이 올바른 확장자를 가지고 있는지
# Safari에서 실제로는 mp4 데이터인데 .webm 확장자일 수 있음
```

안전한 처리:
```python
import io

def transcribe_audio(audio_file) -> str:
    # 파일 내용을 바이트로 읽고, 올바른 이름으로 래핑
    content = audio_file.read()
    name = getattr(audio_file, 'name', 'audio.webm')

    # OpenAI SDK에 전달할 때는 tuple (filename, content, content_type) 사용
    file_tuple = (name, content)

    client = _get_openai_client()
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=file_tuple,
        language="ko",
    )
    return transcript.text
```

### 5.6 성능 최적화 참고 사항

**레이턴시 목표와 현실:**
- 사용자 기대 응답 시간: 3-5초 (Voice assistant 기준 800ms 이하지만, 검색은 더 관대)
- 현재 아키텍처 예상 레이턴시:
  - Whisper STT: 1-3초 (10초 이하 오디오 기준)
  - LLM 파싱 (claude_cli): 3-10초 (서브프로세스 오버헤드 포함)
  - 검색 실행: 0.5-1초
  - **합계: 4.5-14초** → claude_cli가 병목

**개선 방안:**
1. LLM provider를 OpenRouter/Kimi 등 API 직접 호출로 변경 시 3-5초 절감 가능
2. Whisper → gpt-4o-mini-transcribe 전환 시 정확도 개선 (레이턴시는 유사)
3. 프론트엔드에서 STT 완료 후 즉시 사용자 텍스트 표시 → 체감 대기 시간 감소 (현재 구현됨)

참조: [Deepgram: Voice AI Workflows](https://deepgram.com/learn/designing-voice-ai-workflows-using-stt-nlp-tts), [Fish Audio: STT API Comparison 2026](https://fish.audio/blog/speech-to-text-api-comparison-integration-guide-2026/)
