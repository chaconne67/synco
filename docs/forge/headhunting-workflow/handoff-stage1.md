# 헤드헌팅 워크플로우 — 1단계 핸드오프

> **완료일:** 2026-04-08
> **브랜치:** feat/data-extraction-app
> **다음 단계:** 2단계 (P03a, P05~P09)

---

## 1단계 완료 내역 (P01~P04)

| Phase | 커밋 | 신규 테스트 | 전체 테스트 | 주요 산출물 |
|-------|------|-----------|-----------|-----------|
| P01 | `227b0fd` | 56 | 440 | clients/projects 앱 생성, 전체 모델 정의, Organization/Membership |
| P02 | `8eb0858` | 34 | 474 | Client CRUD, org 격리, 동적 extends 패턴 확립 |
| P03 | `d29525e` | 36 | 510 | Project CRUD, scope=mine 필터, JD 파일 업로드 |
| P04 | `41dc208` | 29 | 539 | 보드/리스트/테이블 3종 뷰, 칸반 D&D, PATCH status |

---

## 확립된 패턴 (2단계에서 반드시 따를 것)

1. **Organization 격리:** 모든 queryset에 `organization=org` 필터. `_get_org(request)` 헬퍼 사용
2. **@login_required:** 모든 view에 적용
3. **동적 extends:** `{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}`
4. **HTMX target:** `hx-target="#main-content"` (전체 네비), `#view-content` (탭 전환)
5. **UI 텍스트:** 한국어 존대말
6. **삭제 보호:** 관련 데이터 존재 시 삭제 차단

---

## 담금질에서 확정된 주요 설계 변경

| 원안 | 변경 | 이유 |
|------|------|------|
| Organization.logo ImageField | FileField | Pillow 의존성 제거 |
| Client.contacts | contact_persons | projects.Contact 모델과 혼동 방지 |
| Membership.user FK(unique) | OneToOneField | Django 권장 |
| SubmissionDraft in P01 | P08로 이동 | 파이프라인 상세 설계 시 확정 |
| 권한 enforcement in P01 | P02+ | 모델만 P01, view-level은 각 CRUD Phase |
| 캘린더 뷰 in P04 | defer | Event 데이터 충분 시 추가 |
| 복잡한 긴급도 in P04 | days_elapsed 기반 단순화 | P13 대시보드에서 정교화 |

---

## 현재 앱/파일 구조

```
clients/
  models.py    — Client, Contract, UniversityTier, CompanyProfile, PreferredCert
  views.py     — Client CRUD 5개 + Contract CRUD 3개
  urls.py, forms.py, templates/

projects/
  models.py    — Project(+days_elapsed), Contact, Submission, Interview, Offer,
                 ProjectApproval, ProjectContext, Notification
  views.py     — Project CRUD 5개 + status_update + 멀티뷰(board/list/table)
  urls.py, forms.py, templates/, static/js/kanban.js

accounts/
  models.py    — Organization, Membership, TelegramBinding (추가됨)

candidates/
  models.py    — Candidate.owned_by FK(Organization) (추가됨)
```

---

## 2단계 작업 목록

| Phase | 이름 | 선행 |
|-------|------|------|
| P03a | JD 분석 파이프라인 | P03 |
| P05 | 프로젝트 상세 탭 | P03a |
| P06 | 컨택 관리 | P05 |
| P07 | 추천 서류 기본 | P05 |
| P08 | AI 서류 생성 | P07 |
| P09 | 면접 + 오퍼 | P05 |

## 시작 방법

```
새 세션에서:
plan-forge-batch docs/plans/headhunting-workflow/ 
(P03a, P05~P09 대상으로 순차 실행)
이 핸드오프 문서 참조하여 확립된 패턴 따르기
```
