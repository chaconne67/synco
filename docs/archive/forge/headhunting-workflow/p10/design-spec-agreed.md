# P10: Job Posting — 확정 설계서

> **Phase:** 10
> **선행조건:** P05 (개요 탭 골격), P03 (프로젝트 모델 — `posting_text` 필드)
> **산출물:** 개요 탭 공지 섹션 + AI 공지 생성 + 포스팅 사이트 추적

---

## 목표

프로젝트 개요 탭에 공지 섹션을 추가한다. JD를 기반으로 AI가 잡포털 포스팅용
공지 초안을 생성하고, 포스팅 사이트별 게시 여부와 지원자 수를 추적한다.

---

## URL 설계

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/projects/<pk>/posting/generate/` | POST | `posting_generate` | AI 공지 초안 생성 (사용자 명시 액션) |
| `/projects/<pk>/posting/edit/` | GET/POST | `posting_edit` | 공지 내용 편집 |
| `/projects/<pk>/posting/download/` | GET | `posting_download` | 공지 파일 다운로드 (.txt) |
| `/projects/<pk>/posting/sites/` | GET | `posting_sites` | 포스팅 사이트 목록 (HTMX partial) |
| `/projects/<pk>/posting/sites/new/` | POST | `posting_site_add` | 포스팅 사이트 추가 |
| `/projects/<pk>/posting/sites/<site_pk>/edit/` | POST | `posting_site_update` | 포스팅 사이트 수정 |
| `/projects/<pk>/posting/sites/<site_pk>/delete/` | POST | `posting_site_delete` | 포스팅 사이트 비활성화 (소프트 삭제) |

---

## 모델 변경

### Project (기존 모델 필드 활용)

- `posting_text` — TextField, 공지 본문 (이미 존재)
- `posting_file_name` — CharField(max_length=300, blank=True), 생성된 파일명 (추가)

### PostingSite (projects 앱 — 신규)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | UUID | PK (BaseModel) |
| `project` | FK → Project | 소속 프로젝트 |
| `site` | CharField(max_length=20) choices | 포스팅 사이트 |
| `posted_at` | DateField null | 게시일 |
| `is_active` | BooleanField default=True | 게시 중 여부 (False = 비활성/삭제) |
| `applicant_count` | PositiveIntegerField default=0 | 지원자 수 |
| `url` | URLField blank | 포스팅 URL (옵션) |
| `notes` | TextField blank | 메모 |
| `created_at` / `updated_at` | DateTimeField | 타임스탬프 (BaseModel) |

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

> **저장값:** 영어 slug 사용. 이유: 잡포털 사이트명은 외부 서비스 식별자이며,
> 코드베이스에서 JDSource, ProjectStatus, DraftStatus 등도 이미 영어 slug 사용.

**constraints:** `UniqueConstraint(fields=["project", "site"], name="unique_posting_site_per_project")` — 같은 프로젝트에 같은 사이트 중복 방지. 현재 상태 스냅샷 모델.

**소프트 삭제:** `posting_site_delete` 뷰는 `is_active=False`로 설정. UI에서는 `is_active=True`인 항목만 표시. 지원자 수 합계에도 활성 항목만 포함.

---

## 공지 생성 AI

### 입력 → 출력

| 입력 | 필수 여부 | 출력 |
|------|----------|------|
| `jd_raw_text or jd_text` (JD 원문, 우선순위) | **필수** | 공지 본문 (포스팅용 텍스트) |
| `Project.client` (고객사 정보: industry, size, region) | 선택 | 회사명 비노출 처리된 간접 표현 |
| `Project.requirements` (요구조건 JSON) | 선택 | 구조화된 자격요건 (있으면 활용, 없으면 JD에서 추론) |

> **JD 읽기 우선순위:** `project.jd_raw_text or project.jd_text` — 기존 `jd_analysis.py`와 동일 패턴.
> 둘 다 없으면 생성 불가 → "JD를 먼저 등록해주세요" 안내.

### AI 공지 생성 규칙

| 규칙 | 설명 | 예시 |
|------|------|------|
| 회사명 비노출 | **공지 본문에만 적용.** 업종 + 규모(Client.size) 간접 표현 | "중견 의료기기 제조사" |
| 텍스트 파일 | .txt 형식, 포스팅 에러 방지 | — |
| 파일명 규칙 | `(YYMMDD) 회사명_포지션명_담당자명.txt` — **내부 관리용** (회사명 포함 허용) | `(260407) Rayence_품질기획팀장_전병권.txt` |
| 구조 | 포지션/업종/주요업무/자격요건/근무지/처우 | 잡포털 표준 양식 |

> **비노출 범위 명확화:** "회사명 비노출"은 `posting_text`(공지 본문)에만 적용됩니다.
> `posting_file_name`은 헤드헌터가 내부 문서 관리에 사용하는 네이밍이므로 회사명을 포함합니다.

### 섹션별 데이터 소스 매핑

| 공지 섹션 | 데이터 소스 | 폴백 |
|----------|-----------|------|
| 포지션 | requirements.position 또는 JD 추론 | 프로젝트 제목 |
| 업종 | Client.industry | JD에서 추론 |
| 주요업무 | requirements.responsibilities 또는 JD 추론 | — |
| 자격요건 | requirements (경력/학력/자격증/키워드) 또는 JD 추론 | — |
| 근무지 | Client.region 또는 requirements.location 또는 JD 추론 | "협의" |
| 처우 | requirements.salary_info 또는 JD 추론 | "협의" |

> **AI 프롬프트 규칙:** "정보가 없는 섹션은 해당 항목을 '협의'로 표시하거나 생략한다."

### 생성 흐름

```
사용자가 개요 탭에서 "공지 생성" 버튼 클릭
  ↓
posting_generate 뷰 (동기 POST)
  ↓
JD 원문 확인 → 없으면 에러 반환
  ↓
Gemini API 호출 (generate_posting)
  ↓
posting_text + posting_file_name 저장
  ↓
개요 탭 공지 섹션에 표시 (HTMX swap)
```

### 덮어쓰기 정책

| 상황 | 동작 |
|------|------|
| posting_text가 비어있음 | 바로 생성 및 저장 |
| posting_text가 이미 존재 (생성 버튼) | 클라이언트 사이드 confirm 후 저장 |
| "AI 재생성" 버튼 (편집 화면) | 클라이언트 사이드 confirm 후 기존 내용 덮어쓰기 |
| "저장" 버튼 (편집 화면) | 사용자 편집본 항상 우선 저장 |

**서비스:** `projects/services/posting.py`
- `generate_posting(project) -> str` — JD + 고객사 정보 → 공지 텍스트. Gemini API 호출.
- `get_posting_filename(project, user) -> str` — 파일명 규칙 적용. `user`는 request.user.

> **담당자명:** `request.user.get_full_name()` 사용 (생성 시점의 현재 사용자).

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
│  │  [업종] 중견 의료기기 제조사                   │   │
│  │  [주요업무]                                  │   │
│  │  · 품질경영시스템 기획 및 운영 총괄            │   │
│  │  · ISO 13485 인증 관리                       │   │
│  │  [자격요건]                                  │   │
│  │  · 경력 15년 이상 · 품질경영기사 보유          │   │
│  │  [근무지] 경기도                              │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
├─ 포스팅 현황 ─────────────────── [+ 포스팅 추가] ───┤
│  ✅ 잡코리아  |  04/07  |  지원자: 3명  [수정]       │
│  ✅ 사람인    |  04/07  |  지원자: 1명  [수정]       │
│                                                     │
│  합계 지원자: 4명                                    │
└─────────────────────────────────────────────────────┘
```

> **공지 미생성 상태:** posting_text가 비어있으면 "공지 생성" 버튼 표시.
> JD도 없으면 "JD를 먼저 등록해주세요" 안내.

> **포스팅 현황:** DB에 존재하는 `PostingSite` (is_active=True) 행만 표시.
> 추가하지 않은 사이트는 목록에 나타나지 않는다.

### 포스팅 사이트 추가/수정 (인라인)

```
┌─ 포스팅 추가 ──────────────────────────────────────┐
│  사이트: [사람인 ▾]  게시일: [2026-04-07]            │
│  URL: [https://www.saramin.co.kr/...    ] (선택)    │
│  [저장]  [취소]                                     │
└────────────────────────────────────────────────────┘
```

수정 폼은 PostingSiteForm의 모든 필드를 포함: site, posted_at, is_active, applicant_count, url, notes.

---

## 공지 편집 화면

```
┌─ 공지 편집 ────────────────────────────────────────┐
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ [포지션] 의료기기 품질기획 팀장급               │  │
│  │ [업종] 중견 의료기기 제조사                    │  │
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

### 성공 경로

| 항목 | 검증 방법 |
|------|----------|
| AI 공지 생성 | JD 입력 → posting_text 생성 확인 |
| 회사명 비노출 | 생성된 본문(posting_text)에 고객사명 미포함 확인 |
| 파일명 규칙 | `(YYMMDD) 회사명_포지션명_담당자명.txt` 형식 확인 |
| .txt 다운로드 | 다운로드 시 올바른 파일명 + 내용 |
| 포스팅 사이트 CRUD | 추가 → 목록 표시 → 수정 → 비활성화 |
| 지원자 수 업데이트 | 숫자 수정 → 저장 → 합계 반영 |
| 중복 방지 | 같은 프로젝트+사이트 중복 등록 차단 |
| 공지 편집 | 내용 수정 → 저장 → 미리보기 반영 |

### 실패 경로

| 항목 | 검증 방법 |
|------|----------|
| Gemini API 오류 | 에러 메시지 표시, 기존 posting_text 보존 |
| JD 없는 프로젝트 | 생성 시도 시 "JD를 먼저 등록해주세요" 안내 |
| 중복 사이트 등록 | 같은 사이트 재등록 시 에러 메시지 |
| 공지 없는 다운로드 | posting_text 없을 때 다운로드 시도 → 404 |
| 덮어쓰기 취소 | confirm 취소 후 기존 내용 보존 확인 |
| requirements 없이 생성 | JD 원문만으로 공지 생성 성공 확인 |

---

## 산출물

- `projects/models.py` — PostingSite 모델 추가, Project에 `posting_file_name` 필드
- `projects/migrations/` — PostingSite 생성 + posting_file_name 추가 migration
- `projects/views.py` — Posting 관련 뷰 7개
- `projects/forms.py` — PostingEditForm, PostingSiteForm
- `projects/urls.py` — Posting 관련 URL 추가
- `projects/services/posting.py` — AI 공지 생성 + 파일명 규칙
- `projects/templates/projects/partials/posting_section.html` — 공지 섹션
- `projects/templates/projects/partials/posting_edit.html` — 공지 편집
- `projects/templates/projects/partials/posting_sites.html` — 포스팅 사이트 목록
- `projects/templates/projects/partials/posting_site_form.html` — 사이트 추가/수정 폼
- P05 개요 탭에 공지 섹션 include 추가
- 테스트 파일

## 프로젝트 컨텍스트 (핸드오프에서 확립된 패턴)

1. **Organization 격리:** 모든 queryset에 `organization=org` 필터. `_get_org(request)` 헬퍼 사용
2. **@login_required:** 모든 view에 적용
3. **동적 extends:** `{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}`
4. **HTMX target:** `hx-target="#main-content"` (전체 네비), `hx-target="#tab-content"` (탭 전환)
5. **UI 텍스트:** 한국어 존대말
6. **삭제 보호:** 관련 데이터 존재 시 삭제 차단, PostingSite는 소프트 삭제
7. **HTMX CRUD 패턴:** `{model}Changed` 이벤트 + `#{model}-form-area` + 204+HX-Trigger
8. **DB 저장값:** 도메인 상태값은 한국어, 외부 식별자는 영어 slug 허용
9. **상태 전이 서비스:** 허용 전이 맵 + `InvalidTransition` 예외
10. **조직 격리 체이닝:** Project(organization=org) → 하위 모델

<!-- forge:p10:설계담금질:complete:2026-04-08T22:55:00+09:00 -->
