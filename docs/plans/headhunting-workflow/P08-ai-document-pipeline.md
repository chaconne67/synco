# P08: AI Document Pipeline

> **Phase:** 8
> **선행조건:** P07 (Submission CRUD — 추천 서류 기본 구조 존재)
> **산출물:** SubmissionDraft 기반 AI 문서 생성 파이프라인 전체 (초안 → 상담 → 최종 → 변환)

---

## 목표

후보자 DB 데이터를 기반으로 고객사 제출용 서류를 AI가 자동 생성하는 파이프라인을 구현한다.
6단계 흐름: AI 초안 생성 → AI 자동 보정 → 상담 내용 입력 → AI 최종 정리 → 컨설턴트 검토 → 제출용 변환.

---

## URL 설계

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/projects/<pk>/submissions/<sub_pk>/draft/` | GET | `submission_draft` | 초안 작업 메인 화면 |
| `/projects/<pk>/submissions/<sub_pk>/draft/generate/` | POST | `draft_generate` | AI 초안 생성 |
| `/projects/<pk>/submissions/<sub_pk>/draft/consultation/` | GET/POST | `draft_consultation` | 상담 내용 입력 |
| `/projects/<pk>/submissions/<sub_pk>/draft/consultation/audio/` | POST | `draft_consultation_audio` | 녹음 파일 업로드 + 딕테이션 |
| `/projects/<pk>/submissions/<sub_pk>/draft/finalize/` | POST | `draft_finalize` | AI 최종 정리 요청 |
| `/projects/<pk>/submissions/<sub_pk>/draft/review/` | GET/POST | `draft_review` | 컨설턴트 검토/수정 |
| `/projects/<pk>/submissions/<sub_pk>/draft/convert/` | POST | `draft_convert` | 제출용 파일 변환 |
| `/projects/<pk>/submissions/<sub_pk>/draft/preview/` | GET | `draft_preview` | 미리보기 |

---

## 모델 추가

### SubmissionDraft (projects 앱)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | UUID | PK |
| `submission` | OneToOne → Submission | 대상 추천 서류 |
| `template` | CharField choices | 양식 (P07의 SubmissionTemplate 재사용) |
| `status` | CharField choices | 파이프라인 진행 상태 |
| `auto_draft_json` | JSONField | AI 초안 구조화 데이터 |
| `auto_corrections` | JSONField | AI 자동 보정 내역 리스트 |
| `consultation_input` | TextField blank | 상담 내용 (직접 입력 텍스트) |
| `consultation_audio` | FileField null | 녹음 파일 |
| `consultation_transcript` | TextField blank | Whisper 딕테이션 결과 |
| `consultation_summary` | JSONField null | AI 정리 결과 (항목별 구조화) |
| `final_content_json` | JSONField null | AI 최종 정리 데이터 |
| `masking_config` | JSONField default | 마스킹 설정 |
| `output_format` | CharField choices | word / pdf |
| `output_language` | CharField choices | ko / en / ko_en |
| `output_file` | FileField null | 생성된 최종 파일 |
| `created_at` / `updated_at` | DateTimeField | 타임스탬프 |

**status choices:**
```python
class DraftStatus(models.TextChoices):
    PENDING = "pending", "대기"
    DRAFT_GENERATED = "draft_generated", "초안 생성됨"
    CONSULTATION_ADDED = "consultation_added", "상담 입력됨"
    FINALIZED = "finalized", "AI 정리 완료"
    REVIEWED = "reviewed", "검토 완료"
    CONVERTED = "converted", "변환 완료"
```

**masking_config 기본값:**
```python
{"salary": True, "birth_detail": True, "contact": True, "current_company": False}
```

---

## 파이프라인 단계

### 1단계: AI 초안 생성

후보자 DB 데이터(Candidate의 parsed_data)를 엑스다임 양식에 자동 매핑.

```
┌─ 추천 서류 작성 ─ 홍길동 ─────────────────────────────┐
│                                                       │
│  양식: [엑스다임 국영문 ▾]   고객사: Rayence            │
│                                                       │
│  [AI 초안 생성]                                        │
│                                                       │
│  ┌─ 초안 미리보기 ─────────────────────────────────┐   │
│  │  ■ 인적사항                                     │   │
│  │    홍길동 (Hong Gil-dong) | 1980년생 | 남        │   │
│  │  ■ 경력 요약                                    │   │
│  │    품질관리 분야 16년 경력 ...                    │   │
│  │  ■ 경력사항                                     │   │
│  │    메디톡스 | 품질부장 | 2019.03 - 현재 (7년)     │   │
│  │                                                 │   │
│  │  ⚠ AI 자동 보정 3건:                            │   │
│  │    · 경력 기간 계산 보정 (6년11개월 → 7년)        │   │
│  │    · 영문명 추가 (Hong Gil-dong)                 │   │
│  │    · 회사 소개 자동 생성 (CompanyProfile 참조)    │   │
│  └─────────────────────────────────────────────────┘   │
│                                                       │
│  [다음: 상담 내용 추가 →]                              │
└───────────────────────────────────────────────────────┘
```

**AI 자동 보정 항목:**
- 오탈자, 문법 교정
- 서식 통일 (날짜 표기: YYYY.MM, 경력 기간 계산)
- 영문명 생성 (국영문/영문 양식)
- 회사 소개 자동 작성 (CompanyProfile 레퍼런스 데이터 활용)
- 자격증 공식 명칭 매칭 (PreferredCert 참조)

### 2단계: 상담 내용 입력

2가지 입력 방식 제공.

**직접 입력:** 이직 사유, 희망/현재 연봉, 입사 가능일, 기타 특이사항 입력 → "AI 정리 → 서류에 반영".

**녹음 파일:** 파일 업로드 → Whisper API 딕테이션 (기존 `candidates/services/whisper.py` 활용) → AI 정리 (항목별 구조화, 불필요한 대화 제거) → 컨설턴트 검토/수정 → 서류 반영.

### 3단계: AI 최종 정리 + 검토

초안 + 상담 내용 병합 → 완성본 미리보기. 각 섹션별 OK/추가됨/자동생성 표시.
컨설턴트가 직접 수정 또는 AI 재정리 요청 가능.

### 4단계: 제출용 변환

포맷(Word/PDF), 언어(국문/국영문/영문), 마스킹(연봉/생년월일/연락처/현 회사명) 선택 후 변환.
변환 후 `output_file`에 저장, Submission의 `document_file`에도 복사.

---

## 서비스 구조

| 파일 | 역할 |
|------|------|
| `projects/services/draft_generator.py` | AI 초안 생성 + 자동 보정 (Gemini API) |
| `projects/services/draft_consultation.py` | 상담 내용 처리 (직접 입력 정리, 녹음 딕테이션 + AI 정리) |
| `projects/services/draft_finalizer.py` | AI 최종 정리 (초안 + 상담 병합) |
| `projects/services/draft_converter.py` | Word/PDF 변환 + 마스킹 처리 |

**외부 의존:**
- Gemini API — 초안 생성, 보정, 정리 (기존 data_extraction 패턴 활용)
- Whisper API — 녹음 딕테이션 (`candidates/services/whisper.py` 재사용)
- python-docx / reportlab — Word/PDF 생성

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| AI 초안 생성 | 후보자 데이터 → auto_draft_json 생성 확인 |
| 자동 보정 | 경력 기간, 영문명, 회사 소개 등 보정 내역 확인 |
| 직접 입력 | 상담 내용 입력 → consultation_input 저장 |
| 녹음 딕테이션 | 오디오 파일 → transcript → summary 생성 |
| AI 최종 정리 | 초안 + 상담 병합 → final_content_json 확인 |
| Word 변환 | .docx 생성 + 마스킹 필드 제거 확인 |
| PDF 변환 | .pdf 생성 + 마스킹 필드 제거 확인 |
| 상태 전환 | pending → draft_generated → ... → converted 순서 |

---

## 산출물

- `projects/models.py` — SubmissionDraft 모델 추가
- `projects/views.py` — Draft 관련 뷰 8개
- `projects/urls.py` — Draft 관련 URL 추가
- `projects/services/draft_generator.py` — AI 초안 생성 + 보정
- `projects/services/draft_consultation.py` — 상담 내용 처리
- `projects/services/draft_finalizer.py` — AI 최종 정리
- `projects/services/draft_converter.py` — Word/PDF 변환 + 마스킹
- `projects/templates/projects/partials/draft_*.html` — 각 단계 템플릿 (4개)
- 테스트 파일
