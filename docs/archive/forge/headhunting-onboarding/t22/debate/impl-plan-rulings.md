# impl-plan Rulings — t22

Status: COMPLETE

## Resolved Items

### R1-01: 상단 버튼과 스타일 불일치 [CRITICAL → ACCEPTED]
저자가 수용. 상단 버튼과 동일한 규격(px-3 py-1.5 rounded-lg)으로 통일하도록 변경안을 수정한다.

### R1-02: 좁은 화면/긴 이름 시 레이아웃 붕괴 위험 [CRITICAL → PARTIAL]
검증 단계에 레이아웃 확인 항목(긴 이름, 좁은 viewport, 잠금 해제 공존) 추가 수용. 코드 변경(flex-shrink-0, truncate)은 할일 범위 외로 별도 처리.

### R1-03: 같은 라벨 중복 — 상단/행 버튼 동작 차이 혼란 [MAJOR → REBUTTED]
Round 2에서 레드팀이 저자 반박을 ACCEPT. "+" prefix, 위치 맥락, query param 차이, git 이력으로 기존 디자인 확인. 설계 명세의 범위 제한도 타당.

### R1-04: "잠금 해제" 텍스트 링크와의 시각적 불균형 [MINOR → REBUTTED]
주 행동 vs 파괴적 행동의 의도적 위계 차이. items-center 적용으로 수직 정렬 문제 없음.

### R1-05: 라인 번호 참조 불일치 [MINOR → ACCEPTED]
저자가 수용. 구현계획의 라인 번호를 96-98에서 105-107로 수정한다.
