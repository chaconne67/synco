# Implementation Rulings — p14-voice-agent

Status: COMPLETE
Last updated: 2026-04-10T01:00:00Z
Rounds: 1

## Resolved Items

### Issue 1: action_executor에 4개 write intent 누락 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** project_create, submission_create, interview_schedule, offer_create의 preview/confirm 핸들러가 구현계획에 없음.
- **Action:** 4개 intent의 preview/confirm 핸들러와 테스트를 Task 7에 추가.

### Issue 2: REQUIRED_ENTITIES가 설계서와 불일치 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** contact_record에 contacted_at 누락, submission_create에 template이 선택적으로 처리됨.
- **Action:** REQUIRED_ENTITIES를 설계서 기준으로 정확히 정렬. contacted_at과 template을 필수로 변경.

### Issue 3: contact_reserve 엔티티 파이프라인 단절 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** parser가 candidate_names를 출력하지만 view는 단일 candidate_name만 resolve, confirm은 candidate_ids를 기대. 파이프라인이 연결되지 않음.
- **Action:** list 기반 candidate resolution 추가. candidate_names -> 각각 resolve -> candidate_ids 생성.

### Issue 4: 멀티턴 흐름이 실제로 구현되지 않음 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 누락 필드 시 "추가 정보가 필요합니다"만 출력하고 후속 입력을 pending intent에 병합하지 않음. 리셋이 GET-only인 history에 POST 시도.
- **Action:** JS에서 후속 입력을 pending intent에 병합하는 continuation 로직 추가. reset 전용 엔드포인트 추가 또는 history를 POST 허용.

### Issue 5: search_candidate가 잘못된 endpoint에 연결 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** candidate_list는 q 파라미터를 읽지 않음. 실제 검색은 search_chat POST 엔드포인트 사용.
- **Action:** voice 검색 어댑터를 추가하여 기존 search_chat/search-session 흐름 재사용.

### Issue 6: contact_record confirm이 비즈니스 규칙 우회 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Contact.objects.create() 직접 호출로 중복 체크, RESERVED 잠금 해제를 건너뜀.
- **Action:** check_duplicate + 기존 view의 validation 경로를 통해 생성. RESERVED 잠금 해제 포함.

### Issue 7: resolve_submission이 offer_create에 불충분 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** status=PASSED만 필터링하고 is_submission_offer_eligible()과 기존 offer 존재 체크를 하지 않음.
- **Action:** intent별 submission resolution 분리. offer_create는 InterviewForm/OfferForm의 eligibility 로직 미러링.

### Issue 8: meeting upload에서 비동기 처리 시작 안 함 + candidate 검증 없음 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 업로드만 하고 "분석을 시작합니다" 메시지만 반환. candidate의 organization 소유 검증 없음.
- **Action:** 업로드 후 비동기 처리 시작 (subprocess 또는 threading). candidate 소유 검증 추가.

### Issue 9: 120분 최대 녹음 길이 검증 누락 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 설계서의 120분 제한이 validate_meeting_file에 구현되지 않음.
- **Action:** 오디오 파일 duration 추출/검증 추가. 테스트 포함.

### Issue 10: meeting_navigate UI 흐름 불완전 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** meeting_navigate가 POST-only API로 리다이렉트. 모달에 업로드/상태 부분 미포함. form select 빈 상태.
- **Action:** 미팅 업로드/상태를 voice 모달 내 패널로 통합. JS에 업로드/polling/apply 로직 추가.

### Issue 11: apply_meeting_insights가 설계서 DB 매핑과 불일치 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 모든 필드를 notes에 append하지만, 설계서는 interest_level → Contact.result 업데이트, action_items → RESERVED Contact 생성, mood → DB 반영하지 않음.
- **Action:** 필드별 매핑을 설계서 기준으로 정확히 구현.

### Issue 12: 테스트 커버리지 부족 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 11개 intent 중 3개만 테스트. view 엔드포인트, idempotency, CSRF, 비동기 처리 미테스트.
- **Action:** 모든 intent, entity resolution, 중복/잠금, preview-token, CSRF, 비동기, duration 검증, 미팅 필드별 DB 매핑 테스트 추가.

## Disputed Items

(없음)
