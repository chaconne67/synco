# P19: Chrome Extension — 후보자 소싱 자동화

> **Phase:** 19
> **선행조건:** P01 (모델 기반, Organization 모델), P06 (컨택 관리)
> **산출물:** synco Chrome Extension + 서버 API

---

## 목표

Chrome Extension으로 후보자 소싱을 자동화한다. 헤드헌터가 LinkedIn, 잡코리아, 사람인 등
채용 사이트를 브라우징하면서 원클릭으로 프로필을 synco DB에 저장할 수 있게 한다.
Loxo, Recruiterflow, Gem 등 해외 리크루팅 SaaS들이 Chrome Extension으로 시작한 방식을 따른다.

핵심 기능:
- LinkedIn/잡코리아/사람인 프로필 페이지 DOM 파싱 + 원클릭 저장
- 프로필 방문 시 synco DB 중복 자동 감지
- 팝업에서 synco 후보자 DB 검색 + 유사 후보자 추천
- 서버에서 셀렉터 설정 업데이트 (사이트 DOM 변경 대응)

---

## URL 설계

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/api/extension/save-profile/` | POST | `extension_save_profile` | 파싱된 프로필 저장 (Candidate 생성/업데이트) |
| `/api/extension/check-duplicate/` | POST | `extension_check_duplicate` | 중복 체크 (이름+회사 또는 URL) |
| `/api/extension/search/` | GET | `extension_search` | 키워드 검색 |
| `/api/extension/auth-status/` | GET | `extension_auth_status` | 인증 상태 확인 |

---

## 기술 스택

| 구성요소 | 기술 | 비고 |
|---------|------|------|
| Chrome Extension | Manifest V3 | Service Worker 기반 |
| 팝업 UI | Vanilla JS + Tailwind CSS | 경량, 프레임워크 없음 |
| 콘텐츠 스크립트 | Vanilla JS | 사이트별 DOM 파싱 |
| 서버 API | Django REST views (JSON 응답) | candidates 앱 |
| 인증 | synco 세션 쿠키 또는 API 토큰 | |

---

## Extension 구조

```
synco-extension/
├── manifest.json
├── popup/
│   ├── popup.html          # 팝업 UI (검색, 설정)
│   ├── popup.js
│   └── popup.css
├── content/
│   ├── linkedin.js         # LinkedIn DOM 파싱 + 오버레이 버튼
│   ├── jobkorea.js         # 잡코리아 DOM 파싱
│   └── saramin.js          # 사람인 DOM 파싱
├── background/
│   └── service-worker.js   # API 통신, 인증 관리
├── icons/
└── styles/
    └── overlay.css         # 사이트 위 오버레이 스타일
```

---

## 서비스 구조

### Extension 측

| 파일 | 역할 |
|------|------|
| `background/service-worker.js` | API 통신 래퍼, 인증 토큰 관리, 메시지 라우팅 |
| `content/linkedin.js` | LinkedIn 프로필 DOM 파싱 + 오버레이 UI 주입 |
| `content/jobkorea.js` | 잡코리아 인재검색 DOM 파싱 + 오버레이 UI |
| `content/saramin.js` | 사람인 인재검색 DOM 파싱 + 오버레이 UI |
| `popup/popup.js` | 팝업 UI — 검색, 최근 저장 목록, 설정 |

### 서버 측

| 파일 | 역할 |
|------|------|
| `api/views.py` | Extension API 뷰 (save-profile, check-duplicate, search, auth-status) |
| `api/urls.py` | `/api/extension/` 하위 URL 라우팅 |
| `api/serializers.py` | 프로필 데이터 시리얼라이저 (파싱 데이터 검증) |
| `candidates/services/extension.py` | 프로필 저장 로직 (Candidate 생성/업데이트, 경력/학력 병합) |
| `candidates/services/duplicate.py` | 중복 감지 (이름+회사, LinkedIn URL, email/phone) |

---

## LinkedIn 파싱 대상 (DOM 구조)

| 데이터 | CSS 셀렉터 (참고, 변경 가능) | DB 필드 |
|--------|--------------------------|---------|
| 이름 | `.text-heading-xlarge` | Candidate.name |
| 현재 직함 | `.text-body-medium` | Candidate.current_position |
| 현재 회사 | 경력 첫번째 항목 | Candidate.current_company |
| 위치 | `.text-body-small` | Candidate.address |
| 경력 목록 | `#experience ~ .pvs-list` | Career 레코드들 |
| 학력 목록 | `#education ~ .pvs-list` | Education 레코드들 |
| 스킬 목록 | `#skills ~ .pvs-list` | Candidate.skills |

> **주의:** LinkedIn은 DOM 구조를 자주 변경하므로, 셀렉터는 설정 파일로 분리하여
> 서버에서 업데이트 가능하게 해야 한다. Extension이 시작 시 서버에서 최신 셀렉터를 받아온다.

---

## 프로필 저장 파이프라인

1. Extension이 DOM에서 raw 데이터 파싱
2. 서버로 전송 (`POST /api/extension/save-profile/`)
3. 서버에서:
   - 중복 체크 (이름+현재회사, LinkedIn URL)
   - 중복이면: 기존 후보자 업데이트 (경력/학력 병합)
   - 신규면: Candidate + Career + Education 생성
   - `source = "chrome_extension"` 으로 마킹
4. 응답으로 저장 결과 + synco URL 반환

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

### 오버레이 UI — 이미 저장된 후보자

```
┌─────────────────────────────┐
│ synco  DB에 있음             │
│ 홍길동 / 메디톡스 품질부장     │
│ 최종 업데이트: 2026.03.15    │
│ [프로필 업데이트] [상세 보기]  │
└─────────────────────────────┘
```

### 오버레이 UI — 새 후보자

```
┌─────────────────────────────┐
│ synco  새 후보자              │
│ [후보자로 저장]               │
└─────────────────────────────┘
```

---

## 법적 고려사항

- 사용자(헤드헌터)의 LinkedIn 세션을 활용하므로 API 접근이 아닌 사용자 행위 보조
- 개인정보보호법상 후보자 동의 프로세스는 별도 관리 필요 (synco 메인 앱에서)
- LinkedIn TOS: 자동화된 대량 수집은 금지이나, 사용자가 직접 방문한 프로필의 개별 저장은 회색 지대
  - Loxo, Gem 등도 동일 방식 운영 중

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| LinkedIn 파싱 | LinkedIn 프로필 페이지에서 이름/경력/학력 정확하게 파싱 |
| 잡코리아 파싱 | 잡코리아 인재검색 결과에서 프로필 데이터 파싱 |
| 사람인 파싱 | 사람인 인재검색 결과에서 프로필 데이터 파싱 |
| 원클릭 저장 | 저장 버튼 클릭 → synco DB에 후보자 생성 확인 |
| 중복 감지 | 이미 저장된 후보자의 프로필 방문 시 "DB에 있음" 표시 |
| 프로필 업데이트 | 기존 후보자의 경력 변경 감지 및 업데이트 |
| 팝업 검색 | 팝업에서 키워드 검색 → 결과 표시 |
| 인증 | synco 로그인 상태에서만 동작, 미로그인 시 안내 |
| source 마킹 | 저장된 후보자의 source가 `chrome_extension`으로 기록 |
| 셀렉터 갱신 | 서버에서 셀렉터 변경 → Extension 재시작 시 반영 |

---

## 산출물

- `synco-extension/` 디렉토리 (Chrome Extension 전체)
  - `manifest.json` — Manifest V3 설정
  - `content/linkedin.js` — LinkedIn DOM 파싱
  - `content/jobkorea.js` — 잡코리아 DOM 파싱
  - `content/saramin.js` — 사람인 DOM 파싱
  - `background/service-worker.js` — API 통신 + 인증
  - `popup/popup.html`, `popup.js`, `popup.css` — 팝업 UI
  - `styles/overlay.css` — 오버레이 스타일
- `api/views.py` — Extension API 뷰
- `api/urls.py` — `/api/extension/` 하위 URL
- `api/serializers.py` — 프로필 데이터 시리얼라이저
- `candidates/services/extension.py` — 프로필 저장/업데이트 로직
- `candidates/services/duplicate.py` — 중복 감지 서비스
- Candidate.Source choices에 `CHROME_EXTENSION = "chrome_extension"` 추가
- Chrome Web Store 배포 가이드
- 테스트 파일
