# data_extraction 품질 및 성능 개선 권고안

**일자:** 2026-04-05  
**대상:** `data_extraction` 앱  
**목적:** 현재 코드 상태를 다시 반영해, 이미 반영된 개선과 아직 남은 개선을 구분하고 우선순위를 재정렬한다.  
**전제:** 종이 문서는 없고, 주요 입력은 한글 이력서이며, 현재 비용 구조는 낮다. 따라서 이번 권고안은 `토큰 절감 자체`보다 `정확도`, `정합성`, `운영 안정성`, `검수 효율` 개선을 우선한다.

---

## 1. 현재 상태 요약

현재 `data_extraction` 앱은 초기 버전과 비교해 꽤 많이 정리되어 있다.

- 추출 진입점은 `data_extraction/services/pipeline.py`
- 기본 추출은 `data_extraction/services/extraction/gemini.py`
- 무결성 경로는 `data_extraction/services/extraction/integrity.py`
- 규칙 검증은 `data_extraction/services/validation.py`
- 저장은 `data_extraction/services/save.py`
- 배치 준비/요청/적재는 `data_extraction/services/batch/*.py`

이전 점검 대비 이미 좋아진 점이 분명하다.

- `skills`, `personal_etc`, `education_etc`, `career_etc`, `skills_etc`가 프롬프트/저장 경로에 반영되어 있다.
- validation은 단순 필드 평균이 아니라 `인적사항/학력/경력/능력` 카테고리 점수 기반으로 계산된다.
- 저장 단계에서 `resume_reference_date_evidence`, `date_evidence`, `date_confidence`, integrity alerts merge가 반영되어 있다.
- 저장 단계는 기존 후보자 재사용을 위한 `build_candidate_comparison_context()`를 사용한다.

즉, 이 문서는 더 이상 “무에서 설계” 문서가 아니라, `현재 구현을 기준으로 남은 품질 개선 과제`를 정리하는 문서다.

---

## 2. 현재 코드에서 이미 반영된 개선

## A. 스키마 확장과 저장 정책 정리가 이미 진행됨

아래 항목은 이미 구현되어 있다.

- `skills`, `*_etc` 필드가 프롬프트에 포함됨: `data_extraction/services/extraction/prompts.py`
- `skills`와 `*_etc`가 저장됨: `data_extraction/services/save.py`
- legacy JSON 필드 일부는 비우고 새 `*_etc`로 이관하는 정책이 적용됨: `data_extraction/services/save.py`

의미:

- “원본 이력서에 있는 정보를 어디엔가 보존해야 한다”는 방향은 이미 코드에 반영되었다.
- 따라서 이제 남은 일은 스키마 추가가 아니라 `이 필드들의 추출 품질과 검수 기준을 높이는 것`이다.

## B. validation이 카테고리 점수 기반으로 바뀜

`data_extraction/services/validation.py`는 현재 다음 구조를 가진다.

- 개별 field score 계산
- `인적사항/학력/경력/능력` 카테고리 점수 계산
- 카테고리 평균 + issue penalty로 `validation_status` 산출

이전 문서에서 “카테고리 점수 기반으로 바꾸자”라고 적어둔 내용은 이미 상당 부분 반영되었다.

다만 아직 부족한 점은 남아 있다.

- `critical field gate`가 없다.
- `rule_code`가 없다.
- `needs_review`로 가는 이유를 구조적으로 분석하기 어렵다.

즉, 현 상태는 “단순 존재 점수”보다 좋아졌지만, 아직 `핵심 필드 우선 라우팅` 수준까지는 아니다.

## C. 근거 데이터 저장이 부분적으로 반영됨

현재 저장 경로에는 이미 다음이 있다.

- `resume_reference_date_source`
- `resume_reference_date_evidence`
- 경력별 `date_evidence`
- 경력별 `date_confidence`
- integrity alert의 `evidence`, `reasoning`

이전 문서의 “근거 데이터 저장 강화”는 일부 완료된 상태다.  
남은 과제는 `핵심 필드 전반`으로 확장하는 것이다.

## D. integrity 리포트와 rule-based 리포트는 단일 리포트로 병합됨

`data_extraction/services/save.py`는 integrity alerts와 rule-based discrepancy alerts를 합쳐 단일 `DiscrepancyReport`를 만든다.

이건 이전 점검에서 지적됐던 “integrity 결과가 뒤 리포트에 묻히는 문제”를 줄이는 방향의 개선이다.

---

## 3. 현재 코드 기준 핵심 한계

## A. 입력 포맷 커버리지는 여전히 좁다

현재 상태:

- `data_extraction/services/drive.py`는 실제 수집을 `.doc` / `.docx` MIME에 한정한다.
- `data_extraction/services/text.py`도 실제 텍스트 추출은 `.doc`, `.docx`만 지원한다.
- 반면 `data_extraction/services/filename.py`는 `.pdf`, `.hwp` 확장자까지 알고 있다.

즉, 파일명 파서와 실제 추출 파이프라인의 커버리지가 어긋나 있다.

영향:

- PDF/HWP 파일은 그룹핑/파일명 파싱 관점에서는 고려되지만, 실제 본문 추출 경로에는 올라오지 못한다.
- “지원하는 것처럼 보이지만 실제로는 수집되지 않는 포맷”이 존재한다.

이 항목은 현재도 높은 우선순위다.

## B. Gemini 출력은 아직 자유 JSON 파싱 방식이다

현재 `data_extraction/services/extraction/gemini.py`와 `data_extraction/services/extraction/integrity.py`는 모두:

- 일반 텍스트 응답 수신
- fenced code block 제거
- `json.loads()` 수동 파싱

방식을 쓴다.

배치 경로도 동일하다.

- 요청 생성: `data_extraction/services/batch/request_builder.py`
- 결과 파싱: `data_extraction/services/batch/ingest.py`

의미:

- structured output이 아직 도입되지 않았다.
- JSON 파싱 실패, fence 포함, key 누락 같은 문제는 여전히 남아 있다.

이 항목은 지금도 `P0`다.

## C. 짧거나 깨진 텍스트를 막는 품질 게이트가 아직 없다

현재 `data_extraction/services/batch/prepare.py`는 `raw_text.strip()`만 확인한다.

즉:

- 문자 수가 거의 없는 문서
- 깨진 텍스트
- 의미 없는 헤더만 남은 문서

도 빈 문자열만 아니면 LLM에 들어갈 수 있다.

실제 배치 샘플에도 극단적으로 짧은 텍스트가 섞여 있었다.

이 문제는 비용보다 품질 리스크가 더 크다.

## D. validation이 좋아졌지만 아직 `critical field gate`는 없다

현재 validation은 카테고리 점수 기반이지만, 아래처럼 강제 게이트는 없다.

- 이름 미존재면 무조건 review
- 이메일/전화 중 하나라도 형식 이상이면 auto_confirmed 금지
- 현재 회사/직위/경력 날짜 불확실 시 무조건 review

현재 방식은 평균 기반이라, 핵심 필드 하나가 약해도 다른 점수가 보완할 수 있다.

실무 운영에서는 이게 위험하다.

## E. 비용/토큰/실패 유형 관측성이 아직 부족하다

현재 `GeminiBatchItem.metadata`에 토큰 사용량이 자동 저장되지 않는다.

아직 없는 것:

- `prompt_token_count`
- `candidate_token_count`
- `total_token_count`
- `response_chars`
- `raw_text_chars`
- `error_type`

따라서 다음 질문에 답하기 어렵다.

- 어떤 폴더가 비싼가
- 어떤 템플릿이 실패가 많은가
- 어떤 문서군이 review를 많이 유발하는가

## F. 프롬프트가 길고 반복적이다

현재 `data_extraction/services/extraction/prompts.py`는 다음이 모두 포함된 긴 형태다.

- 장문의 규칙
- 긴 JSON 스키마
- skills 규칙
- etc 규칙
- 번역 규칙

이 방식은 설명력은 좋지만 다음 비용이 있다.

- 입력 토큰 증가
- 긴 문서에서 context 여유 감소
- batch payload 크기 증가

다만 현재 비용 구조가 낮기 때문에, 이건 “비용 절감”보다 `출력 안정성` 관점에서 다뤄야 한다.

## G. 현재 실제 LLM 호출 수는 경로별로 다르다

이 항목은 비용 문서화에 중요하다.

### 기본/배치 경로

- 추출: 1회
- 검증: 코드 기반

즉, 현재 `data_extraction` 기본 batch 경로는 `문서당 1회 LLM`이다.

### integrity 경로

보통 아래 호출이 발생한다.

1. Step 1 faithful extraction
2. Step 1 warning 시 재추출 가능
3. career normalization
4. career normalization retry 가능
5. education normalization

즉, integrity 경로는 문서당 `3~5회`까지 갈 수 있다.

따라서 비용 문서화는 반드시 경로별로 분리해야 한다.

---

## 4. 비용 관련 현재 기준 정리

남아 있는 batch request 샘플 기준 실측치는 다음과 같다.

- 기본 추출 1회 기준:
  - 평균 입력 약 `3,281 tokens / 문서`
  - 평균 출력 약 `1,344 tokens / 문서`
  - 20만건 약 `$284`

여기서 `추출 + 품질용 LLM 검증` 2회 구조를 가정하면:

- 동일 규모 2회: 20만건 약 `$567`
- 좀 더 현실적인 `검증 프롬프트는 작고 출력도 짧다` 가정: 20만건 약 `$420~$460`

즉, 현재 문서에 비용을 적을 때는 아래처럼 써야 정확하다.

- `기본 batch 경로`: 약 `$300 전후`
- `추출 + LLM 검증 2회`: 약 `$420~$570`
- `integrity 3~5회`: 그보다 더 높음

이 문서의 남은 개선안은 이 비용 구조를 전제로 판단해야 한다.

---

## 5. 현재 기준 우선순위

## P0. Gemini Structured Output 도입

**상태:** 아직 미구현  
**이유:** 현재 가장 직접적으로 JSON 품질을 올릴 수 있는 항목

### 수정 대상

- `data_extraction/services/extraction/gemini.py`
- `data_extraction/services/extraction/integrity.py`
- `data_extraction/services/batch/request_builder.py`
- `data_extraction/services/batch/ingest.py`

### 권장 방향

- `response_mime_type="application/json"`
- `response_json_schema=...`

를 사용해 추출과 정규화 응답을 스키마 강제형으로 바꾼다.

### 기대 효과

- JSON 파싱 실패 감소
- fenced code block 후처리 제거 가능
- batch/realtime 경로 정합성 향상

## P0. 텍스트 품질 게이트 도입

**상태:** 아직 미구현  
**이유:** 짧은 텍스트와 깨진 텍스트가 LLM으로 넘어가는 것을 막아야 함

### 수정 대상

- `data_extraction/services/text.py`
- `data_extraction/services/batch/prepare.py`
- `data_extraction/services/pipeline.py`

### 권장 방향

`extract_text()` 이후 아래 분류를 추가한다.

- `ok`
- `too_short`
- `garbled_text`
- `unsupported_format`

`too_short`, `garbled_text`는 `TEXT_ONLY` 또는 `FAILED`로 라우팅하고 LLM 호출을 생략한다.

## P0. critical field gate 추가

**상태:** 부분 반영, 아직 미완성  
**이유:** 카테고리 평균만으로는 핵심 필드 위험을 충분히 막지 못함

### 수정 대상

- `data_extraction/services/validation.py`
- `data_extraction/services/pipeline.py`
- `data_extraction/services/save.py`

### 권장 방향

아래 필드는 평균 점수와 별도로 게이트한다.

- `name`
- `email`
- `phone`
- `current_company`
- `current_position`
- `careers`

예시:

- `name == 0.0` 이면 무조건 `failed`
- `email < 1.0` 또는 `phone < 1.0`이면 자동 통과 금지
- 경력 날짜 역전/낮은 `date_confidence`가 있으면 `needs_review`

## P1. batch 관측성 강화

**상태:** 아직 미구현  
**이유:** 비용/실패 분석을 위해 반드시 필요

### 수정 대상

- `batch_extract/models.py`
- `data_extraction/services/batch/ingest.py`

### 권장 방향

`GeminiBatchItem.metadata`에 저장:

- `prompt_token_count`
- `candidate_token_count`
- `total_token_count`
- `response_chars`
- `raw_text_chars`
- `error_type`

또한 `ValidationDiagnosis.issues`와 별도로 machine-friendly한 `rule_code`를 도입하는 것이 좋다.

## P1. Drive MIME 확장과 다운로드 전략 분리

**상태:** 아직 미구현  
**이유:** filename 파서와 실제 추출 커버리지를 맞춰야 함

### 수정 대상

- `data_extraction/services/drive.py`
- `data_extraction/services/text.py`
- `data_extraction/services/batch/prepare.py`
- `data_extraction/management/commands/extract.py`

### 권장 방향

- 수집 MIME 확장: PDF, Google Docs
- `mime_type -> extract strategy` 분기
- 장기적으로 Google Drive changes API 기반 증분 동기화

현재는 `filename.py`가 `.pdf`, `.hwp`를 알고 있어도 실제 수집/본문 추출은 따라가지 못한다.

## P1. 프롬프트 슬림화

**상태:** 아직 미구현  
**이유:** 이미 스키마가 커졌고 설명도 많아졌기 때문에 유지보수와 안정성 관점에서 필요

### 수정 대상

- `data_extraction/services/extraction/prompts.py`
- `data_extraction/services/extraction/gemini.py`
- `data_extraction/services/batch/request_builder.py`

### 권장 방향

- 긴 JSON 스키마와 장문 규칙을 매 호출 본문에 직접 넣는 방식을 줄인다.
- structured output 도입 후에는 prompt를 `원칙 중심`으로 줄인다.

## P2. 템플릿/문서 유형 classifier 추가

**상태:** 아직 미구현  
**이유:** 표 중심 문서, 국영문 혼합 문서, 짧은 문서의 실패 패턴을 줄이기 위해 유효

### 수정 대상

- `data_extraction/services/pipeline.py`
- `data_extraction/services/extraction/prompts.py`
- `data_extraction/services/batch/request_builder.py`

### 권장 방향

LLM classifier가 아니라 lightweight rule classifier부터 시작한다.

- `mixed_ko_en`
- `table_heavy`
- `sparse_short`
- `career_heavy`

유형별로 prompt, max tokens, validation strictness를 다르게 적용한다.

## P2. 근거 데이터 저장 확장

**상태:** 일부 반영, 아직 미완성  
**이유:** 현재는 날짜 계열 중심이며 핵심 필드 전반의 증거 저장은 부족함

### 수정 대상

- `data_extraction/services/extraction/prompts.py`
- `data_extraction/services/save.py`
- 필요 시 모델/JSON 구조

### 권장 방향

핵심 필드에 대해 아래 구조를 추가 저장한다.

```json
{
  "field": "current_company",
  "value": "삼성전자",
  "evidence": "2022.03 ~ 현재 / 삼성전자 / 반도체사업부",
  "source_section": "경력사항"
}
```

---

## 6. 지금 단계에서 하지 않아도 되는 것

## A. 전문 파서 전면 교체

현재 비용 구조상 전면 교체는 우선순위가 아니다.

- 기본 batch 경로는 이미 저비용
- 지금 더 급한 건 JSON 안정성, 입력 품질 게이트, 관측성

전문 파서는 특정 폴더/직군 PoC로만 제한하는 것이 맞다.

## B. OCR 중심 투자

종이 문서가 없으므로 OCR은 현재 우선순위가 낮다.

더 급한 건:

- MIME 커버리지
- structured output
- validation gate
- batch observability

---

## 7. 성공 지표

현재 코드 상태를 기준으로 보면 아래 지표가 핵심이다.

- JSON 파싱 실패율
- 짧은/깨진 텍스트 차단율
- `auto_confirmed` 비율
- `needs_review` 비율
- 핵심 필드 오류율
- 문서당 평균 입력 토큰
- 문서당 평균 출력 토큰
- 문서 유형별 실패율
- 폴더별 실패율
- batch item별 `error_type` 분포

권장 대시보드 축:

- `folder`
- `mime_type`
- `validation_status`
- `error_type`
- `model_name`
- `schema_version`
- `integrity_mode`

---

## 8. 최종 권고

현재 `data_extraction`은 “기초 구조를 세우는 단계”는 이미 지나갔다.  
지금은 `출력 형식 강제`, `핵심 필드 우선 검수`, `입력 품질 게이트`, `비용/실패 관측성`을 붙여서 운영 품질을 끌어올릴 단계다.

가장 먼저 할 일은 다음 네 가지다.

1. Gemini structured output 도입
2. 텍스트 품질 게이트 추가
3. critical field gate 추가
4. batch 토큰/실패 유형 메타데이터 저장

이 네 가지가 들어가면, 지금 이미 구현된 `skills/ETC 확장`, `카테고리 점수 validation`, `integrity merge`, `후보자 재사용 저장`의 가치가 훨씬 더 커진다.
