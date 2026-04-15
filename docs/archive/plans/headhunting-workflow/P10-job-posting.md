# P10: Job Posting

> **Phase:** 10
> **선행조건:** P05 (개요 탭 골격), P03 (프로젝트 모델 — `posting_text` 필드)
> **산출물:** 개요 탭 공지 섹션 + AI 공지 생성 + 포스팅 사이트 추적

---

## 목표

프로젝트 개요 탭에 공지 섹션을 추가한다. JD를 기반으로 AI가 잡포털 포스팅용
공지 초안을 자동 생성하고, 포스팅 사이트별 게시 여부와 지원자 수를 추적한다.

---

## URL 설계

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/projects/<pk>/posting/generate/` | POST | `posting_generate` | AI 공지 초안 생성 |
| `/projects/<pk>/posting/edit/` | GET/POST | `posting_edit` | 공지 내용 편집 |
| `/projects/<pk>/posting/download/` | GET | `posting_download` | 공지 파일 다운로드 (.txt) |
| `/projects/<pk>/posting/sites/` | GET | `posting_sites` | 포스팅 사이트 목록 (HTMX partial) |
| `/projects/<pk>/posting/sites/new/` | POST | `posting_site_add` | 포스팅 사이트 추가 |
| `/projects/<pk>/posting/sites/<site_pk>/edit/` | POST | `posting_site_update` | 지원자 수 업데이트 |
| `/projects/<pk>/posting/sites/<site_pk>/delete/` | POST | `posting_site_delete` | 포스팅 사이트 삭제 |

---

## 모델 변경

### Project (기존 모델 필드 활용)

- `posting_text` — TextField, 공지 본문 (이미 설계에 포함)
- `posting_file_name` — CharField, 생성된 파일명 (추가)

### PostingSite (projects 앱 — 신규)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | UUID | PK |
| `project` | FK → Project | 소속 프로젝트 |
| `site` | CharField choices | 포스팅 사이트 |
| `posted_at` | DateField null | 게시일 |
| `is_active` | BooleanField default=True | 게시 중 여부 |
| `applicant_count` | PositiveIntegerField default=0 | 지원자 수 |
| `url` | URLField blank | 포스팅 URL (옵션) |
| `notes` | TextField blank | 메모 |
| `created_at` / `updated_at` | DateTimeField | 타임스탬프 |

```python
class PostingSiteChoice(models.TextChoices):
    JOBKOREA = "jobkorea", "잡코리아"
    SARAMIN = "saramin", "사람인"
    INCRUIT = "incruit", "인크루트"
    LINKEDIN = "linkedin", "LinkedIn"
    WANTED = "wanted", "원티드"
    CATCH = "catch", "캐치"
    OTHER = "other", "기타"
```

**unique_together:** `(project, site)` — 같은 프로젝트에 같은 사이트 중복 방지.

---

## 공지 생성 AI

### 입력 → 출력

| 입력 | 출력 |
|------|------|
| Project.jd_text (JD 원문) | 공지 본문 (포스팅용 텍스트) |
| Project.client (고객사 정보) | 회사명 비노출 처리된 간접 표현 |
| Project.requirements (요구조건 JSON) | 구조화된 자격요건 |

### AI 공지 생성 규칙

| 규칙 | 설명 | 예시 |
|------|------|------|
| 회사명 비노출 | 업종+규모+상장구분 간접 표현 | "코스닥 상장 의료기기사" |
| 텍스트 파일 | .txt 형식, 포스팅 에러 방지 | — |
| 파일명 규칙 | `(YYMMDD) 회사명_포지션명_담당자명.txt` | `(260407) Rayence_품질기획팀장_전병권.txt` |
| 구조 | 포지션/업종/주요업무/자격요건/근무지/처우 | 잡포털 표준 양식 |

### 생성 흐름

```
Project 등록 완료
  ↓
AI 자동 생성 (비동기 — 프로젝트 등록 직후 트리거)
  ↓
posting_text + posting_file_name 저장
  ↓
개요 탭 공지 섹션에 표시
```

**서비스:** `projects/services/posting.py`
- `generate_posting(project) -> str` — JD + 고객사 정보 → 공지 텍스트
- `get_posting_filename(project) -> str` — 파일명 규칙 적용

---

## 개요 탭 공지 섹션 UI

```
┌─ 공지 ─────────────────────────────────────────────┐
│                                                     │
│  파일: (260407) Rayence_품질기획팀장_전병권.txt       │
│  [공지 편집]  [다운로드]  [클립보드 복사]              │
│                                                     │
│  ┌─ 공지 미리보기 ──────────────────────────────┐   │
│  │  [포지션] 의료기기 품질기획 팀장급              │   │
│  │  [업종] 의료기기 제조 (코스닥 상장사)           │   │
│  │  [주요업무]                                  │   │
│  │  · 품질경영시스템 기획 및 운영 총괄            │   │
│  │  · ISO 13485 인증 관리                       │   │
│  │  [자격요건]                                  │   │
│  │  · 경력 15년 이상 · 품질경영기사 보유          │   │
│  │  [근무지] 경기도                              │   │
│  │  ⚠ 회사명 비노출 처리됨                       │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
├─ 포스팅 현황 ─────────────────── [+ 포스팅 추가] ───┤
│  ✅ 잡코리아  |  04/07  |  지원자: 3명  [수정]       │
│  ✅ 사람인    |  04/07  |  지원자: 1명  [수정]       │
│  ☐ 인크루트  |  미게시                  [게시 등록]  │
│                                                     │
│  합계 지원자: 4명                                    │
└─────────────────────────────────────────────────────┘
```

### 포스팅 사이트 추가/수정 (인라인)

```
┌─ 포스팅 추가 ──────────────────────────────────────┐
│  사이트: [사람인 ▾]  게시일: [2026-04-07]            │
│  URL: [https://www.saramin.co.kr/...    ] (선택)    │
│  [저장]  [취소]                                     │
└────────────────────────────────────────────────────┘
```

지원자 수는 수시로 업데이트 가능 (인라인 숫자 입력).

---

## 공지 편집 화면

```
┌─ 공지 편집 ────────────────────────────────────────┐
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ [포지션] 의료기기 품질기획 팀장급               │  │
│  │ [업종] 의료기기 제조 (코스닥 상장사)            │  │
│  │ ...                                          │  │
│  │ (textarea — 자유 편집)                        │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  [AI 재생성]  [저장]  [취소]                         │
└─────────────────────────────────────────────────────┘
```

"AI 재생성" 클릭 시 기존 내용을 덮어쓸지 확인 후 재생성.

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| AI 공지 생성 | JD 입력 → posting_text 생성 확인 |
| 회사명 비노출 | 생성된 텍스트에 고객사명 미포함 확인 |
| 파일명 규칙 | `(YYMMDD) 회사명_포지션명_담당자명.txt` 형식 확인 |
| .txt 다운로드 | 다운로드 시 올바른 파일명 + 내용 |
| 포스팅 사이트 CRUD | 추가 → 목록 표시 → 수정 → 삭제 |
| 지원자 수 업데이트 | 숫자 수정 → 저장 → 합계 반영 |
| 중복 방지 | 같은 프로젝트+사이트 중복 등록 차단 |
| 공지 편집 | 내용 수정 → 저장 → 미리보기 반영 |

---

## 산출물

- `projects/models.py` — PostingSite 모델 추가, Project에 `posting_file_name` 필드
- `projects/views.py` — Posting 관련 뷰 7개
- `projects/forms.py` — PostingEditForm, PostingSiteForm
- `projects/urls.py` — Posting 관련 URL 추가
- `projects/services/posting.py` — AI 공지 생성 + 파일명 규칙
- `projects/templates/projects/partials/posting_section.html` — 공지 섹션
- `projects/templates/projects/partials/posting_edit.html` — 공지 편집
- `projects/templates/projects/partials/posting_sites.html` — 포스팅 사이트 목록
- P05 개요 탭에 공지 섹션 include 추가
- 테스트 파일
