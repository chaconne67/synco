# P01 구현 쟁점 판정 결과

**Status:** COMPLETE
**Rounds:** 1

## 판정

| # | Issue | Severity | Verdict | Resolution |
|---|-------|----------|---------|------------|
| 1 | Pillow 미설치 | CRITICAL | ACCEPT | Organization.logo → FileField 변경 |
| 2 | MEDIA 설정 없음 | CRITICAL | ACCEPT | settings.py에 MEDIA_ROOT/MEDIA_URL 추가 |
| 3 | projects 이름 충돌 | MAJOR | PARTIAL | 앱 이름 유지. Candidate.projects rename은 P01 범위 밖. 주의사항 기록 |
| 4 | User company 필드 중복 | MAJOR | ACCEPT | 기존 필드 deprecation 방향 기록 (즉시 삭제는 아님) |
| 5 | migration 0017 누락 | MAJOR | REBUT | Django migration은 이름 기반. gap은 무해 |
| 6 | Contact 이름 혼동 | MAJOR | ACCEPT | Client.contacts → contact_persons 변경 |
| 7 | Notification 배치 | MAJOR | ACCEPT | Notification → notifications 앱 분리 (또는 common) |
| 8 | 마스터 데이터 도메인 | MAJOR | PARTIAL | clients 앱 배치 유지 (P12 설계와 일관). 향후 분리 가능 |
| 9 | FK+unique → OneToOneField | MINOR | ACCEPT | Membership.user → OneToOneField |
| 10 | 권한 구현 전략 | MAJOR | PARTIAL | P01은 모델만. 권한 enforcement는 P02+. 테스트 축소 |
| 11 | TelegramBinding scope | MINOR | REBUT | accounts 확장과 일괄 처리 |
| 12 | data_extraction 미언급 | MINOR | REBUT | 무관한 앱 열거 불필요 |
| 13 | 과도한 모델 scope | MINOR | PARTIAL | SubmissionDraft → P08 이동. ProjectContext는 유지 |
