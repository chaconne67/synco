# Implementation Rulings — p10

Status: COMPLETE
Last updated: 2026-04-08T23:40:00+09:00
Rounds: 2

## Resolved Items

### Issue 1: posting_site_add/update GET/POST vs POST-only [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 설계서 URL 메서드를 GET/POST로 수정. HTMX 인라인 폼 패턴에 필요.
- **Action:** 설계서 갱신 + 계획은 현재 GET/POST 그대로 유지.

### Issue 2: PostingSiteForm에 is_active 필드 누락 [MAJOR]
- **Resolution:** ACCEPTED (R2에서 저자가 수용)
- **Summary:** 합의 스펙이 is_active를 명시적으로 포함하므로 폼에 추가해야 함.
- **Action:** PostingSiteForm fields에 is_active 추가. 체크박스 위젯. 템플릿에도 렌더링.

### Issue 3: posting_site_update UniqueConstraint 위반 시 500 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 수정 시 site 변경으로 인한 IntegrityError 미처리.
- **Action:** try/except IntegrityError 처리 추가. 에러 메시지와 함께 폼 재렌더링.

### Issue 4: 소프트 삭제 후 재등록 불가 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** unique_together + soft delete = 비활성 레코드가 재등록 차단.
- **Action:** posting_site_add에서 기존 비활성 레코드 재활성화 로직 추가. 테스트 추가.

### Issue 5: 데이터 소스 매핑 프롬프트 부족 [MAJOR]
- **Resolution:** PARTIAL
- **Summary:** 프롬프트에 섹션별 우선순위 규칙을 더 명확히 추가.
- **Action:** POSTING_SYSTEM_PROMPT에 섹션별 데이터 소스 우선순위 규칙 명시.

### Issue 6: Gemini 오류 시 기존 posting_text 보존 테스트 누락 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** RuntimeError 시 기존 값 보존 검증 테스트 필요.
- **Action:** test_generate_runtime_error_preserves_existing 테스트 추가.

### Issue 7: 덮어쓰기 취소 테스트 불가 [MAJOR]
- **Resolution:** PARTIAL
- **Summary:** 서버사이드 overwrite 파라미터 추가로 테스트 가능하게.
- **Action:** posting_generate에 overwrite POST 파라미터 추가. 기존 내용 있고 overwrite 없으면 경고 UI 반환.

### Issue 8: Lint 실패 (unused imports) [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 미사용 import/변수 정리 필요.
- **Action:** Candidate import, 미사용 변수 등 제거.

### Issue 9: Task 5 기대 테스트 수 오류 [MINOR]
- **Resolution:** ACCEPTED
- **Summary:** 테스트 카운트 수정.
- **Action:** 기대 개수를 실제 수로 수정.

### Issue 10: 파일명 테스트 정확도 부족 [MINOR]
- **Resolution:** ACCEPTED
- **Summary:** 정규식으로 전체 형식 검증.
- **Action:** 파일명 테스트에 regex 패턴 매칭 추가.

## Disputed Items

(없음)
