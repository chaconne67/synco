# synco 문서

이 폴더는 **마스터 문서 3종**과 **디자인 자료**, **과거 기록 아카이브**로 구성된다.

## 1. 마스터 문서 (단일 진실 소스)

`docs/master/` 아래에 위치한 3개 문서가 현재 시점의 진실이다. 다른 모든 문서보다 우선한다.

| 파일 | 내용 |
|---|---|
| [master/01-business-plan.md](master/01-business-plan.md) | 사업계획서 — 시장·경쟁·수익 모델·GTM·방어 전략 |
| [master/02-work-process.md](master/02-work-process.md) | 업무 프로세스 — 사용자 롤·온보딩·헤드헌팅 워크플로우·화면별 흐름·데이터 파이프라인·일일 시나리오 |
| [master/03-engineering-spec.md](master/03-engineering-spec.md) | 개발 기획문서 — 스택·인프라·앱·모델·URL·파이프라인·커맨드·배포·완성도 |

## 2. 디자인 자료

- [design-system.md](design-system.md) — Pretendard, 컬러 토큰, 컴포넌트 패턴. 모든 신규/리팩터링 화면의 기준
- [designs/](designs/) — 목업 진화, 대시보드 인터랙션 플랜, Phase×Application 재설계 FINAL-SPEC

`assets/ui-sample/*.html` 의 목업이 디자인 SoT이며, 코드가 이를 기준으로 재정리 중이다.

## 3. 아카이브

[archive/](archive/) — 이전 버전의 계획·검사·리뷰·담금질 기록. 역사적 맥락 참조용으로 보존되며, **마스터 문서와 충돌하면 마스터가 이긴다.** 자세한 인덱스는 [archive/README.md](archive/README.md).

---

## 문서 작성 규칙

- 모든 문서는 `docs/` 아래에 둔다 (루트에 `.md` 문서 생성 금지, README/CLAUDE 제외)
- 마스터 문서는 `docs/master/` 에서만 관리
- 진행 중인 실행 기록·담금질·리뷰는 `docs/archive/`가 아닌 새 위치에 쌓지 말고, 마스터에 반영하거나 commit 메시지로 남길 것
- 디자인 목업이 바뀌면 `docs/design-system.md`와 `docs/master/02-work-process.md` 를 동시에 업데이트
