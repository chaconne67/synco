import logging

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)

# Max interactions to process in ensure_sentiments_and_tasks (page load protection)
MAX_ENSURE_INTERACTIONS = 20


def ensure_embedding(contact):
    """Ensure contact has an embedding. Create if missing, skip if exists.

    Called from HTMX lazy-load endpoint — does not block main page render.
    Returns ContactEmbedding or None on failure.
    """
    from intelligence.models import ContactEmbedding

    if ContactEmbedding.objects.filter(contact=contact).exists():
        return ContactEmbedding.objects.get(contact=contact)

    from .embedding import embed_contact

    try:
        return embed_contact(contact)
    except Exception:
        logger.exception("ensure_embedding failed for contact %s", contact.pk)
        return None


def ensure_sentiments_and_tasks(contact) -> None:
    """Process unanalyzed interactions: sentiment classification + task detection.

    Target selection:
    - Sentiment: interactions with sentiment=""
    - Task: interactions with task_checked=False
    - Union of above for embedding generation (shared, one API call)

    Max 20 interactions per call. Excess retried on next page entry.
    """
    from contacts.models import Interaction

    from .sentiment import classify_sentiments_batch
    from .task_detect import detect_tasks_batch

    # Find interactions needing processing
    needs_sentiment = models.Q(sentiment="")
    needs_task = models.Q(task_checked=False)

    target_interactions = list(
        Interaction.objects.filter(contact=contact, fc=contact.fc)
        .filter(needs_sentiment | needs_task)
        .select_related("contact")
        .order_by("-created_at")[:MAX_ENSURE_INTERACTIONS]
    )

    if not target_interactions:
        return

    # Generate embeddings once for all targets
    from common.embedding import get_embeddings_batch

    try:
        texts = [i.summary for i in target_interactions]
        embeddings = get_embeddings_batch(texts)
    except Exception:
        logger.exception("ensure_sentiments_and_tasks: embedding generation failed")
        return  # Skip all — retry next time

    # Split into sentiment and task targets
    sentiment_targets = [i for i in target_interactions if not i.sentiment]
    task_targets = [i for i in target_interactions if not i.task_checked]

    # Build index mapping for embeddings
    interaction_to_idx = {i.pk: idx for idx, i in enumerate(target_interactions)}

    # Classify sentiments (only unprocessed)
    if sentiment_targets:
        sentiment_embs = [embeddings[interaction_to_idx[i.pk]] for i in sentiment_targets]
        try:
            classify_sentiments_batch(sentiment_targets, embeddings=sentiment_embs)
        except Exception:
            logger.exception("ensure_sentiments_and_tasks: sentiment classification failed")

    # Detect tasks (only unchecked)
    if task_targets:
        task_embs = [embeddings[interaction_to_idx[i.pk]] for i in task_targets]
        try:
            detect_tasks_batch(task_targets, embeddings=task_embs)
        except Exception:
            logger.exception("ensure_sentiments_and_tasks: task detection failed")


def ensure_deep_analysis(contact):
    """Ensure contact has a fresh RelationshipAnalysis. LLM call if stale/missing.

    Cache valid if:
    1. created_at within 24 hours
    2. AND no new interactions since analysis

    Returns RelationshipAnalysis or None.
    """
    from intelligence.models import RelationshipAnalysis

    from .deep_analysis import generate_insights, generate_summary

    now = timezone.now()
    twenty_four_hours_ago = now - timezone.timedelta(hours=24)

    analysis = (
        RelationshipAnalysis.objects.filter(contact=contact, fc=contact.fc)
        .order_by("-created_at")
        .first()
    )

    if analysis:
        # Check freshness
        is_recent = analysis.created_at >= twenty_four_hours_ago

        # Check if new interactions since analysis
        latest_interaction = (
            contact.interactions.order_by("-created_at").values_list("created_at", flat=True).first()
        )
        no_new_interactions = latest_interaction is None or latest_interaction < analysis.created_at

        if is_recent and no_new_interactions:
            return analysis  # Cache hit

    # Generate new analysis
    try:
        summary = generate_summary(contact)
        insights = generate_insights(contact)
    except Exception:
        logger.exception("ensure_deep_analysis: LLM failed for contact %s", contact.pk)
        return analysis  # Return stale if exists

    new_analysis = RelationshipAnalysis.objects.create(
        contact=contact,
        fc=contact.fc,
        ai_summary=summary,
        fortunate_insights=insights,
    )

    return new_analysis
