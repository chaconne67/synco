# Implementation Rulings — P09: Interview & Offer

Status: COMPLETE
Last updated: 2026-04-08T20:30:00+09:00
Rounds: 1

## Resolved Items

### Issue 1: URL 설계의 UUID PK 충돌 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 계획서의 `<int_pk>`, `<off_pk>`를 `<uuid:interview_pk>`, `<uuid:offer_pk>`로 수정 필요. BaseModel UUID PK 규칙과 일치시킴.
- **Action:** URL 테이블 및 뷰 시그니처를 UUID 컨버터로 통일.

### Issue 2: Interview/Offer choice 값 한국어/영어 충돌 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 기존 모델의 한국어 DB 저장값(`대면/합격/협상중` 등)을 유지. 영어 토큰으로 변경하면 기존 데이터/템플릿/테스트 호환이 깨짐.
- **Action:** 기존 choice 값 유지, 새 필드(location, notes, decided_at)만 추가.

### Issue 3: closed_fail 규칙 성립 불가 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 오퍼 단계 도달 시 면접 이력이 이미 존재하므로 "면접 없음" 조건은 사실상 무의미. P09에서는 closed_fail 자동 전환을 제외.
- **Action:** closed_fail 자동 전환을 P09 범위에서 제외. 수동 전환으로만 처리.

### Issue 4: 오퍼 등록 가능 조건 모호 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** "면접 합격 Submission"만으로는 다회차 시나리오를 커버하지 못함.
- **Action:** "해당 Submission의 최신(max round) 인터뷰 결과가 합격"으로 명시. 폼 queryset + clean() 이중 검증.

### Issue 5: 수동 status_update 역전환 허용 [MAJOR]
- **Resolution:** REBUTTED
- **Summary:** `status_update`는 칸반 드래그앤드롭용 관리자 기능. P09 범위는 자동 전환 추가이지 수동 전환 제한이 아님. P07에서도 동일하게 자동 전환만 제한.

### Issue 6: HTMX 상호작용 계약 누락 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** P07 submission 패턴과 동일한 HTMX 규약 필요.
- **Action:** interviewChanged/offerChanged 이벤트, #interview-form-area/#offer-form-area, 204 + HX-Trigger 계약 추가.

### Issue 7: 중복 생성 런타임 검증 누락 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** OneToOne/unique 제약에 대한 폼 레벨 검증 없으면 IntegrityError 500 발생.
- **Action:** OfferForm에서 기존 Offer 있는 Submission 제외, InterviewForm에서 round 자동계산 + clean() 중복 검증.

### Issue 8: Interview 유니크 제약 추가 시 기존 데이터 [MAJOR]
- **Resolution:** REBUTTED
- **Summary:** P09까지 Interview 생성 뷰가 없었으므로 운영 DB에 데이터 0건. 데이터 정리 마이그레이션 불필요.

### Issue 9: 인증/조직 격리 테스트 누락 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 기존 P05/P07 패턴에 따라 모든 엔드포인트에 login_required + org isolation 테스트 필요.
- **Action:** 11개 엔드포인트 전부에 대해 테스트 클래스 추가.

### Issue 10: 상태 전이 실패 케이스 테스트 누락 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** P07 submission 패턴과 동일하게 서비스 레이어에서 전이 규칙을 강제하고 실패 케이스 테스트 필요.
- **Action:** Interview result/Offer status 전이 규칙 + InvalidTransition + 실패 테스트 추가.

### Issue 11: P07 "면접 등록 →" 진입 계약 불명확 [MINOR]
- **Resolution:** ACCEPTED
- **Summary:** P07의 `?candidate=` 프리필 패턴을 따라 `?submission=<uuid>` 진입 계약 명시 필요.
- **Action:** 면접 등록 뷰에서 query param 처리 + round 자동 제안 + P07 링크 활성화.

## Disputed Items

(없음)
