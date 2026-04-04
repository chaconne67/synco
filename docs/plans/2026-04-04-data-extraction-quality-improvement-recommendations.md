# data_extraction 품질 및 성능 개선 권고안

**일자:** 2026-04-04  
**대상:** `data_extraction` 앱  
**목적:** 현재 `Gemini 3.1 Flash-Lite Preview` 기반 추출 파이프라인의 정확도, 안정성, 운영 효율을 개선한다.  
**범위:** Google Drive 수집, 텍스트 추출, Gemini 구조화 추출, 검증, 배치 처리, 저장/관측성  
**전제:** 종이 문서는 없고, 주요 입력은 한글 이력서이며, 현재 비용 구조는 이미 낮다. 따라서 이번 권고안은 `토큰 절감 자체`보다 `품질/정합성/실패율/검수율 개선`을 우선한다.

---

## 1. 요약

현재 `data_extraction` 앱은 이미 다음 골격을 갖추고 있다.

- Drive 수집: `data_extraction/services/drive.py`
- 텍스트 추출: `data_extraction/services/text.py`
- 단건/무결성 추출: `data_extraction/services/pipeline.py`, `data_extraction/services/extraction/gemini.py`, `data_extraction/services/extraction/integrity.py`
- 규칙 검증: `data_extraction/services/validation.py`
- 배치 처리: `data_extraction/services/batch/prepare.py`, `data_extraction/services/batch/request_builder.py`, `data_extraction/services/batch/ingest.py`
- 저장 및 불일치 리포트: `data_extraction/services/save.py`

구조 자체는 충분히 좋다. 다만 현재 구현은 아래 성격이 강하다.

- 입력 포맷이 사실상 `.doc/.docx`에 치우쳐 있다.
- Gemini 응답을 `자유 JSON 텍스트`로 받아 파싱한다.
- 검증은 존재 여부와 일부 규칙 중심이라, `핵심 필드 우선` 검수 라우팅이 약하다.
- 비용 추적과 실패 원인 분류가 충분히 남지 않는다.
- 배치 샘플 기준으로 문서당 평균 입력 토큰이 이미 크다.

현재 남아 있는 배치 샘플(`.batch_extract/7296afbc-.../requests.jsonl`)을 실측한 결과:

- 평균 입력 토큰: 약 `3,281 tokens / 문서`
- 평균 출력 토큰: 약 `1,344 tokens / 문서`
- 배치 단가 기준 예상 비용: `20만건 약 $284~$302`

즉, 지금 파이프라인은 이미 저비용이다. 따라서 1차 목표는 `전문 파서 도입`이나 `극단적 프롬프트 축소`가 아니라, `실패를 줄이고 검수량을 낮추는 품질 개선`이어야 한다.

---

## 2. 현재 코드 기준 주요 관찰

### A. 입력 포맷 커버리지가 좁다

`data_extraction/services/drive.py`의 `list_files_in_folder()`는 `.doc`와 `.docx` MIME만 수집한다.  
`data_extraction/services/text.py`도 `.doc`, `.docx`만 처리한다.

영향:

- PDF 이력서
- Google Docs 문서
- 일부 HTML/TXT/RTF 기반 이력서

가 있으면 현재 경로에 진입하지 못한다.

### B. 구조화 출력이 모델 프롬프트와 후처리에 과도하게 의존한다

`data_extraction/services/extraction/gemini.py`와 `data_extraction/services/extraction/integrity.py`는 Gemini 응답을 일반 텍스트로 받고, 코드에서 fenced code block 제거 후 `json.loads()`를 수행한다.

영향:

- JSON fence, 설명 문구, key 누락, partial JSON 등 포맷 오류가 여전히 발생할 수 있다.
- 배치 경로(`data_extraction/services/batch/request_builder.py`, `ingest.py`)도 같은 리스크를 공유한다.

### C. 검증은 있으나 "핵심 필드 우선 라우팅"이 약하다

`data_extraction/services/validation.py`는 이름, 출생연도, 날짜 역전, 파일명 교차검증, 일부 필드 confidence를 계산한다.

하지만 실제 운영에서는 필드 중요도가 다르다.

- `name`, `email`, `phone`, `current_company`, `career dates`는 오검출 비용이 크다.
- `summary`, `core_competencies`는 비교적 느슨하게 봐도 된다.

현재는 이런 차등 정책이 충분히 반영돼 있지 않다.

### D. 실패 원인과 비용 관측성이 부족하다

배치 저장 모델과 ingest 경로는 현재 다음을 체계적으로 남기지 않는다.

- 실제 입력/출력 토큰 수
- 문서 길이 이상치
- 짧은 텍스트/깨진 추출 원인
- 어떤 검증 rule 때문에 review로 갔는지에 대한 구조화된 reason code

이 정보가 없으면 `품질 개선`이 감각적 작업이 된다.

### E. 텍스트 추출 이상치가 LLM 단계까지 흘러간다

배치 샘플에 실제로 `resume_text` 길이가 거의 없는 문서가 있었다.  
`data_extraction/services/batch/prepare.py`는 현재 `raw_text.strip()`만 검사하므로, `1~10자` 수준의 비정상 문서도 LLM에 들어갈 수 있다.

---

## 3. 우선순위별 수정 권고

## P0. Gemini Structured Output으로 전환

**우선순위:** 가장 높음  
**효과:** 품질 높음, 구현 난이도 중간, 비용 영향 낮음

### 이유

현재는 JSON 스키마를 프롬프트 본문에 길게 붙이고 자유 텍스트 JSON을 파싱한다.  
Gemini 공식 문서는 `response_mime_type="application/json"`와 `response_json_schema` 기반 structured output을 공식 지원한다.

이 변경은 다음 문제를 직접 줄인다.

- fenced code block 제거 로직 의존
- JSON 파싱 실패
- key 순서/형식 흔들림
- batch ingest 시 텍스트 응답 후처리 복잡도

### 수정 대상

- `data_extraction/services/extraction/gemini.py`
- `data_extraction/services/extraction/integrity.py`
- `data_extraction/services/batch/request_builder.py`
- `data_extraction/services/batch/ingest.py`
- `data_extraction/services/extraction/prompts.py`

### 권장 수정

1. 추출 스키마를 Python dict 또는 Pydantic/JSON Schema 형태로 분리한다.
2. Gemini 호출 시 아래 구성을 사용한다.

```python
config=genai.types.GenerateContentConfig(
    system_instruction=...,
    response_mime_type="application/json",
    response_json_schema=...,
    temperature=0.3,
    max_output_tokens=...,
)
```

3. batch JSONL 생성 시에도 동일하게 `response_mime_type`과 `response_json_schema`를 넣는다.
4. ingest 단계는 fenced text 제거 대신 `response.parts[].text`가 JSON 문자열이라는 가정으로 단순화한다.

### 예상 효과

- JSON 파싱 실패율 감소
- 스키마 이탈 감소
- `validate_extraction()` 이전 단계의 노이즈 감소
- batch 경로와 realtime 경로의 출력 정합성 상승

---

## P0. 문서 길이/품질 게이트 추가

**우선순위:** 가장 높음  
**효과:** 품질 높음, 비용 절감 소폭, 구현 난이도 낮음

### 이유

현재는 텍스트가 `빈 문자열`만 아니면 LLM에 보낸다.  
실제 샘플에는 사실상 무의미한 길이의 텍스트도 존재했다.

이런 문서는 LLM이 잘못된 구조를 만들어내거나, review queue만 늘린다.

### 수정 대상

- `data_extraction/services/text.py`
- `data_extraction/services/batch/prepare.py`
- `data_extraction/services/pipeline.py`
- `data_extraction/services/save.py`

### 권장 수정

1. `extract_text()` 이후 품질 점검 함수를 추가한다.
2. 최소 기준 예시:
   - 한글/영문/숫자 유효 문자 수 최소치
   - 전체 길이 최소치
   - 줄 수 최소치
   - 특정 잡음 패턴만 있는 경우 차단
3. 결과를 아래 유형으로 라우팅한다.
   - `ok`
   - `too_short`
   - `garbled_text`
   - `unsupported_format`
4. `too_short`와 `garbled_text`는 바로 `TEXT_ONLY` 또는 `FAILED`로 저장하고 LLM 호출을 생략한다.

### 예상 효과

- 불필요한 호출 감소
- 허위 JSON 생성 감소
- 사람 검수 큐의 잡음 감소
- 실패 원인 분류 명확화

---

## P0. 핵심 필드 기준 검수 라우팅 재설계

**우선순위:** 가장 높음  
**효과:** 품질 높음, 운영 효율 높음, 구현 난이도 중간

### 이유

현재 `data_extraction/services/validation.py`의 점수는 필드 중요도 차이를 충분히 반영하지 않는다.  
실제 운영에선 아래 필드가 핵심이다.

- 이름
- 이메일
- 전화번호
- 현재 회사/직위
- 경력 시작/종료일

이 필드가 불확실하면 `summary`가 좋아도 자동 통과시키면 안 된다.

### 수정 대상

- `data_extraction/services/validation.py`
- `data_extraction/services/pipeline.py`
- `data_extraction/services/save.py`

### 권장 수정

1. 필드별 점수를 `critical`, `important`, `secondary` 세 그룹으로 나눈다.
2. 자동 통과 조건을 전체 평균 하나가 아니라 `게이트 방식`으로 바꾼다.

예시:

- `critical` 필드 중 하나라도 `0.8 미만`이면 `needs_review`
- `critical` 모두 통과 + 전체 점수 `0.85 이상`이면 `auto_confirmed`
- `date_confidence`가 낮거나 날짜 역전/중복이 있으면 자동 review

3. `issues`에 free-text만 저장하지 말고 `rule_code`를 추가한다.

예시:

- `missing_name`
- `invalid_email`
- `phone_too_short`
- `career_date_reversed`
- `filename_name_mismatch`

### 예상 효과

- 자동 통과 품질 상승
- 잘못된 후보자 저장 감소
- 검수 UI에서 이유별 필터링 가능

---

## P1. Drive 수집 계층을 MIME 라우터 + 증분 동기화 구조로 확장

**우선순위:** 높음  
**효과:** 성능/운영 안정성 높음, 구현 난이도 중간

### 이유

현재 `drive.py`는 `.doc/.docx` 중심이며, full scan 성격이 강하다.  
리서치 기준으로 Google Drive 대량 처리의 정석은 `files.list` + `changes` 기반 증분 추적이다.

또 Google Docs 문서는 일반 download가 아니라 `files.export`가 필요하다.

### 수정 대상

- `data_extraction/services/drive.py`
- `data_extraction/services/batch/prepare.py`
- `data_extraction/management/commands/extract.py`

### 권장 수정

1. 수집 대상 MIME을 확장한다.
   - MS Word
   - DOCX
   - PDF
   - Google Docs
2. `mime_type -> download/extract strategy` 라우터를 도입한다.
3. Google Docs는 `files.export` 경로를 추가한다.
4. shared drive를 쓰는 경우 `supportsAllDrives`와 관련 옵션을 명시적으로 반영한다.
5. 장기적으로는 `startPageToken` 기반 변경분 동기화 기능을 추가한다.

### 예상 효과

- 입력 커버리지 향상
- full rescan 비용 절감
- 운영 시 재처리 시간 단축

### 주의

Google Docs export는 공식 문서상 `10MB 제한`이 있다. 큰 문서는 예외 처리와 fallback 전략이 필요하다.

---

## P1. 템플릿/문서 유형 분류 단계를 추출 앞단에 추가

**우선순위:** 높음  
**효과:** 품질 중~높음, 구현 난이도 중간

### 이유

리서치에서 반복적으로 보인 패턴은 `분류 후 추출`이다.  
모든 문서에 동일 프롬프트를 적용하면 긴 이력서, 경력기술서형, 국/영문 혼합형, 표 중심형에서 누락 패턴이 반복된다.

### 수정 대상

- `data_extraction/services/pipeline.py`
- `data_extraction/services/extraction/prompts.py`
- `data_extraction/services/batch/request_builder.py`

### 권장 수정

1. lightweight classifier를 추가한다.
   - `resume`
   - `career_description_heavy`
   - `mixed_ko_en`
   - `table_heavy`
   - `sparse_short`
2. classifier는 처음부터 LLM으로 갈 필요는 없다.
   - 파일명
   - MIME
   - 텍스트 길이
   - 영어 비율
   - 표/탭 비율
   - 날짜 패턴 밀도
3. 유형별로 아래를 바꾼다.
   - prompt variant
   - max_output_tokens
   - validation strictness

### 예상 효과

- 특정 템플릿군에서 반복 누락 감소
- 긴 문서에서 불필요한 설명 축소
- 짧은 문서에서 환각 감소

---

## P1. 현재 프롬프트를 "짧은 지시 + 외부 스키마"로 재구성

**우선순위:** 높음  
**효과:** 품질 중간, 비용 절감 소폭, 구현 난이도 낮음

### 이유

현재 `data_extraction/services/extraction/prompts.py`는 장문의 JSON 스키마와 설명을 매 요청마다 본문에 넣는다.  
실측 샘플 기준 평균 입력 토큰은 이미 `3,281 tokens / 문서`다.

입력비는 낮아서 비용 절감폭 자체는 크지 않다.  
하지만 프롬프트가 길수록 다음 리스크가 생긴다.

- 모델 주의 집중 분산
- 긴 문서에서 context 낭비
- batch 파일 크기 증가

### 수정 대상

- `data_extraction/services/extraction/prompts.py`
- `data_extraction/services/extraction/gemini.py`
- `data_extraction/services/batch/request_builder.py`

### 권장 수정

1. 필드 설명은 JSON schema `description`으로 이동한다.
2. user prompt에는 아래만 남긴다.
   - 문서 성격
   - 누락 금지 원칙
   - 원문 근거 우선 원칙
3. 출력 형식 강제는 prompt가 아니라 structured output 설정으로 옮긴다.

### 예상 효과

- 프롬프트 안정성 향상
- 긴 문서에서 입력 context 여유 확보
- 향후 스키마 변경 시 유지보수 쉬움

### 비용 참고

입력 토큰 25% 절감이 되더라도 현재 배치 단가 기준 절감액은 크지 않다.  
따라서 이 항목은 `비용 최적화`보다 `출력 안정화` 목적으로 보는 것이 맞다.

---

## P1. 배치 결과에 토큰/비용/실패 원인 메타데이터 저장

**우선순위:** 높음  
**효과:** 운영 품질 높음, 구현 난이도 낮음

### 이유

현재는 실제 비용과 이상치 문서를 배치 후 정교하게 분석하기 어렵다.  
운영 관점에서는 품질 개선보다 먼저 `측정 가능성`을 확보해야 한다.

### 수정 대상

- `batch_extract/models.py`
- `data_extraction/services/batch/ingest.py`
- `data_extraction/services/save.py`

### 권장 수정

1. `GeminiBatchItem.metadata`에 아래 값을 저장한다.
   - `prompt_token_count`
   - `candidate_token_count`
   - `total_token_count`
   - `response_chars`
   - `raw_text_chars`
2. ingest 시 `usage_metadata`가 응답에 있으면 파싱한다.
3. 실패 시 `error_type`을 구조화해서 저장한다.

예시:

- `json_parse_failure`
- `schema_validation_failure`
- `empty_text`
- `drive_download_failure`
- `unsupported_mime`

### 예상 효과

- 실제 문서당 비용 추적 가능
- 고비용/저품질 문서군 식별 가능
- 폴더/업종별 품질 비교 가능

---

## P2. 스크립트 선추출 + LLM 보완 구조로 조정

**우선순위:** 중간  
**효과:** 품질 중간, 구현 난이도 중간

### 이유

이메일, 전화번호, URL, 일부 날짜 패턴은 현재도 규칙 기반으로 다룰 수 있다.  
이 필드는 LLM이 새로 창작할수록 오히려 불안정하다.

### 수정 대상

- `data_extraction/services/text.py`
- `data_extraction/services/filters.py`
- `data_extraction/services/extraction/prompts.py`
- `data_extraction/services/validation.py`

### 권장 수정

1. 전처리 단계에서 `email`, `phone`, `url`, `LinkedIn/GitHub/blog`, `date candidates`를 선추출한다.
2. 이를 prompt metadata로 주되, "원문과 다르면 수정하지 말라"는 조건을 둔다.
3. LLM 결과와 regex 결과가 다르면 validation issue를 남긴다.

### 예상 효과

- 연락처 필드 안정성 상승
- 핵심 식별 필드의 자동 통과율 개선

---

## P2. 근거 데이터 저장 강화

**우선순위:** 중간  
**효과:** 품질 중간, 검수 UX 높음, 구현 난이도 중간

### 이유

현재 스키마에는 `date_evidence`, `resume_reference_date_evidence`, integrity `source_section` 정도만 있다.  
검수와 디버깅을 쉽게 하려면 핵심 필드별 근거가 더 필요하다.

### 수정 대상

- `data_extraction/services/extraction/prompts.py`
- `data_extraction/services/extraction/integrity.py`
- `data_extraction/services/save.py`
- 관련 모델 또는 JSON 필드

### 권장 수정

핵심 필드에 대해 아래 구조를 추가 저장한다.

```json
{
  "field": "current_company",
  "value": "삼성전자",
  "evidence": "2022.03 ~ 현재 / 삼성전자 / 반도체사업부",
  "source_section": "경력사항"
}
```

### 예상 효과

- 사람 검수 시간 단축
- 오탐 원인 파악 속도 향상

---

## 4. 구체적 구현 순서

아래 순서로 가는 것이 안전하다.

1. Structured output 도입
2. 짧은 텍스트/깨진 텍스트 게이트 추가
3. 핵심 필드 중심 validation gate 재설계
4. batch 메타데이터에 토큰/실패 원인 저장
5. Drive MIME 라우터 확장
6. 문서 유형 classifier 추가
7. 선추출/근거 저장 강화

이 순서를 추천하는 이유는 간단하다.

- 1~4는 현재 아키텍처를 깨지 않고 들어간다.
- 5~7은 입력 커버리지와 품질을 더 높이지만, 변경 범위가 더 넓다.

---

## 5. 권장하지 않는 방향

### A. 지금 단계에서 전문 파서로 전면 교체

현재 배치 비용이 이미 매우 낮다.  
전문 파서는 특정 정형 필드 품질은 좋아질 수 있지만, 공개 가격 기준으로는 현재 비용 구조보다 비싸질 가능성이 높다.

따라서 전면 교체보다 다음이 낫다.

- 현재 Gemini 파이프라인 개선
- 필요 시 특정 폴더/업종에서만 전문 파서 PoC

### B. 프롬프트 축소만으로 품질 문제를 해결하려는 접근

프롬프트 축소는 보조 수단이지 핵심 해결책이 아니다.  
현재 문제의 핵심은 `출력 형식 보장`, `검증 라우팅`, `입력 품질 게이트`, `관측성`이다.

### C. OCR 중심 설계

이번 전제는 종이 문서가 없다는 것이다.  
따라서 1차 개선 우선순위는 OCR이 아니라:

- MIME 커버리지
- Google Docs export
- PDF 텍스트 처리
- structured output

이다.

---

## 6. 성공 지표

수정 이후 아래 지표를 추적해야 한다.

- JSON 파싱 실패율
- 문서당 평균 입력 토큰
- 문서당 평균 출력 토큰
- 자동 통과율
- `needs_review` 비율
- `critical field` 오류율
- 짧은 텍스트 차단율
- 폴더별 성공률
- 문서 유형별 성공률

권장 대시보드 축:

- `folder`
- `mime_type`
- `doc_variant`
- `validation_status`
- `error_type`
- `model_name`
- `schema_version`

---

## 7. 참고 코드 위치

- `data_extraction/services/drive.py`
- `data_extraction/services/text.py`
- `data_extraction/services/pipeline.py`
- `data_extraction/services/validation.py`
- `data_extraction/services/save.py`
- `data_extraction/services/extraction/gemini.py`
- `data_extraction/services/extraction/integrity.py`
- `data_extraction/services/extraction/prompts.py`
- `data_extraction/services/batch/request_builder.py`
- `data_extraction/services/batch/prepare.py`
- `data_extraction/services/batch/ingest.py`
- `batch_extract/models.py`

---

## 8. 참고 자료

- Gemini Structured Output: https://ai.google.dev/gemini-api/docs/structured-output
- Gemini Batch API: https://ai.google.dev/gemini-api/docs/batch-api
- Gemini 3 Developer Guide: https://ai.google.dev/gemini-api/docs/gemini-3
- Gemini Pricing: https://ai.google.dev/gemini-api/docs/pricing
- Google Drive changes: https://developers.google.com/workspace/drive/api/guides/manage-changes
- Google Drive changes overview: https://developers.google.com/workspace/drive/api/guides/change-overview
- Google Drive downloads and export: https://developers.google.com/workspace/drive/api/guides/manage-downloads

---

## 9. 최종 권고

현재 `data_extraction` 앱은 버릴 단계가 아니라 `정교화할 단계`다.

가장 큰 개선 효과는 다음 세 가지에서 나온다.

1. `structured output`으로 JSON 품질을 강제한다.
2. `핵심 필드 우선 검증`으로 자동 통과 기준을 현실화한다.
3. `입력 품질 게이트 + 배치 관측성`으로 실패를 줄이고 원인을 보이게 만든다.

이 세 가지를 먼저 적용하면, 전문 파서 없이도 현재 구조의 정확도와 운영 안정성을 꽤 끌어올릴 수 있다.
