# 보이스 서치 기능 점검 보고서 R3

**점검일:** 2026-03-31
**점검 방식:** 제로 베이스 코드 리뷰 (기존 보고서 미참조)

---

## 1. 음성 녹음 & 전송

### 1.1 MediaRecorder mimeType 감지
- **파일:** `candidates/static/candidates/chatbot.js:89-108`
- **PASS** — `detectMimeType()`이 `audio/webm;codecs=opus` → `audio/webm` → `audio/mp4` → `audio/ogg;codecs=opus` → `audio/ogg` 순으로 fallback하며, 지원 타입이 없으면 빈 문자열 반환하여 브라우저 기본값 사용. `getMimeExtension()`도 mp4/ogg/webm 매핑 정상.

### 1.2 Blob 크기 검증
- **파일:** `candidates/static/candidates/chatbot.js:273`
- **PASS** — 프론트엔드에서 10MB 초과 시 차단. 백엔드(`views.py:404`)에서도 동일하게 10MB 검증. 이중 방어 정상.

### 1.3 CSRF 토큰 전송
- **파일:** `candidates/static/candidates/chatbot.js:285-288`
- **PASS** — `X-CSRFToken` 헤더로 쿠키에서 추출한 토큰 전송. `settings.py:33`에서 `CSRF_COOKIE_HTTPONLY = False`로 JS 접근 허용 설정 확인.

### 1.4 녹음 시간 제한
- **파일:** `candidates/static/candidates/chatbot.js:15, 127-129`
- **PASS** — 60초 타이머로 자동 정지. 잔여 10초부터 `animate-pulse` 경고.

### 1.5 스트림 정리
- **파일:** `candidates/static/candidates/chatbot.js:159`
- **PASS** — `mediaRecorder.onstop`에서 `stream.getTracks().forEach(t => t.stop())` 호출하여 마이크 릴리스.

### 1.6 마이크 에러 핸들링
- **파일:** `candidates/static/candidates/chatbot.js:170-180`
- **PASS** — `NotAllowedError`, `NotFoundError`, `NotReadableError` 개별 처리, 그 외는 텍스트 입력 유도 메시지.

---

## 2. Whisper STT

### 2.1 모델 및 타임아웃
- **파일:** `candidates/services/whisper.py:39, 65-68`
- **PASS** — `whisper-1` 모델, `language="ko"` 명시. httpx 타임아웃 30초.

### 2.2 Hallucination 방어
- **파일:** `candidates/services/whisper.py:13-26, 43-48`
- **PASS** — 한국어 Whisper 환각 패턴 12개 목록 검증. 빈 텍스트도 hallucination으로 처리.

### 2.3 빈 오디오 처리
- **파일:** `candidates/services/whisper.py:72-73` + `chatbot.js:308-312`
- **PASS** — 서버 측: 빈 텍스트 시 빈 문자열 반환 → 뷰에서 400 응답. 클라이언트 측: 빈 `data.text` 시 "음성이 감지되지 않았습니다" 메시지 표시.

### 2.4 문제점: Whisper API 파일명 전달

- **파일:** `candidates/views.py:410-411`, `candidates/services/whisper.py:65-66`
- **심각도:** LOW
- **설명:** `voice_transcribe` 뷰에서 `request.FILES.get("audio")`로 받은 `UploadedFile` 객체를 `transcribe_audio()`에 직접 전달한다. OpenAI SDK의 `audio.transcriptions.create(file=...)`는 파일 객체의 `.name` 속성을 사용하여 파일 형식을 유추한다. Django의 `UploadedFile.name`은 클라이언트가 보낸 파일명(`voice.webm` 등)을 사용하므로 대부분 정상 동작하지만, 만약 파일명에 확장자가 없거나 MIME과 불일치하면 Whisper가 형식 인식에 실패할 수 있다.
- **수정 방향:** 현재 chatbot.js:281에서 `"voice." + ext`로 명시적 확장자를 붙이고 있어 실질적 위험은 낮음. 다만, 방어적으로 서버에서도 `audio.name`을 확인하거나 덮어쓰는 것을 고려할 수 있음.

---

## 3. LLM 검색 연동

### 3.1 프롬프트 품질
- **파일:** `candidates/services/search.py:40-72`
- **PASS** — 시스템 프롬프트가 JSON 스키마를 명시하고, 카테고리 목록 주입, 음성 필러 단어 무시 규칙, 구어체 숫자 변환 가이드 포함. 충분히 구체적.

### 3.2 Action 처리 (new/narrow/broaden)
- **파일:** `candidates/views.py:329-348`
- **PASS** — 세 가지 액션 모두 구현. `new`: non-null 필터만 적용. `narrow`: 기존 필터에 non-null 병합. `broaden`: null/빈 값은 기존 필터에서 제거, 나머지는 업데이트. 알 수 없는 액션은 `new`와 동일 처리.

### 3.3 Null 필터 처리
- **파일:** `candidates/views.py:332`
- **PASS** — `non_null_filters = {k: v for k, v in new_filters.items() if v is not None}`로 LLM이 반환한 null 값이 기존 필터를 덮어쓰지 않도록 방어.

### 3.4 LLM 실패 Fallback
- **파일:** `candidates/services/search.py:93-104`
- **PASS** — `parse_search_query`에서 예외 발생 시 `_fallback_result()`가 빈 필터 + 시맨틱 검색만으로 결과 반환. 사용자 경험 단절 없음.

### 3.5 문제점: LLM 응답이 JSON이 아닌 경우의 에러 메시지 누출

- **파일:** `common/llm.py:40-47`, `candidates/services/search.py:93-95`
- **심각도:** LOW
- **설명:** `_extract_json()`에서 `json.loads()` 실패 시 `json.JSONDecodeError` 발생. `call_llm_json()`은 이를 catch하지 않고 전파하고, `parse_search_query()`의 bare `except Exception`이 잡아서 fallback 처리한다. 동작 자체는 정상이나, `call_llm_json()`의 호출자가 `parse_search_query`가 아닌 다른 곳이라면 예외가 전파될 수 있다. 현재 검색 파이프라인에서는 문제없음.

### 3.6 문제점: claude_cli 프로바이더의 timeout이 LLM 호출에서 subprocess 레벨

- **파일:** `common/llm.py:56-67`
- **심각도:** MEDIUM
- **설명:** `search.py:84`에서 `timeout=120`으로 호출하지만, `claude_cli` 프로바이더는 `subprocess.run(timeout=120)`으로 전체 프로세스 타임아웃이다. Claude CLI가 120초 동안 응답하지 않으면 `subprocess.TimeoutExpired` 예외가 발생하는데, 이 예외는 `RuntimeError`가 아니라 `subprocess.TimeoutExpired`이다. `parse_search_query()`의 bare `except Exception`이 잡긴 하지만, 120초 대기 동안 사용자가 응답 없이 기다려야 한다. 검색 요청에 120초는 과도하게 길다.
- **수정 방향:** 검색용 LLM 타임아웃을 30초 정도로 줄이고, `call_llm()`에서 `subprocess.TimeoutExpired`를 `RuntimeError`로 래핑하는 것을 고려.

---

## 4. 결과 렌더링

### 4.1 XSS 방어 (클라이언트)
- **파일:** `candidates/static/candidates/chatbot.js:544-548`
- **PASS** — `escapeHtml()` 함수가 `textContent` → `innerHTML` 패턴으로 HTML 이스케이프 처리. `appendUserMessage`, `appendAIMessage`, `updateStatusBar` 모두 `escapeHtml()` 사용.

### 4.2 XSS 방어 (서버 렌더링)
- **파일:** `candidates/templates/candidates/partials/chat_messages.html:25, 33`
- **PASS** — Django 템플릿의 `{{ turn.user_text }}`와 `{{ turn.ai_response }}`는 기본 auto-escape로 XSS 방어.

### 4.3 XSS 방어 (검색 상태바 서버)
- **파일:** `candidates/templates/candidates/partials/search_status_bar.html:6`
- **PASS** — `{{ last_turn.user_text }}`도 Django auto-escape 적용.

### 4.4 HTMX 후보자 목록 갱신
- **파일:** `candidates/static/candidates/chatbot.js:513-517`
- **PASS** — `refreshCandidateList()`가 `htmx.ajax("GET", url, {target: "#candidate-list", swap: "innerHTML"})` 호출. session_id 포함하여 검색 결과 반영.

### 4.5 빈 결과
- **파일:** `candidates/views.py:355-357`
- **PASS** — `result_count`가 0이어도 `ai_message`가 "0명의 후보자를 찾았습니다."로 표시. 클라이언트 측에서도 정상 렌더링.

---

## 5. 세션/턴 관리

### 5.1 세션 생성/조회
- **파일:** `candidates/views.py:314-323`
- **PASS** — `session_id`로 기존 세션 조회, 없으면 기존 활성 세션 모두 비활성화 후 새 세션 생성. `user=request.user` 조건으로 타 사용자 세션 접근 차단.

### 5.2 멀티턴
- **파일:** `candidates/views.py:364-376`
- **PASS** — `turn_number = session.turns.count() + 1`로 순차 턴 번호 부여. 세션 필터를 누적 업데이트하여 멀티턴 대화 지원.

### 5.3 문제점: turn_number 동시성 경합

- **파일:** `candidates/views.py:364`
- **심각도:** LOW
- **설명:** `turn_number = session.turns.count() + 1`은 동시에 두 요청이 들어오면 같은 번호가 부여될 수 있다. 프론트엔드에서 `isSearching` 플래그로 동시 요청을 막고 있고, 단일 사용자 시나리오에서는 실질적 문제가 되지 않지만, `turn_number`에 unique_together 제약이 없어 DB 레벨에서 보호되지 않는다.
- **수정 방향:** `unique_together = [("session", "turn_number")]` 추가 또는 DB 시퀀스 사용 고려. 현재 사용 패턴에서는 실질적 위험 낮음.

### 5.4 시맨틱 쿼리 저장
- **파일:** `candidates/views.py:360-361`
- **PASS** — `_semantic_query`를 세션 필터에 저장하여 페이지 새로고침 시에도 시맨틱 검색 랭킹 유지. `candidate_list` 뷰에서 `filters.pop("_semantic_query", None)`으로 꺼내 사용.

### 5.5 sessionId URL 복원
- **파일:** `candidates/static/candidates/chatbot.js:6-7, 370`
- **PASS** — URL 파라미터 `session_id` 우선, 없으면 `sessionStorage` fallback. 검색 후 `history.replaceState`로 URL에 `session_id` 반영. 새 탭/북마크에서 세션 복원 가능.

---

## 6. 에러 핸들링

### 6.1 HTTP 상태코드별 처리 (음성)
- **파일:** `candidates/static/candidates/chatbot.js:291-329`
- **PASS** — 401/403 → 로그인 필요, 429 → rate limit 메시지, 그 외 서버 에러 → 텍스트 입력 유도, 오프라인 → 인터넷 연결 확인.

### 6.2 HTTP 상태코드별 처리 (검색)
- **파일:** `candidates/static/candidates/chatbot.js:348-384`
- **PASS** — 동일 패턴으로 401/403, 429, 서버 에러, 오프라인 각각 처리.

### 6.3 서버 에러 응답
- **파일:** `candidates/views.py:417-420`
- **PASS** — `RuntimeError`는 에러 메시지 노출 (Whisper 한국어 메시지), 그 외 `Exception`은 일반 메시지. 내부 스택트레이스 미노출.

### 6.4 문제점: RuntimeError 메시지에 잠재적 내부 정보 포함

- **파일:** `candidates/services/whisper.py:82`, `candidates/views.py:417`
- **심각도:** LOW
- **설명:** `whisper.py:82`에서 `raise RuntimeError(f"음성 인식에 실패했습니다: {e}")`로 원본 예외 메시지를 포함하고, `views.py:417`에서 `str(e)`로 그대로 클라이언트에 전달한다. OpenAI API 에러 메시지에 API 키 일부나 내부 정보가 포함될 가능성이 있다.
- **수정 방향:** `views.py:417`에서 `RuntimeError`의 메시지를 그대로 전달하지 말고 고정 메시지 사용, 또는 `whisper.py`에서 원본 예외 메시지를 포함하지 않도록 변경.

### 6.5 JSON 파싱 에러
- **파일:** `candidates/views.py:298-300`
- **PASS** — `json.JSONDecodeError` catch하여 400 응답.

### 6.6 빈 메시지 검증
- **파일:** `candidates/views.py:309-310`
- **PASS** — 빈 `user_text`에 대해 400 응답.

---

## 7. 성능

### 7.1 LLM 레이턴시
- **파일:** `candidates/services/search.py:84-86`
- **참고:** `timeout=120, max_tokens=500`. 실제 검색 응답 시간은 LLM 프로바이더 의존적. `claude_cli`는 subprocess 오버헤드 추가.
- **문제점:** 상기 3.6 참조. 120초 타임아웃이 과도함.

### 7.2 Rate Limiter
- **파일:** `candidates/views.py:14-34`
- **설명:** `LocMemCache` 기반. 음성: 5회/60초, 검색: 10회/60초.

### 7.3 문제점: Rate Limiter의 TTL 갱신 경합

- **파일:** `candidates/views.py:30-33`
- **심각도:** LOW
- **설명:** `cache.incr(key)` 실패 시 `cache.set(key, count + 1, period_seconds)` fallback으로 TTL이 재설정된다. 즉, rate limit 기간이 마지막 요청 기준으로 연장될 수 있다. 예: 59초에 요청하면 TTL이 다시 60초로 리셋. 단, `cache.incr`이 성공하는 일반적인 경우에는 TTL이 유지되므로, `ValueError` fallback 경로에서만 발생.
- **수정 방향:** fallback 경로에서 `cache.set` 대신 남은 TTL을 계산하여 설정하거나, 슬라이딩 윈도우가 의도된 동작이라면 문서화.

### 7.4 문제점: LocMemCache의 멀티 워커 한계

- **파일:** `candidates/views.py:21-22` (주석으로 인지)
- **심각도:** MEDIUM (운영 환경 한정)
- **설명:** 코드 주석에 "production with multiple workers, use Redis" 명시. 현재 Docker Swarm에서 gunicorn 멀티 워커 구성이라면 워커별 독립 카운터로 rate limit이 N배 느슨해짐. 개발 환경에서는 문제없음.
- **수정 방향:** 운영 배포 시 Redis 캐시 백엔드 전환 필요. 이미 인지된 사항이므로 우선순위만 확인.

### 7.5 Hybrid Search 성능
- **파일:** `candidates/services/search.py:164-188`
- **참고:** `candidate_ids`를 먼저 구해서 `CandidateEmbedding.objects.filter(candidate_id__in=candidate_ids)` 수행. 후보자 수가 수천 이상이면 `IN` 쿼리가 느려질 수 있으나, `limit=200`(뷰 호출)으로 상위에서 제한되지 않음 — `hybrid_search`의 `limit=50` 기본값 대비 `candidate_list` 뷰에서 `limit=200` 호출. `values_list("id", flat=True)`의 반환 크기에 상한이 없다.
- **심각도:** LOW — 현재 데이터 규모에서는 문제없을 것으로 보이나, 후보자 수 증가 시 모니터링 필요.

---

## 8. 보안

### 8.1 XSS
- **PASS** — 상기 4.1~4.3 참조. 클라이언트/서버 양쪽 모두 이스케이프 처리.

### 8.2 CSRF
- **PASS** — 모든 POST 요청에 `X-CSRFToken` 헤더 포함. Django CSRF 미들웨어 활성화 (`settings.py:63`). 쿠키 설정 정상 (`CSRF_COOKIE_HTTPONLY = False`).

### 8.3 인증
- **PASS** — 모든 뷰에 `@login_required` 데코레이터. 세션 조회 시 `user=request.user` 필터로 타 사용자 데이터 접근 차단.

### 8.4 세션 데이터 격리
- **파일:** `candidates/views.py:185-187, 315-317, 437`
- **PASS** — `SearchSession.objects.filter(pk=session_id, user=request.user)` 패턴으로 IDOR 방어.

### 8.5 파일 업로드 검증
- **파일:** `candidates/views.py:404`
- **PASS** — 파일 크기 10MB 제한. Whisper API가 파일 형식 검증 수행.

### 8.6 운영 보안 설정
- **파일:** `main/settings.py:193-199`
- **PASS** — 운영 시 `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS 설정 활성화.

---

## 요약

| 영역 | 판정 | 지적 사항 수 |
|------|------|------------|
| 음성 녹음 & 전송 | PASS | 0 |
| Whisper STT | PASS (경미한 개선점 1) | 1 LOW |
| LLM 검색 연동 | PASS (개선점 2) | 1 LOW, 1 MEDIUM |
| 결과 렌더링 | PASS | 0 |
| 세션/턴 관리 | PASS (경미한 개선점 1) | 1 LOW |
| 에러 핸들링 | PASS (경미한 개선점 1) | 1 LOW |
| 성능 | PASS (개선점 3) | 2 LOW, 1 MEDIUM |
| 보안 | PASS | 0 |

### MEDIUM 이슈 (2건)

1. **LLM 타임아웃 120초 과도** (`search.py:84`) — 검색 UX상 30초 이내가 적절. 사용자가 2분간 대기하는 상황 발생 가능.
2. **LocMemCache rate limiter가 멀티 워커에서 무력화** (`views.py:21`) — 운영 배포 시 Redis 전환 필요 (코드 주석으로 인지됨).

### LOW 이슈 (5건)

1. Whisper 파일명 의존성 (현재 프론트에서 확장자 보장)
2. LLM JSON 파싱 실패 시 예외 전파 경로 (현재 bare except으로 방어)
3. turn_number 동시성 경합 (프론트 isSearching으로 실질 방어)
4. RuntimeError 메시지에 내부 정보 포함 가능성
5. Rate limiter TTL fallback 경로에서 기간 연장

### 전체 판정

**PASS** — 심각한 결함 없음. 파이프라인 전체가 방어적으로 잘 구현되어 있음. MEDIUM 이슈 2건은 운영 품질 향상을 위해 순차 개선 권장.
