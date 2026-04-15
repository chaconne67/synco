# Implementation Rulings — P07 Submission Basic CRUD

Status: COMPLETE
Last updated: 2026-04-08T19:00:00+09:00
Rounds: 1

## Resolved Items

### Issue 1: Status value mismatch [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 계획의 영어 기반 SubmissionStatus는 기존 한국어 저장값과 충돌. 기존 Submission.Status를 그대로 사용.
- **Action:** SubmissionStatus 별도 정의 삭제. 기존 Submission.Status (작성중/제출/통과/탈락) 재사용.

### Issue 2: template field migration strategy missing [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** template 필드를 blank=True, default=""로 추가하여 기존 데이터/테스트 호환.
- **Action:** template = CharField(max_length=20, choices=..., blank=True, default=""). notes, client_feedback_at도 nullable/blank.

### Issue 3: "추천 서류 작성 →" link doesn't exist yet [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 현재 컨택 탭에 해당 링크 없음. P07에서 추가해야 함.
- **Action:** tab_contacts.html에 "관심" 결과 행에 링크 추가. 해당 후보자의 기존 Submission이 없을 때만 표시.

### Issue 4: Organization scoping for Submission views [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Submission에 organization 필드 없으므로 Project를 통해 스코핑.
- **Action:** project = get_object_or_404(Project, pk=pk, organization=org) → submission = get_object_or_404(Submission, pk=sub_pk, project=project).

### Issue 5: Submission delete protection missing [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Interview/Offer CASCADE 연결로 삭제 보호 필수.
- **Action:** submission_delete에서 interviews.exists() 또는 offer 존재 시 차단 + 에러 메시지.

### Issue 6: HTMX CRUD flow undefined [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** HTMX 이벤트 기반 갱신 흐름 누락.
- **Action:** submissionChanged 이벤트, #submission-form-area, 204+HX-Trigger 패턴 contacts 탭과 동일.

### Issue 7: Download via HTMX conflict [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 파일 다운로드는 일반 <a href> 링크로 처리.
- **Action:** hx-get 없이 일반 링크. View는 FileResponse. 파일 없을 시 404.

### Issue 8: Form candidate filtering incomplete [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** SubmissionForm에 project 인자 필요.
- **Action:** SubmissionForm(organization, project) — 관심 후보자만 필터링, 기존 Submission 있는 후보자 제외.

### Issue 9: Project status transition rule ambiguous [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** "searching 이하" 표현이 모호.
- **Action:** "NEW 또는 SEARCHING일 때만" 으로 명시.

### Issue 10: File upload validation/tests insufficient [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 파일 검증 로직 및 테스트 누락.
- **Action:** clean_document_file() 추가 (확장자, 용량), enctype, 임시 스토리지 테스트.

### Issue 11: Security/isolation tests missing [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** login_required 및 조직 격리 테스트 누락.
- **Action:** 7개 URL 전체에 대해 login/org isolation 테스트 추가.

### Issue 12: State transition negative tests missing [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 부정 케이스 테스트 누락.
- **Action:** 작성중→피드백 불가, 제출 전 통과/탈락 불가, 재제출 불가, 종료 후 변경 불가 테스트 추가.

### Issue 13: Feedback UI undecided [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** "인라인 폼 또는 모달" placeholder 남아 있음.
- **Action:** 인라인 폼으로 확정. contacts 패턴 동일.

### Issue 14: Dead "면접 등록 →" link [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** P09 전 면접 생성 URL 없음.
- **Action:** disabled 상태로 표시 (회색, 클릭 불가, 툴팁).

## Disputed Items

(없음)
