# synco 전체 프로젝트 점검 보고서

**일자:** 2026-04-03
**범위:** 프로젝트 전체 구조, 활성 앱, 핵심 기능 흐름, 테스트 상태, 운영 리스크
**점검자:** Codex + 서브에이전트 병렬 점검

---

## 1. 종합 판정

## 판정: CONDITIONAL GO

현재 레포는 **후보자 검색/상세/검수 + 이력서 임포트/추출 파이프라인** 중심의 단일 Django 앱으로 정리되어 있으며, 최근 `contacts`, `meetings`, `intelligence` 제거 이후 구조가 훨씬 단순해졌다. 핵심 기능은 테스트 기준으로 안정적이고, 자연어 검색도 SQL 직접 실행에서 구조화 필터 + ORM 방식으로 리팩터링되었다. 다만 LLM 필터 해석 품질, Google Drive secret 경로 의존, Docker의 실운영성 부족, historical 문서 drift 같은 운영 리스크는 아직 남아 있다.

### 요약 표

| 항목 | 상태 | 상세 |
|------|------|------|
| 핵심 후보자 기능 | **PASS** | 로그인, 후보자 목록/상세, 검수 화면, 자연어/음성 검색, 이력서 import 파이프라인이 코드상 연결되어 있음 |
| 활성 런타임 구조 | **PASS** | `accounts`, `candidates`, `main`, `common` 중심으로 단순화됨 |
| 테스트 상태 | **PASS** | `uv run pytest -q` 기준 **104 passed, 1 warning** |
| 실행 환경 정합성 | **PASS / WARNING** | 표준 경로는 `uv` 기준으로 정리됨. plain `pytest`는 여전히 실패 가능 |
| 검색 안전성 | **PASS / WARNING** | SQL 직접 실행은 제거됨. 다만 LLM 필터 해석 품질 리스크는 남아 있음 |
| 보안/secret 관리 | **WARNING** | gitignore는 보강됐지만 Google OAuth secret이 여전히 repo 내 `assets/` 경로를 사용 |
| 문서/환경 샘플 정합성 | **PASS / WARNING** | `.env.example`와 README는 개선됨. historical 문서는 여전히 삭제 전 구조를 참조 |

---

## 2. 현재 활성 제품 범위

### 실제 활성 앱

현재 Django 설정과 URL 라우팅 기준 활성 앱은 아래 둘뿐이다.

- `accounts`
- `candidates`

근거:

- `main/settings.py`의 `INSTALLED_APPS`에는 `accounts`, `candidates`만 포함됨
- `main/urls.py`는 `accounts.urls`, `candidates.urls`만 연결함

### 제거된 앱

다음 앱은 이번 기준 시점에 코드베이스에서 제거된 상태다.

- `contacts`
- `meetings`
- `intelligence`

즉, 현재 synco는 다중 도메인 통합 앱이 아니라 **후보자 도메인 중심의 단순화된 앱**으로 보는 것이 정확하다.

---

## 3. 핵심 구조 요약

### 인증/사용자

- `accounts.models.User`는 UUID PK 기반 커스텀 유저 모델
- 카카오 OAuth 로그인 플로우가 `accounts.views`에 구현되어 있음
- 설정/약관/개인정보처리방침 화면이 `accounts`에 남아 있음

### 후보자 도메인

`candidates` 앱이 프로젝트의 중심이다.

핵심 모델:

- `Candidate`
- `Resume`
- `Education`
- `Career`
- `Certification`
- `LanguageSkill`
- `ExtractionLog`
- `SearchSession`
- `SearchTurn`
- `CandidateEmbedding`
- `ValidationDiagnosis`

핵심 화면/엔드포인트:

- 후보자 목록: `/candidates/`
- 후보자 상세: `/candidates/<uuid>/`
- 검수 목록/상세: `/candidates/review/`
- 챗봇 검색: `/candidates/search/`
- 음성 전사: `/candidates/voice/`
- 채팅 히스토리: `/candidates/chat-history/`

### AI/데이터 파이프라인

이력서 처리 흐름은 아래와 같다.

1. `import_resumes` management command 실행
2. Google Drive에서 파일 목록 조회/다운로드
3. 텍스트 추출
4. Gemini 기반 구조화 추출
5. 규칙 검증 + 파일명 교차 검증
6. Candidate 및 하위 엔티티 저장
7. 추출 로그/진단 결과 저장

보조 기능:

- Whisper 기반 음성 전사
- Gemini 임베딩 생성
- LLM 기반 자연어 후보자 검색

---

## 4. 확인한 강점

### A. 구조가 이전보다 명확해짐

비활성 앱 제거 이후 현재 레포는 `accounts` + `candidates` 중심으로 이해하기 쉬워졌다. 실제 실행 범위와 코드베이스의 중심축이 맞아가고 있다.

### B. 핵심 기능이 한 도메인 안에서 이어짐

후보자 검색 UI, 상세 화면, 검수 흐름, 음성 입력, 자연어 검색, 이력서 import, 구조화 추출, 검증, 임베딩이 하나의 도메인으로 연결되어 있다. 데모 수준이 아니라 운영형 워크플로우를 염두에 둔 구조다.

### C. 테스트 기반이 유지되고 있음

다음 영역에 테스트가 존재한다.

- 모델
- 검색 뷰
- 파일명 파싱
- 검증 로직
- 추출 파이프라인
- Drive sync
- Whisper
- 임베딩
- LLM 유틸

재확인 결과:

```bash
uv run pytest -q
```

- 결과: **104 passed, 1 warning**
- warning: Python 3.13 환경에서는 위 Python 3.10 지원 종료 경고가 해소될 수 있음

### D. 개발 문서와 실행 경로가 일부 개선됨

README는 현재 활성 범위와 `uv` 기반 표준 실행 경로를 비교적 잘 설명하고 있다. 실제 개발 진입점은 `./dev.sh`, `uv run python manage.py runserver`, `uv run pytest -q`로 보는 것이 맞다.

---

## 5. 주요 리스크 및 발견 사항

### MEDIUM 1. 자연어 검색은 안전해졌지만 여전히 LLM 해석 품질에 의존

위치:

- `candidates/services/search.py`
- `candidates/views.py`

증상:

- 검색은 이제 구조화 필터를 생성해 Django ORM으로 적용함
- SQL 직접 실행 리스크는 제거되었지만, 필터 해석 정확도는 여전히 LLM 응답 품질에 좌우됨
- 다중 턴에서 이전 필터를 유지/교체하는 판단도 프롬프트 설계의 영향을 받음

영향:

- 보안 리스크는 크게 줄었음
- 대신 잘못된 필터 생성 시 결과 품질이 낮아질 수 있음
- 검색 UX 개선을 위해 추가 평가/테스트가 필요함

권장 조치:

- 검색 품질 회귀 테스트 추가
- 대표 질의셋으로 필터 생성 평가

### MEDIUM 2. secret 파일 관리가 여전히 repo 내부 경로에 의존

위치:

- `candidates/services/drive_sync.py`
- `.env.example`
- `.gitignore`

증상:

- Google OAuth secret/token 경로는 이제 settings/env로 설정 가능함
- 기본 예시는 `.secrets/`이지만, 여전히 프로젝트 작업 디렉토리 안에 둘 가능성이 높음

영향:

- 실수 커밋 위험은 줄었지만 완전히 없어지진 않음
- 로컬/서버 secret 관리 경계가 약함

권장 조치:

- 환경변수 또는 별도 secure path로 이동

### MEDIUM 3. Docker는 여전히 실운영 배포 구성이 아님

위치:

- `docker-compose.yml`
- `Dockerfile`
- `README.md`

증상:

- 문서/주석은 개발/실험용이라고 정리되었음
- 컨테이너는 이제 `gunicorn`으로 실행됨
- 다만 볼륨 마운트와 compose 구성은 여전히 개발/검증 중심

영향:

- 이전보다 나아졌지만, 운영용 컨테이너로 보기엔 아직 부족함

권장 조치:

- 운영 배포용 설정(정적 파일, 헬스체크, 환경 분리) 보강

### LOW 4. historical 문서가 삭제 전 앱 구조를 계속 참조함

위치:

- `docs/superpowers/plans/...`
- `docs/inspection/2026-03-31-production-readiness-inspection.md`

증상:

- 오래된 문서에는 `contacts`, `meetings`, `intelligence` 기준 설명이 남아 있음

영향:

- 현재 상태를 처음 파악하는 사람에게 혼란 가능

권장 조치:

- historical 문서임을 명확히 표시하거나
- 현재 상태 문서와 구분되는 섹션 표기 추가

---

## 6. 테스트 및 실행 확인 결과

### 수행한 확인

- 프로젝트 파일 구조 확인
- Django settings / URL 연결 확인
- `accounts`, `candidates` 주요 모델/뷰/서비스 확인
- import pipeline, Gemini extraction, Whisper, Drive sync 확인
- README, `.env.example`, Docker 설정 확인
- 검색 리팩터링(구조화 필터 + ORM) 확인
- 테스트 실행

### 테스트 결과

```bash
uv run pytest -q
```

- 성공
- 결과: **104 passed, 1 warning**

```bash
pytest -q
```

- 실패 가능
- 원인: 시스템 파이썬 기준 Django/pytest-django 미설정

판단:

- 현재 프로젝트의 표준 실행 경로는 **`uv` 전제**로 보는 것이 맞다

---

## 7. 권장 우선순위

### 1순위

- 검색 품질 평가용 테스트셋 보강
- secret 파일을 repo 외부 경로 또는 안전한 secret 관리 방식으로 이동

### 2순위

- Docker를 실제 WSGI 서버 기준으로 정리
- historical 문서에 현재 상태와의 차이 표시

### 3순위

- Python 3.11 이상 업그레이드 계획 수립

---

## 8. 결론

2026-04-03 기준 synco는 **후보자 도메인 중심의 단순화된 Django 프로젝트**로 보는 것이 정확하다. 이전에 존재하던 다른 앱 축은 제거되었고, 현재 실제 가치의 중심은 후보자 검색, 이력서 추출, 검수, 임베딩 파이프라인에 있다.

핵심 기능은 테스트 기준으로 안정적이다. 다만 지금 단계에서 가장 중요한 일은 기능 추가보다 **운영 리스크를 줄이는 정합성 작업**이다. 특히 검색 SQL 구조, DB 전제, secret 관리, 환경 문서 정리는 다음 개발 라운드 전에 우선 처리하는 것이 바람직하다.
