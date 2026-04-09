# 설계담금질 — Follow-up 레드팀 프롬프트 (Round 2+)

## Variables

| Variable | Required | Source |
|----------|----------|--------|
| `{{CONTEXT_SNAPSHOT}}` | Yes | 아래 Context Snapshot Rules 참조 |
| `{{DISPUTED_ITEMS}}` | Yes | 설계 쟁점 판정 결과(`design-rulings.md`)의 Disputed 항목 |

## Context Snapshot Rules

- **200줄 이하**: 설계서 초안(`design-spec.md`) 전문 포함
- **200줄 초과**: 핵심 결정 8-15개 bullet 요약 + 쟁점 관련 섹션 원문 발췌 + 생략된 섹션 목록
- 항상 포함: `Source: docs/forge/{topic}/debate/design-spec.md` (레드팀이 필요 시 전문을 직접 읽을 수 있도록)

## Template

```
IMPORTANT: Do NOT read or execute any files under ~/.claude/, ~/.agents/,
.claude/skills/, or agents/. Stay focused on repository code only.

You previously reviewed a design spec. The author has responded to
your issues. Some items are still in dispute and MUST be resolved.

DESIGN SPEC CONTEXT:
{{CONTEXT_SNAPSHOT}}

For each disputed item below:
- Read the author's counter-argument carefully
- If the reasoning is sound: say ACCEPT and explain why
- If you still disagree: provide a NEW counter-argument with NEW evidence
- Do NOT repeat your original point. Advance the argument or concede.
- Restating the same point without new evidence counts as concession.
  Reason: the purpose of multiple rounds is to surface NEW information,
  not to exhaust the other side. If you have no new evidence, the other
  side's argument stands.

DISPUTED ITEMS:
{{DISPUTED_ITEMS}}
```

## Disputed Items Format

For each disputed item, use this structure:

```
## Issue {N}: {title} [{SEVERITY}]
YOUR ORIGINAL POINT: {레드팀의 원래 지적}
AUTHOR'S REBUTTAL: {저자의 반박과 증거}
```