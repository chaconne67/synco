# 헤드헌팅 워크플로우 — 개발 Phase 목록

> **설계 문서:** [2026-04-06-headhunting-workflow-design.md](../2026-04-06-headhunting-workflow-design.md)

## Phase 구조

```
[핵심 워크플로우]                    [보조 기능]
P01 모델 + Organization 기반  ─────  P12 레퍼런스 데이터
 ↓
P02 고객사 CRUD
 ↓
P03 프로젝트 기본
 ↓
P03a JD 분석 + 매칭 스코어링  ─────  P04 멀티뷰 (병렬)
 ↓
P05 상세 탭 구조
 ↓
P06 컨택 관리
 ↓
P07 추천 서류 기본     ─────────────  P11 충돌·승인 (병렬)
 ↓
P09 면접 + 오퍼
 ↓
P08 AI 서류 생성      ─────────────  P10 공지 자동 생성 (병렬)
 ↓
P13 대시보드
 ↓
[확장]
P14 보이스 에이전트 + 미팅 녹음 인사이트
P15 텔레그램 통합
P16 업무 연속성 + 자동 생성
P17 뉴스피드
P18 이메일 이력서 자동 처리
P19 Chrome Extension (후보자 소싱)
```

## Phase 목록

### 핵심 (P01–P09): 기본 업무 프로세스

| Phase | 파일 | 이름 | 선행 |
|-------|------|------|------|
| P01 | [P01-models-and-app-foundation.md](P01-models-and-app-foundation.md) | 모델·앱 기반 + Organization/Membership | — |
| P02 | [P02-client-management.md](P02-client-management.md) | 고객사 관리 | P01 |
| P03 | [P03-project-basic-crud.md](P03-project-basic-crud.md) | 프로젝트 기본 CRUD | P02 |
| **P03a** | [**P03a-jd-analysis-pipeline.md**](P03a-jd-analysis-pipeline.md) | **JD 분석 + 매칭 스코어링** | **P03** |
| P04 | [P04-project-multi-view.md](P04-project-multi-view.md) | 프로젝트 멀티뷰 | P03 |
| P05 | [P05-project-detail-tabs.md](P05-project-detail-tabs.md) | 프로젝트 상세 탭 | P03a |
| P06 | [P06-contact-management.md](P06-contact-management.md) | 컨택 관리 + 중복 방지 | P05 |
| P07 | [P07-submission-basic.md](P07-submission-basic.md) | 추천 서류 기본 | P05 |
| P08 | [P08-ai-document-pipeline.md](P08-ai-document-pipeline.md) | AI 서류 생성 파이프라인 | P07 |
| P09 | [P09-interview-offer.md](P09-interview-offer.md) | 면접 + 오퍼 추적 | P05 |

### 기능 완성 (P10–P13): 자동화·관리

| Phase | 파일 | 이름 | 선행 |
|-------|------|------|------|
| P10 | [P10-job-posting.md](P10-job-posting.md) | 공지 자동 생성 | P05 |
| P11 | [P11-project-collision-approval.md](P11-project-collision-approval.md) | 프로젝트 충돌·승인 | P03 |
| P12 | [P12-reference-data.md](P12-reference-data.md) | 레퍼런스 데이터 | P01 |
| P13 | [P13-dashboard.md](P13-dashboard.md) | 대시보드 | P06, P07 |

### 확장 (P14–P19): 보이스·텔레그램·소싱·자동화

| Phase | 파일 | 이름 | 선행 |
|-------|------|------|------|
| P14 | [P14-voice-agent.md](P14-voice-agent.md) | 보이스 에이전트 + 미팅 녹음 인사이트 | P06 |
| P15 | [P15-telegram-integration.md](P15-telegram-integration.md) | 텔레그램 통합 | P11, P06 |
| P16 | [P16-work-continuity.md](P16-work-continuity.md) | 업무 연속성 + 자동 생성 | P08, P10 |
| P17 | [P17-news-feed.md](P17-news-feed.md) | 뉴스피드 | P01 |
| P18 | [P18-email-resume-processing.md](P18-email-resume-processing.md) | 이메일 이력서 자동 처리 | P06 |
| **P19** | [**P19-chrome-extension.md**](P19-chrome-extension.md) | **Chrome Extension (후보자 소싱)** | **P01, P06** |
