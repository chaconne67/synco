---
name: Task UX fundamental issues
description: Dashboard "오늘의 업무" section has fundamental product problems - task data is raw memo text, no detail view, no meaningful classification
type: feedback
---

대시보드 "오늘의 업무" 섹션이 투두리스트로서 기능하지 않음.

**Why:**
1. Task title에 사업자번호+이름+전화번호+메모 원문이 통째로 들어감 (ai_extracted)
2. 카드를 클릭해도 상세 페이지가 없음 — 사용자는 카드를 누르면 뭔가 나올거라 기대
3. due_date가 전부 None — "오늘의 업무" 분류 기준이 없음
4. 체크 완료 동그라미의 의미를 사용자가 직관적으로 알 수 없었음

**How to apply:**
- Task 생성 시 title은 액션 가능한 한 줄 요약 ("진현태 대표 팔로업 전화"), raw 데이터는 별도 description 필드
- 카드 클릭 → 연락처 상세로 이동하거나 업무 상세 확장
- due_date 기반으로 오늘/이번주/밀린 업무 분류
- AI 추출 시 "다음주 통화", "자료 놓고 가라" 같은 액션을 파싱해서 title로 사용