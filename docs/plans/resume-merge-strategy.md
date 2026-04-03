# 이력서 중복 처리 및 머지 전략

## 1. 현황

| 구분 | 건수 | 상태 |
|------|------|------|
| primary 이력서 | 1,145건 | 텍스트 추출 + LLM 파싱 완료 |
| 중복 이력서 (others) | 275건 | 텍스트 미추출 (pending), candidate 연결됨 |
| 추출 실패 (orphan) | 424건 | 텍스트 추출 실패, candidate 없음 |

209명이 2개 이상의 이력서를 보유 (최대 6개).

## 2. 문제

- 중복 이력서 275건의 텍스트가 추출되지 않아 연봉/최신 경력 등 정보 손실 가능
- primary 선정 기준이 "파일 수정일 최신순"인데, 수정일이 이력서 내용의 최신성을 보장하지 않음
- 추출 실패 424건은 candidate조차 생성되지 않은 완전 누락

## 3. 처리 단계

### Phase 1: 중복 이력서 텍스트 추출 (275건)

구글 드라이브에서 파일 다운로드 → 텍스트 추출 → Resume.raw_text에 저장.
LLM 파싱은 하지 않음. 텍스트만 확보.

```python
# management command: extract_pending_resumes
for resume in Resume.objects.filter(is_primary=False, processing_status='pending', candidate__isnull=False):
    # 1. 드라이브에서 다운로드
    # 2. 텍스트 추출 (extract_text)
    # 3. resume.raw_text = text, status = 'parsed'
    # 4. resume.save()
```

### Phase 2: 추출 실패 재시도 (424건)

실패 원인 분석 후 재시도:
- LibreOffice 없어서 실패 → 지금은 설치됨, 재시도 가능
- 파일 손상 → 스킵
- LLM 타임아웃 → 재시도

```python
# management command: retry_failed_resumes
for resume in Resume.objects.filter(candidate__isnull=True, processing_status='failed'):
    # 기존 import_resumes 파이프라인으로 재처리
```

### Phase 3: 동일 후보자 이력서 머지

한 후보자의 여러 이력서(primary + others)를 하나의 통합 프로필로 머지.

#### 머지 원칙

1. **최신 우선 (Recency)**: 동일 필드에 값이 여러 개면 가장 최신 이력서의 값을 채택
2. **보충 (Supplement)**: primary에 없는 필드가 other에 있으면 추가
3. **충돌 시 primary 우선**: 같은 필드에 다른 값이면 primary를 유지하되, other 값을 `merge_notes`에 기록
4. **리스트 필드는 합집합**: careers, educations, certifications → 중복 제거 후 합침

#### 필드별 머지 규칙

| 필드 | 전략 | 이유 |
|------|------|------|
| name, name_en, gender, birth_year | primary 유지 | 변하지 않는 신상 정보 |
| email, phone, address | 최신 우선 | 변경 가능 |
| current_company, current_position | 최신 우선 | 이직 가능 |
| total_experience_years | 최대값 | 경력은 늘기만 함 |
| current_salary, desired_salary | 최신 우선 | 연봉은 변동 |
| salary_detail | 최신 우선 | 보수 구조 변동 |
| summary | 더 긴 것 | 더 상세한 요약 |
| core_competencies | 합집합 | 역량은 누적 |
| careers | 합집합 (회사+기간 기준 중복 제거) | 경력 추가 |
| educations | 합집합 (학교+전공 기준 중복 제거) | 학력 추가 |
| certifications | 합집합 (자격증명 기준 중복 제거) | 자격증 추가 |
| language_skills | 합집합 (언어+시험 기준 중복 제거) | 어학 추가 |
| awards | 합집합 | 수상 추가 |
| military_service | primary 유지 | 변하지 않음 |
| self_introduction | 더 긴 것 | 더 상세한 자기소개 |
| trainings | 합집합 | 교육 추가 |
| overseas_experience | 합집합 | 해외 경험 추가 |

#### 최신 판단 기준

이력서 내 "현재" 시점을 추정:
1. `careers`에서 `is_current=True`인 경력의 `start_date` → 해당 이력서가 작성된 대략적 시점
2. 파일 수정일 (`modified_time`)
3. 둘 다 없으면 파일명의 회사 정보 개수 (많을수록 최신 추정)

#### 중복 판단 기준

| 데이터 | 중복 판단 키 |
|--------|-------------|
| career | (company, start_date) 동일하면 중복 |
| education | (institution, major) 동일하면 중복 |
| certification | name ILIKE 매칭 (정규화 후 비교) |
| language_skill | (language, test_name) 동일하면 중복 |
| award | name ILIKE 매칭 |
| training | name ILIKE 매칭 |

### Phase 4: 머지 실행

```python
# management command: merge_candidate_resumes
for candidate in Candidate.objects.annotate(resume_count=Count('resumes')).filter(resume_count__gt=1):
    primary_resume = candidate.resumes.filter(is_primary=True).first()
    other_resumes = candidate.resumes.filter(is_primary=False, processing_status='parsed')
    
    for other in other_resumes:
        # 1. other.raw_text를 LLM으로 파싱 (누락 필드만 추출)
        # 2. 머지 규칙 적용
        # 3. candidate 업데이트
        # 4. 머지 로그 기록 (어떤 필드가 어디서 왔는지)
```

#### 머지 로그 (감사 추적)

```python
# Candidate 모델에 추가
merge_log = models.JSONField(default=list, blank=True)
# 예: [
#   {"field": "current_salary", "source": "resume_v2", "old": null, "new": 8000, "date": "2026-04-01"},
#   {"field": "careers", "action": "added", "source": "resume_v3", "value": {"company": "삼성", ...}},
# ]
```

## 4. 실행 순서

```
1. Phase 1: 중복 275건 텍스트 추출 (드라이브 다운로드 필요, ~30분)
2. Phase 2: 실패 424건 재시도 (~1시간)
3. Phase 3: 보완 추출 — 전체 raw_text에서 연봉/병역/수상 등 LLM 추출 (~$21)
4. Phase 4: 머지 실행 — 209명의 중복 이력서 통합
5. 검증: 머지 전후 데이터 건수 비교, 스팟체크
```

## 5. 비용/시간 추정

| 단계 | 시간 | API 비용 |
|------|------|---------|
| Phase 1 (텍스트 추출) | ~30분 | $0 |
| Phase 2 (실패 재시도) | ~1시간 | ~$5 (LLM 파싱) |
| Phase 3 (보완 추출) | ~2시간 | ~$21 |
| Phase 4 (머지) | ~1시간 | ~$10 (LLM 파싱) |
| **합계** | **~4.5시간** | **~$36** |
