# Design Rulings — p14-voice-agent

Status: COMPLETE
Last updated: 2026-04-09T14:30:00Z
Rounds: 1

## Resolved Items

### Issue 1: URL 설계가 현재 라우팅 구조와 맞지 않음 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** `/voice/` URL을 독립 prefix로 사용하려면 main/urls.py 변경이 필요. 설계서에 명시.
- **Action:** URL 설계를 `main/urls.py`에 `path("voice/", include("projects.urls_voice"))` 추가로 명시. 또는 projects.urls 내 `/voice/` prefix 사용 시 실제 URL이 `/projects/voice/...`임을 명시.

### Issue 2: execute와 confirm의 책임이 모순 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** `execute`는 preview/dry-run으로, `confirm`만 실제 DB commit으로 2단계 패턴 재정의.
- **Action:** 파이프라인을 Intent Parsing → Preview(execute) → 사용자 확인(confirm) → DB 저장으로 명확히 분리.

### Issue 3: 기존 Whisper 서비스가 범용 음성 에이전트에 부적합 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 기존 whisper.py의 프롬프트/필터가 검색 전용. use case별 분리 필요.
- **Action:** transcriber.py에서 mode(command/meeting) 파라미터에 따라 프롬프트/hallucination 필터를 분기. 기존 whisper.py는 candidates 전용으로 유지.

### Issue 4: 미팅 녹음 파이프라인에 비동기 처리 설계 없음 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 미팅 녹음 처리는 동기 불가. 파일 제한과 비동기 처리 흐름 추가.
- **Action:** 파일 제한(100MB, mp3/m4a/wav/webm), 비동기 처리(status polling), MeetingRecord 상태 머신(uploaded → transcribing → analyzing → ready → applied) 설계 추가.

### Issue 5: meeting_upload intent의 엔티티 계약이 불가능 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** audio_file은 텍스트 기반 intent에서 추출 불가. 네비게이션 intent로 변경.
- **Action:** `meeting_upload` intent를 "미팅 녹음 업로드 화면 열기" 네비게이션 intent로 변경. 실제 업로드는 별도 form/endpoint.

### Issue 6: project_create intent가 실제 모델과 맞지 않음 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Project 모델에 `position` 필드 없음. `title`이 position 역할.
- **Action:** 필수 엔티티를 `client, title`로 수정. `jd_text`는 선택적.

### Issue 7: contact_record와 contact_reserve가 실제 컨택 규칙을 반영하지 않음 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 실제 폼의 필수 필드와 비즈니스 규칙이 설계서에 누락.
- **Action:** `contact_record` 필수 엔티티를 `candidate, channel, contacted_at, result, notes`로 확장. `contact_reserve`는 `candidate_ids`와 잠금/만료 정책 명시.

### Issue 8: submission_create 필수 엔티티가 실제 조건 누락 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** INTERESTED 컨택 전제조건과 unique 제약이 누락.
- **Action:** 전제조건(관심 컨택, 중복 submission 없음)과 추가 필수 엔티티(template) 추가.

### Issue 9: interview_schedule는 submission 기반 작업 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** InterviewForm은 submission 기반. candidate만으로는 대상 특정 불가.
- **Action:** intent를 `submission(auto-resolve from candidate+project), scheduled_at, type, location` 기반으로 재정의.

### Issue 10: offer_create도 candidate 기준으로 정의 불가 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** OfferForm은 submission 1:1. eligible submission 자동 resolve 필요.
- **Action:** candidate+project 컨텍스트로 eligible submission 자동 resolve. 복수 eligible 시 선택 단계 추가.

### Issue 11: 후보자 식별/중복 해소 단계가 없음 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 음성에서 이름만 추출 시 동명이인 문제. 엔티티 해소 단계 필수.
- **Action:** 파이프라인에 entity resolution 단계 추가: 이름 검색 → 결과 리스트 → 사용자 선택 → UUID 확정.

### Issue 12: 미팅 영속 데이터 모델이 없음 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 다단계 미팅 처리에 영속 모델 필수.
- **Action:** `MeetingRecord` 모델(audio_file, transcript, analysis_json, status, candidate FK, project FK) 설계 추가.

### Issue 13: meeting_apply의 DB 반영 대상이 미정의 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 분석 결과 항목별 DB 반영 대상 매핑 필요.
- **Action:** 항목별 매핑 테이블 추가 (연봉/의향 → Contact notes, 경력 → Candidate, 액션 → Notification 등).

### Issue 14: data-voice-context 권한 경계 불명확 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 클라이언트 컨텍스트를 서버가 그대로 신뢰하면 안 됨.
- **Action:** "컨텍스트는 UX 힌트로만 사용, 권한 검증은 서버에서 request.user + object permission으로 수행" 명시.

### Issue 15: 기존 전역 음성 UI와의 공존/대체 계획 없음 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 기존 chatbot FAB와 voice-input.js와의 충돌 해소 필요.
- **Action:** 기존 chatbot FAB를 voice agent로 대체(통합). candidates 검색은 `search_candidate` intent로 흡수. migration plan 추가.

## Disputed Items

(없음)
