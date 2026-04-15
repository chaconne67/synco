# synco 문서

이 폴더는 **마스터 문서 3종**과 **디자인 시스템 문서**, 그리고 **삭제해도 무방한 과거 기록 아카이브**로 구성된다.

## 1. 마스터 문서 (단일 진실 소스, 자립 문서)

`docs/master/` 아래의 3개 문서가 synco의 사업·업무·구현을 모두 담는다. 이 세 문서만으로 모든 맥락을 파악할 수 있도록 자립적으로 작성되었다.

| 파일 | 내용 |
|---|---|
| [master/01-business-plan.md](master/01-business-plan.md) | 사업계획서 — 시장·경쟁·수익 모델·GTM·방어 전략 |
| [master/02-work-process.md](master/02-work-process.md) | 업무 프로세스 — 용어집·사용자 롤·온보딩·헤드헌팅 워크플로우·3층 상태 모델·ActionType 23종·화면별 흐름·데이터 파이프라인·크로스커팅 채널·일일 시나리오·권한 매트릭스 |
| [master/03-engineering-spec.md](master/03-engineering-spec.md) | 개발 기획문서 — 스택·인프라·앱·도메인 모델·Signal 로직·URL 맵·뷰 카탈로그·파이프라인·서비스 레이어 함수·커맨드·배포·Phase 로드맵 |

## 2. 디자인 자료

- [design-system.md](design-system.md) — Pretendard, 컬러 토큰, 컴포넌트 패턴. 모든 신규/리팩터링 화면의 기준
- `../assets/ui-sample/*.html` — UI 목업. 디자인 단일 진실 소스

## 3. 아카이브

[archive/](archive/) — 기획·담금질·검사·리뷰의 과거 기록. **언제든 통째로 삭제해도 된다.** 마스터 3종이 자립적이므로 archive를 참조하지 않는다. 역사적 맥락이 궁금할 때만 들여다본다.

---

## 문서 작성 규칙

- 모든 문서는 `docs/` 아래에 둔다 (루트에 `.md` 문서 생성 금지, `README.md`/`CLAUDE.md` 제외)
- 마스터 문서는 `docs/master/` 에서만 관리
- 마스터 문서에서 `docs/archive/` 를 링크하지 않는다. 모든 필요 내용은 마스터 자체에 녹여넣는다
- 디자인 목업이 바뀌면 `docs/design-system.md`와 `docs/master/02-work-process.md` 의 화면 설명을 동시에 업데이트
- 새 기획/결정은 마스터를 직접 편집한다. archive에 새 파일을 추가하지 않는다
