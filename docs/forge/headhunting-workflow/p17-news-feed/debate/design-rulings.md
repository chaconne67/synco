# P17 News Feed — Design Rulings

**Status:** COMPLETE
**Rounds:** 1
**Issues:** 15 (CRITICAL: 2, MAJOR: 9, MINOR: 4)
**Accepted:** 13 | **Rebutted:** 2 | **Escalated:** 0

---

## Accepted Items

### D-R1-01 [CRITICAL] URL routing → Create `urls_news.py` with top-level `/news/` mount
### D-R1-02 [CRITICAL] Relevance storage → Normalized `NewsArticleRelevance` join model
### D-R1-03 [MAJOR] Org scoping → `organization` FK on NewsSource
### D-R1-04 [MAJOR] Pipeline atomicity → `summary_status` field + `transaction.atomic()` + `on_commit`
### D-R1-05 [MAJOR] Cron mechanism → Concrete crontab with flock, env, timezone
### D-R1-06 [MAJOR] feedparser dependency → `uv add feedparser`
### D-R1-07 [MAJOR] Category consistency → Machine enum in AI prompt + ECONOMY in UI
### D-R1-09 [MAJOR] Telegram delivery → Per-org/project recipient selection + dedupe
### D-R1-10 [MAJOR] Source type → `NewsSourceType` TextChoices, MVP RSS only
### D-R1-11 [MINOR] Dot indicator → `last_news_seen_at` on User
### D-R1-12 [MINOR] BaseModel → Explicit model skeletons
### D-R1-14 [MINOR] is_pinned → Removed, derive from relevance
### D-R1-15 [MINOR] Auth → `@login_required` + staff for source CRUD

## Disputed Items (Author Rebutted)

### D-R1-08 [MAJOR] SSRF risk
- **Red team:** Full SSRF protection (DNS resolution check, private IP blocking)
- **Author:** Basic scheme validation (http/https) + timeout. Full SSRF protection is over-engineering for admin-only internal tool.
- **Ruling:** Author rebuttal accepted. Basic validation sufficient for current deployment.

### D-R1-13 [MINOR] URL canonicalization
- **Red team:** Strip tracking params, canonical URL field for dedup
- **Author:** Premature optimization for Korean RSS feeds. feedparser link field adequate. Can add without schema change later.
- **Ruling:** Author rebuttal accepted. No schema change needed.
