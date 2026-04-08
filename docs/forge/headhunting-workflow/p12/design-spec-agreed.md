# P12: Reference Data Management — 확정 설계서

> **Phase:** 12
> **선행조건:** P01 (clients 앱 기반 — UniversityTier, CompanyProfile, PreferredCert 모델)
> **산출물:** 레퍼런스 데이터 초기 구축 + 관리 UI + CSV 가져오기/내보내기

---

## 목표

대학 랭킹(UniversityTier), 기업 DB(CompanyProfile), 자격증 DB(PreferredCert)의
초기 데이터를 구축하고, 사이드바에서 접근 가능한 관리 UI를 제공한다.

---

## 조직 격리 예외

레퍼런스 모델(UniversityTier, CompanyProfile, PreferredCert)은 **전역 시스템 마스터**로
organization 필드가 없다. 프로젝트의 조직 격리 원칙의 예외에 해당한다.

- **읽기(목록/검색/내보내기):** 모든 로그인 사용자 (`@login_required`)
- **쓰기(추가/수정/삭제/가져오기):** staff 전용 (`@staff_member_required`)

---

## URL 설계

`/reference/` prefix는 `main/urls.py`에서 `clients.urls_reference`를 별도 include한다.

| URL | Method | View | 권한 | 설명 |
|-----|--------|------|------|------|
| `/reference/` | GET | `reference_index` | login | 레퍼런스 관리 메인 (대학 탭 기본) |
| `/reference/universities/` | GET | `reference_universities` | login | 대학 랭킹 탭 |
| `/reference/universities/new/` | GET/POST | `university_create` | staff | 대학 추가 |
| `/reference/universities/<pk>/edit/` | GET/POST | `university_update` | staff | 대학 수정 |
| `/reference/universities/<pk>/delete/` | POST | `university_delete` | staff | 대학 삭제 |
| `/reference/universities/import/` | POST | `university_import` | staff | CSV 가져오기 |
| `/reference/universities/export/` | GET | `university_export` | login | CSV 내보내기 |
| `/reference/companies/` | GET | `reference_companies` | login | 기업 DB 탭 |
| `/reference/companies/new/` | GET/POST | `company_create` | staff | 기업 추가 |
| `/reference/companies/<pk>/edit/` | GET/POST | `company_update` | staff | 기업 수정 |
| `/reference/companies/<pk>/delete/` | POST | `company_delete` | staff | 기업 삭제 |
| `/reference/companies/<pk>/autofill/` | POST | `company_autofill` | staff | 웹검색 자동채움 |
| `/reference/companies/import/` | POST | `company_import` | staff | CSV 가져오기 |
| `/reference/companies/export/` | GET | `company_export` | login | CSV 내보내기 |
| `/reference/certs/` | GET | `reference_certs` | login | 자격증 탭 |
| `/reference/certs/new/` | GET/POST | `cert_create` | staff | 자격증 추가 |
| `/reference/certs/<pk>/edit/` | GET/POST | `cert_update` | staff | 자격증 수정 |
| `/reference/certs/<pk>/delete/` | POST | `cert_delete` | staff | 자격증 삭제 |
| `/reference/certs/import/` | POST | `cert_import` | staff | CSV 가져오기 |
| `/reference/certs/export/` | GET | `cert_export` | login | CSV 내보내기 |

---

## 모델 (clients 앱) — P01 대비 변경사항

### UniversityTier

| 필드 | 타입 | 설명 | 변경 |
|------|------|------|------|
| `id` | UUID | PK | 유지 |
| `name` | CharField(200) | 대학명 (한글) | 유지 |
| `name_en` | CharField(200) blank | 대학명 (영문) | 유지 |
| `country` | CharField(10) | 국가 코드 (KR, US, JP, ...) | 유지 |
| `tier` | CharField(20) choices | 분류 그룹 | **choices 변경** |
| `ranking` | PositiveSmallIntegerField null | 그룹 내 순위 (선택) | **타입 변경** (IntegerField → PositiveSmallIntegerField) |
| `notes` | TextField blank | 비고 | **추가** |

**Unique constraint:** `unique_together = [("name", "country")]`

**티어 체계 변경 (P01 → P12):**

| P01 저장값 | P12 저장값 | 표시값 |
|-----------|-----------|--------|
| S | SKY | SKY |
| A | SSG | 서성한 |
| B | JKOS | 중경외시 |
| C | KDH | 건동홍 |
| D | INSEOUL | 인서울 기타 |
| E | SCIENCE_ELITE | 이공계 명문 |
| F | REGIONAL | 지방 거점 국립 |
| 해외최상위 | OVERSEAS_TOP | 해외 최상위 |
| 해외상위 | OVERSEAS_HIGH | 해외 상위 |
| 해외우수 | OVERSEAS_GOOD | 해외 우수 |

기존 테이블이 빈 상태이므로 AlterField로 choices만 변경.

### CompanyProfile

| 필드 | 타입 | 설명 | 변경 |
|------|------|------|------|
| `id` | UUID | PK | 유지 |
| `name` | CharField(200) unique | 회사명 (한글) | **unique 추가** |
| `name_en` | CharField(200) blank | 회사명 (영문) | **추가** |
| `industry` | CharField(100) blank | 업종 | 유지 |
| `size_category` | CharField(50) choices blank | 대기업/중견/중소/외국계/스타트업 | 유지 |
| `revenue_range` | CharField(50) blank | 매출 규모 | 유지 |
| `employee_count_range` | CharField(50) blank | 직원 수 규모 | **추가** |
| `listed` | CharField(20) choices blank | 상장 구분 | **추가** |
| `region` | CharField(100) blank | 소재지 | **추가** |
| `notes` | TextField blank | 비고 | 유지 |
| ~~`preference_tier`~~ | — | — | **삭제** |

**size_category choices:** 대기업/중견/중소/외국계/스타트업
**listed choices:** KOSPI/KOSDAQ/비상장/해외상장

### PreferredCert

| 필드 | 타입 | 설명 | 변경 |
|------|------|------|------|
| `id` | UUID | PK | 유지 |
| `name` | CharField(200) unique | 자격증 약칭 | 유지 (unique 유지) |
| `full_name` | CharField(200) | 정식 명칭 | **추가** |
| `category` | CharField(30) choices | 분류 카테고리 | **choices 확장** |
| `level` | CharField(10) choices blank | 난이도 (상/중/하) | **추가** |
| `aliases` | JSONField default=list | 별칭 목록 | **추가** |
| `notes` | TextField blank | 비고 | **추가** |
| ~~`description`~~ | — | — | **삭제** |

**category choices (확장):** 회계/재무, 법률, 기술/엔지니어링, IT, 의료/제약, 무역/물류, 건설/부동산, 식품/환경, 어학, 안전/품질, 기타

**level choices:** 상/중/하

### aliases 데이터 계약

- **저장:** JSON 배열, 각 항목은 trim 처리, 대소문자 원본 유지
  - 예: `["CPA", "공인회계사"]`
- **검색:** 대소문자 무시. PostgreSQL `LOWER()` 비교 또는 `__icontains`
- **CSV 직렬화:** 세미콜론(`;`) 구분 문자열
  - 예: `"CPA;공인회계사"`
- **CSV import:** 세미콜론으로 split → trim → JSON 배열로 저장

---

## 마이그레이션 전략

모든 레퍼런스 테이블은 P01에서 생성되었으나 **빈 상태**이다. 따라서:

1. `makemigrations`로 필드 추가/변경/삭제 마이그레이션 자동 생성
2. RunPython 백필 불필요 (빈 테이블)
3. 단일 마이그레이션 파일로 3개 모델 변경을 묶어도 무방

---

## 관리 UI

3개 탭 전환(대학/기업/자격증), 동일한 레이아웃: 필터 + 테이블 + 페이지네이션 + 액션.

**HTMX 구조:**
- 전체 페이지 네비게이션: `hx-target="#main-content"` + `hx-push-url="true"`
- 탭 전환: `hx-target="#ref-tab-content"` (reference_index.html 내부의 탭 콘텐츠 영역)

```
┌─ 레퍼런스 관리 ─────────────────────────────────────┐
│  [대학 랭킹]  [기업 DB]  [자격증]                     │
│ ┌─ #ref-tab-content ─────────────────────────────┐ │
│ │ 필터: [국가▾] [티어▾]  검색: [         ]         │ │
│ │ ┌─────────┬──────────┬──────┬──────┬──────┐   │ │
│ │ │ 대학명   │ 영문명    │ 국가 │ 티어  │      │   │ │
│ │ │ 서울대   │ Seoul Nat│ KR   │ SKY  │ [수정]│   │ │
│ │ │ ...     │          │      │      │      │   │ │
│ │ └─────────┴──────────┴──────┴──────┴──────┘   │ │
│ │ [+ 추가]  [CSV 가져오기]  [CSV 내보내기]         │ │
│ └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**검색/필터:** 대학(국가, 티어, 이름), 기업(상장, 업종, 규모, 이름), 자격증(카테고리, 난이도, 이름/별칭).

**삭제:** 단순 삭제 허용 (현재 FK 참조 없음). 향후 FK 참조 추가 시 삭제 보호 구현.

---

## CSV 가져오기

단일 POST + 즉시 처리 + 결과 리포트 패턴.

### 처리 규칙

1. **헤더 검증:** 필수 컬럼 누락 시 전체 거부 + 에러 메시지
2. **인코딩:** UTF-8 (BOM 허용). 인코딩 오류 시 전체 거부
3. **행 처리:** 트랜잭션 내에서 전체 처리. 1건이라도 오류 시 전체 롤백
4. **upsert 기준:**
   - UniversityTier: `(name, country)` 일치 시 업데이트
   - CompanyProfile: `name` 일치 시 업데이트
   - PreferredCert: `name` 일치 시 업데이트
5. **choices 검증:** 유효하지 않은 choice 값은 행 오류로 처리
6. **결과 리포트:** 추가 N건, 수정 N건, 오류 N건 + 오류 행번호와 사유

### 모델별 CSV 컬럼

**UniversityTier:** `name`, `name_en`, `country`, `tier`, `ranking`, `notes`
**CompanyProfile:** `name`, `name_en`, `industry`, `size_category`, `revenue_range`, `employee_count_range`, `listed`, `region`, `notes`
**PreferredCert:** `name`, `full_name`, `category`, `level`, `aliases`, `notes`

aliases 컬럼은 세미콜론(`;`) 구분 문자열.

---

## CSV 내보내기

필터 적용 데이터 → CSV 다운로드 (UTF-8 BOM, Excel 호환).

**HTMX 제외:** 일반 `<a>` 태그 + `hx-boost="false"`. Content-Disposition: attachment 헤더.

---

## 사이드바 메뉴

사이드바 설정 영역 위에 추가 (`templates/common/nav_sidebar.html` + `templates/common/nav_bottom.html`):

```html
<a href="/reference/"
   hx-get="/reference/" hx-target="#main-content" hx-push-url="true"
   data-nav="reference"
   class="sidebar-tab ...">
  레퍼런스 관리
</a>
```

사이드바 JavaScript에 `reference` 키 추가 (`path.startsWith('/reference')`).

---

## 초기 데이터 로딩

management command로 초기 데이터 투입:

```bash
uv run python manage.py load_reference_data
```

**데이터 소스 파일:**
- `clients/fixtures/universities.csv` — 대학 목록 (~200교) — 직접 작성
- `clients/fixtures/companies.csv` — KOSPI/KOSDAQ 상장사 (~2,500사) — DART 기반 수동 작성
- `clients/fixtures/certs.csv` — 자격증 목록 (~800종, aliases 포함) — 한국산업인력공단 + 국제자격증 직접 작성

command는 idempotent — 재실행 시 기존 데이터 업데이트(upsert), 신규만 추가.

**갱신:** P12는 초기 적재만. 데이터 갱신은 CSV 파일 수정 후 커맨드 재실행으로 수동 처리. 정기 자동 갱신은 별도 Phase에서 기획.

---

## 웹검색 자동채움 (CompanyProfile)

기업 추가/수정 폼에서 회사명 입력 + [자동채움] 버튼 → 웹검색으로 업종/규모/매출/상장/소재지 자동 채움.

### 상세 스펙

- **API:** Gemini API + Google Search grounding (기존 프로젝트 인프라 활용)
- **입력:** 회사명 (string)
- **출력:** `{ industry, size_category, revenue_range, employee_count_range, listed, region }`
- **타임아웃:** 10초
- **실패 처리:** 빈값 유지 + 토스트 알림 ("자동채움에 실패했습니다. 직접 입력해 주세요.")
- **저장 방식:** 결과를 폼 필드에 채우기만 함. 저장은 사용자가 별도로 [저장] 클릭
- **외부 전송 안내:** 자동채움 버튼 옆에 "회사명이 외부 검색 서비스로 전송됩니다" 안내 문구
- **호출 방식:** 사용자가 명시적으로 [자동채움] 버튼 클릭 시에만 호출. 자동 호출 금지.

### 구현

`clients/services/company_autofill.py` — Gemini API 호출 + 응답 파싱 + 필드 매핑.

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| 대학 CRUD | 추가 → 목록 표시 → 수정 → 삭제 |
| 기업 CRUD | 추가 → 목록 표시 → 수정 → 삭제 |
| 자격증 CRUD | 추가 → 목록 표시 → 수정 → 삭제 |
| 탭 전환 | 대학 → 기업 → 자격증 탭 전환 |
| 검색/필터 | 이름 검색, 카테고리 필터 동작 |
| CSV 가져오기 | CSV 업로드 → 데이터 반영 |
| CSV 가져오기 오류 | 잘못된 CSV → 전체 롤백 + 에러 리포트 |
| CSV 내보내기 | 다운로드 → 파일 내용 정합 (UTF-8 BOM) |
| 초기 데이터 | `load_reference_data` → 대학/기업/자격증 데이터 확인 |
| 웹검색 자동채움 | 기업명 입력 → 필드 자동 채움 |
| 사이드바 메뉴 | 레퍼런스 관리 메뉴 접근 가능 |
| aliases 검색 | "CPA" 검색 → "KICPA" 매칭 |
| staff 권한 | 비staff 사용자 CRUD 시도 시 403 |
| unique constraint | 동일 대학(name+country) 중복 생성 시 에러 |

---

## 산출물

- `clients/models.py` — UniversityTier, CompanyProfile, PreferredCert 모델 변경
- `clients/migrations/0002_*.py` — 스키마 변경 마이그레이션
- `clients/views.py` (또는 별도 `views_reference.py`) — 레퍼런스 관리 뷰 (~20개)
- `clients/forms.py` — 각 모델 CRUD 폼 + CSV Import 폼
- `clients/urls_reference.py` — `/reference/` 하위 URL 전체
- `main/urls.py` — `/reference/` include 추가
- `clients/services/company_autofill.py` — 웹검색 자동채움
- `clients/services/csv_handler.py` — CSV 가져오기/내보내기 공통 로직
- `clients/management/commands/load_reference_data.py` — 초기 데이터 로딩
- `clients/fixtures/universities.csv`, `companies.csv`, `certs.csv` — 초기 데이터
- `clients/templates/clients/reference_index.html` — 메인 레이아웃
- `clients/templates/clients/partials/ref_universities.html` — 대학 탭
- `clients/templates/clients/partials/ref_companies.html` — 기업 탭
- `clients/templates/clients/partials/ref_certs.html` — 자격증 탭
- `templates/common/nav_sidebar.html` — 레퍼런스 관리 메뉴 추가
- `templates/common/nav_bottom.html` — 모바일 하단 네비 추가 (선택)
- 테스트 파일

## 프로젝트 컨텍스트 (핸드오프에서 확립된 패턴)

1. **Organization 격리:** 레퍼런스 모델은 예외 (전역 시스템 마스터). Client/Contract는 기존대로 organization 필터.
2. **@login_required:** 읽기 뷰. **@staff_member_required:** 쓰기 뷰.
3. **동적 extends:** `{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}`
4. **HTMX target:** `hx-target="#main-content"` (전체 네비), `hx-target="#ref-tab-content"` (탭 전환)
5. **UI 텍스트:** 한국어 존대말
6. **삭제:** 단순 삭제 허용 (현재 FK 참조 없음)
7. **HTMX CRUD 패턴:** `{model}Changed` 이벤트 + `#{model}-form-area` + 204+HX-Trigger
8. **DB 저장값:** 한국어 TextChoices 유지
9. **CSV export:** 일반 링크 + hx-boost="false" + Content-Disposition: attachment

<!-- forge:p12:설계담금질:complete:2026-04-08T22:35:00+09:00 -->
