"""Legacy functions to be replaced in Phase 3/6.
- analyze_contact_relationship → deep_analysis.py
- analyze_sentiments → sentiment.py (embedding-based)
"""

from django.utils import timezone

from common.claude import call_claude_json


def analyze_contact_relationship(contact):
    """Deep AI analysis of a single contact's relationship.

    LEGACY: Will be replaced by modular deep_analysis + orchestration in Phase 3.
    """
    from contacts.models import Task
    from intelligence.models import FortunateInsight, RelationshipAnalysis
    from meetings.models import Meeting

    interactions = list(
        contact.interactions.order_by("-created_at")[:30].values(
            "type", "summary", "sentiment", "created_at"
        )
    )
    meetings_data = list(
        Meeting.objects.filter(contact=contact, fc=contact.fc)
        .order_by("-scheduled_at")[:10]
        .values("title", "scheduled_at", "status", "location")
    )

    interaction_lines = []
    for i in interactions:
        date_str = i["created_at"].strftime("%Y-%m-%d")
        sentiment_str = f" [{i['sentiment']}]" if i["sentiment"] else ""
        interaction_lines.append(f"- {date_str} ({i['type']}{sentiment_str}): {i['summary'][:150]}")

    meeting_lines = []
    for m in meetings_data:
        date_str = m["scheduled_at"].strftime("%Y-%m-%d")
        meeting_lines.append(f"- {date_str} [{m['status']}]: {m['title']}")

    prompt = f"""아래 고객과 FC(보험설계사)의 관계를 분석해줘.

**고객 정보:**
- 이름: {contact.name}
- 회사: {contact.company_name}
- 업종: {contact.industry}
- 지역: {contact.region}
- 매출: {contact.revenue_range}
- 직원수: {contact.employee_count or '미상'}
- 메모: {(contact.memo or '')[:200]}

**인터랙션 이력 ({len(interactions)}건):**
{chr(10).join(interaction_lines) or '없음'}

**미팅 이력 ({len(meetings_data)}건):**
{chr(10).join(meeting_lines) or '없음'}

다음 JSON 형식으로 분석해줘:
{{
  "business_urgency": 0-100,
  "closeness": 0-100,
  "business_signals": {{
    "pending_actions": ["처리해야 할 사항들"],
    "opportunities": ["영업 기회"],
    "contract_status": "계약 상태 요약"
  }},
  "relationship_signals": {{
    "tone": "관계 톤 (친밀/비즈니스/소원)",
    "frequency_pattern": "접촉 패턴 요약",
    "key_topics": ["주요 대화 주제"]
  }},
  "pending_tasks": [
    {{"title": "해야 할 업무", "due": "YYYY-MM-DD 또는 null"}}
  ],
  "fortunate_insights": [
    {{"reason": "유망한 이유 설명", "type": "personal_event/promotion/business_opportunity"}}
  ],
  "summary": "한 문단 관계 요약"
}}

JSON으로만 응답해."""

    try:
        result = call_claude_json(prompt, timeout=120)
    except Exception:
        return None

    business = result.get("business_urgency", 50)
    close = result.get("closeness", 50)
    score = business * 0.6 + close * 0.4

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
    contact.business_urgency_score = round(business, 1)
    contact.closeness_score = round(close, 1)
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

    RelationshipAnalysis.objects.create(
        contact=contact,
        fc=contact.fc,
        business_signals=result.get("business_signals", {}),
        relationship_signals=result.get("relationship_signals", {}),
        ai_summary=result.get("summary", ""),
        extracted_tasks=result.get("pending_tasks", []),
        fortunate_insights=result.get("fortunate_insights", []),
    )

    for task_data in result.get("pending_tasks", []):
        title = task_data.get("title", "")
        if not title:
            continue
        due = task_data.get("due")
        Task.objects.get_or_create(
            fc=contact.fc,
            contact=contact,
            title=title,
            defaults={
                "due_date": due if due and due != "null" else None,
                "source": Task.Source.AI_EXTRACTED,
            },
        )

    for insight_data in result.get("fortunate_insights", []):
        reason = insight_data.get("reason", "")
        if not reason:
            continue
        FortunateInsight.objects.update_or_create(
            fc=contact.fc,
            contact=contact,
            defaults={
                "reason": reason,
                "signal_type": insight_data.get("type", ""),
            },
        )

    return result


def analyze_sentiments(memos: list[dict]) -> list[str]:
    """Analyze sentiment of multiple memos in one Claude call.

    LEGACY: Will be replaced by embedding-based classify_sentiments_batch in Phase 3.
    """
    if not memos:
        return []

    entries = "\n".join(f'{i + 1}. {m["text"][:100]}' for i, m in enumerate(memos))

    prompt = f"""아래 미팅/영업 메모들의 감정을 분석해줘.
각 메모가 비즈니스 관계에서 긍정적인지, 보통인지, 부정적인지 판단해.

판단 기준:
- positive: 관심 표현, 다음 미팅 약속, 계약 논의, 긍정적 반응
- neutral: 단순 안부, 정보 교환, 특별한 반응 없음, 통화만 함
- negative: 거절, 무관심, 취소, 차단

메모 목록:
{entries}

JSON 배열로만 응답. 형식: ["positive", "neutral", ...]
메모 개수({len(memos)}개)와 정확히 같은 수의 결과를 반환해."""

    return call_claude_json(prompt, timeout=90)
