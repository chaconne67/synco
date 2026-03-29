---
name: User journey continuity principle
description: User action must produce immediate feedback AND pre-populate all downstream screens - no "분석 중" after navigation
type: feedback
---

Every user action must deliver immediate feedback, and the results must be ready everywhere the user might go next.

**Why:** Users upload data expecting AI value. If they upload, see "done", then navigate to dashboard and find empty/loading states, the experience breaks. The whole point of an AI assistant is that it processes data and delivers value without the user having to manage the process.

**How to apply:** When designing data processing pipelines (like Excel import), ensure ALL cheap analysis (embedding, sentiment, scoring) completes BEFORE returning the success response. The import completion screen should show the analysis summary ("골드 12명, 주의 8명"). After that, dashboard/contact list/detail views must reflect those results immediately with no additional loading.