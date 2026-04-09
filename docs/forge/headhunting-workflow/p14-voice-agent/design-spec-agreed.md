# P14 Voice Agent - 확정 설계서

## 핵심 결정 요약

- **목표:** 기존 Whisper 보이스 검색을 대화형 에이전트로 확장. 모든 주요 화면에 마이크 버튼 배치, 음성/텍스트로 주요 업무 처리. 미팅 녹음 업로드 → STT + LLM 인사이트 추출 기능 추가.
- **URL 설계:** `/voice/` 독립 prefix (main/urls.py에 `path("voice/", include("projects.urls_voice"))` 추가). 하위 9개 엔드포인트.
- **파이프라인:** MediaRecorder → Whisper STT (use case별 프롬프트 분기) → Gemini Intent Parsing → Entity Resolution (후보자 식별) → Preview (dry-run) → 사용자 확인 → DB 저장
- **미팅 녹음 인사이트:** 별도 form에서 파일 업로드 → MeetingRecord 영속 저장 → 비동기 STT → LLM 구조화 분석 → 헤드헌터 확인 → 선택 항목 DB 반영 (항목별 매핑 정의)
- **서비스 구조:** `projects/services/voice/` 하위 7개 서비스 파일 (transcriber, intent_parser, action_executor, context_resolver, conversation, meeting_analyzer, entity_resolver)
- **프론트엔드:** voice-agent.js + voice_modal.html + voice_button.html. MediaRecorder API → WebM/Opus → FormData POST. 기존 chatbot FAB를 대체(통합).
- **컨텍스트 인식:** `data-voice-context` HTML 속성은 UX 힌트로만 사용. 실제 권한 검증은 서버에서 request.user + object permission으로 수행.
- **세션 관리:** Django 세션에 대화 상태 저장. 모달 닫기 또는 5분 비활성 시 초기화.
- **v1 접근:** 화자 분리 없이 전체 텍스트만 사용 가능.

## URL 설계

main/urls.py에 추가:
```python
path("voice/", include("projects.urls_voice")),
```

projects/urls_voice.py:
```
/voice/transcribe/          POST  음성→텍스트 변환
/voice/intent/              POST  텍스트→의도 파싱
/voice/preview/             POST  의도→미리보기 (dry-run, DB 변경 없음)
/voice/confirm/             POST  사용자 확인 후 DB 저장 (idempotent token)
/voice/context/             GET   현재 컨텍스트 조회
/voice/history/             GET   대화 히스토리 조회
/voice/meeting-upload/      POST  미팅 녹음 파일 업로드 (form 기반)
/voice/meeting-status/<id>/ GET   미팅 분석 상태 조회 (polling)
/voice/meeting-apply/       POST  분석 결과 선택 항목 DB 반영
```

**변경사항 (vs 초안):**
- `/voice/execute/` → `/voice/preview/` 로 rename (dry-run 의미 명확화)
- `/voice/meeting-analyze/` → `/voice/meeting-status/<id>/` 로 변경 (비동기 상태 polling)
- main/urls.py 변경 명시

## 파이프라인 (2단계 확인 패턴)

```
1. 음성 입력 → /voice/transcribe/ → 텍스트
2. 텍스트 → /voice/intent/ → intent + entities (미확정)
3. entities에 후보자 이름 포함 시 → Entity Resolution:
   - 이름으로 검색 → 결과 리스트 반환
   - 1건: 자동 선택 (컨텍스트 일치 시)
   - 복수: 사용자에게 선택 요청
   - 0건: "후보자를 찾을 수 없습니다" 안내
4. 확정된 entities → /voice/preview/ → 미리보기 결과 (DB 변경 없음)
5. 사용자 확인 → /voice/confirm/ (idempotent token) → DB 저장
```

## Intent 정의 (실제 모델 기반 수정)

| Intent | 설명 | 필수 엔티티 | 전제조건 |
|--------|------|------------|---------|
| `project_create` | 프로젝트 등록 | client, title | — |
| `contact_record` | 컨택 결과 기록 | candidate, channel, contacted_at, result | 프로젝트 컨텍스트 필요 |
| `contact_reserve` | 컨택 예정 등록 | candidate_ids | 프로젝트 컨텍스트 필요, 7일 잠금 정책 적용 |
| `submission_create` | 추천 서류 생성 | candidate, template | INTERESTED 컨택 존재, 프로젝트별 중복 없음 |
| `interview_schedule` | 면접 일정 등록 | submission(auto-resolve), scheduled_at, type | PASSED submission만 대상 |
| `offer_create` | 오퍼 등록 | submission(auto-resolve), salary | 최신 인터뷰 합격 + 기존 offer 없음 |
| `status_query` | 현황 조회 | project(optional) | — |
| `todo_query` | 오늘 할 일 | — | — |
| `search_candidate` | 후보자 검색 | keywords | — |
| `navigate` | 화면 이동 | target_page | — |
| `meeting_navigate` | 미팅 녹음 업로드 화면 열기 | candidate(optional) | — |

**변경사항 (vs 초안):**
- `project_create`: position → title. 실제 모델 필드 반영.
- `contact_record`: channel/result만 → contacted_at, notes 추가. RESERVED 불가 명시.
- `contact_reserve`: 7일 잠금 정책 명시.
- `submission_create`: INTERESTED 전제조건, unique 제약, template 추가.
- `interview_schedule`: candidate → submission 기반. auto-resolve 가능.
- `offer_create`: candidate → submission 기반. eligibility 조건 명시.
- `meeting_upload` → `meeting_navigate`: 파일은 텍스트 intent에서 추출 불가. 네비게이션으로 변경.

### Entity Resolution (후보자 식별)

음성에서 후보자 이름이 추출되면 즉시 UUID로 변환하지 않음. 반드시 다음 과정을 거침:

1. **검색:** 이름 + 현재 프로젝트 컨텍스트로 후보자 검색
2. **단일 결과:** 컨텍스트 내 유일한 매칭 → 자동 선택 (사용자 확인 포함)
3. **복수 결과:** 리스트를 보여주고 사용자가 명시적 선택
4. **결과 없음:** "해당 후보자를 찾을 수 없습니다" 안내 + 재시도 유도

**submission auto-resolve:** candidate UUID + project 컨텍스트로 eligible submission을 자동 결정. 복수 eligible 시 선택 단계.

## 컨텍스트 인식

| 현재 화면 | 기본 컨텍스트 | 예시 |
|-----------|-------------|------|
| 대시보드 | 전체 | "레이언스 건 현황" → status_query |
| 프로젝트 상세 | 해당 프로젝트 | "홍길동 전화했는데 관심 있대" → contact_record |
| 서칭 탭 | 해당 프로젝트 + 검색 | "15년 이상 품질 경험" → search_candidate |
| 컨택 탭 | 해당 프로젝트 + 컨택 | "김영희 재컨택해야 해" → contact_reserve |
| 후보자 DB | 검색 | "삼성전자 출신 개발자" → search_candidate |

**보안 원칙:** `data-voice-context`는 프론트엔드 UX 힌트로만 사용. 서버는 이 값을 신뢰하지 않으며, 모든 액션에서 `request.user`의 organization 소속 여부와 대상 객체 접근 권한을 독립적으로 검증.

## 서비스/파일 구조

| 파일 | 역할 |
|------|------|
| `projects/services/voice/transcriber.py` | Whisper STT 래퍼. use case별 프롬프트/필터 분기 (command mode, meeting mode) |
| `projects/services/voice/intent_parser.py` | Gemini API 의도 파싱 + 엔티티 추출. 실제 모델 필드 기반 엔티티 스키마 |
| `projects/services/voice/entity_resolver.py` | 이름 → UUID 해소. 검색/매칭/사용자 선택 흐름 |
| `projects/services/voice/action_executor.py` | Intent별 미리보기(preview) + 실제 커밋(confirm). 기존 서비스 레이어 호출 |
| `projects/services/voice/context_resolver.py` | 화면 컨텍스트 → 파싱 힌트 변환. 서버 사이드 권한 검증 포함 |
| `projects/services/voice/conversation.py` | 멀티턴 대화 관리 (세션 기반) |
| `projects/services/voice/meeting_analyzer.py` | 미팅 녹음 분석 파이프라인 (비동기 STT + LLM 인사이트 추출) |

### Whisper STT 분기 (transcriber.py)

| Mode | 프롬프트 | Hallucination 필터 | 타임아웃 |
|------|---------|-------------------|---------|
| `command` | "헤드헌팅 업무 음성 명령입니다. 프로젝트, 컨택, 면접, 오퍼, 추천..." | 업무 명령 컨텍스트용 패턴 | 30초 |
| `meeting` | "헤드헌팅 미팅 녹음입니다. 후보자 면담, 연봉 협상, 경력 상담..." | 미팅 컨텍스트용 패턴 (검색 패턴 제외) | 300초 |
| `search` (기존) | 기존 whisper.py 그대로 호출 | 기존 패턴 유지 | 30초 |

기존 `candidates/services/whisper.py`는 candidates 앱 전용으로 유지. voice agent의 transcriber.py는 별도 구현.

## 프론트엔드 구현

| 파일 | 역할 |
|------|------|
| `static/js/voice-agent.js` | MediaRecorder, 대화 UI 제어 |
| `projects/templates/projects/partials/voice_modal.html` | 대화 모달 |
| `projects/templates/projects/partials/voice_button.html` | 플로팅 버튼 (base 템플릿 include) |

녹음: MediaRecorder API → WebM/Opus → FormData POST → `/voice/transcribe/`.
대화 UI: HTMX swap으로 메시지 추가. 세션 ID로 멀티턴 관리.

### 기존 UI 통합 계획

기존 `chatbot_fab.html` (candidates 챗봇) → voice agent의 `voice_button.html`로 대체:
1. `base.html`에서 `chatbot_fab.html` include를 `voice_button.html`로 교체
2. 기존 후보자 검색 기능은 voice agent의 `search_candidate` intent로 흡수
3. `candidates/static/candidates/chatbot.js`와 `voice-input.js`는 점진적 제거

## 세션 관리

Django 세션에 대화 상태 저장:
```python
request.session["voice_conversation"] = {
    "id": "uuid",
    "turns": [...],
    "pending_intent": "contact_record",
    "collected_entities": {"candidate": "uuid", "channel": "phone"},
    "missing_fields": ["contacted_at", "result"],
    "preview_token": "uuid",  # confirm 시 idempotent key
}
```
모달 닫기 또는 5분 비활성 시 세션 초기화.

## 미팅 녹음 인사이트 파이프라인

### 제한사항
- **허용 형식:** mp3, m4a, wav, webm
- **최대 파일 크기:** 100MB
- **최대 녹음 길이:** 120분 (초과 시 거부)

### 영속 모델: MeetingRecord

```python
class MeetingRecord(BaseModel):
    """미팅 녹음 분석 레코드."""
    class Status(models.TextChoices):
        UPLOADED = "uploaded"
        TRANSCRIBING = "transcribing"
        ANALYZING = "analyzing"
        READY = "ready"        # 분석 완료, 사용자 확인 대기
        APPLIED = "applied"    # 선택 항목 DB 반영 완료
        FAILED = "failed"

    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.CASCADE)
    audio_file = models.FileField(upload_to="meetings/audio/")
    transcript = models.TextField(blank=True)
    analysis_json = models.JSONField(default=dict, blank=True)
    edited_json = models.JSONField(default=dict, blank=True)  # 사용자 수정본
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED)
    error_message = models.TextField(blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
```

### 처리 흐름

1. **업로드** (`/voice/meeting-upload/`, form 기반 POST)
   - 파일 검증 (형식, 크기)
   - MeetingRecord 생성 (status=UPLOADED)
   - 비동기 처리 시작 (management command 또는 DB 기반 job queue)

2. **비동기 처리** (서버 사이드)
   - status → TRANSCRIBING: Whisper STT (meeting mode 프롬프트)
   - status → ANALYZING: LLM 구조화 분석
   - status → READY: 분석 완료
   - 실패 시: status → FAILED + error_message 기록

3. **상태 조회** (`/voice/meeting-status/<id>/`, GET)
   - 프론트엔드에서 polling (5초 간격)
   - READY 도달 시 분석 결과 UI 표시

4. **사용자 확인 + DB 반영** (`/voice/meeting-apply/`, POST)
   - 헤드헌터가 분석 결과 확인/편집
   - 선택 항목만 DB에 반영

### 분석 결과 항목별 DB 반영 매핑

| 분석 항목 | DB 반영 대상 | 반영 방식 |
|-----------|-------------|----------|
| 후보자 관심도/의향 | Contact.result (현재 프로젝트) | result 업데이트 (INTERESTED/NOT_INTERESTED 등) |
| 현재 연봉/희망 연봉 | Contact.notes 또는 Offer 참조용 메모 | notes에 append (구조화 태그) |
| 이직 가능 시기 | Contact.notes | notes에 append |
| 주요 경력 하이라이트 | Contact.notes | notes에 append |
| 우려 사항/질문 | Contact.notes | notes에 append |
| 다음 단계 액션 아이템 | 신규 Contact (RESERVED, next_contact_date 설정) | 자동 생성 |
| 전반적 미팅 분위기 | MeetingRecord.analysis_json 보존 | DB에 직접 반영하지 않음 (참조용) |
| 특이사항/메모 | Contact.notes | notes에 append |

**provenance:** 모든 DB 반영 시 `[미팅녹음분석 {meeting_record_id}]` 태그를 notes에 포함하여 출처 추적 가능.

Source: docs/plans/headhunting-workflow/P14-voice-agent.md

<!-- forge:p14-voice-agent:설계담금질:complete:2026-04-09T14:35:00Z -->
