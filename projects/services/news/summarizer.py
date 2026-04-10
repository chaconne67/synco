"""Gemini AI article summarizer — extracts summary, tags, and category."""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from google import genai

from data_extraction.services.extraction.sanitizers import parse_llm_json
from projects.models import NewsArticle, NewsCategory, SummaryStatus

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-preview-05-20"

VALID_CATEGORIES = {c.value for c in NewsCategory}

SUMMARIZE_PROMPT = """You are a Korean news article summarizer for a headhunting platform.

Given an article title (and optional content), produce a JSON response with:
- "summary": 2-3 sentence summary in Korean
- "tags": list of 3-7 Korean keyword strings relevant to hiring/HR industry
- "category": exactly one of "hiring" | "hr" | "industry" | "economy"

Rules:
- category MUST be one of the four exact English strings above
- summary MUST be in Korean
- tags MUST be Korean keywords
- Respond ONLY with valid JSON, no markdown fencing

Article title: {title}
Article content: {content}"""


def _get_gemini_client() -> genai.Client:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in settings")
    return genai.Client(api_key=api_key)


def summarize_article(article: NewsArticle) -> bool:
    """Summarize a single article with Gemini AI.

    Returns True on success, False on failure.
    Skips articles that are already COMPLETED.
    Uses raw_content as input (I-R1-09), parse_llm_json for parsing (I-R1-14).
    """
    if article.summary_status == SummaryStatus.COMPLETED:
        return True

    try:
        client = _get_gemini_client()
        # I-R1-09: Use raw_content as input to Gemini, not article.summary
        content = article.raw_content or article.title
        prompt = SUMMARIZE_PROMPT.format(
            title=article.title,
            content=content if content else "(no content available)",
        )

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                max_output_tokens=1000,
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )

        # I-R1-14: Use parse_llm_json instead of plain json.loads()
        parsed = parse_llm_json(response.text)
        if parsed is None:
            raise ValueError("parse_llm_json returned None")

        summary = parsed.get("summary", "")
        tags = parsed.get("tags", [])
        category = parsed.get("category", "")

        if category not in VALID_CATEGORIES:
            logger.warning(
                "Invalid category '%s' for article %s, defaulting to blank",
                category,
                article.pk,
            )
            category = ""

        with transaction.atomic():
            article.summary = summary
            article.tags = tags if isinstance(tags, list) else []
            article.category = category
            article.summary_status = SummaryStatus.COMPLETED
            article.save(
                update_fields=[
                    "summary", "tags", "category", "summary_status", "updated_at"
                ]
            )

        return True

    except (ValueError, KeyError) as e:
        logger.error("Failed to parse Gemini response for article %s: %s", article.pk, e)
        article.summary_status = SummaryStatus.FAILED
        article.save(update_fields=["summary_status", "updated_at"])
        return False

    except Exception:
        logger.exception("Gemini API error for article %s", article.pk)
        article.summary_status = SummaryStatus.FAILED
        article.save(update_fields=["summary_status", "updated_at"])
        return False
