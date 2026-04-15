# Implementation Rulings — p03a

Status: COMPLETE
Last updated: 2026-04-08T12:00:00+09:00
Rounds: 1

## Resolved Items

### Issue 1: 파일 포맷 전제 충돌 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** text.py는 .doc/.docx만 지원. PDF/HWP를 "기존 활용"이라고 적은 것은 사실 오류.
- **Action:** 지원 포맷을 .doc/.docx + PDF(PyMuPDF 추가)로 수정. HWP는 P03a 범위에서 제외.

### Issue 2: jd_text vs jd_raw_text 필드 혼란 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 기존 jd_text와 신규 jd_raw_text의 역할이 미정의.
- **Action:** jd_text = 사용자 직접 입력, jd_raw_text = 파일/Drive에서 추출한 원문. analyze_jd()는 jd_raw_text or jd_text 순서로 읽음.

### Issue 3: requirements 스키마 비호환 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** requirements JSON이 FILTER_SPEC_TEMPLATE과 구조적으로 호환되지 않음.
- **Action:** requirements_to_search_filters() 매퍼 함수를 추가. 매핑 규칙을 구현계획서에 명시.

### Issue 4: 서칭 필터 연결 경로 부재 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** SearchSession 생성 → redirect 경로가 계획에 없음.
- **Action:** 프로젝트 상세에서 "후보자 서칭" 버튼 → requirements_to_search_filters() → SearchSession 생성 → /candidates/?session_id= redirect.

### Issue 5: Drive 파일 메타데이터 부재 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** jd_drive_file_id만으로는 포맷 판별 불가.
- **Action:** Drive 선택 즉시 다운로드 → 텍스트 추출 → jd_raw_text 영속화. file_id는 출처 참조용.

### Issue 6: 핵심 서비스 placeholder [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 모든 서비스 함수가 ... 상태로 실행 불가.
- **Action:** 확정 구현계획서에서 각 함수의 입출력 스키마, 알고리즘, 에러 처리를 구체화.

### Issue 7: 서비스 파일 경계 충돌 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** jd_analysis.py vs candidate_matching.py 소속 불일치.
- **Action:** jd_analysis.py = 분석/추출/필터변환, candidate_matching.py = 매칭/스코어링/Gap, jd_prompts.py = 프롬프트.

### Issue 8: P03a 범위 초과 (P05 영역 침범) [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 서칭 탭 UI 수정, 후보자 상세 Gap 리포트는 P05 영역.
- **Action:** P03a IN: JD 입력→추출→AI분석→결과저장→결과UI→서칭 세션 생성. OUT: 서칭 탭 내부, 후보자 상세 Gap UI.

### Issue 9: 업종/대학 티어 매핑 부재 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** industry 필드 미존재, 대학 티어 스코어링용 매핑 없음.
- **Action:** 업종 → 회사명/직무/키워드 텍스트 매칭으로 대체. 대학 티어 → UNIVERSITY_GROUPS 재활용. 매칭 불가 → "판정 불가" 표시.

### Issue 10: 인증/조직 격리 미명시 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 새 뷰의 보안 패턴이 계획에 없음.
- **Action:** 모든 새 뷰에 @login_required + _get_org() + organization 격리 명시. 테스트에 비인증/타조직 차단 포함.

### Issue 11: Gemini 실패 경로 미설계 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** None 반환 시 TypeError 발생 가능.
- **Action:** extract_jd_requirements() 실패 시 에러 메시지 표시, 기존 값 보존, max_retries=3 포함.

### Issue 12: JD 소스 상호배타 규칙 누락 [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 3가지 소스의 유효성 규칙과 소스 변경 시 정리 규칙 부재.
- **Action:** clean() 규칙 명시: 소스별 필수 필드, 소스 변경 시 기존 분석 리셋, 미입력 시 분석 비활성화.

### Issue 13: Gap 리포트 라우팅/모델 부재 [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Gap 리포트 UI 경로와 매칭 결과 저장 모델이 없음.
- **Action:** generate_gap_report() 서비스만 구현. UI는 프로젝트 상세 내 매칭 목록까지만. 개별 Gap 화면은 P05 이관.

### Issue 14: 범위 외 기능 혼입 [MAJOR]
- **Resolution:** REBUTTED
- **Summary:** 레드팀이 참조한 P03a-jd-analysis-pipeline.md는 docs/plans/에 있는 별도 문서이며, 현재 담금질 대상인 forge의 impl-plan.md에는 해당 기능(공지 초안, 보이스 JD)이 존재하지 않는다.

## Disputed Items

(없음)
