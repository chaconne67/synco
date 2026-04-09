# P12: Reference Data Management

> **Phase:** 12
> **선행조건:** P01 (clients 앱 기반 — UniversityTier, CompanyProfile, PreferredCert 모델)
> **산출물:** 레퍼런스 데이터 초기 구축 + 관리 UI + CSV 가져오기/내보내기

---

## 목표

대학 랭킹(UniversityTier), 기업 DB(CompanyProfile), 자격증 DB(PreferredCert)의
초기 데이터를 구축하고, 사이드바에서 접근 가능한 관리 UI를 제공한다.

---

## URL 설계

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/reference/` | GET | `reference_index` | 레퍼런스 관리 메인 (대학 탭 기본) |
| `/reference/universities/` | GET | `reference_universities` | 대학 랭킹 탭 |
| `/reference/universities/new/` | GET/POST | `university_create` | 대학 추가 |
| `/reference/universities/<pk>/edit/` | GET/POST | `university_update` | 대학 수정 |
| `/reference/universities/<pk>/delete/` | POST | `university_delete` | 대학 삭제 |
| `/reference/universities/import/` | POST | `university_import` | CSV 가져오기 |
| `/reference/universities/export/` | GET | `university_export` | CSV 내보내기 |
| `/reference/companies/` | GET | `reference_companies` | 기업 DB 탭 |
| `/reference/companies/new/` | GET/POST | `company_create` | 기업 추가 |
| `/reference/companies/<pk>/edit/` | GET/POST | `company_update` | 기업 수정 |
| `/reference/companies/<pk>/delete/` | POST | `company_delete` | 기업 삭제 |
| `/reference/companies/<pk>/autofill/` | POST | `company_autofill` | 웹검색 자동채움 |
| `/reference/companies/import/` | POST | `company_import` | CSV 가져오기 |
| `/reference/companies/export/` | GET | `company_export` | CSV 내보내기 |
| `/reference/certs/` | GET | `reference_certs` | 자격증 탭 |
| `/reference/certs/new/` | GET/POST | `cert_create` | 자격증 추가 |
| `/reference/certs/<pk>/edit/` | GET/POST | `cert_update` | 자격증 수정 |
| `/reference/certs/<pk>/delete/` | POST | `cert_delete` | 자격증 삭제 |
| `/reference/certs/import/` | POST | `cert_import` | CSV 가져오기 |
| `/reference/certs/export/` | GET | `cert_export` | CSV 내보내기 |

---

## 모델 (clients 앱)

### UniversityTier

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | UUID | PK |
| `name` | CharField | 대학명 (한글) |
| `name_en` | CharField blank | 대학명 (영문) |
| `country` | CharField(2) | 국가 코드 (KR, US, JP, ...) |
| `tier` | CharField choices | 분류 그룹 |
| `ranking` | PositiveSmallIntegerField null | 그룹 내 순위 (선택) |
| `notes` | TextField blank | 비고 |

**국내 7개 티어:** SKY, 서성한(SSG), 중경외시(JKOS), 건동홍(KDH), 인서울 기타, 이공계 명문(KAIST 등), 지방 거점 국립.

**해외 3개 티어:** 최상위(Harvard/MIT/Oxford/도쿄대), 상위(Ivy League/Russell Group 상위/와세다), 우수(Top 50/Russell Group/구제국대학).

### CompanyProfile

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | UUID | PK |
| `name` | CharField | 회사명 (한글) |
| `name_en` | CharField blank | 회사명 (영문) |
| `industry` | CharField | 업종 |
| `size_category` | CharField choices | 대기업/중견/중소/외국계/스타트업 |
| `revenue_range` | CharField blank | 매출 규모 |
| `employee_count_range` | CharField blank | 직원 수 규모 |
| `listed` | CharField choices | 상장 구분 |
| `region` | CharField blank | 소재지 |
| `notes` | TextField blank | 비고 |

**size_category choices:** 대기업/중견/중소/외국계/스타트업. **listed choices:** KOSPI/KOSDAQ/비상장/해외상장.

**초기 데이터:** KOSPI/KOSDAQ 상장사 (~2,500사). 비상장은 프로젝트 등록 시 점진적 추가.
**웹검색 자동채움:** 이름 입력 → 웹검색으로 industry, size_category, revenue_range, region 자동 채움.

### PreferredCert

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | UUID | PK |
| `name` | CharField | 자격증 약칭 (예: "KICPA") |
| `full_name` | CharField | 정식 명칭 (예: "한국공인회계사") |
| `category` | CharField choices | 분류 카테고리 |
| `level` | CharField choices | 난이도 (상/중/하) |
| `aliases` | JSONField default=list | 별칭 목록 (예: ["CPA", "공인회계사"]) |
| `notes` | TextField blank | 비고 |

**category choices:** 회계/재무, 법률, 기술/엔지니어링, IT, 의료/제약, 무역/물류, 건설/부동산, 식품/환경, 어학, 안전/품질, 기타.

**초기 데이터:** ~800종 국가자격증 + 국제자격증. aliases 포함하여 이력서 파싱 시 자동 매칭에 활용.

---

## 관리 UI

3개 탭 전환(대학/기업/자격증), 동일한 레이아웃: 필터 + 테이블 + 페이지네이션 + 액션.
HTMX 탭 전환: `hx-get="/reference/universities/"` → `hx-target="#ref-content"`.

```
┌─ 레퍼런스 관리 ─────────────────────────────────────┐
│  [대학 랭킹]  [기업 DB]  [자격증]                     │
│  필터: [국가▾] [티어▾]  검색: [         ]             │
│  ┌─────────┬──────────┬──────┬──────┬──────┐       │
│  │ 대학명   │ 영문명    │ 국가 │ 티어  │      │       │
│  │ 서울대   │ Seoul Nat│ KR   │ SKY  │ [수정]│       │
│  │ ...     │          │      │      │      │       │
│  └─────────┴──────────┴──────┴──────┴──────┘       │
│  [+ 추가]  [CSV 가져오기]  [CSV 내보내기]             │
└─────────────────────────────────────────────────────┘
```

**검색/필터:** 대학(국가, 티어, 이름), 기업(상장, 업종, 규모, 이름), 자격증(카테고리, 난이도, 이름/별칭).

**CSV 가져오기:** 업로드 → 미리보기 → 확인 후 upsert (이름 일치 시 업데이트).
**CSV 내보내기:** 필터 적용 데이터 → CSV 다운로드 (UTF-8 BOM, Excel 호환).

---

## 사이드바 메뉴

사이드바 하단 설정 영역에 추가:

```
├─────────────────────────────┤
│  ⚙️  레퍼런스 관리          │
│  👤  설정                   │
└─────────────────────────────┘
```

`hx-get="/reference/"` + `hx-target="main"` + `hx-push-url="true"`.

---

## 초기 데이터 로딩

management command로 초기 데이터 투입:

```bash
uv run python manage.py load_reference_data
```

**데이터 소스 파일:**
- `clients/fixtures/universities.csv` — 대학 목록 (~200교)
- `clients/fixtures/companies.csv` — KOSPI/KOSDAQ 상장사 (~2,500사)
- `clients/fixtures/certs.csv` — 자격증 목록 (~800종, aliases 포함)

command는 idempotent — 재실행 시 기존 데이터 업데이트, 신규만 추가.

---

## 웹검색 자동채움 (CompanyProfile)

기업 추가 폼에서 회사명 입력 + [자동채움] 버튼 → 웹검색으로 업종/규모/매출/상장/소재지 자동 채움.
**구현:** `clients/services/company_autofill.py` — 웹검색 API → 필드 매핑.

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
| CSV 내보내기 | 다운로드 → 파일 내용 정합 |
| 초기 데이터 | `load_reference_data` → 대학/기업/자격증 데이터 확인 |
| 웹검색 자동채움 | 기업명 입력 → 필드 자동 채움 |
| 사이드바 메뉴 | 레퍼런스 관리 메뉴 접근 가능 |
| aliases 검색 | "CPA" 검색 → "KICPA" 매칭 |

---

## 산출물

- `clients/models.py` — UniversityTier, CompanyProfile, PreferredCert 모델
- `clients/views.py` — 레퍼런스 관리 뷰 (~20개)
- `clients/forms.py` — 각 모델 CRUD 폼 + CSV Import 폼
- `clients/urls.py` — `/reference/` 하위 URL 전체
- `clients/services/company_autofill.py` — 웹검색 자동채움
- `clients/services/csv_handler.py` — CSV 가져오기/내보내기 공통 로직
- `clients/management/commands/load_reference_data.py` — 초기 데이터 로딩
- `clients/fixtures/universities.csv`, `companies.csv`, `certs.csv` — 초기 데이터
- `clients/templates/clients/reference_index.html` — 메인 레이아웃
- `clients/templates/clients/partials/ref_universities.html` — 대학 탭
- `clients/templates/clients/partials/ref_companies.html` — 기업 탭
- `clients/templates/clients/partials/ref_certs.html` — 자격증 탭
- 사이드바 템플릿 수정 (레퍼런스 관리 메뉴 추가)
- 테스트 파일
