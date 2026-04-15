# Design Audit: synco-product-intro.pptx

**Date:** 2026-04-11
**Target:** synco 제품 소개 프레젠테이션 (16 slides)
**Audience:** 고객사 채용담당자 (B2B)
**Tool:** Gemini multimodal + manual visual QA

---

## Scores

| Category | Grade | Notes |
|----------|-------|-------|
| Visual Hierarchy | **B** | Clear section numbering, dark/light rhythm works |
| Typography | **C+** | Georgia+Calibri pairing slightly dissonant for Korean |
| Color & Contrast | **B-** | Fixed: S1 description text contrast, S3 orange on blue |
| Spacing & Layout | **B** | Most slides well-organized, S9 pipeline/card count mismatch |
| AI Slop Detection | **A-** | Decorative blobs removed, geometric accents substituted |
| Cross-slide Consistency | **B+** | Header pattern, dark/light rhythm, card shadows consistent |
| **Overall** | **B** | |

---

## Findings & Fixes

| # | Slide | Issue | Impact | Fix | Status |
|---|-------|-------|--------|-----|--------|
| 1 | S1 | Description text (#94A3B8 on #1E2761) low contrast | High | Changed to #E8ECFD (lightBlue) | Verified |
| 2 | S1,S16 | Decorative blob circles — generic AI template trope | Medium | Replaced with geometric line accents | Verified |
| 3 | S3 | Orange numbers (#F97316) on transparent indigo — contrast risk | Medium | Darkened card background (#141E47, 30% transparency) | Verified |
| 4 | S8 | BLUE severity card text overlapping bottom stat cards | High | Reduced card height + spacing | Verified |
| 5 | S12 | "CONSULTANT" text wrapping to "CONSULTAN T" | Medium | Reduced font to 10pt | Verified |
| 6 | S9 | 5 pipeline stages vs 4 feature cards — grid mismatch | Polish | Noted (structural, would need content change) | Deferred |
| 7 | S14 | 7-color rainbow circles slightly diverge from main palette | Polish | Noted (intentional for workflow differentiation) | Deferred |

---

## Gemini Analysis Summary

### Strengths
- Avoids generic "SaaS card grid" pattern — varied layouts across slides
- Dark/light slide alternation creates visual rhythm
- Section numbering (01-11) provides clear navigation
- Content is specific to actual product features, not generic marketing copy
- KPI chart (S12) and pipeline flow (S9, S14) add visual variety

### Opportunities
- Font pairing: consider a geometric sans-serif for "synco" logo to better match Calibri
- S4 Before/After: could use structured field layout instead of text block
- S2 colored dots: could use semantic colors tied to severity (not random)
- Consider adding subtle product screenshots or UI mockups to feature slides

---

## Files Modified

- `/tmp/pptx-gen/generate-synco.js` — generation script
- `/home/work/synco/docs/designs/synco-product-intro.pptx` — output

## Status: DONE
