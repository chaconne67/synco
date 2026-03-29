---
name: Auto-orchestration UX principle
description: Users should never press buttons to trigger analysis - system auto-runs needed functions based on context, user sees only finished results
type: feedback
---

Modular backend functions must be auto-orchestrated by the system, not manually triggered by the user.

**Why:** Users want to see final results only. They don't want to understand the process or press buttons to trigger each analysis step. But the program should still be efficient, running only what's needed.

**How to apply:** Use `ensure_*` patterns that check if processing is needed and auto-run. Cheap operations (embedding, sentiment, scoring) run eagerly/proactively. Expensive operations (LLM) run on context entry (e.g., opening a report) with caching. The user never sees "분석 실행" buttons for standard flows.