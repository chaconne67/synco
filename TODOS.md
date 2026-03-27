# TODOS

## Phase 1 (MVP)

### Contact 중복 방지 + CEO 계정 연결 전략
**What:** CSV 임포트, 카톡 파싱, 수동 생성, CEO 가입 시 기존 Contact와 자동 매칭
**Why:** 3,000명 임포트 시 중복 발생 불가피. CEO가 Kakao OAuth로 가입할 때 FC가 이미 등록한 Contact 레코드와 연결 필요 (ceo_user_id)
**Pros:** 데이터 무결성 보장, CEO 가입 즉시 기존 관계 데이터 활용 가능
**Cons:** 한국 이름 비고유성 문제, 전화번호 포맷 다양성
**Context:** 전화번호 정규화 (010-1234-5678 → 01012345678) + 회사명+이름 조합 fuzzy matching. CSV 임포트 전에 해결해야 함.
**Depends on:** Pydantic schema 입력 검증 (eng review에서 결정)
**Priority:** HIGH — CSV 임포트 (Week 5) 전까지 구현

### DESIGN.md 디자인 시스템 토큰 정의
**What:** 최소 디자인 시스템 문서 생성. 폰트(Pretendard), 컬러(primary #5B6ABF + semantic colors), 스페이싱(4px 배수), 컨포넌트 패턴(card/button/input/nav/modal), responsive 브레이크포인트(sm/md/lg).
**Why:** 구현 일관성의 기초. AI 코딩으로 여러 화면을 빠르게 만들 때 디자인 토큰이 없으면 화면마다 스타일이 달라짐.
**Pros:** 구현 속도 향상 (매번 판단 안 해도 됨), 일관된 UX
**Cons:** 초기 작업 ~30분
**Context:** Tailwind config에 커스텀 토큰 반영. Pretendard 웹폰트 CDN 추가. 기존 #5B6ABF primary 유지하되 secondary/success/warning/error 정의. 현재 rounded-xl/2xl 혼재 → 용도별 규칙화.
**Depends on:** 없음
**Priority:** HIGH — Week 2 시작 전 완료

### OpenAI API 비용 트래킹 + 월간 예산 제한
**What:** 월간 토큰 사용량 카운터 + 예산 도달 시 AI 기능 graceful degradation
**Why:** 브리핑(on-demand) + 음성 메모(즉시) + 카톡 파싱(배치) + 다이제스트(주간) 합산 시 5-8만원 예산 초과 가능. 200+ 활성 연락처에서 확실히 초과.
**Pros:** 예산 초과로 서비스 중단 방지, 기능별 비용 파악으로 최적화 근거
**Cons:** 구현 복잡도 소폭 증가
**Context:** api_usage 테이블에 (user_id, feature, tokens_used, cost_krw, created_at) 기록. 월간 합산 > 예산이면 AI 기능을 캐시된 결과만 제공하거나 "이번 달 AI 사용량을 초과했습니다" 표시.
**Depends on:** AI briefing pipeline 구현 (Week 3)
**Priority:** MEDIUM — AI 기능 구현 직후

## Phase 2

### Cross-FC 매칭 데이터 모델 재설계
**What:** Match 테이블의 단일 fc_id 구조를 cross-FC 매칭 지원으로 변경. CEO 데이터 공유 동의 모델, 익명화 레이어, FC간 수익 분배 구조 설계.
**Why:** FC 내부 매칭("내 CEO 두 명이 비슷하다")은 무의미. 진짜 가치는 "다른 FC의 CEO가 당신 CEO에게 필요한 걸 갖고 있다" = cross-FC 매칭.
**Pros:** 매칭의 실제 가치 실현, 딜 중개 수수료 수익 모델의 전제
**Cons:** 데이터 공유 동의 법적 검토 필요 (PIPA), 신뢰 모델 설계 복잡
**Context:** Match 테이블에 fc_a_id, fc_b_id 추가. CEO가 매칭 참여 동의 시에만 데이터 노출. 초기에는 동일 GA 내 FC간 매칭으로 시작 (GA가 데이터 소유자이므로 권한 구조 단순). 이후 cross-GA 확장.
**Depends on:** CEO 회원가입 플로우 + 동의 화면 구현
**Priority:** Phase 2 Week 6-7
