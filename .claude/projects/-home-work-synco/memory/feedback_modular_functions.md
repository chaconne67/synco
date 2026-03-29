---
name: Modular function design principle
description: User wants micro-functions that each do ONE thing, composable for different UX flows - not monolithic multi-purpose functions
type: feedback
---

Functions must be micro and single-purpose. Never bundle multiple capabilities into one function.

**Why:** If a function does scoring + sentiment + task extraction + insight generation together, you can't call just sentiment analysis alone. Different UX flows need different subsets of capabilities. Monolithic functions waste compute on unused outputs.

**How to apply:** When designing AI/analysis pipelines, each atomic operation (embedding, sentiment, scoring, similarity, task extraction, summary generation) should be its own function. Pipeline callers compose only what they need. Import calls embed+sentiment+score. Detail page calls extract_tasks+generate_summary. Dashboard calls find_similar.