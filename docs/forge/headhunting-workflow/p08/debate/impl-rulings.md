# Implementation Rulings — p08

Status: COMPLETE
Last updated: 2026-04-08T12:00:00+09:00
Rounds: 1

## Resolved Items

### Issue 1: 입력 데이터 필드 `parsed_data`가 존재하지 않음 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Candidate 모델에 `parsed_data` 필드는 없다. 실제 데이터 소스(기본 필드, JSON 필드, 관련 모델)를 명시적으로 열거한다.
- **Action:** 초안 생성 서비스의 입력을 Candidate 기본 필드 + JSON 필드 + Career/Education/Certification/LanguageSkill 쿼리셋으로 정의. `parsed_data` 참조 제거.

### Issue 2: PDF 변환 의존성(reportlab) 미설치 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** reportlab이 설치되어 있지 않으므로 PDF 전략을 재정의한다.
- **Action:** Word(python-docx) 생성을 기본으로 하고, PDF 변환이 필요하면 의존성 추가 단계를 계획에 포함. 1차 구현은 Word만 지원, PDF는 후속 또는 선택적 의존성으로 처리.

### Issue 3: SubmissionDraft 생성 시점 미정의 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** draft 진입점에서 `get_or_create()`로 lazy 생성. 기존 Submission 생성 로직 변경 불필요.
- **Action:** `submission_draft` 뷰에서 `SubmissionDraft.objects.get_or_create(submission=submission)` 사용. 기존 데이터 backfill 불필요.

### Issue 4: 상태 전이 규칙 누락 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** P07 패턴을 따라 draft 전용 상태 전이 서비스 추가.
- **Action:** `projects/services/draft_pipeline.py`에 허용 전이 맵 + `InvalidTransition` 예외 정의. 회귀 전이(reviewed→finalized, converted→reviewed) 허용.

### Issue 5: 기존 제출 흐름이 AI 파이프라인을 우회 가능 [CRITICAL]
- **Resolution:** PARTIAL
- **Summary:** AI 파이프라인 강제는 과도하나, 제출 시 document_file 존재 검증은 추가한다. 직접 업로드 경로 유지.
- **Action:** `submit_to_client()` 호출 전 `document_file` 존재 검증 추가. Draft 변환 완료 시 자동 복사되므로 파이프라인 사용자도 자연스럽게 충족.

### Issue 6: UI 진입점 누락 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 추천 탭에 "초안 작업" 버튼 추가 필요.
- **Action:** `tab_submissions.html`에 Submission 카드별 "초안 작업" 버튼 추가. `hx-get` + `hx-target="#main-content"` + `hx-push-url="true"`.

### Issue 7: 템플릿 full-page vs partial 구분 누락 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** draft 메인 화면은 full-page, 각 단계는 partial로 분리.
- **Action:** `submission_draft.html` (full page, 동적 extends) + `partials/draft_step_*.html` (단계별 partial) 구조 확정.

### Issue 8: template/language 필드 중복 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** SubmissionDraft에서 template 필드 제거, submission.template 참조. output_language만 유지.
- **Action:** SubmissionDraft 모델에서 `template` 필드 삭제. `output_language` 기본값은 submission.template에서 derive.

### Issue 9: 삭제 보호 규칙 미반영 [CRITICAL]
- **Resolution:** PARTIAL
- **Summary:** Draft는 Submission 부속물이므로 CASCADE 삭제 유지. converted 상태 시 경고만 추가.
- **Action:** 삭제 시 draft가 converted 상태이면 확인 경고 메시지. CASCADE 삭제 유지, 별도 차단 불필요.

### Issue 10: 오디오 업로드 검증 누락 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 오디오 파일 검증 규칙을 계획에 추가.
- **Action:** 허용 확장자(.webm, .mp4, .m4a, .ogg, .wav, .mp3), 최대 25MB, Content-Type 검증, 빈 파일 거부.

### Issue 11: 테스트 계획 부족 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** P07 수준으로 테스트 범위 확대.
- **Action:** login_required, org isolation, HTMX 응답, invalid transition, AI API 실패, 오디오 검증 테스트 추가.

## Disputed Items

(없음)
