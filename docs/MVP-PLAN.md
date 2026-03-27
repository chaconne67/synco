# synco MVP 개발 계획

**Version:** v2
**Date:** 2026-03-27
**Status:** CONFIRMED
**Base:** office-hours design doc (APPROVED) + 기술 스파이크 결과

---

## 전체 타임라인

| Phase | 기간 | 목표 | 산출물 |
|-------|------|------|--------|
| Phase 1 | Week 1-5 | 웹앱 MVP | PWA 배포 (VPS) |
| Phase 2 | Week 6-10 | AI 자동화 + 과금 | 매칭 엔진 + 결제 |

기술 스파이크 완료 (SPIKE-REPORT.md 참조). 네이티브 앱 불필요 판정 → 웹앱 단일 구조로 확정.

---

## 기술 스택

### Backend
- **Framework:** FastAPI (Python)
- **DB:** PostgreSQL (VPS 직접 운영)
- **ORM:** SQLAlchemy 2.0 + Alembic (마이그레이션)
- **Auth:** 카카오 OAuth2 (httpx + JWT)
- **AI:** OpenAI API (GPT-4o) — 브리핑 생성, 기업정보 분석
- **스케줄러:** APScheduler — 미팅 후 메모 리마인더 등 예약 작업
- **배포:** VPS (별도 인스턴스) + Nginx reverse proxy + Uvicorn

### Frontend
- **HTMX** — 서버 렌더링 + 부분 갱신 (SPA 없이 반응형 UX)
- **Jinja2** — 템플릿 엔진 (FastAPI 내장)
- **Tailwind CSS** — 스타일링
- **JavaScript** — HTMX로 안 되는 인터랙션만 바닐라 JS
- **PWA:** manifest.json + service worker (Push Notification + 홈 화면 설치)

### 선택 근거
- 창업자가 익숙한 스택 → 개발 속도 최대화
- FastAPI + HTMX: 백엔드 한 곳에서 전부 관리, 프론트 빌드 파이프라인 불필요
- VPS 직접 운영: 비용 통제 + 기존 운영 노하우 활용
- PostgreSQL 직접 운영: 데이터 완전 소유
- 네이티브 앱 불필요: 핵심 기능이 웹앱으로 충분히 구현 가능

---

## 핵심 설계 결정: 접점 기록 전략

### 문제
FC는 CEO와 통화/미팅 후 메모를 깜빡할 수 있다.

### 해결: 스마트 리마인더
네이티브 앱(통화 감지/녹음 연동) 대신, 미팅 일정 기반 Push 알림으로 메모 입력을 유도한다.

**플로우:**
```
FC가 미팅 일정 등록 (CEO 김대표, 3/28 14:00~15:00)
    ↓
미팅 종료 예정 시간 + 1시간 (16:00)
    ↓
메모 입력 여부 확인
    ↓
미입력 시 → PWA Push 알림
"김대표님 미팅은 어떠셨나요? 메모를 남겨주세요"
    ↓
알림 탭 → 메모 입력 화면 (음성 입력 가능)
```

**구현:**
- APScheduler로 미팅 종료 시간 + 1시간에 체크 작업 예약
- Interaction 테이블에 해당 미팅 관련 메모가 없으면 Push 발송
- PWA Push Notification (Web Push API + VAPID)
- 메모 입력: 텍스트 또는 음성 (Web Speech API → 텍스트 변환)

**확장 가능:**
- N일 미연락 CEO 리마인더 (예: 30일 이상 접점 없는 CEO 알림)
- 주간 브리핑 Push ("이번 주 3건의 미팅이 있습니다")

---

## 데이터 모델

```
User (사용자 — FC/CEO 통합)
├── id (UUID)
├── kakao_id (카카오 OAuth)
├── name, phone, email
├── role: 'fc' | 'ceo'
├── company_name, industry (KSIC), region
├── revenue_range, employee_count
├── ga_id (FC만 해당, 소속 GA)
├── push_subscription (PWA Push 토큰)
├── created_at, updated_at

Contact (연락처 — FC가 관리하는 CEO 목록)
├── id
├── fc_id → User(fc)
├── ceo_id → User(ceo) (가입한 CEO면 연결, 아니면 NULL)
├── name, phone, company_name, industry, region
├── revenue_range, employee_count
├── memo (한 줄 메모)
├── last_interaction_at
├── created_at

Meeting (미팅/일정)
├── id
├── fc_id → User(fc)
├── contact_id → Contact
├── title (예: "분기 리뷰 미팅")
├── scheduled_at (시작 시간)
├── scheduled_end_at (종료 시간)
├── location
├── reminder_sent: boolean (리마인더 발송 여부)
├── status: 'scheduled' | 'completed' | 'cancelled'
├── created_at

Interaction (접점 기록)
├── id
├── fc_id → User(fc)
├── contact_id → Contact
├── meeting_id → Meeting (미팅 관련이면 연결)
├── type: 'call' | 'meeting' | 'message' | 'memo'
├── summary (텍스트 메모 또는 AI 요약)
├── sentiment: 'positive' | 'neutral' | 'negative' | NULL
├── created_at

Brief (AI 브리핑)
├── id
├── contact_id → Contact
├── fc_id → User(fc)
├── company_analysis (AI 생성 기업 분석)
├── action_suggestion (AI 추천 행동)
├── insights JSONB (기회, 리마인드, 신규 등)
├── generated_at

Match (매칭)
├── id
├── contact_a_id → Contact
├── contact_b_id → Contact
├── fc_id → User(fc)
├── score (0-100)
├── industry_fit (0-100)
├── region_proximity (0-100)
├── size_balance (0-100)
├── synergy_description (AI 생성)
├── status: 'proposed' | 'viewed' | 'accepted' | 'rejected'
├── created_at
```

---

## 주차별 계획

### Week 1: 프로젝트 초기화 + 인증 + DB
- [ ] FastAPI 프로젝트 구조 생성
- [ ] PostgreSQL DB 세팅 + SQLAlchemy 모델 정의
- [ ] Alembic 마이그레이션 초기화
- [ ] 카카오 OAuth2 로그인 (회원가입/로그인 플로우)
- [ ] JWT 토큰 발급/검증
- [ ] 역할 선택 화면 (FC / CEO)
- [ ] PWA 기본 설정 (manifest.json, service worker)
- [ ] Tailwind CSS + Jinja2 기본 레이아웃

### Week 2: FC 핵심 화면 + 연락처 관리
- [ ] FC 메인 대시보드 (와이어프레임 Screen 1 기반)
  - 인사말 + 오늘의 일정
  - AI 브리핑 카드 (초기엔 하드코딩 → Week 3에서 AI 연결)
  - 최근 연락처 리스트
  - 하단 네비게이션 (브리핑 / 연락처 / 매칭 / 설정)
- [ ] 연락처 CRUD
  - 최소 필드: 이름, 전화번호, 회사명, 업종(선택), 지역(선택)
  - 연락처 검색/필터
- [ ] 접점 기록 (메모 입력)
  - 텍스트 입력 + 음성 입력 (Web Speech API)
  - 접점 히스토리 타임라인

### Week 3: 미팅 일정 + 리마인더 + AI 브리핑
- [ ] 미팅 일정 등록/수정/삭제
  - 연락처 연결, 시작/종료 시간, 장소
- [ ] APScheduler 설정
  - 미팅 종료 + 1시간 체크 → 메모 미입력 시 Push 알림
- [ ] PWA Push Notification 구현
  - Web Push API + VAPID 키 생성
  - 사용자 push_subscription 저장
  - 리마인더 알림 발송
- [ ] AI 브리핑 생성 파이프라인
  - Contact 기업정보 → GPT-4o → 브리핑 카드 생성
  - 업종 평균 대비 분석, 접근 제안
- [ ] 브리핑 조회 기록 추적 (활성 사용 측정용)

### Week 4: 매칭 엔진 + CEO 화면
- [ ] 매칭 스코어 산출 (규칙 기반)
  - 업종 적합도 50% (KSIC 코드 매칭 테이블)
  - 지역 근접성 25% (좌표 거리 계산)
  - 규모 균형 25% (매출 비율)
- [ ] 매칭 제안 화면 (와이어프레임 Screen 2 기반)
  - 매칭 확률 + 3개 세부 지표
  - "왜 이 기업인가" AI 설명
  - 시너지 요약
- [ ] CEO 화면 (가입한 CEO용)
  - 사업 프로필 등록 (업종, 매출, 유휴 자원)
  - 매칭 제안 수신/열람
- [ ] 매칭 발견 시 FC에게 Push 알림

### Week 5: 통합 테스트 + 배포
- [ ] 전체 플로우 테스트
  - FC 가입 → 연락처 등록 → 미팅 등록 → 리마인더 → 메모 입력 → 브리핑 → 매칭
- [ ] 공동창업자 실사용 테스트 (실제 CEO 데이터로)
- [ ] GA DB 일괄 임포트 (CSV/Excel 업로드 → Contact 일괄 생성)
- [ ] VPS 배포 (Nginx + Uvicorn + SSL)
- [ ] 커스텀 도메인 연결
- [ ] 에러 모니터링 (Sentry 무료 티어)
- [ ] 버그 수정 + UX 개선

---

## Phase 2: AI 강화 + 과금 (Week 6-10)

### AI 자동화
- [ ] 카카오톡 채팅 내보내기 파싱 (txt 업로드 → 관계 데이터 추출)
- [ ] AI 자동 브리핑 갱신 (기업 뉴스 크롤링, DART 공시 데이터)
- [ ] N일 미연락 CEO 자동 리마인더
- [ ] 주간 AI 브리핑 Push ("이번 주 인사이트 3건")
- [ ] 매칭 알고리즘 튜닝 (사용 데이터 기반 가중치 조정)

### 과금
- [ ] CEO 과금 기능 (크레딧 or 구독)
- [ ] 결제 연동 (토스페이먼츠 or 포트원)
- [ ] 무료/유료 기능 분리

---

## 과금 구조 (Phase 2)

| 플랜 | 가격 | 포함 |
|------|------|------|
| Free | 0원 | AI CRM + 브리핑 3건/월 + 인맥 관리 |
| Credit | 건당 3,000~5,000원 | 매칭 상세 열람 1건 |
| Pro | 월 9.9만원 | 무제한 매칭 + AI 브리핑 + 우선 연결 |
| Deal | 거래액 3-10% | 실제 거래 성사 시 수수료 |

**BEP:** Pro 17명 × 9.9만원 = 168만원/월 > 운영비 150만원/월

---

## 성공 지표

### Phase 1 (Week 5 기준)
- FC 5명 이상 가입, 3명 이상 주 3회 접속
- CEO 20명 이상 등록 (수동)
- AI 브리핑 생성 성공률 90%+
- 미팅 리마인더 → 메모 입력 전환율 50%+

### Phase 2 (Week 10 기준)
- FC 10명 중 5명, 14일 중 5일 AI 브리핑 조회
- 매칭 제안 → CEO 열람 전환율 30%+
- 유료 전환 CEO 3명+

---

## Kill Signals

| 시점 | 지표 | 기준 | 액션 |
|------|------|------|------|
| Month 2 | 활성 FC | < 3명 | 접근 재검토 |
| Month 5 | 유료 CEO | < 3명 | 피봇 또는 중단 |

---

## 비용 추정 (월간)

| 항목 | 비용 | 비고 |
|------|------|------|
| VPS | ~1-3만원 | 별도 인스턴스 |
| PostgreSQL | 0원 | VPS 내 직접 운영 |
| OpenAI API | ~3-5만원 | GPT-4o, 초기 소량 |
| 도메인 | ~2만원/년 | synco.kr or synco.app |
| Sentry | 0원 | 무료 티어 |
| **합계** | **~5-8만원/월** | 부트스트래핑 가능 |

---

## 즉시 시작: Week 1

1. FastAPI 프로젝트 구조 생성
2. PostgreSQL + SQLAlchemy 모델 정의
3. 카카오 OAuth2 로그인 구현
4. PWA 기본 설정
