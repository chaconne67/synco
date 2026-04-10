# P19: Chrome Extension — 후보자 소싱 자동화 (확정 설계서)

> **Phase:** 19
> **선행조건:** P01 (모델 기반, Organization 모델), P06 (컨택 관리)
> **산출물:** synco Chrome Extension + 서버 API

---

## 목표

Chrome Extension으로 후보자 소싱을 자동화한다. 헤드헌터가 LinkedIn, 잡코리아, 사람인 등
채용 사이트를 브라우징하면서 원클릭으로 프로필을 synco DB에 저장할 수 있게 한다.

핵심 기능:
- LinkedIn/잡코리아/사람인 프로필 페이지 DOM 파싱 + 원클릭 저장
- 프로필 방문 시 synco DB 중복 자동 감지 (organization 스코핑)
- 팝업에서 synco 후보자 DB 검색 (organization 스코핑)
- 파싱 결과 사용자 확인 후 저장 (자동 저장 금지)

### Phase 구분

- **Phase 1 (본 설계):** Extension 코어 + 서버 API + 3개 사이트 파서
- **Phase 2 (향후):** 서버 셀렉터 관리, 관찰성 대시보드, Chrome Web Store 공개 배포

---

## 모델 변경

### Candidate 모델 확장

```python
# candidates/models.py — Source choices 추가
class Source(models.TextChoices):
    DRIVE_IMPORT = "drive_import", "드라이브 임포트"
    MANUAL = "manual", "직접 입력"
    REFERRAL = "referral", "추천"
    CHROME_EXT = "chrome_ext", "크롬 확장"  # 10 chars, fits max_length=15

# 새 필드 추가
external_profile_url = models.CharField(
    max_length=500, blank=True, db_index=True,
    help_text="LinkedIn/잡코리아/사람인 프로필 URL (정규화)"
)
consent_status = models.CharField(
    max_length=20, blank=True, default="",
    help_text="not_requested | requested | granted | denied"
)

class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=["owned_by", "external_profile_url"],
            condition=models.Q(external_profile_url__gt=""),
            name="unique_candidate_external_url_per_org",
        ),
    ]
```

### ExtractionLog Action 확장

```python
class Action(models.TextChoices):
    AUTO_EXTRACT = "auto_extract", "자동 추출"
    HUMAN_EDIT = "human_edit", "사람 편집"
    HUMAN_CONFIRM = "human_confirm", "사람 확인"
    EXTENSION_SAVE = "extension_save", "확장 저장"  # NEW
```

---

## URL 설계

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/candidates/extension/auth-status/` | GET | `extension_auth_status` | 인증 상태 + CSRF 토큰 반환 |
| `/candidates/extension/save-profile/` | POST | `extension_save_profile` | 파싱된 프로필 저장 |
| `/candidates/extension/check-duplicate/` | POST | `extension_check_duplicate` | 중복 체크 (org 스코핑) |
| `/candidates/extension/search/` | GET | `extension_search` | 키워드 검색 (org 스코핑, 페이지네이션) |
| `/candidates/extension/stats/` | GET | `extension_stats` | 총 후보자 수 (org 스코핑) |

모든 엔드포인트: `@login_required` + organization 스코핑 필수.

---

## 인증 메커니즘

- **인증 방식:** Django 세션 쿠키 (API 토큰 없음)
- **CSRF 처리:**
  1. Extension이 `GET /candidates/extension/auth-status/`를 호출하여 CSRF 토큰 획득
  2. POST 요청 시 `X-CSRFToken` 헤더에 토큰 포함
- **쿠키 설정:** Production에서 `SameSite=None; Secure` 필수
- **Extension manifest:** `host_permissions`에 synco 서버 URL 포함 → 쿠키 자동 전송
- **Fetch 설정:** 모든 API 호출에 `credentials: "include"` 사용

---

## 기술 스택

| 구성요소 | 기술 | 비고 |
|---------|------|------|
| Chrome Extension | Manifest V3 | Service Worker 기반 |
| 팝업 UI | Vanilla JS + Tailwind CSS | 경량, 프레임워크 없음 |
| 콘텐츠 스크립트 | Vanilla JS | 사이트별 DOM 파싱 |
| 서버 API | Django views + JsonResponse | DRF 사용하지 않음 |
| 인증 | Django 세션 쿠키 + CSRF | API 토큰 없음 |

---

## Extension 구조

```
synco-extension/
├── manifest.json              # Manifest V3 + host_permissions
├── popup/
│   ├── popup.html             # 팝업 UI (검색, 설정)
│   ├── popup.js
│   └── popup.css
├── content/
│   ├── linkedin.js            # LinkedIn /in/* 프로필 DOM 파싱
│   ├── jobkorea.js            # 잡코리아 DOM 파싱
│   └── saramin.js             # 사람인 DOM 파싱
├── background/
│   └── service-worker.js      # API 통신, 인증, 메시지 라우팅
├── options/
│   ├── options.html           # 설정 페이지 (서버 URL)
│   └── options.js
├── icons/
└── styles/
    └── overlay.css            # 사이트 위 오버레이 스타일
```

### Manifest V3 설정

```json
{
  "manifest_version": 3,
  "name": "synco - 후보자 소싱",
  "version": "1.0.0",
  "permissions": ["storage", "activeTab"],
  "host_permissions": [
    "*://*.linkedin.com/*",
    "*://*.jobkorea.co.kr/*",
    "*://*.saramin.co.kr/*"
  ],
  "content_scripts": [
    {
      "matches": ["*://*.linkedin.com/in/*"],
      "js": ["content/linkedin.js"],
      "css": ["styles/overlay.css"]
    },
    {
      "matches": ["*://*.jobkorea.co.kr/*"],
      "js": ["content/jobkorea.js"],
      "css": ["styles/overlay.css"]
    },
    {
      "matches": ["*://*.saramin.co.kr/*"],
      "js": ["content/saramin.js"],
      "css": ["styles/overlay.css"]
    }
  ],
  "background": {
    "service_worker": "background/service-worker.js"
  },
  "action": {
    "default_popup": "popup/popup.html",
    "default_icon": "icons/icon48.png"
  },
  "options_page": "options/options.html",
  "icons": {
    "16": "icons/icon16.png",
    "48": "icons/icon48.png",
    "128": "icons/icon128.png"
  }
}
```

**주의:** synco 서버 URL은 `host_permissions`에 동적으로 추가할 수 없으므로, 빌드 시 production URL을 포함한다. 개발 시에는 별도 manifest로 `localhost:8000` 추가.

---

## 서버 구조

모든 서버 코드는 `candidates/` 앱 내에 배치 (별도 `api/` 앱 생성하지 않음).

| 파일 | 역할 |
|------|------|
| `candidates/views_extension.py` | Extension API 뷰 (5개 엔드포인트) |
| `candidates/serializers_extension.py` | 프로필 데이터 검증 (plain Python, DRF 미사용) |
| `candidates/urls.py` | 기존 URL에 `/extension/` 하위 패턴 추가 |
| `candidates/services/candidate_identity.py` | 기존 서비스 확장: `identify_candidate_from_extension()` |

---

## 중복 감지 정책

기존 `candidate_identity.py` 정책을 확장한다. **auto-merge 정책 유지: email/phone만 자동 병합.**

| 매칭 기준 | 동작 | 비고 |
|-----------|------|------|
| `external_profile_url` 일치 (same org) | 자동 매칭 → 업데이트 제안 | 새 필드, unique constraint |
| email 일치 | 자동 매칭 (기존 정책) | `candidate_identity.py` 재사용 |
| phone 일치 | 자동 매칭 (기존 정책) | `candidate_identity.py` 재사용 |
| name + company 일치 | **가능한 매칭** → 사용자 확인 필요 | 자동 병합 금지 |
| 매칭 없음 | 새 후보자 생성 | |

`identify_candidate_from_extension(data, organization)` 함수:
1. `external_profile_url` 매칭 (org 스코핑)
2. email 매칭 (기존 함수 재사용)
3. phone 매칭 (기존 함수 재사용)
4. name + company 유사 매칭 → `possible_matches` 리스트 반환

---

## 프로필 저장 파이프라인

1. Extension이 DOM에서 raw 데이터 파싱 → `parse_quality` 산출 (complete/partial/failed)
2. **사용자가 오버레이에서 파싱 결과 확인** (자동 저장 금지)
3. 사용자가 "저장" 클릭 → 서버로 전송 (`POST /candidates/extension/save-profile/`)
4. 서버에서:
   - 입력 데이터 검증 (required fields, max lengths, HTML strip, payload limit)
   - Organization 스코핑: `request.user` → organization
   - `identify_candidate_from_extension(data, org)` 호출
   - **자동 매칭:** 기존 후보자 발견 → 변경 사항 diff 반환 (자동 업데이트 안 함)
   - **가능한 매칭:** possible_matches 리스트 반환 → 사용자 확인 필요
   - **매칭 없음:** `transaction.atomic()` 내에서 Candidate + Career + Education 생성
   - `source = Candidate.Source.CHROME_EXT`, `owned_by = org`
   - `consent_status = "not_requested"`
   - ExtractionLog 기록 (`Action.EXTENSION_SAVE`)
5. 응답으로 저장 결과 + synco URL 반환

### 업데이트 플로우 (기존 후보자)

자동 매칭 시 서버가 diff를 반환하면:
1. Extension이 오버레이에서 변경 사항을 사용자에게 표시
2. 사용자가 개별 필드 업데이트를 확인/거부
3. 확인된 필드만 `POST /candidates/extension/save-profile/` 재전송 (`update_mode=true`, `candidate_id=...`, `fields=[...]`)
4. Career/Education: 새 레코드는 추가, 기존 레코드는 사용자 확인 없이 수정하지 않음

### Career/Education 병합 규칙

- Career identity key: `(normalize(company), start_date)`
- Education identity key: `(normalize(institution), degree)`
- 동일 키 레코드 발견: diff를 사용자에게 표시, 확인 시에만 업데이트
- 새 레코드: 추가
- 동일 URL + 동일 데이터: no-op (멱등성)

---

## 데이터 검증

### 필수/선택 필드

| 필드 | 필수 | max_length | 검증 |
|------|------|-----------|------|
| name | Yes | 100 | HTML strip, whitespace normalize |
| current_company | No | 255 | HTML strip |
| current_position | No | 255 | HTML strip |
| address | No | 500 | HTML strip |
| email | No | 254 | EmailValidator |
| phone | No | 255 | digits + special chars only |
| external_profile_url | No | 500 | URLValidator, normalize |
| skills | No | array, max 100 items | each max 100 chars |
| careers | No | array, max 50 items | nested validation |
| educations | No | array, max 20 items | nested validation |

### 저장 최소 조건

`name` + 다음 중 1개 이상: `current_company`, `current_position`, `email`, `external_profile_url`

### Payload 제한

- 총 payload: 100KB
- 모든 텍스트: HTML 태그 제거 (bleach 또는 수동 strip)
- URL 정규화: query params 제거, trailing slash 제거, lowercase

---

## API 응답 계약

### 공통 응답 형식

```json
{
  "status": "success" | "error" | "duplicate_found" | "possible_match",
  "data": { ... },
  "errors": [ ... ]
}
```

### HTTP 상태 코드

| Code | 의미 | 사용 |
|------|------|------|
| 200 | 성공 | auth-status, search, check-duplicate, stats |
| 201 | 생성됨 | save-profile (신규) |
| 400 | 검증 오류 | 필수 필드 누락, 형식 오류 |
| 401 | 미인증 | 세션 만료, 로그인 필요 |
| 403 | 권한 없음 | 다른 org 리소스 접근 시도 |
| 409 | 중복 발견 | save-profile (기존 후보자 매칭) |
| 429 | 요청 제한 | 일일 저장 100건 초과 |
| 500 | 서버 오류 | 예기치 않은 오류 |

### save-profile 응답 예시

**신규 생성 (201):**
```json
{
  "status": "success",
  "data": {
    "candidate_id": "uuid",
    "name": "홍길동",
    "synco_url": "/candidates/uuid/",
    "operation": "created"
  }
}
```

**기존 매칭 — 자동 (409):**
```json
{
  "status": "duplicate_found",
  "data": {
    "candidate_id": "uuid",
    "name": "홍길동",
    "match_reason": "external_url",
    "synco_url": "/candidates/uuid/",
    "diff": {
      "current_position": {"old": "과장", "new": "부장"},
      "new_careers": [{ ... }]
    }
  }
}
```

**가능한 매칭 (409):**
```json
{
  "status": "possible_match",
  "data": {
    "possible_matches": [
      {
        "candidate_id": "uuid",
        "name": "홍길동",
        "company": "메디톡스",
        "match_reason": "name_company",
        "synco_url": "/candidates/uuid/"
      }
    ]
  }
}
```

---

## 지원 페이지 유형

| 사이트 | 지원 URL 패턴 | 데이터 완전성 |
|--------|-------------|-------------|
| LinkedIn | `/in/*` (프로필 상세) | 높음 (이름, 경력, 학력, 스킬) |
| 잡코리아 | 인재검색 상세 페이지 | 중간~높음 |
| 잡코리아 | 인재검색 결과 카드 | 낮음 (이름, 회사, 직함) |
| 사람인 | 인재검색 상세 페이지 | 중간~높음 |
| 사람인 | 인재검색 결과 카드 | 낮음 (이름, 회사, 직함) |

LinkedIn 검색 결과 페이지 (`/search/results/people/`)는 지원하지 않음 (불완전한 데이터).

---

## DOM 파싱 & 파서 품질

### LinkedIn 파싱 대상 (참고 셀렉터, 변경 가능)

| 데이터 | CSS 셀렉터 (참고) | DB 필드 |
|--------|------------------|---------|
| 이름 | `.text-heading-xlarge` | Candidate.name |
| 현재 직함 | `.text-body-medium` | Candidate.current_position |
| 현재 회사 | 경력 첫번째 항목 | Candidate.current_company |
| 위치 | `.text-body-small` | Candidate.address |
| 경력 목록 | `#experience ~ .pvs-list` | Career 레코드 |
| 학력 목록 | `#education ~ .pvs-list` | Education 레코드 |
| 스킬 목록 | `#skills ~ .pvs-list` | Candidate.skills |
| 프로필 URL | `window.location.href` | Candidate.external_profile_url |

### 파서 품질 지표

각 파서는 `parse_quality` 지표를 반환:
- **complete:** name + 2개 이상 추가 필드 성공
- **partial:** name 성공 + 일부 필드 실패
- **failed:** name 파싱 실패

파싱 실패 시: 사용자에게 "파싱에 실패했습니다. 사이트 구조가 변경되었을 수 있습니다." 안내.
부분 파싱 시: 성공한 필드만 표시, 실패 필드는 빈칸으로 표시 + 경고.

> **Phase 1:** 셀렉터는 Extension 코드에 번들. Extension 업데이트로 셀렉터 변경 배포.
> **Phase 2:** 서버 셀렉터 관리 (선언적 CSS 셀렉터만, 실행 코드 금지).

---

## UI 와이어프레임

### 팝업 UI

```
┌─ synco Extension ────────────────────┐
│                                       │
│  [후보자 검색...              ] [검색] │
│                                       │
│  최근 저장:                           │
│  - 홍길동 - 메디톡스 (방금 전)         │
│  - 김영희 - 오스템 (1시간 전)          │
│                                       │
│  오늘: 3명 저장 | 총 DB: 1,234명       │
│                                       │
│  [synco 열기]  [설정]                  │
└───────────────────────────────────────┘
```

- "최근 저장", "오늘 N명": `chrome.storage.local` (서버 호출 없음)
- "총 DB": `GET /candidates/extension/stats/` (org 스코핑)
- 검색: `GET /candidates/extension/search/?q=...` (페이지네이션 20건)

### 오버레이 UI — 이미 저장된 후보자 (auto match)

```
┌─────────────────────────────────────┐
│ synco  DB에 있음                     │
│ 홍길동 / 메디톡스 품질부장             │
│ 최종 업데이트: 2026.03.15            │
│                                     │
│ 변경 감지: 직함 과장→부장             │
│ [변경 사항 업데이트] [상세 보기] [무시] │
└─────────────────────────────────────┘
```

### 오버레이 UI — 가능한 매칭

```
┌─────────────────────────────────────┐
│ synco  유사 후보자 발견               │
│ 홍길동 / 메디톡스 (유사도: 이름+회사)  │
│ [같은 사람 → 업데이트] [다른 사람 → 새로 저장] │
└─────────────────────────────────────┘
```

### 오버레이 UI — 새 후보자

```
┌─────────────────────────────────────┐
│ synco  새 후보자                     │
│ 파싱 결과: 홍길동 / 메디톡스 / 부장    │
│ [후보자로 저장]                       │
└─────────────────────────────────────┘
```

### 오버레이 UI — 파싱 실패

```
┌─────────────────────────────────────┐
│ synco  파싱 실패                     │
│ 사이트 구조가 변경되었을 수 있습니다    │
│ [수동으로 synco에서 입력]             │
└─────────────────────────────────────┘
```

---

## TOS 준수 & 가드레일

- **사용자 클릭 필수:** 모든 저장은 사용자의 명시적 클릭으로만 실행 (자동 저장 금지)
- **자동 탐색 금지:** Background에서 페이지를 자동으로 열거나 탐색하지 않음
- **일일 제한:** 사용자당 최대 100건/일 저장 (서버에서 429 반환)
- **확인 오버레이:** 저장 전 파싱 결과를 오버레이에서 확인
- **감사 로그:** 모든 저장/업데이트 기록 (user, source_site, source_url, timestamp)
- **비활성화 스위치:** 사이트별 콘텐츠 스크립트 on/off (options page)

---

## 개인정보 처리

- Extension으로 생성된 후보자: `consent_status = "not_requested"` (기본값)
- Source metadata 기록: `source = "chrome_ext"`, `external_profile_url`, collector user
- 동의 워크플로우는 synco 메인 앱에서 별도 처리 (본 설계 범위 외)
- Extension은 사용자(헤드헌터)의 세션을 활용한 행위 보조 도구

---

## 서버 URL 설정

- Extension options 페이지에서 서버 URL 설정
- 기본값: Production URL (빌드 시 `manifest.json` 또는 상수로 포함)
- 저장: `chrome.storage.sync` (기기 간 동기화)
- URL 검증: 저장 시 `GET /candidates/extension/auth-status/` 호출로 연결 확인

---

## 감사 추적

모든 Extension 저장 행위를 `ExtractionLog`에 기록:

```python
ExtractionLog.objects.create(
    candidate=candidate,
    action=ExtractionLog.Action.EXTENSION_SAVE,
    actor=request.user,
    details={
        "source_site": "linkedin",  # linkedin | jobkorea | saramin
        "source_url": "https://linkedin.com/in/...",
        "operation": "created",  # created | updated | skipped
        "fields_changed": ["current_position", "careers"],
        "parse_quality": "complete",
    },
)
```

---

## 동시성 & 멱등성

- 모든 저장: `transaction.atomic()` 내에서 실행
- URL 기반 중복 방지: `UniqueConstraint(fields=["owned_by", "external_profile_url"])` — `IntegrityError` catch → 409 반환
- 클라이언트 이중 클릭 방지: 저장 버튼 debounce (300ms)
- 동일 URL + 동일 데이터 재전송: 변경 없음 응답 (멱등)

---

## 테스트 기준

### Django 서버 테스트

| 항목 | 검증 방법 |
|------|----------|
| 인증 | 미인증 요청 → 401, 인증 요청 → 200 |
| Organization 스코핑 | 다른 org 후보자 접근 → 403/빈 결과 |
| 프로필 저장 (신규) | POST → 201, Candidate/Career/Education 생성 확인 |
| 프로필 저장 (중복 URL) | POST → 409 + diff |
| 프로필 저장 (가능한 매칭) | POST → 409 + possible_matches |
| 입력 검증 | 필수 필드 누락 → 400, 초과 길이 → 400, HTML → strip |
| 멱등성 | 동일 데이터 재전송 → 변경 없음 |
| 동시성 | 동시 저장 → unique constraint, 1건만 생성 |
| 검색 | 키워드 → org 스코핑된 결과, 페이지네이션 |
| 중복 체크 | org 내 매칭만 반환, cross-org 접근 불가 |
| 일일 제한 | 101번째 저장 → 429 |
| 감사 로그 | 저장/업데이트 시 ExtractionLog 생성 확인 |
| Source 마킹 | 저장된 후보자의 source == "chrome_ext" |

### Extension 파서 테스트

| 항목 | 검증 방법 |
|------|----------|
| LinkedIn 파싱 | 저장된 HTML fixture에서 name/경력/학력 정확 파싱 |
| 잡코리아 파싱 | 저장된 HTML fixture에서 프로필 데이터 파싱 |
| 사람인 파싱 | 저장된 HTML fixture에서 프로필 데이터 파싱 |
| 부분 파싱 | 일부 필드 누락 → partial 결과 + 경고 |
| 파싱 실패 | 비정상 DOM → failed 결과 + 에러 메시지 |
| URL 정규화 | 다양한 URL 형태 → 정규화된 URL |

---

## 산출물

### Extension

- `synco-extension/manifest.json` — Manifest V3, host_permissions, content_scripts
- `synco-extension/content/linkedin.js` — LinkedIn /in/* DOM 파싱 + 오버레이
- `synco-extension/content/jobkorea.js` — 잡코리아 DOM 파싱 + 오버레이
- `synco-extension/content/saramin.js` — 사람인 DOM 파싱 + 오버레이
- `synco-extension/background/service-worker.js` — API 통신, 인증, 메시지 라우팅
- `synco-extension/popup/popup.html`, `popup.js`, `popup.css` — 팝업 UI
- `synco-extension/options/options.html`, `options.js` — 서버 URL 설정
- `synco-extension/styles/overlay.css` — 오버레이 스타일

### 서버

- `candidates/views_extension.py` — Extension API 5개 뷰
- `candidates/serializers_extension.py` — 입력 데이터 검증 (plain Python)
- `candidates/urls.py` — `/extension/` 하위 URL 추가
- `candidates/services/candidate_identity.py` — `identify_candidate_from_extension()` 추가
- `candidates/models.py` — Source.CHROME_EXT, external_profile_url, consent_status 추가
- DB migration 파일

### 테스트

- `tests/test_extension_api.py` — 서버 API 테스트
- `synco-extension/tests/` — 파서 fixture 테스트

### 배포

- 초기 배포: 비공개/unlisted 배포 (Chrome Web Store 또는 직접 설치)
- 개인정보 처리방침 필요 (Extension store 등록 요건)

<!-- forge:p19-chrome-extension:설계담금질:complete:2026-04-10T13:55:00+09:00 -->
