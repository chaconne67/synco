# P17 News Feed — Implementation Rulings

**Status:** COMPLETE
**Rounds:** 1
**Issues:** 14 (CRITICAL: 2, MAJOR: 9, MINOR: 3)
**Accepted:** 11 | **Rebutted:** 3 | **Escalated:** 0

---

## Accepted Items

### I-R1-02 [CRITICAL] Source deletion cascades to articles → Change to SET_NULL + nullable source
### I-R1-03 [MAJOR] No timeout/size controls in fetcher → Use httpx with timeout, redirect limit, content cap
### I-R1-04 [MAJOR] Digest ignores project relevance → Build digest from NewsArticleRelevance per recipient
### I-R1-05 [MAJOR] Dedupe not atomic → Use get_or_create in transaction.atomic()
### I-R1-06 [MAJOR] No cron installation task → Add deployment task with crontab file
### I-R1-07 [MAJOR] Sidebar dot checks all org news → Query via NewsArticleRelevance + user's projects
### I-R1-08 [MAJOR] No stale relevance cleanup → Delete below-threshold/closed-project rows in matcher
### I-R1-09 [MAJOR] Summarizer has no article content → Store RSS description in raw_content field
### I-R1-11 [MAJOR] _is_staff too restrictive → Check owner role (matches codebase convention)
### I-R1-13 [MINOR] Test assertion too loose → Use exact status code assertion
### I-R1-14 [MINOR] Should use parse_llm_json → Use existing utility from data_extraction

## Disputed Items (Author Rebutted)

### I-R1-01 [CRITICAL] Global URL unique vs org-scoped
- **Red team:** First org to fetch URL "owns" article, other orgs can't see it
- **Author:** Global URL uniqueness is correct (a URL is a real article). Visibility is already org-scoped via source FK. The fetcher handles existing articles gracefully with get_or_create. In practice, synco operates single-org. Multi-org dedup of the same public article is correct behavior.
- **Ruling:** Author rebuttal accepted. Global URL unique maintained; fetcher already idempotent.

### I-R1-10 [MAJOR] SSRF validation insufficient
- **Red team:** Full SSRF protection needed (DNS resolution, private IP blocking)
- **Author:** Already resolved in design D-R1-08. Basic scheme validation + timeout for admin-only internal tool. Consistent with design ruling.
- **Ruling:** Author rebuttal accepted. Consistent with design decision.

### I-R1-12 [MAJOR] Empty related articles header
- **Red team:** Empty section header renders when user has no assigned projects
- **Author:** Template already has `{% if related_articles %}` guard. Section only renders when articles exist.
- **Ruling:** Author rebuttal accepted. Template guard handles this case.
