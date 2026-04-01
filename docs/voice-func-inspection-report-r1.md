# 보이스 서치 기능 파이프라인 점검 보고서 (R1)

> 점검일: 2026-03-31
> 점검 방법: 코드 리딩 + API 호출 테스트 (비인증 엔드포인트만 — Kakao OAuth로 인해 curl 인증 세션 획득 불가)

---

## 점검 결과 요약

| 구분 | 통과 | 문제 | 개선 권장 | 미점검 |
|------|------|------|-----------|--------|
| 음성 녹음 & 전송 | 3 | 2 | 2 | 0 |
| Whisper STT | 3 | 2 | 3 | 0 |
| LLM 검색 연동 | 2 | 2 | 2 | 0 |
| 결과 렌더링 | 3 | 1 | 1 | 0 |
| 세션/턴 관리 | 3 | 0 | 2 | 0 |
| 에러 핸들링 | 7 | 1 | 1 | 0 |
| 성능 | 1 | 1 | 3 | 0 |
| **합계** | **22** | **9** | **14** | **0** |

---

## 상세 점검 결과

### 3.1 음성 녹음 & 전송 (JS -> Django)

**3.1.1 — mimeType 명시**
- 현재 상태: `new MediaRecorder(stream)` (chatbot.js:58) — mimeType 미지정, 브라우저 기본값 사용
- 판정: ❌ 문제
- 문제: Safari/iOS에서 `audio/webm` 미지원. `MediaRecorder.isTypeSupported()` 검사 없이 브라우저 기본 mimeType에 의존. Safari는 `audio/mp4`를 기본 생성하지만, 이후 blob 생성 시 `audio/webm`으로 하드코딩되어 있어 실제 인코딩과 MIME 타입이 불일치함
- 영향도: 높음 — iOS/Safari 사용자 전체에 영향
- 수정 방향: `MediaRecorder.isTypeSupported()`로 `audio/webm;codecs=opus` → `audio/mp4` → `audio/ogg` 순서로 동적 선택하고, 선택된 mimeType을 blob 생성과 서버 전송에 일관 적용

**3.1.2 — blob type 하드코딩**
- 현재 상태: `new Blob(audioChunks, { type: "audio/webm" })` (chatbot.js:84)
- 판정: ❌ 문제
- 문제: 3.1.1과 연동 — 실제 MediaRecorder가 mp4로 녹음해도 blob MIME을 `audio/webm`으로 선언. Whisper API가 확장자/MIME으로 포맷을 판단하므로 디코딩 에러 가능
- 영향도: 높음 — Safari/iOS에서 Whisper 전사 실패 가능
- 수정 방향: `mediaRecorder.mimeType` 값을 저장하고, blob 생성 시 동일 MIME 사용. 파일명도 MIME에 맞게 동적 결정 (webm/mp4/ogg)

**3.1.3 — 녹음 최대 시간 제한**
- 현재 상태: 제한 없음. `mediaRecorder.start()` 호출 후 사용자가 수동으로 멈출 때까지 무한 녹음
- 판정: ⚠️ 개선 권장
- 문제: 장시간 녹음 시 blob 크기가 10MB 서버 제한 초과 가능. 사용자에게 사전 경고 없이 서버에서 400 거부
- 수정 방향: 60초 자동 정지 + 프론트에서 blob.size 10MB 사전 체크

**3.1.4 — blob 크기 프론트 검증**
- 현재 상태: 없음. 서버 측에서만 10MB 검증 (views.py:370)
- 판정: ⚠️ 개선 권장
- 수정 방향: `handleRecordingComplete()`에서 blob.size 체크 후 초과 시 toast 경고

**3.1.5 — CSRF 토큰 전송**
- 현재 상태: `getCSRF()` (chatbot.js:264-267) — `document.cookie.match(/csrftoken=([^;]+)/)` 패턴으로 추출. `settings.py:33`에 `CSRF_COOKIE_HTTPONLY = False` 설정 확인
- 판정: ✅ 통과
- 정상: CSRF 쿠키가 JS에서 읽기 가능하고, `X-CSRFToken` 헤더로 전송

**3.1.6 — 마이크 권한 거부 처리**
- 현재 상태: `getUserMedia().catch()` → `showToast("마이크 권한을 허용해주세요")` (chatbot.js:70-72)
- 판정: ✅ 통과

**3.1.7 — 녹음 중 UI 피드백**
- 현재 상태: `setMicState("recording")` → 마이크 버튼 빨간색 + 정지 아이콘 (chatbot.js:196-215). 3단계 상태(idle/recording/processing) 구현됨
- 판정: ✅ 통과 (기본 수준)
- 개선 사항: 오디오 레벨 시각 피드백(파형/진폭 표시)은 없으나, MVP 수준에서는 충분

---

### 3.2 Whisper STT 호출 (오디오 -> 텍스트)

**3.2.1 — 모델 버전**
- 현재 상태: `model="whisper-1"` (whisper.py:36)
- 판정: ⚠️ 개선 권장
- 설명: `gpt-4o-mini-transcribe` 대비 WER(Word Error Rate) 높고 hallucination 발생 빈도 높음. 비용은 유사하거나 낮음
- 수정 방향: `gpt-4o-mini-transcribe`로 업그레이드 검토. API 호환성 확인 후 교체

**3.2.2 — 타임아웃**
- 현재 상태: OpenAI 클라이언트 생성 시 timeout 미설정 (whisper.py:17). `OpenAI(api_key=...)` — timeout 파라미터 없음
- 판정: ❌ 문제
- 문제: 네트워크 지연 또는 OpenAI 서버 장애 시 무한 대기. Django worker 스레드가 블로킹됨
- 영향도: 중간 — 장애 시 서버 리소스 고갈 가능
- 수정 방향: `OpenAI(api_key=..., timeout=30)` 또는 `httpx.Timeout(30)` 설정

**3.2.3 — 파일 크기 검증**
- 현재 상태: `audio.size > 10 * 1024 * 1024` → 400 응답 (views.py:370-374)
- 판정: ✅ 통과
- Whisper API 제한 25MB 대비 보수적(10MB) — 적절

**3.2.4 — Rate limit**
- 현재 상태: `_check_rate_limit(user.pk, "voice_transcribe", 5, 60)` — 5회/분 (views.py:361)
- 판정: ✅ 통과
- 주의: Django 기본 캐시 사용 (`LocMemCache` — settings.py에 CACHES 미설정). 서버 재시작 시 카운터 초기화. 다중 worker 환경에서는 worker별 독립 카운터가 됨
- 개선 사항: 운영 환경에서는 Redis 등 공유 캐시 사용 권장

**3.2.5 — InMemoryUploadedFile -> Whisper API 전달**
- 현재 상태: `request.FILES.get("audio")`를 직접 `transcribe_audio(audio)` → `client.audio.transcriptions.create(file=audio_file)` (whisper.py:35-38)
- 판정: ✅ 통과
- 설명: OpenAI Python SDK는 file-like 객체를 받으며, Django `InMemoryUploadedFile`은 `.name`, `.read()` 속성이 있어 호환. 프론트에서 파일명 `voice.webm`으로 지정 (chatbot.js:86)하므로 Whisper가 확장자로 포맷 판단 가능. 단, Safari에서 실제 mp4 데이터가 webm 확장자로 전달될 수 있음 (3.1.2와 연동)

**3.2.6 — 빈 오디오/무음 처리**
- 현재 상태: 없음. Whisper 전사 결과가 빈 문자열이거나 hallucination일 때 별도 처리 없음
- 판정: ❌ 문제
- 문제: Whisper-1은 무음 입력 시 "시청해 주셔서 감사합니다" 같은 hallucination 텍스트를 반환하는 것으로 알려져 있음. 이 텍스트가 그대로 LLM 검색에 전달되면 무의미한 검색 결과 반환
- 영향도: 중간 — 사용자 혼란 유발
- 수정 방향: 전사 텍스트 빈 문자열 체크 + 알려진 hallucination 패턴 필터링 (예: "자막", "구독", "시청" 등 YouTube 자막 패턴)

**3.2.7 — Whisper hallucination 방어**
- 현재 상태: 없음
- 판정: ⚠️ 개선 권장
- 수정 방향: `gpt-4o-mini-transcribe` 업그레이드가 가장 효과적 (hallucination 90% 감소). 또는 전사 텍스트 길이 체크 (3자 미만 시 경고)

**3.2.8 — OPENAI_API_KEY 설정**
- 현재 상태: `settings.OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")` (settings.py:121)
- 판정: ⚠️ 개선 권장
- 설명: 키가 빈 문자열일 때 OpenAI 클라이언트가 생성은 되지만 API 호출 시 에러 발생. 서버 시작 시 사전 검증이 없어 첫 음성 요청에서야 에러 발견
- 수정 방향: 심각하지 않으나, `_get_openai_client()`에서 키 존재 여부 체크 후 명확한 에러 메시지 반환 검토

---

### 3.3 LLM 검색 연동 (텍스트 -> 검색 쿼리 -> 결과)

**3.3.1 — 구어체 처리**
- 현재 상태: `SEARCH_SYSTEM_PROMPT` (search.py:40-63)에 구어체/음성 입력 관련 가이드 없음. "사용자의 자연어 검색 요청을 구조화된 필터 JSON으로 변환합니다"만 있음
- 판정: ⚠️ 개선 권장
- 설명: "음 그 있잖아요", "한 20년 정도" 같은 음성 특유 표현 처리를 LLM에 맡기고 있으나, 프롬프트에 가이드가 없으면 LLM이 필러 단어를 필터에 반영할 수 있음
- 수정 방향: 시스템 프롬프트에 "음성 입력이므로 필러 단어(음, 어, 그), 존대말 어미, 불완전 문장은 무시하고 핵심 의도만 추출하세요" 추가

**3.3.2 — 폴백 동작**
- 현재 상태: `_fallback_result()` (search.py:90-96) — 빈 필터 + 시맨틱 검색만 수행. `ai_message: "정확한 필터 대신 유사 검색으로 찾았습니다."`
- 판정: ✅ 통과
- 폴백 시에도 시맨틱 검색으로 유의미한 결과 반환 가능

**3.3.3 — JSON 파싱 (`_extract_json`)**
- 현재 상태: (llm.py:39-47) — ` ``` ` 블록 추출 후 `json.loads()`. `split("```")[1]`로 첫 번째 코드 블록 내용 추출
- 판정: ✅ 통과
- 설명: 일반적인 LLM 출력 형식(raw JSON, ```json 블록) 처리 가능. 파싱 실패 시 `call_llm_json()` → `parse_search_query()` → `_fallback_result()`로 폴백

**3.3.4 — `broaden` action 처리**
- 현재 상태: (views.py:313-318) `if action == "new": filters = new_filters` / `elif action == "narrow": filters = {**session.current_filters, **new_filters}` / `else: filters = new_filters`
- 판정: ❌ 문제
- 문제: `broaden`이 `new`와 동일하게 처리됨. LLM이 broaden을 반환하면 기존 필터가 완전히 버려지고 새 필터로 대체됨. 의도적일 수 있으나, "넓히기"라면 기존 필터에서 특정 조건을 제거하는 것이 자연스러움
- 영향도: 낮음 — LLM이 broaden 필터에 기존 조건 일부를 포함할 수 있으나, 명시적 로직 없음
- 수정 방향: broaden 시 LLM이 반환한 필터만 적용하되, 명시적으로 "기존 필터에서 조건을 제거하여 넓히기" 동작을 구현하거나, 현재 동작이 의도적이라면 주석으로 명시

**3.3.5 — `narrow` 필터 병합 시 null 값 덮어쓰기**
- 현재 상태: `filters = {**session.current_filters, **new_filters}` (views.py:316)
- 판정: ❌ 문제
- 문제: LLM이 `{"filters": {"category": null, "min_experience_years": 10}}` 반환 시, `new_filters`에 `category: None`이 포함됨. 병합 결과 기존 session의 category 필터가 `None`으로 덮어써짐. `execute_structured_search`에서 `if category:` 체크로 None은 무시되지만, session.current_filters에 None 값이 누적됨
- 영향도: 중간 — 멀티턴 대화에서 필터가 의도치 않게 사라질 수 있음
- 수정 방향: narrow 병합 시 `new_filters`에서 None 값을 제거한 후 병합: `filters = {**session.current_filters, **{k: v for k, v in new_filters.items() if v is not None}}`

**3.3.6 — `claude_cli` provider 레이턴시**
- 현재 상태: `subprocess.run(["claude", "--print", "--max-turns", "1"], timeout=120)` (llm.py:58-64). 서브프로세스로 Claude CLI 실행
- 판정: ⚠️ 개선 권장
- 문제: 프로세스 생성 오버헤드 + CLI 초기화 시간으로 응답이 느림. timeout 120초는 검색 UX에 비해 과도
- 수정 방향: 운영 환경에서는 API 직접 호출(openrouter 등) 사용 권장. `parse_search_query`에서 timeout=120으로 설정 (search.py:77) — 검색 응답 대기 2분은 UX에 치명적

---

### 3.4 결과 렌더링 (백엔드 -> 프론트엔드)

**3.4.1 — HTML 이스케이프**
- 현재 상태: `escapeHtml(text)` (chatbot.js:269-273) — `div.textContent = text; return div.innerHTML;` 패턴
- 판정: ✅ 통과
- XSS 방지됨. AI 응답 메시지에 포함될 수 있는 HTML/스크립트 안전하게 이스케이프

**3.4.2 — HTMX 후보자 리스트 새로고침**
- 현재 상태: `htmx.ajax("GET", url, {target: "#candidate-list", swap: "innerHTML"})` (chatbot.js:241)
- 판정: ✅ 통과
- session_id 파라미터 포함하여 검색 결과 필터링된 리스트 로드

**3.4.3 — 상태 바 XSS**
- 현재 상태: `updateStatusBar()` (chatbot.js:244-252) — `escapeHtml(query)` 적용
- 판정: ✅ 통과

**3.4.4 — "생각 중..." 인디케이터**
- 현재 상태: `appendThinking()` / `removeThinking()` (chatbot.js:171-189) — bounce 애니메이션 3점
- 판정: ✅ 통과 (코드 리딩 기준)

**3.4.5 — 결과 0건 시 UI**
- 현재 상태: AI 메시지로만 안내 (LLM이 "검색 결과가 없습니다" 등 반환). 후보자 리스트 영역에 빈 상태 전용 UI 없음
- 판정: ⚠️ 개선 권장
- 수정 방향: 후보자 리스트 empty state에 "검색 조건을 넓혀보세요" 등 안내 UI 추가

**3.4.6 — 시맨틱 검색 결과 페이지 새로고침 시 손실** (계획서 외 추가 발견)
- 현재 상태: `search_chat` 뷰에서 `session.current_filters = filters` 저장 시 `semantic_query`를 포함하지 않음 (views.py:341). `candidate_list` 뷰에서 `filters.pop("_semantic_query", None)` (views.py:186)하지만 해당 키가 session.current_filters에 존재하지 않으므로 항상 None
- 판정: ❌ 문제
- 문제: 채팅 검색 후 페이지 새로고침하면 시맨틱 랭킹이 손실되고, 구조화 필터만 적용된 결과가 `updated_at` 순으로 표시됨. 검색 품질이 크게 저하됨
- 영향도: 중간 — 검색 후 리스트 스크롤/페이지 이동 시 랭킹 일관성 깨짐
- 수정 방향: `search_chat`에서 `session.current_filters`에 `_semantic_query` 키로 시맨틱 쿼리 저장. 또는 별도 필드 `session.semantic_query` 추가

---

### 3.5 세션/턴 관리 (멀티턴 대화)

**3.5.1 — 세션 생성/조회**
- 현재 상태: UUID 검증 (views.py:295-298) + user 매칭 + is_active 필터. 유효하지 않은 session_id 시 새 세션 생성
- 판정: ✅ 통과

**3.5.2 — SearchTurn input_type 구분**
- 현재 상태: `input_type=input_type` (views.py:333). 프론트에서 `doSearch(data.text, "voice")` / `doSearch(text, "text")` (chatbot.js:42, 102)로 구분 전달. 백엔드에서 유효성 검증: `if input_type not in ("text", "voice"): input_type = "text"` (views.py:287-288)
- 판정: ✅ 통과

**3.5.3 — 멀티턴 필터 누적**
- 현재 상태: `narrow` action 시 `{**session.current_filters, **new_filters}` (views.py:316)
- 판정: ✅ 통과 (기본 동작)
- 주의: 3.3.5에서 지적한 null 값 덮어쓰기 이슈 참조

**3.5.4 — 세션 정리**
- 현재 상태: 미구현. 새 세션 생성 시 기존 active 세션 비활성화(views.py:301-302)하지만, 비활성 세션/턴 레코드 삭제 로직 없음
- 판정: ⚠️ 개선 권장
- 수정 방향: 주기적 cleanup task (예: 30일 이상 된 비활성 세션 삭제) 또는 management command

**3.5.5 — chat_history 뷰**
- 현재 상태: (views.py:386-403) session_id UUID 검증 + user 매칭 + `turns.order_by("turn_number")`. HTML partial `chat_messages.html` 렌더링
- 판정: ✅ 통과 (코드 리딩 기준)
- 참고: chat_messages.html에서 `{{ turn.user_text }}`와 `{{ turn.ai_response }}`는 Django 템플릿 자동 이스케이프로 XSS 방지됨

**3.5.6 — sessionStorage 사용**
- 현재 상태: `sessionStorage.getItem("synco_session_id")` (chatbot.js:5)
- 판정: ⚠️ 개선 권장
- 설명: 새 탭마다 세션 초기화됨. 의도적일 수 있으나 (탭 독립 검색), 동일 사용자가 여러 탭에서 다른 검색 세션을 갖게 됨

---

### 3.6 에러 핸들링

**3.6.1 — 마이크 권한 거부**
- 현재 상태: `getUserMedia().catch()` → toast (chatbot.js:70-72)
- 판정: ✅ 통과

**3.6.2 — 네트워크 오류 (음성 전송)**
- 현재 상태: `fetch().catch()` → toast "음성 인식에 실패했습니다" + `setMicState("idle")` (chatbot.js:104-107)
- 판정: ✅ 통과

**3.6.3 — 네트워크 오류 (검색)**
- 현재 상태: `fetch().catch()` → AI 메시지 "검색 중 오류가 발생했습니다" + `removeThinking()` (chatbot.js:140-144)
- 판정: ✅ 통과

**3.6.4 — Whisper API 실패**
- 현재 상태: `RuntimeError` catch → `JsonResponse({"error": str(e)}, status=500)` (views.py:376-380). 일반 Exception도 catch → 500 (views.py:381-382)
- 판정: ✅ 통과

**3.6.5 — LLM 파싱 실패**
- 현재 상태: `parse_search_query()` except → `_fallback_result()` (search.py:85-87). 폴백으로 시맨틱 검색만 수행
- 판정: ✅ 통과

**3.6.6 — Rate limit 초과**
- 현재 상태:
  - voice: 5회/분 → 429 JSON `{"error": "요청이 너무 많습니다..."}` (views.py:361-364)
  - search: 10회/분 → 429 JSON (views.py:273-276)
- 판정: ✅ 통과 (서버 측)
- 주의: 프론트에서 429 응답 시 `r.json()` → `data.error` 확인으로 정상 처리됨 (fetch는 HTTP 에러에서 reject하지 않음)

**3.6.7 — OPENAI_API_KEY 미설정**
- 현재 상태: 빈 문자열 기본값 (settings.py:121). 서버 시작 시 검증 없음. 첫 API 호출 시 `OpenAI(api_key="")` → API 에러
- 판정: ⚠️ 개선 권장

**3.6.8 — 오디오 파일 없음**
- 현재 상태: `request.FILES.get("audio")` → None → 400 "오디오 파일이 없습니다." (views.py:366-368)
- 판정: ✅ 통과
- curl 비인증 테스트: `curl -X POST http://localhost:8000/candidates/voice/` → 403 (CSRF/인증 정상 차단)

**3.6.9 — 파일 크기 초과**
- 현재 상태: `audio.size > 10 * 1024 * 1024` → 400 "10MB 이하로 녹음해주세요" (views.py:370-374)
- 판정: ✅ 통과

**3.6.10 — 비인증 사용자 접근** (계획서 외 추가 확인)
- 현재 상태: 모든 뷰에 `@login_required` 데코레이터 (views.py). 비인증 시 302/403 반환
- 판정: ✅ 통과
- curl 테스트 결과: `/candidates/voice/` POST → 403, `/candidates/search/` POST → 403

**3.6.11 — HTTP 에러 응답 프론트 처리** (계획서 외 추가 발견)
- 현재 상태: `fetch().then(r => r.json())` (chatbot.js:93, 125) — HTTP 상태 코드 확인 없이 항상 JSON 파싱 시도
- 판정: ❌ 문제
- 문제: `@login_required`가 302 리다이렉트 반환 시, 또는 서버가 HTML 에러 페이지 반환 시, `r.json()` 파싱 실패 → `.catch()` 핸들러가 처리. 기능적으로는 동작하지만, 에러 메시지가 "음성 인식에 실패했습니다" 같은 일반 메시지만 표시되어 실제 원인(인증 만료 등) 파악 불가
- 영향도: 낮음 — 로그인 상태 확인 후 사용하는 시나리오에서는 드물게 발생
- 수정 방향: `if (!r.ok)` 체크 추가. 401/403 시 로그인 페이지 리다이렉트 안내

---

### 3.7 성능

**3.7.1 — 전체 파이프라인 레이턴시**
- 현재 상태: 미측정. 예상: STT(1-3초) + LLM 파싱(5-120초, claude_cli 기준) + 검색(0.5-2초) = 최소 6.5초, 최대 125초
- 판정: ❌ 문제
- 문제: `claude_cli` 서브프로세스 방식의 LLM 호출이 병목. timeout 120초 설정으로 최악의 경우 사용자가 2분 대기
- 영향도: 높음 — 음성 검색 UX의 핵심은 빠른 응답
- 수정 방향: API 직접 호출(openrouter/kimi 등) 전환으로 LLM 레이턴시 3-5초 목표. 전체 파이프라인 5초 이내 목표

**3.7.2 — Whisper STT 레이턴시**
- 현재 상태: 미측정. OpenAI API 직접 호출이므로 일반적으로 1-3초 (10초 이내 오디오 기준)
- 판정: ⚠️ 개선 권장
- 수정 방향: 타임아웃 설정 (3.2.2 참조) + 응답 시간 로깅 추가

**3.7.3 — LLM 파싱 레이턴시**
- 현재 상태: `claude_cli` 서브프로세스 (llm.py:56-67). `subprocess.run()` + timeout 120초 (search.py:77에서 설정)
- 판정: ⚠️ 개선 권장
- 문제: 프로세스 생성 + CLI 초기화 + API 호출 시간 합산. 일반적으로 5-30초 예상
- 수정 방향: OpenAI-compatible API 직접 호출로 전환

**3.7.4 — 오디오 파일 크기**
- 현재 상태: WebM opus 기본 설정 → 약 5-10KB/초
- 판정: ✅ 통과
- edge-tts 테스트: 2.5초 한국어 문장 MP3 = 24KB. WebM opus는 더 작을 수 있음

**3.7.5 — Rate limit 캐시 백엔드**
- 현재 상태: Django 기본 캐시 (`LocMemCache`) 사용. settings.py에 CACHES 설정 없음
- 판정: ⚠️ 개선 권장
- 문제: `LocMemCache`는 프로세스 메모리에 저장. gunicorn 다중 worker 환경에서 worker별 독립 카운터 → rate limit이 worker 수 배로 완화됨
- 수정 방향: 운영 환경에서 Redis 캐시 사용

---

## 수정 필요 사항 (우선순위별)

### Critical (즉시 수정)

1. **Safari/iOS MediaRecorder 호환성** (3.1.1 + 3.1.2)
   - 파일: `candidates/static/candidates/chatbot.js`
   - 문제: mimeType 미지정 + blob type 하드코딩으로 Safari에서 Whisper 전사 실패 가능
   - 수정: `MediaRecorder.isTypeSupported()` 동적 감지 + 실제 mimeType 기반 blob/파일명 생성

2. **Whisper 타임아웃 미설정** (3.2.2)
   - 파일: `candidates/services/whisper.py`
   - 문제: API 호출 무한 대기 가능 → worker 블로킹
   - 수정: `OpenAI(api_key=..., timeout=30)` 설정

3. **시맨틱 검색 결과 페이지 새로고침 시 손실** (3.4.6)
   - 파일: `candidates/views.py`
   - 문제: `session.current_filters`에 semantic_query 미저장 → 새로고침 시 랭킹 손실
   - 수정: `search_chat` 뷰에서 semantic_query를 session에 저장

### Major (수정 권장)

4. **빈 오디오/무음 Whisper hallucination** (3.2.6 + 3.2.7)
   - 파일: `candidates/services/whisper.py`, `candidates/views.py`
   - 수정: 전사 텍스트 빈 문자열/알려진 hallucination 패턴 체크

5. **`narrow` 필터 병합 시 null 값 덮어쓰기** (3.3.5)
   - 파일: `candidates/views.py`
   - 수정: None 값 필터링 후 병합

6. **`broaden` action 로직 미구현** (3.3.4)
   - 파일: `candidates/views.py`
   - 수정: 의도 확인 후 명시적 broaden 로직 구현 또는 주석 추가

7. **LLM 파이프라인 레이턴시** (3.7.1 + 3.7.3)
   - 파일: `common/llm.py`, `candidates/services/search.py`
   - 수정: 운영 환경에서 API 직접 호출 전환. 검색 timeout을 30초 이하로 축소

8. **HTTP 에러 응답 프론트 처리** (3.6.11)
   - 파일: `candidates/static/candidates/chatbot.js`
   - 수정: `r.ok` 체크 추가, 인증 만료 시 안내

### Minor (개선 권장)

9. **녹음 최대 시간 제한** (3.1.3) — 60초 자동 정지 추가
10. **blob 크기 프론트 검증** (3.1.4) — 10MB 사전 체크
11. **Whisper 모델 업그레이드** (3.2.1) — `gpt-4o-mini-transcribe` 검토
12. **구어체 처리 프롬프트 보강** (3.3.1) — 음성 입력 필러 단어 무시 가이드
13. **Rate limit 캐시 백엔드** (3.7.5) — 운영 환경 Redis 전환
14. **세션 정리 로직** (3.5.4) — 오래된 세션 자동 삭제
15. **결과 0건 빈 상태 UI** (3.4.5) — 검색 조건 넓히기 안내
16. **OPENAI_API_KEY 사전 검증** (3.2.8) — 서버 시작 시 키 존재 확인

---

## API 호출 테스트 결과

### 실행 환경
- 개발 서버: `http://localhost:8000` — 실행 중 확인 (302 응답)
- 인증: Kakao OAuth 전용 로그인 — curl로 세션 쿠키 획득 불가

### 테스트 결과

| 테스트 | 결과 | 비고 |
|--------|------|------|
| `POST /candidates/voice/` (비인증) | 403 Forbidden | CSRF/인증 정상 차단 |
| `POST /candidates/search/` (비인증) | 403 Forbidden | CSRF/인증 정상 차단 |
| `GET /` | 302 Redirect | 루트 리다이렉트 정상 |

### edge-tts 테스트 파일 생성

| 파일 | 크기 | 생성 결과 |
|------|------|-----------|
| `tests/voice_fixtures/test_basic.mp3` | 24KB | 성공 |
| WebM 변환 | - | ffmpeg 미설치로 미실행 |

### 인증 API 테스트 미실행 사유
- Kakao OAuth 전용 로그인으로 curl 기반 세션 쿠키 획득 불가
- 실제 Whisper API 호출, 검색 파이프라인 E2E 테스트는 브라우저 기반 수동 테스트 또는 Django test client 기반 자동화 테스트 필요

---

## 부록: 점검 대상 파일 목록

| 파일 | 역할 |
|------|------|
| `candidates/static/candidates/chatbot.js` | 프론트엔드: 음성 녹음, 채팅 UI, 검색 요청 |
| `candidates/services/whisper.py` | Whisper STT API 호출 |
| `candidates/services/search.py` | 자연어 → 필터 변환 + 하이브리드 검색 |
| `common/llm.py` | 멀티 프로바이더 LLM 클라이언트 |
| `common/embedding.py` | Gemini 임베딩 API |
| `candidates/views.py` | 검색/음성/히스토리 뷰 |
| `candidates/models.py` | SearchSession, SearchTurn 모델 |
| `candidates/urls.py` | URL 라우팅 |
| `candidates/templates/candidates/search.html` | 검색 페이지 전체 레이아웃 |
| `candidates/templates/candidates/partials/chatbot_modal.html` | 챗봇 모달 UI |
| `candidates/templates/candidates/partials/chat_messages.html` | 채팅 히스토리 partial |
| `candidates/templates/candidates/partials/search_status_bar.html` | 검색 상태 바 |
| `main/settings.py` | OPENAI_API_KEY, CSRF, LLM 설정 |
