# Candidate Schema Migration Plan

## 목표

- LLM/문서 원문이 조금 비정형이어도 DB 저장이 실패하지 않게 한다.
- 계산에 꼭 필요한 값만 정규화 상태를 유지하고, 나머지는 원문에 가까운 텍스트로 저장한다.
- 기존 코드 영향이 큰 리네임은 피하고, 먼저 **넉넉한 폭 확장 + 최소 보조 필드 추가** 중심으로 간다.

## 원칙

1. `raw/display` 성격의 값은 기본적으로 넉넉한 `CharField(255)`를 우선 검토한다.
2. `match / filter / sort / 계산`에 실제로 쓰는 값만 별도 정규화 필드를 둔다.
3. 1차 마이그레이션에서는 필드명 변경을 하지 않는다.
4. Postgres에서 길이 확장은 대부분 안전한 온라인 변경이므로, 먼저 `AlterField` 위주로 적용한다.
5. "30자면 충분하겠지" 같은 추정은 버리고, LLM 출력과 원문 변형을 전제로 스키마를 잡는다.

## 핵심 방향

- 전화번호, 날짜 문자열, 점수, 학교명, 회사명처럼 "한 줄짜리 값"은 대부분 `255` 전후로 넓힌다.
- 근거 문구처럼 길이가 튈 수 있는 값은 `TextField`로 바꾼다.
- 숫자 계산이나 상태값에 실제로 쓰는 필드는 지금처럼 정규화 유지한다.
- 구조화 추출 실패 시에도 raw text는 버리지 않고 저장한다.

## 필드 분류

### 1. 넓히기만 하면 되는 필드

이 필드들은 계산용 정규화가 꼭 필요하지 않고, 현재 실패 원인의 대부분이 "표현이 길어짐"이므로 폭을 충분히 넓히는 편이 낫다.

#### Candidate

- `phone`: `CharField(30)` -> `CharField(255)`
- `address`: `CharField(300)` -> `CharField(500)`
- `resume_reference_date`: `CharField(30)` -> `CharField(255)`
- `resume_reference_date_evidence`: `CharField(200)` -> `TextField(blank=True)`
- `current_company`: `CharField(200)` -> `CharField(255)`
- `current_position`: `CharField(200)` -> `CharField(255)`

#### Education

- `institution`: `CharField(100)` -> `CharField(255)`
- `degree`: `CharField(50)` -> `CharField(100)`
- `major`: `CharField(100)` -> `CharField(255)`
- `gpa`: `CharField(30)` -> `CharField(100)`

#### Career

- `company`: `CharField(200)` -> `CharField(255)`
- `company_en`: `CharField(200)` -> `CharField(255)`
- `position`: `CharField(200)` -> `CharField(255)`
- `department`: `CharField(200)` -> `CharField(255)`
- `start_date`: `CharField(30)` -> `CharField(255)`
- `end_date`: `CharField(30)` -> `CharField(255)`
- `end_date_inferred`: `CharField(30)` -> `CharField(255)`
- `duration_text`: `CharField(50)` -> `CharField(255)`
- `date_evidence`: `CharField(500)` -> `TextField(blank=True)`
- `reason_left`: `CharField(300)` -> `CharField(500)`

#### Certification

- `name`: `CharField(100)` -> `CharField(255)`
- `issuer`: `CharField(100)` -> `CharField(255)`
- `acquired_date`: `CharField(30)` -> `CharField(255)`

#### LanguageSkill

- `language`: `CharField(30)` -> `CharField(100)`
- `test_name`: `CharField(50)` -> `CharField(100)`
- `score`: `CharField(30)` -> `CharField(255)`
- `level`: `CharField(50)` -> `CharField(255)`

### 2. 정규화 유지가 필요한 필드

이 필드들은 enum, 상태값, 숫자 계산, 검색 키로 실제 의미가 있으므로 유지한다.

#### 그대로 유지

- `Candidate.birth_year`
- `Candidate.total_experience_years`
- `Candidate.current_salary`
- `Candidate.desired_salary`
- `Candidate.gender`
- `Candidate.status`
- `Candidate.source`
- `Candidate.validation_status`
- `Candidate.resume_reference_date_source`
- `Career.date_confidence`
- `Career.is_current`
- `Resume.processing_status`
- `ValidationDiagnosis.retry_action`

### 3. 보조 정규화 필드를 추가할 값

실제로 별도 정규화 필드를 둘 가치가 있는 건 현재 기준으로 `phone` 하나가 가장 크다.

#### 추가 제안

- `Candidate.phone_normalized = models.CharField(max_length=20, blank=True, db_index=True)`

의도:

- `phone`은 사람이 보는 값 / LLM이 추출한 대표값을 저장
- `phone_normalized`는 동일인 매칭용 숫자 정규화 값 저장

이 방식이면 `phone`에 `+82-10-1234-5678`, `010-1234-5678 / 02-123-4567` 같은 문자열이 들어와도 보관은 되고, 매칭은 `phone_normalized`로 안정적으로 할 수 있다.

## TextField vs 넉넉한 CharField 기준

이번 단계에서는 "한 줄 값"은 넉넉한 `CharField`, "근거 문구/서술"은 `TextField`로 단순하게 나누는 편이 낫다.

### 넉넉한 `CharField`를 유지하는 게 맞는 값

- phone
- address
- 날짜 문자열
- 회사명 / 직책 / 부서
- 학교명 / 전공 / 학위
- GPA
- 자격 취득일
- 자격증명 / 발급기관
- 어학 시험명 / 점수 / 수준
- duration text

이 값들은 "한 줄짜리 값"이라 `TextField`까지 갈 필요는 없지만, LLM 출력과 원문 변형을 감안하면 `CharField(100~255)`가 더 안전하다.

### `TextField`가 더 자연스러운 값

- `Candidate.summary`
- `Candidate.self_introduction`
- `Resume.raw_text`
- `Career.duties`
- `Career.inferred_capabilities`
- `Career.achievements`
- `Candidate.resume_reference_date_evidence`
- `Career.date_evidence`

### 왜 전부 `TextField`로 바꾸지 않나

- 인덱스/폼/UI 영향이 커진다.
- 실제 값은 대부분 한 줄이며, 서술형 본문과는 성격이 다르다.
- 따라서 "한 줄 값은 255 전후로 넉넉하게, 근거 문구만 TextField"가 운영상 균형이 좋다.

## 권장 마이그레이션 순서

### Migration 0015: widen_generous_text_fields

`AlterField`만 수행한다.

- `Candidate.phone` -> `255`
- `Candidate.address` -> `500`
- `Candidate.resume_reference_date` -> `255`
- `Candidate.resume_reference_date_evidence` -> `TextField`
- `Candidate.current_company` -> `255`
- `Candidate.current_position` -> `255`
- `Education.institution` -> `255`
- `Education.degree` -> `100`
- `Education.major` -> `255`
- `Education.gpa` -> `100`
- `Career.company` -> `255`
- `Career.company_en` -> `255`
- `Career.position` -> `255`
- `Career.department` -> `255`
- `Career.start_date` -> `255`
- `Career.end_date` -> `255`
- `Career.end_date_inferred` -> `255`
- `Career.duration_text` -> `255`
- `Career.date_evidence` -> `TextField`
- `Career.reason_left` -> `500`
- `Certification.name` -> `255`
- `Certification.issuer` -> `255`
- `Certification.acquired_date` -> `255`
- `LanguageSkill.language` -> `100`
- `LanguageSkill.test_name` -> `100`
- `LanguageSkill.score` -> `255`
- `LanguageSkill.level` -> `255`

이 단계는 데이터 마이그레이션이 필요 없다.

### Migration 0016: add_candidate_phone_normalized

`AddField`:

- `Candidate.phone_normalized = CharField(max_length=20, blank=True, db_index=True)`

### Migration 0017: backfill_candidate_phone_normalized

`RunPython`:

- 기존 `Candidate.phone` 값을 현재 정규화 로직으로 백필
- `select_primary_phone()` 후 `_normalize_phone()` 적용

### Migration 0018: switch_matching_to_phone_normalized

스키마 변경이 아니라 앱 로직 전환 단계다.

- 동일인 매칭은 `Candidate.phone_normalized` 우선 사용
- 저장 시 `phone`과 `phone_normalized`를 함께 갱신

## 필드별 한글 의미

- `Candidate.phone`: 화면 표시용 대표 연락처 문자열
- `Candidate.phone_normalized`: 동일인 비교용 정규화 전화번호
- `Candidate.resume_reference_date`: 이 이력서 정보가 어느 시점을 기준으로 하는지 나타내는 원문 날짜 문자열
- `Candidate.resume_reference_date_evidence`: 기준일을 그렇게 판단한 근거 문구
- `Candidate.current_company`: 현재 소속 회사명 원문
- `Candidate.current_position`: 현재 직책명 원문
- `Education.institution`: 학교명 원문
- `Education.degree`: 학위명 원문
- `Education.major`: 전공명 원문
- `Education.gpa`: 학점 표기 원문
- `Career.company`: 경력 회사명 원문
- `Career.position`: 경력 직책명 원문
- `Career.department`: 경력 부서명 원문
- `Career.start_date`: 입사/시작일 원문
- `Career.end_date`: 퇴사/종료일 원문
- `Career.end_date_inferred`: 종료일이 비어 있을 때 시스템이 추정한 종료일 문자열
- `Career.duration_text`: 재직기간 원문 표현
- `Career.date_evidence`: 날짜를 해석한 근거 문구
- `Certification.name`: 자격증명 원문
- `Certification.issuer`: 발급기관 원문
- `Certification.acquired_date`: 취득일 원문
- `LanguageSkill.language`: 언어명 원문
- `LanguageSkill.test_name`: 시험명 원문
- `LanguageSkill.score`: 점수/등급 원문
- `LanguageSkill.level`: 서술형 어학 수준 원문

## 추천 결론

1. 바로 적용:
   - `0015_widen_generous_text_fields`
   - `0016_add_candidate_phone_normalized`
   - `0017_backfill_candidate_phone_normalized`
2. 코드 전환:
   - phone 매칭을 `phone_normalized` 기반으로 변경
3. 보류:
   - `resume_reference_date` 전용 normalized 컬럼 추가
   - raw/normalized 리네임

## 실행 메모

- 현재 확인된 실패 유형 기준으로는 **폭을 255 중심으로 넓히는 것만으로도 대부분의 저장 장애가 사라진다**.
- `phone_normalized`는 기능 안정성을 위한 최소 추가 컬럼이다.
- `resume_reference_date`는 당장 별도 normalized 컬럼 없이도 현재 계산 로직을 유지할 수 있다.
