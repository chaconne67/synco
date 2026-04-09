# 쟁점 판정 결과 파일 포맷

`design-rulings.md` 및 `impl-rulings.md`에 적용되는 표준 포맷.

## 구조

```markdown
# {Design|Implementation} Rulings — {topic}

Status: IN_PROGRESS | COMPLETE
Last updated: {ISO 8601}
Rounds: {N}

## Resolved Items

### Issue {N}: {title} [{SEVERITY}]
- **Resolution:** ACCEPTED | REBUTTED | PARTIAL | USER_DECIDED
- **Summary:** 판정 결론 1-2문장
- **Action:** 확정 문서에 반영할 구체적 변경 내용 (ACCEPTED/PARTIAL인 경우)

## Disputed Items

### Issue {N}: {title} [{SEVERITY}]
- **레드팀:** {레드팀의 현재 주장}
- **저자:** {저자의 현재 반박}
- **Evidence type:** CODE REFERENCE | EXECUTION RESULT | LOGICAL REASONING
- **Round:** {현재 라운드 수}
```

## Resolution 상태값

| 상태 | 의미 |
|------|------|
| `ACCEPTED` | 레드팀 이슈를 수용, 확정 문서에 반영 |
| `REBUTTED` | 저자 반박이 승인됨, 변경 없음 |
| `PARTIAL` | 이슈의 일부만 수용 |
| `USER_DECIDED` | 에스컬레이션 후 사용자가 결정 |

## 완료 조건

모든 항목이 Resolved로 이동하고, Disputed Items가 비어있으면 Status를 `COMPLETE`로 변경한다.