from django.utils import timezone


def calculate_relationship_score(contact):
    """Calculate relationship score from existing data (no AI call, <10ms).

    Updates contact.relationship_score, relationship_tier, etc. in-place and saves.
    """
    from contacts.models import Interaction  # noqa: F401
    from meetings.models import Meeting

    interactions = contact.interactions.all()
    interaction_count = interactions.count()

    # No data → gray
    if interaction_count == 0 and not contact.last_interaction_at:
        contact.relationship_tier = "gray"
        contact.relationship_score = 0
        contact.business_urgency_score = 0
        contact.closeness_score = 0
        contact.score_updated_at = timezone.now()
        contact.save(
            update_fields=[
                "relationship_score",
                "relationship_tier",
                "business_urgency_score",
                "closeness_score",
                "score_updated_at",
            ]
        )
        return

    now = timezone.now()

    # --- Business Urgency (0-100) ---
    urgency = 0

    # Recency factor (0-40): more recent = higher
    days = contact.days_since_contact or 999
    if days <= 3:
        urgency += 40
    elif days <= 7:
        urgency += 35
    elif days <= 14:
        urgency += 28
    elif days <= 30:
        urgency += 20
    elif days <= 60:
        urgency += 10
    elif days <= 90:
        urgency += 5

    # Upcoming meetings (0-30)
    upcoming = Meeting.objects.filter(
        contact=contact,
        fc=contact.fc,
        scheduled_at__gte=now,
        status=Meeting.Status.SCHEDULED,
    ).count()
    urgency += min(upcoming * 15, 30)

    # Recent interaction frequency (0-30): interactions in last 30 days
    thirty_days_ago = now - timezone.timedelta(days=30)
    recent_count = interactions.filter(created_at__gte=thirty_days_ago).count()
    urgency += min(recent_count * 6, 30)

    urgency = min(urgency, 100)

    # --- Closeness (0-100) ---
    closeness = 0

    # Total interaction volume (0-25)
    closeness += min(interaction_count * 3, 25)

    # Positive sentiment ratio (0-35)
    sentiments = list(
        interactions.exclude(sentiment="").values_list("sentiment", flat=True)
    )
    if sentiments:
        positive_ratio = sentiments.count("positive") / len(sentiments)
        closeness += int(positive_ratio * 35)
        # Penalty for negative
        negative_ratio = sentiments.count("negative") / len(sentiments)
        closeness -= int(negative_ratio * 15)

    # Meeting count (0-20): completed meetings show deeper relationship
    completed_meetings = Meeting.objects.filter(
        contact=contact,
        fc=contact.fc,
        status=Meeting.Status.COMPLETED,
    ).count()
    closeness += min(completed_meetings * 5, 20)

    # Contact longevity (0-20): how long have we known this person
    if contact.created_at:
        months_known = (now - contact.created_at).days / 30
        closeness += min(int(months_known * 4), 20)

    closeness = max(min(closeness, 100), 0)

    # --- Weighted Average ---
    score = urgency * 0.6 + closeness * 0.4

    # --- Tier Assignment ---
    if score >= 80:
        tier = "gold"
    elif score >= 60:
        tier = "green"
    elif score >= 40:
        tier = "yellow"
    elif score >= 20:
        tier = "red"
    else:
        tier = "gray"

    contact.relationship_score = round(score, 1)
    contact.relationship_tier = tier
    contact.business_urgency_score = round(urgency, 1)
    contact.closeness_score = round(closeness, 1)
    contact.score_updated_at = timezone.now()
    contact.save(
        update_fields=[
            "relationship_score",
            "relationship_tier",
            "business_urgency_score",
            "closeness_score",
            "score_updated_at",
        ]
    )
