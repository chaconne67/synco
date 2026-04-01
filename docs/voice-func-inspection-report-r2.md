# 보이스 서치 기능 파이프라인 점검 보고서 (R2 — 제로 베이스)

> 점검일: 2026-03-31
> 기존 보고서 참조: 없음 (제로 베이스)

## 점검 결과 요약

| 구분 | 통과 | 문제 | 개선 권장 |
|------|------|------|-----------|
| 1. 음성 녹음 & 전송 (JS → Django) | 7 | 0 | 1 |
| 2. Whisper STT | 5 | 0 | 2 |
| 3. LLM 검색 연동 | 5 | 1 | 2 |
| 4. 결과 렌더링 | 4 | 1 | 1 |
| 5. 세션/턴 관리 | 5 | 1 | 1 |
| 6. 에러 핸들링 | 6 | 0 | 1 |
| 7. 성능 | 2 | 0 | 3 |
| **합계** | **34** | **3** | **11** |

---

## 상세 점검 결과

### 1. 음성 녹음 & 전송 (JS → Django)

#### ✅ MediaRecorder mimeType 감지
- `detectMimeType()`이 `audio/webm;codecs=opus`, `audio/webm`, `audio/mp4`, `audio/ogg;codecs=opus`, `audio/ogg` 순서로 브라우저 지원 여부를 확인한다.
- 지원 타입이 없으면 빈 문자열 반환 → `new MediaRecorder(stream, {})` 로 브라우저 기본값 사용.
- `mediaRecorder.mimeType` 폴백으로 실제 브라우저 선택 mimeType을 캡처한다.
- **코드 근거:** `chatbot.js:80-98`, `chatbot.js:144-145`

#### ✅ Blob 생성 및 서버 전송
- `audioChunks` 배열에 `ondataavailable`로 청크 수집 → `new Blob(audioChunks, { type: recordingMimeType })`으로 합성.
- `FormData.append("audio", blob, "voice." + ext)`로 파일명과 확장자를 명시적으로 전달.
- **코드 근거:** `chatbot.js:146-148`, `chatbot.js:171-184`

#### ✅ Blob 크기 프론트엔드 검증
- `MAX_BLOB_SIZE = 10 * 1024 * 1024` (10MB) 초과 시 전송 차단 + 사용자 메시지 표시.
- 서버 측에서도 `audio.size > 10 * 1024 * 1024` 이중 검증.
- **코드 근거:** `chatbot.js:14,176-179`, `views.py:383-386`

#### ✅ 최대 녹음 시간 제한
- `MAX_RECORDING_SECONDS = 60`. 타이머가 1초 간격으로 경과 시간 표시, 10초 남으면 `animate-pulse` 적용, 60초 도달 시 자동 `stopRecording()`.
- **코드 근거:** `chatbot.js:13,102-121`

#### ✅ CSRF 토큰 전송
- `getCSRF()` 함수가 `document.cookie`에서 `csrftoken`을 파싱하여 `X-CSRFToken` 헤더에 포함.
- `settings.py`에 `CSRF_COOKIE_HTTPONLY = False`로 JS 접근 허용.
- **코드 근거:** `chatbot.js:441-444`, `settings.py:33`

#### ✅ 인증 보호
- `voice_transcribe` 뷰에 `@login_required` 데코레이터 적용.
- JS에서 401/403 응답 시 "로그인이 필요합니다" 메시지 표시.
- **코드 근거:** `views.py:368-369`, `chatbot.js:195-196,224`

#### ✅ 마이크 권한 거부 처리
- `getUserMedia` 실패 시 `showMicPermissionError()`로 권한 변경 안내 + 텍스트 입력 폴백 제공.
- **코드 근거:** `chatbot.js:159-161,381-393`

#### ⚠️ MediaRecorder 미지원 브라우저 처리 미흡
- `detectMimeType()`에서 `typeof MediaRecorder !== "undefined"` 체크는 있으나, `startRecording()`에서 `MediaRecorder` 생성자 호출 전 API 존재 여부를 별도 확인하지 않는다. 매우 오래된 브라우저에서 `navigator.mediaDevices`가 없으면 `getUserMedia`가 `undefined`로 실패하여 `.catch()`에 걸리긴 하나, 에러 메시지가 "마이크 권한이 거부되었습니다"로 표시되어 실제 원인(미지원 브라우저)과 다를 수 있다.
- **수정 방향:** `startRecording()` 진입부에서 `navigator.mediaDevices && navigator.mediaDevices.getUserMedia` 존재 여부를 먼저 확인하고, 미지원 시 별도 메시지("이 브라우저는 음성 녹음을 지원하지 않습니다") 표시 권장.

---

### 2. Whisper STT (오디오 → 텍스트)

#### ✅ OpenAI 클라이언트 초기화 & API 키 검증
- `_get_openai_client()`에서 `settings.OPENAI_API_KEY` 미설정 시 `RuntimeError` 발생, 메시지에 한국어 안내 포함.
- 글로벌 싱글턴 패턴으로 중복 초기화 방지.
- **코드 근거:** `whisper.py:29-39`

#### ✅ Whisper API 호출
- `whisper-1` 모델 사용, `language="ko"` 명시로 한국어 인식 최적화.
- **코드 근거:** `whisper.py:62-66`

#### ✅ 빈 텍스트 / 무음 처리
- 빈 문자열 반환 시 빈 문자열 리턴 → 뷰에서 400 응답 → JS에서 "음성이 감지되지 않았습니다" 처리.
- 3자 미만 텍스트도 노이즈로 간주하고 빈 문자열 반환.
- **코드 근거:** `whisper.py:68-78`, `views.py:391-393`, `chatbot.js:211-213`

#### ✅ Hallucination 감지
- 12개의 한국어 hallucination 패턴 정의 (`"시청해 주셔서 감사합니다"`, `"MBC 뉴스"` 등).
- `_is_hallucination()`이 부분 문자열 매치로 검사, 매칭 시 빈 문자열 반환.
- **코드 근거:** `whisper.py:13-26,43-45,72-73`

#### ✅ 에러 전파
- Whisper API 예외 시 `RuntimeError`로 래핑하여 re-raise → 뷰에서 `RuntimeError`는 `str(e)` 메시지로 500 응답, 기타 예외는 일반 에러 메시지로 500 응답.
- **코드 근거:** `whisper.py:81-83`, `views.py:396-399`

#### ⚠️ 타임아웃 설정 제한적
- `httpx.Timeout(30.0)`은 OpenAI 클라이언트 전체 타임아웃인데, Whisper API는 오디오 길이에 따라 처리 시간이 크게 달라질 수 있다. 60초 녹음의 경우 30초 타임아웃이 부족할 수 있다.
- **수정 방향:** 타임아웃을 60초 이상으로 늘리거나, 오디오 크기에 비례한 동적 타임아웃 고려.

#### ⚠️ Hallucination 패턴 확장 필요
- 현재 12개 패턴은 주로 YouTube/뉴스 관련이다. Whisper가 무음에서 생성하는 다른 패턴(영어 hallucination 포함: "Thank you for watching", "Subscribe", 단순 반복 등)은 커버하지 못한다.
- **수정 방향:** 영어 패턴 추가, 반복 텍스트 감지 로직(동일 구절 3회 이상 반복 등) 고려.

---

### 3. LLM 검색 연동 (텍스트 → 검색)

#### ✅ 자연어 → 필터 변환 프롬프트
- `SEARCH_SYSTEM_PROMPT`가 사용 가능한 카테고리 20개를 명시, JSON 스키마를 정의, 음성 특화 규칙(필러 단어 무시, 구어체 숫자 변환)을 포함.
- **코드 근거:** `search.py:40-68`

#### ✅ 폴백 동작
- LLM 호출 실패 또는 잘못된 응답 시 `_fallback_result()`로 빈 필터 + 시맨틱 검색만 실행. 사용자에게 "정확한 필터 대신 유사 검색으로 찾았습니다" 안내.
- **코드 근거:** `search.py:89-100`

#### ✅ Action 처리 (new/narrow/broaden)
- `new`: 기존 필터 버리고 새 필터만 적용.
- `narrow`: 기존 필터에 새 non-null 필터를 병합 (기존 값 유지, 새 값 덮어쓰기).
- `broaden`: LLM이 반환한 non-null 필터를 그대로 적용 (완화된 필터셋).
- null 값을 사전 제거하여 기존 필터 보호.
- **코드 근거:** `views.py:314-327`

#### ✅ Hybrid 검색 (구조적 필터 + 시맨틱 랭킹)
- `execute_structured_search()`로 DB 필터 → `get_embedding()`으로 쿼리 벡터 생성 → `CandidateEmbedding`의 코사인 거리로 정렬.
- 임베딩 없는 후보자도 `unranked`로 결과에 포함.
- **코드 근거:** `search.py:103-168`

#### ✅ 현재 필터 컨텍스트 전달
- `parse_search_query()`가 `current_filters`를 프롬프트에 포함하여 LLM이 멀티턴 맥락을 이해하도록 한다.
- **코드 근거:** `search.py:71-77`

#### ❌ `broaden` 액션이 `new`와 동일하게 동작
- `views.py:325-327`에서 `broaden`의 else 분기가 `filters = non_null_filters`로 처리되어, `new` 액션과 완전히 동일한 결과를 낸다. `broaden`은 기존 필터를 기반으로 일부 조건을 완화해야 하는데, 현재 로직은 기존 필터를 전혀 참조하지 않는다.
- **수정 방향:** `broaden`은 기존 `session.current_filters`를 기반으로, LLM이 명시적으로 제거하고 싶은 필터만 null로 반환하게 하고, null이 아닌 기존 필터는 유지하는 병합 로직이 필요하다. 또는 LLM 프롬프트에서 `broaden` 시 "기존 필터 전체를 다시 생성하되 일부 조건을 완화하라"는 지시를 강화해야 한다.

#### ⚠️ LLM 프롬프트에 age/gender/address 필터 없음
- 채팅 칩 예시에 "강남 30대 여성"이 있지만, JSON 스키마에 `age`, `gender`, `address` 필터가 없다. LLM이 이 요청을 받으면 `semantic_query`로만 처리되어 정확한 필터링이 불가능하다.
- Candidate 모델에는 `birth_year`, `gender`, `address` 필드가 존재하므로 필터 추가가 가능하다.
- **수정 방향:** 프롬프트 스키마에 `birth_year_min`, `birth_year_max`, `gender`, `address_keyword` 필터 추가 및 `execute_structured_search()`에 해당 필터 로직 구현.

#### ⚠️ `call_llm_json` JSON 파싱 실패 시 에러 처리
- `_extract_json()`에서 `json.loads()` 실패 시 `json.JSONDecodeError` 발생. `parse_search_query()`의 `except Exception` 블록에서 잡히기는 하지만, LLM이 유효하지 않은 JSON을 반환하는 빈도가 높을 수 있으며, 매번 로그에 스택 트레이스가 남는다.
- **수정 방향:** `_extract_json()`에서 JSON 파싱 실패 시 재시도(1회) 또는 JSON repair 로직 추가 고려. 또는 `call_llm_json`에서 `response_format: json`을 지원하는 프로바이더라면 해당 옵션 활용.

---

### 4. 결과 렌더링

#### ✅ XSS 방지 (JS 측)
- `appendUserMessage()`, `appendAIMessage()`, `updateStatusBar()` 모두 `escapeHtml()` 함수를 통해 텍스트를 이스케이프한다.
- `escapeHtml()`은 `document.createElement("div") → textContent → innerHTML` 패턴으로 안전하게 HTML 엔티티 변환.
- **코드 근거:** `chatbot.js:446-450`, `chatbot.js:293-298`, `chatbot.js:302-311`, `chatbot.js:421-429`

#### ✅ HTMX 리스트 갱신
- `refreshCandidateList()`가 `htmx.ajax("GET", url, { target: "#candidate-list", swap: "innerHTML" })`로 후보자 목록을 새로고침.
- 채팅 모달 닫을 때와 검색 완료 시 자동 호출.
- **코드 근거:** `chatbot.js:415-419`, `chatbot.js:26,271`

#### ✅ 상태 바 업데이트
- `updateStatusBar()`가 검색어와 결과 수를 표시, `escapeHtml()`로 XSS 방지.
- 서버 측 템플릿(`search_status_bar.html`)은 Django 템플릿 자동 이스케이프로 보호.
- **코드 근거:** `chatbot.js:421-429`, `search_status_bar.html:1-15`

#### ✅ 빈 결과 처리
- 결과가 0건이어도 `ai_message`에 "0명의 후보자를 찾았습니다" 메시지가 표시된다.
- **코드 근거:** `views.py:335-336`

#### ❌ 채팅 히스토리 템플릿에서 XSS 취약점
- `chat_messages.html:25`에서 `{{ turn.user_text }}`가 Django 자동 이스케이프로 보호되지만, `{{ turn.ai_response }}`도 동일하게 자동 이스케이프된다 — 이 부분은 안전하다.
- **그러나** `loadChatHistory()`에서 서버 응답을 `container.innerHTML = html`로 직접 삽입한다(`chatbot.js:404`). 이 HTML은 서버 렌더링된 Django 템플릿이므로 Django의 자동 이스케이프가 적용되어 있어 일반적으로 안전하다.
- **실제 문제:** `showMicPermissionError()` 함수(`chatbot.js:386-389`)에서 `innerHTML`에 하드코딩된 HTML을 직접 삽입하는데, 이 부분은 동적 데이터가 없어 안전하다. 그러나 `loadChatHistory()`가 `r.text()`로 받은 응답을 검증 없이 `innerHTML`에 넣는 구조는, 만약 서버 응답이 변조되면(MITM 등) XSS 벡터가 될 수 있다. HTTPS 환경에서는 실질적 위험이 낮으나, Content-Type 검증이 없다.
- **수정 방향:** `loadChatHistory()` 응답에 대해 Content-Type이 `text/html`인지 검증 추가. 또는 JSON으로 전환하여 JS 측에서 `escapeHtml()`을 거치도록 변경하면 더 안전하다.

#### ⚠️ history.replaceState로 URL 업데이트 시 인코딩 미흡
- `chatbot.js:272`에서 `'/candidates/?session_id=' + sessionId`로 URL을 구성하는데, `sessionId`가 UUID이므로 특수문자가 없어 현재는 안전하다. 다만 `encodeURIComponent`를 사용하는 것이 방어적 코딩 관점에서 바람직하다.
- **수정 방향:** `encodeURIComponent(sessionId)` 사용 권장 (저우선).

---

### 5. 세션/턴 관리

#### ✅ 세션 생성
- 새 세션 생성 시 기존 활성 세션을 `is_active=False`로 일괄 비활성화하여 사용자당 1개의 활성 세션만 유지.
- **코드 근거:** `views.py:305-308`

#### ✅ 세션 조회 & 검증
- `session_id`에 대해 UUID 유효성 검사 후 `user=request.user, is_active=True` 조건으로 조회. 다른 사용자의 세션 접근 차단.
- **코드 근거:** `views.py:173-181`, `views.py:299-303`

#### ✅ 멀티턴 필터 누적
- `session.current_filters`를 `narrow` 액션에서 병합하여 필터가 턴마다 누적. 각 턴의 `filters_applied`도 `SearchTurn`에 저장되어 이력 추적 가능.
- **코드 근거:** `views.py:322-323`, `views.py:344-352`

#### ✅ 시맨틱 쿼리 저장/복원
- `semantic_query`를 `filters["_semantic_query"]`로 세션 필터에 포함하여 페이지 새로고침 시에도 시맨틱 랭킹 유지.
- `candidate_list` 뷰에서 `filters.pop("_semantic_query")`로 추출하여 사용.
- **코드 근거:** `views.py:339-340`, `views.py:191`

#### ✅ JS 측 세션 관리
- `sessionStorage`에 `synco_session_id` 저장. 브라우저 탭 닫으면 자동 초기화.
- 채팅 모달 열 때 기존 세션 히스토리 로드.
- **코드 근거:** `chatbot.js:5,267-268`, `chatbot.js:31-33`

#### ❌ 턴 번호 동시성 문제 (race condition)
- `turn_number = session.turns.count() + 1`은 동시 요청 시 동일 번호가 부여될 수 있다. `SearchTurn` 모델에 `(session, turn_number)` unique constraint가 없으므로 중복 번호가 DB에 저장될 수 있다.
- 현실적으로 단일 사용자가 동시에 두 검색 요청을 보낼 가능성은 낮지만(JS의 `isSearching` 플래그가 방지), 네트워크 재시도나 브라우저 뒤로 가기 등의 경우 발생 가능하다.
- **수정 방향:** `SearchTurn.Meta`에 `unique_together = [("session", "turn_number")]` 추가, 또는 DB 레벨에서 `MAX(turn_number) + 1`로 계산하도록 변경.

#### ⚠️ 세션 정리 메커니즘 없음
- 비활성 세션(`is_active=False`)이 영구적으로 DB에 남는다. 시간이 지나면 `search_sessions`과 `search_turns` 테이블이 무한 증가한다.
- **수정 방향:** 주기적 정리 작업(management command 또는 cron) 추가하여 일정 기간 이후의 비활성 세션 삭제.

---

### 6. 에러 핸들링

#### ✅ Rate Limiting
- `voice_transcribe`: 분당 5회, `search_chat`: 분당 10회 제한.
- 429 응답 시 JS에서 서버 메시지를 그대로 표시.
- **코드 근거:** `views.py:277,374`, `chatbot.js:198-199,253-254`

#### ✅ 네트워크 오프라인 감지
- `!navigator.onLine` 체크로 오프라인 상태 시 별도 메시지 표시.
- **코드 근거:** `chatbot.js:227,281`

#### ✅ 서버 에러 구분 처리
- `voice_transcribe`에서 `RuntimeError`(Whisper 에러)와 일반 `Exception`을 분리하여 다른 메시지 반환.
- **코드 근거:** `views.py:396-399`

#### ✅ JSON 파싱 에러
- `search_chat`에서 `json.JSONDecodeError` 시 400 응답.
- **코드 근거:** `views.py:283-285`

#### ✅ 빈 메시지 검증
- 빈 `user_text` 시 400 응답, JS에서도 빈 입력 전송 방지.
- **코드 근거:** `views.py:294-295`, `chatbot.js:64-65`

#### ✅ 오디오 파일 누락 검증
- `request.FILES.get("audio")`가 None이면 400 응답.
- **코드 근거:** `views.py:379-380`

#### ⚠️ Rate Limiter가 LocMemCache 사용
- `settings.py`에 `CACHES` 설정이 없으므로 Django 기본값인 `LocMemCache`가 사용된다. 뷰 코드 주석에도 이 점이 명시되어 있다(`views.py:21`). 프로덕션에서 gunicorn 멀티 워커 환경이면 워커별로 카운터가 분리되어 실질적 rate limit이 `N * max_requests`가 된다.
- **수정 방향:** 프로덕션 환경에서 Redis 캐시 백엔드로 전환하거나, django-ratelimit 같은 검증된 라이브러리 사용 권장.

---

### 7. 성능

#### ✅ DB 쿼리 최적화
- `select_related("primary_category")`, `prefetch_related("educations", "careers", "categories")`로 N+1 쿼리 방지.
- **코드 근거:** `search.py:105-107`, `views.py:199-203`

#### ✅ 임베딩 검색 제한
- `hybrid_search`의 `limit` 파라미터(기본 50)로 코사인 거리 정렬 결과를 제한.
- **코드 근거:** `search.py:144-168`

#### ⚠️ LLM 호출이 동기식 블로킹
- `call_llm()`이 동기 subprocess(claude_cli) 또는 동기 HTTP(OpenAI SDK)로 실행된다. `timeout=120`초로 설정되어 있어, 최악의 경우 gunicorn 워커가 2분간 블로킹된다.
- 음성 파이프라인은 Whisper API(최대 30초) + LLM 호출(최대 120초) = 총 최대 150초 블로킹 가능.
- **수정 방향:** 비동기 뷰 또는 Celery 태스크로 전환 검토. 단기적으로는 LLM `timeout`을 30초 이하로 줄이고 폴백 활용.

#### ⚠️ hybrid_search에서 전체 ID 목록 메모리 로드
- `candidate_ids = set(qs.values_list("id", flat=True))`가 필터 결과의 모든 ID를 메모리에 로드한다. 후보자가 수만 명이 되면 메모리와 쿼리 시간에 영향.
- **수정 방향:** 서브쿼리 방식으로 변경하여 DB 레벨에서 필터링하거나, `candidate_ids`가 일정 수 이상이면 시맨틱 검색 skip 고려.

#### ⚠️ Gemini 임베딩 API 호출 지연
- `get_embedding()`이 매 검색 요청마다 외부 API를 호출한다. 쿼리 벡터 캐싱이 없으므로 동일 쿼리 반복 시에도 매번 네트워크 왕복이 발생한다.
- **수정 방향:** 최근 쿼리 임베딩을 인메모리 또는 캐시에 저장하여 재사용 (LRU 캐시 등).

---

## 수정 필요 사항 (우선순위별)

### Critical
없음.

### Major

| # | 항목 | 위치 | 설명 |
|---|------|------|------|
| M1 | `broaden` 액션이 `new`와 동일 | `views.py:325-327` | `broaden`이 기존 필터를 참조하지 않아 "넓히기" 의미가 없음. 기존 필터 기반 완화 로직 필요. |
| M2 | 검색 필터에 나이/성별/지역 없음 | `search.py:40-68` | UI 칩 예시("강남 30대 여성")와 실제 필터 스키마 불일치. 모델에 필드는 있으나 필터 미구현. |
| M3 | 채팅 히스토리 innerHTML 직접 삽입 | `chatbot.js:404` | Content-Type 미검증. JSON 전환 또는 응답 검증 추가 권장. |

### Minor

| # | 항목 | 위치 | 설명 |
|---|------|------|------|
| m1 | 턴 번호 동시성 | `views.py:344` | unique constraint 없어 중복 가능. 실질적 위험은 낮음. |
| m2 | Whisper 타임아웃 30초 | `whisper.py:39` | 60초 녹음 시 부족할 수 있음. 60초로 상향 권장. |
| m3 | Hallucination 패턴 영어 미포함 | `whisper.py:13-26` | 영어 패턴 및 반복 텍스트 감지 추가 권장. |
| m4 | Rate limiter LocMemCache | `views.py:14-27` | 멀티 워커 환경에서 비효과적. Redis 전환 권장. |
| m5 | LLM 동기 블로킹 120초 | `search.py:81`, `common/llm.py:58` | 워커 고갈 위험. 타임아웃 단축 + 비동기화 검토. |
| m6 | 쿼리 임베딩 캐싱 없음 | `common/embedding.py:20-32` | 동일 쿼리 반복 시 불필요한 API 호출. LRU 캐시 권장. |
| m7 | 비활성 세션 정리 없음 | `candidates/models.py:302-318` | 세션/턴 데이터 무한 증가. 주기적 정리 필요. |
| m8 | MediaRecorder 미지원 브라우저 메시지 | `chatbot.js:136-161` | 권한 거부와 미지원을 동일하게 처리. 별도 분기 권장. |
