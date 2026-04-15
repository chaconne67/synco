# t11 Implementation Rulings

**Status:** COMPLETE
**Rounds:** 1
**Date:** 2026-04-12

---

## Accepted Items

### I-R1-02: JSONField 스키마 유효성 검증 부재 [MAJOR — PARTIAL ACCEPT]
- **Resolution:** 모델에 `clean()` 메서드 추가. `NOTIFICATION_TYPES`와 `CHANNELS` 상수 정의 후 최상위 key 존재 + boolean 타입 검증.
- **Scope:** 전체 REQUIRED_SCHEMA 중첩 순회는 과잉이므로, 간단한 검증만 적용.

### I-R1-03: Admin 등록 검증 누락 [MINOR — ACCEPT]
- **Resolution:** `admin.site._registry` 확인 테스트 1건 추가.

### I-R1-04: OneToOne 제약 테스트 범위 과도 [MINOR — ACCEPT]
- **Resolution:** `pytest.raises(Exception)` → `pytest.raises(IntegrityError)` 변경.

### I-R1-05: 기본값 중복 하드코딩 [MINOR — ACCEPT]
- **Resolution:** 모델에서 기본값 함수를 공개하고, 테스트에서 import하여 사용.

---

## Rebutted Items

### I-R1-01: 기존 사용자 데이터 마이그레이션 누락 [CRITICAL → MINOR]
- **Rebuttal:** 후속 t13에서 `get_or_create` 패턴 확정 (code_reference: t13/impl-plan.md:224). t11 배포 시점에 접근 코드 없음. `RelatedObjectDoesNotExist` 시나리오 성립하지 않음.
- **Concession:** 구현계획서에 lazy creation NOTE 추가하여 명시.

### I-R1-06: JSONField GinIndex 미적용 [MAJOR → DISMISSED]
- **Rebuttal:** 현재 내부 키 필터링 쿼리 없음. B2B 헤드헌팅 플랫폼 사용자 수 수백~수천 규모. YAGNI — 필요 시 migration 하나로 추가 가능.

### I-R1-07: 문서 내부 불일치 [MINOR → DISMISSED]
- **Rebuttal:** 원본 impl-plan.md에 `default=dict` 구문 없음. Gemini가 별도 문서(phase2 전체 계획서)를 혼동. False positive.
