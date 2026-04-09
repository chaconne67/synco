# 구현담금질 — Round 1 레드팀 프롬프트

## Variables

| Variable | Required | Source |
|----------|----------|--------|
| `{{PROJECT_CONTEXT}}` | Yes | 저자가 CLAUDE.md에서 추출 (Tech Stack, Infrastructure, Conventions) |
| `{{AGREED_DESIGN_SPEC}}` | Yes | 확정 설계서(`design-spec-agreed.md`) 전문 또는 요약 (Context Snapshot Rules 참조) |
| `{{IMPL_PLAN_CONTENT}}` | Yes | 구현계획서 초안(`impl-plan.md`) 전문 |

## Context Snapshot Rules (확정 설계서)

- **200줄 이하**: 확정 설계서 전문 포함
- **200줄 초과**: 핵심 결정 8-15개 bullet 요약 + 구현계획서가 참조하는 섹션 원문 발췌 + `Omitted sections: [list]`
- 항상 포함: `Source: docs/forge/{topic}/design-spec-agreed.md`

## Template

```
IMPORTANT: Do NOT read or execute any files under ~/.claude/, ~/.agents/,
.claude/skills/, or agents/. Stay focused on repository code only.

You are reviewing an IMPLEMENTATION PLAN. This plan will be executed by an AI
coding agent step by step. Your job is to find every issue that would cause
the implementation to fail or produce incorrect results.

PROJECT CONTEXT:
{{PROJECT_CONTEXT}}

Review within this project's constraints.

Review for:
1. Missing or incomplete code in steps (placeholders, TODOs, "implement later")
2. Incorrect file paths or function signatures
3. Steps that depend on state from other steps but don't account for it
4. Missing test cases or inadequate test coverage
5. Steps in wrong order (dependency violations)
6. Code that contradicts the agreed design spec
7. Edge cases not covered by any test
8. Incorrect commands or expected outputs

Do not limit yourself to these categories. Consider project-specific risks.

Also verify that the implementation plan faithfully implements the agreed design spec.

Your findings will be individually challenged by the author with evidence.
Ensure each issue stands on its own with specific, verifiable evidence.

AGREED DESIGN SPEC:
{{AGREED_DESIGN_SPEC}}

NUMBER each issue. For each issue provide:
- SEVERITY: judge by "이 이슈를 무시하고 구현했을 때, 언제 문제가 드러나는가?"
  - CRITICAL: 구현 단계에서 (기능 미동작, 데이터 손실 위험)
  - MAJOR: 운영/부하 상황에서 (성능, 보안, 유지보수성에 심각한 영향)
  - MINOR: 코드 리뷰에서 (개선 기회, 현재 설계로도 동작에 문제 없음)
- DESCRIPTION, EVIDENCE, SUGGESTION for each issue.

THE IMPLEMENTATION PLAN:
{{IMPL_PLAN_CONTENT}}
```