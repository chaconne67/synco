# Design Rulings — p10

Status: COMPLETE
Last updated: 2026-04-08T22:50:00+09:00
Rounds: 2

## Resolved Items

### Issue 1: 회사명 비노출 vs 파일명 규칙 충돌 [CRITICAL]
- **Resolution:** PARTIAL
- **Summary:** 비노출은 공지 본문에만 적용. 파일명은 내부 관리용으로 회사명 포함 허용.
- **Action:** 설계서에 "비노출 정책은 posting_text(공지 본문)에만 적용, 파일명은 내부 관리용" 명시.

### Issue 2: 상장구분 데이터 부재 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Client 모델에 상장구분 필드 없음. 간접 표현을 업종+규모 기반으로 변경.
- **Action:** 규칙을 `업종 + 규모(Client.size)` 기반으로 변경. 예시: "중견 의료기기 제조사".

### Issue 3: 담당자명 출처 미정의 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** request.user의 full_name으로 고정.
- **Action:** `get_posting_filename(project, user)` 시그니처로 변경.

### Issue 4: JD 입력 경로 불일치 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** jd_raw_text → jd_text 우선순위로 읽도록 변경.
- **Action:** 입력 정의를 `jd_raw_text or jd_text`로 수정.

### Issue 5: requirements 존재 가정 [CRITICAL]
- **Resolution:** PARTIAL
- **Summary:** requirements는 선택적 보조 데이터. JD 원문만으로 생성 가능.
- **Action:** 필수 = JD 원문, 선택 = requirements/client 정보.

### Issue 6: 비동기 메커니즘 부재 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 비동기 삭제. 사용자 명시 액션(POST 버튼)으로 변경.
- **Action:** "공지 생성" 버튼 클릭 → 동기 POST → posting_text 저장.

### Issue 7: 근무지/처우 데이터 소스 미정의 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 섹션별 데이터 소스 매핑 추가.
- **Action:** 포지션/업무/자격 → JD+requirements, 업종 → Client.industry, 근무지 → Client.region 또는 JD 추론, 처우 → JD 추론 또는 "협의".

### Issue 8: 덮어쓰기 정책 모호 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 기존 내용 있으면 덮어쓰기 확인 필수.
- **Action:** posting_text 비어있으면 바로 저장, 있으면 confirm 후 저장.

### Issue 9: 미게시 사이트 렌더링 모호 [CRITICAL]
- **Resolution:** REBUTTED (R2에서 레드팀 ACCEPT)
- **Summary:** DB에 존재하는 PostingSite 행만 렌더링. 와이어프레임의 미게시 행은 설명용 예시.
- **Action:** 설계서에 "DB 행만 표시" 명시. 와이어프레임 수정 불필요.

### Issue 10: unique_together vs 이력 추적 충돌 [MAJOR]
- **Resolution:** REBUTTED (R2에서 레드팀 ACCEPT)
- **Summary:** 추적 목적은 현재 상태 스냅샷. Submission과 동일한 패턴. 이력은 별도 피쳐.
- **Action:** 변경 없음.

### Issue 11: 삭제와 추적 목적 충돌 [MAJOR]
- **Resolution:** PARTIAL
- **Summary:** 하드 삭제를 소프트 삭제(is_active=False)로 변경.
- **Action:** 삭제 엔드포인트를 "비활성화"로 변경. UI에서 비활성 항목 숨김.

### Issue 12: posting_site_update 범위 모호 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 수정 엔드포인트로 전체 필드 수정 가능하게 명확화.
- **Action:** URL 설명을 "포스팅 사이트 수정"으로 변경.

### Issue 13: 실패 경로 테스트 누락 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 실패 경로 테스트 항목 추가.
- **Action:** Gemini 오류, JD 없음, 중복 등록, 공지 없는 다운로드, 덮어쓰기 취소 테스트 추가.

### Issue 14: TextChoices 저장값 컨벤션 위반 [MINOR]
- **Resolution:** REBUTTED (R2에서 레드팀 ACCEPT)
- **Summary:** 코드베이스에 이미 영어 slug 저장값 다수 사용. 외부 서비스 식별자는 영어 slug 적합.
- **Action:** 변경 없음. 프로젝트 컨텍스트의 "한국어 TextChoices" 문구는 향후 정확도 향상 고려.

## Disputed Items

(없음)
