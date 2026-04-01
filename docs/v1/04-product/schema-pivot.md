# DB Schema: 헤드헌팅 플랫폼 피보팅

## 개요

기존 보험 FC CRM → AI 헤드헌팅 플랫폼으로 전환.
Google Drive 이력서 2,000건+ → 구조화 → AI 매칭.

---

## 중복 후보자 처리

같은 사람이 여러 이력서를 제출한 케이스가 존재함:
- 같은 폴더 내 버전 차이 (경력 추가 후 재제출)
- 다른 폴더에 동일 인물 (직무 전환)

### 중복 판별 기준 (파이프라인 순서)

1. **파일명 매칭** — 이름 + 생년이 동일 (예: `강원용.81.*`)
2. **LLM 추출 후** — 이름 + 생년 + 전화번호/이메일 일치
3. **수동 머지** — AI가 "중복 가능성" 플래그 → 리크루터가 확인

### 처리 방식

- Candidate 1건에 Resume N건 연결 (이미 1:N)
- Resume에 `is_primary` 필드 — 가장 최신/완전한 이력서를 대표로 지정
- Education, Career 등 하위 데이터는 **대표 이력서 기준으로 추출**
- 이전 버전 이력서는 원본 보존만 (하위 데이터 미추출)

### 다른 카테고리에 같은 인물

- 한 Candidate에 `categories` M:N 관계 (주 카테고리 + 부 카테고리)
- 예: 강원용 → Engineer(주) + EHS(부)

---

## 핵심 엔티티

```
Candidate (후보자)          ← 이력서에서 추출
├── Education (학력)        ← 1:N
├── Career (경력)           ← 1:N
│   └── CareerDetail (업무상세) ← 1:N
├── Certification (자격증)  ← 1:N
├── LanguageSkill (어학)    ← 1:N
└── Resume (원본파일)       ← 1:N (버전 관리)

JobOpening (채용건)         ← 고객사가 의뢰
├── JobRequirement (요구사항) ← 1:1 embedded in fields
└── Placement (배치결과)    ← 1:N

Client (고객사)             ← 채용 의뢰 기업
└── ClientContact (담당자)  ← 1:N

Match (AI 매칭)             ← Candidate + JobOpening
```

---

## 모델 상세

### Candidate (후보자)

| 필드 | 타입 | 설명 |
|------|------|------|
| id | UUID | PK |
| name | CharField(50) | 한글 이름 |
| name_en | CharField(100) | 영문 이름 (nullable) |
| birth_year | SmallIntegerField | 출생년도 |
| gender | CharField(1) | M/F (nullable) |
| email | EmailField | nullable |
| phone | CharField(20) | nullable |
| address | CharField(200) | nullable |
| categories | ManyToMany(Category) | 직무 카테고리 (주/부) |
| primary_category | ForeignKey(Category) | 대표 카테고리 (nullable) |
| total_experience_years | SmallIntegerField | 총 경력 연수 (nullable) |
| current_company | CharField(100) | 현 직장 (nullable) |
| current_position | CharField(100) | 현 직급 (nullable) |
| current_salary | IntegerField | 현재 연봉 만원 (nullable) |
| desired_salary | IntegerField | 희망 연봉 만원 (nullable) |
| core_competencies | JSONField | 핵심역량 리스트 |
| summary | TextField | AI 요약 (nullable) |
| status | CharField | active / placed / inactive |
| source | CharField | drive_import / manual / referral |
| drive_file_id | CharField(100) | 구글 드라이브 파일 ID (nullable) |
| drive_folder | CharField(50) | 원본 폴더명 (nullable) |
| raw_text | TextField | 이력서 전문 텍스트 (검색용) |
| created_at | DateTimeField | |
| updated_at | DateTimeField | |

**인덱스:** category, status, birth_year, total_experience_years

---

### Category (직무 카테고리)

| 필드 | 타입 | 설명 |
|------|------|------|
| id | UUID | PK |
| name | CharField(50) | Accounting, Sales 등 |
| name_ko | CharField(50) | 회계, 영업 등 |
| candidate_count | IntegerField | 캐시 카운트 |

**초기 데이터:** 20개 (Accounting, EHS, Engineer, Finance, HR, Law, Logistics, Marketing, MD, MR, Plant, PR+AD, Procurement, Production, Quality, R&D, Sales, SCM, SI+IT, VMD)

---

### Education (학력)

| 필드 | 타입 | 설명 |
|------|------|------|
| id | UUID | PK |
| candidate | ForeignKey(Candidate) | CASCADE |
| institution | CharField(100) | 학교명 |
| degree | CharField(20) | bachelor / master / phd / etc |
| major | CharField(100) | 전공 (nullable) |
| gpa | CharField(20) | 학점 (nullable, 형식 다양) |
| start_year | SmallIntegerField | nullable |
| end_year | SmallIntegerField | nullable |
| is_abroad | BooleanField | 해외 학교 여부 |

---

### Career (경력)

| 필드 | 타입 | 설명 |
|------|------|------|
| id | UUID | PK |
| candidate | ForeignKey(Candidate) | CASCADE |
| company | CharField(100) | 회사명 |
| company_en | CharField(100) | 영문 회사명 (nullable) |
| position | CharField(100) | 직급/직책 |
| department | CharField(100) | 부서 (nullable) |
| start_date | CharField(20) | 입사일 (형식 다양 → 문자열) |
| end_date | CharField(20) | 퇴사일 (nullable = 재직중) |
| is_current | BooleanField | 현 직장 여부 |
| duties | TextField | 주요 업무 (nullable) |
| achievements | TextField | 성과 (nullable) |
| reason_left | CharField(200) | 퇴사 사유 (nullable) |
| salary | IntegerField | 당시 연봉 만원 (nullable) |
| order | SmallIntegerField | 정렬순서 (최신 0) |

---

### Certification (자격증)

| 필드 | 타입 | 설명 |
|------|------|------|
| id | UUID | PK |
| candidate | ForeignKey(Candidate) | CASCADE |
| name | CharField(100) | 자격증명 |
| issuer | CharField(100) | 발급기관 (nullable) |
| acquired_date | CharField(20) | 취득일 (nullable) |

---

### LanguageSkill (어학능력)

| 필드 | 타입 | 설명 |
|------|------|------|
| id | UUID | PK |
| candidate | ForeignKey(Candidate) | CASCADE |
| language | CharField(30) | 영어, 일본어, 중국어 등 |
| test_name | CharField(50) | TOEIC, OPIC 등 (nullable) |
| score | CharField(30) | 점수/등급 (nullable) |
| level | CharField(20) | native/fluent/business/basic (nullable) |

---

### Resume (원본 이력서)

| 필드 | 타입 | 설명 |
|------|------|------|
| id | UUID | PK |
| candidate | ForeignKey(Candidate) | CASCADE |
| file_name | CharField(300) | 원본 파일명 |
| drive_file_id | CharField(100) | 구글 드라이브 파일 ID |
| drive_folder | CharField(50) | 폴더명 |
| mime_type | CharField(50) | doc/docx |
| file_size | IntegerField | 바이트 |
| extracted_at | DateTimeField | 파싱 시각 (nullable) |
| is_primary | BooleanField | 대표 이력서 여부 (default False) |
| version | SmallIntegerField | 같은 후보자 이력서 버전 |
| created_at | DateTimeField | |

---

### Client (고객사)

| 필드 | 타입 | 설명 |
|------|------|------|
| id | UUID | PK |
| name | CharField(100) | 회사명 |
| name_en | CharField(100) | 영문명 (nullable) |
| industry | CharField(100) | 업종 |
| size | CharField(20) | startup/sme/mid/large/enterprise |
| region | CharField(50) | 지역 |
| website | URLField | nullable |
| memo | TextField | 메모 |
| created_at | DateTimeField | |
| updated_at | DateTimeField | |

---

### ClientContact (고객사 담당자)

| 필드 | 타입 | 설명 |
|------|------|------|
| id | UUID | PK |
| client | ForeignKey(Client) | CASCADE |
| name | CharField(50) | |
| position | CharField(100) | 직급 |
| email | EmailField | nullable |
| phone | CharField(20) | nullable |
| is_primary | BooleanField | 주 담당자 여부 |

---

### JobOpening (채용건)

| 필드 | 타입 | 설명 |
|------|------|------|
| id | UUID | PK |
| client | ForeignKey(Client) | CASCADE |
| title | CharField(200) | 포지션명 |
| category | ForeignKey(Category) | SET_NULL, nullable |
| department | CharField(100) | 부서 (nullable) |
| level | CharField(30) | staff/senior/manager/director/executive |
| experience_min | SmallIntegerField | 최소 경력 연수 |
| experience_max | SmallIntegerField | 최대 경력 연수 (nullable) |
| salary_min | IntegerField | 연봉 하한 만원 (nullable) |
| salary_max | IntegerField | 연봉 상한 만원 (nullable) |
| description | TextField | 상세 설명 |
| requirements | JSONField | 필수 요건 리스트 |
| preferred | JSONField | 우대 사항 리스트 |
| location | CharField(100) | 근무지 |
| status | CharField | open / filled / cancelled / on_hold |
| opened_at | DateField | 의뢰일 |
| deadline | DateField | 마감일 (nullable) |
| created_at | DateTimeField | |
| updated_at | DateTimeField | |

---

### CandidateMatch (AI 매칭)

| 필드 | 타입 | 설명 |
|------|------|------|
| id | UUID | PK |
| candidate | ForeignKey(Candidate) | CASCADE |
| job | ForeignKey(JobOpening) | CASCADE |
| score | IntegerField | 0-100 종합 점수 |
| experience_fit | IntegerField | 0-100 경력 적합도 |
| skill_fit | IntegerField | 0-100 역량 적합도 |
| salary_fit | IntegerField | 0-100 연봉 적합도 |
| ai_reasoning | TextField | AI 판단 근거 |
| status | CharField | suggested / shortlisted / submitted / interviewing / offered / placed / rejected |
| created_at | DateTimeField | |
| updated_at | DateTimeField | |

**Unique:** (candidate, job)

---

### Placement (배치 결과)

| 필드 | 타입 | 설명 |
|------|------|------|
| id | UUID | PK |
| match | OneToOneField(CandidateMatch) | CASCADE |
| offered_salary | IntegerField | 확정 연봉 만원 |
| start_date | DateField | 입사일 |
| fee_rate | DecimalField | 수수료율 % |
| fee_amount | IntegerField | 수수료 만원 |
| status | CharField | confirmed / started / warranty / completed / cancelled |
| notes | TextField | 비고 |
| created_at | DateTimeField | |

---

### CandidateEmbedding (벡터 검색)

| 필드 | 타입 | 설명 |
|------|------|------|
| id | UUID | PK |
| candidate | OneToOneField(Candidate) | CASCADE |
| vector | VectorField(3072) | pgvector |
| source_text | TextField | 임베딩 소스 텍스트 |
| source_hash | CharField(64) | 변경 감지 |

---

## 기존 모델 처리

| 기존 모델 | 처리 |
|-----------|------|
| Contact | **삭제** → Candidate + Client로 대체 |
| Interaction | **삭제** → 헤드헌팅에 불필요 |
| Task | **유지** → 채용건별 할 일 관리 (FK를 JobOpening으로 변경) |
| Meeting | **유지** → 후보자/고객사 미팅 관리 (FK 변경) |
| Brief | **삭제** → CandidateMatch.ai_reasoning으로 대체 |
| Match | **삭제** → CandidateMatch로 대체 |
| ContactEmbedding | **삭제** → CandidateEmbedding으로 대체 |
| ImportBatch | **재활용** → 드라이브 임포트 배치 추적 |
| User | **유지** → role 필드 변경 (fc→recruiter, ceo→삭제) |

---

## 데이터 파이프라인

```
Google Drive (2,000+ .doc/.docx)
  ↓ sync & download
Resume (원본 저장)
  ↓ antiword / python-docx → raw text
Candidate (LLM 구조화 추출)
  ├→ Education, Career, Certification, LanguageSkill
  └→ CandidateEmbedding (벡터화)

JobOpening (고객사 의뢰)
  ↓ AI 매칭
CandidateMatch (후보자 추천)
  ↓ 프로세스 진행
Placement (배치 완료)
```

---

## 인덱스 전략

```sql
-- 후보자 검색
CREATE INDEX idx_candidate_category ON candidates(category_id, status);
CREATE INDEX idx_candidate_experience ON candidates(total_experience_years);
CREATE INDEX idx_candidate_status ON candidates(status);

-- 경력 검색
CREATE INDEX idx_career_company ON careers(company);

-- 채용건 검색
CREATE INDEX idx_job_status ON job_openings(status, category_id);
CREATE INDEX idx_job_client ON job_openings(client_id, status);

-- 매칭
CREATE INDEX idx_match_job ON candidate_matches(job_id, score DESC);
CREATE INDEX idx_match_candidate ON candidate_matches(candidate_id, status);

-- 벡터 검색
CREATE INDEX idx_embedding_vector ON candidate_embeddings USING ivfflat (vector vector_cosine_ops);
```
