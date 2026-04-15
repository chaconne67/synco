# 헤드헌팅 워크플로우 — 2단계 핸드오프

> **완료일:** 2026-04-08
> **브랜치:** feat/data-extraction-app
> **다음 단계:** 3단계 (P10~P13 기능 완성)

---

## 2단계 완료 내역 (P03a, P05~P09)

| Phase | 커밋 | 신규 테스트 | 전체 테스트 | 담금질 이슈 | 주요 산출물 |
|-------|------|-----------|-----------|------------|-----------|
| P03a | `67be1f4` | 48 | 580 | 14 (9C/4M/1R) | JD 분석 파이프라인, Gemini 추출, 5차원 매칭 |
| P05 | `f0f6aa2` | 36 | 616 | 8 (1C/6M/1m) | 프로젝트 상세 6탭 구조, 개요+서칭 완성 |
| P06 | `3eb3066` | 30 | 646 | 11 (3C/5M/3m) | 컨택 CRUD, 7일 잠금, 중복 방지 |
| P07 | `8b3cea8` | 54 | 700 | 14 (9C/4M/1m) | 추천 서류 CRUD, 상태 전환, 피드백 |
| P08 | `d341470` | 36 | 736 | 11 (8C/3M) | AI 초안 생성, 상담/딕테이션, Word 변환 |
| P09 | `d031346` | 76 | 812 | 11 (5C/5M/1m) | 면접/오퍼 CRUD, 프로젝트 라이프사이클 |

---

## 1+2단계 확립된 패턴 (3단계에서 반드시 따를 것)

1. **Organization 격리:** 모든 queryset에 `organization=org` 필터. `_get_org(request)` 헬퍼 사용
2. **@login_required:** 모든 view에 적용
3. **동적 extends:** `{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}`
4. **HTMX target:** `hx-target="#main-content"` (전체 네비), `hx-target="#tab-content"` (탭 전환)
5. **UI 텍스트:** 한국어 존대말
6. **삭제 보호:** 관련 데이터 존재 시 삭제 차단
7. **HTMX CRUD 패턴:** `{model}Changed` 이벤트 + `#{model}-form-area` + 204+HX-Trigger
8. **DB 저장값:** 한국어 TextChoices 유지 (대면/합격/협상중 등)
9. **상태 전이 서비스:** 허용 전이 맵 + `InvalidTransition` 예외 (P07 submission, P08 draft, P09 lifecycle)
10. **조직 격리 체이닝:** Project(organization=org) → Submission(project=project) → Interview/Offer/Draft

---

## 담금질에서 확정된 주요 설계 변경

| 원안 | 변경 | Phase | 이유 |
|------|------|-------|------|
| parsed_data 필드 참조 | Candidate 기본+JSON+관련 모델 열거 | P08 | Candidate에 parsed_data 없음 |
| PDF 변환 (reportlab) | Word만 1차 구현 | P08 | reportlab 미설치, 후속 처리 |
| 서칭 탭 POST + 컨택 예정 | 서칭 탭 읽기 전용 (P05), P06에서 추가 | P05 | 범위 분리 |
| "활동 로그" 전체 타임라인 | "최근 진행 현황" Contact 3건+Submission 2건 | P05 | 스키마 비대 방지 |
| 중복 컨택 전체 차단 | 관심/거절→차단, 응답/미응답/보류→경고(재컨택 허용) | P06 | 실무상 재컨택 필요 |
| 만료 예정 .delete() | .update(locked_until=None) | P06 | 이력 보존 |
| 영어 Status enum (draft/submitted) | 기존 한국어 저장값 유지 (작성중/제출) | P07 | 기존 데이터 호환 |
| closed_fail 자동 전환 | 수동 전환으로만 | P09 | 오퍼 단계에서 면접 이력 무조건 존재 |
| SubmissionDraft.template 필드 | 제거, Submission.template 참조 | P08 | 중복 제거 |
| HWP 파일 지원 | 범위 제외 | P03a | text.py 미지원, 의존성 추가 부담 |

---

## 현재 앱/파일 구조

```
projects/
  models.py    — Project(+JD 필드), Contact(+RESERVED), Submission(+template/notes),
                 SubmissionDraft(6단계 파이프라인), Interview(+location/notes),
                 Offer(+notes/decided_at), ProjectApproval, ProjectContext, Notification
  views.py     — Project CRUD 5개 + status_update + 멀티뷰(board/list/table)
                 + JD 분석 5개 + 탭 7개(detail+6탭)
                 + Contact CRUD 6개 + 중복체크
                 + Submission CRUD 6개 + 피드백
                 + Draft 8개
                 + Interview CRUD 4개 + 결과입력
                 + Offer CRUD 5개 + 수락/거절
  urls.py      — 전체 ~50개 URL 패턴
  forms.py     — ProjectForm, ContactForm, SubmissionForm, SubmissionFeedbackForm,
                 InterviewForm, InterviewResultForm, OfferForm
  services/
    jd_analysis.py          — JD 텍스트 분석, requirements 추출 (Gemini)
    jd_prompts.py           — Gemini 프롬프트 상수
    candidate_matching.py   — 5차원 적합도 매칭, 키워드 확장
    contact.py              — 중복 체크, 예정 등록, 만료 해제
    submission.py           — 상태 전환, 프로젝트 status 연동
    draft_pipeline.py       — Draft 상태 전이 서비스
    draft_generator.py      — AI 초안 생성 (Gemini)
    draft_consultation.py   — 상담 처리 (Whisper + Gemini)
    draft_finalizer.py      — AI 최종 정리
    draft_converter.py      — Word 변환 + 마스킹
    lifecycle.py            — 프로젝트 라이프사이클 자동 전환
  templates/projects/
    project_detail.html     — 탭 wrapper (full page)
    submission_draft.html   — Draft 작업 (full page)
    partials/
      detail_tab_bar.html, tab_overview/search/contacts/submissions/interviews/offers.html
      contact_form.html, duplicate_check_result.html
      submission_form.html, submission_feedback.html
      draft_*.html (10개 — progress, steps, preview, error)
      interview_form.html, interview_result_form.html, offer_form.html
      jd_*.html (5개 — analysis result/error, drive picker, matching)
      view_*.html (6개 — board/list/table/filters/tabs/card)

clients/
  models.py    — Client, Contract, UniversityTier, CompanyProfile, PreferredCert
  views.py     — Client CRUD 5개 + Contract CRUD 3개

accounts/
  models.py    — Organization, Membership, TelegramBinding

candidates/
  models.py    — Candidate.owned_by FK(Organization)
```

---

## 3단계 작업 목록

| Phase | 이름 | 선행 | 비고 |
|-------|------|------|------|
| P10 | 공지 자동 생성 | P05 (완료) | JD → 채용 공지문 자동 생성 |
| P11 | 프로젝트 충돌·승인 | P03 (완료) | 동일 후보자 다중 프로젝트 충돌 감지 |
| P12 | 레퍼런스 데이터 | P01 (완료) | UniversityTier, CompanyProfile, PreferredCert 관리 UI |
| P13 | 대시보드 | P06, P07 (완료) | KPI, 파이프라인 현황, 컨설턴트별 실적 |

### 병렬 가능 분석

- P10, P11, P12는 서로 의존성 없음 — 파일 충돌 분석 후 병렬 가능
- P13은 P06, P07 완료 필요 (충족됨) — P10~P12와 병렬 가능 여부 확인 필요

## 시작 방법

```
새 세션에서:
plan-forge-batch docs/plans/headhunting-workflow/
(P10, P11, P12, P13 대상으로 실행)
이 핸드오프 문서 참조하여 확립된 패턴 따르기
```
