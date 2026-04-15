# Design Rulings — p12

Status: COMPLETE
Last updated: 2026-04-08T22:30:00+09:00
Rounds: 2

## Resolved Items

### Issue 1: Organization isolation vs reference models [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 레퍼런스 모델은 전역 시스템 마스터로 organization 필드 없음. 조직 격리 예외 명시.
- **Action:** 설계서에 "조직 격리 예외" 섹션 추가. CRUD는 staff 전용, 읽기는 전체 사용자.

### Issue 2: URL routing mismatch (/reference/ vs /clients/) [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** /reference/ URL을 위해 main/urls.py 수정 + clients/urls_reference.py 별도 생성.
- **Action:** 산출물에 main/urls.py 수정, clients/urls_reference.py 추가.

### Issue 3: Sidebar HTMX target mismatch [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** hx-target="main"은 오타. #main-content로 수정.
- **Action:** 사이드바 메뉴 hx-target을 #main-content로 수정.

### Issue 4: Tab container id inconsistency [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** 탭 전환 target을 #ref-tab-content로 통일.
- **Action:** 탭 전환 hx-target을 #ref-tab-content로 통일. reference_index.html에 해당 div 배치.

### Issue 5: Schema migration strategy missing [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** P01 대비 필드 추가/변경/삭제 목록 + 마이그레이션 전략 포함.
- **Action:** 모델별 필드 변경 내역 명시. 빈 테이블이므로 AddField/AlterField/RemoveField로 처리.

### Issue 6: University tier system incompatibility [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** S/A/B → SKY/SSG/JKOS 등으로 전환. 매핑표 포함.
- **Action:** 티어 매핑표 추가. choices를 10개로 재정의.

### Issue 7: Name-based upsert fragile [CRITICAL]
- **Resolution:** PARTIAL
- **Summary:** 모델별 자연키 분리. 대학은 (name, country), 자격증은 name unique, 기업은 name unique + 충돌 시 에러 리포트.
- **Action:** unique constraint 추가. CSV import 충돌 처리 로직 명시.

### Issue 8: CSV import preview flow undefined [CRITICAL]
- **Resolution:** PARTIAL
- **Summary:** 미리보기 단계 제거. 단일 POST + 즉시 처리 + 결과 리포트로 간소화.
- **Action:** "미리보기 → 확인" 문구 삭제. 즉시 처리 + 결과 리포트 패턴으로 변경.

### Issue 9: CSV import error handling rules missing [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** 헤더 검증, 인코딩 규칙, 트랜잭션 롤백, 에러 리포트 추가.
- **Action:** CSV import 규칙 섹션 추가 (필수 컬럼, UTF-8, 전체 롤백, 행 단위 에러).

### Issue 10: CSV export HTMX conflict [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** export는 일반 링크 + hx-boost=false + Content-Disposition: attachment.
- **Action:** CSV export를 HTMX 제외 일반 다운로드로 명시.

### Issue 11: Delete protection references undefined [MAJOR]
- **Resolution:** REBUTTED
- **Summary:** 현재 FK 참조가 없으므로 삭제 보호 불필요. 향후 FK 추가 시 구현.
- **Action:** 삭제 보호 요구 제거. 단순 삭제 허용.

### Issue 12: Autofill API dependency undefined [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Gemini API + Google Search grounding, 10초 타임아웃, 실패 시 빈값 + 토스트, 사용자 검토 후 저장.
- **Action:** 자동채움 상세 스펙 섹션 추가.

### Issue 13: Autofill data leak risk [MAJOR]
- **Resolution:** ACCEPTED (Round 2)
- **Summary:** CompanyProfile이 비상장사 포함하므로 외부 전송 안내 필요.
- **Action:** 자동채움 버튼에 외부 전송 안내 문구 표시. 명시적 사용자 액션으로만 호출. 자동 호출 금지.

### Issue 14: No permission model [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** CRUD는 staff 전용, 읽기는 전체 로그인 사용자.
- **Action:** staff 권한 체크 추가. @staff_member_required 또는 동등 데코레이터.

### Issue 15: aliases search/CSV rules missing [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** JSON 배열 저장, CSV는 세미콜론 구분, 대소문자 무시 검색.
- **Action:** aliases 데이터 계약 섹션 추가.

### Issue 16: Initial data source and refresh policy [MAJOR]
- **Resolution:** PARTIAL
- **Summary:** 데이터 소스 출처 명시. 정기 갱신은 P12 범위 밖. 수동 갱신은 CSV 업데이트 + 커맨드 재실행.
- **Action:** 데이터 소스 출처 섹션 추가. 갱신은 수동 재적재로 처리.

## Disputed Items

(none — all resolved)
